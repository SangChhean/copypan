# -*- coding: utf-8 -*-
"""IP 限流（改造自 3.0）。Redis 不可用时降级为进程内计数并放行策略由调用方决定。"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Optional

logger = logging.getLogger("qa4.rate_limit")

_local_lock = threading.Lock()
_local_counts: dict[str, list[float]] = {}
_local_degraded = 0


def get_client_ip(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _local_allow(ip: str, limit: int, window: int = 60) -> bool:
    global _local_degraded
    now = time.time()
    with _local_lock:
        _local_degraded += 1
        bucket = _local_counts.setdefault(ip, [])
        cutoff = now - window
        bucket[:] = [t for t in bucket if t >= cutoff]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


def check_rate_limit(
    request,
    store: Any,
    *,
    limit: int = 15,
    window: int = 60,
) -> bool:
    """True=放行；False=超限。

    store 不可用 / 操作失败：降级为进程内计数，并记录；仍可能因进程内超限返回 False。
    """
    ip = get_client_ip(request)
    key = f"ratelimit:{ip}"
    try:
        if store is None:
            return _local_allow(ip, limit, window)
        # 滑动窗口：用 incr_with_ttl 简化（固定窗口）；与 3.0 sorted-set 略有不同，见报告
        # 为更接近 3.0，若 store 有底层 redis client 可用 sorted set；否则 incr
        client = getattr(store, "_client", None)
        if client is not None:
            full = f"{store.prefix}{key}"
            pipe = client.pipeline()
            now = int(time.time())
            member = f"{now}:{uuid.uuid4().hex}"
            pipe.zremrangebyscore(full, 0, now - window)
            pipe.zadd(full, {member: now})
            pipe.zcard(full)
            pipe.expire(full, window + 5)
            results = pipe.execute()
            count = int(results[2])
            return count <= limit
        # MemoryStore / 降级路径
        count = store.incr_with_ttl(key, window)
        if count == 0:
            return _local_allow(ip, limit, window)
        return count <= limit
    except Exception as e:
        logger.warning("限流检查失败，降级进程内: %s", type(e).__name__)
        return _local_allow(ip, limit, window)


def local_degraded_count() -> int:
    return _local_degraded
