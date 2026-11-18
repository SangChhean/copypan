# -*- coding: utf-8 -*-
"""流水线规则前置探针：直接调用 apply_rule_plan（无 LLM / 无 HTTP）。"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
_QA4 = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\pipeline_rules")
DEFAULT_NOTES = _QA4 / "notes" / "pipeline_rules_probe_summary.md"
DEFAULT_SEED = 20261117
DEFAULT_N = 300
DEFAULT_SCRIPTURE = _QA4 / "notes" / "scripture_format_cases_v2.csv"
DEFAULT_HYMN = _QA4 / "notes" / "hymn_format_cases_v2.csv"
DEFAULT_HOLDOUT_S = Path(r"G:\PanAI4.0专用\holdout\scripture_format_holdout.csv")
DEFAULT_HOLDOUT_H = Path(r"G:\PanAI4.0专用\holdout\hymn_format_holdout.csv")


def _deps():
    from config import load_config_json

    class D:
        pass

    d = D()
    d.cfg = load_config_json("pipeline.json")
    d.bible = None
    try:
        from scripture.bible_text import BibleText
        from config.settings import get_settings

        s = get_settings(require_runtime=False)
        if getattr(s, "bible_dir", None) and Path(s.bible_dir).is_dir():
            d.bible = BibleText(s.bible_dir)
    except Exception:
        pass
    return d


def _std_to_full():
    from tools.probe_scripture_formats import build_std_to_full

    return build_std_to_full()


def _scripture_actual(text: str, bible, std_to_full) -> str:
    from tools.probe_scripture_formats import format_ref_expected_style
    from scripture.normalize import parse_refs

    refs = parse_refs(text, bible=bible, validate=bible is not None)
    if not refs:
        return "无出处"
    return " ; ".join(format_ref_expected_style(r, std_to_full) for r in refs)


def _hymn_actual(text: str) -> str:
    from hymn.parse import format_hymn_refs, parse_hymn_refs

    return format_hymn_refs(parse_hymn_refs(text))


def _group_reason(text: str, kind: str, deps, *, has_refs: bool) -> tuple[str, str]:
    """返回 (组别, 原因)。"""
    from pipeline.step03_rules import (
        is_pure_citation,
        _scripture_fragments,
        _hymn_fragments,
        _strip_fragments,
        _strip_hymn_structural,
        _strip_scripture_structural,
        _clean_residual,
        _has_block_keyword,
    )
    from scripture.normalize import parse_refs
    from hymn.parse import parse_hymn_refs

    cfg = deps.cfg
    req = list(cfg.get("rule_request_words") or [])
    block = list(cfg.get("rule_block_keywords") or [])
    rmax = int(cfg.get("rule_pure_residual_max", 4))

    if kind == "scripture":
        refs = parse_refs(text, bible=deps.bible, validate=deps.bible is not None)
        if not refs:
            return "不识别", "无解析"
        frags = _scripture_fragments(text, refs)
        residual = _clean_residual(_strip_scripture_structural(_strip_fragments(text, frags, req)))
        if _has_block_keyword(text, block):
            hit = next((k for k in block if k in text), "")
            return "带实质问题", f"实质关键词={hit};剩余字数={len(residual)}"
        if is_pure_citation(text, frags, request_words=req, block_keywords=block, residual_max=rmax, kind="scripture"):
            return "纯出处", f"剩余字数={len(residual)}"
        return "带实质问题", f"剩余字数={len(residual)}"

    refs = parse_hymn_refs(text)
    if not refs:
        return "不识别", "无解析"
    frags = _hymn_fragments(text, refs)
    residual = _clean_residual(_strip_hymn_structural(_strip_fragments(text, frags, req)))
    if _has_block_keyword(text, block):
        hit = next((k for k in block if k in text), "")
        return "带实质问题", f"实质关键词={hit};剩余字数={len(residual)}"
    if is_pure_citation(text, frags, request_words=req, block_keywords=block, residual_max=rmax, kind="hymn"):
        return "纯出处", f"剩余字数={len(residual)}"
    return "带实质问题", f"剩余字数={len(residual)}"


def _plan_scripture_label(plan, std_to_full, bible) -> str:
    from tools.probe_scripture_formats import format_ref_expected_style
    from scripture.normalize import parse_refs

    s = (plan.locator.scripture if plan and plan.locator else "") or ""
    refs = parse_refs(s, bible=bible, validate=False)
    if not refs:
        return ""
    return " ; ".join(format_ref_expected_style(r, std_to_full) for r in refs)


def _plan_hymn_label(plan) -> str:
    from hymn.parse import HymnRef, HymnRefList, format_hymn_refs

    if not plan:
        return ""
    truncated = "截断" in (plan.understanding or "")
    items: list[HymnRef] = []
    for r in plan.hymn_refs or []:
        items.append(
            HymnRef(
                series=str(r.get("series") or "big"),
                number=int(r.get("number") or 0),
                explicit_series=bool(r.get("explicit_series", True)),
                fallback=bool(r.get("fallback")),
                exists=bool(r.get("exists", True)),
            )
        )
    if not items and plan.locator and plan.locator.hymn_number is not None:
        items.append(
            HymnRef(
                series=str(plan.locator.hymn_series or "big"),
                number=int(plan.locator.hymn_number),
                explicit_series=True,
                fallback=False,
                exists=True,
            )
        )
    refs = HymnRefList(items, truncated=truncated)
    return format_hymn_refs(refs) if refs else ""


def eval_format_cases(
    rows: list[dict[str, str]],
    kind: str,
    deps,
    std_to_full,
    fails: list[dict],
    *,
    source_tag: str,
) -> dict[str, Any]:
    from pipeline.step03_rules import apply_rule_plan

    stats = {
        "纯出处": {"n": 0, "pass": 0},
        "带实质问题": {"n": 0, "pass": 0},
        "不识别": {"n": 0, "pass": 0},
    }
    split_rows: list[dict[str, Any]] = []

    for row in rows:
        cid = row.get("id") or ""
        inp = (row.get("input") or "").strip()
        expected = (row.get("expected") or "").strip()
        group, reason = _group_reason(inp, kind, deps, has_refs=False)
        stats[group]["n"] += 1
        o = apply_rule_plan(inp, inp, deps, bible=deps.bible)
        ok = True
        detail = ""

        if group == "纯出处":
            if not (o.skip_llm and o.plan and o.plan.source == f"{kind}_rule"):
                ok = False
                detail = f"未短路 source={getattr(o.plan,'source',None)}"
            else:
                if kind == "scripture":
                    probe_act = _scripture_actual(inp, deps.bible, std_to_full)
                    plan_act = _plan_scripture_label(o.plan, std_to_full, deps.bible)
                    if probe_act != expected:
                        ok = False
                        detail = f"探针不一致 actual={probe_act!r} exp={expected!r}"
                    elif plan_act and plan_act != expected:
                        ok = False
                        detail = f"Plan标签不符 got={plan_act!r} exp={expected!r}"
                else:
                    probe_act = _hymn_actual(inp)
                    plan_act = _plan_hymn_label(o.plan)
                    if probe_act != expected:
                        ok = False
                        detail = f"探针不一致 actual={probe_act!r} exp={expected!r}"
                    elif plan_act != expected:
                        ok = False
                        detail = f"Plan标签不符 got={plan_act!r} exp={expected!r}"
        elif group == "带实质问题":
            if o.skip_llm and o.plan and o.plan.source in {"scripture_rule", "hymn_rule", "lyrics_rule"}:
                # 歌词抢占 found 在实质句上可能合法；格式集不应 lyrics
                if o.plan.source != "lyrics_rule":
                    ok = False
                    detail = f"误短路 source={o.plan.source}"
            if kind == "scripture" and expected not in ("无出处",) and not any(
                h.get("kind") == "scripture" for h in o.rule_hits
            ):
                ok = False
                detail = "应识别但无 rule_hits"
            if kind == "hymn" and expected not in ("无首数",) and not expected.startswith("无此首"):
                if not any(h.get("kind") == "hymn" for h in o.rule_hits) and not (
                    o.plan and o.plan.source == "lyrics_rule"
                ):
                    # 诗15 等被经文截获：允许 scripture hits
                    if not any(h.get("kind") == "scripture" for h in o.rule_hits):
                        ok = False
                        detail = "应识别但无 rule_hits"
        else:  # 不识别（本域无解析）：仅当「本域」规则短路才算误短路；跨域命中属正常
            if o.skip_llm and o.plan and o.plan.source == f"{kind}_rule":
                ok = False
                detail = f"负例误短路 source={o.plan.source}"

        if ok:
            stats[group]["pass"] += 1
        else:
            fails.append(
                {
                    "source": source_tag,
                    "id": cid,
                    "kind": kind,
                    "group": group,
                    "reason": reason,
                    "detail": detail,
                    "input": inp,
                    "expected": expected,
                    "plan_source": getattr(o.plan, "source", None) if o.plan else None,
                }
            )

        split_rows.append(
            {
                "id": cid,
                "input": inp,
                "group": group,
                "reason": reason,
                "expected": expected,
                "pass": ok,
            }
        )

    return {"stats": stats, "split_rows": split_rows}


def _lyrics_cases(n: int, seed: int, deps):
    """复用 probe_hymn_lyrics 造例；挂真实索引。T9 与词条名冲突的排除。"""
    from tools.probe_hymn_lyrics import build_cases
    from hymn.lyrics import reset_lyrics_index
    from pipeline.step03_rules import _norm_name, lexicon_norm_names

    reset_lyrics_index()
    cases, idx = build_cases(n, seed)
    deps.lyrics_index = idx
    lex = lexicon_norm_names(deps, deps.cfg if hasattr(deps, "cfg") else None)
    keep = {"T1", "T4", "T5", "T7", "T8", "T9", "T10a", "T10b"}
    out = []
    t9_excluded = 0
    for c in cases:
        if c["kind"] not in keep:
            continue
        if c["kind"] == "T9":
            qn = _norm_name(c["query"])
            if qn in lex:
                t9_excluded += 1
                continue
        out.append(c)
    setattr(idx, "_probe_t9_lexicon_excluded", t9_excluded)
    return out, idx


def eval_lyrics(cases: list[dict], deps, fails: list) -> dict[str, Any]:
    from pipeline.step03_rules import apply_rule_plan

    by = defaultdict(lambda: {"n": 0, "pass": 0})
    for case in cases:
        kind = case["kind"]
        q = case["query"]
        exp = case.get("expect") or {}
        by[kind]["n"] += 1
        o = apply_rule_plan(q, q, deps, bible=deps.bible)
        ok = True
        detail = ""
        if kind in {"T1", "T4", "T5", "T7", "T9"}:
            series, num = exp.get("must_include") or (None, None)
            if o.early_done and o.awaiting_choice:
                cands = {(c.get("series"), int(c.get("hymn_number") or 0)) for c in o.choose_candidates}
                if (series, int(num)) not in cands:
                    ok = False
                    detail = "choose 未含来源首"
            elif o.skip_llm and o.plan and o.plan.source == "lyrics_rule" and o.plan.main_type == "诗歌":
                if o.plan.locator and (
                    o.plan.locator.hymn_series != series or int(o.plan.locator.hymn_number) != int(num)
                ):
                    # 多首共享句：允许 choose；单首必须匹配
                    ok = False
                    detail = f"首数不符 {o.plan.locator.hymn_series}/{o.plan.locator.hymn_number}"
            else:
                ok = False
                detail = f"未走歌词路径 source={getattr(o.plan,'source',None)} early={o.early_done}"
        elif kind == "T8":
            if not (o.lyrics_status == "too_short" and o.early_done and o.skip_llm):
                ok = False
                detail = f"status={o.lyrics_status}"
        elif kind in {"T10a", "T10b"}:
            # 验收：source 不得是 lyrics_rule（过短守卫用 lyrics_too_short，不算命中）
            if o.plan and o.plan.source == "lyrics_rule":
                ok = False
                detail = "误触发 lyrics_rule"
        if ok:
            by[kind]["pass"] += 1
        else:
            fails.append(
                {
                    "kind": kind,
                    "detail": detail,
                    "query": q,
                    "plan_source": getattr(o.plan, "source", None) if o.plan else None,
                    "lyrics_status": o.lyrics_status,
                    "meta": case.get("meta") or {},
                }
            )
    return {k: {**v, "rate": round(v["pass"] / v["n"], 4) if v["n"] else 0} for k, v in sorted(by.items())}


def write_split_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "input", "group", "reason", "expected", "pass"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-notes", action="store_true")
    ap.add_argument("--scripture-cases", type=Path, default=DEFAULT_SCRIPTURE)
    ap.add_argument("--hymn-cases", type=Path, default=DEFAULT_HYMN)
    ap.add_argument("--holdout-scripture", type=Path, default=DEFAULT_HOLDOUT_S)
    ap.add_argument("--holdout-hymn", type=Path, default=DEFAULT_HOLDOUT_H)
    ap.add_argument("--export-split", action="store_true", help="写出 wiring/rule_split_*.csv")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    deps = _deps()
    std_to_full = _std_to_full()
    fails: list[dict[str, Any]] = []

    def load(p: Path) -> list[dict[str, str]]:
        if not p.is_file():
            print(f"WARN missing {p}")
            return []
        with p.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    print("eval scripture/hymn format + holdout ...")
    s_main = eval_format_cases(load(args.scripture_cases), "scripture", deps, std_to_full, fails, source_tag="scripture_v2")
    h_main = eval_format_cases(load(args.hymn_cases), "hymn", deps, std_to_full, fails, source_tag="hymn_v2")
    s_hold = eval_format_cases(load(args.holdout_scripture), "scripture", deps, std_to_full, fails, source_tag="scripture_holdout")
    h_hold = eval_format_cases(load(args.holdout_hymn), "hymn", deps, std_to_full, fails, source_tag="hymn_holdout")

    if args.export_split:
        wiring = Path(r"G:\PanAI4.0专用\logs\wiring")
        write_split_csv(wiring / "rule_split_scripture.csv", s_main["split_rows"])
        write_split_csv(wiring / "rule_split_hymn.csv", h_main["split_rows"])
        print(f"SPLIT scripture={wiring / 'rule_split_scripture.csv'}")
        print(f"SPLIT hymn={wiring / 'rule_split_hymn.csv'}")

    print(f"build lyrics cases seed={args.seed} n={args.n} ...")
    t0 = time.perf_counter()
    ly_cases, _idx = _lyrics_cases(args.n, args.seed, deps)
    t9_excl = int(getattr(_idx, "_probe_t9_lexicon_excluded", 0) or 0)
    print(f"lyrics_cases={len(ly_cases)} t9_lexicon_excluded={t9_excl} built_in={time.perf_counter()-t0:.1f}s")
    ly_stats = eval_lyrics(ly_cases, deps, fails)

    summary = {
        "seed": args.seed,
        "n": args.n,
        "scripture_v2": s_main["stats"],
        "hymn_v2": h_main["stats"],
        "scripture_holdout": s_hold["stats"],
        "hymn_holdout": h_hold["stats"],
        "lyrics": ly_stats,
        "t9_lexicon_excluded": t9_excl,
        "n_fail": len(fails),
    }
    (args.out / f"pipeline_rules_summary_{args.seed}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out / f"pipeline_rules_fails_{args.seed}.json").write_text(
        json.dumps({"fails": fails[:800]}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if not args.no_notes:
        lines = [
            f"# 流水线规则探针汇总 seed={args.seed} n={args.n}",
            "",
            "## 格式集",
        ]
        for name in ("scripture_v2", "hymn_v2", "scripture_holdout", "hymn_holdout"):
            st = summary[name]
            lines.append(f"### {name}")
            for g, v in st.items():
                rate = round(v["pass"] / v["n"], 4) if v["n"] else 0
                lines.append(f"- {g}: n={v['n']} pass={v['pass']} rate={rate}")
        lines.append("")
        lines.append("## 歌词")
        lines.append(f"- T9 词条名冲突排除: {t9_excl}")
        for k, v in ly_stats.items():
            lines.append(f"- {k}: n={v['n']} pass={v['pass']} rate={v['rate']}")
        lines.append("")
        lines.append("失败明细仅 logs/pipeline_rules/。")
        notes = DEFAULT_NOTES.with_name(f"pipeline_rules_probe_summary_{args.seed}.md")
        notes.write_text("\n".join(lines) + "\n", encoding="utf-8")
        DEFAULT_NOTES.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"NOTES={notes}")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT={args.out} n_fail={len(fails)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
