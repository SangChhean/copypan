"""
读取 A:\\copypan\\test_B\\data\\ephesians_raw.json，
只保留 type == "text" 的记录，每条转为一个 chunk：
  - chunk_id: 取原始 id
  - text    : 原样保留
  - title   : 原样保留
  - source  : 取原始 source 数组的第一个元素（中文出处字符串）；
              若 source 为空数组或不存在则为空字符串

输出 A:\\copypan\\test_B\\data\\ephesians_chunks.json：
  - 整体是一个 JSON 数组，[ 和 ] 各占一行
  - 每条 chunk 一行，字段顺序：chunk_id, text, title, source
  - 不缩进；ensure_ascii=False（中文不转义）
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
SRC_PATH = DATA_DIR / "ephesians_raw.json"
DST_PATH = DATA_DIR / "ephesians_chunks.json"


def _first_source(value) -> str:
    if isinstance(value, list) and value:
        first = value[0]
        return first if isinstance(first, str) else ""
    return ""


def main() -> int:
    if not SRC_PATH.is_file():
        print(f"源文件不存在: {SRC_PATH}", file=sys.stderr)
        return 1

    raw = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("源文件根节点必须是数组", file=sys.stderr)
        return 1

    chunks: list[dict] = []
    for rec in raw:
        if not isinstance(rec, dict):
            continue
        if rec.get("type") != "text":
            continue
        chunks.append({
            "chunk_id": rec.get("id"),
            "text": rec.get("text"),
            "title": rec.get("title"),
            "source": _first_source(rec.get("source")),
        })

    with DST_PATH.open("w", encoding="utf-8", newline="\n") as fp:
        fp.write("[\n")
        for i, chunk in enumerate(chunks):
            line = json.dumps(chunk, ensure_ascii=False)
            sep = "," if i < len(chunks) - 1 else ""
            fp.write(line + sep + "\n")
        fp.write("]\n")

    print(f"共生成 chunk: {len(chunks)} 条 -> {DST_PATH}")

    if chunks:
        sample_n = min(3, len(chunks))
        samples = random.sample(chunks, sample_n)
        print("\n随机抽样 3 条 chunk：")
        for idx, item in enumerate(samples, 1):
            print(f"--- sample {idx} ---")
            print(json.dumps(item, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
