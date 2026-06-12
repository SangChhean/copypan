# -*- coding: utf-8 -*-
"""CN 站用户注册/登录与管理员用户管理接口。"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from back_cn.auth import (
    FEATURES,
    create_invite_code,
    create_token,
    create_user,
    delete_user,
    get_daily_usage,
    list_invite_codes,
    list_users,
    set_user_daily_limit,
    use_invite_code,
    verify_token,
    verify_user,
)

router = APIRouter(prefix="/api/cn/auth", tags=["cn-auth"])


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


class SetLimitRequest(BaseModel):
    feature: str
    daily_limit: int

    @field_validator("feature")
    @classmethod
    def _valid_feature(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in FEATURES:
            raise ValueError(f"feature 必须是 {', '.join(FEATURES)} 之一")
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
    token = os.environ.get("CN_ADMIN_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="管理接口未配置 CN_ADMIN_TOKEN")
    provided = request.headers.get("X-Admin-Token", "")
    if provided != token:
        raise HTTPException(status_code=401, detail="无效的管理员 Token")


@router.post("/register")
async def register(req: RegisterRequest):
    if not use_invite_code(req.invite_code, req.username):
        raise HTTPException(status_code=400, detail="邀请码无效或已使用")
    if not create_user(req.username, req.password):
        raise HTTPException(status_code=400, detail="用户名已存在")
    return {"ok": True}


@router.post("/login")
async def login(req: LoginRequest):
    if not verify_user(req.username, req.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(req.username)
    return {"token": token, "username": req.username}


@router.get("/me")
async def me(request: Request):
    username = _require_user(request)
    return {"username": username}


@router.get("/usage")
async def get_usage(request: Request):
    username = _require_user(request)
    return get_daily_usage(username)


@router.post("/invite")
async def create_invite(req: InviteRequest, request: Request):
    _check_admin(request)
    if not create_invite_code(req.code):
        raise HTTPException(status_code=400, detail="邀请码已存在")
    return {"ok": True, "code": req.code}


@router.get("/users")
async def users(request: Request):
    _check_admin(request)
    return {"items": list_users()}


@router.delete("/users/{username}")
async def delete_user_api(username: str, request: Request):
    _check_admin(request)
    if not delete_user(username):
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True}


@router.get("/invites")
async def invites(request: Request):
    _check_admin(request)
    return {"items": list_invite_codes()}


@router.post("/users/{username}/limit")
async def set_limit(username: str, req: SetLimitRequest, request: Request):
    _check_admin(request)
    if req.daily_limit < -1:
        raise HTTPException(status_code=400, detail="daily_limit 不能小于 -1")
    try:
        ok = set_user_daily_limit(username, req.feature, req.daily_limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail=f"用户 {username!r} 不存在")
    return {"ok": True, "username": username, "feature": req.feature, "daily_limit": req.daily_limit}
