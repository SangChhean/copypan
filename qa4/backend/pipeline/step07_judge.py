# -*- coding: utf-8 -*-
"""第 7 步：材料把关（Haiku 逐子问题）。

- 不够 → 放宽重试一次（检索放宽模式）后重判；仍不够 → 「没有找到」结论。
- 取具体对象不走模型，只看是否取到。
- 核实说法：有原话即放行；只有近似则放行并标注；两者都没有才算不够。
- 比较：缺一边算部分够。
- 综合类子问题：看其依赖的子问题是否都至少有材料。
- 调用失败默认放行并记录。
"""

from __future__ import annotations

from typing import Any

from pipeline.context import RequestContext
from pipeline.schemas import Passage, Verdict

OK_SET = {"够", "部分够", "不够"}


def format_passages(passages: list[Passage], max_chars: int) -> str:
    return "\n".join(f"[{p.number}]〔{p.book_title} {p.message_title}〕\n{(p.text or '')[:max_chars]}" for p in passages)


def apply_rules(qtype: str, data: dict[str, Any], passages: list[Passage]) -> Verdict:
    keep_nums = {int(n) for n in (data.get("keep") or []) if str(n).isdigit() or isinstance(n, int)}
    drop_nums = {int(n) for n in (data.get("drop") or []) if str(n).isdigit() or isinstance(n, int)}
    keep = {p.number: (p.number in keep_nums) if keep_nums else (p.number not in drop_nums) for p in passages}
    overall = str(data.get("overall") or "够")
    if overall not in OK_SET:
        overall = "够"
    note = ""
    if qtype == "核实说法":
        if data.get("has_original"):
            overall = "够"
        elif data.get("has_approx"):
            overall = "够"
            note = "只找到近似说法"
    if qtype == "比较" and data.get("sides_missing"):
        overall = "部分够"
        note = "比较的一方缺材料"
    if not passages:
        overall = "不够"
    return Verdict(subq=0, keep=keep, overall=overall, note=note)


async def judge_one(ctx: RequestContext, deps: Any, i: int, passages: list[Passage]) -> Verdict:
    sq = ctx.plan.subquestions[i]
    if not passages:
        return Verdict(subq=i, overall="不够")
    tpl = deps.prompts.get("step7")
    pchars = int(deps.cfg.get("step7_passage_chars", 600))
    vals = {
        "subquestion": sq.text,
        "qtype": sq.qtype,
        "passages": format_passages(passages, pchars),
        "passage_chars": str(pchars),
    }
    prompt = tpl.render(**{k: vals.get(k, "") for k in tpl.variables})
    try:
        data, res = await deps.llm.complete_json("haiku", "", [{"role": "user", "content": prompt}], step="step7", max_tokens=int(deps.cfg.get("json_max_tokens", 2000)))
        ctx.note_llm(f"step7.{i}", res)
        if not isinstance(data, dict):
            raise ValueError("verdict not object")
        v = apply_rules(sq.qtype, data, passages)
        v.subq = i
        return v
    except Exception as e:
        ctx.degrade(f"step7:{type(e).__name__}")
        return Verdict(subq=i, keep={p.number: True for p in passages}, overall="够", defaulted=True, note="把关调用失败，默认放行")


async def run(ctx: RequestContext, deps: Any) -> list[Verdict]:
    plan = ctx.plan
    from pipeline import step06_retrieve as s6

    verdicts: dict[int, Verdict] = {}
    normal = [i for i, sq in enumerate(plan.subquestions) if not sq.synthesis]
    for i in normal:
        verdicts[i] = await judge_one(ctx, deps, i, ctx.passages_by_subq.get(i, []))

    # 反找经文 / 核实说法不放宽重试；取具体对象不走本步（编排器跳过）
    no_retry_types = {"反找经文", "核实说法"}
    need_retry = [
        i
        for i in normal
        if verdicts[i].overall == "不够" and plan.subquestions[i].qtype not in no_retry_types and plan.main_type not in no_retry_types
    ]
    if need_retry:
        ctx.retried = True
        specs = s6.specs_for(ctx, deps, relaxed=True, only=set(need_retry))
        more = await s6.retrieve_subquestions(ctx, deps, specs)
        next_n = max([p.number for p in ctx.passages] or [0]) + 1
        known = {p.id: p for p in ctx.passages}
        for i, ps in more.items():
            merged = list(ctx.passages_by_subq.get(i, []))
            ids = {p.id for p in merged}
            for p in ps:
                if p.id in ids:
                    continue
                if p.id in known:
                    merged.append(known[p.id])
                else:
                    p.number = next_n
                    next_n += 1
                    known[p.id] = p
                    ctx.passages.append(p)
                    merged.append(p)
                ids.add(p.id)
            ctx.passages_by_subq[i] = merged
            v = await judge_one(ctx, deps, i, merged)
            v.retried = True
            verdicts[i] = v

    for i, sq in enumerate(plan.subquestions):
        if not sq.synthesis:
            continue
        deps_ok = all(any(verdicts.get(d, Verdict(subq=d)).keep.values()) for d in sq.depends_on) if sq.depends_on else bool(ctx.passages)
        verdicts[i] = Verdict(subq=i, overall="够" if deps_ok else "不够", note="综合类：看依赖子问题")

    # 比较类对象未覆盖：够 → 最多降为部分够【暂定】
    if "compare_object_uncovered" in ctx.warnings:
        for i, sq in enumerate(plan.subquestions):
            if sq.qtype != "比较":
                continue
            v = verdicts.get(i)
            if v and v.overall == "够":
                v.overall = "部分够"
                v.note = (v.note + "；" if v.note else "") + "compare_object_uncovered"

    ordered = [verdicts[i] for i in sorted(verdicts)]
    if normal and all(verdicts[i].overall == "不够" for i in normal):
        ctx.not_found = True
    ctx.record(
        7,
        verdicts=[
            {
                "subq": v.subq,
                "overall": v.overall,
                "retried": v.retried,
                "defaulted": v.defaulted,
                "kept": sum(1 for x in v.keep.values() if x),
            }
            for v in ordered
        ],
        retried=ctx.retried,
    )
    return ordered


def kept_passages(ctx: RequestContext) -> list[Passage]:
    keep: dict[int, bool] = {}
    for v in ctx.verdicts:
        for n, k in v.keep.items():
            keep[n] = keep.get(n, False) or bool(k)
    return [p for p in ctx.passages if keep.get(p.number, False)]
