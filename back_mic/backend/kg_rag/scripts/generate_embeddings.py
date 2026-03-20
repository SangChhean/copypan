# -*- coding: utf-8 -*-
"""对 ES 中无 embedding 的文档批量生成 1024 维向量并写回。"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# 保证可导入 back_mic/backend 下的 embedding_adapter
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 可选：若 embedding_adapter 未加载 .env，由脚本加载
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _batches(items, batch_size):
    """将列表按 batch_size 分批。"""
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


async def _get_embeddings_kg_rag(texts):
    """调用 embedding_adapter.get_embeddings(texts, profile='kg_rag')。"""
    from embedding_adapter import get_embeddings
    return await get_embeddings(texts, profile="kg_rag")


def process_batch(
    chunk_ids: list[str],
    texts: list[str],
) -> list[list[float]]:
    """
    对一批文本调用 embedding_adapter profile=kg_rag，返回向量列表。
    同步包装：内部使用 asyncio.run 调用异步 get_embeddings。
    """
    if not texts:
        return []
    return asyncio.run(_get_embeddings_kg_rag(texts))


def main() -> None:
    """入口：扫 ES（仅缺 embedding 的文档）、分批调用 Embedding API、bulk update 仅 embedding 字段。"""
    parser = argparse.ArgumentParser(
        description="KG-RAG Embedding 生成并写回 ES"
    )
    parser.add_argument(
        "--index",
        type=str,
        default="kg-rag_test",
        help="索引名（默认 kg-rag_test）",
    )
    parser.add_argument(
        "--es-url",
        type=str,
        default="http://localhost:9200",
        help="Elasticsearch 地址",
    )
    parser.add_argument(
        "--es-user",
        type=str,
        default="",
        help="ES 用户名（可选）",
    )
    parser.add_argument(
        "--es-password",
        type=str,
        default="",
        help="ES 密码（可选）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="每批条数（默认 50）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多处理条数，0 表示不限制（默认 0）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅扫描并打印统计，不调 API、不写 ES",
    )
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

    total_docs = es.count(index=index_name)["count"]
    docs_with_embedding = es.count(
        index=index_name,
        body={"query": {"exists": {"field": "embedding"}}},
    )["count"]
    docs_to_process = total_docs - docs_with_embedding

    # 扫描缺 embedding 的文档，只取 chunk_id 和 text
    body = {
        "query": {"bool": {"must_not": [{"exists": {"field": "embedding"}}]}},
        "_source": {"includes": ["chunk_id", "text"]},
        "size": 10000,
    }
    resp = es.search(index=index_name, body=body)
    hits = resp["hits"]["hits"]
    if args.limit > 0:
        hits = hits[: args.limit]
    docs_to_process_this_run = len(hits)

    if args.dry_run:
        print("【dry-run】仅扫描，不调用 API、不写 ES")
        print(f"  索引总文档数: {total_docs}")
        print(f"  已有 embedding 的文档数: {docs_with_embedding}")
        print(f"  本次需处理文档数: {docs_to_process_this_run}")
        if args.limit > 0:
            print(f"  (已应用 --limit {args.limit})")
        return

    if not hits:
        print("没有需要填充 embedding 的文档，退出")
        return

    success_count = 0
    failed_chunk_ids = []
    total_batches = (len(hits) + args.batch_size - 1) // args.batch_size
    start_time = time.perf_counter()

    for batch_num, batch in enumerate(_batches(hits, args.batch_size)):
        docs = []
        for h in batch:
            src = h.get("_source") or {}
            doc = {
                "chunk_id": src.get("chunk_id") or h.get("_id", ""),
                "text": (src.get("text") or "").strip(),
            }
            docs.append(doc)

        texts = [d["text"] or "" for d in docs]
        chunk_ids = [d["chunk_id"] for d in docs]

        vectors = None
        try:
            vectors = process_batch(chunk_ids, texts)
        except Exception as e1:
            time.sleep(5)
            try:
                vectors = process_batch(chunk_ids, texts)
            except Exception as e2:
                failed_chunk_ids.extend(chunk_ids)
                print(f"Batch {batch_num + 1}/{total_batches} Embedding 失败（已重试 1 次）: {e2}")
                time.sleep(1)
                continue

        if not vectors or len(vectors) != len(docs):
            failed_chunk_ids.extend(chunk_ids)
            time.sleep(1)
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
                        failed_chunk_ids.append(item["update"].get("_id", ""))
        except Exception as e:
            failed_chunk_ids.extend(chunk_ids)
            print(f"Batch {batch_num + 1}/{total_batches} ES 写入异常: {e}")

        done = min((batch_num + 1) * args.batch_size, len(hits))
        print(f"Batch {batch_num + 1}/{total_batches}: {len(docs)} docs embedded ({done}/{len(hits)} total)")
        time.sleep(1)

    elapsed = time.perf_counter() - start_time
    failed_count = len(failed_chunk_ids)

    print("\n统计：")
    print(f"  索引总文档数: {total_docs}")
    print(f"  已有 embedding 的文档数（本次运行前）: {docs_with_embedding}")
    print(f"  本次需处理文档数: {docs_to_process_this_run}")
    print(f"  成功生成: {success_count}")
    print(f"  失败: {failed_count}")
    if failed_chunk_ids:
        print(f"  失败 chunk_id 列表: {failed_chunk_ids[:50]}" + (" ..." if len(failed_chunk_ids) > 50 else ""))
    print(f"  总耗时: {elapsed:.2f}s")
    if docs_to_process_this_run > 0:
        avg_tokens = 230
        est_tokens = docs_to_process_this_run * avg_tokens
        print(f"  预估费用参考: 约 {docs_to_process_this_run} 条 × ~{avg_tokens} tokens/条 ≈ {est_tokens // 1000}K tokens")


if __name__ == "__main__":
    main()
