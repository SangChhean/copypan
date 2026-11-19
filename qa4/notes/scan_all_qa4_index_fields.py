# -*- coding: utf-8 -*-
"""全文扫描所有 qa4_* 索引：book_title / message_title / source_zh / source_en 有值/空/无字段。"""
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

FIELDS = ("book_title", "message_title", "source_zh", "source_en")


def classify(src: dict, field: str) -> str:
    if field not in src:
        return "missing_key"
    v = src.get(field)
    if v is None or (isinstance(v, str) and not v.strip()):
        return "empty"
    return "present"


def scan_index(es: Elasticsearch, index: str, batch: int = 2000) -> dict:
    mapping = es.indices.get_mapping(index=index)
    props = (list(mapping.values())[0].get("mappings") or {}).get("properties") or {}
    in_mapping = {f: f in props for f in FIELDS}
    total = es.count(index=index)["count"]
    counts = {f: {"present": 0, "empty": 0, "missing_key": 0} for f in FIELDS}
    samples = {f: {"present": None, "empty": None, "missing_key": None} for f in FIELDS}

    resp = es.search(
        index=index,
        body={
            "size": batch,
            "query": {"match_all": {}},
            "_source": list(FIELDS),
            "sort": ["_doc"],
        },
        scroll="3m",
    )
    sid = resp.get("_scroll_id")
    seen = 0
    while True:
        hits = (resp.get("hits") or {}).get("hits") or []
        if not hits:
            break
        for h in hits:
            src = h.get("_source") or {}
            seen += 1
            for f in FIELDS:
                kind = classify(src, f)
                counts[f][kind] += 1
                if samples[f][kind] is None:
                    samples[f][kind] = {k: src.get(k) for k in FIELDS}
        resp = es.scroll(scroll_id=sid, scroll="3m")
        sid = resp.get("_scroll_id")
    try:
        es.clear_scroll(scroll_id=sid)
    except Exception:
        pass

    # 再取 1 条完整样例（任意有 book_title 的）
    r1 = es.search(
        index=index,
        body={"size": 1, "query": {"match_all": {}}, "_source": list(FIELDS)},
    )
    any_sample = (r1["hits"]["hits"][0]["_source"] if r1["hits"]["hits"] else {})

    return {
        "index": index,
        "total": total,
        "scanned": seen,
        "in_mapping": in_mapping,
        "counts": counts,
        "samples_by_status": samples,
        "any_sample": any_sample,
    }


def main() -> None:
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    es = Elasticsearch(
        hosts=[s.es_url],
        basic_auth=(s.es_user or "", s.es_secret or ""),
        verify_certs=True,
    )
    names = sorted(es.indices.get_alias(index="qa4_*").keys())
    print("indices", names)
    rows = []
    for idx in names:
        print("scanning", idx, "...")
        row = scan_index(es, idx)
        rows.append(row)
        c = row["counts"]
        print(
            f"  total={row['total']} "
            f"book_title present/empty/miss={c['book_title']['present']}/{c['book_title']['empty']}/{c['book_title']['missing_key']} "
            f"source_en={c['source_en']['present']}/{c['source_en']['empty']}/{c['source_en']['missing_key']}"
        )
    out = Path(__file__).with_name("scan_all_qa4_index_fields_out.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
