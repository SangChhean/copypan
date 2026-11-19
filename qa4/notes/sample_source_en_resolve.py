# -*- coding: utf-8 -*-
"""抽 11 类书目各一条，跑 resolve_source_en_line，汇报路径。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

backend = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend))
os.environ.setdefault("QA4_ENV_FILE", str(backend / ".env"))

from config import get_settings, reset_settings_cache  # noqa: E402
from core.translate import resolve_source_en_line  # noqa: E402
from elasticsearch import Elasticsearch  # noqa: E402
from retrieval.config import reset_cache as reset_retrieval_cache  # noqa: E402

CASES = [
    ("生命读经", "qa4_text_life", "book_title", "生命读经"),
    ("生命课程", "qa4_text_others", "book_title", "生命课程"),
    ("真理课程", "qa4_text_others", "book_title", "真理课程"),
    ("圣经真理题库", "qa4_text_others", "book_title", "圣经真理题库"),
    ("新约总论", "qa4_text_others", "book_title", "新约总论"),
    ("倪柝声文集", "qa4_text_cwwn", "book_title", "倪柝声文集"),
    ("李常受文集", "qa4_text_cwwl", "book_title", "李常受文集"),
    ("2015年冬季训练", "qa4_outline_feasts", "book_title", "2015年冬季训练"),
    ("2014年国殇节特会", "qa4_outline_feasts", "book_title", "2014年国殇节特会"),
    ("节期纲目一条", "qa4_outline_feasts", None, None),
]


def fetch_one(es: Elasticsearch, index: str, field: str | None, phrase: str | None) -> dict:
    if field and phrase:
        q = {"match_phrase": {field: phrase}}
    else:
        q = {"match_all": {}}
    r = es.search(
        index=index,
        body={
            "size": 1,
            "query": q,
            "_source": [
                "book_title",
                "message_title",
                "message_number",
                "source_zh",
                "source_en",
            ],
        },
    )
    hits = (r.get("hits") or {}).get("hits") or []
    return (hits[0].get("_source") or {}) if hits else {}


def main() -> None:
    reset_settings_cache()
    reset_retrieval_cache()
    s = get_settings(require_runtime=False)
    es = Elasticsearch(
        hosts=[s.es_url],
        basic_auth=(s.es_user or "", s.es_secret or ""),
        verify_certs=True,
    )
    rows = []
    for label, index, field, phrase in CASES:
        src = fetch_one(es, index, field, phrase)
        item = {
            "n": 1,
            "zh": f"[1] {src.get('book_title') or ''} {src.get('message_title') or ''}".strip(),
            "en": src.get("source_en") or "",
            "source_zh": src.get("source_zh") or "",
            "book_title": src.get("book_title") or "",
            "message_title": src.get("message_title") or "",
            "message_number": src.get("message_number"),
        }
        line, path = resolve_source_en_line(item)
        path_label = {"source_en": "用了 source_en", "rule": "用了规则", "zh": "保留中文"}[path]
        row = {
            "label": label,
            "index": index,
            "book_title": src.get("book_title"),
            "message_title": src.get("message_title"),
            "message_number": src.get("message_number"),
            "source_en_raw": src.get("source_en"),
            "source_zh_raw": src.get("source_zh"),
            "resolved": line,
            "path": path,
            "path_label": path_label,
        }
        rows.append(row)
        print(f"{label}: {path_label}")
        print(f"  zh: {item['zh'][:100]}")
        print(f"  en_raw: {item['en'][:100] if item['en'] else None}")
        print(f"  -> {line}")
    out = Path(__file__).with_name("sample_source_en_resolve_out.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
