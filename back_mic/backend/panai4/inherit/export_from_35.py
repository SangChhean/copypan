# -*- coding: utf-8 -*-
"""从本机 ES 导出五个 3.5 索引（排除 dense_vector），写出 JSONL。

用法（在 back_mic/backend 下）::

    python -m panai4.inherit.export_from_35
    python -m panai4.inherit.export_from_35 --out "G:/PanAI4.0专用/12490原文JSONL"

只读源索引，禁止写入/删除。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

EXPECTED = {
    "kg-rag_life": 39463,
    "kg-rag_cwwl": 178107,
    "kg-rag_cwwn": 32032,
    "kg-rag_others": 15481,
    "kg-rag_map_note": 16052,
}

DEFAULT_OUT = r"G:\PanAI4.0专用\12490原文JSONL"
PAGE_SIZE = 1000
KEEP_ALIVE = "5m"


def _backend_env() -> str:
    here = Path(__file__).resolve()
    backend = here.parents[2]
    return str(backend / ".env")


def make_local_es() -> Elasticsearch:
    load_dotenv(_backend_env())
    host = os.getenv("ES_HOST", "localhost")
    port = os.getenv("ES_PORT", "9200")
    user = os.getenv("ES_USERNAME", "elastic")
    password = os.getenv("ES_PASSWORD", "")
    return Elasticsearch(
        hosts=[f"http://{host}:{port}"],
        basic_auth=(user, password),
        request_timeout=120,
    )


def dense_vector_fields(es: Elasticsearch, index: str) -> list[str]:
    mapping = es.indices.get_mapping(index=index)
    props = mapping[index]["mappings"].get("properties") or {}
    found: list[str] = []

    def walk(prefix: str, node: dict) -> None:
        for name, spec in node.items():
            path = f"{prefix}.{name}" if prefix else name
            if not isinstance(spec, dict):
                continue
            if spec.get("type") == "dense_vector":
                found.append(path)
            if "properties" in spec:
                walk(path, spec["properties"])
            if "fields" in spec:
                walk(path, spec["fields"])

    walk("", props)
    return found


def export_index(es: Elasticsearch, index: str, out_path: Path) -> int:
    excludes = dense_vector_fields(es, index)
    print(f"EXPORT_START {index} exclude_vectors {excludes}", flush=True)

    pit = es.open_point_in_time(index=index, keep_alive=KEEP_ALIVE)
    pit_id = pit["id"]
    count = 0
    search_after = None
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with out_path.open("w", encoding="utf-8", newline="\n") as fp:
            while True:
                body = {
                    "size": PAGE_SIZE,
                    "pit": {"id": pit_id, "keep_alive": KEEP_ALIVE},
                    "sort": [{"_shard_doc": "asc"}],
                    "_source": {"excludes": excludes} if excludes else True,
                    "query": {"match_all": {}},
                }
                if search_after is not None:
                    body["search_after"] = search_after
                resp = es.search(body=body)
                pit_id = resp.get("pit_id") or pit_id
                hits = resp["hits"]["hits"]
                if not hits:
                    break
                for hit in hits:
                    src = hit.get("_source") or {}
                    # 保留 _id 便于溯源，但不改 _source；chunk_id 已在 source 内
                    fp.write(json.dumps(src, ensure_ascii=False) + "\n")
                    count += 1
                search_after = hits[-1]["sort"]
                if count % 10000 == 0:
                    print(f"PROGRESS {index} {count}", flush=True)
    finally:
        try:
            es.close_point_in_time(body={"id": pit_id})
        except Exception as exc:  # noqa: BLE001
            print(f"PIT_CLOSE_WARN {index} {exc}", flush=True)

    size = out_path.stat().st_size if out_path.is_file() else 0
    print(
        f"EXPORT_DONE {index} docs {count} bytes {size} "
        f"mb {size / 1024 / 1024:.2f}",
        flush=True,
    )
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export kg-rag_* from local ES")
    parser.add_argument("--out", default=DEFAULT_OUT, help="输出目录")
    parser.add_argument(
        "--indices",
        nargs="*",
        default=list(EXPECTED.keys()),
        help="要导出的索引名",
    )
    args = parser.parse_args(argv)

    es = make_local_es()
    if not es.ping():
        print("ES_UNREACHABLE local", flush=True)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for name in args.indices:
        if name not in EXPECTED:
            print(f"UNKNOWN_INDEX {name}", flush=True)
            return 2
        if not es.indices.exists(index=name):
            print(f"MISSING_INDEX {name}", flush=True)
            return 2
        # 只读确认：不要调用 delete/create/update
        path = out_dir / f"{name}.jsonl"
        n = export_index(es, name, path)
        results[name] = n
        expect = EXPECTED[name]
        if n != expect:
            print(
                f"COUNT_MISMATCH {name} exported {n} expected {expect}",
                flush=True,
            )
            print("STOP 导出条数与期望不一致，已停下。", flush=True)
            return 3

    print("ALL_EXPORT_OK", flush=True)
    for name, n in results.items():
        path = out_dir / f"{name}.jsonl"
        print(f"  {name}: {n} docs, {path.stat().st_size} bytes", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
