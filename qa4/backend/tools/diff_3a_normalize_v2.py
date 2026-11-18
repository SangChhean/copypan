# -*- coding: utf-8 -*-
"""只读诊断：3a 读经行「旧路径 vs 新路径」对照。

旧路径复现方法（脚本内联，不改 normalize.py）：
  - preprocess = 补强前的 preprocess_ref_text：制表符/全角冒号、空白压缩、
    「书+阿拉伯章:节」→中文章+节、「十〇X」→「一〇X」。
  - parse = vendor VerseParser + _tok_to_ref，无 enhance / 整卷 / 章范围 /
    整章+节合并 / bare_chapter 回退。

用法：
  python qa4/backend/tools/diff_3a_normalize_v2.py
  [--out G:\\PanAI4.0专用\\logs\\formats_v2]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripture import vendor_get_vers_v21 as v21  # noqa: E402
from scripture.bible_text import BibleText  # noqa: E402
from scripture.normalize import (  # noqa: E402
    KIND_BOOK,
    KIND_CHAPTER,
    KIND_CHAPTER_RANGE,
    KIND_CROSS,
    KIND_VERSE,
    Ref,
    _cfg,
    _tok_to_ref,
    build_validator,
    heuristic_miss,
    parse_refs,
    reading_line_of,
)
from scripture.vendor_get_vers_v21 import STD2IDX  # noqa: E402
from config import get_settings  # noqa: E402

QA4 = _BACKEND.parent
DEFAULT_TD = QA4 / "data" / "graph_annotations" / "truth_dictionary_3a3b.json"
DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\formats_v2")

_SHI_LING = re.compile(r"十〇([一二三四五六七八九])")
_ARABIC_CH_VERSE = re.compile(r"(?<=[\u4e00-\u9fff])[ \u3000]*(\d+)[ \u3000]*:[ \u3000]*(\d+)")


def _int_to_cn_chapter(n: int) -> str:
    digits = "零一二三四五六七八九"
    if n <= 0:
        return str(n)
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n % 10] if n % 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        return digits[tens] + "十" + (digits[ones] if ones else "")
    if n < 200:
        h, rest = divmod(n, 100)
        body = digits[h] + "百"
        if rest == 0:
            return body
        if rest < 10:
            return body + "零" + digits[rest]
        return body + _int_to_cn_chapter(rest)
    return str(n)


def preprocess_old(text: str) -> str:
    """补强前 preprocess_ref_text（仅十〇 / 空白 / 全角冒号 / 阿拉伯章:节）。"""
    if not text:
        return text or ""
    s = text.replace("\t", " ").replace("：", ":")
    s = re.sub(r"[ \u3000]+", " ", s).strip()

    def _arab(m: re.Match[str]) -> str:
        return _int_to_cn_chapter(int(m.group(1))) + m.group(2)

    s = _ARABIC_CH_VERSE.sub(_arab, s)
    return _SHI_LING.sub(r"一〇\1", s)


def parse_refs_old(
    text: str,
    *,
    bible: Any,
    psalm_title: bool = True,
) -> list[Ref]:
    """旧路径：旧 preprocess + vendor + _tok_to_ref，无合并/整卷/回退。"""
    if not text:
        return []
    text = preprocess_old(text)
    validator = build_validator(bible, psalm_title=psalm_title)
    parser = v21.VerseParser(validate=validator, volume_book=None)
    parser.start_paragraph()
    out: list[Ref] = []
    for g in parser.parse_text(text):
        raw = g.get("text") or ""
        for part in (g.get("verses") or "").split("，"):
            part = part.strip()
            if not part:
                continue
            ref = _tok_to_ref(part, raw, psalm_title=psalm_title)
            if ref is not None:
                out.append(ref)
    return out


def label_of(r: Ref) -> str:
    return r.label()


def _endpoints(r: Ref) -> tuple[tuple[int, int], tuple[int, int]]:
    """返回 ((起章,起节), (止章,止节))，整章/章范围节用 1..9999。"""
    if r.kind == KIND_BOOK:
        return (0, 0), (9999, 9999)
    if r.kind == KIND_CHAPTER_RANGE:
        return (r.chapter, 1), (r.end_chapter, 9999)
    if r.kind == KIND_CHAPTER:
        return (r.chapter, 1), (r.chapter, 9999)
    if r.kind == KIND_CROSS:
        return (r.chapter, r.v_start), (r.end_chapter, r.v_end)
    return (r.chapter, r.v_start), (r.chapter, r.v_end)


def _covers(new: Ref, old: Ref) -> bool:
    """新 Ref 是否覆盖旧 Ref（同卷且 (章,节) 区间包含）。"""
    if new.book_no != old.book_no:
        return False
    ns, ne = _endpoints(new)
    os_, oe = _endpoints(old)
    return ns <= os_ and ne >= oe


def classify_change(old: list[Ref], new: list[Ref]) -> str:
    ol = [label_of(r) for r in old]
    nl = [label_of(r) for r in new]
    if ol == nl:
        return "不变"
    if not old and new:
        return "新增"
    if old and not new:
        return "丢失"
    if len(new) < len(old):
        # 每个被去掉的旧 Ref 是否被某个新 Ref 覆盖 → 合并，否则丢失
        new_labels = set(nl)
        uncovered = []
        for o in old:
            if label_of(o) in new_labels:
                continue
            if any(_covers(n, o) for n in new):
                continue
            # 整章被同章经节取代也算合并覆盖
            if o.kind == KIND_CHAPTER and any(
                n.book_no == o.book_no and n.chapter == o.chapter and n.kind in (KIND_VERSE, KIND_CROSS)
                for n in new
            ):
                continue
            uncovered.append(o)
        return "丢失" if uncovered else "合并"
    if len(new) > len(old):
        old_labels = set(ol)
        if all(x in nl for x in ol):
            return "新增"
        # 旧的被拆开
        return "拆分"
    return "同数量但不同"


def lost_refs(old: list[Ref], new: list[Ref]) -> list[Ref]:
    nl = {label_of(r) for r in new}
    lost = []
    for o in old:
        if label_of(o) in nl:
            continue
        if any(_covers(n, o) for n in new):
            continue
        if o.kind == KIND_CHAPTER and any(
            n.book_no == o.book_no and n.chapter == o.chapter and n.kind in (KIND_VERSE, KIND_CROSS)
            for n in new
        ):
            continue
        lost.append(o)
    return lost


def reason_lost(ref: Ref, line: str, bible: BibleText) -> str:
    """推断丢失原因（观察 + 有限核对）。"""
    from scripture.normalize import preprocess_ref_text

    bno = ref.book_no
    pre = preprocess_ref_text(line)
    # 跨章改写后整段失败：旧路径拆成两端时可能只保留合法端
    if "章" in pre and "至" in pre and ref.book in pre:
        # 核对利一1~五26 类：新写成跨章后止节不存在 → 整段空
        if ref.kind == KIND_VERSE and bible.verse_exists(bno, ref.chapter, ref.v_start):
            return (
                "【观察】新路径把含「~」的跨章短写改写成单一跨章；"
                "止端节在 bible_data 不存在时整段校验失败，"
                f"旧路径拆分后仍保留的合法端 `{ref.label()}` 一并丢失"
            )
    if ref.kind == KIND_CHAPTER:
        if not bible.chapter_exists(bno, ref.chapter):
            return "章不存在"
        return "【观察】旧为整章，新路径未再产出该整章"
    if ref.kind in (KIND_VERSE, KIND_CROSS):
        if not bible.chapter_exists(bno, ref.chapter):
            return "章不存在"
        if ref.kind == KIND_VERSE:
            missing = [
                v
                for v in range(ref.v_start, ref.v_end + 1)
                if not bible.verse_exists(bno, ref.chapter, v)
            ]
            if missing:
                return f"节不存在（缺节 {missing}）"
        else:
            if not bible.verse_exists(bno, ref.chapter, ref.v_start) or not bible.verse_exists(
                bno, ref.end_chapter, ref.v_end
            ):
                return "节不存在（跨章端点）"
        return "【观察】新旧路径切分/改写不同，旧标签未再出现且未被新 Ref 覆盖"


def run(td_path: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    bible = BibleText(get_settings(require_runtime=False).bible_dir)
    rows = json.loads(td_path.read_text(encoding="utf-8"))

    old_ge1 = old_total = new_ge1 = new_total = 0
    old_zero: list[dict] = []
    new_zero: list[dict] = []
    old_miss = new_miss = 0
    n_with = 0
    diff_rows: list[dict] = []
    type_counts: Counter = Counter()

    for row in rows:
        title = row.get("title") or ""
        line = reading_line_of(row.get("content_3a") or "")
        if line is None:
            continue
        n_with += 1
        old = parse_refs_old(line, bible=bible)
        new = parse_refs(line, bible=bible)
        old_total += len(old)
        new_total += len(new)
        if old:
            old_ge1 += 1
        else:
            old_zero.append({"title": title, "line": line})
        if new:
            new_ge1 += 1
        else:
            new_zero.append({"title": title, "line": line})
        if heuristic_miss(line, len(old)):
            old_miss += 1
        if heuristic_miss(line, len(new)):
            new_miss += 1

        ctype = classify_change(old, new)
        type_counts[ctype] += 1
        ol = [label_of(r) for r in old]
        nl = [label_of(r) for r in new]
        lost = lost_refs(old, new)
        diff_rows.append(
            {
                "词条": title,
                "读经行原文": line,
                "旧出处列表": " ; ".join(ol),
                "新出处列表": " ; ".join(nl),
                "变化类型": ctype,
                "旧数量": len(old),
                "新数量": len(new),
                "数量差": len(new) - len(old),
                "未覆盖的旧出处": " ; ".join(label_of(r) for r in lost),
            }
        )

    # 证明旧路径
    print("=== 旧路径复现 ===")
    print(f"复现方法: 脚本内联 preprocess_old + vendor + _tok_to_ref（无 enhance/合并/整卷/回退）")
    expect = {
        "n_with": 2365,
        "ge1": 2360,
        "total": 23103,
        "zero": 5,
        "miss": 23,
    }
    actual_old = {
        "n_with": n_with,
        "ge1": old_ge1,
        "total": old_total,
        "zero": len(old_zero),
        "miss": old_miss,
    }
    print(f"期望: {expect}")
    print(f"实际: {actual_old}")
    ok = actual_old == expect
    print(f"复现成功: {ok}")
    if not ok:
        print("旧路径未能复现旧数字，按任务要求停止后续 diff 结论输出。")
        # 仍写出部分诊断
        (out_dir / "regression_3a_old_path_failed.txt").write_text(
            f"expect={expect}\nactual={actual_old}\nzero={[z['title']+':'+z['line'] for z in old_zero]}\n",
            encoding="utf-8",
        )
        return 1

    print("=== 新路径 ===")
    print(
        f"with={n_with} ge1={new_ge1} total={new_total} zero={len(new_zero)} miss={new_miss}"
    )
    net = new_total - old_total
    print(f"净变化 total: {net} （期望 -37）")

    csv_path = out_dir / "regression_3a_diff.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "词条",
                "读经行原文",
                "旧出处列表",
                "新出处列表",
                "变化类型",
                "旧数量",
                "新数量",
                "数量差",
                "未覆盖的旧出处",
            ],
        )
        w.writeheader()
        for r in diff_rows:
            w.writerow(r)

    # 类型条数 + 净变化核对
    print("=== 变化类型条数（按读经行） ===")
    for k in ("不变", "合并", "拆分", "新增", "丢失", "同数量但不同"):
        print(f"  {k}: {type_counts.get(k, 0)}")
    sum_delta = sum(r["数量差"] for r in diff_rows)
    print(f"各行数量差之和: {sum_delta}")

    # 丢失逐条
    lost_lines = []
    for r in diff_rows:
        if r["变化类型"] != "丢失" and not r["未覆盖的旧出处"]:
            continue
        # 逐条丢失出处
        row_old = parse_refs_old(r["读经行原文"], bible=bible)
        row_new = parse_refs(r["读经行原文"], bible=bible)
        for o in lost_refs(row_old, row_new):
            lost_lines.append(
                {
                    "词条": r["词条"],
                    "原文": r["读经行原文"],
                    "丢失出处": label_of(o),
                    "原因": reason_lost(o, r["读经行原文"], bible),
                    "行类型": r["变化类型"],
                }
            )

    print("=== 丢失出处（未被子 Ref 覆盖）条数 ===", len(lost_lines))
    for x in lost_lines:
        print(
            f"  [{x['行类型']}] {x['词条']}: 丢 {x['丢失出处']} | {x['原因']} | 原文={x['原文'][:60]}"
        )

    same_diff = [r for r in diff_rows if r["变化类型"] == "同数量但不同"]
    print("=== 同数量但不同 ===", len(same_diff))
    for r in same_diff:
        print(f"  {r['词条']}: 旧=[{r['旧出处列表']}] 新=[{r['新出处列表']}]")

    # 零出处 5→1：现在能解析的 4 行
    old_zero_titles = {z["title"] for z in old_zero}
    newly_parsed = []
    for z in old_zero:
        new = parse_refs(z["line"], bible=bible)
        if new:
            newly_parsed.append(
                {
                    "title": z["title"],
                    "line": z["line"],
                    "new": [label_of(r) for r in new],
                    "kinds": [r.kind for r in new],
                }
            )
    print("=== 原零出处现能解析 ===", len(newly_parsed))
    for x in newly_parsed:
        print(f"  {x['title']}: {x['line']!r} → {x['new']} kinds={x['kinds']}")

    still_zero = [z for z in old_zero if z["title"] not in {x["title"] for x in newly_parsed}]
    # also check new_zero
    print("=== 新零出处 ===", [z["title"] + ":" + z["line"] for z in new_zero])

    # 写要点 md
    md = [
        "# 3a normalize v2 回归对照",
        "",
        "## 旧路径复现",
        "",
        "- 方法：脚本内联 `preprocess_old` + vendor + `_tok_to_ref`",
        f"- 结果：with={n_with} ge1={old_ge1} total={old_total} zero={len(old_zero)} miss={old_miss}",
        f"- 复现成功：{ok}",
        "",
        "## 新路径",
        "",
        f"- with={n_with} ge1={new_ge1} total={new_total} zero={len(new_zero)} miss={new_miss}",
        f"- 净变化 total={net}",
        "",
        "## 变化类型（按行）",
        "",
    ]
    for k in ("不变", "合并", "拆分", "新增", "丢失", "同数量但不同"):
        md.append(f"- {k}: {type_counts.get(k, 0)}")
    md += ["", f"- 各行数量差之和: {sum_delta}", "", "## 丢失出处", ""]
    if not lost_lines:
        md.append("- （无）")
    for x in lost_lines:
        md.append(
            f"- {x['词条']} | 丢 `{x['丢失出处']}` | {x['原因']} | 原文=`{x['原文']}` | 行类型={x['行类型']}"
        )
    md += ["", "## 同数量但不同", ""]
    if not same_diff:
        md.append("- （无）")
    for r in same_diff:
        md.append(f"- {r['词条']}: 旧=`{r['旧出处列表']}` → 新=`{r['新出处列表']}`")
    md += ["", "## 原零出处→现可解析", ""]
    for x in newly_parsed:
        md.append(f"- {x['title']}: `{x['line']}` → {x['new']} ({x['kinds']})")
    md += ["", f"CSV: `{csv_path}`", ""]
    (out_dir / "regression_3a_diff.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"OUT_CSV={csv_path}")
    print(f"OUT_MD={out_dir / 'regression_3a_diff.md'}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--td", type=Path, default=DEFAULT_TD)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    return run(args.td, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
