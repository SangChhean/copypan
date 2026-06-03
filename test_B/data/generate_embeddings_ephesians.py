# -*- coding: utf-8 -*-
"""对 ES 中无 embedding 的以弗所书文档批量生成 1024 维向量并写回。"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# 保证可导入 back_mic/backend 下的 embedding_adapter
_BACKEND_DIR = Path(__file__).resolve().parents[2] / "back_mic" / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

# 可选：加载 back_mic/backend/.env
try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND_DIR / ".env")
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
    同步包装：复用单个事件循环调用异步 get_embeddings，避免反复创建/关闭。
    """
    if not texts:
        return []
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_get_embeddings_kg_rag(texts))


def main() -> None:
    """入口：扫 ES（仅缺 embedding 的文档）、分批调用 Embedding API、bulk update 仅 embedding 字段。"""
    parser = argparse.ArgumentParser(
        description="以弗所书 Embedding 生成并写回 ES"
    )
    parser.add_argument(
        "--index",
        type=str,
        default="ephesians-test",
        help="索引名（默认 ephesians-test）",
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
    no_emb_query = {"query": {"bool": {"must_not": [{"exists": {"field": "embedding"}}]}}}
    docs_with_embedding = es.count(
        index=index_name,
        body={"query": {"exists": {"field": "embedding"}}},
    )["count"]
    docs_to_process = es.count(index=index_name, body=no_emb_query)["count"]

    print(f"  index:               {index_name}")
    print(f"  total docs:          {total_docs}")
    print(f"  with embedding:      {docs_with_embedding}")
    print(f"  without embedding:   {docs_to_process}")

    if docs_to_process == 0:
        print("all docs already have embeddings, nothing to do")
        return

    # ── Phase 1: collect all doc IDs + text via scroll ──────────────
    # We collect first, then process — this avoids scroll timeout issues
    # when embedding API calls are slow.  Memory is ~1 KB/doc (chunk_id +
    # text), so even 200K docs ≈ 200 MB which is fine.
    print("  scrolling to collect docs without embedding ...")
    all_hits: list[dict] = []
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

    # ── Phase 2: embed and write back ────────────────────────────────
    success_count = 0
    failed_chunk_ids: list[str] = []
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
            vectors = process_batch(chunk_ids, texts)
        except Exception:
            time.sleep(5)
            try:
                vectors = process_batch(chunk_ids, texts)
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
            {"_op_type": "update", "_index": index_name,
             "_id": d["chunk_id"], "doc": {"embedding": vec}}
            for d, vec in zip(docs, vectors)
        ]
        try:
            ok, errs = bulk(es, actions, raise_on_error=False, raise_on_exception=False)
            success_count += ok
            if errs:
                for item in errs:
                    if item.get("update", {}).get("error"):
                        failed_chunk_ids.append(item["update"].get("_id", ""))
        except Exception as exc:
            failed_chunk_ids.extend(chunk_ids)
            print(f"  batch {batch_num} ES write error: {exc}")

        processed += len(docs)
        if processed - last_progress >= 200 or processed >= target:
            elapsed_so_far = time.perf_counter() - start_time
            print(f"  progress: {processed}/{target}"
                  f"  ok={success_count}  fail={len(failed_chunk_ids)}"
                  f"  elapsed={elapsed_so_far:.0f}s")
            last_progress = processed

        time.sleep(1)

    elapsed = time.perf_counter() - start_time
    failed_count = len(failed_chunk_ids)

    print(f"\n=== summary ===")
    print(f"  index:            {index_name}")
    print(f"  total docs:       {total_docs}")
    print(f"  had embedding:    {docs_with_embedding}")
    print(f"  processed:        {processed}")
    print(f"  success:          {success_count}")
    print(f"  failed:           {failed_count}")
    if failed_chunk_ids:
        print(f"  failed ids:       {failed_chunk_ids[:50]}" + (" ..." if failed_count > 50 else ""))
    print(f"  elapsed:          {elapsed:.1f}s")
    if processed > 0:
        avg_tokens = 230
        print(f"  est tokens used:  ~{processed * avg_tokens // 1000}K tokens")


if __name__ == "__main__":
    main()
