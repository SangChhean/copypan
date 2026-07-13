# -*- coding: utf-8 -*-
"""经文库惰性加载：模块首次查询时自动 load 一次，避免调用方遗漏。"""
from __future__ import annotations

from pathlib import Path

from back_qa.qa.bible_service import get_verse, load_bible_data

_loaded = False

# back_cn/roundtable/ -> parents[2] == repo root (E:\copypan)
_BIBLE_DIR = Path(__file__).resolve().parent.parent.parent / "back_qa" / "bible_data"


def ensure_bible_loaded() -> None:
    global _loaded
    if not _loaded:
        load_bible_data(str(_BIBLE_DIR))
        _loaded = True


def get_verse_safe(book: int, chapter: int, verse: int) -> dict | None:
    ensure_bible_loaded()
    return get_verse(book, chapter, verse)
