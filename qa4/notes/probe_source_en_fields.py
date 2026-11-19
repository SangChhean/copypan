# -*- coding: utf-8 -*-
"""只读：查各文本/纲目索引是否有 source_en 等英文出处字段。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

backend = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend))
os.environ.setdefault("QA4_ENV_FILE", str(backend / ".env"))

from config import get_settings, load_index_map, reset_settings_cache  # noqa: E402
from elasticsearch import Elasticsearch  # noqa: E402

LOGICALS = [
    ("生命读经", "text_life"),
    ("新约总论", "text_others"),  # 通常在 others；同时看 outline_12490
    ("倪柝声文集", "text_cwwn"),
    ("李常受文集", "text_cwwl"),
    ("节期纲目", "outline_feasts"),
    ("一二四九〇纲目", "outline_12490"),
]
CHECK = ["source_en", "source_zh", "en", "book_title", "message_title", "name", "title", "year"]


def main() -> None:
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    kwargs: dict = {"hosts": [s.es_url], "verify_certs": True}
    if s.es_user or s.es_secret:
        kwargs["basic_auth"] = (s.es_user or "", s.es_secret or "")
    es = Elasticsearch(**kwargs)
    print("ping", es.ping())
    im = (load_index_map().get("indices") or {})
    out = []
    for label, logical in LOGICALS:
        meta = im.get(logical) or {}
        idx = meta.get("index") or f"qa4_{logical}"
        exists = bool(es.indices.exists(index=idx))
        row: dict = {"label": label, "logical": logical, "index": idx, "exists": exists}
        if not exists:
            out.append(row)
            print(json.dumps(row, ensure_ascii=False))
            continue
        m = es.indices.get_mapping(index=idx)
        props = ((list(m.values())[0].get("mappings") or {}).get("properties") or {})
        row["all_fields"] = sorted(props.keys())
        row["fields"] = {}
        for f in CHECK:
            if f in props:
                row["fields"][f] = {"present": True, "type": props[f].get("type")}
            else:
                row["fields"][f] = {"present": False}
        r = es.search(
            index=idx,
            body={
                "size": 2,
                "_source": CHECK,
                "query": {"match_all": {}},
            },
        )
        samples = []
        for h in (r.get("hits") or {}).get("hits") or []:
            src = h.get("_source") or {}
            samples.append(
                {
                    k: (str(src.get(k))[:100] if src.get(k) is not None else None)
                    for k in CHECK
                }
            )
        row["samples"] = samples
        # 非空 source_en 占比粗查
        try:
            nonempty = es.count(
                index=idx,
                body={"query": {"bool": {"must": [{"exists": {"field": "source_en"}}]}}},
            )["count"]
            total = es.count(index=idx)["count"]
            row["source_en_nonempty_approx"] = {"exists_field_count": nonempty, "total": total}
        except Exception as e:
            row["source_en_nonempty_approx"] = {"error": type(e).__name__}
        out.append(row)
        print("---")
        print(f"{label} / {logical} / {idx}")
        print("  source_en:", row["fields"]["source_en"])
        print("  source_zh:", row["fields"]["source_zh"])
        print("  en:", row["fields"]["en"])
        usable = [f for f in CHECK if row["fields"].get(f, {}).get("present")]
        print("  usable among check:", usable)
        print("  sample0:", samples[0] if samples else None)
        print("  counts:", row.get("source_en_nonempty_approx"))
    out_path = Path(__file__).with_name("probe_source_en_fields_out.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out_path)


if __name__ == "__main__":
    main()
