from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import asyncio
import base64
import logging

from user.token import test_token
from features.feast_outline.service import (
    format_feast_outline_docx,
    feast_outline_collect_scripture,
    feast_outline_morning_revival,
    feast_outline_transcript,
    feast_outline_composite,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["feast_outline"])
_auth = APIRouter(dependencies=[Depends(test_token)])


class FeastOutlineWithScriptureRequest(BaseModel):
    """节期纲目 - 带经文的纲目：经文汇集后刷格式并下载"""
    content: str = Field(..., min_length=1, max_length=100_000, description="纲目原文（将用经文汇集处理）")


class FeastOutlineMorningRevivalRequest(BaseModel):
    """节期纲目 - 晨兴信息选读的纲目：Claude 生成纲目后刷格式并下载"""
    content: str = Field(..., min_length=1, max_length=100_000, description="晨兴信息选读内容")


class FeastOutlineTranscriptRequest(BaseModel):
    """节期纲目 - 听抄稿的纲目：在原纲目基础上加听抄稿重点后刷格式并下载"""
    original_outline: str = Field(..., min_length=1, max_length=100_000, description="原纲目")
    transcript: str = Field(..., min_length=1, max_length=100_000, description="听抄稿内容")
    transcript_preface: Optional[str] = Field(None, max_length=50_000, description="听抄稿序言原文，生成时一并交给 Claude 做成序言纲目")
    transcript_addendum: Optional[str] = Field(None, max_length=50_000, description="听抄稿添言原文，生成时一并交给 Claude 做成添言纲目")


class FeastOutlineCompositeRequest(BaseModel):
    """节期纲目 - 复合的纲目：将晨兴纲目融入听抄稿纲目后刷格式并下载"""
    transcript_outline: str = Field(..., min_length=1, max_length=100_000, description="听抄稿的纲目")
    morning_revival_outline: str = Field(..., min_length=1, max_length=100_000, description="晨兴信息选读的纲目")


class FeastOutlineFormatDownloadRequest(BaseModel):
    """节期纲目 - 刷格式并下载：传入正文列表、类型、可选前三行与文件名"""
    contents: List[str] = Field(..., min_length=1, max_length=20, description="纲目正文列表，合并后刷格式")
    outline_type: Optional[str] = Field(
        "original",
        description="纲目类型：original | with_scripture | morning_revival | transcript | composite，决定刷格式规则",
    )
    line1: Optional[str] = Field(None, max_length=500, description="刷格式时写入文档第一行")
    line2: Optional[str] = Field(None, max_length=500, description="刷格式时写入文档第二行")
    line3: Optional[str] = Field(None, max_length=500, description="刷格式时写入文档第三行")
    filename: Optional[str] = Field(None, max_length=200, description="下载文件名，默认 节期纲目.docx")
    morning_revival_content: Optional[str] = Field(None, max_length=100_000, description="晨兴信息选读原文，刷格式时在晨兴纲目末行后分页并追加「晨兴圣言信息：」+ 该内容")
    transcript_content: Optional[str] = Field(None, max_length=100_000, description="听抄稿原文，刷格式时在听抄稿纲目末行后分页并追加「听抄信息：」+ 该内容")
    transcript_preface: Optional[str] = Field(None, max_length=50_000, description="听抄稿序言原文，当未传 preface_outline 时由服务端生成序言纲目")
    transcript_addendum: Optional[str] = Field(None, max_length=50_000, description="听抄稿添言原文，当未传 addendum_outline 时由服务端生成添言纲目")
    preface_outline: Optional[str] = Field(None, max_length=50_000, description="已生成的序言纲目，优先使用（生成节期纲目时一并生成）")
    addendum_outline: Optional[str] = Field(None, max_length=50_000, description="已生成的添言纲目，优先使用（生成节期纲目时一并生成）")


