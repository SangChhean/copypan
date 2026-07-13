# -*- coding: utf-8 -*-
"""给已有 cn_users.db 增加 roundtable 配额列（本地与服务器各执行一次）。"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "cn_users.db"

conn = sqlite3.connect(DB_PATH)
try:
    conn.execute(
        "ALTER TABLE users ADD COLUMN count_roundtable INTEGER NOT NULL DEFAULT 0"
    )
    print("已添加 count_roundtable")
except sqlite3.OperationalError as e:
    print(f"count_roundtable 跳过: {e}")

try:
    conn.execute(
        "ALTER TABLE users ADD COLUMN limit_roundtable INTEGER NOT NULL DEFAULT 2"
    )
    print("已添加 limit_roundtable")
except sqlite3.OperationalError as e:
    print(f"limit_roundtable 跳过: {e}")

conn.commit()
conn.close()
print("迁移完成")
