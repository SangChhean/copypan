# -*- coding: utf-8 -*-
"""
段落型/经文型：在原索引上追加 embedding 字段（dense_vector 512 维）。
纲目型：新建 {index}_chunks 索引，不改原索引。

使用方式：在 back_mic/backend 目录下执行
  python scripts/add_embedding_mapping.py

依赖：es_config.py 的 es 客户端（连接 ES 8.x，需 .env 配置 ES_PORT 等）。
"""
import sys
import os

# 确保从 backend 目录加载 es_config
_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_script_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# 段落型 + 经文型：原索引 put_mapping 追加 embedding
SIMPLE_INDICES = ["cwwl", "cwwn", "life", "others", "bib"]

# 纲目型：新建 {index}_chunks 索引，不改原索引
MAP_INDICES = ["map_7feasts", "map_note", "map_pano", "map_dictionary"]

EMBEDDING_MAPPING = {
    "type": "dense_vector",
    "dims": 512,
    "index": True,
    "similarity": "dot_product",
}

CHUNKS_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "parent_id": {"type": "keyword"},
            "text": {"type": "text"},
            "embedding": {
                "type": "dense_vector",
                "dims": 512,
                "index": True,
                "similarity": "dot_product",
            },
        }
    }
}


def has_embedding_field(es, index_name):
    """检查索引是否已有 embedding 字段。"""
    try:
        m = es.indices.get_mapping(index=index_name)
        props = m.get(index_name, {}).get("mappings", {}).get("properties", {})
        return "embedding" in props
    except Exception:
        return False


def index_exists(es, index_name):
    """检查索引是否存在。"""
    try:
        return bool(es.indices.exists(index=index_name))
    except Exception:
        return False


def main():
    from es_config import es

    success_count = 0
    skip_count = 0
    fail_count = 0

    for index_name in SIMPLE_INDICES:
        try:
            if has_embedding_field(es, index_name):
                print("[跳过] {} 已有 embedding 字段".format(index_name))
                skip_count += 1
                continue
            es.indices.put_mapping(
                index=index_name,
                body={"properties": {"embedding": EMBEDDING_MAPPING}},
            )
            print("[完成] {} embedding 字段已添加".format(index_name))
            success_count += 1
        except Exception as e:
            print("[失败] {}: {}".format(index_name, e))
            fail_count += 1

    for index_name in MAP_INDICES:
        chunks_index = "{}_chunks".format(index_name)
        try:
            if index_exists(es, chunks_index):
                print("[跳过] {} 已存在".format(chunks_index))
                skip_count += 1
                continue
            es.indices.create(index=chunks_index, body=CHUNKS_INDEX_MAPPING)
            print("[完成] {} 已创建".format(chunks_index))
            success_count += 1
        except Exception as e:
            print("[失败] {}: {}".format(chunks_index, e))
            fail_count += 1

    print()
    print("汇总：成功 {} 个，跳过 {} 个，失败 {} 个".format(success_count, skip_count, fail_count))


if __name__ == "__main__":
    main()
