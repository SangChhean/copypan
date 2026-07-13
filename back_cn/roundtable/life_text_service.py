# -*- coding: utf-8 -*-
"""生命读经原文查询（Step 0 数据读取层）。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LIFE_TEXTS_DIR = Path(__file__).parent.parent / "data" / "life_texts"


@lru_cache(maxsize=None)
def _load_book(book_id: int) -> dict:
    path = LIFE_TEXTS_DIR / f"life_{book_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"找不到卷号 {book_id} 的生命读经数据")
    return json.loads(path.read_text(encoding="utf-8"))


def get_message(book_id: int, message_no: int) -> dict:
    """返回 {"book_name": ..., "title": ..., "paragraphs": [...], "full_text": "..."}"""
    book = _load_book(book_id)
    msg = book.get("messages", {}).get(str(message_no))
    if msg is None:
        raise ValueError(f"卷 {book_id} 没有第 {message_no} 篇")
    full_text = "\n".join(msg["paragraphs"])
    return {
        "book_name": book["book_name"],
        "title": msg["title"],
        "paragraphs": msg["paragraphs"],
        "full_text": full_text,
    }


def get_messages(book_id: int, message_nos: list[int]) -> list[dict]:
    """支持 1-3 篇，按用户选择顺序返回"""
    if not (1 <= len(message_nos) <= 3):
        raise ValueError("篇号数量须在 1~3 之间")
    return [get_message(book_id, n) for n in message_nos]
