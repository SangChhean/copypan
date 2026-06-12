# -*- coding: utf-8 -*-
import asyncio
import logging
import os

import anthropic
from elasticsearch import Elasticsearch
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import retrieval
from source_format import format_source

logger = logging.getLogger("qa_simple")

router = APIRouter(prefix="/api/testa/qa_simple")

SONNET_MODEL = "claude-sonnet-4-6"
INDICES = ",".join([
    "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_bib", "kg-rag_map_note", "kg-rag_7feasts",
])

es = Elasticsearch(
    ["http://localhost:9200"],
    basic_auth=("elastic", "qwSD4AF2Dcv"),
)

QA_PROMPT = """你是一位专注于倪柝声与李常受弟兄职事著作的真理问答助手。
用户带着对真理的疑惑而来，你的任务是从以下职事著作段落中找到答案，让原文直接供应用户。

用户问题：
{question}

以下是相关职事著作段落（每段含编号和来源）：
{chunks_text}

回答要求：
1. 先立主旨：开头第一段以【核心要点】起首，从段落中找出1-2句最能概括核心答案的原句，用「」逐字引用并在末尾标注方括号编号，如 [3]；严禁用自己总结的话替代原文作为主旨句
2. 原文展开：围绕主旨分层推进论述，每层有一行小标题，小标题措辞取自原文并推进主旨展开（如"经纶的起点"→"经纶的内容"→"经纶的目标"），严禁用"…的原则"、"…的真理"等规范性措辞
3. 让原文说话：「」内必须逐字照录原文，一字不差；多处引用分别用各自的「」并各自标注方括号编号，如 [3]；严禁改写、缩写或意译后放入「」
4. 衔接语从简：原文前后可加少量衔接语，自己的解说篇幅不可超过原文
5. 若不同段落讲法有差异（如得胜者的班次），必须指出差异并用原文说明各自的角度或方面，严禁并列矛盾内容而不加解释
6. 参考段落不足以回答时，直接说明未在职事信息中找到相关内容
7. 回答末尾输出【引用书目】，每条格式为"[编号] 完整书名"（书名取自段落来源信息，完整取用、不截断、严禁重复），编号与正文引用一一对应
8. 严禁出现 chunk_id、文件名等技术字符串
9. 全文纯文本输出：第一行为总标题（一句话从原文角度提炼，严禁复述用户问题），小标题独立成行，不使用任何 Markdown 符号（#、>、**、-）
"""


class QARequest(BaseModel):
    question: str


def _build_chunks_text(results: list[dict]) -> str:
    parts = []
    for i, doc in enumerate(results, 1):
        text = (doc.get("text") or "")[:500]
        src = format_source(doc)
        parts.append(f"[{i}] 来源：{src}\n{text}")
    return "\n---\n".join(parts)


def _align_sources(results: list[dict]) -> list[str]:
    """按检索段落顺序对齐出处列表，与段落编号一一对应。"""
    return [format_source(doc) for doc in results]


async def _call_sonnet(prompt: str) -> str:
    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("Claude 客户端未配置（请设置 CLAUDE_API_KEY）")

    def _sync():
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=4096,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        return (msg.content[0].text or "").strip()

    return await asyncio.to_thread(_sync)


@router.post("/query")
async def qa_query(req: QARequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question 不能为空")

    question = req.question.strip()
    try:
        bm25_results, dense_results = await asyncio.gather(
            retrieval.bm25_search(es, question, INDICES, 20),
            retrieval.dense_search(es, question, INDICES, 20, 100),
        )
        merged = await retrieval.rrf_merge(
            bm25_results, dense_results, k=60, bm25_weight=1.0, dense_weight=1.0,
        )
        reranked = await retrieval.rerank(merged, question, 10)
        chunks_text = _build_chunks_text(reranked)
        prompt = QA_PROMPT.format(question=question, chunks_text=chunks_text)
        answer = await _call_sonnet(prompt)
        sources = _align_sources(reranked)
        return {
            "answer": answer,
            "sources_count": len(reranked),
            "sources": sources,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[qa_simple] query 失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
