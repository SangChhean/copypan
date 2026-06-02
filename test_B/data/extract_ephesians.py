# 依赖：ijson（流式 JSON 解析，避免一次性加载 ~950MB 文件到内存）
# 若环境中未安装，请先执行：
#     pip install ijson
"""
从 A:\\copypan\\test_B\\data\\life.json 中流式提取 id 以 "life_49-" 开头的记录，
每条只保留 id / type / text / title / source 五个字段，结果写入同目录 ephesians_raw.json
（UTF-8，缩进 2 空格，非 ASCII 不转义），并打印提取条数。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import ijson
except ImportError as e:
    print("缺少依赖 ijson，请先执行：pip install ijson", file=sys.stderr)
    raise SystemExit(1) from e


DATA_DIR = Path(__file__).resolve().parent
SRC_PATH = DATA_DIR / "life.json"
DST_PATH = DATA_DIR / "ephesians_raw.json"
ID_PREFIX = "life_49-"
KEEP_FIELDS = ("id", "type", "text", "title", "source")


def main() -> int:
    if not SRC_PATH.is_file():
        print(f"源文件不存在: {SRC_PATH}", file=sys.stderr)
        return 1

    extracted: list[dict] = []
    with SRC_PATH.open("rb") as fp:
        # ijson 默认从根开始解析，'item' 匹配顶层数组中的每个元素
        for record in ijson.items(fp, "item"):
            rid = record.get("id") if isinstance(record, dict) else None
            if not (isinstance(rid, str) and rid.startswith(ID_PREFIX)):
                continue
            extracted.append({k: record.get(k) for k in KEEP_FIELDS})

    with DST_PATH.open("w", encoding="utf-8") as fp:
        json.dump(extracted, fp, ensure_ascii=False, indent=2)

    print(f"提取完成：共 {len(extracted)} 条 -> {DST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
