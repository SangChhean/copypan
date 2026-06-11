from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional
import asyncio
import logging

from user.token import test_token
from features.outline_translate.service import (
    translate_outline,
    translate_outline_en2zh,
    translate_outline_zh2ko,
    translate_outline_en2es,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["outline_translate"])
_auth = APIRouter(dependencies=[Depends(test_token)])


class OutlineTranslateRequest(BaseModel):
    """工具箱 - 纲目翻译：中翻英或英翻中"""
    direction: Literal["zh2en", "en2zh", "zh2ko", "en2es"] = Field(
        ..., description="zh2en=中文→英文, en2zh=英文→中文, zh2ko=中文→韩文, en2es=英文→西班牙语"
    )
    content: str = Field(..., min_length=1, max_length=100_000, description="待翻译的纲目全文")
    outline_topic: Optional[str] = Field(None, max_length=200, description="纲目主题（仅中翻英时用于翻译标题）")
    output_format: Literal["docx", "pdf"] = Field("docx", description="输出格式：docx 或 pdf，默认 docx")


@_auth.post("/ai_search/outline_translate", summary="工具箱 - 纲目翻译（中翻英 / 英翻中）")
async def outline_translate(request: OutlineTranslateRequest):
    try:
        if request.direction == "zh2en":
            out = await asyncio.to_thread(
                translate_outline,
                request.content,
                request.outline_topic,
                False,
            )
            return {
                "result": out.get("answer_en"),
                "title_en": out.get("title_en"),
                "error": out.get("error"),
            }
        elif request.direction == "en2zh":
            out = await asyncio.to_thread(translate_outline_en2zh, request.content)
            return {
                "result": out.get("answer_zh"),
                "error": out.get("error"),
            }
        elif request.direction == "zh2ko":
            out = await asyncio.to_thread(translate_outline_zh2ko, request.content)
            return {
                "result": out.get("answer_ko"),
                "error": out.get("error"),
            }
        elif request.direction == "en2es":
            out = await asyncio.to_thread(translate_outline_en2es, request.content)
            return {
                "result": out.get("answer_es"),
                "error": out.get("error"),
            }
        else:
            raise HTTPException(status_code=400, detail=f"不支持的翻译方向：{request.direction}")
    except Exception as e:
        logger.error(f"outline_translate 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


router.include_router(_auth)
