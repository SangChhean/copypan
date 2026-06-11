# -*- coding: utf-8 -*-
"""增强式翻译 API（主站副本，前缀 /api/ai_search/enhanced_translate）。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from user.token import test_token
from features.enhanced_translate.pool import update_record
from features.enhanced_translate.service import enhanced_translate

logger = logging.getLogger("ai_search.enhanced_translate")

router = APIRouter(prefix="/api/ai_search/enhanced_translate", tags=["enhanced_translate"])


class EnhancedTranslateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    prompt_override: str | None = Field(default=None, max_length=10_000)


class UpdateTranslationRequest(BaseModel):
    original_line: str = Field(..., min_length=1, max_length=10_000)
    new_translation: str = Field(..., min_length=1, max_length=10_000)


@router.post(
    "/translate",
    dependencies=[Depends(test_token)],
)
async def api_enhanced_translate(req: EnhancedTranslateRequest):
    try:
        return await enhanced_translate(req.content, req.prompt_override)
    except Exception as e:
        logger.exception("enhanced_translate 失败")
        return {"result": None, "refs": [], "error": str(e)}


@router.post(
    "/update_translation",
    dependencies=[Depends(test_token)],
)
async def api_update_translation(req: UpdateTranslationRequest):
    updated = update_record(req.original_line, req.new_translation)
    if not updated:
        return {
            "success": False,
            "error": "Additional Pool 中未找到对应条目，或译文为空",
        }
    return {"success": True}
