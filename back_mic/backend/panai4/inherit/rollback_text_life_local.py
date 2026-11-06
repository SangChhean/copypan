# -*- coding: utf-8 -*-
"""回滚 panai4_text_life（local）。默认不写；加 --execute 才覆盖写回。
来源：G:\PanAI4.0专用\备份_text_life修订前_20261106\es_local_before.jsonl
"""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

BEFORE = Path(r"G:\PanAI4.0专用\备份_text_life修订前_20261106\es_local_before.jsonl")
INDEX = "panai4_text_life"
BATCH = 100

def make_es():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    return Elasticsearch(
        hosts=["http://localhost:9200"],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=180,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    docs = []
    with BEFORE.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                o = json.loads(line)
                cid = o.get("chunk_id") or o.get("_id")
                src = o.get("_source") if "_source" in o else o
                docs.append((cid, src))
    print("loaded=%s execute=%s" % (len(docs), args.execute))
    if not args.execute:
        print("dry-run only; pass --execute to write")
        return 0
    es = make_es()
    actions = [{"_op_type": "index", "_index": INDEX, "_id": cid, **src} for cid, src in docs]
    ok = fail = 0
    for i in range(0, len(actions), BATCH):
        success, errs = bulk(es, actions[i:i+BATCH], raise_on_error=False, raise_on_exception=False, request_timeout=180)
        ok += success
        if errs:
            fail += len(errs)
            print("ERR", errs[:2])
            break
        print("ok", ok)
    es.indices.refresh(index=INDEX)
    print("done ok=", ok, "fail=", fail, "count=", es.count(index=INDEX)["count"])
    return 0 if fail == 0 else 2

if __name__ == "__main__":
    raise SystemExit(main())
