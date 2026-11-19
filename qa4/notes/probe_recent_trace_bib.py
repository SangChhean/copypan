# -*- coding: utf-8 -*-
"""读最近一条真实回答的书目，跑英译，列出仍为中文的条目。"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

backend = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend))
os.environ.setdefault("QA4_ENV_FILE", str(backend / ".env"))

from config import get_settings, reset_settings_cache  # noqa: E402
from core.translate import resolve_source_en_line  # noqa: E402


def main() -> None:
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    db = Path(s.traces_db_path)
    print("db", db, "exists", db.is_file())
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    print("tables", tables)
    # 找有 citations / answer 的表
    for t in tables:
        cols = [r[1] for r in con.execute(f"pragma table_info({t})")]
        print(t, cols)
    # 常见 traces 表
    for t in tables:
        cols = {r[1] for r in con.execute(f"pragma table_info({t})")}
        if "payload" in cols or "citations" in cols or "answer" in cols or "json" in cols:
            rows = list(con.execute(f"select * from {t} order by rowid desc limit 5"))
            print("--- sample from", t, "n=", len(rows))
            for r in rows[:2]:
                d = dict(r)
                print({k: (str(v)[:200] if v is not None else None) for k, v in d.items()})


if __name__ == "__main__":
    main()
