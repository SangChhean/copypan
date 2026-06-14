"""
Embedding 统一适配层

使用规则（调用方必须遵守）：
- profile="default"：现有 AI 纲目 / 双路 RAG 使用，OpenAI text-embedding-3-small，512 维。
- profile="kg_rag"：KG-RAG 模块使用，OpenRouter Qwen3-Embedding-8B，1024 维。

不在本模块内写死具体模型名与维度；通过环境变量配置，默认值与上述规则一致。
"""
import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

Profile = Literal["default", "kg_rag"]

# ---------- default（现有 RAG）----------
# 由 ai_search.embedding_service 实现，本模块仅做转发，避免重复实现

# ---------- kg_rag（KG-RAG）----------
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


async def get_embeddings(
    texts: list[str],
    profile: Profile = "default",
) -> list[list[float]]:
    """
    按 profile 选择后端，返回与 texts 顺序一致的向量列表。

    Args:
        texts: 文本列表
        profile: "default" → 现有 RAG（OpenAI 512 维）；"kg_rag" → KG-RAG（OpenRouter 1024 维）

    Returns:
        与 texts 顺序一致的向量列表

    Raises:
        ValueError: 未配置对应 API Key 或 profile 非法
    """
    if not texts:
        return []

    if profile == "default":
        from ai_search.embedding_service import get_embeddings as _default_get_embeddings
        return await _default_get_embeddings(texts)

    if profile == "kg_rag":
        client = _get_kg_rag_client()
        if not client:
            raise ValueError("KG-RAG Embedding 需要配置 OPENROUTER_API_KEY")
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

    raise ValueError(f"不支持的 profile: {profile}，仅支持 default | kg_rag")


async def get_embedding(text: str, profile: Profile = "default") -> list[float]:
    """单条文本的向量，等价于 get_embeddings([text], profile)[0]。"""
    return (await get_embeddings([text], profile=profile))[0]


def get_embedding_dims(profile: Profile) -> int:
    """返回指定 profile 的向量维度，用于 ES mapping、kNN 等配置。"""
    if profile == "default":
        return 512
    if profile == "kg_rag":
        return EMBEDDING_KG_DIMS
    raise ValueError(f"不支持的 profile: {profile}")
