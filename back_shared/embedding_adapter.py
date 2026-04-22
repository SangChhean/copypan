# -*- coding: utf-8 -*-
"""
Embedding 适配层（back_shared 版）
仅供 back_qa 使用，只支持 kg_rag profile。
profile="kg_rag"：OpenRouter Qwen3-Embedding-8B，1024 维。
"""
import logging
import os

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_KG_MODEL = os.getenv("EMBEDDING_KG_MODEL", "qwen/qwen3-embedding-8b")
EMBEDDING_KG_DIMS = int(os.getenv("EMBEDDING_KG_DIMS", "1024"))


def _get_kg_rag_client():
    """懒加载 OpenRouter 客户端（OpenAI 兼容接口）。"""
    if not OPENROUTER_API_KEY:
        return None
    from openai import AsyncOpenAI
    return AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """返回与 texts 顺序一致的向量列表（kg_rag profile）。"""
    if not texts:
        return []
    client = _get_kg_rag_client()
    if not client:
        raise ValueError("Embedding 需要配置 OPENROUTER_API_KEY")
    try:
        r = await client.embeddings.create(
            model=EMBEDDING_KG_MODEL,
            input=texts,
            dimensions=EMBEDDING_KG_DIMS,
        )
    except Exception as e:
        logger.error("OpenRouter Embedding 请求失败: %s", e)
        raise
    order = {d.index: d.embedding for d in r.data}
    return [order[i] for i in range(len(texts))]


async def get_embedding(text: str) -> list[float]:
    """单条文本向量，等价于 get_embeddings([text])[0]。"""
    return (await get_embeddings([text]))[0]


def get_embedding_dims() -> int:
    """返回 kg_rag profile 的向量维度。"""
    return EMBEDDING_KG_DIMS
