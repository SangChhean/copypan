# -*- coding: utf-8 -*-
"""重渲染 text：头部行 + 原 text。

头部行 = [book_title, message_title, section_title]
  - 去空（map_note 无 section_title → 只用前两段）
  - 相邻完全相同只留一段
  - 全角空格 U+3000 连接
  - message_title 原样
  - 头部行 >120 字时截断 section_title（保留 book/message 完整）

cwwl 额外保留 year；map_note 的 en/source_en 空串原样保留。

产出：{out}/rendered/{索引名}.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

DEFAULT_IN = r"G:\PanAI4.0专用\12490原文JSONL"

KEEP_FIELDS = [
    "chunk_id",
    "message_key",
    "book_title",
    "message_number",
    "message_title",
    "section_title",
    "author",
    "paragraph_type",
    "source_zh",
    "source_en",
    "en",
    "original_ids",
]
# cwwl 独有；其它索引不写
OPTIONAL_FIELDS = ("year",)

# 源索引名 → corpus
CORPUS_MAP = {
    "kg-rag_life": "life",
    "kg-rag_cwwl": "cwwl",
    "kg-rag_cwwn": "cwwn",
    "kg-rag_others": "others",
    "kg-rag_map_note": "map_note",
}

HEADER_MAX = 120
SEP = "\u3000"  # 全角空格


def _norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def build_header(book_title, message_title, section_title) -> str:
    parts = []
    for part in (_norm(book_title), _norm(message_title), _norm(section_title)):
        if not part:
            continue
        if parts and parts[-1] == part:
            continue
        parts.append(part)
    if not parts:
        return ""

    header = SEP.join(parts)
    if len(header) <= HEADER_MAX:
        return header

    # 截断 section_title，保留 book + message 完整
    book = _norm(book_title)
    msg = _norm(message_title)
    sec = _norm(section_title)
    head_parts = []
    for part in (book, msg):
        if not part:
            continue
        if head_parts and head_parts[-1] == part:
            continue
        head_parts.append(part)
    base = SEP.join(head_parts)
    if not sec or (head_parts and head_parts[-1] == sec):
        return base[:HEADER_MAX] if len(base) > HEADER_MAX else base

    budget = HEADER_MAX - len(base) - (len(SEP) if base else 0)
    if budget <= 0:
        return base[:HEADER_MAX]
    return (base + SEP + sec[:budget]) if base else sec[:HEADER_MAX]


def render_text(book_title, message_title, section_title, body: str) -> str:
    header = build_header(book_title, message_title, section_title)
    body = body if body is not None else ""
    if header:
        return header + "\n\n" + body
    return body


def render_record(obj: dict, source_index: str) -> dict:
    body = obj.get("text") if obj.get("text") is not None else ""
    book = obj.get("book_title")
    msg = obj.get("message_title")
    # map_note 无 section_title → 缺失当空，头部行只用两段
    sec = obj.get("section_title") if "section_title" in obj else None
    new_text = render_text(book, msg, sec, body)

    out = {}
    for k in KEEP_FIELDS:
        if k in obj:
            # 保留空字符串（map_note 的 en / source_en），不要改成 None
            out[k] = obj[k]
        else:
            out[k] = None
    for k in OPTIONAL_FIELDS:
        if k in obj:
            out[k] = obj[k]
    out["text"] = new_text
    out["chars"] = len(new_text)
    out["corpus"] = CORPUS_MAP[source_index]
    out["source_index"] = source_index
    return out


def render_file(src: Path, dst: Path, source_index: str, sample_n: int = 10) -> dict:
    dst.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    samples_idx = set()
    # first pass count for sampling? For large files reservoir sample while writing
    reservoir: list[tuple[dict, dict]] = []
    rng = random.Random(20260930)

    with src.open(encoding="utf-8") as fin, dst.open(
        "w", encoding="utf-8", newline="\n"
    ) as fout:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            rendered = render_record(obj, source_index)
            fout.write(json.dumps(rendered, ensure_ascii=False) + "\n")
            n += 1
            # reservoir sampling for print
            if len(reservoir) < sample_n:
                reservoir.append((obj, rendered))
            else:
                j = rng.randint(1, n)
                if j <= sample_n:
                    reservoir[j - 1] = (obj, rendered)

    return {"n": n, "samples": reservoir, "dst": dst, "bytes": dst.stat().st_size}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_dir", default=DEFAULT_IN)
    parser.add_argument(
        "--out",
        default=None,
        help="默认 {in}/rendered",
    )
    parser.add_argument(
        "--indices",
        nargs="*",
        default=list(CORPUS_MAP.keys()),
    )
    args = parser.parse_args(argv)

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out) if args.out else in_dir / "rendered"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in args.indices:
        if name not in CORPUS_MAP:
            print(f"UNKNOWN {name}", flush=True)
            return 2
        src = in_dir / f"{name}.jsonl"
        if not src.is_file():
            print(f"MISSING {src}", flush=True)
            return 2
        dst = out_dir / f"{name}.jsonl"
        print(f"RENDER_START {name}", flush=True)
        info = render_file(src, dst, name)
        print(
            f"RENDER_DONE {name} n={info['n']} bytes={info['bytes']}",
            flush=True,
        )
        print(f"--- SAMPLE {name} (up to 10) ---", flush=True)
        for i, (before, after) in enumerate(info["samples"], 1):
            old_text = before.get("text") or ""
            new_text = after.get("text") or ""
            header = new_text.split("\n\n", 1)[0] if "\n\n" in new_text else ""
            body_after = new_text.split("\n\n", 1)[1] if "\n\n" in new_text else new_text
            body_ok = body_after == old_text
            print(f"[{i}] chunk_id={after.get('chunk_id')}", flush=True)
            print(f"  book={before.get('book_title')!r}", flush=True)
            print(f"  msg={before.get('message_title')!r}", flush=True)
            print(f"  sec={before.get('section_title')!r}", flush=True)
            print(f"  header={header!r}", flush=True)
            print(f"  body_unchanged={body_ok}", flush=True)
            print(f"  old_text[:80]={old_text[:80]!r}", flush=True)
            print(f"  new_text[:120]={new_text[:120]!r}", flush=True)

    print("ALL_RENDER_OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
