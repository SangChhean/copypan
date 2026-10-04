# -*- coding: utf-8 -*-
"""SC 专用表：sc_plain_cache / sc_runs。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from panai4 import db as panai4_db

_DDL = """
CREATE TABLE IF NOT EXISTS sc_plain_cache (
    id          INTEGER PRIMARY KEY,
    topic       TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    model       TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    result_text TEXT NOT NULL,
    usage_json  TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (topic, prompt_hash, model)
);

CREATE TABLE IF NOT EXISTS sc_runs (
    id                  INTEGER PRIMARY KEY,
    created_at          TEXT NOT NULL,
    topic               TEXT NOT NULL,
    select_prompt       TEXT,
    select_raw_output   TEXT,
    select_usage_json   TEXT,
    select_items_json   TEXT,
    final_terms_json    TEXT,
    skipped_json        TEXT,
    merged_json         TEXT,
    defs_chars          INTEGER,
    ref_prompt_full     TEXT,
    ref_result          TEXT,
    ref_usage_json      TEXT,
    plain_cache_id      INTEGER REFERENCES sc_plain_cache(id) ON DELETE SET NULL,
    plain_result        TEXT,
    plain_usage_json    TEXT,
    plain_from_cache    INTEGER,
    status              TEXT NOT NULL,
    error               TEXT
);

CREATE INDEX IF NOT EXISTS idx_sc_runs_created ON sc_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_sc_plain_topic ON sc_plain_cache(topic);
"""

_EXTRA_COLUMNS = {
    "sc_plain_cache": {
        "cost_usd": "REAL",
    },
    "sc_runs": {
        "cost_select_usd": "REAL",
        "cost_ref_usd": "REAL",
        "cost_plain_usd": "REAL",
        "cost_total_usd": "REAL",
    },
}

_ready = False


def ensure_tables() -> None:
    global _ready
    if _ready:
        return
    conn = panai4_db.connect()
    conn.executescript(_DDL)
    for table, cols in _EXTRA_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    conn.commit()
    _ready = True


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_plain_cache(topic: str, p_hash: str, model: str) -> dict | None:
    ensure_tables()
    conn = panai4_db.connect()
    row = conn.execute(
        "SELECT * FROM sc_plain_cache WHERE topic = ? AND prompt_hash = ? AND model = ?",
        (topic, p_hash, model),
    ).fetchone()
    return dict(row) if row else None


def upsert_plain_cache(
    topic: str,
    prompt_text: str,
    model: str,
    result_text: str,
    usage: dict | None,
    cost_usd: float | None = None,
) -> int:
    ensure_tables()
    conn = panai4_db.connect()
    p_hash = prompt_hash(prompt_text)
    now = panai4_db.utc_now()
    conn.execute(
        """
        INSERT INTO sc_plain_cache (topic, prompt_hash, model, prompt_text, result_text, usage_json, created_at, cost_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(topic, prompt_hash, model) DO UPDATE SET
            prompt_text = excluded.prompt_text,
            result_text = excluded.result_text,
            usage_json = excluded.usage_json,
            created_at = excluded.created_at,
            cost_usd = excluded.cost_usd
        """,
        (
            topic,
            p_hash,
            model,
            prompt_text,
            result_text,
            json.dumps(usage or {}, ensure_ascii=False),
            now,
            cost_usd,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM sc_plain_cache WHERE topic = ? AND prompt_hash = ? AND model = ?",
        (topic, p_hash, model),
    ).fetchone()
    return int(row["id"])


def create_run(**fields: Any) -> int:
    ensure_tables()
    conn = panai4_db.connect()
    cols = ["created_at", "status"]
    vals: list[Any] = [panai4_db.utc_now(), fields.get("status") or "done"]
    allowed = (
        "topic",
        "select_prompt",
        "select_raw_output",
        "select_usage_json",
        "select_items_json",
        "final_terms_json",
        "skipped_json",
        "merged_json",
        "defs_chars",
        "ref_prompt_full",
        "ref_result",
        "ref_usage_json",
        "plain_cache_id",
        "plain_result",
        "plain_usage_json",
        "plain_from_cache",
        "cost_select_usd",
        "cost_ref_usd",
        "cost_plain_usd",
        "cost_total_usd",
        "error",
    )
    for key in allowed:
        if key in fields and fields[key] is not None:
            cols.append(key)
            val = fields[key]
            if key.endswith("_json") and not isinstance(val, str):
                val = json.dumps(val, ensure_ascii=False)
            vals.append(val)
    placeholders = ", ".join("?" for _ in cols)
    cur = conn.execute(
        f"INSERT INTO sc_runs ({', '.join(cols)}) VALUES ({placeholders})",
        vals,
    )
    conn.commit()
    return int(cur.lastrowid)


def update_run(run_id: int, **fields: Any) -> None:
    ensure_tables()
    conn = panai4_db.connect()
    parts = []
    vals: list[Any] = []
    for key, val in fields.items():
        if key.endswith("_json") and val is not None and not isinstance(val, str):
            val = json.dumps(val, ensure_ascii=False)
        parts.append(f"{key} = ?")
        vals.append(val)
    vals.append(run_id)
    conn.execute(f"UPDATE sc_runs SET {', '.join(parts)} WHERE id = ?", vals)
    conn.commit()


def list_runs(limit: int = 50) -> dict:
    ensure_tables()
    conn = panai4_db.connect()
    rows = conn.execute(
        """
        SELECT id, created_at, topic, final_terms_json, status, error,
               cost_select_usd, cost_ref_usd, cost_plain_usd, cost_total_usd
        FROM sc_runs ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        terms = []
        if item.get("final_terms_json"):
            try:
                terms = json.loads(item["final_terms_json"])
            except json.JSONDecodeError:
                terms = []
        item["final_term_count"] = len(terms) if isinstance(terms, list) else 0
        total = item.get("cost_total_usd")
        item["cost_total_display"] = None if total is None else f"${float(total):.3f}"
        out.append(item)

    # 累计：有费用记录的运行，未舍入相加后再显示舍入
    sum_row = conn.execute(
        "SELECT COALESCE(SUM(cost_total_usd), 0), COUNT(cost_total_usd) FROM sc_runs WHERE cost_total_usd IS NOT NULL"
    ).fetchone()
    raw_sum = float(sum_row[0] or 0)
    counted = int(sum_row[1] or 0)
    return {
        "runs": out,
        "cost_sum_raw": raw_sum if counted else None,
        "cost_sum_display": f"${raw_sum:.3f}" if counted else "—",
        "cost_counted_runs": counted,
    }


def get_run(run_id: int) -> dict | None:
    ensure_tables()
    conn = panai4_db.connect()
    row = conn.execute("SELECT * FROM sc_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    for key in (
        "select_usage_json",
        "select_items_json",
        "final_terms_json",
        "skipped_json",
        "merged_json",
        "ref_usage_json",
        "plain_usage_json",
    ):
        if item.get(key):
            try:
                item[key.replace("_json", "")] = json.loads(item[key])
            except json.JSONDecodeError:
                item[key.replace("_json", "")] = None
    return item
