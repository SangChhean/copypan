"""
圆桌历史记录 SQLite 读写
"""
import os
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_db_path = os.getenv("ROUNDTABLE_DB_PATH", "roundtable.db")
# 默认使用 backend 目录下 roundtable.db（与 main.py 同级）
if not os.path.isabs(_db_path):
    _db_path = str(Path(__file__).resolve().parent.parent.parent / _db_path)

_conn = sqlite3.connect(_db_path)
_conn.execute("""
CREATE TABLE IF NOT EXISTS roundtable_records (
    record_id TEXT PRIMARY KEY,
    scene_type TEXT,
    topic TEXT,
    participants TEXT,
    ai_roles TEXT,
    rounds TEXT,
    conclusion TEXT,
    created_at TIMESTAMP,
    is_pinned BOOLEAN DEFAULT 0,
    total_cost REAL DEFAULT 0
)
""")
_conn.commit()
try:
    _conn.execute("ALTER TABLE roundtable_records ADD COLUMN total_cost REAL DEFAULT 0")
    _conn.commit()
except Exception:
    pass


def save_record(record: dict) -> None:
    """将 record 字典写入 roundtable_records 表。"""
    created_at = record.get("created_at")
    if created_at is None:
        created_at = datetime.utcnow().isoformat()
    participants = json.dumps(record.get("participants") or [], ensure_ascii=False)
    ai_roles = json.dumps(record.get("ai_roles") or {}, ensure_ascii=False)
    rounds = json.dumps(record.get("rounds") or [], ensure_ascii=False)
    total_cost = record.get("total_cost")
    if total_cost is None:
        total_cost = 0.0
    _conn.execute(
        """
        INSERT OR REPLACE INTO roundtable_records
        (record_id, scene_type, topic, participants, ai_roles, rounds, conclusion, created_at, is_pinned, total_cost)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.get("record_id"),
            record.get("scene_type"),
            record.get("topic"),
            participants,
            ai_roles,
            rounds,
            record.get("conclusion") or "",
            created_at,
            1 if record.get("is_pinned") else 0,
            total_cost,
        ),
    )
    _conn.commit()


def _row_to_dict(row: tuple, cursor: sqlite3.Cursor) -> dict:
    """将一行转为 dict，JSON 字段反序列化。"""
    names = [d[0] for d in cursor.description]
    d = dict(zip(names, row))
    for key in ("participants", "ai_roles", "rounds"):
        if key in d and d[key] is not None:
            try:
                d[key] = json.loads(d[key])
            except (TypeError, json.JSONDecodeError):
                d[key] = [] if key == "participants" else {} if key == "ai_roles" else []
    if "is_pinned" in d:
        d["is_pinned"] = bool(d["is_pinned"])
    return d


def get_all_records() -> List[dict]:
    """按 is_pinned DESC, created_at DESC 排序返回所有记录。"""
    cursor = _conn.execute(
        """
        SELECT record_id, scene_type, topic, participants, ai_roles, rounds,
               conclusion, created_at, is_pinned, total_cost
        FROM roundtable_records
        ORDER BY is_pinned DESC, created_at DESC
        """
    )
    return [_row_to_dict(row, cursor) for row in cursor.fetchall()]


def get_record_by_id(record_id: str) -> Optional[dict]:
    """按 record_id 查单条，找不到返回 None。"""
    cursor = _conn.execute(
        """
        SELECT record_id, scene_type, topic, participants, ai_roles, rounds,
               conclusion, created_at, is_pinned, total_cost
        FROM roundtable_records
        WHERE record_id = ?
        """,
        (record_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row, cursor)


def toggle_pin(record_id: str) -> bool:
    """查出当前 is_pinned 值，取反后写回，返回操作后的新值。"""
    cursor = _conn.execute("SELECT is_pinned FROM roundtable_records WHERE record_id = ?", (record_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Record {record_id} not found")
    current = bool(row[0])
    new_value = not current
    _conn.execute(
        "UPDATE roundtable_records SET is_pinned = ? WHERE record_id = ?",
        (1 if new_value else 0, record_id),
    )
    _conn.commit()
    return new_value


def delete_record(record_id: str) -> bool:
    """删除指定 record_id 的记录，返回是否删除了行。"""
    cursor = _conn.execute(
        "DELETE FROM roundtable_records WHERE record_id = ?", (record_id,)
    )
    _conn.commit()
    return cursor.rowcount > 0


def get_roundtable_cost_stats(days: int) -> Dict[str, Any]:
    """
    返回最近 days 天的圆桌费用统计：
    {
        "total_cost": float,          # days 天内总费用
        "daily": {                    # key: "YYYY-MM-DD"（UTC），value: float
            "2026-03-10": 1.2345,
            ...
        },
        "total_count": int,           # days 天内圆桌总次数
        "scene_counts": {             # 按场景分组的统计
            "scene_one": {"count": int, "cost": float},
            "scene_two": {"count": int, "cost": float}
        }
    }
    日期范围：UTC 今天往前 days 天（含今天）。
    """
    start = (datetime.utcnow() - timedelta(days=days - 1)).strftime("%Y-%m-%d") + "T00:00:00"
    cursor = _conn.execute(
        """
        SELECT substr(created_at, 1, 10) AS date,
               SUM(total_cost) AS day_cost,
               COUNT(*) AS day_count
        FROM roundtable_records
        WHERE created_at >= ?
        GROUP BY date
        ORDER BY date DESC
        """,
        (start,),
    )
    rows = cursor.fetchall()
    daily = {}
    total_cost = 0.0
    total_count = 0
    for row in rows:
        date_str = row[0]
        day_cost = float(row[1] or 0)
        day_count = int(row[2] or 0)
        daily[date_str] = day_cost
        total_cost += day_cost
        total_count += day_count

    # 按场景类型分组统计
    scene_cursor = _conn.execute(
        """
        SELECT scene_type, COUNT(*) AS cnt, SUM(total_cost) AS cost
        FROM roundtable_records
        WHERE created_at >= ?
        GROUP BY scene_type
        """,
        (start,),
    )
    scene_rows = scene_cursor.fetchall()
    scene_counts = {
        "scene_one": {"count": 0, "cost": 0.0},
        "scene_two": {"count": 0, "cost": 0.0},
        "scene_three": {"count": 0, "cost": 0.0},
        "scene_four": {"count": 0, "cost": 0.0},
    }
    for row in scene_rows:
        scene_type = row[0] or ""
        cnt = int(row[1] or 0)
        cost = float(row[2] or 0)
        if scene_type not in scene_counts:
            scene_counts[scene_type] = {"count": 0, "cost": 0.0}
        scene_counts[scene_type] = {"count": cnt, "cost": cost}

    return {"total_cost": total_cost, "daily": daily, "total_count": total_count, "scene_counts": scene_counts}
