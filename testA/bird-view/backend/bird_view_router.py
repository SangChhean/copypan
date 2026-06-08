# -*- coding: utf-8 -*-
import anthropic
import asyncio
import json
import os
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from bird_view_prompts import (
    BIRD_VIEW_SKELETON_PROMPT,
    BIRD_VIEW_OUTLINE_PROMPT,
    BIRD_VIEW_SOURCE_PROMPT_MINISTRY,
    BIRD_VIEW_SOURCE_PROMPT_FEAST,
)

router = APIRouter(prefix='/api/testa/bird_view')


# ── Claude 调用 ────────────────────────────────────────────

async def call_claude(prompt: str, max_tokens: int = 1000) -> str:
    def _sync():
        client = anthropic.Anthropic(api_key=os.environ.get('CLAUDE_API_KEY'))
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=max_tokens,
            temperature=0,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return message.content[0].text or ''
    return await asyncio.to_thread(_sync)


# ── 工具函数 ───────────────────────────────────────────────

def safe_parse_json(raw: str) -> dict:
    """安全解析 LLM 返回的 JSON，处理代码围栏和中文引号。"""
    text = (raw or '').strip()
    if text.startswith('```'):
        lines = text.split('\n')
        inner = []
        for line in lines[1:]:
            if line.strip() == '```':
                break
            inner.append(line)
        text = '\n'.join(inner).strip()
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    try:
        return json.loads(text)
    except Exception:
        return {}


def strip_code_fence(raw: str) -> str:
    """提取最后一个完整代码块的内容，找不到则返回原文。"""
    text = (raw or '').strip()
    lines = text.split('\n')
    last_fence_start = -1
    for idx, line in enumerate(lines):
        if line.strip().startswith('```'):
            last_fence_start = idx
    if last_fence_start != -1:
        inner = []
        found_close = False
        for line in lines[last_fence_start + 1:]:
            if line.strip() == '```':
                found_close = True
                break
            inner.append(line)
        result = '\n'.join(inner).strip()
        # 只有找到完整代码块（有开有闭）且内容非空时才返回剥离结果
        if found_close and result:
            return result
    # 找不到完整代码块或内容为空，返回原始文本
    return text


# ── 请求模型 ───────────────────────────────────────────────

class SkeletonRequest(BaseModel):
    keyword: str
    type: str      # ministry / feast
    content: str


class OutlineRequest(BaseModel):
    keyword: str
    type: str
    content: str
    skeleton: str


class SourceRequest(BaseModel):
    keyword: str
    type: str
    content: str
    outline: str


# ── 路由 ───────────────────────────────────────────────────

@router.post('/skeleton')
async def skeleton(req: SkeletonRequest):
    if not req.keyword.strip():
        raise HTTPException(status_code=400, detail='关键词不能为空')
    if not req.content.strip():
        raise HTTPException(status_code=400, detail='内容不能为空')
    prompt = BIRD_VIEW_SKELETON_PROMPT.format(
        keyword=req.keyword,
        content=req.content,
    )
    raw = await call_claude(prompt, max_tokens=1000)
    obj = safe_parse_json(raw)
    steps = obj.get('skeleton', [])
    skeleton_text = '\n'.join(
        f"{i + 1}. {s.get('step', '')}" for i, s in enumerate(steps)
    )
    return {
        'skeleton_json': steps,
        'skeleton_text': skeleton_text,
        'type': req.type,
    }


@router.post('/outline')
async def outline(req: OutlineRequest):
    if not req.keyword.strip():
        raise HTTPException(status_code=400, detail='关键词不能为空')
    if not req.content.strip():
        raise HTTPException(status_code=400, detail='内容不能为空')
    if not req.skeleton.strip():
        raise HTTPException(status_code=400, detail='骨架不能为空')
    prompt = BIRD_VIEW_OUTLINE_PROMPT.format(
        keyword=req.keyword,
        skeleton=req.skeleton,
        content=req.content,
    )
    raw = await call_claude(prompt, max_tokens=8000)
    text = strip_code_fence(raw)
    print(f"[outline] type={req.type} outline_length={len(text)} outline_preview={text[:100]!r}")
    return {
        'outline': text,
        'type': req.type,
    }


@router.post('/source')
async def source(req: SourceRequest):
    if not req.outline.strip():
        raise HTTPException(status_code=400, detail='纲目不能为空')
    if req.type == 'ministry':
        prompt = BIRD_VIEW_SOURCE_PROMPT_MINISTRY.format(
            content=req.content,
            outline=req.outline,
        )
    else:
        prompt = BIRD_VIEW_SOURCE_PROMPT_FEAST.format(
            content=req.content,
            outline=req.outline,
        )
    raw = await call_claude(prompt, max_tokens=8000)
    text = strip_code_fence(raw)
    return {
        'outline_with_source': text,
        'type': req.type,
    }
