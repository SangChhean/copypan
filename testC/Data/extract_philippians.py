import json
from pathlib import Path


INPUT_PATH = Path(r"D:\copypan\TestC\Data\life.json")
OUTPUT_PATH = Path(r"D:\copypan\testC\Data\life_philippians.json")
PREFIX = "life_50-"


def iter_top_level_array(path: Path):
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as f:
        buf = ""
        eof = False
        started = False

        while True:
            if not eof and len(buf) < 65536:
                chunk = f.read(65536)
                if chunk == "":
                    eof = True
                else:
                    buf += chunk

            if not started:
                stripped = buf.lstrip()
                if not stripped and not eof:
                    continue
                if not stripped:
                    raise ValueError("JSON 内容为空")
                if stripped[0] != "[":
                    raise ValueError("JSON 顶层不是数组")
                buf = stripped[1:]
                started = True

            buf = buf.lstrip()
            if not buf:
                if eof:
                    break
                continue

            if buf[0] == "]":
                break
            if buf[0] == ",":
                buf = buf[1:]
                continue

            try:
                item, idx = decoder.raw_decode(buf)
            except json.JSONDecodeError:
                if eof:
                    raise
                continue

            yield item
            buf = buf[idx:]


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    first = True
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        f.write("[\n")
        for item in iter_top_level_array(INPUT_PATH):
            if isinstance(item, dict) and str(item.get("id", "")).startswith(PREFIX):
                if not first:
                    f.write(",\n")
                f.write(json.dumps(item, ensure_ascii=False))
                first = False
                count += 1
        f.write("\n]\n")

    print(f"共提取 {count} 条，已保存到 D:\\copypan\\testC\\Data\\life_philippians.json")


if __name__ == "__main__":
    main()
