from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
import asyncio
import base64
import logging

from user.token import test_token
from features.rough_outline.service import (
    get_rough_outline_ai_counts,
    generate_rough_outline,
    format_rough_outline_docx,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["rough_outline"])
_auth = APIRouter(dependencies=[Depends(test_token)])


class RoughOutlineRequest(BaseModel):
    """工具箱 - 毛坯纲目生成（每次只生成一篇，由 ai_index 指定用哪个 AI）"""
    outline_type: Literal["polish", "beginner", "youth", "truth", "sharing"] = Field(..., description="纲目类型")
    content: str = Field(..., min_length=1, max_length=100_000, description="原始纲目内容")
    ai_index: Optional[int] = Field(0, ge=0, description="该类型下第几个 AI（0 起），每次请求只调用一个 AI 生成一篇")


class RoughOutlineFormatRequest(BaseModel):
    """工具箱 - 毛胚纲目刷格式并下载（五类均可：润色版/初信版/青少年版/真理加强版/三分钟分享）"""
    outline_type: Literal["polish", "sharing", "beginner", "youth", "truth"] = Field(..., description="纲目类型")
    contents: List[str] = Field(..., min_length=1, max_length=10, description="多篇纲目正文，按顺序合并后刷格式")
    header_lines: List[str] = Field(default_factory=list, description="前三段：系列/总题/篇题，写入 DOCX 开头")


@_auth.get("/ai_search/rough_outline_config", summary="毛胚纲目 - 各类型对应的 AI 数量")
async def rough_outline_config():
    try:
        config = get_rough_outline_ai_counts()
        return config
    except Exception as e:
        logger.error(f"rough_outline_config 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/rough_outline", summary="工具箱 - 毛胚纲目生成（单次一篇）")
async def rough_outline(request: RoughOutlineRequest):
    try:
        result = await asyncio.to_thread(
            generate_rough_outline,
            request.outline_type,
            request.content,
            request.ai_index,
        )
        return {
            "results": result.get("results", []),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"rough_outline 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/rough_outline_format_and_download", summary="工具箱 - 毛胚纲目刷格式并下载（五类均可）")
async def rough_outline_format_and_download(request: RoughOutlineFormatRequest):
    try:
        result = await asyncio.to_thread(
            format_rough_outline_docx,
            request.outline_type,
            request.contents,
            request.header_lines,
        )
        if result.get("error") and not result.get("docx_bytes"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        if not result.get("docx_bytes"):
            raise HTTPException(status_code=400, detail=result.get("error") or "生成 DOCX 失败")

        return {
            "docx_base64": base64.b64encode(result["docx_bytes"]).decode("utf-8"),
            "filename": result.get("filename", "毛胚纲目.docx"),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"rough_outline_format_and_download 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


router.include_router(_auth)
