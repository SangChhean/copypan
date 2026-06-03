# -*- coding: utf-8 -*-
"""对 ephesians-test 索引做 BM25 与 kNN 检索测试。"""
import argparse
import asyncio
import sys
from pathlib import Path

from elasticsearch import Elasticsearch

# 保证可导入 back_mic/backend 下的 embedding_adapter
_BACKEND_DIR = Path(__file__).resolve().parents[2] / "back_mic" / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

# 加载 back_mic/backend/.env
try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND_DIR / ".env")
except ImportError:
    pass


def _print_hits(hits: list[dict]) -> None:
    """打印命中结果的 chunk_id 与 text 前 80 字。"""
    for i, h in enumerate(hits, 1):
        src = h.get("_source") or {}
        chunk_id = src.get("chunk_id") or h.get("_id", "")
        text = (src.get("text") or "")[:80]
        print(f"  {i}. [{chunk_id}] {text}")


def bm25_search(es: Elasticsearch, index: str, query: str, top_k: int = 5) -> None:
    """用 match 查询搜索 text 字段并打印结果。"""
    body = {
        "size": top_k,
        "query": {"match": {"text": query}},
        "_source": ["chunk_id", "text"],
    }
    resp = es.search(index=index, body=body)
    hits = resp["hits"]["hits"]
    print("=== BM25 检索结果 ===")
    _print_hits(hits)


async def _get_query_vector(query: str):
    """调用 embedding_adapter 取查询向量（取列表第一个）。"""
    from embedding_adapter import get_embeddings
    vectors = await get_embeddings([query], profile="kg_rag")
    return vectors[0]


def knn_search(es: Elasticsearch, index: str, query: str, top_k: int = 5) -> None:
    """对 embedding 字段做 kNN 检索并打印结果。"""
    vector = asyncio.run(_get_query_vector(query))
    body = {
        "size": top_k,
        "knn": {
            "field": "embedding",
            "query_vector": vector,
            "k": top_k,
            "num_candidates": 100,
        },
        "_source": ["chunk_id", "text"],
    }
    resp = es.search(index=index, body=body)
    hits = resp["hits"]["hits"]
    print("=== kNN 检索结果 ===")
    _print_hits(hits)


def main() -> None:
    """入口：解析参数、连接 ES，先 BM25 再 kNN 检索。"""
    parser = argparse.ArgumentParser(description="ephesians-test 检索测试（BM25 + kNN）")
    parser.add_argument(
        "--index",
        type=str,
        default="ephesians-test",
        help="索引名（默认 ephesians-test）",
    )
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="查询词（必填）",
    )
    parser.add_argument(
        "--es-url",
        type=str,
        default="http://localhost:9200",
        help="Elasticsearch 地址（默认 http://localhost:9200）",
    )
    parser.add_argument(
        "--es-user",
        type=str,
        default="elastic",
        help="ES 用户名（默认 elastic）",
    )
    parser.add_argument(
        "--es-password",
        type=str,
        default="qwSD4AF2Dcv",
        help="ES 密码（默认 qwSD4AF2Dcv）",
    )
    args = parser.parse_args()

    try:
        es = Elasticsearch(
            hosts=[args.es_url],
            basic_auth=(args.es_user, args.es_password),
            request_timeout=60,
        )
        if not es.ping():
            raise SystemExit("无法连接 Elasticsearch，请检查 --es-url 与认证")
    except Exception as e:
        raise SystemExit(f"连接 ES 失败: {e}") from e

    bm25_search(es, args.index, args.query)
    print()
    knn_search(es, args.index, args.query)


if __name__ == "__main__":
    main()
