# -*- coding: utf-8 -*-
"""3a 读经行整行解析汇总（离线、只读）。

读 qa4/data/graph_annotations/truth_dictionary_3a3b.json，对每个词条 content_3a 首行的
「读经：」整行解析（不按逗号切开），输出：
  有读经行的词条数、至少解析出一个出处的行数、出处总数（及能在 bible_data 找到的数）、
  零出处行数及词名、疑似遗漏行数及词名（判定照搬 probe6 heuristic_miss）。
整章与跨章写法单独计数，不列原文。

用法：python qa4/backend/tools/stage2_scripture_report.py [--out DIR] [--td PATH] [--dump-fixtures DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripture.bible_text import BibleText  # noqa: E402
from scripture.normalize import (  # noqa: E402
    heuristic_miss,
    parse_refs,
    reading_line_of,
    ref_in_bible,
)

QA4_ROOT = _BACKEND.parent
DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\stage2")
EXPECT = {
    # 2026-11-17 normalize v2 补强后（整章简写/跨章合并/空白压缩等）更新；详见 scripture_normalize_v2_notes.md
    "n_entries_with_reading": 2365,
    "n_lines_ge1_ref": 2364,
    "n_refs_total": 23067,
    "n_zero_ref_lines": 1,
    "miss_heuristic_n": 22,
}


def run(td_path: Path, bible_dir: Path) -> dict:
    bible = BibleText(bible_dir)
    rows = json.loads(td_path.read_text(encoding="utf-8"))
    n_with = n_ge1 = total = inbib = 0
    kinds: Counter = Counter()
    zero: list[dict] = []
    miss: list[dict] = []
    for row in rows:
        line = reading_line_of(row.get("content_3a") or "")
        if line is None:
            continue
        n_with += 1
        refs = parse_refs(line, bible=bible)
        total += len(refs)
        if refs:
            n_ge1 += 1
        else:
            zero.append({"title": row.get("title"), "line": line})
        for r in refs:
            kinds[r.kind] += 1
            if ref_in_bible(r, bible):
                inbib += 1
        if heuristic_miss(line, len(refs)):
            miss.append({"title": row.get("title"), "line": line, "n_refs": len(refs)})
    return {
        "n_entries_with_reading": n_with,
        "n_lines_ge1_ref": n_ge1,
        "n_refs_total": total,
        "n_in_bible_data": inbib,
        "kinds": dict(kinds),
        "n_zero_ref_lines": len(zero),
        "zero_ref_titles": [z["title"] for z in zero],
        "miss_heuristic_n": len(miss),
        "miss_titles": [m["title"] for m in miss],
        "_zero_rows": zero,
        "_miss_rows": miss,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--td",
        type=Path,
        default=QA4_ROOT / "data" / "graph_annotations" / "truth_dictionary_3a3b.json",
    )
    ap.add_argument("--bible-dir", type=Path, default=QA4_ROOT / "data" / "bible_data")
    ap.add_argument("--dump-fixtures", type=Path, default=None, help="把零出处/疑似遗漏行写成测试夹具")
    args = ap.parse_args(argv)

    if not args.td.is_file():
        print("跳过：缺少 data/graph_annotations/truth_dictionary_3a3b.json")
        return 0
    res = run(args.td, args.bible_dir)
    summary = {k: v for k, v in res.items() if not k.startswith("_")}
    summary["expect"] = EXPECT
    summary["diff"] = {
        k: {"actual": summary[k], "expect": v} for k, v in EXPECT.items() if summary[k] != v
    }
    args.out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out / f"stage2_scripture_report_{ts}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.dump_fixtures:
        args.dump_fixtures.mkdir(parents=True, exist_ok=True)
        (args.dump_fixtures / "reading_lines_zero.json").write_text(
            json.dumps(
                [{"title": z["title"], "line": z["line"]} for z in res["_zero_rows"]],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (args.dump_fixtures / "reading_lines_miss.json").write_text(
            json.dumps(
                [
                    {"title": m["title"], "line": m["line"], "n_refs": m["n_refs"]}
                    for m in res["_miss_rows"]
                ],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    for k in EXPECT:
        mark = "OK " if summary[k] == EXPECT[k] else "DIFF"
        print(f"{mark} {k}: actual={summary[k]} expect={EXPECT[k]}")
    print(f"n_in_bible_data={summary['n_in_bible_data']} kinds={summary['kinds']}")
    print(f"zero_ref_titles={summary['zero_ref_titles']}")
    print(f"OUT={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
