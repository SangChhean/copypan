# -*- coding: utf-8 -*-
"""panai4_hymns 集中配置（独立，不依赖 outline.config）。"""

from __future__ import annotations

import os
from pathlib import Path

INDEX_NAME = "panai4_hymns"
CHUNK_ID_PREFIX = "gmhymns"
VEC_FIELD = "embedding"
VEC_DIMS = 1024
SIMILARITY = "cosine"
INDEX_OPTIONS = {"type": "int8_hnsw"}

SOURCE_PATH = Path(r"C:\Users\28121\Desktop\可导入资料\hymns.json")
SOURCE_EXPECT_BYTES = 1_341_790
SOURCE_EXPECT_SHA256 = "CF9D6F11334FF6A97A98A8A9D737078A8CA9CD7622B5C28AFC3E7FDB204818E9"

DATA_ROOT = Path(r"G:\PanAI4.0专用\索引数据") / INDEX_NAME
DIR_SRC = DATA_ROOT / "01_源文件"
DIR_CLEAN = DATA_ROOT / "02_清洗JSON"
DIR_VEC = DATA_ROOT / "03_向量"
CLEAN_JSON = DIR_CLEAN / "chunks_hymns.json"
VEC_JSON = DIR_VEC / "chunks_hymns_vec.json"
MANIFEST = DATA_ROOT / "MANIFEST.md"
SHA256SUMS = DATA_ROOT / "SHA256SUMS.txt"
SOURCE_MD = DIR_SRC / "SOURCE.md"
SOURCE_COPY = DIR_SRC / "hymns.json"

REPORT_PATH = Path(__file__).resolve().parents[4] / "docs" / "panai4_es" / "hymns_index.md"
README_INDEX = Path(r"G:\PanAI4.0专用\索引数据\README.md")

EXPECT_SERIES = {"诗歌": 780, "诗歌附": 6, "补充本诗歌": 513}
EXPECT_HYMNS = 1299
EXPECT_FULL = 1299
EXPECT_STANZA = 5836
EXPECT_CHORUS = 2019
EXPECT_UNITS = 7855
EXPECT_TOTAL = 9154

PRICE_PER_MILLION = 0.01  # OpenRouter qwen3-embedding-8b
COST_GATE_USD = 0.05
TOKEN_INFLATE = 1.155

BATCH_SIZE = 50
CONCURRENCY = 5
BATCH_PAUSE = 0.2
RETRY_WAITS = (1, 2, 4, 8, 16)

BULK_SIZE_LOCAL = 200
BULK_SIZE_REMOTE = 100

REMOTE_ENV_KEYS = (
    "ES_REMOTE_HOST",
    "ES_REMOTE_PORT",
    "ES_REMOTE_USERNAME",
    "ES_REMOTE_PASSWORD",
)
EMBED_ENV_KEYS = ("OPENROUTER_API_KEY", "EMBEDDING_KG_MODEL", "EMBEDDING_KG_DIMS")
LOCAL_ES_ENV_KEYS = ("ES_HOST", "ES_PORT", "ES_USERNAME", "ES_PASSWORD")

OTHER_PANAI4_EXPECT = {
    "panai4_outline_12490": 55841,
    "panai4_outline_feasts": 11110,
    "panai4_bible": 3691,
    "panai4_text_life": 39463,
    "panai4_text_cwwl": 178107,
    "panai4_text_cwwn": 32032,
    "panai4_text_others": 15481,
    "panai4_map_note": 16052,
    "panai4_pano_catalog": 53151,
}

SAMPLE_SEED = 20261106


def backend_env() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def mapping_body() -> dict:
    """与 outline 索引同风格：IK + dense_vector 1024 cosine int8_hnsw。"""
    props = {
        "chunk_id": {"type": "keyword"},
        "message_key": {"type": "keyword"},
        "series": {"type": "keyword"},
        "hymn_number": {"type": "integer"},
        "name": {
            "type": "keyword",
            "fields": {
                "text": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                }
            },
        },
        "title": {
            "type": "keyword",
            "fields": {
                "text": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                }
            },
        },
        "category": {"type": "keyword"},
        "subtitle": {
            "type": "keyword",
            "fields": {
                "text": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                }
            },
        },
        "reference": {"type": "keyword", "index": False},
        "unit_type": {"type": "keyword"},
        "unit_label": {"type": "keyword"},
        "chunk_index": {"type": "integer"},
        "chunk_total": {"type": "integer"},
        "tokens": {"type": "integer"},
        "text": {
            "type": "text",
            "analyzer": "ik_max_word",
            "search_analyzer": "ik_smart",
        },
        VEC_FIELD: {
            "type": "dense_vector",
            "dims": VEC_DIMS,
            "index": True,
            "similarity": SIMILARITY,
            "index_options": dict(INDEX_OPTIONS),
        },
    }
    return {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {"properties": props},
    }


def collect_secret_values() -> list[str]:
    """仅内存收集密钥值，供泄露自检；绝不打印。"""
    keys = (
        "OPENROUTER_API_KEY",
        "ES_PASSWORD",
        "ES_REMOTE_PASSWORD",
        "ES_USERNAME",
        "ES_REMOTE_USERNAME",
        "NEO4J_PASSWORD",
        "NEO4J_V4_PASSWORD",
    )
    out = []
    for k in keys:
        v = (os.environ.get(k) or "").strip()
        if len(v) >= 4:
            out.append(v)
    return out


def leak_check(text: str, secrets: list[str] | None = None) -> list[str]:
    """内存内比对：报告/日志文本是否含密钥值。返回命中的变量名提示（不含值）。"""
    secrets = secrets if secrets is not None else collect_secret_values()
    hits = []
    for i, s in enumerate(secrets):
        if s and s in (text or ""):
            hits.append(f"secret#{i}")
    return hits


def redact(text: str, secrets: list[str] | None = None) -> str:
    out = text or ""
    secrets = secrets if secrets is not None else collect_secret_values()
    for s in secrets:
        if len(s) >= 4:
            out = out.replace(s, "***")
    return out
