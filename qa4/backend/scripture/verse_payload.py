# -*- coding: utf-8 -*-
"""经文问答 verse_data SSE 载荷（形状对齐 3.0，数据来自 qa4 BibleText）。"""

from __future__ import annotations

from typing import Any, Optional

from scripture.normalize import (
    KIND_BOOK,
    KIND_CHAPTER,
    KIND_CHAPTER_RANGE,
    KIND_CROSS,
    KIND_VERSE,
)


def _query_type_from_refs(refs: list[Any]) -> str:
    if not refs:
        return "verse"
    if any(getattr(r, "kind", None) == KIND_CHAPTER for r in refs):
        return "chapter"
    if any(getattr(r, "kind", None) in {KIND_CHAPTER_RANGE, KIND_CROSS} for r in refs):
        return "range"
    if len(refs) == 1:
        r = refs[0]
        if getattr(r, "kind", None) == KIND_VERSE:
            vs = int(getattr(r, "v_start", 0) or 0)
            ve = int(getattr(r, "v_end", 0) or 0)
            if vs and ve and vs != ve:
                return "range"
            if vs == 0 and ve == 0:
                return "chapter"
        return "verse"
    return "range"


def rows_from_targeted_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 targeted scripture blocks 抽出可给前端的经文行（信息较少时的回退）。"""
    out: list[dict[str, Any]] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        if b.get("unit") == "book_overview" or b.get("chunk_type") == "book_outline":
            continue
        if b.get("verse") is None:
            continue
        row = dict(b)
        if "book" not in row and row.get("book_no") is not None:
            row["book"] = row["book_no"]
        if "name_gb" not in row and row.get("book_title"):
            row["name_gb"] = row["book_title"]
        if "text_gb" not in row and row.get("text"):
            row["text_gb"] = row["text"]
        out.append(row)
    return out


def build_verse_data(
    *,
    bible: Any,
    refs: list[Any],
    targeted: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """构造 SSE verse_data 的 data 字段。

    单节 → verse 对象；多节 → {verses, query_type}。
    """
    rows: list[dict[str, Any]] = []
    if bible is not None and refs:
        for r in refs:
            kind = getattr(r, "kind", None)
            b = int(getattr(r, "book_no", 0) or 0)
            ch = int(getattr(r, "chapter", 0) or 0)
            vs = int(getattr(r, "v_start", 0) or 0)
            ve = int(getattr(r, "v_end", 0) or 0)
            if kind == KIND_BOOK:
                continue
            if kind == KIND_CHAPTER:
                rows.extend(bible.get_chapter(b, ch))
            elif kind == KIND_CHAPTER_RANGE:
                c1, c2 = ch, int(getattr(r, "end_chapter", ch) or ch)
                for c in range(min(c1, c2), max(c1, c2) + 1):
                    rows.extend(bible.get_chapter(b, c))
            elif kind == KIND_CROSS:
                rows.extend(
                    bible.get_cross(
                        b,
                        ch,
                        vs,
                        int(getattr(r, "end_chapter", ch) or ch),
                        ve,
                    )
                )
            elif kind == KIND_VERSE:
                if vs == 0 and ve == 0:
                    rows.extend(bible.get_chapter(b, ch))
                else:
                    rows.extend(bible.get_range(b, ch, vs or 1, ve or vs or 1))
            else:
                one = bible.get_verse(b, ch, vs or ve or 1)
                if one:
                    rows.append(one)
    if not rows and targeted:
        rows = rows_from_targeted_blocks(list(targeted.get("blocks") or []))
    if not rows:
        return None
    qtype = _query_type_from_refs(refs) if refs else ("chapter" if len(rows) > 1 else "verse")
    if len(rows) == 1 and qtype == "verse":
        return rows[0]
    return {"verses": rows, "query_type": qtype if qtype != "verse" else "range"}
