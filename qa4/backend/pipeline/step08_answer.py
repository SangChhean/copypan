# -*- coding: utf-8 -*-
"""第 8 步：生成回答（Sonnet 流式）。

输入：保留的段落（带编号）、题型与限定、把关结论、理解说明、3a 定义、各层词、辩理材料；
不带对话历史，只带改写后的问题。不传 temperature（封装层保证）。
完成后：[n] → citations（书目由程序按编号生成）；超范围编号标出并记录；引文核对；核对不过的标 unverified 并加小标记。
流式出错：已发文本视为无效，发 error 事件，done 里 degraded=true，answer 换成说明性文字。
取具体对象：原文由系统直接显示；生命读经篇与节期篇另让模型写摘要（标注为归纳），诗歌与注解不写摘要。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, AsyncIterator

from pipeline.citations import build_citations, mark_unverified, verify_quotes
from pipeline.context import RequestContext
from pipeline.schemas import Answer, Passage
from pipeline.step07_judge import format_passages, kept_passages

SUMMARY_TYPES = {"生命读经", "节期纲目"}
logger = logging.getLogger("qa4.step8")


def _step8_token_log_enabled() -> bool:
    return (os.environ.get("QA4_LOG_STEP8_TOKENS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def fallback_text(passages: list[Passage]) -> str:
    lines = ["未能生成完整回答（已降级）。以下是找到的材料，供参考："]
    for p in passages[:20]:
        lines.append(f"[{p.number}] {p.book_title} {p.message_title}".strip())
    return "\n".join(lines)


def _restrictions_text(ctx: RequestContext) -> str:
    plan = ctx.plan
    rs = "；".join(f"{r.kind}={r.value}（{r.role}）" for r in plan.restrictions) or "无"
    return f"{plan.main_type}；限定：{rs}"


def _verdict_text(ctx: RequestContext) -> str:
    return "；".join(f"#{v.subq}:{v.overall}" + (f"（{v.note}）" if v.note else "") for v in ctx.verdicts)


def _layers_text(ctx: RequestContext) -> str:
    return json.dumps([l.model_dump(exclude={"layer1_is_entry"}) for l in ctx.layers], ensure_ascii=False)


def build_prompt(ctx: RequestContext, deps: Any, passages: list[Passage]) -> str:
    tpl = deps.prompts.get("step8")
    return tpl.render(
        question=ctx.question,
        qtype=_restrictions_text(ctx),
        understanding=ctx.plan.understanding,
        verdict=_verdict_text(ctx),
        definitions="\n".join(f"【{k}】{v}" for k, v in ctx.definitions.items()),
        layers=_layers_text(ctx),
        devine="\n".join(d["content"] for d in ctx.devine),
        passages=format_passages(passages, 100000),
    )


def finalize(ctx: RequestContext, deps: Any, text: str, passages: list[Passage]) -> Answer:
    years = {}
    for i, cov in ctx.retrieval_cov.items():
        yr = (cov or {}).get("year_range_covered")
        if yr:
            for p in ctx.passages_by_subq.get(int(i), []):
                years[p.number] = list(yr)
    cites, invalid = build_citations(text, passages, years_by_n=years)
    checks = verify_quotes(text, passages)
    marked = mark_unverified(text, checks, str(deps.cfg.get("unverified_quote_mark", "〔未核实〕")))
    if invalid:
        ctx.record(8, invalid_refs=invalid)
    bad = [c for c in checks if not c.ok]
    if bad:
        ctx.record(8, unverified_quotes=len(bad))
    return Answer(text=marked, citations=cites, quote_checks=checks, invalid_refs=invalid, premise_note=ctx.plan.understanding)


async def run(ctx: RequestContext, deps: Any) -> AsyncIterator[dict[str, Any]]:
    """产出 token / error 事件；结束时 ctx.answer 已就绪。"""
    if ctx.not_found:
        ctx.answer = Answer(text=str(deps.cfg.get("not_found_message")), not_found=True, premise_note=ctx.plan.understanding)
        return
    passages = kept_passages(ctx) or list(ctx.passages)
    prompt = build_prompt(ctx, deps, passages)
    parts: list[str] = []
    log_tok = _step8_token_log_enabled()
    t0 = time.perf_counter()
    token_times: list[float] = []
    try:
        async for delta in deps.llm.stream(
            "sonnet", "", [{"role": "user", "content": prompt}], step="step8", max_tokens=int(deps.cfg.get("step8_max_tokens", 6000))
        ):
            parts.append(delta)
            if log_tok:
                token_times.append(time.perf_counter() - t0)
            yield {"event": "token", "text": delta}
        if log_tok:
            n = len(token_times)
            span = (token_times[-1] - token_times[0]) if n >= 2 else 0.0
            first5 = [round(x, 4) for x in token_times[:5]]
            # 直接 print：不依赖 logger 配置，uvicorn 控制台可见
            print(
                f"[QA4_LOG_STEP8_TOKENS] request={(ctx.request_id or '')[:8]} "
                f"count={n} span_s={span:.4f} first5_s={first5}",
                flush=True,
            )
            logger.info(
                "step8 tokens request=%s count=%s span_s=%.4f first5_s=%s",
                (ctx.request_id or "")[:8],
                n,
                span,
                first5,
            )
            ctx.record(
                8,
                token_log={
                    "count": n,
                    "span_s": round(span, 4),
                    "first5_s": first5,
                    "first_s": round(token_times[0], 4) if token_times else None,
                    "last_s": round(token_times[-1], 4) if token_times else None,
                },
            )
        ctx.note_llm("step8", getattr(deps.llm, "last_stream_result", None))
        ctx.answer = finalize(ctx, deps, "".join(parts), passages)
    except Exception as e:
        ctx.degrade(f"step8:{type(e).__name__}")
        ctx.record(8, stream_error=type(e).__name__, streamed_chars_invalidated=sum(len(p) for p in parts))
        yield {"event": "error", "message": "生成回答时出错，已发出的文字作废", "invalidate_streamed": True}
        ctx.answer = Answer(text=fallback_text(passages), degraded=True, premise_note=ctx.plan.understanding)


async def targeted_summary(ctx: RequestContext, deps: Any) -> Answer:
    t = ctx.targeted or {}
    blocks = t.get("blocks") or []
    meta = t.get("meta") or {}
    notes = list(meta.get("notes") or [])
    if t.get("status") in {"not_found", "not_supported"} or not blocks:
        missing = meta.get("missing")
        msg = "；".join(str(x) for x in notes if x) or (
            f"没有找到要取的内容{('：' + str(missing)) if missing else ''}。"
        )
        return Answer(text=msg, not_found=True, premise_note=ctx.plan.understanding)
    # 诗歌：fallback 等说明拼到 premise；正文靠 direct
    if ctx.plan.main_type == "诗歌" and notes:
        return Answer(text="\n".join(str(x) for x in notes), premise_note=ctx.plan.understanding)
    if ctx.plan.main_type not in SUMMARY_TYPES:
        return Answer(text="", premise_note=ctx.plan.understanding)
    pseudo = [
        Passage(
            number=i + 1,
            id=str(b.get("id") or i),
            index=str(b.get("index")),
            book_title=str(b.get("book_title") or ""),
            message_title=str(b.get("message_title") or ""),
            text=str(b.get("text") or ""),
        )
        for i, b in enumerate(blocks)
    ]
    prompt = build_prompt(ctx, deps, pseudo)
    try:
        res = await deps.llm.complete("sonnet", "", [{"role": "user", "content": prompt}], step="step8_summary", max_tokens=int(deps.cfg.get("step8_summary_max_tokens", 1500)))
        ctx.note_llm("step8_summary", res)
        text = res.text if res.text.startswith("（归纳）") else "（归纳）" + res.text
        return Answer(text=text, premise_note=ctx.plan.understanding)
    except Exception as e:
        ctx.degrade(f"step8_summary:{type(e).__name__}")
        return Answer(text="", degraded=True, premise_note=ctx.plan.understanding)
