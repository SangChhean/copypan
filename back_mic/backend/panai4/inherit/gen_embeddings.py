# -*- coding: utf-8 -*-
"""继承索引向量化：profile=kg_rag，输入=渲染后 text。

接口对齐 outline/gen_embeddings.py：
  --inputs / --concurrency / --trial

断点续跑（强制）：
  - 每 2000 条一片，片文件名含索引名与片序号
  - 每片算完立即落盘
  - 启动扫描输出目录，完整片直接跳过

用法（在 back_mic/backend 下）::

    # 试跑
    python -m panai4.inherit.gen_embeddings --trial --inputs ... --report ...

    # 全量（确认并发后）
    python -m panai4.inherit.gen_embeddings --inputs ... --concurrency 5 --out ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ENV_KEYS = ("OPENROUTER_API_KEY", "EMBEDDING_KG_MODEL", "EMBEDDING_KG_DIMS")
PRICE_PER_MILLION = 0.01
BATCH_SIZE = 50
SHARD_SIZE = 2000
RETRY_WAITS = (1, 2, 4, 8, 16)
TRIAL_TOTAL = 500
TRIAL_CONCURRENCIES = (3, 5, 8)
TRIAL_GAP_SECONDS = 10
DEFAULT_IN = r"G:\PanAI4.0专用\12490原文JSONL\rendered"
DEFAULT_OUT = r"G:\PanAI4.0专用\12490原文JSONL\vectors"


def _backend_env() -> str:
    here = Path(__file__).resolve()
    return str(here.parents[2] / ".env")


def _repo_docs() -> Path:
    return Path(__file__).resolve().parents[4] / "docs" / "panai4_es"


def _env_status(path: str) -> dict:
    status = {key: "缺失" for key in ENV_KEYS}
    if not os.path.isfile(path):
        return status
    found = {key: "" for key in ENV_KEYS}
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            name, value = raw.split("=", 1)
            name = name.strip()
            if name in found:
                found[name] = value.strip().strip('"').strip("'")
    for key in ENV_KEYS:
        status[key] = "存在" if found[key] else "缺失"
    return status


def _redact(text: str, secrets: list) -> str:
    out = text or ""
    for s in secrets:
        if s:
            out = out.replace(s, "***")
    return out


def _is_retryable(exc: Exception) -> tuple[bool, str]:
    text = str(exc).lower()
    if "429" in text or "rate" in text:
        return True, "429"
    if "timeout" in text or "timed out" in text:
        return True, "timeout"
    if "connection" in text or "network" in text:
        return True, "network"
    return False, type(exc).__name__


def _index_label(path: str) -> str:
    name = Path(path).stem  # kg-rag_life
    return name


def _shard_path(out_dir: Path, label: str, shard_i: int) -> Path:
    return out_dir / f"{label}_shard_{shard_i:05d}.jsonl"


def _meta_path(out_dir: Path, label: str, shard_i: int) -> Path:
    return out_dir / f"{label}_shard_{shard_i:05d}.meta.json"


def _load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def _count_jsonl(path: Path) -> int:
    if not path.is_file():
        return 0
    n = 0
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                n += 1
    return n


def _shard_complete(out_dir: Path, label: str, shard_i: int, expect_n: int) -> bool:
    meta = _meta_path(out_dir, label, shard_i)
    shard = _shard_path(out_dir, label, shard_i)
    if not meta.is_file() or not shard.is_file():
        return False
    try:
        info = json.loads(meta.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    if info.get("status") != "complete":
        return False
    if int(info.get("n", -1)) != expect_n:
        return False
    return _count_jsonl(shard) == expect_n


async def _embed(texts: list, secrets: list) -> dict:
    from kg_rag.embedding_adapter import get_embeddings

    started = time.perf_counter()
    try:
        vectors = await get_embeddings(texts, profile="kg_rag")
        elapsed = time.perf_counter() - started
        dims = [len(vec) if isinstance(vec, list) else None for vec in vectors]
        return {"ok": True, "vectors": vectors, "dims": dims, "seconds": elapsed, "error": None}
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        return {
            "ok": False,
            "vectors": [],
            "dims": [],
            "seconds": elapsed,
            "error": _redact(str(exc), secrets),
            "traceback": _redact(traceback.format_exc(), secrets),
            "retryable": _is_retryable(exc)[0],
            "kind": _is_retryable(exc)[1],
        }


async def _embed_with_retry(texts: list, secrets: list, retry_counts: Counter) -> dict:
    last = None
    for attempt in range(len(RETRY_WAITS) + 1):
        result = await _embed(texts, secrets)
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


async def _run_batches(
    records: list[dict],
    concurrency: int,
    secrets: list,
    retry_counts: Counter,
    expect_dim: int,
) -> dict:
    batches = [records[i : i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
    sem = asyncio.Semaphore(concurrency)
    failures = []
    bad_dims = []
    vector_rows = []
    batch_seconds = []
    lock = asyncio.Lock()

    async def one(index: int, chunk: list) -> None:
        texts = [rec.get("text") or "" for rec in chunk]
        async with sem:
            started = time.perf_counter()
            result = await _embed_with_retry(texts, secrets, retry_counts)
            elapsed = time.perf_counter() - started
        async with lock:
            batch_seconds.append(elapsed)
            if result["ok"]:
                for rec, vec, dim in zip(chunk, result["vectors"], result["dims"]):
                    row = dict(rec)
                    row["embedding"] = vec
                    row["dim"] = dim
                    vector_rows.append(row)
                    if dim != expect_dim:
                        bad_dims.append((rec.get("chunk_id"), dim))
            else:
                err = result.get("error") or ""
                kind = result.get("kind") or "unknown"
                for rec in chunk:
                    failures.append({
                        "chunk_id": rec.get("chunk_id"),
                        "kind": kind,
                        "error": err,
                    })
                print(
                    "BATCH_FAIL", "conc", concurrency, "batch", index,
                    "kind", kind, flush=True,
                )

    await asyncio.gather(*[one(i, b) for i, b in enumerate(batches)])
    ok = len(records) - len(failures)
    elapsed = sum(batch_seconds) if batch_seconds else 0.0
    per_sec = (ok / elapsed) if elapsed > 0 else 0.0
    return {
        "vector_rows": vector_rows,
        "failures": failures,
        "bad_dims": bad_dims,
        "ok": ok,
        "fail": len(failures),
        "per_sec": per_sec,
        "elapsed": elapsed,
        "retries": dict(retry_counts),
    }


def _sample_trial_records(inputs: list[str], total: int = TRIAL_TOTAL) -> list[dict]:
    """按各文件条数比例抽 total 条。"""
    sizes = []
    for path in inputs:
        n = _count_jsonl(Path(path))
        sizes.append((path, n))
    grand = sum(n for _, n in sizes) or 1
    quotas = []
    assigned = 0
    for i, (path, n) in enumerate(sizes):
        if i == len(sizes) - 1:
            q = total - assigned
        else:
            q = max(1, round(total * n / grand)) if n else 0
            assigned += q
        quotas.append((path, min(q, n)))

    rng = random.Random(20260930)
    picked = []
    for path, q in quotas:
        if q <= 0:
            continue
        rows = _load_jsonl(path)
        if len(rows) <= q:
            chosen = rows
        else:
            chosen = rng.sample(rows, q)
        for rec in chosen:
            rec = dict(rec)
            rec["_source_file"] = Path(path).name
            picked.append(rec)
    # trim/pad to total
    if len(picked) > total:
        picked = rng.sample(picked, total)
    return picked


async def _trial(args) -> int:
    env_file = _backend_env()
    status = _env_status(env_file)
    report_path = Path(args.report or (_repo_docs() / "inherit_embedding_trial.md"))
    inputs = list(args.inputs) if args.inputs else []
    if not inputs:
        print("NO_INPUTS", flush=True)
        return 2
    concurrencies = list(args.concurrency) if args.concurrency else list(TRIAL_CONCURRENCIES)

    lines = ["# 继承索引 embedding 并发试跑", ""]
    lines.append("embedding 输入 = 渲染后 `text`；profile=`kg_rag`（qwen3-embedding-8b / 1024）。")
    lines.append(f"试跑条数：{TRIAL_TOTAL}；并发：{concurrencies}")
    lines.append("")
    lines.append("## 环境")
    lines.append("")
    for key in ENV_KEYS:
        lines.append(f"- {key}：{status[key]}")
    lines.append("")

    if any(status[k] != "存在" for k in ENV_KEYS):
        lines.append("环境变量缺失，试跑停下。")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("ENV_MISSING", flush=True)
        return 2

    for path in inputs:
        if not os.path.isfile(path):
            print(f"MISSING {path}", flush=True)
            return 2
        n = _count_jsonl(Path(path))
        lines.append(f"- 输入 `{Path(path).name}`：{n:,} 条")
    lines.append("")

    load_dotenv(env_file)
    secrets = [os.environ.get("OPENROUTER_API_KEY", "")]
    from kg_rag.embedding_adapter import EMBEDDING_KG_DIMS, EMBEDDING_KG_MODEL

    expect_dim = int(EMBEDDING_KG_DIMS)
    lines.append(f"- 模型：`{EMBEDDING_KG_MODEL}`；期望维：{expect_dim}")
    lines.append("")

    records = _sample_trial_records(inputs, TRIAL_TOTAL)
    lines.append(f"实际抽样：{len(records)} 条")
    lines.append("")
    print(f"TRIAL_SAMPLE {len(records)}", flush=True)

    results = []
    for i, conc in enumerate(concurrencies):
        print(f"TRIAL_START conc={conc}", flush=True)
        retry_counts = Counter()
        started = time.perf_counter()
        out = await _run_batches(records, conc, secrets, retry_counts, expect_dim)
        wall = time.perf_counter() - started
        per_sec = (out["ok"] / wall) if wall > 0 else 0.0
        row = {
            "concurrency": conc,
            "ok": out["ok"],
            "fail": out["fail"],
            "per_sec": per_sec,
            "wall": wall,
            "retries": dict(retry_counts),
            "bad_dims": len(out["bad_dims"]),
        }
        results.append(row)
        print(
            f"TRIAL_DONE conc={conc} ok={out['ok']} fail={out['fail']} "
            f"per_sec={per_sec:.2f} wall={wall:.1f}s",
            flush=True,
        )
        lines.append(f"### 并发 {conc}")
        lines.append("")
        lines.append(f"- 成功：{out['ok']}；失败：{out['fail']}；非 {expect_dim} 维：{len(out['bad_dims'])}")
        lines.append(f"- 墙钟：{wall:.1f}s；速率：{per_sec:.2f} 条/秒")
        lines.append(f"- 重试：{dict(retry_counts) or '{}'}")
        lines.append("")
        if i < len(concurrencies) - 1:
            await asyncio.sleep(TRIAL_GAP_SECONDS)

    # pick fastest with zero fail preferred
    ranked = sorted(
        results,
        key=lambda r: (r["fail"] > 0, -r["per_sec"], r["concurrency"]),
    )
    best = ranked[0]
    lines.append("## 推荐")
    lines.append("")
    lines.append(
        f"最快档：并发 **{best['concurrency']}**（{best['per_sec']:.2f} 条/秒，"
        f"失败 {best['fail']}）。**等确认后再放全量。**"
    )
    lines.append("")
    lines.append("| 并发 | 条/秒 | 成功 | 失败 | 墙钟(s) |")
    lines.append("|---:|---:|---:|---:|---:|")
    for r in results:
        lines.append(
            f"| {r['concurrency']} | {r['per_sec']:.2f} | {r['ok']} | {r['fail']} | {r['wall']:.1f} |"
        )
    lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {report_path}", flush=True)
    print(
        f"TRIAL_BEST conc={best['concurrency']} per_sec={best['per_sec']:.2f}",
        flush=True,
    )
    return 0


async def _process_shard(
    records: list[dict],
    out_dir: Path,
    label: str,
    shard_i: int,
    concurrency: int,
    secrets: list,
    expect_dim: int,
) -> dict:
    expect_n = len(records)
    if _shard_complete(out_dir, label, shard_i, expect_n):
        print(f"SKIP_SHARD {label} {shard_i} n={expect_n}", flush=True)
        return {"skipped": True, "ok": expect_n, "fail": 0, "retries": {}, "elapsed": 0.0}

    # incomplete: remove partial
    shard = _shard_path(out_dir, label, shard_i)
    meta = _meta_path(out_dir, label, shard_i)
    if shard.exists():
        shard.unlink()
    if meta.exists():
        meta.unlink()

    retry_counts = Counter()
    started = time.perf_counter()
    out = await _run_batches(records, concurrency, secrets, retry_counts, expect_dim)
    wall = time.perf_counter() - started

    # write only successful rows; failures listed in meta
    with shard.open("w", encoding="utf-8", newline="\n") as fp:
        for row in out["vector_rows"]:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    meta_obj = {
        "status": "complete" if out["fail"] == 0 else "partial",
        "n": len(out["vector_rows"]),
        "expect": expect_n,
        "fail": out["fail"],
        "failures": out["failures"][:50],
        "retries": dict(retry_counts),
        "wall": wall,
        "per_sec": (len(out["vector_rows"]) / wall) if wall > 0 else 0.0,
    }
    meta.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"SHARD_DONE {label} {shard_i} ok={len(out['vector_rows'])} "
        f"fail={out['fail']} per_sec={meta_obj['per_sec']:.2f}",
        flush=True,
    )
    return {
        "skipped": False,
        "ok": len(out["vector_rows"]),
        "fail": out["fail"],
        "retries": dict(retry_counts),
        "elapsed": wall,
    }


async def _full(args) -> int:
    env_file = _backend_env()
    status = _env_status(env_file)
    if any(status[k] != "存在" for k in ENV_KEYS):
        print("ENV_MISSING", flush=True)
        return 2

    inputs = list(args.inputs) if args.inputs else []
    if not inputs:
        print("NO_INPUTS", flush=True)
        return 2

    concurrency = int(args.concurrency[0]) if args.concurrency else 5
    out_dir = Path(args.out or DEFAULT_OUT)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report or (_repo_docs() / "inherit_embedding_report.md"))

    load_dotenv(env_file)
    secrets = [os.environ.get("OPENROUTER_API_KEY", "")]
    from kg_rag.embedding_adapter import EMBEDDING_KG_DIMS

    expect_dim = int(EMBEDDING_KG_DIMS)

    summary = []
    grand_start = time.perf_counter()

    for path in inputs:
        label = _index_label(path)
        print(f"FULL_START {label}", flush=True)
        records = _load_jsonl(path)
        total = len(records)
        shards = [
            records[i : i + SHARD_SIZE]
            for i in range(0, total, SHARD_SIZE)
        ]
        ok = fail = 0
        retries = Counter()
        skipped = 0
        t0 = time.perf_counter()
        for si, chunk in enumerate(shards):
            result = await _process_shard(
                chunk, out_dir, label, si, concurrency, secrets, expect_dim,
            )
            ok += result["ok"]
            fail += result["fail"]
            if result["skipped"]:
                skipped += 1
            for k, v in (result.get("retries") or {}).items():
                retries[k] += v
        wall = time.perf_counter() - t0
        # merge count
        merged_n = 0
        for si in range(len(shards)):
            merged_n += _count_jsonl(_shard_path(out_dir, label, si))
        cover = merged_n / total if total else 0.0
        est_chars = sum(len(r.get("text") or "") for r in records)
        # rough token ≈ chars/1.5；OpenRouter embedding 按 token 计，这里用 chars 估
        est_tokens = est_chars / 1.5
        est_cost = est_tokens / 1_000_000 * PRICE_PER_MILLION
        summary.append({
            "label": label,
            "input": total,
            "embedded": merged_n,
            "cover": cover,
            "fail": fail,
            "retries": dict(retries),
            "skipped_shards": skipped,
            "shards": len(shards),
            "wall_min": wall / 60,
            "est_cost": est_cost,
        })
        print(
            f"FULL_DONE {label} embedded={merged_n}/{total} fail={fail} "
            f"min={wall/60:.1f}",
            flush=True,
        )

    lines = ["# 继承索引 embedding 全量报告", ""]
    lines.append(f"批大小 {BATCH_SIZE}；片大小 {SHARD_SIZE}；并发 {concurrency}。")
    lines.append(f"输出目录：`{out_dir}`")
    lines.append("")
    lines.append("| 索引 | 输入 | 已嵌入 | 覆盖率 | 失败 | 重试 | 片数(跳过) | 耗时(分) | 估费($) |")
    lines.append("|---|---:|---:|---:|---:|---|---:|---:|---:|")
    for s in summary:
        lines.append(
            f"| `{s['label']}` | {s['input']:,} | {s['embedded']:,} | "
            f"{s['cover']*100:.2f}% | {s['fail']} | {s['retries'] or '{}'} | "
            f"{s['shards']}({s['skipped_shards']}) | {s['wall_min']:.1f} | "
            f"{s['est_cost']:.4f} |"
        )
    lines.append("")
    lines.append(f"总墙钟：{(time.perf_counter()-grand_start)/60:.1f} 分钟。")
    lines.append("")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {report_path}", flush=True)
    print("FULL_ALL_DONE", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inherit embedding")
    parser.add_argument("--inputs", nargs="*", default=None)
    parser.add_argument("--concurrency", nargs="*", type=int, default=None)
    parser.add_argument("--trial", action="store_true")
    parser.add_argument("--out", default=None)
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)

    if args.trial:
        return asyncio.run(_trial(args))
    return asyncio.run(_full(args))


if __name__ == "__main__":
    sys.exit(main())
