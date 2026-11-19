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

# (实际索引名, status, error.type, error.reason) — 同因只打一次，避免刷屏
_ES_FAIL_LOGGED: set[tuple[str, Optional[int], str, str]] = set()


def _es_error_bits(exc: BaseException) -> tuple[Optional[int], str, str]:
    """从 elasticsearch 异常取 HTTP 状态与 error.type / error.reason。"""
    status: Optional[int] = None
    meta = getattr(exc, "meta", None)
    if meta is not None:
        st = getattr(meta, "status", None)
        if isinstance(st, int):
            status = st
    if status is None:
        for attr in ("status_code", "status"):
            v = getattr(exc, attr, None)
            if isinstance(v, int):
                status = v
                break

    etype = ""
    reason = ""
    body = getattr(exc, "body", None)
    err: Any = None
    if isinstance(body, dict):
        err = body.get("error")
    elif body is not None:
        err = body
    if isinstance(err, dict):
        etype = str(err.get("type") or "")
        reason = str(err.get("reason") or "")
        # 优先更深一层原因（root_cause / caused_by），顶层常为 all shards failed
        rc = err.get("root_cause")
        if isinstance(rc, list) and rc and isinstance(rc[0], dict):
            etype = str(rc[0].get("type") or etype)
            deeper = str(rc[0].get("reason") or "")
            cb = rc[0].get("caused_by")
            if isinstance(cb, dict) and cb.get("reason"):
                etype = str(cb.get("type") or etype)
                deeper = str(cb.get("reason") or deeper)
            if deeper:
                reason = deeper
        fs = err.get("failed_shards")
        if (not reason or reason == "all shards failed") and isinstance(fs, list) and fs:
            r0 = fs[0].get("reason") if isinstance(fs[0], dict) else None
            if isinstance(r0, dict):
                cb = r0.get("caused_by") if isinstance(r0.get("caused_by"), dict) else None
                if cb and cb.get("reason"):
                    etype = str(cb.get("type") or etype)
                    reason = str(cb.get("reason"))
                elif r0.get("reason"):
                    etype = str(r0.get("type") or etype)
                    reason = str(r0.get("reason"))
    elif isinstance(err, str):
        reason = err
    if not reason:
        reason = str(exc)[:300]
    return status, etype or type(exc).__name__, reason


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


def record_es_failure(
    failures_out: Optional[list[dict[str, Any]]],
    *,
    logical: str,
    index: str,
    status: Optional[int],
    etype: str,
    reason: str = "",
) -> None:
    """记入本趟检索的失败列表（按 logical+status+type 去重）。"""
    if failures_out is None:
        return
    entry = {"logical": logical, "index": index, "status": status, "type": etype}
    if reason:
        entry["reason"] = reason
    key = (logical, status, etype)
    for old in failures_out:
        if (old.get("logical"), old.get("status"), old.get("type")) == key:
            return
    failures_out.append(entry)


async def run_search(
    es: Any,
    logical: str,
    body: dict[str, Any],
    *,
    failures_out: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    idx = actual_index(logical)
    try:
        resp = await asyncio.to_thread(es.search, index=idx, body=body)
    except Exception as e:
        status, etype, reason = _es_error_bits(e)
        key = (idx, status, etype, reason)
        if key not in _ES_FAIL_LOGGED:
            _ES_FAIL_LOGGED.add(key)
            logger.warning(
                "ES 检索失败 logical=%s index=%s status=%s type=%s reason=%s",
                logical,
                idx,
                status,
                etype,
                reason,
            )
        record_es_failure(
            failures_out,
            logical=logical,
            index=idx,
            status=status,
            etype=etype,
            reason=reason,
        )
        return []
    return normalize_hits(logical, resp)


async def run_search_raw(es: Any, logical: str, body: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(es.search, index=actual_index(logical), body=body)
