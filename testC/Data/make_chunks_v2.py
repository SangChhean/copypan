import json
import random
from pathlib import Path


INPUT_PATH = Path(r"D:\copypan\testC\Data\philippians_raw.json")
OUTPUT_PATH = Path(r"D:\copypan\testC\Data\philippians_chunks.json")


def main() -> None:
    with INPUT_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue

        source = item.get("source")
        source_first = source[0] if isinstance(source, list) and len(source) > 0 else ""
        title_str = item.get("title", "")
        if "，" in title_str:
            parts = title_str.split("，", 1)
            book_title = parts[0]
            message_title = parts[1]
        else:
            book_title = title_str
            message_title = ""

        chunk = {
            "chunk_id": item.get("id", "").replace("life_50-", "philippians-"),
            "text": item.get("text", ""),
            "book_title": book_title,
            "message_title": message_title,
            "source_zh": source_first,
        }
        chunks.append(chunk)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        f.write("[\n")
        for i, chunk in enumerate(chunks):
            line = json.dumps(chunk, ensure_ascii=False)
            if i < len(chunks) - 1:
                f.write(line + ",\n")
            else:
                f.write(line + "\n")
        f.write("]\n")

    print(f"共生成 {len(chunks)} 个 chunk")
    print("随机抽样 3 条：")
    sample_size = min(3, len(chunks))
    for s in random.sample(chunks, sample_size):
        print(json.dumps(s, ensure_ascii=False))


if __name__ == "__main__":
    main()
