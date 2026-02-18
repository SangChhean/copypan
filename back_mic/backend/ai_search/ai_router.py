"""
AI搜索API路由
提供/api/ai_search接口（问答、健康检查、监控统计）
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional
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


class OutlineTranslateRequest(BaseModel):
    """工具箱 - 纲目翻译：中翻英或英翻中"""
    direction: Literal["zh2en", "en2zh"] = Field(..., description="zh2en=中文→英文, en2zh=英文→中文")
    content: str = Field(..., min_length=1, max_length=100_000, description="待翻译的纲目全文")
    outline_topic: Optional[str] = Field(None, max_length=200, description="纲目主题（仅中翻英时用于翻译标题）")


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
        result = ai_service.search_only(
            question=request.question,
            depth=request.depth or "general",
            metadata=metadata
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
        result = ai_service.generate_only(
            question=request.question,
            search_id=request.search_id,
            max_results=request.max_results or 30,
            metadata=metadata
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
    """
    try:
        result = ai_service.translate_outline(request.chinese_outline, request.outline_topic)
        return result
    except Exception as e:
        logger.error(f"翻译纲目失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/outline_translate", summary="工具箱 - 纲目翻译（中翻英 / 英翻中）")
async def outline_translate(request: OutlineTranslateRequest):
    """
    工具箱「纲目翻译」：按 direction 选择中翻英或英翻中，使用 Gemini 与对应 instruction。
    中翻英与 AI 纲目流程一致（术语表 instruction + 可选标题）；英翻中使用英翻中 instruction。
    """
    try:
        if request.direction == "zh2en":
            # 工具箱 - 纲目翻译：不使用缓存，每次调用 API
            out = ai_service.translate_outline(request.content, request.outline_topic, use_cache=False)
            return {
                "result": out.get("answer_en"),
                "title_en": out.get("title_en"),
                "error": out.get("error"),
            }
        else:
            out = ai_service.translate_outline_en2zh(request.content)
            return {
                "result": out.get("answer_zh"),
                "error": out.get("error"),
            }
    except Exception as e:
        logger.error(f"outline_translate 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/outline_translate_and_format", summary="工具箱 - 纲目翻译并格式化下载 DOCX")
async def outline_translate_and_format(request: OutlineTranslateRequest):
    """
    工具箱「纲目翻译」：翻译 + 格式化 + 返回 DOCX。
    流程：翻译 → 复制模板 → 写入内容 → 刷格式 → 返回 DOCX bytes。
    若格式化失败，仍返回翻译文本，docx_bytes 为 None。
    """
    try:
        result = ai_service.translate_and_format_outline(
            direction=request.direction,
            content=request.content,
            outline_topic=request.outline_topic,
        )
        
        if result.get("error") and not result.get("result"):
            # 翻译失败
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        response_data = {
            "result": result.get("result"),
            "error": result.get("error"),  # 可能是格式化失败但翻译成功
        }
        
        # 如果有 DOCX bytes，返回 base64 编码
        if result.get("docx_bytes"):
            import base64
            response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
            response_data["filename"] = result.get("filename", "outline.docx")
        
        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"outline_translate_and_format 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai_search/info_retrieval", summary="信息检索：多关键词/排除词导出 DOCX（单文件 40MB，超出则多个 DOCX 分别下载）")
async def info_retrieval_export(request: InfoRetrievalRequest):
    """
    多关键词 AND、排除关键词 OR。单文件上限 40MB，超出则拆成多个 DOCX（-1、-2…）分别下载。
    """
    try:
        logger.info("info_retrieval 请求: keyword=%r, exclude_keywords=%r",
                    request.keyword, request.exclude_keywords)
        docx_bytes, filename, log_message = ai_service.info_retrieval_export(
            keyword=request.keyword,
            exclude_keywords=request.exclude_keywords or "",
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

        # 调用服务层
        metadata = _extract_metadata(request)
        result = ai_service.search(
            question=request.question,
            max_results=request.max_results,
            depth=request.depth,
            metadata=metadata
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
