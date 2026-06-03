"""
从 life.json 流式提取 id 以 "life_49-" 开头的记录，
仅保留 id, type, text, title, source 字段，写入 ephesians_raw.json。
"""

import ijson
import json
from pathlib import Path

INPUT_PATH = Path(__file__).with_name("life.json")
OUTPUT_PATH = Path(__file__).with_name("ephesians_raw.json")

ID_PREFIX = "life_49-"
KEEP_FIELDS = ("id", "type", "text", "title", "source")


def main() -> int:
    count = 0

    with open(INPUT_PATH, "rb") as fin, open(OUTPUT_PATH, "w", encoding="utf-8") as fout:
        fout.write("[\n")

        # 'item' 表示顶层数组里的每个元素，逐条产出，避免一次性载入内存
        records = ijson.items(fin, "item")

        first = True
        for rec in records:
            rec_id = rec.get("id")
            if not isinstance(rec_id, str) or not rec_id.startswith(ID_PREFIX):
                continue

            filtered = {k: rec.get(k) for k in KEEP_FIELDS if k in rec}

            if not first:
                fout.write(",\n")
            first = False

            json.dump(filtered, fout, ensure_ascii=False)

            count += 1
            if count % 500 == 0:
                print(f"  ...已提取 {count} 条")

        fout.write("\n]\n")

    print(f"完成：共提取 {count} 条记录 -> {OUTPUT_PATH.name}")
    return count


if __name__ == "__main__":
    main()
