# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ai_search.enhanced_translate_rerank")

_DEGRADE_WARNING = (
    "Jina Reranker 已降级为原序（{reason}），参考语料排序可能不准确"
)


def _degrade_results(results: list[dict], top_n: int, reason: str) -> tuple[list[dict[str, Any]], str]:
    msg = _DEGRADE_WARNING.format(reason=reason)
    logger.warning("[enhanced_translate_rerank] %s", msg)
    out: list[dict[str, Any]] = []
    for d in results[:top_n]:
        item = dict(d)
        item["retrieval_route"] = "reranked"
        item["rerank_degraded"] = True
        out.append(item)
    return out, msg


async def rerank(
    results: list[dict],
    query: str,
    top_n: int = 20,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    精排并返回 (结果列表, 降级提示或 None)。
    降级时打 WARNING 日志，由调用方写入 translate warnings[]。
    """
    if not results:
        return [], None
    texts = [d.get("text") or "" for d in results]
    try:
        from ai_search.reranker_service import rerank as _jina_rerank

        indices, scores, degraded = await _jina_rerank(query, texts, top_n=top_n)
        if degraded or not indices:
            reason = "JINA_API_KEY 未配置或 API 失败" if degraded else "indices 为空"
            out, msg = _degrade_results(results, top_n, reason)
            return out, msg
    except Exception as e:
        out, msg = _degrade_results(results, top_n, str(e) or type(e).__name__)
        return out, msg

    out: list[dict[str, Any]] = []
    for rank, i in enumerate(indices):
        if i < len(results):
            d = dict(results[i])
            d["retrieval_route"] = "reranked"
            d["rerank_degraded"] = False
            if rank < len(scores):
                d["rerank_score"] = scores[rank]
            out.append(d)
    if not out:
        out, msg = _degrade_results(results, top_n, "indices 解析后 out 为空")
        return out, msg
    return out, None
