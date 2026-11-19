# -*- coding: utf-8 -*-
"""最近真实回答的 citations → 英译，列出仍中文条目。"""
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

_CJK = re.compile(r"[\u4e00-\u9fff]")


def main() -> None:
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    con = sqlite3.connect(str(s.traces_db_path))
    con.row_factory = sqlite3.Row
    rows = list(
        con.execute(
            "SELECT request_id, created_at, question_text, record_json "
            "FROM qa4_traces ORDER BY created_at DESC LIMIT 20"
        )
    )
    picked = None
    for r in rows:
        rec = json.loads(r["record_json"] or "{}")
        cites = rec.get("citations") or []
        if not cites:
            # 有的记在 answer / steps
            for k in ("answer", "done", "final"):
                if isinstance(rec.get(k), dict) and rec[k].get("citations"):
                    cites = rec[k]["citations"]
                    break
        if cites:
            picked = (r, rec, cites)
            break
    if not picked:
        print("NO_CITATIONS_IN_RECENT_TRACES")
        # dump keys of latest
        if rows:
            rec = json.loads(rows[0]["record_json"] or "{}")
            print("latest keys", sorted(rec.keys()))
            print("question", rows[0]["question_text"])
            print(json.dumps(rec, ensure_ascii=False)[:2000])
        return

    r, rec, cites = picked
    print("request_id", r["request_id"])
    print("question", r["question_text"])
    print("n_citations", len(cites))
    print("sample cite keys", sorted((cites[0] or {}).keys()) if cites else [])

    items = []
    still_zh = []
    for i, c in enumerate(cites):
        loc = (c or {}).get("location") or {}
        item = {
            "n": (c or {}).get("n") or i + 1,
            "zh": f"[{(c or {}).get('n') or i+1}] {(c or {}).get('book_title') or ''} {(c or {}).get('message_title') or ''}".strip(),
            "en": ((c or {}).get("source_en") or loc.get("source_en") or "").strip(),
            "source_zh": (loc.get("source_zh") or "").strip(),
            "book_title": (c or {}).get("book_title") or "",
            "message_title": (c or {}).get("message_title") or "",
            "message_number": loc.get("message_number"),
            "index": (c or {}).get("index") or "",
        }
        line, path = resolve_source_en_line(item, i)
        row = {**item, "resolved": line, "path": path}
        items.append(row)
        if path == "zh" or _CJK.search(line):
            reason = []
            if not item["en"]:
                reason.append("无 source_en（citation/location 皆空）")
            else:
                reason.append(f"有 source_en 但未采用？en={item['en'][:80]}")
            if item["index"] in ("outline_12490", "outline_feasts"):
                reason.append(f"来自纲目索引 {item['index']}（无 source_en 字段）")
            if path == "rule":
                reason.append("走了规则但仍含中文？")
            if path == "zh":
                reason.append("规则也无法识别")
            still_zh.append({**row, "reason": "；".join(reason)})

    print("--- all resolved ---")
    for it in items:
        print(f"  [{it['path']}] {it['resolved'][:120]}  (index={it['index']})")
    print("--- still Chinese ---")
    for it in still_zh:
        print(f"  {it['resolved']}")
        print(f"    reason: {it['reason']}")

    out = Path(__file__).with_name("probe_recent_trace_bib_out.json")
    out.write_text(
        json.dumps(
            {
                "request_id": r["request_id"],
                "question": r["question_text"],
                "items": items,
                "still_zh": still_zh,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", out)


if __name__ == "__main__":
    main()
