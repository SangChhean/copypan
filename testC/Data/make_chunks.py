import json
from pathlib import Path


INPUT_PATH = Path(r"D:\copypan\testC\Data\life_philippians.json")
OUTPUT_PATH = Path(r"D:\copypan\testC\Data\life_philippians_chunks.json")


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

        chunks.append(
            {
                "id": item.get("id", ""),
                "text": item.get("text", ""),
                "title": item.get("title", ""),
                "source": source_first,
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"共生成 {len(chunks)} 个 chunk，已保存到 life_philippians_chunks.json")


if __name__ == "__main__":
    main()
