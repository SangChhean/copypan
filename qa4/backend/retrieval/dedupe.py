# -*- coding: utf-8 -*-
"""去重三种：map_note（书+章节+注N）、hymns（series, hymn_number）、同篇段数上限。"""

from __future__ import annotations

import re
from typing import Any, Optional

_NOTE_RE = re.compile(r"注\s*(\d+)")


def map_note_key(source_zh: str, *, bible: Any = None) -> Optional[tuple]:
    """「（恢复本圣经，可十四24，注1）」→ (卷, 章, 起节, 止章, 止节, 注号)；解析不出返回 None。

    仅接受 verse_range / whole_chapter / cross_chapter；whole_book / chapter_range
    不能唯一对应一处注解，返回 None，避免跨节碰撞。
    """
    if not source_zh:
        return None
    from scripture.normalize import KIND_BOOK, KIND_CHAPTER_RANGE, parse_refs

    s = source_zh.strip().strip("（）()")
    note = _NOTE_RE.search(s)
    body = _NOTE_RE.sub("", s)
    refs = parse_refs(body, bible=bible, validate=bible is not None)
    if not refs:
        return None
    if refs[0].kind in (KIND_BOOK, KIND_CHAPTER_RANGE):
        return None
    return refs[0].key() + (int(note.group(1)) if note else 0,)


def hymn_key(doc: dict[str, Any], *, default_series: str = "诗歌") -> Optional[tuple[str, int]]:
    num = doc.get("hymn_number")
    if num is None:
        return None
    return (str(doc.get("series") or default_series), int(num))


def message_key(doc: dict[str, Any]) -> Optional[tuple[str, Any]]:
    bt = doc.get("book_title")
    mn = doc.get("message_number")
    if not bt or mn is None:
        return None
    return (str(bt), mn)


def dedupe(
    docs: list[dict[str, Any]],
    *,
    per_message_cap: int = 3,
    bible: Any = None,
    default_series: str = "诗歌",
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """按顺序保留；返回 (保留, 去掉计数)。"""
    kept: list[dict[str, Any]] = []
    stats = {"map_note_dup": 0, "hymn_dup": 0, "message_cap": 0}
    seen_note: set = set()
    seen_hymn: set = set()
    per_msg: dict[tuple, int] = {}
    for d in docs:
        lg = d.get("_logical")
        if lg == "map_note":
            k = map_note_key(str(d.get("source_zh") or ""), bible=bible)
            if k is not None:
                if k in seen_note:
                    stats["map_note_dup"] += 1
                    continue
                seen_note.add(k)
        if lg == "hymns":
            hk = hymn_key(d, default_series=default_series)
            if hk is not None:
                if hk in seen_hymn:
                    stats["hymn_dup"] += 1
                    continue
                seen_hymn.add(hk)
        mk = message_key(d)
        if mk is not None and lg not in ("hymns", "bible"):
            n = per_msg.get(mk, 0)
            if n >= per_message_cap:
                stats["message_cap"] += 1
                continue
            per_msg[mk] = n + 1
        kept.append(d)
    return kept, stats
