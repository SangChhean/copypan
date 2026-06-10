# -*- coding: utf-8 -*-
"""PanAI 2.0 练习：检索 + Claude 生成纲目。"""
import asyncio
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from back_shared.format_utils.format_outline import format_and_download

from back_shared.retrieval import bm25_search, dense_search, rerank, rrf_merge

from .prompts import STEP5_GENERATION_FLAT

_ENV_PATH = Path(__file__).resolve().parents[3] / "back_mic" / "backend" / ".env"
load_dotenv(_ENV_PATH)

es = Elasticsearch(["http://localhost:9200"], basic_auth=("elastic", "qwSD4AF2Dcv"))
INDEX_NAME = "philippians-practice"

router = APIRouter(prefix="/api/practice/kg_rag")


class KgRagRequest(BaseModel):
    query: str = Field(..., min_length=1, description="纲目主题")
    outline_nature: str = Field("一般性", description="纲目性质")
    burden_description: str = Field("", description="负担说明")


class FormatDownloadRequest(BaseModel):
    text: str
    direction: str   # 'zh' | 'zh_tw' | 'en' | 'es'
    output_format: str = 'docx'  # 'docx' | 'pdf'


def format_chunks(chunks: list[dict]) -> str:
    """格式化 rerank 后的 chunks，供 Prompt 使用。"""
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


