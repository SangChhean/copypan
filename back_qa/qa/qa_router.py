# -*- coding: utf-8 -*-
"""QA 路由：输入校验、request_id 处理、健康检查。"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

router = APIRouter()


# ---------- 请求 / 响应模型 ----------

class QueryRequest(BaseModel):
    question: str
    skip_cache: bool = False

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question 不能为空")
        if len(v) > 500:
            raise ValueError("question 不能超过 500 字")
        return v


class QueryResponse(BaseModel):
    request_id: str
    answer: str
    sources: list[str]
    concepts: list[str]
    found: bool
    cache_hit: bool
    total_elapsed_ms: int
    total_cost_usd: float


# ---------- 工具函数 ----------

def _resolve_request_id(request: Request) -> str:
    """从 X-Request-ID 头读取，合法则复用，否则生成新 UUID。"""
    raw = request.headers.get("X-Request-ID", "")
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError):
        return str(uuid.uuid4())


# ---------- 接口 ----------

@router.get("/liveness")
async def liveness():
    """轻量存活探针，仅检查进程。"""
    return {"status": "ok"}


@router.get("/readiness")
async def readiness(request: Request):
    """就绪探针：检查各依赖项状态与数据基线。"""
    from back_qa.qa.dependencies import get_es_client, get_redis_client
    from back_shared.version_manifest import PROMPT_VERSION, MODEL_PROFILE, FIREWALL_RULES_VERSION

    # Neo4j
    neo4j = request.app.state.neo4j_client
    neo4j_status = "connected" if neo4j._available else "unavailable"

    # ES
    try:
        es = get_es_client()
        es.cluster.health(request_timeout=3)
        es_status = "connected"
    except Exception:
        es_status = "unavailable"

    # Redis
    try:
        r = get_redis_client()
        redis_status = "connected" if r is not None else "unavailable"
    except Exception:
        redis_status = "unavailable"

    overall = "ok" if all(
        s == "connected" for s in [neo4j_status, es_status, redis_status]
    ) else "degraded"

    baseline = getattr(request.app.state, "data_baseline", {})
    updated_at = getattr(request.app.state, "baseline_updated_at", "")

    return {
        "status": overall,
        "neo4j": neo4j_status,
        "elasticsearch": es_status,
        "redis": redis_status,
        "data_baseline": {
            "concept_total": baseline.get("concept_total", -1),
            "concept_with_greek_terms": baseline.get("concept_with_greek_terms", -1),
            "baseline_updated_at": updated_at,
            "prompt_version": PROMPT_VERSION,
            "model_profile": MODEL_PROFILE,
            "firewall_rules_version": FIREWALL_RULES_VERSION,
        },
    }


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, request: Request):
    """提交问题，返回答案。流水线实现在 qa_service。"""
    from back_qa.qa.qa_service import run_pipeline

    request_id = _resolve_request_id(request)
    result = await run_pipeline(
        question=req.question,
        skip_cache=req.skip_cache,
        request_id=request_id,
        app=request.app,
    )
    return QueryResponse(**result)
