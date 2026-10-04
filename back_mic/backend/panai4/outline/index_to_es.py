# -*- coding: utf-8 -*-
"""panai4 三个索引：建 mapping、bulk 写入、冒烟测试、报告。

用法：
  python -m panai4.outline.index_to_es
  python -m panai4.outline.index_to_es --target remote
  python -m panai4.outline.index_to_es --index panai4_bible --input .../chunks_bible_vec.json

--target local：本机 es_config（默认）
--target remote：ES_REMOTE_*，只允许创建/写入 panai4_*，绝不碰 kg-rag_*。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import sys
import time
from copy import deepcopy
from typing import Any

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from es_config import es as local_es

DEFAULT_OUT = r"G:\PanAI4.0专用\纲目JSON"
ES_DATA_HINT = r"G:/copypan/es_data"
DISK_MIN_BYTES = 10 * 1024 ** 3
BULK_SIZE = 200
REMOTE_BULK_SIZE = 100
PROGRESS_EVERY_BATCHES = 50
KG_RAG_PATTERN = "kg-rag_*"
PROTECTED_PREFIX = "kg-rag_"
ALLOWED_REMOTE_PREFIX = "panai4_"
REMOTE_ENV_KEYS = (
    "ES_REMOTE_HOST",
    "ES_REMOTE_PORT",
    "ES_REMOTE_USERNAME",
    "ES_REMOTE_PASSWORD",
)
SAMPLE_SEED = 20260929

# 兼容旧名
es = local_es

OUTLINE_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "message_key": {"type": "keyword"},
            "source_path": {"type": "keyword", "index": False},
            "batch": {"type": "keyword"},
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
                "index_options": {"type": "int8_hnsw"},
            },
            "book_title": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart",
                    }
                },
            },
            "book_path": {"type": "keyword"},
            "message_title": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart",
                    }
                },
            },
            "message_number": {"type": "integer"},
            "author": {"type": "keyword"},
            "year": {"type": "integer"},
            "year_end": {"type": "integer"},
            "paragraph_type": {"type": "keyword"},
            "tokens": {"type": "integer"},
            "min_level": {"type": "integer"},
            "point_count": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            "chunk_total": {"type": "integer"},
            "para_nos": {"type": "integer", "index": False},
            "part_no": {"type": "integer"},
            "part_name": {"type": "keyword"},
            "conference": {"type": "keyword"},
            "month": {"type": "integer"},
        }
    },
}

BIBLE_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "message_key": {"type": "keyword"},
            "batch": {"type": "keyword"},
            "chunk_type": {"type": "keyword"},
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
                "index_options": {"type": "int8_hnsw"},
            },
            "book_title": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart",
                    }
                },
            },
            "book_no": {"type": "integer"},
            "message_title": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart",
                    }
                },
            },
            "message_number": {"type": "integer"},
            "author": {"type": "keyword"},
            "verse_range": {"type": "keyword"},
            "outline_path": {"type": "keyword"},
            "outline_level": {"type": "integer"},
            "paragraph_type": {"type": "keyword"},
            "tokens": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            "chunk_total": {"type": "integer"},
            "split_rule": {"type": "keyword"},
            "source_keys": {"type": "integer", "index": False},
        }
    },
}

JOBS = (
    {
        "index": "panai4_outline_12490",
        "input_name": "chunks_12490_vec.json",
        "expect": 55841,
        "mapping": OUTLINE_MAPPING,
        "kind": "outline",
    },
    {
        "index": "panai4_outline_feasts",
        "input_name": "chunks_feasts_vec.json",
        "expect": 11110,
        "mapping": OUTLINE_MAPPING,
        "kind": "outline",
    },
    {
        "index": "panai4_bible",
        "input_name": "chunks_bible_vec.json",
        "expect": 3691,
        "mapping": BIBLE_MAPPING,
        "kind": "bible",
    },
)

# 远程推送顺序：bible → feasts → 12490（小的先跑）
REMOTE_JOBS = (JOBS[2], JOBS[1], JOBS[0])

OUTLINE_FIELDS = set(OUTLINE_MAPPING["mappings"]["properties"])
BIBLE_FIELDS = set(BIBLE_MAPPING["mappings"]["properties"])


def _repo_report_path() -> str:
    here = os.path.abspath(__file__)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here)))))
    return os.path.join(root, "docs", "panai4_es", "indexing_report.md")


def _remote_report_path() -> str:
    here = os.path.abspath(__file__)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here)))))
    return os.path.join(root, "docs", "panai4_es", "remote_indexing_report.md")


def _assert_safe_index(name: str, *, remote: bool = False) -> None:
    if name.startswith(PROTECTED_PREFIX):
        raise SystemExit("拒绝操作受保护索引：{0}".format(name))
    if remote and not name.startswith(ALLOWED_REMOTE_PREFIX):
        raise SystemExit("远程只允许 panai4_* 索引：{0}".format(name))


def _remote_env_status() -> dict[str, str]:
    load_dotenv()
    status = {}
    for key in REMOTE_ENV_KEYS:
        val = (os.getenv(key) or "").strip()
        status[key] = "存在" if val else "缺失"
    return status


def make_remote_client() -> Elasticsearch:
    load_dotenv()
    host = (os.getenv("ES_REMOTE_HOST") or "").strip()
    port = (os.getenv("ES_REMOTE_PORT") or "").strip()
    user = (os.getenv("ES_REMOTE_USERNAME") or "").strip()
    password = (os.getenv("ES_REMOTE_PASSWORD") or "").strip()
    missing = [k for k, v in [
        ("ES_REMOTE_HOST", host),
        ("ES_REMOTE_PORT", port),
        ("ES_REMOTE_USERNAME", user),
        ("ES_REMOTE_PASSWORD", password),
    ] if not v]
    if missing:
        raise SystemExit("缺少远程 ES 环境变量：{0}".format("、".join(missing)))
    return Elasticsearch(
        hosts=["http://{0}:{1}".format(host, port)],
        basic_auth=(user, password),
        request_timeout=120,
        max_retries=2,
        retry_on_timeout=True,
    )


def _kg_rag_snapshot(client: Elasticsearch) -> dict[str, dict]:
    """docs.count + store.size；只读 kg-rag_*。"""
    out = {}
    try:
        rows = client.cat.indices(index=KG_RAG_PATTERN, format="json", bytes="b")
    except Exception:
        rows = []
    for row in rows:
        name = row.get("index") or ""
        if not name.startswith(PROTECTED_PREFIX):
            continue
        out[name] = {
            "docs": row.get("docs.count"),
            "size": row.get("store.size"),
        }
    return out


def _disk_avail_bytes(client: Elasticsearch) -> tuple[int | None, list]:
    """从 _cat/allocation 取各节点 disk.avail，返回最小可用字节与原始行。"""
    try:
        rows = client.cat.allocation(format="json", bytes="b")
    except Exception as exc:
        return None, [{"error": _redact(str(exc))}]
    avail_list = []
    for row in rows:
        raw = row.get("disk.avail")
        if raw is None or raw == "":
            continue
        try:
            avail_list.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not avail_list:
        return None, rows
    return min(avail_list), rows


def _fetch_existing_ids(client: Elasticsearch, index: str) -> set[str]:
    if not client.indices.exists(index=index):
        return set()
    ids = set()
    resp = client.search(
        index=index,
        body={"size": 1000, "query": {"match_all": {}}, "_source": False},
        scroll="2m",
    )
    sid = resp.get("_scroll_id")
    hits = resp["hits"]["hits"]
    while hits:
        for h in hits:
            ids.add(h["_id"])
        resp = client.scroll(scroll_id=sid, scroll="2m")
        sid = resp.get("_scroll_id")
        hits = resp["hits"]["hits"]
    if sid:
        try:
            client.clear_scroll(scroll_id=sid)
        except Exception:
            pass
    return ids


def _is_retryable_transport(exc: Exception) -> bool:
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


def _estimate_batch_bytes(batch: list) -> int:
    n = 0
    for item in batch:
        # 粗估：embedding 1024*float ~ 粗 JSON；用 dumps 太慢，按字段近似
        text = item["_source"].get("text") or ""
        n += len(text.encode("utf-8")) + 1024 * 12 + 200
    return n


def _redact(text: str) -> str:
    out = text or ""
    out = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[REDACTED]", out)
    pw = os.environ.get("ES_PASSWORD") or ""
    if pw and len(pw) >= 4:
        out = out.replace(pw, "[REDACTED]")
    key = os.environ.get("OPENROUTER_API_KEY") or ""
    if key and len(key) >= 8:
        out = out.replace(key, "[REDACTED]")
    return out


def _count_lines(path: str) -> int:
    n = 0
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                n += 1
    return n


def _kg_rag_counts() -> dict[str, int]:
    counts = {}
    try:
        names = sorted(es.indices.get_alias(index=KG_RAG_PATTERN).keys())
    except Exception:
        names = []
    for name in names:
        if not name.startswith(PROTECTED_PREFIX):
            continue
        counts[name] = int(es.count(index=name)["count"])
    return counts


def _disk_free(path: str) -> int:
    return shutil.disk_usage(path).free


def _analyze_ik(text: str = "基督是神的奥秘", client: Elasticsearch | None = None) -> dict:
    client = client or es
    try:
        resp = client.indices.analyze(analyzer="ik_smart", text=text)
        tokens = [t["token"] for t in resp.get("tokens") or []]
        return {"ok": True, "tokens": tokens, "error": None}
    except Exception as exc:
        return {"ok": False, "tokens": [], "error": _redact(str(exc))}


def _flatten_props(props: dict, prefix: str = "") -> dict[str, dict]:
    out = {}
    for name, spec in props.items():
        key = "{0}.{1}".format(prefix, name) if prefix else name
        fields = spec.get("fields") or {}
        core = {k: v for k, v in spec.items() if k != "fields"}
        out[key] = core
        for sub, sub_spec in fields.items():
            out["{0}.{1}".format(key, sub)] = dict(sub_spec)
    return out


def _diff_mapping(actual: dict, expected: dict) -> list[str]:
    """逐字段比对 properties（含 .text 子字段）。"""
    act = _flatten_props((actual.get("mappings") or {}).get("properties") or {})
    exp = _flatten_props((expected.get("mappings") or {}).get("properties") or {})
    diffs = []
    for key in sorted(set(act) | set(exp)):
        if key not in exp:
            diffs.append("多出字段 `{0}`".format(key))
            continue
        if key not in act:
            diffs.append("缺失字段 `{0}`".format(key))
            continue
        a, e = act[key], exp[key]
        for attr in ("type", "analyzer", "search_analyzer", "index", "dims", "similarity"):
            if attr in e and a.get(attr) != e.get(attr):
                diffs.append("`{0}.{1}`：期望 {2}，实际 {3}".format(key, attr, e.get(attr), a.get(attr)))
        if "index_options" in e:
            want = (e.get("index_options") or {}).get("type")
            got = (a.get("index_options") or {}).get("type")
            if want and got != want:
                diffs.append("`{0}.index_options.type`：期望 {1}，实际 {2}".format(key, want, got))
    return diffs


def _common_field_diff() -> list[str]:
    """两套 mapping 公共字段同名同类型检查。"""
    common = OUTLINE_FIELDS & BIBLE_FIELDS
    diffs = []
    oprops = OUTLINE_MAPPING["mappings"]["properties"]
    bprops = BIBLE_MAPPING["mappings"]["properties"]
    for name in sorted(common):
        o = {k: v for k, v in oprops[name].items() if k != "fields"}
        b = {k: v for k, v in bprops[name].items() if k != "fields"}
        if o.get("type") != b.get("type"):
            diffs.append("`{0}` type：outline={1} bible={2}".format(name, o.get("type"), b.get("type")))
        for attr in ("analyzer", "search_analyzer", "index", "dims", "similarity"):
            if o.get(attr) != b.get(attr) and (attr in o or attr in b):
                diffs.append("`{0}.{1}`：outline={2} bible={3}".format(name, attr, o.get(attr), b.get(attr)))
    only_o = sorted(OUTLINE_FIELDS - BIBLE_FIELDS)
    only_b = sorted(BIBLE_FIELDS - OUTLINE_FIELDS)
    return diffs, only_o, only_b


def create_index(name: str, mapping: dict, client: Elasticsearch | None = None, *, remote: bool = False) -> None:
    client = client or es
    _assert_safe_index(name, remote=remote)
    body = deepcopy(mapping)
    client.indices.create(index=name, body=body)


def iter_docs(path: str, field_names: set[str]):
    """逐行读 JSONL，过滤 tokens==0，yield (doc, skipped_info|None)。"""
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            tokens = obj.get("tokens")
            if tokens == 0:
                yield None, {
                    "message_key": obj.get("message_key"),
                    "chunk_id": obj.get("chunk_id"),
                    "chunk_index": obj.get("chunk_index"),
                }
                continue
            doc = {}
            for key in field_names:
                if key in obj:
                    doc[key] = obj[key]
            # embedding 必须有
            if "embedding" not in doc or not isinstance(doc.get("embedding"), list):
                yield None, {
                    "message_key": obj.get("message_key"),
                    "chunk_id": obj.get("chunk_id"),
                    "chunk_index": obj.get("chunk_index"),
                    "reason": "missing_embedding",
                }
                continue
            yield {"_id": obj["chunk_id"], "_source": doc}, None


def bulk_write(
    index: str,
    path: str,
    mapping: dict,
    client: Elasticsearch | None = None,
    *,
    batch_size: int | None = None,
    remote: bool = False,
    skip_ids: set[str] | None = None,
    progress_rows: list | None = None,
) -> dict:
    client = client or es
    _assert_safe_index(index, remote=remote)
    batch_size = batch_size or (REMOTE_BULK_SIZE if remote else BULK_SIZE)
    skip_ids = skip_ids or set()
    fields = set(mapping["mappings"]["properties"].keys())
    filtered = []
    missing_emb = []
    fail_list = []
    written_ids = set()
    batch = []
    ok = fail = skipped_exist = 0
    input_n = 0
    batch_index = 0
    window_start = time.perf_counter()
    window_ok = 0
    window_bytes = 0
    started = time.perf_counter()
    total_pending_hint = None

    def flush() -> None:
        nonlocal ok, fail, batch, batch_index, window_start, window_ok, window_bytes
        if not batch:
            return
        actions = [
            {
                "_op_type": "index",
                "_index": index,
                "_id": item["_id"],
                "_source": item["_source"],
            }
            for item in batch
        ]
        approx_bytes = _estimate_batch_bytes(batch)
        last_exc = None
        for attempt in range(4):
            try:
                success, errors = bulk(
                    client,
                    actions,
                    raise_on_error=False,
                    raise_on_exception=False,
                    request_timeout=180,
                )
                ok += success
                window_ok += success
                window_bytes += approx_bytes
                if errors:
                    for item in errors:
                        fail += 1
                        err = item.get("index") or item.get("create") or {}
                        status = None
                        error_obj = err.get("error") or {}
                        if isinstance(error_obj, dict):
                            status = error_obj.get("status")
                        fail_list.append({
                            "chunk_id": err.get("_id"),
                            "error": _redact(str(error_obj))[:200],
                            "status": status,
                        })
                        print("BULK_FAIL", index, err.get("_id"), flush=True)
                        # 硬 4xx（非 429）停下
                        if isinstance(status, int) and 400 <= status < 500 and status != 429:
                            raise SystemExit(
                                "不可重试的 bulk 错误 status={0}：{1}".format(
                                    status, _redact(str(error_obj))[:200])
                            )
                for item in batch:
                    written_ids.add(item["_id"])
                last_exc = None
                break
            except SystemExit:
                raise
            except Exception as exc:
                last_exc = exc
                if _is_retryable_transport(exc) and attempt < 3:
                    wait = 2 ** attempt
                    print("BULK_RETRY", index, "wait", wait, type(exc).__name__, flush=True)
                    time.sleep(wait)
                    continue
                # 非网络错误：停下
                raise SystemExit(
                    "bulk 失败（不可重试）：{0}".format(_redact(str(exc))[:300])
                ) from exc
        if last_exc is not None:
            raise SystemExit("bulk 多次重试仍失败：{0}".format(_redact(str(last_exc))[:300]))

        batch_index += 1
        print("BULK", index, "ok", ok, "fail", fail, "skip", skipped_exist, flush=True)
        if progress_rows is not None and batch_index % PROGRESS_EVERY_BATCHES == 0:
            now = time.perf_counter()
            elapsed = now - started
            w_elapsed = max(now - window_start, 1e-6)
            instant = window_ok / w_elapsed
            mb_s = (window_bytes / w_elapsed) / (1024 ** 2)
            avg = ok / elapsed if elapsed else 0
            row = {
                "index": index,
                "batches": batch_index,
                "ok": ok,
                "elapsed_min": elapsed / 60,
                "instant": instant,
                "mb_s": mb_s,
                "avg": avg,
            }
            progress_rows.append(row)
            print(
                "PROGRESS",
                index,
                "ok", ok,
                "instant", "{0:.2f}/s".format(instant),
                "mb_s", "{0:.2f}".format(mb_s),
                "avg", "{0:.2f}/s".format(avg),
                "elapsed_min", "{0:.1f}".format(row["elapsed_min"]),
                flush=True,
            )
            window_start = now
            window_ok = 0
            window_bytes = 0
        batch = []

    for doc, skip in iter_docs(path, fields):
        input_n += 1
        if skip is not None:
            if skip.get("reason") == "missing_embedding":
                missing_emb.append(skip)
            else:
                filtered.append(skip)
            continue
        if doc["_id"] in skip_ids:
            skipped_exist += 1
            continue
        batch.append(doc)
        if len(batch) >= batch_size:
            flush()
    flush()
    client.indices.refresh(index=index)
    count = int(client.count(index=index)["count"])
    return {
        "input_n": input_n,
        "filtered": filtered,
        "missing_emb": missing_emb,
        "ok": ok,
        "fail": fail,
        "fail_list": fail_list,
        "skipped_exist": skipped_exist,
        "docs_count": count,
        "written_ids": written_ids,
        "seconds": time.perf_counter() - started,
    }


def _hit_summary(hit: dict) -> dict:
    src = hit.get("_source") or {}
    text = src.get("text") or ""
    return {
        "index": hit.get("_index"),
        "message_key": src.get("message_key"),
        "book_title": src.get("book_title"),
        "message_title": src.get("message_title"),
        "score": hit.get("_score"),
        "text_head": text[:100].replace("\n", "\\n"),
    }


def bm25_search(index: str, query: str, size: int = 5, client: Elasticsearch | None = None) -> list:
    client = client or es
    body = {
        "size": size,
        "query": {"match": {"text": query}},
        "_source": ["message_key", "book_title", "message_title", "text"],
    }
    resp = client.search(index=index, body=body)
    return [_hit_summary(h) for h in resp["hits"]["hits"]]


def knn_search(index: str, vector: list, size: int = 5, client: Elasticsearch | None = None) -> list:
    client = client or es
    body = {
        "size": size,
        "knn": {
            "field": "embedding",
            "query_vector": vector,
            "k": size,
            "num_candidates": max(size * 20, 100),
        },
        "_source": ["message_key", "book_title", "message_title", "text"],
    }
    resp = client.search(index=index, body=body)
    return [_hit_summary(h) for h in resp["hits"]["hits"]]


def filter_search(index: str, query: dict, size: int = 5, client: Elasticsearch | None = None) -> tuple:
    client = client or es
    body = {
        "size": size,
        "query": query,
        "_source": ["message_key", "book_title", "message_title", "text", "chunk_type", "year", "part_no", "book_no", "batch"],
        "track_total_hits": True,
    }
    resp = client.search(index=index, body=body)
    total = resp["hits"]["total"]
    if isinstance(total, dict):
        total = total.get("value", 0)
    return int(total), [_hit_summary(h) for h in resp["hits"]["hits"]]


def _fmt_hits(lines: list, hits: list) -> None:
    if not hits:
        lines.append("（无结果）")
        lines.append("")
        return
    for i, h in enumerate(hits, 1):
        lines.append(
            "{0}. score={1} | `{2}` | {3} | {4}".format(
                i, h.get("score"), h.get("message_key"), h.get("book_title"), h.get("message_title")
            )
        )
        lines.append("   text: {0}".format(h.get("text_head")))
    lines.append("")


async def _embed_query(text: str) -> list:
    from kg_rag.embedding_adapter import get_embeddings

    vecs = await get_embeddings([text], profile="kg_rag")
    return vecs[0]


def _header_hits(hits: list, needle: str) -> int:
    n = 0
    for h in hits:
        blob = "{0} {1} {2}".format(
            h.get("book_title") or "",
            h.get("message_title") or "",
            h.get("text_head") or "",
        )
        if needle in blob:
            n += 1
    return n


def run_smoke(indices: dict, client: Elasticsearch | None = None) -> dict:
    """indices: label -> index name。client 默认本机。"""
    import asyncio

    client = client or es
    results = {"bm25": [], "header": [], "knn": [], "filters": [], "cross": None}

    # A
    for q in ("基督作我们的生命", "神的经纶", "召会的建造"):
        for label, index in indices.items():
            hits = bm25_search(index, q, client=client)
            results["bm25"].append({"query": q, "index": index, "label": label, "hits": hits})

    # B header
    header_cases = [
        ("福音题纲", indices["12490"], "福音题纲"),
        ("以弗所书", indices["bible"], "以弗所书"),
        ("安那翰秋季全时间训练", indices["feasts"], "安那翰秋季全时间训练"),
    ]
    for q, index, needle in header_cases:
        hits = bm25_search(index, q, client=client)
        matched = _header_hits(hits, needle)
        results["header"].append({
            "query": q, "index": index, "needle": needle,
            "hits": hits, "matched": matched,
        })

    # C knn
    async def _knn_all():
        out = []
        for q in ("基督作我们的生命", "以弗所书讲召会"):
            vec = await _embed_query(q)
            for label, index in indices.items():
                hits = knn_search(index, vec, client=client)
                out.append({"query": q, "index": index, "label": label, "hits": hits})
        return out

    results["knn"] = asyncio.run(_knn_all())

    # D filters — 远程报告只要 batch / book_outline / book_no；本机保留完整套
    total, hits = filter_search(indices["feasts"], {"term": {"batch": "feasts"}}, client=client)
    results["filters"].append({"name": "batch=feasts", "index": indices["feasts"], "total": total, "hits": hits})

    agg = client.search(
        index=indices["12490"],
        body={
            "size": 0,
            "query": {"term": {"book_title": "福音题纲"}},
            "aggs": {"bt": {"terms": {"field": "book_title", "size": 5}}},
        },
    )
    book_val = "福音题纲"
    buckets = (((agg.get("aggregations") or {}).get("bt") or {}).get("buckets")) or []
    if buckets and book_val not in [b["key"] for b in buckets]:
        book_val = buckets[0]["key"]
    total, hits = filter_search(indices["12490"], {"term": {"book_title": book_val}}, client=client)
    if total == 0 and buckets:
        book_val = buckets[0]["key"]
        total, hits = filter_search(indices["12490"], {"term": {"book_title": book_val}}, client=client)
    results["filters"].append({
        "name": "book_title={0}".format(book_val),
        "index": indices["12490"],
        "total": total,
        "hits": hits,
        "book_title_value": book_val,
    })

    total, hits = filter_search(
        indices["12490"],
        {"range": {"year": {"gte": 1990, "lte": 1997}}},
        client=client,
    )
    results["filters"].append({"name": "year 1990~1997", "index": indices["12490"], "total": total, "hits": hits})

    total, hits = filter_search(indices["12490"], {"term": {"part_no": 2}}, client=client)
    results["filters"].append({"name": "part_no=2", "index": indices["12490"], "total": total, "hits": hits})

    total, hits = filter_search(indices["bible"], {"term": {"chunk_type": "book_outline"}}, client=client)
    results["filters"].append({
        "name": "chunk_type=book_outline",
        "index": indices["bible"],
        "total": total,
        "hits": hits,
        "expect": 66,
    })

    total, hits = filter_search(
        indices["bible"],
        {"range": {"book_no": {"gte": 40, "lte": 66}}},
        client=client,
    )
    results["filters"].append({"name": "book_no 40~66", "index": indices["bible"], "total": total, "hits": hits})

    # E cross
    try:
        resp = client.search(
            index="panai4_*",
            body={
                "size": 9,
                "query": {"match": {"text": "基督"}},
                "_source": ["message_key", "book_title", "message_title", "text"],
            },
        )
        by_index = {}
        for h in resp["hits"]["hits"]:
            by_index.setdefault(h["_index"], []).append(_hit_summary(h))
        results["cross"] = {"ok": True, "by_index": by_index, "error": None}
    except Exception as exc:
        results["cross"] = {"ok": False, "by_index": {}, "error": _redact(str(exc))}

    return results


def write_report(path: str, data: dict) -> None:
    lines = []
    w = lines.append
    w("# panai4 本机建索引报告")
    w("")
    w("方案：`chunks_es_plan.md` v0.2 第七、九节；`bible_index_plan.md` 第八、九节。")
    w("本步不上服务器。")
    w("")

    w("## 1. 第零步检查")
    w("")
    pre = data["preflight"]
    for row in pre["counts"]:
        w("- `{0}`：{1} 条（期望 {2}）{3}".format(
            row["name"], row["n"], row["expect"], "✓" if row["n"] == row["expect"] else "✗"))
    w("- G: 盘余量：{0:.2f} GB（须 ≥ 10 GB）{1}".format(
        pre["g_free"] / 1024 ** 3, "✓" if pre["g_free"] >= DISK_MIN_BYTES else "✗"))
    w("- 目标索引已存在：{0}".format(pre["existing"] or "无"))
    for name, cnt in (pre.get("existing_counts") or {}).items():
        w("  - `{0}` docs.count={1}".format(name, cnt))
    ik = pre["ik"]
    if ik["ok"]:
        w("- IK `ik_smart`：{0}".format(" / ".join(ik["tokens"])))
    else:
        w("- IK 失败：{0}".format(ik["error"]))
    w("")

    w("## 2. 条数对账")
    w("")
    w("| 索引 | 输入 | 过滤 tokens=0 | 写入成功 | docs.count |")
    w("|---|---:|---:|---:|---:|")
    for row in data["writes"]:
        w("| `{0}` | {1} | {2} | {3} | {4} |".format(
            row["index"], row["input_n"], len(row["filtered"]), row["ok"], row["docs_count"]))
    w("")
    for row in data["writes"]:
        if row["filtered"]:
            w("### `{0}` 过滤清单（tokens==0）".format(row["index"]))
            w("")
            for item in row["filtered"]:
                w("- `{0}`".format(item.get("message_key")))
            w("")
        else:
            w("`{0}`：无 tokens==0 过滤。".format(row["index"]))
    w("")

    w("## 3. mapping 比对")
    w("")
    diffs_common, only_o, only_b = data["common_diff"]
    w("公共字段类型差异：{0}".format(len(diffs_common)))
    for d in diffs_common:
        w("- {0}".format(d))
    if not diffs_common:
        w("- 无（公共字段同名同类型）")
    w("- 仅纲目：{0}".format("、".join("`{0}`".format(x) for x in only_o)))
    w("- 仅圣经：{0}".format("、".join("`{0}`".format(x) for x in only_b)))
    w("")
    for row in data["mapping_diffs"]:
        w("### `{0}`".format(row["index"]))
        w("")
        if row["diffs"]:
            for d in row["diffs"]:
                w("- {0}".format(d))
        else:
            w("- 与方案一致。")
        w("")

    w("## 4. 孤儿文档")
    w("")
    for row in data["orphans"]:
        w("- `{0}`：{1}".format(row["index"], row["n"]))
        for cid in row["ids"][:20]:
            w("  - `{0}`".format(cid))
    w("")

    smoke = data["smoke"]
    w("## 5. 冒烟测试")
    w("")
    w("### A. BM25")
    w("")
    for item in smoke["bm25"]:
        w("#### 「{0}」→ `{1}`".format(item["query"], item["index"]))
        w("")
        _fmt_hits(lines, item["hits"])

    w("### B. 头部行验证")
    w("")
    for item in smoke["header"]:
        w("#### 「{0}」→ `{1}`（针：{2}，top-5 命中 {3}/5）".format(
            item["query"], item["index"], item["needle"], item["matched"]))
        w("")
        _fmt_hits(lines, item["hits"])

    w("### C. kNN")
    w("")
    for item in smoke["knn"]:
        w("#### 「{0}」→ `{1}`".format(item["query"], item["index"]))
        w("")
        _fmt_hits(lines, item["hits"])

    w("### D. 过滤")
    w("")
    for item in smoke["filters"]:
        extra = ""
        if item.get("expect") is not None:
            extra = "（期望 {0}）".format(item["expect"])
        w("#### {0} → `{1}` total={2}{3}".format(
            item["name"], item["index"], item["total"], extra))
        w("")
        _fmt_hits(lines, item["hits"])

    w("### E. 跨索引 `panai4_*`「基督」")
    w("")
    cross = smoke["cross"]
    if not cross["ok"]:
        w("报错：{0}".format(cross["error"]))
    else:
        for idx, hits in sorted(cross["by_index"].items()):
            w("#### `{0}`（本页 {1} 条）".format(idx, len(hits)))
            w("")
            _fmt_hits(lines, hits)
        missing = [n for n in data["index_names"] if n not in cross["by_index"]]
        if missing:
            w("未出现在本页的索引：{0}".format("、".join(missing)))
        else:
            w("三个索引本页均有结果。")
    w("")

    w("## 6. 索引占用")
    w("")
    w("| 索引 | docs.count | store.size |")
    w("|---|---:|---|")
    for row in data["cat"]:
        w("| `{0}` | {1} | {2} |".format(row["index"], row["docs"], row["size"]))
    w("")

    w("## 7. 磁盘与保护索引")
    w("")
    w("| | 建索引前 | 建索引后 |")
    w("|---|---:|---:|")
    w("| G: 余量（字节） | {0} | {1} |".format(data["g_before"], data["g_after"]))
    w("| G: 余量（GB） | {0:.2f} | {1:.2f} |".format(
        data["g_before"] / 1024 ** 3, data["g_after"] / 1024 ** 3))
    w("")
    w("### kg-rag_* docs.count 前后对照")
    w("")
    w("| 索引 | 前 | 后 |")
    w("|---|---:|---:|")
    names = sorted(set(data["kg_before"]) | set(data["kg_after"]))
    for name in names:
        w("| `{0}` | {1} | {2} |".format(
            name, data["kg_before"].get(name), data["kg_after"].get(name)))
    same_kg = data["kg_before"] == data["kg_after"]
    w("")
    w("kg-rag_* 条数前后完全一致。" if same_kg else "kg-rag_* 条数发生变化。")
    w("")

    w("## 8. 输入文件")
    w("")
    w("| 文件 | 前 | 后 |")
    w("|---|---:|---:|")
    for name, before in data["input_before"].items():
        after = data["input_after"].get(name)
        w("| `{0}` | {1} | {2} |".format(name, before, after))
    w("")

    text = _redact("\n".join(lines).rstrip() + "\n")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)


def main_local(args) -> int:
    report_path = args.report or _repo_report_path()

    if not es.ping():
        print("ES_UNREACHABLE", flush=True)
        return 2

    # 选定 jobs
    if args.index or args.input:
        if not (args.index and args.input):
            print("需要同时提供 --index 与 --input", flush=True)
            return 2
        job = None
        for candidate in JOBS:
            if candidate["index"] == args.index:
                job = dict(candidate)
                job["input"] = args.input
                break
        if job is None:
            # 按名猜 mapping
            kind = "bible" if "bible" in args.index else "outline"
            job = {
                "index": args.index,
                "input": args.input,
                "input_name": os.path.basename(args.input),
                "expect": None,
                "mapping": BIBLE_MAPPING if kind == "bible" else OUTLINE_MAPPING,
                "kind": kind,
            }
        jobs = [job]
    else:
        jobs = []
        for candidate in JOBS:
            job = dict(candidate)
            job["input"] = os.path.join(args.out, candidate["input_name"])
            jobs.append(job)

    g_before = _disk_free("G:/")
    kg_before = _kg_rag_counts()
    input_before = {os.path.basename(j["input"]): os.path.getsize(j["input"]) for j in jobs}

    # --- preflight ---
    pre_counts = []
    for job in jobs:
        n = _count_lines(job["input"])
        pre_counts.append({
            "name": os.path.basename(job["input"]),
            "n": n,
            "expect": job.get("expect"),
        })
        job["line_count"] = n

    existing = []
    existing_counts = {}
    for job in jobs:
        if es.indices.exists(index=job["index"]):
            existing.append(job["index"])
            existing_counts[job["index"]] = int(es.count(index=job["index"])["count"])

    ik = _analyze_ik()
    preflight = {
        "counts": pre_counts,
        "g_free": g_before,
        "existing": existing,
        "existing_counts": existing_counts,
        "ik": ik,
    }

    count_ok = all(
        row["expect"] is None or row["n"] == row["expect"] for row in pre_counts
    )
    if not count_ok or g_before < DISK_MIN_BYTES or existing or not ik["ok"]:
        # 仍写出部分报告
        write_report(report_path, {
            "preflight": preflight,
            "writes": [],
            "common_diff": _common_field_diff(),
            "mapping_diffs": [],
            "orphans": [],
            "smoke": {"bm25": [], "header": [], "knn": [], "filters": [], "cross": {"ok": False, "by_index": {}, "error": "preflight"}},
            "cat": [],
            "g_before": g_before,
            "g_after": g_before,
            "kg_before": kg_before,
            "kg_after": kg_before,
            "input_before": input_before,
            "input_after": input_before,
            "index_names": [j["index"] for j in jobs],
        })
        print("PREFLIGHT_FAIL", "existing", existing, "ik", ik["ok"], "count_ok", count_ok, flush=True)
        if existing:
            print("目标索引已存在，请决定是否删除重建：", existing_counts, flush=True)
        return 2

    # --- create + write ---
    writes = []
    mapping_diffs = []
    orphans = []
    for job in jobs:
        print("CREATE", job["index"], flush=True)
        create_index(job["index"], job["mapping"])
        print("WRITE", job["index"], job["input"], flush=True)
        result = bulk_write(job["index"], job["input"], job["mapping"])
        writes.append({
            "index": job["index"],
            "input_n": result["input_n"],
            "filtered": result["filtered"],
            "ok": result["ok"],
            "fail": result["fail"],
            "docs_count": result["docs_count"],
        })
        # mapping diff
        actual = es.indices.get_mapping(index=job["index"])[job["index"]]
        diffs = _diff_mapping(actual, job["mapping"])
        mapping_diffs.append({"index": job["index"], "diffs": diffs})
        # orphans: existing docs not in this write (first create → 0)
        # scroll all ids
        orphan_ids = []
        resp = es.search(
            index=job["index"],
            body={"size": 1000, "query": {"match_all": {}}, "_source": False},
            scroll="2m",
        )
        sid = resp.get("_scroll_id")
        hits = resp["hits"]["hits"]
        while hits:
            for h in hits:
                if h["_id"] not in result["written_ids"]:
                    # also allow filtered tokens==0 never written
                    orphan_ids.append(h["_id"])
            resp = es.scroll(scroll_id=sid, scroll="2m")
            sid = resp.get("_scroll_id")
            hits = resp["hits"]["hits"]
        if sid:
            try:
                es.clear_scroll(scroll_id=sid)
            except Exception:
                pass
        orphans.append({"index": job["index"], "n": len(orphan_ids), "ids": orphan_ids})
        print(
            "DONE", job["index"],
            "docs", result["docs_count"],
            "filtered", len(result["filtered"]),
            "fail", result["fail"],
            flush=True,
        )

    # smoke
    index_map = {}
    for job in jobs:
        if job["index"] == "panai4_outline_12490":
            index_map["12490"] = job["index"]
        elif job["index"] == "panai4_outline_feasts":
            index_map["feasts"] = job["index"]
        elif job["index"] == "panai4_bible":
            index_map["bible"] = job["index"]
    # if single-index run, skip full smoke requiring all three
    if len(index_map) == 3:
        print("SMOKE_START", flush=True)
        smoke = run_smoke(index_map)
        print("SMOKE_DONE", flush=True)
    else:
        smoke = {"bm25": [], "header": [], "knn": [], "filters": [], "cross": {"ok": False, "by_index": {}, "error": "need all three indexes"}}

    # cat
    cat_rows = []
    cat = es.cat.indices(index="panai4_*", format="json", bytes="b")
    for row in cat:
        cat_rows.append({
            "index": row["index"],
            "docs": row.get("docs.count"),
            "size": row.get("store.size"),
        })

    g_after = _disk_free("G:/")
    kg_after = _kg_rag_counts()
    input_after = {os.path.basename(j["input"]): os.path.getsize(j["input"]) for j in jobs}

    write_report(report_path, {
        "preflight": preflight,
        "writes": writes,
        "common_diff": _common_field_diff(),
        "mapping_diffs": mapping_diffs,
        "orphans": orphans,
        "smoke": smoke,
        "cat": cat_rows,
        "g_before": g_before,
        "g_after": g_after,
        "kg_before": kg_before,
        "kg_after": kg_after,
        "input_before": input_before,
        "input_after": input_after,
        "index_names": [j["index"] for j in jobs],
    })

    # verify hard checks
    header_ok = all(item["matched"] >= 3 for item in smoke.get("header") or []) if smoke.get("header") else False
    outline66 = None
    for item in smoke.get("filters") or []:
        if item["name"] == "chunk_type=book_outline":
            outline66 = item["total"]
    knn_ok = True
    for item in smoke.get("knn") or []:
        if not item["hits"]:
            knn_ok = False
        for h in item["hits"]:
            score = h.get("score")
            if score is None or score < 0 or score > 1.0001:
                knn_ok = False
    cross_ok = bool((smoke.get("cross") or {}).get("ok"))
    counts_ok = all(
        row["docs_count"] == row["input_n"] - len(row["filtered"])
        for row in writes
    )
    kg_ok = kg_before == kg_after
    inputs_ok = input_before == input_after

    ok = (
        counts_ok and header_ok and outline66 == 66 and knn_ok and cross_ok
        and kg_ok and inputs_ok
        and all(row["fail"] == 0 for row in writes)
    )
    print(
        "INDEX_DONE",
        "ok", ok,
        "header_ok", header_ok,
        "outline66", outline66,
        "knn_ok", knn_ok,
        "cross_ok", cross_ok,
        flush=True,
    )
    return 0 if ok else 2


def _sample_ids_for_consistency(out_dir: str, n: int = 20) -> list[tuple[str, str]]:
    """返回 [(index_name, chunk_id), ...]，三份按比例，种子固定。"""
    sizes = {
        "panai4_outline_12490": 55841,
        "panai4_outline_feasts": 11110,
        "panai4_bible": 3691,
    }
    files = {
        "panai4_outline_12490": "chunks_12490_vec.json",
        "panai4_outline_feasts": "chunks_feasts_vec.json",
        "panai4_bible": "chunks_bible_vec.json",
    }
    total = sum(sizes.values())
    raw = {k: n * sizes[k] / total for k in sizes}
    base = {k: int(raw[k]) for k in sizes}
    remain = n - sum(base.values())
    for k in sorted(sizes, key=lambda x: raw[x] - base[x], reverse=True):
        if remain <= 0:
            break
        base[k] += 1
        remain -= 1
    rng = random.Random(SAMPLE_SEED)
    picked = []
    for index_name, quota in base.items():
        path = os.path.join(out_dir, files[index_name])
        ids = []
        with open(path, encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("tokens") == 0:
                    continue
                ids.append(obj["chunk_id"])
        sample = rng.sample(ids, min(quota, len(ids)))
        for cid in sample:
            picked.append((index_name, cid))
    return picked


def _compare_docs(local_doc: dict, remote_doc: dict) -> list[str]:
    diffs = []
    if (local_doc.get("text") or "") != (remote_doc.get("text") or ""):
        diffs.append("text 不同")
    le = local_doc.get("embedding") or []
    re_ = remote_doc.get("embedding") or []
    if le[:10] != re_[:10]:
        diffs.append("embedding 前 10 不同")
    keys = set(local_doc) | set(remote_doc)
    keys.discard("embedding")
    for key in sorted(keys):
        if local_doc.get(key) != remote_doc.get(key):
            diffs.append("字段 `{0}` 不同".format(key))
    return diffs


def write_remote_report(path: str, data: dict) -> None:
    lines = []
    w = lines.append
    w("# panai4 远程建索引报告")
    w("")
    w("路一：本机直连服务器 ES bulk 写入（不传文件）。")
    w("方案：`chunks_es_plan.md` v0.2 第八节；mapping 同本机。")
    w("")

    w("## 1. 第零步检查")
    w("")
    pre = data["preflight"]
    for key, st in pre["env"].items():
        w("- {0}：{1}".format(key, st))
    info = pre["info"]
    w("- 服务器版本：{0}；集群名：{1}".format(info.get("version"), info.get("cluster")))
    w("- 本机版本：{0}".format(pre.get("local_version")))
    ik = pre["ik"]
    if ik["ok"]:
        w("- IK：{0}".format(" / ".join(ik["tokens"])))
    else:
        w("- IK 失败：{0}".format(ik["error"]))
    w("- disk.avail（最小节点）：{0:.2f} GB".format((pre["disk_avail"] or 0) / 1024 ** 3))
    w("- 目标索引已存在：{0}".format(pre["existing"] or "无"))
    w("")
    w("### kg-rag_* 基线")
    w("")
    w("| 索引 | docs.count | store.size |")
    w("|---|---:|---|")
    for name in sorted(pre["kg_before"]):
        row = pre["kg_before"][name]
        w("| `{0}` | {1} | {2} |".format(name, row.get("docs"), row.get("size")))
    w("")

    w("## 2. 条数对账")
    w("")
    w("| 索引 | 输入 | 过滤 | 跳过已有 | 新写 | 失败 | docs.count |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    for row in data["writes"]:
        w("| `{0}` | {1} | {2} | {3} | {4} | {5} | {6} |".format(
            row["index"], row["input_n"], len(row["filtered"]),
            row["skipped_exist"], row["ok"], row["fail"], row["docs_count"]))
    w("")

    w("## 3. 上传速率")
    w("")
    w("批大小 {0}；每 {1} 批打印一次。".format(REMOTE_BULK_SIZE, PROGRESS_EVERY_BATCHES))
    w("")
    if data["progress"]:
        w("| # | 索引 | 累计批 | 已写 | 已用时(分) | 即时条/秒 | 即时 MB/秒 | 累计平均条/秒 |")
        w("|---:|---|---:|---:|---:|---:|---:|---:|")
        for i, row in enumerate(data["progress"], 1):
            w("| {0} | {1} | {2} | {3} | {4:.1f} | {5:.2f} | {6:.2f} | {7:.2f} |".format(
                i, row["index"], row["batches"], row["ok"], row["elapsed_min"],
                row["instant"], row["mb_s"], row["avg"]))
    else:
        w("无进度采样（可能全部跳过）。")
    w("")
    w("总耗时：{0:.1f} 分钟。".format(data["total_seconds"] / 60))
    w("")

    w("## 4. 失败清单")
    w("")
    fails = []
    for row in data["writes"]:
        for item in row.get("fail_list") or []:
            fails.append((row["index"], item))
    w("共 {0} 条。".format(len(fails)))
    for index, item in fails[:50]:
        w("- `{0}` `{1}`：{2}".format(index, item.get("chunk_id"), item.get("error")))
    w("")

    smoke = data["smoke"]
    w("## 5. 冒烟测试（服务器）")
    w("")
    w("### A. BM25")
    w("")
    for item in smoke["bm25"]:
        w("#### 「{0}」→ `{1}`".format(item["query"], item["index"]))
        w("")
        _fmt_hits(lines, item["hits"])
    w("### B. 头部行")
    w("")
    for item in smoke["header"]:
        w("#### 「{0}」→ `{1}`（命中 {2}/5）".format(
            item["query"], item["index"], item["matched"]))
        w("")
        _fmt_hits(lines, item["hits"])
    w("### C. kNN")
    w("")
    for item in smoke["knn"]:
        w("#### 「{0}」→ `{1}`".format(item["query"], item["index"]))
        w("")
        _fmt_hits(lines, item["hits"])
    w("### D. 过滤")
    w("")
    for item in smoke["filters"]:
        if item["name"] not in ("batch=feasts", "chunk_type=book_outline", "book_no 40~66") and not item["name"].startswith("book_title="):
            # 远程任务 D 组只要指定几项；其它也打印无妨
            pass
        extra = ""
        if item.get("expect") is not None:
            extra = "（期望 {0}）".format(item["expect"])
        w("#### {0} → `{1}` total={2}{3}".format(
            item["name"], item["index"], item["total"], extra))
        w("")
        _fmt_hits(lines, item["hits"])
    w("### E. 跨索引")
    w("")
    cross = smoke["cross"]
    if not cross["ok"]:
        w("报错：{0}".format(cross["error"]))
    else:
        for idx, hits in sorted(cross["by_index"].items()):
            w("#### `{0}`".format(idx))
            w("")
            _fmt_hits(lines, hits)
    w("")

    w("## 6. 本机与服务器一致性抽查")
    w("")
    w("种子 {0}，共 {1} 条。".format(SAMPLE_SEED, len(data["consistency"])))
    w("")
    bad = [c for c in data["consistency"] if c["diffs"]]
    w("不一致：{0}。".format(len(bad)))
    for item in data["consistency"]:
        if item["diffs"]:
            w("- `{0}` `{1}`：{2}".format(item["index"], item["chunk_id"], "；".join(item["diffs"])))
        else:
            w("- `{0}` `{1}`：一致".format(item["index"], item["chunk_id"]))
    w("")

    w("## 7. 服务器索引占用")
    w("")
    w("| 索引 | docs.count | store.size |")
    w("|---|---:|---|")
    for row in data["cat"]:
        w("| `{0}` | {1} | {2} |".format(row["index"], row["docs"], row["size"]))
    w("")

    w("## 8. kg-rag_* 前后对照")
    w("")
    w("| 索引 | docs 前 | docs 后 | size 前 | size 后 |")
    w("|---|---:|---:|---:|---:|")
    names = sorted(set(data["kg_before"]) | set(data["kg_after"]))
    changed = []
    for name in names:
        b = data["kg_before"].get(name) or {}
        a = data["kg_after"].get(name) or {}
        w("| `{0}` | {1} | {2} | {3} | {4} |".format(
            name, b.get("docs"), a.get("docs"), b.get("size"), a.get("size")))
        if b != a:
            changed.append(name)
    w("")
    if changed:
        w("**警告：以下 kg-rag_* 发生变化：{0}**".format("、".join(changed)))
    else:
        w("kg-rag_* docs.count 与 store.size 前后完全一致。")
    w("")

    w("## 9. 磁盘与输入")
    w("")
    w("| | 前 | 后 |")
    w("|---|---:|---:|")
    w("| disk.avail（字节） | {0} | {1} |".format(data["disk_before"], data["disk_after"]))
    w("| disk.avail（GB） | {0:.2f} | {1:.2f} |".format(
        (data["disk_before"] or 0) / 1024 ** 3, (data["disk_after"] or 0) / 1024 ** 3))
    w("")
    w("| 文件 | 前 | 后 |")
    w("|---|---:|---:|")
    for name, before in data["input_before"].items():
        w("| `{0}` | {1} | {2} |".format(name, before, data["input_after"].get(name)))
    w("")

    text = _redact("\n".join(lines).rstrip() + "\n")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)


def main_remote(args) -> int:
    report_path = args.report or _remote_report_path()
    out_dir = args.out or DEFAULT_OUT

    env_status = _remote_env_status()
    if any(v != "存在" for v in env_status.values()):
        write_remote_report(report_path, {
            "preflight": {
                "env": env_status, "info": {}, "ik": {"ok": False, "tokens": [], "error": "env"},
                "disk_avail": 0, "existing": [], "kg_before": {}, "local_version": None,
            },
            "writes": [], "progress": [], "total_seconds": 0, "smoke": {
                "bm25": [], "header": [], "knn": [], "filters": [],
                "cross": {"ok": False, "by_index": {}, "error": "preflight"},
            },
            "consistency": [], "cat": [],
            "kg_before": {}, "kg_after": {},
            "disk_before": 0, "disk_after": 0,
            "input_before": {}, "input_after": {},
        })
        print("ENV_MISSING", env_status, flush=True)
        return 2

    remote = make_remote_client()
    if not remote.ping():
        print("REMOTE_UNREACHABLE", flush=True)
        return 2

    # 本机版本对照
    local_version = None
    try:
        if local_es.ping():
            local_version = local_es.info()["version"]["number"]
    except Exception:
        local_version = None

    info_raw = remote.info()
    info = {
        "version": info_raw.get("version", {}).get("number"),
        "cluster": info_raw.get("cluster_name"),
    }
    ik = _analyze_ik(client=remote)
    disk_before, _alloc = _disk_avail_bytes(remote)
    kg_before = _kg_rag_snapshot(remote)

    jobs = []
    for candidate in REMOTE_JOBS:
        job = dict(candidate)
        job["input"] = os.path.join(out_dir, candidate["input_name"])
        jobs.append(job)

    input_before = {j["input_name"]: os.path.getsize(j["input"]) for j in jobs}
    existing = []
    existing_counts = {}
    for job in jobs:
        if remote.indices.exists(index=job["index"]):
            existing.append(job["index"])
            existing_counts[job["index"]] = int(remote.count(index=job["index"])["count"])

    preflight = {
        "env": env_status,
        "info": info,
        "local_version": local_version,
        "ik": ik,
        "disk_avail": disk_before,
        "existing": existing,
        "existing_counts": existing_counts,
        "kg_before": kg_before,
    }

    # 条数确认
    for job in jobs:
        n = _count_lines(job["input"])
        if job["expect"] and n != job["expect"]:
            print("COUNT_MISMATCH", job["input_name"], n, job["expect"], flush=True)
            return 2

    if existing or not ik["ok"] or disk_before is None or disk_before < DISK_MIN_BYTES:
        write_remote_report(report_path, {
            "preflight": preflight,
            "writes": [], "progress": [], "total_seconds": 0,
            "smoke": {"bm25": [], "header": [], "knn": [], "filters": [],
                      "cross": {"ok": False, "by_index": {}, "error": "preflight"}},
            "consistency": [], "cat": [],
            "kg_before": kg_before, "kg_after": kg_before,
            "disk_before": disk_before, "disk_after": disk_before,
            "input_before": input_before, "input_after": input_before,
        })
        print("PREFLIGHT_FAIL", "existing", existing_counts, "ik", ik["ok"],
              "disk_gb", None if disk_before is None else round(disk_before / 1024 ** 3, 2), flush=True)
        return 2

    progress_rows = []
    writes = []
    started = time.perf_counter()

    for job in jobs:
        idx = job["index"]
        _assert_safe_index(idx, remote=True)
        if not remote.indices.exists(index=idx):
            print("CREATE", idx, flush=True)
            try:
                create_index(idx, job["mapping"], client=remote, remote=True)
            except Exception as exc:
                # 硬错误停下
                print("CREATE_FAIL", _redact(str(exc))[:300], flush=True)
                return 2
        else:
            # 理论上 preflight 已拦住；若续跑允许存在
            print("INDEX_EXISTS_RESUME", idx, flush=True)

        skip_ids = _fetch_existing_ids(remote, idx)
        print("WRITE", idx, "skip_existing", len(skip_ids), flush=True)
        result = bulk_write(
            idx, job["input"], job["mapping"],
            client=remote, remote=True, batch_size=REMOTE_BULK_SIZE,
            skip_ids=skip_ids, progress_rows=progress_rows,
        )
        expect_count = job["expect"] - len(result["filtered"])
        if result["docs_count"] != expect_count:
            writes.append({
                "index": idx,
                "input_n": result["input_n"],
                "filtered": result["filtered"],
                "skipped_exist": result["skipped_exist"],
                "ok": result["ok"],
                "fail": result["fail"],
                "fail_list": result["fail_list"],
                "docs_count": result["docs_count"],
            })
            write_remote_report(report_path, {
                "preflight": preflight,
                "writes": writes,
                "progress": progress_rows,
                "total_seconds": time.perf_counter() - started,
                "smoke": {"bm25": [], "header": [], "knn": [], "filters": [],
                          "cross": {"ok": False, "by_index": {}, "error": "count mismatch"}},
                "consistency": [], "cat": [],
                "kg_before": kg_before, "kg_after": _kg_rag_snapshot(remote),
                "disk_before": disk_before, "disk_after": _disk_avail_bytes(remote)[0],
                "input_before": input_before,
                "input_after": {j["input_name"]: os.path.getsize(j["input"]) for j in jobs},
            })
            print("COUNT_FAIL", idx, "docs", result["docs_count"], "expect", expect_count, flush=True)
            return 2

        writes.append({
            "index": idx,
            "input_n": result["input_n"],
            "filtered": result["filtered"],
            "skipped_exist": result["skipped_exist"],
            "ok": result["ok"],
            "fail": result["fail"],
            "fail_list": result["fail_list"],
            "docs_count": result["docs_count"],
        })
        print("DONE", idx, "docs", result["docs_count"], "fail", result["fail"], flush=True)

    total_seconds = time.perf_counter() - started

    print("SMOKE_START", flush=True)
    smoke = run_smoke({
        "12490": "panai4_outline_12490",
        "feasts": "panai4_outline_feasts",
        "bible": "panai4_bible",
    }, client=remote)
    print("SMOKE_DONE", flush=True)

    # consistency
    print("CONSISTENCY_START", flush=True)
    consistency = []
    if not local_es.ping():
        print("LOCAL_ES_DOWN_SKIP_CONSISTENCY", flush=True)
    else:
        for index_name, cid in _sample_ids_for_consistency(out_dir, 20):
            try:
                loc = local_es.get(index=index_name, id=cid)["_source"]
                rem = remote.get(index=index_name, id=cid)["_source"]
                diffs = _compare_docs(loc, rem)
            except Exception as exc:
                diffs = ["获取失败：{0}".format(_redact(str(exc))[:120])]
            consistency.append({"index": index_name, "chunk_id": cid, "diffs": diffs})
    print("CONSISTENCY_DONE", flush=True)

    cat_rows = []
    for row in remote.cat.indices(index="panai4_*", format="json", bytes="b"):
        cat_rows.append({
            "index": row["index"],
            "docs": row.get("docs.count"),
            "size": row.get("store.size"),
        })

    kg_after = _kg_rag_snapshot(remote)
    disk_after, _ = _disk_avail_bytes(remote)
    input_after = {j["input_name"]: os.path.getsize(j["input"]) for j in jobs}

    write_remote_report(report_path, {
        "preflight": preflight,
        "writes": writes,
        "progress": progress_rows,
        "total_seconds": total_seconds,
        "smoke": smoke,
        "consistency": consistency,
        "cat": cat_rows,
        "kg_before": kg_before,
        "kg_after": kg_after,
        "disk_before": disk_before,
        "disk_after": disk_after,
        "input_before": input_before,
        "input_after": input_after,
    })

    header_ok = all(item["matched"] >= 3 for item in smoke["header"]) if smoke["header"] else False
    outline66 = next((item["total"] for item in smoke["filters"] if item["name"] == "chunk_type=book_outline"), None)
    knn_ok = all(bool(item["hits"]) for item in smoke["knn"]) if smoke["knn"] else False
    # remote kNN score 可能不在 0~1，本步不卡死；只要求非空
    cross_ok = bool(smoke["cross"]["ok"])
    kg_ok = kg_before == kg_after
    cons_ok = all(not c["diffs"] for c in consistency) if consistency else False
    counts_ok = all(
        row["docs_count"] == row["input_n"] - len(row["filtered"]) for row in writes
    )
    inputs_ok = input_before == input_after

    ok = (
        counts_ok and header_ok and outline66 == 66 and knn_ok and cross_ok
        and kg_ok and cons_ok and inputs_ok
        and all(row["fail"] == 0 for row in writes)
    )
    if not kg_ok:
        print("KG_RAG_CHANGED", flush=True)
    print(
        "REMOTE_INDEX_DONE",
        "ok", ok,
        "header_ok", header_ok,
        "outline66", outline66,
        "knn_ok", knn_ok,
        "cons_ok", cons_ok,
        "kg_ok", kg_ok,
        flush=True,
    )
    return 0 if ok else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="panai4 建 ES 索引（本机或远程）")
    parser.add_argument("--target", choices=("local", "remote"), default="local")
    parser.add_argument("--index", default=None, help="单索引名")
    parser.add_argument("--input", default=None, help="单输入 JSONL")
    parser.add_argument("--out", default=DEFAULT_OUT, help="纲目JSON 目录")
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)
    if args.target == "remote":
        return main_remote(args)
    return main_local(args)


if __name__ == "__main__":
    sys.exit(main())
