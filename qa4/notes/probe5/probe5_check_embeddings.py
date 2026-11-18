# -*- coding: utf-8 -*-
"""
D. 向量抽样核对（供 Srey 运行）

默认：只抽样并估算费用（不调 API）。
--dry-run：只检查数据与参数，不联网。
--yes：真实调用 OpenRouter 重算向量。

密钥：仅环境变量 OPENROUTER_API_KEY；不读 .env；日志不写密钥。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径与常量（与 MANIFEST / es_import.INDEX_SPECS 对齐）
# ---------------------------------------------------------------------------
DATA_ROOT = Path(r"G:\PanAI4.0专用\qa4_import_src\es\data")
MANIFEST_PATH = Path(r"G:\PanAI4.0专用\qa4_import_src\MANIFEST.json")
LOG_DIR = Path(r"G:\PanAI4.0专用\logs")
SEED = 20261116
SAMPLE_PER_INDEX = 20
NEG_PAIRS_PER_INDEX = 5
BATCH_SIZE = 20
RETRIES = 2
PASS_RATIO = 0.95
COS_PASS = 0.99
COS_SUSPECT = 0.90

# 估算单价（USD / 1M tokens）；仅用于费用上限提示，非官方报价
EST_USD_PER_MTOK = 0.01

# 与 back_shared/embedding_adapter.py 一致
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_KG_MODEL = os.getenv("EMBEDDING_KG_MODEL", "qwen/qwen3-embedding-8b")
EMBEDDING_KG_DIMS = int(os.getenv("EMBEDDING_KG_DIMS", "1024"))

# V2 查询式前缀（可配置）
DEFAULT_V2_PREFIX = (
    "Instruct: Given a passage, retrieve relevant documents that match the query\n"
    "Query: "
)

# 索引规格：files 或 files_glob；es_vec_field=MANIFEST/ES 字段；file_vec_field=包内实际字段
INDEX_SPECS: dict[str, dict[str, Any]] = {
    "panai4_outline_12490": {
        "files": ["chunks_12490_vec.new.json"],
        "es_vec_field": "embedding",
        "file_vec_field": "embedding",
        "kind": "embedding_jsonl",
    },
    "panai4_outline_feasts": {
        "files": ["chunks_feasts_vec.json"],
        "es_vec_field": "embedding",
        "file_vec_field": "embedding",
        "kind": "embedding_jsonl",
    },
    "panai4_bible": {
        "files": ["chunks_bible_vec.json"],
        "es_vec_field": "embedding",
        "file_vec_field": "embedding",
        "kind": "embedding_jsonl",
    },
    "panai4_hymns": {
        "files": ["chunks_hymns_vec.json"],
        "es_vec_field": "embedding",
        "file_vec_field": "embedding",
        "kind": "embedding_jsonl",
    },
    "panai4_text_life": {
        "files_glob": "shards/*.jsonl",
        "es_vec_field": "text_vector",
        "file_vec_field": "embedding",  # 包内 embedding → 导入时写入 text_vector
        "kind": "inherit_jsonl",
    },
    "panai4_text_cwwl": {
        "files_glob": "shards/*.jsonl",
        "es_vec_field": "text_vector",
        "file_vec_field": "embedding",
        "kind": "inherit_jsonl",
    },
    "panai4_text_cwwn": {
        "files_glob": "shards/*.jsonl",
        "es_vec_field": "text_vector",
        "file_vec_field": "embedding",
        "kind": "inherit_jsonl",
    },
    "panai4_text_others": {
        "files_glob": "shards/*.jsonl",
        "es_vec_field": "text_vector",
        "file_vec_field": "embedding",
        "kind": "inherit_jsonl",
    },
    "panai4_map_note": {
        "files_glob": "shards/*.jsonl",
        "es_vec_field": "text_vector",
        "file_vec_field": "embedding",
        "kind": "inherit_jsonl",
    },
}

SECRET_RE = re.compile(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*\S+")
# 避免源码出现连续的 s k - 字面量（便于 Select-String 扫密钥）
_SK_PREFIX = "sk" + "-"
SK_RE = re.compile(re.escape(_SK_PREFIX) + r"[A-Za-z0-9_\-]{10,}")


def redact(s: str) -> str:
    s = SECRET_RE.sub(r"\1=***", s)
    s = SK_RE.sub(_SK_PREFIX + "***", s)
    return s


def setup_logger(name: str) -> tuple[logging.Logger, Path, Path]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"probe5_{name}_{ts}.log"
    json_path = LOG_DIR / f"probe5_{name}_{ts}.json"
    logger = logging.getLogger(f"probe5_{name}_{ts}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)

    class RedactFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            return True

    logger.addFilter(RedactFilter())
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger, log_path, json_path


def resolve_files(index: str) -> list[Path]:
    spec = INDEX_SPECS[index]
    base = DATA_ROOT / index
    if "files" in spec:
        paths = [base / n for n in spec["files"]]
    else:
        paths = sorted(base.glob(spec["files_glob"]))
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"{index} 缺少: {[str(p) for p in missing]}")
    if not paths:
        raise FileNotFoundError(f"{index} 无数据文件 under {base}")
    return paths


def get_vec(row: dict, file_vec_field: str) -> list[float] | None:
    v = row.get(file_vec_field)
    if v is None and file_vec_field == "embedding":
        v = row.get("text_vector")
    if isinstance(v, list) and v:
        return v
    return None


def title_for_v1(row: dict) -> str:
    for k in ("book_title", "message_title", "title"):
        t = row.get(k)
        if isinstance(t, str) and t.strip():
            return t.strip()
    return ""


def estimate_tokens(text: str) -> int:
    # 中英混合粗估：约 1.5 字/ token
    return max(1, int(math.ceil(len(text) / 1.5)))


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return float("nan")
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        xf = float(x)
        yf = float(y)
        dot += xf * yf
        na += xf * xf
        nb += yf * yf
    if na <= 0 or nb <= 0:
        return float("nan")
    return dot / math.sqrt(na * nb)


def median(xs: list[float]) -> float:
    if not xs:
        return float("nan")
    ys = sorted(xs)
    m = len(ys) // 2
    if len(ys) % 2:
        return ys[m]
    return 0.5 * (ys[m - 1] + ys[m])


# ---------------------------------------------------------------------------
# 抽样：先扫元数据（丢弃向量），再按字数三档各取
# ---------------------------------------------------------------------------
def scan_meta(index: str, paths: list[Path], file_vec_field: str, log: logging.Logger, dry_limit: int | None = None):
    """Yield (path, lineno, chunk_id, text_len). dry_limit: 每文件最多扫 N 行（dry-run）。"""
    n = 0
    for path in paths:
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if dry_limit is not None and lineno > dry_limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = row.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                if get_vec(row, file_vec_field) is None:
                    continue
                cid = row.get("chunk_id") or f"{path.name}:{lineno}"
                yield path, lineno, str(cid), len(text)
                n += 1
                if n % 20000 == 0:
                    log.info("%s scanned_ok=%s ...", index, n)


def stratified_sample(metas: list[tuple], k: int, rng: random.Random) -> list[tuple]:
    if len(metas) <= k:
        return list(metas)
    lens = sorted(m[3] for m in metas)
    t1 = lens[len(lens) // 3]
    t2 = lens[(2 * len(lens)) // 3]
    bins: dict[str, list] = {"lo": [], "mid": [], "hi": []}
    for m in metas:
        L = m[3]
        if L <= t1:
            bins["lo"].append(m)
        elif L <= t2:
            bins["mid"].append(m)
        else:
            bins["hi"].append(m)
    # 尽量均分
    base = k // 3
    rem = k - 3 * base
    quotas = {"lo": base, "mid": base, "hi": base}
    for key in ("lo", "mid", "hi"):
        if rem <= 0:
            break
        quotas[key] += 1
        rem -= 1
    picked: list = []
    leftover: list = []
    for key in ("lo", "mid", "hi"):
        pool = bins[key][:]
        rng.shuffle(pool)
        take = min(quotas[key], len(pool))
        picked.extend(pool[:take])
        leftover.extend(pool[take:])
    if len(picked) < k:
        rng.shuffle(leftover)
        picked.extend(leftover[: k - len(picked)])
    rng.shuffle(picked)
    return picked[:k]


def load_rows(selected: list[tuple], file_vec_field: str) -> list[dict]:
    """selected: (path, lineno, chunk_id, text_len)"""
    by_path: dict[Path, list[tuple]] = defaultdict(list)
    for path, lineno, cid, tlen in selected:
        by_path[path].append((lineno, cid, tlen))
    out: list[dict] = []
    for path, items in by_path.items():
        want = {ln: (cid, tlen) for ln, cid, tlen in items}
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if lineno not in want:
                    continue
                row = json.loads(line)
                vec = get_vec(row, file_vec_field)
                out.append(
                    {
                        "chunk_id": row.get("chunk_id") or want[lineno][0],
                        "text": row.get("text") or "",
                        "vector": [float(x) for x in vec] if vec else [],
                        "title": title_for_v1(row),
                        "text_len": len(row.get("text") or ""),
                        "source_file": str(path),
                        "lineno": lineno,
                    }
                )
                if len(out) >= sum(len(v) for v in by_path.values()) and all(
                    any(r["lineno"] == ln and r["source_file"] == str(path) for r in out)
                    for ln, _, _ in items
                ):
                    # early exit if all line nos for this file collected
                    if len([r for r in out if r["source_file"] == str(path)]) >= len(items):
                        break
    return out


# ---------------------------------------------------------------------------
# Embedding 调用（参数对齐 embedding_adapter.py）
# ---------------------------------------------------------------------------
async def embed_batch(texts: list[str]) -> list[list[float]]:
    key = os.environ.get("OPENROUTER_API_KEY") or ""
    if not key:
        raise RuntimeError("缺少环境变量 OPENROUTER_API_KEY")
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=key)
    last_err: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            r = await client.embeddings.create(
                model=EMBEDDING_KG_MODEL,
                input=texts,
                dimensions=EMBEDDING_KG_DIMS,
            )
            order = {d.index: d.embedding for d in r.data}
            return [order[i] for i in range(len(texts))]
        except Exception as e:
            last_err = e
            if attempt >= RETRIES:
                break
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"embedding 失败（已重试 {RETRIES} 次）: {redact(str(last_err))}")


async def embed_all(texts: list[str], log: logging.Logger) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        log.info("embed batch %s-%s / %s", i + 1, i + len(batch), len(texts))
        vecs = await embed_batch(batch)
        out.extend(vecs)
    return out


def verdict(ratio_ge: float, cos_min: float) -> str:
    if ratio_ge >= PASS_RATIO and cos_min >= COS_PASS:
        return "PASS"
    if cos_min >= COS_SUSPECT or ratio_ge >= 0.5:
        return "可疑"
    return "FAIL"


def summarize_index(name: str, cosines: list[float], neg_cos: list[float], fails: list[str]) -> dict:
    ge = sum(1 for c in cosines if c >= COS_PASS)
    ratio = (ge / len(cosines)) if cosines else 0.0
    cmin = min(cosines) if cosines else float("nan")
    cmax = max(cosines) if cosines else float("nan")
    cmed = median(cosines)
    v = verdict(ratio, cmin if cosines else 0.0)
    # 判定口径：≥95% 块 ≥0.99 → PASS；整体落在 0.9–0.99 → 可疑；<0.9 → FAIL
    if cosines:
        if ratio >= PASS_RATIO:
            v = "PASS"
        elif cmed >= COS_SUSPECT:
            v = "可疑"
        else:
            v = "FAIL"
    return {
        "index": name,
        "n": len(cosines),
        "cos_min": cmin,
        "cos_median": cmed,
        "cos_max": cmax,
        "ratio_ge_0_99": ratio,
        "neg_cos_median": median(neg_cos),
        "fail_chunk_ids": fails,
        "verdict": v,
    }


def dry_run_check(log: logging.Logger) -> dict:
    report: dict[str, Any] = {
        "mode": "dry-run",
        "data_root": str(DATA_ROOT),
        "manifest": str(MANIFEST_PATH),
        "model": EMBEDDING_KG_MODEL,
        "dims": EMBEDDING_KG_DIMS,
        "base_url": OPENROUTER_BASE_URL,
        "pass_dimensions_kwarg": True,
        "indices": [],
        "key_present": bool(os.environ.get("OPENROUTER_API_KEY")),
        "note": "dry-run 不联网；不读取密钥值",
    }
    if not DATA_ROOT.is_dir():
        raise SystemExit(f"数据根目录不存在: {DATA_ROOT}")
    man = None
    if MANIFEST_PATH.is_file():
        man = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        report["manifest_embedding_dims"] = man.get("embedding_dims")
    for index, spec in INDEX_SPECS.items():
        paths = resolve_files(index)
        # 每文件读前 3 行非空，确认字段
        samples = []
        with paths[0].open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                vec = get_vec(row, spec["file_vec_field"])
                samples.append(
                    {
                        "chunk_id": row.get("chunk_id"),
                        "text_len": len(row.get("text") or ""),
                        "vec_len": len(vec) if vec else 0,
                        "has_title": bool(title_for_v1(row)),
                    }
                )
                if len(samples) >= 3:
                    break
        entry = {
            "index": index,
            "files": [str(p) for p in paths],
            "n_files": len(paths),
            "es_vec_field": spec["es_vec_field"],
            "file_vec_field": spec["file_vec_field"],
            "sample_rows": samples,
        }
        report["indices"].append(entry)
        log.info(
            "OK %s files=%s es_field=%s file_field=%s sample_vec_len=%s",
            index,
            len(paths),
            spec["es_vec_field"],
            spec["file_vec_field"],
            samples[0]["vec_len"] if samples else None,
        )
    report["plan"] = {
        "sample_per_index": SAMPLE_PER_INDEX,
        "neg_pairs_per_index": NEG_PAIRS_PER_INDEX,
        "total_positive": SAMPLE_PER_INDEX * len(INDEX_SPECS),
        "batch_size": BATCH_SIZE,
        "v2_prefix_preview": DEFAULT_V2_PREFIX[:60] + "...",
    }
    return report


def build_samples(log: logging.Logger, dry_limit: int | None = None) -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    all_samples: dict[str, list[dict]] = {}
    for index, spec in INDEX_SPECS.items():
        paths = resolve_files(index)
        log.info("扫描元数据 %s (%s files)...", index, len(paths))
        metas = list(scan_meta(index, paths, spec["file_vec_field"], log, dry_limit=dry_limit))
        log.info("%s 可用块=%s", index, len(metas))
        if len(metas) < SAMPLE_PER_INDEX:
            log.warning("%s 可用块不足 %s，仅有 %s", index, SAMPLE_PER_INDEX, len(metas))
        selected = stratified_sample(metas, min(SAMPLE_PER_INDEX, len(metas)), rng)
        rows = load_rows(selected, spec["file_vec_field"])
        # 保序按 selected chunk
        by_id = {r["chunk_id"]: r for r in rows}
        ordered = []
        for _, _, cid, _ in selected:
            if cid in by_id:
                ordered.append(by_id[cid])
        all_samples[index] = ordered
        log.info("%s 抽到 %s 条", index, len(ordered))
    return all_samples


def make_neg_pairs(rows: list[dict], rng: random.Random, n_pairs: int) -> list[tuple[dict, dict]]:
    if len(rows) < 2:
        return []
    pairs = []
    tried = set()
    while len(pairs) < n_pairs and len(tried) < n_pairs * 20:
        i, j = rng.sample(range(len(rows)), 2)
        key = tuple(sorted((rows[i]["chunk_id"], rows[j]["chunk_id"])))
        if key in tried:
            continue
        tried.add(key)
        pairs.append((rows[i], rows[j]))
    return pairs


def estimate_plan(samples: dict[str, list[dict]], v2_prefix: str) -> dict:
    texts = []
    for rows in samples.values():
        for r in rows:
            texts.append(r["text"])
    # 主路径：180 条；最坏再假设全部 <0.99 各跑 V1+V2 → ×3
    tok_main = sum(estimate_tokens(t) for t in texts)
    tok_worst = tok_main * 3
    n_req_main = math.ceil(len(texts) / BATCH_SIZE) if texts else 0
    n_req_worst = n_req_main * 3
    cost_main = tok_main / 1_000_000 * EST_USD_PER_MTOK
    cost_worst = tok_worst / 1_000_000 * EST_USD_PER_MTOK
    return {
        "n_texts_main": len(texts),
        "n_requests_main": n_req_main,
        "est_tokens_main": tok_main,
        "est_usd_main": round(cost_main, 6),
        "n_requests_worst_with_v1v2": n_req_worst,
        "est_tokens_worst": tok_worst,
        "est_usd_worst": round(cost_worst, 6),
        "usd_per_mtok_assumed": EST_USD_PER_MTOK,
        "note": "价格为粗估；官方价以 OpenRouter 页面为准",
        "v2_prefix_len": len(v2_prefix),
    }


async def run_yes(samples: dict[str, list[dict]], v2_prefix: str, log: logging.Logger) -> dict:
    rng = random.Random(SEED)
    index_results = []
    for index, rows in samples.items():
        log.info("==== 重算 %s n=%s ====", index, len(rows))
        texts = [r["text"] for r in rows]
        recomputed = await embed_all(texts, log)
        cosines = []
        fails = []
        low = []
        for r, vec in zip(rows, recomputed):
            dim_ok = len(vec) == EMBEDDING_KG_DIMS and len(r["vector"]) == EMBEDDING_KG_DIMS
            cos = cosine(r["vector"], vec) if dim_ok else float("nan")
            cosines.append(cos)
            if not (cos >= COS_PASS):
                fails.append(r["chunk_id"])
                low.append(r)
            log.info(
                "%s chunk=%s dim_store=%s dim_new=%s cos=%.6f",
                index,
                r["chunk_id"],
                len(r["vector"]),
                len(vec),
                cos if cos == cos else -1,
            )

        # 负对照：存库向量两两
        neg_pairs = make_neg_pairs(rows, rng, NEG_PAIRS_PER_INDEX)
        neg_cos = [cosine(a["vector"], b["vector"]) for a, b in neg_pairs]

        # 低分块试 V1 / V2
        alt_trials = []
        if low:
            v1_texts = []
            v2_texts = []
            for r in low:
                title = r["title"]
                v1 = f"{title}\n{r['text']}" if title else r["text"]
                v1_texts.append(v1)
                v2_texts.append(v2_prefix + r["text"])
            v1_vecs = await embed_all(v1_texts, log)
            v2_vecs = await embed_all(v2_texts, log)
            for r, v1, v2 in zip(low, v1_vecs, v2_vecs):
                c0 = cosine(r["vector"], recomputed[rows.index(r)]) if r in rows else float("nan")
                # rows.index may be wrong if duplicates; use stored from cosines loop
                c_plain = next(
                    (c for rr, c in zip(rows, cosines) if rr["chunk_id"] == r["chunk_id"]),
                    float("nan"),
                )
                c1 = cosine(r["vector"], v1)
                c2 = cosine(r["vector"], v2)
                best = max(
                    (c_plain, "plain"),
                    (c1, "V1_title_plus_text"),
                    (c2, "V2_instruct_query"),
                    key=lambda x: (x[0] if x[0] == x[0] else -1),
                )
                alt_trials.append(
                    {
                        "chunk_id": r["chunk_id"],
                        "cos_plain": c_plain,
                        "cos_v1": c1,
                        "cos_v2": c2,
                        "best": best[1],
                        "best_cos": best[0],
                    }
                )

        summary = summarize_index(index, cosines, neg_cos, fails)
        summary["alt_trials"] = alt_trials
        summary["dim_expected"] = EMBEDDING_KG_DIMS
        index_results.append(summary)
        log.info(
            "%s verdict=%s ratio=%.3f min=%.4f med=%.4f neg_med=%.4f",
            index,
            summary["verdict"],
            summary["ratio_ge_0_99"],
            summary["cos_min"],
            summary["cos_median"],
            summary["neg_cos_median"],
        )
    return {"mode": "yes", "indices": index_results}


def parse_args():
    p = argparse.ArgumentParser(description="probe5 向量抽样核对")
    p.add_argument("--dry-run", action="store_true", help="只检查数据与参数，不联网")
    p.add_argument("--yes", action="store_true", help="真实调用 OpenRouter 重算向量")
    p.add_argument(
        "--v2-prefix",
        default=DEFAULT_V2_PREFIX,
        help="V2 查询式前缀（可配置）",
    )
    p.add_argument(
        "--estimate-only",
        action="store_true",
        help="强制只估算（与默认相同；抽样后打印费用）",
    )
    return p.parse_args()


def main():
    args = parse_args()
    if args.yes and args.dry_run:
        raise SystemExit("不能同时使用 --yes 与 --dry-run")

    log, log_path, json_path = setup_logger("check_embeddings")
    log.info("log=%s", log_path)
    log.info(
        "model=%s dims=%s base_url=%s dimensions_kwarg=True",
        EMBEDDING_KG_MODEL,
        EMBEDDING_KG_DIMS,
        OPENROUTER_BASE_URL,
    )

    result: dict[str, Any] = {
        "script": "qa4/notes/probe5/probe5_check_embeddings.py",
        "log": str(log_path),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "index_file_map": {
            k: {
                "es_vec_field": v["es_vec_field"],
                "file_vec_field": v["file_vec_field"],
                "files": v.get("files"),
                "files_glob": v.get("files_glob"),
            }
            for k, v in INDEX_SPECS.items()
        },
    }

    try:
        if args.dry_run:
            result["report"] = dry_run_check(log)
            log.info("dry-run 完成（未联网）")
        else:
            # 默认与 --estimate-only：本地抽样 + 估算；--yes 再调用
            log.info("开始本地抽样（seed=%s）...", SEED)
            samples = build_samples(log)
            plan = estimate_plan(samples, args.v2_prefix)
            result["estimate"] = plan
            result["sample_counts"] = {k: len(v) for k, v in samples.items()}
            log.info(
                "估算：主路径请求约 %s 次，token≈%s，费用≈$%s；最坏(含V1/V2)×3 ≈$%s",
                plan["n_requests_main"],
                plan["est_tokens_main"],
                plan["est_usd_main"],
                plan["est_usd_worst"],
            )
            if args.yes:
                if not os.environ.get("OPENROUTER_API_KEY"):
                    raise SystemExit("缺少 OPENROUTER_API_KEY，无法 --yes")
                result["report"] = asyncio.run(run_yes(samples, args.v2_prefix, log))
            else:
                result["report"] = {
                    "mode": "estimate",
                    "message": "未加 --yes，未调用 API。加 --yes 才会真实重算。",
                    "sample_chunk_ids": {
                        k: [r["chunk_id"] for r in v] for k, v in samples.items()
                    },
                }
                log.info("仅估算完成。真实调用请加 --yes")
    except Exception as e:
        log.exception("失败: %s", redact(str(e)))
        result["error"] = redact(str(e))
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(1) from e

    result["finished_at"] = datetime.now().isoformat(timespec="seconds")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("结果 JSON: %s", json_path)
    print(f"RESULT_JSON={json_path}")
    print(f"LOG={log_path}")


if __name__ == "__main__":
    main()
