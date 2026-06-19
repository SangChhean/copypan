# -*- coding: utf-8 -*-
"""增强式翻译 API（主站副本，前缀 /api/ai_search/enhanced_translate）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from user.token import test_token
from features.enhanced_translate.pool import lookup_line_en, update_record, update_record_en2zh
from features.enhanced_translate.service import (
    MAX_CONTENT_CHARS,
    _INDICES_DENSE,
    _RetrievalCtx,
    _build_line_ref_group,
    _build_summary,
    _precompute_line_types,
    _prep_cached_line,
    _probe_es,
    _retrieve_bible_reading_line,
    _retrieve_line,
    _retrieve_title_line,
    enhanced_translate,
    enhanced_translate_en2zh,
)
from features.enhanced_translate.source_translator import (
    _kg_rag_source_lookup,
    bracket_has_star,
    format_source_en,
    format_source_zh,
    parse_source_from_line,
)

logger = logging.getLogger("ai_search.enhanced_translate")

router = APIRouter(prefix="/api/ai_search/enhanced_translate", tags=["enhanced_translate"])


class EnhancedTranslateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    prompt_override: str | None = Field(default=None, max_length=10_000)


class UpdateTranslationRequest(BaseModel):
    original_line: str = Field(..., min_length=1, max_length=10_000)
    new_translation: str = Field(..., min_length=1, max_length=10_000)
    direction: str = Field(default="zh2en")  # "zh2en" 或 "en2zh"


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
    "/en2zh",
    dependencies=[Depends(test_token)],
)
async def api_enhanced_translate_en2zh(req: EnhancedTranslateRequest):
    try:
        return await enhanced_translate_en2zh(req.content, req.prompt_override)
    except Exception as e:
        logger.exception("enhanced_translate_en2zh 失败")
        return {"result": None, "refs": [], "error": str(e)}


@router.post(
    "/update_translation",
    dependencies=[Depends(test_token)],
)
async def api_update_translation(req: UpdateTranslationRequest):
    if req.direction == "en2zh":
        if not any(c.isascii() and c.isalpha() for c in req.original_line):
            return {
                "success": False,
                "error": "英翻中方向的 original_line 必须是英文",
            }
        updated = update_record_en2zh(req.original_line, req.new_translation)
    else:
        updated = update_record(req.original_line, req.new_translation)
    if not updated:
        return {
            "success": False,
            "error": "Additional Pool 中未找到对应条目，或译文为空",
        }
    return {"success": True}


class RetrieveTestRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)


async def _resolve_source_en_no_gemini(
    source_list: list[str],
    reference_source_zh: str,
) -> str:
    """仅路1：kg-rag 出处查询，不走 Gemini 硬翻。"""
    if not source_list:
        return ""
    en_parts: list[str] = []
    for src in source_list:
        hit_en, _, _, _ = await _kg_rag_source_lookup(src)
        en_parts.append(hit_en)
    return format_source_en(en_parts, bracket_has_star(reference_source_zh))


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
    line_types = _precompute_line_types(lines)

    ctx = _RetrievalCtx.create(_INDICES_DENSE)
    if any(not lookup_line_en(line) for line in lines):
        await _probe_es(ctx)

    async def _prep_one(i: int, line: str, lt: str) -> dict[str, Any]:
        cached = lookup_line_en(line)
        if cached:
            return _prep_cached_line(i, line, cached, line_type=lt)
        line_for_retrieval, reference_source_zh_list = parse_source_from_line(line)
        from features.enhanced_translate.service import _strip_scripture_suffix

        prefix, body, _ = _strip_scripture_suffix(line_for_retrieval)
        reference_source_zh = format_source_zh(reference_source_zh_list)
        _src = {
            "line_for_retrieval": line_for_retrieval,
            "reference_source_zh": reference_source_zh,
            "reference_source_zh_list": reference_source_zh_list,
            "reference_source_en": "",
        }
        if lt == "bible-reading":
            prep = await _retrieve_bible_reading_line(i, line, body, lt, _src)
        elif lt == "title":
            prep = await _retrieve_title_line(
                i, line, body, lt, line_for_retrieval, _src, ctx
            )
        else:
            prep = await _retrieve_line(i, line, ctx, line_type=lt)
        prep["line_cached_en"] = ""
        return prep

    preps = await asyncio.gather(
        *[_prep_one(i, line, line_types[i]) for i, line in enumerate(lines)]
    )

    for prep in preps:
        source_list = prep.get("reference_source_zh_list") or []
        prep["reference_source_en"] = await _resolve_source_en_no_gemini(
            source_list, prep.get("reference_source_zh") or ""
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
            reference_source_zh_list=prep.get("reference_source_zh_list") or [],
            reference_source_en=prep.get("reference_source_en") or "",
        )
        lt = prep.get("line_type") or ""
        if prep.get("line_cached_en"):
            group["hit_layer"] = "层1·Additional Pool"
        elif lt == "bible-reading":
            group["hit_layer"] = "读经·跳过检索"
        elif lt == "title" and prep.get("deduped_refs"):
            group["hit_layer"] = "篇题·Pool"
        elif lt == "title":
            group["hit_layer"] = "篇题·无参考"
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
