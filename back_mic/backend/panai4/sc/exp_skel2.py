# -*- coding: utf-8 -*-
"""龙骨一步实验 B2：原句切分 + 允许代词换成明确名称。

用法（在 back_mic/backend）:
    python -m panai4.sc.exp_skel2          # dry-run（FAKE_LLM）
    python -m panai4.sc.exp_skel2 --run    # 真实 API
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
_LOG = _REPO / "logs" / "sc_exp_skel2.log"
_B2_PATH = Path(__file__).resolve().parent / "prompts" / "skeleton_B2.txt"

_TOPIC_CH1 = "认识并经历亚伯拉罕的神、以撒的神和雅各的神，而成为神的以色列"
_MAX_TOKENS = 8192
_REPEATS = 2
_COVER_RATIO = 0.6

# 代词/指示词白名单（长词优先）
_WHITELIST = [
    "他们的",
    "祂们的",
    "她们的",
    "它们的",
    "他们",
    "祂们",
    "她们",
    "它们",
    "这样的",
    "这样",
    "他的",
    "祂的",
    "她的",
    "它的",
    "这的",
    "那的",
    "其的",
    "此的",
    "他",
    "祂",
    "她",
    "它",
    "这",
    "那",
    "其",
    "此",
]

# 用于拆开 SequenceMatcher 把增字吞进「代词→名称」的常见明确名称（仅辅助切分）
_KNOWN_NAMES = sorted(
    [
        "亚伯拉罕",
        "以撒",
        "雅各",
        "撒拉",
        "以实玛利",
        "新耶路撒冷",
        "耶路撒冷",
        "以色列",
        "亚伯拉罕的后裔",
        "复活的神",
        "荣耀的神",
        "呼召的神",
        "那灵",
        "基督",
        "召会",
        "神",
        "主",
        "我们",
        "人",
    ],
    key=len,
    reverse=True,
)

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
                # 保留在原文中的起止（含前导空白的切片起止用 strip 后重定位）
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


def find_cover_span(burden: str, item: str) -> tuple[int, int] | None:
    """滑动窗口找覆盖区间；得分兼顾 equal 与「代词未丢掉」。"""
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
            # ratio 优先，避免更长窗口靠误匹配单字（如「神」）抬高 equal
            score = (r, eq, -abs(wlen - len(item)), wlen)
            if best is None or score > best[0]:
                best = (score, i, i + wlen)
    if best is None:
        return None
    s0, s1 = best[1], best[2]
    # 向左吞回紧邻的白名单代词/指示词（条目往往已换成名称）
    while s0 > 0:
        extended = False
        for w in _WHITELIST:
            if s0 >= len(w) and burden[s0 - len(w) : s0] == w:
                s0 -= len(w)
                extended = True
                break
        if not extended:
            break
    return s0, s1


def _next_whitelist(s: str, i: int) -> str | None:
    for w in _WHITELIST:
        if s.startswith(w, i):
            return w
    return None


def _split_known_name(new: str) -> tuple[str, str]:
    """若 new 以已知明确名称开头且后面还有短后缀，拆成 名称 + 疑似增字。"""
    if not new:
        return "", ""
    for name in _KNOWN_NAMES:
        if new == name:
            return name, ""
        if new.startswith(name):
            extra = new[len(name) :]
            # 仅拆很短的后缀，避免误拆「亚伯拉罕的后裔」等
            if 0 < len(extra) <= 2:
                return name, extra
    return new, ""


def _diff_region(region: str, item: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """SequenceMatcher 字符级比对；白名单原文 → 第①类，其余 → 第②类。"""
    type1: list[tuple[str, str]] = []
    type2: list[tuple[str, str]] = []
    sm = SequenceMatcher(None, region, item, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        orig = region[i1:i2]
        new = item[j1:j2]
        if tag in ("replace", "delete") and is_whitelist_only(orig):
            name, extra = _split_known_name(new)
            if new and extra:
                type1.append((orig, name))
                type2.append(("", extra))
            else:
                type1.append((orig, new))
        elif tag == "insert":
            type2.append(("", new))
        else:
            # 非白名单 replace/delete
            if is_whitelist_only(orig) and tag == "delete":
                type1.append((orig, new))
            else:
                type2.append((orig, new))
    return type1, type2


def classify_item(burden: str, item: str) -> dict:
    """对单条做字符级比对，返回改动分类与覆盖位置。"""
    span = find_cover_span(burden, item)
    if span is None:
        return {
            "span": None,
            "start": None,
            "unchanged": False,
            "diffs": [],
            "type1": [],
            "type2": [],
            "ratio": 0.0,
        }
    s0, s1 = span
    region = burden[s0:s1]
    type1, type2 = _diff_region(region, item)
    sm = SequenceMatcher(None, region, item, autojunk=False)
    diffs: list[tuple[str, str, str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        diffs.append((tag, region[i1:i2], item[j1:j2]))
    return {
        "span": span,
        "start": s0,
        "unchanged": not type1 and not type2,
        "diffs": diffs,
        "type1": type1,
        "type2": type2,
        "ratio": sm.ratio(),
    }


def analyze_b2(burden: str, items: list[str]) -> dict:
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
        # 亦用 SequenceMatcher 与各条覆盖原文比，取较高者
        region_ratios = [
            SequenceMatcher(None, sent, burden[c0:c1], autojunk=False).ratio() for c0, c1 in covers
        ]
        item_ratios = [SequenceMatcher(None, sent, it, autojunk=False).ratio() for it in items]
        match_rate = max([rate] + region_ratios + item_ratios) if (covers or items) else 0.0
        if match_rate < _COVER_RATIO:
            uncovered.append(sent)

    type2_all: list[tuple[int, str, str, str]] = []  # (item_idx, item, orig, new)
    for i, (it, c) in enumerate(zip(items, per_item), start=1):
        for orig, new in c["type2"]:
            type2_all.append((i, it, orig, new))

    char_counts = [len(re.sub(r"\s+", "", it)) for it in items]
    return {
        "per_item": per_item,
        "unchanged_n": unchanged_n,
        "starts": starts,
        "order_ok": order_ok,
        "order_bad": order_bad,
        "uncovered": uncovered,
        "type2_all": type2_all,
        "char_counts": char_counts,
        "n": len(items),
    }


def _selftest_classify() -> list[tuple[str, bool, str]]:
    burden = "他信神。祂赐下以撒。"
    cases = [
        ("亚伯拉罕信神。", "only1", "应只有第①类"),
        ("亚伯拉罕相信神。", "has2", "应有第②类（信→相信）"),
        ("神赐下以撒。", "only1", "应只有第①类（祂→神）"),
    ]
    results: list[tuple[str, bool, str]] = []
    for item, expect, note in cases:
        c = classify_item(burden, item)
        has1 = bool(c["type1"])
        has2 = bool(c["type2"])
        if expect == "only1":
            ok = has1 and not has2
        else:
            ok = has2
        detail = (
            f"条={item!r}；type1={c['type1']}；type2={c['type2']}；"
            f"span={c['span']}；{note} → {'PASS' if ok else 'FAIL'}"
        )
        results.append((item, ok, detail))
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
        "b2_sha1": _sha1_file(_B2_PATH),
    }


def _latest_direct_ref_run(topic: str) -> dict:
    """按题目找最后一条有加词条定义版结果的记录（直写版以【负担说明】起）。"""
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
        # 直写版特征：含【负担说明】；旧版职事界定也可有负担，但优先直写
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
    tpl = _B2_PATH.read_text(encoding="utf-8")

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
    log("=== SC EXP SKEL2 dry-run ===")
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
        path = _OUT_DIR / f"prompt_B2_{job['key']}.txt"
        path.write_text(job["prompt"], encoding="utf-8")
        (_OUT_DIR / f"burden_B2_{job['key']}.txt").write_text(job["burden"], encoding="utf-8")
        # 每份负担 × 2 次 = 打印 6 份（内容相同，标 trial）
        for trial in range(1, _REPEATS + 1):
            log(f"\n===== PROMPT B2 {job['key']} trial{trial} (chars={len(job['prompt'])}) =====")
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
    for i, (it, c) in enumerate(zip(items, ana["per_item"]), start=1):
        if c["unchanged"]:
            continue
        any_diff = True
        pairs = list(c["type1"]) + list(c["type2"])
        if not pairs and c["diffs"]:
            pairs = [(o, n) for _tag, o, n in c["diffs"]]
        detail = "；".join(_fmt_diff_pair(o, n) for o, n in pairs) if pairs else "（未能枚举）"
        lines.append(f"  - 第{i}条：{detail}")
    if not any_diff:
        lines.append("  - 无")

    lines.append("- 第①类（代词/指示词白名单置换）：")
    any1 = False
    for i, c in enumerate(ana["per_item"], start=1):
        for o, n in c["type1"]:
            any1 = True
            lines.append(f"  - 第{i}条：{_fmt_diff_pair(o, n)}")
    if not any1:
        lines.append("  - 无")

    lines.append("- 第②类（其他改动）：")
    if ana["type2_all"]:
        for i, _it, o, n in ana["type2_all"]:
            lines.append(f"  - {_red(f'第{i}条：{_fmt_diff_pair(o, n)}')}")
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

    log("=== SC EXP SKEL2 --run ===")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    before = _snapshot_guards()
    log(
        f"guard before: max_run_id={before['max_run_id']} "
        f"prompt2_sha1={before['prompt2_sha1']} b2_sha1={before['b2_sha1']}"
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
                log(f"calling B2 {tag}...")
                result, usage, cost = await _call(job["prompt"], job["topic"])
                total_cost += cost
                text = result.text or ""
                (_OUT_DIR / f"out_B2_{tag}.txt").write_text(text, encoding="utf-8")
                (_OUT_DIR / f"usage_B2_{tag}.json").write_text(
                    json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                (_OUT_DIR / f"prompt_B2_{job['key']}.txt").write_text(job["prompt"], encoding="utf-8")
                (_OUT_DIR / f"burden_B2_{job['key']}.txt").write_text(job["burden"], encoding="utf-8")
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

    # 全局第②类置顶
    type2_front: list[str] = []
    by_key: dict[str, list[dict]] = {}
    for r in results:
        by_key.setdefault(r["key"], []).append(r)
        items = parse_numbered_items(r["text"])
        ana = analyze_b2(r["burden"], items)
        r["items"] = items
        r["ana"] = ana
        for i, it, o, n in ana["type2_all"]:
            head = f"{r['label']} 第{r['trial']}次 / 第{i}条：{_fmt_diff_pair(o, n)}"
            type2_front.append(f"- {_red(head)}  · 条目：{it}")

    lines = [
        "# 龙骨一步实验 B2：原句切分（允许代词→明确名称）",
        "",
        f"模型：claude-opus-5-5；max_tokens={_MAX_TOKENS}；未传 temperature；每份负担跑 {_REPEATS} 次",
        f"模板：`panai4/sc/prompts/skeleton_B2.txt`",
        "",
        "## 需人工查看：第②类改动（非代词/指示词白名单）",
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

    # 按 jobs 顺序出节
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

        # 并列条目表
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
            f"| B2 {r['key']}_t{r['trial']} | {u.get('input_tokens')} | "
            f"{u.get('output_tokens')} | {u.get('cost_display')} |"
        )
    lines.append(f"| 合计 | — | — | {format_usd(total_cost)} |")
    lines.append("")

    path = _OUT_DIR / "report_B2.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    log(f"wrote {path}")
    log("=== --run done ===")
    flush_log()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="龙骨 B2 原句切分（代词可换名）实验")
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
