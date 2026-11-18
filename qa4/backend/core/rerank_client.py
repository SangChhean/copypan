# -*- coding: utf-8 -*-
"""重排客户端（参照 3.0 back_shared/reranker_service.py：Jina /v1/rerank，jina-reranker-v3，
请求体 {model, query, documents, top_n}，不加指令前缀；失败降级为原序）。

配置：QA4_RERANK_BASE_URL / QA4_RERANK_API_KEY / QA4_RERANK_MODEL。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

logger = logging.getLogger("qa4.rerank")


class RerankClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout_s: float = 10.0,
        http_client: Any = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._key = api_key or ""
        self._http = http_client
        self.key_present = bool(self._key.strip())

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.key_present and self.model)

    async def rerank(self, query: str, docs: list[str], top_n: int) -> tuple[list[int], bool]:
        """返回 (按相关性降序的下标, degraded)。失败/未配置 → 原序 + degraded=True。"""
        n = min(int(top_n), len(docs))
        if n <= 0:
            return [], False
        if not self.configured:
            return list(range(n)), True
        import httpx

        payload = {"model": self.model, "query": query, "documents": list(docs), "top_n": n}
        headers = {"Authorization": "Bearer " + self._key}
        try:
            if self._http is not None:
                resp = await self._http.post(f"{self.base_url}/rerank", json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                    resp = await c.post(f"{self.base_url}/rerank", json=payload, headers=headers)
        except Exception as e:
            logger.warning("rerank 请求失败，降级原序: %s", type(e).__name__)
            return list(range(n)), True
        if resp.status_code != 200:
            logger.warning("rerank HTTP %s，降级原序", resp.status_code)
            return list(range(n)), True
        try:
            results = resp.json().get("results") or []
        except Exception:
            return list(range(n)), True
        out: list[int] = []
        for r in results:
            idx = r.get("index")
            if isinstance(idx, int) and 0 <= idx < len(docs) and idx not in out:
                out.append(idx)
            if len(out) >= n:
                break
        for i in range(len(docs)):
            if len(out) >= n:
                break
            if i not in out:
                out.append(i)
        return out[:n], False


class FakeRerankClient:
    """确定顺序：按 (query 中字符在文档里出现的个数 降序, 文本哈希) 排序。可注入失败。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.configured = True
        self.key_present = False
        self.calls = 0

    async def rerank(self, query: str, docs: list[str], top_n: int) -> tuple[list[int], bool]:
        self.calls += 1
        n = min(int(top_n), len(docs))
        if self.fail:
            return list(range(n)), True
        qs = set(query or "")

        def score(i: int) -> tuple[int, str]:
            d = docs[i] or ""
            return (-sum(1 for ch in set(d) if ch in qs), hashlib.sha256(d.encode("utf-8")).hexdigest())

        order = sorted(range(len(docs)), key=score)
        return order[:n], False


def make_rerank_client(settings: Any, *, fake: Optional[bool] = None) -> Any:
    use_fake = fake if fake is not None else getattr(settings, "retrieval_mode", "live") == "fake"
    if use_fake:
        return FakeRerankClient()
    return RerankClient(settings.rerank_base_url, settings.rerank_api_key, settings.rerank_model)
