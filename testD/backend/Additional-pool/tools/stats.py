# -*- coding: utf-8 -*-
"""Additional Pool 条数统计。"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from testD.backend.additional_pool import _POOL_FILE, reload_pool


def main() -> int:
    n = reload_pool(force=True)
    print(f"pool: {_POOL_FILE}")
    print(f"条数: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
