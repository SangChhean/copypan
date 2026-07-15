# -*- coding: utf-8 -*-
"""CN 站小排生命读经材料制作：生成四版本预览 + 最终文档。"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from back_cn.auth import (
    check_and_increment_daily_usage,
    get_current_user,
    refund_daily_usage,
)
from back_cn.roundtable.format_service import (
    format_version_preview,
    format_version_preview_html,
)
from back_cn.roundtable.life_text_service import (
    get_message,
    get_messages_by_selection,
    list_book_issues,
    list_books,
    resolve_cross_book_selection,
)
from back_cn.roundtable.prompts import VERSION_CONFIG
from back_cn.roundtable.step1_service import generate_unified_fields
from back_cn.roundtable.step2_service import generate_version
from back_cn.roundtable.step5_service import VERSION_LABELS, build_version_file
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

router = APIRouter(tags=["cn-roundtable"])

# token -> 文件路径；进程内内存态，重启会丢失（可接受）
_PENDING_FILES: dict[str, Path] = {}


class GenerateRoundtableBody(BaseModel):
    book: int
    start_issue: int
    count: int = Field(..., ge=1, le=3)
    versions: list[str] = Field(..., min_length=1, max_length=4)
    week_number: str | None = Field(default=None, max_length=20)

    @field_validator("versions")
    @classmethod
    def _valid_versions(cls, v: list[str]) -> list[str]:
        invalid = [k for k in v if k not in VERSION_CONFIG]
        if invalid:
            raise ValueError(
                f"未知的版本：{invalid}，可选值为 {list(VERSION_CONFIG.keys())}"
            )
        return v

    @field_validator("week_number")
    @classmethod
    def _strip_week(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v if v else None


class PreviewSelectionBody(BaseModel):
    book: int
    start_issue: int
    count: int = Field(..., ge=1, le=3)


class FinalizeOneVersionBody(BaseModel):
    task_id: str = Field(..., min_length=1)
    version_key: str

    @field_validator("version_key")
    @classmethod
    def _valid_version(cls, v: str) -> str:
        if v not in VERSION_CONFIG:
            raise ValueError(
                f"未知的版本：{v}，可选值为 {list(VERSION_CONFIG.keys())}"
            )
        return v


@router.get("/api/cn/roundtable/books")
async def get_book_list(request: Request):
    get_current_user(request)
    return {"books": list_books()}


@router.get("/api/cn/roundtable/book_issues/{book_id}")
async def get_book_issues(book_id: int, request: Request):
    get_current_user(request)
    try:
        return list_book_issues(book_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"卷号 {book_id} 没有生命读经数据"
        ) from None


@router.post("/api/cn/roundtable/preview_selection")
async def preview_selection(request: Request, body: PreviewSelectionBody):
    get_current_user(request)
    try:
        selection = resolve_cross_book_selection(
            body.book, body.start_issue, body.count
        )
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    items = []
    for b, i in selection:
        try:
            msg = get_message(b, i)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        items.append(
            {
                "book": b,
                "issue": i,
                "book_name": msg["book_name"],
                "title": msg["title"],
            }
        )
    crosses_book = len({item["book"] for item in items}) > 1
    return {"selection": items, "crosses_book": crosses_book}


@router.post("/api/cn/roundtable/generate")
async def generate_roundtable(request: Request, body: GenerateRoundtableBody):
    username = get_current_user(request)["username"]

    try:
        selection = resolve_cross_book_selection(
            body.book, body.start_issue, body.count
        )
        texts = get_messages_by_selection(selection)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    usage = check_and_increment_daily_usage(username, "roundtable")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"今日小排材料制作次数已达上限（{usage['limit']}次），请明天再来",
        )

    cleanup_old_tasks()
    task_id = create_task(body.versions, week_number=body.week_number)
    init_task_usage(task_id, body.versions)

    async def run_background() -> None:
        interrupt_msg = "生成任务被中断（服务重启），请重新生成"
        try:
            unified_fields = await generate_unified_fields(
                texts,
                week_number=body.week_number,
                task_id=task_id,
            )
            set_unified_fields(task_id, unified_fields)

            async def run_one(version_key: str) -> None:
                def callback(stage: str, attempt: int) -> None:
                    update_version_progress(
                        task_id, version_key, stage, attempt
                    )

                try:
                    result = await generate_version(
                        version_key,
                        texts,
                        unified_fields,
                        on_progress=callback,
                        task_id=task_id,
                    )
                    set_version_done(
                        task_id,
                        version_key,
                        {
                            "label": result["label"],
                            "word_count": result["word_count"],
                            "preview_text": format_version_preview(
                                unified_fields, result
                            ),
                            "preview_html": format_version_preview_html(
                                unified_fields, result
                            ),
                            "raw_data": result["data"],
                        },
                    )
                except asyncio.CancelledError:
                    set_version_error(task_id, version_key, interrupt_msg)
                    raise  # 必须重新抛出，不能吞掉取消
                except RuntimeError:
                    set_version_error(task_id, version_key, "生成失败，请重试")
                except Exception as e:
                    set_version_error(task_id, version_key, "生成失败，请重试")
                    logger.exception(
                        "roundtable version %s failed: %s", version_key, e
                    )

            await asyncio.gather(
                *[run_one(v) for v in body.versions], return_exceptions=True
            )

            task = get_task(task_id)
            if task:
                all_failed = all(
                    v["status"] == "error" for v in task["versions"].values()
                )
                if all_failed:
                    refund_daily_usage(username, "roundtable")
                    logger.info(
                        "[配额退还] %s 本次生成全部版本失败，已退还roundtable配额",
                        username,
                    )
        except asyncio.CancelledError:
            for v in body.versions:
                task = get_task(task_id)
                if task and task["versions"].get(v, {}).get("status") == "done":
                    continue
                set_version_error(task_id, v, interrupt_msg)
            raise
        except Exception as e:
            refund_daily_usage(username, "roundtable")
            logger.info(
                "[配额退还] %s Step1失败，已退还roundtable配额: %s",
                username,
                e,
            )
            for v in body.versions:
                task = get_task(task_id)
                if task and task["versions"].get(v, {}).get("status") == "done":
                    continue
                set_version_error(task_id, v, str(e))
        finally:
            log_task_usage(task_id)
            discard_task_usage(task_id)

    asyncio.create_task(run_background())
    return {"task_id": task_id}


@router.get("/api/cn/roundtable/task/{task_id}")
async def get_task_status(task_id: str, request: Request):
    get_current_user(request)
    cleanup_old_tasks()
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return task


@router.post("/api/cn/roundtable/finalize_one")
async def finalize_one_version(request: Request, body: FinalizeOneVersionBody):
    get_current_user(request)
    cleanup_old_tasks()

    task = get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    version = task.get("versions", {}).get(body.version_key)
    if not version:
        raise HTTPException(status_code=400, detail="该任务未生成所选版本")
    if version.get("status") != "done" or not (version.get("result") or {}).get(
        "raw_data"
    ):
        raise HTTPException(status_code=409, detail="该版本内容尚未生成完成")
    if not task.get("unified_fields"):
        raise HTTPException(status_code=409, detail="统一字段尚未生成完成")

    finalize = version.get("finalize") or {}
    if finalize.get("status") in {"running", "done"}:
        return {
            "task_id": body.task_id,
            "version_key": body.version_key,
            "status": finalize["status"],
        }

    set_finalize_running(body.task_id, body.version_key)

    async def run_finalize() -> None:
        try:
            path = await asyncio.to_thread(
                build_version_file,
                body.version_key,
                task["unified_fields"],
                version["result"]["raw_data"],
                task.get("week_number"),
            )
            token = uuid.uuid4().hex
            _PENDING_FILES[token] = path
            set_finalize_done(
                body.task_id,
                body.version_key,
                {
                    "version": body.version_key,
                    "label": VERSION_LABELS[body.version_key],
                    "filename": path.name,
                    "token": token,
                },
            )
        except Exception:
            logger.exception(
                "roundtable finalize failed: task=%s version=%s",
                body.task_id,
                body.version_key,
            )
            set_finalize_error(
                body.task_id, body.version_key, "Word文档生成失败，请重试"
            )

    asyncio.create_task(run_finalize())
    return {
        "task_id": body.task_id,
        "version_key": body.version_key,
        "status": "running",
    }


def _cleanup_file(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get("/api/cn/roundtable/download/{token}")
async def download_roundtable_file(
    token: str, request: Request, background_tasks: BackgroundTasks
):
    get_current_user(request)  # 仍需登录态才能下载
    path = _PENDING_FILES.pop(token, None)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在或已过期，请重新生成")
    background_tasks.add_task(_cleanup_file, path)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )
