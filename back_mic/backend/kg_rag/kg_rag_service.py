# -*- coding: utf-8 -*-
"""KgRagService：编排 Step 1→5 全流程与检索/预览。"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("kg_rag")

# 确保可导入 ai_search（Claude 客户端）、retrieval、prompts
try:
    from ai_search.ai_service import claude_client
except ImportError:
    _backend = str(Path(__file__).resolve().parents[1])
    if _backend not in __import__("sys").path:
        __import__("sys").path.insert(0, _backend)
    try:
        from ai_search.ai_service import claude_client
    except ImportError:
        claude_client = None

from kg_rag.prompts import (
    STEP1_CONCEPT_EXTRACTION,
    STEP2_SKELETON_SCORING,
    QUERY_REWRITE,
    STEP5_GENERATION,
    STEP5_GENERATION_FLAT,
)

# QUERY_REWRITE 调用时传入 Claude 的 system，与 prompts 中说明一致
QUERY_REWRITE_SYSTEM = "你是一个资深的圣经研究学者，只输出 JSON，不输出其他任何内容。"
from kg_rag.retrieval import (
    bm25_search,
    dense_search,
    rrf_merge,
    rerank,
    skeleton_route_search,
)

DEFAULT_PARAMS = {
    "bm25_top_k": 30,
    "dense_top_k": 30,
    "num_candidates": 100,
    "rrf_k": 60,
    "bm25_weight": 1.0,
    "dense_weight": 1.0,
    "rerank_top_n": 20,
    "skeleton_route_top_k": 5,
    "temperature": 0.3,
    "skip_query_rewrite": False,
    "skip_skeleton_route": False,
    "skip_generation": False,
    "llm_model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
}

PATH_COUNT_THRESHOLD = 20  # 多概念路径数少于此则取全路径，否则 shortestPath + 单概念扩展


def _format_skeleton(skeleton: list[str] | None) -> str:
    """将 Step 2 输出的骨架维度列表格式化为可读文本。"""
    if not skeleton:
        return ""
    return "\n".join(f"{i + 1}. {str(x)}" for i, x in enumerate(skeleton) if str(x).strip())


def _format_chunks(chunks: list[dict]) -> str:
    """格式化段落列表为 Prompt 文本。"""
    out = []
    for c in chunks:
        chunk_id = c.get("chunk_id", "")
        book = c.get("book_title", "")
        msg = c.get("message_number", "")
        msg_title = c.get("message_title", "")
        sec = c.get("section_title", "")
        text = c.get("text", "")
        line1 = f"[{chunk_id}] {book}"
        if msg:
            line1 += f" 第{msg}篇"
        if msg_title:
            line1 += f" {msg_title}"
        if sec:
            line1 += f" {sec}"
        out.append(line1)
        out.append(text.strip() if text else "")
        out.append("---")
    return "\n".join(out)


def _format_expanded_chunks(chunks: list[dict]) -> str:
    """格式化扩展段落，标注来源概念。"""
    out = []
    for c in chunks:
        chunk_id = c.get("chunk_id", "")
        expanded_from = c.get("expanded_from", "")
        book = c.get("book_title", "")
        msg = c.get("message_number", "")
        msg_title = c.get("message_title", "")
        text = c.get("text", "")
        line1 = f"[{chunk_id}] (扩展自: {expanded_from}) {book}"
        if msg:
            line1 += f" 第{msg}篇"
        if msg_title:
            line1 += f" {msg_title}"
        out.append(line1)
        out.append(text.strip() if text else "")
        out.append("---")
    return "\n".join(out)


def _parse_json_array(text: str) -> list[Any]:
    """从 Claude 返回文本解析 JSON 数组，支持被截断的 JSON 修复。"""
    if not text or not text.strip():
        return []
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    try:
        arr = json.loads(s)
        return arr if isinstance(arr, list) else []
    except json.JSONDecodeError as e:
        logger.info(f"[KG-RAG DEBUG] _parse_json_array JSON parse error: {e} — text[:200]={s[:200]}")
        last_brace = s.rfind("}")
        if last_brace > 0:
            truncated = s[: last_brace + 1] + "]"
            try:
                arr = json.loads(truncated)
                if isinstance(arr, list):
                    logger.info(f"[KG-RAG DEBUG] _parse_json_array truncated recovery OK, got {len(arr)} items")
                    return arr
            except json.JSONDecodeError:
                pass
        return []


def _parse_step1_layers(text: str) -> tuple[list[str], list[str]]:
    """解析 Step 1 返回的 {"surface": [...], "deep": [...]}。失败时返回空数组。"""
    if not text or not text.strip():
        return ([], [])
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            return ([], [])
    except json.JSONDecodeError:
        return ([], [])
    surface_raw = obj.get("surface", [])
    deep_raw = obj.get("deep", [])
    surface = [str(x).strip() for x in surface_raw if str(x).strip()] if isinstance(surface_raw, list) else []
    deep = [str(x).strip() for x in deep_raw if str(x).strip()] if isinstance(deep_raw, list) else []
    return (surface[:3], deep[:3])


def _safe_parse_json(text: str) -> dict:
    """尽量稳健地解析 JSON 对象；失败返回空 dict。"""
    if not text or not text.strip():
        return {}
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        last_brace = s.rfind("}")
        if last_brace > 0:
            try:
                obj = json.loads(s[: last_brace + 1])
                return obj if isinstance(obj, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def _format_paths_text(paths: list[dict]) -> str:
    if not paths:
        return "暂无已知路径"
    lines = []
    for p in paths:
        from_name = p.get("from", "")
        relation = p.get("relation", "")
        to_name = p.get("to", "")
        via = p.get("via")
        hops = p.get("hops", "")
        if via:
            lines.append(f"{from_name} ──{relation}──► {to_name} （经由: {via}，{hops}跳）")
        else:
            lines.append(f"{from_name} ──{relation}──► {to_name} （{hops}跳）")
    return "\n".join(lines)


def _format_all_neighbors_text(all_neighbors: dict[str, list[dict]]) -> str:
    if not all_neighbors:
        return "暂无邻居关系"
    lines = []
    for concept, neighbors in all_neighbors.items():
        lines.append(f"【{concept}】的邻居：")
        if not neighbors:
            lines.append("（无）")
            continue
        for n in neighbors:
            rels = n.get("relations") or []
            rel_type = n.get("relation_type", "相关")
            neighbor = n.get("neighbor", "")
            if rels:
                for rel in rels:
                    lines.append(f"{rel} ({rel_type})")
            else:
                lines.append(f"{concept} ──{rel_type}──► {neighbor} ({rel_type})")
    return "\n".join(lines)


async def _call_claude(
    prompt: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    system: str | None = None,
) -> str:
    """
    封装 Claude API 调用。复用 ai_search 的 Claude 客户端（CLAUDE_API_KEY）。
    参考：back_mic/backend/ai_search/ai_service.py 第 177 行 claude_client、第 62-66 行 messages.create。
    """
    client = claude_client
    if not client:
        try:
            import anthropic
            api_key = os.environ.get("CLAUDE_API_KEY")
            client = anthropic.Anthropic(api_key=api_key) if api_key else None
        except Exception:
            client = None
    if not client:
        raise RuntimeError("Claude 客户端未配置（请设置 CLAUDE_API_KEY）")

    def _sync_create():
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "你是一位专业、精确的助手。请严格按要求的格式输出。",
            messages=[{"role": "user", "content": prompt}],
        )

    try:
        msg = await asyncio.to_thread(_sync_create)
    except Exception as e:
        print(f"[KG-RAG] Claude 调用失败: {e}")
        raise
    if not msg.content or not getattr(msg.content[0], "text", None):
        return ""
    return msg.content[0].text


class KgRagService:
    """KG-RAG 流水线编排：Step 1 概念抽取 → Step 2 骨架 → Step 3 三路检索 → Step 4 Prompt 构建 → Step 5 生成。"""

    def __init__(self, es_client: Any, neo4j_client: Any):
        """
        :param es_client: 已初始化的 Elasticsearch 实例
        :param neo4j_client: 已初始化的 Neo4jClient（可能 _available=False）
        """
        self.es = es_client
        self.neo4j = neo4j_client
        _DEFAULT_INDICES = ",".join([
            "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
            "kg-rag_others", "kg-rag_bib", "kg-rag_map_note",
            "kg-rag_7feasts", "kg-rag_pano", "kg-rag_dictionary",
        ])
        self.index = os.environ.get("KG_RAG_ES_INDEX", _DEFAULT_INDICES)

    async def full_query(self, query: str, params: dict | None = None) -> dict:
        """全流程：Step 1→2→3→4→5，返回最终回答与每步中间结果。"""
        p = {**DEFAULT_PARAMS, **(params or {})}
        result = {"query": query, "params": p, "steps": {}, "answer": None}

        # Step 1: 概念抽取
        concepts = []
        surface: list[str] = []
        deep: list[str] = []
        raw1 = ""
        try:
            concept_names = self.neo4j.get_concept_names()
            concept_list_text = "、".join(concept_names)
            step1_prompt = STEP1_CONCEPT_EXTRACTION.format(query=query, concept_list=concept_list_text)
            logger.info(f"[KG-RAG DEBUG] Step1 prompt (with concept list): {step1_prompt}")
            raw1 = await _call_claude(step1_prompt, p["llm_model"], temperature=0, max_tokens=500)
            surface, deep = _parse_step1_layers(raw1)
            logger.info(f"[KG-RAG DEBUG] Step 1 字面层: {surface}，深层: {deep}")
            concepts = []
            seen = set()
            for c in surface + deep:
                if c not in seen:
                    seen.add(c)
                    concepts.append(c)
        except Exception as e:
            result["steps"]["step1"] = {"concepts": [], "raw_response": "", "error": str(e)}
        if "step1" not in result["steps"]:
            result["steps"]["step1"] = {"concepts": concepts, "surface": surface, "deep": deep, "raw_response": raw1}

        # Step 1 直出概念，直接进入 Step 2
        normalized = concepts
        logger.info("[KG-RAG DEBUG] Step 1 done: concepts go directly to Step2")

        # Step 2: 统一骨架生成（一次收集关系 + 一次 LLM 筛选/构建）
        step2_start = asyncio.get_event_loop().time()
        skeleton = None
        expanded_nodes: list[str] = []
        paths: list[dict] = []
        valuable_neighbors: list[dict] = []
        all_neighbors: dict[str, list[dict]] = {}

        if not normalized or p.get("skip_skeleton_route"):
            logger.info("[KG-RAG DEBUG] Step2 skipped: no concepts or skip_skeleton_route=True")
        else:
            paths = self.neo4j.get_paths_between(normalized)
            for concept in normalized:
                neighbors = self.neo4j.get_neighbors(concept)
                if neighbors:
                    all_neighbors[concept] = neighbors

            if not paths and not all_neighbors:
                logger.info("[KG-RAG DEBUG] Step2 graph empty: no paths and no neighbors")
            else:
                try:
                    paths_text = _format_paths_text(paths)
                    all_neighbors_text = _format_all_neighbors_text(all_neighbors)
                    step2_prompt = STEP2_SKELETON_SCORING.format(
                        query=query,
                        concepts_json=json.dumps(normalized, ensure_ascii=False),
                        paths_text=paths_text,
                        all_neighbors_text=all_neighbors_text,
                    )
                    raw2 = await _call_claude(step2_prompt, p["llm_model"], temperature=0, max_tokens=4096)
                    logger.info(f"[KG-RAG DEBUG] Step2 single LLM raw response: {raw2[:1000]}")
                    parsed = _safe_parse_json(raw2)

                    raw_valuable = parsed.get("valuable_neighbors", [])
                    if isinstance(raw_valuable, list):
                        for item in raw_valuable[:8]:
                            if not isinstance(item, dict):
                                continue
                            nb = str(item.get("neighbor", "")).strip()
                            if not nb:
                                continue
                            valuable_neighbors.append({
                                "neighbor": nb,
                                "relation": str(item.get("relation", "")).strip(),
                                "reason": str(item.get("reason", "")).strip(),
                            })

                    sk = parsed.get("skeleton")
                    skeleton = sk if isinstance(sk, list) else None

                    deep_concepts = deep
                    valuable_names = [v["neighbor"] for v in valuable_neighbors if v.get("neighbor")]
                    seen_nodes = set()
                    for name in deep_concepts + valuable_names:
                        if name not in seen_nodes:
                            seen_nodes.add(name)
                            expanded_nodes.append(name)
                except Exception as e:
                    logger.info(f"[KG-RAG DEBUG] Step2 unified EXCEPTION: {e}")
                    result["steps"]["step2_error"] = str(e)

        step2_end = asyncio.get_event_loop().time()
        logger.info(
            f"[KG-RAG DEBUG] Step2 done: llm_calls={'1' if (paths or all_neighbors) and normalized and not p.get('skip_skeleton_route') else '0'}, "
            f"paths={len(paths)}, valuable_neighbors={len(valuable_neighbors)}, expanded_nodes={len(expanded_nodes)}, "
            f"skeleton={'yes' if skeleton else 'no'}, elapsed_ms={(step2_end - step2_start) * 1000:.1f}"
        )
        result["steps"]["step2"] = {
            "paths": paths,
            "valuable_neighbors": valuable_neighbors,
            "skeleton": skeleton,
            "expanded_nodes": expanded_nodes,
            "all_neighbors": all_neighbors,
            **({"skipped": True} if (not normalized or p.get("skip_skeleton_route")) else {}),
        }

        # Step 3: 三路检索
        if p.get("skip_query_rewrite"):
            rewritten_queries = [query]
        else:
            try:
                rewrite_prompt = QUERY_REWRITE.format(query=query)
                raw_rewrite = (await _call_claude(rewrite_prompt, p["llm_model"], temperature=0, max_tokens=300)).strip()
                parsed = _parse_json_array(raw_rewrite)
                rewritten_queries = [str(q).strip() for q in parsed if str(q).strip()] if parsed else [query]
                if not rewritten_queries:
                    rewritten_queries = [query]
            except Exception:
                rewritten_queries = [query]

        bm25_task = bm25_search(self.es, query, self.index, p["bm25_top_k"])
        dense_tasks = [
            dense_search(self.es, rq, self.index, p["dense_top_k"], p["num_candidates"])
            for rq in rewritten_queries
        ]
        route3_tasks = []
        if expanded_nodes and not p.get("skip_skeleton_route"):
            route3_tasks = [
                skeleton_route_search(self.es, node, query, self.index, p["skeleton_route_top_k"])
                for node in expanded_nodes
            ]
        results = await asyncio.gather(bm25_task, *dense_tasks, *route3_tasks)
        bm25_results = results[0]
        dense_results_all = list(results[1: 1 + len(dense_tasks)])
        route3_all = list(results[1 + len(dense_tasks):]) if route3_tasks else []

        # 多路 Dense 结果合并去重（按 chunk_id，保留最高分）
        dense_merged: dict[str, dict] = {}
        for hits in dense_results_all:
            for doc in hits:
                cid = doc.get("chunk_id", "")
                if cid not in dense_merged or doc.get("score", 0) > dense_merged[cid].get("score", 0):
                    dense_merged[cid] = doc
        dense_results = list(dense_merged.values())

        merged = await rrf_merge(bm25_results, dense_results, p["rrf_k"], p["bm25_weight"], p["dense_weight"])
        main_results = await rerank(merged, query, p["rerank_top_n"])

        expanded_results = []
        if route3_all:
            main_ids = {r.get("chunk_id") for r in main_results}
            for i, _node in enumerate(expanded_nodes):
                node_hits = route3_all[i] if i < len(route3_all) else []
                unique_hits = [r for r in node_hits if r.get("chunk_id") not in main_ids]
                expanded_results.extend(unique_hits[:2])

        result["steps"]["step3"] = {
            "rewritten_queries": rewritten_queries,
            "bm25_count": len(bm25_results),
            "dense_count": len(dense_results),
            "rrf_count": len(merged),
            "main_results": main_results,
            "expanded_results": expanded_results,
            "bm25_results": bm25_results,
            "dense_results": dense_results,
        }

        # Step 4: Prompt 构建
        if skeleton:
            skeleton_text = _format_skeleton(skeleton)
            main_chunks_text = _format_chunks(main_results)
            expanded_chunks_text = _format_expanded_chunks(expanded_results)
            prompt = STEP5_GENERATION.format(
                query=query,
                skeleton=skeleton_text,
                main_chunks=main_chunks_text,
                expanded_chunks=expanded_chunks_text,
            )
            prompt_type = "skeleton"
        else:
            all_chunks = main_results + expanded_results
            chunks_text = _format_chunks(all_chunks)
            prompt = STEP5_GENERATION_FLAT.format(query=query, chunks=chunks_text)
            prompt_type = "flat"
        result["steps"]["step4"] = {"prompt": prompt, "prompt_type": prompt_type, "token_estimate": len(prompt) // 4}

        # Step 5: 生成
        if p.get("skip_generation"):
            result["steps"]["step5"] = {"skipped": True}
            return result
        try:
            gen = await _call_claude(prompt, p["llm_model"], temperature=p["temperature"], max_tokens=4096, system=None)
            result["answer"] = gen.strip() if gen else None
            result["steps"]["step5"] = {"answer": result["answer"], "model": p["llm_model"]}
        except Exception as e:
            result["steps"]["step5"] = {"error": str(e)}
            result["answer"] = None
        return result

    async def search_only(self, query: str, params: dict | None = None) -> dict:
        """仅执行 Step 1→3，返回检索结果，不含 step4、step5。"""
        p = {**DEFAULT_PARAMS, **(params or {})}
        result = {"query": query, "params": p, "steps": {}}

        concepts = []
        surface: list[str] = []
        deep: list[str] = []
        try:
            concept_names = self.neo4j.get_concept_names()
            concept_list_text = "、".join(concept_names)
            step1_prompt = STEP1_CONCEPT_EXTRACTION.format(query=query, concept_list=concept_list_text)
            logger.info(f"[KG-RAG DEBUG] Step1 prompt (with concept list): {step1_prompt}")
            raw1 = await _call_claude(step1_prompt, p["llm_model"], temperature=0, max_tokens=500)
            surface, deep = _parse_step1_layers(raw1)
            logger.info(f"[KG-RAG DEBUG] Step 1 字面层: {surface}，深层: {deep}")
            concepts = []
            seen = set()
            for c in surface + deep:
                if c not in seen:
                    seen.add(c)
                    concepts.append(c)
        except Exception as e:
            result["steps"]["step1"] = {"concepts": [], "error": str(e)}
        if "step1" not in result["steps"]:
            result["steps"]["step1"] = {"concepts": concepts, "surface": surface, "deep": deep}

        # Step 1 直出概念，直接进入 Step 2
        normalized = concepts
        logger.info("[KG-RAG DEBUG] Step 1 done: concepts go directly to Step2")

        step2_start = asyncio.get_event_loop().time()
        skeleton = None
        expanded_nodes: list[str] = []
        paths: list[dict] = []
        valuable_neighbors: list[dict] = []
        all_neighbors: dict[str, list[dict]] = {}

        if not normalized or p.get("skip_skeleton_route"):
            logger.info("[KG-RAG DEBUG] Step2 skipped: no concepts or skip_skeleton_route=True")
        else:
            paths = self.neo4j.get_paths_between(normalized)
            for concept in normalized:
                neighbors = self.neo4j.get_neighbors(concept)
                if neighbors:
                    all_neighbors[concept] = neighbors

            if not paths and not all_neighbors:
                logger.info("[KG-RAG DEBUG] Step2 graph empty: no paths and no neighbors")
            else:
                try:
                    paths_text = _format_paths_text(paths)
                    all_neighbors_text = _format_all_neighbors_text(all_neighbors)
                    step2_prompt = STEP2_SKELETON_SCORING.format(
                        query=query,
                        concepts_json=json.dumps(normalized, ensure_ascii=False),
                        paths_text=paths_text,
                        all_neighbors_text=all_neighbors_text,
                    )
                    raw2 = await _call_claude(step2_prompt, p["llm_model"], temperature=0, max_tokens=4096)
                    parsed2 = _safe_parse_json(raw2)
                    raw_valuable = parsed2.get("valuable_neighbors", [])
                    if isinstance(raw_valuable, list):
                        for item in raw_valuable[:8]:
                            if not isinstance(item, dict):
                                continue
                            nb = str(item.get("neighbor", "")).strip()
                            if not nb:
                                continue
                            valuable_neighbors.append({
                                "neighbor": nb,
                                "relation": str(item.get("relation", "")).strip(),
                                "reason": str(item.get("reason", "")).strip(),
                            })
                    sk = parsed2.get("skeleton")
                    skeleton = sk if isinstance(sk, list) else None

                    deep_concepts = deep
                    valuable_names = [v["neighbor"] for v in valuable_neighbors if v.get("neighbor")]
                    seen_nodes = set()
                    for name in deep_concepts + valuable_names:
                        if name not in seen_nodes:
                            seen_nodes.add(name)
                            expanded_nodes.append(name)
                except Exception as e:
                    logger.info(f"[KG-RAG DEBUG] Step2 unified EXCEPTION: {e}")
                    result["steps"]["step2_error"] = str(e)

        step2_end = asyncio.get_event_loop().time()
        logger.info(
            f"[KG-RAG DEBUG] Step2 done: llm_calls={'1' if (paths or all_neighbors) and normalized and not p.get('skip_skeleton_route') else '0'}, "
            f"paths={len(paths)}, valuable_neighbors={len(valuable_neighbors)}, expanded_nodes={len(expanded_nodes)}, "
            f"skeleton={'yes' if skeleton else 'no'}, elapsed_ms={(step2_end - step2_start) * 1000:.1f}"
        )
        result["steps"]["step2"] = {
            "paths": paths,
            "valuable_neighbors": valuable_neighbors,
            "skeleton": skeleton,
            "expanded_nodes": expanded_nodes,
            "all_neighbors": all_neighbors,
            **({"skipped": True} if (not normalized or p.get("skip_skeleton_route")) else {}),
        }

        if p.get("skip_query_rewrite"):
            rewritten_queries = [query]
            dense_rqs = [query]
        else:
            try:
                raw_rw = (
                    await _call_claude(
                        QUERY_REWRITE.format(query=query),
                        p["llm_model"],
                        temperature=0,
                        max_tokens=300,
                        system=QUERY_REWRITE_SYSTEM,
                    )
                ).strip()
                parsed = _parse_json_array(raw_rw)
                rewritten_queries = [str(q).strip() for q in parsed if str(q).strip()] if parsed else [query]
                if not rewritten_queries:
                    rewritten_queries = [query]
            except Exception:
                rewritten_queries = [query]
            lines4 = list(rewritten_queries[:4])
            while len(lines4) < 4:
                lines4.append(query)
            dense_rqs = [query] + lines4[:4]

        bm25_task = bm25_search(self.es, query, self.index, p["bm25_top_k"])
        dense_tasks = [
            dense_search(self.es, rq, self.index, p["dense_top_k"], p["num_candidates"])
            for rq in dense_rqs
        ]
        route3_tasks = []
        if expanded_nodes and not p.get("skip_skeleton_route"):
            route3_tasks = [
                skeleton_route_search(self.es, node, query, self.index, p["skeleton_route_top_k"])
                for node in expanded_nodes
            ]
        if len(dense_rqs) == 5:
            logger.info(
                "[KG-RAG DEBUG] search_only Step3: 5-way concurrent dense "
                "(theme + 启示/真理/经历/应用), asyncio.gather + chunk_id dedupe"
            )
        else:
            logger.info(
                f"[KG-RAG DEBUG] search_only Step3: {len(dense_rqs)}-way dense "
                f"(skip_query_rewrite or fallback), asyncio.gather + chunk_id dedupe"
            )
        results = await asyncio.gather(bm25_task, *dense_tasks, *route3_tasks)
        bm25_results = results[0]
        dense_results_all = list(results[1: 1 + len(dense_tasks)])
        route3_all = list(results[1 + len(dense_tasks):]) if route3_tasks else []

        dense_merged: dict[str, dict] = {}
        for hits in dense_results_all:
            for doc in hits:
                cid = doc.get("chunk_id", "")
                if cid not in dense_merged or doc.get("score", 0) > dense_merged[cid].get("score", 0):
                    dense_merged[cid] = doc
        dense_results = list(dense_merged.values())

        merged = await rrf_merge(bm25_results, dense_results, p["rrf_k"], p["bm25_weight"], p["dense_weight"])
        main_results = await rerank(merged, query, p["rerank_top_n"])
        expanded_results = []
        if route3_all:
            main_ids = {r.get("chunk_id") for r in main_results}
            for i, _node in enumerate(expanded_nodes):
                node_hits = route3_all[i] if i < len(route3_all) else []
                unique_hits = [r for r in node_hits if r.get("chunk_id") not in main_ids]
                expanded_results.extend(unique_hits[:2])
        result["steps"]["step3"] = {
            "rewritten_queries": rewritten_queries,
            "dense_queries": dense_rqs,
            "bm25_count": len(bm25_results),
            "dense_count": len(dense_results),
            "rrf_count": len(merged),
            "main_results": main_results,
            "expanded_results": expanded_results,
            "bm25_results": bm25_results,
            "dense_results": dense_results,
        }
        return result

    async def build_prompt_preview(self, query: str, params: dict | None = None) -> dict:
        """执行 Step 1→4，返回构建好的 Prompt，不执行 Step 5。"""
        full = await self.full_query(query, {**(params or {}), "skip_generation": True})
        full["steps"].pop("step5", None)
        full["answer"] = None
        return full
