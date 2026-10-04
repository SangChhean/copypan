# -*- coding: utf-8 -*-
"""将继承后的向量片写入本机/远程 ES（默认本机）。

目标索引：
  panai4_text_life / panai4_text_cwwl / panai4_text_cwwn /
  panai4_text_others / panai4_map_note

用法::

    python -m panai4.inherit.index_to_es --target local
    python -m panai4.inherit.index_to_es --target local --smoke-only
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
from elasticsearch.helpers import bulk

VEC_DIR = Path(r"G:\PanAI4.0专用\12490原文JSONL\vectors")
REPORT_DEFAULT = None
BULK_SIZE = 200
HEADER_SAMPLE = 10
HEADER_SEED = 20260930
SEP = "\u3000"

JOBS = [
    {
        "source": "kg-rag_life",
        "index": "panai4_text_life",
        "corpus": "life",
        "expect": 39463,
        "has_year": False,
        "has_section": True,
    },
    {
        "source": "kg-rag_cwwl",
        "index": "panai4_text_cwwl",
        "corpus": "cwwl",
        "expect": 178107,
        "has_year": True,
        "has_section": True,
    },
    {
        "source": "kg-rag_cwwn",
        "index": "panai4_text_cwwn",
        "corpus": "cwwn",
        "expect": 32032,
        "has_year": False,
        "has_section": True,
    },
    {
        "source": "kg-rag_others",
        "index": "panai4_text_others",
        "corpus": "others",
        "expect": 15481,
        "has_year": False,
        "has_section": True,
    },
    {
        "source": "kg-rag_map_note",
        "index": "panai4_map_note",
        "corpus": "map_note",
        "expect": 16052,
        "has_year": False,
        "has_section": False,
    },
]


def _backend_env() -> str:
    return str(Path(__file__).resolve().parents[2] / ".env")


def _repo_report() -> Path:
    return Path(__file__).resolve().parents[4] / "docs" / "panai4_es" / "inherit_indexing_report.md"


def make_local_es() -> Elasticsearch:
    load_dotenv(_backend_env())
    return Elasticsearch(
        hosts=[f"http://{os.getenv('ES_HOST', 'localhost')}:{os.getenv('ES_PORT', '9200')}"],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=120,
    )


def _text_with_keyword(name: str = "keyword") -> dict:
    return {
        "type": "text",
        "analyzer": "ik_max_word",
        "search_analyzer": "ik_smart",
        "fields": {name: {"type": "keyword"}},
    }


def build_mapping(*, has_year: bool, has_section: bool) -> dict:
    """字段规格：IK 主字段 + keyword 子字段供精确过滤。

    map_note：无 section_title（不进 mapping）。
    cwwl：额外 year。
    """
    props = {
        "chunk_id": {"type": "keyword"},
        "message_key": {"type": "keyword"},
        "source_index": {"type": "keyword"},
        "corpus": {"type": "keyword"},
        "text": {
            "type": "text",
            "analyzer": "ik_max_word",
            "search_analyzer": "ik_smart",
        },
        "text_vector": {
            "type": "dense_vector",
            "dims": 1024,
            "index": True,
            "similarity": "cosine",
            "index_options": {"type": "int8_hnsw"},
        },
        "book_title": _text_with_keyword(),
        "message_title": {
            "type": "text",
            "analyzer": "ik_max_word",
            "search_analyzer": "ik_smart",
        },
        "message_number": {"type": "integer"},
        # keyword 供精确过滤（与 book_title.keyword 对齐）
        "author": {"type": "keyword"},
        "paragraph_type": {"type": "keyword"},
        "source_zh": {"type": "text", "index": False},
        "source_en": {"type": "text", "index": False},
        "en": {"type": "text", "index": False},
        "original_ids": {"type": "keyword"},
        "chars": {"type": "integer"},
    }
    if has_section:
        props["section_title"] = {
            "type": "text",
            "analyzer": "ik_max_word",
            "search_analyzer": "ik_smart",
        }
    if has_year:
        props["year"] = {"type": "integer"}
    return {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {"properties": props},
    }


def iter_shard_rows(source_label: str, vec_dir: Path):
    """按片序号读 `{label}_shard_NNNNN.jsonl`。"""
    i = 0
    while True:
        path = vec_dir / f"{source_label}_shard_{i:05d}.jsonl"
        if not path.is_file():
            break
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                if line.strip():
                    yield json.loads(line)
        i += 1


def count_shards(source_label: str, vec_dir: Path) -> tuple[int, int]:
    n_files = 0
    n_docs = 0
    i = 0
    while True:
        path = vec_dir / f"{source_label}_shard_{i:05d}.jsonl"
        if not path.is_file():
            break
        n_files += 1
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                if line.strip():
                    n_docs += 1
        i += 1
    return n_files, n_docs


def to_es_doc(row: dict, field_names: set[str]) -> dict | None:
    emb = row.get("embedding") if row.get("embedding") is not None else row.get("text_vector")
    if not isinstance(emb, list) or not emb:
        return None
    src = {}
    for k in field_names:
        if k == "text_vector":
            continue
        if k not in row:
            continue
        # map_note 无 section_title：不补空字段
        if k == "section_title" and (row[k] is None or row[k] == ""):
            continue
        src[k] = row[k]
    src["text_vector"] = emb
    cid = row.get("chunk_id")
    if not cid:
        return None
    return {"_id": cid, "_source": src}


def index_one(es: Elasticsearch, job: dict, vec_dir: Path) -> dict:
    name = job["index"]
    label = job["source"]
    mapping = build_mapping(
        has_year=job["has_year"],
        has_section=job["has_section"],
    )
    fields = set(mapping["mappings"]["properties"].keys())

    n_files, n_docs = count_shards(label, vec_dir)
    print(f"INDEX_START {name} shards={n_files} docs={n_docs}", flush=True)
    if n_docs != job["expect"]:
        print(
            f"COUNT_WARN {name} embedded={n_docs} expect={job['expect']}",
            flush=True,
        )

    if es.indices.exists(index=name):
        es.indices.delete(index=name)
        print(f"DELETE_OLD {name}", flush=True)
    es.indices.create(index=name, body=deepcopy(mapping))
    print(f"CREATE {name}", flush=True)

    batch = []
    ok = fail = 0
    fail_ids = []
    started = time.perf_counter()

    def flush():
        nonlocal ok, fail, batch
        if not batch:
            return
        actions = []
        for item in batch:
            actions.append({
                "_op_type": "index",
                "_index": name,
                "_id": item["_id"],
                **item["_source"],
            })
        try:
            success, errors = bulk(es, actions, raise_on_error=False, request_timeout=120)
            ok += success
            if errors:
                for err in errors:
                    fail += 1
                    fail_ids.append(str(err)[:200])
        except Exception as exc:  # noqa: BLE001
            fail += len(batch)
            fail_ids.append(str(exc)[:200])
        batch = []

    for row in iter_shard_rows(label, vec_dir):
        doc = to_es_doc(row, fields)
        if doc is None:
            fail += 1
            fail_ids.append(row.get("chunk_id") or "missing")
            continue
        batch.append(doc)
        if len(batch) >= BULK_SIZE:
            flush()
            if ok and ok % 5000 == 0:
                print(f"PROGRESS {name} ok={ok}", flush=True)
    flush()
    es.indices.refresh(index=name)
    count = es.count(index=name)["count"]
    elapsed = time.perf_counter() - started
    print(
        f"INDEX_DONE {name} ok={ok} fail={fail} es_count={count} "
        f"sec={elapsed:.1f}",
        flush=True,
    )
    return {
        "index": name,
        "embedded": n_docs,
        "written_ok": ok,
        "fail": fail,
        "es_count": count,
        "expect": job["expect"],
        "fail_ids": fail_ids[:20],
        "elapsed": elapsed,
    }


def _first_line(text: str, n: int = 80) -> str:
    line = (text or "").split("\n", 1)[0]
    return line[:n]


def _embed_query(text: str) -> list[float]:
    import asyncio
    from kg_rag.embedding_adapter import get_embedding

    return asyncio.run(get_embedding(text, profile="kg_rag"))


def _expected_header(src: dict, *, has_section: bool) -> str:
    """与 render_text.build_header 对齐的简版校验期望。"""
    parts = []
    for key in ("book_title", "message_title", "section_title"):
        if key == "section_title" and not has_section:
            continue
        part = src.get(key)
        if part is None:
            continue
        part = str(part).strip()
        if not part:
            continue
        if parts and parts[-1] == part:
            continue
        parts.append(part)
    return SEP.join(parts)


def smoke(es: Elasticsearch, jobs: list[dict]) -> list[dict]:
    """每个索引 1 次 BM25 + 1 次 kNN（查询文本现算向量）。"""
    results = []
    queries = {
        "panai4_text_life": "基督作我们的生命",
        "panai4_text_cwwl": "神的经纶",
        "panai4_text_cwwn": "正常的基督徒生活",
        "panai4_text_others": "召会的建造",
        "panai4_map_note": "更美之约",
    }
    for job in jobs:
        name = job["index"]
        q = queries.get(name, "基督")
        entry = {"index": name, "query": q, "bm25": [], "knn": []}
        resp = es.search(
            index=name,
            size=3,
            query={"match": {"text": q}},
            _source=["chunk_id", "book_title", "text"],
        )
        for hit in resp["hits"]["hits"]:
            s = hit["_source"]
            entry["bm25"].append({
                "chunk_id": s.get("chunk_id"),
                "book_title": s.get("book_title"),
                "score": hit.get("_score"),
                "text0": _first_line(s.get("text") or ""),
            })
        try:
            knn_vec = _embed_query(q)
            knn_resp = es.search(
                index=name,
                size=3,
                knn={
                    "field": "text_vector",
                    "query_vector": knn_vec,
                    "k": 3,
                    "num_candidates": 50,
                },
                _source=["chunk_id", "book_title", "text"],
            )
            for hit in knn_resp["hits"]["hits"]:
                s = hit["_source"]
                entry["knn"].append({
                    "chunk_id": s.get("chunk_id"),
                    "book_title": s.get("book_title"),
                    "score": hit.get("_score"),
                    "text0": _first_line(s.get("text") or ""),
                })
        except Exception as exc:  # noqa: BLE001
            entry["knn_error"] = str(exc)[:200]
        results.append(entry)
        print(f"SMOKE {name} bm25={len(entry['bm25'])} knn={len(entry['knn'])}", flush=True)
    return results


def header_check(es: Elasticsearch, jobs: list[dict]) -> list[dict]:
    """每库随机抽 10 条，检查 text 第一行头部形态。"""
    out = []
    for job in jobs:
        name = job["index"]
        has_section = job["has_section"]
        resp = es.search(
            index=name,
            size=HEADER_SAMPLE,
            query={
                "function_score": {
                    "query": {"match_all": {}},
                    "random_score": {"seed": HEADER_SEED, "field": "_seq_no"},
                }
            },
            _source=[
                "chunk_id",
                "book_title",
                "message_title",
                "section_title",
                "text",
            ],
        )
        samples = []
        bad = []
        for hit in resp["hits"]["hits"]:
            s = hit["_source"]
            text = s.get("text") or ""
            line0 = text.split("\n", 1)[0] if text else ""
            book = str(s.get("book_title") or "").strip()
            msg = str(s.get("message_title") or "").strip()
            expect = _expected_header(s, has_section=has_section)
            # 重建的两段基线（书名　篇题）；字段值本身可含全角空格
            base_parts = []
            for p in (book, msg):
                if not p:
                    continue
                if base_parts and base_parts[-1] == p:
                    continue
                base_parts.append(p)
            base = SEP.join(base_parts)

            ok = True
            reason = ""
            if not line0:
                ok = False
                reason = "空首行"
            elif not book:
                ok = False
                reason = "无 book_title"
            elif not line0.startswith(book):
                ok = False
                reason = "首行不以书名开头"
            elif not has_section:
                # map_note：两段 = book　msg（字段内可含　）
                if line0 != base:
                    ok = False
                    reason = "map_note 首行应为「书名　篇题」"
            else:
                # 书名　篇题（　小节标题）：完整 expect，或截断后的 book　msg　sec…
                if line0 == expect or line0 == base:
                    ok = True
                elif expect and line0.startswith(base + SEP):
                    ok = True  # 带小节；可能相对 expect 截断
                elif base and line0.startswith(base):
                    ok = True
                else:
                    ok = False
                    reason = "与字段重建头部不符"

            item = {
                "chunk_id": s.get("chunk_id"),
                "line0": line0[:120],
                "expect": (expect or base)[:120],
                "ok": ok,
                "reason": reason,
            }
            samples.append(item)
            if not ok:
                bad.append(item)
        entry = {"index": name, "samples": samples, "bad": bad}
        out.append(entry)
        print(
            f"HEADER {name} sample={len(samples)} bad={len(bad)}",
            flush=True,
        )
    return out


def write_report(
    path: Path,
    index_results: list,
    smoke_results: list,
    header_results: list | None = None,
) -> None:
    lines = ["# 继承索引本机建索引报告", ""]
    lines.append("目标：本机 ES；未推服务器。")
    lines.append("")
    lines.append("## 条数对账")
    lines.append("")
    lines.append("| 索引 | 期望 | 向量片 | 写入成功 | ES count | 失败 | 对账 |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for r in index_results:
        ok = r["es_count"] == r["expect"] and r["fail"] == 0
        lines.append(
            f"| `{r['index']}` | {r['expect']:,} | {r['embedded']:,} | "
            f"{r['written_ok']:,} | {r['es_count']:,} | {r['fail']} | "
            f"{'✓' if ok else '✗'} |"
        )
    lines.append("")
    lines.append("## 冒烟（BM25 + kNN top3）")
    lines.append("")
    lines.append("kNN 用真实查询文本现算向量，不用文档自向量。")
    lines.append("")
    for s in smoke_results:
        lines.append(f"### `{s['index']}`　查询「{s['query']}」")
        lines.append("")
        lines.append("#### BM25")
        for i, h in enumerate(s["bm25"], 1):
            lines.append(
                f"{i}. `{h['chunk_id']}` | {h['book_title']} | score={h['score']}"
            )
            lines.append(f"   首行：{h['text0']}")
        lines.append("")
        lines.append("#### kNN")
        if s.get("knn_error"):
            lines.append(f"（错误）{s['knn_error']}")
        elif not s["knn"]:
            lines.append("（无）")
        for i, h in enumerate(s["knn"], 1):
            lines.append(
                f"{i}. `{h['chunk_id']}` | {h['book_title']} | score={h['score']}"
            )
            lines.append(f"   首行：{h['text0']}")
        lines.append("")

    if header_results is not None:
        lines.append("## 头部行自检（每库随机 10 条）")
        lines.append("")
        lines.append("形态：书名　篇题（　小节标题）；`map_note` 为两段。")
        lines.append("")
        for h in header_results:
            lines.append(f"### `{h['index']}`　不符 {len(h['bad'])}/{len(h['samples'])}")
            lines.append("")
            for i, s in enumerate(h["samples"], 1):
                mark = "✓" if s["ok"] else "✗"
                lines.append(
                    f"{i}. {mark} `{s['chunk_id']}`"
                    + (f" — {s['reason']}" if s["reason"] else "")
                )
                lines.append(f"   {s['line0']}")
            if h["bad"]:
                lines.append("")
                lines.append("不符清单：")
                for b in h["bad"]:
                    lines.append(f"- `{b['chunk_id']}`：{b['reason']} / `{b['line0']}`")
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {path}", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["local", "remote"], default="local")
    parser.add_argument("--vec-dir", default=str(VEC_DIR))
    parser.add_argument("--report", default=str(_repo_report()))
    parser.add_argument("--smoke-only", action="store_true")
    args = parser.parse_args(argv)

    if args.target != "local":
        print("REMOTE_NOT_IN_THIS_STEP 本步只建本机，推服务器等确认。", flush=True)
        return 2

    es = make_local_es()
    if not es.ping():
        print("ES_UNREACHABLE", flush=True)
        return 2

    vec_dir = Path(args.vec_dir)
    if args.smoke_only:
        smoke_results = smoke(es, JOBS)
        header_results = header_check(es, JOBS)
        write_report(Path(args.report), [], smoke_results, header_results)
        return 0

    results = []
    for job in JOBS:
        results.append(index_one(es, job, vec_dir))

    print("SMOKE_START", flush=True)
    smoke_results = smoke(es, JOBS)
    print("SMOKE_DONE", flush=True)
    print("HEADER_START", flush=True)
    header_results = header_check(es, JOBS)
    print("HEADER_DONE", flush=True)
    write_report(Path(args.report), results, smoke_results, header_results)

    all_ok = all(r["es_count"] == r["expect"] and r["fail"] == 0 for r in results)
    print(f"INHERIT_INDEX_DONE ok={all_ok}", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
