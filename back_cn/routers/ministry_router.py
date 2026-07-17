# -*- coding: utf-8 -*-
"""CN 站职事书报追求材料制作：复用真理加强版生成流程。"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from back_cn.auth import (
    check_and_increment_daily_usage,
    get_current_user,
    quota_exceeded_message,
    refund_daily_usage,
)
from back_cn.roundtable.format_service import (
    format_version_preview,
    format_version_preview_html,
)
from back_cn.roundtable.ministry_helpers import (
    DISPLAY_LABEL,
    apply_unified_field_overrides,
    build_original_texts,
    patch_source_lines,
)
from back_cn.roundtable.ministry_step5 import build_ministry_file
from back_cn.roundtable.step1_service import generate_unified_fields
from back_cn.roundtable.step2_service import generate_version
from back_cn.roundtable.task_manager import (
    cleanup_old_tasks,
    create_task,
    get_task,
    set_finalize_done,
    set_finalize_error,
    set_finalize_running,
    set_unified_fields,
    set_version_done,
    set_version_error,
    update_version_progress,
)
from back_cn.roundtable.usage_tracker import (
    discard_task_usage,
    init_task_usage,
    log_task_usage,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cn-ministry"])

VERSION_KEY = "truth"
TEXT_MIN_LEN = 1500
TEXT_MAX_LEN = 30000

_PENDING_FILES: dict[str, tuple[Path, str]] = {}


def cleanup_files_for_task(task_id: str) -> None:
    tokens_to_remove = [
        t for t, (_path, tid) in _PENDING_FILES.items() if tid == task_id
    ]
    for token in tokens_to_remove:
        path, _ = _PENDING_FILES.pop(token)
        path.unlink(missing_ok=True)


def _cleanup_expired_tasks() -> None:
    for tid in cleanup_old_tasks():
        cleanup_files_for_task(tid)


class GenerateMinistryBody(BaseModel):
    text: str = Field(..., min_length=TEXT_MIN_LEN, max_length=TEXT_MAX_LEN)
    outline_title: str = Field(..., min_length=1, max_length=200)
    book_name: str = Field(default="", max_length=100)
    chapter_info: str = Field(default="", max_length=100)
    week_number: str | None = Field(default=None, max_length=20)

    @field_validator("text", "outline_title", "book_name", "chapter_info")
    @classmethod
    def _strip_text_fields(cls, v: str) -> str:
        return (v or "").strip()

    @field_validator("outline_title")
    @classmethod
    def _outline_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("纲要题目不能为空")
        return v

    @field_validator("week_number")
    @classmethod
    def _strip_week(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v if v else None


class FinalizeMinistryBody(BaseModel):
    task_id: str = Field(..., min_length=1)


@router.post("/api/cn/ministry/generate")
async def generate_ministry(request: Request, body: GenerateMinistryBody):
    username = get_current_user(request)["username"]

    usage = check_and_increment_daily_usage(username, "ministry_pursuit")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=quota_exceeded_message("ministry_pursuit", usage["limit"]),
        )

    _cleanup_expired_tasks()
    task_id = create_task([VERSION_KEY], week_number=body.week_number)
    init_task_usage(task_id, [VERSION_KEY])

    original_texts = build_original_texts(body.text, body.book_name)

    async def run_background() -> None:
        interrupt_msg = "生成任务被中断（服务重启），请重新生成"
        try:
            unified_fields = await generate_unified_fields(
                original_texts,
                week_number=body.week_number,
                task_id=task_id,
            )
            apply_unified_field_overrides(
                unified_fields,
                outline_title=body.outline_title,
                week_number=body.week_number,
                book_name=body.book_name,
                chapter_info=body.chapter_info,
            )
            set_unified_fields(task_id, unified_fields)

            def callback(stage: str, attempt: int) -> None:
                update_version_progress(task_id, VERSION_KEY, stage, attempt)

            result = await generate_version(
                VERSION_KEY,
                original_texts,
                unified_fields,
                on_progress=callback,
                task_id=task_id,
            )

            # 须在 format_version_preview 之前覆盖 source_line
            patch_source_lines(
                result["data"],
                body.book_name,
                body.chapter_info,
            )

            version_payload = {
                "label": DISPLAY_LABEL,
                "word_count": result["word_count"],
                "preview_text": format_version_preview(unified_fields, result),
                "preview_html": format_version_preview_html(
                    unified_fields, result
                ),
                "raw_data": result["data"],
            }
            set_version_done(task_id, VERSION_KEY, version_payload)
        except asyncio.CancelledError:
            task = get_task(task_id)
            if not task or task["versions"].get(VERSION_KEY, {}).get("status") != "done":
                set_version_error(task_id, VERSION_KEY, interrupt_msg)
            raise
        except Exception as e:
            refund_daily_usage(username, "ministry_pursuit")
            logger.info(
                "[配额退还] %s 职事书报生成失败，已退还ministry_pursuit配额: %s",
                username,
                e,
            )
            task = get_task(task_id)
            if not task or task["versions"].get(VERSION_KEY, {}).get("status") != "done":
                if isinstance(e, RuntimeError):
                    set_version_error(task_id, VERSION_KEY, "生成失败，请重试")
                else:
                    set_version_error(task_id, VERSION_KEY, "生成失败，请重试")
                    logger.exception("ministry generate failed: %s", e)
        finally:
            log_task_usage(task_id)
            discard_task_usage(task_id)

    asyncio.create_task(run_background())
    return {"task_id": task_id}


@router.get("/api/cn/ministry/task/{task_id}")
async def get_task_status(task_id: str, request: Request):
    get_current_user(request)
    _cleanup_expired_tasks()
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return task


@router.post("/api/cn/ministry/finalize")
async def finalize_ministry(request: Request, body: FinalizeMinistryBody):
    get_current_user(request)
    _cleanup_expired_tasks()

    task = get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    version = task.get("versions", {}).get(VERSION_KEY)
    if not version:
        raise HTTPException(status_code=400, detail="该任务未生成内容")
    if version.get("status") != "done" or not (version.get("result") or {}).get(
        "raw_data"
    ):
        raise HTTPException(status_code=409, detail="内容尚未生成完成")
    if not task.get("unified_fields"):
        raise HTTPException(status_code=409, detail="统一字段尚未生成完成")

    finalize = version.get("finalize") or {}
    if finalize.get("status") == "running":
        return {"task_id": body.task_id, "status": finalize["status"]}

    set_finalize_running(body.task_id, VERSION_KEY)

    async def run_finalize() -> None:
        try:
            path = await asyncio.to_thread(
                build_ministry_file,
                task["unified_fields"],
                version["result"]["raw_data"],
                task.get("week_number"),
            )
            token = uuid.uuid4().hex
            _PENDING_FILES[token] = (path, body.task_id)
            set_finalize_done(
                body.task_id,
                VERSION_KEY,
                {
                    "version": VERSION_KEY,
                    "label": DISPLAY_LABEL,
                    "filename": path.name,
                    "token": token,
                },
            )
        except FileNotFoundError as e:
            logger.exception("ministry finalize failed: task=%s", body.task_id)
            set_finalize_error(
                body.task_id,
                VERSION_KEY,
                f"Word文档生成失败：{e}",
            )
        except Exception:
            logger.exception("ministry finalize failed: task=%s", body.task_id)
            set_finalize_error(body.task_id, VERSION_KEY, "Word文档生成失败，请重试")

    asyncio.create_task(run_finalize())
    return {"task_id": body.task_id, "status": "running"}


@router.post("/api/cn/ministry/cleanup_task/{task_id}")
async def cleanup_task_endpoint(task_id: str, request: Request):
    get_current_user(request)
    cleanup_files_for_task(task_id)
    discard_task_usage(task_id)
    return {"cleaned": True}


@router.get("/api/cn/ministry/download/{token}")
async def download_ministry_file(token: str, request: Request):
    get_current_user(request)
    entry = _PENDING_FILES.get(token)
    if not entry:
        raise HTTPException(status_code=404, detail="文件不存在或已过期，请重新生成")
    path, _ = entry
    if not path.exists():
        _PENDING_FILES.pop(token, None)
        raise HTTPException(status_code=404, detail="文件不存在或已过期，请重新生成")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )
