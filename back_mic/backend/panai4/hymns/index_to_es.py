# -*- coding: utf-8 -*-
"""阶段 2–3：本机建 panai4_hymns、向量化、bulk 写入、验证。

用法（在 back_mic/backend 下）::

    python -m panai4.hymns.index_to_es
    python -m panai4.hymns.index_to_es --verify-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import sys
import time
import traceback
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, scan

from . import config

RETRY_WAITS = config.RETRY_WAITS


def _load_env() -> None:
    load_dotenv(config.backend_env())


def make_local() -> Elasticsearch:
    _load_env()
    return Elasticsearch(
        hosts=[f"http://{os.getenv('ES_HOST', 'localhost')}:{os.getenv('ES_PORT', '9200')}"],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=120,
    )


def env_status(keys: tuple[str, ...]) -> dict[str, str]:
    _load_env()
    return {k: ("存在" if (os.getenv(k) or "").strip() else "缺失") for k in keys}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def estimate_cost(rows: list[dict]) -> dict:
    chars = sum(len(r.get("text") or "") for r in rows)
    est = int(chars / 1.5)
    adj = int(est * config.TOKEN_INFLATE)
    usd_raw = est / 1_000_000 * config.PRICE_PER_MILLION
    usd_adj = adj / 1_000_000 * config.PRICE_PER_MILLION
    return {
        "chunks": len(rows),
        "chars": chars,
        "est_tokens": est,
        "adj_tokens": adj,
        "usd_raw": round(usd_raw, 6),
        "usd_adj": round(usd_adj, 6),
        "price_per_mtok": config.PRICE_PER_MILLION,
        "inflate": config.TOKEN_INFLATE,
    }


def _is_retryable(exc: Exception) -> tuple[bool, str]:
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
    except ImportError:
        APIConnectionError = APIStatusError = APITimeoutError = RateLimitError = ()  # type: ignore
    if RateLimitError and isinstance(exc, RateLimitError):
        return True, "429"
    if APITimeoutError and isinstance(exc, APITimeoutError):
        return True, "timeout"
    if APIConnectionError and isinstance(exc, APIConnectionError):
        return True, "network"
    if APIStatusError and isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None) or 0
        if status == 429:
            return True, "429"
        if status >= 500:
            return True, "5xx"
        return False, f"http_{status}"
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return True, "timeout"
    if "connection" in text or "network" in text:
        return True, "network"
    return False, type(exc).__name__


def _vec_ok(vec: Any, dims: int) -> tuple[bool, str]:
    if not isinstance(vec, list):
        return False, "not_list"
    if len(vec) != dims:
        return False, f"dims={len(vec)}"
    if any(not isinstance(x, (int, float)) for x in vec):
        return False, "non_numeric"
    if any(math.isnan(float(x)) or math.isinf(float(x)) for x in vec):
        return False, "nan_or_inf"
    if all(float(x) == 0.0 for x in vec):
        return False, "all_zero"
    return True, "ok"


async def _embed_batch(texts: list[str], secrets: list[str]) -> dict:
    from kg_rag.embedding_adapter import get_embeddings

    started = time.perf_counter()
    try:
        vectors = await get_embeddings(texts, profile="kg_rag")
        return {
            "ok": True,
            "vectors": vectors,
            "seconds": time.perf_counter() - started,
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "vectors": [],
            "seconds": time.perf_counter() - started,
            "error": config.redact(str(exc), secrets),
            "traceback": config.redact(traceback.format_exc(), secrets),
            "retryable": _is_retryable(exc)[0],
            "kind": _is_retryable(exc)[1],
        }


async def _embed_with_retry(texts: list[str], secrets: list[str], retry_counts: Counter) -> dict:
    last = None
    for attempt in range(len(RETRY_WAITS) + 1):
        result = await _embed_batch(texts, secrets)
        if result["ok"]:
            result["attempts"] = attempt + 1
            return result
        last = result
        if not result.get("retryable") or attempt >= len(RETRY_WAITS):
            result["attempts"] = attempt + 1
            return result
        kind = result.get("kind") or "retry"
        retry_counts[kind] += 1
        wait = RETRY_WAITS[attempt]
        print("RETRY", kind, "wait", wait, "attempt", attempt + 1, flush=True)
        await asyncio.sleep(wait)
    last["attempts"] = len(RETRY_WAITS) + 1
    return last


async def embed_all(rows: list[dict], secrets: list[str]) -> tuple[list[dict], dict]:
    from kg_rag.embedding_adapter import EMBEDDING_KG_DIMS, EMBEDDING_KG_MODEL

    expect_dim = int(EMBEDDING_KG_DIMS)
    retry_counts: Counter = Counter()
    failures = []
    out_rows: list[dict | None] = [None] * len(rows)
    batches = [(i, rows[i : i + config.BATCH_SIZE]) for i in range(0, len(rows), config.BATCH_SIZE)]
    sem = asyncio.Semaphore(config.CONCURRENCY)
    done = 0
    started = time.perf_counter()
    lock = asyncio.Lock()

    async def one(offset: int, chunk: list[dict]) -> None:
        nonlocal done
        texts = [r.get("text") or "" for r in chunk]
        async with sem:
            result = await _embed_with_retry(texts, secrets, retry_counts)
            if config.BATCH_PAUSE:
                await asyncio.sleep(config.BATCH_PAUSE)
        async with lock:
            if not result["ok"]:
                for r in chunk:
                    failures.append({"chunk_id": r["chunk_id"], "error": result.get("error")})
                print("BATCH_FAIL", "n", len(chunk), "kind", result.get("kind"), flush=True)
                return
            for j, (rec, vec) in enumerate(zip(chunk, result["vectors"])):
                ok, reason = _vec_ok(vec, expect_dim)
                if not ok:
                    failures.append({"chunk_id": rec["chunk_id"], "error": reason})
                    continue
                row = dict(rec)
                row["embedding"] = vec
                out_rows[offset + j] = row
            done += len(chunk)
            elapsed = time.perf_counter() - started
            rate = done / elapsed if elapsed else 0
            print(
                "EMBED_PROGRESS",
                "done", done,
                "total", len(rows),
                "pct", f"{100 * done / len(rows):.1f}%",
                "rate", f"{rate:.2f}/s",
                flush=True,
            )

    await asyncio.gather(*[one(off, ch) for off, ch in batches])
    if failures:
        return [], {
            "ok": False,
            "failures": failures[:50],
            "failure_n": len(failures),
            "retry_counts": dict(retry_counts),
            "model": EMBEDDING_KG_MODEL,
            "dims": expect_dim,
        }
    if any(r is None for r in out_rows):
        return [], {"ok": False, "error": "missing_rows", "retry_counts": dict(retry_counts)}
    wall = time.perf_counter() - started
    return out_rows, {  # type: ignore[return-value]
        "ok": True,
        "n": len(out_rows),
        "wall_seconds": wall,
        "retry_counts": dict(retry_counts),
        "model": EMBEDDING_KG_MODEL,
        "dims": expect_dim,
    }


def create_index(es: Elasticsearch) -> None:
    body = deepcopy(config.mapping_body())
    es.indices.create(index=config.INDEX_NAME, body=body)


def bulk_index(es: Elasticsearch, rows: list[dict], bulk_size: int = config.BULK_SIZE_LOCAL) -> dict:
    def gen():
        for row in rows:
            src = {k: v for k, v in row.items()}
            yield {
                "_op_type": "index",
                "_index": config.INDEX_NAME,
                "_id": row["chunk_id"],
                "_source": src,
            }

    success = 0
    errors = []
    batch = []
    for action in gen():
        batch.append(action)
        if len(batch) >= bulk_size:
            ok, errs = bulk(es, batch, raise_on_error=False, request_timeout=180)
            success += ok
            if errs:
                errors.extend(errs[:20])
            batch = []
            print("BULK", success, flush=True)
    if batch:
        ok, errs = bulk(es, batch, raise_on_error=False, request_timeout=180)
        success += ok
        if errs:
            errors.extend(errs[:20])
    es.indices.refresh(index=config.INDEX_NAME)
    return {"success": success, "errors": errors}


def scroll_ids(es: Elasticsearch, index: str) -> set[str]:
    ids = set()
    for hit in scan(es, index=index, query={"query": {"match_all": {}}}, _source=False, size=1000):
        ids.add(hit["_id"])
    return ids


def other_counts(es: Elasticsearch) -> dict[str, int]:
    out = {}
    for name in config.OTHER_PANAI4_EXPECT:
        if es.indices.exists(index=name):
            out[name] = int(es.count(index=name)["count"])
        else:
            out[name] = -1
    return out


def verify_local(es: Elasticsearch, rows: list[dict]) -> dict:
    report: dict[str, Any] = {"ok": True, "checks": {}}
    count = int(es.count(index=config.INDEX_NAME)["count"])
    report["checks"]["count"] = {"got": count, "expect": config.EXPECT_TOTAL, "ok": count == config.EXPECT_TOTAL}
    if count != config.EXPECT_TOTAL:
        report["ok"] = False

    file_ids = {r["chunk_id"] for r in rows}
    es_ids = scroll_ids(es, config.INDEX_NAME)
    miss = sorted(file_ids - es_ids)
    extra = sorted(es_ids - file_ids)
    report["checks"]["id_set"] = {"miss": len(miss), "extra": len(extra), "ok": not miss and not extra}
    if miss or extra:
        report["ok"] = False
        report["checks"]["id_set"]["miss_sample"] = miss[:10]
        report["checks"]["id_set"]["extra_sample"] = extra[:10]

    # series / unit_type counts from file vs ES scroll
    file_ut = Counter((r["series"], r["unit_type"]) for r in rows)
    es_ut: Counter = Counter()
    for hit in scan(
        es,
        index=config.INDEX_NAME,
        query={"query": {"match_all": {}}},
        _source=["series", "unit_type"],
        size=1000,
    ):
        s = hit["_source"]
        es_ut[(s.get("series"), s.get("unit_type"))] += 1

    report["checks"]["series_unit_type"] = {
        "file": {f"{a}|{b}": n for (a, b), n in sorted(file_ut.items())},
        "es": {f"{a}|{b}": n for (a, b), n in sorted(es_ut.items())},
        "ok": dict(file_ut) == dict(es_ut),
    }
    if dict(file_ut) != dict(es_ut):
        report["ok"] = False

    rng = random.Random(config.SAMPLE_SEED)
    sample = rng.sample(rows, min(20, len(rows)))
    field_mismatches = []
    vec_mismatches = []
    compare_fields = [
        "chunk_id", "message_key", "series", "hymn_number", "name", "title",
        "category", "subtitle", "reference", "unit_type", "unit_label",
        "chunk_index", "chunk_total", "tokens", "text",
    ]
    for rec in sample:
        doc = es.get(index=config.INDEX_NAME, id=rec["chunk_id"])["_source"]
        for f in compare_fields:
            if doc.get(f) != rec.get(f):
                field_mismatches.append({"chunk_id": rec["chunk_id"], "field": f})
        dv = doc.get("embedding") or []
        fv = rec.get("embedding") or []
        if len(dv) != len(fv) or any(abs(float(a) - float(b)) > 1e-5 for a, b in zip(dv, fv)):
            vec_mismatches.append(rec["chunk_id"])
    report["checks"]["sample20"] = {
        "field_mismatches": field_mismatches[:10],
        "vec_mismatches": vec_mismatches[:10],
        "ok": not field_mismatches and not vec_mismatches,
    }
    if field_mismatches or vec_mismatches:
        report["ok"] = False

    # knn 自检：top1 应为自己；若存在完全相同向量（重复副歌/单节=整首），
    # 则并列最高分的命中集合中必须包含自己。
    by_id = {r["chunk_id"]: r for r in rows}
    knn_sample = rng.sample(rows, min(10, len(rows)))
    knn_fail = []
    knn_ties = []
    for rec in knn_sample:
        vec = rec["embedding"]
        try:
            resp = es.search(
                index=config.INDEX_NAME,
                size=10,
                knn={
                    "field": "embedding",
                    "query_vector": vec,
                    "k": 10,
                    "num_candidates": 200,
                },
            )
            hits = resp["hits"]["hits"]
            if not hits:
                knn_fail.append({"expect": rec["chunk_id"], "error": "no_hits"})
                continue
            top_score = hits[0]["_score"]
            tied = [h for h in hits if abs(float(h["_score"]) - float(top_score)) < 1e-9]
            tied_ids = [h["_id"] for h in tied]
            if rec["chunk_id"] in tied_ids:
                if tied_ids[0] != rec["chunk_id"]:
                    knn_ties.append(
                        {
                            "chunk_id": rec["chunk_id"],
                            "tied_with": [i for i in tied_ids if i != rec["chunk_id"]],
                            "reason": "identical_or_near_vector",
                        }
                    )
                continue
            # 仍失败时核对 top1 是否真同向量
            top_id = tied_ids[0]
            top_rec = by_id.get(top_id)
            if top_rec and top_rec.get("embedding") == vec:
                knn_ties.append(
                    {
                        "chunk_id": rec["chunk_id"],
                        "tied_with": [top_id],
                        "reason": "identical_embedding_not_in_tied_window",
                    }
                )
                continue
            knn_fail.append({"expect": rec["chunk_id"], "got": tied_ids[:5]})
        except Exception as exc:
            knn_fail.append({"expect": rec["chunk_id"], "error": config.redact(str(exc))})
    report["checks"]["knn_self"] = {
        "fail": knn_fail,
        "ties_ok": knn_ties,
        "ok": not knn_fail,
    }
    if knn_fail:
        report["ok"] = False

    # BM25: take a stanza from 诗歌|1 unit c2 (二)
    bm25_ok = False
    bm25_detail = {}
    target = next((r for r in rows if r["message_key"] == "诗歌|1" and r["chunk_index"] == 2), None)
    if target:
        # pick a distinctive phrase from unit body
        body = target["text"].split("\n", 1)[-1]
        # strip marker
        phrase = body.split("　", 1)[-1][:20]
        resp = es.search(
            index=config.INDEX_NAME,
            size=5,
            query={"match": {"text": phrase}},
        )
        hits = [h["_id"] for h in resp["hits"]["hits"]]
        bm25_ok = target["chunk_id"] in hits
        bm25_detail = {"phrase": phrase, "hits": hits, "target": target["chunk_id"]}
    report["checks"]["bm25"] = {"ok": bm25_ok, **bm25_detail}
    if not bm25_ok:
        report["ok"] = False

    # knn theme 颂赞三一神 → 诗歌|1 full
    theme_ok = False
    theme_detail = {}
    full1 = next((r for r in rows if r["message_key"] == "诗歌|1" and r["unit_type"] == "full"), None)
    if full1:
        # embed query via existing vector of a related chunk is cheating;
        # use knn with full1's own vector would always hit — instead BM25+filter or
        # use script_score with a query embedding. Simpler smoke: match query on text
        # plus filter series, check full block appears; AND knn using full1 vector
        # is tautology. Spec: 用主题词做 knn → need to embed the query.
        # We'll embed "颂赞三一神" once.
        theme_detail["note"] = "theme_knn_deferred_to_async"
    report["checks"]["theme_knn"] = {"ok": theme_ok, **theme_detail}

    # category filter
    cat_resp = es.search(
        index=config.INDEX_NAME,
        size=3,
        query={"term": {"category": "赞美主"}},
    )
    cat_n = cat_resp["hits"]["total"]["value"] if isinstance(cat_resp["hits"]["total"], dict) else cat_resp["hits"]["total"]
    report["checks"]["category_filter"] = {"ok": cat_n > 0, "n": cat_n}
    if cat_n <= 0:
        report["ok"] = False

    others = other_counts(es)
    others_ok = all(others.get(k) == v for k, v in config.OTHER_PANAI4_EXPECT.items())
    report["checks"]["other_indices"] = {"counts": others, "ok": others_ok}
    if not others_ok:
        report["ok"] = False

    return report


async def theme_knn_check(es: Elasticsearch, rows: list[dict], secrets: list[str]) -> dict:
    full1 = next(r for r in rows if r["message_key"] == "诗歌|1" and r["unit_type"] == "full")
    result = await _embed_with_retry(["颂赞三一神"], secrets, Counter())
    if not result["ok"]:
        return {"ok": False, "error": result.get("error")}
    vec = result["vectors"][0]
    resp = es.search(
        index=config.INDEX_NAME,
        size=20,
        knn={
            "field": "embedding",
            "query_vector": vec,
            "k": 20,
            "num_candidates": 100,
        },
    )
    ids = [h["_id"] for h in resp["hits"]["hits"]]
    rank = ids.index(full1["chunk_id"]) + 1 if full1["chunk_id"] in ids else None
    return {
        "ok": full1["chunk_id"] in ids,
        "target": full1["chunk_id"],
        "rank": rank,
        "hits": ids[:20],
    }


def compare_blueprint_mapping(es: Elasticsearch) -> dict:
    name = "panai4_outline_12490"
    if not es.indices.exists(index=name):
        return {"ok": False, "error": f"{name} missing"}
    m = es.indices.get_mapping(index=name)[name]["mappings"]["properties"]
    s = es.indices.get_settings(index=name)[name]["settings"]
    emb = m.get("embedding") or {}
    text = m.get("text") or {}
    return {
        "ok": True,
        "outline_embedding": {
            "dims": emb.get("dims"),
            "similarity": emb.get("similarity"),
            "index_options": emb.get("index_options"),
        },
        "outline_text": {
            "analyzer": text.get("analyzer"),
            "search_analyzer": text.get("search_analyzer"),
        },
        "outline_shards": s.get("index", {}).get("number_of_shards"),
        "our_match": {
            "dims": emb.get("dims") == config.VEC_DIMS,
            "similarity": emb.get("similarity") == config.SIMILARITY,
            "analyzer": text.get("analyzer") == "ik_max_word",
            "search_analyzer": text.get("search_analyzer") == "ik_smart",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    _load_env()
    secrets = config.collect_secret_values()
    # also include openrouter key explicitly after load
    if (os.getenv("OPENROUTER_API_KEY") or "").strip():
        secrets = config.collect_secret_values()

    summary: dict[str, Any] = {"stage2": {}, "stage3": {}, "ok": False}

    if not config.CLEAN_JSON.is_file():
        print("FAIL clean json missing", config.CLEAN_JSON)
        return 2
    rows = load_jsonl(config.CLEAN_JSON)
    if len(rows) != config.EXPECT_TOTAL:
        print("FAIL clean n", len(rows))
        return 2

    cost = estimate_cost(rows)
    summary["stage2"]["cost_estimate"] = cost
    print("COST", cost)
    if cost["usd_adj"] > config.COST_GATE_USD:
        print("FAIL cost gate", cost["usd_adj"])
        return 2

    es = make_local()
    if not args.verify_only:
        if es.indices.exists(index=config.INDEX_NAME):
            print("FAIL local index already exists", config.INDEX_NAME)
            return 2

        bp = compare_blueprint_mapping(es)
        summary["stage2"]["blueprint"] = bp
        print("BLUEPRINT", json.dumps(bp, ensure_ascii=False))
        if not bp.get("ok") or not all(bp.get("our_match", {}).values()):
            print("FAIL blueprint mapping mismatch")
            return 2

        # env for embed
        st = env_status(config.EMBED_ENV_KEYS)
        summary["stage2"]["embed_env"] = st
        if any(st[k] != "存在" for k in config.EMBED_ENV_KEYS):
            print("FAIL embed env", st)
            return 2

        print("CREATE_INDEX", config.INDEX_NAME, flush=True)
        create_index(es)

        print("EMBED_START", len(rows), flush=True)
        vec_rows, embed_meta = asyncio.run(embed_all(rows, secrets))
        summary["stage2"]["embed"] = {k: v for k, v in embed_meta.items() if k != "failures"}
        if not embed_meta.get("ok"):
            summary["stage2"]["embed_failures"] = embed_meta.get("failures")
            print("FAIL embed", embed_meta.get("failure_n") or embed_meta.get("error"))
            # leave index empty-ish; do not push
            return 2

        write_jsonl(config.VEC_JSON, vec_rows)
        print("WROTE_VEC", config.VEC_JSON, flush=True)

        bulk_res = bulk_index(es, vec_rows)
        summary["stage2"]["bulk"] = {
            "success": bulk_res["success"],
            "error_n": len(bulk_res["errors"]),
        }
        print("BULK_DONE", bulk_res["success"], "errors", len(bulk_res["errors"]))
        if bulk_res["success"] != config.EXPECT_TOTAL or bulk_res["errors"]:
            print("FAIL bulk")
            return 2
        rows = vec_rows
    else:
        if not config.VEC_JSON.is_file():
            print("FAIL vec missing")
            return 2
        rows = load_jsonl(config.VEC_JSON)

    # stage 3
    print("VERIFY_LOCAL", flush=True)
    v = verify_local(es, rows)
    # theme knn needs embed
    theme = asyncio.run(theme_knn_check(es, rows, secrets))
    v["checks"]["theme_knn"] = theme
    if not theme.get("ok"):
        v["ok"] = False
    summary["stage3"] = v
    print("VERIFY", json.dumps({k: (val if k != "checks" else {ck: {**cv, "hits": cv.get("hits", [])[:5]} if isinstance(cv, dict) else cv for ck, cv in val.items()}) for k, val in v.items()}, ensure_ascii=False)[:2000])

    # leak check on summary text
    dumped = json.dumps(summary, ensure_ascii=False)
    hits = config.leak_check(dumped, secrets)
    summary["leak_check"] = {"ok": not hits, "hits": hits}
    if hits:
        print("FAIL leak_check")
        return 2

    out = Path(r"C:\Users\28121\AppData\Local\Temp\hymns_index_local_report.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (config.DATA_ROOT / "stage2_3_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if not v.get("ok"):
        print("FAIL verify")
        return 2
    summary["ok"] = True
    print("STAGE2_3_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
