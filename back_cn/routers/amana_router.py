# -*- coding: utf-8 -*-
"""Amana书库免登录入口：按用户 JWT 下发一次性入口链接，链接本身不落日志、不进前端。"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Response

from back_cn.auth import get_current_user

router = APIRouter(prefix="/api/cn/amana", tags=["amana"])


@router.get("/enter_url")
def get_enter_url(response: Response, _user: dict = Depends(get_current_user)):
    url = os.getenv("AMANA_ENTER_URL", "").strip()
    response.headers["Cache-Control"] = "no-store"
    if not url:
        raise HTTPException(status_code=503, detail="Amana书库入口暂未配置")
    return {"url": url}
