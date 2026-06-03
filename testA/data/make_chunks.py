import json


INPUT = r"E:\copypan\testA\data\life_48.json"
OUTPUT = r"E:\copypan\testA\data\chunks.json"


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        records = json.load(f)

    chunks = []
    for item in records:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue

        source = item.get("source")
        if isinstance(source, list) and source:
            source_first = source[0]
        else:
            source_first = ""

        chunk = {
            "chunk_id": item.get("id", ""),
            "text": item.get("text", ""),
            "title": item.get("title", ""),
            "source": source_first,
        }
        chunks.append(chunk)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("[\n")
        for i, chunk in enumerate(chunks):
            suffix = ",\n" if i < len(chunks) - 1 else "\n"
            f.write(json.dumps(chunk, ensure_ascii=False) + suffix)
        f.write("]\n")


if __name__ == "__main__":
    main()
