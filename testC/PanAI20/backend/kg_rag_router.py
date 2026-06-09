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
    draft_text: str = Field("")

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

# ── 新接口 ────────────────────────────────────────────────────

@router.post("/burden")
async def kg_rag_burden(req: BurdenRequest):
    try:
        if req.draft_text.strip():
            prompt = BURDEN_GENERATION.format(
                query=req.query,
                outline_nature=req.outline_nature,
                draft_text=req.draft_text.strip(),
            )
            raw = await asyncio.to_thread(_call_claude_with_system, prompt)
            return {"burdens": [raw.strip()]}
        else:
            prompt = BURDEN_GENERATION_NO_DRAFT.format(
                query=req.query,
                outline_nature=req.outline_nature,
            )
            raw = await asyncio.to_thread(_call_claude_with_system, prompt)
            burdens = _parse_json_array_local(raw)
            if not burdens:
                burdens = [raw.strip()]
            return {"burdens": burdens}
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
        dense_query_list = [req.query] + req.rewritten_queries[:4]

        bm25_task = bm25_search(es, req.query, INDICES_35, top_k=30)
        dense_tasks = [
            dense_search(es, q, INDICES_35, top_k=10)
            for q in dense_query_list
        ]
        route3_tasks = [
            _route3_search_local(es, node, req.query, INDICES_35, top_k=5, outline_nature=req.outline_nature)
            for node in req.expanded_nodes[:12]
        ]

        all_results = await asyncio.gather(
            bm25_task, *dense_tasks, *route3_tasks,
            return_exceptions=True,
        )

        bm25_results = all_results[0] if not isinstance(all_results[0], Exception) else []
        dense_results_list = [
            r for r in all_results[1: 1 + len(dense_tasks)]
            if not isinstance(r, Exception)
        ]
        route3_results_list = [
            r for r in all_results[1 + len(dense_tasks):]
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

        chunks = main_results + expanded_results
        chunks_text = format_chunks(chunks)
        metadata_block = _build_metadata_block(req.outline_nature, req.burden_description)
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
            "chunks_used": len(chunks),
            "main_results_count": len(main_results),
            "expanded_results_count": len(expanded_results),
            "expanded_from_nodes": expanded_from_nodes,
        }
    except Exception as e:
        return {"answer": None, "error": str(e)}
