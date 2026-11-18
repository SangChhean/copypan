# -*- coding: utf-8 -*-
"""RedisStore / MemoryStore：键自动加前缀；错误降级不抛给调用方。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional, Protocol

logger = logging.getLogger("qa4.redis")


class RedisStore(Protocol):
    def get(self, key: str) -> Optional[str]: ...
    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool: ...
    def incr_with_ttl(self, key: str, ttl: int) -> int: ...
    def push_capped(self, key: str, value: str, cap: int) -> bool: ...
    def scan_delete(self, match_suffix: str = "*") -> int: ...
    def ping(self) -> bool: ...
    def delete(self, key: str) -> bool: ...


class MemoryStore:
    """进程内假 Redis，接口与 RedisStore 一致。"""

    def __init__(self, prefix: str = "qa4:") -> None:
        self.prefix = prefix
        self._data: dict[str, tuple[str, Optional[float]]] = {}
        self._lists: dict[str, list[str]] = {}
        self._lock = threading.Lock()
        self.degraded_count = 0

    def _k(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def _purge(self, full: str) -> None:
        item = self._data.get(full)
        if item and item[1] is not None and item[1] < time.time():
            self._data.pop(full, None)

    def get(self, key: str) -> Optional[str]:
        full = self._k(key)
        with self._lock:
            self._purge(full)
            item = self._data.get(full)
            return item[0] if item else None

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        full = self._k(key)
        exp = time.time() + ttl if ttl else None
        with self._lock:
            self._data[full] = (str(value), exp)
        return True

    def incr_with_ttl(self, key: str, ttl: int) -> int:
        full = self._k(key)
        with self._lock:
            self._purge(full)
            cur = 0
            if full in self._data:
                try:
                    cur = int(self._data[full][0])
                except Exception:
                    cur = 0
            cur += 1
            self._data[full] = (str(cur), time.time() + ttl)
            return cur

    def push_capped(self, key: str, value: str, cap: int) -> bool:
        full = self._k(key)
        with self._lock:
            lst = self._lists.setdefault(full, [])
            lst.append(str(value))
            while len(lst) > cap:
                lst.pop(0)
        return True

    def scan_delete(self, match_suffix: str = "*") -> int:
        # 只删本前缀下匹配项
        with self._lock:
            if match_suffix.endswith("*"):
                stem = match_suffix[:-1]
                pattern_prefix = self._k(stem)
                keys = [k for k in list(self._data) + list(self._lists) if k.startswith(pattern_prefix)]
            else:
                full = self._k(match_suffix)
                keys = [full] if full in self._data or full in self._lists else []
            n = 0
            for k in set(keys):
                if k in self._data:
                    self._data.pop(k, None)
                    n += 1
                if k in self._lists:
                    self._lists.pop(k, None)
                    n += 1
            return n

    def ping(self) -> bool:
        return True

    def delete(self, key: str) -> bool:
        full = self._k(key)
        with self._lock:
            gone = full in self._data or full in self._lists
            self._data.pop(full, None)
            self._lists.pop(full, None)
            return gone


class RealRedisStore:
    def __init__(self, url: str, prefix: str = "qa4:") -> None:
        import redis

        self.prefix = prefix
        self.degraded_count = 0
        self._client = redis.Redis.from_url(url, decode_responses=True)

    def _k(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def _fail(self, op: str, exc: Exception) -> None:
        self.degraded_count += 1
        logger.warning("Redis %s 降级: %s", op, type(exc).__name__)

    def get(self, key: str) -> Optional[str]:
        try:
            return self._client.get(self._k(key))
        except Exception as e:
            self._fail("get", e)
            return None

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        try:
            if ttl:
                self._client.setex(self._k(key), int(ttl), value)
            else:
                self._client.set(self._k(key), value)
            return True
        except Exception as e:
            self._fail("set", e)
            return False

    def incr_with_ttl(self, key: str, ttl: int) -> int:
        full = self._k(key)
        try:
            pipe = self._client.pipeline()
            pipe.incr(full)
            pipe.expire(full, int(ttl))
            results = pipe.execute()
            return int(results[0])
        except Exception as e:
            self._fail("incr", e)
            return 0

    def push_capped(self, key: str, value: str, cap: int) -> bool:
        full = self._k(key)
        try:
            pipe = self._client.pipeline()
            pipe.rpush(full, value)
            pipe.ltrim(full, -int(cap), -1)
            pipe.execute()
            return True
        except Exception as e:
            self._fail("push_capped", e)
            return False

    def scan_delete(self, match_suffix: str = "*") -> int:
        """按前缀 SCAN 分批删除；禁止 KEYS / FLUSH*。"""
        pattern = self._k(match_suffix if match_suffix else "*")
        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=200)
                if keys:
                    # UNLINK 优先，失败回退 DEL
                    try:
                        deleted += int(self._client.unlink(*keys))
                    except Exception:
                        deleted += int(self._client.delete(*keys))
                if cursor == 0:
                    break
            return deleted
        except Exception as e:
            self._fail("scan_delete", e)
            return 0

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception as e:
            self._fail("ping", e)
            return False

    def delete(self, key: str) -> bool:
        try:
            return bool(self._client.delete(self._k(key)))
        except Exception as e:
            self._fail("delete", e)
            return False


def create_store(redis_url: str, prefix: str = "qa4:") -> Any:
    if not (redis_url or "").strip():
        logger.info("QA4_REDIS_URL 为空，使用 MemoryStore（仅本机开发）")
        return MemoryStore(prefix=prefix)
    return RealRedisStore(redis_url, prefix=prefix)
