# -*- coding: utf-8 -*-
"""模型用量计价（USD）：试跑工具与正式问答共用。

单价来自 config/prices.json（或 QA4_PRICES_PATH）。不含嵌入 / 重排 / ES。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
PRICES_PATH = _BACKEND / "config" / "prices.json"

_prices_cache: Optional[dict[str, Any]] = None
_prices_cache_path: Optional[str] = None


def resolve_prices_path(path: Path | None = None) -> Path:
    """显式路径 > 环境变量 QA4_PRICES_PATH > 默认 config/prices.json。"""
    if path is not None:
        return Path(path)
    env = (os.environ.get("QA4_PRICES_PATH") or "").strip()
    if env:
        return Path(env)
    return PRICES_PATH


def load_prices(path: Path | None = None, *, use_cache: bool = True) -> dict[str, Any]:
    p = resolve_prices_path(path)
    key = str(p.resolve()) if p.exists() else str(p)
    global _prices_cache, _prices_cache_path
    if use_cache and _prices_cache is not None and _prices_cache_path == key:
        return _prices_cache
    raw = json.loads(p.read_text(encoding="utf-8"))
    data = raw if isinstance(raw, dict) else {}
    if use_cache:
        _prices_cache = data
        _prices_cache_path = key
    return data


def clear_prices_cache() -> None:
    global _prices_cache, _prices_cache_path
    _prices_cache = None
    _prices_cache_path = None


def prices_incomplete(prices: dict[str, Any]) -> bool:
    """任一模型缺价或 status=待核实 → 视为未就绪。"""
    if str(prices.get("status") or "") == "待核实":
        return True
    models = prices.get("models") or {}
    if not models:
        return True
    for _name, row in models.items():
        if not isinstance(row, dict):
            return True
        for k in ("input", "output", "cache_write_5m", "cache_read"):
            if row.get(k) is None:
                return True
    return False


def model_rates(prices: dict[str, Any], model: Optional[str]) -> Optional[dict[str, Any]]:
    models = prices.get("models") or {}
    if model and model in models:
        return models[model]
    # 后缀/别名宽松匹配
    if model:
        for k, v in models.items():
            if model.endswith(k) or k.endswith(model) or model in k or k in model:
                return v
    return None


def _numeric_tokens(val: Any) -> Optional[int]:
    """可识别的数字 token 数；bool 不当数字。"""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return int(val)
    return None


def parse_cache_creation(usage: dict[str, Any]) -> dict[str, Any]:
    """解析 usage 的 cache_creation / cache_creation_input_tokens。

    返回：
      tokens_5m: 可按 5 分钟档计价的写入量
      usage_unparsed: 有未识别或未完整计价部分
      price_missing_1h: 出现 1h 缓存写入但价格表无 1h 档（本工具亦不计价 1h）
    """
    out = {"tokens_5m": 0, "usage_unparsed": False, "price_missing_1h": False}
    total = _numeric_tokens(usage.get("cache_creation_input_tokens"))
    cc = usage.get("cache_creation")

    if total is not None:
        out["tokens_5m"] = total
        if isinstance(cc, dict):
            one_h = _numeric_tokens(cc.get("ephemeral_1h_input_tokens"))
            if one_h is not None and one_h > 0:
                out["usage_unparsed"] = True
                out["price_missing_1h"] = True
            for k, v in cc.items():
                if k not in {"ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"} and v not in (None, 0, ""):
                    out["usage_unparsed"] = True
        elif cc is not None and _numeric_tokens(cc) is None and not isinstance(cc, dict):
            out["usage_unparsed"] = True
        return out

    if cc is None:
        return out
    n = _numeric_tokens(cc)
    if n is not None:
        out["tokens_5m"] = n
        return out
    if isinstance(cc, dict):
        known = {"ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"}
        five = _numeric_tokens(cc.get("ephemeral_5m_input_tokens"))
        one_h = _numeric_tokens(cc.get("ephemeral_1h_input_tokens"))
        if "ephemeral_5m_input_tokens" in cc and five is None and cc.get("ephemeral_5m_input_tokens") is not None:
            out["usage_unparsed"] = True
        if five is not None:
            out["tokens_5m"] = five
        if one_h is not None and one_h > 0:
            out["usage_unparsed"] = True
            out["price_missing_1h"] = True
        elif "ephemeral_1h_input_tokens" in cc and cc.get("ephemeral_1h_input_tokens") is not None and one_h is None:
            out["usage_unparsed"] = True
        for k, v in cc.items():
            if k not in known and v not in (None, 0, ""):
                out["usage_unparsed"] = True
        return out
    # 未知结构
    out["usage_unparsed"] = True
    return out


def parse_usage_counts(usage: dict[str, Any]) -> dict[str, Any]:
    """从一步 usage 抽出 input/output/cache_*；不抛异常。"""
    u = dict(usage or {}) if isinstance(usage, dict) else {}
    inp = _numeric_tokens(u.get("input_tokens") if u.get("input_tokens") is not None else u.get("input"))
    out_n = _numeric_tokens(u.get("output_tokens") if u.get("output_tokens") is not None else u.get("output"))
    cread = _numeric_tokens(
        u.get("cache_read_input_tokens") if u.get("cache_read_input_tokens") is not None else u.get("cache_read")
    )
    cache = parse_cache_creation(u)
    unparsed = bool(cache["usage_unparsed"])
    # input/output/cache_read 若存在却非数字 → unparsed
    for key, raw in (
        ("input", u.get("input_tokens", u.get("input"))),
        ("output", u.get("output_tokens", u.get("output"))),
        ("cache_read", u.get("cache_read_input_tokens", u.get("cache_read"))),
    ):
        if raw is not None and _numeric_tokens(raw) is None and not isinstance(raw, dict):
            unparsed = True
        if isinstance(raw, dict):
            unparsed = True
    return {
        "input": int(inp or 0),
        "output": int(out_n or 0),
        "cache_creation": int(cache["tokens_5m"] or 0),
        "cache_read": int(cread or 0),
        "usage_unparsed": unparsed,
        "price_missing_1h": bool(cache["price_missing_1h"]),
    }


def est_usd_for_usage(
    usage: dict[str, Any],
    *,
    model: Optional[str],
    prices: dict[str, Any],
) -> tuple[Optional[float], bool, bool, bool]:
    """返回 (估算美元或 None, price_missing, usage_unparsed, price_missing_1h)。

    按已识别部分计价；1h 缓存写入无法计价时只打标，不抛异常。
    """
    counts = parse_usage_counts(usage)
    rates = model_rates(prices, model)
    if rates is None:
        return None, True, counts["usage_unparsed"], counts["price_missing_1h"]
    keys = ("input", "output", "cache_write_5m", "cache_read")
    if any(rates.get(k) is None for k in keys):
        return None, True, counts["usage_unparsed"], counts["price_missing_1h"]
    usd = (
        counts["input"] * float(rates["input"])
        + counts["output"] * float(rates["output"])
        + counts["cache_creation"] * float(rates["cache_write_5m"])
        + counts["cache_read"] * float(rates["cache_read"])
    ) / 1_000_000.0
    return usd, False, counts["usage_unparsed"], counts["price_missing_1h"]


def _model_for_step(step: str, usage: dict[str, Any], models: dict[str, Any]) -> Optional[str]:
    if isinstance(usage, dict) and usage.get("model"):
        return str(usage.get("model") or "") or None
    meta = models.get(step) if isinstance(models, dict) else None
    if isinstance(meta, dict):
        return meta.get("request_model") or meta.get("response_model")
    if isinstance(meta, str):
        return meta
    return None


def estimate_total_cost_usd(
    tokens: Optional[dict[str, Any]],
    models: Optional[dict[str, Any]] = None,
    *,
    prices: Optional[dict[str, Any]] = None,
) -> float:
    """对各步 usage 求和；缺价的步骤计 0。返回四位小数。"""
    if not tokens:
        return 0.0
    price_table = prices if prices is not None else load_prices()
    models = models or {}
    total = 0.0
    for step, usage in tokens.items():
        if not isinstance(usage, dict):
            continue
        model = _model_for_step(str(step), usage, models)
        part, _miss, _unp, _m1h = est_usd_for_usage(usage, model=model, prices=price_table)
        if part is not None:
            total += part
    return round(total, 4)


def cost_usd_from_record(
    record: dict[str, Any],
    *,
    prices: Optional[dict[str, Any]] = None,
) -> float:
    """优先用已存 total_cost_usd；否则按 tokens+models 现算；无 tokens → 0。"""
    if not isinstance(record, dict):
        return 0.0
    if "total_cost_usd" in record and record.get("total_cost_usd") is not None:
        try:
            return round(float(record["total_cost_usd"]), 4)
        except (TypeError, ValueError):
            pass
    tokens = record.get("tokens") or {}
    if not tokens:
        return 0.0
    return estimate_total_cost_usd(tokens, record.get("models") or {}, prices=prices)
