# -*- coding: utf-8 -*-
"""嵌入客户端（参照 3.0 back_shared/embedding_adapter.py：OpenAI 兼容 /embeddings，
Qwen3-Embedding-8B，dimensions=1024，不加指令前缀）。

配置：QA4_EMBED_BASE_URL / QA4_EMBED_API_KEY / QA4_EMBED_MODEL（值只从环境变量读，不进日志）。
"""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Any, Optional

from core.ready import redact_secrets

logger = logging.getLogger("qa4.embed")

EMBED_DIMS = 1024


class EmbeddingError(RuntimeError):
    pass


class EmbeddingClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        dims: int = EMBED_DIMS,
        timeout_s: float = 30.0,
        http_client: Any = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.dims = dims
        self.timeout_s = timeout_s
        self._key = api_key or ""
        self._http = http_client
        self.key_present = bool(self._key.strip())

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.key_present and self.model)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.configured:
            raise EmbeddingError("嵌入服务未配置（QA4_EMBED_BASE_URL / QA4_EMBED_API_KEY）")
        import httpx

        payload = {"model": self.model, "input": list(texts), "dimensions": self.dims}
        headers = {"Authorization": "Bearer " + self._key}
        try:
            if self._http is not None:
                resp = await self._http.post(f"{self.base_url}/embeddings", json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                    resp = await c.post(f"{self.base_url}/embeddings", json=payload, headers=headers)
        except Exception as e:
            raise EmbeddingError(redact_secrets(f"{type(e).__name__}: {e}")) from e
        if resp.status_code != 200:
            raise EmbeddingError(f"HTTP {resp.status_code}")
        data = resp.json().get("data") or []
        order = {int(d.get("index", i)): d.get("embedding") for i, d in enumerate(data)}
        out = [order.get(i) for i in range(len(texts))]
        if any(v is None or len(v) != self.dims for v in out):
            raise EmbeddingError("嵌入返回维度或条数不符")
        return out  # type: ignore[return-value]


class FakeEmbeddingClient:
    """由文本哈希生成的确定向量（单位长度，1024 维）。不联网。"""

    def __init__(self, dims: int = EMBED_DIMS) -> None:
        self.dims = dims
        self.configured = True
        self.key_present = False
        self.calls: list[int] = []

    def vector(self, text: str) -> list[float]:
        vals: list[float] = []
        counter = 0
        while len(vals) < self.dims:
            h = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
            vals.extend((b - 127.5) / 127.5 for b in h)
            counter += 1
        vals = vals[: self.dims]
        norm = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / norm for v in vals]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(len(texts))
        return [self.vector(t) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def make_embedding_client(settings: Any, *, fake: Optional[bool] = None) -> Any:
    use_fake = fake if fake is not None else getattr(settings, "retrieval_mode", "live") == "fake"
    if use_fake:
        return FakeEmbeddingClient()
    return EmbeddingClient(
        settings.embed_base_url, settings.embed_api_key, settings.embed_model
    )
