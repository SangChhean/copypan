# -*- coding: utf-8 -*-
"""第 9 步：缓存 + 记录。

缓存：键见 pipeline/cache.py；「未找到」只在放宽重试后仍不够时才缓存（1 天）；取具体对象不缓存；降级结果不缓存【暂定】。
记录：qa4_traces（方案 A 默认可存问题原文，仅管理接口可读）+ Redis 监控列表（不含原文）。
"""

from __future__ import annotations

from typing import Any

from core.pricing import estimate_total_cost_usd
from pipeline.context import RequestContext
from pipeline.schemas import TraceRecord
from pipeline.textutil import qhash



def collect_es_failures(retrieval_cov: dict[str, Any]) -> list[dict[str, Any]]:
    """从各子问题 coverage.es_failures 汇总（按 logical+status+type 去重）。"""
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for sub in (retrieval_cov or {}).values():
        if not isinstance(sub, dict):
            continue
        cov = sub.get("coverage") if isinstance(sub.get("coverage"), dict) else {}
        for f in cov.get("es_failures") or []:
            if not isinstance(f, dict):
                continue
            key = (f.get("logical"), f.get("status"), f.get("type"))
            if key in seen:
                continue
            seen.add(key)
            entry = {
                "logical": f.get("logical"),
                "status": f.get("status"),
                "type": f.get("type"),
            }
            if f.get("index"):
                entry["index"] = f.get("index")
            out.append(entry)
    return out


def build_trace(ctx: RequestContext, deps: Any) -> dict[str, Any]:
    plan = ctx.plan
    store_text = bool((deps.cfg.get("traces") or {}).get("store_question_text", True))
    # 有送入第 2 步的上文才记改写后问题（失败回退时仍记原问题，便于对照）
    rewritten = ctx.question if ctx.history_for_rewrite else ""
    es_failures = collect_es_failures(ctx.retrieval_cov)
    rec = TraceRecord(
        request_id=ctx.request_id,
        question_hash=qhash(ctx.question_orig),
        question_len=len(ctx.question_orig),
        question_text=ctx.question_orig if store_text else None,
        history_json=list(ctx.history_for_rewrite) if store_text else None,
        rewritten_question=(rewritten if store_text else "") or "",
        steps=ctx.steps,
        models=ctx.models,
        prompt_versions=deps.prompts.versions(),
        timings_ms=ctx.timings_ms,
        tokens=ctx.tokens,
        retrieval=ctx.retrieval_cov,
        verdicts=[v.model_dump() for v in ctx.verdicts],
        retried=ctx.retried,
        quote_checks=[{"ok": c.ok, "passage_n": c.passage_n, "parts": c.parts, "quote_len": len(c.quote)} for c in ctx.answer.quote_checks],
        cache_hit=ctx.cache_hit,
        degraded=ctx.degraded or ctx.answer.degraded,
        degraded_reasons=list(ctx.degraded_reasons),
        es_failures=es_failures,
        not_found=ctx.not_found or ctx.answer.not_found,
        main_type=plan.main_type if plan else "",
        elapsed_ms=ctx.elapsed_ms(),
        total_cost_usd=estimate_total_cost_usd(ctx.tokens, ctx.models),
        warnings=list(ctx.warnings),
    )
    data = rec.model_dump()
    # 附加规则/歌词摘要（steps 内已有部分；顶层便于面板）
    data["plan_source"] = plan.source if plan else ""
    data["lyrics_status"] = ctx.lyrics_status or (ctx.answer.lyrics_status if ctx.answer else None)
    data["rule_hits"] = list(ctx.rule_hits or [])
    data["awaiting_choice"] = bool(ctx.awaiting_choice)
    return data


def should_cache(ctx: RequestContext) -> bool:
    if ctx.cache_hit or ctx.plan is None or ctx.plan.targeted:
        return False
    # 歌词规则路径一律不缓存（含 too_*/候选/not_found 回落前已早退）
    if getattr(ctx.plan, "source", None) == "lyrics_rule" or ctx.lyrics_status or ctx.rule_early_done:
        return False
    if ctx.degraded or ctx.answer.degraded:
        return False
    if ctx.not_found or ctx.answer.not_found:
        return bool(ctx.retried)
    return True


def save_cache(ctx: RequestContext, deps: Any, payload: dict[str, Any]) -> bool:
    if not should_cache(ctx):
        return False
    restrictions = [r.model_dump() for r in ctx.plan.restrictions]
    deps.cache.save(
        ctx.question,
        ctx.plan.main_type,
        restrictions,
        payload,
        not_found=bool(ctx.not_found or ctx.answer.not_found),
        targeted=ctx.plan.targeted,
    )
    if ctx.question != ctx.question_orig and not ctx.history:
        deps.cache.save(ctx.question_orig, ctx.plan.main_type, restrictions, payload, not_found=bool(ctx.not_found), targeted=False)
    return True


def write_trace(ctx: RequestContext, deps: Any) -> dict[str, Any]:
    rec = build_trace(ctx, deps)
    try:
        deps.traces.write(rec)
    except Exception as e:
        ctx.degrade(f"step9:{type(e).__name__}")
    return rec
