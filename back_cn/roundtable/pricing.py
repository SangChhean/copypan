# -*- coding: utf-8 -*-
"""Claude Sonnet 5 计价（小排材料专用，勿与 kg_rag llm_pricing 混用）。

优惠价有效期至 2026-08-31（含当天）；之后自动切到标准价。
若 Anthropic 实际标准价与下方硬编码不一致，需人工核对官方定价页后更新。
当前 cache_control 为 ephemeral 默认 5 分钟，故 cache write 用 cache_write_5m。
"""
from __future__ import annotations

from datetime import date
from typing import Any

# Sonnet 5 定价（每百万 token，美元）
SONNET5_INTRO_PRICING = {
    "input": 2.0,
    "output": 10.0,
    "cache_write_5m": 2.50,
    "cache_read": 0.20,
}
SONNET5_STANDARD_PRICING = {
    "input": 3.0,
    "output": 15.0,
    "cache_write_5m": 3.75,
    "cache_read": 0.30,
}
INTRO_PRICING_CUTOFF = date(2026, 8, 31)  # 优惠截止日（含当天）


def get_current_pricing() -> dict[str, float]:
    """按当前日期返回生效的价格表，优惠到期后自动切换为标准价。"""
    if date.today() <= INTRO_PRICING_CUTOFF:
        return SONNET5_INTRO_PRICING
    return SONNET5_STANDARD_PRICING


def calc_cost_usd(usage: dict[str, Any]) -> float:
    """根据 usage 字典计算美元费用。

    字段：input_tokens / output_tokens /
    cache_creation_input_tokens / cache_read_input_tokens
    """
    p = get_current_pricing()
    input_tokens = usage.get("input_tokens") or 0
    output_tokens = usage.get("output_tokens") or 0
    cache_creation = usage.get("cache_creation_input_tokens") or 0
    cache_read = usage.get("cache_read_input_tokens") or 0
    return (
        input_tokens / 1_000_000 * p["input"]
        + output_tokens / 1_000_000 * p["output"]
        + cache_creation / 1_000_000 * p["cache_write_5m"]
        + cache_read / 1_000_000 * p["cache_read"]
    )
