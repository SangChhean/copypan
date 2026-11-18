# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from api.deps import get_auth, get_store, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class InviteCreate(BaseModel):
    code: str
    note: str = ""
    max_uses: int = 1
    expires_at: Optional[str] = None

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("邀请码不能为空")
        return v


class SetLimitRequest(BaseModel):
    daily_limit: int = Field(..., ge=0)


class DisableRequest(BaseModel):
    disabled: bool = True


@router.post("/invites")
def create_invite(req: InviteCreate, request: Request):
    auth = get_auth(request)
    if not auth.create_invite(
        req.code, note=req.note, max_uses=req.max_uses, expires_at=req.expires_at
    ):
        raise HTTPException(status_code=400, detail={"message": "邀请码已存在或无效"})
    return {"ok": True, "code": req.code}


@router.get("/invites")
def list_invites(request: Request):
    return {"items": get_auth(request).list_invites()}


@router.post("/invites/{code}/disable")
def disable_invite(code: str, request: Request):
    if not get_auth(request).disable_invite(code):
        raise HTTPException(status_code=404, detail={"message": "邀请码不存在"})
    return {"ok": True}


@router.get("/users")
def list_users(request: Request):
    return {"items": get_auth(request).list_users()}


@router.post("/users/{username}/limit")
def set_limit(username: str, req: SetLimitRequest, request: Request):
    if not get_auth(request).set_daily_limit(username, req.daily_limit):
        raise HTTPException(status_code=404, detail={"message": "用户不存在"})
    return {"ok": True, "username": username, "daily_limit": req.daily_limit}


@router.post("/users/{username}/disable")
def disable_user(username: str, req: DisableRequest, request: Request):
    if not get_auth(request).set_disabled(username, req.disabled):
        raise HTTPException(status_code=404, detail={"message": "用户不存在"})
    return {"ok": True, "username": username, "disabled": req.disabled}


@router.get("/usage")
def usage_stats(request: Request, day: Optional[str] = None):
    return {"items": get_auth(request).usage_stats(day)}


@router.get("/feedback")
def feedback_list(request: Request, limit: int = 50):
    return {"items": get_auth(request).list_feedback(limit=limit)}


@router.get("/feedback/stats")
def feedback_stats(request: Request):
    """对照 3.0 GET /api/qa/feedback/stats。"""
    stats = get_auth(request).feedback_stats()
    # 用 traces 补差评问题预览（qa4 反馈表无原文）
    deps = getattr(request.app.state, "pipeline_deps", None)
    traces = getattr(deps, "traces", None) if deps else None
    if traces is not None:
        for row in stats.get("recent_down") or []:
            rid = row.get("request_id")
            if not rid:
                continue
            try:
                rec = traces.get(rid)
            except Exception:
                rec = None
            if rec:
                q = (rec.get("question_text") or "")[:200]
                if q:
                    row["question"] = q
    return stats


@router.delete("/users/{username}")
def delete_user(username: str, request: Request):
    """对照 3.0 DELETE /api/qa/auth/users/{username}。"""
    if not get_auth(request).delete_user(username):
        raise HTTPException(status_code=404, detail={"message": "用户不存在"})
    return {"ok": True, "username": username}


@router.get("/stats")
def admin_stats(request: Request, limit: int = 5000):
    """对照 3.0 GET /api/qa/stats（聚合 traces）。"""
    deps = getattr(request.app.state, "pipeline_deps", None)
    if deps is None or getattr(deps, "traces", None) is None:
        raise HTTPException(status_code=503, detail={"message": "记录库未初始化"})
    return deps.traces.stats(limit=max(1, min(int(limit), 20000)))


@router.post("/stats/clear")
def stats_clear(request: Request):
    """对照 3.0 POST /api/qa/stats/clear：仅清空 Redis 监控列表，不删 SQLite。"""
    deps = getattr(request.app.state, "pipeline_deps", None)
    if deps is None or getattr(deps, "traces", None) is None:
        raise HTTPException(status_code=503, detail={"message": "记录库未初始化"})
    return deps.traces.clear_monitor()


@router.post("/cache/clear")
def cache_clear(request: Request):
    store = get_store(request)
    # 只删本前缀下全部（match *）
    n = store.scan_delete("*")
    return {"ok": True, "deleted": n, "prefix": getattr(store, "prefix", "")}


@router.get("/traces")
def list_traces(request: Request, limit: int = 50):
    """记录查看：最近 N 条（只读，需管理令牌）。"""
    deps = getattr(request.app.state, "pipeline_deps", None)
    if deps is None or getattr(deps, "traces", None) is None:
        raise HTTPException(status_code=503, detail={"message": "记录库未初始化"})
    return {"items": deps.traces.recent(n=max(1, min(int(limit), 500)))}


@router.get("/traces/{request_id}")
def get_trace(request_id: str, request: Request):
    deps = getattr(request.app.state, "pipeline_deps", None)
    if deps is None or getattr(deps, "traces", None) is None:
        raise HTTPException(status_code=503, detail={"message": "记录库未初始化"})
    rec = deps.traces.get(request_id)
    if rec is None:
        raise HTTPException(status_code=404, detail={"message": "记录不存在"})
    return {"item": rec}
