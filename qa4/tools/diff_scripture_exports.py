# -*- coding: utf-8 -*-
"""对比本机与服务器 Scripture 导出（cypher-shell --format plain）。

输入格式（两边相同）:
  第一行表头：ref, n
  之后每行："帖后三5", 2

输出:
  a) only_server: 只在服务器有的 ref
  b) only_local: 只在本机有的 ref
  c) count_mismatch: 两边都有但 SUPPORTED_BY 数量不同

用法:
  python diff_scripture_exports.py --local local.txt --server server.txt
  python diff_scripture_exports.py --local local.txt --server server.txt --out diff.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict


_LINE_RE = re.compile(r'^\s*"(?P<ref>(?:\\.|[^"\\])*)"\s*,\s*(?P<n>-?\d+)\s*$')


def parse_plain_export(text: str) -> Dict[str, int]:
    """解析 cypher-shell --format plain 的 ref,n 导出。"""
    lines = [ln.rstrip("\r") for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("空文件")
    # 跳过表头（允许 ref, n / ref,n）
    start = 0
    header = lines[0].strip().lower().replace(" ", "")
    if header in {"ref,n", "ref,count"} or header.startswith("ref,"):
        start = 1
    out: Dict[str, int] = {}
    for i, ln in enumerate(lines[start:], start=start + 1):
        m = _LINE_RE.match(ln)
        if m:
            ref = m.group("ref").replace('\\"', '"').replace("\\\\", "\\")
            out[ref] = int(m.group("n"))
            continue
        # 兼容无引号行
        if "," in ln:
            left, right = ln.rsplit(",", 1)
            ref = left.strip().strip('"')
            out[ref] = int(right.strip())
            continue
        raise ValueError("第 %d 行无法解析: %r" % (i, ln[:80]))
    return out


def diff_maps(local: Dict[str, int], server: Dict[str, int]) -> dict:
    only_server = sorted(set(server) - set(local))
    only_local = sorted(set(local) - set(server))
    both = set(local) & set(server)
    count_mismatch = sorted(
        [
            {"ref": r, "local_n": local[r], "server_n": server[r]}
            for r in both
            if local[r] != server[r]
        ],
        key=lambda x: x["ref"],
    )
    return {
        "local_n": len(local),
        "server_n": len(server),
        "only_server": only_server,
        "only_local": only_local,
        "count_mismatch": count_mismatch,
        "only_server_n": len(only_server),
        "only_local_n": len(only_local),
        "count_mismatch_n": len(count_mismatch),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Diff Scripture export plain files")
    ap.add_argument("--local", required=True, help="local export .txt")
    ap.add_argument("--server", required=True, help="server export .txt")
    ap.add_argument("--out", help="optional JSON report")
    args = ap.parse_args()

    local = parse_plain_export(Path(args.local).read_text(encoding="utf-8"))
    server = parse_plain_export(Path(args.server).read_text(encoding="utf-8"))
    report = diff_maps(local, server)

    print("local_n=%d server_n=%d" % (report["local_n"], report["server_n"]))
    print("a) only_server (%d):" % report["only_server_n"])
    for r in report["only_server"]:
        print("  %s  (server_n=%d)" % (r, server[r]))
    print("b) only_local (%d):" % report["only_local_n"])
    for r in report["only_local"]:
        print("  %s  (local_n=%d)" % (r, local[r]))
    print("c) count_mismatch (%d):" % report["count_mismatch_n"])
    for row in report["count_mismatch"]:
        print(
            "  %s  local=%d server=%d"
            % (row["ref"], row["local_n"], row["server_n"])
        )

    if args.out:
        Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
