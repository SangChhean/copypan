# -*- coding: utf-8 -*-
"""只读打开恢复本 sqlite，绝不写入。"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from . import config


def connect(path: str | None = None) -> sqlite3.Connection:
    db = path or config.SQLITE_PATH
    if not os.path.isfile(db):
        raise FileNotFoundError(db)
    try:
        con = sqlite3.connect(
            "file:{0}?mode=ro&immutable=1".format(db.replace("\\", "/")),
            uri=True,
        )
    except sqlite3.OperationalError as exc:
        raise SystemExit(
            "无法以只读方式打开 sqlite（可能被 DB Browser 占用）。请先关闭后重试。\n{0}".format(exc)
        ) from exc
    con.row_factory = sqlite3.Row
    return con


def _strip_quotes(value: Any) -> Any:
    if isinstance(value, str) and len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def load_volumes(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute(
        "SELECT chapter_code, chapter_name, abbreviation, chapter_sum "
        "FROM {0} ORDER BY chapter_code".format(config.TABLE_VOLUME)
    ).fetchall()
    out = []
    for row in rows:
        out.append({
            "book_no": int(row["chapter_code"]),
            "book_title": _strip_quotes(row["chapter_name"]),
            "abbreviation": _strip_quotes(row["abbreviation"]),
            "chapter_sum": int(row["chapter_sum"]),
        })
    return out


def load_topics(con: sqlite3.Connection) -> dict[int, str]:
    rows = con.execute(
        "SELECT chapter_code, content FROM {0}".format(config.TABLE_TOPIC)
    ).fetchall()
    return {int(r["chapter_code"]): _strip_quotes(r["content"]) for r in rows}


def load_outlines(con: sqlite3.Connection, book_no: int) -> list[dict]:
    """
    纲目表列名与经文表不一致，这里映射清楚：
    - related_chapters = 章（section_code）
    - related_number = 节（segment_code）
    - related_section_code = 上下（unit_code：0整节/1上/2下）
    """
    rows = con.execute(
        "SELECT id, volume_order, level, level_order, outline_content, "
        "related_chapters, related_number, related_section_code "
        "FROM {0} WHERE chapter_code=? ORDER BY volume_order".format(config.TABLE_OUTLINE),
        (book_no,),
    ).fetchall()
    out = []
    for row in rows:
        chapter = int(row["related_chapters"])
        verse = int(row["related_number"])
        unit = int(row["related_section_code"])
        # 诗篇特例：related_number=0 → 视为该章第 1 节
        if verse == 0:
            verse = 1
            unit = 0
        out.append({
            "id": int(row["id"]),
            "volume_order": int(row["volume_order"]),
            "level": int(row["level"]),
            "level_order": int(row["level_order"]),
            "outline_content": row["outline_content"] or "",
            "chapter": chapter,
            "verse": verse,
            "unit": unit,
            "start_key": config.make_key(chapter, verse, unit),
        })
    return out


def load_verses(con: sqlite3.Connection, book_no: int) -> list[dict]:
    rows = con.execute(
        "SELECT id, section_code, segment_code, unit_code, content "
        "FROM {0} WHERE chapter_code=? "
        "ORDER BY section_code, segment_code, unit_code".format(config.TABLE_VERSE),
        (book_no,),
    ).fetchall()
    out = []
    for row in rows:
        chapter = int(row["section_code"])
        verse = int(row["segment_code"])
        unit = int(row["unit_code"])
        out.append({
            "id": int(row["id"]),
            "chapter": chapter,
            "verse": verse,
            "unit": unit,
            "key": config.make_key(chapter, verse, unit),
            "content": row["content"] or "",
        })
    return out


def load_paragraph_keys(con: sqlite3.Connection, book_no: int) -> list[int]:
    rows = con.execute(
        "SELECT section_code, segment_code, unit_code "
        "FROM {0} WHERE chapter_code=? "
        "ORDER BY section_code, segment_code, unit_code".format(config.TABLE_PARAGRAPH),
        (book_no,),
    ).fetchall()
    return [
        config.make_key(int(r["section_code"]), int(r["segment_code"]), int(r["unit_code"]))
        for r in rows
    ]


def file_stat(path: str | None = None) -> dict:
    db = path or config.SQLITE_PATH
    st = os.stat(db)
    return {"path": db, "size": st.st_size, "mtime": st.st_mtime}
