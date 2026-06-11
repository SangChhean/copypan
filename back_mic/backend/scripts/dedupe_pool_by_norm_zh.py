# -*- coding: utf-8 -*-
"""
按 normalize_zh(zh) 去重 pool.jsonl，每组保留 saved_at 最新的一条。
默认 --dry-run 只报告；--apply 会先备份再写入。

用法（在 back_mic/backend 目录）:
  python scripts/dedupe_pool_by_norm_zh.py
  python scripts/dedupe_pool_by_norm_zh.py --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from features.enhanced_translate.pool import normalize_zh

POOL = _BACKEND / "data" / "enhanced_translate" / "pool.jsonl"


def _parse_saved_at(s: str) -> str:
    return s or ""


def main() -> int:
    parser = argparse.ArgumentParser(description="pool.jsonl norm_zh 去重（保留 saved_at 最新）")
    parser.add_argument("--apply", action="store_true", help="实际写入（会先备份）")
    parser.add_argument("--path", type=Path, default=POOL)
    args = parser.parse_args()

    rows: list[dict] = []
    for raw in args.path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.strip():
            continue
        rows.append(json.loads(raw))

    best: dict[str, dict] = {}
    for rec in rows:
        zh = (rec.get("zh") or "").strip()
        norm = normalize_zh(zh)
        if not norm:
            continue
        cur = best.get(norm)
        if cur is None or _parse_saved_at(rec.get("saved_at") or "") >= _parse_saved_at(
            cur.get("saved_at") or ""
        ):
            best[norm] = {**rec, "zh": zh, "en": (rec.get("en") or "").strip(), "norm_zh": norm}

    before = len(rows)
    after = len(best)
    print(f"physical_before={before} unique_after={after} removed={before - after}")

    if before == after:
        print("无需去重。")
        return 0

    if not args.apply:
        print("dry-run 模式，未写入。确认后加 --apply 执行。")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    backup = args.path.parent / f"pool.jsonl.backup-dedupe-{stamp}"
    shutil.copy2(args.path, backup)
    print(f"backup={backup}")

    tmp = args.path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in best.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(args.path)
    print(f"written={args.path} lines={after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
