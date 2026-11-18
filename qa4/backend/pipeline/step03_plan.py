# -*- coding: utf-8 -*-
"""第 3 步：规则前置（可选）+ Haiku 输出 Plan；程序后处理。

- 子问题 ≤ max_subquestions；拿不准不拆（模型没给子问题就用原问题一条）。
- 年代限定：保留区间，检索层用年代表换书名清单（有重叠即命中）。
- 定位键（书名、特会、系列、经节）必须通过 lookups 或 scripture 规范化核对；不过 → 降级为一般问题并在 understanding 说明。
- 诗歌号码：规则与模型路径均用 HymnCatalog 核对（不再依赖 hymn_series.json）。
- 失败 → 一般问题、默认类、不拆。
"""

from __future__ import annotations

from typing import Any, Optional

from hymn.catalog import ES_TO_SERIES, SERIES_TO_ES, get_catalog
from pipeline.context import RequestContext
from pipeline.schemas import Locator, Plan, QType, SubQuestion, TARGETED_TYPES
from pipeline.step03_rules import apply_rule_plan


def fallback_plan(question: str, reason: str) -> Plan:
    return Plan(
        main_type=QType.默认.value,
        source="model",
        complex=False,
        subquestions=[SubQuestion(text=question, qtype=QType.默认.value)],
        understanding=f"未能完成理解（{reason}），按一般问题处理。",
        degraded=True,
    )


def _logical_hymn_series(raw: Optional[str]) -> str:
    s = (raw or "").strip() or "big"
    if s in SERIES_TO_ES:
        return s
    if s in ES_TO_SERIES:
        return ES_TO_SERIES[s]
    # 默认大本
    return "big"


def _locator_ok(plan: Plan, deps: Any) -> tuple[bool, str]:
    loc = plan.locator or Locator()
    t = plan.main_type
    if t == "诗歌":
        cat = get_catalog()
        try:
            cat.ensure_loaded()
        except Exception as e:
            return False, f"诗歌目录不可用（{type(e).__name__}）"
        # 多首：逐条核对
        refs = list(plan.hymn_refs or [])
        if not refs:
            if loc.hymn_number is None:
                return False, "缺少诗歌首数"
            refs = [{"series": loc.hymn_series, "number": loc.hymn_number, "exists": True}]
        for r in refs:
            series = _logical_hymn_series(str(r.get("series") if isinstance(r, dict) else loc.hymn_series))
            num = int(r.get("number") if isinstance(r, dict) else loc.hymn_number or 0)
            if series == "child":
                continue  # 取篇阶段给 not_found 文案
            exists = bool(r.get("exists", True)) if isinstance(r, dict) else True
            if not exists:
                continue
            if not cat.exists(series, num):
                # fallback 补充本可能已在 parse 阶段改 series
                return False, f"{SERIES_TO_ES.get(series, series)}没有第{num}首"
        return True, ""
    if t == "生命读经":
        titles = {b.get("book_title") for b in deps.life_books}
        if not loc.book_title or (titles and loc.book_title not in titles):
            return False, "生命读经书名核对不过"
        if loc.message_number is None:
            return False, "缺少篇号"
        return True, ""
    if t == "节期纲目":
        if loc.feast_year is None or not loc.feast_month:
            return False, "缺少特会年份或月份码"
        ok = any(
            int(f.get("year") or 0) == int(loc.feast_year)
            and str(f.get("month_code")).zfill(2) == str(loc.feast_month).zfill(2)
            for f in deps.feasts
        )
        return (ok, "" if ok else "特会表里没有该特会")
    if t in ("经文", "注解"):
        if t == "注解" and loc.note_topic and not loc.scripture:
            return True, ""
        if not loc.scripture:
            return False, "缺少经节"
        from scripture.normalize import parse_refs

        refs = parse_refs(loc.scripture, bible=deps.bible, validate=deps.bible is not None)
        return (bool(refs), "" if refs else "经节规范化核对不过")
    return True, ""


