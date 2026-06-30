import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "cn_users.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# 1. 重命名旧表
conn.execute("ALTER TABLE material_categories RENAME TO material_categories_old")

# 2. 建新表，dir_name 改为 (dir_name, parent_id) 联合唯一
conn.execute("""
    CREATE TABLE material_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        dir_name TEXT NOT NULL,
        parent_id INTEGER REFERENCES material_categories(id),
        type TEXT NOT NULL DEFAULT 'pastoral',
        sort_order INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(dir_name, parent_id)
    )
""")

# 3. 迁移数据（如果旧表里还有残留数据）
conn.execute("""
    INSERT INTO material_categories (id, name, dir_name, parent_id, type, sort_order, created_at)
    SELECT id, name, dir_name, parent_id, type, sort_order, created_at
    FROM material_categories_old
""")

# 4. 删除旧表
conn.execute("DROP TABLE material_categories_old")

conn.commit()
conn.close()
print("迁移完成")
