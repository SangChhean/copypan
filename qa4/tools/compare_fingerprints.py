# -*- coding: utf-8 -*-
"""对比两份 fingerprint_qa4_es_neo4j.py 产出的 JSON，只列出有差异的项。

用法:
  python compare_fingerprints.py a.json b.json
  python compare_fingerprints.py a.json b.json --out diff.json

不依赖 qa4 其它模块；不读密码。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """把嵌套 dict 展平为 path -> 可比较标量/小结构。"""
    out: Dict[str, Any] = {}
    if isinstance(obj, dict):
        if not obj:
            out[prefix or "$"] = {}
            return out
        for k, v in obj.items():
            key = "%s.%s" % (prefix, k) if prefix else str(k)
            out.update(_flatten(v, key))
        return out
    if isinstance(obj, list):
        # 列表：尝试按稳定键排序后再整段比较；否则按下标
        if obj and all(isinstance(x, dict) for x in obj):
            # constraints / indexes：按 name 排序后比整段 JSON
            try:
                norm = sorted(obj, key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
            except Exception:
                norm = obj
            out[prefix] = norm
            return out
        out[prefix] = obj
        return out
    out[prefix] = obj
    return out


def _norm_val(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# 比对时忽略的易变字段
IGNORE_PREFIXES = (
    "generated_at_unix",
    "host_hint",
    "errors",
)


def _ignored(path: str) -> bool:
    for p in IGNORE_PREFIXES:
        if path == p or path.startswith(p + "."):
            return True
    return False


def diff_fingerprints(a: dict, b: dict, *, label_a: str = "a", label_b: str = "b") -> List[dict]:
    fa = _flatten(a)
    fb = _flatten(b)
    keys = sorted(set(fa) | set(fb))
    rows: List[dict] = []
    for k in keys:
        if _ignored(k):
            continue
        va = fa.get(k, "__MISSING__")
        vb = fb.get(k, "__MISSING__")
        if _norm_val(va) != _norm_val(vb):
            rows.append({"path": k, label_a: va, label_b: vb})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Diff two qa4 fingerprint JSON files")
    ap.add_argument("a", help="first fingerprint JSON (e.g. local)")
    ap.add_argument("b", help="second fingerprint JSON (e.g. server)")
    ap.add_argument("--label-a", default="local")
    ap.add_argument("--label-b", default="server")
    ap.add_argument("--out", help="optional JSON output of diff rows")
    args = ap.parse_args()

    pa, pb = Path(args.a), Path(args.b)
    if not pa.is_file():
        print("文件不存在: %s" % pa, file=sys.stderr)
        return 2
    if not pb.is_file():
        print("文件不存在: %s" % pb, file=sys.stderr)
        return 2

    rows = diff_fingerprints(
        _load(pa),
        _load(pb),
        label_a=args.label_a,
        label_b=args.label_b,
    )
    report = {
        "a": str(pa),
        "b": str(pb),
        "diff_count": len(rows),
        "diffs": rows,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")

    print("对比: %s  vs  %s" % (pa.name, pb.name))
    print("差异项数: %d" % len(rows))
    if not rows:
        print("(无差异)")
        return 0

    # 抽样相关差异单独标出：区分「抽到的文档不同」vs「同一批 id 内容不同」
    sample_rows = [
        r
        for r in rows
        if r["path"].endswith("sample_ids_sha256")
        or r["path"].endswith("sample_content_sha256")
    ]
    if sample_rows:
        print("")
        print("【ES 抽样/内容哈希】")
        for r in sample_rows:
            kind = (
                "抽到的 id 不同"
                if r["path"].endswith("sample_ids_sha256")
                else "内容哈希不同（若 sample_ids 相同则同文档内容不一致）"
            )
            print(
                "  %s  (%s)\n    %s=%s\n    %s=%s"
                % (
                    r["path"],
                    kind,
                    args.label_a,
                    _norm_val(r[args.label_a]),
                    args.label_b,
                    _norm_val(r[args.label_b]),
                )
            )

    # 表格：path | local | server
    w0 = max(4, max(len(r["path"]) for r in rows))
    w0 = min(w0, 72)
    print("")
    print("%-*s | %-40s | %-40s" % (w0, "path", args.label_a[:40], args.label_b[:40]))
    print("-" * (w0 + 3 + 40 + 3 + 40))
    for r in rows:
        va = _norm_val(r[args.label_a])
        vb = _norm_val(r[args.label_b])
        if len(va) > 40:
            va = va[:37] + "..."
        if len(vb) > 40:
            vb = vb[:37] + "..."
        print("%-*s | %-40s | %-40s" % (w0, r["path"][:w0], va, vb))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
