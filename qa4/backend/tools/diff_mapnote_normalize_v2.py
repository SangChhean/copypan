# -*- coding: utf-8 -*-
"""只读：map_note jsonl 旧路径 vs 新路径对照。

用法：
  python qa4/backend/tools/diff_mapnote_normalize_v2.py
  [--jsonl G:\\PanAI4.0专用\\12490原文JSONL\\kg-rag_map_note.jsonl]
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

from config import get_settings  # noqa: E402
from scripture.bible_text import BibleText  # noqa: E402
from scripture.normalize import (  # noqa: E402
    KIND_BOOK,
    KIND_CHAPTER,
    KIND_CHAPTER_RANGE,
    KIND_CROSS,
    KIND_VERSE,
    parse_refs,
)
from tools.diff_3a_normalize_v2 import parse_refs_old  # noqa: E402
from tools.verify_stage2_live import extract_map_note_ref  # noqa: E402

DEFAULT_JSONL = Path(r"G:\PanAI4.0专用\12490原文JSONL\kg-rag_map_note.jsonl")
DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\formats_v2")


def label_of(r) -> str:
    return r.label()


def _endpoints(r):
    if r.kind == KIND_BOOK:
        return (0, 0), (10_000, 10_000)
    if r.kind == KIND_CHAPTER_RANGE:
        return (r.chapter, 1), (r.end_chapter, 10_000)
    if r.kind == KIND_CHAPTER:
        return (r.chapter, 1), (r.chapter, 10_000)
    if r.kind == KIND_CROSS:
        return (r.chapter, r.v_start), (r.end_chapter, r.v_end)
    return (r.chapter, r.v_start), (r.chapter, r.v_end)


def _covers(new_r, old_r) -> bool:
    if new_r.book_no != old_r.book_no:
        return False
    ns, ne = _endpoints(new_r)
    os_, oe = _endpoints(old_r)
    return ns <= os_ and ne >= oe


def classify(old, new) -> str:
    ol = [label_of(r) for r in old]
    nl = [label_of(r) for r in new]
    if ol == nl:
        return "不变"
    if not old and new:
        return "新增"
    if old and not new:
        return "丢失"
    if len(new) < len(old):
        uncovered = [
            o
            for o in old
            if label_of(o) not in nl
            and not any(_covers(n, o) for n in new)
            and not (
                o.kind == KIND_CHAPTER
                and any(
                    n.book_no == o.book_no and n.chapter == o.chapter and n.kind in (KIND_VERSE, KIND_CROSS)
                    for n in new
                )
            )
        ]
        return "丢失" if uncovered else "合并"
    if len(new) > len(old):
        if all(x in nl for x in ol):
            return "新增"
        return "拆分"
    return "同数量但不同"


def reason_uncovered(old_r, new_refs, mid: str, bible: BibleText) -> str:
    # 假整章：旧整章、新同章有节
    if old_r.kind == KIND_CHAPTER and any(
        n.book_no == old_r.book_no and n.chapter == old_r.chapter and n.kind in (KIND_VERSE, KIND_CROSS)
        for n in new_refs
    ):
        return "假整章"
    if old_r.kind in (KIND_VERSE, KIND_CROSS):
        if not bible.chapter_exists(old_r.book_no, old_r.chapter):
            return "章不存在"
        if old_r.kind == KIND_VERSE:
            if not bible.verse_exists(old_r.book_no, old_r.chapter, old_r.v_start) or not bible.verse_exists(
                old_r.book_no, old_r.chapter, old_r.v_end
            ):
                return "节不存在"
        else:
            if not bible.verse_exists(old_r.book_no, old_r.chapter, old_r.v_start) or not bible.verse_exists(
                old_r.book_no, old_r.end_chapter, old_r.v_end
            ):
                return "终点不存在"
        # 跨章改写导致一端非法整段丢？
        if "~" in mid or "～" in mid or re.search(r"\d+~\S", mid):
            return "终点不存在"
    return "其它"


def iter_extractable(jsonl: Path):
    n = 0
    with jsonl.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            sz = obj.get("source_zh") or ""
            mid = extract_map_note_ref(sz)
            if not mid:
                continue
            n += 1
            yield n, sz, mid, obj.get("chunk_id") or ""
    return


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    bible = BibleText(get_settings(require_runtime=False).bible_dir)
    type_counts: Counter = Counter()
    old_total = new_total = 0
    rows_out: list[dict] = []
    uncovered: list[dict] = []
    extras_new: list[dict] = []
    extract_n = 0

    for i, sz, mid, cid in iter_extractable(args.jsonl):
        extract_n = i
        old = parse_refs_old(mid, bible=bible)
        new = parse_refs(mid, bible=bible)
        old_total += len(old)
        new_total += len(new)
        ctype = classify(old, new)
        type_counts[ctype] += 1
        ol = [label_of(r) for r in old]
        nl = [label_of(r) for r in new]
        rows_out.append(
            {
                "chunk_id": cid,
                "source_zh": sz,
                "mid": mid,
                "旧出处列表": " ; ".join(ol),
                "新出处列表": " ; ".join(nl),
                "变化类型": ctype,
                "旧数量": len(old),
                "新数量": len(new),
                "数量差": len(new) - len(old),
            }
        )
        for o in old:
            if any(_covers(n, o) for n in new):
                continue
            if o.kind == KIND_CHAPTER and any(
                n.book_no == o.book_no and n.chapter == o.chapter and n.kind in (KIND_VERSE, KIND_CROSS)
                for n in new
            ):
                uncovered.append(
                    {
                        "chunk_id": cid,
                        "mid": mid,
                        "丢失出处": label_of(o),
                        "原因": "假整章",
                        "新出处列表": " ; ".join(nl),
                    }
                )
                continue
            uncovered.append(
                {
                    "chunk_id": cid,
                    "mid": mid,
                    "丢失出处": label_of(o),
                    "原因": reason_uncovered(o, new, mid, bible),
                    "新出处列表": " ; ".join(nl),
                }
            )
        # 新多出的标签
        old_set = set(ol)
        for lab in nl:
            if lab not in old_set:
                extras_new.append({"chunk_id": cid, "mid": mid, "新增多": lab, "旧": " ; ".join(ol)})

    csv_path = args.out / "regression_mapnote_diff.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "chunk_id",
                "source_zh",
                "mid",
                "旧出处列表",
                "新出处列表",
                "变化类型",
                "旧数量",
                "新数量",
                "数量差",
            ],
        )
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    print(f"extractable={extract_n}")
    print(f"old_total_refs={old_total} new_total_refs={new_total} net={new_total - old_total}")
    print("types", dict(type_counts))
    print(f"uncovered={len(uncovered)}")
    for u in uncovered:
        print(f"  UNCOV {u['原因']}: mid={u['mid']!r} lost={u['丢失出处']} new={u['新出处列表']!r} id={u['chunk_id']}")
    print(f"extras_new={len(extras_new)} sample20:")
    for e in extras_new[:20]:
        print(f"  + {e['新增多']} mid={e['mid']!r} old={e['旧']!r}")
    print(f"OUT={csv_path}")

    md = args.out / "regression_mapnote_diff.md"
    lines = [
        "# map_note 旧/新路径对照",
        "",
        f"- extractable={extract_n}",
        f"- old_refs={old_total} new_refs={new_total} net={new_total - old_total}",
        f"- types={dict(type_counts)}",
        f"- uncovered={len(uncovered)}",
        "",
        "## 未覆盖",
        "",
    ]
    if not uncovered:
        lines.append("- （无）")
    for u in uncovered:
        lines.append(
            f"- `{u['mid']}` 丢 `{u['丢失出处']}` 原因={u['原因']} 新=`{u['新出处列表']}` id={u['chunk_id']}"
        )
    lines += ["", "## 新增多抽样（最多 20）", ""]
    for e in extras_new[:20]:
        lines.append(f"- +`{e['新增多']}` mid=`{e['mid']}` 旧=`{e['旧']}`")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
