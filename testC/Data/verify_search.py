# -*- coding: utf-8 -*-
"""验证 ES 索引的 BM25 和 kNN 检索"""
import argparse
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(r"D:\copypan\back_mic\backend\.env")
sys.path.insert(0, str(Path(r"D:\copypan\back_mic\backend")))

from elasticsearch import Elasticsearch


def get_es():
    host = os.getenv("ES_HOST", "localhost")
    port = os.getenv("ES_PORT", "9200")
    user = os.getenv("ES_USERNAME", "")
    password = os.getenv("ES_PASSWORD", "")
    es = Elasticsearch(
        f"http://{host}:{port}",
        basic_auth=(user, password),
        request_timeout=60
    )
    if not es.ping():
        raise SystemExit("无法连接 Elasticsearch")
    return es


def bm25_search(es, index, query, top_k=5):
    res = es.search(index=index, body={
        "query": {"match": {"text": query}},
        "size": top_k
    })
    return res["hits"]["hits"]


async def _get_vec(query):
    from embedding_adapter import get_embeddings
    vecs = await get_embeddings([query], profile="kg_rag")
    return vecs[0]


def knn_search(es, index, query, top_k=5):
    vec = asyncio.run(_get_vec(query))
    res = es.search(index=index, body={
        "knn": {
            "field": "embedding",
            "query_vector": vec,
            "k": top_k,
            "num_candidates": 100
        }
    })
    return res["hits"]["hits"]


def print_hits(hits):
    for i, hit in enumerate(hits, 1):
        chunk_id = hit["_source"].get("chunk_id", "")
        text = hit["_source"].get("text", "")[:80]
        score = hit["_score"]
        print(f"  {i}. [{chunk_id}] score={score:.4f}")
        print(f"     {text}")


def main():
    parser = argparse.ArgumentParser(description="验证 BM25 和 kNN 检索")
    parser.add_argument("--index", default="philippians-practice", help="索引名")
    parser.add_argument("--query", default="活基督", help="查询词")
    args = parser.parse_args()

    es = get_es()

    print(f"\n查询词：「{args.query}」")
    print(f"索引：{args.index}")

    print("\n── BM25 关键词检索 top5 ──────────────")
    bm25_hits = bm25_search(es, args.index, args.query)
    print_hits(bm25_hits)

    print("\n── kNN 语义检索 top5 ─────────────────")
    knn_hits = knn_search(es, args.index, args.query)
    print_hits(knn_hits)


if __name__ == "__main__":
    main()
