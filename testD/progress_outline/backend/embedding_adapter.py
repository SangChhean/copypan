# -*- coding: utf-8 -*-
"""OpenRouter Embedding（独立实现）。"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_KG_MODEL = os.getenv("EMBEDDING_KG_MODEL", "qwen/qwen3-embedding-8b")
EMBEDDING_KG_DIMS = int(os.getenv("EMBEDDING_KG_DIMS", "1024"))


def _client():
    if not OPENROUTER_API_KEY:
        return None
    from openai import AsyncOpenAI

    return AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)


async def get_embedding(text: str) -> list[float]:
    client = _client()
    if not client:
        raise ValueError("未配置 OPENROUTER_API_KEY")
    r = await client.embeddings.create(
        model=EMBEDDING_KG_MODEL,
        input=[text],
        dimensions=EMBEDDING_KG_DIMS,
    )
    return list(r.data[0].embedding)
