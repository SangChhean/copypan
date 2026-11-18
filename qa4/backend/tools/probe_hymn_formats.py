# -*- coding: utf-8 -*-
"""诗歌首数格式测试集探针。

参数对齐 probe_scripture_formats：--cases --out --only --no-notes
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
_QA4 = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_CASES = _QA4 / "notes" / "hymn_format_cases_v2.csv"
DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\formats")


def load_cases(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def run_one(input_text: str) -> dict[str, Any]:
    from hymn.parse import format_hymn_refs, parse_hymn_refs

    try:
        refs = parse_hymn_refs(input_text)
        actual = format_hymn_refs(refs)
        return {
            "actual": actual,
            "refs_n": len(refs),
            "truncated": bool(refs.truncated),
            "match": "",
            "error": "",
        }
    except Exception as e:
        return {
            "actual": "",
            "refs_n": 0,
            "truncated": False,
            "match": "报错",
            "error": f"{type(e).__name__}: {e}",
        }


def run_cases(cases: list[dict[str, str]], out_dir: Path, only: Optional[set[str]]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_out = []
    by_group: dict[str, Counter] = defaultdict(Counter)
    mismatches = []
    errors = []

    for row in cases:
        cid = row.get("id") or ""
        if only and cid not in only:
            continue
        got = run_one(row.get("input") or "")
        expected = (row.get("expected") or "").strip()
        if got["error"]:
            got["match"] = "报错"
            errors.append(cid)
        elif got["actual"] == expected:
            got["match"] = "一致"
        else:
            got["match"] = "不一致"
            mismatches.append(cid)
        by_group[row.get("group") or ""][got["match"]] += 1
        rows_out.append(
            {
                "id": cid,
                "group": row.get("group") or "",
                "input": row.get("input") or "",
                "expected": expected,
                "actual": got["actual"],
                "match": got["match"],
                "refs_n": got["refs_n"],
                "truncated": got["truncated"],
                "error": got["error"],
                "note": row.get("note") or "",
            }
        )
        if only:
            print(f"{cid}\t{got['match']}\texpected={expected!r}\tactual={got['actual']!r}")

    csv_path = out_dir / "hymn_format_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "group",
                "input",
                "expected",
                "actual",
                "match",
                "refs_n",
                "truncated",
                "error",
                "note",
            ],
        )
        w.writeheader()
        w.writerows(rows_out)

    totals = Counter(r["match"] for r in rows_out)
    md = [
        "# 诗歌首数格式探针",
        "",
        f"- 用例：{len(rows_out)}",
        f"- 合计：{dict(totals)}",
        f"- 不一致：{', '.join(mismatches) or '（无）'}",
        f"- 报错：{', '.join(errors) or '（无）'}",
        "",
        "## 分组",
        "",
    ]
    for g, c in by_group.items():
        md.append(f"- {g}：{dict(c)}")
    if mismatches:
        md += ["", "## 不一致明细", ""]
        for r in rows_out:
            if r["match"] != "不一致":
                continue
            md.append(f"- {r['id']} input=`{r['input']}` expected=`{r['expected']}` actual=`{r['actual']}`")
    (out_dir / "hymn_format_results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {
        "n": len(rows_out),
        "totals": dict(totals),
        "mismatch_ids": mismatches,
        "error_ids": errors,
        "csv": str(csv_path),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--only", default="", help="逗号分隔 id")
    ap.add_argument("--no-notes", action="store_true", help="不写 qa4/notes 摘要（本探针默认只写 --out）")
    args = ap.parse_args(argv)
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    cases = load_cases(args.cases)
    summary = run_cases(cases, args.out, only)
    # --no-notes：与 scripture 探针对齐；本工具本就不写 notes，仅保留开关
    _ = args.no_notes
    print(
        f"HYMN_PROBE n={summary['n']} totals={summary['totals']} "
        f"mismatch={len(summary['mismatch_ids'])} out={summary['csv']}"
    )
    return 0 if not summary["mismatch_ids"] and not summary["error_ids"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
