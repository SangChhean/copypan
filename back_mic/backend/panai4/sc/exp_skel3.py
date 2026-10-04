# -*- coding: utf-8 -*-
"""龙骨一步实验 B3：只换人称代词；指示词原样；承接句并入上一句。

用法（在 back_mic/backend）:
    python -m panai4.sc.exp_skel3          # dry-run（FAKE_LLM）
    python -m panai4.sc.exp_skel3 --run    # 真实 API
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parents[1]
_OUT_DIR = _REPO / "docs" / "panai4_sc" / "exp_skel"
_LOG = _REPO / "logs" / "sc_exp_skel3.log"
_B3_PATH = Path(__file__).resolve().parent / "prompts" / "skeleton_B3.txt"

_TOPIC_CH1 = "认识并经历亚伯拉罕的神、以撒的神和雅各的神，而成为神的以色列"
_MAX_TOKENS = 8192
_REPEATS = 2
_COVER_RATIO = 0.6
_MERGE_GAP = 2

# 第①类：仅人称代词（长词优先）
_WHITELIST = [
    "他们",
    "祂们",
    "她们",
    "它们",
    "他",
    "祂",
    "她",
    "它",
]

# 指示词：被删/被换时标「指示词被改」
_DEMONSTRATIVES = [
    "这享受",
    "这变化",
    "这班",
    "这样的",
    "这样",
    "这些",
    "那些",
    "这个",
    "那个",
    "此",
    "这",
    "那",
]

_lines: list[str] = []


def log(msg: str = "") -> None:
    _lines.append(msg)
    try:
        print(msg)
    except Exception:
        try:
            sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
        except Exception:
            pass


def flush_log() -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    _LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")


def _sha1_file(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _burden_of_run(run: dict) -> str:
    from panai4.sc.export_sc import extract_burden_export

    body, _ = extract_burden_export(run.get("ref_result") or "")
    return body


def parse_numbered_items(text: str) -> list[str]:
    items: list[str] = []
    for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = re.match(r"^\s*(\d+)\.\s*(.*)$", line)
        if not m:
            continue
        body = m.group(2).strip()
        if body:
            items.append(body)
    return items


def split_sentences(burden: str) -> list[tuple[int, int, str]]:
    raw = burden or ""
    spans: list[tuple[int, int, str]] = []
    start = 0
    for i, ch in enumerate(raw):
        if ch in "。；;":
            end = i + 1
            piece = raw[start:end]
            if piece.strip():
                stripped = piece.strip()
                off = piece.find(stripped)
                spans.append((start + off, start + off + len(stripped), stripped))
            start = end
    if start < len(raw) and raw[start:].strip():
        piece = raw[start:]
        stripped = piece.strip()
        off = piece.find(stripped)
        spans.append((start + off, start + off + len(stripped), stripped))
    return spans


def is_whitelist_only(fragment: str) -> bool:
    s = (fragment or "").strip()
    if not s:
        return True
    i = 0
    while i < len(s):
        matched = False
        for w in _WHITELIST:
            if s.startswith(w, i):
                i += len(w)
                matched = True
                break
        if not matched:
            return False
    return True


def involves_demonstrative_change(orig: str, new: str) -> bool:
    """原文侧含指示词，且该指示词在改后减少/消失 → 指示词被改。"""
    for d in _DEMONSTRATIVES:
        if d in (orig or "") and (orig or "").count(d) > (new or "").count(d):
            return True
    return False


def find_cover_span(burden: str, item: str) -> tuple[int, int] | None:
    if not burden or not item:
        return None
    best: tuple[tuple, int, int] | None = None
    min_w = max(1, len(item) - 40)
    max_w = min(len(burden), len(item) + 24)
    for wlen in range(min_w, max_w + 1):
        for i in range(0, len(burden) - wlen + 1):
            window = burden[i : i + wlen]
            sm = SequenceMatcher(None, window, item, autojunk=False)
            eq = sum(n for _a, _b, n in sm.get_matching_blocks())
            if eq == 0:
                continue
            r = sm.ratio()
            score = (r, eq, -abs(wlen - len(item)), wlen)
            if best is None or score > best[0]:
                best = (score, i, i + wlen)
    if best is None:
        return None
    s0, s1 = best[1], best[2]
    # 向左吞回紧邻人称代词（条目常已换成名称）
    while s0 > 0:
        extended = False
        for w in _WHITELIST:
            if s0 >= len(w) and burden[s0 - len(w) : s0] == w:
                s0 -= len(w)
                extended = True
                break
        if not extended:
            break
    # 向左吞回紧邻指示词：若条目未保留它们，比对才能露出「指示词被改」
    while s0 > 0:
        extended = False
        for d in _DEMONSTRATIVES:
            if s0 >= len(d) and burden[s0 - len(d) : s0] == d:
                s0 -= len(d)
                extended = True
                break
        if not extended:
            break
    return s0, s1


def merge_opcodes(
    opcodes: list[tuple[str, int, int, int, int]],
) -> list[tuple[str, int, int, int, int]]:
    """将间隔不超过 _MERGE_GAP 的 replace/insert/delete 合并为一次 replace。"""
    non_eq = [op for op in opcodes if op[0] != "equal"]
    if not non_eq:
        return []
    merged: list[tuple[str, int, int, int, int]] = []
    cur_tag, i1, i2, j1, j2 = non_eq[0]
    for tag, a1, a2, b1, b2 in non_eq[1:]:
        gap_a = a1 - i2
        gap_b = b1 - j2
        if 0 <= gap_a <= _MERGE_GAP and 0 <= gap_b <= _MERGE_GAP:
            # 吞掉中间短 equal，整段视为一次替换
            i2, j2 = a2, b2
            cur_tag = "replace"
        else:
            merged.append((cur_tag if cur_tag != "equal" else "replace", i1, i2, j1, j2))
            cur_tag, i1, i2, j1, j2 = tag, a1, a2, b1, b2
    merged.append((cur_tag if cur_tag != "equal" else "replace", i1, i2, j1, j2))
    return merged


def _diff_region(region: str, item: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
    """返回 (type1, type2, type2_demo)。先合并相邻改动再分类。"""
    type1: list[tuple[str, str]] = []
    type2: list[tuple[str, str]] = []
    type2_demo: list[tuple[str, str]] = []
    sm = SequenceMatcher(None, region, item, autojunk=False)
    raw = list(sm.get_opcodes())
    for tag, i1, i2, j1, j2 in merge_opcodes(raw):
        orig = region[i1:i2]
        new = item[j1:j2]
        if orig and is_whitelist_only(orig):
            type1.append((orig, new))
            continue
        type2.append((orig, new))
        if involves_demonstrative_change(orig, new):
            type2_demo.append((orig, new))
    return type1, type2, type2_demo


def classify_item(burden: str, item: str) -> dict:
    span = find_cover_span(burden, item)
    if span is None:
        return {
            "span": None,
            "start": None,
            "unchanged": False,
            "diffs": [],
            "merged_diffs": [],
            "type1": [],
            "type2": [],
            "type2_demo": [],
            "ratio": 0.0,
        }
    s0, s1 = span
    region = burden[s0:s1]
    type1, type2, type2_demo = _diff_region(region, item)
    sm = SequenceMatcher(None, region, item, autojunk=False)
    raw_ops = list(sm.get_opcodes())
    diffs = [(t, region[a:b], item[c:d]) for t, a, b, c, d in raw_ops if t != "equal"]
    merged = [
        ("replace", region[a:b], item[c:d]) for _t, a, b, c, d in merge_opcodes(raw_ops)
    ]
    return {
        "span": span,
        "start": s0,
        "unchanged": not type1 and not type2,
        "diffs": diffs,
        "merged_diffs": merged,
        "type1": type1,
        "type2": type2,
        "type2_demo": type2_demo,
        "ratio": sm.ratio(),
    }


def analyze_b3(burden: str, items: list[str]) -> dict:
    per_item = [classify_item(burden, it) for it in items]
    unchanged_n = sum(1 for c in per_item if c["unchanged"])
    starts = [c["start"] for c in per_item]
    known = [(i + 1, s) for i, s in enumerate(starts) if s is not None]
    order_ok = all(known[j][1] < known[j + 1][1] for j in range(len(known) - 1))
    order_bad: list[str] = []
    if not order_ok:
        for j in range(len(known) - 1):
            a, b = known[j], known[j + 1]
            if not (a[1] < b[1]):
                order_bad.append(f"第{a[0]}条@{a[1]} → 第{b[0]}条@{b[1]}")

    covers = [c["span"] for c in per_item if c["span"] is not None]

    def overlap_len(a0: int, a1: int, b0: int, b1: int) -> int:
        return max(0, min(a1, b1) - max(a0, b0))

    uncovered: list[str] = []
    for s0, s1, sent in split_sentences(burden):
        if not sent:
            continue
        covered = sum(overlap_len(s0, s1, c0, c1) for c0, c1 in covers)
        rate = covered / len(sent) if sent else 0.0
        region_ratios = [
            SequenceMatcher(None, sent, burden[c0:c1], autojunk=False).ratio() for c0, c1 in covers
        ]
        item_ratios = [SequenceMatcher(None, sent, it, autojunk=False).ratio() for it in items]
        match_rate = max([rate] + region_ratios + item_ratios) if (covers or items) else 0.0
        if match_rate < _COVER_RATIO:
            uncovered.append(sent)

    type2_all: list[tuple[int, str, str, str, bool]] = []
    demo_all: list[tuple[int, str, str, str]] = []
    for i, (it, c) in enumerate(zip(items, per_item), start=1):
        demo_set = {(o, n) for o, n in c["type2_demo"]}
        for orig, new in c["type2"]:
            is_demo = (orig, new) in demo_set or involves_demonstrative_change(orig, new)
            type2_all.append((i, it, orig, new, is_demo))
            if is_demo:
                demo_all.append((i, it, orig, new))

    char_counts = [len(re.sub(r"\s+", "", it)) for it in items]
    return {
        "per_item": per_item,
        "unchanged_n": unchanged_n,
        "starts": starts,
        "order_ok": order_ok,
        "order_bad": order_bad,
        "uncovered": uncovered,
        "type2_all": type2_all,
        "demo_all": demo_all,
        "type2_n": len(type2_all),
        "demo_n": len(demo_all),
        "char_counts": char_counts,
        "n": len(items),
    }


def _selftest_classify() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    # 1) 只有第①类
    c1 = classify_item("他信神。祂赐下以撒。", "亚伯拉罕信神。")
    ok1 = bool(c1["type1"]) and not c1["type2"]
    results.append(
        (
            "亚伯拉罕信神。",
            ok1,
            f"条='亚伯拉罕信神。'；type1={c1['type1']}；type2={c1['type2']}；"
            f"应只有第①类 → {'PASS' if ok1 else 'FAIL'}",
        )
    )

    # 2) 合并后 祂→亚伯拉罕的神，无增字误报
    region2 = "祂是荣耀的神。"
    item2 = "亚伯拉罕的神是荣耀的神。"
    sm2 = SequenceMatcher(None, region2, item2, autojunk=False)
    raw2 = list(sm2.get_opcodes())
    merged2 = merge_opcodes(raw2)
    c2 = classify_item(region2, item2)
    # 合并后应只有一次替换；分类后只有①、无②
    only_one_merged = len(merged2) == 1
    merged_pair = (region2[merged2[0][1] : merged2[0][2]], item2[merged2[0][3] : merged2[0][4]]) if merged2 else ("", "")
    ok2 = (
        only_one_merged
        and merged_pair == ("祂", "亚伯拉罕的神")
        and bool(c2["type1"])
        and not c2["type2"]
        and c2["type1"] == [("祂", "亚伯拉罕的神")]
    )
    results.append(
        (
            item2,
            ok2,
            f"条={item2!r}；raw_ops={[(t, region2[a:b], item2[c:d]) for t,a,b,c,d in raw2 if t!='equal']}；"
            f"merged={merged_pair}；type1={c2['type1']}；type2={c2['type2']}；"
            f"应合并为祂→亚伯拉罕的神且无增字误报 → {'PASS' if ok2 else 'FAIL'}",
        )
    )

    # 3) 指示词被改
    c3 = classify_item("这样的信乃是根基。", "信乃是根基。")
    ok3 = bool(c3["type2"]) and bool(c3["type2_demo"]) and not c3["type1"]
    results.append(
        (
            "信乃是根基。",
            ok3,
            f"条='信乃是根基。'；type1={c3['type1']}；type2={c3['type2']}；"
            f"type2_demo={c3['type2_demo']}；应第②类且指示词被改 → {'PASS' if ok3 else 'FAIL'}",
        )
    )
    return results


def _snapshot_guards() -> dict:
    from panai4.prompts import prompt2_skeleton
    from panai4.sc.store import list_runs

    texts = _BACKEND / "panai4" / "prompts" / "texts"
    p2 = texts / prompt2_skeleton.VERSIONS[prompt2_skeleton.CURRENT]
    listed = list_runs(5)
    runs = listed.get("runs") or listed.get("items") or []
    max_id = max((r["id"] for r in runs), default=0)
    return {
        "max_run_id": max_id,
        "prompt2_sha1": _sha1_file(p2),
        "prompt2_path": str(p2),
        "b3_sha1": _sha1_file(_B3_PATH),
    }


def _latest_direct_ref_run(topic: str) -> dict:
    import panai4.db as panai4_db
    from panai4.sc.store import get_run

    conn = panai4_db.connect()
    rows = conn.execute(
        """
        SELECT id FROM sc_runs
        WHERE topic = ? AND ref_result IS NOT NULL AND length(ref_result) > 0
        ORDER BY id DESC
        """,
        (topic,),
    ).fetchall()
    for row in rows:
        run = get_run(int(row["id"]))
        if not run:
            continue
        text = run.get("ref_result") or ""
        if "【负担说明】" in text:
            return run
    if rows:
        run = get_run(int(rows[0]["id"]))
        if run:
            return run
    raise RuntimeError(f"no ref_result run for topic={topic!r}")


def prepare_jobs() -> list[dict]:
    from panai4.sc.store import get_run

    jobs: list[dict] = []
    tpl = _B3_PATH.read_text(encoding="utf-8")

    for rid in (26, 27):
        run = get_run(rid)
        if not run:
            raise RuntimeError(f"run #{rid} not found")
        topic = run.get("topic") or ""
        burden = _burden_of_run(run)
        prompt = tpl.replace("{query}", topic).replace("{burden}", burden)
        jobs.append(
            {
                "key": f"run{rid}",
                "run_id": rid,
                "label": f"sc_runs #{rid}",
                "topic": topic,
                "burden": burden,
                "prompt": prompt,
            }
        )

    run_ch1 = _latest_direct_ref_run(_TOPIC_CH1)
    rid = int(run_ch1["id"])
    topic = run_ch1.get("topic") or _TOPIC_CH1
    burden = _burden_of_run(run_ch1)
    prompt = tpl.replace("{query}", topic).replace("{burden}", burden)
    jobs.append(
        {
            "key": f"run{rid}",
            "run_id": rid,
            "label": f"sc_runs #{rid}（{_TOPIC_CH1} 最新直写加词条定义版）",
            "topic": topic,
            "burden": burden,
            "prompt": prompt,
        }
    )
    return jobs


async def _call(prompt: str, topic: str):
    from panai4.llm import complete
    from panai4.sc.cost import calc_cost_usd, format_usd
    from panai4.sc.llm_call import usage_dict

    result = await complete(prompt, system="", topic=topic, max_tokens=_MAX_TOKENS)
    usage = usage_dict(result)
    cost = calc_cost_usd(usage)
    usage["cost_usd"] = cost
    usage["cost_display"] = format_usd(cost)
    return result, usage, cost


def dry_run() -> int:
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_FAKE_DELAY"] = "0"
    log("=== SC EXP SKEL3 dry-run ===")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    jobs = prepare_jobs()
    ok = True
    for job in jobs:
        log(
            f"\n--- {job['label']} key={job['key']} "
            f"burden chars={len(job['burden'])} ---"
        )
        log(f"burden preview: {job['burden'][:120]!r}...")
        if "{query}" in job["prompt"] or "{burden}" in job["prompt"]:
            log(f"FAIL: {job['key']} still has placeholders")
            ok = False
        else:
            log(f"PASS: {job['key']} placeholders filled")
        (_OUT_DIR / f"prompt_B3_{job['key']}.txt").write_text(job["prompt"], encoding="utf-8")
        (_OUT_DIR / f"burden_B3_{job['key']}.txt").write_text(job["burden"], encoding="utf-8")
        for trial in range(1, _REPEATS + 1):
            log(f"\n===== PROMPT B3 {job['key']} trial{trial} (chars={len(job['prompt'])}) =====")
            log(job["prompt"])

    st = _selftest_classify()
    for _item, st_ok, detail in st:
        log(f"自测: {'PASS' if st_ok else 'FAIL'}；{detail}")
        if not st_ok:
            ok = False

    log(f"\njobs={len(jobs)} × repeats={_REPEATS} → {len(jobs)*_REPEATS} calls planned")
    log("=== dry-run done ===")
    flush_log()
    return 0 if ok else 1


def _red(s: str) -> str:
    return f'<span style="color:red">{s}</span>'


def _fmt_diff_pair(orig: str, new: str) -> str:
    o = orig if orig else "∅"
    n = new if new else "∅"
    return f"「{o}」→「{n}」"


def _section_for_trial(
    trial: int,
    items: list[str],
    ana: dict,
    usage: dict,
) -> list[str]:
    lines = [
        f"#### 第 {trial} 次",
        f"- 条数：{ana['n']}",
        f"- 无改动条数：{ana['unchanged_n']}",
        f"- 第②类条数（改动处）：{ana['type2_n']}（其中指示词被改：{ana['demo_n']}）",
        f"- 每条字数：{'、'.join(str(n) for n in ana['char_counts'])}",
        f"- 起始位置：{ana['starts']}",
        f"- 起始位置递增：{'是' if ana['order_ok'] else '否'}",
    ]
    if not ana["order_ok"]:
        for x in ana["order_bad"]:
            lines.append(f"  - {x}")
    lines.append("- 完整输出：")
    if items:
        for i, it in enumerate(items, 1):
            lines.append(f"  {i}. {it}")
    else:
        lines.append("  （未能解析编号列表）")

    lines.append("- 有改动的条（原文片段 → 本条写法）：")
    any_diff = False
    for i, (_it, c) in enumerate(zip(items, ana["per_item"]), start=1):
        if c["unchanged"]:
            continue
        any_diff = True
        pairs = list(c["type1"]) + list(c["type2"])
        detail = "；".join(_fmt_diff_pair(o, n) for o, n in pairs) if pairs else "（未能枚举）"
        lines.append(f"  - 第{i}条：{detail}")
    if not any_diff:
        lines.append("  - 无")

    lines.append("- 第①类（人称代词白名单置换）：")
    any1 = False
    for i, c in enumerate(ana["per_item"], start=1):
        for o, n in c["type1"]:
            any1 = True
            lines.append(f"  - 第{i}条：{_fmt_diff_pair(o, n)}")
    if not any1:
        lines.append("  - 无")

    lines.append("- 第②类（其他改动）：")
    if ana["type2_all"]:
        for i, _it, o, n, is_demo in ana["type2_all"]:
            mark = " 【指示词被改】" if is_demo else ""
            lines.append(f"  - {_red(f'第{i}条：{_fmt_diff_pair(o, n)}{mark}')}")
    else:
        lines.append("  - 无")

    if ana["uncovered"]:
        lines.append("- 未覆盖句：")
        for s in ana["uncovered"]:
            lines.append(f"  - {s}")
    else:
        lines.append("- 未覆盖句：无")

    lines += [
        f"- 花费：{usage.get('cost_display')} "
        f"（入 {usage.get('input_tokens')} / 出 {usage.get('output_tokens')}）",
        "",
    ]
    return lines


def _count_b2_under_b3_rules(jobs: list[dict]) -> dict[str, dict[str, int]]:
    """用 B3 检查规则重算上一轮 B2 输出的第②类数量（两次合计）。"""
    out: dict[str, dict[str, int]] = {}
    for job in jobs:
        key = job["key"]
        t2 = 0
        demo = 0
        for trial in range(1, _REPEATS + 1):
            path = _OUT_DIR / f"out_B2_{key}_t{trial}.txt"
            if not path.exists():
                continue
            items = parse_numbered_items(path.read_text(encoding="utf-8"))
            ana = analyze_b3(job["burden"], items)
            t2 += ana["type2_n"]
            demo += ana["demo_n"]
        out[key] = {"type2": t2, "demo": demo}
    return out


def run_api() -> int:
    if os.environ.get("PANAI4_FAKE_LLM") == "1":
        del os.environ["PANAI4_FAKE_LLM"]
    try:
        from dotenv import load_dotenv

        load_dotenv(_BACKEND / ".env")
    except Exception:
        pass
    if not (os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        log("FAIL: CLAUDE_API_KEY not set")
        flush_log()
        return 1

    log("=== SC EXP SKEL3 --run ===")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    before = _snapshot_guards()
    log(
        f"guard before: max_run_id={before['max_run_id']} "
        f"prompt2_sha1={before['prompt2_sha1']} b3_sha1={before['b3_sha1']}"
    )

    st = _selftest_classify()
    for _item, st_ok, detail in st:
        log(f"自测: {'PASS' if st_ok else 'FAIL'}；{detail}")
        if not st_ok:
            flush_log()
            return 1

    jobs = prepare_jobs()
    results: list[dict] = []
    total_cost = 0.0

    async def _all():
        nonlocal total_cost
        out = []
        for job in jobs:
            for trial in range(1, _REPEATS + 1):
                tag = f"{job['key']}_t{trial}"
                log(f"calling B3 {tag}...")
                result, usage, cost = await _call(job["prompt"], job["topic"])
                total_cost += cost
                text = result.text or ""
                (_OUT_DIR / f"out_B3_{tag}.txt").write_text(text, encoding="utf-8")
                (_OUT_DIR / f"usage_B3_{tag}.json").write_text(
                    json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                (_OUT_DIR / f"prompt_B3_{job['key']}.txt").write_text(job["prompt"], encoding="utf-8")
                (_OUT_DIR / f"burden_B3_{job['key']}.txt").write_text(job["burden"], encoding="utf-8")
                log(
                    f"  done in={usage.get('input_tokens')} out={usage.get('output_tokens')} "
                    f"cost={usage.get('cost_display')}"
                )
                out.append(
                    {
                        "key": job["key"],
                        "run_id": job["run_id"],
                        "label": job["label"],
                        "topic": job["topic"],
                        "burden": job["burden"],
                        "trial": trial,
                        "text": text,
                        "usage": usage,
                        "cost": cost,
                    }
                )
        return out

    results = asyncio.run(_all())

    after = _snapshot_guards()
    if after["max_run_id"] != before["max_run_id"]:
        log(f"FAIL: sc_runs max_id changed {before['max_run_id']} → {after['max_run_id']}")
        flush_log()
        return 1
    if after["prompt2_sha1"] != before["prompt2_sha1"]:
        log("FAIL: Prompt2 text file changed")
        flush_log()
        return 1
    log("PASS: sc_runs 与 Prompt2 版本库文件未改动")

    from panai4.sc.cost import format_usd

    type2_front: list[str] = []
    by_key: dict[str, list[dict]] = {}
    total_t2 = 0
    total_demo = 0
    for r in results:
        by_key.setdefault(r["key"], []).append(r)
        items = parse_numbered_items(r["text"])
        ana = analyze_b3(r["burden"], items)
        r["items"] = items
        r["ana"] = ana
        total_t2 += ana["type2_n"]
        total_demo += ana["demo_n"]
        for i, it, o, n, is_demo in ana["type2_all"]:
            mark = " 【指示词被改】" if is_demo else ""
            head = f"{r['label']} 第{r['trial']}次 / 第{i}条：{_fmt_diff_pair(o, n)}{mark}"
            type2_front.append(f"- {_red(head)}  · 条目：{it}")

    b2_counts = _count_b2_under_b3_rules(jobs)

    lines = [
        "# 龙骨一步实验 B3：只换人称代词；指示词原样；承接句并入上一句",
        "",
        f"模型：claude-opus-5-5；max_tokens={_MAX_TOKENS}；未传 temperature；每份负担跑 {_REPEATS} 次",
        f"模板：`panai4/sc/prompts/skeleton_B3.txt`",
        "",
        "## 需人工查看：第②类改动",
        "",
        f"**第②类总数：{total_t2}；其中指示词被改：{total_demo}**",
        "",
    ]
    if type2_front:
        lines.extend(type2_front)
    else:
        lines.append("（无）")
    lines += ["", "## 自测（改动分类）", ""]
    for _item, st_ok, detail in st:
        lines.append(f"- {'PASS' if st_ok else 'FAIL'}：{detail}")
    lines += ["", f"## 本次花费合计：{format_usd(total_cost)}", ""]

    # B2 vs B3 对比
    lines += [
        "## B2 与 B3 的第②类数量对比",
        "",
        "说明：B2 输出按**本轮 B3 检查规则**重算（两次运行合计），与 B3 同一尺度。",
        "",
        "| 负担说明 | B2 第②类 | B2 指示词被改 | B3 第②类 | B3 指示词被改 |",
        "|---|---:|---:|---:|---:|",
    ]
    for job in jobs:
        key = job["key"]
        trials = by_key.get(key) or []
        b3_t2 = sum(t["ana"]["type2_n"] for t in trials)
        b3_demo = sum(t["ana"]["demo_n"] for t in trials)
        b2 = b2_counts.get(key) or {"type2": -1, "demo": -1}
        lines.append(
            f"| #{job['run_id']} | {b2['type2']} | {b2['demo']} | {b3_t2} | {b3_demo} |"
        )
    lines.append("")

    for job in jobs:
        key = job["key"]
        trials = sorted(by_key[key], key=lambda x: x["trial"])
        burden = trials[0]["burden"]
        lines += [
            f"## {trials[0]['label']}",
            "",
            f"篇题：{trials[0]['topic']}",
            f"run id：#{trials[0]['run_id']}",
            "",
            "### 输入负担说明",
            burden,
            "",
            "### 两次运行并列",
            "",
        ]
        for r in trials:
            lines.extend(_section_for_trial(r["trial"], r["items"], r["ana"], r["usage"]))

        items1 = trials[0]["items"] if trials else []
        items2 = trials[1]["items"] if len(trials) > 1 else []
        n = max(len(items1), len(items2))
        lines += [
            "### 两次输出条目对照",
            "",
            "| # | 第1次 | 第2次 |",
            "|---|---|---|",
        ]
        for i in range(n):
            a = items1[i] if i < len(items1) else "—"
            b = items2[i] if i < len(items2) else "—"
            a = a.replace("|", "\\|")
            b = b.replace("|", "\\|")
            lines.append(f"| {i+1} | {a} | {b} |")
        lines.append("")

    lines += [
        "## 花费明细",
        "",
        "| 调用 | 输入 token | 输出 token | 费用 |",
        "|---|---|---|---|",
    ]
    for r in results:
        u = r["usage"]
        lines.append(
            f"| B3 {r['key']}_t{r['trial']} | {u.get('input_tokens')} | "
            f"{u.get('output_tokens')} | {u.get('cost_display')} |"
        )
    lines.append(f"| 合计 | — | — | {format_usd(total_cost)} |")
    lines.append("")

    path = _OUT_DIR / "report_B3.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    log(f"wrote {path}")
    log("=== --run done ===")
    flush_log()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="龙骨 B3 实验（只换人称代词）")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.run:
            return run_api()
        return dry_run()
    except Exception as e:
        log(f"ERROR: {e}")
        flush_log()
        raise


if __name__ == "__main__":
    sys.exit(main())
