# -*- coding: utf-8 -*-
"""第 5 步：第 2–5 层取词（Sonnet 一次处理全部子问题）。

固定前缀【暂定格式】：内在素质候选 + 按主干分组的其余词；cacheable。
程序核对：内在素质只认 133；启示/经历/实行只认 2239；不与第 1 层/各层重复；按 caps 截断。
比较类：为第 2–5 层词标 object_of；截断永不删某对象仅剩的最后一个词；
若某对象在第 1–5 层仍无词 → warning=compare_object_uncovered【暂定】。
全部不合格 → 只用第 1 层。
"""

from __future__ import annotations

from typing import Any

from pipeline.caps import LAYERS, caps_cfg, caps_for, truncate_complex, truncate_layers
from pipeline.context import RequestContext
from pipeline.schemas import Layers


def build_prefix(lookups: Any) -> list[dict[str, Any]]:
    zui = list(lookups.zui_neizai) if lookups else []
    other = set(lookups.other_2239) if lookups else set()
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for e in (lookups.lexicon if lookups else []):
        n = e.get("name")
        if n not in other:
            continue
        t = str(e.get("trunk") or "其他")
        if t not in groups:
            groups[t] = []
            order.append(t)
        groups[t].append(n)
    lines = ["内在素质候选：" + "、".join(zui), "其余候选（按主干分组，只列词名）："]
    lines += [f"·{t}：" + "、".join(groups[t]) for t in order]
    return [{"type": "text", "text": "\n".join(lines), "cacheable": True}]


def _resolve_object_of(raw_map: Any, words: list[str], objects: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(raw_map, dict):
        for w, o in raw_map.items():
            w, o = str(w).strip(), str(o).strip()
            if w in words and o in objects:
                out[w] = o
    # 启发式：未标注的词若恰好等于某对象名则绑定
    for w in words:
        if w in out:
            continue
        if w in objects:
            out[w] = w
    return out


def check_compare_coverage(layers: Layers, objects: list[str]) -> list[str]:
    """返回仍未被第 1–5 层覆盖的对象名。"""
    words = set(layers.all_words())
    pointed = set(layers.object_of.values())
    missing = []
    for o in objects:
        if o in words or o in pointed:
            continue
        missing.append(o)
    return missing


def postprocess(raw: Any, layers: list[Layers], plan: Any, lookups: Any) -> tuple[list[Layers], dict[str, Any]]:
    zui = set(lookups.zui_neizai) if lookups else set()
    other = set(lookups.other_2239) if lookups else set()
    subs = (raw or {}).get("subquestions") if isinstance(raw, dict) else None
    stats: dict[str, Any] = {"dropped_not_in_list": 0, "dropped_dup": 0, "uncovered_objects": {}}
    out = [l.model_copy(deep=True) for l in layers]
    by_index = {int(s.get("index", i)): s for i, s in enumerate(subs or []) if isinstance(s, dict)}
    object_ofs: list[dict[str, str]] = [{} for _ in plan.subquestions]
    protect: list[list[str]] = [[] for _ in plan.subquestions]

    for i, sq in enumerate(plan.subquestions):
        if sq.synthesis:
            continue
        s = by_index.get(i) or {}
        seen = set(out[i].layer1)
        for ln in LAYERS:
            allowed = zui if ln == "intrinsic" else other
            kept: list[str] = []
            for w in s.get(ln) or []:
                w = str(w or "").strip()
                if w not in allowed:
                    stats["dropped_not_in_list"] += 1
                    continue
                if w in seen:
                    stats["dropped_dup"] += 1
                    continue
                seen.add(w)
                kept.append(w)
            setattr(out[i], ln, kept)
        objs = list(sq.compare_objects or []) if sq.qtype == "比较" else []
        protect[i] = objs
        of = _resolve_object_of(s.get("object_of"), out[i].recommended(), objs)
        object_ofs[i] = of
        out[i].object_of = of

    ccfg = caps_cfg()
    caps_list = [caps_for(sq.qtype, ccfg) for sq in plan.subquestions]
    retrievable = [i for i, sq in enumerate(plan.subquestions) if not sq.synthesis]
    if plan.complex and len(retrievable) > 1:
        sub = truncate_complex(
            [out[i] for i in retrievable],
            [caps_list[i] for i in retrievable],
            total_cap=int(ccfg.get("complex_total_cap", 10)),
            min_per=int(ccfg.get("complex_min_per_subquestion", 1)),
            object_ofs=[object_ofs[i] for i in retrievable],
            protect_objects_list=[protect[i] for i in retrievable],
        )
        for i, l in zip(retrievable, sub):
            out[i] = l
    else:
        for i in retrievable:
            out[i] = truncate_layers(
                out[i], caps_list[i], object_of=object_ofs[i], protect_objects=protect[i]
            )

    for i, sq in enumerate(plan.subquestions):
        if sq.qtype != "比较" or not sq.compare_objects:
            continue
        missing = check_compare_coverage(out[i], list(sq.compare_objects))
        if missing:
            stats["uncovered_objects"][str(i)] = missing

    stats["totals"] = [l.total_2_5() for l in out]
    return out, stats


async def run(ctx: RequestContext, deps: Any) -> list[Layers]:
    plan = ctx.plan
    tpl = deps.prompts.get("step5")
    subq_text = "\n".join(
        f"子问题#{i}（{sq.qtype}）：{sq.text}"
        + (f"；比较对象：{'、'.join(sq.compare_objects)}" if sq.compare_objects else "")
        for i, sq in enumerate(plan.subquestions)
        if not sq.synthesis
    )
    layer1 = "；".join(f"#{i}:" + "、".join(l.layer1) for i, l in enumerate(ctx.layers))
    import json

    from pipeline.caps import caps_for

    caps_payload = {
        str(i): caps_for(sq.qtype)
        for i, sq in enumerate(plan.subquestions)
        if not sq.synthesis
    }
    render_vals = {
        "question": ctx.question,
        "subquestions": subq_text,
        "layer1": layer1,
        "caps": json.dumps(caps_payload, ensure_ascii=False),
    }
    prompt = tpl.render(**{k: render_vals.get(k, "") for k in tpl.variables})
    system = build_prefix(deps.lookups)
    try:
        data, res = await deps.llm.complete_json(
            "sonnet", system, [{"role": "user", "content": prompt}], step="step5", max_tokens=int(deps.cfg.get("json_max_tokens", 2000))
        )
        ctx.note_llm("step5", res)
        layers, stats = postprocess(data, ctx.layers, plan, deps.lookups)
        if sum(l.total_2_5() for l in layers) == 0:
            ctx.record(5, note="全部不合格，只用第 1 层")
        uncovered = stats.get("uncovered_objects") or {}
        if uncovered:
            ctx.warn("compare_object_uncovered")
            ctx.record(5, compare_object_uncovered=uncovered)
        ctx.record(5, **{k: v for k, v in stats.items() if k != "uncovered_objects"})
        return layers
    except Exception as e:
        ctx.degrade(f"step5:{type(e).__name__}")
        ctx.record(5, fallback="只用第 1 层")
        return ctx.layers
