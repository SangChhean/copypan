# -*- coding: utf-8 -*-
"""共享依赖：ES、Neo4j、Redis 客户端单例。"""
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_neo4j_client():
    from back_shared.neo4j_client import Neo4jClient
    return Neo4jClient()


def _es_base_url() -> str:
    """与 back_mic/backend/.env 对齐：ES_HOST 常为 localhost，需拼上 scheme 与端口。"""
    host = (os.environ.get("ES_HOST") or "localhost").strip()
    port = (os.environ.get("ES_PORT") or "9200").strip()
    if host.startswith("http://") or host.startswith("https://"):
        return host
    return f"http://{host}:{port}"


@lru_cache(maxsize=1)
def get_es_client():
    from elasticsearch import Elasticsearch
    user = os.environ.get("ES_USERNAME", "elastic")
    password = os.environ.get("ES_PASSWORD", "")
    return Elasticsearch(_es_base_url(), basic_auth=(user, password))


@lru_cache(maxsize=1)
def get_redis_client():
    try:
        import redis
        host = os.environ.get("REDIS_HOST", "localhost")
        port = int(os.environ.get("REDIS_PORT", "6379"))
        db = int(os.environ.get("REDIS_DB", "0"))
        client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        client.ping()
        return client
    except Exception as e:
        print(f"[QA] Redis 连接失败，缓存功能将降级: {e}")
        return None
