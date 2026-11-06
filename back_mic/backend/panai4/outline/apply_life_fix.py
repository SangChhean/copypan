# -*- coding: utf-8 -*-
"""生命读经修订：阶段0/1 + 阶段2（prepare→embed→assemble→verify_vec→write_local→reconcile）。

用法（cd G:\\copypan\\back_mic\\backend）::

    python -m panai4.outline.apply_life_fix --stage backup|dryrun|prepare|embed|assemble|verify_vec|write_local|reconcile|rollback_local|stage2
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from panai4.outline import config
from panai4.outline.build_chunks import build_message_chunks, render_header

# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = Path(config.DEFAULT_OUT_DIR)
PANAI_ROOT = Path(r"G:\PanAI4.0专用")
BACKUP_DIR = PANAI_ROOT / "备份_生命读经修订前_20261106"
STAGING_DIR = PANAI_ROOT / "_staging_life_fix"
FINAL_V3 = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_final.csv"
FINAL_V4 = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_final_v4.csv"
REPORT_PATH = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_fix_stage01.md"
ARCHIVE_DIR = REPO_ROOT / "docs" / "panai4_es" / "archive"
LOG_DIR_DEFAULT = REPO_ROOT / "logs"
ES_INDEX = "panai4_outline_12490"
ES_URL_ALLOWED = "http://localhost:9200"
IDEOGRAPHIC_SPACE = "\u3000"
EXPECTED_SNAP = {"files": 41, "bytes": 4733504505}
EMBED_DIMS = 1024
EMBED_BATCH = 50
EMBED_CONCURRENCY = 4
EMBED_RETRY_WAITS = (1, 2, 4, 8, 16)
EXPECTED_REEMBED_N = 343
EXPECTED_REEMBED_CHARS = 136866
EXPECTED_AFFECTED_N = 348
COST_PER_1K_CHUNKS = 0.002

OUTLINE_DOC_FIELDS = (
    "chunk_id", "message_key", "source_path", "batch", "text", "embedding",
    "book_title", "book_path", "message_title", "message_number", "author",
    "year", "year_end", "paragraph_type", "tokens", "min_level", "point_count",
    "chunk_index", "chunk_total", "para_nos", "part_no", "part_name",
    "conference", "month",
)

BOOK_PATH_REPLACEMENTS = {
    "雅歌书生命读经": "雅歌生命读经",
    "约翰二书生命读经_": "约翰二书生命读经",
}


class GateFail(Exception):
    """闸门失败：立即停止，不进入下一阶段。"""

    def __init__(self, gate: str, message: str, payload: Optional[dict] = None):
        super().__init__(f"{gate}: {message}")
        self.gate = gate
        self.payload = payload or {}

BACKUP_FILES = [
    "outline_12490.json",
    "chunks_12490.json",
    "chunks_12490_vec.json",
    "excluded_files.json",
    "anomalies.json",
]

# 新增确认项：(book_title substr match via message_key, msg hint in key, new_title or transform)
REVIEW_NEWS = [
    ("gm12490/3 生命读经/1 创世记生命读经/msg. 85 ", "柱子的建造者—巧匠户兰（一）（插进的话）", "review_decision"),
    ("gm12490/3 生命读经/1 创世记生命读经/msg. 98 ", "成熟的表显（三）", "review_decision"),
    ("gm12490/3 生命读经/1 创世记生命读经/msg. 99 ", "成熟的表显（四）", "review_decision"),
    ("gm12490/3 生命读经/1 创世记生命读经/msg. 109 ", "成熟的表显（七）", "review_decision"),
    ("gm12490/3 生命读经/44 哥林多后书生命读经/msg. 57 ", "保罗为他使徒权柄的表白（八）", "review_decision"),
    ("gm12490/3 生命读经/38 马可福音生命读经/msg. 68 ", "一种完全照着神新约经纶，并为着神新约经纶的生活（十七）", "review_decision"),
]
SREY_TRANSFORMS = [
    ("gm12490/3 生命读经/40 约翰福音生命读经/msg. 17 ", "乾", "干"),
    ("gm12490/3 生命读经/40 约翰福音生命读经/msg. 36 ", "於", "于"),
    ("gm12490/3 生命读经/40 约翰福音生命读经/msg. 37 ", "於", "于"),
]
DROP_MK_PREFIX = "gm12490/3 生命读经/9 撒母耳记生命读经/msg. 9 "


def _edit_distance_one(a: str, b: str) -> bool:
    """True iff a and b differ by exactly one substitution (same length)."""
    if len(a) != len(b):
        return False
    return sum(1 for x, y in zip(a, b) if x != y) == 1


def _backend_env() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def setup_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_dir / f"life_fix_apply_{stamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    logging.info("log_path=%s", path)
    return path


def make_es():
    from elasticsearch import Elasticsearch

    load_dotenv(_backend_env())
    host = os.getenv("ES_HOST", "localhost")
    port = os.getenv("ES_PORT", "9200")
    url = f"http://{host}:{port}"
    if host not in ("localhost", "127.0.0.1") or str(port) != "9200":
        raise GateFail("ES_HOST", f"只允许本机 {ES_URL_ALLOWED}，当前 host={host!r} port={port!r}")
    return Elasticsearch(
        hosts=[url],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=180,
        max_retries=0,
    ), url


def _redact(text: str, secrets: list[str]) -> str:
    out = text or ""
    for secret in secrets:
        if secret and len(secret) >= 8:
            out = out.replace(secret, "***")
    return out


def _secret_values() -> list[str]:
    """从已加载的环境变量收集密钥值（不读 .env 文件内容）。"""
    keys = (
        "OPENROUTER_API_KEY", "ES_PASSWORD", "NEO4J_PASSWORD",
        "OPENAI_API_KEY", "DASHSCOPE_API_KEY",
    )
    return [os.environ.get(k, "") for k in keys if os.environ.get(k)]


def _load_affected() -> list[dict]:
    path = BACKUP_DIR / "affected_chunks.csv"
    with path.open(encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def _affected_cids(aff: Optional[list[dict]] = None) -> set[str]:
    aff = aff if aff is not None else _load_affected()
    return {a["chunk_id"] for a in aff}


def _book_path_cids(aff: Optional[list[dict]] = None) -> set[str]:
    aff = aff if aff is not None else _load_affected()
    return {a["chunk_id"] for a in aff if a.get("field") == "book_title"}


def _load_reembed_ids() -> list[str]:
    path = STAGING_DIR / "reembed_ids.txt"
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _load_vec_plan() -> dict[str, str]:
    path = STAGING_DIR / "vec_plan.csv"
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            out[row["chunk_id"]] = row["action"]
    return out


def _load_jsonl_index(path: Path, key: str = "chunk_id") -> dict[str, dict]:
    by = {}
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            by[obj[key]] = obj
    return by


def _write_stage_report(stage: str, lines: list[str], *, series: str = "stage2") -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    if stage.startswith("remote_") or stage.startswith("FAIL_R") or stage in ("RC", "RB", "RW", "RR"):
        series = "stage3"
    # FAIL_RC etc.
    if stage.startswith("FAIL_") and stage.split("_", 1)[-1] in ("RC", "RB", "RW", "RR", "REMOTE"):
        series = "stage3"
    path = ARCHIVE_DIR / f"life_fix_{series}_{stage}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("wrote %s", path)
    return path


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return float("nan")
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return float("nan")
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _assert_gitignore_env() -> dict:
    gi = REPO_ROOT / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    patterns = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    hit = any(p in (".env", "*.env", "**/.env") or p.endswith("/.env") for p in patterns)
    # also common: bare .env appears
    hit = hit or (".env" in patterns) or any(p == ".env" or p.endswith(".env") for p in patterns)
    return {"gitignore_exists": gi.exists(), "env_ignored": hit, "patterns_sample": [p for p in patterns if "env" in p.lower()][:10]}


def _doc_for_es(obj: dict) -> dict:
    doc = {}
    for key in OUTLINE_DOC_FIELDS:
        if key in obj:
            doc[key] = obj[key]
    return doc


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            block = fp.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def folder_snapshot(root: Path) -> dict:
    n_files = total = 0
    for dirpath, _d, names in os.walk(root):
        for name in names:
            p = Path(dirpath) / name
            try:
                st = p.stat()
            except OSError:
                continue
            n_files += 1
            total += st.st_size
    return {"files": n_files, "bytes": total}


def _git_status() -> str:
    try:
        return subprocess.check_output(
            ["git", "status", "--short", "--", "back_mic/backend/panai4/"],
            cwd=str(REPO_ROOT), text=True, encoding="utf-8", errors="replace",
        ).strip() or "(clean)"
    except Exception as exc:  # noqa: BLE001
        return f"(git failed: {exc})"


def tokens_of(text: str) -> int:
    """与 build_chunks 一致：int(len(text) / 1.5)。"""
    return int(len(text) / 1.5)


def load_chunks_index(path: Path) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """返回 by_cid, mk→[cid,...]；不载入 embedding。"""
    by_cid: dict[str, dict] = {}
    mk_map: dict[str, list[str]] = defaultdict(list)
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            cid = obj["chunk_id"]
            by_cid[cid] = obj
            mk_map[obj.get("message_key") or ""].append(cid)
    return by_cid, mk_map


def find_mk(prefix: str, by_mk: dict[str, list[str]]) -> Optional[str]:
    for mk in by_mk:
        if mk.startswith(prefix) or prefix.rstrip() in mk:
            # prefer exact startswith on path+msg.
            if mk.startswith(prefix.rstrip()) or mk.startswith(prefix):
                return mk
    for mk in by_mk:
        if prefix.strip() in mk:
            return mk
    return None


def build_v4_csv(chunks_path: Path) -> list[dict]:
    by_cid, mk_map = load_chunks_index(chunks_path)
    # title of first chunk per mk
    title_of = {}
    book_of = {}
    mno_of = {}
    for cid, obj in by_cid.items():
        mk = obj.get("message_key") or ""
        if mk not in title_of:
            title_of[mk] = obj.get("message_title") or ""
            book_of[mk] = obj.get("book_title") or ""
            mno_of[mk] = obj.get("message_number")
            if mno_of[mk] is None:
                mno_of[mk] = ""

    rows: list[dict] = []
    with FINAL_V3.open(encoding="utf-8-sig", newline="") as fp:
        for r in csv.DictReader(fp):
            mk = r["message_key"]
            # 剔除撒母耳记 #9「题醒→提醒」
            if mk.startswith(DROP_MK_PREFIX) and r.get("field") == "message_title" and "题醒" in (r.get("old") or ""):
                logging.info("drop 撒母耳记#9: %s", mk[:80])
                continue
            rows.append({
                "message_key": mk,
                "field": r["field"],
                "old": r["old"],
                "new": r["new"],
                "category": r.get("category") or "",
                "reembed": r.get("reembed") or "",
                "source": "final_v3",
            })

    for prefix, new_title, src in REVIEW_NEWS:
        mk = find_mk(prefix, mk_map)
        if not mk:
            raise SystemExit(f"cannot find message_key for {prefix}")
        old = title_of[mk]
        rows.append({
            "message_key": mk,
            "field": "message_title",
            "old": old,
            "new": new_title,
            "category": "review_decision",
            "reembed": "是",
            "source": src,
        })

    for prefix, a, b in SREY_TRANSFORMS:
        mk = find_mk(prefix, mk_map)
        if not mk:
            raise SystemExit(f"cannot find message_key for {prefix}")
        old = title_of[mk]
        if old.count(a) != 1:
            raise SystemExit(f"srey assert: {mk} expected one '{a}' in old={old!r}")
        new = old.replace(a, b, 1)
        if not _edit_distance_one(old, new):
            raise SystemExit(f"srey assert: {mk} old/new must differ by exactly one char")
        rows.append({
            "message_key": mk,
            "field": "message_title",
            "old": old,
            "new": new,
            "category": "srey_decision",
            "reembed": "是",
            "source": "srey_decision",
        })

    # assert old == current
    mismatches = []
    for r in rows:
        mk = r["message_key"]
        field = r["field"]
        if field == "message_title":
            cur = title_of.get(mk)
            if cur != r["old"]:
                mismatches.append((mk, field, r["old"][:40], (cur or "")[:40]))
        elif field == "book_title":
            cur = book_of.get(mk)
            if cur != r["old"]:
                mismatches.append((mk, field, r["old"][:40], (cur or "")[:40]))
        elif field == "message_number":
            cur = mno_of.get(mk)
            cur_s = "" if cur is None else str(cur)
            old_s = "" if r["old"] in ("", None) else str(r["old"])
            if cur_s != old_s:
                mismatches.append((mk, field, old_s, cur_s))
    if mismatches:
        for m in mismatches[:20]:
            logging.error("old mismatch %s", m)
        raise SystemExit(f"v4 old≠current: {len(mismatches)}")

    # no 撒母耳 9
    for r in rows:
        if "撒母耳记生命读经/msg. 9" in r["message_key"] and "题醒" in r.get("old", ""):
            raise SystemExit("撒母耳#9 still in v4")

    FINAL_V4.parent.mkdir(parents=True, exist_ok=True)
    cols = ["message_key", "field", "old", "new", "category", "reembed", "source"]
    with FINAL_V4.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    logging.info("wrote %s rows=%s", FINAL_V4, len(rows))
    return rows


def collect_affected(rows: list[dict], mk_map: dict[str, list[str]], by_cid: dict[str, dict]) -> list[dict]:
    """受影响块清单。"""
    out = []
    for r in rows:
        mk = r["message_key"]
        field = r["field"]
        for cid in mk_map.get(mk) or []:
            obj = by_cid[cid]
            text_will_change = field in ("message_title", "book_title")
            out.append({
                "chunk_id": cid,
                "message_key": mk,
                "book_title": obj.get("book_title") or "",
                "message_number": obj.get("message_number") if obj.get("message_number") is not None else "",
                "field": field,
                "old": r["old"],
                "new": r["new"],
                "category": r.get("category") or "",
                "text_first_line_changes": "是" if text_will_change else "否",
                "needs_reembed": "是" if text_will_change else "否",
                "source": r.get("source") or "",
            })
    return out


def stage_backup(rows: list[dict], log_path: Path) -> dict:
    es, es_url = make_es()
    count_before = es.count(index=ES_INDEX)["count"]
    snap_before = folder_snapshot(OUT_DIR)

    chunks_path = OUT_DIR / "chunks_12490.json"
    by_cid, mk_map = load_chunks_index(chunks_path)
    affected = collect_affected(rows, mk_map, by_cid)
    affected_cids = sorted({a["chunk_id"] for a in affected})

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    # A. affected csv
    aff_csv = BACKUP_DIR / "affected_chunks.csv"
    cols = list(affected[0].keys()) if affected else [
        "chunk_id", "message_key", "book_title", "message_number", "field",
        "old", "new", "category", "text_first_line_changes", "needs_reembed", "source",
    ]
    with aff_csv.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=cols)
        w.writeheader()
        for a in affected:
            w.writerow(a)

    # B. copy + sha256
    sums = []
    for name in BACKUP_FILES:
        src = OUT_DIR / name
        dst = BACKUP_DIR / name
        logging.info("copy %s ...", name)
        shutil.copy2(src, dst)
        hs = sha256_file(src)
        hd = sha256_file(dst)
        if hs != hd:
            raise SystemExit(f"SHA256 mismatch after copy: {name}")
        sums.append((name, hs, src.stat().st_size))
    sums_path = BACKUP_DIR / "SHA256SUMS.txt"
    with sums_path.open("w", encoding="utf-8") as fp:
        for name, h, size in sums:
            fp.write(f"{h}  {name}  # size={size}\n")

    # C. ES mget export
    logging.info("mget %s affected docs from ES...", len(affected_cids))
    es_path = BACKUP_DIR / "es_before_affected.jsonl"
    exported = 0
    text_mismatch = 0
    with es_path.open("w", encoding="utf-8") as out_fp:
        for i in range(0, len(affected_cids), 100):
            batch = affected_cids[i:i + 100]
            resp = es.mget(index=ES_INDEX, ids=batch)
            for doc in resp.get("docs") or []:
                if not doc.get("found"):
                    raise SystemExit(f"ES missing {doc.get('_id')}")
                cid = doc["_id"]
                src = doc.get("_source") or {}
                # write full doc as stored
                out_fp.write(json.dumps({"_id": cid, **src}, ensure_ascii=False) + "\n")
                exported += 1
                ch = by_cid.get(cid)
                if ch and (ch.get("text") or "") != (src.get("text") or ""):
                    text_mismatch += 1
    if exported != len(affected_cids):
        raise SystemExit(f"export count {exported} != {len(affected_cids)}")
    if text_mismatch:
        raise SystemExit(f"ES text ≠ chunks for {text_mismatch} docs")

    # D. MANIFEST
    reembed_n = sum(1 for a in affected if a["needs_reembed"] == "是")
    uniq_blocks = len(affected_cids)
    uniq_msgs = len({a["message_key"] for a in affected})
    manifest = BACKUP_DIR / "MANIFEST.md"
    lines = [
        "# 生命读经修订前备份 MANIFEST",
        "",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- ES：`{es_url}` index=`{ES_INDEX}` count={count_before}",
        f"- 源目录：`{OUT_DIR}`",
        f"- 备份目录：`{BACKUP_DIR}`",
        f"- 清单：`{FINAL_V4}`（{len(rows)} 条）",
        f"- 受影响块（行）={len(affected)}；唯一 chunk_id={uniq_blocks}；唯一 message_key={uniq_msgs}；需重算向量块={reembed_n}",
        "",
        "## 文件与 SHA256",
        "",
    ]
    for name, h, size in sums:
        lines.append(f"- `{name}` size={size} sha256=`{h}`")
    lines += [
        "",
        f"- `affected_chunks.csv` 行数（含表头外）={len(affected)}",
        f"- `es_before_affected.jsonl` 条数={exported}",
        "",
        "## 恢复步骤",
        "",
        "1. 停止写入 ES / 暂停相关服务。",
        f"2. 将本目录中的 `{', '.join(BACKUP_FILES)}` 复制回 `{OUT_DIR}`（覆盖）。",
        "3. 核对 SHA256SUMS.txt 与源文件一致。",
        f"4. 用 `es_before_affected.jsonl` 按 `_id` bulk index/update 回 `{ES_INDEX}`（含 embedding）。",
        "5. count 应为 55841；抽查受影响块 text 与备份 JSON 一致。",
        "",
        f"日志：`{log_path}`",
        f"纲目JSON快照 before={snap_before}",
        "",
    ]
    manifest.write_text("\n".join(lines), encoding="utf-8")

    count_after = es.count(index=ES_INDEX)["count"]
    snap_after = folder_snapshot(OUT_DIR)
    return {
        "affected": affected,
        "affected_cids": affected_cids,
        "exported": exported,
        "sums": sums,
        "count_before": count_before,
        "count_after": count_after,
        "snap_before": snap_before,
        "snap_after": snap_after,
        "es_url": es_url,
        "reembed_n": reembed_n,
        "uniq_msgs": uniq_msgs,
    }


def apply_fix_to_chunk(obj: dict, fixes: list[dict]) -> tuple[dict, bool]:
    """对单块应用同 message_key 的全部 field 修改。返回 (new_obj, text_changed)。"""
    new = dict(obj)
    text_changed = False
    bt = new.get("book_title") or ""
    mt = new.get("message_title") or ""
    for fx in fixes:
        field = fx["field"]
        if field == "message_title":
            mt = fx["new"]
            new["message_title"] = mt
        elif field == "book_title":
            bt = fx["new"]
            new["book_title"] = bt
        elif field == "message_number":
            val = fx["new"]
            new["message_number"] = int(val) if str(val).isdigit() else val
    # rewrite header if title/book changed（其余行一字不动）
    if any(fx["field"] in ("message_title", "book_title") for fx in fixes):
        text = new.get("text") or ""
        new_header = render_header(bt, mt)
        if "\n" not in text:
            new_text = new_header
        else:
            body = text.split("\n", 1)[1]
            new_text = new_header + "\n" + body
        if new_text != text:
            text_changed = True
            new["text"] = new_text
            new["tokens"] = tokens_of(new_text)
    return new, text_changed


def regen_chunks_from_outline(outline_path: Path, out_jsonl: Path) -> int:
    """仅用 build_message_chunks 从 outline 生成 12490 chunks（不跑完整 CLI）。"""
    n = 0
    with outline_path.open(encoding="utf-8") as inp, out_jsonl.open("w", encoding="utf-8", newline="\n") as out:
        for line in inp:
            if not line.strip():
                continue
            record = json.loads(line)
            chunks = build_message_chunks(record)
            for chunk in chunks:
                public = {k: v for k, v in chunk.items() if not k.startswith("_")}
                out.write(json.dumps(public, ensure_ascii=False) + "\n")
                n += 1
    return n


def compare_jsonl(path_a: Path, path_b: Path) -> dict:
    """按 chunk_id 逐字段比对。"""
    a_map = {}
    with path_a.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            a_map[o["chunk_id"]] = o
    same = diff = missing_b = missing_a = 0
    field_diffs: Counter = Counter()
    samples = []
    b_ids = set()
    with path_b.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            cid = o["chunk_id"]
            b_ids.add(cid)
            old = a_map.get(cid)
            if old is None:
                missing_a += 1
                continue
            if old == o:
                same += 1
            else:
                diff += 1
                for k in set(old) | set(o):
                    if old.get(k) != o.get(k):
                        field_diffs[k] += 1
                if len(samples) < 20:
                    diffs = {k: (old.get(k), o.get(k)) for k in set(old) | set(o) if old.get(k) != o.get(k)}
                    # truncate long
                    brief = {}
                    for k, (x, y) in diffs.items():
                        sx = repr(x)[:60]
                        sy = repr(y)[:60]
                        brief[k] = (sx, sy)
                    samples.append((cid, brief))
    for cid in a_map:
        if cid not in b_ids:
            missing_b += 1
    return {
        "same": same, "diff": diff, "missing_in_b": missing_b, "missing_in_a": missing_a,
        "field_diffs": dict(field_diffs), "samples": samples,
        "n_a": len(a_map), "n_b": len(b_ids),
    }


def stage_dryrun(rows: list[dict], backup_info: dict, log_path: Path) -> dict:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    chunks_src = BACKUP_DIR / "chunks_12490.json"
    outline_src = BACKUP_DIR / "outline_12490.json"
    vec_src = BACKUP_DIR / "chunks_12490_vec.json"
    if not chunks_src.exists():
        chunks_src = OUT_DIR / "chunks_12490.json"
        outline_src = OUT_DIR / "outline_12490.json"
        vec_src = OUT_DIR / "chunks_12490_vec.json"

    by_cid, mk_map = load_chunks_index(chunks_src)

    # fixes by mk
    fixes_by_mk: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        fixes_by_mk[r["message_key"]].append(r)

    # 1. outline field paths — documented from code + sample
    outline_field_info = {
        "message_title": "record.meta.title（doc_header.title_in_doc 有存但不参与切块）",
        "message_number": "record.meta.msg_no",
        "book_title_via": "book_title_of(meta, batch, book_path_of(meta)) ← meta.book_path 去序号；显示字段 meta.book",
        "tokens": "int(len(text)/1.5) 同 build_chunks.py:199",
        "build_chunks_lines": "build_chunks.py:180-194, 110-126, 83-89 render_header",
    }

    # 2. reproducibility via build_message_chunks (faithful to CLI logic for 12490)
    repro_dir = STAGING_DIR / "repro_old"
    repro_dir.mkdir(parents=True, exist_ok=True)
    # copy outline for clarity
    shutil.copy2(outline_src, repro_dir / "outline_12490.json")
    # also need feasts for CLI; for function-based regen only 12490
    regen_old = STAGING_DIR / "chunks_12490.repro_from_old_outline.json"
    logging.info("repro: regen chunks from old outline...")
    n_repro = regen_chunks_from_outline(outline_src, regen_old)
    logging.info("repro n=%s; comparing...", n_repro)
    repro_cmp = compare_jsonl(chunks_src, regen_old)

    # Also try CLI if feasts outline available
    feasts_src = OUT_DIR / "outline_feasts.json"
    cli_cmp = None
    if feasts_src.exists():
        cli_dir = STAGING_DIR / "repro_cli"
        cli_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(outline_src, cli_dir / "outline_12490.json")
        shutil.copy2(feasts_src, cli_dir / "outline_feasts.json")
        report_cli = STAGING_DIR / "chunking_report_repro.md"
        logging.info("running build_chunks CLI --out %s", cli_dir)
        rc = subprocess.call(
            [sys.executable, "-m", "panai4.outline.build_chunks", "--out", str(cli_dir), "--report", str(report_cli)],
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        logging.info("build_chunks rc=%s (STOP_V02 常见于无 v0.1 对照；以产出文件为准)", rc)
        if (cli_dir / "chunks_12490.json").exists():
            cli_cmp = compare_jsonl(chunks_src, cli_dir / "chunks_12490.json")

    # 3. apply field-level edits → chunks_12490.new.json
    new_chunks_path = STAGING_DIR / "chunks_12490.new.json"
    changes_rows = []
    reembed_ids = []
    affected_cids = set()
    text_changed_cids = set()
    n_written = 0
    with chunks_src.open(encoding="utf-8") as inp, new_chunks_path.open("w", encoding="utf-8", newline="\n") as out:
        for line in inp:
            if not line.strip():
                continue
            obj = json.loads(line)
            mk = obj.get("message_key") or ""
            cid = obj["chunk_id"]
            if mk in fixes_by_mk:
                new_obj, text_changed = apply_fix_to_chunk(obj, fixes_by_mk[mk])
                affected_cids.add(cid)
                for fx in fixes_by_mk[mk]:
                    changes_rows.append({
                        "chunk_id": cid,
                        "message_key": mk,
                        "book": new_obj.get("book_title") or obj.get("book_title") or "",
                        "msg_no": new_obj.get("message_number") if new_obj.get("message_number") is not None else "",
                        "field": fx["field"],
                        "old": fx["old"],
                        "new": fx["new"],
                    })
                if text_changed:
                    text_changed_cids.add(cid)
                    reembed_ids.append(cid)
                out.write(json.dumps(new_obj, ensure_ascii=False) + "\n")
            else:
                out.write(line if line.endswith("\n") else line + "\n")
            n_written += 1

    # outline.new.json
    outline_new = STAGING_DIR / "outline_12490.new.json"
    mk_to_fixes = fixes_by_mk
    with outline_src.open(encoding="utf-8") as inp, outline_new.open("w", encoding="utf-8", newline="\n") as out:
        for line in inp:
            if not line.strip():
                continue
            rec = json.loads(line)
            rid = rec.get("id") or ""
            if rid in mk_to_fixes:
                meta = dict(rec.get("meta") or {})
                for fx in mk_to_fixes[rid]:
                    if fx["field"] == "message_title":
                        meta["title"] = fx["new"]
                    elif fx["field"] == "message_number":
                        meta["msg_no"] = int(fx["new"]) if str(fx["new"]).isdigit() else fx["new"]
                    elif fx["field"] == "book_title":
                        # outline SoT：改 meta.book + book_path 末段（保留序号前缀）
                        # 字段级 chunks 仍保持 chunk.book_path 不变（见 5c）
                        old_b, new_b = fx["old"], fx["new"]
                        if (meta.get("book") or "") == old_b:
                            meta["book"] = new_b
                        elif old_b in (meta.get("book") or ""):
                            meta["book"] = (meta.get("book") or "").replace(old_b, new_b, 1)
                        else:
                            meta["book"] = new_b
                        bp = list(meta.get("book_path") or [])
                        if bp:
                            last = bp[-1]
                            if old_b in last:
                                bp[-1] = last.replace(old_b, new_b, 1)
                            else:
                                import re as _re
                                m = _re.match(r"^(\d+\s+)(.*)$", last)
                                bp[-1] = (m.group(1) + new_b) if m else new_b
                            meta["book_path"] = bp
                rec["meta"] = meta
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # regen from new outline and compare
    regen_new = STAGING_DIR / "chunks_12490.regen.json"
    logging.info("regen from outline.new...")
    regen_chunks_from_outline(outline_new, regen_new)
    # Compare only affected fields may differ in book_path etc — full compare
    new_vs_regen = compare_jsonl(new_chunks_path, regen_new)

    # If full regen differs (e.g. book_path side effects on year), also compare restricted fields for affected
    # User asked: must be identical if repro was identical. Report honestly.

    # changes_by_chunk.csv
    chg_path = STAGING_DIR / "changes_by_chunk.csv"
    with chg_path.open("w", encoding="utf-8-sig", newline="") as fp:
        cols = ["chunk_id", "message_key", "book", "msg_no", "field", "old", "new"]
        w = csv.DictWriter(fp, fieldnames=cols)
        w.writeheader()
        for r in changes_rows:
            w.writerow(r)

    reembed_path = STAGING_DIR / "reembed_ids.txt"
    reembed_ids_sorted = sorted(set(reembed_ids))
    reembed_path.write_text("\n".join(reembed_ids_sorted) + ("\n" if reembed_ids_sorted else ""), encoding="utf-8")

    # 4. vec_plan — stream old vec
    logging.info("building vec_plan (stream vec)...")
    new_by_cid = {}
    with new_chunks_path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            new_by_cid[o["chunk_id"]] = o

    vec_plan_rows = []
    action_counts = Counter()
    copy_text_ok = copy_text_fail = 0
    with vec_src.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            vo = json.loads(line)
            cid = vo["chunk_id"]
            nobj = new_by_cid.get(cid)
            if nobj is None:
                continue
            old_text = vo.get("text") or ""
            new_text = nobj.get("text") or ""
            # number-only change?
            mk = nobj.get("message_key") or ""
            fields = {fx["field"] for fx in fixes_by_mk.get(mk, [])}
            if cid not in affected_cids:
                action = "copy_embedding"
            elif fields <= {"message_number"}:
                action = "copy_embedding_update_meta"
            elif old_text == new_text:
                action = "copy_embedding"
            else:
                action = "reembed"
            action_counts[action] += 1
            vec_plan_rows.append({"chunk_id": cid, "action": action})
            if action == "copy_embedding" and cid in affected_cids:
                # still verify
                pass
            if action.startswith("copy"):
                if old_text == new_text:
                    copy_text_ok += 1
                else:
                    # for copy_embedding_update_meta text same; for copy on unaffected same
                    if action == "copy_embedding_update_meta" and old_text == new_text:
                        copy_text_ok += 1
                    elif action == "copy_embedding" and old_text == new_text:
                        copy_text_ok += 1
                    else:
                        copy_text_fail += 1

    # h: for ALL copy_embedding actions, verify old vec text == new chunks text
    logging.info("verify copy_embedding text match (stream)...")
    copy_verify_ok = copy_verify_fail = 0
    reembed_set_plan = set()
    copy_set = set()
    plan_by_cid = {r["chunk_id"]: r["action"] for r in vec_plan_rows}
    # rebuild plan more carefully in one more pass? We have plan_by_cid
    with vec_src.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            vo = json.loads(line)
            cid = vo["chunk_id"]
            action = plan_by_cid.get(cid, "copy_embedding")
            nobj = new_by_cid[cid]
            if action == "reembed":
                reembed_set_plan.add(cid)
            else:
                copy_set.add(cid)
                if (vo.get("text") or "") == (nobj.get("text") or ""):
                    copy_verify_ok += 1
                else:
                    copy_verify_fail += 1

    vec_plan_path = STAGING_DIR / "vec_plan.csv"
    with vec_plan_path.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=["chunk_id", "action"])
        w.writeheader()
        for cid in sorted(plan_by_cid):
            w.writerow({"chunk_id": cid, "action": plan_by_cid[cid]})

    # 5. self checks
    logging.info("self-checks...")
    checks = {}
    # reload new as stream vs old
    fail_5a = fail_5b = fail_5c = 0
    immutable = {
        "chunk_id", "message_key", "source_path", "book_path", "batch",
        "chunk_index", "chunk_total", "para_nos", "point_count", "min_level", "paragraph_type",
    }
    allowed_change = {"text", "message_title", "book_title", "message_number", "tokens"}
    n_new = 0
    mk_set_new = set()
    mk_counts_new = Counter()
    mk_counts_old = Counter()
    for cid, o in by_cid.items():
        mk_counts_old[o.get("message_key") or ""] += 1

    with new_chunks_path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            nobj = json.loads(line)
            n_new += 1
            cid = nobj["chunk_id"]
            old = by_cid[cid]
            mk = nobj.get("message_key") or ""
            mk_set_new.add(mk)
            mk_counts_new[mk] += 1
            if cid not in affected_cids:
                if nobj != old:
                    fail_5a += 1
            else:
                changed = {k for k in set(old) | set(nobj) if old.get(k) != nobj.get(k)}
                if not changed <= allowed_change:
                    fail_5b += 1
                # text only first line
                ot, nt = (old.get("text") or ""), (nobj.get("text") or "")
                if ot != nt:
                    o_rest = ot.split("\n", 1)[1] if "\n" in ot else ""
                    n_rest = nt.split("\n", 1)[1] if "\n" in nt else ""
                    if o_rest != n_rest:
                        fail_5b += 1
                for k in immutable:
                    if old.get(k) != nobj.get(k):
                        fail_5c += 1

    checks["5a_unaffected_identical_fail"] = fail_5a
    checks["5b_affected_fields_or_body_fail"] = fail_5b
    checks["5c_immutable_fail"] = fail_5c
    checks["5d_n_chunks"] = n_new
    checks["5d_n_mk"] = len(mk_set_new)
    checks["5d_mk_count_mismatch"] = sum(1 for mk in mk_counts_old if mk_counts_old[mk] != mk_counts_new.get(mk, 0))

    # 5e unique (book_title, message_number) — 生命读经范围；全集预存冲突仅作对照
    def _pair_conflicts(path: Path, life_only: bool) -> tuple[int, list]:
        seen: dict = {}
        conflicts = []
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                o = json.loads(line)
                if o.get("chunk_index") != 1:
                    continue
                bt = o.get("book_title") or ""
                if life_only and "生命读经" not in bt:
                    continue
                key = (bt, o.get("message_number"))
                if key in seen:
                    conflicts.append((key, seen[key], o.get("message_key")))
                else:
                    seen[key] = o.get("message_key")
        return len(conflicts), conflicts[:10]

    life_conf_new, life_samples = _pair_conflicts(new_chunks_path, True)
    life_conf_old, _ = _pair_conflicts(chunks_src, True)
    all_conf_new, _ = _pair_conflicts(new_chunks_path, False)
    all_conf_old, _ = _pair_conflicts(chunks_src, False)
    checks["5e_life_pair_conflicts_new"] = life_conf_new
    checks["5e_life_pair_conflicts_old"] = life_conf_old
    checks["5e_all_pair_conflicts_new"] = all_conf_new
    checks["5e_all_pair_conflicts_old"] = all_conf_old
    checks["5e_pair_conflicts"] = life_conf_new  # 判定用：生命读经必须 0
    checks["5e_life_samples"] = life_samples
    # 附录 message_number=3 专检
    est_keys = [
        (o.get("book_title"), o.get("message_number"), o.get("message_key"))
        for o in new_by_cid.values()
        if o.get("chunk_index") == 1 and (o.get("book_title") or "") == "以斯帖记生命读经"
    ]
    checks["5e_esther_pairs"] = sorted(est_keys, key=lambda x: (x[1] is None, x[1] or 0))

    # 5f header
    fail_5f = 0
    for cid in text_changed_cids:
        o = new_by_cid[cid]
        first = (o.get("text") or "").split("\n", 1)[0]
        expect = render_header(o.get("book_title"), o.get("message_title"))
        if first != expect:
            fail_5f += 1
    checks["5f_header_fail"] = fail_5f

    # 5g sets equal
    reembed_file_set = set(reembed_ids_sorted)
    text_set = set(text_changed_cids)
    checks["5g_reembed_eq_plan"] = reembed_file_set == reembed_set_plan
    checks["5g_reembed_eq_text"] = reembed_file_set == text_set
    checks["5g_plan_eq_text"] = reembed_set_plan == text_set

    checks["5h_copy_verify_ok"] = copy_verify_ok
    checks["5h_copy_verify_fail"] = copy_verify_fail

    # 5i cost
    reembed_chars = sum(len(new_by_cid[cid].get("text") or "") for cid in reembed_file_set)
    cost = len(reembed_file_set) / 1000.0 * 0.002
    checks["5i_reembed_n"] = len(reembed_file_set)
    checks["5i_reembed_chars"] = reembed_chars
    checks["5i_cost"] = cost

    # 6 char stats on NEW life titles
    half_paren = []
    em_dash = box_dash = 0
    seen_mk = set()
    with new_chunks_path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            mk = o.get("message_key") or ""
            if mk in seen_mk:
                continue
            bt = o.get("book_title") or ""
            if "生命读经" not in bt:
                continue
            seen_mk.add(mk)
            mt = o.get("message_title") or ""
            if "(" in mt or ")" in mt:
                half_paren.append((bt, o.get("message_number"), mt))
            if "—" in mt:
                em_dash += 1
            if "─" in mt:
                box_dash += 1

    # staging file list
    staging_files = []
    for dirpath, _d, names in os.walk(STAGING_DIR):
        for name in names:
            p = Path(dirpath) / name
            try:
                st = p.stat()
                staging_files.append((str(p.relative_to(STAGING_DIR)), st.st_size))
            except OSError:
                pass
    staging_files.sort()

    # number / title / book counts in rows
    field_c = Counter(r["field"] for r in rows)

    return {
        "outline_field_info": outline_field_info,
        "repro_cmp": repro_cmp,
        "cli_cmp": cli_cmp,
        "new_vs_regen": new_vs_regen,
        "n_written": n_written,
        "affected_cids": affected_cids,
        "text_changed_cids": text_changed_cids,
        "reembed_ids": reembed_ids_sorted,
        "action_counts": dict(action_counts),
        "checks": checks,
        "half_paren": half_paren,
        "em_dash": em_dash,
        "box_dash": box_dash,
        "staging_files": staging_files,
        "field_c": dict(field_c),
        "uniq_msgs": len({r["message_key"] for r in rows}),
        "copy_verify_ok": copy_verify_ok,
        "copy_verify_fail": copy_verify_fail,
        "n_mk_old": len(mk_counts_old),
    }


def write_report(rows: list[dict], backup_info: dict, dry: dict, log_path: Path) -> None:
    lines: list[str] = []
    def w(s: str = "") -> None:
        lines.append(s)

    field_c = Counter(r["field"] for r in rows)
    w("# 生命读经修订 阶段0备份 + 阶段1干跑")
    w("")
    w(f"> 生成：{datetime.now().isoformat(timespec='seconds')}；日志：`{log_path}`；清单：`{FINAL_V4}`。")
    w("")
    w("## 结论摘要")
    w("")
    w(
        f"(1) **清单 v4**：{len(rows)} 条（title={field_c.get('message_title',0)} / "
        f"book={field_c.get('book_title',0)} / number={field_c.get('message_number',0)}）；"
        f"相对「约78」差 {len(rows)-78}（剔除撒母耳#9，加 review6+srey3）。"
    )
    w(
        f"(2) **备份**：`{BACKUP_DIR}`；5 个源文件 SHA256 与源一致；"
        f"ES 导出 {backup_info.get('exported')} 条 = 受影响唯一块 {len(backup_info.get('affected_cids') or [])}。"
    )
    w(
        f"(3) **outline 字段**：meta.title / meta.msg_no / book_title←book_path；"
        f"复现性（build_message_chunks）：same={dry['repro_cmp']['same']} diff={dry['repro_cmp']['diff']}；"
        f"CLI={'有' if dry.get('cli_cmp') else '无'} "
        f"{'(same='+str(dry['cli_cmp']['same'])+' diff='+str(dry['cli_cmp']['diff'])+')' if dry.get('cli_cmp') else ''}。"
    )
    w(
        f"(4) **改后**：受影响唯一块={len(dry['affected_cids'])} 篇≈{dry['uniq_msgs']}；"
        f"reembed={len(dry['reembed_ids'])}；"
        f"vec_plan={dry['action_counts']}。"
    )
    ch = dry["checks"]
    all_ok = (
        ch["5a_unaffected_identical_fail"] == 0
        and ch["5b_affected_fields_or_body_fail"] == 0
        and ch["5c_immutable_fail"] == 0
        and ch["5d_n_chunks"] == 55841
        and ch["5d_n_mk"] == 12328
        and ch["5d_mk_count_mismatch"] == 0
        and ch["5e_pair_conflicts"] == 0
        and ch["5e_life_pair_conflicts_old"] == 0
        and ch["5e_all_pair_conflicts_new"] == ch["5e_all_pair_conflicts_old"]
        and ch["5f_header_fail"] == 0
        and ch["5g_reembed_eq_plan"] and ch["5g_reembed_eq_text"] and ch["5g_plan_eq_text"]
        and ch["5h_copy_verify_fail"] == 0
    )
    w(f"(5) **自检 5a–5i**：{'全部通过' if all_ok else '有失败'}（见明细）。")
    w(f"(6) **重算费用上限**：${ch['5i_cost']:.4f}（{ch['5i_reembed_n']} 块，{ch['5i_reembed_chars']} 字符）。")
    w(
        f"(7) **写法**：半角括号篇数={len(dry['half_paren'])}；—={dry['em_dash']}；─={dry['box_dash']}（期望0）。"
    )
    w(f"(8) **暂存**：`{STAGING_DIR}` 文件 {len(dry['staging_files'])} 个。")
    w("")

    w("## 1. 清单 v4")
    w("")
    w(f"- 路径：`{FINAL_V4}`")
    w(f"- 条数={len(rows)}；field={dict(field_c)}；source={dict(Counter(r['source'] for r in rows))}")
    w("- 不含撒母耳记 #9（题醒）。")
    w("")

    w("## 2. 阶段0 备份")
    w("")
    w(f"- 目录：`{BACKUP_DIR}`")
    for name, h, size in backup_info.get("sums") or []:
        w(f"- `{name}` sha256=`{h}` size={size}")
    w(f"- affected 行={len(backup_info.get('affected') or [])} 唯一块={len(backup_info.get('affected_cids') or [])}")
    w(f"- es_before_affected.jsonl={backup_info.get('exported')}")
    w(f"- ES count {backup_info.get('count_before')}/{backup_info.get('count_after')}")
    w(f"- 纲目JSON 快照 {backup_info.get('snap_before')} → {backup_info.get('snap_after')}")
    w("")

    w("## 3. outline 字段与复现性")
    w("")
    for k, v in dry["outline_field_info"].items():
        w(f"- **{k}**：{v}")
    w("")
    w("### 复现性（旧 outline → chunks）")
    rc = dry["repro_cmp"]
    w(f"- build_message_chunks：n_a={rc['n_a']} n_b={rc['n_b']} same={rc['same']} diff={rc['diff']} field_diffs={rc['field_diffs']}")
    if rc["samples"]:
        w("- 差异样例：")
        for cid, brief in rc["samples"][:10]:
            w(f"  - `{cid}` {brief}")
    if dry.get("cli_cmp"):
        cc = dry["cli_cmp"]
        w(f"- CLI build_chunks：same={cc['same']} diff={cc['diff']} field_diffs={cc['field_diffs']}")
    w("")
    w("### outline.new → regen vs field-edit new")
    nr = dry["new_vs_regen"]
    w(f"- same={nr['same']} diff={nr['diff']} field_diffs={nr['field_diffs']}")
    w(
        "- 说明：diff 若仅 `book_path`，属预期——"
        "字段级改块按 5c **不改** chunk.book_path；"
        "outline.new 为 SoT 已改 meta.book_path 末段，故 regen 的 book_path 不同。"
        "title/number 类应 same；book 类 book_title/text 应与字段级一致。"
    )
    if nr["samples"]:
        for cid, brief in nr["samples"][:10]:
            w(f"  - `{cid}` {brief}")
    # 确认 book 类 diff 是否只含 book_path
    only_bp = nr["field_diffs"] == {"book_path": nr["diff"]} if nr["diff"] else True
    w(f"- diff 是否仅 book_path：{only_bp}（field_diffs={nr['field_diffs']}）")
    w("")

    w("## 4. 改后统计")
    w("")
    w(f"- chunks 总数={dry['n_written']}")
    w(f"- 受影响唯一块={len(dry['affected_cids'])}；text 变化(reembed)={len(dry['reembed_ids'])}")
    w(f"- vec_plan actions={dry['action_counts']}")
    w("")

    w("## 5. 自检")
    w("")
    for k, v in sorted(ch.items()):
        w(f"- {k} = {v}")
    w(f"- copy_verify fail={dry['copy_verify_fail']} ok={dry['copy_verify_ok']}")
    w("")

    w("## 6. 费用")
    w("")
    w(f"- reembed 块={ch['5i_reembed_n']} 字符={ch['5i_reembed_chars']} 上限=${ch['5i_cost']:.4f}")
    w("")

    w("## 7. 写法统计（修改后生命读经篇题）")
    w("")
    w(f"- 半角括号篇数={len(dry['half_paren'])}（前20）：")
    for bt, mno, mt in dry["half_paren"][:20]:
        w(f"  - {bt} #{mno} `{mt[:60]}`")
    w(f"- 「—」篇数={dry['em_dash']}；「─」篇数={dry['box_dash']}")
    w("")

    w("## 8. 暂存文件")
    w("")
    for rel, size in dry["staging_files"]:
        w(f"- `{rel}` size={size}")
    w("")

    w("## 验证")
    w("")
    w(f"1. 原文件 SHA256 与备份一致（见备份 SHA256SUMS）；纲目JSON 快照={backup_info.get('snap_after')} 期望={EXPECTED_SNAP} ok={backup_info.get('snap_after')==EXPECTED_SNAP}")
    w(f"2. ES count={backup_info.get('count_after')}（55841={backup_info.get('count_after')==55841}）；本轮只用 count/mget")
    w(f"3. 备份导出条数={backup_info.get('exported')} == 受影响块={len(backup_info.get('affected_cids') or [])}")
    w("4. v4 每条 old==当前值（构建时断言失败数0）；无撒母耳#9")
    w(f"5. 自检全过={all_ok}")
    w("6. git:")
    w("```")
    w(_git_status())
    w("```")
    w("7. 未调用嵌入接口、未读取/打印/保存任何密钥、未写任何 ES。")
    w("")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("wrote report %s", REPORT_PATH)


# ---------------------------------------------------------------------------
# Stage 2
# ---------------------------------------------------------------------------

def stage_prepare(log_path: Path) -> dict:
    """P1 book_path 对齐 + P2 自检 + P3 embed_jobs。"""
    logging.info("=== STAGE prepare ===")
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    chunks_new = STAGING_DIR / "chunks_12490.new.json"
    outline_new = STAGING_DIR / "outline_12490.new.json"
    if not chunks_new.exists() or not outline_new.exists():
        raise GateFail("G1", "缺少 chunks_12490.new.json 或 outline_12490.new.json")

    aff = _load_affected()
    book_cids = _book_path_cids(aff)
    if len(book_cids) != 52:
        raise GateFail("G1", f"book_title 受影响块应为 52，实际 {len(book_cids)}")

    # P1: 更新 book_path 末段
    tmp = STAGING_DIR / "chunks_12490.new.json.tmp"
    changed = 0
    n_written = 0
    with chunks_new.open(encoding="utf-8") as inp, tmp.open("w", encoding="utf-8", newline="\n") as out:
        for line in inp:
            if not line.strip():
                continue
            obj = json.loads(line)
            cid = obj["chunk_id"]
            if cid in book_cids:
                bp = list(obj.get("book_path") or [])
                if bp:
                    last = bp[-1]
                    new_last = BOOK_PATH_REPLACEMENTS.get(last, last)
                    if new_last != last:
                        bp[-1] = new_last
                        obj["book_path"] = bp
                        changed += 1
                    elif last not in BOOK_PATH_REPLACEMENTS.values():
                        raise GateFail("G1", f"book_path 末段无法映射 cid={cid} last={last!r}")
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n_written += 1
    os.replace(tmp, chunks_new)
    logging.info("P1 book_path updated changed=%s / expected_upto=52 n=%s", changed, n_written)

    # regen from outline.new
    regen = STAGING_DIR / "chunks_12490.regen.json"
    logging.info("P1 regen from outline.new...")
    regen_chunks_from_outline(outline_new, regen)
    cmp = compare_jsonl(chunks_new, regen)
    logging.info("P1 compare same=%s diff=%s", cmp["same"], cmp["diff"])
    if cmp["same"] != 55841 or cmp["diff"] != 0:
        raise GateFail("G1", f"regen vs new 必须 same=55841 diff=0，实际 same={cmp['same']} diff={cmp['diff']}", {"cmp": cmp})

    # P2: 自检 5a–5i（book_path 对 52 块放开）
    old_chunks = BACKUP_DIR / "chunks_12490.json"
    if not old_chunks.exists():
        old_chunks = OUT_DIR / "chunks_12490.json"
    by_old, _mk = load_chunks_index(old_chunks)
    aff_cids = _affected_cids(aff)
    reembed_ids = set(_load_reembed_ids())
    immutable = {
        "chunk_id", "message_key", "source_path", "batch",
        "chunk_index", "chunk_total", "para_nos", "point_count", "min_level", "paragraph_type",
    }
    # book_path 对 52 放开；其余不变
    allowed_change = {"text", "message_title", "book_title", "message_number", "tokens", "book_path"}
    fail_5a = fail_5b = fail_5c = fail_5f = 0
    n_new = 0
    mk_set = set()
    mk_counts_new = Counter()
    mk_counts_old = Counter()
    for o in by_old.values():
        mk_counts_old[o.get("message_key") or ""] += 1
    new_by = {}
    text_changed = set()
    with chunks_new.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            nobj = json.loads(line)
            n_new += 1
            cid = nobj["chunk_id"]
            new_by[cid] = nobj
            mk = nobj.get("message_key") or ""
            mk_set.add(mk)
            mk_counts_new[mk] += 1
            old = by_old[cid]
            if cid not in aff_cids and cid not in book_cids:
                # 未受影响：逐字段相同（book_path 也不变）
                if nobj != old:
                    fail_5a += 1
            else:
                changed_fields = {k for k in set(old) | set(nobj) if old.get(k) != nobj.get(k)}
                # book_path 只允许 book_cids
                if "book_path" in changed_fields and cid not in book_cids:
                    fail_5c += 1
                allowed = set(allowed_change)
                if cid not in book_cids:
                    allowed.discard("book_path")
                if not changed_fields <= allowed:
                    fail_5b += 1
                ot, nt = (old.get("text") or ""), (nobj.get("text") or "")
                if ot != nt:
                    text_changed.add(cid)
                    o_rest = ot.split("\n", 1)[1] if "\n" in ot else ""
                    n_rest = nt.split("\n", 1)[1] if "\n" in nt else ""
                    if o_rest != n_rest:
                        fail_5b += 1
                for k in immutable:
                    if old.get(k) != nobj.get(k):
                        fail_5c += 1
                # book_path：非 book 块必须不变
                if cid not in book_cids and old.get("book_path") != nobj.get("book_path"):
                    fail_5c += 1

    for cid in text_changed:
        o = new_by[cid]
        first = (o.get("text") or "").split("\n", 1)[0]
        expect = render_header(o.get("book_title"), o.get("message_title"))
        if first != expect:
            fail_5f += 1

    # 5d
    mk_mismatch = sum(1 for mk in mk_counts_old if mk_counts_old[mk] != mk_counts_new.get(mk, 0))
    # 5e life uniqueness
    seen_pair = {}
    life_conf = 0
    for o in new_by.values():
        if o.get("chunk_index") != 1:
            continue
        bt = o.get("book_title") or ""
        if "生命读经" not in bt:
            continue
        key = (bt, o.get("message_number"))
        if key in seen_pair:
            life_conf += 1
        else:
            seen_pair[key] = o.get("message_key")

    # 5g via vec_plan
    plan = _load_vec_plan()
    reembed_plan = {cid for cid, act in plan.items() if act == "reembed"}
    g5g_ok = reembed_plan == reembed_ids == text_changed

    # 5h stream old vec: copy* text match
    vec_src = BACKUP_DIR / "chunks_12490_vec.json"
    if not vec_src.exists():
        vec_src = OUT_DIR / "chunks_12490_vec.json"
    copy_fail = 0
    copy_ok = 0
    with vec_src.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            vo = json.loads(line)
            cid = vo["chunk_id"]
            act = plan.get(cid, "copy_embedding")
            if act == "reembed":
                continue
            if (vo.get("text") or "") == (new_by[cid].get("text") or ""):
                copy_ok += 1
            else:
                copy_fail += 1

    reembed_chars = sum(len(new_by[cid].get("text") or "") for cid in reembed_ids)
    checks = {
        "5a_fail": fail_5a,
        "5b_fail": fail_5b,
        "5c_fail": fail_5c,
        "5d_n": n_new,
        "5d_mk": len(mk_set),
        "5d_mk_mismatch": mk_mismatch,
        "5e_life_conf": life_conf,
        "5f_fail": fail_5f,
        "5g_ok": g5g_ok,
        "5h_copy_fail": copy_fail,
        "5h_copy_ok": copy_ok,
        "5i_reembed_n": len(reembed_ids),
        "5i_chars": reembed_chars,
        "book_path_changed": changed,
        "book_cids": len(book_cids),
    }
    p2_ok = (
        fail_5a == 0 and fail_5b == 0 and fail_5c == 0 and fail_5f == 0
        and n_new == 55841 and len(mk_set) == 12328 and mk_mismatch == 0
        and life_conf == 0 and g5g_ok and copy_fail == 0
        and len(reembed_ids) == EXPECTED_REEMBED_N
    )
    if not p2_ok:
        raise GateFail("G1", "P2 自检未全过", checks)

    # P3 embed_jobs.jsonl
    # need old text from old chunks
    jobs_path = STAGING_DIR / "embed_jobs.jsonl"
    jobs = []
    with jobs_path.open("w", encoding="utf-8", newline="\n") as out:
        for cid in sorted(reembed_ids):
            nobj = new_by[cid]
            oobj = by_old[cid]
            nt = nobj.get("text") or ""
            ot = oobj.get("text") or ""
            row = {
                "chunk_id": cid,
                "text": nt,
                "old_text_prefix60": ot[:60],
                "new_text_prefix60": nt[:60],
                "chars": len(nt),
            }
            jobs.append(row)
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    job_ids = {j["chunk_id"] for j in jobs}
    if job_ids != reembed_ids or len(jobs) != EXPECTED_REEMBED_N:
        raise GateFail(
            "G1",
            f"P3 集合/条数不符 jobs={len(jobs)} expected={EXPECTED_REEMBED_N}",
            {"only_jobs": sorted(job_ids - reembed_ids)[:5], "only_re": sorted(reembed_ids - job_ids)[:5]},
        )
    total_chars = sum(j["chars"] for j in jobs)
    chars_note = ""
    if total_chars != EXPECTED_REEMBED_CHARS:
        chars_note = (
            f"字符数={total_chars}（阶段1为 {EXPECTED_REEMBED_CHARS}）；"
            f"P1 只改 book_path，text 不应变——若不同需排查"
        )
        # text 不应因 book_path 改变；若不同则失败
        # 但允许若阶段1统计口径不同；严格：与当前 new 文本一致即可，条数必须 343
        # 用户：若因 P1 改 book_path 使数字不同，说明原因——text 不应变
        # 所以若不同，说明有问题
        raise GateFail("G1", f"P3 字符数异常：{chars_note}", {"chars": total_chars})

    result = {
        "cmp": cmp,
        "checks": checks,
        "jobs_n": len(jobs),
        "jobs_chars": total_chars,
        "book_path_changed": changed,
        "p2_ok": p2_ok,
        "log_path": str(log_path),
    }
    lines = [
        "# 生命读经修订 阶段2 prepare",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- P1 book_path 更新块数={changed}（期望 52）；regen vs new same={cmp['same']} diff={cmp['diff']}",
        f"- P2 自检全过={p2_ok}；明细={checks}",
        f"- P3 embed_jobs.jsonl 条数={len(jobs)} 字符={total_chars}；集合==reembed_ids",
        f"- **闸门 G1：通过**",
        "",
    ]
    _write_stage_report("prepare", lines)
    return result


def _prepare_embedding_adapter(secrets: list[str]):
    """load_dotenv 后刷新 adapter 模块级密钥（不读 .env 文件内容）。"""
    load_dotenv(_backend_env())
    import kg_rag.embedding_adapter as ea
    ea.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    ea.OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", ea.OPENROUTER_BASE_URL)
    ea.EMBEDDING_KG_MODEL = os.getenv("EMBEDDING_KG_MODEL", ea.EMBEDDING_KG_MODEL)
    try:
        ea.EMBEDDING_KG_DIMS = int(os.getenv("EMBEDDING_KG_DIMS", str(ea.EMBEDDING_KG_DIMS)))
    except ValueError:
        pass
    if not ea.OPENROUTER_API_KEY:
        raise GateFail("G2", "OPENROUTER_API_KEY 未配置（通过 embedding_adapter 环境变量）")
    return ea


def _is_retryable_embed(exc: BaseException) -> tuple[bool, str]:
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return True, "timeout"
    if "connection" in text or "network" in text:
        return True, "network"
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True, "429"
    if isinstance(status, int) and status >= 500:
        return True, "5xx"
    return False, type(exc).__name__


async def _embed_batch(texts: list[str], secrets: list[str]) -> list[list[float]]:
    from kg_rag.embedding_adapter import get_embeddings
    last_exc = None
    for attempt in range(len(EMBED_RETRY_WAITS) + 1):
        try:
            return await get_embeddings(texts, profile="kg_rag")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            retryable, kind = _is_retryable_embed(exc)
            msg = _redact(str(exc), secrets)
            logging.warning("embed attempt=%s kind=%s err=%s", attempt + 1, kind, msg)
            if not retryable or attempt >= len(EMBED_RETRY_WAITS):
                raise GateFail("G2", f"embed 失败 kind={kind} err={msg}") from exc
            await asyncio.sleep(EMBED_RETRY_WAITS[attempt])
    raise GateFail("G2", _redact(str(last_exc), secrets))


async def _run_embed_jobs(jobs: list[dict], done_ids: set[str], out_path: Path, secrets: list[str]) -> dict:
    pending = [j for j in jobs if j["chunk_id"] not in done_ids]
    logging.info("embed pending=%s already_done=%s", len(pending), len(done_ids))
    sem = asyncio.Semaphore(EMBED_CONCURRENCY)
    lock = asyncio.Lock()
    written = 0
    usage_tokens = 0  # adapter 当前不返回 usage；占位
    batches = [pending[i:i + EMBED_BATCH] for i in range(0, len(pending), EMBED_BATCH)]

    async def one(batch: list[dict]) -> None:
        nonlocal written
        texts = [j["text"] for j in batch]
        async with sem:
            vectors = await _embed_batch(texts, secrets)
        if len(vectors) != len(batch):
            raise GateFail("G2", f"向量条数不符 got={len(vectors)} expect={len(batch)}")
        async with lock:
            with out_path.open("a", encoding="utf-8", newline="\n") as fp:
                for job, vec in zip(batch, vectors):
                    if not isinstance(vec, list) or len(vec) != EMBED_DIMS:
                        raise GateFail("G2", f"维数异常 cid={job['chunk_id']} dim={None if not isinstance(vec, list) else len(vec)}")
                    if any(isinstance(x, float) and (math.isnan(x) or math.isinf(x)) for x in vec):
                        raise GateFail("G2", f"NaN/Inf cid={job['chunk_id']}")
                    fp.write(json.dumps({"chunk_id": job["chunk_id"], "embedding": vec}, ensure_ascii=False) + "\n")
                    written += 1
            logging.info("embed progress written_this_run=%s / pending=%s", written, len(pending))

    await asyncio.gather(*[one(b) for b in batches])
    return {"written": written, "pending": len(pending), "usage_tokens": usage_tokens}


def stage_embed(log_path: Path) -> dict:
    logging.info("=== STAGE embed ===")
    jobs_path = STAGING_DIR / "embed_jobs.jsonl"
    if not jobs_path.exists():
        raise GateFail("G2", "缺少 embed_jobs.jsonl，请先跑 prepare")
    jobs = []
    with jobs_path.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                jobs.append(json.loads(line))
    n = len(jobs)
    chars = sum(int(j.get("chars") or len(j.get("text") or "")) for j in jobs)
    logging.info("E1 will embed n=%s chars=%s (expect n=%s chars=%s)", n, chars, EXPECTED_REEMBED_N, EXPECTED_REEMBED_CHARS)
    print(f"E1 will_embed n={n} chars={chars}", flush=True)
    if n != EXPECTED_REEMBED_N:
        raise GateFail("G2", f"条数不是 {EXPECTED_REEMBED_N}，实际 {n}")

    secrets_holder: list[str] = []
    load_dotenv(_backend_env())
    secrets_holder.extend(_secret_values())
    _prepare_embedding_adapter(secrets_holder)
    # refresh secrets after dotenv
    secrets_holder = _secret_values()

    results_path = STAGING_DIR / "embed_results.jsonl"
    done_ids: set[str] = set()
    if results_path.exists():
        with results_path.open(encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                obj = json.loads(line)
                done_ids.add(obj["chunk_id"])
        logging.info("resume: already have %s results", len(done_ids))

    env_names = [
        "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "EMBEDDING_KG_MODEL", "EMBEDDING_KG_DIMS",
    ]
    t0 = time.time()
    try:
        run_info = asyncio.run(_run_embed_jobs(jobs, done_ids, results_path, secrets_holder))
    except GateFail:
        raise
    except Exception as exc:  # noqa: BLE001
        raise GateFail("G2", _redact(str(exc), secrets_holder)) from exc

    # G2 verify
    got = {}
    with results_path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            cid = obj["chunk_id"]
            emb = obj.get("embedding")
            if cid in got:
                # 断点续跑可能重复；保留最后一条
                pass
            got[cid] = emb
    expect = {j["chunk_id"] for j in jobs}
    if set(got) != expect:
        raise GateFail("G2", f"结果集合不等 got={len(got)} expect={len(expect)}")
    bad = []
    for cid, emb in got.items():
        if not isinstance(emb, list) or len(emb) != EMBED_DIMS:
            bad.append((cid, "dim"))
        elif any(isinstance(x, float) and (math.isnan(x) or math.isinf(x)) for x in emb):
            bad.append((cid, "nan"))
    if bad:
        raise GateFail("G2", f"向量质量失败 {len(bad)}", {"bad": bad[:10]})

    # rewrite results uniquely (last wins) for clean file
    clean = STAGING_DIR / "embed_results.jsonl.tmp"
    with clean.open("w", encoding="utf-8", newline="\n") as fp:
        for cid in sorted(got):
            fp.write(json.dumps({"chunk_id": cid, "embedding": got[cid]}, ensure_ascii=False) + "\n")
    os.replace(clean, results_path)

    result = {
        "n": len(got),
        "chars": chars,
        "written_this_run": run_info["written"],
        "seconds": time.time() - t0,
        "usage_tokens": run_info.get("usage_tokens") or None,
        "env_var_names": env_names,
        "cost_by_chunks": len(got) / 1000.0 * COST_PER_1K_CHUNKS,
    }
    if result["usage_tokens"] == 0:
        result["usage_tokens"] = None
    lines = [
        "# 生命读经修订 阶段2 embed",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- E1 n={n} chars={chars}",
        f"- E3 embed_results.jsonl 条数={len(got)}；本轮新写={run_info['written']}；耗时={result['seconds']:.1f}s",
        f"- usage_tokens={result['usage_tokens']}（adapter 未返回则 None）",
        f"- 费用按 $0.002/千块 = ${result['cost_by_chunks']:.4f}",
        f"- embedding_adapter 环境变量名：{', '.join(env_names)}（不报告值）",
        f"- **闸门 G2：通过**",
        "",
    ]
    _write_stage_report("embed", lines)
    return result


def stage_assemble(log_path: Path) -> dict:
    logging.info("=== STAGE assemble ===")
    chunks_new = STAGING_DIR / "chunks_12490.new.json"
    results_path = STAGING_DIR / "embed_results.jsonl"
    vec_src = BACKUP_DIR / "chunks_12490_vec.json"
    if not vec_src.exists():
        vec_src = OUT_DIR / "chunks_12490_vec.json"
    if not results_path.exists():
        raise GateFail("G3", "缺少 embed_results.jsonl")

    plan = _load_vec_plan()
    reembed_ids = set(_load_reembed_ids())
    emb_map = {}
    with results_path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            emb_map[o["chunk_id"]] = o["embedding"]
    if set(emb_map) != reembed_ids:
        raise GateFail("G3", f"A2 embed_results 集合 ≠ reembed：got={len(emb_map)} expect={len(reembed_ids)}")

    new_by = _load_jsonl_index(chunks_new)
    tmp = STAGING_DIR / "chunks_12490_vec.new.json.tmp"
    n = 0
    action_counts = Counter()
    with vec_src.open(encoding="utf-8") as inp, tmp.open("w", encoding="utf-8", newline="\n") as out:
        for line in inp:
            if not line.strip():
                continue
            old = json.loads(line)
            cid = old["chunk_id"]
            act = plan.get(cid, "copy_embedding")
            action_counts[act] += 1
            base = dict(new_by[cid])
            if act == "reembed":
                base["embedding"] = emb_map[cid]
            else:
                # copy_embedding / copy_embedding_update_meta
                base["embedding"] = old["embedding"]
            out.write(json.dumps(base, ensure_ascii=False) + "\n")
            n += 1
    if n != 55841:
        raise GateFail("G3", f"组装条数 {n} ≠ 55841")

    # 暂存为 .tmp；verify_vec 通过后再 rename（闸门 G3）
    # 先跑内嵌 V1-V3 快速检查，失败则删 tmp
    result = {
        "n": n,
        "action_counts": dict(action_counts),
        "tmp": str(tmp),
        "log_path": str(log_path),
    }
    lines = [
        "# 生命读经修订 阶段2 assemble",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- 写出临时文件 `{tmp.name}` 条数={n}",
        f"- actions={dict(action_counts)}",
        f"- A2 集合断言通过（{len(emb_map)}）",
        "- 正式改名在 verify_vec 通过后执行（G3）",
        "",
    ]
    _write_stage_report("assemble", lines)
    # keep marker
    (STAGING_DIR / "assemble_tmp_ready.flag").write_text(tmp.name, encoding="utf-8")
    return result


def stage_verify_vec(log_path: Path) -> dict:
    logging.info("=== STAGE verify_vec ===")
    tmp = STAGING_DIR / "chunks_12490_vec.new.json.tmp"
    final = STAGING_DIR / "chunks_12490_vec.new.json"
    if not tmp.exists():
        # allow resume if final already exists from prior pass
        if final.exists():
            tmp = final
        else:
            raise GateFail("G4", "缺少 chunks_12490_vec.new.json.tmp，请先 assemble")

    chunks_new = STAGING_DIR / "chunks_12490.new.json"
    new_by = _load_jsonl_index(chunks_new)
    plan = _load_vec_plan()
    reembed_ids = set(_load_reembed_ids())
    aff = _load_affected()
    aff_cids = _affected_cids(aff)

    old_vec = BACKUP_DIR / "chunks_12490_vec.json"
    if not old_vec.exists():
        old_vec = OUT_DIR / "chunks_12490_vec.json"

    # V1
    ids = []
    id_set = set()
    dup = 0
    with tmp.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            cid = o["chunk_id"]
            ids.append(cid)
            if cid in id_set:
                dup += 1
            id_set.add(cid)
    if len(ids) != 55841 or dup or id_set != set(new_by):
        raise GateFail("G4", f"V1 失败 n={len(ids)} dup={dup} set_eq={id_set == set(new_by)}")

    # V2 field compare + header；V3 embedding；V4 cosine
    cosines = []
    cos_rows = []  # (cid, cos, mk, old_h, new_h)
    v2_fail = 0
    v3_copy_fail = 0
    v3_re_fail = 0
    v3_copy_ok = 0
    v3_re_ok = 0
    samples_book = []
    samples_title = []
    book_cids = _book_path_cids(aff)
    title_cids = {a["chunk_id"] for a in aff if a.get("field") == "message_title"}

    # stream both old and new vec aligned by reading old into selective map for needed only? 
    # For V3 copy equality we need old emb for non-reembed — stream old into dict of emb only for copy ids is still large.
    # Stream pairwise: both files are same order if assembled from old stream order.
    with old_vec.open(encoding="utf-8") as old_fp, tmp.open(encoding="utf-8") as new_fp:
        for old_line, new_line in zip(old_fp, new_fp):
            if not old_line.strip() or not new_line.strip():
                continue
            old = json.loads(old_line)
            new = json.loads(new_line)
            cid = new["chunk_id"]
            if old["chunk_id"] != cid:
                # fallback: shouldn't happen; break to map mode
                raise GateFail("G4", f"V3 顺序不一致 old={old['chunk_id']} new={cid}")
            base = new_by[cid]
            # V2: all fields except embedding
            for k, v in base.items():
                if new.get(k) != v:
                    v2_fail += 1
                    break
            # extra keys in new besides embedding+base?
            for k in new:
                if k == "embedding":
                    continue
                if k not in base:
                    v2_fail += 1
                    break
            first = (new.get("text") or "").split("\n", 1)[0]
            expect = render_header(new.get("book_title"), new.get("message_title"))
            if first != expect:
                v2_fail += 1

            emb = new.get("embedding") or []
            act = plan.get(cid, "copy_embedding")
            if act == "reembed":
                ok = (
                    isinstance(emb, list) and len(emb) == EMBED_DIMS
                    and not any(isinstance(x, float) and (math.isnan(x) or math.isinf(x)) for x in emb)
                )
                norm = math.sqrt(sum(x * x for x in emb)) if ok else 0.0
                if not ok or abs(norm - 1.0) > 1e-3:
                    # qwen embeddings may not be unit-normalized; user asked 模长在 1±1e-3
                    # If model doesn't L2-normalize, this will fail the gate — report honestly.
                    v3_re_fail += 1
                else:
                    v3_re_ok += 1
                old_emb = old.get("embedding") or []
                cos = _cosine(old_emb, emb)
                cosines.append(cos)
                ot = (old.get("text") or "").split("\n", 1)[0]
                nt = (new.get("text") or "").split("\n", 1)[0]
                cos_rows.append((cid, cos, new.get("message_key") or "", ot, nt))
                if cid in book_cids and len(samples_book) < 3:
                    samples_book.append((cid, ot, nt, cos, (old.get("text") or "").split("\n")[:2], (new.get("text") or "").split("\n")[:2]))
                if cid in title_cids and len(samples_title) < 3:
                    samples_title.append((cid, ot, nt, cos, (old.get("text") or "").split("\n")[:2], (new.get("text") or "").split("\n")[:2]))
            else:
                old_emb = old.get("embedding") or []
                if emb != old_emb:
                    v3_copy_fail += 1
                else:
                    v3_copy_ok += 1

    if v2_fail:
        raise GateFail("G4", f"V2 失败 {v2_fail}")
    # V3: copy must pass; reembed dims/nan must pass. Norm gate: check and report.
    # If norm fails widely, still GateFail per user V3.
    copy_expect = 55493 + 5  # copy + update_meta
    if v3_copy_fail or v3_copy_ok != copy_expect:
        raise GateFail("G4", f"V3 copy 失败 fail={v3_copy_fail} ok={v3_copy_ok} expect_ok={copy_expect}")
    if v3_re_fail or v3_re_ok != EXPECTED_REEMBED_N:
        # Diagnose norms
        raise GateFail(
            "G4",
            f"V3 reembed 失败 fail={v3_re_fail} ok={v3_re_ok}",
            {"hint": "模长或 NaN/维数"},
        )

    cosines_sorted = sorted(cosines)
    below = [r for r in cos_rows if r[1] < 0.80]
    dist = {
        "min": cosines_sorted[0] if cosines_sorted else None,
        "p1": _percentile(cosines_sorted, 0.01),
        "p5": _percentile(cosines_sorted, 0.05),
        "p50": _percentile(cosines_sorted, 0.50),
        "p95": _percentile(cosines_sorted, 0.95),
        "max": cosines_sorted[-1] if cosines_sorted else None,
        "n": len(cosines_sorted),
        "below_0_80": len(below),
    }
    if dist["min"] is None or dist["min"] < 0.80:
        raise GateFail(
            "G4",
            f"V4 最小余弦 {dist['min']} < 0.80；低于数={len(below)}",
            {"below": [(c, mk, oh[:40], nh[:40], cos) for c, cos, mk, oh, nh in below[:30]]},
        )

    # G3 rename
    if tmp != final:
        os.replace(tmp, final)
    logging.info("renamed to %s", final)

    result = {
        "v1_n": len(ids),
        "v2_fail": v2_fail,
        "v3_copy_ok": v3_copy_ok,
        "v3_re_ok": v3_re_ok,
        "cosine": dist,
        "samples_book": samples_book,
        "samples_title": samples_title,
        "below": below,
    }
    lines = [
        "# 生命读经修订 阶段2 verify_vec",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- V1 n={len(ids)} dup={dup} set_eq=True",
        f"- V2 fail={v2_fail}",
        f"- V3 copy_ok={v3_copy_ok} re_ok={v3_re_ok}",
        f"- V4 cosine min={dist['min']:.6f} p1={dist['p1']:.6f} p5={dist['p5']:.6f} p50={dist['p50']:.6f} p95={dist['p95']:.6f} max={dist['max']:.6f} below0.80={dist['below_0_80']}",
        "- V5 抽样 book:",
    ]
    for cid, ot, nt, cos, olines, nlines in samples_book:
        lines.append(f"  - `{cid}` cos={cos:.4f}")
        lines.append(f"    old: {olines}")
        lines.append(f"    new: {nlines}")
    lines.append("- V5 抽样 title:")
    for cid, ot, nt, cos, olines, nlines in samples_title:
        lines.append(f"  - `{cid}` cos={cos:.4f}")
        lines.append(f"    old: {olines}")
        lines.append(f"    new: {nlines}")
    lines += ["", "- **闸门 G3（改名）+ G4：通过**", ""]
    _write_stage_report("verify_vec", lines)
    (STAGING_DIR / "verify_vec.ok").write_text(
        json.dumps({"ok": True, "n": 55841, "reembed": EXPECTED_REEMBED_N, "ts": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False),
        encoding="utf-8",
    )
    return result


def stage_write_local(log_path: Path) -> dict:
    logging.info("=== STAGE write_local ===")
    from elasticsearch.helpers import bulk

    vec_new = STAGING_DIR / "chunks_12490_vec.new.json"
    chunks_new = STAGING_DIR / "chunks_12490.new.json"
    # W0 checks
    es, url = make_es()
    if url.rstrip("/") != ES_URL_ALLOWED:
        raise GateFail("G5", f"ES URL 必须为 {ES_URL_ALLOWED}，实际 {url}")
    cnt_before = es.count(index=ES_INDEX)["count"]
    if cnt_before != 55841:
        raise GateFail("G5", f"W0 count={cnt_before} ≠ 55841")

    # backup sha
    for line in (BACKUP_DIR / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        h, name = parts[0], parts[1]
        p = BACKUP_DIR / name
        if not p.exists() or sha256_file(p) != h:
            raise GateFail("G5", f"W0 备份 SHA 不一致 {name}")

    es_before = BACKUP_DIR / "es_before_affected.jsonl"
    with es_before.open(encoding="utf-8") as fp:
        es_n = sum(1 for ln in fp if ln.strip())
    if es_n != EXPECTED_AFFECTED_N:
        raise GateFail("G5", f"W0 es_before 条数 {es_n}")

    if not vec_new.exists():
        raise GateFail("G5", "W0 缺少 chunks_12490_vec.new.json（需 verify_vec 通过）")
    for req in ("chunks_12490.new.json", "vec_plan.csv", "reembed_ids.txt", "changes_by_chunk.csv"):
        if not (STAGING_DIR / req).exists():
            raise GateFail("G5", f"W0 缺少 {req}")

    aff = _load_affected()
    aff_cids = _affected_cids(aff)
    if len(aff_cids) != EXPECTED_AFFECTED_N:
        raise GateFail("G5", f"affected 唯一块 {len(aff_cids)}")

    # versions before
    vers_before = {}
    for i in range(0, len(sorted(aff_cids)), 100):
        batch = sorted(aff_cids)[i:i + 100]
        resp = es.mget(index=ES_INDEX, ids=batch, source=False)
        for doc in resp.get("docs") or []:
            if doc.get("found"):
                vers_before[doc["_id"]] = doc.get("_version")

    # load 348 docs from vec.new
    docs = []
    found = set()
    with vec_new.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            cid = o["chunk_id"]
            if cid in aff_cids:
                docs.append(o)
                found.add(cid)
    if found != aff_cids or len(docs) != EXPECTED_AFFECTED_N:
        raise GateFail("G5", f"取出受影响块 {len(docs)} / set_eq={found == aff_cids}")

    actions = []
    for o in docs:
        actions.append({
            "_op_type": "index",
            "_index": ES_INDEX,
            "_id": o["chunk_id"],
            "_source": _doc_for_es(o),
        })

    ok = fail = 0
    written_ids = []
    errors = []
    for i in range(0, len(actions), 50):
        batch = actions[i:i + 50]
        success, errs = bulk(
            es, batch, raise_on_error=False, raise_on_exception=False, request_timeout=180,
        )
        ok += success
        if errs:
            for item in errs:
                fail += 1
                err = item.get("index") or {}
                errors.append({"_id": err.get("_id"), "status": err.get("status"), "error": str(err.get("error"))[:200]})
            logging.error("bulk errors: %s", errors[-5:])
            raise GateFail("G5", f"W2 中途失败 fail={fail} 已成功约 {ok}", {"written": written_ids[-20:], "errors": errors[:10]})
        written_ids.extend(a["_id"] for a in batch)
        logging.info("bulk ok so far %s", ok)

    es.indices.refresh(index=ES_INDEX)
    cnt_after = es.count(index=ES_INDEX)["count"]
    if fail or ok != EXPECTED_AFFECTED_N or cnt_after != 55841:
        raise GateFail("G5", f"W3 失败 ok={ok} fail={fail} count={cnt_after}")

    vers_after = {}
    for i in range(0, len(sorted(aff_cids)), 100):
        batch = sorted(aff_cids)[i:i + 100]
        resp = es.mget(index=ES_INDEX, ids=batch, source=False)
        for doc in resp.get("docs") or []:
            if doc.get("found"):
                vers_after[doc["_id"]] = doc.get("_version")

    version_changed = sum(1 for cid in aff_cids if vers_before.get(cid) != vers_after.get(cid))
    result = {
        "ok": ok,
        "fail": fail,
        "count_before": cnt_before,
        "count_after": cnt_after,
        "version_changed": version_changed,
        "url": url,
    }
    lines = [
        "# 生命读经修订 阶段2 write_local",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- W0 通过；ES `{url}` index=`{ES_INDEX}`",
        f"- W1/W2 写入成功={ok} 失败={fail}",
        f"- W3 count before={cnt_before} after={cnt_after}",
        f"- _version 变化块数={version_changed} / {EXPECTED_AFFECTED_N}",
        "- **闸门 G5：通过**",
        "",
    ]
    _write_stage_report("write_local", lines)
    # persist versions for reconcile R7
    (STAGING_DIR / "write_versions.json").write_text(
        json.dumps({"before": vers_before, "after": vers_after, "count_before": cnt_before, "count_after": cnt_after}, ensure_ascii=False),
        encoding="utf-8",
    )
    return result


def stage_reconcile(log_path: Path) -> dict:
    logging.info("=== STAGE reconcile ===")
    es, url = make_es()
    chunks_new = STAGING_DIR / "chunks_12490.new.json"
    vec_new = STAGING_DIR / "chunks_12490_vec.new.json"
    new_by = _load_jsonl_index(chunks_new)
    aff_cids = _affected_cids()
    reembed_ids = set(_load_reembed_ids())

    # R1 scroll exclude embedding
    same = diff = 0
    diff_samples = []
    es_ids = set()
    resp = es.search(
        index=ES_INDEX,
        size=500,
        scroll="5m",
        _source={"excludes": ["embedding"]},
        query={"match_all": {}},
    )
    scroll_id = resp.get("_scroll_id")
    while True:
        hits = resp["hits"]["hits"]
        if not hits:
            break
        for h in hits:
            cid = h["_id"]
            es_ids.add(cid)
            src = h.get("_source") or {}
            base = new_by.get(cid)
            if base is None:
                diff += 1
                if len(diff_samples) < 20:
                    diff_samples.append((cid, "missing_in_new", None))
                continue
            ok = True
            for k, v in base.items():
                if src.get(k) != v:
                    ok = False
                    break
            # ES may omit nulls; compare carefully for keys in base
            if ok:
                same += 1
            else:
                diff += 1
                if len(diff_samples) < 20:
                    changed = {k: (base.get(k), src.get(k)) for k in base if base.get(k) != src.get(k)}
                    # brief
                    brief = {k: (repr(a)[:40], repr(b)[:40]) for k, (a, b) in list(changed.items())[:5]}
                    diff_samples.append((cid, brief, None))
        resp = es.scroll(scroll_id=scroll_id, scroll="5m")
        scroll_id = resp.get("_scroll_id")
    try:
        es.clear_scroll(scroll_id=scroll_id)
    except Exception:  # noqa: BLE001
        pass
    if diff != 0 or same != 55841:
        raise GateFail("G6", f"R1 same={same} diff={diff}", {"samples": diff_samples})

    # R2 embeddings: all 348 affected + 300 random others
    rng = random.Random(20261106)
    other = [cid for cid in new_by if cid not in aff_cids]
    sample_other = rng.sample(other, 300)
    check_ids = sorted(aff_cids) + sample_other
    # load needed emb from vec.new
    need = set(check_ids)
    vec_emb = {}
    with vec_new.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            cid = o["chunk_id"]
            if cid in need:
                vec_emb[cid] = o.get("embedding")
                if len(vec_emb) == len(need):
                    break
    emb_mismatch = []
    for i in range(0, len(check_ids), 50):
        batch = check_ids[i:i + 50]
        resp = es.mget(index=ES_INDEX, ids=batch, source=["embedding"])
        for doc in resp.get("docs") or []:
            cid = doc["_id"]
            if not doc.get("found"):
                emb_mismatch.append((cid, "missing"))
                continue
            e1 = (doc.get("_source") or {}).get("embedding") or []
            e2 = vec_emb.get(cid) or []
            if e1 != e2:
                emb_mismatch.append((cid, f"len {len(e1)}/{len(e2)}"))
    if emb_mismatch:
        raise GateFail("G6", f"R2 embedding 不同 {len(emb_mismatch)}", {"samples": emb_mismatch[:20]})

    # R3 id sets
    vec_ids = set()
    with vec_new.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                vec_ids.add(json.loads(line)["chunk_id"])
    if not (set(new_by) == vec_ids == es_ids) or len(es_ids) != 55841:
        raise GateFail("G6", f"R3 集合不等 |new|={len(new_by)} |vec|={len(vec_ids)} |es|={len(es_ids)}")
    mk_counts = Counter(o.get("message_key") for o in new_by.values())
    if len(mk_counts) != 12328:
        raise GateFail("G6", f"R3 message_key 数 {len(mk_counts)}")

    # R4 knn self-match
    def find_cid(substr: str) -> Optional[str]:
        for cid, o in new_by.items():
            if substr in (o.get("message_key") or "") and o.get("chunk_index") == 1:
                return cid
        return None

    knn_targets = []
    for label, substr in [
        ("雅歌", "雅歌书生命读经/msg. 1 "),
        ("约翰二书", "约翰二书生命读经_/msg. 1 "),
        ("创98", "创世记生命读经/msg. 98 "),
        ("创99", "创世记生命读经/msg. 99 "),
        ("林后57", "哥林多后书生命读经/msg. 57 "),
        ("徒39", "使徒行传生命读经/msg. 39 "),
        ("约17", "约翰福音生命读经/msg. 17 "),
    ]:
        cid = find_cid(substr)
        if not cid:
            raise GateFail("G6", f"R4 找不到 {label} / {substr}")
        knn_targets.append((label, cid))
    # pad to 10 with other affected reembed
    for cid in sorted(reembed_ids):
        if len(knn_targets) >= 10:
            break
        if cid not in {c for _, c in knn_targets}:
            knn_targets.append(("extra", cid))

    knn_results = []
    for label, cid in knn_targets:
        emb = vec_emb.get(cid)
        if emb is None:
            # load single
            with vec_new.open(encoding="utf-8") as fp:
                for line in fp:
                    o = json.loads(line)
                    if o["chunk_id"] == cid:
                        emb = o["embedding"]
                        break
        resp = es.search(
            index=ES_INDEX,
            size=1,
            knn={"field": "embedding", "query_vector": emb, "k": 1, "num_candidates": 50},
            _source=False,
        )
        hits = resp["hits"]["hits"]
        top = hits[0] if hits else None
        top_id = top["_id"] if top else None
        score = top.get("_score") if top else None
        knn_results.append({"label": label, "cid": cid, "top1": top_id, "score": score, "ok": top_id == cid})
    if not all(r["ok"] for r in knn_results):
        raise GateFail("G6", "R4 kNN 自匹配失败", {"knn": knn_results})

    # R5 smoke
    def count_term(field, value):
        return es.count(index=ES_INDEX, query={"term": {field: value}})["count"]

    def uniq_msgs(field, value):
        resp = es.search(
            index=ES_INDEX, size=0,
            query={"term": {field: value}},
            aggs={"mk": {"cardinality": {"field": "message_key"}}},
        )
        return resp["hits"]["total"]["value"] if isinstance(resp["hits"]["total"], dict) else resp["hits"]["total"], resp["aggregations"]["mk"]["value"]

    r5 = {}
    n, m = uniq_msgs("book_title", "雅歌生命读经")
    r5["雅歌生命读经"] = {"chunks": n, "msgs": m}
    r5["雅歌书生命读经"] = count_term("book_title", "雅歌书生命读经")
    n, m = uniq_msgs("book_title", "约翰二书生命读经")
    r5["约翰二书生命读经"] = {"chunks": n, "msgs": m}
    r5["约翰二书生命读经_"] = count_term("book_title", "约翰二书生命读经_")
    r5["成熟的表显（七）"] = es.search(
        index=ES_INDEX, size=1, query={"term": {"message_title": "成熟的表显（七）"}},
        _source=["message_key", "book_title", "message_number"],
    )["hits"]["hits"]
    r5["保罗表白八"] = es.search(
        index=ES_INDEX, size=1, query={"term": {"message_title": "保罗为他使徒权柄的表白（八）"}},
        _source=["message_key", "book_title", "message_number"],
    )["hits"]["hits"]
    # ─ in title
    r5["box_dash"] = es.count(
        index=ES_INDEX,
        query={"bool": {
            "must": [{"wildcard": {"book_title": "*生命读经*"}}],
            "filter": [{"wildcard": {"message_title": f"*{chr(0x2500)}*"}}],
        }},
    )["count"]
    r5["esther3"] = es.count(
        index=ES_INDEX,
        query={"bool": {"must": [
            {"term": {"book_title": "以斯帖记生命读经"}},
            {"term": {"message_number": 3}},
        ]}},
    )["count"]
    for mno, expect_has, expect_not in [(17, "干渴", "乾"), (36, "于", "於"), (37, "于", "於")]:
        hits = es.search(
            index=ES_INDEX, size=1,
            query={"bool": {"must": [
                {"term": {"book_title": "约翰福音生命读经"}},
                {"term": {"message_number": mno}},
                {"term": {"chunk_index": 1}},
            ]}},
            _source=["message_title"],
        )["hits"]["hits"]
        mt = (hits[0]["_source"].get("message_title") if hits else "") or ""
        r5[f"john{mno}"] = {"title": mt, "ok": expect_has in mt and expect_not not in mt}
    r5["bp_雅歌书"] = es.count(index=ES_INDEX, query={"term": {"book_path": "雅歌书生命读经"}})["count"]
    r5["bp_约翰二书_"] = es.count(index=ES_INDEX, query={"term": {"book_path": "约翰二书生命读经_"}})["count"]

    r5_ok = (
        r5["雅歌生命读经"]["chunks"] == 41 and r5["雅歌生命读经"]["msgs"] == 10
        and r5["雅歌书生命读经"] == 0
        and r5["约翰二书生命读经"]["chunks"] == 11 and r5["约翰二书生命读经"]["msgs"] == 2
        and r5["约翰二书生命读经_"] == 0
        and r5["box_dash"] == 0
        and r5["esther3"] == 5
        and r5["bp_雅歌书"] == 0 and r5["bp_约翰二书_"] == 0
        and r5["john17"]["ok"] and r5["john36"]["ok"] and r5["john37"]["ok"]
    )
    # title exact hits
    def _hit_ok(hits, book_sub, mno):
        if not hits:
            return False
        s = hits[0]["_source"]
        return book_sub in (s.get("book_title") or "") and s.get("message_number") == mno
    r5_ok = r5_ok and _hit_ok(r5["成熟的表显（七）"], "创世记", 109) and _hit_ok(r5["保罗表白八"], "哥林多后书", 57)
    if not r5_ok:
        raise GateFail("G6", "R5 冒烟未全过", {"r5": {k: v for k, v in r5.items() if k not in ("成熟的表显（七）", "保罗表白八")}})

    # R6 header sample 200 (100 life)
    life_ids = [cid for cid, o in new_by.items() if "生命读经" in (o.get("book_title") or "")]
    other_ids = [cid for cid in new_by if cid not in set(life_ids)]
    sample_ids = rng.sample(life_ids, 100) + rng.sample(other_ids, 100)
    header_fail = 0
    for i in range(0, len(sample_ids), 50):
        batch = sample_ids[i:i + 50]
        resp = es.mget(index=ES_INDEX, ids=batch, source=["text", "book_title", "message_title"])
        for doc in resp.get("docs") or []:
            s = doc.get("_source") or {}
            first = (s.get("text") or "").split("\n", 1)[0]
            expect = render_header(s.get("book_title"), s.get("message_title"))
            if first != expect:
                header_fail += 1
    if header_fail:
        raise GateFail("G6", f"R6 header 失败 {header_fail}/200")

    # R7 counts + versions
    vers_path = STAGING_DIR / "write_versions.json"
    vers = json.loads(vers_path.read_text(encoding="utf-8")) if vers_path.exists() else {}
    cnt_now = es.count(index=ES_INDEX)["count"]

    result = {
        "r1_same": same, "r1_diff": diff,
        "r2_checked": len(check_ids), "r2_mismatch": len(emb_mismatch),
        "r3_n": len(es_ids), "r3_mk": len(mk_counts),
        "r4": knn_results,
        "r5": {
            "雅歌生命读经": r5["雅歌生命读经"],
            "雅歌书生命读经": r5["雅歌书生命读经"],
            "约翰二书生命读经": r5["约翰二书生命读经"],
            "约翰二书生命读经_": r5["约翰二书生命读经_"],
            "box_dash": r5["box_dash"],
            "esther3": r5["esther3"],
            "bp_雅歌书": r5["bp_雅歌书"],
            "bp_约翰二书_": r5["bp_约翰二书_"],
            "john17": r5["john17"],
            "john36": r5["john36"],
            "john37": r5["john37"],
            "创109_hits": len(r5["成熟的表显（七）"]),
            "林后57_hits": len(r5["保罗表白八"]),
        },
        "r6_fail": header_fail,
        "r7_count": cnt_now,
        "r7_version_changed": sum(1 for k, v in (vers.get("before") or {}).items() if (vers.get("after") or {}).get(k) != v),
        "url": url,
    }
    lines = [
        "# 生命读经修订 阶段2 reconcile",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- R1 same={same} diff={diff}",
        f"- R2 checked={len(check_ids)} mismatch={len(emb_mismatch)}",
        f"- R3 |ES|={len(es_ids)} mk={len(mk_counts)}",
        f"- R4 knn: {knn_results}",
        f"- R5: {result['r5']}",
        f"- R6 header_fail={header_fail}/200",
        f"- R7 count={cnt_now} version_changed={result['r7_version_changed']}",
        "- **闸门 G6：通过**",
        "",
    ]
    _write_stage_report("reconcile", lines)
    return result


def stage_rollback_local_script(log_path: Path) -> dict:
    """只写好回滚脚本，不运行。"""
    script = STAGING_DIR / "rollback_local.py"
    script.write_text(
        "\n".join([
            "# -*- coding: utf-8 -*-",
            '"""回滚本机 panai4_outline_12490 的 348 个受影响文档。手动运行；apply_life_fix 不会自动执行。"""',
            "from __future__ import annotations",
            "import json, os, sys",
            "from pathlib import Path",
            "from dotenv import load_dotenv",
            "from elasticsearch import Elasticsearch",
            "from elasticsearch.helpers import bulk",
            "",
            "BACKUP = Path(r'G:\\PanAI4.0专用\\备份_生命读经修订前_20261106')",
            "INDEX = 'panai4_outline_12490'",
            f"FIELDS = {list(OUTLINE_DOC_FIELDS)!r}",
            "",
            "def main() -> int:",
            "    load_dotenv(Path(r'G:\\copypan\\back_mic\\backend\\.env'))",
            "    host = os.getenv('ES_HOST', 'localhost')",
            "    port = os.getenv('ES_PORT', '9200')",
            "    assert host in ('localhost', '127.0.0.1') and str(port) == '9200'",
            "    es = Elasticsearch(hosts=[f'http://{host}:{port}'],",
            "        basic_auth=(os.getenv('ES_USERNAME', 'elastic'), os.getenv('ES_PASSWORD', '')),",
            "        request_timeout=180, max_retries=0)",
            "    actions = []",
            "    with (BACKUP / 'es_before_affected.jsonl').open(encoding='utf-8') as fp:",
            "        for line in fp:",
            "            if not line.strip():",
            "                continue",
            "            o = json.loads(line)",
            "            cid = o.get('_id') or o.get('chunk_id')",
            "            src = {k: o[k] for k in FIELDS if k in o}",
            "            actions.append({'_op_type': 'index', '_index': INDEX, '_id': cid, '_source': src})",
            "    assert len(actions) == 348, len(actions)",
            "    ok, errs = bulk(es, actions, raise_on_error=False, raise_on_exception=False, request_timeout=180)",
            "    es.indices.refresh(index=INDEX)",
            "    cnt = es.count(index=INDEX)['count']",
            "    # 与备份逐文档抽查",
            "    bad = 0",
            "    with (BACKUP / 'es_before_affected.jsonl').open(encoding='utf-8') as fp:",
            "        for line in fp:",
            "            o = json.loads(line)",
            "            cid = o.get('_id') or o.get('chunk_id')",
            "            doc = es.get(index=INDEX, id=cid)",
            "            src = doc.get('_source') or {}",
            "            for k in FIELDS:",
            "                if k in o and src.get(k) != o.get(k):",
            "                    bad += 1",
            "                    break",
            "    print('rollback ok', ok, 'errs', len(errs) if errs else 0, 'count', cnt, 'mismatch', bad)",
            "    return 0 if ok == 348 and cnt == 55841 and not errs and bad == 0 else 1",
            "",
            "if __name__ == '__main__':",
            "    raise SystemExit(main())",
            "",
        ]),
        encoding="utf-8",
    )
    lines = [
        "# 生命读经修订 阶段2 rollback_local（只写好，未运行）",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- 脚本：`{script}`",
        "- 作用：从 es_before_affected.jsonl 按 _id 覆盖写回 348 文档，核对 count=55841 并与备份比对",
        "- **本阶段未执行回滚**",
        "",
    ]
    _write_stage_report("rollback_local", lines)
    return {"script": str(script)}


def write_stage2_summary(results: dict, log_path: Path, stopped_at: Optional[str] = None) -> Path:
    gi = _assert_gitignore_env()
    # secret leak check in memory
    load_dotenv(_backend_env())
    secrets = _secret_values()
    leak = False
    scan_paths = []
    for p in ARCHIVE_DIR.glob("life_fix_stage2*.md"):
        scan_paths.append(p)
    for p in LOG_DIR_DEFAULT.glob("life_fix_apply_*.log"):
        # only recent
        scan_paths.append(p)
    for p in STAGING_DIR.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".md", ".txt", ".csv", ".log", ".flag"}:
            scan_paths.append(p)
        if p.name in {"embed_jobs.jsonl"}:
            scan_paths.append(p)  # text only, should not have secrets
    for p in scan_paths:
        try:
            # skip huge / binary-ish
            if p.stat().st_size > 50_000_000:
                continue
            data = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for s in secrets:
            if s and len(s) >= 8 and s in data:
                leak = True
                break
        if leak:
            break

    snap = folder_snapshot(OUT_DIR)
    # backup sha verify
    sha_ok = True
    for line in (BACKUP_DIR / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        if sha256_file(BACKUP_DIR / parts[1]) != parts[0]:
            sha_ok = False

    gates = results.get("gates") or {}
    emb = results.get("embed") or {}
    ver = results.get("verify_vec") or {}
    wr = results.get("write_local") or {}
    rec = results.get("reconcile") or {}
    cos = (ver.get("cosine") or {})

    lines = [
        "# 生命读经修订 阶段2 汇总",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`；stopped_at={stopped_at or '无'}",
        "",
        "## 结论摘要",
        "",
        f"(1) 闸门 G1–G6：{gates}；停在：{stopped_at or '全部通过'}",
        f"(2) 重算块={emb.get('n')} 字符={emb.get('chars')} usage_tokens={emb.get('usage_tokens')} 费用=${emb.get('cost_by_chunks')}",
        f"(3) V4 余弦：{cos}；低于0.80={cos.get('below_0_80')}",
        f"(4) 写入成功={wr.get('ok')} 失败={wr.get('fail')}",
        f"(5) reconcile：R1 same={rec.get('r1_same')} diff={rec.get('r1_diff')}；R2 checked={rec.get('r2_checked')} mismatch={rec.get('r2_mismatch')}；"
        f"R3 n={rec.get('r3_n')} mk={rec.get('r3_mk')}；R4={rec.get('r4')}；R5={rec.get('r5')}；R6_fail={rec.get('r6_fail')}；R7 count={rec.get('r7_count')} ver_changed={rec.get('r7_version_changed')}",
        f"(6) ES count 写前={wr.get('count_before')} 写后={wr.get('count_after')}",
        f"(7) embedding_adapter 环境变量名：{emb.get('env_var_names')}；.env 在 .gitignore={gi}",
        "(8) **提醒：服务器尚未改动；本机已改，服务器仍是旧数据。**",
        "",
        "## 最终验证",
        "",
        f"- 备份 SHA 与 SUMS 一致={sha_ok}",
        f"- 纲目JSON 快照={snap} 期望={EXPECTED_SNAP} ok={snap == EXPECTED_SNAP}",
        f"- ES 只写本机 `{ES_URL_ALLOWED}` / `{ES_INDEX}` 的 348 个 _id；无建删索引",
        f"- git：\n```\n{_git_status()}\n```",
        f"- 密钥泄露检查（内存比对日志/报告/暂存文本）：{'不通过' if leak else '通过'}",
        "",
    ]
    path = ARCHIVE_DIR / "life_fix_stage2_summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("wrote %s", path)
    return path


def _run_stage01_if_needed(stage: str, log_path: Path):
    if stage not in ("backup", "dryrun", "all"):
        return None, None
    chunks_path = OUT_DIR / "chunks_12490.json"
    rows = build_v4_csv(chunks_path)
    backup_info: dict = {}
    dry: dict = {}
    if stage in ("backup", "all"):
        backup_info = stage_backup(rows, log_path)
    if stage in ("dryrun", "all"):
        if not backup_info.get("sums"):
            aff = _load_affected() if (BACKUP_DIR / "affected_chunks.csv").exists() else []
            sums = []
            if (BACKUP_DIR / "SHA256SUMS.txt").exists():
                for line in (BACKUP_DIR / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        sums.append((parts[1], parts[0], (BACKUP_DIR / parts[1]).stat().st_size))
            snap = folder_snapshot(OUT_DIR)
            es, _ = make_es()
            cnt = es.count(index=ES_INDEX)["count"]
            backup_info = {
                "affected": aff,
                "affected_cids": sorted({a["chunk_id"] for a in aff}),
                "exported": sum(1 for _ in open(BACKUP_DIR / "es_before_affected.jsonl", encoding="utf-8")) if (BACKUP_DIR / "es_before_affected.jsonl").exists() else 0,
                "sums": sums,
                "count_before": cnt,
                "count_after": cnt,
                "snap_before": snap,
                "snap_after": snap,
            }
        dry = stage_dryrun(rows, backup_info, log_path)
        write_report(rows, backup_info, dry, log_path)
    return rows, dry


# ---------------------------------------------------------------------------
# Stage 3 — remote sync
# ---------------------------------------------------------------------------

REMOTE_ENV_KEYS = (
    "ES_REMOTE_HOST",
    "ES_REMOTE_PORT",
    "ES_REMOTE_USERNAME",
    "ES_REMOTE_PASSWORD",
)
REMOTE_RANDOM_SEED = 20261106
SERVER_BEFORE_PATH = BACKUP_DIR / "server_before_affected.jsonl"
REMOTE_PRECHECK_PATH = ARCHIVE_DIR / "life_fix_stage3_precheck.md"
VERIFY_OK_PATH = STAGING_DIR / "verify_vec.ok"


def make_remote_es():
    """通过 ES_REMOTE_* 连接服务器；不读 .env 文件内容，只用 load_dotenv + getenv。"""
    from elasticsearch import Elasticsearch

    load_dotenv(_backend_env())
    host = (os.getenv("ES_REMOTE_HOST") or "").strip()
    port = (os.getenv("ES_REMOTE_PORT") or "").strip()
    user = (os.getenv("ES_REMOTE_USERNAME") or "").strip()
    password = (os.getenv("ES_REMOTE_PASSWORD") or "").strip()
    missing = [k for k, v in zip(REMOTE_ENV_KEYS, (host, port, user, password)) if not v]
    if missing:
        raise GateFail("REMOTE", f"缺少远程 ES 环境变量：{'、'.join(missing)}")
    # 禁止误连本机
    if host in ("localhost", "127.0.0.1"):
        raise GateFail("REMOTE", f"ES_REMOTE_HOST 不能是本机 ({host})")
    client = Elasticsearch(
        hosts=[f"http://{host}:{port}"],
        basic_auth=(user, password),
        request_timeout=180,
        max_retries=2,
        retry_on_timeout=True,
    )
    # 不返回/不记录 host 明文到报告以外的必要处；调用方只报变量名
    return client, {"env_keys": list(REMOTE_ENV_KEYS), "host_set": bool(host), "port": port}


def _scroll_all(es, *, exclude_embedding: bool = True, source_includes=None) -> dict[str, dict]:
    """全量 scroll，返回 _id -> _source。"""
    body_source = None
    if source_includes is not None:
        body_source = source_includes
    elif exclude_embedding:
        body_source = {"excludes": ["embedding"]}
    out: dict[str, dict] = {}
    resp = es.search(
        index=ES_INDEX,
        size=500,
        scroll="5m",
        _source=body_source if body_source is not None else True,
        query={"match_all": {}},
    )
    sid = resp.get("_scroll_id")
    try:
        while True:
            hits = resp["hits"]["hits"]
            if not hits:
                break
            for h in hits:
                out[h["_id"]] = h.get("_source") or {}
            resp = es.scroll(scroll_id=sid, scroll="5m")
            sid = resp.get("_scroll_id")
    finally:
        try:
            if sid:
                es.clear_scroll(scroll_id=sid)
        except Exception:  # noqa: BLE001
            pass
    return out


def _diff_docs(a: dict, b: dict, *, ignore_embedding: bool = False) -> list[tuple[str, str, str]]:
    """返回 (field, a_brief, b_brief) 列表。"""
    keys = set(a) | set(b)
    if ignore_embedding:
        keys.discard("embedding")
    diffs = []
    for k in sorted(keys):
        va, vb = a.get(k), b.get(k)
        if va != vb:
            if k == "embedding":
                diffs.append((k, f"len={len(va) if isinstance(va, list) else None}", f"len={len(vb) if isinstance(vb, list) else None}"))
            else:
                diffs.append((k, repr(va)[:80], repr(vb)[:80]))
    return diffs


def _load_es_before_map() -> dict[str, dict]:
    path = BACKUP_DIR / "es_before_affected.jsonl"
    by = {}
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            cid = o.get("_id") or o.get("chunk_id")
            src = {k: v for k, v in o.items() if k != "_id"}
            by[cid] = src
    return by


def _field_class_counts(aff: list[dict]) -> dict:
    # unique cids per field type (a cid may appear once per field row)
    by_field = Counter()
    seen = set()
    for a in aff:
        key = (a["chunk_id"], a["field"])
        if key in seen:
            continue
        seen.add(key)
        by_field[a["field"]] += 1
    return dict(by_field)


def stage_remote_check(log_path: Path) -> dict:
    logging.info("=== STAGE remote_check ===")
    secrets = []
    load_dotenv(_backend_env())
    secrets = _secret_values()
    remote, meta = make_remote_es()
    local, _ = make_es()
    aff = _load_affected()
    aff_cids = sorted(_affected_cids(aff))
    if len(aff_cids) != EXPECTED_AFFECTED_N:
        raise GateFail("RC", f"affected 唯一块 {len(aff_cids)} ≠ {EXPECTED_AFFECTED_N}")

    # C1
    try:
        info = remote.info()
    except Exception as exc:  # noqa: BLE001
        raise GateFail("RC", _redact(f"remote.info 失败: {exc}", secrets)) from exc
    ver = info.get("version", {}).get("number")
    cluster = info.get("cluster_name")
    cnt = remote.count(index=ES_INDEX)["count"]
    mapping = remote.indices.get_mapping(index=ES_INDEX)
    props = mapping[ES_INDEX]["mappings"]["properties"]
    emb = props.get("embedding") or {}
    emb_ok = (
        emb.get("type") == "dense_vector"
        and int(emb.get("dims") or 0) == 1024
        and emb.get("similarity") == "cosine"
        and (emb.get("index_options") or {}).get("type") == "int8_hnsw"
    )
    c1 = {
        "version": ver,
        "cluster_name": cluster,
        "count": cnt,
        "embedding_field": "embedding" if "embedding" in props else None,
        "embedding_spec": {
            "type": emb.get("type"),
            "dims": emb.get("dims"),
            "similarity": emb.get("similarity"),
            "index_options": emb.get("index_options"),
        },
        "emb_ok": emb_ok,
        "env_keys": meta["env_keys"],
    }
    logging.info("C1 version=%s cluster=%s count=%s emb_ok=%s", ver, cluster, cnt, emb_ok)
    if cnt != 55841 or not emb_ok:
        raise GateFail("RC", f"C1 count/mapping 不符 count={cnt} emb_ok={emb_ok}", c1)

    # other panai4_* counts baseline
    try:
        cat_rows = remote.cat.indices(index="panai4_*", format="json", bytes="b")
    except Exception as exc:  # noqa: BLE001
        raise GateFail("RC", _redact(f"cat.indices 失败: {exc}", secrets)) from exc
    other_counts = {r.get("index"): r.get("docs.count") for r in cat_rows}
    (STAGING_DIR / "remote_panai4_counts_before.json").write_text(
        json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "counts": other_counts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # C2: mget 348 with embedding vs es_before
    before_map = _load_es_before_map()
    if len(before_map) != EXPECTED_AFFECTED_N:
        raise GateFail("RC", f"es_before 条数 {len(before_map)}")
    same2 = diff2 = 0
    missing2 = []
    diff2_rows = []
    for i in range(0, len(aff_cids), 50):
        batch = aff_cids[i:i + 50]
        resp = remote.mget(index=ES_INDEX, ids=batch)
        for doc in resp.get("docs") or []:
            cid = doc.get("_id")
            if not doc.get("found"):
                missing2.append(cid)
                diff2 += 1
                continue
            src = doc.get("_source") or {}
            base = before_map.get(cid) or {}
            diffs = _diff_docs(base, src, ignore_embedding=False)
            if not diffs:
                same2 += 1
            else:
                diff2 += 1
                for field, a, b in diffs:
                    diff2_rows.append({"_id": cid, "field": field, "before": a, "remote": b})
    c2 = {"same": same2, "diff": diff2, "missing": missing2, "diff_rows_n": len(diff2_rows), "diff_rows": diff2_rows[:50]}
    logging.info("C2 same=%s diff=%s missing=%s", same2, diff2, len(missing2))

    # C3: 300 non-affected fields; 100 vectors（id 从 chunks.new 取，避免提前全量 scroll）
    rng = random.Random(REMOTE_RANDOM_SEED)
    all_local_ids = list(_load_jsonl_index(STAGING_DIR / "chunks_12490.new.json").keys())
    non_aff = [cid for cid in all_local_ids if cid not in set(aff_cids)]
    sample300 = rng.sample(non_aff, 300)
    sample100 = rng.sample(sample300, 100)
    # field compare
    same3 = diff3 = 0
    diff3_rows = []
    local_src_cache = {}
    # fetch local
    for i in range(0, 300, 50):
        batch = sample300[i:i + 50]
        resp = local.mget(index=ES_INDEX, ids=batch, source={"excludes": ["embedding"]})
        for doc in resp.get("docs") or []:
            if doc.get("found"):
                local_src_cache[doc["_id"]] = doc.get("_source") or {}
    for i in range(0, 300, 50):
        batch = sample300[i:i + 50]
        resp = remote.mget(index=ES_INDEX, ids=batch, source={"excludes": ["embedding"]})
        for doc in resp.get("docs") or []:
            cid = doc["_id"]
            if not doc.get("found"):
                diff3 += 1
                diff3_rows.append({"_id": cid, "reason": "missing_remote"})
                continue
            diffs = _diff_docs(local_src_cache.get(cid) or {}, doc.get("_source") or {}, ignore_embedding=True)
            if diffs:
                diff3 += 1
                diff3_rows.append({"_id": cid, "diffs": diffs[:5]})
            else:
                same3 += 1
    # vector compare 100
    same3v = diff3v = 0
    for i in range(0, 100, 50):
        batch = sample100[i:i + 50]
        loc = {d["_id"]: (d.get("_source") or {}).get("embedding") for d in local.mget(index=ES_INDEX, ids=batch, source=["embedding"]).get("docs") or [] if d.get("found")}
        rem = {d["_id"]: (d.get("_source") or {}).get("embedding") for d in remote.mget(index=ES_INDEX, ids=batch, source=["embedding"]).get("docs") or [] if d.get("found")}
        for cid in batch:
            if loc.get(cid) == rem.get(cid) and loc.get(cid) is not None:
                same3v += 1
            else:
                diff3v += 1
    c3 = {
        "seed": REMOTE_RANDOM_SEED,
        "sample300_n": len(sample300),
        "field_same": same3,
        "field_diff": diff3,
        "field_diff_rows": diff3_rows[:20],
        "vec_sample100_same": same3v,
        "vec_sample100_diff": diff3v,
    }
    logging.info("C3 field same/diff=%s/%s vec same/diff=%s/%s", same3, diff3, same3v, diff3v)

    # C4: full scroll remote vs local
    logging.info("C4 scrolling local...")
    local_map = _scroll_all(local, exclude_embedding=True)
    logging.info("C4 scrolling remote...")
    remote_map = _scroll_all(remote, exclude_embedding=True)
    set_eq = set(local_map) == set(remote_map) and len(local_map) == 55841
    aff_set = set(aff_cids)
    aff_diff = 0
    non_aff_diff = 0
    non_aff_diff_rows = []
    for cid in local_map:
        if cid not in remote_map:
            if cid in aff_set:
                aff_diff += 1
            else:
                non_aff_diff += 1
                if len(non_aff_diff_rows) < 30:
                    non_aff_diff_rows.append({"_id": cid, "reason": "missing_remote"})
            continue
        diffs = _diff_docs(local_map[cid], remote_map[cid], ignore_embedding=True)
        if diffs:
            if cid in aff_set:
                aff_diff += 1
            else:
                non_aff_diff += 1
                if len(non_aff_diff_rows) < 30:
                    non_aff_diff_rows.append({"_id": cid, "diffs": [(f, a, b) for f, a, b in diffs[:5]]})
    for cid in remote_map:
        if cid not in local_map:
            if cid in aff_set:
                aff_diff += 1
            else:
                non_aff_diff += 1
                if len(non_aff_diff_rows) < 30:
                    non_aff_diff_rows.append({"_id": cid, "reason": "missing_local"})
    c4 = {
        "set_eq": set_eq,
        "local_n": len(local_map),
        "remote_n": len(remote_map),
        "affected_diff_docs": aff_diff,
        "non_affected_diff_docs": non_aff_diff,
        "non_affected_samples": non_aff_diff_rows,
    }
    logging.info("C4 set_eq=%s aff_diff=%s non_aff_diff=%s", set_eq, aff_diff, non_aff_diff)

    # C5 gate
    if diff2 > 0 or missing2 or non_aff_diff > 0:
        raise GateFail(
            "RC",
            f"C5 停止：C2.diff={diff2} missing={len(missing2)} C4.non_aff_diff={non_aff_diff}",
            {"c1": c1, "c2": c2, "c3": c3, "c4": c4},
        )
    if not set_eq:
        raise GateFail("RC", "C4 集合不等", c4)

    # persist check state for write W0
    state = {
        "c1_count": cnt,
        "c1": c1,
        "c2": {"same": same2, "diff": diff2},
        "c3": c3,
        "c4": {"set_eq": set_eq, "aff_diff": aff_diff, "non_aff_diff": non_aff_diff},
        "other_counts": other_counts,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    (STAGING_DIR / "remote_check_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    result = {"c1": c1, "c2": c2, "c3": c3, "c4": c4, "other_counts": other_counts}
    lines = [
        "# 生命读经修订 阶段3 remote_check",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- C1 version={ver} cluster={cluster} count={cnt} emb_ok={emb_ok}",
        f"- C1 embedding_spec={c1['embedding_spec']}",
        f"- 连接变量名：{', '.join(REMOTE_ENV_KEYS)}",
        f"- C2 vs es_before：same={same2} diff={diff2} missing={len(missing2)}",
        f"- C3 seed={REMOTE_RANDOM_SEED} field same/diff={same3}/{diff3}；vec100 same/diff={same3v}/{diff3v}",
        f"- C4 set_eq={set_eq} local={len(local_map)} remote={len(remote_map)} aff_diff={aff_diff} non_aff_diff={non_aff_diff}",
        f"- C5：**通过**（C2 全同且非受影响无差异）",
        "",
    ]
    if diff2_rows:
        lines.append("- C2 差异样例（不应出现）：")
        for row in diff2_rows[:10]:
            lines.append(f"  - {row}")
    _write_stage_report("remote_check", lines)
    # also alias path expected by user naming
    (ARCHIVE_DIR / "life_fix_stage3_remote_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def stage_remote_backup(log_path: Path) -> dict:
    logging.info("=== STAGE remote_backup ===")
    load_dotenv(_backend_env())
    secrets = _secret_values()
    remote, _meta = make_remote_es()
    aff_cids = sorted(_affected_cids())
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # B1 export
    exported = []
    with SERVER_BEFORE_PATH.open("w", encoding="utf-8", newline="\n") as out:
        for i in range(0, len(aff_cids), 50):
            batch = aff_cids[i:i + 50]
            resp = remote.mget(index=ES_INDEX, ids=batch)
            for doc in resp.get("docs") or []:
                if not doc.get("found"):
                    raise GateFail("RB", f"服务器缺少 {doc.get('_id')}")
                cid = doc["_id"]
                src = doc.get("_source") or {}
                row = {"_id": cid, **src}
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                exported.append(cid)
    if len(exported) != EXPECTED_AFFECTED_N or set(exported) != set(aff_cids):
        raise GateFail("RB", f"导出条数/集合不符 n={len(exported)}")

    h = sha256_file(SERVER_BEFORE_PATH)
    size = SERVER_BEFORE_PATH.stat().st_size
    sums_path = BACKUP_DIR / "SHA256SUMS.txt"
    # append only if not already present
    existing = sums_path.read_text(encoding="utf-8") if sums_path.exists() else ""
    line = f"{h}  {SERVER_BEFORE_PATH.name}  # size={size}\n"
    if SERVER_BEFORE_PATH.name not in existing:
        with sums_path.open("a", encoding="utf-8") as fp:
            fp.write(line)
        appended = True
    else:
        # replace? user said 只追加一行，不改已有行 — if already there from prior run, keep
        appended = False
        # verify hash matches recorded
        for ln in existing.splitlines():
            if SERVER_BEFORE_PATH.name in ln:
                old_h = ln.split()[0]
                if old_h != h:
                    raise GateFail("RB", f"已有 SUMS 行但 SHA 不一致 old={old_h[:16]}… new={h[:16]}…")
                break

    # B2 rollback_remote script only
    script = STAGING_DIR / "rollback_remote.py"
    script.write_text(
        "\n".join([
            "# -*- coding: utf-8 -*-",
            '"""从 server_before_affected.jsonl 回滚服务器 348 文档。手动运行；apply_life_fix 不自动执行。"""',
            "from __future__ import annotations",
            "import json, os",
            "from pathlib import Path",
            "from dotenv import load_dotenv",
            "from elasticsearch import Elasticsearch",
            "from elasticsearch.helpers import bulk",
            "",
            f"BACKUP = Path(r'{BACKUP_DIR}')",
            f"INDEX = '{ES_INDEX}'",
            f"FIELDS = {list(OUTLINE_DOC_FIELDS)!r}",
            f"SRC = Path(r'{SERVER_BEFORE_PATH}')",
            "",
            "def main() -> int:",
            f"    load_dotenv(Path(r'{_backend_env()}'))",
            "    host = (os.getenv('ES_REMOTE_HOST') or '').strip()",
            "    port = (os.getenv('ES_REMOTE_PORT') or '').strip()",
            "    user = (os.getenv('ES_REMOTE_USERNAME') or '').strip()",
            "    password = (os.getenv('ES_REMOTE_PASSWORD') or '').strip()",
            "    assert host and port and user and password",
            "    assert host not in ('localhost', '127.0.0.1')",
            "    es = Elasticsearch(hosts=[f'http://{host}:{port}'], basic_auth=(user, password),",
            "                       request_timeout=180, max_retries=2, retry_on_timeout=True)",
            "    actions = []",
            "    with SRC.open(encoding='utf-8') as fp:",
            "        for line in fp:",
            "            if not line.strip():",
            "                continue",
            "            o = json.loads(line)",
            "            cid = o.get('_id') or o.get('chunk_id')",
            "            src = {k: o[k] for k in FIELDS if k in o}",
            "            actions.append({'_op_type': 'index', '_index': INDEX, '_id': cid, '_source': src})",
            "    assert len(actions) == 348, len(actions)",
            "    ok, errs = bulk(es, actions, raise_on_error=False, raise_on_exception=False, request_timeout=180)",
            "    es.indices.refresh(index=INDEX)",
            "    cnt = es.count(index=INDEX)['count']",
            "    bad = 0",
            "    with SRC.open(encoding='utf-8') as fp:",
            "        for line in fp:",
            "            o = json.loads(line)",
            "            cid = o.get('_id') or o.get('chunk_id')",
            "            doc = es.get(index=INDEX, id=cid)",
            "            src = doc.get('_source') or {}",
            "            for k in FIELDS:",
            "                if k in o and src.get(k) != o.get(k):",
            "                    bad += 1",
            "                    break",
            "    print('rollback_remote ok', ok, 'errs', len(errs) if errs else 0, 'count', cnt, 'mismatch', bad)",
            "    return 0 if ok == 348 and cnt == 55841 and not errs and bad == 0 else 1",
            "",
            "if __name__ == '__main__':",
            "    raise SystemExit(main())",
            "",
        ]),
        encoding="utf-8",
    )

    result = {
        "n": len(exported),
        "sha256": h,
        "size": size,
        "appended_sums": appended,
        "script": str(script),
    }
    lines = [
        "# 生命读经修订 阶段3 remote_backup",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- B1 `{SERVER_BEFORE_PATH.name}` 条数={len(exported)} size={size} sha256=`{h}`",
        f"- SHA256SUMS.txt 追加={appended}",
        f"- B2 rollback 脚本（未运行）：`{script}`",
        "",
    ]
    _write_stage_report("remote_backup", lines)
    (ARCHIVE_DIR / "life_fix_stage3_remote_backup.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def write_stage3_precheck(check: dict, backup: dict, log_path: Path) -> Path:
    aff = _load_affected()
    field_c = _field_class_counts(aff)
    # title/book/number unique chunks
    title_n = field_c.get("message_title", 0)
    book_n = field_c.get("book_title", 0)
    num_n = field_c.get("message_number", 0)
    vec = STAGING_DIR / "chunks_12490_vec.new.json"
    est_mb = (vec.stat().st_size / 55841 * EXPECTED_AFFECTED_N) / (1024 * 1024) if vec.exists() else None
    c1 = check["c1"]
    c2 = check["c2"]
    c3 = check["c3"]
    c4 = check["c4"]
    lines = [
        "# 生命读经修订 阶段3 预检（暂停点）",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        "## 摘要",
        "",
        f"(1) 服务器 version={c1['version']} cluster={c1['cluster_name']} count={c1['count']}；embedding 字段 OK={c1['emb_ok']}",
        f"(2) C2 vs 本机修改前备份：same={c2['same']} diff={c2['diff']}（期望 same=348 diff=0）",
        f"(3) C3 非受影响抽样 seed={c3['seed']}：字段 same/diff={c3['field_same']}/{c3['field_diff']}；向量100 same/diff={c3['vec_sample100_same']}/{c3['vec_sample100_diff']}",
        f"(4) C4 集合相等={c4['set_eq']}（local={c4['local_n']} remote={c4['remote_n']}）；受影响差异文档={c4['affected_diff_docs']}；**非受影响差异={c4['non_affected_diff_docs']}**（期望 0）",
        f"(5) 服务器备份条数={backup['n']} sha256=`{backup['sha256']}` size={backup['size']}",
        f"(6) 将写入 348 _id：title 行={title_n} / book 行={book_n} / number 行={num_n}（affected 行级）；预计体积 ≈ {est_mb:.2f} MB",
        "(7) **暂停：等你回复「写」后才执行 remote_write / remote_reconcile。**",
        "",
        f"- 连接变量名：{', '.join(REMOTE_ENV_KEYS)}（只报名称）",
        f"- rollback_remote：`{backup['script']}`（未运行）",
        f"- server_before：`{SERVER_BEFORE_PATH}`",
        "",
    ]
    REMOTE_PRECHECK_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("wrote precheck %s", REMOTE_PRECHECK_PATH)
    return REMOTE_PRECHECK_PATH


def stage_remote_write(log_path: Path) -> dict:
    logging.info("=== STAGE remote_write ===")
    from elasticsearch.helpers import bulk

    load_dotenv(_backend_env())
    secrets = _secret_values()
    remote, _meta = make_remote_es()

    # W0
    cnt = remote.count(index=ES_INDEX)["count"]
    if cnt != 55841:
        raise GateFail("RW", f"W0 count={cnt}")
    if not SERVER_BEFORE_PATH.exists():
        raise GateFail("RW", "W0 缺少 server_before_affected.jsonl")
    with SERVER_BEFORE_PATH.open(encoding="utf-8") as fp:
        n_before = sum(1 for ln in fp if ln.strip())
    if n_before != EXPECTED_AFFECTED_N:
        raise GateFail("RW", f"W0 server_before 条数 {n_before}")
    # SHA of server_before matches SUMS
    h = sha256_file(SERVER_BEFORE_PATH)
    sums_ok = False
    for ln in (BACKUP_DIR / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if SERVER_BEFORE_PATH.name in ln and ln.split()[0] == h:
            sums_ok = True
            break
    if not sums_ok:
        raise GateFail("RW", "W0 server_before SHA 与 SUMS 不一致")
    # original backup files still match
    for ln in (BACKUP_DIR / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        parts = ln.split()
        if len(parts) < 2:
            continue
        name = parts[1]
        if name == SERVER_BEFORE_PATH.name:
            continue
        p = BACKUP_DIR / name
        if p.exists() and sha256_file(p) != parts[0]:
            raise GateFail("RW", f"W0 原备份 SHA 变了 {name}")
    state_path = STAGING_DIR / "remote_check_state.json"
    if not state_path.exists():
        raise GateFail("RW", "W0 缺少 remote_check_state.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("c1_count") != cnt:
        raise GateFail("RW", f"W0 count 与 C1 不同 C1={state.get('c1_count')} now={cnt}")
    vec_new = STAGING_DIR / "chunks_12490_vec.new.json"
    if not vec_new.exists() or not VERIFY_OK_PATH.exists():
        raise GateFail("RW", "W0 缺少 vec.new 或 verify_vec.ok")

    aff_cids = _affected_cids()
    # W0 追加：对 348 个 _id 重跑 C2（服务器当前 vs es_before_affected，含 embedding）
    before_map = _load_es_before_map()
    if len(before_map) != EXPECTED_AFFECTED_N:
        raise GateFail("RW", f"W0 es_before 条数 {len(before_map)}")
    c2_same = c2_diff = 0
    c2_missing = []
    c2_diff_rows = []
    sorted_aff = sorted(aff_cids)
    for i in range(0, len(sorted_aff), 50):
        batch = sorted_aff[i:i + 50]
        resp = remote.mget(index=ES_INDEX, ids=batch)
        for doc in resp.get("docs") or []:
            cid = doc.get("_id")
            if not doc.get("found"):
                c2_missing.append(cid)
                c2_diff += 1
                continue
            diffs = _diff_docs(before_map.get(cid) or {}, doc.get("_source") or {}, ignore_embedding=False)
            if not diffs:
                c2_same += 1
            else:
                c2_diff += 1
                for field, a, b in diffs[:3]:
                    c2_diff_rows.append({"_id": cid, "field": field, "before": a, "remote": b})
    logging.info("W0 re-C2 same=%s diff=%s missing=%s", c2_same, c2_diff, len(c2_missing))
    if c2_same != EXPECTED_AFFECTED_N or c2_diff != 0 or c2_missing:
        raise GateFail(
            "RW",
            f"W0 重跑 C2 失败 same={c2_same} diff={c2_diff} missing={len(c2_missing)}（必须 same=348 diff=0）",
            {"diff_rows": c2_diff_rows[:20], "missing": c2_missing[:20]},
        )

    docs = []
    found = set()
    with vec_new.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            if o["chunk_id"] in aff_cids:
                docs.append(o)
                found.add(o["chunk_id"])
    if found != aff_cids or len(docs) != EXPECTED_AFFECTED_N:
        raise GateFail("RW", f"W0 取出块不符 n={len(docs)}")

    # other counts before
    cat_before = {r.get("index"): r.get("docs.count") for r in remote.cat.indices(index="panai4_*", format="json")}

    ok = fail = 0
    errors = []
    written = []
    for i in range(0, len(docs), 50):
        batch = docs[i:i + 50]
        actions = [
            {"_op_type": "index", "_index": ES_INDEX, "_id": o["chunk_id"], "_source": _doc_for_es(o)}
            for o in batch
        ]
        success, errs = bulk(remote, actions, raise_on_error=False, raise_on_exception=False, request_timeout=180)
        ok += success
        if errs:
            for item in errs:
                fail += 1
                err = item.get("index") or {}
                errors.append({"_id": err.get("_id"), "status": err.get("status"), "error": _redact(str(err.get("error"))[:200], secrets)})
            raise GateFail("RW", f"W1 中途失败 ok≈{ok} fail={fail}", {"errors": errors[:10], "written": written[-20:]})
        written.extend(o["chunk_id"] for o in batch)
        logging.info("remote bulk ok so far %s", ok)

    remote.indices.refresh(index=ES_INDEX)
    cnt_after = remote.count(index=ES_INDEX)["count"]
    if fail or ok != EXPECTED_AFFECTED_N or cnt_after != 55841:
        raise GateFail("RW", f"W3 失败 ok={ok} fail={fail} count={cnt_after}")

    cat_after = {r.get("index"): r.get("docs.count") for r in remote.cat.indices(index="panai4_*", format="json")}
    (STAGING_DIR / "remote_write_result.json").write_text(
        json.dumps({
            "ok": ok, "fail": fail, "count_before": cnt, "count_after": cnt_after,
            "cat_before": cat_before, "cat_after": cat_after,
            "ts": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result = {
        "ok": ok, "fail": fail, "count_before": cnt, "count_after": cnt_after,
        "cat_before": cat_before, "cat_after": cat_after,
        "w0_rec2_same": c2_same, "w0_rec2_diff": c2_diff,
    }
    lines = [
        "# 生命读经修订 阶段3 remote_write",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- W0 通过；重跑 C2 same={c2_same} diff={c2_diff}",
        f"- 写入成功={ok} 失败={fail}",
        f"- count before={cnt} after={cnt_after}",
        f"- 连接变量名：{', '.join(REMOTE_ENV_KEYS)}",
        "",
    ]
    _write_stage_report("remote_write", lines)
    (ARCHIVE_DIR / "life_fix_stage3_remote_write.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def stage_remote_reconcile(log_path: Path) -> dict:
    logging.info("=== STAGE remote_reconcile ===")
    load_dotenv(_backend_env())
    secrets = _secret_values()
    remote, _meta = make_remote_es()
    local, _ = make_es()
    chunks_new = STAGING_DIR / "chunks_12490.new.json"
    vec_new = STAGING_DIR / "chunks_12490_vec.new.json"
    new_by = _load_jsonl_index(chunks_new)
    aff_cids = sorted(_affected_cids())
    aff_set = set(aff_cids)
    reembed_ids = set(_load_reembed_ids())
    rng = random.Random(REMOTE_RANDOM_SEED)

    # R1 local vs remote full
    logging.info("R1 scroll local+remote...")
    local_map = _scroll_all(local, exclude_embedding=True)
    remote_map = _scroll_all(remote, exclude_embedding=True)
    same = diff = 0
    samples = []
    if set(local_map) != set(remote_map):
        raise GateFail("RR", f"R1 集合不等 local={len(local_map)} remote={len(remote_map)}")
    for cid, loc in local_map.items():
        diffs = _diff_docs(loc, remote_map.get(cid) or {}, ignore_embedding=True)
        if diffs:
            diff += 1
            if len(samples) < 20:
                samples.append({"_id": cid, "diffs": diffs[:5]})
        else:
            same += 1
    if diff != 0 or same != 55841:
        raise GateFail("RR", f"R1 same={same} diff={diff}", {"samples": samples})

    # R2 embeddings
    other = [cid for cid in new_by if cid not in aff_set]
    sample_other = rng.sample(other, 300)
    check_ids = aff_cids + sample_other
    need = set(check_ids)
    vec_emb = {}
    with vec_new.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            if o["chunk_id"] in need:
                vec_emb[o["chunk_id"]] = o.get("embedding")
                if len(vec_emb) == len(need):
                    break
    mismatch = []
    for i in range(0, len(check_ids), 50):
        batch = check_ids[i:i + 50]
        resp = remote.mget(index=ES_INDEX, ids=batch, source=["embedding"])
        for doc in resp.get("docs") or []:
            cid = doc["_id"]
            if not doc.get("found"):
                mismatch.append((cid, "missing"))
                continue
            e1 = (doc.get("_source") or {}).get("embedding") or []
            e2 = vec_emb.get(cid) or []
            if e1 != e2:
                mismatch.append((cid, f"len {len(e1)}/{len(e2)}"))
    if mismatch:
        raise GateFail("RR", f"R2 mismatch {len(mismatch)}", {"samples": mismatch[:20]})

    # R3
    if len(remote_map) != 55841 or len(set(remote_map)) != 55841:
        raise GateFail("RR", "R3 remote id 异常")
    if set(remote_map) != set(local_map) != set(new_by):
        # careful: set comparison chain
        pass
    if not (set(remote_map) == set(local_map) == set(new_by)):
        raise GateFail("RR", "R3 三向集合不等")
    mk_n = len({o.get("message_key") for o in new_by.values()})
    if mk_n != 12328:
        raise GateFail("RR", f"R3 mk={mk_n}")

    # R4 knn
    def find_cid(substr: str) -> Optional[str]:
        for cid, o in new_by.items():
            if substr in (o.get("message_key") or "") and o.get("chunk_index") == 1:
                return cid
        return None

    knn_targets = []
    for label, substr in [
        ("雅歌", "雅歌书生命读经/msg. 1 "),
        ("约翰二书", "约翰二书生命读经_/msg. 1 "),
        ("创98", "创世记生命读经/msg. 98 "),
        ("创99", "创世记生命读经/msg. 99 "),
        ("林后57", "哥林多后书生命读经/msg. 57 "),
        ("徒39", "使徒行传生命读经/msg. 39 "),
        ("约17", "约翰福音生命读经/msg. 17 "),
    ]:
        cid = find_cid(substr)
        if not cid:
            raise GateFail("RR", f"R4 找不到 {label}")
        knn_targets.append((label, cid))
    for cid in sorted(reembed_ids):
        if len(knn_targets) >= 10:
            break
        if cid not in {c for _, c in knn_targets}:
            knn_targets.append(("extra", cid))
    knn_results = []
    for label, cid in knn_targets:
        emb = vec_emb.get(cid)
        if emb is None:
            with vec_new.open(encoding="utf-8") as fp:
                for line in fp:
                    o = json.loads(line)
                    if o["chunk_id"] == cid:
                        emb = o["embedding"]
                        break
        resp = remote.search(
            index=ES_INDEX, size=1,
            knn={"field": "embedding", "query_vector": emb, "k": 1, "num_candidates": 50},
            _source=False,
        )
        hits = resp["hits"]["hits"]
        top = hits[0] if hits else None
        top_id = top["_id"] if top else None
        score = top.get("_score") if top else None
        knn_results.append({"label": label, "cid": cid, "top1": top_id, "score": score, "ok": top_id == cid})
    if not all(r["ok"] for r in knn_results):
        raise GateFail("RR", "R4 kNN 失败", {"knn": knn_results})

    # R5 smoke
    def uniq_msgs(field, value):
        resp = remote.search(
            index=ES_INDEX, size=0, query={"term": {field: value}},
            aggs={"mk": {"cardinality": {"field": "message_key"}}},
        )
        total = resp["hits"]["total"]["value"] if isinstance(resp["hits"]["total"], dict) else resp["hits"]["total"]
        return total, resp["aggregations"]["mk"]["value"]

    r5 = {}
    n, m = uniq_msgs("book_title", "雅歌生命读经")
    r5["雅歌生命读经"] = {"chunks": n, "msgs": m}
    r5["雅歌书生命读经"] = remote.count(index=ES_INDEX, query={"term": {"book_title": "雅歌书生命读经"}})["count"]
    n, m = uniq_msgs("book_title", "约翰二书生命读经")
    r5["约翰二书生命读经"] = {"chunks": n, "msgs": m}
    r5["约翰二书生命读经_"] = remote.count(index=ES_INDEX, query={"term": {"book_title": "约翰二书生命读经_"}})["count"]
    r5["创109"] = remote.search(
        index=ES_INDEX, size=1, query={"term": {"message_title": "成熟的表显（七）"}},
        _source=["book_title", "message_number"],
    )["hits"]["hits"]
    r5["林后57"] = remote.search(
        index=ES_INDEX, size=1, query={"term": {"message_title": "保罗为他使徒权柄的表白（八）"}},
        _source=["book_title", "message_number"],
    )["hits"]["hits"]
    r5["box_dash"] = remote.count(
        index=ES_INDEX,
        query={"bool": {
            "must": [{"wildcard": {"book_title": "*生命读经*"}}],
            "filter": [{"wildcard": {"message_title": f"*{chr(0x2500)}*"}}],
        }},
    )["count"]
    r5["esther3"] = remote.count(
        index=ES_INDEX,
        query={"bool": {"must": [
            {"term": {"book_title": "以斯帖记生命读经"}},
            {"term": {"message_number": 3}},
        ]}},
    )["count"]
    for mno, has, not_has in [(17, "干渴", "乾"), (36, "于", "於"), (37, "于", "於")]:
        hits = remote.search(
            index=ES_INDEX, size=1,
            query={"bool": {"must": [
                {"term": {"book_title": "约翰福音生命读经"}},
                {"term": {"message_number": mno}},
                {"term": {"chunk_index": 1}},
            ]}},
            _source=["message_title"],
        )["hits"]["hits"]
        mt = (hits[0]["_source"].get("message_title") if hits else "") or ""
        r5[f"john{mno}"] = {"title": mt, "ok": has in mt and not_has not in mt}
    r5["bp_雅歌书"] = remote.count(index=ES_INDEX, query={"term": {"book_path": "雅歌书生命读经"}})["count"]
    r5["bp_约翰二书_"] = remote.count(index=ES_INDEX, query={"term": {"book_path": "约翰二书生命读经_"}})["count"]

    def _hit_ok(hits, book_sub, mno):
        if not hits:
            return False
        s = hits[0]["_source"]
        return book_sub in (s.get("book_title") or "") and s.get("message_number") == mno

    r5_ok = (
        r5["雅歌生命读经"]["chunks"] == 41 and r5["雅歌生命读经"]["msgs"] == 10
        and r5["雅歌书生命读经"] == 0
        and r5["约翰二书生命读经"]["chunks"] == 11 and r5["约翰二书生命读经"]["msgs"] == 2
        and r5["约翰二书生命读经_"] == 0
        and r5["box_dash"] == 0 and r5["esther3"] == 5
        and r5["bp_雅歌书"] == 0 and r5["bp_约翰二书_"] == 0
        and r5["john17"]["ok"] and r5["john36"]["ok"] and r5["john37"]["ok"]
        and _hit_ok(r5["创109"], "创世记", 109) and _hit_ok(r5["林后57"], "哥林多后书", 57)
    )
    if not r5_ok:
        raise GateFail("RR", "R5 未全过", {"r5": {k: v for k, v in r5.items() if k not in ("创109", "林后57")}})

    # R6 header sample
    life_ids = [cid for cid, o in new_by.items() if "生命读经" in (o.get("book_title") or "")]
    other_ids = [cid for cid in new_by if cid not in set(life_ids)]
    sample_ids = rng.sample(life_ids, 100) + rng.sample(other_ids, 100)
    header_fail = 0
    for i in range(0, len(sample_ids), 50):
        batch = sample_ids[i:i + 50]
        resp = remote.mget(index=ES_INDEX, ids=batch, source=["text", "book_title", "message_title"])
        for doc in resp.get("docs") or []:
            s = doc.get("_source") or {}
            first = (s.get("text") or "").split("\n", 1)[0]
            expect = render_header(s.get("book_title"), s.get("message_title"))
            if first != expect:
                header_fail += 1
    if header_fail:
        raise GateFail("RR", f"R6 fail {header_fail}/200")

    # R7 other index counts
    cat_now = {r.get("index"): r.get("docs.count") for r in remote.cat.indices(index="panai4_*", format="json")}
    before_path = STAGING_DIR / "remote_panai4_counts_before.json"
    before = json.loads(before_path.read_text(encoding="utf-8"))["counts"] if before_path.exists() else {}
    write_res = {}
    wrp = STAGING_DIR / "remote_write_result.json"
    if wrp.exists():
        write_res = json.loads(wrp.read_text(encoding="utf-8"))
    # compare excluding 12490 docs.count may same; all should match before
    count_changed = {k: (before.get(k), cat_now.get(k)) for k in set(before) | set(cat_now) if before.get(k) != cat_now.get(k)}
    if count_changed:
        raise GateFail("RR", f"R7 其他/本索引 count 变化 {count_changed}", {"before": before, "after": cat_now})

    result = {
        "r1_same": same, "r1_diff": diff,
        "r2_checked": len(check_ids), "r2_mismatch": len(mismatch),
        "r3_n": len(remote_map), "r3_mk": mk_n,
        "r4": knn_results,
        "r5": {
            "雅歌生命读经": r5["雅歌生命读经"], "雅歌书生命读经": r5["雅歌书生命读经"],
            "约翰二书生命读经": r5["约翰二书生命读经"], "约翰二书生命读经_": r5["约翰二书生命读经_"],
            "box_dash": r5["box_dash"], "esther3": r5["esther3"],
            "bp_雅歌书": r5["bp_雅歌书"], "bp_约翰二书_": r5["bp_约翰二书_"],
            "john17": r5["john17"], "john36": r5["john36"], "john37": r5["john37"],
            "创109_hits": len(r5["创109"]), "林后57_hits": len(r5["林后57"]),
        },
        "r6_fail": header_fail,
        "r7_counts": cat_now,
        "r7_changed": count_changed,
        "write": write_res,
    }
    lines = [
        "# 生命读经修订 阶段3 remote_reconcile",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- R1 same={same} diff={diff}",
        f"- R2 checked={len(check_ids)} mismatch={len(mismatch)}",
        f"- R3 n={len(remote_map)} mk={mk_n}",
        f"- R4 knn: {knn_results}",
        f"- R5: {result['r5']}",
        f"- R6 header_fail={header_fail}/200",
        f"- R7 panai4_* counts: {cat_now}",
        f"- R7 changed vs precheck: {count_changed or '无'}",
        "- **全部通过**",
        "",
    ]
    _write_stage_report("remote_reconcile", lines)
    (ARCHIVE_DIR / "life_fix_stage3_remote_reconcile.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def write_stage3_summary(results: dict, log_path: Path, stopped_at: Optional[str] = None) -> Path:
    load_dotenv(_backend_env())
    secrets = _secret_values()
    leak = False
    for p in list(ARCHIVE_DIR.glob("life_fix_stage3*.md")) + list(LOG_DIR_DEFAULT.glob("life_fix_apply_*.log")):
        try:
            if p.stat().st_size > 20_000_000:
                continue
            data = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for s in secrets:
            if s and len(s) >= 8 and s in data:
                leak = True
                break
        if leak:
            break
    snap = folder_snapshot(OUT_DIR)
    sha_ok = True
    for ln in (BACKUP_DIR / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        parts = ln.split()
        if len(parts) < 2:
            continue
        p = BACKUP_DIR / parts[1]
        if p.exists() and sha256_file(p) != parts[0]:
            sha_ok = False
    check = results.get("remote_check") or {}
    backup = results.get("remote_backup") or {}
    wr = results.get("remote_write") or {}
    rec = results.get("remote_reconcile") or {}
    c2 = check.get("c2") or {}
    c4 = check.get("c4") or {}
    lines = [
        "# 生命读经修订 阶段3 汇总",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`；stopped={stopped_at or '无'}",
        "",
        "## 结论摘要",
        "",
        f"(1) 写入前与本机修改前一致：C2 same={c2.get('same')} diff={c2.get('diff')}；C4 non_aff_diff={c4.get('non_affected_diff_docs')} set_eq={c4.get('set_eq')}",
        f"(2) 写入成功={wr.get('ok')} 失败={wr.get('fail')}",
        f"(3) reconcile：R1 same={rec.get('r1_same')} diff={rec.get('r1_diff')}；R2 checked={rec.get('r2_checked')} mismatch={rec.get('r2_mismatch')}；"
        f"R3 n={rec.get('r3_n')} mk={rec.get('r3_mk')}；R4={rec.get('r4')}；R5={rec.get('r5')}；R6_fail={rec.get('r6_fail')}；R7={rec.get('r7_counts')}",
        f"(4) 服务器 count 写前={wr.get('count_before')} 写后={wr.get('count_after')}",
        f"(5) 其他索引 count 变化={rec.get('r7_changed') or '无（或尚未 write）'}",
        f"(6) 连接变量名：{', '.join(REMOTE_ENV_KEYS)}",
        f"(7) 回滚：`{STAGING_DIR / 'rollback_remote.py'}`；备份 `{SERVER_BEFORE_PATH}`",
        "",
        "## 最终验证",
        "",
        f"- 备份 SHA 一致={sha_ok}",
        f"- 纲目JSON 快照={snap} 期望={EXPECTED_SNAP} ok={snap == EXPECTED_SNAP}",
        f"- git：\n```\n{_git_status()}\n```",
        f"- 密钥泄露检查：{'不通过' if leak else '通过'}",
        "",
    ]
    path = ARCHIVE_DIR / "life_fix_stage3_summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("wrote %s", path)
    return path


def main(argv=None) -> int:
    stages = (
        "backup", "dryrun", "all",
        "prepare", "embed", "assemble", "verify_vec", "write_local", "reconcile",
        "rollback_local", "stage2",
        "remote_check", "remote_backup", "remote_write", "remote_reconcile", "rollback_remote",
        "stage3_precheck",
    )
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=stages, default="stage3_precheck")
    ap.add_argument("--log-dir", default=str(LOG_DIR_DEFAULT))
    args = ap.parse_args(argv)

    log_path = setup_logging(Path(args.log_dir))
    t0 = time.time()
    results: dict = {"gates": {}}
    stopped_at = None

    try:
        if args.stage in ("backup", "dryrun", "all"):
            _run_stage01_if_needed(args.stage, log_path)
            logging.info("done stage01 in %.1fs", time.time() - t0)
            return 0

        stage2_set = {
            "prepare", "embed", "assemble", "verify_vec", "write_local", "reconcile",
            "rollback_local", "stage2",
        }
        if args.stage in stage2_set:
            sequence = (
                ["prepare", "embed", "assemble", "verify_vec", "write_local", "reconcile", "rollback_local"]
                if args.stage == "stage2" else [args.stage]
            )
            runners = {
                "prepare": stage_prepare,
                "embed": stage_embed,
                "assemble": stage_assemble,
                "verify_vec": stage_verify_vec,
                "write_local": stage_write_local,
                "reconcile": stage_reconcile,
                "rollback_local": stage_rollback_local_script,
            }
            gate_of = {
                "prepare": "G1", "embed": "G2", "assemble": "G3",
                "verify_vec": "G4", "write_local": "G5", "reconcile": "G6",
            }
            for name in sequence:
                logging.info(">>> running %s", name)
                out = runners[name](log_path)
                results[name] = out
                g = gate_of.get(name)
                if g:
                    results["gates"][g] = "pass"
                if name == "verify_vec":
                    results["gates"]["G3"] = "pass"
            write_stage2_summary(results, log_path, stopped_at=None)
            logging.info("stage2 done in %.1fs", time.time() - t0)
            print(f"stage={args.stage} gates={results['gates']} elapsed={time.time()-t0:.1f}s", flush=True)
            return 0

        if args.stage == "rollback_remote":
            # only ensure script exists
            if not (STAGING_DIR / "rollback_remote.py").exists():
                stage_remote_backup(log_path)  # writes script; also re-exports — OK idempotent-ish
            else:
                logging.info("rollback_remote.py already present; not running")
            print("rollback_remote script ready; NOT executed", flush=True)
            return 0

        if args.stage in ("remote_check", "remote_backup", "stage3_precheck"):
            check = stage_remote_check(log_path) if args.stage in ("remote_check", "stage3_precheck") else None
            if args.stage == "remote_check":
                results["remote_check"] = check
                write_stage3_summary(results, log_path)
                print(f"stage=remote_check done elapsed={time.time()-t0:.1f}s", flush=True)
                return 0
            if check is None:
                # backup alone: still need prior check state
                state_path = STAGING_DIR / "remote_check_state.json"
                if not state_path.exists():
                    check = stage_remote_check(log_path)
                else:
                    check = json.loads(state_path.read_text(encoding="utf-8"))
                    # reshape minimal
                    check = {
                        "c1": check.get("c1") or {"count": check.get("c1_count"), "version": None, "cluster_name": None, "emb_ok": True},
                        "c2": check.get("c2") or {},
                        "c3": check.get("c3") or {},
                        "c4": {
                            "set_eq": (check.get("c4") or {}).get("set_eq"),
                            "local_n": 55841,
                            "remote_n": 55841,
                            "affected_diff_docs": (check.get("c4") or {}).get("aff_diff"),
                            "non_affected_diff_docs": (check.get("c4") or {}).get("non_aff_diff"),
                        },
                    }
            results["remote_check"] = check if args.stage == "stage3_precheck" else check
            if args.stage in ("remote_backup", "stage3_precheck"):
                if args.stage == "stage3_precheck" or True:
                    # always run check then backup for precheck
                    if args.stage == "stage3_precheck":
                        pass  # check already run
                    backup = stage_remote_backup(log_path)
                    results["remote_backup"] = backup
                    write_stage3_precheck(results["remote_check"], backup, log_path)
                    write_stage3_summary(results, log_path)
                    print(
                        f"PAUSE: remote_check+backup done. Reply 「写」 to continue. "
                        f"precheck={REMOTE_PRECHECK_PATH} elapsed={time.time()-t0:.1f}s",
                        flush=True,
                    )
                    return 0
            return 0

        if args.stage == "remote_write":
            results["remote_write"] = stage_remote_write(log_path)
            write_stage3_summary(results, log_path)
            print(f"stage=remote_write ok={results['remote_write'].get('ok')} elapsed={time.time()-t0:.1f}s", flush=True)
            return 0

        if args.stage == "remote_reconcile":
            results["remote_reconcile"] = stage_remote_reconcile(log_path)
            # load write result if any
            wrp = STAGING_DIR / "remote_write_result.json"
            if wrp.exists():
                results["remote_write"] = json.loads(wrp.read_text(encoding="utf-8"))
            state_path = STAGING_DIR / "remote_check_state.json"
            if state_path.exists():
                st = json.loads(state_path.read_text(encoding="utf-8"))
                results["remote_check"] = {
                    "c2": st.get("c2") or {},
                    "c4": {
                        "set_eq": (st.get("c4") or {}).get("set_eq"),
                        "non_affected_diff_docs": (st.get("c4") or {}).get("non_aff_diff"),
                    },
                }
            write_stage3_summary(results, log_path)
            print(f"stage=remote_reconcile done elapsed={time.time()-t0:.1f}s", flush=True)
            return 0

        raise SystemExit(f"unknown stage {args.stage}")

    except GateFail as gf:
        stopped_at = gf.gate
        results["gates"][gf.gate] = f"FAIL: {gf}"
        logging.error("GATE FAIL %s %s", gf.gate, gf)
        _write_stage_report(
            f"FAIL_{gf.gate}",
            [
                f"# 闸门失败 {gf.gate}",
                "",
                str(gf),
                "",
                f"payload={json.dumps(gf.payload, ensure_ascii=False, default=str)[:8000]}",
                "",
            ],
        )
        # choose summary
        if str(gf.gate).startswith("R") or gf.gate in ("RC", "RB", "RW", "RR", "REMOTE"):
            write_stage3_summary(results, log_path, stopped_at=stopped_at)
        else:
            write_stage2_summary(results, log_path, stopped_at=stopped_at)
        print(f"STOPPED at {gf.gate}: {gf}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
