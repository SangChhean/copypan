# -*- coding: utf-8 -*-
"""CN 站 PanAI 2.5 路由：负担说明生成 + KG-RAG 2.0 纲目制作。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from back_cn.auth import check_and_increment_daily_usage, get_current_user
from back_cn.panai.burden_service import generate_burden
from kg_rag.kg_rag_service import KgRagService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cn-panai"])


def _require_user(request: Request) -> str:
    return get_current_user(request)


class GenerateBurdenBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    outline_nature: str = Field(default="一般性", max_length=50)
    burden_points: list[str] = Field(..., min_length=1, max_length=5)

    @field_validator("burden_points")
    @classmethod
    def validate_points(cls, v: list[str]) -> list[str]:
        if not (1 <= len(v) <= 5):
            raise ValueError("burden_points 数量须在 1~5 之间")
        cleaned: list[str] = []
        for p in v:
            s = (p or "").strip()
            if not s:
                raise ValueError("负担点不能为空")
            if len(s) > 60:
                raise ValueError("每个负担点不能超过 60 字")
            cleaned.append(s)
        return cleaned

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("query 不能为空")
        return s


class KgRagQueryBody(BaseModel):
    """与主站 /api/kg_rag/query 兼容；CN 站强制 mode=2.0。"""

    query: str = Field(..., min_length=1, max_length=500)
    params: Optional[dict[str, Any]] = Field(default=None)
    mode: Optional[str] = Field(default=None, description="CN 站忽略，固定 2.0")
    burden_description: Optional[str] = Field(default=None)
    outline_nature: Optional[str] = Field(default=None)
    extra_params: Optional[dict[str, Any]] = Field(default=None)

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return (v or "").strip()


class CacheTranslationBody(BaseModel):
    cache_key: str = Field(..., min_length=1)
    field: str = Field(...)
    value: str = Field(..., min_length=1)


class TranslateOutlineBody(BaseModel):
    chinese_outline: str = Field(..., min_length=1, max_length=100_000)
    outline_topic: Optional[str] = Field(None, max_length=200)


@router.post("/api/cn/panai/generate_burden")
async def cn_generate_burden(request: Request, body: GenerateBurdenBody):
    username = _require_user(request)
    usage = check_and_increment_daily_usage(username, "burden")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"今日负担说明生成次数已达上限（{usage['limit']}次），请明天再来",
        )

    es_client = request.app.state.es_client
    try:
        return await generate_burden(
            query=body.query,
            outline_nature=body.outline_nature,
            burden_points=body.burden_points,
            es_client=es_client,
        )
    except Exception as e:
        logger.exception("generate_burden 失败")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/kg_rag/query")
async def cn_kg_rag_query(request: Request, body: KgRagQueryBody):
    username = _require_user(request)
    usage = check_and_increment_daily_usage(username, "outline")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"今日纲目制作次数已达上限（{usage['limit']}次），请明天再来",
        )

    params: dict[str, Any] = dict(body.params or {})
    if body.burden_description is not None:
        params["burden_description"] = body.burden_description
    if body.outline_nature is not None:
        params["outline_nature"] = body.outline_nature
    if body.extra_params:
        params.update(body.extra_params)
    params.setdefault("burden_description", "")
    params.setdefault("outline_nature", "一般性")
    params["depth"] = "general"

    service = request.app.state.kg_rag_service
    try:
        result = await service.full_query(body.query, params, mode="2.0")
        return result
    except Exception as e:
        logger.exception("kg_rag full_query 失败")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/kg_rag/cache_translation")
async def cn_cache_translation(request: Request, body: CacheTranslationBody):
    _require_user(request)
    if body.field not in ("answer_en", "answer_zh_tw"):
        return JSONResponse(
            status_code=400,
            content={"error": "field must be answer_en or answer_zh_tw"},
        )
    ok = KgRagService.update_cache_translation(body.cache_key, body.field, body.value)
    return {"ok": ok, "cache_key": body.cache_key, "field": body.field}


@router.post("/api/ai_search/translate_outline")
async def cn_translate_outline(request: Request, body: TranslateOutlineBody):
    """纲目英译（不计配额，与主站路径一致）。"""
    _require_user(request)
    from ai_search.ai_service import ai_service

    try:
        result = await asyncio.to_thread(
            ai_service.translate_outline,
            body.chinese_outline,
            body.outline_topic,
        )
        return result
    except Exception as e:
        logger.exception("translate_outline 失败")
        raise HTTPException(status_code=500, detail=str(e)) from e
