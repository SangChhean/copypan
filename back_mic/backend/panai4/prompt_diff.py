# -*- coding: utf-8 -*-
"""Prompt 按段落对比。一行非空文字算一段；只列出改动的段落，未改动的合并为段落范围。"""
from __future__ import annotations

import difflib


def _paragraphs(text: str) -> list[str]:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return [line.rstrip() for line in text.split("\n") if line.strip()]


def paragraph_diff(old: str, new: str) -> dict:
    """段落编号以 old 为准。返回改动处数与区块：same（from、to）、del（text）、add（text）。"""
    left = _paragraphs(old)
    right = _paragraphs(new)
    matcher = difflib.SequenceMatcher(a=left, b=right, autojunk=False)
    blocks: list[dict] = []
    changes = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            blocks.append({"type": "same", "from": i1 + 1, "to": i2})
            continue
        changes += 1
        for line in left[i1:i2]:
            blocks.append({"type": "del", "text": line})
        for line in right[j1:j2]:
            blocks.append({"type": "add", "text": line})
    return {
        "changes": changes,
        "old_paragraphs": len(left),
        "new_paragraphs": len(right),
        "blocks": blocks,
    }
