"""
AI搜索API路由
提供/api/ai_search接口（问答、健康检查、监控统计）
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
import asyncio
import base64
import json
import logging
from urllib.parse import quote

from .ai_service import ai_service, get_index_weights_for_display
from .monitoring import get_monitoring

logger = logging.getLogger(__name__)

# 创建路由，前缀 /api 使接口为 /api/ai_search、/api/ai_search/health 等
router = APIRouter(prefix="/api")


def _extract_metadata(payload) -> dict:
    """从请求中提取额外提示信息"""
    fields = {
        "outline_topic": getattr(payload, "outline_topic", None),
        "burden_description": getattr(payload, "burden_description", None),
        "special_needs": getattr(payload, "special_needs", None),
        "audience": getattr(payload, "audience", None),
    }
    return {
        key: value.strip()
        for key, value in fields.items()
        if isinstance(value, str) and value.strip()
    }


class SearchRequest(BaseModel):
    """AI搜索请求模型"""
    question: str = Field(..., min_length=1, max_length=500, description="用户问题")
    max_results: Optional[int] = Field(30, ge=1, le=50, description="最多返回结果数")
    depth: Optional[str] = Field("general", description="搜索深度：general(一般)或deep(深度)")
    outline_topic: Optional[str] = Field(None, max_length=200, description="纲目主题")
    burden_description: Optional[str] = Field(None, max_length=300, description="负担说明")
    special_needs: Optional[str] = Field(None, max_length=300, description="纲目性质")
    audience: Optional[str] = Field(None, max_length=200, description="面对对象")

    class Config:
        json_schema_extra = {
            "example": {
                "question": "圣经如何定义爱？",
                "max_results": 30,
                "depth": "general"
            }
        }


class SearchOnlyRequest(BaseModel):
    """方案A - 第一步：仅搜索"""
    question: str = Field(..., min_length=1, max_length=500)
    depth: Optional[str] = Field("general", description="general 或 deep")
    outline_topic: Optional[str] = Field(None, max_length=200)
    burden_description: Optional[str] = Field(None, max_length=300)
    special_needs: Optional[str] = Field(None, max_length=300)
    audience: Optional[str] = Field(None, max_length=200)


class GenerateOnlyRequest(BaseModel):
    """方案A - 第二步：生成答案"""
    question: str = Field(..., min_length=1, max_length=500)
    search_id: str = Field(..., description="第一步返回的 search_id")
    max_results: Optional[int] = Field(30, ge=1, le=50)
    outline_topic: Optional[str] = Field(None, max_length=200)
    burden_description: Optional[str] = Field(None, max_length=300)
    special_needs: Optional[str] = Field(None, max_length=300)
    audience: Optional[str] = Field(None, max_length=200)


class SearchResponse(BaseModel):
    """AI搜索响应模型"""
    answer: str
    sources: list
    cached: bool
    tokens: Optional[dict] = None
    search_time: Optional[float] = None
    ai_time: Optional[float] = None
    total_time: Optional[float] = None
    claude_payload: Optional[dict] = None


class TranslateOutlineRequest(BaseModel):
    """英文纲目翻译请求：传入中文纲目全文和标题"""
    chinese_outline: str = Field(..., min_length=1, max_length=100_000, description="中文纲目全文")
    outline_topic: Optional[str] = Field(None, max_length=200, description="纲目主题（用于翻译标题）")


class OutlineToTraditionalRequest(BaseModel):
    """简体纲目转台湾繁体：传入简体纲目全文"""
    content: str = Field(..., min_length=1, max_length=100_000, description="简体纲目全文")


class TraditionalToSimplifiedRequest(BaseModel):
    """台湾繁体纲目转简体：传入繁体纲目全文"""
    content: str = Field(..., min_length=1, max_length=100_000, description="台湾繁体纲目全文")


class ConvertAndFormatRequest(BaseModel):
    """简繁转换并格式化：传入纲目全文"""
    direction: Literal["zh_cn2tw", "zh_tw2cn"] = Field(..., description="zh_cn2tw=简体→繁体, zh_tw2cn=繁体→简体")
    content: str = Field(..., min_length=1, max_length=100_000, description="待转换的纲目全文")
    output_format: Literal["docx", "pdf"] = Field("docx", description="输出格式：docx 或 pdf，默认 docx")


class OutlineTranslateRequest(BaseModel):
    """工具箱 - 纲目翻译：中翻英或英翻中"""
    direction: Literal["zh2en", "en2zh"] = Field(..., description="zh2en=中文→英文, en2zh=英文→中文")
    content: str = Field(..., min_length=1, max_length=100_000, description="待翻译的纲目全文")
    outline_topic: Optional[str] = Field(None, max_length=200, description="纲目主题（仅中翻英时用于翻译标题）")
    output_format: Literal["docx", "pdf"] = Field("docx", description="输出格式：docx 或 pdf，默认 docx")


class FormatOutlineRequest(BaseModel):
    """工具箱 - 仅格式化已翻译/转换的纲目（不调用翻译/转换 API）"""
    direction: Literal["zh2en", "en2zh", "zh_cn2tw", "zh_tw2cn"] = Field(..., description="zh2en=英文纲目, en2zh/zh_cn2tw/zh_tw2cn=中文纲目")
    translated_text: str = Field(..., min_length=1, max_length=100_000, description="已翻译/转换的纲目全文")
    output_format: Literal["docx", "pdf"] = Field("docx", description="输出格式：docx 或 pdf，默认 docx")


class RoughOutlineRequest(BaseModel):
    """工具箱 - 毛坯纲目生成（每次只生成一篇，由 ai_index 指定用哪个 AI）"""
    outline_type: Literal["polish", "beginner", "youth", "truth", "sharing"] = Field(..., description="纲目类型")
    content: str = Field(..., min_length=1, max_length=100_000, description="原始纲目内容")
    ai_index: Optional[int] = Field(0, ge=0, description="该类型下第几个 AI（0 起），每次请求只调用一个 AI 生成一篇")


class RoughOutlineFormatRequest(BaseModel):
    """工具箱 - 毛胚纲目刷格式并下载（五类均可：润色版/初信版/青少年版/真理加强版/三分钟分享）"""
    outline_type: Literal["polish", "sharing", "beginner", "youth", "truth"] = Field(..., description="纲目类型")
    contents: List[str] = Field(..., min_length=1, max_length=10, description="多篇纲目正文，按顺序合并后刷格式")


# ---------- 节期纲目 ----------
class FeastOutlineOriginalRequest(BaseModel):
    """节期纲目 - 纲目的原文：刷格式并下载"""
    content: str = Field(..., min_length=1, max_length=100_000, description="无格式的纲目原文")


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


class FeastOutlineCompositeRequest(BaseModel):
    """节期纲目 - 复合的纲目：将晨兴纲目融入听抄稿纲目后刷格式并下载"""
    transcript_outline: str = Field(..., min_length=1, max_length=100_000, description="听抄稿的纲目")
    morning_revival_outline: str = Field(..., min_length=1, max_length=100_000, description="晨兴信息选读的纲目")


class InfoRetrievalRequest(BaseModel):
    """信息检索请求：多关键词 AND、排除关键词 OR、DOCX 大小上限"""
    keyword: str = Field(..., min_length=1, max_length=500, description="搜索关键词，空格隔开，多词 AND")
    exclude_keywords: Optional[str] = Field(None, max_length=500, description="排除关键词，空格隔开，多词 OR")
    max_size_mb: Optional[int] = Field(100, description="单 DOCX 合并大小上限（MB），40 或 100")


# ========== 方案A：分步搜索接口 ==========

@router.post("/ai_search/search", summary="第一步：仅检索（返回引用来源）")
async def ai_search_step1(request: SearchOnlyRequest):
    """
    方案A 第一步：仅执行 ES 搜索，快速返回引用来源。
    用户可在等待 AI 生成期间浏览这些来源。
    返回 search_id 供第二步使用。
    """
    try:
        metadata = _extract_metadata(request)
        result = await asyncio.to_thread(
            ai_service.search_only,
            request.question,
            request.depth or "general",
            metadata,
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result.get("message", "搜索失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ai_search/search 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/generate", response_model=SearchResponse, summary="第二步：生成答案")
async def ai_search_step2(request: GenerateOnlyRequest):
    """
    方案A 第二步：使用 search_id 从 Redis 获取上下文，调用 Claude 生成答案。
    search_id 有效期为 5 分钟。
    """
    try:
        metadata = _extract_metadata(request)
        result = await asyncio.to_thread(
            ai_service.generate_only,
            request.question,
            request.search_id,
            request.max_results or 30,
            metadata,
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result.get("answer", "生成失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ai_search/generate 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/translate_outline", summary="将中文纲目翻译为英文纲目")
async def translate_outline(request: TranslateOutlineRequest):
    """
    用户勾选「同时生成英文纲目」后，前端用已展示的中文纲目调用此接口。
    后端用 Gemini 翻译，失败时自动重试 1 次；同一中文纲目会缓存 24 小时。
    同时翻译纲目主题作为英文标题。
    使用 asyncio.to_thread 避免阻塞事件循环，以便与「繁体纲目」请求并发处理。
    """
    try:
        result = await asyncio.to_thread(
            ai_service.translate_outline,
            request.chinese_outline,
            request.outline_topic,
        )
        return result
    except Exception as e:
        logger.error(f"翻译纲目失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/outline_to_traditional", summary="简体纲目转台湾繁体")
async def outline_to_traditional(request: OutlineToTraditionalRequest):
    """
    用户勾选「同时生成繁体纲目」后，前端用已展示的简体纲目调用此接口。
    后端先按术语表替换，再通用简→繁（zhconv zh-tw）。
    使用 asyncio.to_thread 避免阻塞事件循环。
    """
    try:
        result = await asyncio.to_thread(ai_service.outline_to_traditional, request.content)
        if result.get("error") and result.get("answer_zh_tw") is None:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"简转繁失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/traditional_to_simplified", summary="台湾繁体纲目转简体")
async def traditional_to_simplified(request: TraditionalToSimplifiedRequest):
    """
    工具箱「简繁互转」：将台湾繁体纲目转为简体。
    直接使用 zhconv 转换（不经过术语表）。
    使用 asyncio.to_thread 避免阻塞事件循环。
    """
    try:
        result = await asyncio.to_thread(ai_service.traditional_to_simplified, request.content)
        if result.get("error") and result.get("answer_zh_cn") is None:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"繁转简失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/convert_and_format", summary="简繁转换并格式化（返回 DOCX 或 PDF）")
async def convert_and_format(request: ConvertAndFormatRequest):
    """
    工具箱「简繁互转」：转换 + 格式化 + 返回 DOCX 或 PDF。
    流程：转换 → 复制中文模板 → 写入内容 → 刷格式 → 返回 DOCX/PDF bytes。
    若格式化失败，仍返回转换文本，docx_bytes/pdf_bytes 为 None。
    使用 asyncio.to_thread 避免阻塞事件循环。
    """
    try:
        result = await asyncio.to_thread(
            ai_service.convert_and_format_outline,
            request.direction,
            request.content,
            request.output_format,
        )
        
        if result.get("error") and not result.get("result"):
            # 转换失败
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        response_data = {
            "result": result.get("result"),
            "error": result.get("error"),  # 可能是格式化失败但转换成功
        }
        
        import base64
        
        # 根据输出格式返回对应的文件
        if request.output_format == "pdf":
            if result.get("pdf_bytes"):
                response_data["pdf_base64"] = base64.b64encode(result["pdf_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.pdf")
                logger.info(f"返回PDF: filename={response_data['filename']}, base64长度={len(response_data['pdf_base64'])}")
            elif result.get("docx_bytes"):
                # PDF 转换失败，返回 DOCX
                response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.docx").replace(".pdf", ".docx")
                logger.warning(f"PDF转换失败，返回DOCX: filename={response_data['filename']}")
            else:
                logger.warning(f"未返回PDF: result.error={result.get('error')}")
        else:
            # DOCX 格式
            if result.get("docx_bytes"):
                response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.docx")
                logger.info(f"返回DOCX: filename={response_data['filename']}, base64长度={len(response_data['docx_base64'])}")
            else:
                logger.warning(f"未返回DOCX: result.error={result.get('error')}, docx_bytes存在={result.get('docx_bytes') is not None}")
        
        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"转换并格式化失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/outline_translate", summary="工具箱 - 纲目翻译（中翻英 / 英翻中）")
async def outline_translate(request: OutlineTranslateRequest):
    """
    工具箱「纲目翻译」：按 direction 选择中翻英或英翻中，使用 Gemini 与对应 instruction。
    中翻英与 AI 纲目流程一致（术语表 instruction + 可选标题）；英翻中使用英翻中 instruction。
    使用 asyncio.to_thread 避免阻塞事件循环。
    """
    try:
        if request.direction == "zh2en":
            out = await asyncio.to_thread(
                ai_service.translate_outline,
                request.content,
                request.outline_topic,
                False,
            )
            return {
                "result": out.get("answer_en"),
                "title_en": out.get("title_en"),
                "error": out.get("error"),
            }
        else:
            out = await asyncio.to_thread(ai_service.translate_outline_en2zh, request.content)
            return {
                "result": out.get("answer_zh"),
                "error": out.get("error"),
            }
    except Exception as e:
        logger.error(f"outline_translate 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/outline_translate_and_format", summary="工具箱 - 纲目翻译并格式化下载 DOCX 或 PDF")
async def outline_translate_and_format(request: OutlineTranslateRequest):
    """
    工具箱「纲目翻译」：翻译 + 格式化 + 返回 DOCX 或 PDF。
    流程：翻译 → 复制模板 → 写入内容 → 刷格式 → 返回 DOCX/PDF bytes。
    若格式化失败，仍返回翻译文本，docx_bytes/pdf_bytes 为 None。
    使用 asyncio.to_thread 避免阻塞事件循环。
    """
    try:
        result = await asyncio.to_thread(
            ai_service.translate_and_format_outline,
            request.direction,
            request.content,
            request.outline_topic,
            request.output_format,
        )
        
        if result.get("error") and not result.get("result"):
            # 翻译失败
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        response_data = {
            "result": result.get("result"),
            "error": result.get("error"),  # 可能是格式化失败但翻译成功
        }
        
        import base64
        
        # 根据输出格式返回对应的文件
        if request.output_format == "pdf":
            if result.get("pdf_bytes"):
                response_data["pdf_base64"] = base64.b64encode(result["pdf_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.pdf")
                logger.info(f"返回PDF: filename={response_data['filename']}, base64长度={len(response_data['pdf_base64'])}")
            elif result.get("docx_bytes"):
                # PDF 转换失败，返回 DOCX
                response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.docx").replace(".pdf", ".docx")
                logger.warning(f"PDF转换失败，返回DOCX: filename={response_data['filename']}")
            else:
                logger.warning(f"未返回PDF: result.error={result.get('error')}")
        else:
            # DOCX 格式
            if result.get("docx_bytes"):
                response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.docx")
                logger.info(f"返回DOCX: filename={response_data['filename']}, base64长度={len(response_data['docx_base64'])}")
            else:
                logger.warning(f"未返回DOCX: result.error={result.get('error')}, docx_bytes存在={result.get('docx_bytes') is not None}")
        
        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"outline_translate_and_format 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/format_outline_only", summary="工具箱 - 仅格式化已翻译的纲目（不调用翻译 API）")
async def format_outline_only(request: FormatOutlineRequest):
    """
    工具箱「纲目翻译」：仅格式化已翻译的文本，不调用翻译 API。
    用于优化：用户已翻译完成，只需格式化并下载时使用。
    流程：复制模板 → 写入已翻译内容 → 刷格式 → 返回 DOCX/PDF bytes。
    使用 asyncio.to_thread 避免阻塞事件循环（含 LibreOffice 转 PDF）。
    """
    try:
        result = await asyncio.to_thread(
            ai_service.format_outline_only,
            request.direction,
            request.translated_text,
            request.output_format,
        )
        
        if result.get("error") and not (result.get("docx_bytes") or result.get("pdf_bytes")):
            # 格式化失败且没有返回文件
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        response_data = {
            "error": result.get("error"),  # 可能是 PDF 转换失败但 DOCX 成功
        }
        
        import base64
        
        # 根据输出格式返回对应的文件
        if request.output_format == "pdf":
            if result.get("pdf_bytes"):
                response_data["pdf_base64"] = base64.b64encode(result["pdf_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.pdf")
                logger.info(f"返回PDF: filename={response_data['filename']}, base64长度={len(response_data['pdf_base64'])}")
            elif result.get("docx_bytes"):
                # PDF 转换失败，返回 DOCX
                response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.docx").replace(".pdf", ".docx")
                logger.warning(f"PDF转换失败，返回DOCX: filename={response_data['filename']}")
            else:
                logger.warning(f"未返回PDF: result.error={result.get('error')}")
        else:
            # DOCX 格式
            if result.get("docx_bytes"):
                response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.docx")
                logger.info(f"返回DOCX: filename={response_data['filename']}, base64长度={len(response_data['docx_base64'])}")
            else:
                logger.warning(f"未返回DOCX: result.error={result.get('error')}, docx_bytes存在={result.get('docx_bytes') is not None}")
        
        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"format_outline_only 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/info_retrieval", summary="信息检索：多关键词/排除词导出 DOCX（单文件 40MB，超出则多个 DOCX 分别下载）")
async def info_retrieval_export(request: InfoRetrievalRequest):
    """
    多关键词 AND、排除关键词 OR。单文件上限 40MB，超出则拆成多个 DOCX（-1、-2…）分别下载。
    """
    try:
        logger.info("info_retrieval 请求: keyword=%r, exclude_keywords=%r",
                    request.keyword, request.exclude_keywords)
        docx_bytes, filename, log_message = await asyncio.to_thread(
            ai_service.info_retrieval_export,
            request.keyword,
            request.exclude_keywords or "",
        )
        if docx_bytes is None:
            # 中文说明放在 body，避免 HTTP 头 latin-1 编码错误
            body = json.dumps({"no_results": True, "message": log_message}, ensure_ascii=False).encode("utf-8")
            return Response(
                content=body,
                status_code=200,
                media_type="application/json; charset=utf-8",
                headers={"X-No-Results": "true"},
            )
        if isinstance(docx_bytes, list):
            # 多文件：返回 JSON，前端逐个下载 DOCX
            payload = {
                "files": [
                    {"filename": fname, "content": base64.b64encode(content).decode("ascii")}
                    for content, fname in docx_bytes
                ],
                "log_message": log_message,
            }
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            log_b64 = base64.b64encode(log_message.encode("utf-8")).decode("ascii")
            return Response(
                content=body,
                status_code=200,
                media_type="application/json; charset=utf-8",
                headers={"X-Multiple-Files": "true", "X-Retrieval-Log": log_b64},
            )
        encoded_filename = quote(filename)
        log_b64 = base64.b64encode(log_message.encode("utf-8")).decode("ascii")
        headers = {
            "Content-Disposition": f'attachment; filename*=UTF-8\'\'{encoded_filename}',
            "Content-Length": str(len(docx_bytes)),
            "X-Retrieval-Log": log_b64,
        }
        return StreamingResponse(
            iter([docx_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )
    except Exception as e:
        logger.error("信息检索导出失败: %s", e, exc_info=True)
        # 中文说明放在 body，避免 HTTP 头 latin-1 编码错误
        msg = f"导出失败：{str(e)}"
        body = json.dumps({"no_results": True, "message": msg}, ensure_ascii=False).encode("utf-8")
        return Response(
            content=body,
            status_code=200,
            media_type="application/json; charset=utf-8",
            headers={"X-No-Results": "true"},
        )


@router.post("/ai_search", response_model=SearchResponse, summary="AI智能搜索（一步完成）")
async def ai_search(request: SearchRequest):
    """
    AI智能问答接口

    根据用户问题，搜索相关经文，并用AI生成答案。

    **工作流程：**
    1. 检查缓存（命中则直接返回）
    2. 在Elasticsearch中检索相关经文
    3. 调用Claude API生成答案
    4. 返回答案和引用来源

    **请求示例：**
    ```json
    {
        "question": "什么是信心？",
        "max_results": 10,
        "depth": "general"
    }
    ```
    
    **depth参数说明：**
    - "general"（一般）：使用50条上下文，速度快，费用低
    - "deep"（深度）：使用200条上下文，内容更全面，费用更高

    **响应示例：**
    ```json
    {
        "answer": "根据希伯来书 11:1，信心是所望之事的实底...",
        "sources": [
            {
                "reference": "希伯来书 11:1",
                "content": "信就是所望之事的实底...",
                "score": 15.2,
                "type": "[经文]"
            }
        ],
        "cached": false,
        "tokens": {
            "input": 245,
            "output": 156,
            "total": 401,
            "cost": 0.003075
        },
        "search_time": 234,
        "ai_time": 2456,
        "total_time": 2690
    }
    ```

    **注意事项：**
    - 缓存有效期1小时
    - 单次查询费用约$0.003-0.01
    - 响应时间通常2-5秒（缓存命中<1秒）
    """
    try:
        logger.info(f"收到AI搜索请求: {request.question[:50]}...")

        # 调用服务层（to_thread 避免阻塞事件循环，支持多用户并发）
        metadata = _extract_metadata(request)
        result = await asyncio.to_thread(
            ai_service.search,
            request.question,
            request.max_results,
            request.depth,
            metadata,
        )

        # 检查是否有错误
        if result.get("error"):
            logger.warning(f"搜索返回错误: {result['answer']}")
        else:
            logger.info(f"搜索完成: {len(result.get('sources', []))}条来源, "
                       f"缓存={'命中' if result.get('cached') else '未命中'}")

        return result

    except Exception as e:
        logger.error(f"AI搜索失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"搜索失败: {str(e)}"
        )


@router.get("/ai_search/health", summary="健康检查")
async def health_check():
    """
    健康检查接口

    检查AI搜索服务及其依赖（ES、Redis、Claude）是否正常。

    **响应示例：**
    ```json
    {
        "status": "healthy",
        "services": {
            "elasticsearch": true,
            "redis": true,
            "claude": true,
            "overall": true
        }
    }
    ```
    """
    try:
        health_status = ai_service.health_check()

        return {
            "status": "healthy" if health_status["overall"] else "degraded",
            "services": health_status
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# ========== 监控统计 API ==========

@router.get("/ai_search/stats", summary="获取统计数据")
async def get_stats(days: int = Query(7, ge=1, le=30, description="统计包含的最近天数")):
    """
    获取 AI 搜索统计数据。

    - **days**：可选，1-30，默认 7。返回最近 N 天的每日统计。
    - 返回：总查询数、缓存命中率、平均响应时间(ms)、总费用、每日明细。
    """
    try:
        monitoring = get_monitoring()
        data = monitoring.get_stats(days=days)
        data["index_weights"] = get_index_weights_for_display()
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"获取统计失败: {e}", exc_info=True)
        return {"status": "error", "data": None, "message": str(e)}


@router.get("/ai_search/stats/errors", summary="获取最近错误记录")
async def get_recent_errors(limit: int = Query(20, ge=1, le=200, description="最多返回条数")):
    """
    获取最近的 AI 搜索错误记录。

    - **limit**：可选，1-200，默认 20。
    """
    try:
        monitoring = get_monitoring()
        data = monitoring.get_recent_errors(limit=limit)
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"获取错误记录失败: {e}", exc_info=True)
        return {"status": "error", "data": None, "message": str(e)}


@router.post("/ai_search/stats/reset", summary="重置统计数据")
async def reset_stats():
    """
    重置所有监控统计（全局统计、每日统计、错误列表）。

    谨慎调用，不可恢复。
    """
    try:
        monitoring = get_monitoring()
        monitoring.reset_stats()
        return {"status": "success", "data": {"message": "统计已重置"}}
    except Exception as e:
        logger.error(f"重置统计失败: {e}", exc_info=True)
        return {"status": "error", "data": None, "message": str(e)}


@router.get("/ai_search/rough_outline_config", summary="毛胚纲目 - 各类型对应的 AI 数量")
async def rough_outline_config():
    """返回每种纲目类型下会调用几次 AI（即需请求几次 API）。"""
    try:
        config = ai_service.get_rough_outline_ai_counts()
        return config
    except Exception as e:
        logger.error(f"rough_outline_config 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/rough_outline", summary="工具箱 - 毛胚纲目生成（单次一篇）")
async def rough_outline(request: RoughOutlineRequest):
    """
    工具箱「毛胚纲目」：每次只调用一个 AI 生成一篇纲目。
    传入 outline_type、content、ai_index（该类型下第几个 AI，从 0 起）。
    前端按类型 × ai_index 循环调用本接口，实现「每个纲目单独调用一次 API」。
    """
    try:
        result = await asyncio.to_thread(
            ai_service.generate_rough_outline,
            request.outline_type,
            request.content,
            request.ai_index,
        )
        # 即使该路 AI 未实现或失败（results 为空、带 error），也返回 200，由前端展示 error 文案，避免整次请求被当作 HTTP 失败
        return {
            "results": result.get("results", []),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"rough_outline 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/rough_outline_format_and_download", summary="工具箱 - 毛胚纲目刷格式并下载（五类均可）")
async def rough_outline_format_and_download(request: RoughOutlineFormatRequest):
    """
    毛胚纲目：将选定类型的一篇或多篇合并为一个 DOCX，使用中文模板与中文刷格式，返回 DOCX 供下载。
    """
    try:
        result = await asyncio.to_thread(
            ai_service.format_rough_outline_docx,
            request.outline_type,
            request.contents,
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


# ---------- 节期纲目 ----------
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


@router.post("/ai_search/feast_outline/original", summary="节期纲目 - 纲目的原文：刷格式并下载")
async def feast_outline_original(request: FeastOutlineOriginalRequest):
    """用户粘贴无格式纲目，刷格式并下载 DOCX。"""
    try:
        result = await asyncio.to_thread(
            ai_service.format_feast_outline_docx,
            [request.content.strip()],
        )
        return _feast_outline_docx_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_original 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/feast_outline/with_scripture", summary="节期纲目 - 带经文的纲目：经文汇集后刷格式并下载")
async def feast_outline_with_scripture(request: FeastOutlineWithScriptureRequest):
    """用经文汇集处理纲目，再刷格式并下载 DOCX。"""
    try:
        with_scripture_text = await asyncio.to_thread(
            ai_service.feast_outline_collect_scripture,
            request.content.strip(),
        )
        result = await asyncio.to_thread(
            ai_service.format_feast_outline_docx,
            [with_scripture_text],
        )
        return _feast_outline_docx_response(result, "节期纲目_带经文.docx")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_with_scripture 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/feast_outline/morning_revival", summary="节期纲目 - 晨兴信息选读的纲目：生成后刷格式并下载")
async def feast_outline_morning_revival(request: FeastOutlineMorningRevivalRequest):
    """用 Claude 根据晨兴内容生成纲目，再刷格式并下载 DOCX。"""
    try:
        gen = await asyncio.to_thread(
            ai_service.feast_outline_morning_revival,
            request.content.strip(),
        )
        if gen.get("error"):
            raise HTTPException(status_code=400, detail=gen.get("error"))
        outline = (gen.get("outline") or "").strip()
        if not outline:
            raise HTTPException(status_code=400, detail="AI 未生成纲目内容")
        result = await asyncio.to_thread(ai_service.format_feast_outline_docx, [outline])
        return _feast_outline_docx_response(result, "节期纲目_晨兴信息选读.docx")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_morning_revival 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/feast_outline/transcript", summary="节期纲目 - 听抄稿的纲目：原纲目+听抄稿重点后刷格式并下载")
async def feast_outline_transcript(request: FeastOutlineTranscriptRequest):
    """用 Claude 在原纲目基础上加入听抄稿重点，再刷格式并下载 DOCX。"""
    try:
        gen = await asyncio.to_thread(
            ai_service.feast_outline_transcript,
            request.original_outline.strip(),
            request.transcript.strip(),
        )
        if gen.get("error"):
            raise HTTPException(status_code=400, detail=gen.get("error"))
        outline = (gen.get("outline") or "").strip()
        if not outline:
            raise HTTPException(status_code=400, detail="AI 未生成纲目内容")
        result = await asyncio.to_thread(ai_service.format_feast_outline_docx, [outline])
        return _feast_outline_docx_response(result, "节期纲目_听抄稿.docx")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_transcript 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/feast_outline/composite", summary="节期纲目 - 复合的纲目：晨兴融入听抄稿纲目后刷格式并下载")
async def feast_outline_composite(request: FeastOutlineCompositeRequest):
    """用 Claude 将晨兴纲目融入听抄稿纲目，再刷格式并下载 DOCX。"""
    try:
        gen = await asyncio.to_thread(
            ai_service.feast_outline_composite,
            request.transcript_outline.strip(),
            request.morning_revival_outline.strip(),
        )
        if gen.get("error"):
            raise HTTPException(status_code=400, detail=gen.get("error"))
        outline = (gen.get("outline") or "").strip()
        if not outline:
            raise HTTPException(status_code=400, detail="AI 未生成纲目内容")
        result = await asyncio.to_thread(ai_service.format_feast_outline_docx, [outline])
        return _feast_outline_docx_response(result, "节期纲目_复合.docx")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_composite 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/cache/clear", summary="清理 AI 搜索缓存")
async def clear_cache():
    """
    清空 AI 搜索的 Redis 缓存（所有 ai_search:* 键）。

    清理后，相同问题将重新调用 Claude 生成答案。
    """
    try:
        result = ai_service.clear_cache()
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"清理缓存失败: {e}", exc_info=True)
        return {"status": "error", "data": None, "message": str(e)}
