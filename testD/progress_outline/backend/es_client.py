# -*- coding: utf-8 -*-
"""Elasticsearch 客户端（独立配置，不引用主站 es_config）。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")
_back_mic_env = Path(__file__).resolve().parents[3] / "back_mic" / "backend" / ".env"
if _back_mic_env.is_file():
    load_dotenv(_back_mic_env, override=False)

ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
ES_REQUEST_TIMEOUT = int(os.getenv("ES_REQUEST_TIMEOUT", "60"))

es = Elasticsearch(
    hosts=[f"http://{ES_HOST}:{ES_PORT}"],
    basic_auth=(ES_USERNAME, ES_PASSWORD) if ES_PASSWORD else None,
    request_timeout=ES_REQUEST_TIMEOUT,
)

PANO_INDEX = "progress_pano"
