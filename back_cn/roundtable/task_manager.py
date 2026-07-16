# -*- coding: utf-8 -*-
"""小排材料制作：内存态后台任务状态（进程重启会丢失）。"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from back_cn.roundtable.usage_tracker import discard_task_usage

_tasks: dict[str, dict] = {}


def create_task(version_keys: list[str], week_number: str | None = None) -> str:
    task_id = uuid.uuid4().hex
    _tasks[task_id] = {
        "created_at": time.time(),
        "week_number": week_number,
        "unified_fields": None,
        "step1_cost_usd": None,
        "versions": {
            v: {
                "status": "pending",
                "stage": "等待中",
                "attempt": 0,
                "result": None,
                "error": None,
                "cost_usd": None,
                "finalize": {
                    "status": "idle",
                    "file": None,
                    "error": None,
                },
            }
            for v in version_keys
        },
    }
    return task_id


def get_task(task_id: str) -> Optional[dict]:
    return _tasks.get(task_id)


def set_unified_fields(task_id: str, unified_fields: dict) -> None:
    if task_id in _tasks:
        _tasks[task_id]["unified_fields"] = unified_fields


def update_version_progress(
    task_id: str, version_key: str, stage: str, attempt: int
) -> None:
    if task_id in _tasks:
        v = _tasks[task_id]["versions"].get(version_key)
        if v:
            v["status"] = "running"
            v["stage"] = stage
            v["attempt"] = attempt


def set_version_done(task_id: str, version_key: str, result: dict) -> None:
    if task_id in _tasks:
        v = _tasks[task_id]["versions"].get(version_key)
        if v:
            v["status"] = "done"
            v["stage"] = "已完成"
            v["result"] = result
            v["error"] = None


def set_version_error(task_id: str, version_key: str, error: str) -> None:
    if task_id in _tasks:
        v = _tasks[task_id]["versions"].get(version_key)
        if v:
            v["status"] = "error"
            v["stage"] = "生成失败"
            v["error"] = error


def set_finalize_running(task_id: str, version_key: str) -> None:
    if task_id in _tasks:
        v = _tasks[task_id]["versions"].get(version_key)
        if v:
            v["finalize"] = {
                "status": "running",
                "file": None,
                "error": None,
            }


def set_finalize_done(task_id: str, version_key: str, file_info: dict) -> None:
    if task_id in _tasks:
        v = _tasks[task_id]["versions"].get(version_key)
        if v:
            v["finalize"] = {
                "status": "done",
                "file": file_info,
                "error": None,
            }


def set_finalize_error(task_id: str, version_key: str, error: str) -> None:
    if task_id in _tasks:
        v = _tasks[task_id]["versions"].get(version_key)
        if v:
            v["finalize"] = {
                "status": "error",
                "file": None,
                "error": error,
            }


def cleanup_old_tasks(max_age_seconds: int = 3600) -> list[str]:
    """清理超过 max_age_seconds 的旧任务，避免内存无限增长。

    返回被清理的 task_id 列表，供调用方联动清理关联的 Word 文件。
    """
    now = time.time()
    expired = [
        tid
        for tid, t in _tasks.items()
        if now - t["created_at"] > max_age_seconds
    ]
    for tid in expired:
        discard_task_usage(tid)
        del _tasks[tid]
    return expired
