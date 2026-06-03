"""
从 ephesians_raw.json 构建 chunks v2：
- 仅保留 type == "text" 的记录
- 字段：chunk_id, text, book_title, message_title, source_zh
- 输出 ephesians_chunks_v2.json
"""

import json
import random
from pathlib import Path

INPUT_PATH = Path(r"A:\copypan\test_B\data\ephesians_raw.json")
OUTPUT_PATH = Path(r"A:\copypan\test_B\data\ephesians_chunks_v2.json")


def split_title(title: str) -> tuple[str, str]:
    """按第一个「，」拆分 title 为 book_title 与 message_title。"""
    title = title or ""
    if "，" in title:
        book_title, message_title = title.split("，", 1)
        return book_title, message_title
    return title, ""


def build_chunk(rec: dict) -> dict:
    title = rec.get("title") or ""
    book_title, message_title = split_title(title)

    src = rec.get("source")
    if isinstance(src, list) and src:
        source_zh = src[0] if isinstance(src[0], str) else str(src[0])
    else:
        source_zh = ""

    raw_id = rec.get("id") or ""
    chunk_id = raw_id.replace("life_49-", "ephesians-", 1)

    return {
        "chunk_id": chunk_id,
        "text": rec.get("text"),
        "book_title": book_title,
        "message_title": message_title,
        "source_zh": source_zh,
    }


def chunk_to_line(chunk: dict) -> str:
    """单条 chunk 一行 JSON，字段顺序固定。"""
    ordered = {
        "chunk_id": chunk["chunk_id"],
        "text": chunk["text"],
        "book_title": chunk["book_title"],
        "message_title": chunk["message_title"],
        "source_zh": chunk["source_zh"],
    }
    return json.dumps(ordered, ensure_ascii=False)


def main() -> None:
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = [build_chunk(r) for r in data if r.get("type") == "text"]

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("[\n")
        for i, ch in enumerate(chunks):
            sep = "," if i < len(chunks) - 1 else ""
            f.write(chunk_to_line(ch) + sep + "\n")
        f.write("]\n")

    print(f"chunk 总数：{len(chunks)}")
    print(f"已保存：{OUTPUT_PATH}")

    if chunks:
        k = min(3, len(chunks))
        samples = random.sample(chunks, k)
        print(f"\n随机抽样 {k} 条验证格式：")
        for i, s in enumerate(samples, 1):
            print(f"\n--- 样例 {i} ---")
            print(chunk_to_line(s))


if __name__ == "__main__":
    main()
