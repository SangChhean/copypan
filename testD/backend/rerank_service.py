# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("testD.rerank")


async def rerank(
    results: list[dict],
    query: str,
    top_n: int = 20,
) -> list[dict[str, Any]]:
    if not results:
        return []
    texts = [d.get("text") or "" for d in results]
    try:
        from ai_search.reranker_service import rerank as _jina_rerank
        indices, degraded = await _jina_rerank(query, texts, top_n=top_n)
        if degraded or not indices:
            # degraded 或 indices 为空时降级为 RRF 原序截断
            logger.warning("[testD.rerank] Jina degraded=%s indices=%s，降级原序", degraded, indices)
            out = results[:top_n]
            for d in out:
                d["source"] = "reranked"
            return out
    except Exception as e:
        logger.warning("[testD.rerank] Jina 调用异常，降级原序: %s", e)
        out = results[:top_n]
        for d in out:
            d["source"] = "reranked"
        return out
    out = []
    for i in indices:
        if i < len(results):
            d = dict(results[i])
            d["source"] = "reranked"
            out.append(d)
    # 最终兜底：out 仍为空则返回原序
    if not out:
        logger.warning("[testD.rerank] indices 解析后 out 为空，降级原序")
        out = results[:top_n]
        for d in out:
            d["source"] = "reranked"
    return out
