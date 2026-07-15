# -*- coding: utf-8 -*-
"""Claude API usage 统计（仅写服务器日志，不暴露给前端）。"""
from __future__ import annotations

import logging
from typing import Any

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


def log_task_usage(task_id: str) -> None:
    """生成流程结束时把 usage 汇总写入服务器日志。"""
    summary = _task_usage.get(task_id)
    if not summary:
        return
    for key, stats in summary.items():
        logger.info(
            "[Usage统计] %s: 调用%s次, input=%s, output=%s, "
            "cache_creation=%s, cache_read=%s",
            key,
            stats["calls"],
            stats["input_tokens"],
            stats["output_tokens"],
            stats["cache_creation_input_tokens"],
            stats["cache_read_input_tokens"],
        )


def discard_task_usage(task_id: str) -> None:
    """任务结束后释放内存中的 usage 汇总。"""
    _task_usage.pop(task_id, None)
