"""
Jina Reranker v3 精排服务
用于双路检索后的结果重排；API 不可用时降级为保持原序。
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

JINA_API_KEY = os.getenv("JINA_API_KEY", "")
RERANK_ENDPOINT = "https://api.jina.ai/v1/rerank"
RERANK_MODEL = "jina-reranker-v3"
TIMEOUT = 30.0


async def rerank(query: str, documents: list[str], top_n: int) -> list[int]:
    """
    使用 Jina Reranker v3 对文档按与 query 的相关性重排，返回原始下标列表。

    Args:
        query: 查询文本
        documents: 文档文本列表
        top_n: 返回的前几名数量

    Returns:
        按相关性降序的文档下标列表，长度为 min(top_n, len(documents))
        降级时返回 list(range(min(top_n, len(documents))))
    """
    if not documents:
        return []
    n = min(top_n, len(documents))
    if not JINA_API_KEY or not JINA_API_KEY.strip():
        logger.warning("JINA_API_KEY 未配置，Reranker 降级为原序")
        return list(range(n))

    payload = {
        "model": RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": min(top_n, len(documents)),
    }
    headers = {"Authorization": f"Bearer {JINA_API_KEY.strip()}"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(RERANK_ENDPOINT, json=payload, headers=headers)
    except httpx.TimeoutException as e:
        logger.warning("Jina Reranker 请求超时，降级为原序: %s", e)
        return list(range(n))
    except httpx.HTTPError as e:
        logger.warning("Jina Reranker 请求失败，降级为原序: %s", e)
        return list(range(n))

    if resp.status_code != 200:
        logger.warning(
            "Jina Reranker 返回非 200，降级为原序: status=%s body=%s",
            resp.status_code,
            resp.text[:200],
        )
        return list(range(n))

    try:
        data = resp.json()
    except Exception as e:
        logger.warning("Jina Reranker 响应解析失败，降级为原序: %s", e)
        return list(range(n))

    results = data.get("results") or []
    # API 返回的 results 已按 relevance 降序，每项含 index（原始下标）
    out = []
    for r in results:
        if len(out) >= n:
            break
        idx = r.get("index")
        if isinstance(idx, int) and 0 <= idx < len(documents):
            out.append(idx)
    # 若返回条数不足，用原序补齐
    if len(out) < n:
        seen = set(out)
        for i in range(len(documents)):
            if len(out) >= n:
                break
            if i not in seen:
                out.append(i)
    return out[:n]
