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
    "skeleton_score_threshold": 0.5,
    "skeleton_top_n": 5,
    "skeleton_route_top_k": 5,
    "temperature": 0.3,
    "skip_query_rewrite": False,
    "skip_generation": False,
    "llm_model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
}

PATH_COUNT_THRESHOLD = 20  # 多概念路径数少于此则取全路径，否则 shortestPath + 单概念扩展


def _format_skeleton(skeleton: dict | None) -> str:
    """将骨架格式化为可读文本，优先使用带方向的 relation_str；无则用 relation_type 不带方向箭头。"""
    if not skeleton:
        return ""
    lines = []
    if "root" in skeleton and "branches" in skeleton:
        root = skeleton.get("root", "")
        for b in skeleton.get("branches", []):
            score = b.get("score", 0)
            relation_str = b.get("relation_str", "")
            if relation_str:
                lines.append(f"{relation_str} ({score})")
            else:
                name = b.get("name", "")
                rel = b.get("relation_type", "相关")
                lines.append(f"{root} —[{rel}]— {name} ({score})")
    elif "roots" in skeleton and "branches" in skeleton:
        for b in skeleton.get("branches", []):
            score = b.get("score", 0)
            relation_str = b.get("relation_str", "")
            if relation_str:
                lines.append(f"{relation_str} ({score})")
            else:
                root = b.get("root", "")
                name = b.get("name", "")
                rel = b.get("relation_type", "相关")
                lines.append(f"{root} —[{rel}]— {name} ({score})")
    return "\n".join(lines)


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


