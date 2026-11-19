# -*- coding: utf-8 -*-
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

KEYWORDS = [
    "国殇",
    "冬季训练",
    "感恩节",
    "新年",
    "华语",
    "夏季训练",
    "春季长老",
    "秋季长老",
    "全时间",
    "夏训",
]


def main() -> None:
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    es = Elasticsearch(
        hosts=[s.es_url],
        basic_auth=(s.es_user or "", s.es_secret or ""),
        verify_certs=True,
    )
    # book_title 本身是 keyword
    r = es.search(
        index="qa4_outline_feasts",
        body={"size": 0, "aggs": {"bt": {"terms": {"field": "book_title", "size": 300}}}},
    )
    buckets = r["aggregations"]["bt"]["buckets"]
    print("n_unique_titles", len(buckets))
    picked = []
    used = set()
    for kw in KEYWORDS:
        for b in buckets:
            title = b["key"]
            if kw not in title or title in used:
                continue
            r2 = es.search(
                index="qa4_outline_feasts",
                body={
                    "size": 1,
                    "query": {"term": {"book_title": title}},
                    "_source": ["book_title", "message_title", "message_number", "year"],
                },
            )
            if not r2["hits"]["hits"]:
                continue
            src = r2["hits"]["hits"][0]["_source"]
            mn = src.get("message_number")
            rule_in = f"{src['book_title']}，第{mn}篇" if mn is not None else src["book_title"]
            en = translate_source_zh_to_en(rule_in)
            used.add(title)
            picked.append(
                {
                    "kw": kw,
                    "book_title": src["book_title"],
                    "message_title": src.get("message_title"),
                    "message_number": mn,
                    "zh": rule_in,
                    "en": en or "(翻不了)",
                    "ok": bool(en),
                }
            )
            print(f"{kw}: {rule_in} -> {en or '(翻不了)'}")
            break
        else:
            print(f"{kw}: NO TITLE FOUND")

    fails = []
    for b in buckets:
        if len(fails) >= 8:
            break
        t = b["key"]
        en = translate_source_zh_to_en(f"{t}，第1篇")
        if not en:
            fails.append(t)
    print("--- fail title examples ---")
    for t in fails:
        print(" ", t)

    out = {
        "picked": picked,
        "fail_title_examples": fails,
        "n_ok": sum(1 for p in picked if p["ok"]),
        "n_fail": sum(1 for p in picked if not p["ok"]),
    }
    path = Path(__file__).with_name("probe_feasts_10_rules_out.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", path)


if __name__ == "__main__":
    main()
