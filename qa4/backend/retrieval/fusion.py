# -*- coding: utf-8 -*-
"""RRF 融合 + 精排（精排失败退回融合顺序并标 degraded）。"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("qa4.retrieval")


def doc_key(d: dict[str, Any]) -> str:
    return f"{d.get('_logical', '')}:{d.get('_id') or d.get('chunk_id') or ''}"


def rrf(ranked_lists: list[list[dict[str, Any]]], k: int = 60, key: Callable = doc_key) -> list[dict[str, Any]]:
    """每个列表按名次给 1/(k+rank)（rank 从 1 起）累加；返回带 _rrf 分数的文档，按分数降序、首现先后稳定。"""
    scores: dict[str, float] = {}
    docs: dict[str, dict[str, Any]] = {}
    first_seen: dict[str, int] = {}
    routes: dict[str, list[str]] = {}
    seq = 0
    for lst in ranked_lists:
        for rank, d in enumerate(lst, 1):
            dk = key(d)
            scores[dk] = scores.get(dk, 0.0) + 1.0 / (k + rank)
            if dk not in docs:
                docs[dk] = dict(d)
                first_seen[dk] = seq
                seq += 1
            r = d.get("_route")
            if r and r not in routes.setdefault(dk, []):
                routes[dk].append(r)
    ordered = sorted(scores, key=lambda x: (-scores[x], first_seen[x]))
    out = []
    for dk in ordered:
        d = docs[dk]
        d["_rrf"] = scores[dk]
        d["_routes"] = routes.get(dk) or ([d["_route"]] if d.get("_route") else [])
        out.append(d)
    return out


async def rerank_docs(
    docs: list[dict[str, Any]],
    query: str,
    reranker: Any,
    top_n: int,
    *,
    text_field: str = "text",
) -> tuple[list[dict[str, Any]], bool]:
    """返回 (精排后的前 top_n, degraded)。"""
    if not docs:
        return [], False
    head = docs[: max(top_n, 0)] if top_n else docs
    try:
        idx, degraded = await reranker.rerank(query, [str(d.get(text_field) or "") for d in head], len(head))
    except Exception as e:
        logger.warning("精排异常，退回融合顺序: %s", type(e).__name__)
        return head, True
    if degraded:
        return head, True
    out = [head[i] for i in idx if 0 <= i < len(head)]
    seen = {id(x) for x in out}
    out.extend(d for d in head if id(d) not in seen)
    return out, False
