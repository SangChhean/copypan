# -*- coding: utf-8 -*-
"""CN 站工具箱薄壳路由（路径保持主站原样，业务逻辑复用 back_mic 模块）。"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from back_cn.auth import check_and_increment_daily_usage, get_current_user
from ai_search.ai_service import ai_service, format_english_bibco_docx
from features.bible_co.biblecollection import biblecollection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["cn-tools"])


def _require_user(request: Request) -> str:
    return get_current_user(request)["username"]


# ---------- 经文汇集 ----------


@router.post("/getvers")
def get_vers(request: Request, input: str = Form(), lang: str = Form(default="zh")):
    _require_user(request)
    try:
        return biblecollection(input, lang)
    except Exception:
        return JSONResponse(content={"error": "404 Not Found"}, status_code=404)


@router.post("/getvers/format_download")
def getvers_format_download(
    request: Request,
    contents: str = Form(),
    filename: str = Form(default="英文经文汇集"),
):
    _require_user(request)
    try:
        contents = contents.replace("\r\n", "\n").replace("\r", "\n")
        return format_english_bibco_docx(contents, filename)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/getvers/format_download_zh")
def getvers_format_download_zh(
    request: Request,
    contents: str = Form(),
    filename: str = Form(default="中文经文汇集"),
):
    _require_user(request)
    try:
        contents = contents.replace("\r\n", "\n").replace("\r", "\n")
        _header_placeholder = "\u200b"
        padded = f"{_header_placeholder}\n{_header_placeholder}\n{_header_placeholder}\n{contents}"
        result = ai_service.format_feast_outline_docx(
            contents=[padded],
            outline_type="with_scripture",
        )
        if result.get("error") and not result.get("docx_bytes"):
            return JSONResponse(content={"error": result["error"]}, status_code=400)
        docx_bytes = result.get("docx_bytes")
        if not docx_bytes:
            return JSONResponse(
                content={"error": result.get("error") or "生成 DOCX 失败"},
                status_code=400,
            )
        out_name = filename if filename.endswith(".docx") else f"{filename}.docx"
        return {
            "docx_base64": base64.b64encode(docx_bytes).decode("utf-8"),
            "filename": out_name,
        }
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# ---------- 纲目翻译 ----------


class OutlineTranslateRequest(BaseModel):
    direction: Literal["zh2en", "en2zh", "zh2ko", "en2es"] = Field(
        ..., description="zh2en=中文→英文, en2zh=英文→中文"
    )
    content: str = Field(..., min_length=1, max_length=100_000)
    outline_topic: Optional[str] = Field(None, max_length=200)
    output_format: Literal["docx", "pdf"] = Field("docx")


class FormatOutlineRequest(BaseModel):
    direction: Literal["zh2en", "en2zh", "zh_cn2tw", "zh_tw2cn"] = Field(...)
    translated_text: str = Field(..., min_length=1, max_length=100_000)
    output_format: Literal["docx", "pdf"] = Field("docx")
    is_outline: bool = Field(True)


@router.post("/ai_search/outline_translate", summary="工具箱 - 纲目翻译（中↔英）")
async def outline_translate(request: Request, body: OutlineTranslateRequest):
    username = _require_user(request)
    if body.direction in ("zh2ko", "en2es"):
        raise HTTPException(status_code=400, detail="该方向暂未开放")

    usage = check_and_increment_daily_usage(username, "translate")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"今日纲目翻译次数已达上限（{usage['limit']}次），请明天再来",
        )

    try:
        if body.direction == "zh2en":
            out = await asyncio.to_thread(
                ai_service.translate_outline,
                body.content,
                body.outline_topic,
                False,
            )
            return {
                "result": out.get("answer_en"),
                "title_en": out.get("title_en"),
                "error": out.get("error"),
            }
        if body.direction == "en2zh":
            out = await asyncio.to_thread(ai_service.translate_outline_en2zh, body.content)
            return {
                "result": out.get("answer_zh"),
                "error": out.get("error"),
            }
        raise HTTPException(status_code=400, detail=f"不支持的翻译方向：{body.direction}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("outline_translate 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai_search/format_outline_only", summary="工具箱 - 仅格式化已翻译的纲目")
async def format_outline_only(request: Request, body: FormatOutlineRequest):
    _require_user(request)
    try:
        result = await asyncio.to_thread(
            ai_service.format_outline_only,
            body.direction,
            body.translated_text,
            body.output_format,
            body.is_outline,
        )

        if result.get("error") and not (result.get("docx_bytes") or result.get("pdf_bytes")):
            raise HTTPException(status_code=400, detail=result.get("error"))

        response_data: dict = {"error": result.get("error")}

        if body.output_format == "pdf":
            if result.get("pdf_bytes"):
                response_data["pdf_base64"] = base64.b64encode(result["pdf_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.pdf")
            elif result.get("docx_bytes"):
                response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.docx").replace(".pdf", ".docx")
        else:
            if result.get("docx_bytes"):
                response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.docx")

        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("format_outline_only 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---------- 简繁互转 ----------


class OutlineToTraditionalRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)


class TraditionalToSimplifiedRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)


class CheckErrorCharsRequest(BaseModel):
    content: str = Field(..., max_length=100_000)


@router.post("/ai_search/outline_to_traditional", summary="简体纲目转台湾繁体")
async def outline_to_traditional_route(request: Request, body: OutlineToTraditionalRequest):
    _require_user(request)
    try:
        result = await asyncio.to_thread(ai_service.outline_to_traditional, body.content)
        if result.get("error") and result.get("answer_zh_tw") is None:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("简转繁失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai_search/traditional_to_simplified", summary="台湾繁体纲目转简体")
async def traditional_to_simplified_route(
    request: Request, body: TraditionalToSimplifiedRequest
):
    _require_user(request)
    try:
        result = await asyncio.to_thread(ai_service.traditional_to_simplified, body.content)
        if result.get("error") and result.get("answer_zh_cn") is None:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("繁转简失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ai_search/check_error_chars", summary="易错字检查")
async def check_error_chars_route(request: Request, body: CheckErrorCharsRequest):
    _require_user(request)
    try:
        hits = await asyncio.to_thread(ai_service.check_error_chars, body.content)
        return {"hits": hits}
    except Exception as e:
        logger.error("易错字检查失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
