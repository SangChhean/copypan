# -*- coding: utf-8 -*-
"""统计文本索引中 source_en 为空/缺失的文档，按 book_title（年份+册）汇总。

source_en 多为 index:false，不能靠 exists 查询；逐批拉 _source 计数。
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

backend = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend))
os.environ.setdefault("QA4_ENV_FILE", str(backend / ".env"))

from config import get_settings, reset_settings_cache  # noqa: E402
from elasticsearch import Elasticsearch  # noqa: E402

INDICES = [
    "qa4_text_cwwl",
    "qa4_text_life",
    "qa4_text_cwwn",
    "qa4_text_others",
    "qa4_map_note",
]


def scan_index(es: Elasticsearch, index: str, batch: int = 2000) -> dict:
    total = es.count(index=index)["count"]
    empty = 0
    missing_key = 0
    nonempty = 0
    by_book_empty: Counter = Counter()
    by_book_total: Counter = Counter()
    # 空值样例 source_en
    empty_samples: list[dict] = []

    resp = es.search(
        index=index,
        scroll="2m",
        size=batch,
        body={
            "query": {"match_all": {}},
            "_source": ["book_title", "source_en", "chunk_id"],
            "sort": ["_doc"],
        },
    )
    sid = resp.get("_scroll_id")
    while True:
        hits = (resp.get("hits") or {}).get("hits") or []
        if not hits:
            break
        for h in hits:
            src = h.get("_source") or {}
            bt = str(src.get("book_title") or "(无 book_title)")
            by_book_total[bt] += 1
            en = src.get("source_en")
            if "source_en" not in src:
                missing_key += 1
                empty += 1
                by_book_empty[bt] += 1
                if len(empty_samples) < 5:
                    empty_samples.append({"chunk_id": src.get("chunk_id"), "book_title": bt, "reason": "missing_key"})
            elif en is None or str(en).strip() == "":
                empty += 1
                by_book_empty[bt] += 1
                if len(empty_samples) < 5:
                    empty_samples.append({"chunk_id": src.get("chunk_id"), "book_title": bt, "reason": "empty_value"})
            else:
                nonempty += 1
        resp = es.scroll(scroll_id=sid, scroll="2m")
        sid = resp.get("_scroll_id")
    try:
        es.clear_scroll(scroll_id=sid)
    except Exception:
        pass

    top_empty = by_book_empty.most_common(30)
    top_detail = [
        {
            "book_title": bt,
            "empty": n,
            "total": by_book_total[bt],
            "empty_pct": round(100.0 * n / by_book_total[bt], 2) if by_book_total[bt] else 0,
        }
        for bt, n in top_empty
    ]
    return {
        "index": index,
        "total": total,
        "nonempty_source_en": nonempty,
        "empty_or_missing_source_en": empty,
        "missing_key": missing_key,
        "empty_pct": round(100.0 * empty / total, 2) if total else 0,
        "top_books_by_empty": top_detail,
        "empty_samples": empty_samples,
        "n_books_with_any_empty": len(by_book_empty),
        "n_books_total": len(by_book_total),
    }


def main() -> None:
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    es = Elasticsearch(
        hosts=[s.es_url],
        basic_auth=(s.es_user or "", s.es_secret or ""),
        verify_certs=True,
    )
    all_rows = []
    for idx in INDICES:
        print("scanning", idx, "...")
        row = scan_index(es, idx)
        all_rows.append(row)
        print(
            f"  total={row['total']} empty={row['empty_or_missing_source_en']} "
            f"({row['empty_pct']}%) nonempty={row['nonempty_source_en']} "
            f"books_with_empty={row['n_books_with_any_empty']}/{row['n_books_total']}"
        )
        for b in row["top_books_by_empty"][:10]:
            print(f"    {b['empty']:5d}/{b['total']:<5d} ({b['empty_pct']:5.1f}%) {b['book_title']}")
    out = Path(__file__).with_name("stats_empty_source_en_out.json")
    out.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
