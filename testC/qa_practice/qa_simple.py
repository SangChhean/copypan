import sys

sys.path.insert(0, "D:/copypan")
sys.path.insert(0, "D:/copypan/back_mic/backend")
sys.path.insert(0, "D:/copypan/back_mic/backend/kg_rag")

import asyncio
import json
import os
import time

from dotenv import load_dotenv

load_dotenv("D:/copypan/back_mic/backend/.env")

import anthropic
from elasticsearch import Elasticsearch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j_client import Neo4jClient
from pydantic import BaseModel

from back_shared.retrieval import bm25_search, dense_search, rerank, rrf_merge

es = Elasticsearch(["http://localhost:9200"], basic_auth=("elastic", "qwSD4AF2Dcv"))
_neo4j = Neo4jClient()
_anthropic = anthropic.Anthropic(api_key=os.environ["CLAUDE_API_KEY"])

INDEXES = "kg-rag_life,kg-rag_cwwl,kg-rag_cwwn,kg-rag_others,kg-rag_bib,kg-rag_map_note,kg-rag_7feasts"
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU = "claude-haiku-4-5"

CONCEPT_NAMES: list[str] = []


def _call_claude(prompt: str, model: str, max_tokens: int) -> str:
    """同步调用 Claude，返回文本。供 asyncio.to_thread 包装使用。"""
    response = _anthropic.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if not response.content:
        return ""
    return response.content[0].text or ""


def _parse_json_response(raw: str) -> dict | None:
    """剥除可能的 ```json 围栏后 json.loads；失败返回 None，不抛异常。"""
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(
            lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:]
        )
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


async def step1_concepts(question: str) -> dict:
    """概念抽取 + Query Rewrite。

    返回 {"surface": [...], "deep": [...], "rewritten_query": "..."}
    任何失败都降级为 {"surface": [], "deep": [], "rewritten_query": question}
    """
    fallback = {"surface": [], "deep": [], "rewritten_query": question}
    try:
        concept_list_text = "、".join(CONCEPT_NAMES)
        prompt = f"""你是职事文献检索助手。以下是知识图谱中的全部概念词表：
{concept_list_text}

用户问题：{question}

请从词表中选择概念（只能从词表中选，不得自造词或修改词形），并改写问题：
- surface：问题文字中直接出现或字面直接对应的概念，1~3 个
- deep：回答该问题必然涉及、但问题中没有直接说出的概念，1~5 个
- rewritten_query：把问题改写为一句完整、独立、适合全文检索的陈述句

只返回 JSON，不要任何其他文字：
{{"surface": [...], "deep": [...], "rewritten_query": "..."}}"""

        raw = await asyncio.to_thread(_call_claude, prompt, MODEL_SONNET, 1024)
        parsed = _parse_json_response(raw)
        if parsed is None:
            return fallback

        concept_set = set(CONCEPT_NAMES)
        surface = [
            str(x).strip()
            for x in parsed.get("surface", [])
            if str(x).strip() in concept_set
        ][:3]
        deep = [
            str(x).strip()
            for x in parsed.get("deep", [])
            if str(x).strip() in concept_set
        ][:5]
        rewritten = str(parsed.get("rewritten_query", "") or "").strip() or question

        return {
            "surface": surface,
            "deep": deep,
            "rewritten_query": rewritten,
        }
    except Exception:
        return fallback


class QARequest(BaseModel):
    question: str


def _chunk_key(chunk: dict) -> str:
    chunk_id = (chunk.get("chunk_id") or "").strip()
    if chunk_id:
        return chunk_id
    return (chunk.get("text") or "")[:50]


async def _hybrid_search(query: str, top_k: int, top_n: int) -> list[dict]:
    """bm25 + dense 并发 → rrf 融合 → rerank 精排"""
    bm25_results, dense_results = await asyncio.gather(
        bm25_search(es, query, INDEXES, top_k),
        dense_search(es, query, INDEXES, top_k),
    )
    merged = await rrf_merge(bm25_results, dense_results)
    return await rerank(merged, query, top_n=top_n)


async def step2_retrieve(rewritten_query: str, deep_concepts: list[str]) -> list[dict]:
    """主检索 + deep 概念扩展检索，去重合并。"""
    main_results = await _hybrid_search(rewritten_query, top_k=20, top_n=10)

    seen: set[str] = set()
    merged: list[dict] = []

    for chunk in main_results:
        key = _chunk_key(chunk)
        if key in seen:
            continue
        seen.add(key)
        merged.append(chunk)

    concepts = [c.strip() for c in (deep_concepts or []) if (c or "").strip()][:5]
    if concepts:
        expanded_lists = await asyncio.gather(
            *[
                _hybrid_search(f"{rewritten_query} {concept}", top_k=10, top_n=5)
                for concept in concepts
            ]
        )
        for expanded in expanded_lists:
            for chunk in expanded:
                key = _chunk_key(chunk)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(chunk)

    return merged


