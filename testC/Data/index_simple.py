# -*- coding: utf-8 -*-
"""简化版 ES 建索引脚本：建索引 + bulk 写入 chunk（不含 embedding）"""
import argparse
import json
import os
import time
from pathlib import Path
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
            "source_zh": {"type": "keyword"},
        }
    }
}

BULK_FIELDS = ("chunk_id", "text", "book_title", "message_title", "source_zh")


def load_es_env() -> None:
    """从 .env 加载 ES 凭据（与 back_mic/backend/es_config.py 一致）。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    candidates = [
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parents[2] / "back_mic" / "backend" / ".env",
    ]
    for path in candidates:
        if path.exists():
            load_dotenv(path)
            return


def get_es(url: str, user: str, password: str) -> Elasticsearch:
    load_es_env()
    user = user or os.getenv("ES_USERNAME", "elastic")
    password = password if password else os.getenv("ES_PASSWORD", "")
    if url == "http://localhost:9200" and os.getenv("ES_HOST"):
        url = f"http://{os.getenv('ES_HOST')}:{os.getenv('ES_PORT', '9200')}"
    kwargs: dict = {"hosts": [url], "request_timeout": 60}
    if user or password:
        kwargs["basic_auth"] = (user, password)
    es = Elasticsearch(**kwargs)
    try:
        if not es.ping():
            raise SystemExit("无法连接 Elasticsearch（ping 返回 False），请检查地址与认证")
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(f"无法连接 Elasticsearch: {e}") from e
    return es


def create_index(es, index_name):
    try:
        es.indices.create(index=index_name, body=INDEX_MAPPING)
        print(f"索引 {index_name} 创建成功")
    except Exception as e:
        err = str(e).lower()
        if "ik" in err or "analyzer" in err or "analysis" in err:
            raise SystemExit("ES 未安装 IK 分词插件，请先安装 analysis-ik 后重试") from e
        raise


def bulk_index(es, index_name, chunks, batch_size=200):
    total_ok, total_fail = 0, 0
    num_batches = (len(chunks) + batch_size - 1) // batch_size
    for i in range(num_batches):
        batch = chunks[i * batch_size:(i + 1) * batch_size]
        actions = [
            {
                "_index": index_name,
                "_id": ch.get("chunk_id", ""),
                "_source": {k: ch.get(k) for k in BULK_FIELDS if k in ch},
            }
            for ch in batch
        ]
        try:
            ok, errs = bulk(es, actions, raise_on_error=False, raise_on_exception=False)
            total_ok += ok
            if errs:
                for item in errs:
                    if item.get("index", {}).get("error"):
                        total_fail += 1
                        print(f"  失败: _id={item['index'].get('_id')}: {item['index']['error']}")
            print(f"Batch {i+1}/{num_batches}: {len(batch)} 条")
        except Exception as e:
            total_fail += len(batch)
            print(f"Batch {i+1}/{num_batches} 异常: {e}")
    return total_ok, total_fail


def main():
    parser = argparse.ArgumentParser(description="简化版 ES 建索引与批量写入")
    parser.add_argument("--input", required=True, help="chunk JSONL 文件路径")
    parser.add_argument("--index", default="philippians-practice", help="索引名")
    parser.add_argument("--es-url", default="http://localhost:9200", help="ES 地址")
    parser.add_argument("--es-user", default="", help="ES 用户名")
    parser.add_argument("--es-password", default="", help="ES 密码")
    parser.add_argument("--recreate", action="store_true", help="先删除再重建索引")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"文件不存在: {input_path}")

    # 支持 JSONL 和 JSON 数组两种格式
    with open(input_path, encoding="utf-8") as f:
        first_char = f.read(1)
    with open(input_path, encoding="utf-8") as f:
        if first_char == "[":
            chunks = json.load(f)
        else:
            chunks = [json.loads(line) for line in f if line.strip()]
    print(f"读取 {len(chunks)} 条 chunk")

    es = get_es(args.es_url, args.es_user, args.es_password)

    doc_before = 0
    if es.indices.exists(index=args.index):
        doc_before = es.count(index=args.index)["count"]
        if args.recreate:
            es.indices.delete(index=args.index)
            print(f"已删除索引 {args.index}")
            create_index(es, args.index)
    else:
        create_index(es, args.index)

    start = time.perf_counter()
    ok, fail = bulk_index(es, args.index, chunks)
    elapsed = time.perf_counter() - start

    try:
        doc_after = es.count(index=args.index)["count"]
    except Exception:
        doc_after = ok

    print("\n── 统计 ──────────────────────")
    print(f"  索引名:       {args.index}")
    print(f"  写入前文档数: {doc_before}")
    print(f"  写入后文档数: {doc_after}")
    print(f"  成功: {ok}  失败: {fail}")
    print(f"  耗时: {elapsed:.2f}s")


if __name__ == "__main__":
    main()
