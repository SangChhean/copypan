from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import asyncio
import logging

from user.token import test_token
from features.zh_convert.service import (
    outline_to_traditional,
    traditional_to_simplified,
    check_error_chars,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["zh_convert"])
_auth = APIRouter(dependencies=[Depends(test_token)])


class OutlineToTraditionalRequest(BaseModel):
    """简体纲目转台湾繁体：传入简体纲目全文"""
    content: str = Field(..., min_length=1, max_length=100_000, description="简体纲目全文")


class TraditionalToSimplifiedRequest(BaseModel):
    """台湾繁体纲目转简体：传入繁体纲目全文"""
    content: str = Field(..., min_length=1, max_length=100_000, description="台湾繁体纲目全文")


class CheckErrorCharsRequest(BaseModel):
    """易错字检查：传入繁体纲目全文（简繁转换结果）"""
    content: str = Field(..., max_length=100_000, description="待检查的纲目全文")


@_auth.post("/ai_search/outline_to_traditional", summary="简体纲目转台湾繁体")
async def outline_to_traditional_route(request: OutlineToTraditionalRequest):
    try:
        result = await asyncio.to_thread(outline_to_traditional, request.content)
        if result.get("error") and result.get("answer_zh_tw") is None:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"简转繁失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/traditional_to_simplified", summary="台湾繁体纲目转简体")
async def traditional_to_simplified_route(request: TraditionalToSimplifiedRequest):
    try:
        result = await asyncio.to_thread(traditional_to_simplified, request.content)
        if result.get("error") and result.get("answer_zh_cn") is None:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"繁转简失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/check_error_chars", summary="易错字检查（简繁互转结果）")
async def check_error_chars_route(request: CheckErrorCharsRequest):
    try:
        hits = await asyncio.to_thread(check_error_chars, request.content)
        return {"hits": hits}
    except Exception as e:
        logger.error(f"易错字检查失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


router.include_router(_auth)
