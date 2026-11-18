# -*- coding: utf-8 -*-
"""只读 Elasticsearch 客户端。"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("qa4.es")


def _status_from_exc(exc: BaseException) -> Optional[int]:
    """从 elasticsearch 异常取 HTTP 状态码（不读响应体中的密钥）。"""
    for attr in ("status_code", "status"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    meta = getattr(exc, "meta", None)
    if meta is not None:
        st = getattr(meta, "status", None)
        if isinstance(st, int):
            return st
    return None


class EsClient:
    def __init__(
        self,
        url: str,
        user: str = "",
        password: str = "",
        *,
        verify: bool = True,
        index_map: Optional[dict] = None,
    ) -> None:
        self.url = url
        self.user = user
        self._password = password
        self.verify = verify
        self.index_map = (index_map or {}).get("indices") or index_map or {}
        self._client = None
        self.last_ping_error: Optional[dict[str, Any]] = None
        if url:
            try:
                from elasticsearch import Elasticsearch

                kwargs: dict[str, Any] = {"hosts": [url], "verify_certs": verify}
                # 账号密码均传入 basic_auth（ES 8+）；任一侧非空即启用
                if user or password:
                    kwargs["basic_auth"] = (user or "", password or "")
                self._client = Elasticsearch(**kwargs)
            except Exception as e:
                self.last_ping_error = {
                    "phase": "init",
                    "exc_type": type(e).__name__,
                    "status_code": _status_from_exc(e),
                    "message": str(e)[:200],
                }
                logger.warning(
                    "ES 客户端初始化失败: %s status=%s",
                    type(e).__name__,
                    self.last_ping_error.get("status_code"),
                )
                self._client = None
        # 不在实例上长期保留明文口令
        self._password = ""

    def ping(self) -> bool:
        if not self._client:
            if self.last_ping_error is None:
                self.last_ping_error = {
                    "phase": "ping",
                    "exc_type": "NoClient",
                    "status_code": None,
                    "message": "ES 客户端未初始化（缺 URL 或 init 失败）",
                }
            return False
        self.last_ping_error = None
        try:
            ok = bool(self._client.ping())
            if ok:
                return True
            # ping() 在鉴权失败等情况下常直接返回 False 而不抛异常；再用 info() 取状态
            try:
                self._client.info()
                self.last_ping_error = {
                    "phase": "ping",
                    "exc_type": "PingFalse",
                    "status_code": None,
                    "message": "ping()=False 但 info() 成功（异常路径）",
                }
            except Exception as e:
                self.last_ping_error = {
                    "phase": "ping",
                    "exc_type": type(e).__name__,
                    "status_code": _status_from_exc(e),
                    "message": str(e)[:200],
                }
            logger.warning(
                "ES ping 失败: %s status=%s",
                (self.last_ping_error or {}).get("exc_type"),
                (self.last_ping_error or {}).get("status_code"),
            )
            return False
        except Exception as e:
            self.last_ping_error = {
                "phase": "ping",
                "exc_type": type(e).__name__,
                "status_code": _status_from_exc(e),
                "message": str(e)[:200],
            }
            logger.warning(
                "ES ping 异常: %s status=%s",
                type(e).__name__,
                self.last_ping_error.get("status_code"),
            )
            return False

    def index_exists(self, index: str) -> bool:
        if not self._client:
            return False
        try:
            return bool(self._client.indices.exists(index=index))
        except Exception:
            return False

    def count(self, index: str) -> Optional[int]:
        if not self._client:
            return None
        try:
            r = self._client.count(index=index)
            return int(r.get("count", 0))
        except Exception:
            return None

    def search(self, index: str, body: dict, *, scroll: Optional[str] = None) -> dict:
        """只读查询（阶段 2 新增）。失败抛异常，由调用方降级。可选 scroll 供在线检查收集字段。"""
        if not self._client:
            raise RuntimeError("ES 客户端未初始化")
        kwargs: dict[str, Any] = {"index": index, "body": body}
        if scroll:
            kwargs["scroll"] = scroll
        resp = self._client.search(**kwargs)
        return resp.body if hasattr(resp, "body") else dict(resp)

    def scroll(self, *, scroll_id: str, scroll: str = "2m") -> dict:
        if not self._client:
            raise RuntimeError("ES 客户端未初始化")
        resp = self._client.scroll(scroll_id=scroll_id, scroll=scroll)
        return resp.body if hasattr(resp, "body") else dict(resp)

    def clear_scroll(self, *, scroll_id: str) -> None:
        if not self._client:
            return
        try:
            self._client.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass

    def get_mapping(self, index: str) -> dict:
        """只读映射（阶段 2 在线检查用）。"""
        if not self._client:
            raise RuntimeError("ES 客户端未初始化")
        resp = self._client.indices.get_mapping(index=index)
        return resp.body if hasattr(resp, "body") else dict(resp)

    def stats_by_logical(self, expected: dict[str, int]) -> dict[str, dict]:
        """返回逻辑名 → {index, exists, count, expected, status}。"""
        out: dict[str, dict] = {}
        for logical, expect_n in expected.items():
            meta = self.index_map.get(logical) or {}
            actual = meta.get("index") or f"qa4_{logical}"
            exists = self.index_exists(actual)
            cnt = self.count(actual) if exists else None
            status = "ok"
            if not exists:
                status = "missing"
            elif cnt is None:
                status = "error"
            elif cnt != int(expect_n):
                status = "count_mismatch"
            out[logical] = {
                "index": actual,
                "vector_field": meta.get("vector_field"),
                "exists": exists,
                "count": cnt,
                "expected": int(expect_n),
                "status": status,
            }
        return out


class FakeEsClient(EsClient):
    """测试用：不连网。"""

    def __init__(self, stats: Optional[dict[str, dict]] = None, *, reachable: bool = True):
        self.url = "fake"
        self.index_map = {}
        self._client = object() if reachable else None
        self._stats = stats or {}
        self._reachable = reachable
        self.last_ping_error: Optional[dict[str, Any]] = None
        if not reachable:
            self.last_ping_error = {
                "phase": "ping",
                "exc_type": "NoClient",
                "status_code": None,
                "message": "fake unreachable",
            }

    def ping(self) -> bool:
        if not self._reachable:
            return False
        self.last_ping_error = None
        return True

    def stats_by_logical(self, expected: dict[str, int]) -> dict[str, dict]:
        if not self._reachable:
            return {
                k: {
                    "index": f"qa4_{k}",
                    "exists": False,
                    "count": None,
                    "expected": v,
                    "status": "missing",
                }
                for k, v in expected.items()
            }
        if self._stats:
            return self._stats
        return {
            k: {
                "index": f"qa4_{k}",
                "exists": True,
                "count": v,
                "expected": v,
                "status": "ok",
            }
            for k, v in expected.items()
        }
