# -*- coding: utf-8 -*-
"""SC 测试页 API：/api/panai4/sc/..."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from user.token import test_token

from panai4.export_docx import content_disposition

from .citation import compute_citation_stats
from .config import MODEL, TIER_ORDER
from .cost import (
    CACHE_USAGE_FIELDS,
    calc_cost_usd,
    cost_payload,
    format_usd,
    input_output_prices,
    sum_costs,
)
from .data import (
    check_sc_placeholders,
    fill_plain_prompt,
    fill_ref_prompt,
    fill_select_prompt,
    build_term_defs,
    load_sc_data,
    remaining_placeholders,
)
from .export_sc import (
    build_kind_docx,
    build_sc_docx,
    export_warning_header,
    kind_docx_filename,
    sc_docx_filename,
)
from .llm_call import sc_complete, usage_dict
from .parse_select import parse_select_output
from . import store

router = APIRouter(prefix="/api/panai4/sc", tags=["panai4-sc"], dependencies=[Depends(test_token)])


class SelectIn(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    select_prompt: str = Field(..., min_length=1)


class GenerateIn(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    final_terms: list[str] = Field(..., min_length=1)
    ref_prompt: str = Field(..., min_length=1)
    plain_prompt: str = Field(..., min_length=1)
    mode: Literal["ref", "ref_and_plain_parallel", "plain_only"] = "ref"
    force_plain: bool = False
    select_run_id: Optional[int] = None


class ExportDocxIn(BaseModel):
    kind: Literal["select", "plain", "ref"]
    topic: str = Field(..., min_length=1, max_length=500)
    text: str = Field(..., min_length=1)


def _require_data():
    data = load_sc_data()
    if data.load_error:
        raise HTTPException(status_code=503, detail=data.load_error)
    return data


def _stats(data) -> dict:
    out = {}
    for tier in ("外在", "内在", "最内在"):
        names = data.tiers[tier]
        has = sum(1 for n in names if data.content_3a.get(n))
        miss = len(names) - has
        out[tier] = {
            "count": len(names),
            "has_3a": has,
            "null_3a": miss,
            "has_pct": round(100.0 * has / len(names), 2) if names else 0.0,
            "null_pct": round(100.0 * miss / len(names), 2) if names else 0.0,
        }
    return out


@router.get("/meta")
def meta():
    data = load_sc_data()
    if data.load_error:
        return {
            "ok": False,
            "error": data.load_error,
            "tiers": {},
            "terms": [],
            "defaults": {},
            "mismatch": data.mismatch,
            "warning": data.load_error,
        }
    stats = _stats(data)
    inner_miss = stats["内在"]["null_3a"] + stats["最内在"]["null_3a"]
    inner_total = stats["内在"]["count"] + stats["最内在"]["count"]
    inner_miss_pct = (100.0 * inner_miss / inner_total) if inner_total else 0.0
    warning = None
    if inner_miss_pct > 25:
        warning = f"内在+最内在 3a 缺失率 {inner_miss_pct:.1f}%（超过 25%）"
    if not data.mismatch.get("equal"):
        warning = (warning or "") + (
            f" 三档名单与 3a 名字集合不一致："
            f"仅名单有 {len(data.mismatch.get('only_tiers') or [])}，"
            f"仅 3a 有 {len(data.mismatch.get('only_3a') or [])}。"
        ).strip()

    terms = [
        {
            "name": name,
            "tier": data.tier_of[name],
            "has_3a": bool(data.content_3a.get(name)),
        }
        for name in data.names
    ]
    return {
        "ok": True,
        "error": None,
        "tiers": stats,
        "total": len(data.names),
        "terms": terms,
        "mismatch": data.mismatch,
        "warning": warning,
        "defaults": {
            "select_prompt": data.select_prompt_default,
            "plain_prompt": data.plain_prompt_default,
            "ref_prompt": data.ref_prompt_default,
        },
        "ref_chars": {
            "ch1": len(data.ch1.rstrip("\n")),
            "def_外在": len(data.def_wai.rstrip("\n")),
            "def_内在": len(data.def_nei.rstrip("\n")),
            "def_最内在": len(data.def_zui.rstrip("\n")),
        },
        "placeholder_checks": {
            "select": check_sc_placeholders("select", data.select_prompt_default),
            "plain": check_sc_placeholders("plain", data.plain_prompt_default),
            "ref": check_sc_placeholders("ref", data.ref_prompt_default),
        },
        "prices": input_output_prices(),
        "cache_usage_fields": list(CACHE_USAGE_FIELDS),
    }


@router.post("/select")
async def select_terms(body: SelectIn):
    data = _require_data()
    check = check_sc_placeholders("select", body.select_prompt)
    if not check["ok"]:
        raise HTTPException(status_code=400, detail="；".join(check["problems"]))
    prompt = fill_select_prompt(body.select_prompt, body.topic.strip(), data)
    leftover = [p for p in remaining_placeholders(prompt) if p in {"CH1", "DEF_WAI", "DEF_NEI", "DEF_ZUINEI", "LIST_ZUINEI", "LIST_NEI", "LIST_WAI", "query"}]
    if leftover:
        raise HTTPException(status_code=400, detail="选词提示词仍有未替换占位符：" + ", ".join(leftover))

    result = await sc_complete(prompt, topic=body.topic.strip())
    has_3a = {n: bool(data.content_3a.get(n)) for n in data.tier_of}
    items = parse_select_output(result.text, data.tier_of, has_3a)
    usage = usage_dict(result)
    cost_select = calc_cost_usd(usage)
    run_id = store.create_run(
        topic=body.topic.strip(),
        select_prompt=body.select_prompt,
        select_raw_output=result.text,
        select_usage_json=usage,
        select_items_json=items,
        cost_select_usd=cost_select,
        cost_total_usd=cost_select,
        status="select_done",
    )
    return {
        "run_id": run_id,
        "items": items,
        "raw_output": result.text,
        "usage": usage,
        "cost": cost_payload(usage, cost_usd=cost_select),
        "prompt_sent_chars": len(prompt),
    }


@router.post("/generate")
async def generate(body: GenerateIn):
    data = _require_data()
    topic = body.topic.strip()
    for kind, tpl in (("ref", body.ref_prompt), ("plain", body.plain_prompt)):
        check = check_sc_placeholders(kind, tpl)
        if not check["ok"]:
            raise HTTPException(status_code=400, detail=f"{kind}：" + "；".join(check["problems"]))

    # validate names
    unknown = [n for n in body.final_terms if n not in data.tier_of]
    if unknown:
        raise HTTPException(status_code=400, detail="最终名单含不在三档中的名字：" + "、".join(unknown[:20]))

    term_defs, skipped, merged, defs_chars, defs_sent_count = build_term_defs(
        body.final_terms, data
    )
    ref_full = fill_ref_prompt(body.ref_prompt, topic, term_defs, data)
    leftover = [p for p in remaining_placeholders(ref_full) if p in {"DEF_WAI", "DEF_NEI", "DEF_ZUINEI", "TERM_DEFS", "query"}]
    if leftover:
        raise HTTPException(status_code=400, detail="加词条定义版仍有未替换占位符：" + ", ".join(leftover))

    plain_full = fill_plain_prompt(body.plain_prompt, topic)
    p_hash = store.prompt_hash(body.plain_prompt)
    cached = store.get_plain_cache(topic, p_hash, MODEL)

    final_terms_payload = [
        {
            "name": n,
            "tier": data.tier_of[n],
            "has_3a": bool(data.content_3a.get(n)),
        }
        for n in body.final_terms
    ]

    plain_result = None
    plain_usage = None
    plain_from_cache = False
    plain_cache_id = None
    plain_status = None
    plain_cost: float | None = None
    plain_cache_cost: float | None = None
    ref_result = None
    ref_usage = None
    ref_cost: float | None = None

    cost_select: float | None = None
    if body.select_run_id:
        prev = store.get_run(body.select_run_id)
        if prev and prev.get("cost_select_usd") is not None:
            cost_select = float(prev["cost_select_usd"])
        elif prev and prev.get("select_usage"):
            cost_select = calc_cost_usd(prev["select_usage"])

    async def run_ref():
        return await sc_complete(ref_full, topic=topic)

    async def run_plain():
        return await sc_complete(plain_full, topic=topic)

    async def resolve_plain(*, force: bool) -> None:
        nonlocal plain_result, plain_usage, plain_from_cache, plain_cache_id, plain_status, cached
        nonlocal plain_cost, plain_cache_cost
        if (not force) and cached is not None:
            plain_result = cached["result_text"]
            plain_usage = json.loads(cached["usage_json"] or "{}")
            plain_cache_id = cached["id"]
            plain_from_cache = True
            plain_status = "cache_hit"
            plain_cost = 0.0
            raw_cached = cached.get("cost_usd")
            if raw_cached is not None:
                plain_cache_cost = float(raw_cached)
            elif plain_usage:
                plain_cache_cost = calc_cost_usd(plain_usage)
            else:
                plain_cache_cost = None
            return
        pr = await run_plain()
        plain_result = pr.text
        plain_usage = usage_dict(pr)
        plain_cost = calc_cost_usd(plain_usage)
        plain_cache_cost = plain_cost
        plain_cache_id = store.upsert_plain_cache(
            topic, body.plain_prompt, MODEL, plain_result, plain_usage, cost_usd=plain_cost
        )
        plain_from_cache = False
        plain_status = "fresh"
        cached = store.get_plain_cache(topic, p_hash, MODEL)

    def _persist_and_out(**extra):
        cost_total = sum_costs(cost_select, extra.get("cost_ref_usd"), extra.get("cost_plain_usd"))
        run_id = store.create_run(
            topic=topic,
            final_terms_json=final_terms_payload,
            skipped_json=skipped,
            merged_json=merged,
            defs_chars=defs_chars,
            cost_select_usd=cost_select,
            cost_ref_usd=extra.get("cost_ref_usd"),
            cost_plain_usd=extra.get("cost_plain_usd"),
            cost_total_usd=cost_total,
            **{k: v for k, v in extra.items() if k not in {"cost_ref_usd", "cost_plain_usd"}},
        )
        if body.select_run_id:
            # 费用归入本 generate run，避免历史累计把选词跑重复加一遍
            store.update_run(
                body.select_run_id,
                status="merged_into_generate",
                cost_total_usd=None,
            )
        return _gen_out(
            run_id,
            skipped,
            merged,
            defs_chars,
            defs_sent_count,
            ref_result,
            ref_usage,
            plain_result,
            plain_usage,
            plain_from_cache,
            cached if plain_from_cache else None,
            plain_status,
            term_defs,
            cost_select=cost_select,
            cost_ref=extra.get("cost_ref_usd"),
            cost_plain=extra.get("cost_plain_usd"),
            cost_total=cost_total,
            plain_cache_cost=plain_cache_cost,
            final_terms_payload=final_terms_payload,
            data=data,
        )

    if body.mode == "plain_only":
        await resolve_plain(force=True if body.force_plain else False)
        if plain_result is None:
            await resolve_plain(force=True)
        return _persist_and_out(
            plain_cache_id=plain_cache_id,
            plain_result=plain_result,
            plain_usage_json=plain_usage,
            plain_from_cache=1 if plain_from_cache else 0,
            cost_plain_usd=plain_cost,
            status="done",
        )

    if body.mode == "ref":
        rr = await run_ref()
        ref_result = rr.text
        ref_usage = usage_dict(rr)
        ref_cost = calc_cost_usd(ref_usage)
        if cached is not None and not body.force_plain:
            plain_result = cached["result_text"]
            plain_usage = json.loads(cached["usage_json"] or "{}")
            plain_cache_id = cached["id"]
            plain_from_cache = True
            plain_status = "cache_hit"
            plain_cost = 0.0
            raw_cached = cached.get("cost_usd")
            plain_cache_cost = float(raw_cached) if raw_cached is not None else calc_cost_usd(plain_usage)
        else:
            plain_status = "no_cache"
            plain_cost = None
        return _persist_and_out(
            ref_prompt_full=ref_full,
            ref_result=ref_result,
            ref_usage_json=ref_usage,
            plain_cache_id=plain_cache_id,
            plain_result=plain_result,
            plain_usage_json=plain_usage,
            plain_from_cache=1 if plain_from_cache else 0,
            cost_ref_usd=ref_cost,
            cost_plain_usd=plain_cost,
            status="done",
        )

    if body.mode == "ref_and_plain_parallel":
        need_plain_call = body.force_plain or cached is None
        if need_plain_call:
            rr, pr = await asyncio.gather(run_ref(), run_plain())
            ref_result = rr.text
            ref_usage = usage_dict(rr)
            ref_cost = calc_cost_usd(ref_usage)
            plain_result = pr.text
            plain_usage = usage_dict(pr)
            plain_cost = calc_cost_usd(plain_usage)
            plain_cache_cost = plain_cost
            plain_cache_id = store.upsert_plain_cache(
                topic, body.plain_prompt, MODEL, plain_result, plain_usage, cost_usd=plain_cost
            )
            plain_from_cache = False
            plain_status = "fresh"
            cached = store.get_plain_cache(topic, p_hash, MODEL)
        else:
            rr = await run_ref()
            ref_result = rr.text
            ref_usage = usage_dict(rr)
            ref_cost = calc_cost_usd(ref_usage)
            plain_result = cached["result_text"]
            plain_usage = json.loads(cached["usage_json"] or "{}")
            plain_cache_id = cached["id"]
            plain_from_cache = True
            plain_status = "cache_hit"
            plain_cost = 0.0
            raw_cached = cached.get("cost_usd")
            plain_cache_cost = float(raw_cached) if raw_cached is not None else calc_cost_usd(plain_usage)
        return _persist_and_out(
            ref_prompt_full=ref_full,
            ref_result=ref_result,
            ref_usage_json=ref_usage,
            plain_cache_id=plain_cache_id,
            plain_result=plain_result,
            plain_usage_json=plain_usage,
            plain_from_cache=1 if plain_from_cache else 0,
            cost_ref_usd=ref_cost,
            cost_plain_usd=plain_cost,
            status="done",
        )

    raise HTTPException(status_code=400, detail="未知 mode")


def _gen_out(
    run_id,
    skipped,
    merged,
    defs_chars,
    defs_sent_count,
    ref_result,
    ref_usage,
    plain_result,
    plain_usage,
    plain_from_cache,
    cached_row,
    plain_status,
    term_defs,
    *,
    cost_select=None,
    cost_ref=None,
    cost_plain=None,
    cost_total=None,
    plain_cache_cost=None,
    final_terms_payload=None,
    data=None,
):
    plain_block = {
        "text": plain_result,
        "usage": plain_usage,
        "from_cache": plain_from_cache,
        "cache_created_at": (cached_row or {}).get("created_at") if plain_from_cache else None,
        "status": plain_status,
        "cost": cost_payload(plain_usage, cost_usd=cost_plain) if cost_plain is not None or plain_usage else None,
        "cache_original_cost_usd": plain_cache_cost if plain_from_cache else None,
        "cache_original_cost_display": format_usd(plain_cache_cost) if plain_from_cache else None,
    }
    if plain_from_cache:
        plain_block["cost_note"] = (
            f"存档，未产生费用（原跑费用 {format_usd(plain_cache_cost)}）"
            if plain_cache_cost is not None
            else "存档，未产生费用（原跑费用 —）"
        )
    citation_stats = None
    if ref_result is not None:
        citation_stats = compute_citation_stats(
            ref_output=ref_result,
            final_terms=final_terms_payload or [],
            skipped=skipped or [],
            merged=merged or [],
            content_3a=getattr(data, "content_3a", None) if data is not None else None,
            tier_of=getattr(data, "tier_of", None) if data is not None else None,
        )
    return {
        "run_id": run_id,
        "skipped": skipped,
        "merged": merged,
        "defs_chars": defs_chars,
        "defs_sent_count": defs_sent_count,
        "term_defs_preview_chars": len(term_defs),
        "ref": {
            "text": ref_result,
            "usage": ref_usage,
            "cost": cost_payload(ref_usage, cost_usd=cost_ref) if cost_ref is not None or ref_usage else None,
        },
        "plain": plain_block,
        "cost": {
            "select_usd": cost_select,
            "select_display": format_usd(cost_select),
            "ref_usd": cost_ref,
            "ref_display": format_usd(cost_ref),
            "plain_usd": cost_plain,
            "plain_display": format_usd(cost_plain),
            "total_usd": cost_total,
            "total_display": format_usd(cost_total),
        },
        "citation_stats": citation_stats,
    }


@router.post("/export_docx")
def export_docx_kind(body: ExportDocxIn):
    """三种独立导出：不依赖数据库，直接用页面当前文本。"""
    data, warning = build_kind_docx(body.kind, body.topic.strip(), body.text)
    filename = kind_docx_filename(body.kind, body.topic.strip())
    headers = {
        "Content-Disposition": content_disposition(filename),
        "Access-Control-Expose-Headers": "Content-Disposition, X-SC-Export-Warning",
        **export_warning_header(warning),
    }
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@router.get("/plain/cache")
def plain_cache(topic: str, prompt_hash: str):
    row = store.get_plain_cache(topic, prompt_hash, MODEL)
    if not row:
        return {"hit": False}
    return {
        "hit": True,
        "id": row["id"],
        "created_at": row["created_at"],
        "result_text": row["result_text"],
        "usage": json.loads(row["usage_json"] or "{}"),
    }


@router.get("/runs")
def runs(limit: int = 50):
    return store.list_runs(limit=min(limit, 200))


@router.get("/runs/{run_id}")
def run_detail(run_id: int):
    row = store.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="运行不存在")
    return row


@router.get("/runs/{run_id}/citation_stats")
def run_citation_stats(run_id: int):
    row = store.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="运行不存在")
    data = load_sc_data()
    return compute_citation_stats(
        ref_output=row.get("ref_result"),
        final_terms=row.get("final_terms") or [],
        skipped=row.get("skipped") or [],
        merged=row.get("merged") or [],
        content_3a=data.content_3a if not data.load_error else None,
        tier_of=data.tier_of if not data.load_error else None,
    )


@router.post("/runs/{run_id}/export")
def export_run(run_id: int):
    row = store.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="运行不存在")
    payload = dict(row)
    payload["final_terms"] = row.get("final_terms") or []
    payload["skipped"] = row.get("skipped") or []
    payload["merged"] = row.get("merged") or []
    sc_data = load_sc_data()
    payload["citation_stats"] = compute_citation_stats(
        ref_output=row.get("ref_result"),
        final_terms=payload["final_terms"],
        skipped=payload["skipped"],
        merged=payload["merged"],
        content_3a=sc_data.content_3a if not sc_data.load_error else None,
        tier_of=sc_data.tier_of if not sc_data.load_error else None,
    )
    data_bytes = build_sc_docx(payload)
    filename = sc_docx_filename(row.get("topic") or "topic", run_id)
    return Response(
        content=data_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": content_disposition(filename)},
    )
