# -*- coding: utf-8 -*-
"""单索引 BM25 与向量（knn）检索，带硬过滤。

分词：ik_smart 是映射里的 search_analyzer（qa4/data_prep/es_import.py），查询里不临时指定。
ES 客户端只要求有 search(index=..., body=...) -> dict（core.es_client.EsClient 已提供）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from retrieval.config import actual_index, index_cfg, source_fields

logger = logging.getLogger("qa4.retrieval")


def _filter_clauses(terms: Optional[dict[str, list[Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fname, values in (terms or {}).items():
        if values:
            out.append({"terms": {fname: list(values)}})
    return out


def build_bm25_body(
    logical: str,
    query: str,
    *,
    size: int,
    terms: Optional[dict[str, list[Any]]] = None,
    phrases: Optional[list[str]] = None,
    phrase_boost: float = 2.0,
    cfg: Optional[dict] = None,
) -> dict[str, Any]:
    icfg = index_cfg(logical, cfg)
    tf = icfg.get("text_field") or "text"
    should = [
        {"match_phrase": {tf: {"query": p, "boost": float(phrase_boost)}}}
        for p in (phrases or [])
        if p
    ]
    boolq: dict[str, Any] = {"must": [{"match": {tf: {"query": query}}}]}
    if should:
        boolq["should"] = should
    flt = _filter_clauses(terms)
    if flt:
        boolq["filter"] = flt
    return {"size": int(size), "query": {"bool": boolq}, "_source": source_fields(logical, cfg)}


def build_knn_body(
    logical: str,
    vector: list[float],
    *,
    k: int,
    num_candidates: int,
    terms: Optional[dict[str, list[Any]]] = None,
    cfg: Optional[dict] = None,
) -> Optional[dict[str, Any]]:
    icfg = index_cfg(logical, cfg)
    vf = icfg.get("vector_field")
    if not vf:
        return None
    knn: dict[str, Any] = {
        "field": vf,
        "query_vector": list(vector),
        "k": int(k),
        "num_candidates": int(num_candidates),
    }
    flt = _filter_clauses(terms)
    if flt:
        knn["filter"] = flt
    return {"size": int(k), "knn": knn, "_source": source_fields(logical, cfg)}


def normalize_hits(logical: str, resp: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for hit in ((resp or {}).get("hits") or {}).get("hits") or []:
        src = dict(hit.get("_source") or {})
        src["_id"] = hit.get("_id") or src.get("chunk_id") or ""
        src["_score"] = float(hit.get("_score") or 0.0)
        src["_logical"] = logical
        out.append(src)
    return out


def hits_total(resp: dict[str, Any]) -> Optional[int]:
    tot = ((resp or {}).get("hits") or {}).get("total")
    if isinstance(tot, dict):
        return int(tot.get("value") or 0)
    if isinstance(tot, int):
        return tot
    return None


async def run_search(es: Any, logical: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        resp = await asyncio.to_thread(es.search, index=actual_index(logical), body=body)
    except Exception as e:
        logger.warning("ES 检索失败 index=%s: %s", logical, type(e).__name__)
        return []
    return normalize_hits(logical, resp)


async def run_search_raw(es: Any, logical: str, body: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(es.search, index=actual_index(logical), body=body)
