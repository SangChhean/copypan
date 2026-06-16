# -*- coding: utf-8 -*-
"""校验主站 pool.jsonl 完整性。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from features.enhanced_translate.pool import normalize_zh

_POOL_FILE = _BACKEND / "data" / "enhanced_translate" / "pool.jsonl"


def main() -> int:
    path = _POOL_FILE
    if not path.is_file():
        print("通过：0 条（文件不存在）")
        return 0

    errors: list[str] = []
    seen_norm: set[str] = set()
    count = 0

    with path.open(encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            count += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"L{line_no}: JSON 错误: {e}")
                continue
            zh = (rec.get("zh") or "").strip()
            en = (rec.get("en") or "").strip()
            if not zh or not en:
                errors.append(f"L{line_no}: 缺少 zh 或 en")
                continue
            norm = normalize_zh(zh)
            if norm in seen_norm:
                errors.append(f"L{line_no}: 重复 norm_zh={norm}")
            seen_norm.add(norm)

    if errors:
        print(f"失败：{len(errors)} 个问题")
        for e in errors[:20]:
            print(e)
        return 1

    print(f"通过：{count} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
