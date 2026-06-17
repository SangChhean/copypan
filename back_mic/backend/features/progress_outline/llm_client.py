# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_CONCURRENT_LIMIT = max(1, int(os.getenv("PROGRESS_OUTLINE_CLAUDE_CONCURRENCY", "2")))
CLAUDE_MAX_RETRIES = max(0, int(os.getenv("PROGRESS_OUTLINE_CLAUDE_RETRIES", "3")))
CLAUDE_RETRY_BACKOFF = (3, 8, 15)

INPUT_PRICE_PER_M = 3.0
OUTPUT_PRICE_PER_M = 15.0

# 本模块所有调用均不开启 extended thinking（不传 thinking 参数）。

_claude_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _claude_semaphore
    if _claude_semaphore is None:
        _claude_semaphore = asyncio.Semaphore(CLAUDE_CONCURRENT_LIMIT)
    return _claude_semaphore


def calc_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens * INPUT_PRICE_PER_M / 1_000_000
        + output_tokens * OUTPUT_PRICE_PER_M / 1_000_000,
        6,
    )


def usage_from_message(msg: Any, *, model: str | None = None) -> dict[str, Any]:
    usage = getattr(msg, "usage", None)
    in_tok = int(getattr(usage, "input_tokens", 0) or 0)
    out_tok = int(getattr(usage, "output_tokens", 0) or 0)
    cache_create = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    billable_in = in_tok + cache_create + cache_read
    return {
        "model": model or CLAUDE_MODEL,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": calc_cost_usd(billable_in, out_tok),
    }


def text_from_message(msg: Any) -> str:
    text_parts: list[str] = []
    for block in getattr(msg, "content", None) or []:
        if getattr(block, "type", None) == "text":
            text_parts.append(getattr(block, "text", "") or "")
    return "".join(text_parts).strip()


def _error_is_retryable(exc: BaseException) -> bool:
    try:
        import anthropic
    except ImportError:
        return False
    if isinstance(exc, anthropic.APIConnectionError):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in (408, 429, 500, 502, 503, 504, 529)
    return False


async def _messages_create(
    user: str,
    *,
    max_tokens: int,
    system: str = "",
) -> Any:
    if not CLAUDE_API_KEY:
        raise RuntimeError("未配置 CLAUDE_API_KEY")
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=CLAUDE_API_KEY)
    create_kwargs: dict[str, Any] = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user}],
    }
    if system and system.strip():
        create_kwargs["system"] = system.strip()

    last_exc: BaseException | None = None
    for attempt in range(CLAUDE_MAX_RETRIES + 1):
        try:
            async with _get_semaphore():
                return await client.messages.create(**create_kwargs)
        except Exception as e:
            last_exc = e
            if not _error_is_retryable(e) or attempt >= CLAUDE_MAX_RETRIES:
                raise
            wait = CLAUDE_RETRY_BACKOFF[min(attempt, len(CLAUDE_RETRY_BACKOFF) - 1)]
            status = getattr(e, "status_code", None)
            logger.warning(
                "[progress_outline] Claude 可重试错误 attempt=%s/%s status=%s: %s，%ss 后重试",
                attempt + 1,
                CLAUDE_MAX_RETRIES + 1,
                status,
                e,
                wait,
            )
            await asyncio.sleep(wait)
    assert last_exc is not None
    raise last_exc


async def call_sync(prompt: str, max_tokens: int = 2048) -> dict[str, Any]:
    """非流式调用，返回正文与用量；不启用 extended thinking。"""
    msg = await _messages_create(prompt, max_tokens=max_tokens)
    return {
        "text": text_from_message(msg),
        "usage": usage_from_message(msg),
    }


async def call_claude(
    system: str,
    user: str,
    *,
    max_tokens: int = 16000,
) -> dict[str, Any]:
    """一次性调用 Claude，返回正文与用量；失败抛异常。"""
    msg = await _messages_create(user, max_tokens=max_tokens, system=system)
    return {
        "text": text_from_message(msg),
        "usage": usage_from_message(msg),
    }