def postprocess(raw: dict[str, Any], question: str, deps: Any) -> Plan:
    plan = Plan.model_validate(raw)
    if not plan.source:
        plan.source = "model"
    maxn = int(deps.cfg.get("max_subquestions", 4))
    if not plan.subquestions:
        plan.subquestions = [SubQuestion(text=question, qtype=plan.main_type)]
        plan.complex = False
    plan.subquestions = plan.subquestions[:maxn]
    if len(plan.subquestions) <= 1:
        plan.complex = False
    for sq in plan.subquestions:
        sq.depends_on = [i for i in sq.depends_on if 0 <= i < len(plan.subquestions)]
    if plan.main_type in TARGETED_TYPES:
        ok, why = _locator_ok(plan, deps)
        if not ok:
            plan.main_type = QType.默认.value
            plan.locator = None
            plan.hymn_refs = []
            plan.complex = False
            plan.subquestions = [SubQuestion(text=question, qtype=QType.默认.value)]
            plan.understanding = (plan.understanding + "；" if plan.understanding else "") + f"定位核对不过（{why}），按一般问题处理。"
            plan.degraded = True
        else:
            plan.complex = False
            plan.subquestions = [SubQuestion(text=question, qtype=plan.main_type)]
            # 模型给的诗歌系列若为中文名，规范化为逻辑码
            if plan.main_type == "诗歌" and plan.locator:
                plan.locator.hymn_series = _logical_hymn_series(plan.locator.hymn_series)
    return plan


def format_feast_list_compact(feasts: list[dict[str, Any]] | None) -> str:
    """月份码→去年份后的名称去重 + 年份范围；不逐年罗列。"""
    import re

    if not feasts:
        return "（清单未加载）"
    by_mc: dict[str, set[str]] = {}
    years: list[int] = []
    for f in feasts:
        mc = str(f.get("month_code") or "").zfill(2)
        raw = str(f.get("name") or f.get("feast_name") or "").strip()
        base = re.sub(r"^\d{4}年", "", raw).strip() or raw
        if mc and base:
            by_mc.setdefault(mc, set()).add(base)
        try:
            years.append(int(f.get("year") or 0))
        except Exception:
            pass
    years = [y for y in years if y > 0]
    lines = ["月份码对照（名称已去掉年份前缀，同码可能有多种叫法）："]
    for mc in sorted(by_mc):
        lines.append(f"{mc}：" + " / ".join(sorted(by_mc[mc])))
    if years:
        lines.append(
            f"年份范围：{min(years)}–{max(years)}（某年可能缺某些特会，由程序核对，勿臆造未列出的场次）"
        )
    return "\n".join(lines)


def format_scope_options(deps: Any) -> str:
    """从 retrieval 配置取可检索索引名，供 scope 选用。"""
    try:
        from config import load_config_json

        cfg = load_config_json("retrieval.json")
        opts = list(cfg.get("default_scope") or [])
        if not opts:
            opts = sorted((cfg.get("indices") or {}).keys())
        return "、".join(str(x) for x in opts) if opts else "（未配置）"
    except Exception:
        return "（未配置）"


def _step3_render_vars(ctx: RequestContext, deps: Any) -> dict[str, Any]:
    import json

    life = "、".join(str(b.get("book_title") or "") for b in (deps.life_books or []) if b.get("book_title"))
    return {
        "question": ctx.question,
        "rule_hits": json.dumps(ctx.rule_hits or [], ensure_ascii=False),
        "life_book_titles": life or "（清单未加载）",
        "feast_list": format_feast_list_compact(list(deps.feasts or [])),
        "scope_options": format_scope_options(deps),
    }


_STEP3_CACHE_MARKER = "# 本问线索"


def split_step3_system_user(rendered: str, *, draft: bool) -> tuple[Any, str]:
    """草稿通道：固定段→system cacheable；可变段→user。stable 整段放 user。"""
    if draft and _STEP3_CACHE_MARKER in rendered:
        i = rendered.index(_STEP3_CACHE_MARKER)
        system = [{"type": "text", "text": rendered[:i].rstrip(), "cacheable": True}]
        user = rendered[i:].lstrip()
        return system, user
    return "", rendered


