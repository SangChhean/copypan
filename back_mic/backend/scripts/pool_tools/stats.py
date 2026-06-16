# -*- coding: utf-8 -*-
"""主站 enhanced_translate pool 条数统计。"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from features.enhanced_translate.pool import reload_pool

_POOL_FILE = _BACKEND / "data" / "enhanced_translate" / "pool.jsonl"


def main() -> int:
    n = reload_pool(force=True)
    print(f"pool: {_POOL_FILE}")
    print(f"条数: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
