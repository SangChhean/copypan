# -*- coding: utf-8 -*-
"""问答路由：POST /api/qa/stream（SSE）与 POST /api/qa/ask（非流式）。

沿用阶段 1 鉴权依赖；live 模式且提示词仍为占位时返回 503。
SSE：X-Accel-Buffering: no；定期心跳。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import require_user
from pipeline import step01_entry
from pipeline.orchestrator import collect_ask, run_pipeline

logger = logging.getLogger("qa4.api.qa")

router = APIRouter(prefix="/api/qa", tags=["qa"])


class HistoryTurn(BaseModel):
    question: str = ""
    answer: str = ""


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: list[HistoryTurn] = Field(default_factory=list)


def _get_deps(request: Request):
    deps = getattr(request.app.state, "pipeline_deps", None)
    if deps is None:
        raise HTTPException(status_code=503, detail={"message": "流水线未初始化"})
    return deps


def _gate(request: Request, username: str, question: str) -> Any:
    deps = _get_deps(request)
    blocked = deps.live_blocked()
    if blocked:
        raise HTTPException(status_code=503, detail={"message": blocked})
    settings = request.app.state.settings
    refuse = step01_entry.entry_checks(
        request,
        auth=request.app.state.auth,
        store=request.app.state.redis_store,
        username=username,
        question=question,
        rate_limit=settings.rate_limit_per_minute,
    )
    if refuse:
        code, msg = refuse
        raise HTTPException(status_code=code, detail={"message": msg})
    return deps


def _sse_pack(obj: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")


@router.post("/ask")
async def ask(req: AskRequest, request: Request, username: str = Depends(require_user)):
    deps = _gate(request, username, req.question)
    rid = getattr(request.state, "request_id", None)
    history = [h.model_dump() for h in req.history]
    result = await collect_ask(deps, question=req.question, history=history, request_id=rid)
    return result


@router.post("/stream")
async def stream(req: AskRequest, request: Request, username: str = Depends(require_user)):
    deps = _gate(request, username, req.question)
    rid = getattr(request.state, "request_id", None)
    history = [h.model_dump() for h in req.history]
    heartbeat = float(deps.cfg.get("heartbeat_s", 10))

    async def gen():
        q: asyncio.Queue = asyncio.Queue()
        stop = asyncio.Event()

        async def produce():
            try:
                async for ev in run_pipeline(
                    deps, question=req.question, history=history, request_id=rid
                ):
                    await q.put(ev)
            except Exception as e:
                logger.exception("stream produce failed")
                await q.put({"event": "error", "message": type(e).__name__})
            finally:
                stop.set()
                await q.put(None)

        task = asyncio.create_task(produce())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=heartbeat)
                except asyncio.TimeoutError:
                    yield _sse_pack({"event": "heartbeat"})
                    continue
                if item is None:
                    break
                yield _sse_pack(item)
        finally:
            stop.set()
            if not task.done():
                task.cancel()
                try:
                    await task
                except Exception:
                    pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
