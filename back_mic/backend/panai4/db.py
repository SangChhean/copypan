# -*- coding: utf-8 -*-
"""PanAI 4.0 SQLite。连接开启 WAL 与 foreign_keys。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LEGACY_CREATOR, db_path
from .pipeline import STEP_IDS

SCHEMA_VERSION = 2
_STATUS_RUN = ("pending", "queued", "running", "done", "failed", "interrupted", "cancelled")
_STATUS_ITEM = ("pending", "running", "done", "failed", "skipped", "interrupted", "cancelled")
PROMPT_STEPS = ("burden", "skeleton", "orig_skeleton", "diagnosis")
REBUILT_TABLES = ("runs", "run_items", "step_results")
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_ready = False


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _runs_sql(name: str, if_not_exists: bool = False) -> str:
    guard = "IF NOT EXISTS " if if_not_exists else ""
    return f"""
CREATE TABLE {guard}{name} (
    id             INTEGER PRIMARY KEY,
    created_at     TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ({_quoted(_STATUS_RUN)})),
    topic_set_id   INTEGER REFERENCES topic_sets(id) ON DELETE SET NULL,
    parent_run_id  INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    start_step     TEXT CHECK (start_step IS NULL OR start_step IN ({_quoted(STEP_IDS)})),
    main_scope     TEXT,
    analysis_scope TEXT,
    note           TEXT NOT NULL DEFAULT '',
    created_by     TEXT,
    prompt_selection TEXT,
    uses_test      INTEGER NOT NULL DEFAULT 0,
    started_at     TEXT,
    finished_at    TEXT
)"""


def _run_items_sql(name: str, if_not_exists: bool = False) -> str:
    guard = "IF NOT EXISTS " if if_not_exists else ""
    return f"""
CREATE TABLE {guard}{name} (
    id                INTEGER PRIMARY KEY,
    run_id            INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    position          INTEGER NOT NULL,
    title             TEXT NOT NULL,
    original_outline  TEXT,
    outline_hash      TEXT,
    status            TEXT NOT NULL CHECK (status IN ({_quoted(_STATUS_ITEM)})),
    error             TEXT,
    UNIQUE (run_id, position)
)"""


def _step_results_sql(name: str, if_not_exists: bool = False) -> str:
    guard = "IF NOT EXISTS " if if_not_exists else ""
    return f"""
CREATE TABLE {guard}{name} (
    id                          INTEGER PRIMARY KEY,
    run_item_id                 INTEGER NOT NULL REFERENCES run_items(id) ON DELETE CASCADE,
    step                        TEXT NOT NULL CHECK (step IN ({_quoted(STEP_IDS)})),
    prompt_name                 TEXT NOT NULL,
    prompt_version              TEXT NOT NULL,
    model                       TEXT NOT NULL,
    prompt_text                 TEXT NOT NULL,
    output_text                 TEXT,
    input_tokens                INTEGER,
    output_tokens               INTEGER,
    cache_creation_input_tokens INTEGER,
    cache_read_input_tokens     INTEGER,
    cache_creation_5m_tokens    INTEGER,
    cost_usd                    REAL,
    duration_ms                 INTEGER,
    stop_reason                 TEXT,
    status                      TEXT NOT NULL CHECK (status IN ({_quoted(_STATUS_ITEM)})),
    error                       TEXT,
    reused_from                 INTEGER REFERENCES step_results(id) ON DELETE SET NULL,
    created_at                  TEXT NOT NULL,
    content_blocks              TEXT,
    thinking_text               TEXT,
    prompt_test_version_id      INTEGER REFERENCES prompt_test_versions(id),
    UNIQUE (run_item_id, step)
)"""


_TABLE_SQL = {
    "runs": _runs_sql,
    "run_items": _run_items_sql,
    "step_results": _step_results_sql,
}

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_created_by ON runs(created_by);
CREATE INDEX IF NOT EXISTS idx_run_items_run ON run_items(run_id);
CREATE INDEX IF NOT EXISTS idx_step_results_item ON step_results(run_item_id);
CREATE INDEX IF NOT EXISTS idx_step_results_test ON step_results(prompt_test_version_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_topic_sets_name ON topic_sets(name);
"""


