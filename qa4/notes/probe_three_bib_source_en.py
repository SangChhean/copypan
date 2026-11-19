# -*- coding: utf-8 -*-
"""查三条书目对应段落的 source_en。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

backend = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend))
os.environ.setdefault("QA4_ENV_FILE", str(backend / ".env"))

from config import get_settings, reset_settings_cache  # noqa: E402
from elasticsearch import Elasticsearch  # noqa: E402

CASES = [
    {
        "label": "李常受文集一九五四年第三册，福音题纲 钉十字架的基督",
        "book_keyword": "李常受文集一九五四年第三册，福音题纲",
        "msg_keyword": "钉十字架的基督",
    },
    {
        "label": "李常受文集一九七一年第二册，极大的奥秘—基督与召会 基督是谁（一）",
        "book_keyword": "李常受文集一九七一年第二册，极大的奥秘—基督与召会",
        "msg_keyword": "基督是谁（一）",
    },
    {
        "label": "李常受文集一九五四年第三册，福音题纲 问中之问",
        "book_keyword": "李常受文集一九五四年第三册，福音题纲",
        "msg_keyword": "问中之问",
    },
]
INDICES = ["qa4_text_cwwl", "qa4_outline_12490"]


def main() -> None:
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    es = Elasticsearch(
        hosts=[s.es_url],
        basic_auth=(s.es_user or "", s.es_secret or ""),
        verify_certs=True,
    )
    out = []
    for case in CASES:
        print("=" * 60)
        print(case["label"])
        row = {"label": case["label"], "hits": []}
        for idx in INDICES:
            # 1) book + message_title
            q1 = {
                "bool": {
                    "must": [
                        {"term": {"book_title.keyword": case["book_keyword"]}},
                        {"match_phrase": {"message_title": case["msg_keyword"]}},
                    ]
                }
            }
            r1 = es.search(
                index=idx,
                body={
                    "size": 3,
                    "query": q1,
                    "_source": [
                        "book_title",
                        "message_title",
                        "section_title",
                        "source_zh",
                        "source_en",
                        "chunk_id",
                    ],
                },
            )
            tot1 = r1["hits"]["total"]["value"] if isinstance(r1["hits"]["total"], dict) else r1["hits"]["total"]
            print(f"  [{idx}] book+message_title hits={tot1}")
            for h in r1["hits"]["hits"]:
                src = h.get("_source") or {}
                print(
                    "   ",
                    json.dumps(
                        {
                            "chunk_id": src.get("chunk_id"),
                            "message_title": src.get("message_title"),
                            "source_en": src.get("source_en"),
                            "source_zh": src.get("source_zh"),
                            "has_source_en": bool((src.get("source_en") or "").strip()),
                        },
                        ensure_ascii=False,
                    ),
                )
                row["hits"].append({"index": idx, "via": "book+message_title", **src})

            # 2) book + text contains msg keyword (gospel outline topics often in body)
            q2 = {
                "bool": {
                    "must": [
                        {"term": {"book_title.keyword": case["book_keyword"]}},
                        {"match_phrase": {"text": case["msg_keyword"]}},
                    ]
                }
            }
            r2 = es.search(
                index=idx,
                body={
                    "size": 3,
                    "query": q2,
                    "_source": [
                        "book_title",
                        "message_title",
                        "section_title",
                        "source_zh",
                        "source_en",
                        "chunk_id",
                    ],
                },
            )
            tot2 = r2["hits"]["total"]["value"] if isinstance(r2["hits"]["total"], dict) else r2["hits"]["total"]
            print(f"  [{idx}] book+text hits={tot2}")
            for h in r2["hits"]["hits"]:
                src = h.get("_source") or {}
                print(
                    "   ",
                    json.dumps(
                        {
                            "chunk_id": src.get("chunk_id"),
                            "message_title": src.get("message_title"),
                            "source_en": src.get("source_en"),
                            "source_zh": src.get("source_zh"),
                            "has_source_en": bool((src.get("source_en") or "").strip()),
                        },
                        ensure_ascii=False,
                    ),
                )
                row["hits"].append({"index": idx, "via": "book+text", **src})
        out.append(row)

    path = Path(__file__).with_name("probe_three_bib_source_en_out.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", path)


if __name__ == "__main__":
    main()
