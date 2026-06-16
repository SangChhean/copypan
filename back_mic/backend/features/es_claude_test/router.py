# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
from urllib.parse import quote

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from features.es_claude_test import generation_service, retrieval_service
from features.es_claude_test.prompts import EXPAND_PROMPT
from user.token import test_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/es_claude_test", tags=["es_claude_test"])

_EXPAND_MODEL = "claude-haiku-4-5-20251001"


class ExpandRequest(BaseModel):
    keyword: str = Field(..., min_length=1)


class ExpandResponse(BaseModel):
    keywords: list[str]


class SearchRequest(BaseModel):
    keyword: str = Field(..., min_length=1)
    keywords: list[str] = Field(..., min_length=1)


class GenerateRequest(BaseModel):
    keyword: str = Field(..., min_length=1)
    stages: dict


class DownloadRequest(BaseModel):
    keyword: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    version: str = Field(..., pattern="^(concise|rich)$")


def _parse_keyword_array(text: str, fallback: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return [fallback]
    # 去掉可能的 markdown 代码围栏
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("expand JSON 解析失败，使用原词兜底: %r", raw[:200])
        return [fallback]
    if not isinstance(data, list):
        return [fallback]
    keywords = [str(x).strip() for x in data if str(x).strip()]
    return keywords if keywords else [fallback]


async def _expand_keywords(keyword: str) -> list[str]:
    api_key = (os.environ.get("CLAUDE_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="Claude 未配置（请设置 CLAUDE_API_KEY）")

    def _sync() -> str:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=_EXPAND_MODEL,
            max_tokens=200,
            temperature=0,
            system=EXPAND_PROMPT,
            messages=[{"role": "user", "content": f"主题词：{keyword}"}],
        )
        if not message.content or not getattr(message.content[0], "text", None):
            return ""
        return message.content[0].text

    text = await asyncio.to_thread(_sync)
    return _parse_keyword_array(text, keyword)


@router.post("/expand", dependencies=[Depends(test_token)], response_model=ExpandResponse)
async def expand(req: ExpandRequest) -> ExpandResponse:
    keywords = await _expand_keywords(req.keyword.strip())
    return ExpandResponse(keywords=keywords)


@router.post("/search", dependencies=[Depends(test_token)])
async def search(req: SearchRequest) -> dict:
    try:
        return await retrieval_service.search_and_stage(req.keyword.strip(), req.keywords)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/generate", dependencies=[Depends(test_token)])
async def generate(req: GenerateRequest) -> dict:
    try:
        return await generation_service.generate_article(req.keyword.strip(), req.stages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download", dependencies=[Depends(test_token)])
async def download(req: DownloadRequest):
    try:
        from docx import Document

        doc = Document()
        for line in req.text.split("\n"):
            doc.add_paragraph(line)

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        suffix = "精简版" if req.version == "concise" else "丰富版"
        filename = f"{req.keyword.strip()}_进展_{suffix}.docx"
        ascii_name = filename.encode("ascii", "ignore").decode() or "article.docx"
        disposition = (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
        )
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": disposition},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
