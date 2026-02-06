"""
AI搜索API路由
提供/api/ai_search接口
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from .ai_service import ai_service

logger = logging.getLogger(__name__)

# 创建路由，前缀 /api 使接口为 /api/ai_search、/api/ai_search/health 等
router = APIRouter(prefix="/api")


class SearchRequest(BaseModel):
    """AI搜索请求模型"""
    question: str = Field(..., min_length=1, max_length=500, description="用户问题")
    max_results: Optional[int] = Field(30, ge=1, le=50, description="最多返回结果数")

    class Config:
        json_schema_extra = {
            "example": {
                "question": "圣经如何定义爱？",
                "max_results": 30
            }
        }


class SearchResponse(BaseModel):
    """AI搜索响应模型"""
    answer: str
    sources: list
    cached: bool
    tokens: Optional[dict] = None
    search_time: Optional[float] = None
    ai_time: Optional[float] = None
    total_time: Optional[float] = None


@router.post("/ai_search", response_model=SearchResponse, summary="AI智能搜索")
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
        "max_results": 10
    }
    ```

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
        result = ai_service.search(
            question=request.question,
            max_results=request.max_results
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


@router.get("/ai_search/stats", summary="获取统计信息")
async def get_stats():
    """
    获取统计信息（可选功能）

    返回缓存命中率、请求统计等信息。

    **注意：** 此功能需要额外实现统计逻辑，当前为占位接口。
    """
    return {
        "message": "统计功能开发中",
        "note": "可在此添加缓存命中率、请求量等统计信息"
    }
