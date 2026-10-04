# -*- coding: utf-8 -*-
"""SC 费用：复用 panai4.config.PRICES_USD_PER_MILLION / price_for_model。

计费只含 input + output（与任务规则一致）；缓存相关 token 只展示、不计入。
"""
from __future__ import annotations

from typing import Any

from panai4.config import MODEL as PANAI4_MODEL
from panai4.config import price_for_model

from .config import MODEL

MILLION = 1_000_000

# usage 里与缓存相关的字段名（与 panai4.llm.LLMResult / usage_dict 一致）
CACHE_USAGE_FIELDS = (
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "cache_creation_5m_tokens",
)


def input_output_prices(model: str | None = None) -> dict[str, float]:
    """返回 {"input": $/MTok, "output": $/MTok}。复用现有配置，不另设默认。"""
    price = price_for_model(model or MODEL) or price_for_model(PANAI4_MODEL)
    if not price or "input" not in price or "output" not in price:
        raise RuntimeError("找不到模型单价（panai4.config.PRICES_USD_PER_MILLION）")
    return {"input": float(price["input"]), "output": float(price["output"])}


def calc_cost_usd(
    usage: dict[str, Any] | None,
    *,
    prices: dict[str, float] | None = None,
) -> float:
    """按 usage 的 input/output token 计费。内部保留完整浮点，不先舍入。"""
    usage = usage or {}
    p = prices or input_output_prices(usage.get("model"))
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    return inp * p["input"] / MILLION + out * p["output"] / MILLION


def format_usd(amount: float | None) -> str:
    if amount is None:
        return "—"
    return f"${amount:.3f}"


def cache_token_summary(usage: dict[str, Any] | None) -> dict[str, int | None]:
    usage = usage or {}
    return {name: usage.get(name) for name in CACHE_USAGE_FIELDS}


def cost_payload(
    usage: dict[str, Any] | None,
    *,
    cost_usd: float | None = None,
    prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    """接口/页面对单次调用的费用展示块。"""
    raw = calc_cost_usd(usage, prices=prices) if cost_usd is None and usage is not None else cost_usd
    return {
        "cost_usd": raw,
        "cost_display": format_usd(raw),
        "input_tokens": (usage or {}).get("input_tokens"),
        "output_tokens": (usage or {}).get("output_tokens"),
        "cache_tokens": cache_token_summary(usage),
    }


def sum_costs(*parts: float | None) -> float | None:
    """只把非 None 的部分相加；若全部为 None 则返回 None。"""
    values = [p for p in parts if p is not None]
    if not values:
        return None
    return sum(values)
