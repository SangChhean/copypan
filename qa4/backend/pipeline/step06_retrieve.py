# -*- coding: utf-8 -*-
"""第 6 步：检索。

- 每个子问题并行（并发上限配置）；综合类子问题不检索；
- 取具体对象调定向取篇，原文按顺序分块（direct 事件由编排器发出）；
- 反找经文调 ReverseFinder，经文作为段落；
- 每个 Passage 由程序编号 1..N（整题内连续、稳定：按子问题顺序、再按检索顺序；同一段只编一次）。
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from pipeline.context import RequestContext
from pipeline.schemas import Passage
from retrieval.types import SubQuestionSpec


def _to_schema(p: Any, subq: int) -> Passage:
    return Passage(
        id=p.id,
        index=p.index,
        book_title=p.book_title,
        message_title=p.message_title,
        location=dict(p.location),
        text=p.text,
        route=p.route,
        meta=dict(p.meta),
        subq=subq,
    )


def specs_for(ctx: RequestContext, deps: Any, *, relaxed: bool = False, only: set[int] | None = None) -> dict[int, SubQuestionSpec]:
    from retrieval.config import params

    p = params()
    plan = ctx.plan
    cap = int(p.get("per_subquestion_cap", 20)) if plan.complex else int(p.get("unsplit_question_cap", 45))
    out: dict[int, SubQuestionSpec] = {}
    for i, sq in enumerate(plan.subquestions):
        if only is not None and i not in only:
            continue
        layers = ctx.layers[i] if i < len(ctx.layers) else None
        out[i] = SubQuestionSpec(
            query=sq.text,
            qtype=sq.qtype,
            angle=sq.angle,
            words=layers.recommended() if layers else [],
            layer1_words=list(layers.layer1) if layers else [],
            author=plan.author(),
            year_range=plan.year_range(),
            original_question=ctx.question_orig,
            synthesis=sq.synthesis,
            relaxed=relaxed,
            cap=cap,
            scope_override=sq.scope,
        )
    return out


async def retrieve_subquestions(ctx: RequestContext, deps: Any, specs: dict[int, SubQuestionSpec]) -> dict[int, list[Passage]]:
    sem = asyncio.Semaphore(int(deps.cfg.get("subquestion_concurrency", 4)))

    async def one(i: int, spec: SubQuestionSpec):
        async with sem:
            return i, await deps.retrieval.retrieve(spec)

    results = await asyncio.gather(*[one(i, s) for i, s in specs.items()])
    out: dict[int, list[Passage]] = {}
    for i, res in sorted(results, key=lambda x: x[0]):
        ctx.retrieval_cov[str(i)] = {
            "coverage": res.coverage,
            "synthesis": res.synthesis,
            "none_flag": res.none_flag,
            "degraded": res.degraded,
            "year_range_covered": res.year_range_covered,
        }
        if res.degraded:
            ctx.degrade(f"step6:subq{i}:retrieval_degraded")
        out[i] = [_to_schema(p, i) for p in res.passages]
    return out


def number_passages(ctx: RequestContext, by_subq: dict[int, list[Passage]]) -> list[Passage]:
    from retrieval.config import params

    whole_cap = int(params().get("whole_question_cap", 60)) if ctx.plan.complex else int(params().get("unsplit_question_cap", 45))
    numbered: list[Passage] = []
    by_id: dict[str, Passage] = {}
    for i in sorted(by_subq):
        keep: list[Passage] = []
        for p in by_subq[i]:
            if p.id in by_id:
                keep.append(by_id[p.id])
                continue
            if len(numbered) >= whole_cap:
                continue
            p.number = len(numbered) + 1
            numbered.append(p)
            by_id[p.id] = p
            keep.append(p)
        by_subq[i] = keep
    return numbered


def _meta_summary(out: dict[str, Any]) -> dict[str, Any]:
    meta = dict(out.get("meta") or {})
    keep = {}
    for k in ("missing", "from_lyrics", "fallback", "fallbacks", "truncated", "reason", "notes"):
        if k in meta:
            keep[k] = meta[k]
    return keep


async def _run_hymn_targeted(ctx: RequestContext, deps: Any) -> dict[str, Any]:
    """诗歌：支持多首；系列逻辑码 → ES；儿童/不存在给原因。"""
    from hymn.catalog import SERIES_TO_ES
    from hymn.fetch import fetch_hymn_ref_list
    from hymn.parse import HymnRef, HymnRefList, SERIES_LABEL
    from retrieval.targeted import TargetedResult, OK, NOT_FOUND, NOT_SUPPORTED

    plan = ctx.plan
    loc = plan.locator
    raw_refs = list(plan.hymn_refs or [])
    if not raw_refs and loc and loc.hymn_number is not None:
        raw_refs = [
            {
                "series": loc.hymn_series or "big",
                "number": int(loc.hymn_number),
                "fallback": False,
                "exists": True,
                "explicit_series": bool(loc.hymn_series),
            }
        ]

    hrefs = HymnRefList()
    from_lyrics = False
    for r in raw_refs:
        series = str(r.get("series") or "big")
        if series in SERIES_TO_ES:
            pass
        else:
            from hymn.catalog import ES_TO_SERIES

            series = ES_TO_SERIES.get(series, series)
        hrefs.append(
            HymnRef(
                series=series,
                number=int(r.get("number") or 0),
                explicit_series=bool(r.get("explicit_series", True)),
                fallback=bool(r.get("fallback")),
                exists=bool(r.get("exists", True)),
            )
        )
        if r.get("from_lyrics"):
            from_lyrics = True

    packed = await fetch_hymn_ref_list(hrefs, deps.targeted)
    blocks: list[dict[str, Any]] = []
    notes: list[str] = []
    statuses: list[str] = []
    fallbacks: list[int] = []
    cfg = deps.cfg or {}

    if packed.get("truncated"):
        notes.append(str(cfg.get("hymn_truncated_message") or "识别到的首数较多，已按上限截断。"))

    for item in packed.get("items") or []:
        st = str(item.get("status") or NOT_FOUND)
        statuses.append(st)
        num = int(item.get("number") or 0)
        if item.get("fallback"):
            fallbacks.append(num)
            tpl = str(cfg.get("hymn_fallback_message_template") or "大本没有第{n}首，显示的是补充本第{n}首。")
            notes.append(tpl.format(n=num))
        if st in {"not_indexed", "not_found", "not_supported"}:
            reason = item.get("reason") or st
            notes.append(str(reason))
            continue
        result = item.get("result") or {}
        for b in result.get("blocks") or []:
            blocks.append(b)
        statuses.append(str(result.get("status") or OK))

    # 汇总 status
    if not blocks:
        status = NOT_FOUND
        if any(s == "not_indexed" for s in statuses):
            status = NOT_SUPPORTED
    elif any(s in {NOT_FOUND, "not_indexed", "not_supported"} for s in statuses) and blocks:
        from retrieval.targeted import INCOMPLETE

        status = INCOMPLETE
    else:
        status = OK

    missing = None
    if status in {NOT_FOUND, NOT_SUPPORTED} and not blocks:
        missing = "；".join(notes) if notes else "未找到诗歌"

    out = TargetedResult(
        status=status,
        blocks=blocks,
        kind="诗歌",
        meta={
            "notes": notes,
            "fallbacks": fallbacks,
            "fallback": bool(fallbacks),
            "from_lyrics": from_lyrics or (plan.source == "lyrics_rule"),
            "truncated": bool(packed.get("truncated")),
            "missing": missing,
            "n_refs": len(hrefs),
        },
    ).to_dict()
    return out


async def run_targeted(ctx: RequestContext, deps: Any) -> dict[str, Any]:
    plan = ctx.plan
    loc = plan.locator
    t = deps.targeted
    if plan.main_type == "生命读经":
        r = await t.life_study(loc.book_title, int(loc.message_number))
        out = r.to_dict()
    elif plan.main_type == "节期纲目":
        r = await t.feast(int(loc.feast_year), str(loc.feast_month), loc.message_number)
        out = r.to_dict()
    elif plan.main_type == "诗歌":
        out = await _run_hymn_targeted(ctx, deps)
    elif plan.main_type == "经文":
        from scripture.normalize import parse_refs

        r = await t.scripture(parse_refs(loc.scripture or "", bible=deps.bible, validate=deps.bible is not None))
        out = r.to_dict()
    else:  # 注解
        if loc and loc.scripture:
            from scripture.normalize import parse_refs

            refs = parse_refs(loc.scripture, bible=deps.bible, validate=deps.bible is not None)
            r = t.footnotes_for(refs[0])
        else:
            r = await t.notes_by_topic((loc.note_topic if loc else None) or ctx.question)
        out = r.to_dict()

    ctx.record(
        6,
        targeted_status=out.get("status"),
        targeted_blocks=len(out.get("blocks") or []),
        targeted_meta=_meta_summary(out),
        plan_source=getattr(plan, "source", None),
        lyrics_status=ctx.lyrics_status,
    )
    return out


def _infer_ref_kind(key: list[Any], explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    b, c, vs, ce, ve = (list(key) + [0, 0, 0, 0, 0])[:5]
    if int(c) == 0 and int(vs) == 0 and int(ce) == 0 and int(ve) == 0:
        return "whole_book"
    if int(vs) == 0 and int(ve) == 0 and int(ce) != int(c):
        return "chapter_range"
    if int(vs) == 0 and int(ve) == 0:
        return "whole_chapter"
    if int(c) != int(ce):
        return "cross_chapter"
    return "verse_range"


async def run_reverse(ctx: RequestContext, deps: Any) -> list[Passage]:
    from retrieval.targeted import book_verse_total, scripture_caps

    layer1 = ctx.layers[0].layer1 if ctx.layers else []
    term = layer1[0] if layer1 else ctx.question
    found = await deps.reverse.find(term)
    max_chapters, max_verses = scripture_caps()
    passages: list[Passage] = []
    for h in found["hits"]:
        b, c, vs, ce, ve = h["key"]
        kind = _infer_ref_kind(h["key"], h.get("kind"))
        rows: list = []
        meta: dict[str, Any] = {"sources": h["sources"], "flags": h.get("flags") or [], "kind": kind}
        book_title = ""
        text = ""
        if deps.bible is None:
            pass
        elif kind == "whole_book":
            n_ch = int(deps.bible.chapter_count(b))
            n_vs = book_verse_total(deps.bible, b)
            book_title = deps.bible.book_name(b) or ""
            text = f"{book_title}：共{n_ch}章，{n_vs}节"
            meta.update({"chapter_count": n_ch, "verse_count": n_vs, "unit": "book_overview"})
        elif kind == "chapter_range":
            c1, c2 = int(c), int(ce)
            if c2 >= c1 and deps.bible.chapter_exists(b, c1) and deps.bible.chapter_exists(b, c2):
                requested = c2 - c1 + 1
                returned = min(requested, max_chapters)
                meta.update({"requested_chapters": requested, "returned_chapters": returned})
                if returned < requested:
                    meta["truncated"] = True
                for ch in range(c1, c1 + returned):
                    rows.extend(deps.bible.get_chapter(b, ch))
        elif kind == "cross_chapter":
            rows = deps.bible.get_cross(b, c, vs, ce, ve)
            if len(rows) > max_verses:
                meta.update({"truncated": True, "requested_verses": len(rows), "returned_verses": max_verses})
                rows = rows[:max_verses]
        elif kind == "whole_chapter":
            rows = deps.bible.get_chapter(b, c)
        else:
            rows = deps.bible.get_range(b, c, vs, ve) if int(c) == int(ce) else deps.bible.get_cross(b, c, vs, ce, ve)
            if len(rows) > max_verses:
                meta.update({"truncated": True, "requested_verses": len(rows), "returned_verses": max_verses})
                rows = rows[:max_verses]
        if rows:
            book_title = rows[0].get("book_name") or book_title
            text = "".join(str(r.get("text_gb_plain") or "") for r in rows)
        passages.append(
            Passage(
                id=f"bible_data:{h['label']}",
                index="bible_data",
                book_title=book_title,
                message_title=h["label"],
                location={"ref": h["label"], "sources": h["sources"], "rank": h["rank"], "kind": kind},
                text=text,
                route="reverse",
                meta=meta,
                subq=0,
            )
        )
    ctx.record(6, reverse_counts=found["counts"], reverse_used_bible_vector=found["used_bible_vector"])
    return passages


async def run(ctx: RequestContext, deps: Any) -> None:
    plan = ctx.plan
    if plan.main_type == "反找经文":
        ps = await run_reverse(ctx, deps)
        ctx.passages_by_subq = {0: ps}
        ctx.passages = number_passages(ctx, ctx.passages_by_subq)
        return
    by_subq = await retrieve_subquestions(ctx, deps, specs_for(ctx, deps))
    ctx.passages_by_subq = by_subq
    ctx.passages = number_passages(ctx, by_subq)
    ctx.record(
        6,
        per_subq={str(i): len(v) for i, v in by_subq.items()},
        synthesis=[i for i, sq in enumerate(plan.subquestions) if sq.synthesis],
        total=len(ctx.passages),
    )
