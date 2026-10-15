# -*- coding: utf-8 -*-
"""【3.5测试用】独立基础设施：环境变量、Redis、Claude 客户端、监控空实现、纲目代码围栏清理。

与主站 ai_search.ai_service 互不引用。监控是空实现：测试页的调用不写入主站的用量统计。
"""
import logging
import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger("t35test")

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# Redis 可选：未安装或连接失败时仅禁用缓存
redis_client = None
try:
    import redis

    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    redis_client.ping()
    logger.info("[t35test] Redis 连接成功，缓存已启用（键前缀 t35test:）")
except Exception as e:
    redis_client = None
    logger.warning(f"[t35test] Redis 未启用，将跳过缓存: {e}")

# Claude 客户端（需配置 CLAUDE_API_KEY）
try:
    import anthropic

    claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY) if CLAUDE_API_KEY else None
except Exception as e:
    logger.error(f"[t35test] Claude 客户端初始化失败: {e}")
    claude_client = None


class _NoopMonitoring:
    """监控空实现：任何 record_* 调用都什么也不做。"""

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


_NOOP = _NoopMonitoring()


def get_monitoring(*args, **kwargs):
    return _NOOP


def _strip_code_fence_for_outline(text: Optional[str]) -> Optional[str]:
    """
    提取文本中最后一个完整的 fenced code block 内容。
    若存在多个代码块（如 Claude 先输出思考过程再输出纲目），取最后一个。
    若文本中没有任何代码块，原样返回。
    """
    if not text or not isinstance(text, str):
        return text
    s = text.strip()
    last_start = -1
    idx = 0
    lines = s.split("\n")
    fence_starts = []
    fence_ends = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not fence_starts or len(fence_starts) == len(fence_ends):
                fence_starts.append(i)
            elif len(fence_starts) > len(fence_ends):
                fence_ends.append(i)
    if not fence_starts or not fence_ends:
        return text
    # 取最后一对完整的 fence
    last_end = fence_ends[-1]
    last_start = fence_starts[len(fence_ends) - 1]
    inner = lines[last_start + 1 : last_end]
    return "\n".join(inner).strip() if inner else text
