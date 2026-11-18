# -*- coding: utf-8 -*-
"""【PanAI 新测试台 4.0】作纲目的费用与使用统计（与 3.0 的统计完全分开）。

一篇纲目 = 一个「本篇编号」（前端生成，放在请求头 X-T35-Outline-Session）。
负担说明、推荐重点、生成纲目每次请求都记一行（重做几次就记几行），行里带着这次请求实际调用的
每个模型步骤（calls：步骤名、模型、输入/输出 token、费用）。
- 页面：生成纲目后按本篇编号加总，显示这一篇从头做到尾的完整费用和各步骤明细。
- 后台「4.0作纲目」：按天数统计篇数、费用、纲目性质分布、每日统计、每篇明细。

存储：SQLite 文件（默认 backend 目录下 t35test_usage.db，可用环境变量 T35_USAGE_DB_PATH 改）。
*.db 已在 .gitignore 里，不进仓库；第一次用到时自动建表。
"""
import json
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "t35test_usage.db"
DB_PATH = os.environ.get("T35_USAGE_DB_PATH") or str(_DEFAULT_PATH)

# 步骤显示名与顺序（页面和后台共用）
STEP_LABELS: "OrderedDict[str, str]" = OrderedDict(
    [
        ("generate_burden", "负担说明"),
        ("firewall", "防火墙"),
        ("step1", "推荐重点"),
        ("step1_translate", "思考过程翻译"),
        ("step2", "骨架"),
        ("query_rewrite", "Query 改写"),
        ("step5", "生成纲目"),
    ]
)
KIND_LABELS = {"burden": "负担说明", "concepts": "推荐重点", "outline": "生成纲目"}

