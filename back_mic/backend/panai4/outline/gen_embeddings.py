# -*- coding: utf-8 -*-
"""纲目 / 圣经 chunks → embedding。

--trial：并发试跑（默认 3/5/8 路 × 同一批 500 条），不生成正式 *_vec。
不加 --trial：全量生成 chunks_*_vec.json，支持断点续跑与 --concurrency。
embedding 输入 = chunk 的 text 本身（v0.2，不再拼 message_title）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import time
import traceback
from collections import Counter

from dotenv import load_dotenv

from . import config

ENV_KEYS = ("OPENROUTER_API_KEY", "EMBEDDING_KG_MODEL", "EMBEDDING_KG_DIMS")
# OpenRouter 模型页标价，2026-09-29：https://openrouter.ai/qwen/qwen3-embedding-8b
PRICE_PER_MILLION = 0.01
BATCH_SIZE = 50
QUOTA = (("<150", 16), ("150~800", 17), (">800", 17))
FILL_ORDER = ("150~800", "<150", ">800")
THRESHOLDS = (2000, 4000, 8000)
BATCH_PAUSE = 0.2
RETRY_WAITS = (1, 2, 4, 8, 16)
TRIAL_TOTAL = 500
TRIAL_CONCURRENCIES = (3, 5, 8)
TRIAL_GAP_SECONDS = 10
# 上一轮串行全量（A+B，无圣经）：66,951 条 / 264.5 分钟 / 约 11.8 秒每批
SERIAL_PREV_N = 66951
SERIAL_PREV_MINUTES = 264.5
SERIAL_PREV_SEC_PER_BATCH = 11.8
CHUNKING_REPORT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))),
    "docs", "panai4_es", "chunking_report.md",
)
DISK_MIN_BYTES = 3 * 1024 ** 3
TRIAL_DISK_MIN_BYTES = 5 * 1024 ** 3
BACKUP_DIR_NAME = "chunks_v01_20260929"
EXPECTED_COUNTS = {
    "chunks_12490.json": 55841,
    "chunks_feasts.json": 11110,
    "chunks_bible.json": 3691,
}


def _env_path() -> str:
    here = os.path.abspath(__file__)
    backend = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(backend, ".env")


def _env_status(path: str) -> dict:
    """只判断 .env 里三个变量是否有非空值，不返回值本身。"""
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


def _band(tokens: int) -> str:
    if tokens < 150:
        return "<150"
    if tokens <= 800:
        return "150~800"
    return ">800"


def _embed_input(record: dict) -> str:
    """v0.2：embedding 输入 = text 本身，不再拼 message_title。"""
    return record.get("text") or ""


def _batch_label(path: str) -> str:
    name = os.path.basename(path)
    if "12490" in name:
        return "12490"
    if "feasts" in name:
        return "feasts"
    if "bible" in name:
        return "bible"
    return os.path.splitext(name)[0]


def _load_chunks(path: str, batch: str | None = None) -> tuple:
    if batch is None:
        batch = _batch_label(path)
    records = []
    bands = {"<150": [], "150~800": [], ">800": []}
    over = Counter()
    est_tokens = 0
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            rec = {
                "chunk_id": obj["chunk_id"],
                "message_key": obj["message_key"],
                "message_title": obj.get("message_title") or "",
                "book_title": obj.get("book_title") or "",
                "text": obj.get("text") or "",
                "tokens": obj.get("tokens") or 0,
                "batch": batch,
                "source": os.path.basename(path),
            }
            records.append(rec)
            bands[_band(rec["tokens"])].append(rec)
            est_tokens += int(len(_embed_input(rec)) / 1.5)
            for threshold in THRESHOLDS:
                if rec["tokens"] > threshold:
                    over[threshold] += 1
    return records, bands, over, est_tokens


def _proportional_quotas(total: int, sizes: dict) -> dict:
    """按三份条数比例把 total 分到各文件；余数按最大余数法。"""
    keys = list(sizes.keys())
    grand = sum(sizes.values()) or 1
    raw = {k: total * sizes[k] / grand for k in keys}
    base = {k: int(raw[k]) for k in keys}
    remain = total - sum(base.values())
    order = sorted(keys, key=lambda k: (raw[k] - base[k], sizes[k]), reverse=True)
    for k in order:
        if remain <= 0:
            break
        base[k] += 1
        remain -= 1
    return base


def _sample_file_quota(rng: random.Random, bands: dict, quota: int) -> tuple:
    """文件内按 token 三档尽量抽到；配额按各档存量比例，不足从其他档补。"""
    if quota <= 0:
        return [], {"<150": 0, "150~800": 0, ">800": 0}
    names = ("<150", "150~800", ">800")
    sizes = {name: len(bands[name]) for name in names}
    avail = sum(sizes.values())
    if avail == 0:
        return [], {name: 0 for name in names}
    quota = min(quota, avail)
    # 先按存量比例分配
    alloc = _proportional_quotas(quota, {k: max(sizes[k], 1) for k in names if sizes[k] > 0})
    for name in names:
        alloc.setdefault(name, 0)
        alloc[name] = min(alloc[name], sizes[name])
    # 某档为空则其份额为 0，差额后面补
    shortfall = quota - sum(alloc.values())
    picked = []
    taken = {name: 0 for name in names}
    chosen = set()
    for name in names:
        count = alloc[name]
        if count <= 0:
            continue
        sample = rng.sample(bands[name], count)
        picked.extend(sample)
        taken[name] = count
        chosen.update(rec["chunk_id"] for rec in sample)
    if shortfall:
        for name in FILL_ORDER:
            if shortfall <= 0:
                break
            rest = [rec for rec in bands[name] if rec["chunk_id"] not in chosen]
            count = min(shortfall, len(rest))
            if not count:
                continue
            extra = rng.sample(rest, count)
            picked.extend(extra)
            chosen.update(rec["chunk_id"] for rec in extra)
            taken[name] += count
            shortfall -= count
    rng.shuffle(picked)
    return picked, taken


def _sample_band(rng: random.Random, bands: dict) -> tuple:
    picked = []
    taken = {}
    shortfall = 0
    for name, quota in QUOTA:
        pool = bands[name]
        count = min(quota, len(pool))
        picked.extend(rng.sample(pool, count) if count else [])
        taken[name] = count
        shortfall += quota - count
    if shortfall:
        chosen = {rec["chunk_id"] for rec in picked}
        for name in FILL_ORDER:
            if shortfall <= 0:
                break
            rest = [rec for rec in bands[name] if rec["chunk_id"] not in chosen]
            count = min(shortfall, len(rest))
            extra = rng.sample(rest, count) if count else []
            picked.extend(extra)
            chosen.update(rec["chunk_id"] for rec in extra)
            taken[name] = taken.get(name, 0) + count
            shortfall -= count
    return picked, taken


def _longest(records: list) -> dict:
    return max(records, key=lambda rec: (rec["tokens"], rec["chunk_id"]))


def _redact(text: str, secrets: list) -> str:
    out = text or ""
    for secret in secrets:
        if secret and len(secret) >= 8:
            out = out.replace(secret, "[REDACTED]")
    out = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[REDACTED]", out)
    out = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]{8,}", "Bearer [REDACTED]", out)
    return out


def _usage_dict(usage) -> dict | None:
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        data = usage.model_dump()
    elif hasattr(usage, "dict"):
        data = usage.dict()
    else:
        data = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
    clean = {}
    for key, value in data.items():
        if isinstance(value, (int, float, str, bool)) or value is None:
            clean[key] = value
    return clean or None


def _install_usage_spy(bucket: list) -> None:
    from openai.resources.embeddings import AsyncEmbeddings

    original = AsyncEmbeddings.create

    async def create(self, *args, **kwargs):
        response = await original(self, *args, **kwargs)
        bucket.append(_usage_dict(getattr(response, "usage", None)))
        return response

    AsyncEmbeddings.create = create


def _is_retryable(exc: Exception) -> tuple:
    """返回 (是否可重试, 错误类型标签)。"""
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
        return False, "http_{0}".format(status)
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return True, "timeout"
    if "connection" in text or "network" in text:
        return True, "network"
    return False, type(exc).__name__


async def _embed(texts: list, secrets: list) -> dict:
    from kg_rag.embedding_adapter import get_embeddings

    started = time.perf_counter()
    try:
        vectors = await get_embeddings(texts, profile="kg_rag")
        elapsed = time.perf_counter() - started
        dims = [len(vec) if isinstance(vec, list) else None for vec in vectors]
        return {"ok": True, "vectors": vectors, "dims": dims, "seconds": elapsed, "error": None}
    except Exception as exc:
        elapsed = time.perf_counter() - started
        detail = _redact(traceback.format_exc(), secrets)
        message = _redact(str(exc), secrets)
        retryable, kind = _is_retryable(exc)
        return {
            "ok": False,
            "vectors": [],
            "dims": [],
            "seconds": elapsed,
            "error": message,
            "traceback": detail,
            "retryable": retryable,
            "kind": kind,
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


async def _run_concurrent(
    records: list,
    concurrency: int,
    secrets: list,
    retry_counts: Counter,
) -> dict:
    """同一批 records，按 BATCH_SIZE 切批，最多 concurrency 路同时请求。"""
    batches = [records[i:i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
    sem = asyncio.Semaphore(concurrency)
    batch_seconds = []
    failures = []
    bad_dims = []
    vector_rows = []
    lock = asyncio.Lock()

    async def one(index: int, chunk: list) -> None:
        texts = [_embed_input(rec) for rec in chunk]
        async with sem:
            started = time.perf_counter()
            result = await _embed_with_retry(texts, secrets, retry_counts)
            elapsed = time.perf_counter() - started
        async with lock:
            batch_seconds.append(elapsed)
            if result["ok"]:
                for rec, vec, dim in zip(chunk, result["vectors"], result["dims"]):
                    vector_rows.append({
                        "chunk_id": rec["chunk_id"],
                        "message_key": rec["message_key"],
                        "batch": rec["batch"],
                        "source": rec.get("source"),
                        "dim": dim,
                        "embedding": vec,
                    })
                    if dim != 1024:
                        bad_dims.append((rec["chunk_id"], dim))
            else:
                err = result.get("error") or ""
                kind = result.get("kind") or "unknown"
                for rec in chunk:
                    failures.append({
                        "chunk_id": rec["chunk_id"],
                        "message_key": rec["message_key"],
                        "kind": kind,
                        "error": err,
                    })
                print(
                    "BATCH_FAIL", "conc", concurrency, "batch", index,
                    "kind", kind, flush=True,
                )

    wall_started = time.perf_counter()
    await asyncio.gather(*[one(i, chunk) for i, chunk in enumerate(batches)])
    wall = time.perf_counter() - wall_started
    n_batches = len(batches)
    avg_batch = (sum(batch_seconds) / n_batches) if n_batches else 0.0
    # 墙钟吞吐：整段 wall 内完成的条数
    per_sec = (len(records) / wall) if wall else 0.0
    return {
        "concurrency": concurrency,
        "n": len(records),
        "n_batches": n_batches,
        "wall_seconds": wall,
        "avg_batch_seconds": avg_batch,
        "per_sec": per_sec,
        "retry_counts": Counter(retry_counts),
        "failures": failures,
        "bad_dims": bad_dims,
        "vector_rows": vector_rows,
        "batch_seconds": list(batch_seconds),
    }


def _write_vectors(path: str, rows: list) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def _fmt_usage(usage: dict | None) -> str:
    if not usage:
        return "接口这次没有带回 usage。"
    parts = []
    for key in ("prompt_tokens", "total_tokens", "cost"):
        if key in usage and usage[key] is not None:
            parts.append("{0}={1}".format(key, usage[key]))
    rest = ["{0}={1}".format(key, usage[key]) for key in usage if key not in ("prompt_tokens", "total_tokens", "cost")]
    return "，".join(parts + rest) if parts or rest else "usage 为空对象。"


def _report(path: str, lines: list) -> None:
    text = "\n".join(lines).rstrip() + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)


def _title_repeat_check(text: str, message_title: str) -> bool:
    """粗检：篇题是否在输入里连续出现两次（旧拼接痕迹）。"""
    title = (message_title or "").strip()
    if not title:
        return False
    # 旧逻辑是 title + "\n" + text，而 text 第一行已含 title → 前两行都会有篇题
    lines = (text or "").splitlines()
    if len(lines) >= 2 and title in lines[0] and lines[1].strip() == title:
        return True
    if title and (text or "").count(title) >= 2:
        # 第一行含书名+篇题，正文偶尔再提篇题不算「拼接重复」；只抓开头两行同篇题
        return False
    return False


async def _trial(args) -> int:
    """并发试跑 v2：三份输入按比例抽 500 条，3/5/8 路各跑一遍。"""
    env_file = _env_path()
    status = _env_status(env_file)
    out_dir = args.out or config.DEFAULT_OUT_DIR
    report_path = args.report
    inputs = list(args.inputs) if args.inputs else [
        os.path.join(out_dir, "chunks_12490.json"),
        os.path.join(out_dir, "chunks_feasts.json"),
        os.path.join(out_dir, "chunks_bible.json"),
    ]
    concurrencies = list(args.concurrency) if args.concurrency else list(TRIAL_CONCURRENCIES)
    vector_path = os.path.join(out_dir, "trial_vectors_v2.json")
    backup_dir = os.path.join(out_dir, BACKUP_DIR_NAME)

    before_sizes = {}
    for path in inputs:
        before_sizes[path] = os.path.getsize(path) if os.path.isfile(path) else None

    lines = ["# embedding 并发试跑 v2", ""]
    lines.append("方案：`docs/panai4_es/chunks_es_plan.md` v0.2（6.2、6.3）。")
    lines.append("embedding 输入 = `text` 本身（不再拼接 `message_title`）。")
    lines.append("本步不生成 `chunks_*_vec.json`。")
    lines.append("")

    # ---- 第零步 ----
    lines.append("## 1. 第零步确认")
    lines.append("")

    counts = {}
    id_owners = {}
    collisions = []
    for path in inputs:
        name = os.path.basename(path)
        n = 0
        if not os.path.isfile(path):
            lines.append("- `{0}`：文件不存在。".format(name))
            counts[name] = -1
            continue
        with open(path, encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                obj = json.loads(line)
                n += 1
                cid = obj.get("chunk_id")
                if cid in id_owners:
                    collisions.append((cid, id_owners[cid], name))
                else:
                    id_owners[cid] = name
        counts[name] = n
        expect = EXPECTED_COUNTS.get(name)
        mark = "✓" if expect is not None and n == expect else "✗"
        lines.append("- `{0}`：{1} 条（期望 {2}）{3}".format(
            name, n, expect if expect is not None else "—", mark))

    lines.append("- 跨文件 chunk_id 碰撞：{0}".format(len(collisions)))
    for cid, left, right in collisions[:20]:
        lines.append("  - `{0}`：{1} / {2}".format(cid, left, right))

    free = _disk_free("C:\\")
    lines.append("- C:\\ 余量：{0:.2f} GB（须 ≥ 5 GB）{1}".format(
        free / 1024 ** 3, "✓" if free >= TRIAL_DISK_MIN_BYTES else "✗"))

    backup_ok = os.path.isdir(backup_dir)
    backup_files = []
    if backup_ok:
        backup_files = sorted(
            name for name in os.listdir(backup_dir)
            if name.endswith("_vec.json") or name.endswith(".json")
        )
    has_old_vec = any(name.endswith("_vec.json") for name in backup_files)
    lines.append("- `{0}` 旧文件：{1}（_vec 仍在：{2}）".format(
        BACKUP_DIR_NAME,
        "存在" if backup_ok else "缺失",
        "是" if has_old_vec else "否",
    ))
    if backup_files:
        for name in backup_files:
            lines.append("  - `{0}`".format(name))

    lines.append("- 环境变量（只写存在/缺失）：")
    for key in ENV_KEYS:
        lines.append("  - {0}：{1}".format(key, status[key]))
    lines.append("")

    count_ok = all(
        counts.get(name) == expect
        for name, expect in EXPECTED_COUNTS.items()
        if any(os.path.basename(p) == name for p in inputs)
    )
    # 若三份都在 inputs 里，必须全部对上
    if set(os.path.basename(p) for p in inputs) >= set(EXPECTED_COUNTS):
        count_ok = all(counts.get(name) == expect for name, expect in EXPECTED_COUNTS.items())

    if not count_ok or collisions or free < TRIAL_DISK_MIN_BYTES or not has_old_vec:
        lines.append("第零步未通过，试跑在调用接口前停下。")
        lines.append("")
        _report(report_path, lines)
        print("PREFLIGHT_FAIL", flush=True)
        return 2

    if any(status[key] != "存在" for key in ENV_KEYS):
        lines.append("有环境变量缺失，试跑在调用接口前停下。")
        lines.append("")
        _report(report_path, lines)
        print("ENV_MISSING", flush=True)
        return 2

    load_dotenv(env_file)
    secrets = [os.environ.get("OPENROUTER_API_KEY", "")]
    from kg_rag.embedding_adapter import EMBEDDING_KG_DIMS, EMBEDDING_KG_MODEL

    model_name = EMBEDDING_KG_MODEL
    expect_dim = int(EMBEDDING_KG_DIMS)

    # ---- 加载与抽样 ----
    loaded = {}
    sizes = {}
    for path in inputs:
        name = os.path.basename(path)
        records, bands, _over, _est = _load_chunks(path)
        loaded[name] = {"path": path, "records": records, "bands": bands}
        sizes[name] = len(records)

    quotas = _proportional_quotas(TRIAL_TOTAL, sizes)
    rng = random.Random(config.SAMPLE_SEED)
    sample = []
    sample_meta = {}
    for name in sizes:
        picked, taken = _sample_file_quota(rng, loaded[name]["bands"], quotas[name])
        sample.extend(picked)
        sample_meta[name] = {"quota": quotas[name], "taken": taken, "n": len(picked), "bands": {
            k: len(loaded[name]["bands"][k]) for k in ("<150", "150~800", ">800")
        }}
    rng.shuffle(sample)

    # embedding 输入样例：每份各 1 条
    samples_by_source = {}
    for rec in sample:
        src = rec["source"]
        if src not in samples_by_source:
            samples_by_source[src] = rec
        if len(samples_by_source) >= len(inputs):
            break
    # 若某份没抽到（不应发生），从该份全量取第一条
    for name, info in loaded.items():
        if name not in samples_by_source and info["records"]:
            samples_by_source[name] = info["records"][0]

    lines.append("## 2. embedding 输入样例")
    lines.append("")
    lines.append("实际送出的字符串 = chunk 的 `text` 本身。下列各取 1 条，打印前 120 字。")
    lines.append("")
    title_dup = []
    for name in sorted(samples_by_source.keys()):
        rec = samples_by_source[name]
        payload = _embed_input(rec)
        preview = payload[:120].replace("\n", "\\n")
        lines.append("### `{0}`".format(name))
        lines.append("")
        lines.append("- message_key：`{0}`".format(rec["message_key"]))
        lines.append("- message_title：`{0}`".format(rec.get("message_title") or ""))
        lines.append("- 送出前 120 字：")
        lines.append("")
        lines.append("```")
        lines.append(preview)
        lines.append("```")
        lines.append("")
        # 不得出现「篇题单独成行再出现一次」的旧拼接
        first = (payload.split("\n", 1)[0] if payload else "")
        title = rec.get("message_title") or ""
        book = rec.get("book_title") or ""
        # 第一行应含书名；篇题不应在第二行再次单独出现
        second = ""
        if "\n" in payload:
            rest = payload.split("\n", 1)[1]
            second = rest.split("\n", 1)[0]
        if title and second.strip() == title:
            title_dup.append(name)
            lines.append("**警告：第二行等于 message_title，疑似仍在拼接。**")
            lines.append("")
        elif title and payload.startswith(title + "\n"):
            title_dup.append(name)
            lines.append("**警告：输入以 message_title + 换行开头，疑似旧拼接。**")
            lines.append("")
        else:
            lines.append("确认：未发现篇题重复拼接；第一行 = `{0}`。".format(first[:80]))
            lines.append("")

    lines.append("## 3. 抽样方法与分布")
    lines.append("")
    lines.append("种子 `{0}`。先按三份条数比例把 {1} 条分到各文件（最大余数法），".format(
        config.SAMPLE_SEED, TRIAL_TOTAL))
    lines.append("再在文件内按 token 三档存量比例抽，某档不足则按 150~800 → <150 → >800 补齐。")
    lines.append("三档并发用**同一批** {0} 条。".format(len(sample)))
    lines.append("")
    lines.append("| 文件 | 总量 | 配额 | 实抽 | 档存量 <150 / 150~800 / >800 | 实抽分档 |")
    lines.append("|---|---:|---:|---:|---|---|")
    for name in sizes:
        meta = sample_meta[name]
        stock = "{0} / {1} / {2}".format(
            meta["bands"]["<150"], meta["bands"]["150~800"], meta["bands"][">800"])
        got = "{0} / {1} / {2}".format(
            meta["taken"]["<150"], meta["taken"]["150~800"], meta["taken"][">800"])
        lines.append("| `{0}` | {1} | {2} | {3} | {4} | {5} |".format(
            name, sizes[name], meta["quota"], meta["n"], stock, got))
    lines.append("| 合计 | {0} | {1} | {2} | — | — |".format(
        sum(sizes.values()), sum(m["quota"] for m in sample_meta.values()), len(sample)))
    lines.append("")
    band_total = Counter(_band(rec["tokens"]) for rec in sample)
    lines.append("样本整体 token 分档：<150={0}，150~800={1}，>800={2}。".format(
        band_total["<150"], band_total["150~800"], band_total[">800"]))
    lines.append("")
    lines.append("调用：模型 `{0}`，维度 {1}，批大小 {2}，并发档位 {3}。".format(
        model_name, expect_dim, BATCH_SIZE, "、".join(str(c) for c in concurrencies)))
    lines.append("档与档之间等待 {0} 秒。".format(TRIAL_GAP_SECONDS))
    lines.append("")

    usage_log = []
    _install_usage_spy(usage_log)

    run_results = []
    final_vectors = []
    for index, conc in enumerate(concurrencies):
        print("TRIAL_CONC_START", conc, "n", len(sample), flush=True)
        retry_counts = Counter()
        result = await _run_concurrent(sample, conc, secrets, retry_counts)
        run_results.append(result)
        final_vectors = result["vector_rows"]
        print(
            "TRIAL_CONC_DONE", conc,
            "wall", "{0:.1f}".format(result["wall_seconds"]),
            "per_sec", "{0:.2f}".format(result["per_sec"]),
            "fail", len(result["failures"]),
            "retry_429", result["retry_counts"].get("429", 0),
            flush=True,
        )
        if index + 1 < len(concurrencies):
            print("TRIAL_GAP", TRIAL_GAP_SECONDS, flush=True)
            await asyncio.sleep(TRIAL_GAP_SECONDS)

    _write_vectors(vector_path, final_vectors)
    vector_size = os.path.getsize(vector_path) if os.path.isfile(vector_path) else 0

    after_sizes = {}
    for path in inputs:
        after_sizes[path] = os.path.getsize(path) if os.path.isfile(path) else None

    lines.append("## 4. 三档并发实测")
    lines.append("")
    lines.append("| 并发 | 条数 | 批数 | 总耗时（秒） | 平均每批（秒） | 每秒条数 | 429 | 其他重试 | 失败条数 | 非1024 |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|")
    for result in run_results:
        other = {k: v for k, v in result["retry_counts"].items() if k != "429"}
        other_txt = "、".join("{0}={1}".format(k, v) for k, v in sorted(other.items())) or "0"
        lines.append(
            "| {0} | {1} | {2} | {3:.2f} | {4:.2f} | {5:.2f} | {6} | {7} | {8} | {9} |".format(
                result["concurrency"],
                result["n"],
                result["n_batches"],
                result["wall_seconds"],
                result["avg_batch_seconds"],
                result["per_sec"],
                result["retry_counts"].get("429", 0),
                other_txt,
                len(result["failures"]),
                len(result["bad_dims"]),
            )
        )
    lines.append("")
    for result in run_results:
        if result["failures"]:
            lines.append("### 并发 {0} 失败原文".format(result["concurrency"]))
            lines.append("")
            for row in result["failures"][:10]:
                lines.append("- `{0}`（{1}）：{2}".format(
                    row["message_key"], row["kind"], _redact(row["error"], secrets)[:300]))
            lines.append("")
        if result["bad_dims"]:
            lines.append("### 并发 {0} 非 1024 维".format(result["concurrency"]))
            lines.append("")
            for cid, dim in result["bad_dims"]:
                lines.append("- `{0}`：{1}".format(cid, dim))
            lines.append("")

    full_n = sum(sizes.values())
    lines.append("## 5. 全量预估对照")
    lines.append("")
    lines.append("全量合计 {0} 条（本步三份）。上一轮串行实测：{1} 条 / {2} 分钟 / {3} 秒每批（仅 A+B）。".format(
        full_n, SERIAL_PREV_N, SERIAL_PREV_MINUTES, SERIAL_PREV_SEC_PER_BATCH))
    lines.append("")
    lines.append("| 方案 | 每秒条数 | 预估 {0} 条耗时（分钟） | 相对串行加速 |".format(full_n))
    lines.append("|---|---:|---:|---:|")
    serial_per_sec = SERIAL_PREV_N / (SERIAL_PREV_MINUTES * 60) if SERIAL_PREV_MINUTES else 0
    serial_eta = (full_n / serial_per_sec / 60) if serial_per_sec else 0
    lines.append("| 上一轮串行（实测折算） | {0:.2f} | {1:.1f} | 1.0× |".format(serial_per_sec, serial_eta))
    for result in run_results:
        eta = (full_n / result["per_sec"] / 60) if result["per_sec"] else 0
        speedup = (serial_eta / eta) if eta else 0
        lines.append("| 并发 {0}（本试跑） | {1:.2f} | {2:.1f} | {3:.1f}× |".format(
            result["concurrency"], result["per_sec"], eta, speedup))
    lines.append("")

    # 结论：在无明显限流（429=0 或很少）下最快的
    lines.append("## 6. 结论")
    lines.append("")
    candidates = []
    for result in run_results:
        n429 = result["retry_counts"].get("429", 0)
        fail = len(result["failures"])
        candidates.append((result["concurrency"], result["per_sec"], n429, fail, result))
    # 优先：失败=0 且 429 不明显（=0）；其中最快；若都有 429，取 429 最少且最快
    clean = [c for c in candidates if c[3] == 0 and c[2] == 0]
    if not clean:
        clean = [c for c in candidates if c[3] == 0]
    if not clean:
        clean = list(candidates)
    best = max(clean, key=lambda c: c[1])
    best_eta = (full_n / best[1] / 60) if best[1] else 0
    lines.append(
        "在不触发明显限流（本试跑该档 429={0}、失败={1}）的前提下，**并发 {2} 最快**"
        "（{3:.2f} 条/秒），折算全量 {4} 条约 **{5:.1f} 分钟**。".format(
            best[2], best[3], best[0], best[1], full_n, best_eta)
    )
    if title_dup:
        lines.append("")
        lines.append("输入样例发现篇题重复拼接的文件：{0}。须修好后再跑全量。".format("、".join(title_dup)))
    lines.append("")

    lines.append("## 7. trial_vectors_v2.json")
    lines.append("")
    lines.append("- 条数：{0}（来自最后一档并发 {1} 的成功向量）".format(
        len(final_vectors), concurrencies[-1] if concurrencies else "—"))
    lines.append("- 字节：{0}".format(vector_size))
    lines.append("")

    lines.append("## 8. 输入文件未改动")
    lines.append("")
    lines.append("| 文件 | 试跑前 | 试跑后 |")
    lines.append("|---|---:|---:|")
    same = True
    for path in inputs:
        name = os.path.basename(path)
        lines.append("| `{0}` | {1} | {2} |".format(name, before_sizes[path], after_sizes[path]))
        if before_sizes[path] != after_sizes[path]:
            same = False
    lines.append("")
    lines.append("三份输入字节数在本步前后一致。" if same else "输入文件字节数发生变化。")
    lines.append("")

    # 确认未生成正式 vec
    stray = []
    for name in ("chunks_12490_vec.json", "chunks_feasts_vec.json", "chunks_bible_vec.json"):
        path = os.path.join(out_dir, name)
        if os.path.isfile(path):
            # 根目录若存在正式 vec，本步不应新建；若本步前就没有而现在有，则违规
            stray.append(name)
    lines.append("根目录 `chunks_*_vec.json`：{0}。".format(
        "存在（须确认非本步新建；本步只写 trial_vectors_v2.json）" if stray else "未生成（符合预期）"))
    lines.append("")

    _report(report_path, lines)
    with open(report_path, encoding="utf-8") as fp:
        body = fp.read()
    cleaned = _redact(body, secrets)
    if cleaned != body:
        with open(report_path, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(cleaned)

    all_dims_ok = all(not r["bad_dims"] for r in run_results)
    all_fail_ok = all(not r["failures"] for r in run_results)
    ok = (
        same and all_dims_ok and all_fail_ok and not title_dup
        and len(sample) == TRIAL_TOTAL
        and len(final_vectors) == TRIAL_TOTAL
    )
    print(
        "TRIAL_V2_DONE",
        "sample", len(sample),
        "vectors", len(final_vectors),
        "best_conc", best[0],
        "ok", ok,
        flush=True,
    )
    return 0 if ok else 2


def _read_done_ids(path: str) -> set:
    done = set()
    if not os.path.isfile(path):
        return done
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            emb = obj.get("embedding")
            if isinstance(emb, list) and emb:
                done.add(obj.get("chunk_id"))
    return done


def _parse_chunking_checks(report_path: str) -> dict:
    """从 chunking_report.md 复述三个硬指标。报告里没有就明说。"""
    result = {
        "zero_units": None,
        "collisions": None,
        "notes_units": None,
        "missing": [],
        "ok": False,
    }
    if not os.path.isfile(report_path):
        result["missing"].append("找不到 chunking_report.md")
        return result
    text = open(report_path, encoding="utf-8").read()
    m_zero = re.search(r"产出 0 个单位的篇：(\d+)", text)
    m_col = re.search(r"chunk_id 碰撞：(\d+)", text)
    m_notes = re.search(
        r"### 李常受弟兄个人笔记\s*\n(?:- .*\n)*?- 单位数：(\d+)",
        text,
    )
    if m_zero:
        result["zero_units"] = int(m_zero.group(1))
    else:
        result["missing"].append("产出 0 个单位的篇数")
    if m_col:
        result["collisions"] = int(m_col.group(1))
    else:
        result["missing"].append("chunk_id 碰撞数")
    if m_notes:
        result["notes_units"] = int(m_notes.group(1))
    else:
        result["missing"].append("《李常受弟兄个人笔记》单位数")
    result["ok"] = (
        result["zero_units"] == 0
        and result["collisions"] == 0
        and result["notes_units"] is not None
        and 60 <= result["notes_units"] <= 75
        and not result["missing"]
    )
    return result


def _disk_free(path: str) -> int:
    import shutil

    return shutil.disk_usage(path).free


def _preflight(out_dir: str) -> dict:
    checks = _parse_chunking_checks(CHUNKING_REPORT)
    free = _disk_free(out_dir)
    overrides = len(config.BOOK_TITLE_OVERRIDES)
    unique = len(set(config.BOOK_TITLE_OVERRIDES.values()))
    return {
        "checks": checks,
        "free_bytes": free,
        "free_ok": free >= DISK_MIN_BYTES,
        "overrides": overrides,
        "override_unique": unique,
        "ok": checks["ok"] and free >= DISK_MIN_BYTES,
    }


async def _full(args) -> int:
    """三份全量 embedding：并发、断点续跑、边算边追加、吞吐进度。"""
    env_file = _env_path()
    status = _env_status(env_file)
    out_dir = args.out or config.DEFAULT_OUT_DIR
    report_path = args.report
    # 默认顺序：bible → feasts → 12490（小的先跑）
    default_names = ("chunks_bible.json", "chunks_feasts.json", "chunks_12490.json")
    if args.inputs:
        input_paths = list(args.inputs)
    else:
        input_paths = [os.path.join(out_dir, name) for name in default_names]
    # --concurrency 在全量取第一个整数；默认 5
    if args.concurrency:
        concurrency = int(args.concurrency[0])
    else:
        concurrency = 5

    jobs = []
    for src in input_paths:
        name = os.path.basename(src)
        stem = name[:-5] if name.endswith(".json") else name
        if not stem.endswith("_vec"):
            dst_name = stem + "_vec.json"
        else:
            dst_name = name
        jobs.append({
            "label": _batch_label(src),
            "name": name,
            "src": src,
            "dst": os.path.join(out_dir, dst_name),
        })

    before = {job["name"]: (os.path.getsize(job["src"]) if os.path.isfile(job["src"]) else None) for job in jobs}
    backup_dir = os.path.join(out_dir, BACKUP_DIR_NAME)

    lines = ["# embedding 全量报告 v2", ""]
    lines.append("方案：`docs/panai4_es/chunks_es_plan.md` v0.2（6.2、6.3）。")
    lines.append("试跑结论：`docs/panai4_es/embedding_trial_v2.md`（并发 5）。")
    lines.append("embedding 输入 = `text` 本身；批大小 {0}；并发 {1}。".format(BATCH_SIZE, concurrency))
    lines.append("")

    lines.append("## 1. 开跑前确认")
    lines.append("")

    counts = {}
    id_owners = {}
    collisions = []
    for job in jobs:
        n = 0
        if not os.path.isfile(job["src"]):
            lines.append("- `{0}`：不存在。".format(job["name"]))
            counts[job["label"]] = -1
            continue
        with open(job["src"], encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                obj = json.loads(line)
                n += 1
                cid = obj.get("chunk_id")
                if cid in id_owners:
                    collisions.append((cid, id_owners[cid], job["name"]))
                else:
                    id_owners[cid] = job["name"]
        counts[job["label"]] = n
        expect = EXPECTED_COUNTS.get(job["name"])
        mark = "✓" if expect is not None and n == expect else ("—" if expect is None else "✗")
        lines.append("- `{0}`：{1} 条（期望 {2}）{3}".format(
            job["name"], n, expect if expect is not None else "—", mark))
    lines.append("- 跨文件 chunk_id 碰撞：{0}".format(len(collisions)))
    for cid, left, right in collisions[:20]:
        lines.append("  - `{0}`：{1} / {2}".format(cid, left, right))

    free = _disk_free("C:\\")
    lines.append("- C:\\ 余量：{0:.2f} GB".format(free / 1024 ** 3))
    lines.append("- 环境变量（只写存在/缺失）：")
    for key in ENV_KEYS:
        lines.append("  - {0}：{1}".format(key, status[key]))
    lines.append("")

    expect_ok = all(
        EXPECTED_COUNTS.get(job["name"]) is None or counts.get(job["label"]) == EXPECTED_COUNTS[job["name"]]
        for job in jobs
    )
    if not expect_ok or collisions or free < DISK_MIN_BYTES:
        lines.append("开跑前确认未通过，全量在调用接口前停下。")
        lines.append("")
        _report(report_path, lines)
        print("PREFLIGHT_FAIL", flush=True)
        return 2
    if any(status[key] != "存在" for key in ENV_KEYS):
        lines.append("有环境变量缺失，全量在调用接口前停下。")
        lines.append("")
        _report(report_path, lines)
        print("ENV_MISSING", flush=True)
        return 2

    load_dotenv(env_file)
    secrets = [os.environ.get("OPENROUTER_API_KEY", "")]
    from kg_rag.embedding_adapter import EMBEDDING_KG_DIMS, EMBEDDING_KG_MODEL

    model_name = EMBEDDING_KG_MODEL
    expect_dim = int(EMBEDDING_KG_DIMS)

    usage_log = []
    _install_usage_spy(usage_log)
    retry_counts = Counter()
    failures = []
    skipped = {job["label"]: 0 for job in jobs}
    newly = {job["label"]: 0 for job in jobs}
    totals = {job["label"]: counts[job["label"]] for job in jobs}
    progress_rows = []  # 每 50 批一条吞吐记录

    done_maps = {job["label"]: _read_done_ids(job["dst"]) for job in jobs}
    total_all = sum(totals.values())
    already_done = sum(len(v) for v in done_maps.values())

    started = time.perf_counter()
    batch_index = 0  # 已完成批次数（全局）
    finished_new = 0
    window_start = started
    window_new = 0
    write_lock = asyncio.Lock()
    state_lock = asyncio.Lock()

    async def process_file(job: dict) -> None:
        nonlocal batch_index, finished_new, window_start, window_new
        label = job["label"]
        done = done_maps[label]
        pending = []
        with open(job["src"], encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                obj = json.loads(line)
                cid = obj["chunk_id"]
                if cid in done:
                    skipped[label] += 1
                    continue
                pending.append({
                    "chunk_id": cid,
                    "message_key": obj.get("message_key"),
                    "chunk_index": obj.get("chunk_index"),
                    "text": obj.get("text") or "",
                    "raw": obj,
                })

        batches = [pending[i:i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
        if not batches:
            print("FILE_SKIP_ALL", label, "done", len(done), flush=True)
            return

        print(
            "FILE_START", label,
            "pending", len(pending),
            "batches", len(batches),
            "skip", skipped[label],
            "conc", concurrency,
            flush=True,
        )
        sem = asyncio.Semaphore(concurrency)

        async def one_batch(chunk: list) -> None:
            nonlocal batch_index, finished_new, window_start, window_new
            texts = [_embed_input(item) for item in chunk]
            async with sem:
                result = await _embed_with_retry(texts, secrets, retry_counts)
            async with write_lock:
                if result["ok"]:
                    with open(job["dst"], "a", encoding="utf-8", newline="\n") as out_fp:
                        for rec, vec, dim in zip(chunk, result["vectors"], result["dims"]):
                            row = dict(rec["raw"])
                            row["embedding"] = vec
                            out_fp.write(json.dumps(row, ensure_ascii=False) + "\n")
                            done.add(rec["chunk_id"])
                            newly[label] += 1
                            if dim != expect_dim:
                                failures.append({
                                    "message_key": rec["message_key"],
                                    "chunk_index": rec["chunk_index"],
                                    "error": "维度不是 {0}，而是 {1}".format(expect_dim, dim),
                                })
                else:
                    err = (result.get("error") or "")[:200]
                    for rec in chunk:
                        failures.append({
                            "message_key": rec["message_key"],
                            "chunk_index": rec["chunk_index"],
                            "error": err,
                        })
                    print("BATCH_FAIL", label, "n", len(chunk), "kind", result.get("kind"), flush=True)

            async with state_lock:
                batch_index += 1
                if result["ok"]:
                    finished_new += len(chunk)
                    window_new += len(chunk)
                elapsed = time.perf_counter() - started
                done_all = sum(len(v) for v in done_maps.values())
                avg_rate = finished_new / elapsed if elapsed else 0.0
                if batch_index % 50 == 0:
                    now = time.perf_counter()
                    window_elapsed = now - window_start
                    instant = (window_new / window_elapsed) if window_elapsed > 0 else 0.0
                    remain = max(total_all - done_all, 0)
                    eta = (remain / instant) if instant > 0 else 0.0
                    row = {
                        "file": label,
                        "batches": batch_index,
                        "done": done_all,
                        "pct": 100.0 * done_all / total_all if total_all else 0.0,
                        "elapsed_min": elapsed / 60,
                        "instant": instant,
                        "avg": avg_rate,
                        "eta_min": eta / 60,
                        "window_new": window_new,
                    }
                    progress_rows.append(row)
                    print(
                        "PROGRESS",
                        "file", label,
                        "done", done_all,
                        "pct", "{0:.1f}%".format(row["pct"]),
                        "elapsed_min", "{0:.1f}".format(row["elapsed_min"]),
                        "instant", "{0:.2f}/s".format(instant),
                        "avg", "{0:.2f}/s".format(avg_rate),
                        "eta_min", "{0:.1f}".format(row["eta_min"]),
                        flush=True,
                    )
                    window_start = now
                    window_new = 0

        await asyncio.gather(*[one_batch(chunk) for chunk in batches])
        print(
            "FILE_DONE", label,
            "new", newly[label],
            "skip", skipped[label],
            "fail_so_far", len(failures),
            flush=True,
        )

    print(
        "FULL_V2_START",
        "files", [j["label"] for j in jobs],
        "conc", concurrency,
        "already_done", already_done,
        "total", total_all,
        flush=True,
    )
    for job in jobs:
        await process_file(job)
    elapsed = time.perf_counter() - started

    # ---- 覆盖 / 维度 / 抽样 ----
    coverage = {}
    bad_dims = []
    samples_by_label = {job["label"]: [] for job in jobs}
    vec_counts = {}
    vec_sizes = {}
    all_vec_ids = {}
    vec_collisions = []

    for job in jobs:
        label = job["label"]
        have = {}
        if os.path.isfile(job["dst"]):
            vec_sizes[label] = os.path.getsize(job["dst"])
            with open(job["dst"], encoding="utf-8") as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    emb = obj.get("embedding")
                    cid = obj.get("chunk_id")
                    if isinstance(emb, list) and emb:
                        have[cid] = True
                        if cid in all_vec_ids:
                            vec_collisions.append((cid, all_vec_ids[cid], job["name"]))
                        else:
                            all_vec_ids[cid] = job["name"]
                        if len(emb) != 1024:
                            bad_dims.append({
                                "message_key": obj.get("message_key"),
                                "chunk_index": obj.get("chunk_index"),
                                "dim": len(emb),
                            })
                        samples_by_label[label].append(obj)
        else:
            vec_sizes[label] = 0
        vec_counts[label] = len(have)
        missing = []
        with open(job["src"], encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj["chunk_id"] not in have:
                    missing.append({
                        "message_key": obj.get("message_key"),
                        "chunk_index": obj.get("chunk_index"),
                    })
        coverage[label] = {
            "have": len(have),
            "total": totals[label],
            "missing": missing,
        }

    prompt_tokens = 0
    for item in usage_log:
        if item and item.get("prompt_tokens"):
            prompt_tokens += int(item["prompt_tokens"])
    cost = prompt_tokens / 1_000_000 * PRICE_PER_MILLION

    rng = random.Random(config.SAMPLE_SEED)
    sample_rows = []
    for job in jobs:
        pool = samples_by_label[job["label"]]
        if not pool:
            continue
        sample_rows.extend(rng.sample(pool, min(2, len(pool))))

    after = {job["name"]: os.path.getsize(job["src"]) for job in jobs}
    fail_by_label = Counter()
    for row in failures:
        mk = str(row.get("message_key") or "")
        if mk.startswith("bible/") or "/bible" in mk or mk.startswith("bible"):
            fail_by_label["bible"] += 1
        elif mk.startswith("gmfeasts"):
            fail_by_label["feasts"] += 1
        elif mk.startswith("gm12490"):
            fail_by_label["12490"] += 1
        else:
            # 按 message_key 前缀猜不中时记到 unknown，报告里仍有总失败数
            fail_by_label["other"] += 1

    # 更稳：用 jobs 顺序，失败清单本身已有明细；表内按 label 统计用 failures 关联困难
    # 直接按失败条的 message_key 匹配各文件前缀
    def _fail_count(label: str) -> int:
        if label == "bible":
            return sum(1 for f in failures if str(f.get("message_key") or "").startswith("bible/"))
        if label == "feasts":
            return sum(1 for f in failures if str(f.get("message_key") or "").startswith("gmfeasts"))
        if label == "12490":
            return sum(1 for f in failures if str(f.get("message_key") or "").startswith("gm12490"))
        return 0

    lines.append("## 2. 调用方式")
    lines.append("")
    lines.append("- 模型：`{0}`".format(model_name))
    lines.append("- 适配层：`kg_rag/embedding_adapter.py`，`profile=\"kg_rag\"`")
    lines.append("- 请求维度：{0}".format(expect_dim))
    lines.append("- 批大小：{0}；并发：{1}".format(BATCH_SIZE, concurrency))
    lines.append("- 重试：仅 429 / 5xx / 超时 / 网络错误；等待 {0} 秒，最多 {1} 次".format(
        "、".join(str(x) for x in RETRY_WAITS), len(RETRY_WAITS)))
    lines.append("- embedding 输入：`text` 本身（v0.2）。")
    lines.append("- 执行顺序：{0}".format(" → ".join(j["label"] for j in jobs)))
    lines.append("")

    lines.append("## 3. 跳过 / 新算 / 失败")
    lines.append("")
    lines.append("| 文件 | 跳过 | 新算 | 失败 |")
    lines.append("|---|---:|---:|---:|")
    for job in jobs:
        label = job["label"]
        lines.append("| `{0}` | {1} | {2} | {3} |".format(
            job["name"], skipped[label], newly[label], _fail_count(label)))
    lines.append("| 合计 | {0} | {1} | {2} |".format(
        sum(skipped.values()), sum(newly.values()), len(failures)))
    lines.append("")

    lines.append("## 4. 覆盖率")
    lines.append("")
    all_covered = True
    for job in jobs:
        label = job["label"]
        have = coverage[label]["have"]
        total = coverage[label]["total"]
        pct = (100.0 * have / total) if total else 0
        lines.append("- `{0}`：{1} / {2}（{3:.1f}%）".format(job["name"], have, total, pct))
        if have != total:
            all_covered = False
            for miss in coverage[label]["missing"]:
                lines.append("  - 缺失 `{0}` chunk_index={1}".format(
                    miss["message_key"], miss["chunk_index"]))
    lines.append("")
    if not all_covered:
        lines.append("覆盖率未到 100%，报告在此停下，不判定可忽略。")
        lines.append("")

    lines.append("## 5. 维度校验")
    lines.append("")
    lines.append("非 1024 维：{0}".format(len(bad_dims)))
    for row in bad_dims:
        lines.append("- `{0}` chunk_index={1} dim={2}".format(
            row["message_key"], row["chunk_index"], row["dim"]))
    lines.append("")

    lines.append("## 6. 失败清单")
    lines.append("")
    lines.append("共 {0} 条。".format(len(failures)))
    for row in failures:
        lines.append("- `{0}` chunk_index={1}：{2}".format(
            row["message_key"], row["chunk_index"], _redact(row["error"], secrets)))
    lines.append("")

    lines.append("## 7. 吞吐曲线")
    lines.append("")
    lines.append("每完成 50 批（约 2,500 条）记录一次即时吞吐。")
    lines.append("")
    if progress_rows:
        lines.append("| # | 文件 | 累计批 | 已完成条数 | 占比 | 已用时(分) | 即时条/秒 | 累计平均条/秒 | 剩余预估(分) |")
        lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|")
        for index, row in enumerate(progress_rows, 1):
            lines.append(
                "| {0} | {1} | {2} | {3} | {4:.1f}% | {5:.1f} | {6:.2f} | {7:.2f} | {8:.1f} |".format(
                    index, row["file"], row["batches"], row["done"], row["pct"],
                    row["elapsed_min"], row["instant"], row["avg"], row["eta_min"],
                )
            )
        lines.append("")
        instants = [row["instant"] for row in progress_rows]
        first = sum(instants[: max(1, len(instants) // 3)]) / max(1, len(instants) // 3)
        mid_slice = instants[len(instants) // 3: 2 * len(instants) // 3] or instants
        mid = sum(mid_slice) / len(mid_slice)
        last_slice = instants[2 * len(instants) // 3:] or instants
        last = sum(last_slice) / len(last_slice)
        peak = max(instants)
        trough = min(instants)
        lines.append(
            "首/中/尾三段即时吞吐均值：{0:.2f} / {1:.2f} / {2:.2f} 条/秒；"
            "峰值 {3:.2f}，谷值 {4:.2f}。".format(
                first, mid, last, peak, trough)
        )
        # 用首中尾趋势判断衰减，避免单窗谷值误判
        if last >= first * 0.85 and mid >= first * 0.7:
            lines.append(
                "全程未见趋势性衰减（尾段不低于首段的 85%），"
                "也明显高于上一轮串行末段（约 4.2 条/秒）。"
            )
        elif last >= 4.2:
            lines.append(
                "相对首段有所回落，但仍高于上一轮串行末段（约 4.2 条/秒）。"
                "谷值 {0:.2f}，峰值 {1:.2f}。".format(trough, peak)
            )
        else:
            lines.append(
                "衰减明显，接近或低于上一轮串行末段水平，后续须关注。"
                "谷值 {0:.2f}，峰值 {1:.2f}。".format(trough, peak)
            )
    else:
        lines.append("新算不足 50 批，无吞吐采样点（可能几乎全部跳过）。")
    lines.append("")

    lines.append("## 8. 耗时与成本（三方对照）")
    lines.append("")
    lines.append("- 本轮实际耗时：{0:.1f} 分钟（{1:.0f} 秒）".format(elapsed / 60, elapsed))
    lines.append("- 本轮 prompt_tokens 合计：{0}".format(prompt_tokens))
    lines.append("- 本轮标价成本（$0.01/百万 token）：${0:.4f}".format(cost))
    lines.append("- 试跑预估（并发 5）：约 84.5 分钟（70,642 条）")
    lines.append(
        "- 上一轮串行：{0} 条 / {1} 分钟 / 约 {2:,} token / ${3}".format(
            SERIAL_PREV_N, SERIAL_PREV_MINUTES, 20_420_000, "0.204")
    )
    lines.append("")
    lines.append("| | 条数 | 耗时（分） | prompt_tokens | 成本 |")
    lines.append("|---|---:|---:|---:|---:|")
    lines.append("| 本轮实测 | {0} | {1:.1f} | {2} | ${3:.4f} |".format(
        sum(newly.values()) + sum(skipped.values()), elapsed / 60, prompt_tokens, cost))
    lines.append("| 试跑预估 | 70642 | 84.5 | — | — |")
    lines.append("| 上一轮串行 | {0} | {1} | ~20420000 | $0.204 |".format(
        SERIAL_PREV_N, SERIAL_PREV_MINUTES))
    if newly and elapsed:
        lines.append("")
        lines.append("本轮新算 {0} 条，平均吞吐 {1:.2f} 条/秒。".format(
            sum(newly.values()), sum(newly.values()) / elapsed if elapsed else 0))
    lines.append("")

    lines.append("## 9. 重试")
    lines.append("")
    if retry_counts:
        for kind, n in sorted(retry_counts.items()):
            lines.append("- {0}：{1} 次".format(kind, n))
    else:
        lines.append("未触发重试。")
    lines.append("")

    lines.append("## 10. 产出文件")
    lines.append("")
    lines.append("| 文件 | 条数 | 字节 |")
    lines.append("|---|---:|---:|")
    for job in jobs:
        label = job["label"]
        lines.append("| `{0}` | {1} | {2} |".format(
            os.path.basename(job["dst"]), vec_counts[label], vec_sizes[label]))
    lines.append("")
    lines.append("产出侧跨文件 chunk_id 碰撞：{0}。".format(len(vec_collisions)))
    for cid, left, right in vec_collisions[:20]:
        lines.append("- `{0}`：{1} / {2}".format(cid, left, right))
    lines.append("")

    lines.append("## 11. 输入对照")
    lines.append("")
    lines.append("| 文件 | 本步前 | 本步后 |")
    lines.append("|---|---:|---:|")
    same = True
    for job in jobs:
        lines.append("| `{0}` | {1} | {2} |".format(job["name"], before[job["name"]], after[job["name"]]))
        if before[job["name"]] != after[job["name"]]:
            same = False
    lines.append("")
    lines.append("三份输入 chunks 文件的字节数在本步前后一致。" if same else "输入文件字节数发生变化。")
    lines.append("")

    lines.append("## 12. 抽样")
    lines.append("")
    lines.append("种子 {0}，三份各抽 2 条。".format(config.SAMPLE_SEED))
    lines.append("")
    for row in sample_rows:
        emb = row.get("embedding") or []
        head = ", ".join("{0:.6f}".format(x) for x in emb[:3])
        lines.append("- `{0}` chunk_index={1}；len={2}；前 3 个数：[{3}]".format(
            row.get("message_key"), row.get("chunk_index"), len(emb), head))
    lines.append("")

    _report(report_path, lines)
    with open(report_path, encoding="utf-8") as fp:
        body = fp.read()
    cleaned = _redact(body, secrets)
    if cleaned != body:
        with open(report_path, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(cleaned)

    expected_ok = True
    for job in jobs:
        expect = EXPECTED_COUNTS.get(job["name"])
        if expect is not None and vec_counts[job["label"]] != expect:
            expected_ok = False
    ok = (
        all_covered
        and not bad_dims
        and not failures
        and not vec_collisions
        and same
        and expected_ok
    )
    print(
        "FULL_V2_DONE",
        "new", sum(newly.values()),
        "skip", sum(skipped.values()),
        "fail", len(failures),
        "bad_dims", len(bad_dims),
        "ok", ok,
        flush=True,
    )
    return 0 if ok else 2


def main(argv=None) -> int:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    parser = argparse.ArgumentParser(description="纲目 / 圣经 embedding")
    parser.add_argument("--trial", action="store_true", help="并发试跑，不生成正式 *_vec")
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=None,
        help="输入 JSONL 路径（可多份）；全量默认 bible→feasts→12490",
    )
    parser.add_argument(
        "--concurrency",
        nargs="+",
        type=int,
        default=None,
        help="试跑：依次测的并发档（默认 3 5 8）；全量：并行批次数（默认 5）",
    )
    parser.add_argument("--out", default=config.DEFAULT_OUT_DIR)
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)
    if args.trial:
        if not args.report:
            args.report = os.path.join(root, "docs", "panai4_es", "embedding_trial_v2.md")
        return asyncio.run(_trial(args))
    if not args.report:
        args.report = os.path.join(root, "docs", "panai4_es", "embedding_report_v2.md")
    return asyncio.run(_full(args))


if __name__ == "__main__":
    raise SystemExit(main())
