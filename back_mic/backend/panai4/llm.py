# -*- coding: utf-8 -*-
"""单次模型调用。只使用 anthropic 0.105.2 已有的 messages.create 参数和返回字段。"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass

from .config import (
    MAX_RETRIES,
    MAX_TOKENS,
    MAX_TOKENS_RETRY,
    MODEL,
    RETRY_BACKOFF_SECONDS,
    RETRY_STATUS_CODES,
    TIMEOUT_SECONDS,
    fake_llm_delay_seconds,
    fake_llm_enabled,
    price_for_model,
)

logger = logging.getLogger("panai4.llm")


@dataclass
class LLMResult:
    text: str
    model: str
    stop_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_creation_input_tokens: int | None
    cache_read_input_tokens: int | None
    cache_creation_5m_tokens: int | None
    cost_usd: float | None
    cost_note: str | None
    duration_ms: int
    content_blocks: dict
    thinking_text: str


def _block_counts(message) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in getattr(message, "content", None) or []:
        kind = getattr(block, "type", None) or "unknown"
        counts[str(kind)] = counts.get(str(kind), 0) + 1
    return counts


def _thinking_from_message(message) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", None) or []:
        if getattr(block, "type", None) != "thinking":
            continue
        text = getattr(block, "thinking", None)
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n\n".join(parts).strip()


def _text_from_message(message) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", None) or []:
        if getattr(block, "type", None) != "text":
            continue
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n".join(parts).strip()


def _usage_int(usage, name: str) -> int | None:
    if usage is None:
        return None
    value = getattr(usage, name, None)
    if value is None:
        return None
    return int(value)


def _five_minute_cache_tokens(usage) -> int | None:
    if usage is None:
        return None
    breakdown = getattr(usage, "cache_creation", None)
    if breakdown is not None:
        value = getattr(breakdown, "ephemeral_5m_input_tokens", None)
        if value is not None:
            return int(value)
    return _usage_int(usage, "cache_creation_input_tokens")


def _cost(model: str, result_tokens: dict[str, int | None]) -> tuple[float | None, str | None]:
    price = price_for_model(model)
    if price is None:
        return None, "未计价"
    million = 1_000_000
    cost = (
        (result_tokens["input_tokens"] or 0) * price["input"]
        + (result_tokens["output_tokens"] or 0) * price["output"]
        + (result_tokens["cache_creation_5m_tokens"] or 0) * price["cache_write_5m"]
        + (result_tokens["cache_read_input_tokens"] or 0) * price["cache_read"]
    ) / million
    return cost, None


def _retryable(exc: BaseException) -> bool:
    import anthropic

    if isinstance(exc, anthropic.APITimeoutError):
        return True
    if isinstance(exc, anthropic.APIConnectionError):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in RETRY_STATUS_CODES
    return False


async def _call(prompt: str, system: str, max_tokens: int):
    """异步客户端，不开线程。任务被取消时请求随之中止。"""
    import anthropic

    api_key = (os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("未配置 CLAUDE_API_KEY")
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0)
    kwargs = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        # 不指定时接口只回思考签名、正文为空。summarized 才会带回 thinking 块文字。
        "thinking": {"type": "adaptive", "display": "summarized"},
    }
    if system:
        kwargs["system"] = system
    try:
        return await client.messages.create(**kwargs)
    finally:
        await client.close()


def _result_from_message(message, started: float) -> LLMResult:
    usage = getattr(message, "usage", None)
    tokens = {
        "input_tokens": _usage_int(usage, "input_tokens"),
        "output_tokens": _usage_int(usage, "output_tokens"),
        "cache_creation_input_tokens": _usage_int(usage, "cache_creation_input_tokens"),
        "cache_read_input_tokens": _usage_int(usage, "cache_read_input_tokens"),
        "cache_creation_5m_tokens": _five_minute_cache_tokens(usage),
    }
    model = str(getattr(message, "model", "") or "")
    cost, note = _cost(model, tokens)
    return LLMResult(
        text=_text_from_message(message),
        model=model,
        stop_reason=getattr(message, "stop_reason", None),
        cost_usd=cost,
        cost_note=note,
        duration_ms=int((time.perf_counter() - started) * 1000),
        content_blocks=_block_counts(message),
        thinking_text=_thinking_from_message(message),
        **tokens,
    )


call_log: list[dict] = []
FAKE_MISSING_BURDEN = "缺少负担标记"


def _fake_text(topic: str) -> str:
    if FAKE_MISSING_BURDEN in (topic or ""):
        return f"【测试】{topic}"
    return (
        f"【职事界定】\n职事界定：{topic}\n\n"
        f"【真理脉络】\n真理脉络：{topic}\n\n"
        f"【负担说明】\n[360字左右]\n【测试负担】{topic}"
    )


async def complete(prompt: str, system: str = "", topic: str = "", max_tokens: int | None = None) -> LLMResult:
    limit = MAX_TOKENS if max_tokens is None else max_tokens
    call_log.append({"topic": topic, "prompt": prompt, "max_tokens": limit})
    if fake_llm_enabled():
        delay = fake_llm_delay_seconds()
        if delay:
            await asyncio.sleep(delay)
        return LLMResult(
            text=_fake_text(topic),
            model="fake",
            stop_reason="end_turn",
            input_tokens=0,
            output_tokens=0,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            cache_creation_5m_tokens=0,
            cost_usd=0.0,
            cost_note=None,
            duration_ms=int(delay * 1000),
            content_blocks={"text": 1, "thinking": 1},
            thinking_text=f"思考过程：{topic}",
        )

    started = time.perf_counter()
    attempt = 0
    raised_max_tokens = False
    while True:
        try:
            message = await _call(prompt, system, limit)
        except Exception as exc:
            if _retryable(exc) and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                logger.warning("模型调用将重试 attempt=%s wait=%ss error=%s", attempt + 1, wait, exc)
                attempt += 1
                await asyncio.sleep(wait)
                continue
            raise
        result = _result_from_message(message, started)
        if result.stop_reason == "max_tokens" and not raised_max_tokens and limit < MAX_TOKENS_RETRY:
            raised_max_tokens = True
            limit = MAX_TOKENS_RETRY
            call_log.append({"topic": topic, "prompt": prompt, "max_tokens": limit})
            continue
        return result
