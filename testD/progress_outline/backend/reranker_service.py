# -*- coding: utf-8 -*-
"""Jina Reranker v3（独立实现）。"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

JINA_API_KEY = os.getenv("JINA_API_KEY", "")
RERANK_ENDPOINT = "https://api.jina.ai/v1/rerank"
RERANK_MODEL = "jina-reranker-v3"
TIMEOUT = 15.0


async def rerank(query: str, documents: list[str], top_n: int) -> tuple[list[int], bool]:
    if not documents:
        return [], False
    n = min(top_n, len(documents))
    if not JINA_API_KEY.strip():
        logger.warning("JINA_API_KEY 未配置，Reranker 降级为原序")
        return list(range(n)), True

    payload = {
        "model": RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": n,
    }
    headers = {"Authorization": f"Bearer {JINA_API_KEY.strip()}"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(RERANK_ENDPOINT, json=payload, headers=headers)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        out: list[int] = []
        for r in results:
            idx = r.get("index")
            if isinstance(idx, int) and 0 <= idx < len(documents):
                out.append(idx)
        if len(out) < n:
            seen = set(out)
            for i in range(len(documents)):
                if len(out) >= n:
                    break
                if i not in seen:
                    out.append(i)
        return out[:n], False
    except Exception as e:
        logger.warning("Jina Reranker 失败，降级原序: %s", e)
        return list(range(n)), True
