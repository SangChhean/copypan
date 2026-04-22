# -*- coding: utf-8 -*-
"""
IP 限流：同一 IP 每分钟最多 N 次请求（Redis 滑动窗口计数器）。
未配置 Redis 时静默跳过，不阻断请求。
"""
import logging
import os
import time
import uuid

logger = logging.getLogger("qa")

# 每分钟允许的最大请求数，可通过环境变量调整
RATE_LIMIT_PER_MINUTE = int(os.environ.get("QA_RATE_LIMIT_PER_MINUTE", "15"))


def _get_client_ip(request) -> str:
    """优先读 X-Forwarded-For（反向代理场景），否则取直连 IP。"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request, redis_client) -> bool:
    """
    检查 IP 是否超出限流。
    返回 True 表示允许通过，返回 False 表示超限（调用方返回 429）。
    Redis 不可用时始终返回 True（降级放行）。
    """
    if redis_client is None:
        return True

    ip = _get_client_ip(request)
    window = 60  # 秒
    limit = RATE_LIMIT_PER_MINUTE

    key = f"qa:ratelimit:{ip}"
    try:
        pipe = redis_client.pipeline()
        now = int(time.time())
        window_start = now - window

        # 用 sorted set 实现滑动窗口：score = 时间戳，member = 时间戳:随机后缀
        member = f"{now}:{uuid.uuid4().hex}"
        pipe.zremrangebyscore(key, 0, window_start)   # 清除窗口外的记录
        pipe.zadd(key, {member: now})                  # 记录本次请求
        pipe.zcard(key)                                # 当前窗口内请求数
        pipe.expire(key, window + 5)                   # 设置 key 过期
        results = pipe.execute()

        count = results[2]
        if count > limit:
            logger.warning("[QA] IP 限流触发: ip=%s count=%d limit=%d", ip, count, limit)
            return False
        return True
    except Exception as e:
        logger.warning("[QA] 限流检查失败，降级放行: %s", e)
        return True
