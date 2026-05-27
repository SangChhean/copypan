# -*- coding: utf-8 -*-
"""QA 用户注册/登录与管理员用户管理接口。"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from back_qa.qa.auth import (
    create_invite_code,
    create_token,
    create_user,
    list_invite_codes,
    list_users,
    use_invite_code,
    verify_token,
    verify_user,
)

router = APIRouter()


class RegisterRequest(BaseModel):
    invite_code: str
    username: str
    password: str

    @field_validator("invite_code", "username", "password")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("字段不能为空")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("字段不能为空")
        return v


class InviteRequest(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("邀请码不能为空")
        return v


def _require_user(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或 token 格式错误")
    token = auth.split(" ", 1)[1].strip()
    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="token 无效或已过期")
    return username


def _check_admin(request: Request) -> None:
    """管理员 token 验证（与 qa_router 逻辑一致）。"""
    token = os.environ.get("QA_ADMIN_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="管理接口未配置 QA_ADMIN_TOKEN")
    provided = request.headers.get("X-Admin-Token", "")
    if provided != token:
        raise HTTPException(status_code=401, detail="无效的管理员 Token")


@router.post("/api/qa/auth/register")
async def register(req: RegisterRequest):
    """公开：邀请码 + 用户名 + 密码注册。"""
    if not use_invite_code(req.invite_code, req.username):
        raise HTTPException(status_code=400, detail="邀请码无效或已使用")
    if not create_user(req.username, req.password):
        raise HTTPException(status_code=400, detail="用户名已存在")
    return {"ok": True}


@router.post("/api/qa/auth/login")
async def login(req: LoginRequest):
    """公开：用户名密码登录，返回 JWT。"""
    if not verify_user(req.username, req.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(req.username)
    return {"token": token, "username": req.username}


@router.get("/api/qa/auth/me")
async def me(request: Request):
    """已登录：返回当前用户名。"""
    username = _require_user(request)
    return {"username": username}


@router.get("/api/qa/auth/usage")
async def get_usage(request: Request):
    """已登录：返回当日问答用量（不递增）。"""
    username = _require_user(request)
    from back_qa.qa.auth import get_daily_usage

    daily_limit = int(os.getenv("QA_DAILY_LIMIT", "30"))
    return get_daily_usage(username, daily_limit)


@router.post("/api/qa/auth/invite")
async def create_invite(req: InviteRequest, request: Request):
    """管理员：创建邀请码。"""
    _check_admin(request)
    if not create_invite_code(req.code):
        raise HTTPException(status_code=400, detail="邀请码已存在")
    return {"ok": True, "code": req.code}


@router.get("/api/qa/auth/users")
async def users(request: Request):
    """管理员：用户列表（不含密码）。"""
    _check_admin(request)
    return {"items": list_users()}


@router.delete("/api/qa/auth/users/{username}")
async def delete_user_api(username: str, request: Request):
    """管理员：删除用户。"""
    _check_admin(request)
    from back_qa.qa.auth import delete_user

    if not delete_user(username):
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True}


@router.get("/api/qa/auth/invites")
async def invites(request: Request):
    """管理员：邀请码列表。"""
    _check_admin(request)
    return {"items": list_invite_codes()}

