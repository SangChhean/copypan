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
from testD.backend.additional_pool import lookup_line_en
from testD.backend.enhanced_translate_service import (
    MAX_CONTENT_CHARS,
    _INDICES_DENSE,
    _RetrievalCtx,
    _build_line_ref_group,
    _build_summary,
    _precompute_line_types,
    _prep_cached_line,
    _probe_es,
    _retrieve_line,
)
from testD.backend.source_translator import (
    _kg_rag_source_lookup,
    bracket_has_star,
    format_source_en,
)

router = APIRouter(prefix="/api/testd", tags=["testd"])


async def _resolve_source_en_no_gemini(
    source_list: list[str],
    reference_source_zh: str,
) -> str:
    """仅路1：kg-rag 出处查询，不走 Gemini 硬翻。"""
    if not source_list:
        return ""
    en_parts: list[str] = []
    for src in source_list:
        hit_en, _ = await _kg_rag_source_lookup(src)
        en_parts.append(hit_en)
    return format_source_en(en_parts, bracket_has_star(reference_source_zh))


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
    line_types = _precompute_line_types(lines)

    ctx = _RetrievalCtx.create(_INDICES_DENSE)
    if any(not lookup_line_en(line) for line in lines):
        await _probe_es(ctx)

    logger.info(
        "[retrieve_test] ES enabled=%s dense_enabled=%s warnings=%s",
        ctx.es_enabled,
        ctx.dense_enabled,
        ctx.warnings,
    )

    async def _prep_one(i: int, line: str, lt: str) -> dict[str, Any]:
        cached = lookup_line_en(line)
        if cached:
            return _prep_cached_line(i, line, cached, line_type=lt)
        prep = await _retrieve_line(i, line, ctx, line_type=lt)
        prep["line_cached_en"] = ""
        return prep

    preps = await asyncio.gather(
        *[_prep_one(i, line, line_types[i]) for i, line in enumerate(lines)]
    )

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
        "engine": "testD-title-bible-reading-v1",
    }
