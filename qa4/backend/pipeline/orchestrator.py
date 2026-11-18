# -*- coding: utf-8 -*-
"""九步编排：串联步骤；子问题并行（在 step6）；整请求总超时；async generator 产出事件。

事件：step / plan / token / direct / done / error（错误字段统一叫 message）。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncIterator, Optional

from pipeline import (
    step01_entry,
    step02_rewrite,
    step03_plan,
    step04_layer1,
    step05_layers,
    step06_retrieve,
    step07_judge,
    step08_answer,
    step09_record,
)
from pipeline.context import RequestContext, step_event, timed
from pipeline.schemas import TARGETED_TYPES, Answer

logger = logging.getLogger("qa4.pipeline")


def _done_payload(ctx: RequestContext) -> dict[str, Any]:
    ans = ctx.answer
    return {
        "event": "done",
        "answer": ans.text,
        "citations": [c.model_dump() for c in ans.citations],
        "quote_checks": [c.model_dump() for c in ans.quote_checks],
        "cache_hit": ctx.cache_hit,
        "degraded": bool(ctx.degraded or ans.degraded),
        "degraded_reasons": list(ctx.degraded_reasons),
        "not_found": bool(ctx.not_found or ans.not_found),
        "elapsed_ms": ctx.elapsed_ms(),
        "request_id": ctx.request_id,
        "main_type": ctx.plan.main_type if ctx.plan else "",
        "premise_note": ans.premise_note,
        "awaiting_choice": bool(ctx.awaiting_choice or ans.awaiting_choice),
        "lyrics_status": ctx.lyrics_status or ans.lyrics_status,
        "plan_source": (ctx.plan.source if ctx.plan else None),
        "choose_candidates": list(ans.choose_candidates or []),
        "rule_hits": list(ctx.rule_hits or []),
    }


def _chunk_direct(blocks: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    """按顺序分块：每块一个 block；超长 block 再按字数切。"""
    out: list[dict[str, Any]] = []
    for i, b in enumerate(blocks):
        text = str(b.get("text") or "")
        meta = {k: v for k, v in b.items() if k != "text"}
        if size <= 0 or len(text) <= size:
            out.append({"index": i, "text": text, "meta": meta, "part": 0, "parts": 1})
            continue
        parts = [text[j : j + size] for j in range(0, len(text), size)]
        for p, chunk in enumerate(parts):
            out.append({"index": i, "text": chunk, "meta": meta, "part": p, "parts": len(parts)})
    return out


async def run_pipeline(
    deps: Any,
    *,
    question: str,
    history: Optional[list[dict[str, Any]]] = None,
    request_id: Optional[str] = None,
) -> AsyncIterator[dict[str, Any]]:
    """产出事件流。调用方已完成鉴权/限额/限流/注入过滤。"""
    cfg = deps.cfg
    total_timeout = float(cfg.get("request_timeout_s", 180))
    step_to = cfg.get("step_timeouts_s") or {}
    ctx = RequestContext(
        request_id=request_id or uuid.uuid4().hex,
        question_orig=question,
        history=list(history or []),
    )
    t_deadline = time.perf_counter() + total_timeout

    async def _budget(step: int) -> float:
        remain = max(0.1, t_deadline - time.perf_counter())
        named = float(step_to.get(f"step{step}", remain))
        return min(remain, named)

    try:
        # ---- 1 入口缓存 ----
        yield step_event(1, "开始")
        hit = step01_entry.cache_lookup(ctx, deps)
        ctx.record(1, cache_lookup=bool(hit), history=bool(ctx.history))
        if hit:
            ctx.cache_hit = True
            ctx.answer = Answer.model_validate(hit.get("answer") or hit)
            if hit.get("plan"):
                from pipeline.schemas import Plan

                try:
                    ctx.plan = Plan.model_validate(hit["plan"])
                except Exception:
                    pass
            yield step_event(1, "完成", cache_hit=True)
            yield _done_payload(ctx)
            step09_record.write_trace(ctx, deps)
            yield step_event(9, "完成")
            return
        yield step_event(1, "完成", cache_hit=False)

        # ---- 2 追问改写 ----
        if ctx.history:
            yield step_event(2, "开始")
            ctx.question = await timed(ctx, 2, step02_rewrite.run(ctx, deps), await _budget(2))
            yield step_event(2, "完成")
            hit2 = deps.cache.lookup(ctx.question)
            if hit2:
                ctx.cache_hit = True
                ctx.answer = Answer.model_validate(hit2.get("answer") or hit2)
                yield _done_payload(ctx)
                step09_record.write_trace(ctx, deps)
                yield step_event(9, "完成")
                return
        else:
            ctx.question = ctx.question_orig
            ctx.record(2, skipped=True)

        # ---- 3 计划（含规则前置）----
        yield step_event(3, "开始")
        ctx.plan = await timed(ctx, 3, step03_plan.run(ctx, deps), await _budget(3))
        yield step_event(3, "完成" if not ctx.plan.degraded else "降级")
        yield {
            "event": "plan",
            "main_type": ctx.plan.main_type,
            "complex": ctx.plan.complex,
            "subquestions": [sq.model_dump() for sq in ctx.plan.subquestions],
            "understanding": ctx.plan.understanding,
            "sensitive": ctx.plan.sensitive,
            "restrictions": [r.model_dump() for r in ctx.plan.restrictions],
            "locator": ctx.plan.locator.model_dump() if ctx.plan.locator else None,
            "source": ctx.plan.source,
            "rule_hits": list(ctx.rule_hits or []),
            "lyrics_status": ctx.lyrics_status,
        }

        # 歌词 too_*/多选：本轮结束，不进 4–8
        if ctx.rule_early_done:
            ctx.record(4, skipped=True, reason="rule_early")
            ctx.record(5, skipped=True, reason="rule_early")
            ctx.record(6, skipped=True, reason="rule_early", lyrics_status=ctx.lyrics_status, plan_source=ctx.plan.source)
            ctx.record(7, skipped=True, reason="rule_early")
            ctx.record(8, skipped=True, reason="rule_early")
            if ctx.awaiting_choice:
                slim = []
                for c in ctx.answer.choose_candidates or []:
                    slim.append(
                        {
                            "series": c.get("series"),
                            "series_zh": c.get("series_zh"),
                            "hymn_number": c.get("hymn_number"),
                            "name": c.get("name"),
                            "unit_label": c.get("unit_label"),
                            "snippet": c.get("snippet"),
                            "snippet_len": c.get("snippet_len", len(str(c.get("snippet") or ""))),
                            "match_type": c.get("match_type"),
                        }
                    )
                yield {"event": "choose", "candidates": slim, "answer": ctx.answer.text}
            yield step_event(9, "开始")
            # 歌词早退一律不缓存
            ctx.record(9, cached=False, lyrics_early=True)
            step09_record.write_trace(ctx, deps)
            yield step_event(9, "完成")
            yield _done_payload(ctx)
            return

        targeted = ctx.plan.main_type in TARGETED_TYPES

        if targeted:
            # 跳过 4、5、7
            ctx.record(4, skipped=True)
            ctx.record(5, skipped=True)
            yield step_event(6, "开始")
            ctx.targeted = await timed(ctx, 6, step06_retrieve.run_targeted(ctx, deps), await _budget(6))
            yield step_event(6, "完成", targeted_status=(ctx.targeted or {}).get("status"))
            # 经文 / 诗歌：增发结构化展示事件（不改 step06 本体）；有载荷则不再推 plain direct
            structured = None
            if ctx.plan.main_type == "经文":
                try:
                    from scripture.normalize import parse_refs
                    from scripture.verse_payload import build_verse_data

                    loc = ctx.plan.locator
                    refs = parse_refs(
                        (loc.scripture if loc else None) or "",
                        bible=getattr(deps, "bible", None),
                        validate=getattr(deps, "bible", None) is not None,
                    )
                    structured = build_verse_data(
                        bible=getattr(deps, "bible", None),
                        refs=refs,
                        targeted=ctx.targeted,
                    )
                except Exception:
                    structured = None
                if structured is not None:
                    yield {"event": "verse_data", "data": structured}
            elif ctx.plan.main_type == "诗歌":
                try:
                    from hymn.payload import build_hymn_data

                    structured = build_hymn_data(ctx.targeted, plan=ctx.plan)
                except Exception:
                    structured = None
                if structured is not None:
                    yield {"event": "hymn_data", "data": structured}
            if structured is None:
                for ch in _chunk_direct(
                    list((ctx.targeted or {}).get("blocks") or []),
                    int(cfg.get("direct_chunk_chars", 800)),
                ):
                    yield {"event": "direct", **ch}
            ctx.record(7, skipped=True, targeted_status=(ctx.targeted or {}).get("status"))
            yield step_event(8, "开始")
            ctx.answer = await timed(ctx, 8, step08_answer.targeted_summary(ctx, deps), await _budget(8))
            if (ctx.targeted or {}).get("status") in {"not_found", "not_supported"}:
                ctx.not_found = True
                if not ctx.answer.text:
                    ctx.answer = Answer(
                        text=f"没有找到要取的内容（{(ctx.targeted or {}).get('status')}）。",
                        not_found=True,
                        premise_note=ctx.plan.understanding,
                    )
            yield step_event(8, "完成" if not ctx.answer.degraded else "降级")
        else:
            # ---- 4 ----
            yield step_event(4, "开始")
            ctx.layers = await timed(ctx, 4, step04_layer1.run(ctx, deps), await _budget(4))
            yield step_event(4, "完成")

            # ---- 5（核实说法 / 反找经文跳过）----
            only_l1 = ctx.plan.main_type in {"核实说法", "反找经文"}
            if only_l1:
                ctx.record(5, skipped=True, reason=ctx.plan.main_type)
            else:
                yield step_event(5, "开始")
                ctx.layers = await timed(ctx, 5, step05_layers.run(ctx, deps), await _budget(5))
                yield step_event(5, "完成")

            # ---- 6 ----
            yield step_event(6, "开始")
            await timed(ctx, 6, step06_retrieve.run(ctx, deps), await _budget(6))
            n_sub = len(ctx.plan.subquestions)
            yield step_event(
                6,
                "完成",
                passages=len(ctx.passages),
                subquestions=n_sub,
                progress={"done": n_sub, "total": n_sub} if ctx.plan.complex else None,
            )

            # ---- 7 ----
            yield step_event(7, "开始")
            ctx.verdicts = await timed(ctx, 7, step07_judge.run(ctx, deps), await _budget(7))
            yield step_event(7, "完成", not_found=ctx.not_found, retried=ctx.retried)

            # ---- 8 ----
            yield step_event(8, "开始")
            stream_ok = True
            async for ev in step08_answer.run(ctx, deps):
                if ev.get("event") == "error":
                    stream_ok = False
                yield ev
            yield step_event(8, "完成" if stream_ok and not ctx.answer.degraded else "降级")

        # ---- 9 ----
        yield step_event(9, "开始")
        payload = {
            "answer": ctx.answer.model_dump(),
            "plan": ctx.plan.model_dump() if ctx.plan else None,
            "citations": [c.model_dump() for c in ctx.answer.citations],
        }
        cached = step09_record.save_cache(ctx, deps, payload)
        ctx.record(9, cached=cached)
        step09_record.write_trace(ctx, deps)
        yield step_event(9, "完成")
        yield _done_payload(ctx)

    except asyncio.TimeoutError:
        ctx.degrade("request_timeout")
        yield {"event": "error", "message": "请求超时"}
        ctx.answer = Answer(text="请求超时，未能完成回答。", degraded=True)
        step09_record.write_trace(ctx, deps)
        yield _done_payload(ctx)
    except Exception as e:
        logger.exception("pipeline failed request=%s", ctx.request_id[:8])
        ctx.degrade(f"orchestrator:{type(e).__name__}")
        yield {"event": "error", "message": f"流水线异常：{type(e).__name__}"}
        if not ctx.answer.text:
            ctx.answer = Answer(text="处理问题时出错。", degraded=True)
        step09_record.write_trace(ctx, deps)
        yield _done_payload(ctx)


async def collect_ask(
    deps: Any,
    *,
    question: str,
    history: Optional[list[dict[str, Any]]] = None,
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    """非流式：跑完流水线，返回 done 载荷（附带中间事件名序列）。"""
    events: list[str] = []
    done: Optional[dict[str, Any]] = None
    async for ev in run_pipeline(deps, question=question, history=history, request_id=request_id):
        events.append(str(ev.get("event") or ""))
        if ev.get("event") == "done":
            done = ev
    if done is None:
        done = {"event": "done", "answer": "", "degraded": True, "message": "无完成事件"}
    done = dict(done)
    done["events"] = events
    return done
