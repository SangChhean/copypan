"""
OpenAI 批量 Embedding 服务
使用 AsyncOpenAI，供双路检索 kNN 调用。
"""
import logging
import os

from openai import AsyncOpenAI, APIError, APITimeoutError

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# 异步客户端，无 Key 时仍创建实例，调用时由 OpenAI 抛错
_async_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    单次调用 OpenAI embeddings API，返回与输入顺序一致的向量列表。

    Args:
        texts: 文本列表

    Returns:
        与 texts 顺序一致的 512 维向量列表

    Raises:
        openai.APITimeoutError: 请求超时
        openai.APIError: API 错误
    """
    if not texts:
        return []
    if not _async_client:
        raise ValueError("OPENAI_API_KEY 未配置")
    try:
        r = await _async_client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
            dimensions=512,
        )
    except APITimeoutError as e:
        logger.error("OpenAI Embedding 请求超时: %s", e)
        raise
    except APIError as e:
        logger.error("OpenAI Embedding API 错误: %s", e)
        raise
    # 按 input 顺序返回（API 返回的 data 可能按 index 排序）
    order = {d.index: d.embedding for d in r.data}
    return [order[i] for i in range(len(texts))]


async def get_embedding(text: str) -> list[float]:
    """单条文本的 512 维向量，等价于 get_embeddings([text])[0]。"""
    return (await get_embeddings([text]))[0]
