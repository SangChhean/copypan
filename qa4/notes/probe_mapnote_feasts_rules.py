# -*- coding: utf-8 -*-
"""map_note 5 条 + feasts 10 条规则试跑；对照 qa4 书目显示。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

backend = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend))
os.environ.setdefault("QA4_ENV_FILE", str(backend / ".env"))

from config import get_settings, reset_settings_cache  # noqa: E402
from core.translate import translate_source_zh_to_en  # noqa: E402
from elasticsearch import Elasticsearch  # noqa: E402


def main() -> None:
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    es = Elasticsearch(
        hosts=[s.es_url],
        basic_auth=(s.es_user or "", s.es_secret or ""),
        verify_certs=True,
    )

    print("=" * 60)
    print("MAP_NOTE 5 samples")
    r = es.search(
        index="qa4_map_note",
        body={
            "size": 5,
            "query": {"match_all": {}},
            "_source": ["book_title", "message_title", "source_zh", "source_en", "chunk_id"],
        },
    )
    map_rows = []
    for h in r["hits"]["hits"]:
        src = h["_source"]
        zh = (src.get("source_zh") or "").strip()
        rule = translate_source_zh_to_en(zh)
        # qa4 书目显示：citations 用 book_title + message_title
        display = f"[n] {src.get('book_title') or ''} {src.get('message_title') or ''}".strip()
        row = {
            "chunk_id": src.get("chunk_id"),
            "book_title": src.get("book_title"),
            "message_title": src.get("message_title"),
            "source_zh": src.get("source_zh"),
            "source_en": src.get("source_en"),
            "qa4_bib_display": display,
            "rule_en": rule or "(empty=规则翻不了)",
        }
        map_rows.append(row)
        print(json.dumps(row, ensure_ascii=False, indent=2))

    print("=" * 60)
    print("FEASTS 10 diverse samples")
    want = [
        "国殇节",
        "冬季训练",
        "感恩节",
        "新年",
        "国际华语",
        "夏季训练",
        "春季长老",
        "秋季长老",
        "全时间",
        "冬训",
    ]
    feast_rows = []
    seen_types = set()
    for phrase in want:
        r = es.search(
            index="qa4_outline_feasts",
            body={
                "size": 1,
                "query": {"match_phrase": {"book_title": phrase}},
                "_source": ["book_title", "message_title", "message_number", "year", "conference"],
            },
        )
        if not r["hits"]["hits"]:
            continue
        src = r["hits"]["hits"][0]["_source"]
        bt = src.get("book_title") or ""
        if bt in seen_types:
            continue
        seen_types.add(bt)
        mn = src.get("message_number")
        # 规则输入：与 translate 兜底一致
        rule_in = f"{bt}，第{mn}篇" if mn is not None else bt
        rule = translate_source_zh_to_en(rule_in)
        # 也试仅 book_title
        rule2 = translate_source_zh_to_en(bt)
        row = {
            "book_title": bt,
            "message_title": src.get("message_title"),
            "message_number": mn,
            "year": src.get("year"),
            "rule_input": rule_in,
            "rule_en": rule or "(翻不了)",
            "rule_on_book_title_only": rule2 or "(翻不了)",
        }
        feast_rows.append(row)
        print(f"{rule_in} -> {row['rule_en']}")
        if len(feast_rows) >= 10:
            break

    # 补足到 10：随机再取
    if len(feast_rows) < 10:
        r = es.search(
            index="qa4_outline_feasts",
            body={
                "size": 30,
                "query": {"match_all": {}},
                "_source": ["book_title", "message_title", "message_number", "year"],
            },
        )
        for h in r["hits"]["hits"]:
            src = h["_source"]
            bt = src.get("book_title") or ""
            if bt in seen_types:
                continue
            seen_types.add(bt)
            mn = src.get("message_number")
            rule_in = f"{bt}，第{mn}篇" if mn is not None else bt
            rule = translate_source_zh_to_en(rule_in)
            feast_rows.append(
                {
                    "book_title": bt,
                    "message_title": src.get("message_title"),
                    "message_number": mn,
                    "year": src.get("year"),
                    "rule_input": rule_in,
                    "rule_en": rule or "(翻不了)",
                }
            )
            print(f"{rule_in} -> {rule or '(翻不了)'}")
            if len(feast_rows) >= 10:
                break

    out = Path(__file__).with_name("probe_mapnote_feasts_rules_out.json")
    out.write_text(
        json.dumps({"map_note": map_rows, "feasts": feast_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("wrote", out)


if __name__ == "__main__":
    main()
