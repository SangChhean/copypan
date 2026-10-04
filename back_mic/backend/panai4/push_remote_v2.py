# -*- coding: utf-8 -*-
"""把六个本机索引推到服务器（路一：直连 remote ES bulk，不传文件）。

索引：
  panai4_text_life / panai4_text_cwwl / panai4_text_cwwn /
  panai4_text_others / panai4_map_note / panai4_pano_catalog

用法（在 back_mic/backend 下）::

    python -m panai4.push_remote_v2
    python -m panai4.push_remote_v2 --preflight-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from copy import deepcopy
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, scan

REMOTE_ENV_KEYS = (
    "ES_REMOTE_HOST",
    "ES_REMOTE_PORT",
    "ES_REMOTE_USERNAME",
    "ES_REMOTE_PASSWORD",
)
PROTECTED_PREFIX = "kg-rag_"
ALLOWED_PREFIX = "panai4_"
BULK_SIZE = 100
PROGRESS_EVERY_BATCHES = 50
DISK_MIN_BYTES = 20 * 1024 ** 3  # 本轮预估写约 6 GB，余量不足 20 GB 停下
SAMPLE_N = 20
SAMPLE_SEED = 20260930
KG_RAG_PATTERN = "kg-rag_*"

JOBS = [
    {
        "index": "panai4_text_life",
        "expect": 39463,
        "id_field": "chunk_id",
        "has_vector": True,
        "query": "基督作我们的生命",
    },
    {
        "index": "panai4_text_cwwl",
        "expect": 178107,
        "id_field": "chunk_id",
        "has_vector": True,
        "query": "神的经纶",
    },
    {
        "index": "panai4_text_cwwn",
        "expect": 32032,
        "id_field": "chunk_id",
        "has_vector": True,
        "query": "正常的基督徒生活",
    },
    {
        "index": "panai4_text_others",
        "expect": 15481,
        "id_field": "chunk_id",
        "has_vector": True,
        "query": "召会的建造",
    },
    {
        "index": "panai4_map_note",
        "expect": 16052,
        "id_field": "chunk_id",
        "has_vector": True,
        "query": "更美之约",
    },
    {
        "index": "panai4_pano_catalog",
        "expect": 53151,
        "id_field": "node_id",
        "has_vector": False,
        "query": "以撒但为路线",
    },
]


def _backend_env() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def _report_path() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "panai4_es" / "remote_indexing_report_v2.md"


def _load_env() -> None:
    load_dotenv(_backend_env())


def make_local() -> Elasticsearch:
    _load_env()
    return Elasticsearch(
        hosts=[f"http://{os.getenv('ES_HOST', 'localhost')}:{os.getenv('ES_PORT', '9200')}"],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=120,
    )


def make_remote() -> Elasticsearch:
    _load_env()
    host = (os.getenv("ES_REMOTE_HOST") or "").strip()
    port = (os.getenv("ES_REMOTE_PORT") or "").strip()
    user = (os.getenv("ES_REMOTE_USERNAME") or "").strip()
    password = (os.getenv("ES_REMOTE_PASSWORD") or "").strip()
    missing = [
        k for k, v in zip(REMOTE_ENV_KEYS, (host, port, user, password)) if not v
    ]
    if missing:
        raise SystemExit(f"缺少远程 ES 环境变量：{'、'.join(missing)}")
    return Elasticsearch(
        hosts=[f"http://{host}:{port}"],
        basic_auth=(user, password),
        request_timeout=180,
        max_retries=2,
        retry_on_timeout=True,
    )


def _assert_safe(name: str) -> None:
    if name.startswith(PROTECTED_PREFIX):
        raise SystemExit(f"拒绝操作受保护索引：{name}")
    if not name.startswith(ALLOWED_PREFIX):
        raise SystemExit(f"远程只允许 panai4_* 索引：{name}")


def _env_status() -> dict[str, str]:
    _load_env()
    return {
        k: ("存在" if (os.getenv(k) or "").strip() else "缺失")
        for k in REMOTE_ENV_KEYS
    }


def _redact(text: str) -> str:
    out = text or ""
    for key in ("ES_REMOTE_PASSWORD", "ES_PASSWORD", "OPENROUTER_API_KEY"):
        val = os.environ.get(key) or ""
        if len(val) >= 4:
            out = out.replace(val, "[REDACTED]")
    return out


def _disk_avail_bytes(client: Elasticsearch) -> int | None:
    try:
        rows = client.cat.allocation(format="json", bytes="b")
    except Exception:  # noqa: BLE001
        return None
    vals = []
    for row in rows:
        raw = row.get("disk.avail")
        if raw is None or raw == "":
            continue
        try:
            vals.append(int(raw))
        except (TypeError, ValueError):
            continue
    return min(vals) if vals else None


def _analyze_ik(client: Elasticsearch, text: str = "基督是神的奥秘") -> dict:
    try:
        resp = client.indices.analyze(analyzer="ik_smart", text=text)
        tokens = [t["token"] for t in resp.get("tokens") or []]
        return {"ok": True, "tokens": tokens, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "tokens": [], "error": _redact(str(exc))}


def _kg_snapshot(client: Elasticsearch) -> dict:
    out = {}
    try:
        rows = client.cat.indices(index=KG_RAG_PATTERN, format="json", bytes="b")
    except Exception:  # noqa: BLE001
        rows = []
    for row in rows:
        name = row.get("index") or ""
        if name.startswith(PROTECTED_PREFIX):
            out[name] = {"docs": row.get("docs.count"), "size": row.get("store.size")}
    return out


def _local_mapping_body(local: Elasticsearch, index: str) -> dict:
    mapping = local.indices.get_mapping(index=index)[index]["mappings"]
    settings = local.indices.get_settings(index=index)[index]["settings"]["index"]
    return {
        "settings": {
            "number_of_shards": settings.get("number_of_shards", "1"),
            "number_of_replicas": "0",
        },
        "mappings": deepcopy(mapping),
    }


def _fetch_existing_ids(client: Elasticsearch, index: str) -> set[str]:
    if not client.indices.exists(index=index):
        return set()
    ids: set[str] = set()
    for hit in scan(
        client,
        index=index,
        query={"query": {"match_all": {}}, "_source": False},
        size=1000,
        scroll="5m",
    ):
        ids.add(hit["_id"])
    return ids


def _is_retryable(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timeout" in text or "timed out" in text:
        return True
    if "connection" in name or "connection" in text:
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status in (429, 502, 503, 504):
        return True
    return False


def _estimate_bytes(src: dict) -> int:
    text = src.get("text") or ""
    n = len(text.encode("utf-8")) + 200
    vec = src.get("text_vector") or src.get("embedding")
    if isinstance(vec, list):
        n += len(vec) * 12
    return n


def push_one(
    local: Elasticsearch,
    remote: Elasticsearch,
    job: dict,
    progress_rows: list,
) -> dict:
    idx = job["index"]
    _assert_safe(idx)
    expect = job["expect"]

    local_count = int(local.count(index=idx)["count"])
    if local_count != expect:
        raise SystemExit(f"LOCAL_COUNT_MISMATCH {idx} local={local_count} expect={expect}")

    if not remote.indices.exists(index=idx):
        body = _local_mapping_body(local, idx)
        print(f"CREATE {idx}", flush=True)
        remote.indices.create(index=idx, body=body)
    else:
        print(f"INDEX_EXISTS_RESUME {idx}", flush=True)

    skip_ids = _fetch_existing_ids(remote, idx)
    print(f"WRITE {idx} skip_existing={len(skip_ids)}", flush=True)

    batch = []
    ok = fail = skipped = 0
    fail_list = []
    batch_index = 0
    window_start = time.perf_counter()
    window_ok = 0
    window_bytes = 0
    started = time.perf_counter()

    def flush() -> None:
        nonlocal ok, fail, batch, batch_index, window_start, window_ok, window_bytes
        if not batch:
            return
        actions = [
            {
                "_op_type": "index",
                "_index": idx,
                "_id": item["_id"],
                "_source": item["_source"],
            }
            for item in batch
        ]
        approx = sum(_estimate_bytes(a["_source"]) for a in actions)
        last_exc = None
        for attempt in range(4):
            try:
                success, errors = bulk(
                    remote,
                    actions,
                    raise_on_error=False,
                    raise_on_exception=False,
                    request_timeout=180,
                )
                ok += success
                window_ok += success
                window_bytes += approx
                if errors:
                    for err_item in errors:
                        fail += 1
                        err = err_item.get("index") or err_item.get("create") or {}
                        error_obj = err.get("error") or {}
                        fail_list.append({
                            "id": err.get("_id"),
                            "error": _redact(str(error_obj))[:200],
                        })
                        status = error_obj.get("status") if isinstance(error_obj, dict) else None
                        if isinstance(status, int) and 400 <= status < 500 and status != 429:
                            raise SystemExit(
                                f"不可重试 bulk status={status}: {_redact(str(error_obj))[:200]}"
                            )
                last_exc = None
                break
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if _is_retryable(exc) and attempt < 3:
                    wait = 2 ** attempt
                    print(f"BULK_RETRY {idx} wait={wait} {type(exc).__name__}", flush=True)
                    time.sleep(wait)
                    continue
                raise SystemExit(f"bulk 失败：{_redact(str(exc))[:300]}") from exc
        if last_exc is not None:
            raise SystemExit(f"bulk 多次重试仍失败：{_redact(str(last_exc))[:300]}")

        batch_index += 1
        if batch_index % PROGRESS_EVERY_BATCHES == 0:
            now = time.perf_counter()
            elapsed = now - started
            w_elapsed = max(now - window_start, 1e-6)
            instant = window_ok / w_elapsed
            mb_s = (window_bytes / w_elapsed) / (1024 ** 2)
            avg = ok / elapsed if elapsed else 0
            row = {
                "index": idx,
                "batches": batch_index,
                "ok": ok,
                "elapsed_min": elapsed / 60,
                "instant": instant,
                "mb_s": mb_s,
                "avg": avg,
            }
            progress_rows.append(row)
            print(
                f"PROGRESS {idx} batches={batch_index} ok={ok} "
                f"min={elapsed/60:.1f} instant={instant:.2f}/s "
                f"mb={mb_s:.2f} avg={avg:.2f}/s",
                flush=True,
            )
            window_start = now
            window_ok = 0
            window_bytes = 0
        batch = []

    for hit in scan(
        local,
        index=idx,
        query={"query": {"match_all": {}}},
        size=200,
        scroll="10m",
        request_timeout=120,
    ):
        doc_id = hit["_id"]
        if doc_id in skip_ids:
            skipped += 1
            continue
        batch.append({"_id": doc_id, "_source": hit["_source"]})
        if len(batch) >= BULK_SIZE:
            flush()
    flush()

    remote.indices.refresh(index=idx)
    remote_count = int(remote.count(index=idx)["count"])
    elapsed = time.perf_counter() - started
    print(
        f"DONE {idx} ok={ok} fail={fail} skip={skipped} "
        f"remote={remote_count} local={local_count} sec={elapsed:.1f}",
        flush=True,
    )
    return {
        "index": idx,
        "expect": expect,
        "local_count": local_count,
        "remote_count": remote_count,
        "ok": ok,
        "fail": fail,
        "skipped_exist": skipped,
        "fail_list": fail_list[:20],
        "elapsed": elapsed,
    }


def _vectors_equal(a, b) -> bool:
    if a is None and b is None:
        return True
    if not isinstance(a, list) or not isinstance(b, list):
        return False
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if float(x) != float(y):
            return False
    return True


def consistency_check(local: Elasticsearch, remote: Elasticsearch, jobs: list) -> list:
    rows = []
    for job in jobs:
        idx = job["index"]
        id_field = job["id_field"]
        has_vector = job["has_vector"]
        resp = local.search(
            index=idx,
            size=SAMPLE_N,
            query={
                "function_score": {
                    "query": {"match_all": {}},
                    "random_score": {"seed": SAMPLE_SEED, "field": "_seq_no"},
                }
            },
            _source=True,
        )
        for hit in resp["hits"]["hits"]:
            doc_id = hit["_id"]
            loc = hit["_source"]
            diffs = []
            try:
                rem = remote.get(index=idx, id=doc_id)["_source"]
            except Exception as exc:  # noqa: BLE001
                diffs.append(f"远程获取失败：{_redact(str(exc))[:120]}")
                rows.append({
                    "index": idx,
                    "id": doc_id,
                    "id_field": id_field,
                    "diffs": diffs,
                })
                continue
            if (loc.get("text") or "") != (rem.get("text") or ""):
                diffs.append("text 不一致")
            if has_vector:
                lv = loc.get("text_vector") or loc.get("embedding")
                rv = rem.get("text_vector") or rem.get("embedding")
                if not _vectors_equal(lv, rv):
                    diffs.append("向量不一致")
            rows.append({
                "index": idx,
                "id": doc_id,
                "id_field": id_field,
                "diffs": diffs,
            })
        print(f"CONSISTENCY {idx} sampled={SAMPLE_N}", flush=True)
    return rows


def _embed_query(text: str) -> list[float]:
    import asyncio
    from kg_rag.embedding_adapter import get_embedding

    return asyncio.run(get_embedding(text, profile="kg_rag"))


def _top1_bm25(client: Elasticsearch, index: str, query: str) -> dict | None:
    resp = client.search(
        index=index,
        size=1,
        query={"match": {"text": query}},
        _source=["chunk_id", "node_id", "book_title", "text"],
    )
    hits = resp["hits"]["hits"]
    if not hits:
        return None
    h = hits[0]
    s = h["_source"]
    return {
        "id": h["_id"],
        "score": h.get("_score"),
        "text0": ((s.get("text") or "").split("\n", 1)[0])[:80],
    }


def _top1_knn(client: Elasticsearch, index: str, vec: list[float]) -> dict | None:
    resp = client.search(
        index=index,
        size=1,
        knn={
            "field": "text_vector",
            "query_vector": vec,
            "k": 1,
            "num_candidates": 50,
        },
        _source=["chunk_id", "book_title", "text"],
    )
    hits = resp["hits"]["hits"]
    if not hits:
        return None
    h = hits[0]
    s = h["_source"]
    return {
        "id": h["_id"],
        "score": h.get("_score"),
        "text0": ((s.get("text") or "").split("\n", 1)[0])[:80],
    }


def smoke_compare(local: Elasticsearch, remote: Elasticsearch, jobs: list) -> list:
    results = []
    for job in jobs:
        idx = job["index"]
        q = job["query"]
        entry = {
            "index": idx,
            "query": q,
            "bm25_local": None,
            "bm25_remote": None,
            "bm25_match": False,
            "knn_local": None,
            "knn_remote": None,
            "knn_match": None,
            "knn_error": None,
        }
        bl = _top1_bm25(local, idx, q)
        br = _top1_bm25(remote, idx, q)
        entry["bm25_local"] = bl
        entry["bm25_remote"] = br
        entry["bm25_match"] = bool(bl and br and bl["id"] == br["id"])

        if job["has_vector"]:
            try:
                vec = _embed_query(q)
                kl = _top1_knn(local, idx, vec)
                kr = _top1_knn(remote, idx, vec)
                entry["knn_local"] = kl
                entry["knn_remote"] = kr
                entry["knn_match"] = bool(kl and kr and kl["id"] == kr["id"])
            except Exception as exc:  # noqa: BLE001
                entry["knn_error"] = _redact(str(exc))[:200]
                entry["knn_match"] = False
        else:
            entry["knn_match"] = None  # N/A

        results.append(entry)
        print(
            f"SMOKE {idx} bm25_match={entry['bm25_match']} knn_match={entry['knn_match']}",
            flush=True,
        )
    return results


def write_report(path: Path, data: dict) -> None:
    pf = data["preflight"]
    lines = ["# panai4 远程建索引报告 v2", ""]
    lines.append("路一：本机直连服务器 ES bulk 写入（不传文件）。")
    lines.append("本轮六个索引：五个继承文本库 + `panai4_pano_catalog`。")
    lines.append("")
    lines.append("## 1. 第零步检查")
    lines.append("")
    for k, v in pf["env"].items():
        lines.append(f"- {k}：{v}")
    info = pf.get("info") or {}
    lines.append(f"- 服务器版本：{info.get('version')}；集群名：{info.get('cluster')}")
    lines.append(f"- 本机版本：{pf.get('local_version')}")
    ik = pf.get("ik") or {}
    if ik.get("ok"):
        lines.append(f"- IK：{' / '.join(ik.get('tokens') or [])}")
    else:
        lines.append(f"- IK：失败 — {ik.get('error')}")
    disk = pf.get("disk_avail")
    if disk is None:
        lines.append("- disk.avail（最小节点）：未知")
    else:
        lines.append(f"- disk.avail（最小节点）：{disk / 1024 ** 3:.2f} GB（门槛 20 GB）")
    existing = pf.get("existing") or []
    lines.append(
        "- 目标索引已存在："
        + ("无" if not existing else "、".join(f"`{x}`" for x in existing))
    )
    lines.append("")
    lines.append("### kg-rag_* 基线（推送前）")
    lines.append("")
    lines.append("| 索引 | docs.count | store.size |")
    lines.append("|---|---:|---:|")
    for name in sorted((pf.get("kg_before") or {}).keys()):
        row = pf["kg_before"][name]
        lines.append(f"| `{name}` | {row.get('docs')} | {row.get('size')} |")
    lines.append("")

    lines.append("## 2. 条数对账")
    lines.append("")
    lines.append(
        "| 索引 | 期望 | 本机 | 跳过已有 | 新写 | 失败 | 服务器 | 对账 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for w in data.get("writes") or []:
        ok = (
            w["local_count"] == w["expect"]
            and w["remote_count"] == w["expect"]
            and w["fail"] == 0
        )
        lines.append(
            f"| `{w['index']}` | {w['expect']:,} | {w['local_count']:,} | "
            f"{w['skipped_exist']:,} | {w['ok']:,} | {w['fail']} | "
            f"{w['remote_count']:,} | {'✓' if ok else '✗'} |"
        )
    lines.append("")

    lines.append("## 3. 上传速率")
    lines.append("")
    lines.append("批大小 100；每 50 批打印一次。")
    lines.append("")
    lines.append(
        "| # | 索引 | 累计批 | 已写 | 已用时(分) | 即时条/秒 | 即时 MB/秒 | 累计平均条/秒 |"
    )
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|")
    for i, p in enumerate(data.get("progress") or [], 1):
        lines.append(
            f"| {i} | {p['index']} | {p['batches']} | {p['ok']} | "
            f"{p['elapsed_min']:.1f} | {p['instant']:.2f} | {p['mb_s']:.2f} | "
            f"{p['avg']:.2f} |"
        )
    total_min = (data.get("total_seconds") or 0) / 60
    lines.append("")
    lines.append(f"总耗时：{total_min:.1f} 分钟。")
    lines.append("")

    lines.append("## 4. 失败清单")
    lines.append("")
    fails = []
    for w in data.get("writes") or []:
        for f in w.get("fail_list") or []:
            fails.append((w["index"], f))
    if not fails:
        lines.append("共 0 条。")
    else:
        lines.append(f"共 {len(fails)} 条（每索引最多列 20）：")
        for idx, f in fails:
            lines.append(f"- `{idx}` `{f.get('id')}`：{f.get('error')}")
    lines.append("")

    lines.append("## 5. 一致性抽查（每库 20 条）")
    lines.append("")
    cons = data.get("consistency") or []
    bad = [c for c in cons if c.get("diffs")]
    lines.append(f"合计 {len(cons)} 条；不符 {len(bad)} 条。")
    lines.append("")
    if bad:
        lines.append("不符清单：")
        for c in bad:
            lines.append(
                f"- `{c['index']}` `{c['id']}`：{'; '.join(c['diffs'])}"
            )
    else:
        lines.append("全部一致（text 逐字；有向量的库向量逐位）。")
    lines.append("")

    lines.append("## 6. 冒烟（服务器 vs 本机 top1）")
    lines.append("")
    lines.append("查询沿用 L4；kNN 用查询文本现算向量；pano 只跑 BM25。")
    lines.append("")
    for s in data.get("smoke") or []:
        lines.append(f"### `{s['index']}`　「{s['query']}」")
        lines.append("")
        bl, br = s.get("bm25_local"), s.get("bm25_remote")
        lines.append(
            f"- BM25 top1：本机 `{bl and bl['id']}` / 服务器 `{br and br['id']}` "
            f"→ {'一致' if s.get('bm25_match') else '**不一致**'}"
        )
        if bl:
            lines.append(f"  - 本机首行：{bl.get('text0')}")
        if br:
            lines.append(f"  - 服务器首行：{br.get('text0')}")
        if s.get("knn_match") is None:
            lines.append("- kNN：跳过（pano 无向量）")
        elif s.get("knn_error"):
            lines.append(f"- kNN：错误 — {s['knn_error']}")
        else:
            kl, kr = s.get("knn_local"), s.get("knn_remote")
            lines.append(
                f"- kNN top1：本机 `{kl and kl['id']}` / 服务器 `{kr and kr['id']}` "
                f"→ {'一致' if s.get('knn_match') else '**不一致**'}"
            )
            if kl:
                lines.append(f"  - 本机首行：{kl.get('text0')}")
            if kr:
                lines.append(f"  - 服务器首行：{kr.get('text0')}")
        lines.append("")

    lines.append("## 7. 备注")
    lines.append("")
    lines.append(
        "- `cwwn` 的 `message_title` 末尾带 `--书名` 重复，源自 3.5 原始数据；"
        "本轮不做修改。查书名时用 `book_title` 精确过滤。"
    )
    lines.append("")

    # kg after / disk
    lines.append("## 8. 推送后状态")
    lines.append("")
    disk_b = data.get("disk_before")
    disk_a = data.get("disk_after")
    if disk_b is not None and disk_a is not None:
        lines.append(
            f"- disk.avail：{disk_b / 1024 ** 3:.2f} GB → {disk_a / 1024 ** 3:.2f} GB"
        )
    kg_b = data.get("kg_before") or {}
    kg_a = data.get("kg_after") or {}
    kg_ok = kg_b == kg_a
    lines.append(f"- kg-rag_* 未改动：{'是' if kg_ok else '**否**'}")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {path}", flush=True)


def preflight(local: Elasticsearch, remote: Elasticsearch) -> dict:
    env = _env_status()
    local_version = None
    try:
        if local.ping():
            local_version = local.info()["version"]["number"]
    except Exception:  # noqa: BLE001
        local_version = None
    info_raw = remote.info()
    info = {
        "version": info_raw.get("version", {}).get("number"),
        "cluster": info_raw.get("cluster_name"),
    }
    ik = _analyze_ik(remote)
    disk = _disk_avail_bytes(remote)
    kg_before = _kg_snapshot(remote)
    existing = []
    existing_counts = {}
    for job in JOBS:
        if remote.indices.exists(index=job["index"]):
            existing.append(job["index"])
            existing_counts[job["index"]] = int(remote.count(index=job["index"])["count"])
    return {
        "env": env,
        "info": info,
        "local_version": local_version,
        "ik": ik,
        "disk_avail": disk,
        "existing": existing,
        "existing_counts": existing_counts,
        "kg_before": kg_before,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(_report_path()))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    report_path = Path(args.report)

    env = _env_status()
    if any(v != "存在" for v in env.values()):
        write_report(report_path, {
            "preflight": {
                "env": env, "info": {}, "ik": {"ok": False, "tokens": [], "error": "env"},
                "disk_avail": None, "existing": [], "kg_before": {}, "local_version": None,
            },
            "writes": [], "progress": [], "total_seconds": 0,
            "consistency": [], "smoke": [],
            "kg_before": {}, "kg_after": {},
            "disk_before": None, "disk_after": None,
        })
        print("ENV_MISSING", env, flush=True)
        return 2

    local = make_local()
    remote = make_remote()
    if not local.ping():
        print("LOCAL_UNREACHABLE", flush=True)
        return 2
    if not remote.ping():
        print("REMOTE_UNREACHABLE", flush=True)
        return 2

    pf = preflight(local, remote)
    print(
        "PREFLIGHT",
        "ik", pf["ik"]["ok"],
        "disk_gb", None if pf["disk_avail"] is None else round(pf["disk_avail"] / 1024 ** 3, 2),
        "existing", pf["existing"],
        flush=True,
    )

    # 本机条数预检
    for job in JOBS:
        n = int(local.count(index=job["index"])["count"])
        if n != job["expect"]:
            print("LOCAL_EXPECT_FAIL", job["index"], n, job["expect"], flush=True)
            write_report(report_path, {
                "preflight": pf, "writes": [], "progress": [], "total_seconds": 0,
                "consistency": [], "smoke": [],
                "kg_before": pf["kg_before"], "kg_after": pf["kg_before"],
                "disk_before": pf["disk_avail"], "disk_after": pf["disk_avail"],
            })
            return 2

    disk_ok = pf["disk_avail"] is not None and pf["disk_avail"] >= DISK_MIN_BYTES
    if (not pf["ik"]["ok"]) or (not disk_ok):
        write_report(report_path, {
            "preflight": pf, "writes": [], "progress": [], "total_seconds": 0,
            "consistency": [], "smoke": [],
            "kg_before": pf["kg_before"], "kg_after": pf["kg_before"],
            "disk_before": pf["disk_avail"], "disk_after": pf["disk_avail"],
        })
        print("PREFLIGHT_FAIL", flush=True)
        return 2

    # 已存在：允许续跑（幂等跳过），但报告出来
    if pf["existing"]:
        print("EXISTING_RESUME", pf["existing_counts"], flush=True)

    if args.preflight_only:
        write_report(report_path, {
            "preflight": pf, "writes": [], "progress": [], "total_seconds": 0,
            "consistency": [], "smoke": [],
            "kg_before": pf["kg_before"], "kg_after": pf["kg_before"],
            "disk_before": pf["disk_avail"], "disk_after": pf["disk_avail"],
        })
        print("PREFLIGHT_ONLY_DONE", flush=True)
        return 0

    progress_rows = []
    writes = []
    started = time.perf_counter()
    disk_before = pf["disk_avail"]
    kg_before = pf["kg_before"]

    for job in JOBS:
        result = push_one(local, remote, job, progress_rows)
        writes.append(result)
        # Q3：逐库对账，不对立刻停
        if not (
            result["local_count"] == result["expect"]
            and result["remote_count"] == result["expect"]
            and result["fail"] == 0
        ):
            write_report(report_path, {
                "preflight": pf,
                "writes": writes,
                "progress": progress_rows,
                "total_seconds": time.perf_counter() - started,
                "consistency": [],
                "smoke": [],
                "kg_before": kg_before,
                "kg_after": _kg_snapshot(remote),
                "disk_before": disk_before,
                "disk_after": _disk_avail_bytes(remote),
            })
            print(
                "COUNT_FAIL",
                result["index"],
                "local", result["local_count"],
                "remote", result["remote_count"],
                "expect", result["expect"],
                "fail", result["fail"],
                flush=True,
            )
            return 2

    total_seconds = time.perf_counter() - started

    print("CONSISTENCY_START", flush=True)
    consistency = consistency_check(local, remote, JOBS)
    print("CONSISTENCY_DONE", flush=True)

    print("SMOKE_START", flush=True)
    smoke = smoke_compare(local, remote, JOBS)
    print("SMOKE_DONE", flush=True)

    kg_after = _kg_snapshot(remote)
    disk_after = _disk_avail_bytes(remote)
    write_report(report_path, {
        "preflight": pf,
        "writes": writes,
        "progress": progress_rows,
        "total_seconds": total_seconds,
        "consistency": consistency,
        "smoke": smoke,
        "kg_before": kg_before,
        "kg_after": kg_after,
        "disk_before": disk_before,
        "disk_after": disk_after,
    })

    cons_ok = all(not c["diffs"] for c in consistency)
    smoke_ok = all(
        s["bm25_match"] and (s["knn_match"] is None or s["knn_match"])
        for s in smoke
    )
    kg_ok = kg_before == kg_after
    print(
        f"REMOTE_V2_DONE cons_ok={cons_ok} smoke_ok={smoke_ok} kg_ok={kg_ok} "
        f"min={total_seconds/60:.1f}",
        flush=True,
    )
    return 0 if cons_ok and smoke_ok and kg_ok else 1


if __name__ == "__main__":
    sys.exit(main())
