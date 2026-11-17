# -*- coding: utf-8 -*-
"""【PanAI 新测试台】纲目制作页「暂时保存」历史记录：存在服务器上，按电脑分开。

以前记录存在各自浏览器的 localStorage：同一浏览器开几个分页，后存的分页会把整包覆盖掉别的分页
刚存的记录。现在改成存在这里，按「一条一条」新增、修改、删除，互相不会盖掉。

按电脑分开：每台电脑的浏览器第一次打开时生成一个「本机编号」（device），每条记录都带着它；
读、改、删都只认本机编号——同一台电脑的几个窗口共用、同步，别的电脑的记录看不到也动不到。

存储：SQLite 文件（默认 backend 目录下 t35test_history.db，可用环境变量 T35_HISTORY_DB_PATH 改）。
*.db 已在 .gitignore 里，不进仓库；第一次用到时自动建表。
"""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "t35test_history.db"
DB_PATH = os.environ.get("T35_HISTORY_DB_PATH") or str(_DEFAULT_PATH)

# 列表里不带的大字段（页面上的历史记录用不到，只存着；修改时服务器端合并，不会丢）
_HEAVY_FIELDS = ("thinking_text", "thinking_text_zh", "answer", "skeleton", "eval", "dropped", "truncated")

_init_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    global _initialized
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)  # 自己控制事务
    if not _initialized:
        with _init_lock:
            if not _initialized:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY,
                        device TEXT,
                        created_by TEXT,
                        created_ts INTEGER,
                        updated_ts INTEGER,
                        updated_by TEXT,
                        data TEXT NOT NULL
                    )"""
                )
                cols = {r[1] for r in conn.execute("PRAGMA table_info(history)").fetchall()}
                if "device" not in cols:
                    conn.execute("ALTER TABLE history ADD COLUMN device TEXT")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_history_device ON history(device, id)")
                _initialized = True
    return conn


def _now_ms() -> int:
    return int(time.time() * 1000)


def _row_to_record(row, light: bool) -> dict:
    data = json.loads(row[2] or "{}")
    if light:
        for k in _HEAVY_FIELDS:
            data.pop(k, None)
    data["id"] = row[0]
    data["created_by"] = row[1] or data.get("created_by") or ""
    return data


def list_records(device: str, light: bool = True) -> list[dict]:
    """只取本机编号的记录（新的在前）。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, created_by, data FROM history WHERE device = ? ORDER BY id DESC", (device,)
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        try:
            out.append(_row_to_record(r, light))
        except Exception:
            continue
    return out


def get_record(rid: int, device: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, created_by, data FROM history WHERE id = ? AND device = ?", (rid, device)
        ).fetchone()
    finally:
        conn.close()
    return _row_to_record(row, light=False) if row else None


def create_record(record: dict, username: str, device: str) -> int:
    """新增一条。id 用前端给的（毫秒时间戳）；若已被占用，就换一个新的并返回。"""
    rec = dict(record or {})
    rec.pop("created_by", None)
    try:
        rid = int(rec.get("id") or 0)
    except (TypeError, ValueError):
        rid = 0
    now = _now_ms()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if rid <= 0 or conn.execute("SELECT 1 FROM history WHERE id = ?", (rid,)).fetchone():
            max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM history").fetchone()[0]
            rid = max(int(max_id) + 1, now)
        rec["id"] = rid
        conn.execute(
            "INSERT INTO history (id, device, created_by, created_ts, updated_ts, updated_by, data) VALUES (?,?,?,?,?,?,?)",
            (rid, device, username, now, now, username, json.dumps(rec, ensure_ascii=False)),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return rid


def import_records(records: list[dict], username: str, device: str) -> dict:
    """把本机浏览器里的旧记录搬上来，记在本机编号下：id 已存在的跳过（同一份不会重复导入）。"""
    added = skipped = 0
    now = _now_ms()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for rec in records or []:
            if not isinstance(rec, dict):
                skipped += 1
                continue
            try:
                rid = int(rec.get("id") or 0)
            except (TypeError, ValueError):
                rid = 0
            if rid <= 0:
                skipped += 1
                continue
            rec = dict(rec)
            rec.pop("created_by", None)
            cur = conn.execute(
                "INSERT OR IGNORE INTO history (id, device, created_by, created_ts, updated_ts, updated_by, data) VALUES (?,?,?,?,?,?,?)",
                (rid, device, username, rid, now, username, json.dumps(rec, ensure_ascii=False)),
            )
            if cur.rowcount:
                added += 1
            else:
                skipped += 1
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return {"added": added, "skipped": skipped}


def update_record(rid: int, fields: dict, username: str, device: str) -> bool:
    """只改传进来的字段，其余保留（两个窗口改同一条的不同地方不会互相盖掉）。只能改本机的记录。"""
    fields = {k: v for k, v in (fields or {}).items() if k not in ("id", "created_by")}
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT data FROM history WHERE id = ? AND device = ?", (rid, device)).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return False
        data = json.loads(row[0] or "{}")
        data.update(fields)
        data["id"] = rid
        conn.execute(
            "UPDATE history SET data = ?, updated_ts = ?, updated_by = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), _now_ms(), username, rid),
        )
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return True


def delete_record(rid: int, device: str) -> bool:
    """只能删本机的记录。"""
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM history WHERE id = ? AND device = ?", (rid, device))
        return cur.rowcount > 0
    finally:
        conn.close()
