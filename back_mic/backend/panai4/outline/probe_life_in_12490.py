# -*- coding: utf-8 -*-
"""只读检查 panai4_outline_12490 中的生命读经纲目。

不新建索引、不改桌面、不改 outline 既有代码。复用 life_outline_pairing.csv。

用法（在 back_mic/backend 下）::

    python -m panai4.outline.probe_life_in_12490
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import random
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 书名映射常量表（显式）
# ---------------------------------------------------------------------------

# 12490 / 桌面 → 对齐用 canon（新索引决定写法）
BOOK_TO_CANON = {
    "雅歌书生命读经": "雅歌生命读经",
}

LIFE_ROOT = Path(r"C:\Users\28121\Desktop\生命读经")
REPO_ROOT = Path(__file__).resolve().parents[4]
PAIRING_CSV = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_outline_pairing.csv"
REPORT_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_in_12490_check.md"
LOG_DIR_DEFAULT = REPO_ROOT / "logs"
ES_INDEX = "panai4_outline_12490"
ROUND1_SNAP = {"files": 1984, "bytes": 77896253, "max_mtime": 1766425146.0}
SAMPLE_SEED = 20261106
LEVEL_STYLES_CHECK = {"2大点", "3中点", "4小点", "大点", "中点", "小点"}
_CN_PIAN_RE = re.compile(r"^第([一二三四五六七八九十百千零〇两0-9]+)篇")
_CN_DIGIT = {
    "〇": 0,
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CN_UNIT = {"十": 10, "百": 100, "千": 1000}


def _backend_env() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def setup_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_dir / f"life_in_12490_{stamp}.log"
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
        request_timeout=120,
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


def is_life_study_book(title: str) -> bool:
    """本系列：以「生命读经」结尾（允许尾部下划线），且不含「文集」。"""
    t = (title or "").strip()
    if "文集" in t:
        return False
    t2 = t.rstrip("_")
    return t2.endswith("生命读经")


def is_excluded_life_like(title: str) -> bool:
    t = (title or "").strip()
    return "生命读经" in t and not is_life_study_book(t)


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


def normalize_title_cmp(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u3000", "").replace("\xa0", "")
    s = s.replace("\n", "").replace("\r", "").replace("\v", "")
    trans = str.maketrans(
        {
            "（": "(",
            "）": ")",
            "【": "[",
            "】": "]",
            "—": "-",
            "–": "-",
            "－": "-",
            "，": ",",
            "、": ",",
            "：": ":",
            "；": ";",
        }
    )
    s = s.translate(trans)
    return re.sub(r"\s+", "", s)


def strip_pian_prefix_title(message_title: str) -> str:
    """若 message_title 以第N篇开头则去掉；12490 通常已是纯篇题。"""
    raw = (message_title or "").strip()
    m = re.match(r"^第[一二三四五六七八九十百千零〇两0-9]+篇[\s\u3000]*(.*)$", raw)
    if m:
        return (m.group(1) or "").strip()
    return raw


def extract_pian_no(message_title: str) -> Optional[int]:
    m = _CN_PIAN_RE.match((message_title or "").strip())
    if not m:
        return None
    return cn_to_int(m.group(1))


def load_pairing(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            rows.append(row)
    return rows


def scroll_life_chunks(es) -> tuple[list[dict], list[dict], dict]:
    from elasticsearch.helpers import scan

    mapping = es.indices.get_mapping(index=ES_INDEX)[ES_INDEX]["mappings"]["properties"]
    life_chunks = []
    excluded_chunks = []
    for doc in scan(
        es,
        index=ES_INDEX,
        query={"query": {"wildcard": {"book_title": "*生命读经*"}}},
        _source=[
            "book_title",
            "message_title",
            "message_number",
            "message_key",
            "source_path",
            "text",
            "tokens",
            "point_count",
            "chunk_index",
            "chunk_total",
        ],
        size=500,
    ):
        src = doc.get("_source") or {}
        bt = (src.get("book_title") or "").strip()
        row = {
            "book_title": bt,
            "message_title": (src.get("message_title") or "").strip(),
            "message_number": src.get("message_number"),
            "message_key": src.get("message_key") or "",
            "source_path": src.get("source_path") or "",
            "text": src.get("text") or "",
            "tokens": src.get("tokens"),
            "point_count": src.get("point_count"),
            "chunk_index": src.get("chunk_index"),
            "chunk_total": src.get("chunk_total"),
        }
        if is_life_study_book(bt):
            life_chunks.append(row)
        elif is_excluded_life_like(bt):
            excluded_chunks.append(row)
    return life_chunks, excluded_chunks, mapping


def find_outline_after_excerpt_files(root: Path, limit_scan: Optional[int] = None) -> list[str]:
    """复现 probe2：标志行之后仍有 LEVEL 样式的文件。"""
    from panai4.outline.docx_parser import read_paragraphs
    from panai4.outline import config

    found = []
    paths = sorted(
        [p for p in root.rglob("*.docx") if p.is_file() and not p.name.startswith("~$")],
        key=lambda p: p.as_posix().lower(),
    )
    if limit_scan:
        paths = paths[:limit_scan]
    for path in paths:
        paras, err = read_paragraphs(str(path))
        if err:
            continue
        marker_idx = None
        for para in paras:
            for line in re.split(r"[\n\r\v]+", para.get("text") or ""):
                compact = line.strip()
                if compact.startswith("职事信息摘录"):
                    marker_idx = para["para_no"]
                    break
            if marker_idx is not None:
                break
        if marker_idx is None:
            continue
        for para in paras:
            if para["para_no"] <= marker_idx:
                continue
            st = para.get("style") or ""
            if st in config.LEVEL_STYLES or st in LEVEL_STYLES_CHECK:
                found.append(path.relative_to(root).as_posix())
                break
    return found


def sample_post_marker_level_texts(root: Path, rel: str, n: int = 3) -> list[dict]:
    from panai4.outline.docx_parser import read_paragraphs
    from panai4.outline import config

    path = root / rel
    paras, err = read_paragraphs(str(path))
    if err:
        return [{"error": err}]
    marker_idx = None
    for para in paras:
        for line in re.split(r"[\n\r\v]+", para.get("text") or ""):
            if line.strip().startswith("职事信息摘录"):
                marker_idx = para["para_no"]
                break
        if marker_idx is not None:
            break
    out = []
    for para in paras:
        if marker_idx is None or para["para_no"] <= marker_idx:
            continue
        st = para.get("style") or ""
        if st not in LEVEL_STYLES_CHECK and st not in config.LEVEL_STYLES:
            continue
        text = (para.get("text") or "").strip()
        if not text:
            continue
        out.append({"style": st, "text": text, "para_no": para["para_no"]})
        if len(out) >= n:
            break
    return out


def chunk_body_only(text: str) -> str:
    """去掉头部行与随后空行，剩正文。"""
    lines = (text or "").split("\n")
    if not lines:
        return ""
    # drop first line (header)
    rest = lines[1:]
    while rest and not rest[0].strip():
        rest = rest[1:]
    return "\n".join(rest).strip()


def is_preface_only_chunk(text: str) -> bool:
    body = chunk_body_only(text)
    if not body:
        return False
    # 几乎只有「前言」行
    compact = re.sub(r"[\s\u3000]+", "", body)
    return compact in {"前言", "前言：", "前言:", "序言", "序言：", "添言", "添言："} or (
        len(compact) <= 6 and compact.startswith("前言")
    )


def _git_status() -> str:
    import subprocess

    try:
        out = subprocess.check_output(
            ["git", "status", "--short", "--", "back_mic/backend/panai4/outline/"],
            cwd=str(REPO_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:  # noqa: BLE001
        return f"(failed: {exc})"
    return out.strip() or "(clean)"


def run(report_path: Path, log_path: Path) -> int:
    t0 = time.time()
    rng = random.Random(SAMPLE_SEED)
    snap_before = folder_snapshot(LIFE_ROOT)
    logging.info("snap_before=%s", snap_before)

    if not PAIRING_CSV.is_file():
        logging.error("missing pairing csv %s", PAIRING_CSV)
        return 2
    pairing = load_pairing(PAIRING_CSV)
    logging.info("pairing rows=%s", len(pairing))

    es, es_url = make_es()
    info = es.info()
    count_before = es.count(index=ES_INDEX)["count"]
    logging.info("ES %s count=%s", es_url, count_before)

    life_chunks, excluded_chunks, mapping = scroll_life_chunks(es)
    logging.info("life_chunks=%s excluded=%s", len(life_chunks), len(excluded_chunks))

    # excluded book titles
    excluded_books = Counter(c["book_title"] for c in excluded_chunks)

    # aggregate by book_title and by message
    by_book_chunks: Counter = Counter()
    by_book_msgs: dict[str, set] = defaultdict(set)
    msgs: dict[tuple[str, int], dict] = {}
    for c in life_chunks:
        bt = c["book_title"]
        by_book_chunks[bt] += 1
        mno = c["message_number"]
        if mno is None:
            continue
        try:
            mno_i = int(mno)
        except (TypeError, ValueError):
            continue
        by_book_msgs[bt].add(mno_i)
        canon = normalize_book(bt)
        key = (canon, mno_i)
        if key not in msgs:
            msgs[key] = {
                "book_raw": bt,
                "book_canon": canon,
                "message_number": mno_i,
                "message_title": c["message_title"],
                "message_key": c["message_key"],
                "chunks": [],
                "dirty": "，第" in bt,
            }
        msgs[key]["chunks"].append(c)
        # prefer non-empty title
        if not msgs[key]["message_title"] and c["message_title"]:
            msgs[key]["message_title"] = c["message_title"]

    # desktop keys from CSV
    desk: dict[tuple[str, int], dict] = {}
    for row in pairing:
        book = normalize_book(row["desktop_book(映射后)"])
        mno = int(row["msg_no"])
        desk[(book, mno)] = row

    both = set(desk) & set(msgs)
    desk_only = set(desk) - set(msgs)
    es_only = set(msgs) - set(desk)

    desk_only_by_book: Counter = Counter(k[0] for k in desk_only)

    # special cases
    special_checks = []
    specials = [
        ("附录", "以斯帖", None, "附录"),
        ("创世记", None, 25, None),
        ("利未记", None, 15, None),
        ("马可福音", None, 55, None),
        ("约翰福音", None, 13, None),
    ]
    for book_hint, _b2, mno_hint, title_hint in [
        ("以斯帖记生命读经", None, 3, "附录"),
        ("创世记生命读经", None, 25, None),
        ("利未记生命读经", None, 15, None),
        ("马可福音生命读经", None, 55, None),
        ("约翰福音生命读经", None, 13, None),
    ]:
        key = (normalize_book(book_hint), mno_hint)
        em = msgs.get(key)
        desk_row = desk.get(key)
        special_checks.append(
            {
                "key": key,
                "in_12490": em is not None,
                "message_title": (em or {}).get("message_title"),
                "book_raw": (em or {}).get("book_raw"),
                "n_chunks": len((em or {}).get("chunks") or []),
                "desktop": desk_row,
            }
        )

    # book title spelling classes
    spelling = {"规范": [], "需改名": [], "脏片段": [], "尾部下划线": []}
    for bt, n_chunks in sorted(by_book_chunks.items(), key=lambda x: -x[1]):
        canon = normalize_book(bt)
        n_msgs = len(by_book_msgs.get(bt, []))
        item = {"book_title": bt, "canon": canon, "msgs": n_msgs, "chunks": n_chunks}
        if "，第" in bt:
            spelling["脏片段"].append(item)
        elif bt.rstrip("_") != bt:
            spelling["尾部下划线"].append(item)
        elif bt != canon:
            spelling["需改名"].append(item)
        else:
            spelling["规范"].append(item)

    # 3.1 excerpt in text
    excerpt_chunks = [c for c in life_chunks if "职事信息摘录" in (c.get("text") or "")]
    # sample 20 long chunks without 壹贰叁 markers
    long_candidates = []
    for c in life_chunks:
        body = chunk_body_only(c.get("text") or "")
        if len(body) < 400:
            continue
        if re.search(r"[壹贰叁肆伍陆柒捌玖]|[一二三四五六七八九十]、|\t", body):
            continue
        long_candidates.append(c)
    rng.shuffle(long_candidates)
    excerptish_samples = long_candidates[:20]

    # 3.2 post-marker level texts
    logging.info("scanning desktop for outline-after-excerpt files...")
    after_files = find_outline_after_excerpt_files(LIFE_ROOT)
    logging.info("outline_after_excerpt files=%s", len(after_files))
    # 优先抽「标志后确有非空 LEVEL 文本」的文件
    scored = []
    for rel in after_files:
        samples = sample_post_marker_level_texts(LIFE_ROOT, rel, 3)
        nonempty = [s for s in samples if s.get("text")]
        if nonempty:
            scored.append((rel, nonempty))
    rng.shuffle(scored)
    pick_scored = scored[:10]
    # 若不足 10，用无非空样本的文件补齐并注明
    if len(pick_scored) < 10:
        used = {r for r, _ in pick_scored}
        rest = [r for r in after_files if r not in used]
        rng.shuffle(rest)
        for rel in rest:
            if len(pick_scored) >= 10:
                break
            pick_scored.append((rel, sample_post_marker_level_texts(LIFE_ROOT, rel, 3)))

    post_marker_check = []
    for rel, samples in pick_scored:
        results = []
        for s in samples:
            if s.get("error"):
                results.append({**s, "found": False})
                continue
            if not s.get("text"):
                continue
            needle = (s["text"] or "")[:40]
            hit_rows = [r for r in pairing if r["desktop_path"] == rel]
            chunks_for_msg = []
            if hit_rows:
                book = normalize_book(hit_rows[0]["desktop_book(映射后)"])
                mno = int(hit_rows[0]["msg_no"])
                em = msgs.get((book, mno))
                if em:
                    chunks_for_msg = em["chunks"]
            blob = "\n".join(c.get("text") or "" for c in chunks_for_msg)
            found = needle in blob or normalize_title_cmp(needle) in normalize_title_cmp(blob)
            results.append({"style": s.get("style"), "text40": needle, "found": found})
        post_marker_check.append(
            {
                "rel": rel,
                "results": results,
                "note": "无非空LEVEL样本" if not results else "",
            }
        )

    # 3.3 message_title compare
    title_cats: Counter = Counter()
    title_examples: dict[str, list] = defaultdict(list)
    for key in both:
        row = desk[key]
        em = msgs[key]
        doc_t = normalize_title_cmp(row.get("doc_title") or "")
        mt_raw = em.get("message_title") or ""
        mt = normalize_title_cmp(strip_pian_prefix_title(mt_raw))
        if not mt:
            cat = "12490为空或缺失"
        elif doc_t == mt:
            cat = "相同"
        elif "插进的话" in mt_raw or "插进的话" in (row.get("doc_title") or ""):
            if doc_t.replace(normalize_title_cmp("（插进的话）"), "") == mt.replace(
                normalize_title_cmp("（插进的话）"), ""
            ) or doc_t in mt or mt in doc_t:
                cat = "12490多了后缀/插进的话类"
            elif doc_t == mt:
                cat = "相同"
            else:
                # still check suffix pattern
                if mt.startswith(doc_t) or doc_t.startswith(mt):
                    cat = "12490多了后缀/插进的话类"
                else:
                    cat = "篇题用字差异"
        elif mt.startswith(doc_t) or doc_t.startswith(mt):
            cat = "12490多了后缀/插进的话类"
        elif doc_t and mt:
            cat = "篇题用字差异"
        else:
            cat = "其他"
        title_cats[cat] += 1
        if len(title_examples[cat]) < 8:
            title_examples[cat].append(
                {
                    "key": key,
                    "doc": (row.get("doc_title") or "")[:50],
                    "mt": mt_raw[:50],
                    "path": row.get("desktop_path"),
                }
            )

    # refine: if doc empty
    # recount with doc missing
    title_cats = Counter()
    title_examples = defaultdict(list)
    for key in both:
        row = desk[key]
        em = msgs[key]
        doc_raw = row.get("doc_title") or ""
        doc_t = normalize_title_cmp(doc_raw)
        mt_raw = em.get("message_title") or ""
        mt = normalize_title_cmp(strip_pian_prefix_title(mt_raw))
        if not mt:
            cat = "12490为空或缺失"
        elif not doc_t:
            cat = "其他"  # desktop doc missing; still compare filename?
            # use filename_title
            fn_t = normalize_title_cmp(row.get("filename_title") or "")
            if fn_t == mt:
                cat = "相同"  # treat as same via filename when doc missing? user asked vs doc_title
                cat = "其他"
            else:
                cat = "其他"
        elif doc_t == mt:
            cat = "相同"
        elif ("插进" in mt_raw) or mt.startswith(doc_t) or (
            normalize_title_cmp(doc_raw + "（插进的话）") == mt
        ):
            cat = "12490多了后缀/插进的话类"
        elif doc_t != mt:
            cat = "篇题用字差异"
        else:
            cat = "其他"
        title_cats[cat] += 1
        if len(title_examples[cat]) < 8:
            title_examples[cat].append(
                {
                    "key": key,
                    "doc": doc_raw[:50],
                    "mt": mt_raw[:50],
                    "path": row.get("desktop_path"),
                }
            )

    # 3.4 出埃及记 102-131
    exodus_rows = []
    for mno in range(102, 132):
        key = ("出埃及记生命读经", mno)
        em = msgs.get(key)
        desk_row = desk.get(key)
        mt = (em or {}).get("message_title") or ""
        pian = extract_pian_no(mt)
        # 12490 message_title usually without 第N篇 - compare message_number
        exodus_rows.append(
            {
                "msg_no": mno,
                "in_12490": em is not None,
                "message_title": mt,
                "pian_in_title": pian,
                "message_number": (em or {}).get("message_number"),
                "number_ok": (em or {}).get("message_number") == mno,
                "filename_title": (desk_row or {}).get("filename_title"),
            }
        )

    # 3.5 preface-only
    preface_chunks = [c for c in life_chunks if is_preface_only_chunk(c.get("text") or "")]

    # 3.6 chunk count distribution per message
    chunk_counts = [len(em["chunks"]) for em in msgs.values()]
    tiny_one = []
    for em in msgs.values():
        if len(em["chunks"]) == 1:
            text = em["chunks"][0].get("text") or ""
            if len(text) < 80:
                tiny_one.append(em)

    # 4.1 other indices
    other_idx_stats = probe_other_indices(es)

    count_after = es.count(index=ES_INDEX)["count"]
    snap_after = folder_snapshot(LIFE_ROOT)
    git_status = _git_status()

    # verification numbers
    sum_book_chunks = sum(by_book_chunks.values())
    sum_book_msgs = sum(len(v) for v in by_book_msgs.values())
    # note: same msg could appear once per book_title raw; msgs dict uses canon so may merge 雅歌书+雅歌
    total_msgs_raw = sum(len(v) for v in by_book_msgs.values())
    total_msgs_canon = len(msgs)

    report = render_report(
        es_url=es_url,
        cluster=info.get("cluster_name"),
        version=info.get("version", {}).get("number"),
        mapping=mapping,
        count_before=count_before,
        count_after=count_after,
        life_chunks=life_chunks,
        excluded_books=excluded_books,
        by_book_chunks=by_book_chunks,
        by_book_msgs=by_book_msgs,
        msgs=msgs,
        desk=desk,
        both=both,
        desk_only=desk_only,
        es_only=es_only,
        desk_only_by_book=desk_only_by_book,
        special_checks=special_checks,
        spelling=spelling,
        excerpt_chunks=excerpt_chunks,
        excerptish_samples=excerptish_samples,
        after_files=after_files,
        post_marker_check=post_marker_check,
        title_cats=title_cats,
        title_examples=title_examples,
        exodus_rows=exodus_rows,
        preface_chunks=preface_chunks,
        chunk_counts=chunk_counts,
        tiny_one=tiny_one,
        other_idx_stats=other_idx_stats,
        sum_book_chunks=sum_book_chunks,
        total_msgs_raw=total_msgs_raw,
        total_msgs_canon=total_msgs_canon,
        snap_before=snap_before,
        snap_after=snap_after,
        git_status=git_status,
        log_path=log_path,
        elapsed=time.time() - t0,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    logging.info("report %s chars=%s", report_path, len(report))
    logging.info("done %.1fs", time.time() - t0)
    return 0


def probe_other_indices(es) -> list[dict]:
    from elasticsearch.helpers import scan

    targets = [
        "panai4_outline_feasts",
        "panai4_bible",
        "panai4_map_note",
        "panai4_text_others",
        "panai4_pano_catalog",
    ]
    out = []
    for idx in targets:
        if not es.indices.exists(index=idx):
            out.append({"index": idx, "exists": False})
            continue
        props = es.indices.get_mapping(index=idx)[idx]["mappings"].get("properties") or {}
        field = None
        if "book_title" in props:
            if props["book_title"].get("type") == "keyword":
                field = "book_title"
            elif "keyword" in (props["book_title"].get("fields") or {}):
                field = "book_title.keyword"
        life_books: Counter = Counter()
        msgs = set()
        if field:
            try:
                # scroll wildcard if keyword
                for doc in scan(
                    es,
                    index=idx,
                    query={"query": {"wildcard": {field: "*生命读经*"}}},
                    _source=["book_title", "message_number", "message_key"],
                    size=500,
                ):
                    src = doc.get("_source") or {}
                    bt = (src.get("book_title") or "").strip()
                    if not is_life_study_book(bt):
                        continue
                    life_books[bt] += 1
                    mno = src.get("message_number")
                    if mno is not None:
                        msgs.add((normalize_book(bt), int(mno)))
            except Exception as exc:  # noqa: BLE001
                logging.warning("scan fail %s: %s", idx, exc)
        out.append(
            {
                "index": idx,
                "exists": True,
                "field": field,
                "chunks": sum(life_books.values()),
                "msgs": len(msgs),
                "books": dict(life_books),
            }
        )
    return out


def _esc(s: str) -> str:
    return (s or "").replace("|", "\\|")


def render_report(**kw) -> str:
    lines: list[str] = []
    w = lines.append
    both = kw["both"]
    desk_only = kw["desk_only"]
    es_only = kw["es_only"]
    msgs = kw["msgs"]
    desk = kw["desk"]
    by_book_chunks = kw["by_book_chunks"]
    by_book_msgs = kw["by_book_msgs"]
    spelling = kw["spelling"]

    n_books = len(by_book_chunks)
    need_rename_chunks = sum(i["chunks"] for i in spelling["需改名"])
    need_rename_msgs = sum(i["msgs"] for i in spelling["需改名"])
    underscore_chunks = sum(i["chunks"] for i in spelling["尾部下划线"])
    dirty_chunks = sum(i["chunks"] for i in spelling["脏片段"])

    post_found = sum(1 for p in kw["post_marker_check"] for r in p["results"] if r.get("found"))
    post_miss = sum(1 for p in kw["post_marker_check"] for r in p["results"] if r.get("found") is False)

    w("# panai4_outline_12490 生命读经只读检查报告")
    w("")
    w(f"> ES：`{kw['es_url']}` cluster=`{kw.get('cluster')}` v`{kw.get('version')}`；索引 `{ES_INDEX}`。")
    w(f"> 配对 CSV：`{PAIRING_CSV}`；桌面只读快照用。")
    w(f"> 生成：{datetime.now().isoformat(timespec='seconds')}；日志：`{kw['log_path']}`；耗时 {kw['elapsed']:.1f}s。")
    w("")
    w("## 结论摘要")
    w("")
    w(
        f"1. **覆盖**：12490 生命读经 canon 篇数=**{len(msgs)}**，桌面=1984；both=**{len(both)}**，"
        f"桌面独有=**{len(desk_only)}**，12490独有=**{len(es_only)}**；book_title 取值 **{n_books}** 个"
        f"（含尾部下划线变体）。"
        + ("覆盖完整。" if len(desk_only) == 0 and len(both) == 1984 else f"不完整，缺 {len(desk_only)} 篇。")
    )
    rename_names = ", ".join(i["book_title"] for i in spelling["需改名"]) or "无"
    under_names = ", ".join(i["book_title"] for i in spelling["尾部下划线"]) or "无"
    w(
        f"2. **书名**：需改名（{rename_names}）→ 影响 **{need_rename_msgs} 篇 / {need_rename_chunks} 块**；"
        f"尾部下划线（{under_names}）→ {underscore_chunks} 块；脏片段 {dirty_chunks} 块。"
    )
    w(
        f"3. **摘录混入**：text 含「职事信息摘录」的块=**{len(kw['excerpt_chunks'])}**；"
        f"疑似无序号长论述抽样 {len(kw['excerptish_samples'])} 块见明细。"
    )
    w(
        f"4. **标志后纲目**：桌面复扫 outline-after-excerpt=**{len(kw['after_files'])}** 文件；"
        f"抽 10 文件共查 {post_found + post_miss} 条，出现={post_found}，未出现={post_miss}。"
    )
    w(
        f"5. **篇题/篇号**：title 分类 {dict(kw['title_cats'])}；"
        f"出埃及记 102–131 见 3.4；message_number 字段存在。"
    )
    other_life = [x for x in kw["other_idx_stats"] if x.get("chunks")]
    w(
        f"6. **其他索引**：含生命读经块的索引数=**{len(other_life)}**；明细见 4.1。"
    )
    w(
        f"7. **待修汇总**：书名改写（雅歌书等）；"
        + (f"缺篇 {len(desk_only)}；" if desk_only else "缺篇 0；")
        + f"摘录字样块 {len(kw['excerpt_chunks'])}；"
        + f"前言空壳块 {len(kw['preface_chunks'])}；"
        + f"标志后纲目未进抽样未出现 {post_miss}。"
    )
    w("")

    w("## 书名映射常量表")
    w("")
    w("| 原始 book_title | canon |")
    w("|---|---|")
    for a, b in BOOK_TO_CANON.items():
        w(f"| {a} | {b} |")
    w("")
    w("另：尾部 `_` 在 normalize 时去掉（如 `约翰二书生命读经_` → `约翰二书生命读经`）。")
    w("")

    # 1.1 mapping
    w("## 1. 覆盖")
    w("")
    w("### 1.1 mapping 字段")
    w("")
    w("字段：" + ", ".join(f"`{k}`" for k in sorted(kw["mapping"].keys())))
    w("")
    mno = kw["mapping"].get("message_number", {})
    w(f"- `message_number`：type=`{mno.get('type')}` → **有整数篇号字段，直接用，不解析 chunk_id**。")
    w(f"- `book_title`：type=`{(kw['mapping'].get('book_title') or {}).get('type')}`")
    w(f"- `message_title`：type=`{(kw['mapping'].get('message_title') or {}).get('type')}`")
    w(f"- `message_key`：type=`{(kw['mapping'].get('message_key') or {}).get('type')}`（一篇的稳定标识）")
    w("")

    w("### 1.2 排除的「生命读经」相关文集")
    w("")
    w("排除依据：book_title **不以**「生命读经」结尾，或含「文集」。本系列以「生命读经」结尾且无「文集」。")
    w("")
    w("| book_title | 块数 |")
    w("|---|---:|")
    for bt, n in kw["excluded_books"].most_common():
        w(f"| {_esc(bt)} | {n} |")
    if not kw["excluded_books"]:
        w("| （无） | |")
    w("")

    w("### 1.3 生命读经 book_title 清单")
    w("")
    w(f"总块数={len(kw['life_chunks'])}；按 book_title 块数合计={kw['sum_book_chunks']}；raw 篇数合计={kw['total_msgs_raw']}；canon 去重篇数={kw['total_msgs_canon']}")
    w("")
    w("| book_title | 篇数(message_number去重) | 块数 |")
    w("|---|---:|---:|")
    for bt, n_chunks in sorted(by_book_chunks.items(), key=lambda x: (-x[1], x[0])):
        w(f"| {_esc(bt)} | {len(by_book_msgs.get(bt, []))} | {n_chunks} |")
    w("")

    w("### 1.5 与桌面对照")
    w("")
    w(f"- both=**{len(both)}**")
    w(f"- 桌面独有=**{len(desk_only)}**")
    w(f"- 12490独有=**{len(es_only)}**")
    w(f"- 闭合：both+桌面独有={len(both)+len(desk_only)} vs 1984；both+12490独有={len(both)+len(es_only)} vs {len(msgs)}")
    w("")
    if desk_only:
        w("桌面独有按书：")
        w("")
        w("| book | 缺篇数 |")
        w("|---|---:|")
        for b, n in kw["desk_only_by_book"].most_common():
            w(f"| {b} | {n} |")
        w("")
        w("桌面独有逐条：")
        w("")
        for key in sorted(desk_only):
            row = desk[key]
            w(
                f"- {key[0]} #{key[1]} `{row.get('filename_title')}` / doc=`{row.get('doc_title')}` path=`{row.get('desktop_path')}`"
            )
        w("")
    else:
        w("桌面独有：无。")
        w("")
    if es_only:
        w("12490独有逐条：")
        w("")
        for key in sorted(es_only):
            em = msgs[key]
            w(f"- {key[0]} #{key[1]} mt=`{em.get('message_title')}` raw=`{em.get('book_raw')}` chunks={len(em['chunks'])}")
        w("")
    else:
        w("12490独有：无。")
        w("")

    w("### 1.6 特殊篇")
    w("")
    for sp in kw["special_checks"]:
        w(
            f"- {sp['key']}：in_12490={sp['in_12490']} mt=`{sp.get('message_title')}` "
            f"book_raw=`{sp.get('book_raw')}` chunks={sp.get('n_chunks')} "
            f"desktop_path=`{(sp.get('desktop') or {}).get('desktop_path')}`"
        )
    w("")

    # 2
    w("## 2. 书名写法")
    w("")
    for cls, items in spelling.items():
        w(f"### {cls}（{len(items)} 个取值）")
        w("")
        if not items:
            w("（无）")
            w("")
            continue
        w("| book_title | canon | 篇数 | 块数 |")
        w("|---|---|---:|---:|")
        for it in items:
            w(f"| {_esc(it['book_title'])} | {_esc(it['canon'])} | {it['msgs']} | {it['chunks']} |")
        w("")
    w(
        f"判断：需要改的主要是「雅歌书生命读经」→「雅歌生命读经」"
        f"（{need_rename_msgs} 篇 / {need_rename_chunks} 块）；"
        f"尾部下划线规范化 {underscore_chunks} 块；脏片段 {dirty_chunks} 块。"
    )
    w("")

    # 3
    w("## 3. 内容质量")
    w("")
    w(f"### 3.1 text 含「职事信息摘录」：{len(kw['excerpt_chunks'])} 块")
    w("")
    for c in kw["excerpt_chunks"][:10]:
        w(f"- `{c['book_title']}` #{c.get('message_number')} idx={c.get('chunk_index')} text头=`{(c.get('text') or '')[:60].replace(chr(10),' ')}`")
    w("")
    w("疑似无序号长论述抽样（最多20）：")
    w("")
    for c in kw["excerptish_samples"]:
        body = chunk_body_only(c.get("text") or "")[:80].replace("\n", " ")
        w(f"- `{c['book_title']}` #{c.get('message_number')} len_body≈{len(chunk_body_only(c.get('text') or ''))} `{body}`")
    w("")

    w(f"### 3.2 标志行后纲目是否进 12490（桌面复扫 {len(kw['after_files'])} 文件，抽 10）")
    w("")
    w(f"合计：出现={post_found} 未出现={post_miss}")
    w("")
    w(
        f"说明：复扫得 {len(kw['after_files'])} 文件（probe2 报告为 126；差异可能来自空 LEVEL 段是否计入）。"
        "抽样优先取标志后确有非空 2大点/3中点/4小点 文本的文件。"
    )
    w("")
    for item in kw["post_marker_check"]:
        w(f"#### `{item['rel']}` {item.get('note') or ''}")
        w("")
        if not item["results"]:
            w("- （该文件标志后无非空 LEVEL 文本可抽）")
        for r in item["results"]:
            w(f"- found={r.get('found')} style=`{r.get('style')}` text=`{r.get('text40')}`")
        w("")

    w("### 3.3 message_title vs 桌面 doc_title")
    w("")
    w(f"分类合计={sum(kw['title_cats'].values())}（应等于 both={len(both)}）")
    w("")
    for cat, n in kw["title_cats"].most_common():
        w(f"#### {cat}（{n}）")
        w("")
        for ex in kw["title_examples"].get(cat) or []:
            w(f"- {ex['key']} doc=`{ex['doc']}` mt=`{ex['mt']}`")
        w("")

    w("### 3.4 出埃及记 msg.102–131")
    w("")
    w("| msg_no | in_12490 | message_number一致 | message_title | filename_title |")
    w("|---:|:---:|:---:|---|---|")
    for row in kw["exodus_rows"]:
        w(
            f"| {row['msg_no']} | {row['in_12490']} | {row['number_ok']} | {_esc(row['message_title'][:40])} | {_esc((row.get('filename_title') or '')[:40])} |"
        )
    w("")

    w(f"### 3.5 前言空壳块：{len(kw['preface_chunks'])}")
    w("")
    for c in kw["preface_chunks"][:5]:
        w(f"- `{c['book_title']}` #{c.get('message_number')} idx={c.get('chunk_index')} `{chunk_body_only(c.get('text') or '')}`")
    w("")

    cc = kw["chunk_counts"] or [0]
    w("### 3.6 每篇块数分布")
    w("")
    w(f"- min={min(cc)} median={statistics.median(cc)} max={max(cc)} mean={sum(cc)/len(cc):.2f}")
    w(f"- 块数=1 且 text 很短（<80字）：{len(kw['tiny_one'])}")
    for em in kw["tiny_one"][:8]:
        w(f"- {em['book_canon']} #{em['message_number']} `{em['message_title']}`")
    w("")

    # 4
    w("## 4. 其他索引与待修汇总")
    w("")
    w("### 4.1 其他索引")
    w("")
    w("| 索引 | 生命读经块数 | 篇数 | book_title 取值数 |")
    w("|---|---:|---:|---:|")
    for item in kw["other_idx_stats"]:
        if not item.get("exists"):
            w(f"| {item['index']} | 缺失 | | |")
            continue
        w(
            f"| {item['index']} | {item.get('chunks', 0)} | {item.get('msgs', 0)} | {len(item.get('books') or {})} |"
        )
        for bt, n in sorted((item.get("books") or {}).items(), key=lambda x: -x[1])[:10]:
            w(f"| ↳ | {_esc(bt)} × {n} | | |")
    w("")

    w("### 4.2 待修分类汇总（只报告）")
    w("")
    w("| 类别 | 影响 |")
    w("|---|---|")
    w(f"| 书名「雅歌书生命读经」→「雅歌生命读经」 | {need_rename_msgs} 篇 / {need_rename_chunks} 块 |")
    w(f"| 书名尾部下划线规范化 | {sum(i['msgs'] for i in spelling['尾部下划线'])} 篇 / {underscore_chunks} 块 |")
    w(f"| 脏 book_title（含「，第」） | {sum(i['msgs'] for i in spelling['脏片段'])} 篇 / {dirty_chunks} 块 |")
    w(f"| 桌面有而 12490 无 | {len(desk_only)} 篇 |")
    w(f"| 12490 有而桌面无 | {len(es_only)} 篇 |")
    w(f"| text 含职事信息摘录 | {len(kw['excerpt_chunks'])} 块 |")
    w(f"| 标志后纲目抽样未出现 | {post_miss} 条（10 文件抽样） |")
    w(f"| 篇题用字差异 | {kw['title_cats'].get('篇题用字差异', 0)} 篇 |")
    w(f"| 前言空壳块 | {len(kw['preface_chunks'])} 块 |")
    w("")

    # verify
    w("## 验证步骤结果")
    w("")
    w(f"1. 12490 count 前后：{kw['count_before']} / {kw['count_after']} 一致={kw['count_before']==kw['count_after']}（期望 55841：{kw['count_before']==55841}）")
    w(f"2. book_title 块数之和 {kw['sum_book_chunks']} = life scroll 块数 {len(kw['life_chunks'])} → {kw['sum_book_chunks']==len(kw['life_chunks'])}；raw篇数合计 {kw['total_msgs_raw']}，canon篇数 {kw['total_msgs_canon']}")
    w(f"3. both+桌面独有={len(both)+len(desk_only)} vs 1984 → {len(both)+len(desk_only)==1984}；both+12490独有={len(both)+len(es_only)} vs {len(msgs)} → {len(both)+len(es_only)==len(msgs)}")
    w(f"4. title 分类之和 {sum(kw['title_cats'].values())} = both {len(both)} → {sum(kw['title_cats'].values())==len(both)}")
    w(f"5. 桌面快照 before={kw['snap_before']} after={kw['snap_after']} round1一致={kw['snap_before']==ROUND1_SNAP} 前后一致={kw['snap_before']==kw['snap_after']}")
    w("")
    w("6. git status：")
    w("```")
    w(kw["git_status"])
    w("```")
    w("")
    w("ES 只用只读接口：info / count / indices.exists / get_mapping / search / scroll。")
    w("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读检查 12490 中的生命读经")
    parser.add_argument("--report", default=str(REPORT_DEFAULT))
    parser.add_argument("--log-dir", default=str(LOG_DIR_DEFAULT))
    args = parser.parse_args(argv)
    log_path = setup_logging(Path(args.log_dir))
    load_dotenv(_backend_env())
    return run(Path(args.report), log_path)


if __name__ == "__main__":
    raise SystemExit(main())
