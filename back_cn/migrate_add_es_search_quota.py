# -*- coding: utf-8 -*-
"""给已有 cn_users.db 增加 es_search 配额列（本地与服务器各执行一次；init_db 也会自动补列）。"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "cn_users.db"
DEFAULT_LIMIT = 1

conn = sqlite3.connect(DB_PATH)
try:
    conn.execute(
        "ALTER TABLE users ADD COLUMN count_es_search INTEGER NOT NULL DEFAULT 0"
    )
    print("已添加 count_es_search")
except sqlite3.OperationalError as e:
    print(f"count_es_search 跳过: {e}")

try:
    conn.execute(
        f"ALTER TABLE users ADD COLUMN limit_es_search INTEGER NOT NULL DEFAULT {DEFAULT_LIMIT}"
    )
    print("已添加 limit_es_search")
except sqlite3.OperationalError as e:
    print(f"limit_es_search 跳过: {e}")

conn.commit()
conn.close()
print("迁移完成")
