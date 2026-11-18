# -*- coding: utf-8 -*-
"""只读：从导入用 jsonl 收集 text_* 的 chunk_id（供在线检查 8 与离线工具）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Iterator, Optional


def env_or_default(env_name: str, default: Path) -> Path:
    v = (os.environ.get(env_name) or "").strip()
    return Path(v) if v else default


def resolve_jsonl_paths(src: Optional[Path]) -> list[Path]:
    if src is None:
        return []
    src = Path(src)
    if not src.exists():
        return []
    if src.is_file() and src.suffix.lower() == ".jsonl":
        return [src]
    shards = src / "shards"
    if shards.is_dir():
        return sorted(shards.glob("*.jsonl"))
    if src.is_dir():
        return sorted(src.glob("**/*.jsonl"))
    return []


def iter_chunk_rows(paths: Iterable[Path]) -> Iterator[dict]:
    for p in paths:
        with Path(p).open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def chunk_ids_for_message(
    paths: list[Path],
    *,
    message_key: Optional[str] = None,
    book_title: Optional[str] = None,
    message_number: Optional[int] = None,
) -> set[str]:
    out: set[str] = set()
    for row in iter_chunk_rows(paths):
        if message_key and str(row.get("message_key") or "") != message_key:
            continue
        if book_title is not None and str(row.get("book_title") or "") != book_title:
            continue
        if message_number is not None and int(row.get("message_number") or -1) != int(message_number):
            continue
        cid = row.get("chunk_id")
        if cid:
            out.add(str(cid))
    return out