_init_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    global _initialized
    conn = sqlite3.connect(DB_PATH, timeout=15)
    if not _initialized:
        with _init_lock:
            if not _initialized:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS usage_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        ts INTEGER,
                        day TEXT,
                        username TEXT,
                        device TEXT,
                        kind TEXT,
                        query TEXT,
                        outline_nature TEXT,
                        loaded INTEGER DEFAULT 0,
                        cached INTEGER DEFAULT 0,
                        elapsed_ms REAL,
                        input_tokens INTEGER,
                        output_tokens INTEGER,
                        cost REAL,
                        calls TEXT
                    )"""
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_session ON usage_requests(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_day ON usage_requests(day)")
                conn.commit()
                _initialized = True
    return conn


def record_request(
    *,
    session_id: str,
    kind: str,
    username: str,
    device: str,
    query: str,
    outline_nature: str,
    loaded: bool,
    cached: bool,
    elapsed_ms: float,
    calls: list[dict[str, Any]],
) -> None:
    """记一次请求（负担说明 / 推荐重点 / 生成纲目）实际花的钱。"""
    clean = []
    for c in calls or []:
        if not isinstance(c, dict):
            continue
        clean.append(
            {
                "step": c.get("step") or "",
                "model": c.get("billing_model") or c.get("model") or "",
                "input_tokens": int(c.get("input_tokens") or 0),
                "output_tokens": int(c.get("output_tokens") or 0),
                "cost_usd": float(c.get("cost_usd") or 0.0),
            }
        )
    ti = sum(c["input_tokens"] for c in clean)
    to = sum(c["output_tokens"] for c in clean)
    tc = sum(c["cost_usd"] for c in clean)
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO usage_requests
               (session_id, ts, day, username, device, kind, query, outline_nature, loaded, cached,
                elapsed_ms, input_tokens, output_tokens, cost, calls)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id or "",
                int(now * 1000),
                datetime.fromtimestamp(now).strftime("%Y-%m-%d"),
                username or "",
                device or "",
                kind,
                (query or "")[:500],
                outline_nature or "",
                1 if loaded else 0,
                1 if cached else 0,
                float(elapsed_ms or 0.0),
                ti,
                to,
                round(tc, 6),
                json.dumps(clean, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _empty_steps() -> "OrderedDict[str, dict]":
    return OrderedDict((k, {"step": k, "label": v, "count": 0, "cost_usd": 0.0}) for k, v in STEP_LABELS.items())


def _add_calls(steps: "OrderedDict[str, dict]", calls_json: str) -> None:
    try:
        calls = json.loads(calls_json or "[]")
    except Exception:
        calls = []
    for c in calls:
        k = c.get("step") or "其他"
        if k not in steps:
            steps[k] = {"step": k, "label": STEP_LABELS.get(k, k), "count": 0, "cost_usd": 0.0}
        steps[k]["count"] += 1
        steps[k]["cost_usd"] += float(c.get("cost_usd") or 0.0)


def _finish_steps(steps: "OrderedDict[str, dict]", keep_empty: bool = False) -> list[dict]:
    out = []
    for s in steps.values():
        if s["count"] or keep_empty:
            out.append({**s, "cost_usd": round(s["cost_usd"], 6)})
    return out


_COLS = "session_id, ts, day, username, kind, query, outline_nature, loaded, cached, elapsed_ms, input_tokens, output_tokens, cost, calls"


def _summarize_session(rows: list[tuple]) -> dict:
    """把同一篇的多行请求合成一篇的摘要（rows 按时间先后）。"""
    steps = _empty_steps()
    kinds = {"burden": {"count": 0, "cost_usd": 0.0}, "concepts": {"count": 0, "cost_usd": 0.0}, "outline": {"count": 0, "cost_usd": 0.0}}
    total = ti = to = 0.0
    last_outline = None
    for r in rows:
        (sid, ts, day, user, kind, query, nature, loaded, cached, elapsed, inp, out, cost, calls) = r
        _add_calls(steps, calls)
        if kind in kinds:
            kinds[kind]["count"] += 1
            kinds[kind]["cost_usd"] += float(cost or 0.0)
        total += float(cost or 0.0)
        ti += int(inp or 0)
        to += int(out or 0)
        if kind == "outline":
            last_outline = r
    first, last = rows[0], rows[-1]
    ref = last_outline or last
    return {
        "session_id": first[0],
        "start_ts": first[1],
        "end_ts": last[1],
        "day": first[2],
        "username": ref[3],
        "query": ref[5],
        "outline_nature": ref[6] or next((x[6] for x in reversed(rows) if x[6]), ""),
        "loaded": any(x[7] for x in rows),
        "generated": last_outline is not None,
        "last_outline_cached": bool(last_outline[8]) if last_outline else False,
        "last_outline_cost_usd": round(float(last_outline[12] or 0.0), 6) if last_outline else None,
        "last_outline_elapsed_ms": float(last_outline[9] or 0.0) if last_outline else None,
        "input_tokens": int(ti),
        "output_tokens": int(to),
        "total_cost_usd": round(total, 6),
        "kinds": {k: {"label": KIND_LABELS[k], "count": v["count"], "cost_usd": round(v["cost_usd"], 6)} for k, v in kinds.items()},
        "steps": _finish_steps(steps),
    }


def session_summary(session_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT {_COLS} FROM usage_requests WHERE session_id = ? ORDER BY ts, id", (session_id,)
        ).fetchall()
    finally:
        conn.close()
    return _summarize_session(rows) if rows else None


def stats(days: int = 7, list_limit: int = 200) -> dict:
    """后台「4.0作纲目」用：最近 days 天（含今天）的统计。按「篇」算：篇的日期 = 这一篇第一次请求的日期。"""
    days = max(1, min(int(days or 7), 3650))
    today = datetime.now().date()
    start_day = (today - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    conn = _connect()
    try:
        # 先找出起始日期落在范围内的篇，再取这些篇的全部请求
        sids = [
            r[0]
            for r in conn.execute(
                "SELECT session_id FROM usage_requests GROUP BY session_id HAVING MIN(day) >= ?", (start_day,)
            ).fetchall()
        ]
        rows_by_sid: dict[str, list] = {s: [] for s in sids}
        if sids:
            for i in range(0, len(sids), 500):
                chunk = sids[i : i + 500]
                q = f"SELECT {_COLS} FROM usage_requests WHERE session_id IN ({','.join('?' * len(chunk))}) ORDER BY ts, id"
                for r in conn.execute(q, chunk).fetchall():
                    rows_by_sid[r[0]].append(r)
    finally:
        conn.close()

    sessions = [_summarize_session(rs) for rs in rows_by_sid.values() if rs]
    sessions.sort(key=lambda s: s["start_ts"], reverse=True)
    generated = [s for s in sessions if s["generated"]]
    full = [s for s in generated if not s["loaded"]]  # 从头做到尾的篇（不是载入记录的）

    steps = _empty_steps()
    total_cost = 0.0
    for rs in rows_by_sid.values():
        for r in rs:
            _add_calls(steps, r[13])
            total_cost += float(r[12] or 0.0)

    natures: dict[str, int] = {}
    for s in generated:
        n = s["outline_nature"] or "（未填）"
        natures[n] = natures.get(n, 0) + 1

    daily_map = OrderedDict()
    for i in range(days):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_map[d] = {"day": d, "outlines": 0, "sessions": 0, "cost_usd": 0.0}
    for s in sessions:
        d = daily_map.get(s["day"])
        if d is None:
            continue
        d["sessions"] += 1
        d["cost_usd"] += s["total_cost_usd"]
        if s["generated"]:
            d["outlines"] += 1

    outline_elapsed = [s["last_outline_elapsed_ms"] for s in generated if s["last_outline_elapsed_ms"] and not s["last_outline_cached"]]
    return {
        "days": days,
        "summary": {
            "sessions": len(sessions),
            "outlines": len(generated),
            "full_outlines": len(full),
            "cached_outlines": sum(1 for s in generated if s["last_outline_cached"]),
            "total_cost_usd": round(total_cost, 4),
            "avg_cost_per_full_outline_usd": round(sum(s["total_cost_usd"] for s in full) / len(full), 4) if full else None,
            "avg_outline_elapsed_ms": round(sum(outline_elapsed) / len(outline_elapsed), 1) if outline_elapsed else None,
        },
        "natures": [
            {"nature": k, "count": v, "percent": round(v * 100.0 / len(generated), 1)}
            for k, v in sorted(natures.items(), key=lambda kv: -kv[1])
        ],
        "steps": _finish_steps(steps, keep_empty=True),
        "daily": [{**d, "cost_usd": round(d["cost_usd"], 4)} for d in daily_map.values()],
        "sessions": sessions[:list_limit],
    }
