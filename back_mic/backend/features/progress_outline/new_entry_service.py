# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ai_search.reranker_service import rerank
from es_config import es as es_client
from kg_rag.embedding_adapter import get_embedding
from kg_rag.retrieval import rrf_merge

from features.progress_outline.token_utils import default_output_length, estimate_tokens

logger = logging.getLogger(__name__)

RRF_K = 60
BM25_TOP_K = 30
DENSE_TOP_K = 30

_SOURCE_FIELDS = [
    "chunk_id",
    "text",
    "book_title",
    "author",
    "source_zh",
    "message_number",
    "message_title",
    "section_title",
    "paragraph_type",
    "tokens",
    "en",
    "source_en",
    "year",
]

STAGE_CONFIG: dict[int, dict[str, Any]] = {
    1: {"index": "kg-rag_cwwn", "year_range": None},
    2: {"index": "kg-rag_cwwl", "year_range": (1932, 1960)},
    3: {"index": "kg-rag_cwwl", "year_range": (1961, 1973)},
    4: {"index": "kg-rag_cwwl", "year_range": (1974, 1984)},
    5: {"index": "kg-rag_cwwl", "year_range": (1984, 1990)},
    6: {"index": "kg-rag_cwwl", "year_range": (1990, 1997)},
}

SOURCE_GROUP_LABELS = {
    1: "倪柝声弟兄职事",
    2: "李常受弟兄职事第一阶段（1932-1960）",
    3: "李常受弟兄职事第二阶段（1961-1973）",
    4: "李常受弟兄职事第三阶段（1974-1984）",
    5: "李常受弟兄职事第四阶段（1984-1990）",
    6: "李常受弟兄职事高峰阶段（1990-1997）",
}


async def _bm25_search(
    query: str,
    index: str,
    top_k: int,
    year_range: tuple[int, int] | None,
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
        "_source": _SOURCE_FIELDS,
    }
    try:
        resp = await asyncio.to_thread(es_client.search, index=index, body=body)
    except Exception as e:
        logger.warning("[progress_outline] BM25 检索失败: %s", e)
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        src["score"] = hit.get("_score") or 0.0
        src["source"] = "bm25"
        src.setdefault("chunk_id", hit.get("_id", ""))
        out.append(src)
    return out


async def _dense_search(
    query: str,
    index: str,
    top_k: int,
    year_range: tuple[int, int] | None,
) -> list[dict[str, Any]]:
    if top_k <= 0:
        return []
    try:
        query_vector = await get_embedding(query, profile="kg_rag")
    except Exception as e:
        logger.warning("[progress_outline] Embedding 失败: %s", e)
        return []

    knn: dict[str, Any] = {
        "field": "embedding",
        "query_vector": query_vector,
        "k": top_k,
        "num_candidates": max(100, top_k * 3),
    }
    if year_range:
        knn["filter"] = {"range": {"year": {"gte": year_range[0], "lte": year_range[1]}}}

    body = {"size": top_k, "knn": knn, "_source": _SOURCE_FIELDS}
    try:
        resp = await asyncio.to_thread(es_client.search, index=index, body=body)
    except Exception as e:
        logger.warning("[progress_outline] Dense 检索失败: %s", e)
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        src["score"] = float(hit.get("_score") or 0.0)
        src["source"] = "dense"
        src.setdefault("chunk_id", hit.get("_id", ""))
        out.append(src)
    return out


async def _hybrid_search(
    query: str,
    index: str,
    top_k: int,
    year_range: tuple[int, int] | None,
) -> list[dict[str, Any]]:
    fetch_k = max(BM25_TOP_K, DENSE_TOP_K, top_k)
    bm25, dense = await asyncio.gather(
        _bm25_search(query, index, fetch_k, year_range),
        _dense_search(query, index, fetch_k, year_range),
    )
    merged = await rrf_merge(bm25, dense, k=RRF_K)
    texts = [d.get("text") or "" for d in merged]
    indices, _, _ = await rerank(query, texts, top_n=top_k)
    return [merged[i] for i in indices if i < len(merged)]


async def search_entries(term: str, source_group_no: int, top_k: int = 80) -> dict[str, Any]:
    cfg = STAGE_CONFIG.get(source_group_no)
    if not cfg:
        raise ValueError(f"无效阶段: {source_group_no}")
    query = (term or "").strip()
    if not query:
        raise ValueError("词条名称不能为空")

    results = await _hybrid_search(
        query,
        cfg["index"],
        top_k=top_k,
        year_range=cfg["year_range"],
    )
    items = []
    for r in results:
        items.append(
            {
                "chunk_id": r.get("chunk_id") or "",
                "source_zh": r.get("source_zh") or r.get("book_title") or "",
                "text": r.get("text") or "",
                "book_title": r.get("book_title") or "",
                "author": r.get("author") or "",
                "year": r.get("year"),
                "message_title": r.get("message_title") or "",
                "section_title": r.get("section_title") or "",
            }
        )
    plain = entries_to_plain_text(items)
    tokens = estimate_tokens(plain)
    return {
        "items": items,
        "count": len(items),
        "estimated_tokens": tokens,
        "default_output_length": default_output_length(tokens),
        "plain_text": plain,
        "source_group_label": SOURCE_GROUP_LABELS.get(source_group_no, ""),
        "index": cfg["index"],
    }


def entries_to_plain_text(items: list[dict]) -> str:
    parts: list[str] = []
    for it in items:
        header = it.get("source_zh") or it.get("book_title") or it.get("chunk_id") or ""
        if header:
            parts.append(header)
        text = it.get("text") or ""
        if text:
            parts.append(text)
        parts.append("")
    return "\n".join(parts).strip()
