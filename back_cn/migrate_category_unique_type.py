import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "cn_users.db"
conn = sqlite3.connect(DB_PATH)

# 1. 重命名旧表
conn.execute("ALTER TABLE material_categories RENAME TO material_categories_old")

# 2. 建新表，UNIQUE 加入 type
conn.execute("""
    CREATE TABLE material_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        dir_name TEXT NOT NULL,
        parent_id INTEGER REFERENCES material_categories(id),
        type TEXT NOT NULL DEFAULT 'pastoral',
        sort_order INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(dir_name, parent_id, type)
    )
""")

# 3. 迁移所有现有数据（保留原 id，避免 materials 表外键失效）
conn.execute("""
    INSERT INTO material_categories (id, name, dir_name, parent_id, type, sort_order, created_at)
    SELECT id, name, dir_name, parent_id, type, sort_order, created_at
    FROM material_categories_old
""")

conn.commit()

# 4. 验证迁移后数量一致
old_count = conn.execute("SELECT COUNT(*) FROM material_categories_old").fetchone()[0]
new_count = conn.execute("SELECT COUNT(*) FROM material_categories").fetchone()[0]
print(f"旧表: {old_count} 条, 新表: {new_count} 条")
print("schema:", conn.execute("SELECT sql FROM sqlite_master WHERE name='material_categories'").fetchone()[0])

if old_count != new_count:
    raise SystemExit("COUNT MISMATCH — aborting, old table kept")

conn.close()
print("迁移成功，可继续 DROP 旧表")
