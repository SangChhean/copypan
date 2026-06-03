import json
from pathlib import Path


INPUT_PATH = Path(r"E:\copypan\testA\data\life.json")
OUTPUT_PATH = Path(r"E:\copypan\testA\data\life_48.json")
TARGET_PREFIX = "life_48-"
CHUNK_SIZE = 1024 * 1024  # 1MB


def iter_top_level_array_items(file_path: Path):
    """
    Incrementally parse a top-level JSON array and yield each item.
    This avoids loading the full file into memory.
    """
    decoder = json.JSONDecoder()
    buf = ""
    started = False
    ended = False

    with file_path.open("r", encoding="utf-8") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            buf += chunk
            pos = 0

            while True:
                # Skip whitespace and commas between items.
                while pos < len(buf) and buf[pos] in " \t\r\n,":
                    pos += 1

                if not started:
                    if pos >= len(buf):
                        break
                    if buf[pos] != "[":
                        raise ValueError("Input JSON is not a top-level array.")
                    started = True
                    pos += 1
                    continue

                if pos >= len(buf):
                    break

                if buf[pos] == "]":
                    ended = True
                    pos += 1
                    # Ignore trailing whitespace.
                    while pos < len(buf) and buf[pos] in " \t\r\n":
                        pos += 1
                    break

                try:
                    item, next_pos = decoder.raw_decode(buf, pos)
                except json.JSONDecodeError:
                    # Need more data.
                    break

                yield item
                pos = next_pos

            # Keep only unconsumed tail in buffer.
            buf = buf[pos:]

            if ended:
                break

    if not started:
        raise ValueError("Empty or invalid JSON content.")
    if not ended:
        raise ValueError("Top-level array was not properly closed with ']'.")


def extract_life48():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as out:
        out.write("[\n")
        first = True

        for item in iter_top_level_array_items(INPUT_PATH):
            if not isinstance(item, dict):
                continue

            item_id = item.get("id")
            if isinstance(item_id, str) and item_id.startswith(TARGET_PREFIX):
                if not first:
                    out.write(",\n")
                out.write(json.dumps(item, ensure_ascii=False, indent=2))
                first = False

        out.write("\n]\n")


if __name__ == "__main__":
    extract_life48()
