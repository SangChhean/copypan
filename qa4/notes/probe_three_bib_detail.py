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
from elasticsearch import Elasticsearch  # noqa: E402

CASES = [
    ("钉十字架的基督", "李常受文集一九五四年第三册，福音题纲"),
    ("问中之问", "李常受文集一九五四年第三册，福音题纲"),
    ("基督是谁（一）", "李常受文集一九七一年第二册，极大的奥秘—基督与召会"),
]


def main() -> None:
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    es = Elasticsearch(
        hosts=[s.es_url],
        basic_auth=(s.es_user or "", s.es_secret or ""),
        verify_certs=True,
    )
    rows = []
    for msg, book in CASES:
        print("=" * 60)
        print(book, msg)
        case = {"book": book, "message": msg, "indices": {}}
        for idx in ["qa4_outline_12490", "qa4_text_cwwl"]:
            body = {
                "size": 2,
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"book_title.keyword": book}},
                            {"match_phrase": {"message_title": msg}},
                        ]
                    }
                },
                "_source": True,
            }
            r = es.search(index=idx, body=body)
            tot = r["hits"]["total"]["value"] if isinstance(r["hits"]["total"], dict) else r["hits"]["total"]
            print(idx, "hits", tot)
            info = {"hits": tot, "samples": []}
            for h in r["hits"]["hits"]:
                src = h.get("_source") or {}
                sample = {
                    "chunk_id": src.get("chunk_id"),
                    "message_title": src.get("message_title"),
                    "has_source_en_key": "source_en" in src,
                    "source_en": src.get("source_en"),
                    "has_source_zh_key": "source_zh" in src,
                    "source_zh": src.get("source_zh"),
                    "field_keys": sorted(src.keys()),
                }
                info["samples"].append(sample)
                print(json.dumps(sample, ensure_ascii=False, indent=2))
            case["indices"][idx] = info
        rows.append(case)
    out = Path(__file__).with_name("probe_three_bib_detail_out.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
