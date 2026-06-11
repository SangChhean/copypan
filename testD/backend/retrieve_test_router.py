# -*- coding: utf-8 -*-
"""检索测试台 API：复用 enhanced_translate 检索逻辑，不调用 Gemini。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("testD.retrieve_test")

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from testD.backend._bootstrap import ensure_main_backend_path

ensure_main_backend_path()

from user.token import test_token
from testD.backend.additional_pool import lookup_line_en, normalize_zh, zh_eq
from testD.backend.enhanced_translate_service import (
    MAX_CONTENT_CHARS,
    _INDICES_DENSE,
    _RetrievalCtx,
    _build_line_ref_group,
    _build_summary,
    _prep_cached_line,
    _probe_es,
    _retrieve_line,
)
from testD.backend.source_translator import _strip_paragraph_suffix

router = APIRouter(prefix="/api/testd", tags=["testd"])


def _resolve_source_en_no_gemini(source_zh: str, line_refs: list) -> str:
    """仅路1：normalize_zh 验证，不走 Gemini。"""
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


class RetrieveTestRequest(BaseModel):
    content: str


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

    logger.info(
        "[retrieve_test] ES enabled=%s dense_enabled=%s warnings=%s",
        ctx.es_enabled,
        ctx.dense_enabled,
        ctx.warnings,
    )

    async def _prep_one(i: int, line: str) -> dict[str, Any]:
        cached = lookup_line_en(line)
        if cached:
            return _prep_cached_line(i, line, cached)
        prep = await _retrieve_line(i, line, ctx)
        prep["line_cached_en"] = ""
        return prep

    preps = await asyncio.gather(*[_prep_one(i, line) for i, line in enumerate(lines)])

    for prep in preps:
        logger.info(
            "[retrieve_test] line=%r line_for_retrieval=%r body=%r "
            "line_type=%s retrieval_failed=%s",
            prep.get("line"),
            prep.get("line_for_retrieval"),
            prep.get("body"),
            prep.get("line_type"),
            prep.get("retrieval_failed"),
        )

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
        elif prep.get("retrieval_failed"):
            group["hit_layer"] = "层4·检索失败"
        else:
            group["hit_layer"] = "层4·检索"
        if prep.get("reference_source_zh"):
            group["reference_source_zh"] = prep["reference_source_zh"]
            group["reference_source_en"] = prep.get("reference_source_en") or ""
        line_ref_groups.append(group)

    summary = _build_summary(line_ref_groups)

    return {
        "refs": line_ref_groups,
        "summary": summary,
        "error": None,
        "warnings": list(dict.fromkeys(ctx.warnings)),
    }
