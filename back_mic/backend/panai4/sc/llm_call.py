# -*- coding: utf-8 -*-
"""SC 的 Opus 调用：沿用 panai4.llm.complete，受最多 3 并发限制；可注入 mock。"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from panai4.config import max_concurrent_runs
from panai4.llm import LLMResult, complete

from .config import MAX_TOKENS, MODEL

_sem: asyncio.Semaphore | None = None
# tests may set this to intercept calls
_mock_complete: Callable[..., Awaitable[LLMResult]] | None = None
call_count = 0


def _semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(max_concurrent_runs())
    return _sem


def reset_semaphore() -> None:
    global _sem
    _sem = asyncio.Semaphore(max_concurrent_runs())


def set_mock(fn: Callable[..., Awaitable[LLMResult]] | None) -> None:
    global _mock_complete
    _mock_complete = fn


def usage_dict(result: LLMResult) -> dict:
    return {
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cache_creation_input_tokens": result.cache_creation_input_tokens,
        "cache_read_input_tokens": result.cache_read_input_tokens,
        "cache_creation_5m_tokens": result.cache_creation_5m_tokens,
        "cost_usd": result.cost_usd,
        "duration_ms": result.duration_ms,
        "stop_reason": result.stop_reason,
    }


async def sc_complete(prompt: str, *, topic: str = "") -> LLMResult:
    global call_count
    call_count += 1
    async with _semaphore():
        if _mock_complete is not None:
            return await _mock_complete(prompt, topic=topic)
        return await complete(prompt, system="", topic=topic, max_tokens=MAX_TOKENS)
