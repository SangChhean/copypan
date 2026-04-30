# -*- coding: utf-8 -*-
"""QA 路由：输入校验、request_id 处理、健康检查。"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from back_qa.qa.rate_limit import check_rate_limit, check_prompt_injection
from back_qa.qa.auth_router import _require_user

router = APIRouter()
_bearer = HTTPBearer()


# ---------- 请求 / 响应模型 ----------


class HistoryTurn(BaseModel):
    question: str
    answer: str


class DebugParams(BaseModel):
    bm25_top_k: int = 30
    dense_top_k: int = 30
    expansion_top_n: int = 5
    rerank_top_n: int = 20


class QueryRequest(BaseModel):
    question: str
    skip_cache: bool = False
    debug: bool = False
    params: DebugParams = DebugParams()
    history: list[HistoryTurn] = Field(default_factory=list)

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
    debug: dict[str, Any] | None = None


class FeedbackRequest(BaseModel):
    request_id: str
    question: str
    answer: str
    rating: int  # 1 或 -1


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
    from back_qa.qa.dependencies import get_redis_client

    _require_user(request)
    if not check_rate_limit(request, get_redis_client()):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    if not check_prompt_injection(req.question):
        raise HTTPException(status_code=400, detail="输入包含不支持的内容")

    request_id = _resolve_request_id(request)
    history_payload = [{"question": h.question, "answer": h.answer} for h in req.history]
    result = await run_pipeline(
        question=req.question,
        skip_cache=req.skip_cache,
        request_id=request_id,
        app=request.app,
        debug=req.debug,
        debug_params=req.params.model_dump(),
        history=history_payload,
    )
    return QueryResponse(**result)


@router.post("/stream")
async def stream_answer(req: QueryRequest, request: Request):
    """流式问答（SSE）。Steps 0–3 与 /query 一致；非缓存时 Step4 逐 token 推送。缓存命中仅返回一条 done。"""
    from back_qa.qa.qa_service import stream_query
    from back_qa.qa.dependencies import get_redis_client

    _require_user(request)
    if not check_rate_limit(request, get_redis_client()):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    if not check_prompt_injection(req.question):
        raise HTTPException(status_code=400, detail="输入包含不支持的内容")

    request_id = _resolve_request_id(request)
    history_payload = [{"question": h.question, "answer": h.answer} for h in req.history]

    async def event_generator():
        try:
            async for chunk in stream_query(
                question=req.question,
                skip_cache=req.skip_cache,
                request_id=request_id,
                app=request.app,
                history=history_payload,
                debug=req.debug,
                debug_params=req.params.model_dump(),
            ):
                yield {"data": json.dumps(chunk, ensure_ascii=False)}
        except Exception as e:
            yield {"data": json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest, request: Request):
    """提交答案质量反馈（需登录）。"""
    username = _require_user(request)
    if req.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating 只能是 1 或 -1")

    from back_qa.qa.auth import insert_feedback

    insert_feedback(
        request_id=(req.request_id or "").strip(),
        username=username,
        question=(req.question or "").strip(),
        answer=(req.answer or "").strip(),
        rating=req.rating,
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# 管理接口（需 X-Admin-Token 验证）
# ---------------------------------------------------------------------------


def _check_admin(request: Request):
    """简单 token 验证，从环境变量 QA_ADMIN_TOKEN 读取。未配置时拒绝所有请求。"""
    token = os.environ.get("QA_ADMIN_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="管理接口未配置 QA_ADMIN_TOKEN")
    provided = request.headers.get("X-Admin-Token", "")
    if provided != token:
        raise HTTPException(status_code=401, detail="无效的管理员 Token")


def _require_admin(request: Request):
    _check_admin(request)


@router.post("/cache/clear")
async def cache_clear(request: Request):
    """清理所有 qa:cache:* 缓存，返回删除条数。"""
    _check_admin(request)
    from back_qa.qa.dependencies import get_redis_client

    r = get_redis_client()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis 不可用")
    prefix = os.environ.get("QA_REDIS_PREFIX", "qa:cache:")
    keys = r.keys(f"{prefix}*")
    deleted = 0
    if keys:
        deleted = r.delete(*keys)
    return {"deleted": deleted, "prefix": prefix}


@router.post("/stats/clear")
async def stats_clear(request: Request):
    """清空监控统计数据（管理员）"""
    _require_admin(request)
    r = getattr(request.app.state, "redis_client", None)
    if r is None:
        raise HTTPException(status_code=503, detail="Redis 不可用")
    from back_qa.qa.qa_service import _MONITOR_KEY
    deleted = r.delete(_MONITOR_KEY)
    return {"deleted": bool(deleted), "key": _MONITOR_KEY}


@router.get("/stats")
async def stats(request: Request):
    """查看用量与监控统计。"""
    _check_admin(request)
    from back_qa.qa.dependencies import get_redis_client
    from back_qa.qa.qa_service import _MONITOR_KEY

    r = get_redis_client()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis 不可用")

    raw_records = r.lrange(_MONITOR_KEY, 0, -1)
    records = []
    for raw in raw_records:
        try:
            records.append(json.loads(raw))
        except Exception:
            pass

    total = len(records)
    cache_hits = sum(1 for rec in records if rec.get("cache_hit"))
    found_non_cache = [rec for rec in records if not rec.get("cache_hit")]
    found_count = sum(1 for rec in found_non_cache if rec.get("found"))
    step_fail = [rec for rec in found_non_cache if not rec.get("found")]

    total_cost = sum(rec.get("total_cost_usd", 0) for rec in found_non_cache)
    avg_elapsed = (
        sum(rec.get("total_elapsed_ms", 0) for rec in found_non_cache) / len(found_non_cache)
        if found_non_cache
        else 0
    )

    return {
        "total_requests": total,
        "cache_hit_rate": round(cache_hits / total, 4) if total else 0,
        "found_rate_new": round(found_count / len(found_non_cache), 4) if found_non_cache else 0,
        "total_cost_usd": round(total_cost, 4),
        "avg_elapsed_ms": round(avg_elapsed),
        "step_fail_records": step_fail[-20:],  # 最近 20 条未找到记录
    }


@router.get("/feedback/stats")
async def feedback_stats(request: Request):
    _require_admin(request)
    from back_qa.qa.auth import get_feedback_stats

    return get_feedback_stats()


@router.post("/asr")
async def asr_transcribe(
    request: Request,
    file: UploadFile = File(...),
    _: HTTPAuthorizationCredentials = Depends(_bearer),
):
    _require_user(request)

    allowed_prefixes = (
        "audio/webm",
        "audio/wav",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/x-m4a",
        "audio/m4a",
    )
    content_type = (file.content_type or "").lower().strip()
    if not any(content_type.startswith(p) for p in allowed_prefixes):
        raise HTTPException(status_code=400, detail="不支持的音频格式")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过 10MB")

    from back_qa.qa import asr_service

    try:
        text = await asr_service.transcribe(content, file.filename or "audio.webm")
        return {"text": text}
    except Exception:
        raise HTTPException(status_code=500, detail="语音识别失败，请重试")
