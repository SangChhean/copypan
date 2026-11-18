# -*- coding: utf-8 -*-
"""第 4 步：第 1 层取词。

程序核对：
- 每个词必须逐字出现在（改写后）问题原文里，否则丢弃；
- 在 2,372 词条（括号词映射到外词）里的标为词条，不在的保留并标「非词条」；
- 限定词按角色：作为「限定」的不进第 1 层，作为「对象」保留；
- 个数：每个子问题 ≤3（比较类 ≤ layer1_per_subquestion_compare，默认 4【暂定】）；
  整题 ≤8 按去重后的不同词数计（共用词可进多个子问题，只计一次）；
- 词出现在哪个非综合子问题 text 里就分给哪个（共用词回填所有匹配子问题）；
- 比较类的 compare_objects 无论是否词条都必须保留在第 1 层，不被上限挤掉。
失败兜底：用词表做最长匹配，排除 generic_words。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from pipeline.context import RequestContext
from pipeline.schemas import Layers, Plan, SubQuestion


def _restricted_values(plan: Optional[Plan]) -> set[str]:
    if plan is None:
        return set()
    return {str(r.value) for r in plan.restrictions if r.role == "限定" and r.kind == "author"}


def entry_name(word: str, lookups: Any) -> Optional[str]:
    """词条名（括号内词映射到外词）；不是词条返回 None。"""
    if lookups is None:
        return None
    e = lookups.by_name.get(word)
    if not e:
        return None
    return e.get("same_as") or e.get("name")


def postprocess_words(words: list[Any], question: str, lookups: Any, plan: Optional[Plan]) -> tuple[list[str], dict[str, bool]]:
    restricted = _restricted_values(plan)
    out: list[str] = []
    is_entry: dict[str, bool] = {}
    for w in words:
        w = str(w or "").strip()
        if not w or w not in question:
            continue
        if w in restricted:
            continue
        name = entry_name(w, lookups)
        final = name or w
        if final in out:
            continue
        out.append(final)
        is_entry[final] = name is not None
    return out, is_entry


def fallback_longest_match(question: str, lookups: Any, generic: dict[str, Any]) -> list[str]:
    if lookups is None:
        return []
    names = [e["name"] for e in lookups.lexicon]
    by_len = sorted({n for n in names if n}, key=len, reverse=True)
    exclude = set(generic.get("generic") or [])
    rw = generic.get("restriction_words") or {}
    for k in ("author", "source"):
        exclude |= set(rw.get(k) or [])
    out: list[str] = []
    i = 0
    while i < len(question):
        hit = None
        for n in by_len:
            if question.startswith(n, i):
                hit = n
                break
        if hit is None:
            i += 1
            continue
        i += len(hit)
        if hit in exclude:
            continue
        if hit not in out:
            out.append(hit)
    return out


def _per_cap_for(sq: SubQuestion, ccfg: dict[str, Any]) -> int:
    if sq.qtype == "比较":
        return int(ccfg.get("layer1_per_subquestion_compare", 4))
    return int(ccfg.get("layer1_per_subquestion", 3))


def _force_compare_objects(
    per: list[list[str]],
    is_entry: dict[str, bool],
    plan: Plan,
    lookups: Any,
    *,
    ccfg: dict[str, Any],
    whole: int,
) -> None:
    """比较对象强制进第 1 层：非词条也保留；可挤掉同子问题末尾的非对象词。"""
    total = sum(len(p) for p in per)

    def _is_forced(j: int, w: str) -> bool:
        objs = plan.subquestions[j].compare_objects or []
        return w in objs or any(entry_name(o, lookups) == w for o in objs)

    for i, sq in enumerate(plan.subquestions):
        if sq.qtype != "比较" or not sq.compare_objects:
            continue
        cap = _per_cap_for(sq, ccfg)
        for obj in sq.compare_objects:
            obj = str(obj).strip()
            if not obj:
                continue
            name = entry_name(obj, lookups)
            final = name or obj
            is_entry[final] = name is not None
            if final in per[i]:
                continue
            # 本子问题满：挤掉非对象
            while len(per[i]) >= cap:
                dropped = False
                for k in range(len(per[i]) - 1, -1, -1):
                    if not _is_forced(i, per[i][k]):
                        per[i].pop(k)
                        total -= 1
                        dropped = True
                        break
                if not dropped:
                    break
            if final in per[i]:
                continue
            if total >= whole:
                freed = False
                for j in range(len(per)):
                    for k in range(len(per[j]) - 1, -1, -1):
                        if not _is_forced(j, per[j][k]):
                            per[j].pop(k)
                            total -= 1
                            freed = True
                            break
                    if freed:
                        break
                if not freed:
                    continue
            if len(per[i]) < cap or True:
                # 即使超 cap 也必须保留对象（比较类硬规则）
                if final not in per[i]:
                    per[i].append(final)
                    total += 1
                    # 若超 cap，再挤非对象
                    while len(per[i]) > cap:
                        dropped = False
                        for k in range(len(per[i]) - 1, -1, -1):
                            if not _is_forced(i, per[i][k]):
                                per[i].pop(k)
                                total -= 1
                                dropped = True
                                break
                        if not dropped:
                            break


def assign_to_subquestions(
    words: list[str],
    plan: Plan,
    *,
    caps_cfg: dict[str, Any],
    whole: int,
) -> list[list[str]]:
    """按子问题 text 回填：共用词进每一个包含它的非综合子问题。

    整题上限 ``whole`` 按去重后的不同词数计；每子问题仍受 ``_per_cap_for``。
    未出现在任何子问题 text 的词：仍落到第一个有空位的非综合子问题（与改前一致）。
    """
    n = max(1, len(plan.subquestions))
    per: list[list[str]] = [[] for _ in range(n)]
    unique: set[str] = set()
    for w in words:
        is_new = w not in unique
        if is_new and len(unique) >= whole:
            break
        placed = False
        for i, sq in enumerate(plan.subquestions):
            if sq.synthesis:
                continue
            cap = _per_cap_for(sq, caps_cfg)
            if w in sq.text and len(per[i]) < cap and w not in per[i]:
                per[i].append(w)
                placed = True
        if placed:
            if is_new:
                unique.add(w)
            continue
        # 未匹配任何 text（或匹配槽已满）：沿用「落到第一个有空位」的兜底
        for i, sq in enumerate(plan.subquestions):
            if sq.synthesis:
                continue
            cap = _per_cap_for(sq, caps_cfg)
            if len(per[i]) < cap and w not in per[i]:
                per[i].append(w)
                if is_new:
                    unique.add(w)
                break
    return per


async def run(ctx: RequestContext, deps: Any) -> list[Layers]:
    plan = ctx.plan
    from pipeline.caps import caps_cfg

    ccfg = caps_cfg()
    whole = int(ccfg.get("layer1_whole_question", 8))
    words: list[str] = []
    is_entry: dict[str, bool] = {}
    try:
        tpl = deps.prompts.get("step4")
        subq_text = "\n".join(f"子问题#{i}（{sq.qtype}）：{sq.text}" for i, sq in enumerate(plan.subquestions))
        prompt = tpl.render(question=ctx.question, subquestions=subq_text)
        data, res = await deps.llm.complete_json(
            "haiku", "", [{"role": "user", "content": prompt}], step="step4", max_tokens=int(deps.cfg.get("json_max_tokens", 2000))
        )
        ctx.note_llm("step4", res)
        # 单子问题 {"words":[...]}；多子问题 {"subquestions":[{"index":0,"words":[...]},...]}（扁平后仍走既有分配）
        raw_words = data.get("words") if isinstance(data, dict) else data
        if not isinstance(raw_words, list) and isinstance(data, dict):
            subs = data.get("subquestions")
            if isinstance(subs, list):
                flat: list[Any] = []
                for s in subs:
                    if isinstance(s, dict) and isinstance(s.get("words"), list):
                        flat.extend(s["words"])
                raw_words = flat
        if not isinstance(raw_words, list):
            raise ValueError("words not list")
        words, is_entry = postprocess_words(raw_words, ctx.question, deps.lookups, plan)
        ctx.record(4, model_words=len(raw_words), kept_words=len(words))
    except Exception as e:
        ctx.degrade(f"step4:{type(e).__name__}")
        words = fallback_longest_match(ctx.question, deps.lookups, deps.generic)
        words, is_entry = postprocess_words(words, ctx.question, deps.lookups, plan)
        ctx.record(4, fallback="longest_match", kept_words=len(words))

    per = assign_to_subquestions(words, plan, caps_cfg=ccfg, whole=whole)
    _force_compare_objects(per, is_entry, plan, deps.lookups, ccfg=ccfg, whole=whole)
    layers = [Layers(layer1=p, layer1_is_entry={w: is_entry.get(w, False) for w in p}) for p in per]

    def_types = {"定义", "比较"}
    if plan.main_type in def_types or any(sq.qtype in def_types for sq in plan.subquestions):
        from lookups.definitions import truncate_by_paragraph

        maxc = int(deps.cfg.get("definition_max_chars", 1500))
        for w in words:
            if is_entry.get(w):
                c = deps.definitions.content_3a(w) if deps.definitions else ""
                if c:
                    ctx.definitions[w] = truncate_by_paragraph(c, maxc)
    if plan.sensitive:
        entries = [w for w in words if is_entry.get(w)] or words
        ctx.devine = deps.devine.fetch(entries, int(deps.cfg.get("devine_max_items", 2)))
        if not deps.devine.available:
            ctx.record(4, devine_note=deps.devine.reason)
    ctx.record(4, layer1=[len(l.layer1) for l in layers], definitions=len(ctx.definitions), devine=len(ctx.devine))
    return layers


def layers_json(layers: list[Layers]) -> str:
    return json.dumps([l.model_dump() for l in layers], ensure_ascii=False)
