#!/usr/bin/env python3
"""
本地文件夹 -> 服务器注册脚本
用法：
  python back_cn/scripts/register_materials.py <本地目录> <type> [parent_category_id]

参数：
  本地目录           要注册的文件夹路径（已通过 scp 传到服务器上）
  type               分类类型：conference / service / community / sisters / young_pro / college / youth / kids
  parent_category_id 可选，指定父分类 id（不填则自动建根分类）

示例：
  python back_cn/scripts/register_materials.py /tmp/upload/2026-03guoshangjietehu conference
  python back_cn/scripts/register_materials.py /tmp/upload/zijianjiia conference 159
"""
import os
import re
import sys
import uuid
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "back_cn" / "cn_users.db"
MATERIALS_DIR = Path(os.getenv("CN_MATERIALS_DIR", "/opt/pansearch/data/cn_materials"))

def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _to_pinyin_dir(name: str) -> str:
    try:
        from pypinyin import lazy_pinyin
        chars = lazy_pinyin(name)
        result = "_".join(chars)
    except ImportError:
        result = name
    result = re.sub(r"[^a-zA-Z0-9_-]", "_", result)
    result = re.sub(r"_+", "_", result).strip("_")
    return result or "_upload"

def _ensure_category(name: str, parent_id, type_: str, conn) -> int:
    dir_name = _to_pinyin_dir(name)
    row = conn.execute(
        "SELECT id FROM material_categories WHERE dir_name = ? AND (parent_id IS ? OR parent_id = ?)",
        (dir_name, parent_id, parent_id),
    ).fetchone()
    if row:
        return row["id"]
    cat_dir = MATERIALS_DIR / dir_name
    cat_dir.mkdir(parents=True, exist_ok=True)
    try:
        cur = conn.execute(
            """
            INSERT INTO material_categories(name, dir_name, parent_id, sort_order, created_at, type)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (name, dir_name, parent_id, _utc_now(), type_),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        row = conn.execute(
            "SELECT id FROM material_categories WHERE dir_name = ? AND (parent_id IS ? OR parent_id = ?)",
            (dir_name, parent_id, parent_id),
        ).fetchone()
        return row["id"]

def register_dir(src_dir: Path, type_: str, parent_id, conn):
    items = sorted(src_dir.iterdir())
    files = [i for i in items if i.is_file() and not i.name.startswith(".")]
    subdirs = [i for i in items if i.is_dir() and not i.name.startswith(".")]

    uploaded = 0
    errors = []

    for f in files:
        ext = f.suffix or ""
        stored_name = f"{uuid.uuid4()}{ext}"
        cat_row = conn.execute(
            "SELECT dir_name FROM material_categories WHERE id = ?", (parent_id,)
        ).fetchone()
        if not cat_row:
            errors.append(f"分类 id={parent_id} 不存在，跳过文件 {f.name}")
            continue
        dest = MATERIALS_DIR / cat_row["dir_name"] / stored_name
        try:
            shutil.copy2(f, dest)
            conn.execute(
                """
                INSERT INTO materials(category_id, display_name, stored_name, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (parent_id, f.name, stored_name, f.stat().st_size, _utc_now()),
            )
            conn.commit()
            uploaded += 1
            print(f"OK: {f.name}")
        except Exception as e:
            errors.append(f"{f.name}: {e}")
            print(f"FAIL: {f.name}: {e}")

    for d in subdirs:
        cat_id = _ensure_category(d.name, parent_id, type_, conn)
        print(f"[分类] {d.name} (id={cat_id})")
        u, e = register_dir(d, type_, cat_id, conn)
        uploaded += u
        errors.extend(e)

    return uploaded, errors

def main():
    if len(sys.argv) < 3:
        print("用法: python register_materials.py <目录> <type> [parent_category_id]")
        sys.exit(1)

    src = Path(sys.argv[1])
    type_ = sys.argv[2]
    parent_id = int(sys.argv[3]) if len(sys.argv) > 3 else None

    if not src.exists() or not src.is_dir():
        print(f"目录不存在: {src}")
        sys.exit(1)

    if type_ not in ("conference", "service", "community", "sisters", "young_pro", "college", "youth", "kids"):
        print(f"type 必须是 conference / service / community / sisters / young_pro / college / youth / kids，当前: {type_}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if parent_id is None:
        root_id = _ensure_category(src.name, None, type_, conn)
        print(f"[根分类] {src.name} (id={root_id})")
        uploaded, errors = register_dir(src, type_, root_id, conn)
    else:
        print(f"[父分类 id={parent_id}] 注册 {src.name} 下的内容")
        uploaded, errors = register_dir(src, type_, parent_id, conn)

    conn.close()
    print(f"\n完成: {uploaded} 个文件注册成功，{len(errors)} 个失败")
    if errors:
        print("失败列表:")
        for e in errors:
            print(f"  - {e}")

if __name__ == "__main__":
    main()
