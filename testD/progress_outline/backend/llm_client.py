# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# Claude Sonnet 4.6 Standard 定价（美元 / 百万 token）
INPUT_PRICE_PER_M = 3.0
OUTPUT_PRICE_PER_M = 15.0


def calc_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens * INPUT_PRICE_PER_M / 1_000_000 + output_tokens * OUTPUT_PRICE_PER_M / 1_000_000,
        6,
    )


async def call_claude(system: str, user: str) -> dict[str, Any]:
    """一次性调用 Claude，返回正文与用量。"""
    if not CLAUDE_API_KEY:
        return {
            "text": "[错误] 未配置 CLAUDE_API_KEY",
            "usage": None,
        }
    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=CLAUDE_API_KEY)
        msg = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=system or None,
            messages=[{"role": "user", "content": user}],
        )
        text_parts: list[str] = []
        for block in msg.content or []:
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", "") or "")
        text = "".join(text_parts).strip()
        usage = getattr(msg, "usage", None)
        in_tok = int(getattr(usage, "input_tokens", 0) or 0)
        out_tok = int(getattr(usage, "output_tokens", 0) or 0)
        return {
            "text": text,
            "usage": {
                "model": CLAUDE_MODEL,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": calc_cost_usd(in_tok, out_tok),
            },
        }
    except Exception as e:
        logger.exception("Claude 调用失败")
        return {"text": f"[错误] {e}", "usage": None}
