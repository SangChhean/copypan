# polish_router.py
# 文章润色路由

from __future__ import annotations

import asyncio
import logging
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from user.token import test_token

from features.article_polish.prompts import (
    CHURCH_PROMPTS,
    MEMORIAL_ROLES,
    POLISH_STYLES,
    build_church_prompt,
    build_memorial_prompt,
    build_polish_prompt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
_auth = APIRouter(dependencies=[Depends(test_token)])


# ── DeepSeek 调用 ────────────────────────────────────────────────

async def _call_deepseek_polish(
    system: str,
    user_content: str,
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """轻量 DeepSeek 调用，专用于文章润色。只返回文本。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DeepSeek 未配置（请设置 DEEPSEEK_API_KEY）")

    def _sync() -> str:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=600.0,
        )
        r = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if not r.choices:
            return ""
        return (getattr(r.choices[0].message, "content", None) or "").strip()

    return await asyncio.to_thread(_sync)


# ── 请求模型 ─────────────────────────────────────────────────────

class PolishArticleRequest(BaseModel):
    article: str = Field(..., max_length=50_000)
    styles: List[str] = Field(..., min_length=1)
    recovery: bool = Field(False)


class PolishMemorialRequest(BaseModel):
    article: str = Field(..., max_length=50_000)
    roles: List[str] = Field(..., min_length=1)


# ── 路由 ─────────────────────────────────────────────────────────

@_auth.post("/polish/article", summary="通用文章润色")
async def polish_article(request: PolishArticleRequest):
    invalid = [s for s in request.styles if s not in POLISH_STYLES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"无效风格：{invalid}")

    async def _run_one(style_key: str):
        system, user_content = build_polish_prompt(
            style_key, request.article, request.recovery
        )
        try:
            result = await _call_deepseek_polish(system, user_content)
            return {
                "style": style_key,
                "label": POLISH_STYLES[style_key]["label"],
                "result": result,
                "error": None,
            }
        except Exception as e:
            logger.error(f"润色失败 style={style_key}: {e}", exc_info=True)
            return {
                "style": style_key,
                "label": POLISH_STYLES[style_key]["label"],
                "result": None,
                "error": str(e),
            }

    results = await asyncio.gather(*[_run_one(s) for s in request.styles])
    return {"results": list(results)}


@_auth.post("/polish/memorial", summary="恩典陵园见证稿润色")
async def polish_memorial(request: PolishMemorialRequest):
    invalid = [r for r in request.roles if r not in MEMORIAL_ROLES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"无效角色：{invalid}")

    async def _run_one(role_key: str):
        system, user_content = build_memorial_prompt(role_key, request.article)
        try:
            result = await _call_deepseek_polish(system, user_content)
            return {
                "role": role_key,
                "label": MEMORIAL_ROLES[role_key]["label"],
                "result": result,
                "error": None,
            }
        except Exception as e:
            logger.error(f"润色失败 role={role_key}: {e}", exc_info=True)
            return {
                "role": role_key,
                "label": MEMORIAL_ROLES[role_key]["label"],
                "result": None,
                "error": str(e),
            }

    results = await asyncio.gather(*[_run_one(r) for r in request.roles])
    return {"results": list(results)}


class PolishChurchRequest(BaseModel):
    article: str = Field(..., max_length=50_000)
    type_key: str = Field(...)


@_auth.post("/polish/church", summary="召会通讯/见证稿润色（Claude）")
async def polish_church(request: PolishChurchRequest):
    if request.type_key not in CHURCH_PROMPTS:
        raise HTTPException(status_code=400, detail=f"无效类型：{request.type_key}")
    system, user_content = build_church_prompt(request.type_key, request.article)
    try:
        from anthropic import AsyncAnthropic

        api_key = os.environ.get("CLAUDE_API_KEY")
        if not api_key:
            raise RuntimeError("Claude 未配置（请设置 CLAUDE_API_KEY）")
        client = AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        result = message.content[0].text if message.content else ""
        return {
            "type_key": request.type_key,
            "label": CHURCH_PROMPTS[request.type_key]["label"],
            "result": result.strip(),
        }
    except Exception as e:
        logger.error(f"召会润色失败 type={request.type_key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


router.include_router(_auth)
