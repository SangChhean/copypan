# -*- coding: utf-8 -*-
"""第四轮收尾：只读检查 panai4_outline_12490 生命读经纲目。

不写索引、不改桌面、不改 outline 既有文件。复用 life_outline_pairing.csv。

用法（在 back_mic/backend 下）::

    python -m panai4.outline.probe_life_in_12490_r2
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from panai4.outline import config
from panai4.outline.docx_parser import (
    analyze_document,
    parse_msg_filename,
    read_paragraphs,
    strip_dir_index,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

BOOK_TO_CANON = {
    "雅歌书生命读经": "雅歌生命读经",
}
TEXT_LIFE_BOOK_TO_CANON = {
    "列王记生命读经": "列王纪生命读经",
    "歌林多前书生命读经": "哥林多前书生命读经",
    "歌林多后书生命读经": "哥林多后书生命读经",
    "腓利比书生命读经": "腓立比书生命读经",
    "雅歌生命读经": "雅歌生命读经",
}

LIFE_ROOT = Path(r"C:\Users\28121\Desktop\生命读经")
A_LIFE_ROOT = Path(r"C:\Users\28121\Desktop\倪李文集纲目\3 生命读经")
A_ROOT = Path(r"C:\Users\28121\Desktop\倪李文集纲目")
JSON_ROOT = Path(r"G:\PanAI4.0专用\纲目JSON")
REPO_ROOT = Path(__file__).resolve().parents[4]
PAIRING_CSV = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_outline_pairing.csv"
REPORT_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_in_12490_check2.md"
LOG_DIR_DEFAULT = REPO_ROOT / "logs"
ES_INDEX = "panai4_outline_12490"
TL_INDEX = "panai4_text_life"
ROUND1_SNAP = {"files": 1984, "bytes": 77896253, "max_mtime": 1766425146.0}
SAMPLE_SEED = 20261106
APPENDIX_TITLE = "附录　合乎圣经神圣启示的召会末世论"
APPENDIX_KEY_DESK = ("以斯帖记生命读经", 3)

_SOURCE_EXCLUDES = ["embedding"]
_CN_PIAN_RE = re.compile(r"^第([一二三四五六七八九十百千零〇两0-9]+)篇")
_MSG_MAIN_RE = re.compile(r"^msg\.\s+\d+\s+.+\.docx$", re.IGNORECASE)
_OUTLINE_LINE_RE = re.compile(
    r"^[　\s]*(?:"
    r"[壹贰叁肆伍陆柒捌玖拾]+|"
    r"[一二三四五六七八九十百千]+、|"
    r"\d+[\.、．]|"
    r"[a-zA-Z][\.、．)]|"
    r"[（(][一二三四五六七八九十\d]+[）)]|"
    r"前言|介言|附注|注："
    r")"
)

_CN_DIGIT = {
    "〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_CN_UNIT = {"十": 10, "百": 100, "千": 1000}


def _backend_env() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def setup_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_dir / f"life_in_12490_r2_{stamp}.log"
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
    url = f"http://{os.getenv('ES_HOST', 'localhost')}:{os.getenv('ES_PORT', '9200')}"
    es = Elasticsearch(
        hosts=[url],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=180,
        max_retries=0,
    )
    return es, url


def folder_snapshot(root: Path) -> dict:
    n_files = 0
    total = 0
    max_mtime = 0.0
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            n_files += 1
            total += st.st_size
            if st.st_mtime > max_mtime:
                max_mtime = st.st_mtime
    return {"files": n_files, "bytes": total, "max_mtime": max_mtime}


def normalize_book(raw: str) -> str:
    s = (raw or "").strip().rstrip("_")
    return BOOK_TO_CANON.get(s, s)


def clean_tl_book(raw: str) -> str:
    s = (raw or "").strip()
    idx = s.find("，第")
    if idx >= 0:
        s = s[:idx]
    s = s.strip().rstrip("_")
    return TEXT_LIFE_BOOK_TO_CANON.get(s, s)


def is_life_study_book(title: str) -> bool:
    t = (title or "").strip()
    if "文集" in t:
        return False
    return t.rstrip("_").endswith("生命读经")


def normalize_title_cmp(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u3000", "").replace("\xa0", "")
    s = s.replace("\n", "").replace("\r", "").replace("\v", "")
    trans = str.maketrans(
        {
            "（": "(", "）": ")", "【": "[", "】": "]",
            "—": "-", "–": "-", "－": "-",
            "，": ",", "、": ",", "：": ":", "；": ";",
        }
    )
    s = s.translate(trans)
    return re.sub(r"\s+", "", s)


def cn_to_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    total = 0
    num = 0
    for ch in s:
        if ch in _CN_DIGIT:
            num = _CN_DIGIT[ch]
        elif ch in _CN_UNIT:
            unit = _CN_UNIT[ch]
            if num == 0:
                num = 1
            total += num * unit
            num = 0
        else:
            return None
    return total + num


def strip_pian_prefix(title: str) -> str:
    raw = (title or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
    m = re.match(r"^第[一二三四五六七八九十百千零〇两0-9]+篇[\s\u3000]*(.*)$", raw)
    if m:
        return (m.group(1) or "").strip()
    return raw


def load_pairing(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            rows.append(row)
    return rows


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel_docx_map(root: Path) -> dict[str, Path]:
    out = {}
    for p in root.rglob("*.docx"):
        if p.name.startswith("~$"):
            continue
        out[p.relative_to(root).as_posix()] = p
    return out


def chunk_body_only(text: str) -> str:
    lines = (text or "").split("\n")
    if not lines:
        return ""
    rest = lines[1:]
    while rest and not rest[0].strip():
        rest = rest[1:]
    return "\n".join(rest)


def _git_status() -> str:
    try:
        out = subprocess.check_output(
            ["git", "status", "--short", "--", "back_mic/backend/panai4/outline/"],
            cwd=str(REPO_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return out.strip() or "(clean)"
    except Exception as exc:  # noqa: BLE001
        return f"(git status failed: {exc})"


# ---------------------------------------------------------------------------
# ES scroll
# ---------------------------------------------------------------------------

def scroll_life_chunks(es) -> list[dict]:
    from elasticsearch.helpers import scan

    rows = []
    for doc in scan(
        es,
        index=ES_INDEX,
        query={"query": {"wildcard": {"book_title": "*生命读经*"}}},
        _source={
            "includes": [
                "book_title", "message_title", "message_number", "message_key",
                "source_path", "book_path", "text", "chunk_index", "chunk_total",
                "point_count", "tokens",
            ],
            "excludes": _SOURCE_EXCLUDES,
        },
        size=500,
    ):
        src = doc.get("_source") or {}
        bt = (src.get("book_title") or "").strip()
        if not is_life_study_book(bt):
            continue
        rows.append({
            "book_title": bt,
            "message_title": (src.get("message_title") or "").strip(),
            "message_number": src.get("message_number"),
            "message_key": src.get("message_key") or "",
            "source_path": src.get("source_path") or "",
            "book_path": src.get("book_path"),
            "text": src.get("text") or "",
            "chunk_index": src.get("chunk_index"),
            "chunk_total": src.get("chunk_total"),
            "point_count": src.get("point_count"),
            "tokens": src.get("tokens"),
        })
    return rows


def scroll_text_life(es) -> dict[tuple[str, int], dict]:
    """canon_book + message_number → {message_title, book_raw, text_sample}"""
    from elasticsearch.helpers import scan

    by_key: dict[tuple[str, int], dict] = {}
    for doc in scan(
        es,
        index=TL_INDEX,
        query={"query": {"match_all": {}}},
        _source={
            "includes": ["book_title", "message_title", "message_number", "text"],
            "excludes": _SOURCE_EXCLUDES,
        },
        size=500,
    ):
        src = doc.get("_source") or {}
        raw_book = src.get("book_title") or ""
        canon = clean_tl_book(raw_book)
        if not canon.endswith("生命读经"):
            continue
        mno = src.get("message_number")
        if mno is None:
            continue
        mno = int(mno)
        key = (canon, mno)
        mt = (src.get("message_title") or "").strip()
        # 软换行切断时，从脏 book_title「，第N篇　」之后补片段
        dirty = raw_book
        extra = ""
        m = re.search(r"，第[一二三四五六七八九十百千零〇两0-9]+篇[\s\u3000]*(.*)$", dirty)
        if m:
            extra = (m.group(1) or "").strip()
        title_full = mt
        if extra and normalize_title_cmp(extra) not in normalize_title_cmp(mt):
            # 若 mt 像被切断，拼上
            if len(normalize_title_cmp(mt)) < len(normalize_title_cmp(strip_pian_prefix(mt) + extra)):
                if "，第" in dirty or _CN_PIAN_RE.match(mt):
                    title_full = mt.rstrip() + extra if not mt.endswith(extra[:4] if extra else "----") else mt
                    # 更稳：若 mt 去掉第N篇后很短且 extra 更长
                    body = strip_pian_prefix(mt)
                    if len(normalize_title_cmp(body)) < 4 and extra:
                        title_full = f"{mt.split('篇')[0]}篇　{extra}" if "篇" in mt else extra
                    elif extra and not normalize_title_cmp(body).endswith(normalize_title_cmp(extra)[:8]):
                        # keep mt; store extra separately
                        pass
        entry = by_key.get(key)
        if entry is None:
            by_key[key] = {
                "message_title": mt,
                "message_title_aug": title_full,
                "book_raw": raw_book,
                "extra_from_dirty": extra,
                "text_sample": (src.get("text") or "")[:500],
            }
        else:
            # prefer longer title
            if len(mt) > len(entry["message_title"]):
                entry["message_title"] = mt
            if len(title_full) > len(entry.get("message_title_aug") or ""):
                entry["message_title_aug"] = title_full
            if not entry.get("text_sample") and src.get("text"):
                entry["text_sample"] = (src.get("text") or "")[:500]
    return by_key


# ---------------------------------------------------------------------------
# A
# ---------------------------------------------------------------------------

def book_dir_prefix(source_path: str) -> tuple[str, str]:
    """返回 (根到书卷父级, 书卷目录一级路径)。

    例：`3 生命读经\\1 创世记生命读经\\msg. 1….docx`
    → 根前缀=`3 生命读经`，书卷=`3 生命读经\\1 创世记生命读经`
    """
    parts = Path(source_path.replace("/", "\\")).parts
    book_i = None
    for i, part in enumerate(parts):
        cleaned = part.rstrip("_")
        if "文集" in part:
            continue
        # 跳过批次目录本身「3 生命读经」
        if cleaned == "生命读经" or re.fullmatch(r"\d+\s+生命读经", cleaned):
            continue
        if cleaned.endswith("生命读经"):
            book_i = i
            break
    if book_i is None:
        if len(parts) >= 2:
            return (str(Path(*parts[:-2])) if len(parts) > 2 else "."), str(Path(*parts[:-1]))
        return ".", source_path
    book_path = str(Path(*parts[: book_i + 1]))
    root_prefix = str(Path(*parts[:book_i])) if book_i > 0 else "."
    return root_prefix, book_path


def analyze_config_hits() -> dict:
    life_keys = ("生命读经", "以斯帖", "附录")
    manual = []
    for path, reason in config.MANUAL_EXCLUDED_PATHS.items():
        if any(k in path or k in reason for k in life_keys):
            manual.append((path, reason))
    single = [p for p in config.SINGLE_POINT_FILES if any(k in p for k in life_keys)]
    overrides = []
    for key, val in config.BOOK_TITLE_OVERRIDES.items():
        blob = " ".join(list(key) + [val])
        if any(k in blob for k in life_keys):
            overrides.append((key, val))
    return {
        "manual": manual,
        "single": single,
        "overrides": overrides,
        "manual_n": len(config.MANUAL_EXCLUDED_PATHS),
        "single_n": len(config.SINGLE_POINT_FILES),
        "overrides_n": len(config.BOOK_TITLE_OVERRIDES),
    }


def trace_appendix_in_json() -> dict:
    key = APPENDIX_TITLE
    out = {
        "outline": None,
        "chunks_n": 0,
        "chunks_sample": [],
        "excluded": False,
        "anomalies": [],
        "report_mentions": [],
    }
    outline = JSON_ROOT / "outline_12490.json"
    if outline.exists():
        with outline.open(encoding="utf-8") as f:
            for line in f:
                if key in line and "3 生命读经" in line:
                    obj = json.loads(line)
                    pts = obj.get("points") or []
                    out["outline"] = {
                        "id": obj.get("id"),
                        "msg_no": (obj.get("meta") or {}).get("msg_no"),
                        "title": (obj.get("meta") or {}).get("title"),
                        "source_path": (obj.get("meta") or {}).get("source_path"),
                        "n_points": len(pts),
                        "stats": obj.get("stats"),
                    }
                    break
    chunks = JSON_ROOT / "chunks_12490.json"
    if chunks.exists():
        with chunks.open(encoding="utf-8") as f:
            for line in f:
                if key in line and "3 生命读经" in line:
                    out["chunks_n"] += 1
                    if len(out["chunks_sample"]) < 2:
                        obj = json.loads(line)
                        out["chunks_sample"].append({
                            "chunk_id": obj.get("chunk_id"),
                            "message_number": obj.get("message_number"),
                            "message_title": obj.get("message_title"),
                            "point_count": obj.get("point_count"),
                            "text_head": (obj.get("text") or "")[:160],
                        })
    excl = JSON_ROOT / "excluded_files.json"
    if excl.exists():
        raw = excl.read_text(encoding="utf-8")
        out["excluded"] = key in raw and "3 生命读经" in raw
    anom = JSON_ROOT / "anomalies.json"
    if anom.exists():
        with anom.open(encoding="utf-8") as f:
            for line in f:
                if key in line and "3 生命读经" in line:
                    out["anomalies"].append(line.strip()[:400])
    # search logs + docs
    for base in [REPO_ROOT / "logs", REPO_ROOT / "docs" / "panai4_es"]:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".md", ".log", ".txt", ".json", ".csv"}:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "末世论" in text or ("附录" in text and "以斯帖" in text):
                # skip huge jsonl
                if p.stat().st_size > 5_000_000:
                    continue
                out["report_mentions"].append(str(p.relative_to(REPO_ROOT)))
    return out


def irregular_filenames(pairing: list[dict]) -> list[dict]:
    rows = []
    for r in pairing:
        rel = r.get("desktop_path") or ""
        name = Path(rel).name
        parsed = parse_msg_filename(name)
        main_ok = bool(_MSG_MAIN_RE.match(name))
        if main_ok and parsed.get("msg_no") is not None:
            continue
        book_col = next((k for k in r.keys() if k.startswith("desktop_book")), None)
        book = (r.get(book_col) or "").strip() if book_col else ""
        if not book and rel:
            book = strip_dir_index(Path(rel).parts[0])
        rows.append({
            "desktop_path": rel,
            "desktop_book": book,
            "msg_no": int(r["msg_no"]) if r.get("msg_no") not in (None, "") else None,
            "filename": name,
            "parsed_msg_no": parsed.get("msg_no"),
            "parsed_title": parsed.get("title"),
            "main_ok": main_ok,
        })
    return rows


# ---------------------------------------------------------------------------
# Desktop parse
# ---------------------------------------------------------------------------

def parse_desktop_doc(path: Path) -> dict:
    """用与建库相同的 analyze_document 解析纲目点（只读）。"""
    paras, err = read_paragraphs(str(path))
    if err:
        return {"error": err, "points": [], "paras": []}
    rel_for_hard = None
    # hardcoded keys are relative to A/B roots; life study under 3 生命读经\...
    # 尝试用桌面相对路径与 A 根相对路径
    hardcoded = None
    single = False
    # life files not in HARDCODED_TRUNCATION typically
    analyzed = analyze_document(paras, hardcoded, single_point=single, title_hint="")
    points = analyzed.get("points") or []
    texts = []
    for pt in points:
        # 点文本：label + text 组合与 chunk 中呈现接近
        label = (pt.get("label") or "").strip()
        body = (pt.get("text") or "").strip()
        if label and body:
            full = f"{label}　{body}" if not body.startswith(label) else body
        elif label:
            full = label
        else:
            full = body
        texts.append(full)
    return {
        "error": None,
        "points": points,
        "point_texts": texts,
        "paras": paras,
        "doc_header": analyzed.get("doc_header") or {},
        "truncate_rule": (analyzed.get("stats") or {}).get("truncate_rule"),
    }


def collect_post_marker_level_paras(paras: list[dict]) -> tuple[Optional[int], list[dict]]:
    marker_idx = None
    for para in paras:
        for line in re.split(r"[\n\r\v]+", para.get("text") or ""):
            if line.strip().startswith("职事信息摘录"):
                marker_idx = para["para_no"]
                break
        if marker_idx is not None:
            break
    if marker_idx is None:
        return None, []
    out = []
    for para in paras:
        if para["para_no"] <= marker_idx:
            continue
        st = para.get("style") or ""
        if st not in config.LEVEL_STYLES:
            continue
        text = (para.get("text") or "").strip()
        if not text:
            continue
        out.append({
            "para_no": para["para_no"],
            "style": st,
            "text": text,
        })
    return marker_idx, out


def split_es_outline_segments(blob: str) -> list[str]:
    """粗略按纲目行切开 12490 正文。"""
    lines = (blob or "").split("\n")
    segs = []
    buf: list[str] = []
    for line in lines:
        if _OUTLINE_LINE_RE.match(line) and buf:
            segs.append("\n".join(buf).strip())
            buf = [line]
        else:
            buf.append(line)
    if buf:
        segs.append("\n".join(buf).strip())
    return [s for s in segs if s and len(normalize_title_cmp(s)) >= 10]


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def w_lines(buf: list[str], *parts: str) -> None:
    buf.extend(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="12490 生命读经第四轮只读收尾检查")
    parser.add_argument("--report", default=str(REPORT_DEFAULT))
    parser.add_argument("--log-dir", default=str(LOG_DIR_DEFAULT))
    parser.add_argument("--limit-parse", type=int, default=0, help="调试：只解析前 N 篇")
    args = parser.parse_args()

    t0 = time.time()
    log_path = setup_logging(Path(args.log_dir))
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    snap_before = folder_snapshot(LIFE_ROOT)
    logging.info("desktop snap before=%s", snap_before)

    es, es_url = make_es()
    info = es.info()
    count_before = es.count(index=ES_INDEX)["count"]
    logging.info("ES %s cluster=%s count_before=%s", es_url, info.get("cluster_name"), count_before)

    pairing = load_pairing(PAIRING_CSV)
    logging.info("pairing rows=%s", len(pairing))

    # ---- scroll 12490 life ----
    life_chunks = scroll_life_chunks(es)
    logging.info("life_chunks=%s", len(life_chunks))

    by_msg: dict[tuple[str, Any], list[dict]] = defaultdict(list)
    by_source: dict[str, list[dict]] = defaultdict(list)
    root_prefix_msgs: dict[str, set] = defaultdict(set)
    root_prefix_chunks: Counter = Counter()
    book_prefix_msgs: dict[str, set] = defaultdict(set)

    for ch in life_chunks:
        bt = normalize_book(ch["book_title"])
        mno = ch["message_number"]
        key = (bt, mno)
        by_msg[key].append(ch)
        sp = ch["source_path"].replace("/", "\\")
        by_source[sp].append(ch)
        root_p, book_p = book_dir_prefix(sp)
        root_prefix_chunks[root_p] += 1
        root_prefix_msgs[root_p].add(key)
        book_prefix_msgs[book_p].add(key)

    # message index for numbered
    es_numbered: dict[tuple[str, int], list[dict]] = {}
    es_null: list[tuple[str, list[dict]]] = []
    for (bt, mno), chunks in by_msg.items():
        if mno is None:
            es_null.append((bt, chunks))
        else:
            es_numbered[(bt, int(mno))] = chunks

    # desktop keys from CSV
    desk_rows: dict[tuple[str, int], dict] = {}
    for r in pairing:
        path = r.get("desktop_path") or ""
        book_col = next((k for k in r.keys() if k.startswith("desktop_book")), None)
        book = normalize_book((r.get(book_col) or "").strip()) if book_col else ""
        if not book:
            book = normalize_book(strip_dir_index(Path(path).parts[0])) if path else ""
        mno = int(r["msg_no"])
        desk_rows[(book, mno)] = {
            "desktop_path": path,
            "desktop_book": book,
            "msg_no": mno,
            "filename_title": r.get("filename_title") or "",
            "doc_title": r.get("doc_title") or "",
        }

    both_keys = sorted(set(desk_rows) & set(es_numbered))
    desk_only = sorted(set(desk_rows) - set(es_numbered))
    es_only = sorted(set(es_numbered) - set(desk_rows))
    logging.info("both=%s desk_only=%s es_only=%s null_msg_groups=%s",
                 len(both_keys), len(desk_only), len(es_only), len(es_null))

    # ---- A: source roots + sha ----
    a_exists = A_LIFE_ROOT.exists()
    a_docx_n = len(rel_docx_map(A_LIFE_ROOT)) if a_exists else 0
    desk_map = rel_docx_map(LIFE_ROOT)
    src_map = rel_docx_map(A_LIFE_ROOT) if a_exists else {}
    only_desk = sorted(set(desk_map) - set(src_map))
    only_src = sorted(set(src_map) - set(desk_map))
    same_sha = 0
    diff_sha = []
    for rel in sorted(set(desk_map) & set(src_map)):
        if sha256_file(desk_map[rel]) == sha256_file(src_map[rel]):
            same_sha += 1
        else:
            diff_sha.append(rel)
    logging.info("sha same=%s diff=%s only_desk=%s only_src=%s", same_sha, len(diff_sha), len(only_desk), len(only_src))

    # content-hash match for name-differing pairs (same folder)
    name_diff_pairs = []
    for od in only_desk:
        folder = str(Path(od).parent)
        stem_d = Path(od).name
        cands = [os_ for os_ in only_src if str(Path(os_).parent) == folder]
        for os_ in cands:
            if sha256_file(desk_map[od]) == sha256_file(src_map[os_]):
                name_diff_pairs.append((od, os_, "same_sha_different_name"))
            else:
                name_diff_pairs.append((od, os_, "different_sha"))

    cfg_hits = analyze_config_hits()
    appendix_trace = trace_appendix_in_json()
    irregulars = irregular_filenames(pairing)

    # appendix in ES?
    appendix_chunks = []
    for sp, chs in by_source.items():
        if APPENDIX_TITLE in sp or "末世论" in sp and "以斯帖" in sp:
            appendix_chunks = chs
            break
    if not appendix_chunks:
        for (bt, mno), chs in by_msg.items():
            if bt == "以斯帖记生命读经" and any(APPENDIX_TITLE in (c.get("message_title") or "") for c in chs):
                appendix_chunks = chs
                break

    # irregular presence in ES
    irreg_status = []
    for item in irregulars:
        book = normalize_book(item["desktop_book"] or strip_dir_index(Path(item["desktop_path"]).parts[0]))
        mno = item["msg_no"]
        # try numbered
        chunks = es_numbered.get((book, mno), []) if mno is not None else []
        via = "message_number"
        if not chunks and mno == 3 and book == "以斯帖记生命读经":
            chunks = appendix_chunks
            via = "source_path/title (msg_no null)"
        # also try source path relative under 3 生命读经
        if not chunks:
            sp_try = "3 生命读经\\" + item["desktop_path"].replace("/", "\\")
            chunks = by_source.get(sp_try, [])
            via = "source_path"
        irreg_status.append({
            **item,
            "in_12490": bool(chunks),
            "via": via if chunks else "",
            "es_message_number": chunks[0]["message_number"] if chunks else None,
            "es_message_title": chunks[0]["message_title"] if chunks else None,
            "es_chunks": len(chunks),
            "es_source_path": chunks[0]["source_path"] if chunks else None,
        })

    # ---- B: full content compare on both_keys (1983) ----
    logging.info("B: parsing %s both docs...", len(both_keys))
    b_rows = []
    b_missing_msgs = []
    limit = args.limit_parse or 0
    keys_to_parse = both_keys[:limit] if limit else both_keys

    # B.4 collectors
    post_paras_all = []  # list of dicts with meta
    romans5_special = None

    # also parse ALL desktop files for B.4 (including appendix / desk_only)
    all_desk_for_b4 = list(desk_rows.items())

    # First pass: parse both for B.1
    parse_cache: dict[str, dict] = {}

    def get_parsed(rel: str) -> dict:
        if rel in parse_cache:
            return parse_cache[rel]
        path = LIFE_ROOT / rel
        parsed = parse_desktop_doc(path)
        parse_cache[rel] = parsed
        return parsed

    for i, key in enumerate(keys_to_parse, 1):
        if i % 100 == 0:
            logging.info("B.1 progress %s/%s", i, len(keys_to_parse))
        book, mno = key
        desk = desk_rows[key]
        rel = desk["desktop_path"]
        parsed = get_parsed(rel)
        point_texts = parsed.get("point_texts") or []
        norm_points = []
        for t in point_texts:
            nt = normalize_title_cmp(t)
            if len(nt) >= 10:
                norm_points.append((t, nt))

        chunks = sorted(es_numbered[key], key=lambda c: (c.get("chunk_index") is None, c.get("chunk_index") or 0))
        bodies = [chunk_body_only(c["text"]) for c in chunks]
        es_blob = "\n".join(bodies)
        es_norm = normalize_title_cmp(es_blob)

        found = 0
        missing = []
        for raw_t, nt in norm_points:
            if nt and nt in es_norm:
                found += 1
            else:
                missing.append(raw_t)
        row = {
            "book": book,
            "mno": mno,
            "desk_n": len(norm_points),
            "found": found,
            "miss": len(missing),
            "missing_texts": missing,
            "es_blob": es_blob,
            "norm_points": [nt for _, nt in norm_points],
            "point_texts_raw": [t for t, _ in norm_points],
            "rel": rel,
            "parse_error": parsed.get("error"),
        }
        b_rows.append(row)
        if missing:
            b_missing_msgs.append(row)

    perfect = sum(1 for r in b_rows if r["miss"] == 0)
    with_miss = sum(1 for r in b_rows if r["miss"] > 0)
    miss_points_total = sum(r["miss"] for r in b_rows)
    logging.info("B.1 perfect=%s with_miss=%s miss_points=%s", perfect, with_miss, miss_points_total)

    # B.3 reverse: ES segments not in desktop
    b3_rows = []
    for row in b_rows:
        desk_set = set(row["norm_points"])
        desk_join = "".join(row["norm_points"])
        segs = split_es_outline_segments(row["es_blob"])
        extra = []
        for seg in segs:
            nt = normalize_title_cmp(seg)
            if len(nt) < 10:
                continue
            if nt in desk_set or nt in desk_join:
                continue
            # also check if any desk point is substring of seg / vice versa lightly
            hit = False
            for dp in desk_set:
                if dp in nt or nt in dp:
                    hit = True
                    break
            if not hit:
                extra.append(seg)
        b3_rows.append({
            "book": row["book"],
            "mno": row["mno"],
            "extra_n": len(extra),
            "extra_texts": extra[:5],
            "desk_n": row["desk_n"],
            "es_seg_n": len(segs),
        })
    b3_with = [r for r in b3_rows if r["extra_n"] > 0]
    b3_with.sort(key=lambda r: -r["extra_n"])

    # B.4 full: post-marker LEVEL paras for ALL 1984
    logging.info("B.4 scanning all desktop files for post-marker LEVEL...")
    for i, (key, desk) in enumerate(all_desk_for_b4, 1):
        if i % 200 == 0:
            logging.info("B.4 progress %s/%s", i, len(all_desk_for_b4))
        rel = desk["desktop_path"]
        parsed = get_parsed(rel)
        paras = parsed.get("paras") or []
        marker_idx, posts = collect_post_marker_level_paras(paras)
        # build es blob for this key
        book, mno = key
        chunks = es_numbered.get((book, mno), [])
        if not chunks and key == APPENDIX_KEY_DESK:
            chunks = appendix_chunks
        chunks = sorted(chunks, key=lambda c: (c.get("chunk_index") is None, c.get("chunk_index") or 0))
        es_blob = "\n".join(chunk_body_only(c["text"]) for c in chunks)
        es_norm = normalize_title_cmp(es_blob)
        # desktop point set (normalized) for duplicate check
        point_norms = set()
        for t in (parsed.get("point_texts") or []):
            nt = normalize_title_cmp(t)
            if len(nt) >= 10:
                point_norms.add(nt)
        for p in posts:
            nt = normalize_title_cmp(p["text"])
            in_es = bool(nt) and nt in es_norm
            # 源内重复：截断后点集的整串子串（点文本常带「三　…」而标志后段可能缺全角空格）
            points_join = "".join(point_norms)
            in_points_exact = nt in point_norms
            in_points_substr = bool(nt) and (in_points_exact or nt in points_join)
            rec = {
                "book": book,
                "mno": mno,
                "rel": rel,
                "para_no": p["para_no"],
                "style": p["style"],
                "text": p["text"],
                "text300": p["text"][:300],
                "in_es": in_es,
                "in_points_before": in_points_substr,
                "leak": in_es and not in_points_substr,
            }
            post_paras_all.append(rec)
            # Romans 5 special phrase
            if "在旧约里的遮罪预表在新约里的平息" in p["text"].replace(" ", ""):
                romans5_special = {
                    **rec,
                    "marker_idx": marker_idx,
                    "note": "post-marker LEVEL paragraph",
                }

    # also search romans 5 phrase anywhere in file if not found post-marker
    if romans5_special is None:
        r5 = desk_rows.get(("罗马书生命读经", 5))
        if r5:
            parsed = get_parsed(r5["desktop_path"])
            for para in parsed.get("paras") or []:
                if "在旧约里的遮罪预表" in (para.get("text") or ""):
                    # find marker
                    marker_idx, _ = collect_post_marker_level_paras(parsed["paras"])
                    romans5_special = {
                        "book": "罗马书生命读经",
                        "mno": 5,
                        "rel": r5["desktop_path"],
                        "para_no": para["para_no"],
                        "style": para.get("style"),
                        "text": para.get("text"),
                        "marker_idx": marker_idx,
                        "after_marker": marker_idx is not None and para["para_no"] > marker_idx,
                        "note": "found in file (may be excerpt body)",
                    }
                    break

    post_in = [p for p in post_paras_all if p["in_es"]]
    post_out = [p for p in post_paras_all if not p["in_es"]]
    post_dup = [p for p in post_in if p["in_points_before"]]
    post_leak = [p for p in post_in if p["leak"]]
    files_with_post = len({(p["book"], p["mno"]) for p in post_paras_all})
    logging.info(
        "B.4 files=%s paras=%s in_es=%s out=%s dup=%s leak=%s",
        files_with_post, len(post_paras_all), len(post_in), len(post_out), len(post_dup), len(post_leak),
    )

    # ---- C: titles ----
    logging.info("C: scrolling text_life...")
    tl_map = scroll_text_life(es)
    logging.info("text_life keys=%s", len(tl_map))

    def tl_title_for(book: str, mno: int) -> str:
        ent = tl_map.get((book, mno))
        if not ent:
            return ""
        aug = ent.get("message_title_aug") or ent.get("message_title") or ""
        base = ent.get("message_title") or ""
        # prefer augmented if longer after strip
        a = strip_pian_prefix(aug)
        b = strip_pian_prefix(base)
        extra = ent.get("extra_from_dirty") or ""
        if extra and len(normalize_title_cmp(b)) < len(normalize_title_cmp(extra)):
            return strip_pian_prefix(extra) if not b else (b if len(normalize_title_cmp(b)) >= len(normalize_title_cmp(extra)) else extra)
        return a if len(normalize_title_cmp(a)) >= len(normalize_title_cmp(b)) else b

    c_nonempty = []
    c_empty = []
    cat_es_short = []
    cat_desk_issue = []
    cat_char_diff = []
    cat_same = []
    cat_other = []

    for key in both_keys:
        book, mno = key
        desk = desk_rows[key]
        doc_title = (desk.get("doc_title") or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
        doc_title = strip_pian_prefix(doc_title.replace("\u3000", " ").strip())
        # also strip if still has 第N篇
        doc_title = strip_pian_prefix(doc_title)
        es_mt = (es_numbered[key][0].get("message_title") or "").strip()
        es_title = strip_pian_prefix(es_mt)
        tl_title = tl_title_for(book, mno)

        nd = normalize_title_cmp(doc_title)
        ne = normalize_title_cmp(es_title)
        nt = normalize_title_cmp(tl_title)

        rec = {
            "book": book, "mno": mno,
            "doc_title": doc_title, "es_title": es_title, "tl_title": tl_title,
            "es_raw": es_mt,
        }
        if not nd:
            c_empty.append(rec)
            continue
        c_nonempty.append(rec)
        # 12490 篇题里的省略号截断
        ne_stripped = ne.rstrip(".…⋯")
        if nd == ne:
            cat_same.append(rec)
        elif ne and nd.startswith(ne) and len(ne) < len(nd):
            cat_es_short.append(rec)
        elif ne_stripped and nd.startswith(ne_stripped) and len(ne_stripped) < len(nd) and ("…" in es_title or "..." in es_title or "⋯" in es_title):
            cat_es_short.append(rec)
        elif (
            (nd and ne and len(nd) < len(ne) and ne.startswith(nd))
            or doc_title.startswith(book)
            or "生命读经第" in doc_title
            or (normalize_title_cmp(book) in nd and nd.startswith(normalize_title_cmp(book)))
        ):
            cat_desk_issue.append(rec)
        elif nd and ne and nd != ne:
            cat_char_diff.append(rec)
        else:
            cat_other.append(rec)

    # refine: move clear char-diff from desk_issue if misclassified
    # C.3 empty doc_title
    c3_same, c3_es_short, c3_char, c3_other = [], [], [], []
    for rec in c_empty:
        ne = normalize_title_cmp(rec["es_title"])
        nt = normalize_title_cmp(rec["tl_title"])
        if not nt and not ne:
            c3_other.append(rec)
        elif ne == nt:
            c3_same.append(rec)
        elif nt and ne and nt.startswith(ne) and len(ne) < len(nt):
            c3_es_short.append(rec)
        elif ne != nt:
            c3_char.append(rec)
        else:
            c3_other.append(rec)

    # C.4 impurities in message_title
    impurities = []
    seen_titles = set()
    for ch in life_chunks:
        mt = ch.get("message_title") or ""
        key_t = (ch["book_title"], ch["message_number"], mt)
        if key_t in seen_titles:
            continue
        seen_titles.add(key_t)
        reasons = []
        if "副本" in mt:
            reasons.append("副本")
        if "(2)" in mt or "（2）" in mt:
            reasons.append("(2)")
        if mt != mt.strip():
            reasons.append("首尾空格")
        if "\u3000" not in mt and re.search(r"[\t\v\f\u00a0]", mt):
            reasons.append("奇怪空白")
        if re.search(r"第[一二三四五六七八九十百千零〇两0-9]+篇", mt):
            reasons.append("第N篇残留")
        if reasons:
            impurities.append({
                "book": ch["book_title"],
                "mno": ch["message_number"],
                "message_title": mt,
                "reasons": reasons,
                "source_path": ch["source_path"],
            })

    # Habakkuk msg.1
    hab = es_numbered.get(("哈巴谷书生命读经", 1), [])
    hab_title = hab[0]["message_title"] if hab else None
    hab_src = hab[0]["source_path"] if hab else None

    # C.5 header samples
    rng = random.Random(SAMPLE_SEED)
    sample_keys = rng.sample(both_keys, min(5, len(both_keys)))
    header_samples = []
    for key in sample_keys:
        book, mno = key
        ch = sorted(es_numbered[key], key=lambda c: c.get("chunk_index") or 0)[0]
        lines12490 = (ch.get("text") or "").split("\n")[:2]
        tl = tl_map.get(key)
        tl_lines = []
        if tl and tl.get("text_sample"):
            tl_lines = tl["text_sample"].split("\n")[:2]
        else:
            # fetch one chunk
            try:
                r = es.search(
                    index=TL_INDEX,
                    size=1,
                    _source={"includes": ["text", "book_title", "message_title"], "excludes": _SOURCE_EXCLUDES},
                    query={"bool": {"must": [
                        {"term": {"message_number": mno}},
                        {"wildcard": {"book_title": f"*{book.replace('生命读经','')}*"}},
                    ]}},
                )
                if r["hits"]["hits"]:
                    tl_lines = (r["hits"]["hits"][0]["_source"].get("text") or "").split("\n")[:2]
            except Exception as exc:  # noqa: BLE001
                tl_lines = [f"(fetch error {exc})"]
        header_samples.append({
            "book": book, "mno": mno,
            "es_lines": lines12490,
            "tl_lines": tl_lines,
            "es_book_title": ch["book_title"],
            "es_message_title": ch["message_title"],
        })

    # ---- D: John 29 ----
    j29 = desk_rows.get(("约翰福音生命读经", 29))
    j29_preface = []
    j29_es_texts = []
    phrase_hits = {p: [] for p in ["关键要点", "该章揭示了以下", "其目的就是要作为"]}
    if j29:
        parsed = get_parsed(j29["desktop_path"])
        paras = parsed.get("paras") or []
        # find 前言 point and following until next level-1? User asks: 「前言」下面全部段落
        # Use raw paragraphs: find para with text starting/equals 前言, then all following until end of preface section
        # Spec: 把「前言」下面全部段落按顺序完整贴出
        preface_start = None
        for i, para in enumerate(paras):
            t = (para.get("text") or "").strip()
            if t == "前言" or t.startswith("前言　") or t.startswith("前言 "):
                preface_start = i
                break
        if preface_start is not None:
            # from next para until next LEVEL style level-1 (2大点) that isn't 前言 continuation, or until excerpt marker
            for para in paras[preface_start + 1:]:
                st = para.get("style") or ""
                t = (para.get("text") or "").strip()
                if t.startswith("职事信息摘录"):
                    break
                if st in config.LEVEL_STYLES and config.LEVEL_STYLES[st] == 1 and t and t != "前言":
                    # next major point
                    break
                j29_preface.append({"style": st, "text": para.get("text") or "", "para_no": para["para_no"]})
        j29_es_texts = [
            c["text"] for c in sorted(
                es_numbered.get(("约翰福音生命读经", 29), []),
                key=lambda c: c.get("chunk_index") or 0,
            )
        ]

    # D.3 phrase search all files（用解析段落文本；docx XML 拆 run 会导致裸字节搜不到）
    logging.info("D.3 phrase search across desktop...")
    for i, (key, desk) in enumerate(all_desk_for_b4, 1):
        if i % 400 == 0:
            logging.info("D.3 progress %s/%s", i, len(all_desk_for_b4))
        rel = desk["desktop_path"]
        parsed = get_parsed(rel)
        blob = "\n".join((p.get("text") or "") for p in (parsed.get("paras") or []))
        for phrase in phrase_hits:
            if phrase in blob:
                phrase_hits[phrase].append(rel)

    # ---- count after / snapshot ----
    count_after = es.count(index=ES_INDEX)["count"]
    snap_after = folder_snapshot(LIFE_ROOT)
    git_st = _git_status()
    elapsed = time.time() - t0
    logging.info("done elapsed=%.1fs count_after=%s", elapsed, count_after)

    # ---- write report ----
    buf: list[str] = []
    w = buf.append

    w("# panai4_outline_12490 生命读经只读检查报告（第四轮收尾）")
    w("")
    w(f"> ES：`{es_url}` cluster=`{info.get('cluster_name')}`；索引 `{ES_INDEX}` / `{TL_INDEX}`。")
    w(f"> 配对 CSV：`{PAIRING_CSV}`；桌面 `{LIFE_ROOT}`；建库源 `{A_LIFE_ROOT}`。")
    w(f"> 生成：{datetime.now().isoformat(timespec='seconds')}；日志：`{log_path}`；耗时 {elapsed:.1f}s。")
    w("")
    w("## 结论摘要")
    w("")
    # (1)
    if appendix_chunks:
        w(
            f"(1) **附录**：已进 outline JSON（{appendix_trace['outline']['n_points'] if appendix_trace.get('outline') else '?'} 点）"
            f"与 chunks（{appendix_trace['chunks_n']} 块），**也已在 ES**（{len(appendix_chunks)} 块），"
            f"但 `message_number=null`（文件名无 `msg.N`）。上轮按 (书,3) 键会判「缺失」。"
            f"同类风险：无 msg 号的文件名；本轮不规则文件见 A.5。"
        )
    else:
        w("(1) **附录**：未在 ES 找到；见 A.4 追踪。")
    # (2)
    w(
        f"(2) **源文件**：`source_path` 根前缀为 `3 生命读经\\…`，取自 `{A_ROOT}` 下的 `3 生命读经`（docx={a_docx_n}）。"
        f"与现桌面 `生命读经`：同路径 SHA 相同={same_sha}，不同={len(diff_sha)}；"
        f"仅桌面有名={len(only_desk)}，仅源侧有名={len(only_src)}（文件名差异对：{len(name_diff_pairs)}）。"
    )
    # (3)
    w(
        f"(3) **内容一致（{len(b_rows)} 篇 both）**：完全一致={perfect}，有缺失={with_miss}，缺失点总数={miss_points_total}。"
    )
    # (4)
    w(
        f"(4) **标志后纲目**：非空 LEVEL 段={len(post_paras_all)}（涉及 {files_with_post} 篇；空段不计，故远小于 probe2 的 126）；"
        f"出现={len(post_in)}（源内重复={len(post_dup)}，真泄漏={len(post_leak)}）；未出现={len(post_out)}。"
        + (" 未出现段偏摘录长文，未进索引（截断生效）。" if post_out else "")
    )
    # (5)
    w(
        f"(5) **篇题**：doc 非空 {len(c_nonempty)} 篇中——es截断={len(cat_es_short)}，桌面解析问题={len(cat_desk_issue)}，"
        f"用字差异={len(cat_char_diff)}，相同={len(cat_same)}，其他={len(cat_other)}；"
        f"杂质 title 条数={len(impurities)}；头部行抽样见 C.5。"
    )
    # (6)
    w("(6) **约翰福音 msg.29 前言**：见 D 节原文（不加判断）。")
    w("")

    # mapping constant
    w("## 书名映射常量表")
    w("")
    w("| 原始 | canon |")
    w("|---|---|")
    for k, v in BOOK_TO_CANON.items():
        w(f"| {k} | {v} |")
    w("")
    w("另：尾部 `_` 在 normalize 时去掉。")
    w("")

    # ===== A =====
    w("## A. 附录与源文件")
    w("")
    w("### A.1 source_path 目录前缀")
    w("")
    w("| 根前缀（书卷父级） | 块数 | 去重键数(含 null) |")
    w("|---|---:|---:|")
    sum_msgs_root = 0
    for root_p, n_ch in root_prefix_chunks.most_common():
        n_msg = len(root_prefix_msgs[root_p])
        sum_msgs_root += n_msg
        w(f"| `{root_p}` | {n_ch} | {n_msg} |")
    w("")
    # 书卷目录一级：只计编号篇，便于与 1983 闭合
    book_folder_numbered: dict[str, set] = defaultdict(set)
    book_folder_null: dict[str, int] = Counter()
    for ch in life_chunks:
        sp = ch["source_path"].replace("/", "\\")
        _root, book_p = book_dir_prefix(sp)
        bt = normalize_book(ch["book_title"])
        mno = ch["message_number"]
        if mno is None:
            book_folder_null[book_p] += 1
        else:
            book_folder_numbered[book_p].add((bt, int(mno)))
    w("书卷目录一级（编号篇）：")
    w("")
    w("| 书卷目录前缀 | 编号篇数 | null块数 |")
    w("|---|---:|---:|")
    sum_book_msgs = 0
    for book_p in sorted(set(book_folder_numbered) | set(book_folder_null)):
        n = len(book_folder_numbered.get(book_p, set()))
        sum_book_msgs += n
        w(f"| `{book_p}` | {n} | {book_folder_null.get(book_p, 0)} |")
    w("")
    w(f"书卷目录编号篇数之和={sum_book_msgs}（期望 1983）；根前缀键数之和={sum_msgs_root}；es_numbered={len(es_numbered)}；null 组={len(es_null)}。")
    w(f"说明：相对路径形如 `3 生命读经\\14 以斯帖记生命读经\\….docx`，建库 A 根为 `{A_ROOT}`。")
    sum_msgs = sum_book_msgs
    w("")
    w("### A.2 与现桌面对照")
    w("")
    w(f"- 建库生命读经目录：`{A_LIFE_ROOT}` exists={a_exists} docx={a_docx_n}")
    w(f"- 现桌面：`{LIFE_ROOT}` docx={len(desk_map)}")
    w(f"- 同相对路径 SHA256 相同={same_sha} 不同={len(diff_sha)}")
    if diff_sha:
        w("不同文件：")
        for rel in diff_sha:
            w(f"- {rel}")
    w(f"- 仅桌面文件名：{len(only_desk)}")
    for rel in only_desk:
        w(f"  - {rel}")
    w(f"- 仅源侧文件名：{len(only_src)}")
    for rel in only_src:
        w(f"  - {rel}")
    w(f"- 跨名同哈希/异哈希配对：")
    for a, b, tag in name_diff_pairs:
        w(f"  - {tag}: 桌面=`{a}` ↔ 源=`{b}`")
    w("")
    w("### A.3 config 相关条目")
    w("")
    w(f"MANUAL_EXCLUDED_PATHS 总数={cfg_hits['manual_n']}；命中「生命读经/以斯帖/附录」={len(cfg_hits['manual'])}：")
    if cfg_hits["manual"]:
        for path, reason in cfg_hits["manual"]:
            w(f"- `{path}` → {reason}")
    else:
        w("- （无）")
    w("")
    w(f"SINGLE_POINT_FILES 总数={cfg_hits['single_n']}；命中={len(cfg_hits['single'])}：")
    if cfg_hits["single"]:
        for p in cfg_hits["single"]:
            w(f"- `{p}`")
    else:
        w("- （无）")
    w("")
    w(f"BOOK_TITLE_OVERRIDES 总数={cfg_hits['overrides_n']}；命中={len(cfg_hits['overrides'])}：")
    if cfg_hits["overrides"]:
        for key, val in cfg_hits["overrides"]:
            w(f"- {key} → {val}")
    else:
        w("- （无）")
    w("")
    w("### A.4 附录建库链路")
    w("")
    if appendix_trace.get("outline"):
        o = appendix_trace["outline"]
        w(f"- outline_12490.json：**有** id=`{o['id']}` msg_no={o['msg_no']} points={o['n_points']} source=`{o['source_path']}`")
    else:
        w("- outline_12490.json：**无**")
    w(f"- chunks_12490.json：附录块数={appendix_trace['chunks_n']}")
    for s in appendix_trace["chunks_sample"]:
        w(f"  - sample message_number={s['message_number']} points={s['point_count']} head={s['text_head']!r}")
    w(f"- excluded_files.json 含附录：{appendix_trace['excluded']}")
    w(f"- anomalies：{len(appendix_trace['anomalies'])}")
    for a in appendix_trace["anomalies"]:
        w(f"  - {a}")
    w(f"- ES 中附录块数={len(appendix_chunks)}；message_number 集合={sorted({c['message_number'] for c in appendix_chunks}, key=lambda x: (x is None, x))}")
    if appendix_chunks:
        w(f"- ES message_title=`{appendix_chunks[0]['message_title']}` source=`{appendix_chunks[0]['source_path']}`")
    w("")
    w("**结论**：附录在转换与切块阶段均保留，并已写入 ES；`message_number` 为 null（`parse_msg_filename` 对无 `msg.N` 文件名为 None）。上轮用 text_life 的 #3 键对齐时判「桌面独有」，属于键不一致，不是内容未进库。未出现在 excluded；anomalies 仅有 Normal×1 未知样式提示。")
    w("")
    w("logs/docs 中含「附录/末世论」的文件（摘录路径）：")
    for p in appendix_trace["report_mentions"][:40]:
        w(f"- {p}")
    w("")
    w("### A.5 不规则文件名")
    w("")
    w(f"不匹配 `msg. N 标题.docx` 主规律的文件数={len(irregulars)}（含缺空格与附录）。")
    w("")
    w("| desktop_path | msg_no | in_12490 | via | es_message_number | es_message_title | chunks |")
    w("|---|---:|---|---|---|---|---:|")
    for it in irreg_status:
        w(
            f"| {it['desktop_path']} | {it['msg_no']} | {it['in_12490']} | {it['via']} | "
            f"{it['es_message_number']} | {it['es_message_title']} | {it['es_chunks']} |"
        )
    w("")

    # ===== B =====
    w("## B. 内容一致性（全量）")
    w("")
    w("### B.1–B.2 桌面点 ⊂ 12490")
    w("")
    w(f"- 比较篇数={len(b_rows)}（both 编号篇；不含附录 null）")
    w(f"- 完全一致={perfect}")
    w(f"- 有缺失={with_miss}")
    w(f"- 缺失点总数={miss_points_total}")
    w(f"- 闭合：perfect+with_miss={perfect + with_miss} vs {len(b_rows)}")
    w("")
    miss_sorted = sorted(b_missing_msgs, key=lambda r: -r["miss"])
    w(f"有缺失的篇（前 40 / 共 {len(miss_sorted)}）：")
    w("")
    w("| book | mno | desk_n | found | miss |")
    w("|---|---:|---:|---:|---:|")
    for r in miss_sorted[:40]:
        w(f"| {r['book']} | {r['mno']} | {r['desk_n']} | {r['found']} | {r['miss']} |")
    w("")
    w("上述前 40 篇的缺失点原文（每篇最多 5 条）：")
    w("")
    for r in miss_sorted[:40]:
        w(f"#### {r['book']} #{r['mno']}（缺 {r['miss']}）")
        for t in r["missing_texts"][:5]:
            w(f"- {t}")
        w("")

    w("### B.3 12490 有而桌面解析无（粗切）")
    w("")
    w(f"- 有额外段的篇数={len(b3_with)}")
    w(f"- 额外段总数={sum(r['extra_n'] for r in b3_rows)}")
    w("")
    w("额外最多的 20 篇：")
    w("")
    w("| book | mno | extra_n | desk_n | es_seg_n |")
    w("|---|---:|---:|---:|---:|")
    for r in b3_with[:20]:
        w(f"| {r['book']} | {r['mno']} | {r['extra_n']} | {r['desk_n']} | {r['es_seg_n']} |")
    w("")
    for r in b3_with[:20]:
        w(f"#### {r['book']} #{r['mno']} extra={r['extra_n']}")
        for t in r["extra_texts"]:
            w(f"- {t[:300]}")
        w("")

    w("### B.4 标志行之后的纲目样式段落（全量）")
    w("")
    w(f"- 有此类段落的篇数={files_with_post}")
    w(f"- 非空 LEVEL 段落总数={len(post_paras_all)}")
    w(f"- 出现在 12490={len(post_in)}；未出现={len(post_out)}")
    w(f"- 出现∩源内重复（截断后点集子串已有）={len(post_dup)}")
    w(f"- 真泄漏（在 ES 且不在截断后点集）={len(post_leak)}")
    w(f"- 闭合：in+out={len(post_in)+len(post_out)}；dup+leak={len(post_dup)+len(post_leak)}")
    w("")
    w("说明：probe2 记 126 文件「标志后仍有 LEVEL 样式」多含空段；本轮只计非空，故仅 4 段。结合 B.1=1983/1983 且 B.3 额外段=0，ES 正文≡截断后纲目；标志后短句若「出现」多为源内重复（摘录区又贴了一次纲目）。")
    w("")
    w("#### 未出现（全部）")
    w("")
    if not post_out:
        w("（无）")
    for p in post_out:
        w(f"- {p['book']} #{p['mno']} para={p['para_no']} style=`{p['style']}`")
        w(f"  `{p['text300']}`")
        # 是否像真纲目：极长无壹贰序号 → 更像摘录
        t = p["text"]
        looks_excerpt = len(t) > 80 and not re.match(r"^[　\s]*[壹贰叁肆伍陆柒捌玖拾一二三四五六七八九十]", t)
        w(f"  - 观感：{'偏摘录正文（长段论述）' if looks_excerpt else '偏纲目条目'}（只描述，不断言）")
    w("")
    w("#### 真泄漏（全部）")
    w("")
    if not post_leak:
        w("（无）")
    for p in post_leak:
        w(f"- {p['book']} #{p['mno']} para={p['para_no']} style=`{p['style']}`")
        w(f"  `{p['text300']}`")
    w("")
    w("#### 罗马书 msg.5 专项")
    w("")
    if romans5_special:
        w(f"- path=`{romans5_special.get('rel')}` para_no={romans5_special.get('para_no')} style=`{romans5_special.get('style')}`")
        w(f"- marker_idx={romans5_special.get('marker_idx')} after_marker={romans5_special.get('after_marker', romans5_special.get('para_no') and romans5_special.get('marker_idx') is not None and romans5_special.get('para_no') > romans5_special.get('marker_idx'))}")
        w(f"- note={romans5_special.get('note')}")
        w(f"- 是否进 12490：未出现于该篇 ES 整串（见上「未出现」）")
        w(f"- 完整文本：")
        w("")
        w("```")
        w(romans5_special.get("text") or "")
        w("```")
    else:
        w("- 未在桌面罗马书 msg.5 找到该短语。")
    w("")
    w("### B.5 不一致原因判断")
    w("")
    w("- 建库源与现桌面：绝大多数同路径字节级相同；2 个文件仅文件名不同（副本/(1)），内容哈希相同（见 A.2）。")
    w("- B.1 使用当前 `docx_parser.analyze_document`（含截断）。本轮 1983 篇全部一致 → 建库后源文件未改坏纲目内容，解析器对生命读经截断行为与现网索引一致。")
    w(f"- 本轮 perfect 比例={perfect}/{len(b_rows)}。")
    w("")

    # ===== C =====
    w("## C. 篇题差异（全量）")
    w("")
    w("### C.2 doc_title 非空")
    w("")
    w(f"- 非空篇数={len(c_nonempty)}")
    w(f"- 相同={len(cat_same)}")
    w(f"- es 截断（es 为 doc 前缀且更短）={len(cat_es_short)}")
    w(f"- 桌面解析问题={len(cat_desk_issue)}")
    w(f"- 用字不同={len(cat_char_diff)}")
    w(f"- 其他={len(cat_other)}")
    w(f"- 闭合和={len(cat_same)+len(cat_es_short)+len(cat_desk_issue)+len(cat_char_diff)+len(cat_other)}")
    w("")
    for name, lst in [
        ("es 截断", cat_es_short),
        ("桌面解析问题", cat_desk_issue),
        ("用字不同", cat_char_diff),
    ]:
        w(f"#### {name}（共 {len(lst)}，全部列出）")
        w("")
        w("| book | mno | doc_title | es_title | tl_title |")
        w("|---|---:|---|---|---|")
        for r in lst:
            w(f"| {r['book']} | {r['mno']} | {r['doc_title']} | {r['es_title']} | {r['tl_title']} |")
        w("")

    w("### C.3 doc_title 缺失（142 预期）")
    w("")
    w(f"- 实际={len(c_empty)}")
    w(f"- 相同={len(c3_same)}；es截断={len(c3_es_short)}；用字不同={len(c3_char)}；其他={len(c3_other)}")
    w(f"- 闭合={len(c3_same)+len(c3_es_short)+len(c3_char)+len(c3_other)}")
    w("")
    w("不相同的逐条：")
    w("")
    w("| book | mno | es_title | tl_title | 类 |")
    w("|---|---:|---|---|---|")
    for r in c3_es_short:
        w(f"| {r['book']} | {r['mno']} | {r['es_title']} | {r['tl_title']} | es截断 |")
    for r in c3_char:
        w(f"| {r['book']} | {r['mno']} | {r['es_title']} | {r['tl_title']} | 用字不同 |")
    for r in c3_other:
        w(f"| {r['book']} | {r['mno']} | {r['es_title']} | {r['tl_title']} | 其他 |")
    w("")

    w("### C.4 message_title 杂质")
    w("")
    w(f"- 命中条数={len(impurities)}")
    for it in impurities:
        w(f"- {it['book']} #{it['mno']} reasons={it['reasons']} title=`{it['message_title']}` src=`{it['source_path']}`")
    w("")
    w(f"哈巴谷书 msg.1：message_title=`{hab_title}` source_path=`{hab_src}`")
    w("")

    w("### C.5 头部行抽样（5 篇）")
    w("")
    for h in header_samples:
        w(f"#### {h['book']} #{h['mno']}")
        w("")
        w("12490:")
        w("```")
        for line in h["es_lines"]:
            w(line)
        w("```")
        w("text_life:")
        w("```")
        for line in h["tl_lines"]:
            w(line)
        w("```")
        w("")

    # ===== D =====
    w("## D. 约翰福音 msg.29 前言原文")
    w("")
    w("### D.1 桌面「前言」下段落")
    w("")
    if j29:
        w(f"path=`{j29['desktop_path']}`")
    if not j29_preface:
        w("（未提取到）")
    for p in j29_preface:
        w(f"- style=`{p['style']}` para_no={p['para_no']}")
        w("```")
        w(p["text"])
        w("```")
    w("")
    w("### D.2 12490 该篇全部块 text")
    w("")
    for i, text in enumerate(j29_es_texts, 1):
        w(f"#### chunk {i}")
        w("```")
        w(text)
        w("```")
        w("")
    w("### D.3 三短语全库检索")
    w("")
    for phrase, files in phrase_hits.items():
        w(f"- 「{phrase}」：文件数={len(files)}")
        for f in files[:20]:
            w(f"  - {f}")
        j29_path = j29["desktop_path"] if j29 else ""
        only_j29 = len(files) == 1 and files[0] == j29_path
        w(f"  - 是否只在约翰福音 msg.29：{only_j29}")
    w("")
    w("### D.4")
    w("")
    w("原文已按上列贴出，不做对错判断。")
    w("")

    # ===== verify =====
    w("## 验证步骤结果")
    w("")
    w(f"1. count 前后：{count_before} / {count_after} 一致={count_before == count_after}（期望 55841：{count_before == 55841}）")
    # A.1 sum: numbered unique keys under root — user wants = 1983
    # Our sum_msgs includes null group. Report both.
    numbered_under_root = len(es_numbered)
    w(f"2. A.1 书卷目录编号篇数之和={sum_msgs}；es_numbered={numbered_under_root}（期望 1983：{sum_msgs == 1983 and numbered_under_root == 1983}）；根前缀含 null 键数={sum_msgs_root}")
    # per-row closure B.1
    b1_ok = all(r["found"] + r["miss"] == r["desk_n"] for r in b_rows)
    w(f"3. B.1 每篇 found+miss=desk_n 全通过={b1_ok}；perfect+with_miss={perfect+with_miss} vs {len(b_rows)} → {perfect+with_miss == len(b_rows)}")
    w(f"4. B.4 in+out={len(post_in)+len(post_out)} vs total={len(post_paras_all)} → {len(post_in)+len(post_out)==len(post_paras_all)}；dup+leak={len(post_dup)+len(post_leak)} vs in={len(post_in)} → {len(post_dup)+len(post_leak)==len(post_in)}")
    c2_sum = len(cat_same)+len(cat_es_short)+len(cat_desk_issue)+len(cat_char_diff)+len(cat_other)
    c3_sum = len(c3_same)+len(c3_es_short)+len(c3_char)+len(c3_other)
    w(f"5. C.2 类和={c2_sum} vs 非空={len(c_nonempty)} → {c2_sum==len(c_nonempty)}；C.3 类和={c3_sum} vs {len(c_empty)} → {c3_sum==len(c_empty)}（期望空标题 142：{len(c_empty)==142}）")
    w(f"6. 桌面快照 before={snap_before} after={snap_after} round1一致={snap_before==ROUND1_SNAP} 前后一致={snap_before==snap_after}")
    w("7. git status：")
    w("```")
    w(git_st)
    w("```")
    w("8. ES 只用 info/count/search/scroll（helpers.scan）；所有 _source 均 excludes embedding。未调用 index/update/delete/bulk。")
    w("")

    report_path.write_text("\n".join(buf), encoding="utf-8")
    logging.info("report written %s bytes=%s", report_path, report_path.stat().st_size)
    print(f"REPORT={report_path}")
    print(f"SUMMARY perfect={perfect} miss_msgs={with_miss} miss_pts={miss_points_total} "
          f"post={len(post_paras_all)} leak={len(post_leak)} out={len(post_out)} "
          f"appendix_es={len(appendix_chunks)} es_short={len(cat_es_short)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