async def _run_llm(ctx: RequestContext, deps: Any) -> Plan:
    tpl = deps.prompts.get("step3")
    vals = _step3_render_vars(ctx, deps)
    # 兼容旧变量集：未声明的键忽略
    rendered = tpl.render(**{k: vals.get(k, "") for k in tpl.variables})
    system, user = split_step3_system_user(rendered, draft=bool(getattr(tpl, "draft", False)))
    try:
        data, res = await deps.llm.complete_json(
            "haiku",
            system,
            [{"role": "user", "content": user}],
            step="step3",
            max_tokens=int(deps.cfg.get("json_max_tokens", 2000)),
        )
        ctx.note_llm("step3", res)
        if not isinstance(data, dict):
            raise ValueError("plan not object")
        plan = postprocess(data, ctx.question, deps)
        plan.source = plan.source or "model"
        if plan.degraded:
            ctx.degrade("step3:locator")
    except Exception as e:
        ctx.degrade(f"step3:{type(e).__name__}")
        plan = fallback_plan(ctx.question, type(e).__name__)
    return plan


async def run(ctx: RequestContext, deps: Any) -> Plan:
    cfg = deps.cfg or {}
    enabled = bool(cfg.get("rule_preplan_enabled", True))

    if enabled:
        outcome = apply_rule_plan(ctx.question, ctx.question_orig, deps, bible=deps.bible)
        ctx.rule_hits = list(outcome.rule_hits)
        if outcome.lyrics_status:
            ctx.lyrics_status = outcome.lyrics_status
        if outcome.early_done:
            ctx.rule_early_done = True
            ctx.awaiting_choice = bool(outcome.awaiting_choice)
            ctx.answer.text = outcome.answer_text
            ctx.answer.awaiting_choice = bool(outcome.awaiting_choice)
            ctx.answer.lyrics_status = outcome.lyrics_status
            ctx.answer.choose_candidates = list(outcome.choose_candidates)
            ctx.answer.premise_note = (outcome.plan.understanding if outcome.plan else "") or ""
            plan = outcome.plan or Plan(
                main_type=QType.默认.value,
                source="lyrics_rule",
                subquestions=[SubQuestion(text=ctx.question_orig or ctx.question, qtype=QType.默认.value)],
            )
            ctx.record(
                3,
                main_type=plan.main_type,
                source=plan.source,
                skip_llm=True,
                early_done=True,
                lyrics_status=outcome.lyrics_status,
                rule_hits=ctx.rule_hits,
                complex=False,
                n_subquestions=len(plan.subquestions),
                degraded=plan.degraded,
            )
            return plan
        if outcome.skip_llm and outcome.plan is not None:
            plan = outcome.plan
            # 规则诗歌仍做 catalog 核对（儿童/不存在留给 step6 文案）
            if plan.main_type in TARGETED_TYPES and plan.main_type == "诗歌":
                ok, why = _locator_ok(plan, deps)
                if not ok and not any(not r.get("exists", True) or r.get("series") == "child" for r in (plan.hymn_refs or [])):
                    # 仅当「声称存在却核对不过」才降级
                    plan.main_type = QType.默认.value
                    plan.locator = None
                    plan.hymn_refs = []
                    plan.degraded = True
                    plan.understanding = (plan.understanding + "；" if plan.understanding else "") + f"定位核对不过（{why}）"
                    ctx.degrade("step3:locator")
            ctx.record(
                3,
                main_type=plan.main_type,
                source=plan.source,
                skip_llm=True,
                rule_hits=ctx.rule_hits,
                complex=plan.complex,
                n_subquestions=len(plan.subquestions),
                sensitive=plan.sensitive,
                degraded=plan.degraded,
                lyrics_status=ctx.lyrics_status,
            )
            return plan
        # 有 rule_hits 但未短路：继续模型
        ctx.record(3, rule_hits=ctx.rule_hits, rule_short_circuit=False)

    plan = await _run_llm(ctx, deps)
    ctx.record(
        3,
        main_type=plan.main_type,
        source=plan.source,
        skip_llm=False,
        complex=plan.complex,
        n_subquestions=len(plan.subquestions),
        sensitive=plan.sensitive,
        degraded=plan.degraded,
        rule_hits=ctx.rule_hits,
    )
    return plan
