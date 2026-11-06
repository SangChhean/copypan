# -*- coding: utf-8 -*-
"""阶段 4：把本机已向量化的 panai4_hymns 推到服务器（不重新 embedding）。

用法（在 back_mic/backend 下）::

    python -m panai4.hymns.push_remote
    python -m panai4.hymns.push_remote --preflight-only
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, scan

from . import config
from .index_to_es import (
    load_jsonl,
    make_local,
    other_counts,
    scroll_ids,
)


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


def env_status() -> dict[str, str]:
    _load_env()
    return {k: ("存在" if (os.getenv(k) or "").strip() else "缺失") for k in config.REMOTE_ENV_KEYS}


def ik_ok(es: Elasticsearch) -> dict:
    try:
        # analyze API
        r = es.indices.analyze(body={"analyzer": "ik_max_word", "text": "测试分析器"})
        tokens = [t.get("token") for t in r.get("tokens") or []]
        return {"ok": bool(tokens), "tokens": tokens[:5], "version": es.info().get("version", {}).get("number")}
    except Exception as exc:
        return {"ok": False, "error": config.redact(str(exc))}


def create_remote_index(es: Elasticsearch) -> None:
    body = deepcopy(config.mapping_body())
    es.indices.create(index=config.INDEX_NAME, body=body)


def bulk_index(es: Elasticsearch, rows: list[dict]) -> dict:
    success = 0
    errors = []
    batch = []
    for row in rows:
        batch.append(
            {
                "_op_type": "index",
                "_index": config.INDEX_NAME,
                "_id": row["chunk_id"],
                "_source": row,
            }
        )
        if len(batch) >= config.BULK_SIZE_REMOTE:
            ok, errs = bulk(es, batch, raise_on_error=False, request_timeout=180)
            success += ok
            if errs:
                errors.extend(errs[:20])
            batch = []
            print("REMOTE_BULK", success, flush=True)
    if batch:
        ok, errs = bulk(es, batch, raise_on_error=False, request_timeout=180)
        success += ok
        if errs:
            errors.extend(errs[:20])
    es.indices.refresh(index=config.INDEX_NAME)
    return {"success": success, "errors": errors}


def verify_remote(remote: Elasticsearch, local: Elasticsearch, rows: list[dict]) -> dict:
    report: dict[str, Any] = {"ok": True, "checks": {}}
    count = int(remote.count(index=config.INDEX_NAME)["count"])
    report["checks"]["count"] = {"got": count, "expect": config.EXPECT_TOTAL, "ok": count == config.EXPECT_TOTAL}
    if count != config.EXPECT_TOTAL:
        report["ok"] = False

    local_ids = scroll_ids(local, config.INDEX_NAME)
    remote_ids = scroll_ids(remote, config.INDEX_NAME)
    miss = sorted(local_ids - remote_ids)
    extra = sorted(remote_ids - local_ids)
    report["checks"]["id_vs_local"] = {"miss": len(miss), "extra": len(extra), "ok": not miss and not extra}
    if miss or extra:
        report["ok"] = False

    rng = random.Random(config.SAMPLE_SEED)
    sample = rng.sample(rows, min(20, len(rows)))
    mismatches = []
    for rec in sample:
        loc = local.get(index=config.INDEX_NAME, id=rec["chunk_id"])["_source"]
        rem = remote.get(index=config.INDEX_NAME, id=rec["chunk_id"])["_source"]
        if loc.get("text") != rem.get("text"):
            mismatches.append({"chunk_id": rec["chunk_id"], "field": "text"})
        lv = loc.get("embedding") or []
        rv = rem.get("embedding") or []
        if len(lv) != len(rv) or any(abs(float(a) - float(b)) > 1e-5 for a, b in zip(lv, rv)):
            mismatches.append({"chunk_id": rec["chunk_id"], "field": "embedding"})
    report["checks"]["sample20"] = {"mismatches": mismatches[:10], "ok": not mismatches}
    if mismatches:
        report["ok"] = False

    knn_fail = []
    for rec in rng.sample(rows, min(10, len(rows))):
        resp = remote.search(
            index=config.INDEX_NAME,
            size=10,
            knn={
                "field": "embedding",
                "query_vector": rec["embedding"],
                "k": 10,
                "num_candidates": 200,
            },
        )
        hits = resp["hits"]["hits"]
        top_score = hits[0]["_score"]
        tied_ids = [h["_id"] for h in hits if abs(float(h["_score"]) - float(top_score)) < 1e-9]
        if rec["chunk_id"] not in tied_ids:
            knn_fail.append({"expect": rec["chunk_id"], "got": tied_ids[:5]})
    report["checks"]["knn_self"] = {"fail": knn_fail, "ok": not knn_fail}
    if knn_fail:
        report["ok"] = False

    target = next((r for r in rows if r["message_key"] == "诗歌|1" and r["chunk_index"] == 2), None)
    bm25_ok = False
    if target:
        body = target["text"].split("\n", 1)[-1]
        phrase = body.split("　", 1)[-1][:20]
        resp = remote.search(index=config.INDEX_NAME, size=5, query={"match": {"text": phrase}})
        hits = [h["_id"] for h in resp["hits"]["hits"]]
        bm25_ok = target["chunk_id"] in hits
        report["checks"]["bm25"] = {"ok": bm25_ok, "phrase": phrase, "hits": hits, "target": target["chunk_id"]}
    else:
        report["checks"]["bm25"] = {"ok": False, "error": "target missing"}
    if not bm25_ok:
        report["ok"] = False

    cat = remote.search(index=config.INDEX_NAME, size=1, query={"term": {"category": "赞美主"}})
    cat_n = cat["hits"]["total"]["value"] if isinstance(cat["hits"]["total"], dict) else cat["hits"]["total"]
    report["checks"]["category_filter"] = {"ok": cat_n > 0, "n": cat_n}
    if cat_n <= 0:
        report["ok"] = False

    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    _load_env()
    secrets = config.collect_secret_values()
    summary: dict[str, Any] = {"stage4": {}, "ok": False}

    st = env_status()
    summary["stage4"]["env"] = st
    if any(st[k] != "存在" for k in config.REMOTE_ENV_KEYS):
        print("FAIL remote env", st)
        return 2

    if not config.VEC_JSON.is_file():
        print("FAIL vec file missing", config.VEC_JSON)
        return 2
    rows = load_jsonl(config.VEC_JSON)
    if len(rows) != config.EXPECT_TOTAL:
        print("FAIL vec n", len(rows))
        return 2

    remote = make_remote()
    local = make_local()

    if remote.indices.exists(index=config.INDEX_NAME):
        print("FAIL remote already has", config.INDEX_NAME)
        return 2

    before_counts = other_counts(remote)
    summary["stage4"]["remote_other_before"] = before_counts
    print("REMOTE_OTHER_BEFORE", before_counts)

    ik = ik_ok(remote)
    local_ik = ik_ok(local)
    summary["stage4"]["ik"] = {"remote": ik, "local": local_ik}
    print("IK", json.dumps({"remote": ik, "local": {k: v for k, v in local_ik.items() if k != "tokens"}}, ensure_ascii=False))
    if not ik.get("ok"):
        print("FAIL remote IK")
        return 2

    if args.preflight_only:
        print("PREFLIGHT_OK")
        Path(r"C:\Users\28121\AppData\Local\Temp\hymns_push_preflight.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 0

    print("CREATE_REMOTE", config.INDEX_NAME, flush=True)
    create_remote_index(remote)

    print("REMOTE_BULK_START", flush=True)
    t0 = time.perf_counter()
    bulk_res = bulk_index(remote, rows)
    summary["stage4"]["bulk"] = {
        "success": bulk_res["success"],
        "error_n": len(bulk_res["errors"]),
        "seconds": round(time.perf_counter() - t0, 2),
    }
    print("REMOTE_BULK_DONE", bulk_res["success"], "errors", len(bulk_res["errors"]))
    if bulk_res["success"] != config.EXPECT_TOTAL or bulk_res["errors"]:
        print("FAIL remote bulk")
        return 2

    v = verify_remote(remote, local, rows)
    after_counts = other_counts(remote)
    others_ok = after_counts == before_counts
    v["checks"]["other_indices_unchanged"] = {
        "ok": others_ok,
        "before": before_counts,
        "after": after_counts,
    }
    if not others_ok:
        v["ok"] = False
    summary["stage4"]["verify"] = v

    dumped = json.dumps(summary, ensure_ascii=False)
    hits = config.leak_check(dumped, secrets)
    summary["leak_check"] = {"ok": not hits, "hits": hits}
    if hits:
        print("FAIL leak")
        return 2

    if not v.get("ok"):
        Path(r"C:\Users\28121\AppData\Local\Temp\hymns_push_report.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (config.DATA_ROOT / "stage4_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("FAIL remote verify")
        return 2
    summary["ok"] = True
    Path(r"C:\Users\28121\AppData\Local\Temp\hymns_push_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (config.DATA_ROOT / "stage4_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("STAGE4_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
