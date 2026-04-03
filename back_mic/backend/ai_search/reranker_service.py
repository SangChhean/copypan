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
TIMEOUT = 10.0


def _parse_rerank_response(resp: httpx.Response, documents: list[str], n: int) -> tuple[list[int], bool]:
    """从成功响应解析下标列表；失败则返回 (原序下标, degraded=True)。"""
    try:
        data = resp.json()
    except Exception as e:
        logger.warning("Jina Reranker 响应解析失败，降级为原序: %s", e)
        return list(range(n)), True

    results = data.get("results") or []
    out: list[int] = []
    for r in results:
        if len(out) >= n:
            break
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


async def rerank(query: str, documents: list[str], top_n: int) -> tuple[list[int], bool]:
    """
    使用 Jina Reranker v3 对文档按与 query 的相关性重排，返回原始下标列表。

    Args:
        query: 查询文本
        documents: 文档文本列表
        top_n: 返回的前几名数量

    Returns:
        (indices, degraded): indices 为按相关性降序的文档下标；degraded 为 True 表示已降级为原序。
    """
    if not documents:
        return [], False
    n = min(top_n, len(documents))
    if not JINA_API_KEY or not JINA_API_KEY.strip():
        logger.warning("JINA_API_KEY 未配置，Reranker 降级为原序")
        return list(range(n)), True

    payload = {
        "model": RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": min(top_n, len(documents)),
    }
    headers = {"Authorization": f"Bearer {JINA_API_KEY.strip()}"}

    first_attempt_failed = False
    resp: httpx.Response | None = None

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(RERANK_ENDPOINT, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            reason = str(e) or "超时"
            if attempt == 0:
                logger.warning("[Reranker] 第1次请求失败（%s），正在重试...", reason)
                first_attempt_failed = True
                continue
            logger.warning("[Reranker] 重试仍失败（%s），降级为原序", reason)
            return list(range(n)), True
        except httpx.HTTPError as e:
            reason = str(e) or type(e).__name__
            if attempt == 0:
                logger.warning("[Reranker] 第1次请求失败（%s），正在重试...", reason)
                first_attempt_failed = True
                continue
            logger.warning("[Reranker] 重试仍失败（%s），降级为原序", reason)
            return list(range(n)), True

        if resp is None:
            return list(range(n)), True

        if resp.status_code != 200:
            reason = f"HTTP {resp.status_code}"
            if attempt == 0:
                logger.warning("[Reranker] 第1次请求失败（%s），正在重试...", reason)
                first_attempt_failed = True
                continue
            logger.warning("[Reranker] 重试仍失败（%s），降级为原序", reason)
            return list(range(n)), True

        if first_attempt_failed:
            logger.info("[Reranker] 重试成功")
        return _parse_rerank_response(resp, documents, n)

    return list(range(n)), True
