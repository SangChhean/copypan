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
