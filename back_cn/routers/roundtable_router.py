# -*- coding: utf-8 -*-
"""CN 站小排生命读经材料制作：生成四版本预览。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from back_cn.auth import check_and_increment_daily_usage, get_current_user
from back_cn.roundtable.format_service import (
    format_version_preview,
    format_version_preview_html,
)
from back_cn.roundtable.life_text_service import get_messages
from back_cn.roundtable.prompts import VERSION_CONFIG
from back_cn.roundtable.step1_service import generate_unified_fields
from back_cn.roundtable.step2_service import generate_all_versions

router = APIRouter(tags=["cn-roundtable"])


class GenerateRoundtableBody(BaseModel):
    book: int
    issues: list[int] = Field(..., min_length=1, max_length=3)
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


@router.post("/api/cn/roundtable/generate")
async def generate_roundtable(request: Request, body: GenerateRoundtableBody):
    username = get_current_user(request)["username"]

    sorted_issues = sorted(body.issues)
    for i in range(1, len(sorted_issues)):
        if sorted_issues[i] != sorted_issues[i - 1] + 1:
            raise HTTPException(
                status_code=400,
                detail=f"篇号必须连续，收到不连续的篇号：{body.issues}",
            )

    usage = check_and_increment_daily_usage(username, "roundtable")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"今日小排材料制作次数已达上限（{usage['limit']}次），请明天再来",
        )

    try:
        texts = get_messages(body.book, sorted_issues)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        unified_fields = await generate_unified_fields(
            texts, week_number=body.week_number
        )
        versions = await generate_all_versions(
            texts, unified_fields, version_keys=body.versions
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    previews = {
        key: {
            "label": v["label"],
            "word_count": v["word_count"],
            "preview_text": format_version_preview(unified_fields, v),
            "preview_html": format_version_preview_html(unified_fields, v),
            "raw_data": v["data"],
        }
        for key, v in versions.items()
    }

    return {
        "unified_fields": unified_fields,
        "versions": previews,
    }