async def step3_relevance(rewritten_query: str, chunks: list[dict]) -> bool:
    """Haiku 二分类：检索段落整体是否足以回答问题。

    任何调用或解析失败都降级返回 True（宁可继续生成，不中断）。
    """
    if not chunks:
        return False

    try:
        lines = []
        for i, chunk in enumerate(chunks[:10], start=1):
            text = (chunk.get("text") or "")[:200]
            lines.append(f"[{i}] {text}")
        excerpts = "\n".join(lines)

        prompt = f"""用户问题：{rewritten_query}

以下是检索到的段落摘要：
{excerpts}

请判断这些段落整体上是否足以回答用户的问题。
判断标准：只要其中有段落与问题主题实质相关、能支撑回答，就算足以回答；
只有当所有段落都与问题明显无关时，才判定为不足。

只返回 JSON，不要任何其他文字：
{{"relevant": true}} 或 {{"relevant": false}}"""

        raw = await asyncio.to_thread(_call_claude, prompt, MODEL_HAIKU, 256)
        parsed = _parse_json_response(raw)
        if parsed is None or "relevant" not in parsed:
            return True
        return bool(parsed.get("relevant"))
    except Exception:
        return True


async def step4_generate(question: str, chunks: list[dict]) -> str:
    """Sonnet 生成最终答案，非流式。"""
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        text = chunk.get("text") or ""
        parts.append(f"[{i}] {text}")
    chunks_text = "\n---\n".join(parts)

    prompt = f"""你是一位熟悉倪柝声、李常受职事文献的助手。
请根据以下参考段落，回答用户的问题。

回答要求：
- 引用原文时用「」逐字照录，一字不差，不得改写、缩写或意译
- 严禁把多处原文拼接后放在同一个「」里；每处引用单独一对「」
- 每处引用末尾标注其参考段落编号，如「……」[3]
- 先用一两句话直接回答问题，再用引用原文展开说明
- 如果参考段落不足以回答，直接说明未在参考段落中找到相关内容
- 用简洁清晰的中文回答
- 用纯文本输出，禁止使用任何 Markdown 语法（不要 **加粗**、# 标题、- 列表符号）；小标题直接用「一、」「二、」编号加换行即可
- 控制篇幅：选取最相关的 3~5 处原文引用展开，不必罗列所有相关段落

问题：{question}

参考段落：
{chunks_text}"""

    return await asyncio.to_thread(_call_claude, prompt, MODEL_SONNET, 4096)


def _build_sources(chunks: list[dict]) -> list[dict]:
    return [
        {
            "index": i + 1,
            "book_title": c.get("book_title"),
            "message_title": c.get("message_title"),
            "source_zh": c.get("source_zh"),
            "preview": (c.get("text") or "")[:80],
        }
        for i, c in enumerate(chunks)
    ]


app = FastAPI(title="testC QA Practice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    global CONCEPT_NAMES
    _neo4j.startup()
    CONCEPT_NAMES = _neo4j.get_concept_names()
    print(f"概念词表加载完成：{len(CONCEPT_NAMES)} 个")


@app.on_event("shutdown")
async def shutdown() -> None:
    _neo4j.shutdown()
    if hasattr(es, "close"):
        es.close()


@app.get("/api/testc/qa/liveness")
async def liveness():
    return {"status": "ok", "concepts_loaded": len(CONCEPT_NAMES)}


@app.post("/api/testc/qa/query")
async def qa_query(req: QARequest):
    t0 = time.perf_counter()
    try:
        s1 = await step1_concepts(req.question)
        chunks = await step2_retrieve(s1["rewritten_query"], s1["deep"])
        relevant = await step3_relevance(s1["rewritten_query"], chunks)

        if relevant:
            answer = await step4_generate(req.question, chunks)
        else:
            answer = "未能在职事信息中找到相关依据。"

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "answer": answer,
            "rewritten_query": s1["rewritten_query"],
            "surface_concepts": s1["surface"],
            "deep_concepts": s1["deep"],
            "relevant": relevant,
            "sources_count": len(chunks),
            "sources": _build_sources(chunks),
            "elapsed_ms": elapsed_ms,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)},
        )
