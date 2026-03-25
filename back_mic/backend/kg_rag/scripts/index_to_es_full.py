# -*- coding: utf-8 -*-
"""读取 chunking_full.py 输出的 chunks JSON，创建 ES 索引并 bulk 写入。

六个数据源共用同一套 mapping；embedding 字段留空，后续由 generate_embeddings 回填。

用法示例：
    python -m kg_rag.scripts.index_to_es_full ^
        --input "E:\\12490_with_bib\\kg-rag_life_chunks.json" ^
        --index kg-rag_life ^
        --es-url http://localhost:9200 ^
        --es-user elastic ^
        --es-password qwSD4AF2Dcv ^
        --recreate
"""
import argparse
import json
import time
from pathlib import Path
from typing import Any

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

INDEX_SETTINGS: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "chunk_id":       {"type": "keyword"},
            "text":           {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
            "en":             {"type": "text", "index": False},
            "embedding":      {"type": "dense_vector", "dims": 1024, "index": True, "similarity": "cosine"},
            "book_title":     {"type": "keyword"},
            "author":         {"type": "keyword"},
            "year":           {"type": "integer"},
            "message_key":    {"type": "keyword"},
            "message_number": {"type": "integer"},
            "message_title":  {"type": "keyword"},
            "section_title":  {"type": "keyword"},
            "paragraph_type": {"type": "keyword"},
            "scripture_refs": {"type": "keyword"},
            "source_zh":      {"type": "text", "index": False},
            "source_en":      {"type": "text", "index": False},
            "tokens":         {"type": "integer"},
            "original_ids":   {"type": "keyword"},
        }
    },
}

WRITE_FIELDS = (
    "chunk_id", "text", "en",
    "book_title", "author", "year",
    "message_key", "message_number", "message_title",
    "section_title", "paragraph_type", "scripture_refs",
    "source_zh", "source_en", "tokens", "original_ids",
)


def _create_index(es: Elasticsearch, name: str) -> None:
    try:
        es.indices.create(index=name, body=INDEX_SETTINGS)
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in ("analysis", "analyzer", "ik_")):
            raise RuntimeError(
                "ES 未安装 IK 分词插件，请先安装 analysis-ik 后重试"
            ) from e
        raise


def _delete_index(es: Elasticsearch, name: str) -> None:
    if es.indices.exists(index=name):
        es.indices.delete(index=name)


def _bulk_index(
    es: Elasticsearch,
    index_name: str,
    chunks: list[dict[str, Any]],
    batch_size: int = 200,
) -> tuple[int, int]:
    total_ok = 0
    total_fail = 0
    n = len(chunks)
    logged = 0

    for start in range(0, n, batch_size):
        batch = chunks[start: start + batch_size]
        actions = []
        for ch in batch:
            doc: dict[str, Any] = {}
            for k in WRITE_FIELDS:
                v = ch.get(k)
                if v is None:
                    continue
                doc[k] = v
            actions.append({
                "_index": index_name,
                "_id": ch.get("chunk_id", ""),
                "_source": doc,
            })

        try:
            ok, errs = bulk(es, actions, raise_on_error=False, raise_on_exception=False)
            total_ok += ok
            if errs:
                for item in errs:
                    err = item.get("index", {}).get("error")
                    if err:
                        total_fail += 1
                        print(f"  FAIL _id={item['index'].get('_id')}: {err}")
        except Exception as exc:
            total_fail += len(batch)
            print(f"  batch exception: {exc}")

        logged += len(batch)
        if logged >= 2000 or start + batch_size >= n:
            print(f"  progress: {min(start + batch_size, n)}/{n}")
            logged = 0

    return total_ok, total_fail


def main() -> None:
    parser = argparse.ArgumentParser(description="KG-RAG full index builder")
    parser.add_argument("--input", required=True, help="chunks JSON file")
    parser.add_argument("--index", required=True, help="ES index name")
    parser.add_argument("--es-url", default="http://localhost:9200")
    parser.add_argument("--es-user", default="elastic")
    parser.add_argument("--es-password", default="")
    parser.add_argument("--recreate", action="store_true",
                        help="drop and recreate index if it exists")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"file not found: {input_path}")

    print(f"[index_to_es_full] loading {input_path} ...")
    with open(input_path, "r", encoding="utf-8") as f:
        chunks: list[dict] = json.load(f)
    if not isinstance(chunks, list):
        raise SystemExit("input JSON must be an array")

    before_len = len(chunks)
    chunks = [c for c in chunks if c.get("tokens", 0) > 0]
    skipped = before_len - len(chunks)
    if skipped:
        print(f"  filtered {skipped} chunks with tokens=0")
    print(f"  {len(chunks)} chunks to index")

    kwargs: dict[str, Any] = {"hosts": [args.es_url], "request_timeout": 120}
    if args.es_user or args.es_password:
        kwargs["basic_auth"] = (args.es_user or "", args.es_password or "")

    try:
        es = Elasticsearch(**kwargs)
        if not es.ping():
            raise SystemExit("cannot reach Elasticsearch")
    except Exception as e:
        raise SystemExit(f"ES connection failed: {e}") from e

    doc_count_before = 0
    try:
        if es.indices.exists(index=args.index):
            doc_count_before = es.count(index=args.index)["count"]
            if args.recreate:
                print(f"  dropping existing index '{args.index}' ...")
                _delete_index(es, args.index)
                _create_index(es, args.index)
            else:
                print(f"  appending to existing index '{args.index}' ({doc_count_before} docs)")
        else:
            _create_index(es, args.index)
            print(f"  created index '{args.index}'")
    except RuntimeError as e:
        raise SystemExit(str(e)) from e

    t0 = time.perf_counter()
    ok, fail = _bulk_index(es, args.index, chunks, args.batch_size)
    elapsed = time.perf_counter() - t0

    es.indices.refresh(index=args.index)
    try:
        doc_count_after = es.count(index=args.index)["count"]
    except Exception:
        doc_count_after = ok

    print(f"\n=== summary ===")
    print(f"  index:        {args.index}")
    print(f"  docs before:  {doc_count_before}")
    print(f"  docs after:   {doc_count_after}")
    print(f"  success:      {ok}")
    print(f"  failed:       {fail}")
    print(f"  elapsed:      {elapsed:.1f}s")


if __name__ == "__main__":
    main()
