# -*- coding: utf-8 -*-
"""简化版 embedding 生成脚本：扫描缺 embedding 的文档，批量生成并写回 ES。"""
import argparse
import asyncio
import sys
import time
from pathlib import Path
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(r"D:\copypan\back_mic\backend\.env")
except ImportError:
    pass

# 保证可导入 back_mic/backend 下的 embedding_adapter
sys.path.insert(0, str(Path(r"D:\copypan\back_mic\backend")))


def get_es(url, user, password):
    import os
    if not user:
        user = os.getenv("ES_USERNAME", "")
    if not password:
        password = os.getenv("ES_PASSWORD", "")
    if not url or url == "http://localhost:9200":
        host = os.getenv("ES_HOST", "localhost")
        port = os.getenv("ES_PORT", "9200")
        url = f"http://{host}:{port}"
    kwargs = {"hosts": [url], "request_timeout": 60}
    if user or password:
        kwargs["basic_auth"] = (user, password)
    es = Elasticsearch(**kwargs)
    if not es.ping():
        raise SystemExit("无法连接 Elasticsearch，请检查地址与认证")
    return es


async def _get_embeddings(texts):
    from embedding_adapter import get_embeddings
    return await get_embeddings(texts, profile="kg_rag")


def embed_batch(texts):
    return asyncio.run(_get_embeddings(texts))


def main():
    parser = argparse.ArgumentParser(description="简化版 Embedding 生成脚本")
    parser.add_argument("--index", default="philippians-practice", help="索引名")
    parser.add_argument("--es-url", default="http://localhost:9200", help="ES 地址")
    parser.add_argument("--es-user", default="", help="ES 用户名")
    parser.add_argument("--es-password", default="", help="ES 密码")
    parser.add_argument("--batch-size", type=int, default=50, help="每批条数（默认 50）")
    args = parser.parse_args()

    es = get_es(args.es_url, args.es_user, args.es_password)

    if not es.indices.exists(index=args.index):
        raise SystemExit(f"索引不存在: {args.index}")

    # 统计
    total = es.count(index=args.index)["count"]
    no_emb_query = {"query": {"bool": {"must_not": [{"exists": {"field": "embedding"}}]}}}
    to_process = es.count(index=args.index, body=no_emb_query)["count"]
    has_emb = total - to_process
    print(f"索引: {args.index}")
    print(f"总文档数: {total}  已有 embedding: {has_emb}  待处理: {to_process}")

    if to_process == 0:
        print("所有文档已有 embedding，无需处理")
        return

    # scroll 收集所有缺 embedding 的文档
    print("正在收集待处理文档...")
    all_hits = []
    scroll_body = {**no_emb_query, "_source": {"includes": ["chunk_id", "text"]}, "size": 500}
    resp = es.search(index=args.index, body=scroll_body, scroll="2m")
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
    print(f"收集到 {len(all_hits)} 条待处理文档")

    # 分批生成 embedding 并写回
    success, failed = 0, 0
    processed = 0
    start = time.perf_counter()
    batch_size = args.batch_size
    num_batches = (len(all_hits) + batch_size - 1) // batch_size

    for i in range(num_batches):
        batch = all_hits[i * batch_size:(i + 1) * batch_size]
        docs = [{"chunk_id": h.get("_source", {}).get("chunk_id") or h["_id"],
                 "text": (h.get("_source", {}).get("text") or "").strip()}
                for h in batch]
        texts = [d["text"] for d in docs]

        # 调用 embedding API，失败重试一次
        vectors = None
        try:
            vectors = embed_batch(texts)
        except Exception as e:
            time.sleep(5)
            try:
                vectors = embed_batch(texts)
            except Exception as e2:
                failed += len(batch)
                print(f"Batch {i+1}/{num_batches} embedding 失败: {e2}")
                processed += len(batch)
                continue

        if not vectors or len(vectors) != len(docs):
            failed += len(batch)
            processed += len(batch)
            continue

        # bulk update 写回 embedding
        actions = [
            {"_op_type": "update", "_index": args.index,
             "_id": d["chunk_id"], "doc": {"embedding": vec}}
            for d, vec in zip(docs, vectors)
        ]
        try:
            ok, errs = bulk(es, actions, raise_on_error=False, raise_on_exception=False)
            success += ok
            if errs:
                failed += len([e for e in errs if e.get("update", {}).get("error")])
        except Exception as e:
            failed += len(batch)
            print(f"Batch {i+1}/{num_batches} ES 写入失败: {e}")

        processed += len(batch)

        # 每 200 条打印进度
        if processed % 200 == 0 or processed >= len(all_hits):
            elapsed = time.perf_counter() - start
            print(f"进度: {processed}/{len(all_hits)}  成功: {success}  失败: {failed}  耗时: {elapsed:.0f}s")

        time.sleep(0.5)

    elapsed = time.perf_counter() - start
    print(f"\n── 完成 ──────────────────────")
    print(f"  索引: {args.index}")
    print(f"  处理: {processed}  成功: {success}  失败: {failed}")
    print(f"  耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
