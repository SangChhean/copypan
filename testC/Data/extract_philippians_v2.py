import json
from pathlib import Path

import ijson


INPUT_PATH = Path(r"D:\copypan\testC\Data\life.json")
OUTPUT_PATH = Path(r"D:\copypan\testC\Data\philippians_raw.json")
PREFIX = "life_50-"
KEEP_FIELDS = ("id", "type", "text", "title", "source")


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    first = True

    with INPUT_PATH.open("rb") as fin, OUTPUT_PATH.open("w", encoding="utf-8") as fout:
        fout.write("[\n")
        for item in ijson.items(fin, "item"):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", ""))
            if not item_id.startswith(PREFIX):
                continue

            out_item = {k: item.get(k) for k in KEEP_FIELDS}
            if not first:
                fout.write(",\n")
            fout.write(json.dumps(out_item, ensure_ascii=False))
            first = False
            count += 1
        fout.write("\n]\n")

    print(f"共提取 {count} 条")


if __name__ == "__main__":
    main()
