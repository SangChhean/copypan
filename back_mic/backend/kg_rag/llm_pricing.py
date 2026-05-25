# -*- coding: utf-8 -*-
"""
KG-RAG LLM 费用估算：单价取自厂商公开文档（Standard，未计 Batch / Cache / 区域加价）。

- Anthropic Claude：https://docs.anthropic.com/en/about-claude/pricing
  Sonnet 4.6 输入 $3/MTok、输出 $15/MTok；Opus 4.6 输入 $5/MTok、输出 $25/MTok。
- OpenAI GPT-5.4：https://platform.openai.com/docs/pricing
  gpt-5.4（<272K context, Standard）输入 $2.50/MTok、输出 $15/MTok（与 2026-03 官网 Flagship 表一致）。
- DeepSeek V4 Pro：https://api-docs.deepseek.com/quick_start/pricing
  deepseek-v4-pro 最新定价（cache miss）：Input $0.435/1M、Output $0.87/1M；
  未区分 cache hit（约 $0.003625/1M），实际账单可能更低。

说明：虚拟 id「gpt-5.4-thinking」实际调用仍为 gpt-5.4，计价同 gpt-5.4（Standard 单价不变）。
开启 reasoning.effort（如 high）时，模型往往产生更多「推理侧」token；OpenAI 通常将其计入
output_tokens（或等价 completion 计量），按输出价计费，故总费用常高于同任务下 effort 较低
或无 reasoning 的调用，并非单独加价率，而是 token 量变多。
若输入超过 272K 等触发加价档，以下估算会偏低，以账单为准。
"""
from __future__ import annotations

from typing import Any

PRICING_REFERENCES: list[str] = [
    "Anthropic Claude API: https://docs.anthropic.com/en/about-claude/pricing",
    "OpenAI API: https://platform.openai.com/docs/pricing (gpt-5.4 <272K Standard)",
    "DeepSeek API: https://api-docs.deepseek.com/quick_start/pricing (deepseek-v4-pro)",
]

USAGE_DISCLAIMER = (
    "费用为按官网 Standard 标价的估算值；不含 Prompt Cache、Batch 折扣、"
    "数据驻留/区域加价、OpenAI 长上下文（>272K）加价等；以实际账单为准。"
)


def billing_model_for_cost(request_model: str) -> str:
    """用于计价的逻辑模型 id（与 API 请求 model 对齐）。"""
    m = (request_model or "").strip().lower()
    if m == "gpt-5.4-thinking":
        return "gpt-5.4"
    return (request_model or "").strip() or "unknown"


def price_per_million_usd(billing_model: str) -> tuple[float, float, str]:
    """
    返回 (input_usd_per_mtok, output_usd_per_mtok, 人类可读档位说明)。
    """
    m = (billing_model or "").strip().lower()
    if m == "claude-opus-4-7":
        return 5.0, 25.0, "Claude Opus 4.7 标准价 $5/$25 per MTok"
    if m == "claude-opus-4-6":
        return 5.0, 25.0, "Claude Opus 4.6 标准价 $5/$25 per MTok"
    if m == "claude-sonnet-4-6":
        return 3.0, 15.0, "Claude Sonnet 4.6 标准价 $3/$15 per MTok"
    if m.startswith("claude-opus"):
        return 5.0, 25.0, "Claude Opus 系列近似 $5/$25 per MTok"
    if m.startswith("claude-sonnet") or m.startswith("claude-"):
        return 3.0, 15.0, "Claude（默认按 Sonnet 档 $3/$15 per MTok 估算）"
    if m == "gpt-5.4" or m.startswith("gpt-5.4-"):
        if "pro" in m:
            return 30.0, 180.0, "gpt-5.4-pro 标准价 $30/$180 per MTok（<272K）"
        return 2.5, 15.0, "gpt-5.4 标准价 $2.50/$15 per MTok（<272K）"
    if m == "deepseek-v4-pro":
        return 0.435, 0.87, "DeepSeek V4 Pro 最新定价 Input $0.435/1M · Output $0.87/1M（cache miss）"
    if m == "deepseek-v4-flash" or m == "deepseek-chat" or m == "deepseek-reasoner":
        return 0.14, 0.28, "DeepSeek V4 Flash 标准价 $0.14/$0.28 per MTok（cache miss）"
    if m.startswith("deepseek"):
        return 0.435, 0.87, "DeepSeek（默认按 V4 Pro 档 Input $0.435/1M · Output $0.87/1M 估算）"
    return 0.0, 0.0, f"未知模型 {billing_model!r}，未计价"


def estimate_cost_usd(billing_model: str, input_tokens: int, output_tokens: int) -> tuple[float, str]:
    pin, pout, label = price_per_million_usd(billing_model)
    if pin <= 0 and pout <= 0:
        return 0.0, label
    cost = (input_tokens * pin + output_tokens * pout) / 1_000_000.0
    return cost, label


def register_llm_usage(
    calls: list[dict[str, Any]],
    *,
    step: str,
    request_model: str,
    usage: dict[str, int] | None,
) -> dict[str, Any] | None:
    """
    将单次调用的 token 与估算费用写入 calls，并返回可挂到 step 上的 llm_usage 片段。
    usage: {"input_tokens": int, "output_tokens": int}
    """
    if not usage:
        return None
    inp = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    if inp == 0 and out == 0:
        return None
    bid = billing_model_for_cost(request_model)
    cost, rate_label = estimate_cost_usd(bid, inp, out)
    rec: dict[str, Any] = {
        "step": step,
        "model": request_model,
        "billing_model": bid,
        "input_tokens": inp,
        "output_tokens": out,
        "cost_usd": round(cost, 6),
        "rate_description": rate_label,
    }
    calls.append(rec)
    return {
        "model": request_model,
        "billing_model": bid,
        "input_tokens": inp,
        "output_tokens": out,
        "cost_usd": round(cost, 6),
        "rate_description": rate_label,
    }


def pack_llm_usage_response(
    calls: list[dict[str, Any]],
    *,
    step_elapsed_ms: dict[str, float] | None = None,
    total_elapsed_ms: float | None = None,
) -> dict[str, Any]:
    ti = sum(int(c.get("input_tokens", 0) or 0) for c in calls)
    to = sum(int(c.get("output_tokens", 0) or 0) for c in calls)
    tc = sum(float(c.get("cost_usd", 0) or 0) for c in calls)
    out: dict[str, Any] = {
        "currency": "USD",
        "pricing_references": PRICING_REFERENCES,
        "disclaimer": USAGE_DISCLAIMER,
        "calls": list(calls),
        "totals": {
            "input_tokens": ti,
            "output_tokens": to,
            "cost_usd": round(tc, 6),
        },
    }
    if step_elapsed_ms:
        out["step_elapsed_ms"] = {k: round(float(v), 1) for k, v in step_elapsed_ms.items()}
    if total_elapsed_ms is not None:
        out["total_elapsed_ms"] = round(float(total_elapsed_ms), 1)
    return out