def _feast_outline_docx_response(result: dict, default_filename: str = "节期纲目.docx"):
    """节期纲目 DOCX 下载统一响应"""
    if result.get("error") and not result.get("docx_bytes"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    if not result.get("docx_bytes"):
        raise HTTPException(status_code=400, detail=result.get("error") or "生成 DOCX 失败")
    return {
        "docx_base64": base64.b64encode(result["docx_bytes"]).decode("utf-8"),
        "filename": result.get("filename", default_filename),
        "error": result.get("error"),
    }


@_auth.post("/ai_search/feast_outline/scripture_text", summary="节期纲目 - 仅经文汇集，返回带经文文本（供多选生成用）")
async def feast_outline_scripture_text(request: FeastOutlineWithScriptureRequest):
    try:
        content = await asyncio.to_thread(
            feast_outline_collect_scripture,
            request.content.strip(),
        )
        return {"content": content or ""}
    except Exception as e:
        logger.error(f"feast_outline_scripture_text 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/feast_outline/generate/morning_revival", summary="节期纲目 - 仅生成晨兴纲目文本（供多选生成用）")
async def feast_outline_generate_morning_revival(request: FeastOutlineMorningRevivalRequest):
    logger.info("feast_outline/generate/morning_revival 收到请求")
    try:
        gen = await asyncio.to_thread(
            feast_outline_morning_revival,
            request.content.strip(),
        )
        if gen.get("error"):
            raise HTTPException(status_code=400, detail=gen.get("error"))
        return {"outline": (gen.get("outline") or "").strip()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_generate_morning_revival 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/feast_outline/generate/transcript", summary="节期纲目 - 仅生成听抄稿纲目文本（供多选生成用）")
async def feast_outline_generate_transcript(request: FeastOutlineTranscriptRequest):
    logger.info("feast_outline/generate/transcript 收到请求")
    try:
        gen = await asyncio.to_thread(
            feast_outline_transcript,
            request.original_outline.strip(),
            request.transcript.strip(),
            request.transcript_preface.strip() if request.transcript_preface else None,
            request.transcript_addendum.strip() if request.transcript_addendum else None,
        )
        if gen.get("error"):
            raise HTTPException(status_code=400, detail=gen.get("error"))
        out = {"outline": (gen.get("outline") or "").strip()}
        if gen.get("preface_outline") is not None:
            out["preface_outline"] = gen.get("preface_outline") or ""
        if gen.get("addendum_outline") is not None:
            out["addendum_outline"] = gen.get("addendum_outline") or ""
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_generate_transcript 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/feast_outline/generate/composite", summary="节期纲目 - 仅生成复合纲目文本（供多选生成用）")
async def feast_outline_generate_composite(request: FeastOutlineCompositeRequest):
    try:
        gen = await asyncio.to_thread(
            feast_outline_composite,
            request.transcript_outline.strip(),
            request.morning_revival_outline.strip(),
        )
        if gen.get("error"):
            raise HTTPException(status_code=400, detail=gen.get("error"))
        return {"outline": (gen.get("outline") or "").strip()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_generate_composite 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/feast_outline/format_download", summary="节期纲目 - 刷格式并下载（传入正文列表）")
async def feast_outline_format_download(request: FeastOutlineFormatDownloadRequest):
    try:
        result = await asyncio.to_thread(
            format_feast_outline_docx,
            [c.strip() for c in request.contents if (c or "").strip()],
            request.outline_type or "original",
            request.line1,
            request.line2,
            request.line3,
            request.morning_revival_content,
            request.transcript_content,
            request.transcript_preface,
            request.transcript_addendum,
            request.preface_outline,
            request.addendum_outline,
        )
        if result.get("error") and not result.get("docx_bytes"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        if not result.get("docx_bytes"):
            raise HTTPException(status_code=400, detail=result.get("error") or "生成 DOCX 失败")
        filename = (result.get("filename") or "").strip() or (request.filename or "").strip() or "节期纲目.docx"
        if not filename.endswith(".docx"):
            filename = filename + ".docx"
        return {
            "docx_base64": base64.b64encode(result["docx_bytes"]).decode("utf-8"),
            "filename": filename,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_format_download 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


router.include_router(_auth)
