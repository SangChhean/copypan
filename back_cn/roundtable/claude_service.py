# -*- coding: utf-8 -*-
"""Claude Sonnet 5（adaptive thinking + 可配置 effort）通用调用封装。"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import anthropic

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("CLAUDE_API_KEY")
        if not api_key:
            raise RuntimeError("CLAUDE_API_KEY 未配置")
        _client = anthropic.Anthropic(api_key=api_key, timeout=600.0)
    return _client


async def call_sonnet5_high(
    prompt: str,
    system: str,
    max_tokens: int = 24000,
    effort: str = "medium",
    cacheable_prefix: str | None = None,
    *,
    use_streaming: bool = False,
) -> tuple[str, dict]:
    """
    cacheable_prefix：如果传入，会作为单独的、带 cache_control 标记的内容块放在最前面，
    prompt 则作为紧随其后的、不缓存的部分（比如具体这次要做什么任务的指令）。
    调用方必须保证多次调用里 cacheable_prefix 的文字内容逐字节完全一致，才能命中缓存，
    哪怕多一个空格、换行位置不同都会导致缓存失效。

    返回 (生成的文本, usage字典)，usage 里含 cache_creation_input_tokens / cache_read_input_tokens，
    调用方应该打印这两个字段，用于验证缓存是否真的命中。
    """
    client = _get_client()

    def _sync_create():
        if cacheable_prefix:
            content: Any = [
                {
                    "type": "text",
                    "text": cacheable_prefix,
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": prompt},
            ]
        else:
            content = prompt
        kwargs = dict(
            model="claude-sonnet-5",
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        if use_streaming:
            with client.messages.stream(**kwargs) as stream:
                return stream.get_final_message()
        return client.messages.create(**kwargs)

    msg = await asyncio.to_thread(_sync_create)

    text_parts = [
        block.text
        for block in msg.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    if not text_parts:
        block_types = [
            getattr(b, "type", type(b).__name__) for b in (msg.content or [])
        ]
        stop = getattr(msg, "stop_reason", None)
        raise RuntimeError(
            f"Claude 返回内容中没有找到 text 类型的内容块 "
            f"(stop_reason={stop}, block_types={block_types})"
        )

    usage = {
        "input_tokens": getattr(msg.usage, "input_tokens", None),
        "output_tokens": getattr(msg.usage, "output_tokens", None),
        "cache_creation_input_tokens": getattr(
            msg.usage, "cache_creation_input_tokens", None
        ),
        "cache_read_input_tokens": getattr(
            msg.usage, "cache_read_input_tokens", None
        ),
    }
    return "".join(text_parts), usage