def _parse_skeleton_scores(text: str) -> list[dict]:
    """解析 Step 2 返回的 [{\"name\": \"...\", \"score\": ...}]。"""
    arr = _parse_json_array(text)
    out = []
    for x in arr:
        if isinstance(x, dict) and x.get("name") is not None:
            try:
                out.append({"name": str(x["name"]).strip(), "score": float(x.get("score", 0))})
            except (TypeError, ValueError):
                pass
    return out


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
    """KG-RAG 流水线编排：Step 1 概念抽取 → 1.5 规范化 → Step 2 骨架 → Step 3 三路检索 → Step 4 Prompt 构建 → Step 5 生成。"""

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
        ])
        self.index = os.environ.get("KG_RAG_ES_INDEX", _DEFAULT_INDICES)

    async def full_query(self, query: str, params: dict | None = None) -> dict:
        """全流程：Step 1→1.5→2→3→4→5，返回最终回答与每步中间结果。"""
        p = {**DEFAULT_PARAMS, **(params or {})}
        result = {"query": query, "params": p, "steps": {}, "answer": None}

        # Step 1: 概念抽取
        concepts = []
        raw1 = ""
        try:
            step1_prompt = STEP1_CONCEPT_EXTRACTION.format(query=query)
            raw1 = await _call_claude(step1_prompt, p["llm_model"], temperature=0, max_tokens=500)
            concepts = _parse_json_array(raw1)
            if isinstance(concepts, list):
                concepts = [str(x).strip() for x in concepts if str(x).strip()][:3]
            else:
                concepts = []
        except Exception as e:
            result["steps"]["step1"] = {"concepts": [], "raw_response": "", "error": str(e)}
        if "step1" not in result["steps"]:
            result["steps"]["step1"] = {"concepts": concepts, "raw_response": raw1}

        # Step 1.5: 概念规范化
        normalized = self.neo4j.normalize_concepts(concepts) if concepts else []
        dropped = [c for c in concepts if not (self.neo4j.normalize_concepts([c]))] if concepts else []
        result["steps"]["step1_5"] = {"input": concepts, "normalized": normalized, "dropped": dropped}

        # Step 2: 骨架生成
        skeleton = None
        expanded_nodes = []
        if normalized:
            if len(normalized) == 1:
                root = normalized[0]
                neighbors = self.neo4j.get_neighbors(root)
                logger.info(f"[KG-RAG DEBUG] Step2 single root={root}, neighbors count={len(neighbors)}")
                if not neighbors:
                    skeleton = {"root": root, "branches": []}
                else:
                    try:
                        neighbors_for_llm = [
                            {
                                "neighbor": n["neighbor"],
                                "relation": " ／ ".join(n["relations"]),
                            }
                            for n in neighbors
                        ]
                        step2_prompt = STEP2_SKELETON_SCORING.format(
                            query=query,
                            concept_name=root,
                            neighbors_json=json.dumps(neighbors_for_llm, ensure_ascii=False),
                        )
                        raw2 = await _call_claude(step2_prompt, p["llm_model"], temperature=0, max_tokens=4096)
                        logger.info(f"[KG-RAG DEBUG] Step2 single LLM raw response (root={root}): {raw2[:500]}")
                        scored = _parse_skeleton_scores(raw2)
                        logger.info(f"[KG-RAG DEBUG] Step2 single LLM scored (root={root}): {scored}")
                        by_name = {n["neighbor"]: n["relation_type"] for n in neighbors}
                        filtered = [s for s in scored if s["score"] >= p["skeleton_score_threshold"]]
                        logger.info(f"[KG-RAG DEBUG] Step2 single after threshold>={p['skeleton_score_threshold']}: {len(filtered)} remain — {filtered}")
                        filtered.sort(key=lambda x: x["score"], reverse=True)
                        top_n = filtered[: p["skeleton_top_n"]]
                        logger.info(f"[KG-RAG DEBUG] Step2 single top-{p['skeleton_top_n']}: {[x['name'] for x in top_n]}")
                        branches = [
                            {
                                "name": x["name"],
                                "relation_type": by_name.get(x["name"], "相关"),
                                "relation_str": " ／ ".join(
                                    next((n["relations"] for n in neighbors if n["neighbor"] == x["name"]), [])
                                ),
                                "score": x["score"],
                            }
                            for x in top_n
                        ]
                        skeleton = {"root": root, "branches": branches}
                        expanded_nodes = [b["name"] for b in branches]
                        logger.info(f"[KG-RAG DEBUG] Step2 single expanded_nodes: {expanded_nodes}")
                    except Exception as e:
                        logger.info(f"[KG-RAG DEBUG] Step2 single EXCEPTION root={root}: {e}")
                        result["steps"]["step2_error"] = str(e)
                        skeleton = {"root": root, "branches": []}
            else:
                all_branches = []
                for root in normalized:
                    neighbors = self.neo4j.get_neighbors(root)
                    logger.info(f"[KG-RAG DEBUG] Step2 multi root={root}, neighbors count={len(neighbors)}")
                    if not neighbors:
                        continue
                    try:
                        neighbors_for_llm = [
                            {
                                "neighbor": n["neighbor"],
                                "relation": " ／ ".join(n["relations"]),
                            }
                            for n in neighbors
                        ]
                        step2_prompt = STEP2_SKELETON_SCORING.format(
                            query=query,
                            concept_name=root,
                            neighbors_json=json.dumps(neighbors_for_llm, ensure_ascii=False),
                        )
                        raw2 = await _call_claude(step2_prompt, p["llm_model"], temperature=0, max_tokens=4096)
                        logger.info(f"[KG-RAG DEBUG] Step2 multi LLM raw response (root={root}): {raw2[:500]}")
                        scored = _parse_skeleton_scores(raw2)
                        logger.info(f"[KG-RAG DEBUG] Step2 multi LLM scored (root={root}): {scored}")
                        by_name = {n["neighbor"]: n["relation_type"] for n in neighbors}
                        filtered = [s for s in scored if s["score"] >= p["skeleton_score_threshold"]]
                        logger.info(f"[KG-RAG DEBUG] Step2 multi after threshold>={p['skeleton_score_threshold']} (root={root}): {len(filtered)} remain — {filtered}")
                        filtered.sort(key=lambda x: x["score"], reverse=True)
                        top_n = filtered[: p["skeleton_top_n"]]
                        logger.info(f"[KG-RAG DEBUG] Step2 multi top-{p['skeleton_top_n']} (root={root}): {[x['name'] for x in top_n]}")
                        for x in top_n:
                            all_branches.append({
                                "root": root,
                                "name": x["name"],
                                "relation_type": by_name.get(x["name"], "相关"),
                                "relation_str": " ／ ".join(
                                    next((n["relations"] for n in neighbors if n["neighbor"] == x["name"]), [])
                                ),
                                "score": x["score"],
                            })
                    except Exception as e:
                        logger.info(f"[KG-RAG DEBUG] Step2 multi EXCEPTION root={root}: {e}")
                expanded_nodes = list({b["name"] for b in all_branches if b["name"] not in normalized})
                logger.info(f"[KG-RAG DEBUG] Step2 multi expanded_nodes: {expanded_nodes}")
                skeleton = {"roots": normalized, "branches": all_branches} if all_branches else {"root": normalized[0], "branches": []}
        has_branches = bool(skeleton and skeleton.get("branches"))
        mode = "skeleton" if has_branches else "flat"
        logger.info(f"[KG-RAG DEBUG] Step2 final — skeleton empty={not has_branches}, mode={mode}, expanded_nodes={expanded_nodes}")
        result["steps"]["step2"] = {"skeleton": skeleton, "expanded_nodes": expanded_nodes}

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
        results = await asyncio.gather(bm25_task, *dense_tasks)
        bm25_results = results[0]
        dense_results_all = list(results[1:])

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
        if expanded_nodes:
            route3_tasks = [
                skeleton_route_search(self.es, node, query, self.index, p["skeleton_route_top_k"])
                for node in expanded_nodes
            ]
            route3_all = await asyncio.gather(*route3_tasks)
            for hits in route3_all:
                expanded_results.extend(hits)
            main_ids = {r.get("chunk_id") for r in main_results}
            expanded_results = [r for r in expanded_results if r.get("chunk_id") not in main_ids]

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
        try:
            step1_prompt = STEP1_CONCEPT_EXTRACTION.format(query=query)
            raw1 = await _call_claude(step1_prompt, p["llm_model"], temperature=0, max_tokens=500)
            concepts = _parse_json_array(raw1)
            if isinstance(concepts, list):
                concepts = [str(x).strip() for x in concepts if str(x).strip()][:3]
            else:
                concepts = []
        except Exception as e:
            result["steps"]["step1"] = {"concepts": [], "error": str(e)}
        if "step1" not in result["steps"]:
            result["steps"]["step1"] = {"concepts": concepts}

        normalized = self.neo4j.normalize_concepts(concepts) if concepts else []
        dropped = [c for c in concepts if not (self.neo4j.normalize_concepts([c]))] if concepts else []
        result["steps"]["step1_5"] = {"input": concepts, "normalized": normalized, "dropped": dropped}

        skeleton = None
        expanded_nodes = []
        if normalized:
            if len(normalized) == 1:
                root = normalized[0]
                neighbors = self.neo4j.get_neighbors(root)
                if not neighbors:
                    skeleton = {"root": root, "branches": []}
                else:
                    try:
                        neighbors_for_llm = [
                            {
                                "neighbor": n["neighbor"],
                                "relation": " ／ ".join(n["relations"]),
                            }
                            for n in neighbors
                        ]
                        step2_prompt = STEP2_SKELETON_SCORING.format(
                            query=query,
                            concept_name=root,
                            neighbors_json=json.dumps(neighbors_for_llm, ensure_ascii=False),
                        )
                        raw2 = await _call_claude(step2_prompt, p["llm_model"], temperature=0, max_tokens=4096)
                        scored = _parse_skeleton_scores(raw2)
                        by_name = {n["neighbor"]: n["relation_type"] for n in neighbors}
                        filtered = [s for s in scored if s["score"] >= p["skeleton_score_threshold"]]
                        filtered.sort(key=lambda x: x["score"], reverse=True)
                        branches = [
                            {
                                "name": x["name"],
                                "relation_type": by_name.get(x["name"], "相关"),
                                "relation_str": " ／ ".join(
                                    next((n["relations"] for n in neighbors if n["neighbor"] == x["name"]), [])
                                ),
                                "score": x["score"],
                            }
                            for x in filtered[: p["skeleton_top_n"]]
                        ]
                        skeleton = {"root": root, "branches": branches}
                        expanded_nodes = [b["name"] for b in branches]
                    except Exception:
                        skeleton = {"root": root, "branches": []}
            else:
                all_branches = []
                for root in normalized:
                    neighbors = self.neo4j.get_neighbors(root)
                    if not neighbors:
                        continue
                    try:
                        neighbors_for_llm = [
                            {
                                "neighbor": n["neighbor"],
                                "relation": " ／ ".join(n["relations"]),
                            }
                            for n in neighbors
                        ]
                        step2_prompt = STEP2_SKELETON_SCORING.format(
                            query=query,
                            concept_name=root,
                            neighbors_json=json.dumps(neighbors_for_llm, ensure_ascii=False),
                        )
                        raw2 = await _call_claude(step2_prompt, p["llm_model"], temperature=0, max_tokens=4096)
                        scored = _parse_skeleton_scores(raw2)
                        by_name = {n["neighbor"]: n["relation_type"] for n in neighbors}
                        filtered = [s for s in scored if s["score"] >= p["skeleton_score_threshold"]]
                        filtered.sort(key=lambda x: x["score"], reverse=True)
                        for x in filtered[: p["skeleton_top_n"]]:
                            all_branches.append({
                                "root": root,
                                "name": x["name"],
                                "relation_type": by_name.get(x["name"], "相关"),
                                "relation_str": " ／ ".join(
                                    next((n["relations"] for n in neighbors if n["neighbor"] == x["name"]), [])
                                ),
                                "score": x["score"],
                            })
                    except Exception:
                        pass
                expanded_nodes = list({b["name"] for b in all_branches if b["name"] not in normalized})
                skeleton = {"roots": normalized, "branches": all_branches} if all_branches else {"root": normalized[0], "branches": []}
        result["steps"]["step2"] = {"skeleton": skeleton, "expanded_nodes": expanded_nodes}

        if p.get("skip_query_rewrite"):
            rewritten_query = query
        else:
            try:
                rewritten_query = (await _call_claude(QUERY_REWRITE.format(query=query), p["llm_model"], temperature=0, max_tokens=300)).strip() or query
            except Exception:
                rewritten_query = query
        bm25_results, dense_results = await asyncio.gather(
            bm25_search(self.es, query, self.index, p["bm25_top_k"]),
            dense_search(self.es, rewritten_query, self.index, p["dense_top_k"], p["num_candidates"]),
        )
        merged = await rrf_merge(bm25_results, dense_results, p["rrf_k"], p["bm25_weight"], p["dense_weight"])
        main_results = await rerank(merged, query, p["rerank_top_n"])
        expanded_results = []
        if expanded_nodes:
            route3_all = await asyncio.gather(*[
                skeleton_route_search(self.es, node, query, self.index, p["skeleton_route_top_k"])
                for node in expanded_nodes
            ])
            for hits in route3_all:
                expanded_results.extend(hits)
            main_ids = {r.get("chunk_id") for r in main_results}
            expanded_results = [r for r in expanded_results if r.get("chunk_id") not in main_ids]
        result["steps"]["step3"] = {
            "rewritten_query": rewritten_query,
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
