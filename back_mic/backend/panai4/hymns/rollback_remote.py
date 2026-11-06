# -*- coding: utf-8 -*-
"""回滚：仅允许删除服务器上的 panai4_hymns。写好默认不运行。

用法（必须显式确认）::

    python -m panai4.hymns.rollback_remote --confirm DELETE_panai4_hymns
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

from . import config

CONFIRM = "DELETE_panai4_hymns"


def _load_env() -> None:
    load_dotenv(config.backend_env())


def make_remote() -> Elasticsearch:
    _load_env()
    host = (os.getenv("ES_REMOTE_HOST") or "").strip()
    port = (os.getenv("ES_REMOTE_PORT") or "").strip()
    user = (os.getenv("ES_REMOTE_USERNAME") or "").strip()
    password = (os.getenv("ES_REMOTE_PASSWORD") or "").strip()
    missing = [k for k, v in zip(config.REMOTE_ENV_KEYS, (host, port, user, password)) if not v]
    if missing:
        raise SystemExit(f"缺少远程 ES 环境变量：{'、'.join(missing)}")
    return Elasticsearch(
        hosts=[f"http://{host}:{port}"],
        basic_auth=(user, password),
        request_timeout=180,
        max_retries=2,
        retry_on_timeout=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"必须等于 {CONFIRM}",
    )
    args = parser.parse_args()
    if args.confirm != CONFIRM:
        print("REFUSED: confirm token mismatch; nothing deleted")
        return 2

    # 硬编码只允许这一个名字
    name = "panai4_hymns"
    if name != config.INDEX_NAME or name != "panai4_hymns":
        print("REFUSED: hard-coded name check failed")
        return 2

    es = make_remote()
    if not es.indices.exists(index=name):
        print("NOOP: remote index does not exist", name)
        return 0
    es.indices.delete(index=name)
    print("DELETED", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
