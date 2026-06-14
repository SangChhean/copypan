# -*- coding: utf-8 -*-
"""PanAI 2.5 阶段0：负担点检索式负担说明生成。"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from back_cn.panai.burden_prompts import BURDEN_POINT_REWRITE_PROMPT, BURDEN_RAG_PROMPT
from kg_rag.kg_rag_service import _INDICES_BASE, _call_kg_rag_llm
from kg_rag.llm_pricing import estimate_cost_usd
from kg_rag.retrieval import bm25_search, dense_search, rerank, rrf_merge

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_REWRITE_SYSTEM = "你是职事语料检索助手。只输出一条检索短句，不输出其他任何内容。"
_RAG_SYSTEM = (
    "你是一个资深的圣经研究学者。"
    "严格只输出负担说明正文，不输出内部流程、步骤说明、分析过程。"
)


def _accumulate_usage(
    total: dict[str, int],
    usage: dict[str, int] | None,
) -> None:
    if not usage:
        return
    total["input_tokens"] += int(usage.get("input_tokens", 0) or 0)
    total["output_tokens"] += int(usage.get("output_tokens", 0) or 0)


def _extract_top1(hit: dict[str, Any]) -> dict[str, str]:
    text = hit.get("text") or ""
    return {
        "source_zh": str(hit.get("source_zh") or ""),
        "book_title": str(hit.get("book_title") or ""),
        "message_title": str(hit.get("message_title") or ""),
        "text_preview": text[:120],
    }


async def _rewrite_point(
    query: str,
    point: str,
    token_totals: dict[str, int],
) -> tuple[str | None, str, list[str]]:
    """返回 (rewritten_query|None, search_query, warnings)。"""
    warnings: list[str] = []
    prompt = BURDEN_POINT_REWRITE_PROMPT.format(query=query, point=point)
    try:
        raw, usage = await _call_kg_rag_llm(
            prompt,
            _MODEL,
            temperature=0.2,
            max_tokens=200,
            system=_REWRITE_SYSTEM,
        )
        _accumulate_usage(token_totals, usage)
        rewritten = (raw or "").strip()
        if rewritten:
            return rewritten, rewritten, warnings
    except Exception as e:
        logger.warning("[burden] rewrite 异常 point=%r: %s", point, e)

    warnings.append(f"{point}：rewrite 失败，已降级")
    fallback = f"{query} {point}".strip()
    return None, fallback, warnings


async def _retrieve_top1(
    es_client: Any,
    search_q: str,
    point: str,
) -> tuple[dict[str, str] | None, dict[str, Any] | None, list[str]]:
    """返回 (top1 展示字段, 原始 hit 供 points_block, warnings)。"""
    warnings: list[str] = []
    k = 30
    fetch = k * 3
    try:
        bm25_hits = await bm25_search(es_client, search_q, _INDICES_BASE, fetch)
        dense_hits = await dense_search(
            es_client, search_q, _INDICES_BASE, fetch, num_candidates=100
        )
        merged = await rrf_merge(bm25_hits[:k], dense_hits[:k], k=60)
        top1_list = await rerank(merged, search_q, top_n=1)
        if not top1_list:
            warnings.append(f"{point}：无检索结果")
            return None, None, warnings
        hit = top1_list[0]
        return _extract_top1(hit), hit, warnings
    except Exception as e:
        logger.warning("[burden] 检索异常 point=%r q=%r: %s", point, search_q, e)
        warnings.append(f"{point}：无检索结果")
        return None, None, warnings


async def _process_point(
    query: str,
    point: str,
    es_client: Any,
    token_totals: dict[str, int],
) -> dict[str, Any]:
    rewritten_query, search_q, w1 = await _rewrite_point(query, point, token_totals)
    top1, raw_hit, w2 = await _retrieve_top1(es_client, search_q, point)
    return {
        "point": point,
        "rewritten_query": rewritten_query,
        "top1": top1,
        "_raw_hit": raw_hit,
        "warnings": w1 + w2,
    }


async def generate_burden(
    query: str,
    outline_nature: str,
    burden_points: list[str],
    es_client,
) -> dict:
    """
    阶段0：对每个负担点并发 rewrite + 检索，再一次性生成负担说明。

    返回 burden_description、points、warnings、elapsed_ms、cost_usd。
    """
    t0 = time.perf_counter()
    query = (query or "").strip()
    outline_nature = (outline_nature or "").strip() or "一般性"
    points = [p.strip() for p in burden_points if (p or "").strip()]

    token_totals = {"input_tokens": 0, "output_tokens": 0}
    warnings: list[str] = []

    point_results = await asyncio.gather(
        *[
            _process_point(query, pt, es_client, token_totals)
            for pt in points
        ]
    )

    blocks: list[str] = []
    out_points: list[dict[str, Any]] = []
    for i, pr in enumerate(point_results):
        warnings.extend(pr.pop("warnings", []))
        raw_hit = pr.pop("_raw_hit", None)
        out_points.append(pr)

        pt = pr["point"]
        top1 = pr.get("top1")
        if raw_hit:
            ref_text = (raw_hit.get("text") or "")[:300]
            source = str(raw_hit.get("source_zh") or "")
        else:
            ref_text = "（无参考段落）"
            source = top1.get("source_zh", "") if top1 else ""

        blocks.append(
            f"负担点{i + 1}：{pt}\n参考段落：{ref_text}\n（出处：{source}）"
        )

    points_block = "\n\n".join(blocks)
    rag_prompt = BURDEN_RAG_PROMPT.format(
        query=query,
        outline_nature=outline_nature,
        points_block=points_block,
    )
    raw_desc, rag_usage = await _call_kg_rag_llm(
        rag_prompt,
        _MODEL,
        temperature=0.3,
        max_tokens=600,
        system=_RAG_SYSTEM,
    )
    _accumulate_usage(token_totals, rag_usage)
    burden_description = (raw_desc or "").strip()

    if len(burden_description) > 220:
        compress_prompt = (
            f"以下负担说明超过220字（当前{len(burden_description)}字）。"
            "请压缩到220字以内，保留核心负担与关键经文，直接输出压缩后的正文，不要其他说明：\n\n"
            f"{burden_description}"
        )
        compressed, compress_usage = await _call_kg_rag_llm(
            compress_prompt,
            _MODEL,
            temperature=0.2,
            max_tokens=400,
            system=_RAG_SYSTEM,
        )
        _accumulate_usage(token_totals, compress_usage)
        if (compressed or "").strip():
            burden_description = compressed.strip()
        if len(burden_description) > 220:
            warnings.append("负担说明超长，已截断至220字")
            burden_description = burden_description[:220]

    cost_usd, _ = estimate_cost_usd(
        _MODEL,
        token_totals["input_tokens"],
        token_totals["output_tokens"],
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "burden_description": burden_description,
        "points": out_points,
        "warnings": warnings,
        "elapsed_ms": elapsed_ms,
        "cost_usd": round(cost_usd, 6),
    }
