# -*- coding: utf-8 -*-
"""创建 testA 索引并 bulk 写入 chunk（life-galatians-test 等）。"""
import argparse
import json
import time
from pathlib import Path
from typing import Any

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "text": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "embedding": {
                "type": "dense_vector",
                "dims": 1024,
                "index": True,
                "similarity": "cosine",
            },
            "source_zh": {
                "type": "keyword",
            },
        }
    }
}

BULK_SOURCE_FIELDS = (
    "chunk_id",
    "text",
    "book_title",
    "message_title",
    "source_zh",
)


def create_index(es_client: Elasticsearch, index_name: str) -> None:
    """
    按 INDEX_MAPPING 创建索引。
    若 ES 未安装 IK 分词插件会抛出异常，脚本层捕获后提示安装 analysis-ik。
    """
    try:
        es_client.indices.create(index=index_name, body=INDEX_MAPPING)
    except Exception as e:
        err_msg = str(e).lower()
        if "analysis" in err_msg or "analyzer" in err_msg or "ik_" in err_msg or "ik_max_word" in err_msg:
            raise RuntimeError(
                "ES 未安装 IK 分词插件，请先安装 analysis-ik 后重试"
            ) from e
        raise


def delete_index(es_client: Elasticsearch, index_name: str) -> None:
    """删除索引（用于 --recreate）。"""
    if es_client.indices.exists(index=index_name):
        es_client.indices.delete(index=index_name)


def bulk_index(
    es_client: Elasticsearch,
    index_name: str,
    chunks: list[dict[str, Any]],
    batch_size: int = 200,
) -> tuple[int, int]:
    """
    使用 _bulk API 批量写入，文档 _id 使用 chunk_id（幂等）。
    只写入 BULK_SOURCE_FIELDS，不写入 embedding。
    返回 (成功数, 失败数)。
    """
    total_ok = 0
    total_fail = 0
    num_batches = (len(chunks) + batch_size - 1) // batch_size

    for batch_num in range(num_batches):
        start = batch_num * batch_size
        batch = chunks[start : start + batch_size]
        actions = []
        for ch in batch:
            doc = {k: ch.get(k) for k in BULK_SOURCE_FIELDS if k in ch}
            actions.append({
                "_index": index_name,
                "_id": ch.get("chunk_id", ""),
                "_source": doc,
            })
        try:
            ok, errs = bulk(
                es_client,
                actions,
                raise_on_error=False,
                raise_on_exception=False,
            )
            total_ok += ok
            if errs:
                for item in errs:
                    if item.get("index", {}).get("error"):
                        total_fail += 1
                        print(f"  失败文档 _id={item.get('index', {}).get('_id')}: {item['index']['error']}")
            print(f"Batch {batch_num + 1}/{num_batches}: {len(batch)} docs indexed")
        except Exception as e:
            total_fail += len(batch)
            print(f"Batch {batch_num + 1}/{num_batches} 异常: {e}")

    return total_ok, total_fail


def main() -> None:
    """入口：解析参数、连接 ES、可选 recreate、create_index、读取 chunk 文件、bulk_index、打印统计。"""
    parser = argparse.ArgumentParser(
        description="testA 索引创建与批量写入"
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="chunk JSON 文件路径（必填）",
    )
    parser.add_argument(
        "--es-url",
        type=str,
        default="http://localhost:9200",
        help="Elasticsearch 地址（默认 http://localhost:9200）",
    )
    parser.add_argument(
        "--index",
        type=str,
        default="galatians",
        help="索引名（默认 life-galatians-test）",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="若存在则先删除索引再重建；不加则追加模式",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="每批写入条数（默认 200）",
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
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    if not isinstance(chunks, list):
        raise SystemExit("输入 JSON 应为数组")

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
    doc_count_before = 0
    try:
        if es.indices.exists(index=index_name):
            doc_count_before = es.count(index=index_name)["count"]
            if args.recreate:
                delete_index(es, index_name)
                create_index(es, index_name)
        else:
            create_index(es, index_name)
    except RuntimeError as e:
        if "IK" in str(e):
            print(str(e))
            raise SystemExit(1) from e
        raise

    start_time = time.perf_counter()
    total_ok, total_fail = bulk_index(es, index_name, chunks, args.batch_size)
    elapsed = time.perf_counter() - start_time

    try:
        doc_count_after = es.count(index=index_name)["count"]
    except Exception:
        doc_count_after = total_ok

    print("\n统计：")
    print(f"  索引名: {index_name}")
    print(f"  写入前文档数: {doc_count_before}")
    print(f"  写入后文档数: {doc_count_after}")
    print(f"  成功: {total_ok}  失败: {total_fail}")
    print(f"  耗时: {elapsed:.2f}s")


if __name__ == "__main__":
    main()
