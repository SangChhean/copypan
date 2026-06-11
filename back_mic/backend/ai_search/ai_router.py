"""
AI搜索API路由
提供 /api/ai_search 等接口。除 GET /api/ai_search/health 外需登录（Authorization Bearer 或 session cookie）；
监控统计与缓存清理需管理员（role t0）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal, Optional
import asyncio
import base64
import logging

from .ai_service import ai_service, get_index_weights_for_display
from .monitoring import get_monitoring
from features.roundtable.roundtable_db import get_roundtable_cost_stats
from user.token import require_admin, test_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
_auth = APIRouter(dependencies=[Depends(test_token)])


class TranslateOutlineRequest(BaseModel):
    """英文纲目翻译请求：传入中文纲目全文和标题"""
    chinese_outline: str = Field(..., min_length=1, max_length=100_000, description="中文纲目全文")
    outline_topic: Optional[str] = Field(None, max_length=200, description="纲目主题（用于翻译标题）")


class FormatOutlineRequest(BaseModel):
    """工具箱 - 仅格式化已翻译/转换的纲目（不调用翻译/转换 API）"""
    direction: Literal["zh2en", "en2zh", "zh_cn2tw", "zh_tw2cn"] = Field(..., description="zh2en=英文纲目, en2zh/zh_cn2tw/zh_tw2cn=中文纲目")
    translated_text: str = Field(..., min_length=1, max_length=100_000, description="已翻译/转换的纲目全文")
    output_format: Literal["docx", "pdf"] = Field("docx", description="输出格式：docx 或 pdf，默认 docx")
    is_outline: bool = Field(True, description="True=纲目格式刷，False=通用平铺格式刷（末尾无标点→居中加粗，其余→paragraph 样式）")


@_auth.post("/ai_search/translate_outline", summary="将中文纲目翻译为英文纲目")
async def translate_outline(request: TranslateOutlineRequest):
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


@_auth.post("/ai_search/format_outline_only", summary="工具箱 - 仅格式化已翻译的纲目（不调用翻译 API）")
async def format_outline_only(request: FormatOutlineRequest):
    try:
        result = await asyncio.to_thread(
            ai_service.format_outline_only,
            request.direction,
            request.translated_text,
            request.output_format,
            request.is_outline,
        )

        if result.get("error") and not (result.get("docx_bytes") or result.get("pdf_bytes")):
            raise HTTPException(status_code=400, detail=result.get("error"))

        response_data = {
            "error": result.get("error"),
        }

        if request.output_format == "pdf":
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
        logger.error(f"format_outline_only 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai_search/health", summary="健康检查")
async def health_check():
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


@_auth.get(
    "/ai_search/stats/detail",
    summary="获取详细统计数据（供子页面使用）",
    dependencies=[Depends(require_admin)],
)
async def get_stats_detail(days: int = Query(7, ge=1, le=30, description="统计包含的最近天数")):
    try:
        monitoring = get_monitoring()
        stats = monitoring.get_stats(days=days)
        roundtable_stats = {"total_cost": 0.0, "total_count": 0, "daily": {}, "scene_counts": {"scene_one": {"count": 0, "cost": 0.0}, "scene_two": {"count": 0, "cost": 0.0}}}
        try:
            roundtable_stats = get_roundtable_cost_stats(days)
        except Exception as rt_e:
            logger.warning("获取圆桌统计失败: %s", rt_e)

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

        roundtable_daily = []
        for date_str, cost in roundtable_stats.get("daily", {}).items():
            roundtable_daily.append({"date": date_str, "count": 0, "cost": cost})
        roundtable = {
            "total_count": roundtable_stats.get("total_count", 0),
            "total_cost": roundtable_stats.get("total_cost", 0.0),
            "scene_counts": roundtable_stats.get("scene_counts", {
                "scene_one": {"count": 0, "cost": 0.0},
                "scene_two": {"count": 0, "cost": 0.0},
            }),
            "daily": sorted(roundtable_daily, key=lambda x: x["date"], reverse=True),
        }

        rag_cost = stats.get("total_cost", 0.0)
        toolbox_cost = stats.get("tool_stats", {}).get("total_cost", 0.0)
        roundtable_cost = roundtable_stats.get("total_cost", 0.0)
        total_cost = rag_cost + toolbox_cost + roundtable_cost

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
    logger.info("reset_stats 被调用")
    try:
        monitoring = get_monitoring()
        monitoring.reset_stats()
        return {"status": "success", "data": {"message": "统计已重置"}}
    except Exception as e:
        logger.error(f"重置统计失败: {e}", exc_info=True)
        return {"status": "error", "data": None, "message": str(e)}


router.include_router(_auth)
