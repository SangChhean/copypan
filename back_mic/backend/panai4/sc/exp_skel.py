# -*- coding: utf-8 -*-
"""龙骨一步对照：现行 Prompt2 (A) vs 原句切分版 (B)。

用法（在 back_mic/backend）:
    python -m panai4.sc.exp_skel          # dry-run（FAKE_LLM）
    python -m panai4.sc.exp_skel --run    # 真实 API
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parents[1]
_OUT_DIR = _REPO / "docs" / "panai4_sc" / "exp_skel"
_LOG = _REPO / "logs" / "sc_exp_skel.log"
_B_PATH = Path(__file__).resolve().parent / "prompts" / "skeleton_B.txt"

_RUN_IDS = (26, 27)
_MAX_TOKENS = 8192

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


def _fill_ab(topic: str, burden: str) -> tuple[str, str, str]:
    """返回 (tpl_a_raw, prompt_a, prompt_b)。"""
    from panai4.prompts import load_template, render_user

    tpl_a = load_template("skeleton")
    prompt_a = render_user("skeleton", topic=topic, burden=burden, template=tpl_a)
    tpl_b = _B_PATH.read_text(encoding="utf-8")
    prompt_b = tpl_b.replace("{query}", topic).replace("{burden}", burden)
    return tpl_a, prompt_a, prompt_b


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
    """按句号/分号切分，返回 (start, end, text)；保留原文切片。"""
    raw = burden or ""
    spans: list[tuple[int, int, str]] = []
    start = 0
    for i, ch in enumerate(raw):
        if ch in "。；;":
            end = i + 1
            piece = raw[start:end]
            if piece.strip():
                spans.append((start, end, piece.strip()))
            start = end
    if start < len(raw) and raw[start:].strip():
        spans.append((start, len(raw), raw[start:].strip()))
    return spans


def analyze_items(burden: str, items: list[str]) -> dict:
    """机械检查：子串、顺序、未覆盖句、字数。"""
    positions: list[int | None] = []
    not_substr: list[tuple[int, str]] = []
    search_from = 0
    covered: list[tuple[int, int]] = []
    for i, item in enumerate(items, start=1):
        idx = burden.find(item, search_from)
        if idx < 0:
            # 再试从头找（报告仍标不递增可能）
            idx2 = burden.find(item)
            if idx2 < 0:
                positions.append(None)
                not_substr.append((i, item))
            else:
                positions.append(idx2)
                covered.append((idx2, idx2 + len(item)))
                search_from = idx2 + 1
        else:
            positions.append(idx)
            covered.append((idx, idx + len(item)))
            search_from = idx + 1

    # 顺序：有位置的序列是否严格递增
    known = [(i + 1, p) for i, p in enumerate(positions) if p is not None]
    order_ok = all(known[j][1] < known[j + 1][1] for j in range(len(known) - 1))
    order_bad: list[str] = []
    if not order_ok:
        for j in range(len(known) - 1):
            a, b = known[j], known[j + 1]
            if not (a[1] < b[1]):
                order_bad.append(f"第{a[0]}条@{a[1]} → 第{b[0]}条@{b[1]}")

    def overlaps(a0, a1, b0, b1) -> bool:
        return a0 < b1 and b0 < a1

    uncovered: list[str] = []
    for s0, s1, sent in split_sentences(burden):
        hit = any(overlaps(s0, s1, c0, c1) for c0, c1 in covered)
        if not hit:
            uncovered.append(sent)

    char_counts = [len(re.sub(r"\s+", "", it)) for it in items]
    return {
        "positions": positions,
        "not_substr": not_substr,
        "order_ok": order_ok,
        "order_bad": order_bad,
        "uncovered": uncovered,
        "char_counts": char_counts,
    }


def _selftest_substr() -> tuple[bool, str]:
    burden = "甲乙丙丁戊己庚辛。"
    good = "甲乙丙丁"
    bad = "甲乙XX丁"
    ok_good = good in burden
    ok_bad = bad in burden
    passed = ok_good and (not ok_bad)
    detail = (
        f"自测负担={burden!r}；"
        f"原文条 {good!r} → {'有' if ok_good else '无'}；"
        f"故意改动条 {bad!r} → {'有' if ok_bad else '无'}（期望无）"
    )
    return passed, detail


def _snapshot_guards() -> dict:
    from panai4.sc.store import list_runs
    from panai4.prompts import prompt2_skeleton

    texts = _BACKEND / "panai4" / "prompts" / "texts"
    p2 = texts / prompt2_skeleton.VERSIONS[prompt2_skeleton.CURRENT]
    listed = list_runs(5)
    runs = listed.get("runs") or listed.get("items") or []
    max_id = max((r["id"] for r in runs), default=0)
    return {
        "max_run_id": max_id,
        "prompt2_sha1": _sha1_file(p2),
        "prompt2_path": str(p2),
    }


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


def prepare_jobs():
    from panai4.sc.store import get_run

    jobs = []
    for rid in _RUN_IDS:
        run = get_run(rid)
        if not run:
            raise RuntimeError(f"run #{rid} not found")
        topic = run.get("topic") or ""
        burden = _burden_of_run(run)
        tpl_a, pa, pb = _fill_ab(topic, burden)
        jobs.append(
            {
                "run_id": rid,
                "topic": topic,
                "burden": burden,
                "tpl_a": tpl_a,
                "prompt_a": pa,
                "prompt_b": pb,
            }
        )
    return jobs


def dry_run() -> int:
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_FAKE_DELAY"] = "0"
    log("=== SC EXP SKEL dry-run ===")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    from panai4.prompts import load_template, render_user

    jobs = prepare_jobs()
    ok = True
    for job in jobs:
        rid = job["run_id"]
        topic = job["topic"]
        burden = job["burden"]
        log(f"\n--- run #{rid} burden chars={len(burden)} paras={burden.count(chr(10))+1} ---")
        log(f"burden preview: {burden[:120]!r}...")

        # A 与版本库：原始模板逐字节 = CURRENT；填好的 = render_user
        raw = load_template("skeleton")
        if raw != job["tpl_a"]:
            log("FAIL: tpl_a != load_template(skeleton)")
            ok = False
        filled_ref = render_user("skeleton", topic=topic, burden=burden)
        if filled_ref != job["prompt_a"]:
            log("FAIL: prompt_a != render_user")
            ok = False
        else:
            # 只有占位符被替换：从 raw 替换应得同一结果
            manual = raw.replace("{query}", topic).replace("{burden}", burden)
            if manual != job["prompt_a"]:
                log("FAIL: prompt_a != raw with only {query}/{burden} replaced")
                ok = False
            else:
                log(f"PASS: #{rid} A prompt == 版本库当前版（仅占位符替换）")

        if "{query}" in job["prompt_a"] or "{burden}" in job["prompt_a"]:
            log(f"FAIL: #{rid} A still has placeholders")
            ok = False
        if "{query}" in job["prompt_b"] or "{burden}" in job["prompt_b"]:
            log(f"FAIL: #{rid} B still has placeholders")
            ok = False

        (_OUT_DIR / f"prompt_A_run{rid}.txt").write_text(job["prompt_a"], encoding="utf-8")
        (_OUT_DIR / f"prompt_B_run{rid}.txt").write_text(job["prompt_b"], encoding="utf-8")
        (_OUT_DIR / f"burden_run{rid}.txt").write_text(burden, encoding="utf-8")
        log(f"\n===== PROMPT A #{rid} (chars={len(job['prompt_a'])}) =====")
        log(job["prompt_a"])
        log(f"\n===== PROMPT B #{rid} (chars={len(job['prompt_b'])}) =====")
        log(job["prompt_b"])

    st_ok, st_detail = _selftest_substr()
    log(f"\n自测子串检查: {'PASS' if st_ok else 'FAIL'}；{st_detail}")
    if not st_ok:
        ok = False

    log("=== dry-run done ===")
    flush_log()
    return 0 if ok else 1


def _fmt_analysis(label: str, items: list[str], ana: dict) -> list[str]:
    lines = [
        f"### {label}",
        f"条数：{len(items)}",
        "",
        "完整输出：",
    ]
    if items:
        for i, it in enumerate(items, 1):
            lines.append(f"{i}. {it}")
    else:
        lines.append("（未能解析编号列表）")
    lines += ["", "机械检查："]
    if ana["not_substr"]:
        lines.append("- 逐字子串：有条目「无」")
        for i, it in ana["not_substr"]:
            lines.append(f"  - 第{i}条（无）：{it}")
    else:
        lines.append("- 逐字子串：全部「有」")
    if ana["order_ok"]:
        lines.append("- 起始位置递增：是")
    else:
        lines.append("- 起始位置递增：否")
        for x in ana["order_bad"]:
            lines.append(f"  - {x}")
    lines.append(f"- 各条起始位置：{ana['positions']}")
    if ana["uncovered"]:
        lines.append("- 未覆盖句：")
        for s in ana["uncovered"]:
            lines.append(f"  - {s}")
    else:
        lines.append("- 未覆盖句：无")
    lines.append("- 每条字数：" + "、".join(str(n) for n in ana["char_counts"]))
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

    log("=== SC EXP SKEL --run ===")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    before = _snapshot_guards()
    log(f"guard before: max_run_id={before['max_run_id']} prompt2_sha1={before['prompt2_sha1']}")

    jobs = prepare_jobs()
    results = []  # list of dicts
    total_cost = 0.0

    async def _all():
        nonlocal total_cost
        out = []
        for job in jobs:
            for ver, prompt in (("A", job["prompt_a"]), ("B", job["prompt_b"])):
                log(f"calling #{job['run_id']} {ver}...")
                result, usage, cost = await _call(prompt, job["topic"])
                total_cost += cost
                text = result.text or ""
                fname = f"out_{ver}_run{job['run_id']}.txt"
                (_OUT_DIR / fname).write_text(text, encoding="utf-8")
                (_OUT_DIR / f"usage_{ver}_run{job['run_id']}.json").write_text(
                    json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                log(
                    f"  done in={usage.get('input_tokens')} out={usage.get('output_tokens')} "
                    f"cost={usage.get('cost_display')}"
                )
                out.append(
                    {
                        "run_id": job["run_id"],
                        "ver": ver,
                        "topic": job["topic"],
                        "burden": job["burden"],
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

    st_ok, st_detail = _selftest_substr()
    log(f"自测子串检查: {'PASS' if st_ok else 'FAIL'}；{st_detail}")

    from panai4.sc.cost import format_usd

    # report
    by_run: dict[int, dict[str, dict]] = {26: {}, 27: {}}
    for r in results:
        by_run[r["run_id"]][r["ver"]] = r

    lines = [
        "# 龙骨一步对照：Prompt2 (A) vs 原句切分版 (B)",
        "",
        "篇题：亚伯拉罕的神见于祂对待亚伯拉罕的事",
        "输入：sc_runs #26、#27 的负担说明正文",
        f"模型：claude-opus-5-5；max_tokens={_MAX_TOKENS}；未传 temperature",
        "",
        "## 自测（逐字子串检查）",
        f"- {'PASS' if st_ok else 'FAIL'}：{st_detail}",
        "",
        f"## 本次花费合计：{format_usd(total_cost)}",
        "",
    ]

    for rid in _RUN_IDS:
        burden = by_run[rid]["A"]["burden"]
        lines += [
            f"## 负担说明来源：sc_runs #{rid}",
            "",
            "### 输入负担说明",
            burden,
            "",
        ]
        pair = {}
        for ver in ("A", "B"):
            r = by_run[rid][ver]
            items = parse_numbered_items(r["text"])
            ana = analyze_items(burden, items)
            pair[ver] = (items, ana, r)
            lines.extend(_fmt_analysis(f"版本 {ver}", items, ana))
            lines += [
                "",
                f"花费 {ver}：{r['usage'].get('cost_display')} "
                f"（入 {r['usage'].get('input_tokens')} / 出 {r['usage'].get('output_tokens')}）",
                "",
            ]

        # 并列
        items_a, _, _ = pair["A"]
        items_b, _, _ = pair["B"]
        n = max(len(items_a), len(items_b))
        lines += [
            "### A 与 B 并列",
            "",
            "| # | A（Prompt2） | B（原句切分） |",
            "|---|---|---|",
        ]
        for i in range(n):
            a = items_a[i] if i < len(items_a) else "—"
            b = items_b[i] if i < len(items_b) else "—"
            a = a.replace("|", "\\|")
            b = b.replace("|", "\\|")
            lines.append(f"| {i+1} | {a} | {b} |")
        lines.append("")

    # cost table
    lines += [
        "## 花费明细",
        "",
        "| 调用 | 输入 token | 输出 token | 费用 |",
        "|---|---|---|---|",
    ]
    for r in results:
        u = r["usage"]
        lines.append(
            f"| #{r['run_id']} {r['ver']} | {u.get('input_tokens')} | {u.get('output_tokens')} | "
            f"{u.get('cost_display')} |"
        )
    lines.append(f"| 合计 | — | — | {format_usd(total_cost)} |")
    lines.append("")

    path = _OUT_DIR / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    log(f"wrote {path}")
    log("=== --run done ===")
    flush_log()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="龙骨 Prompt2 vs 原句切分对照")
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
