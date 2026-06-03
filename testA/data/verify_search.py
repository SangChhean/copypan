# -*- coding: utf-8 -*-
"""
验证 ES 索引的 BM25 和 kNN 检索。
kNN 需在 back_mic/backend/kg_rag/scripts/ 目录下运行：
    cd back_mic/backend/kg_rag/scripts
    python ../../../../testA/data/verify_search.py --index galatians --query 基督的生命
"""
import sys
import asyncio
import argparse
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "back_mic" / "backend"))
load_dotenv(Path(__file__).resolve().parents[2] / "back_mic" / "backend" / ".env")

from elasticsearch import Elasticsearch
from embedding_adapter import get_embeddings


def _preview(text: str, n: int = 80) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= n:
        return text
    return text[:n] + "…"


def _chunk_id(hit: dict) -> str:
    src = hit.get("_source") or {}
    return src.get("chunk_id") or hit.get("_id", "")


def _text(hit: dict) -> str:
    src = hit.get("_source") or {}
    return src.get("text") or ""


def bm25_search(es: Elasticsearch, index: str, query: str, top_k: int = 5) -> list[dict]:
    body = {
        "size": top_k,
        "query": {"match": {"text": query}},
        "_source": ["chunk_id", "text"],
    }
    resp = es.search(index=index, body=body)
    return (resp.get("hits") or {}).get("hits") or []


async def _embed_query(query: str) -> list[float]:
    vectors = await get_embeddings([query], profile="kg_rag")
    if not vectors:
        raise RuntimeError("embedding 返回为空")
    return vectors[0]


def knn_search(es: Elasticsearch, index: str, query_vector: list[float], top_k: int = 5) -> list[dict]:
    body = {
        "size": top_k,
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": top_k,
            "num_candidates": max(top_k * 20, 100),
        },
        "_source": ["chunk_id", "text"],
    }
    resp = es.search(index=index, body=body)
    return (resp.get("hits") or {}).get("hits") or []


def print_hits(title: str, hits: list[dict]) -> None:
    print(f"\n=== {title} (top {len(hits)}) ===")
    if not hits:
        print("  (无结果)")
        return
    for i, hit in enumerate(hits, 1):
        score = hit.get("_score")
        cid = _chunk_id(hit)
        preview = _preview(_text(hit))
        print(f"  [{i}] chunk_id={cid}  score={score}")
        print(f"      {preview}")


def main() -> None:
    parser = argparse.ArgumentParser(description="验证 ES 索引 BM25 / kNN 检索")
    parser.add_argument("--index", type=str, default="galatians", help="索引名（默认 galatians）")
    parser.add_argument("--query", type=str, default="基督的生命", help="查询词")
    parser.add_argument("--es-url", type=str, default="http://localhost:9200", help="ES 地址")
    parser.add_argument("--es-user", type=str, default="", help="ES 用户名（可选）")
    parser.add_argument("--es-password", type=str, default="", help="ES 密码（可选）")
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

    if not es.indices.exists(index=args.index):
        raise SystemExit(f"索引不存在: {args.index}")

    print(f"index: {args.index}")
    print(f"query: {args.query}")

    bm25_hits = bm25_search(es, args.index, args.query)
    print_hits("BM25", bm25_hits)

    try:
        query_vector = asyncio.run(_embed_query(args.query))
    except Exception as e:
        raise SystemExit(f"查询 embedding 失败: {e}") from e

    knn_hits = knn_search(es, args.index, query_vector)
    print_hits("kNN", knn_hits)


if __name__ == "__main__":
    main()
