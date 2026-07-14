# -*- coding: utf-8 -*-
"""小排材料制作：最近诗歌推荐历史（避免短期内重复推荐）。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

# 与 back_cn/auth.py 同一份 cn_users.db
DB_PATH = Path(__file__).resolve().parent.parent / "cn_users.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_hymn_history_table() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS roundtable_hymn_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                no INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()


def get_recent_hymns(limit: int = 10) -> list[dict]:
    """取最近 limit 次用过的诗歌，用于提示模型避免重复。"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT source, no FROM roundtable_hymn_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"source": r[0], "no": r[1]} for r in rows]


def record_hymn_used(source: str, no: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO roundtable_hymn_history (source, no) VALUES (?, ?)",
            (source, int(no)),
        )
        # 只保留最近 50 条，避免表无限增长
        conn.execute(
            """
            DELETE FROM roundtable_hymn_history
            WHERE id NOT IN (
                SELECT id FROM roundtable_hymn_history ORDER BY id DESC LIMIT 50
            )
            """
        )
        conn.commit()
