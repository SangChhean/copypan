# -*- coding: utf-8 -*-
"""
只读校验：按 normalize_zh(zh) 分组检查 pool.jsonl 重复条目。
用法（在 back_mic/backend 目录）:
  python scripts/validate_pool_duplicates.py
  python scripts/validate_pool_duplicates.py --path data/enhanced_translate/pool.jsonl.backup-20260611
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from features.enhanced_translate.pool import normalize_zh

DEFAULT_POOL = _BACKEND / "data" / "enhanced_translate" / "pool.jsonl"


def _load_rows(path: Path) -> list[tuple[int, dict]]:
    rows: list[tuple[int, dict]] = []
    if not path.is_file():
        return rows
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            rows.append((line_no, json.loads(line)))
        except json.JSONDecodeError as e:
            print(f"[WARN] L{line_no} 无效 JSON: {e}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 pool.jsonl norm_zh 重复组")
    parser.add_argument("--path", type=Path, default=DEFAULT_POOL, help="pool.jsonl 路径")
    args = parser.parse_args()

    rows = _load_rows(args.path)
    groups: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for line_no, rec in rows:
        zh = (rec.get("zh") or "").strip()
        norm = normalize_zh(zh)
        if not norm:
            continue
        groups[norm].append((line_no, rec))

    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    physical = len(rows)
    unique = len(groups)

    print(f"file={args.path}")
    print(f"physical_lines={physical}")
    print(f"unique_norm_zh={unique}")
    print(f"duplicate_groups={len(dup_groups)}")
    print(f"extra_physical_rows={physical - unique}")

    if not dup_groups:
        print("结论: 无归一化重复组。")
        return 0

    print("\n--- 重复组明细（load 时末条覆盖 / lookup 命中末条）---")
    for i, (norm, items) in enumerate(sorted(dup_groups.items(), key=lambda x: -len(x[1])), 1):
        print(f"\n[组 {i}] norm_zh={norm[:80]}{'…' if len(norm) > 80 else ''}  count={len(items)}")
        for line_no, rec in items:
            zh = (rec.get("zh") or "").strip()
            en = (rec.get("en") or "").strip()
            saved = rec.get("saved_at") or ""
            print(f"  L{line_no} saved_at={saved}")
            print(f"    zh: {zh[:120]}{'…' if len(zh) > 120 else ''}")
            print(f"    en: {en[:120]}{'…' if len(en) > 120 else ''}")

    print(
        "\nlookup_line_en / update_record 行为: "
        "_load_pool_file 按文件顺序遍历，同 norm_zh 后者覆盖前者；"
        "lookup 返回缓存中唯一条目；update_record 更新该条目后 _write_pool 整文件重写为每 norm 一行。"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
