# -*- coding: utf-8 -*-
"""增强式翻译 API（主站副本，前缀 /api/ai_search/enhanced_translate）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from user.token import test_token
from features.enhanced_translate.pool import lookup_line_en, update_record, zh_eq
from features.enhanced_translate.service import (
    MAX_CONTENT_CHARS,
    _INDICES_DENSE,
    _RetrievalCtx,
    _build_line_ref_group,
    _build_summary,
    _prep_cached_line,
    _probe_es,
    _retrieve_line,
    enhanced_translate,
)
from features.enhanced_translate.source_translator import _strip_paragraph_suffix

logger = logging.getLogger("ai_search.enhanced_translate")

router = APIRouter(prefix="/api/ai_search/enhanced_translate", tags=["enhanced_translate"])


class EnhancedTranslateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    prompt_override: str | None = Field(default=None, max_length=10_000)


class UpdateTranslationRequest(BaseModel):
    original_line: str = Field(..., min_length=1, max_length=10_000)
    new_translation: str = Field(..., min_length=1, max_length=10_000)


@router.post(
    "/translate",
    dependencies=[Depends(test_token)],
)
async def api_enhanced_translate(req: EnhancedTranslateRequest):
    try:
        return await enhanced_translate(req.content, req.prompt_override)
    except Exception as e:
        logger.exception("enhanced_translate 失败")
        return {"result": None, "refs": [], "error": str(e)}


@router.post(
    "/update_translation",
    dependencies=[Depends(test_token)],
)
async def api_update_translation(req: UpdateTranslationRequest):
    updated = update_record(req.original_line, req.new_translation)
    if not updated:
        return {
            "success": False,
            "error": "Additional Pool 中未找到对应条目，或译文为空",
        }
    return {"success": True}


class RetrieveTestRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)


def _resolve_source_en_no_gemini(source_zh: str, line_refs: list) -> str:
    if not source_zh:
        return ""
    for ref in line_refs:
        zh_src = (ref.get("ch_source") or ref.get("source") or "").strip()
        if not zh_src:
            continue
        stripped = _strip_paragraph_suffix(zh_src)
        if zh_eq(stripped, source_zh):
            en_src = (ref.get("en_source") or "").strip()
            if en_src:
                return en_src
    return ""


@router.post("/retrieve_test", dependencies=[Depends(test_token)])
async def retrieve_test(req: RetrieveTestRequest) -> dict[str, Any]:
    outline = (req.content or "").strip()
    if not outline:
        return {"refs": [], "summary": None, "error": "内容为空", "warnings": []}
    if len(outline) > MAX_CONTENT_CHARS:
        return {
            "refs": [],
            "summary": None,
            "error": f"内容过长（最多 {MAX_CONTENT_CHARS} 字）",
            "warnings": [],
        }

    lines = [ln for ln in outline.splitlines() if ln.strip()]
    ctx = _RetrievalCtx.create(_INDICES_DENSE)
    if any(not lookup_line_en(line) for line in lines):
        await _probe_es(ctx)

    async def _prep_one(i: int, line: str) -> dict[str, Any]:
        cached = lookup_line_en(line)
        if cached:
            return _prep_cached_line(i, line, cached)
        prep = await _retrieve_line(i, line, ctx)
        prep["line_cached_en"] = ""
        return prep

    preps = await asyncio.gather(*[_prep_one(i, line) for i, line in enumerate(lines)])

    for prep in preps:
        source_zh = prep.get("reference_source_zh") or ""
        prep["reference_source_en"] = _resolve_source_en_no_gemini(
            source_zh, prep.get("line_refs") or []
        )

    line_ref_groups: list[dict[str, Any]] = []
    for prep in preps:
        group = _build_line_ref_group(
            prep["line_i"],
            prep["line"],
            prep.get("line_refs") or [],
            line_type=prep["line_type"],
            gemini_translate="",
            additional_pool_line=bool(prep.get("line_cached_en")),
            retrieval_skipped=bool(prep.get("line_cached_en")),
            pool_line=bool(prep.get("pool_line_en")),
            feasts_line=bool(prep.get("feasts_line")),
            reference_source_zh=prep.get("reference_source_zh") or "",
            reference_source_en=prep.get("reference_source_en") or "",
        )
        if prep.get("line_cached_en"):
            group["hit_layer"] = "层1·Additional Pool"
        elif prep.get("pool_line_en"):
            group["hit_layer"] = "层2·ES Pool"
        elif prep.get("feasts_line"):
            group["hit_layer"] = "层3·Feasts"
        elif prep.get("degraded_no_refs"):
            group["hit_layer"] = "层4·检索失败"
        else:
            group["hit_layer"] = "层4·检索"
        line_ref_groups.append(group)

    return {
        "refs": line_ref_groups,
        "summary": _build_summary(line_ref_groups),
        "error": None,
        "warnings": list(dict.fromkeys(ctx.warnings)),
    }
