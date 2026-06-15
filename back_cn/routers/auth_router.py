# -*- coding: utf-8 -*-
"""CN 站用户注册/登录与管理员用户管理接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from back_cn.auth import (
    FEATURES,
    create_invite_code,
    create_token,
    create_user,
    delete_user,
    get_current_user,
    get_daily_usage,
    get_user,
    get_user_feature_limits,
    list_invite_codes,
    list_users,
    set_admin,
    set_user_daily_limit,
    use_invite_code,
    verify_admin_access,
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


class SetAdminRequest(BaseModel):
    is_admin: bool


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
    user = get_user(req.username) or {}
    return {
        "token": token,
        "username": req.username,
        "is_admin": bool(user.get("is_admin")),
    }


@router.get("/me")
async def me(request: Request):
    user = get_current_user(request)
    return {"username": user["username"], "is_admin": user["is_admin"]}


@router.get("/usage")
async def get_usage(request: Request):
    user = get_current_user(request)
    return get_daily_usage(user["username"])


@router.post("/invite")
async def create_invite(
    req: InviteRequest,
    _: bool = Depends(verify_admin_access),
):
    if not create_invite_code(req.code):
        raise HTTPException(status_code=400, detail="邀请码已存在")
    return {"ok": True, "code": req.code}


@router.get("/users")
async def users(_: bool = Depends(verify_admin_access)):
    return {"items": list_users()}


@router.get("/users/{username}/limits")
async def user_limits(username: str, _: bool = Depends(verify_admin_access)):
    data = get_user_feature_limits(username)
    if not data:
        raise HTTPException(status_code=404, detail=f"用户 {username!r} 不存在")
    return data


@router.delete("/users/{username}")
async def delete_user_api(username: str, _: bool = Depends(verify_admin_access)):
    if not delete_user(username):
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True}


@router.get("/invites")
async def invites(_: bool = Depends(verify_admin_access)):
    return {"items": list_invite_codes()}


@router.post("/users/{username}/limit")
async def set_limit(
    username: str,
    req: SetLimitRequest,
    _: bool = Depends(verify_admin_access),
):
    if req.daily_limit < -1:
        raise HTTPException(status_code=400, detail="daily_limit 不能小于 -1")
    try:
        ok = set_user_daily_limit(username, req.feature, req.daily_limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail=f"用户 {username!r} 不存在")
    return {"ok": True, "username": username, "feature": req.feature, "daily_limit": req.daily_limit}


@router.post("/users/{username}/admin")
async def set_user_admin(
    username: str,
    req: SetAdminRequest,
    _: bool = Depends(verify_admin_access),
):
    if not set_admin(username, req.is_admin):
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"username": username, "is_admin": req.is_admin}
