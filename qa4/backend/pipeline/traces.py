# -*- coding: utf-8 -*-
"""每问一条完整记录：SQLite 表 qa4_traces（独立库 qa4_traces.db）+ Redis 监控定长列表。

方案 A：默认存问题原文 / 截断后上文 / 改写后问题（可配置关掉）；哈希与长度始终保留。
Redis 监控列表与普通日志仍不含原文。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

_PREVIEW_CHARS = 60
_DAY_S = 86400.0


class TraceStore:
    def __init__(
        self,
        db_path: Path,
        *,
        retention_days: int = 90,
        store: Any = None,
        monitor_key: str = "monitor:traces",
        monitor_cap: int = 5000,
        store_question_text: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = int(retention_days)
        self.store = store
        self.monitor_key = monitor_key
        self.monitor_cap = int(monitor_cap)
        self.store_question_text = bool(store_question_text)
        self._lock = threading.Lock()
        self._last_purge_at: float = 0.0
        self._init()
        self.purge_expired(force=True)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS qa4_traces ("
                "request_id TEXT PRIMARY KEY, created_at REAL NOT NULL, "
                "question_hash TEXT NOT NULL, question_len INTEGER NOT NULL, "
                "cache_hit INTEGER NOT NULL DEFAULT 0, degraded INTEGER NOT NULL DEFAULT 0, "
                "record_json TEXT NOT NULL)"
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(qa4_traces)").fetchall()}
            for col, decl in (
                ("question_text", "TEXT"),
                ("history_json", "TEXT"),
                ("rewritten_question", "TEXT"),
            ):
                if col not in cols:
                    conn.execute(f"ALTER TABLE qa4_traces ADD COLUMN {col} {decl}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qa4_traces_created ON qa4_traces(created_at)")
            conn.commit()

    def purge_expired(self, *, force: bool = False, now: Optional[float] = None) -> int:
        """清理过期行。启动时 force；写入路径上每天最多一次。"""
        now = time.time() if now is None else float(now)
        if not force and (now - self._last_purge_at) < _DAY_S:
            return 0
        cutoff = now - self.retention_days * _DAY_S
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM qa4_traces WHERE created_at < ?", (cutoff,))
            n = cur.rowcount if cur.rowcount is not None else 0
            conn.commit()
        self._last_purge_at = now
        return int(n)

    def _monitor_payload(self, record: dict[str, Any]) -> str:
        """监控列表：只放哈希前 8 位、长度、耗时、缓存命中等，不放原文。"""
        slim = {
            "request_id": record.get("request_id"),
            "question_hash8": str(record.get("question_hash") or "")[:8],
            "question_len": record.get("question_len"),
            "timings_ms": record.get("timings_ms"),
            "cache_hit": record.get("cache_hit"),
            "degraded": record.get("degraded"),
            "not_found": record.get("not_found"),
            "main_type": record.get("main_type"),
            "elapsed_ms": record.get("elapsed_ms"),
            "retried": record.get("retried"),
        }
        return json.dumps(slim, ensure_ascii=False, default=str)

    def write(self, record: dict[str, Any], *, now: Optional[float] = None) -> None:
        now = time.time() if now is None else float(now)
        self.purge_expired(force=False, now=now)
        body = json.dumps(record, ensure_ascii=False, default=str)
        q_text = record.get("question_text") if self.store_question_text else None
        hist = record.get("history_json") if self.store_question_text else None
        rewritten = record.get("rewritten_question") if self.store_question_text else None
        if isinstance(hist, (list, dict)):
            hist = json.dumps(hist, ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO qa4_traces("
                "request_id, created_at, question_hash, question_len, cache_hit, degraded, "
                "record_json, question_text, history_json, rewritten_question) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    record["request_id"],
                    now,
                    record["question_hash"],
                    int(record["question_len"]),
                    1 if record.get("cache_hit") else 0,
                    1 if record.get("degraded") else 0,
                    body,
                    q_text,
                    hist,
                    rewritten or None,
                ),
            )
            conn.commit()
        if self.store is not None:
            try:
                self.store.push_capped(self.monitor_key, self._monitor_payload(record), self.monitor_cap)
            except Exception:
                pass

    def recent(self, n: int = 20) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT request_id, created_at, question_hash, question_len, cache_hit, degraded, "
                "question_text FROM qa4_traces ORDER BY created_at DESC LIMIT ?",
                (int(n),),
            ).fetchall()
        out = []
        for r in rows:
            preview = ""
            if r[6]:
                preview = str(r[6])[:_PREVIEW_CHARS]
            out.append(
                {
                    "request_id": r[0],
                    "created_at": r[1],
                    "question_hash": r[2],
                    "question_len": r[3],
                    "cache_hit": bool(r[4]),
                    "degraded": bool(r[5]),
                    "question_preview": preview,
                }
            )
        return out

    def get(self, request_id: str) -> Optional[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT record_json, question_text, history_json, rewritten_question FROM qa4_traces WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if not row:
            return None
        rec = json.loads(row[0])
        # 列优先（store_question_text=false 时列为 NULL，不覆盖 record 里可能残留的字段）
        if "question_text" not in rec or row[1] is not None or self.store_question_text:
            rec["question_text"] = row[1]
        if row[2] is not None:
            try:
                rec["history_json"] = json.loads(row[2])
            except Exception:
                rec["history_json"] = row[2]
        elif not self.store_question_text:
            rec["history_json"] = None
        if row[3] is not None or not self.store_question_text:
            rec["rewritten_question"] = row[3] or ""
        return rec

    def count(self) -> int:
        with self._lock, self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM qa4_traces").fetchone()[0])

    def stats(self, limit: int = 5000) -> dict[str, Any]:
        """对照 3.0 /api/qa/stats：从 SQLite traces 聚合（费用字段 qa4 未落库时为 0）。"""
        lim = max(1, min(int(limit), 20000))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT created_at, record_json, question_text FROM qa4_traces "
                "ORDER BY created_at DESC LIMIT ?",
                (lim,),
            ).fetchall()
        records: list[dict[str, Any]] = []
        for created_at, body, q_text in rows:
            try:
                rec = json.loads(body)
            except Exception:
                continue
            if not isinstance(rec, dict):
                continue
            if q_text and not rec.get("question_text"):
                rec["question_text"] = q_text
            rec["_created_at"] = created_at
            records.append(rec)

        total = len(records)
        cache_hits = sum(1 for r in records if r.get("cache_hit"))
        found_non_cache = [r for r in records if not r.get("cache_hit")]
        found_count = sum(1 for r in found_non_cache if not r.get("not_found"))
        step_fail = [r for r in found_non_cache if r.get("not_found")]

        elapsed_vals = [
            int(r.get("elapsed_ms") or 0)
            for r in found_non_cache
            if r.get("elapsed_ms") is not None
        ]
        avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0

        fail_out = []
        for r in step_fail[:20]:
            ts = r.get("_created_at")
            try:
                ts_s = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts))) if ts else ""
            except Exception:
                ts_s = str(ts or "")
            fail_out.append(
                {
                    "question": (r.get("question_text") or r.get("question_preview") or "")[:120],
                    "ts": ts_s,
                    "total_elapsed_ms": int(r.get("elapsed_ms") or 0),
                    "total_cost_usd": 0.0,
                    "request_id": r.get("request_id"),
                }
            )

        return {
            "total_requests": total,
            "cache_hit_rate": round(cache_hits / total, 4) if total else 0,
            "found_rate_new": round(found_count / len(found_non_cache), 4) if found_non_cache else 0,
            "total_cost_usd": 0.0,  # qa4 traces 未存 USD；保留字段对齐 3.0 UI
            "avg_elapsed_ms": avg_elapsed,
            "step_fail_records": fail_out,
        }

    def clear_monitor(self) -> dict[str, Any]:
        """清空 Redis 监控定长列表（对照 3.0 stats/clear）；不删 SQLite 记录。"""
        if self.store is None:
            return {"deleted": False, "key": self.monitor_key}
        try:
            ok = bool(self.store.delete(self.monitor_key))
        except Exception:
            ok = False
        return {"deleted": ok, "key": self.monitor_key}
