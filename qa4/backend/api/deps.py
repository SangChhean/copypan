# -*- coding: utf-8 -*-
"""FastAPI 依赖。"""

from __future__ import annotations

from fastapi import Header, HTTPException, Request


def get_auth(request: Request):
    return request.app.state.auth


def get_store(request: Request):
    return request.app.state.redis_store


def get_settings_dep(request: Request):
    return request.app.state.settings


def require_user(request: Request, authorization: str = Header(default="")) -> str:
    auth = request.app.state.auth
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"message": "未登录或 token 格式错误"})
    token = authorization.split(" ", 1)[1].strip()
    username = auth.verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail={"message": "token 无效或已过期"})
    user = auth.get_user(username)
    if not user or int(user.get("disabled") or 0) != 0:
        raise HTTPException(status_code=401, detail={"message": "用户不可用"})
    return username


def require_admin(request: Request, x_admin_token: str = Header(default="", alias="X-Admin-Token")) -> None:
    auth = request.app.state.auth
    if not auth.admin_token:
        raise HTTPException(status_code=503, detail={"message": "管理接口未配置 QA4_ADMIN_TOKEN"})
    if not auth.check_admin_token(x_admin_token):
        raise HTTPException(status_code=401, detail={"message": "无效的管理员 Token"})
