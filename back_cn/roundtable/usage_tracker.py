# -*- coding: utf-8 -*-
"""Claude API usage 统计：累加 token，实时把费用写回任务状态并打日志。"""
from __future__ import annotations

import logging
from typing import Any

from back_cn.roundtable.pricing import calc_cost_usd

logger = logging.getLogger(__name__)

_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)

_task_usage: dict[str, dict[str, dict[str, int]]] = {}


def _empty_stats() -> dict[str, int]:
    return {field: 0 for field in _USAGE_FIELDS} | {"calls": 0}


def init_task_usage(task_id: str, version_keys: list[str]) -> None:
    """为一次生成任务初始化 usage 汇总结构。"""
    _task_usage[task_id] = {"step1": _empty_stats()}
    for key in version_keys:
        _task_usage[task_id][key] = _empty_stats()


def _flush_costs_to_task(task_id: str) -> None:
    """把当前累计费用写回 task（可重复调用；discard 前必须已落盘）。"""
    # 延迟导入，避免与 task_manager 循环依赖
    from back_cn.roundtable.task_manager import get_task

    summary = _task_usage.get(task_id)
    if not summary:
        return
    task = get_task(task_id)
    if not task:
        return
    for key, stats in summary.items():
        cost = round(calc_cost_usd(stats), 4)
        if key == "step1":
            task["step1_cost_usd"] = cost
        elif key in task.get("versions", {}):
            task["versions"][key]["cost_usd"] = cost


def accumulate_usage(
    task_id: str | None, key: str, usage: dict[str, Any] | None
) -> None:
    """把单次 call_sonnet5_high 的 usage 累加到指定任务/阶段。"""
    if not task_id:
        return
    summary = _task_usage.get(task_id)
    if summary is None or key not in summary:
        return
    stats = summary[key]
    stats["calls"] += 1
    if not usage:
        return
    for field in _USAGE_FIELDS:
        value = usage.get(field)
        if isinstance(value, int):
            stats[field] += value
    _flush_costs_to_task(task_id)


def log_task_usage(task_id: str) -> None:
    """结束时：确保费用写回 task，并打 usage 日志。

    必须在 discard_task_usage 之前调用。
    """
    summary = _task_usage.get(task_id)
    if not summary:
        return

    _flush_costs_to_task(task_id)
    for key, stats in summary.items():
        cost = round(calc_cost_usd(stats), 4)
        logger.info(
            "[Usage统计] %s: 调用%s次, input=%s, output=%s, "
            "cache_creation=%s, cache_read=%s, cost_usd=$%.4f",
            key,
            stats["calls"],
            stats["input_tokens"],
            stats["output_tokens"],
            stats["cache_creation_input_tokens"],
            stats["cache_read_input_tokens"],
            cost,
        )


def discard_task_usage(task_id: str) -> None:
    """任务结束后释放内存中的 usage 汇总（费用已写在 task 上）。"""
    _task_usage.pop(task_id, None)
