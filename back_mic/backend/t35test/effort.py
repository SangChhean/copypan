# -*- coding: utf-8 -*-
"""【4.0 新测试台】Opus 5.5 思考程度（effort）测试开关。

页面上的「思考程度」按钮选「低」时，请求头带 X-T35-Effort: low；router 在这次请求里设定下面的
ContextVar，这次请求里所有 Opus 5.5 调用（负担说明、防火墙、推荐重点、骨架、Query 改写、生成纲目）
都会带 output_config.effort=low。没选（预设）就什么都不送，Opus 5.5 用它自己的预设「中」，与原来完全相同。

用 ContextVar 而不是一层层传参数：asyncio.create_task / asyncio.to_thread 都会复制当前 context，
同一次请求里的并发调用（例如防火墙与 Step1 同时跑）都读得到，不同请求之间互不影响。
"""
from contextvars import ContextVar
from typing import Optional

ALLOWED_EFFORTS = {"low"}  # 目前只开放「低」做测试；不送 = Opus 5.5 预设「中」
EFFORT_LABELS = {None: "中", "": "中", "low": "低"}

_effort: ContextVar[Optional[str]] = ContextVar("t35_opus_effort", default=None)


def normalize_effort(v: Optional[str]) -> Optional[str]:
    v = (v or "").strip().lower()
    return v if v in ALLOWED_EFFORTS else None


def set_effort(v: Optional[str]):
    """设定这次请求的思考程度，返回 token（用完以 reset_effort 还原）。"""
    return _effort.set(normalize_effort(v))


def reset_effort(token) -> None:
    try:
        _effort.reset(token)
    except Exception:
        pass


def current_effort() -> Optional[str]:
    return _effort.get()
