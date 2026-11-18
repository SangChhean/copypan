# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from api.deps import get_auth, require_user
from config.settings import is_loopback_bind, is_loopback_client

router = APIRouter(prefix="/api/auth", tags=["auth"])

_DEV_USER = "dev"


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


_PROXY_HINT_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded")


def _has_proxy_hint_headers(request: Request) -> bool:
    """反向代理常见头：任一出现即视为非直连本机。"""
    headers = request.headers
    return any(name in headers for name in _PROXY_HINT_HEADERS)


def _host_header_is_local(host_header: str) -> bool:
    """Host 必须是 localhost / 127.0.0.1 / [::1]（可带端口）。"""
    h = (host_header or "").strip().lower()
    if not h:
        return False
    if h.startswith("["):
        # [::1] 或 [::1]:port
        if not h.startswith("[::1]"):
            return False
        rest = h[len("[::1]") :]
        return rest == "" or (rest.startswith(":") and rest[1:].isdigit())
    # hostname 或 hostname:port（IPv4 / 名字最多一个冒号）
    if h.count(":") > 1:
        return False
    name = h.rsplit(":", 1)[0] if ":" in h else h
    return name in {"localhost", "127.0.0.1"}


def _dev_autologin_ok(request: Request) -> bool:
    """开关开 + 绑回环 + 客户端回环 + 无代理头 + Host 为本机。"""
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not getattr(settings, "dev_autologin", False):
        return False
    if not is_loopback_bind(getattr(settings, "bind_host", "") or ""):
        return False
    client_host = request.client.host if request.client else ""
    if not is_loopback_client(client_host):
        return False
    if _has_proxy_hint_headers(request):
        return False
    if not _host_header_is_local(request.headers.get("host") or ""):
        return False
    return True


@router.post("/register")
def register(req: RegisterRequest, request: Request):
    auth = get_auth(request)
    ok, msg = auth.register(req.invite_code, req.username, req.password)
    if not ok:
        raise HTTPException(status_code=400, detail={"message": msg or "注册失败"})
    return {"ok": True}


@router.post("/login")
def login(req: LoginRequest, request: Request):
    auth = get_auth(request)
    username = (req.username or "").strip()
    if username == _DEV_USER and _dev_autologin_ok(request):
        existing = auth.get_user(_DEV_USER)
        if existing is None:
            # 任意非空密码仅用于首次落库哈希；之后本机免登录不再校验密码
            if not auth.create_user(_DEV_USER, req.password):
                raise HTTPException(status_code=401, detail={"message": "用户名或密码错误"})
        elif int(existing.get("disabled") or 0) != 0:
            raise HTTPException(status_code=401, detail={"message": "用户名或密码错误"})
        token = auth.create_token(_DEV_USER)
        return {"token": token, "username": _DEV_USER}

    if not auth.verify_user(req.username, req.password):
        raise HTTPException(status_code=401, detail={"message": "用户名或密码错误"})
    token = auth.create_token(req.username)
    return {"token": token, "username": req.username}


@router.get("/me")
def me(request: Request, username: str = Depends(require_user)):
    auth = get_auth(request)
    user = auth.get_user(username)
    usage = auth.get_usage(username)
    return {
        "username": username,
        "daily_limit": user["daily_limit"] if user else 0,
        "usage": usage,
    }


@router.get("/usage")
def usage(request: Request, username: str = Depends(require_user)):
    """已登录：当日问答用量（不递增）。形状同 3.0：{used, limit}。"""
    auth = get_auth(request)
    u = auth.get_usage(username)
    return {"used": int(u.get("used") or 0), "limit": int(u.get("limit") or 0)}
