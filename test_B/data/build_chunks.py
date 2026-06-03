"""
从 ephesians_raw.json 构建检索用 chunks：
- 仅保留 type == "text" 的记录
- 字段：chunk_id (来自 id), text, title, source (仅保留原 source 的中文首项，单元素数组)
- 输出 ephesians_chunks.json：顶层为数组，每个 chunk 单独占一行
"""

import json
import random
from pathlib import Path

INPUT_PATH = Path(__file__).with_name("ephesians_raw.json")
OUTPUT_PATH = Path(__file__).with_name("ephesians_chunks.json")


def build_chunk(rec: dict) -> dict:
    src = rec.get("source")
    # 原 source 形如 ["（中文出处）", "(English source)"]，只保留中文首项
    if isinstance(src, list) and src:
        source_field = [src[0]]
    elif isinstance(src, str):
        source_field = [src]
    else:
        source_field = []

    return {
        "chunk_id": rec.get("id"),
        "text": rec.get("text"),
        "title": rec.get("title"),
        "source": source_field,
    }


def main() -> None:
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = [build_chunk(r) for r in data if r.get("type") == "text"]

    # 写成 JSON 数组，但让每个 chunk 单独占一行，便于 diff / grep
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("[\n")
        for i, ch in enumerate(chunks):
            line = json.dumps(ch, ensure_ascii=False)
            sep = "," if i < len(chunks) - 1 else ""
            f.write(line + sep + "\n")
        f.write("]\n")

    print(f"完成：共生成 {len(chunks)} 个 chunk -> {OUTPUT_PATH.name}")

    if chunks:
        k = min(3, len(chunks))
        samples = random.sample(chunks, k)
        print(f"\n随机抽样 {k} 条验证格式：")
        for i, s in enumerate(samples, 1):
            print(f"\n--- 样例 {i} ---")
            print(json.dumps(s, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
