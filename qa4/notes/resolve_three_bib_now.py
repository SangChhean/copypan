# -*- coding: utf-8 -*-
"""用当前 ES _source 模拟三条书目英译结果（区分 outline / text）。"""
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
from retrieval.config import reset_cache, source_fields  # noqa: E402
from retrieval.service import to_passage  # noqa: E402

CASES = [
    {
        "label": "李常受文集一九五四年第三册，福音题纲 钉十字架的基督",
        "outline_msg": "钉十字架的基督",
        "book": "李常受文集一九五四年第三册，福音题纲",
    },
    {
        "label": "李常受文集一九七一年第二册，极大的奥秘—基督与召会 基督是谁（一）",
        "text_msg": "基督是谁（一）",
        "book": "李常受文集一九七一年第二册，极大的奥秘—基督与召会",
    },
    {
        "label": "李常受文集一九五四年第三册，福音题纲 问中之问",
        "outline_msg": "问中之问",
        "book": "李常受文集一九五四年第三册，福音题纲",
    },
]


def main() -> None:
    reset_settings_cache()
    reset_cache()
    print("source_fields text_cwwl:", source_fields("text_cwwl"))
    print("source_fields outline_12490:", source_fields("outline_12490"))
    s = get_settings(require_runtime=False)
    es = Elasticsearch(
        hosts=[s.es_url],
        basic_auth=(s.es_user or "", s.es_secret or ""),
        verify_certs=True,
    )
    rows = []
    for case in CASES:
        print("=" * 60)
        print(case["label"])
        # outline path
        if case.get("outline_msg"):
            r = es.search(
                index="qa4_outline_12490",
                body={
                    "size": 1,
                    "query": {
                        "bool": {
                            "must": [
                                {"match_phrase": {"book_title": case["book"]}},
                                {"match_phrase": {"message_title": case["outline_msg"]}},
                            ]
                        }
                    },
                    "_source": True,
                },
            )
            if r["hits"]["hits"]:
                src = r["hits"]["hits"][0]["_source"]
                hit = dict(src)
                hit["_id"] = r["hits"]["hits"][0]["_id"]
                hit["_logical"] = "outline_12490"
                p = to_passage(hit)
                item = {
                    "n": 1,
                    "zh": f"[1] {p.book_title} {p.message_title}".strip(),
                    "en": p.location.get("source_en") or "",
                    "source_zh": p.location.get("source_zh") or "",
                    "book_title": p.book_title,
                    "message_number": p.location.get("message_number"),
                    "index": "outline_12490",
                }
                line, path = resolve_source_en_line(item)
                print("  via outline:", path, "->", line)
                print("  ES has source_en key?", "source_en" in src, "value=", repr(src.get("source_en")))
                print("  after to_passage location.source_en=", repr(p.location.get("source_en")))
                rows.append({"label": case["label"], "via": "outline", "path": path, "line": line, "item": item})
                continue
        # text path
        r = es.search(
            index="qa4_text_cwwl",
            body={
                "size": 1,
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"book_title.keyword": case["book"]}},
                            {"match_phrase": {"message_title": case.get("text_msg") or case.get("outline_msg")}},
                        ]
                    }
                },
                "_source": source_fields("text_cwwl"),
            },
        )
        if not r["hits"]["hits"]:
            print("  NO HIT")
            rows.append({"label": case["label"], "via": None, "path": None})
            continue
        src = r["hits"]["hits"][0]["_source"]
        hit = dict(src)
        hit["_id"] = r["hits"]["hits"][0]["_id"]
        hit["_logical"] = "text_cwwl"
        p = to_passage(hit)
        item = {
            "n": 1,
            "zh": f"[1] {p.book_title} {p.message_title}".strip(),
            "en": p.location.get("source_en") or "",
            "source_zh": p.location.get("source_zh") or "",
            "book_title": p.book_title,
            "message_number": p.location.get("message_number"),
            "index": "text_cwwl",
        }
        line, path = resolve_source_en_line(item)
        print("  via text_cwwl:", path, "->", line)
        print("  ES source_en=", repr(src.get("source_en")))
        print("  after to_passage=", repr(p.location.get("source_en")))

        # simulate OLD pipeline: _source without source_en
        hit_old = {k: v for k, v in hit.items() if k != "source_en"}
        p_old = to_passage(hit_old)
        item_old = {
            "n": 1,
            "zh": f"[1] {p_old.book_title} {p_old.message_title}".strip(),
            "en": p_old.location.get("source_en") or "",
            "source_zh": p_old.location.get("source_zh") or "",
            "book_title": p_old.book_title,
            "message_number": p_old.location.get("message_number"),
        }
        line_old, path_old = resolve_source_en_line(item_old)
        print("  OLD _source omit source_en ->", path_old, line_old)
        rows.append(
            {
                "label": case["label"],
                "via": "text_cwwl",
                "path": path,
                "line": line,
                "old_path": path_old,
                "old_line": line_old,
                "item": item,
            }
        )

    out = Path(__file__).with_name("resolve_three_bib_now_out.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
