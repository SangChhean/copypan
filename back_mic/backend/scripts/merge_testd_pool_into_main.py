# -*- coding: utf-8 -*-
"""
一次性脚本：将 testD pool 中 saved_at >= 2026-06-10 的新条目合并入主站 pool。
用法（在 back_mic/backend 目录）: python scripts/merge_testd_pool_into_main.py
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from features.enhanced_translate.pool import zh_eq, normalize_zh

MAIN_POOL = _BACKEND / "data" / "enhanced_translate" / "pool.jsonl"
TESTD_POOL = _BACKEND.parent.parent / "testD" / "backend" / "Additional-pool" / "pool.jsonl"
CUTOFF = "2026-06-10"
BACKUP = MAIN_POOL.parent / "pool.jsonl.backup-20260611"


def _load_lines(path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def main() -> None:
    main_rows = _load_lines(MAIN_POOL)
    testd_rows = _load_lines(TESTD_POOL)
    candidates = [
        r for r in testd_rows
        if (r.get("saved_at") or "")[:10] >= CUTOFF
    ]

    merged_norms = {normalize_zh(r.get("zh") or "") for r in main_rows}
    to_add: list[dict] = []
    skipped = 0
    skip_log: list[str] = []
    for rec in candidates:
        zh = (rec.get("zh") or "").strip()
        en = (rec.get("en") or "").strip()
        if not zh or not en:
            skip_log.append(f"SKIP empty zh/en saved_at={rec.get('saved_at', '')[:19]}")
            continue
        norm = normalize_zh(zh)
        zh_eq_dup = any(zh_eq(zh, existing.get("zh") or "") for existing in main_rows)
        norm_dup = norm in merged_norms
        if zh_eq_dup or norm_dup:
            skipped += 1
            reason = "zh_eq" if zh_eq_dup else "norm_zh"
            skip_log.append(
                f"SKIP dup({reason}) zh={zh[:60]}{'…' if len(zh) > 60 else ''} "
                f"saved_at={rec.get('saved_at', '')[:19]}"
            )
            continue
        merged_norms.add(norm)
        row = {**rec, "zh": zh, "en": en, "norm_zh": norm}
        to_add.append(row)
        print(
            f"ADD norm={norm[:40]}{'…' if len(norm) > 40 else ''} "
            f"saved_at={rec.get('saved_at', '')[:19]}"
        )

    print(f"candidates={len(candidates)} skipped_dup={skipped} to_add={len(to_add)}")
    if skip_log:
        print("--- skip detail ---")
        for line in skip_log:
            print(line)
    if not to_add:
        print(f"main_pool_lines={len(main_rows)} (no changes)")
        return

    if MAIN_POOL.is_file():
        shutil.copy2(MAIN_POOL, BACKUP)
        print(f"backup={BACKUP}")

    with MAIN_POOL.open("a", encoding="utf-8", newline="\n") as f:
        for row in to_add:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    final = len(_load_lines(MAIN_POOL))
    print(f"main_pool_final_lines={final}")


if __name__ == "__main__":
    main()
