# -*- coding: utf-8 -*-
"""命令行查询 Additional Pool。"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from testD.backend.additional_pool import lookup_line_en, normalize_zh, reload_pool


def main() -> int:
    if len(sys.argv) < 2:
        print('用法: python lookup.py "一\\t生命"')
        return 1
    zh = sys.argv[1]
    reload_pool(force=True)
    norm = normalize_zh(zh)
    en = lookup_line_en(zh)
    print(f"norm_zh: {norm}")
    if en:
        print(f"en: {en}")
    else:
        print("未命中")
    return 0 if en else 1


if __name__ == "__main__":
    raise SystemExit(main())
