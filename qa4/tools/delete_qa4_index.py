# -*- coding: utf-8 -*-
"""安全删除 qa4-es 上白名单内的 qa4_* 索引。

约束:
  - 索引名必须以 qa4_ 开头
  - 必须在 ALLOWED_DELETE_INDICES 白名单内（当前仅 qa4_pano_catalog）
  - 必须确认 cluster_name == qa4
  - 先打印文档数；必须带 --yes 才真正删除
  - 不依赖 qa4 其他模块；密码只从环境变量读取

环境变量:
  QA4_ES_URL        必填，例 http://127.0.0.1:9202
  QA4_ES_USER       默认 elastic
  QA4_ES_PASSWORD   ES 开认证时必填
  QA4_ES_VERIFY / QA4_ENV_FILE

用法:
  python delete_qa4_index.py qa4_pano_catalog          # 只核对，不删
  python delete_qa4_index.py qa4_pano_catalog --yes    # 确认后删除
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

ALLOWED_DELETE_INDICES = frozenset({"qa4_pano_catalog"})
EXPECTED_COUNTS = {"qa4_pano_catalog": 53151}
REQUIRED_CLUSTER = "qa4"


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit("QA4_ENV_FILE not found: %s" % path)
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if not k or k in os.environ:
            continue
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ[k] = v


def _es_auth_hint() -> str:
    return (
        "请 export QA4_ES_PASSWORD=... ；"
        "用户名 QA4_ES_USER（默认 elastic）。"
        "例: export QA4_ES_USER=elastic"
    )


def _es_client():
    url = (os.environ.get("QA4_ES_URL") or "").strip().rstrip("/")
    if not url:
        raise SystemExit("缺少 QA4_ES_URL，例: export QA4_ES_URL=http://127.0.0.1:9202")
    user = (os.environ.get("QA4_ES_USER") or "elastic").strip()
    password = os.environ.get("QA4_ES_PASSWORD") or ""
    verify_raw = (os.environ.get("QA4_ES_VERIFY") or "1").strip().lower()
    verify = verify_raw not in {"0", "false", "no"}
    from elasticsearch import Elasticsearch
    from elasticsearch.exceptions import AuthenticationException, AuthorizationException

    kwargs: Dict[str, Any] = {"hosts": [url], "verify_certs": verify}
    if password:
        kwargs["basic_auth"] = (user, password)
    password = ""
    es = Elasticsearch(**kwargs)
    try:
        es.info()
    except (AuthenticationException, AuthorizationException) as e:
        raise SystemExit("ES 认证失败（401/403）：%s" % _es_auth_hint()) from e
    except Exception as e:
        msg = str(e)
        if "401" in msg or "Unauthorized" in msg or "security_exception" in msg.lower():
            raise SystemExit("ES 认证失败：%s" % _es_auth_hint()) from e
        raise
    return es, url


def _qa4_doc_counts(es) -> Dict[str, int]:
    out: Dict[str, int] = {}
    try:
        names = sorted(
            n for n in es.indices.get_alias(index="qa4_*").keys() if n.startswith("qa4_")
        )
    except Exception:
        cat = es.cat.indices(index="qa4_*", format="json")
        names = sorted(r["index"] for r in cat if str(r.get("index", "")).startswith("qa4_"))
    for name in names:
        out[name] = int(es.count(index=name)["count"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Delete whitelisted qa4_* index on qa4-es only")
    ap.add_argument("index", help="index name, e.g. qa4_pano_catalog")
    ap.add_argument("--yes", action="store_true", help="actually delete (required)")
    ap.add_argument(
        "--expect-remaining-total",
        type=int,
        default=360931,
        help="after delete, sum of remaining qa4_* docs (default 360931)",
    )
    args = ap.parse_args()

    env_file = (os.environ.get("QA4_ENV_FILE") or "").strip()
    if env_file:
        _load_env_file(Path(env_file))

    index = str(args.index).strip()
    if not index.startswith("qa4_"):
        print("REFUSE: index must start with qa4_", file=sys.stderr)
        return 2
    if index not in ALLOWED_DELETE_INDICES:
        print(
            "REFUSE: index not in whitelist %s" % sorted(ALLOWED_DELETE_INDICES),
            file=sys.stderr,
        )
        return 2

    es, url = _es_client()
    info = es.info()
    cluster = info.get("cluster_name")
    print("ES_URL_HOST=%s" % url.split("://", 1)[-1])
    print("cluster_name=%s" % cluster)
    if cluster != REQUIRED_CLUSTER:
        print(
            "REFUSE: cluster_name must be %r, got %r (wrong ES?)" % (REQUIRED_CLUSTER, cluster),
            file=sys.stderr,
        )
        return 2

    before = _qa4_doc_counts(es)
    print("qa4_indices_before=%s" % json.dumps(before, ensure_ascii=False, sort_keys=True))
    print("qa4_total_before=%d" % sum(before.values()))
    if index not in before:
        print("REFUSE: index %s does not exist" % index, file=sys.stderr)
        return 2
    count = before[index]
    expect = EXPECTED_COUNTS.get(index)
    print("target_index=%s doc_count=%d expect=%s" % (index, count, expect))
    if expect is not None and count != expect:
        print(
            "REFUSE: doc_count %d != expect %d" % (count, expect),
            file=sys.stderr,
        )
        return 2

    if not args.yes:
        print("DRY_RUN: pass --yes to delete. No changes made.")
        return 0

    print("DELETING %s ..." % index)
    es.indices.delete(index=index)
    exists = es.indices.exists(index=index)
    after = _qa4_doc_counts(es)
    total_after = sum(after.values())
    print("exists_after=%s" % bool(exists))
    print("qa4_indices_after=%s" % json.dumps(after, ensure_ascii=False, sort_keys=True))
    print("qa4_total_after=%d expect_remaining=%d" % (total_after, args.expect_remaining_total))
    if exists:
        print("FAIL: index still exists", file=sys.stderr)
        return 1
    if index in after:
        print("FAIL: index still listed", file=sys.stderr)
        return 1
    if total_after != args.expect_remaining_total:
        print(
            "FAIL: remaining total %d != %d" % (total_after, args.expect_remaining_total),
            file=sys.stderr,
        )
        return 1
    # other nine unchanged
    for name, c in before.items():
        if name == index:
            continue
        if after.get(name) != c:
            print(
                "FAIL: %s changed %s -> %s" % (name, c, after.get(name)),
                file=sys.stderr,
            )
            return 1
    print("OK: deleted %s; remaining total %d" % (index, total_after))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
