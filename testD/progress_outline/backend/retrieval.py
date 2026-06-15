# -*- coding: utf-8 -*-
"""BM25 + Dense + RRF + Rerank（照搬 QA 检索原语，独立实现）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import embedding_adapter
import reranker_service

logger = logging.getLogger(__name__)

RRF_K = 60
BM25_TOP_K = 30
DENSE_TOP_K = 30


async def bm25_search(
    es: Any,
    query: str,
    index: str,
    top_k: int = BM25_TOP_K,
    year_range: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    if top_k <= 0:
        return []
    must = [{"match": {"text": {"query": query, "analyzer": "ik_smart"}}}]
    filters: list[dict] = []
    if year_range:
        filters.append({"range": {"year": {"gte": year_range[0], "lte": year_range[1]}}})
    body: dict[str, Any] = {
        "query": {"bool": {"must": must, "filter": filters}},
        "size": top_k,
        "_source": [
            "chunk_id", "text", "book_title", "author", "source_zh",
            "message_number", "message_title", "section_title", "paragraph_type",
            "tokens", "en", "source_en", "year",
        ],
    }
    try:
        resp = await asyncio.to_thread(es.search, index=index, body=body)
    except Exception as e:
        logger.warning("BM25 检索失败: %s", e)
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        src["score"] = hit.get("_score") or 0.0
        src["source"] = "bm25"
        src.setdefault("chunk_id", hit.get("_id", ""))
        out.append(src)
    return out


async def dense_search(
    es: Any,
    query: str,
    index: str,
    top_k: int = DENSE_TOP_K,
    year_range: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    if top_k <= 0:
        return []
    try:
        query_vector = await embedding_adapter.get_embedding(query)
    except Exception as e:
        logger.warning("Embedding 失败: %s", e)
        return []

    knn: dict[str, Any] = {
        "field": "embedding",
        "query_vector": query_vector,
        "k": top_k,
        "num_candidates": max(100, top_k * 3),
    }
    if year_range:
        knn["filter"] = {"range": {"year": {"gte": year_range[0], "lte": year_range[1]}}}

    body = {
        "size": top_k,
        "knn": knn,
        "_source": [
            "chunk_id", "text", "book_title", "author", "source_zh",
            "message_number", "message_title", "section_title", "paragraph_type",
            "tokens", "en", "source_en", "year",
        ],
    }
    try:
        resp = await asyncio.to_thread(es.search, index=index, body=body)
    except Exception as e:
        logger.warning("Dense 检索失败: %s", e)
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        src["score"] = float(hit.get("_score") or 0.0)
        src["source"] = "dense"
        src.setdefault("chunk_id", hit.get("_id", ""))
        out.append(src)
    return out


async def rrf_merge(
    bm25_results: list[dict],
    dense_results: list[dict],
    k: int = RRF_K,
) -> list[dict[str, Any]]:
    rrf_scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}
    for rank, doc in enumerate(bm25_results, 1):
        cid = doc.get("chunk_id") or ""
        if not cid:
            continue
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1.0 / (k + rank)
        doc_map[cid] = dict(doc)
    for rank, doc in enumerate(dense_results, 1):
        cid = doc.get("chunk_id") or ""
        if not cid:
            continue
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1.0 / (k + rank)
        if cid not in doc_map:
            doc_map[cid] = dict(doc)
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    out = []
    for cid in sorted_ids:
        d = doc_map[cid]
        d["score"] = rrf_scores[cid]
        d["source"] = "rrf"
        out.append(d)
    return out


async def hybrid_search(
    es: Any,
    query: str,
    index: str,
    top_k: int,
    year_range: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    fetch_k = max(BM25_TOP_K, DENSE_TOP_K, top_k)
    bm25, dense = await asyncio.gather(
        bm25_search(es, query, index, top_k=fetch_k, year_range=year_range),
        dense_search(es, query, index, top_k=fetch_k, year_range=year_range),
    )
    merged = await rrf_merge(bm25, dense)
    texts = [d.get("text") or "" for d in merged]
    indices, _ = await reranker_service.rerank(query, texts, top_n=top_k)
    return [merged[i] for i in indices if i < len(merged)]