def _ddl() -> str:
    return f"""
CREATE TABLE IF NOT EXISTS topic_sets (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_set_items (
    id                INTEGER PRIMARY KEY,
    set_id            INTEGER NOT NULL REFERENCES topic_sets(id) ON DELETE CASCADE,
    position          INTEGER NOT NULL,
    title             TEXT NOT NULL,
    original_outline  TEXT,
    UNIQUE (set_id, position)
);
CREATE INDEX IF NOT EXISTS idx_topic_set_items_set ON topic_set_items(set_id);

CREATE TABLE IF NOT EXISTS prompt_test_versions (
    id                   INTEGER PRIMARY KEY,
    step                 TEXT NOT NULL CHECK (step IN ({_quoted(PROMPT_STEPS)})),
    prompt_name          TEXT NOT NULL,
    base_current_version TEXT NOT NULL,
    seq                  INTEGER NOT NULL,
    version_name         TEXT NOT NULL,
    parent_kind          TEXT NOT NULL CHECK (parent_kind IN ('current', 'test')),
    parent_version       TEXT NOT NULL,
    parent_test_id       INTEGER REFERENCES prompt_test_versions(id),
    template             TEXT NOT NULL,
    change_note          TEXT NOT NULL CHECK (length(trim(change_note)) > 0),
    created_by           TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    deleted_at           TEXT,
    deleted_by           TEXT,
    UNIQUE (step, base_current_version, seq),
    UNIQUE (step, version_name)
);

{_runs_sql("runs", True)};

{_run_items_sql("run_items", True)};

{_step_results_sql("step_results", True)};

CREATE TABLE IF NOT EXISTS orig_skeleton_cache (
    outline_hash            TEXT NOT NULL,
    prompt3_version         TEXT NOT NULL,
    output_text             TEXT NOT NULL,
    source_step_result_id   INTEGER REFERENCES step_results(id) ON DELETE SET NULL,
    created_at              TEXT NOT NULL,
    PRIMARY KEY (outline_hash, prompt3_version)
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def outline_hash_legacy(text: str) -> str:
    """旧算法：只统一换行并去掉首尾空白。仅用于兼容已有缓存。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def outline_hash(text: str) -> str:
    """只用于缓存键。不改变保存或送给模型的原文。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        blank = line == ""
        if blank and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = blank
    normalized = "\n".join(collapsed)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    _conn = conn
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _add_legacy_columns(conn: sqlite3.Connection) -> None:
    """第 1 版以前逐步加上的栏位。重建表之前先补齐，旧库才能整批复制。"""
    step_columns = set(_columns(conn, "step_results"))
    for column in ("content_blocks", "thinking_text"):
        if column not in step_columns:
            conn.execute(f"ALTER TABLE step_results ADD COLUMN {column} TEXT")
    run_columns = set(_columns(conn, "runs"))
    for column in ("main_scope", "analysis_scope"):
        if column not in run_columns:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {column} TEXT")
    conn.commit()


def backup_path_for(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


def _backup(conn: sqlite3.Connection) -> Path:
    target = backup_path_for(db_path())
    dest = sqlite3.connect(str(target))
    try:
        conn.backup(dest)
    finally:
        dest.close()
    return target


def _snapshot(conn: sqlite3.Connection) -> dict[str, tuple[int, str]]:
    shot = {}
    for table in REBUILT_TABLES + ("topic_sets", "topic_set_items", "orig_skeleton_cache"):
        count = conn.execute(f"SELECT COUNT(1) FROM {table}").fetchone()[0]
        if table == "orig_skeleton_cache":
            ids = conn.execute("SELECT group_concat(outline_hash || prompt3_version) FROM orig_skeleton_cache").fetchone()[0]
        else:
            ids = conn.execute(f"SELECT group_concat(id) FROM (SELECT id FROM {table} ORDER BY id)").fetchone()[0]
        digest = hashlib.sha256((ids or "").encode("utf-8")).hexdigest()
        shot[table] = (int(count), digest)
    return shot


migration_report: dict[str, Any] = {}


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """runs、run_items、step_results 的 CHECK 加入 queued、cancelled。SQLite 不能改 CHECK，只能重建表。

    做法依 SQLite 文档：关外键 → 事务内建新表、整批复制、删旧表、新表改回原名 → foreign_key_check → 提交。
    id 原样保留，所有互相引用不变。行数或 id 不一致即回滚。
    """
    backup = _backup(conn)
    before = _snapshot(conn)
    old_isolation = conn.isolation_level
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for table in REBUILT_TABLES:
            temp = f"{table}__v2"
            conn.execute(f"DROP TABLE IF EXISTS {temp}")
            conn.execute(_TABLE_SQL[table](temp))
            shared = [column for column in _columns(conn, table) if column in set(_columns(conn, temp))]
            names = ", ".join(shared)
            conn.execute(f"INSERT INTO {temp} ({names}) SELECT {names} FROM {table}")
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {temp} RENAME TO {table}")
        conn.execute(
            "UPDATE runs SET created_by = ? WHERE created_by IS NULL OR trim(created_by) = ''",
            (LEGACY_CREATOR,),
        )
        for statement in _INDEXES.strip().split(";"):
            if statement.strip():
                conn.execute(statement)
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        after = _snapshot(conn)
        if problems or after != before:
            conn.execute("ROLLBACK")
            raise RuntimeError(f"迁移核对不一致，已回滚。外键问题 {len(problems)} 条；迁移前 {before}；迁移后 {after}")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.isolation_level = old_isolation
    migration_report.clear()
    migration_report.update(
        {
            "backup": str(backup),
            "counts": {table: value[0] for table, value in before.items()},
            "ids_match": True,
        }
    )


def init_db() -> None:
    global _ready
    with _lock:
        if _ready:
            return
        conn = connect()
        existed = _table_exists(conn, "runs")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if existed and version < SCHEMA_VERSION:
            _add_legacy_columns(conn)
            conn.executescript(_ddl())
            _migrate_to_v2(conn)
        else:
            conn.executescript(_ddl())
            conn.executescript(_INDEXES)
            if not existed:
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        _ready = True


def _run_ids_with_status(conn: sqlite3.Connection, statuses: tuple[str, ...]) -> list[int]:
    marks = ",".join("?" for _ in statuses)
    return [row[0] for row in conn.execute(f"SELECT id FROM runs WHERE status IN ({marks})", statuses)]


def _close_run_rows(conn: sqlite3.Connection, run_id: int, status: str) -> None:
    conn.execute(
        f"""
        UPDATE step_results SET status = ?
        WHERE status IN ('pending', 'running')
          AND run_item_id IN (SELECT id FROM run_items WHERE run_id = ?)
        """,
        (status, run_id),
    )
    conn.execute(
        "UPDATE run_items SET status = ? WHERE run_id = ? AND status IN ('pending', 'running')",
        (status, run_id),
    )
    conn.execute(
        "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
        (status, utc_now(), run_id),
    )


def mark_running_interrupted() -> dict[str, int]:
    """启动时：运行中与排队中的运行，连同其下未完成的篇与步骤，标为 interrupted。"""
    init_db()
    with _lock:
        conn = connect()
        run_ids = _run_ids_with_status(conn, ("running", "queued", "pending"))
        for run_id in run_ids:
            _close_run_rows(conn, run_id, "interrupted")
        stray = conn.execute("UPDATE step_results SET status = 'interrupted' WHERE status = 'running'").rowcount
        conn.commit()
        return {"runs": len(run_ids), "stray_steps": stray}


def claim_next_queued() -> int | None:
    """取最早排队的一个，改为 running。"""
    init_db()
    with _lock:
        conn = connect()
        row = conn.execute("SELECT id FROM runs WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE runs SET status = 'running', started_at = ? WHERE id = ? AND status = 'queued'",
            (utc_now(), row["id"]),
        )
        conn.commit()
        return int(row["id"])


def queue_ahead(run_id: int) -> int:
    rows = _rows("SELECT COUNT(1) AS n FROM runs WHERE status = 'queued' AND id < ?", (run_id,))
    return int(rows[0]["n"]) if rows else 0


def cancel_run_rows(run_id: int) -> None:
    """已完成的步骤保留；未完成的步骤与篇、以及运行本身标为 cancelled。"""
    with _lock:
        conn = connect()
        _close_run_rows(conn, run_id, "cancelled")
        conn.commit()


def create_run(
    items: list[dict[str, Any]],
    note: str,
    steps: list[dict[str, Any]],
    parent_run_id: int | None = None,
    start_step: str | None = None,
    topic_set_id: int | None = None,
    main_scope: str | None = None,
    analysis_scope: str | None = None,
    created_by: str | None = None,
    prompt_selection: dict | None = None,
    uses_test: bool = False,
) -> int:
    """items: title, original_outline, outline_hash, position.
    steps: 每一步的初始状态。reused_from 有值表示沿用上一次的结果。新运行一律先排队。
    """
    init_db()
    now = utc_now()
    with _lock:
        conn = connect()
        cur = conn.execute(
            """
            INSERT INTO runs (
                created_at, status, topic_set_id, parent_run_id, start_step,
                main_scope, analysis_scope, note, created_by, prompt_selection, uses_test
            )
            VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                topic_set_id,
                parent_run_id,
                start_step,
                main_scope,
                analysis_scope,
                note or "",
                created_by,
                json.dumps(prompt_selection, ensure_ascii=False) if prompt_selection is not None else None,
                1 if uses_test else 0,
            ),
        )
        run_id = int(cur.lastrowid)
        pos_to_id: dict[int, int] = {}
        for item in items:
            cur = conn.execute(
                """
                INSERT INTO run_items
                    (run_id, position, title, original_outline, outline_hash, status, error)
                VALUES (?, ?, ?, ?, ?, 'pending', NULL)
                """,
                (
                    run_id,
                    item["position"],
                    item["title"],
                    item.get("original_outline"),
                    item.get("outline_hash"),
                ),
            )
            pos_to_id[item["position"]] = int(cur.lastrowid)
        for step in steps:
            item_id = pos_to_id[step["position"]]
            conn.execute(
                """
                INSERT INTO step_results (
                    run_item_id, step, prompt_name, prompt_version, model, prompt_text,
                    output_text, input_tokens, output_tokens,
                    cache_creation_input_tokens, cache_read_input_tokens, cache_creation_5m_tokens,
                    cost_usd, duration_ms, stop_reason, status, error, reused_from,
                    content_blocks, thinking_text, created_at, prompt_test_version_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    step["step"],
                    step.get("prompt_name") or "",
                    step.get("prompt_version") or "",
                    step.get("model") or "",
                    step.get("prompt_text") or "",
                    step.get("output_text"),
                    step.get("input_tokens"),
                    step.get("output_tokens"),
                    step.get("cache_creation_input_tokens"),
                    step.get("cache_read_input_tokens"),
                    step.get("cache_creation_5m_tokens"),
                    step.get("cost_usd"),
                    step.get("duration_ms"),
                    step.get("stop_reason"),
                    step["status"],
                    step.get("error"),
                    step.get("reused_from"),
                    step.get("content_blocks"),
                    step.get("thinking_text"),
                    now,
                    step.get("prompt_test_version_id"),
                ),
            )
        conn.commit()
        return run_id


def set_run_status(run_id: int, status: str) -> None:
    finished = utc_now() if status in {"done", "failed", "cancelled", "interrupted"} else None
    with _lock:
        if finished:
            connect().execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
                (status, finished, run_id),
            )
        else:
            connect().execute("UPDATE runs SET status = ? WHERE id = ?", (status, run_id))
        connect().commit()


def set_item_status(item_id: int, status: str, error: str | None = None) -> None:
    with _lock:
        connect().execute(
            "UPDATE run_items SET status = ?, error = ? WHERE id = ?",
            (status, error, item_id),
        )
        connect().commit()


def update_step(step_id: int, **fields: Any) -> None:
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [step_id]
    with _lock:
        connect().execute(f"UPDATE step_results SET {columns} WHERE id = ?", values)
        connect().commit()


def _rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with _lock:
        cur = connect().execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def get_run(run_id: int) -> dict[str, Any] | None:
    init_db()
    rows = _rows("SELECT * FROM runs WHERE id = ?", (run_id,))
    return rows[0] if rows else None


def list_runs(limit: int = 50, created_by: str | None = None) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: tuple = (limit,)
    if created_by is not None:
        where = "WHERE r.created_by = ?"
        params = (created_by, limit)
    return _rows(
        f"""
        SELECT r.*,
               (SELECT COUNT(*) FROM run_items i WHERE i.run_id = r.id) AS item_count,
               (SELECT COUNT(*) FROM run_items i WHERE i.run_id = r.id AND i.status = 'failed') AS failed_count,
               (SELECT COALESCE(SUM(s.cost_usd), 0)
                  FROM step_results s
                  JOIN run_items i ON i.id = s.run_item_id
                 WHERE i.run_id = r.id) AS cost_usd,
               (SELECT COUNT(*) FROM runs q WHERE q.status = 'queued' AND q.id < r.id) AS queue_ahead
        FROM runs r
        {where}
        ORDER BY r.id DESC
        LIMIT ?
        """,
        params,
    )


def creator_names() -> list[str]:
    """运行与测试版里用过的建立人，合并去重，最近用过的在前。"""
    init_db()
    rows = _rows(
        """
        SELECT name, MAX(at) AS last_at FROM (
            SELECT trim(created_by) AS name, created_at AS at FROM runs
             WHERE created_by IS NOT NULL AND trim(created_by) <> ''
            UNION ALL
            SELECT trim(created_by) AS name, created_at AS at FROM prompt_test_versions
             WHERE trim(created_by) <> ''
        )
        GROUP BY name
        ORDER BY last_at DESC
        """
    )
    return [row["name"] for row in rows]


def list_items(run_id: int) -> list[dict[str, Any]]:
    return _rows(
        "SELECT * FROM run_items WHERE run_id = ? ORDER BY position",
        (run_id,),
    )


def list_steps(item_id: int) -> list[dict[str, Any]]:
    rows = _rows(
        "SELECT * FROM step_results WHERE run_item_id = ? ORDER BY id",
        (item_id,),
    )
    order = {step: index for index, step in enumerate(STEP_IDS)}
    rows.sort(key=lambda row: order.get(row["step"], 99))
    return rows


def pending_steps(item_id: int) -> list[dict[str, Any]]:
    rows = [row for row in list_steps(item_id) if row["status"] == "pending"]
    return rows


def lookup_orig_cache(outline: str, prompt_version: str) -> dict[str, Any] | None:
    """新旧两种 hash 都查。只有旧 hash 命中时，按新 hash 再记一条。"""
    new_hash = outline_hash(outline)
    found = get_orig_cache(new_hash, prompt_version)
    if found:
        return found
    old_hash = outline_hash_legacy(outline)
    if old_hash == new_hash:
        return None
    found = get_orig_cache(old_hash, prompt_version)
    if not found:
        return None
    save_orig_cache(new_hash, prompt_version, found["output_text"], found.get("source_step_result_id"))
    return get_orig_cache(new_hash, prompt_version) or found


def orig_cache_exists(outline: str, prompt_version: str) -> bool:
    if not (outline or "").strip():
        return False
    if get_orig_cache(outline_hash(outline), prompt_version):
        return True
    old_hash = outline_hash_legacy(outline)
    if old_hash == outline_hash(outline):
        return False
    return get_orig_cache(old_hash, prompt_version) is not None


def cache_source_run_id(outline: str, prompt_version: str) -> int | None:
    if not (outline or "").strip():
        return None
    hashes = [outline_hash(outline)]
    legacy = outline_hash_legacy(outline)
    if legacy not in hashes:
        hashes.append(legacy)
    marks = ",".join("?" for _ in hashes)
    rows = _rows(
        f"""
        SELECT r.id AS run_id
        FROM orig_skeleton_cache c
        JOIN step_results s ON s.id = c.source_step_result_id
        JOIN run_items i ON i.id = s.run_item_id
        JOIN runs r ON r.id = i.run_id
        WHERE c.prompt3_version = ? AND c.outline_hash IN ({marks})
        LIMIT 1
        """,
        (prompt_version, *hashes),
    )
    return int(rows[0]["run_id"]) if rows else None


def get_orig_cache(outline_hash_value: str, prompt_version: str) -> dict[str, Any] | None:
    init_db()
    rows = _rows(
        """
        SELECT outline_hash, prompt3_version, output_text, source_step_result_id, created_at
        FROM orig_skeleton_cache
        WHERE outline_hash = ? AND prompt3_version = ?
        """,
        (outline_hash_value, prompt_version),
    )
    return rows[0] if rows else None


def save_orig_cache(
    outline_hash_value: str,
    prompt_version: str,
    output_text: str,
    source_step_result_id: int,
) -> None:
    init_db()
    with _lock:
        conn = connect()
        conn.execute(
            """
            INSERT INTO orig_skeleton_cache (
                outline_hash, prompt3_version, output_text, source_step_result_id, created_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(outline_hash, prompt3_version) DO UPDATE SET
                output_text = excluded.output_text,
                source_step_result_id = excluded.source_step_result_id,
                created_at = excluded.created_at
            """,
            (outline_hash_value, prompt_version, output_text, source_step_result_id, utc_now()),
        )
        conn.commit()


def list_topic_sets() -> list[dict[str, Any]]:
    init_db()
    return _rows(
        """
        SELECT s.id, s.name, s.created_at, s.updated_at,
               (SELECT COUNT(*) FROM topic_set_items i WHERE i.set_id = s.id) AS item_count
        FROM topic_sets s
        ORDER BY s.updated_at DESC, s.id DESC
        """
    )


def get_topic_set(set_id: int) -> dict[str, Any] | None:
    init_db()
    rows = _rows("SELECT * FROM topic_sets WHERE id = ?", (set_id,))
    if not rows:
        return None
    body = rows[0]
    body["items"] = _rows(
        """
        SELECT position, title, original_outline
        FROM topic_set_items
        WHERE set_id = ?
        ORDER BY position
        """,
        (set_id,),
    )
    return body


def topic_set_name_exists(name: str) -> bool:
    init_db()
    rows = _rows("SELECT 1 FROM topic_sets WHERE name = ? LIMIT 1", (name,))
    return bool(rows)


def create_topic_set(name: str, items: list[dict[str, Any]]) -> int:
    init_db()
    now = utc_now()
    with _lock:
        conn = connect()
        cur = conn.execute(
            "INSERT INTO topic_sets (name, created_at, updated_at) VALUES (?, ?, ?)",
            (name, now, now),
        )
        set_id = int(cur.lastrowid)
        for item in items:
            conn.execute(
                """
                INSERT INTO topic_set_items (set_id, position, title, original_outline)
                VALUES (?, ?, ?, ?)
                """,
                (set_id, item["position"], item["title"], item.get("original_outline")),
            )
        conn.commit()
        return set_id


def replace_topic_set_items(set_id: int, items: list[dict[str, Any]]) -> bool:
    init_db()
    with _lock:
        conn = connect()
        found = conn.execute("SELECT 1 FROM topic_sets WHERE id = ?", (set_id,)).fetchone()
        if found is None:
            return False
        conn.execute("DELETE FROM topic_set_items WHERE set_id = ?", (set_id,))
        for item in items:
            conn.execute(
                """
                INSERT INTO topic_set_items (set_id, position, title, original_outline)
                VALUES (?, ?, ?, ?)
                """,
                (set_id, item["position"], item["title"], item.get("original_outline")),
            )
        conn.execute(
            "UPDATE topic_sets SET updated_at = ? WHERE id = ?",
            (utc_now(), set_id),
        )
        conn.commit()
        return True


def delete_run(run_id: int) -> str:
    """删除一次运行。返回 deleted、missing 或 active（排队中或运行中）。

    run_items、step_results 由外键 CASCADE 连带删除。
    其他运行的 parent_run_id、reused_from，以及缓存的 source_step_result_id，由 SET NULL 置空，记录本身保留。
    """
    init_db()
    with _lock:
        conn = connect()
        row = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return "missing"
        if row["status"] in {"running", "queued"}:
            return "active"
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        conn.commit()
        return "deleted"


def delete_topic_set(set_id: int) -> bool:
    init_db()
    with _lock:
        conn = connect()
        cur = conn.execute("DELETE FROM topic_sets WHERE id = ?", (set_id,))
        conn.commit()
        return cur.rowcount > 0


_TEST_USED = """
    (SELECT COUNT(DISTINCT i.run_id)
       FROM step_results s
       JOIN run_items i ON i.id = s.run_item_id
      WHERE s.prompt_test_version_id = t.id AND s.reused_from IS NULL) AS used_count
"""


def next_test_seq(step: str, base_current_version: str) -> int:
    """编号不回收：已删除的也算在内。"""
    init_db()
    rows = _rows(
        "SELECT COALESCE(MAX(seq), 0) AS n FROM prompt_test_versions WHERE step = ? AND base_current_version = ?",
        (step, base_current_version),
    )
    return int(rows[0]["n"]) + 1


def create_prompt_test(
    *,
    step: str,
    prompt_name: str,
    base_current_version: str,
    parent_kind: str,
    parent_version: str,
    parent_test_id: int | None,
    template: str,
    change_note: str,
    created_by: str,
) -> int:
    init_db()
    with _lock:
        conn = connect()
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM prompt_test_versions WHERE step = ? AND base_current_version = ?",
            (step, base_current_version),
        ).fetchone()
        seq = int(row[0]) + 1
        cur = conn.execute(
            """
            INSERT INTO prompt_test_versions (
                step, prompt_name, base_current_version, seq, version_name,
                parent_kind, parent_version, parent_test_id, template, change_note,
                created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step,
                prompt_name,
                base_current_version,
                seq,
                f"{base_current_version}-测{seq}",
                parent_kind,
                parent_version,
                parent_test_id,
                template,
                change_note,
                created_by,
                utc_now(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_prompt_test(test_id: int) -> dict[str, Any] | None:
    init_db()
    rows = _rows(f"SELECT t.*, {_TEST_USED} FROM prompt_test_versions t WHERE t.id = ?", (test_id,))
    return rows[0] if rows else None


def get_prompt_tests(ids: set[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = _rows(
        f"SELECT id, step, version_name, created_by, deleted_at FROM prompt_test_versions WHERE id IN ({marks})",
        tuple(ids),
    )
    return {int(row["id"]): row for row in rows}


def list_prompt_tests() -> list[dict[str, Any]]:
    """未删除的测试版，不含全文。"""
    init_db()
    return _rows(
        f"""
        SELECT t.id, t.step, t.prompt_name, t.base_current_version, t.seq, t.version_name,
               t.parent_kind, t.parent_version, t.parent_test_id, t.change_note,
               t.created_by, t.created_at, {_TEST_USED}
        FROM prompt_test_versions t
        WHERE t.deleted_at IS NULL
        ORDER BY t.step, t.base_current_version, t.seq
        """
    )


def delete_prompt_test(test_id: int, deleted_by: str | None) -> dict[str, Any] | None:
    """标记删除。Prompt3 测试版的原纲目龙骨缓存一并删除。历史步骤里存的全文不动。"""
    init_db()
    with _lock:
        conn = connect()
        row = conn.execute(
            "SELECT id, step, version_name, deleted_at FROM prompt_test_versions WHERE id = ?",
            (test_id,),
        ).fetchone()
        if row is None or row["deleted_at"]:
            return None
        conn.execute(
            "UPDATE prompt_test_versions SET deleted_at = ?, deleted_by = ? WHERE id = ?",
            (utc_now(), deleted_by, test_id),
        )
        removed = 0
        if row["step"] == "orig_skeleton":
            removed = conn.execute(
                "DELETE FROM orig_skeleton_cache WHERE prompt3_version = ?",
                (row["version_name"],),
            ).rowcount
        conn.commit()
        return {"id": test_id, "version_name": row["version_name"], "cache_removed": removed}
