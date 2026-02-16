"""
AI搜索API路由
提供/api/ai_search接口（问答、健康检查、监控统计）
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
import logging

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
