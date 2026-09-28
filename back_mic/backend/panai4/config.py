# -*- coding: utf-8 -*-
"""PanAI 4.0 运行参数。单价单位：美元 / 百万 token。"""
from __future__ import annotations

import os
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]

MODEL = "claude-opus-5-5"
MAX_TOKENS = 8192
MAX_TOKENS_RETRY = 16000
# 负担说明（Prompt1）一开始就用 16000；其余步骤从 8192 起，顶满再升到 16000。
BURDEN_MAX_TOKENS = 16000
# 前端预估，可按实际记录再调。单位：美元 / 篇。
ESTIMATE_USD_BURDEN = 0.15
ESTIMATE_USD_SKELETON = 0.03
ESTIMATE_USD_ORIG_SKELETON = 0.045
ESTIMATE_USD_DIAGNOSIS = 0.08
# 旧的整篇估价，保留给尚未改用分步估价的调用。
ESTIMATE_USD_TWO_STEPS = 0.18
ESTIMATE_USD_FOUR_STEPS = 0.30
# 同时执行的运行数上限，超过的排队。可用 PANAI4_MAX_CONCURRENT_RUNS 覆盖。
MAX_CONCURRENT_RUNS = 3
# “我是”里填的名字上限。
CREATOR_MAX_LEN = 30
# 迁移时给没有建立人的旧运行补上的名字。
LEGACY_CREATOR = "Sang Chhean"
TIMEOUT_SECONDS = 600.0
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = (5, 10)
# 只重试这些 HTTP 状态，另加网络超时。
RETRY_STATUS_CODES = (429, 500, 502, 503, 504, 529)

# 服务器将来的路径：/opt/pansearch/data/panai4/panai4.db
# 本机未设置 PANAI4_DB_PATH 时用 backend/data/panai4/panai4.db。
_DEFAULT_DB = _BACKEND / "data" / "panai4" / "panai4.db"

# claude-opus-5-5。缓存写入价只覆盖 5 分钟档。
PRICES_USD_PER_MILLION = {
    "claude-opus-5-5": {
        "input": 4.0,
        "output": 20.0,
        "cache_write_5m": 5.0,
        "cache_read": 0.20,
    }
}


def db_path() -> Path:
    raw = (os.environ.get("PANAI4_DB_PATH") or "").strip()
    if not raw:
        return _DEFAULT_DB
    path = Path(raw)
    if not path.is_absolute():
        path = _BACKEND / path
    return path


def max_concurrent_runs() -> int:
    raw = (os.environ.get("PANAI4_MAX_CONCURRENT_RUNS") or "").strip()
    if not raw:
        return MAX_CONCURRENT_RUNS
    try:
        return max(1, int(raw))
    except ValueError:
        return MAX_CONCURRENT_RUNS


def fake_llm_enabled() -> bool:
    return (os.environ.get("PANAI4_FAKE_LLM") or "").strip() == "1"


def fake_llm_delay_seconds() -> float:
    raw = (os.environ.get("PANAI4_FAKE_DELAY") or "").strip()
    if not raw:
        return 2.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 2.0


def price_for_model(model: str) -> dict[str, float] | None:
    name = (model or "").strip()
    if name in PRICES_USD_PER_MILLION:
        return PRICES_USD_PER_MILLION[name]
    for key, price in PRICES_USD_PER_MILLION.items():
        if name.startswith(key):
            return price
    return None