def _build_metadata_block(outline_nature: str, burden_description: str) -> str:
    lines = []
    if (outline_nature or "").strip():
        lines.append(f"纲目性质：{outline_nature.strip()}")
    if (burden_description or "").strip():
        lines.append(f"负担说明：{burden_description.strip()}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _call_claude(prompt: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


@router.post("/format_download")
async def kg_rag_format_download(req: FormatDownloadRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail='内容不能为空')
    if req.direction not in ('zh', 'zh_tw', 'en', 'es'):
        raise HTTPException(status_code=400, detail='无效的语言方向')
    result = await asyncio.to_thread(
        format_and_download, req.text, req.direction, req.output_format
    )
    return result


@router.post("/query")
async def kg_rag_query(req: KgRagRequest):
    try:
        bm25_results, dense_results = await asyncio.gather(
            bm25_search(es, req.query, INDEX_NAME, top_k=30),
            dense_search(es, req.query, INDEX_NAME, top_k=30),
        )

        merged = await rrf_merge(bm25_results, dense_results)
        final = await rerank(merged, req.query, top_n=20)
        chunks_text = format_chunks(final)

        metadata_block = _build_metadata_block(req.outline_nature, req.burden_description)
        prompt = STEP5_GENERATION_FLAT.format(
            query=req.query,
            metadata_block=metadata_block,
            chunks=chunks_text,
        )

        answer = await asyncio.to_thread(_call_claude, prompt)
        return {"answer": answer, "chunks_used": len(final)}
    except Exception as e:
        return {"answer": None, "error": str(e)}

# ═══════════════════════════════════════════════════════════
#  PanAI 3.5 — 新增接口与本地辅助代码
# ═══════════════════════════════════════════════════════════

import json as _json
import sys as _sys
from pathlib import Path as _Path

from .prompts import (
    BURDEN_GENERATION,
    BURDEN_GENERATION_NO_DRAFT,
    STEP1_CONCEPT_EXTRACTION,
    QUERY_REWRITE,
)

# ── Neo4j 客户端 ──────────────────────────────────────────────
_KG_RAG_DIR = str(_Path(__file__).resolve().parents[3] / "back_mic" / "backend" / "kg_rag")
if _KG_RAG_DIR not in _sys.path:
    _sys.path.insert(0, _KG_RAG_DIR)

from neo4j_client import Neo4jClient
_neo4j = Neo4jClient()
try:
    _neo4j.startup()
except Exception:
    pass

# ── 本地常量 ──────────────────────────────────────────────────
QUERY_REWRITE_SYSTEM = "你是一个资深的圣经研究学者，只输出 JSON，不输出其他任何内容。"

OUTLINE_NATURE_WEIGHTS: dict = {
    "真理启示": [
        (lambda idx, cid: "life" in idx, 1.3),
        (lambda idx, cid: "bib" in idx, 1.2),
    ],
    "生命经历": [
        (lambda idx, cid: "life" in idx, 1.3),
        (lambda idx, cid: "cwwl" in idx, 1.2),
    ],
    "应用实行": [
        (lambda idx, cid: "cwwl" in idx, 1.3),
        (lambda idx, cid: "others" in idx, 1.2),
    ],
}

INDICES_35 = ",".join([
    "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_bib", "kg-rag_map_note", "kg-rag_7feasts",
])

# ── 本地辅助函数 ───────────────────────────────────────────────

def _apply_weight_local(results: list, outline_nature: str) -> list:
    rules = OUTLINE_NATURE_WEIGHTS.get(outline_nature, [])
    for doc in results:
        idx = doc.get("_index", "") or ""
        cid = doc.get("chunk_id", "") or ""
        original_score = float(doc.get("score", 0) or 0)
        multiplier = 1.0
        for condition, weight in rules:
            try:
                if condition(idx, cid):
                    multiplier = max(multiplier, float(weight))
            except Exception:
                continue
        doc["weighted_score"] = original_score * multiplier
        doc["weight_multiplier"] = multiplier
    results.sort(key=lambda x: float(x.get("weighted_score", 0) or 0), reverse=True)
    return results

def _parse_json_array_local(text: str) -> list:
    if not text or not text.strip():
        return []
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    try:
        arr = _json.loads(s)
        return arr if isinstance(arr, list) else []
    except _json.JSONDecodeError:
        last_brace = s.rfind("}")
        if last_brace > 0:
            try:
                arr = _json.loads(s[: last_brace + 1] + "]")
                if isinstance(arr, list):
                    return arr
            except _json.JSONDecodeError:
                pass
        return []

def _parse_step1_layers_local(text: str, outline_nature: str = "一般性"):
    if not text or not text.strip():
        return [], [], [], ""
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    obj = None
    try:
        parsed = _json.loads(s)
        if isinstance(parsed, dict):
            obj = parsed
    except _json.JSONDecodeError:
        pass
    if not obj:
        return [], [], [], ""
    reasoning = str(obj.get("reasoning", "") or "").strip()
    revelation = [str(x).strip() for x in obj.get("revelation", []) if str(x).strip()]
    experience = [str(x).strip() for x in obj.get("experience", []) if str(x).strip()]
    practice   = [str(x).strip() for x in obj.get("practice",   []) if str(x).strip()]
    nature = (outline_nature or "一般性").strip()
    if nature == "真理启示":
        max_rev, max_exp, max_prac = 8, 4, 4
    elif nature == "生命经历":
        max_rev, max_exp, max_prac = 4, 8, 4
    elif nature == "应用实行":
        max_rev, max_exp, max_prac = 4, 4, 8
    else:
        max_rev, max_exp, max_prac = 6, 5, 5
    experience = experience[:max_exp]
    practice   = practice[:max_prac]
    revelation = revelation[:min(max_rev, 16 - len(experience) - len(practice))]
    return revelation, experience, practice, reasoning

async def _route3_search_local(
    es_client,
    node_name: str,
    original_query: str,
    index: str,
    top_k: int = 5,
    outline_nature: str = "一般性",
) -> list:
    combined_query = f"{original_query} {node_name}".strip()
    fetch_size = top_k * 3
    bm25_hits, dense_hits = await asyncio.gather(
        bm25_search(es_client, combined_query, index, top_k=fetch_size),
        dense_search(es_client, combined_query, index, top_k=fetch_size),
    )
    merged = await rrf_merge(bm25_hits, dense_hits)
    weighted = _apply_weight_local(merged, outline_nature)
    truncated = weighted[:top_k]
    reranked = await rerank(truncated, combined_query, top_n=top_k)
    for doc in reranked:
        doc["expanded_from"] = node_name
        doc["source"] = "skeleton_route"
    return reranked

def _call_claude_with_system(prompt: str, system: str | None = None) -> str:
    client = anthropic.Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
    kwargs = dict(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text

# ── 请求体 ────────────────────────────────────────────────────

class BurdenRequest(BaseModel):
    query: str = Field(..., min_length=1)
    outline_nature: str = Field("一般性")
    audience: str = Field("")
    reference_excerpt: str = Field("")

class Step1Request(BaseModel):
    query: str = Field(..., min_length=1)
    outline_nature: str = Field("一般性")
    burden_description: str = Field("")

class Query35Request(BaseModel):
    query: str = Field(..., min_length=1)
    outline_nature: str = Field("一般性")
    burden_description: str = Field("")
    expanded_nodes: list[str] = Field(default_factory=list)
    rewritten_queries: list[str] = Field(default_factory=list)
    revelation: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    practice: list[str] = Field(default_factory=list)

# ── 新接口 ────────────────────────────────────────────────────

@router.post("/burden")
async def kg_rag_burden(req: BurdenRequest):
    try:
        # 有效摘录判断：去除空白和标点后，至少有10个汉字才算有效摘录
        import re as _re_burden
        cleaned = _re_burden.sub(r'[\s\W\d]', '', req.reference_excerpt or "")
        has_valid_excerpt = len(cleaned) >= 10

        prompt = BURDEN_DESCRIPTION_PROMPT.format(
            query=req.query,
            outline_nature=req.outline_nature or "（未填）",
            audience=req.audience or "（未填）",
            reference_excerpt=req.reference_excerpt.strip() if has_valid_excerpt else "（空）",
        )
        raw = await asyncio.to_thread(
            _call_claude_with_system, prompt, BURDEN_DESCRIPTION_SYSTEM
        )
        result = _parse_burden_generation_output(raw)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/step1")
async def kg_rag_step1(req: Step1Request):
    try:
        concept_names = _neo4j.get_concept_names()
        concept_list_text = "、".join(concept_names) if concept_names else ""
        burden_line = f"信息负担说明：{req.burden_description}" if req.burden_description.strip() else ""
        step1_prompt = STEP1_CONCEPT_EXTRACTION.format(
            query=req.query,
            outline_nature=req.outline_nature,
            burden_line=burden_line,
            concept_list=concept_list_text,
        )
        rewrite_prompt = QUERY_REWRITE.format(query=req.query)

        step1_raw, rewrite_raw = await asyncio.gather(
            asyncio.to_thread(_call_claude_with_system, step1_prompt, None),
            asyncio.to_thread(_call_claude_with_system, rewrite_prompt, QUERY_REWRITE_SYSTEM),
        )

        revelation, experience, practice, reasoning = _parse_step1_layers_local(
            step1_raw, req.outline_nature
        )
        rewritten_queries = _parse_json_array_local(rewrite_raw)
        expanded_nodes = list(dict.fromkeys(revelation + experience + practice))

        return {
            "revelation": revelation,
            "experience": experience,
            "practice": practice,
            "reasoning": reasoning,
            "expanded_nodes": expanded_nodes,
            "rewritten_queries": rewritten_queries,
            "expanded_nodes_count": len(expanded_nodes),
            "concept_list_loaded": len(concept_names),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query35")
async def kg_rag_query35(req: Query35Request):
    try:
        # ── Step2 骨架构建 ────────────────────────────────────
        revelation = req.revelation
        experience = req.experience
        practice = req.practice
        expanded_nodes = req.expanded_nodes
        skeleton = None
        deep: list[str] = []

        deep = revelation + experience + practice if expanded_nodes else []

        # ── Step2 骨架构建 与 三路检索 并发执行 ──────────────
        dense_query_list = [req.query] + req.rewritten_queries[:4]

        bm25_task = bm25_search(es, req.query, INDICES_35, top_k=30)
        dense_tasks = [
            dense_search(es, q, INDICES_35, top_k=10)
            for q in dense_query_list
        ]
        route3_tasks = [
            _route3_search_local(es, node, req.query, INDICES_35, top_k=5, outline_nature=req.outline_nature)
            for node in expanded_nodes[:12]
        ]

        async def _run_step2() -> list[dict] | None:
            if not expanded_nodes:
                return None
            paths = _neo4j.get_paths_between(expanded_nodes)
            key_verses = _neo4j.get_key_verses(revelation + experience + practice)
            step2_prompt = STEP2_SKELETON_BUILD.format(
                query=req.query,
                outline_nature=req.outline_nature,
                intrinsic_burden_text=req.burden_description or "（未填写负担说明）",
                revelation_json=_json.dumps(revelation, ensure_ascii=False),
                experience_json=_json.dumps(experience, ensure_ascii=False),
                practice_json=_json.dumps(practice, ensure_ascii=False),
                paths_text=_format_paths_text(paths),
                key_verses_text=_format_key_verses_text(key_verses),
            )
            step2_raw = await asyncio.to_thread(
                _call_claude_with_system, step2_prompt, None
            )
            return _parse_step2_skeleton(step2_raw)

        all_results = await asyncio.gather(
            _run_step2(),
            bm25_task, *dense_tasks, *route3_tasks,
            return_exceptions=True,
        )

        skeleton = all_results[0] if not isinstance(all_results[0], Exception) else None
        bm25_results = all_results[1] if not isinstance(all_results[1], Exception) else []
        dense_results_list = [
            r for r in all_results[2: 2 + len(dense_tasks)]
            if not isinstance(r, Exception)
        ]
        route3_results_list = [
            r for r in all_results[2 + len(dense_tasks):]
            if not isinstance(r, Exception)
        ]

        dense_combined: list = []
        for batch in dense_results_list:
            dense_combined.extend(batch)
        merged = await rrf_merge(bm25_results, dense_combined)
        main_results = await rerank(merged, req.query, top_n=20)

        main_ids = {r["chunk_id"] for r in main_results}
        expanded_results: list = []
        seen_ids = set(main_ids)
        for batch in route3_results_list:
            for doc in batch:
                cid = doc.get("chunk_id", "")
                if cid and cid not in seen_ids:
                    seen_ids.add(cid)
                    expanded_results.append(doc)

        # ── 根据有无骨架选择 Prompt ───────────────────────────
        metadata_block = _build_metadata_block(req.outline_nature, req.burden_description)

        if skeleton:
            skeleton_with_chunks = _build_skeleton_bound_prompt_block(
                skeleton, expanded_results, deep, main_results
            )
            prompt = STEP5_GENERATION.format(
                query=req.query,
                metadata_block=metadata_block,
                skeleton_with_chunks=skeleton_with_chunks,
            )
        else:
            all_chunks = main_results + expanded_results
            chunks_text = format_chunks(all_chunks)
            prompt = STEP5_GENERATION_FLAT.format(
                query=req.query,
                metadata_block=metadata_block,
                chunks=chunks_text,
            )

        answer = await asyncio.to_thread(_call_claude, prompt)

        expanded_from_nodes = list(dict.fromkeys(
            doc.get("expanded_from", "") for doc in expanded_results
            if doc.get("expanded_from")
        ))

        return {
            "answer": answer,
            "chunks_used": len(main_results) + len(expanded_results),
            "main_results_count": len(main_results),
            "expanded_results_count": len(expanded_results),
            "expanded_from_nodes": expanded_from_nodes,
            "has_skeleton": skeleton is not None,
            "skeleton_steps": len(skeleton) if skeleton else 0,
            "skeleton_preview": [s["step"] for s in skeleton] if skeleton else [],
        }
    except Exception as e:
        return {"answer": None, "error": str(e)}

# ═══════════════════════════════════════════════════════════
#  PanAI 3.5 Step2 — 本地辅助函数
# ═══════════════════════════════════════════════════════════

import re as _re
from typing import Any as _Any

from .prompts import (
    STEP2_SKELETON_BUILD,
    STEP5_GENERATION,
    BURDEN_DESCRIPTION_PROMPT,
    BURDEN_DESCRIPTION_SYSTEM,
)

# ── 1. _format_chunk_line ─────────────────────────────────
def _format_chunk_line(c: dict, max_text: int = 300) -> str:
    """单条段落格式化为一行摘要。"""
    chunk_id = c.get("chunk_id", "")
    book = c.get("book_title", "")
    msg = c.get("message_number", "")
    msg_title = c.get("message_title", "")
    text = (c.get("text") or "").strip()
    header = f"[{chunk_id}] {book}"
    if msg:
        header += f" 第{msg}篇"
    if msg_title:
        header += f" {msg_title}"
    preview = text if len(text) <= max_text else text[:max_text] + "…"
    return f"{header}\n{preview}"

# ── 2. _build_skeleton_bound_prompt_block ─────────────────
def _build_skeleton_bound_prompt_block(
    skeleton: list[dict],
    expanded_results: list[dict],
    deep: list[str],
    main_results: list[dict],
) -> str:
    used_expanded_ids: set[str] = set()
    sections: list[str] = []
    for idx, sk_item in enumerate(skeleton):
        step_text = sk_item.get("step", "")
        deep_indices = sk_item.get("deep_indices", [])
        target_concepts = {deep[i] for i in deep_indices if 0 <= i < len(deep)}
        bound_chunks = []
        for c in expanded_results:
            if c.get("expanded_from") in target_concepts:
                bound_chunks.append(c)
                used_expanded_ids.add(c.get("chunk_id", ""))
        lines = [f"【第{idx + 1}步】{step_text}"]
        if bound_chunks:
            lines.append("  支撑段落：")
            for c in bound_chunks:
                lines.append(f"    {_format_chunk_line(c)}")
                lines.append("    ---")
        else:
            lines.append("  支撑段落：（无绑定段落）")
        sections.append("\n".join(lines))
    leftover_expanded = [
        c for c in expanded_results if c.get("chunk_id", "") not in used_expanded_ids
    ]
    supplement_lines = ["【补充段落】（来自 BM25 与向量检索，适用于任何大点）"]
    for c in main_results:
        supplement_lines.append(f"  {_format_chunk_line(c)}")
        supplement_lines.append("  ---")
    if leftover_expanded:
        for c in leftover_expanded:
            supplement_lines.append(f"  {_format_chunk_line(c)}")
            supplement_lines.append("  ---")
    sections.append("\n".join(supplement_lines))
    return "\n\n".join(sections)

# ── 3. _format_paths_text ─────────────────────────────────
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
        if via and int(hops or 0) == 2:
            rel_parts = [x.strip() for x in str(relation).split("→")]
            via_name = str(via).strip()
            if len(rel_parts) == 2 and via_name:
                lines.append(f"{from_name} ──{rel_parts[0]}──► {via_name} ──{rel_parts[1]}──► {to_name}")
            else:
                lines.append(f"{from_name} ──{relation}──► {to_name}")
        elif via and int(hops or 0) == 3:
            rel_parts = [x.strip() for x in str(relation).split("→")]
            via_parts = [x.strip() for x in str(via).split("→")]
            if len(rel_parts) == 3 and len(via_parts) == 2:
                lines.append(f"{from_name} ──{rel_parts[0]}──► {via_parts[0]} ──{rel_parts[1]}──► {via_parts[1]} ──{rel_parts[2]}──► {to_name}")
            else:
                lines.append(f"{from_name} ──{relation}──► {to_name}")
        else:
            lines.append(f"{from_name} ──{relation}──► {to_name}")
    return "\n".join(lines)

# ── 4. _format_key_verses_text ────────────────────────────
def _format_key_verses_text(raw: dict) -> str:
    if not raw:
        return "（无）"
    lines_out: list[str] = []
    for concept, pairs in raw.items():
        parts: list[str] = []
        for vid, vtext in pairs:
            vtext = (vtext or "").strip()
            vid = (vid or "").strip()
            if not vtext:
                continue
            clean_text = vtext.replace("\u201c", "'").replace("\u201d", "'")
            if vid:
                parts.append(f"{vid}「{clean_text}」")
            else:
                parts.append(f"「{clean_text}」")
        if parts:
            lines_out.append(f"- {concept}：{'；'.join(parts)}")
    return "\n".join(lines_out) if lines_out else "（无）"

# ── 5. _safe_parse_json_local ─────────────────────────────
def _safe_parse_json_local(text: str) -> dict:
    if not text or not text.strip():
        return {}
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    try:
        obj = _json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except _json.JSONDecodeError:
        last_brace = s.rfind("}")
        if last_brace > 0:
            try:
                obj = _json.loads(s[: last_brace + 1])
                return obj if isinstance(obj, dict) else {}
            except _json.JSONDecodeError:
                return {}
        return {}

# ── 6. _parse_step2_skeleton ──────────────────────────────
def _parse_step2_skeleton(text: str) -> list[dict] | None:
    text = text.strip()
    if text.startswith("```"):
        text = _re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = _re.sub(r"\n?```$", "", text)
        text = text.strip()
    obj = _safe_parse_json_local(text or "")
    if not obj:
        return None
    sk = obj.get("skeleton")
    if sk is None:
        return None
    if isinstance(sk, list):
        result = []
        for x in sk:
            if isinstance(x, dict) and "step" in x:
                step = str(x.get("step", "")).strip()
                indices = x.get("deep_indices", [])
                if not isinstance(indices, list):
                    indices = []
                indices = [i for i in indices if isinstance(i, int)]
                pe_raw = x.get("path_evidence")
                path_evidence = str(pe_raw).strip() if pe_raw and str(pe_raw).strip() else None
                sa_raw = x.get("scripture_anchor")
                scripture_anchor = str(sa_raw).strip() if sa_raw and str(sa_raw).strip() else None
                if step:
                    if scripture_anchor is not None:
                        pos = scripture_anchor.find("「")
                        if pos != -1:
                            scripture_id = scripture_anchor[:pos].strip()
                            if scripture_id:
                                step = f"{step}（{scripture_id}）"
                    result.append({
                        "step": step,
                        "deep_indices": indices,
                        "path_evidence": path_evidence,
                        "scripture_anchor": scripture_anchor,
                    })
            elif isinstance(x, str) and x.strip():
                result.append({
                    "step": x.strip(),
                    "deep_indices": [],
                    "path_evidence": None,
                    "scripture_anchor": None,
                })
        return result if result else None
    return None

# ── 7. _parse_burden_generation_output ───────────────────
def _parse_burden_generation_output(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        return {"scenario": "B", "candidates": [], "error": "解析失败"}
    if "候选一" in text:
        candidates: list[str] = []
        for label in ("候选一", "候选二", "候选三"):
            pat = rf"{_re.escape(label)}(?:（侧重[^）]*）)?[：:]\s*(.+?)(?=\n\s*候选[一二三]|$)"
            m = _re.search(pat, text, _re.DOTALL)
            if m:
                candidates.append(_re.sub(r"\s+", " ", m.group(1).strip()))
            else:
                candidates.append("")
        if not any(c.strip() for c in candidates):
            return {"scenario": "B", "candidates": [], "error": "解析失败"}
        while len(candidates) < 3:
            candidates.append("")
        return {"scenario": "B", "candidates": candidates[:3]}
    if "负担说明" in text:
        m = _re.search(r"负担说明[：:]\s*(.+)", text, _re.DOTALL)
        if m:
            line = _re.sub(r"\s+", " ", m.group(1).strip())
            if line:
                return {"scenario": "A", "result": line}
    return {"scenario": "B", "candidates": [], "error": "解析失败"}

