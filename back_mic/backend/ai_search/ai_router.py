"""
AI搜索API路由
提供 /api/ai_search 等接口。除 GET /api/ai_search/health 外需登录（Authorization Bearer 或 session cookie）；
监控统计与缓存清理需管理员（role t0）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
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
from roundtable.roundtable_db import get_roundtable_cost_stats
from user.token import require_admin, test_token

logger = logging.getLogger(__name__)

# 前缀 /api；除 health 外均需登录（Bearer 或 session cookie），与 /api/search 等一致
router = APIRouter(prefix="/api")
_auth = APIRouter(dependencies=[Depends(test_token)])


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
    is_outline: bool = Field(True, description="True=纲目格式刷，False=通用平铺格式刷（末尾无标点→居中加粗，其余→paragraph 样式）")


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


class InfoRetrievalRequest(BaseModel):
    """信息检索请求：多关键词 AND、排除关键词 OR、DOCX 大小上限"""
    keyword: str = Field(..., min_length=1, max_length=500, description="搜索关键词，空格隔开，多词 AND")
    exclude_keywords: Optional[str] = Field(None, max_length=500, description="排除关键词，空格隔开，多词 OR")
    max_size_mb: Optional[int] = Field(100, description="单 DOCX 合并大小上限（MB），40 或 100")


@_auth.post("/ai_search/translate_outline", summary="将中文纲目翻译为英文纲目")
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


@_auth.post("/ai_search/outline_to_traditional", summary="简体纲目转台湾繁体")
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


@_auth.post("/ai_search/traditional_to_simplified", summary="台湾繁体纲目转简体")
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


@_auth.post("/ai_search/outline_translate", summary="工具箱 - 纲目翻译（中翻英 / 英翻中）")
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


@_auth.post("/ai_search/format_outline_only", summary="工具箱 - 仅格式化已翻译的纲目（不调用翻译 API）")
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
            request.is_outline,
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


@_auth.post("/ai_search/info_retrieval", summary="信息检索：多关键词/排除词导出 DOCX（单文件 40MB，超出则多个 DOCX 分别下载）")
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

@_auth.get(
    "/ai_search/stats/detail",
    summary="获取详细统计数据（供子页面使用）",
    dependencies=[Depends(require_admin)],
)
async def get_stats_detail(days: int = Query(7, ge=1, le=30, description="统计包含的最近天数")):
    """
    获取详细 AI 使用统计数据，供六个子页面使用。
    返回 rag、toolbox、roundtable、summary 四个顶层字段。
    """
    try:
        monitoring = get_monitoring()
        stats = monitoring.get_stats(days=days)
        roundtable_stats = {"total_cost": 0.0, "total_count": 0, "daily": {}, "scene_counts": {"scene_one": {"count": 0, "cost": 0.0}, "scene_two": {"count": 0, "cost": 0.0}}}
        try:
            roundtable_stats = get_roundtable_cost_stats(days)
        except Exception as rt_e:
            logger.warning("获取圆桌统计失败: %s", rt_e)

        # RAG 数据
        rag = {
            "total_queries": stats.get("total_queries", 0),
            "total_cost": stats.get("total_cost", 0.0),
            "cache_hit_rate": stats.get("cache_hit_rate", 0.0),
            "avg_response_time_ms": stats.get("avg_response_time_ms", 0.0),
            "nature_counts": stats.get("nature_counts", {}),
            "mode_counts": stats.get("mode_counts", {}),
            "depth_counts": stats.get("depth_counts", {}),
            "daily": stats.get("daily", []),
        }

        # 工具箱数据
        by_tool = stats.get("tool_stats", {}).get("by_tool", {})
        toolbox = {
            "translation": {
                "zh2en": by_tool.get("translation_zh2en", {"count": 0, "cost": 0.0}),
                "en2zh": by_tool.get("translation_en2zh", {"count": 0, "cost": 0.0}),
            },
            "rough_outline": {
                "claude": by_tool.get("rough_outline_claude", {"count": 0, "cost": 0.0}),
                "gemini": by_tool.get("rough_outline_gemini", {"count": 0, "cost": 0.0}),
                "deepseek": by_tool.get("rough_outline_deepseek", {"count": 0, "cost": 0.0}),
                "openai": by_tool.get("rough_outline_openai", {"count": 0, "cost": 0.0}),
                "perplexity": by_tool.get("rough_outline_perplexity", {"count": 0, "cost": 0.0}),
                "grok": by_tool.get("rough_outline_grok", {"count": 0, "cost": 0.0}),
            },
            "feast_outline": {
                "claude": by_tool.get("feast_outline_claude", {"count": 0, "cost": 0.0}),
            },
        }

        # 圆桌数据：将 daily dict 转为数组格式
        roundtable_daily = []
        for date_str, cost in roundtable_stats.get("daily", {}).items():
            roundtable_daily.append({"date": date_str, "count": 0, "cost": cost})
        # 补充 count：重新遍历或使用已有数据
        roundtable = {
            "total_count": roundtable_stats.get("total_count", 0),
            "total_cost": roundtable_stats.get("total_cost", 0.0),
            "scene_counts": roundtable_stats.get("scene_counts", {
                "scene_one": {"count": 0, "cost": 0.0},
                "scene_two": {"count": 0, "cost": 0.0},
            }),
            "daily": sorted(roundtable_daily, key=lambda x: x["date"], reverse=True),
        }

        # 费用总览
        rag_cost = stats.get("total_cost", 0.0)
        toolbox_cost = stats.get("tool_stats", {}).get("total_cost", 0.0)
        roundtable_cost = roundtable_stats.get("total_cost", 0.0)
        total_cost = rag_cost + toolbox_cost + roundtable_cost

        # 合并每日费用
        daily_map = {}
        for item in stats.get("daily", []):
            d = item.get("date", "")
            if d:
                daily_map[d] = daily_map.get(d, 0.0) + item.get("cost", 0.0)
        for date_str, cost in roundtable_stats.get("daily", {}).items():
            daily_map[date_str] = daily_map.get(date_str, 0.0) + cost

        summary_daily = [{"date": d, "cost": round(c, 4)} for d, c in sorted(daily_map.items(), reverse=True)]

        summary = {
            "total_cost": round(total_cost, 4),
            "rag_cost": round(rag_cost, 4),
            "toolbox_cost": round(toolbox_cost, 4),
            "roundtable_cost": round(roundtable_cost, 4),
            "daily": summary_daily,
        }

        return {
            "status": "success",
            "data": {
                "days": days,
                "rag": rag,
                "toolbox": toolbox,
                "roundtable": roundtable,
                "summary": summary,
            },
        }
    except Exception as e:
        logger.error(f"获取详细统计失败: {e}", exc_info=True)
        return {"status": "error", "data": None, "message": str(e)}


@_auth.get(
    "/ai_search/stats",
    summary="获取统计数据",
    dependencies=[Depends(require_admin)],
)
async def get_stats(days: int = Query(7, ge=1, le=30, description="统计包含的最近天数")):
    """
    获取 AI 搜索统计数据。

    - **days**：可选，1-30，默认 7。返回最近 N 天的每日统计。
    - 返回：总查询数、缓存命中率、平均响应时间(ms)、总费用、每日明细。
    """
    try:
        monitoring = get_monitoring()
        data = monitoring.get_stats(days=days)
        try:
            roundtable_stats = get_roundtable_cost_stats(days)
            data["total_cost"] += roundtable_stats["total_cost"]
            data["tool_stats"]["total_cost"] += roundtable_stats["total_cost"]
            data["tool_stats"]["by_tool"]["roundtable"] = {
                "count": roundtable_stats["total_count"],
                "cost": roundtable_stats["total_cost"],
            }
            for item in data["daily"]:
                item["cost"] += roundtable_stats["daily"].get(item["date"], 0)
        except Exception as rt_e:
            logger.warning("圆桌费用统计合并失败（已忽略）: %s", rt_e)
            data["tool_stats"]["by_tool"]["roundtable"] = {"count": 0, "cost": 0.0}
        data["index_weights"] = get_index_weights_for_display()
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"获取统计失败: {e}", exc_info=True)
        return {"status": "error", "data": None, "message": str(e)}


@_auth.get(
    "/ai_search/stats/errors",
    summary="获取最近错误记录",
    dependencies=[Depends(require_admin)],
)
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


@_auth.post(
    "/ai_search/stats/reset",
    summary="重置统计数据",
    dependencies=[Depends(require_admin)],
)
async def reset_stats():
    """
    重置所有监控统计（全局统计、每日统计、错误列表）。

    谨慎调用，不可恢复。
    """
    logger.info("reset_stats 被调用")
    try:
        monitoring = get_monitoring()
        monitoring.reset_stats()
        return {"status": "success", "data": {"message": "统计已重置"}}
    except Exception as e:
        logger.error(f"重置统计失败: {e}", exc_info=True)
        return {"status": "error", "data": None, "message": str(e)}


@_auth.get("/ai_search/rough_outline_config", summary="毛胚纲目 - 各类型对应的 AI 数量")
async def rough_outline_config():
    """返回每种纲目类型下会调用几次 AI（即需请求几次 API）。"""
    try:
        config = ai_service.get_rough_outline_ai_counts()
        return config
    except Exception as e:
        logger.error(f"rough_outline_config 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/rough_outline", summary="工具箱 - 毛胚纲目生成（单次一篇）")
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


@_auth.post("/ai_search/rough_outline_format_and_download", summary="工具箱 - 毛胚纲目刷格式并下载（五类均可）")
async def rough_outline_format_and_download(request: RoughOutlineFormatRequest):
    """
    毛胚纲目：将选定类型的一篇或多篇合并为一个 DOCX，使用中文模板与中文刷格式，返回 DOCX 供下载。
    """
    try:
        result = await asyncio.to_thread(
            ai_service.format_rough_outline_docx,
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


@_auth.post("/ai_search/feast_outline/scripture_text", summary="节期纲目 - 仅经文汇集，返回带经文文本（供多选生成用）")
async def feast_outline_scripture_text(request: FeastOutlineWithScriptureRequest):
    """经文汇集处理纲目，返回纯文本不生成 DOCX。"""
    try:
        content = await asyncio.to_thread(
            ai_service.feast_outline_collect_scripture,
            request.content.strip(),
        )
        return {"content": content or ""}
    except Exception as e:
        logger.error(f"feast_outline_scripture_text 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/feast_outline/generate/morning_revival", summary="节期纲目 - 仅生成晨兴纲目文本（供多选生成用）")
async def feast_outline_generate_morning_revival(request: FeastOutlineMorningRevivalRequest):
    """Claude 根据晨兴内容生成纲目，仅返回纲目文本。"""
    logger.info("feast_outline/generate/morning_revival 收到请求")
    try:
        gen = await asyncio.to_thread(
            ai_service.feast_outline_morning_revival,
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
    """Claude 在原纲目基础上加听抄稿重点，仅返回纲目文本；若提供序言/添言原文则一并生成并返回 preface_outline/addendum_outline。"""
    logger.info("feast_outline/generate/transcript 收到请求")
    try:
        gen = await asyncio.to_thread(
            ai_service.feast_outline_transcript,
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
        ol = out.get("outline") or ""
        logger.info(
            "feast_outline/generate/transcript 完成，将返回客户端 outline_len=%s",
            len(ol),
        )
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_generate_transcript 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/feast_outline/generate/composite", summary="节期纲目 - 仅生成复合纲目文本（供多选生成用）")
async def feast_outline_generate_composite(request: FeastOutlineCompositeRequest):
    """Claude 将晨兴纲目融入听抄稿纲目，仅返回纲目文本。"""
    try:
        gen = await asyncio.to_thread(
            ai_service.feast_outline_composite,
            request.transcript_outline.strip(),
            request.morning_revival_outline.strip(),
        )
        if gen.get("error"):
            raise HTTPException(status_code=400, detail=gen.get("error"))
        outline = (gen.get("outline") or "").strip()
        logger.info(
            "feast_outline/generate/composite 完成，将返回客户端 outline_len=%s",
            len(outline),
        )
        return {"outline": outline}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"feast_outline_generate_composite 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@_auth.post("/ai_search/feast_outline/format_download", summary="节期纲目 - 刷格式并下载（传入正文列表）")
async def feast_outline_format_download(request: FeastOutlineFormatDownloadRequest):
    """将传入的纲目正文合并、刷格式并返回 DOCX 供下载。"""
    try:
        result = await asyncio.to_thread(
            ai_service.format_feast_outline_docx,
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
