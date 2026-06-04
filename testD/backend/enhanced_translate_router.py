# -*- coding: utf-8 -*-
"""增强式翻译 API（挂载到主站 /api/kg_rag）。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from testD.backend._bootstrap import ensure_main_backend_path

ensure_main_backend_path()

from user.token import test_token
from testD.backend.enhanced_translate_service import (
    enhanced_translate,
    get_prompt_override,
    set_prompt_override,
)

logger = logging.getLogger("testD.enhanced_translate")

router = APIRouter(prefix="/api/kg_rag", tags=["kg_rag"])


class EnhancedTranslateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    prompt_override: str | None = Field(default=None, max_length=10_000)


class UpdatePromptRequest(BaseModel):
    prompt: str = Field(default="", max_length=10_000)


@router.post(
    "/enhanced_translate",
    dependencies=[Depends(test_token)],
)
async def api_enhanced_translate(req: EnhancedTranslateRequest):
    try:
        return await enhanced_translate(req.content, req.prompt_override)
    except Exception as e:
        logger.exception("enhanced_translate 失败")
        return {"result": None, "refs": [], "error": str(e)}


@router.post(
    "/enhanced_translate/update_prompt",
    dependencies=[Depends(test_token)],
)
async def api_update_prompt(req: UpdatePromptRequest):
    set_prompt_override(req.prompt)
    return {"success": True, "prompt": get_prompt_override()}
