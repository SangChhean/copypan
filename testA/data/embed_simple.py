# -*- coding: utf-8 -*-
"""
简化版 embedding 生成脚本。
必须在 back_mic/backend/kg_rag/scripts/ 目录下运行：
    cd back_mic/backend/kg_rag/scripts
    python ../../../../testA/data/embed_simple.py --index galatians ...
"""
import sys
import asyncio
import argparse
import time
from pathlib import Path

from dotenv import load_dotenv

# 把 back_mic/backend 加入路径，才能 import embedding_adapter
_BACKEND = Path(__file__).resolve().parents[2] / "back_mic" / "backend"
sys.path.insert(0, str(_BACKEND))
load_dotenv(_BACKEND / ".env")

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from embedding_adapter import get_embeddings


def _batches(items, batch_size):
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


async def _embed_texts(texts):
    return await get_embeddings(texts, profile="kg_rag")


def process_batch(texts):
    if not texts:
        return []
    return asyncio.run(_embed_texts(texts))


def main():
    parser = argparse.ArgumentParser(description="简化版 Embedding 生成并写回 ES")
    parser.add_argument("--index", type=str, default="galatians", help="索引名（默认 galatians）")
    parser.add_argument("--es-url", type=str, default="http://localhost:9200", help="ES 地址")
    parser.add_argument("--es-user", type=str, default="", help="ES 用户名（可选）")
    parser.add_argument("--es-password", type=str, default="", help="ES 密码（可选）")
    parser.add_argument("--batch-size", type=int, default=50, help="每批条数（默认 50）")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不调 API、不写 ES")
    args = parser.parse_args()

    kwargs = {"hosts": [args.es_url], "request_timeout": 60}
    if args.es_user or args.es_password:
        kwargs["basic_auth"] = (args.es_user or "", args.es_password or "")

    try:
        es = Elasticsearch(**kwargs)
        if not es.ping():
            raise SystemExit("无法连接 Elasticsearch，请检查 --es-url 与认证")
    except Exception as e:
        raise SystemExit(f"连接 ES 失败: {e}") from e

    index_name = args.index
    if not es.indices.exists(index=index_name):
        raise SystemExit(f"索引不存在: {index_name}")

    no_emb_query = {"query": {"bool": {"must_not": [{"exists": {"field": "embedding"}}]}}}
    total_docs = es.count(index=index_name)["count"]
    docs_with_embedding = es.count(
        index=index_name,
        body={"query": {"exists": {"field": "embedding"}}},
    )["count"]
    docs_to_process = es.count(index=index_name, body=no_emb_query)["count"]

    print(f"  index:               {index_name}")
    print(f"  total docs:          {total_docs}")
    print(f"  with embedding:      {docs_with_embedding}")
    print(f"  without embedding:   {docs_to_process}")

    if args.dry_run:
        print("\n[dry-run] scan only, no API calls, no ES writes")
        return

    if docs_to_process == 0:
        print("all docs already have embeddings, nothing to do")
        return

    # Phase 1: scroll collect docs without embedding
    print("  scrolling to collect docs without embedding ...")
    all_hits = []
    scroll_body = {
        **no_emb_query,
        "_source": {"includes": ["chunk_id", "text"]},
        "size": 5000,
    }
    resp = es.search(index=index_name, body=scroll_body, scroll="2m")
    scroll_id = resp.get("_scroll_id")
    batch_hits = resp["hits"]["hits"]
    while batch_hits:
        all_hits.extend(batch_hits)
        resp = es.scroll(scroll_id=scroll_id, scroll="2m")
        scroll_id = resp.get("_scroll_id")
        batch_hits = resp["hits"]["hits"]
    if scroll_id:
        try:
            es.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass
    print(f"  collected {len(all_hits)} docs to process")

    # Phase 2: embed and write back
    success_count = 0
    failed_chunk_ids = []
    processed = 0
    batch_num = 0
    start_time = time.perf_counter()
    last_progress = 0
    target = len(all_hits)

    for sub_batch in _batches(all_hits, args.batch_size):
        batch_num += 1
        docs = []
        for h in sub_batch:
            src = h.get("_source") or {}
            docs.append({
                "chunk_id": src.get("chunk_id") or h.get("_id", ""),
                "text": (src.get("text") or "").strip(),
            })
        texts = [d["text"] or "" for d in docs]
        chunk_ids = [d["chunk_id"] for d in docs]

        vectors = None
        try:
            vectors = process_batch(texts)
        except Exception:
            time.sleep(5)
            try:
                vectors = process_batch(texts)
            except Exception as e2:
                failed_chunk_ids.extend(chunk_ids)
                print(f"  batch {batch_num} embedding failed (retried once): {e2}")
                time.sleep(1)
                processed += len(docs)
                continue

        if not vectors or len(vectors) != len(docs):
            failed_chunk_ids.extend(chunk_ids)
            time.sleep(1)
            processed += len(docs)
            continue

        actions = [
            {
                "_op_type": "update",
                "_index": index_name,
                "_id": d["chunk_id"],
                "doc": {"embedding": vec},
            }
            for d, vec in zip(docs, vectors)
        ]
        try:
            ok, errs = bulk(es, actions, raise_on_error=False, raise_on_exception=False)
            success_count += ok
            if errs:
                for item in errs:
                    if item.get("update", {}).get("error"):
                        failed_chunk_ids.append(item.get("update", {}).get("_id", ""))
        except Exception as exc:
            failed_chunk_ids.extend(chunk_ids)
            print(f"  batch {batch_num} ES write error: {exc}")

        processed += len(docs)
        if processed - last_progress >= 200 or processed >= target:
            print(
                f"  progress: {processed}/{target}"
                f"  ok={success_count}  fail={len(failed_chunk_ids)}"
            )
            last_progress = processed

        time.sleep(1)

    failed_count = len(failed_chunk_ids)
    print(f"\n=== summary ===")
    print(f"  success={success_count}  failed={failed_count}")


if __name__ == "__main__":
    main()
