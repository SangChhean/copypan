# -*- coding: utf-8 -*-
"""合并 draft.jsonl 进主站 enhanced_translate pool。"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from features.enhanced_translate import pool as pool_mod
from features.enhanced_translate.pool import normalize_zh, reload_pool

_POOL_DIR = _BACKEND / "data" / "enhanced_translate"
_POOL_FILE = _POOL_DIR / "pool.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="合并 draft 进 pool.jsonl")
    parser.add_argument("draft", type=Path, help="draft.jsonl 路径")
    parser.add_argument("--force", action="store_true", help="同 norm_zh 时强制覆盖")
    args = parser.parse_args()

    reload_pool(force=True)
    existing = dict(pool_mod._cache_by_norm)
    added = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    with args.draft.open(encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            rec = json.loads(line)
            zh = (rec.get("zh") or "").strip()
            en = (rec.get("en") or "").strip()
            if not zh or not en:
                continue
            norm = normalize_zh(zh)
            if norm in existing and not args.force:
                skipped += 1
                continue
            existing[norm] = {
                "zh": zh,
                "en": en,
                "norm_zh": norm,
                "saved_at": rec.get("saved_at") or now,
                "prompt_version": rec.get("prompt_version") or "",
                "source": rec.get("source") or "manual",
            }
            added += 1

    if added == 0:
        print(f"新增/更新 0，跳过 {skipped}，合计 {len(existing)} 条")
        return 0

    _POOL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _POOL_FILE.with_suffix(".jsonl.tmp")
    if _POOL_FILE.is_file():
        shutil.copy2(_POOL_FILE, _POOL_FILE.with_suffix(".jsonl.bak"))
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in existing.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(_POOL_FILE)
    reload_pool(force=True)
    print(f"新增/更新 {added}，跳过 {skipped}，合计 {len(existing)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
