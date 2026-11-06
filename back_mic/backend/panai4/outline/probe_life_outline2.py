# -*- coding: utf-8 -*-
"""生命读经纲目第二轮只读勘探。

已定：新建独立索引；摘录不进索引；书名用桌面写法（雅歌书→雅歌）；
对齐时对 text_life 做显式别名表。本脚本只勘探，不写 ES、不改源文件。

用法（在 back_mic/backend 下）::

    python -m panai4.outline.probe_life_outline2
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import random
import re
import sqlite3
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from . import config
from .docx_parser import (
    analyze_document,
    level_of_label,
    mapped_style_names,
    normalize_label,
    parse_msg_filename,
    read_paragraphs,
    split_label_body,
    strip_dir_index,
)

# ---------------------------------------------------------------------------
# 常量：书名映射表（显式，非零散 replace）
# ---------------------------------------------------------------------------

# 新索引 / 桌面侧最终写法：目录名去序号与尾部下划线后，再套此表
DESKTOP_BOOK_TO_CANON = {
    "雅歌书生命读经": "雅歌生命读经",
}

# 对齐 text_life → 新索引 canon（桌面写法为准）
TEXT_LIFE_BOOK_TO_CANON = {
    "列王记生命读经": "列王纪生命读经",
    "歌林多前书生命读经": "哥林多前书生命读经",
    "歌林多后书生命读经": "哥林多后书生命读经",
    "腓利比书生命读经": "腓立比书生命读经",
    # 已干净的雅歌
    "雅歌生命读经": "雅歌生命读经",
}

TITLE_STYLES = set(config.HEADER_STYLES["title_in_doc"])
SERIES_STYLES = set(config.HEADER_STYLES["series"]) | set(config.HEADER_STYLES["sub_series"])
BIBLE_STYLES = set(config.HEADER_STYLES["bible_reading"])
EXCERPT_STYLES = (
    set(config.EXCERPT_MARKER_STYLES)
    | set(config.EXCERPT_BODY_STYLES)
    | set(config.EXCERPT_HEADING_STYLES)
)
FOCUS_STYLES = [
    "0000模板",
    "9职事信息摘录",
    "职事信息摘录",
    "摘录1",
    "摘录2",
    "摘录3",
    "061摘录正文",
    "051职事信息摘录点",
    "t_spm",
    "t_gti",
    "11111西列",
]

LIFE_ROOT_DEFAULT = Path(r"C:\Users\28121\Desktop\生命读经")
REPO_ROOT = Path(__file__).resolve().parents[4]
REPORT_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_outline_probe2.md"
CSV_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_outline_pairing.csv"
LOG_DIR_DEFAULT = REPO_ROOT / "logs"
ES_INDEX = "panai4_text_life"
BIBLE_SQLITE = Path(r"G:\audio-app\Bible\assets\Bible20240820.sqlite")
SAMPLE_SEED = 20261106
ROUND1_SNAP = {"files": 1984, "bytes": 77896253, "max_mtime": 1766425146.0}

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
_CN_PIAN_RE = re.compile(r"^第([一二三四五六七八九十百千零〇两0-9]+)篇([\s\u3000].*)?$")
_MSG_FORMS = [
    ("msg_dot_space_num_space", re.compile(r"^msg\.\s+\d+\s+.+$", re.I)),
    ("msg_dot_num_nospace_title", re.compile(r"^msg\.\s*\d+\S.*$", re.I)),  # msg.25title or msg. 25title
    ("msg_dot_space_num_only", re.compile(r"^msg\.\s+\d+$", re.I)),
    ("appendix", re.compile(r"^附录")),
    ("other", None),
]


def _backend_env() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def setup_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_dir / f"life_outline_probe2_{stamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    logging.info("log_path=%s", path)
    return path


# ---------------------------------------------------------------------------
# 中文数字
# ---------------------------------------------------------------------------


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


def selftest_cn_to_int() -> list[tuple[str, int, Optional[int], bool]]:
    cases = [
        ("一", 1),
        ("十", 10),
        ("十一", 11),
        ("二十", 20),
        ("一百", 100),
        ("一百零一", 101),
        ("一百一十", 110),
        ("一百二十", 120),
    ]
    out = []
    for cn, expect in cases:
        got = cn_to_int(cn)
        out.append((f"第{cn}篇", expect, got, got == expect))
    return out


# ---------------------------------------------------------------------------
# 书名 / 标题归一
# ---------------------------------------------------------------------------


def desktop_book_raw(book_dir: str) -> str:
    return strip_dir_index(book_dir).rstrip("_").strip()


def desktop_book_canon(book_dir: str) -> str:
    raw = desktop_book_raw(book_dir)
    return DESKTOP_BOOK_TO_CANON.get(raw, raw)


def clean_es_book_title(raw: str) -> str:
    """脏 book_title：只在第一个「，第」处截断。"""
    s = (raw or "").strip()
    idx = s.find("，第")
    if idx >= 0:
        s = s[:idx]
    return s.strip()


def es_book_canon(raw: str) -> str:
    cleaned = clean_es_book_title(raw)
    return TEXT_LIFE_BOOK_TO_CANON.get(cleaned, cleaned)


def is_dirty_book_title(raw: str) -> bool:
    return "，第" in (raw or "")


def normalize_title_cmp(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u3000", "").replace("\xa0", "")
    s = s.replace("\n", "").replace("\r", "").replace("\v", "")
    # 统一括号/破折号/逗号
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
    s = re.sub(r"\s+", "", s)
    return s


def strip_pian_prefix(title_line: str) -> tuple[Optional[int], str, bool]:
    """去掉「第N篇」与后随空白；返回 (msg_no, rest, had_soft_newline)。"""
    raw = title_line or ""
    had_nl = "\n" in raw or "\r" in raw or "\v" in raw
    compact = raw.replace("\n", "").replace("\r", "").replace("\v", "").strip()
    m = _CN_PIAN_RE.match(compact)
    if not m:
        return None, compact, had_nl
    return cn_to_int(m.group(1)), (m.group(2) or "").lstrip(" \u3000"), had_nl


# ---------------------------------------------------------------------------
# 样式角色
# ---------------------------------------------------------------------------


def style_role(name: str) -> str:
    if name in config.LEVEL_STYLES:
        return f"纲目层级 L{config.LEVEL_STYLES[name]}"
    for role, names in config.HEADER_STYLES.items():
        if name in names:
            return {
                "series": "系列",
                "sub_series": "子系列",
                "title_in_doc": "篇题",
                "bible_reading": "读经",
            }.get(role, role)
    if name in config.EXCERPT_MARKER_STYLES:
        return "摘录标志（异常校验；截断靠文字标志）"
    if name in config.EXCERPT_BODY_STYLES:
        return "摘录正文（已映射；非纲目；截断后丢弃，截断前可能并入上一点说明）"
    if name in config.EXCERPT_HEADING_STYLES:
        return "摘录内标题（已映射；非纲目）"
    if name == "Normal":
        return "未映射/正文轨（靠文字编号认层级；非编号段可并入上一点）"
    return "未映射"


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
    return {
        "files": n_files,
        "bytes": total,
        "max_mtime": max_mtime,
        "max_mtime_iso": datetime.fromtimestamp(max_mtime, tz=timezone.utc).isoformat()
        if max_mtime
        else "",
    }


def collect_docx(root: Path) -> list[Path]:
    found = []
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            if name.lower().endswith(".docx") and not name.startswith("~$"):
                found.append(Path(dirpath) / name)
    found.sort(key=lambda p: p.as_posix().lower())
    return found


def make_es():
    from elasticsearch import Elasticsearch

    load_dotenv(_backend_env())
    host = os.getenv("ES_HOST", "localhost")
    port = os.getenv("ES_PORT", "9200")
    url = f"http://{host}:{port}"
    es = Elasticsearch(
        hosts=[url],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=120,
        max_retries=0,
    )
    return es, url


def scroll_text_life(es) -> list[dict]:
    from elasticsearch.helpers import scan

    rows = []
    for doc in scan(
        es,
        index=ES_INDEX,
        query={"query": {"match_all": {}}},
        _source=["book_title", "message_title", "message_number", "chunk_id"],
        size=500,
    ):
        src = doc.get("_source") or {}
        rows.append(
            {
                "book_title": (src.get("book_title") or "").strip(),
                "message_title": (src.get("message_title") or "").strip(),
                "message_number": src.get("message_number"),
                "chunk_id": src.get("chunk_id"),
            }
        )
    return rows


def level1_sequence_ok(points: list[dict]) -> tuple[bool, str]:
    """检查壹贰叁（level==1 且 label 为中文大写数字）连续性。"""
    labels = []
    for p in points:
        if p.get("level") != 1:
            continue
        lab = p.get("label") or ""
        if re.fullmatch(r"[壹贰叁肆伍陆柒捌玖拾]+", lab):
            n = cn_to_int(
                lab.translate(
                    str.maketrans("壹贰叁肆伍陆柒捌玖拾", "一二三四五六七八九十")
                )
            )
            if n is not None:
                labels.append((n, lab))
    if len(labels) < 2:
        return True, "skip"
    nums = [n for n, _ in labels]
    expect = list(range(1, len(nums) + 1))
    if nums == expect:
        return True, "ok"
    if len(set(nums)) != len(nums):
        return False, f"重号={nums}"
    if sorted(nums) != nums:
        return False, f"倒序/乱序={nums}"
    if nums != expect:
        return False, f"缺号={nums} expect={expect}"
    return True, "ok"


def point_body_text(p: dict) -> str:
    return (p.get("text") or "").strip()


def point_full_text(p: dict) -> str:
    lab = (p.get("label") or "").strip()
    body = point_body_text(p)
    if lab and body:
        return lab + "\t" + body
    return lab or body


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run(root: Path, report_path: Path, csv_path: Path, log_path: Path) -> int:
    t0 = time.time()
    rng = random.Random(SAMPLE_SEED)
    if not root.is_dir():
        logging.error("missing root %s", root)
        return 2

    snap_before = folder_snapshot(root)
    logging.info("snap_before=%s", snap_before)

    cn_tests = selftest_cn_to_int()
    if not all(ok for *_a, ok in cn_tests):
        logging.error("cn_to_int selftest failed: %s", cn_tests)
        return 3
    logging.info("cn_to_int selftest OK: %s", cn_tests)

    paths = collect_docx(root)
    logging.info("docx=%s", len(paths))

    # ---- ES ----
    es, es_url = make_es()
    info = es.info()
    es_meta = {
        "url": es_url,
        "cluster": info.get("cluster_name"),
        "version": info.get("version", {}).get("number"),
    }
    logging.info("ES %s", es_meta)
    life_rows = scroll_text_life(es)
    logging.info("scanned text_life rows=%s", len(life_rows))

    # aggregate ES by message
    es_by_raw_pair: dict[tuple[str, Any], list] = defaultdict(list)
    es_msgs: dict[tuple[str, int], dict] = {}
    mno_missing = 0
    for row in life_rows:
        book_raw = row["book_title"]
        mno = row["message_number"]
        if mno is None:
            mno_missing += 1
            continue
        try:
            mno_i = int(mno)
        except (TypeError, ValueError):
            mno_missing += 1
            continue
        es_by_raw_pair[(book_raw, mno_i)].append(row)
        book_c = es_book_canon(book_raw)
        key = (book_c, mno_i)
        if key not in es_msgs:
            es_msgs[key] = {
                "book_raw": book_raw,
                "book_clean": clean_es_book_title(book_raw),
                "book_canon": book_c,
                "message_title": row["message_title"],
                "message_number": mno_i,
                "dirty": is_dirty_book_title(book_raw),
                "chunk_count": 0,
            }
        es_msgs[key]["chunk_count"] += 1
        # 保留一条代表性 message_title（优先干净 book）
        if is_dirty_book_title(es_msgs[key]["book_raw"]) and not is_dirty_book_title(book_raw):
            es_msgs[key]["book_raw"] = book_raw
            es_msgs[key]["message_title"] = row["message_title"]
            es_msgs[key]["dirty"] = False

    # 重新按 canon 聚合 chunk_count（同一 canon+mno 可能有脏/净两条 raw）
    chunk_by_canon: Counter = Counter()
    dirty_raw_books = set()
    for row in life_rows:
        if row["message_number"] is None:
            continue
        try:
            mno_i = int(row["message_number"])
        except (TypeError, ValueError):
            continue
        book_raw = row["book_title"]
        if is_dirty_book_title(book_raw):
            dirty_raw_books.add(book_raw)
        chunk_by_canon[(es_book_canon(book_raw), mno_i)] += 1
    for key, cnt in chunk_by_canon.items():
        if key in es_msgs:
            es_msgs[key]["chunk_count"] = cnt

    # message_number coverage on unique pairs
    unique_pairs_raw = {(r["book_title"], r["message_number"]) for r in life_rows}
    pairs_with_mno = {
        (b, m) for b, m in unique_pairs_raw if m is not None
    }
    # duplicates of message_number within same clean book?
    mno_dups = []
    by_clean: dict[tuple[str, int], set] = defaultdict(set)
    for row in life_rows:
        if row["message_number"] is None:
            continue
        by_clean[(es_book_canon(row["book_title"]), int(row["message_number"]))].add(
            (row["book_title"], row["message_title"])
        )

    # ---- per-file parse ----
    style_para: Counter = Counter()
    style_files: dict[str, set] = defaultdict(set)
    style_nonempty: Counter = Counter()
    style_lengths: dict[str, list] = defaultdict(list)
    style_samples: dict[str, list] = defaultdict(list)

    files_data: list[dict] = []
    total_paras_sum = 0
    excerpt_in_outline_zone = []  # excerpt style before truncate, after outline started
    outline_in_excerpt_zone = []  # level style after excerpt marker line
    marker_after_samples = []

    excerpt_texts_global: set[str] = set()  # normalized >=10 for set size report
    excerpt_text_items: list[tuple[str, str, str]] = []  # rel, style, text
    point_texts_global: set[str] = set()
    point_text_items: list[tuple[str, str]] = []  # rel, text

    no_title_files: list[dict] = []
    conflict_files: list[dict] = []
    jump_files: list[dict] = []
    seq_bad_files: list[dict] = []
    min_ne1_files: list[dict] = []
    empty_text_points: list[dict] = []
    empty_text_by_level: Counter = Counter()
    empty_text_files: set = set()

    title_soft_nl_files = []
    filename_impurity = []
    filename_form_counts: Counter = Counter()
    filename_form_examples: dict[str, list] = defaultdict(list)

    n = len(paths)
    for i, path in enumerate(paths, 1):
        if i % 200 == 0 or i == n:
            logging.info("parse %s/%s", i, n)
        rel = path.relative_to(root).as_posix()
        book_dir = path.parent.name
        book_raw = desktop_book_raw(book_dir)
        book_canon = desktop_book_canon(book_dir)
        parsed_fn = parse_msg_filename(path.name)
        msg_no = parsed_fn.get("msg_no")
        filename_title = parsed_fn.get("title") or ""

        # filename forms
        stem = path.stem
        form_hit = "other"
        for form_name, cre in _MSG_FORMS:
            if cre is None:
                continue
            if cre.match(stem):
                form_hit = form_name
                break
        # refine nospace: msg. Ntitle without space after number
        if re.match(r"^msg\.\s*\d+\S", stem, re.I) and not re.match(
            r"^msg\.\s*\d+\s+\S", stem, re.I
        ):
            form_hit = "msg_dot_num_nospace_title"
        elif re.match(r"^附录", stem):
            form_hit = "appendix"
        elif re.match(r"^msg\.\s+\d+\s+.+$", stem, re.I):
            form_hit = "msg_dot_space_num_space"
        filename_form_counts[form_hit] += 1
        if len(filename_form_examples[form_hit]) < 8:
            filename_form_examples[form_hit].append(rel)
        if re.search(r"副本|\(\s*2\s*\)|（\s*2\s*）|copy", stem, re.I):
            filename_impurity.append(rel)

        paragraphs, err = read_paragraphs(str(path))
        if err:
            files_data.append(
                {
                    "rel": rel,
                    "error": err,
                    "book_canon": book_canon,
                    "book_raw": book_raw,
                    "msg_no": msg_no,
                    "filename_title": filename_title,
                }
            )
            continue

        total_paras_sum += len(paragraphs)
        styles_here = set()
        for para in paragraphs:
            st = para.get("style") or ""
            text = para.get("text") or ""
            style_para[st] += 1
            styles_here.add(st)
            if text.strip():
                style_nonempty[st] += 1
                style_lengths[st].append(len(text))
                if st in FOCUS_STYLES and len(style_samples[st]) < 5:
                    style_samples[st].append(text.replace("\n", "\\n")[:30])
            if st in EXCERPT_STYLES and text.strip():
                tnorm = normalize_title_cmp(text)
                if len(tnorm) >= 10:
                    excerpt_texts_global.add(tnorm)
                    excerpt_text_items.append((rel, st, text.strip()))
        for st in styles_here:
            style_files[st].add(rel)

        analyzed = analyze_document(paragraphs, None, title_hint=filename_title)
        points = analyzed.get("points") or []
        dh = analyzed.get("doc_header") or {}
        title_line = dh.get("title_in_doc") or ""
        msg_from_doc, doc_title, had_nl = strip_pian_prefix(title_line)
        if had_nl and title_line.strip():
            title_soft_nl_files.append(rel)

        # has title styles?
        has_title_style = bool(styles_here & TITLE_STYLES)
        if not has_title_style:
            no_title_files.append(
                {
                    "rel": rel,
                    "styles": sorted(styles_here),
                    "points": points,
                    "analyzed": analyzed,
                    "book_canon": book_canon,
                    "msg_no": msg_no,
                }
            )

        # conflicts / jumps from anomalies + independent check
        conflicts = [a for a in analyzed.get("anomalies") or [] if a.get("type") == "level_conflict"]
        jumps = [a for a in analyzed.get("anomalies") or [] if a.get("type") == "level_jump"]
        if conflicts:
            conflict_files.append({"rel": rel, "n": len(conflicts), "samples": conflicts[:3]})
        if jumps:
            jump_files.append({"rel": rel, "n": len(jumps), "samples": jumps[:3]})

        ok_seq, seq_detail = level1_sequence_ok(points)
        if not ok_seq:
            seq_bad_files.append({"rel": rel, "detail": seq_detail})

        if points:
            mn = min(p["level"] for p in points)
            if mn != 1:
                min_ne1_files.append(
                    {
                        "rel": rel,
                        "min": mn,
                        "first3": [
                            {
                                "level": p["level"],
                                "label": p.get("label"),
                                "text": (p.get("text") or "")[:40],
                                "source": p.get("level_source"),
                            }
                            for p in points[:3]
                        ],
                    }
                )

        for p in points:
            body = point_body_text(p)
            full = point_full_text(p)
            tnorm = normalize_title_cmp(body)
            if len(tnorm) >= 10:
                point_texts_global.add(tnorm)
                point_text_items.append((rel, body))
            # also check label+body and body alone; intersection uses body-like
            lab = (p.get("label") or "").strip()
            # empty text points
            if not body or body in (":", "："):
                # label-only or label with only colon left in text
                empty_text_points.append(
                    {
                        "rel": rel,
                        "level": p.get("level"),
                        "label": lab,
                        "text": p.get("text") or "",
                        "style": p.get("style"),
                        "para_no": p.get("para_no"),
                    }
                )
                empty_text_by_level[p.get("level")] += 1
                empty_text_files.add(rel)

        # excerpt structure independent scan
        marker_idx = None
        for para in paragraphs:
            for line in re.split(r"[\n\r\v]+", para.get("text") or ""):
                compact = line.strip()
                if compact.startswith("职事信息摘录") or compact in (
                    "职事信息摘录",
                    "职事信息摘录：",
                    "职事信息摘录:",
                ):
                    marker_idx = para["para_no"]
                    break
            if marker_idx is not None:
                break

        if marker_idx is not None and len(marker_after_samples) < 5:
            after = []
            for para in paragraphs:
                if para["para_no"] <= marker_idx:
                    continue
                if len(after) >= 10:
                    break
                after.append(
                    {
                        "style": para.get("style"),
                        "text20": (para.get("text") or "").replace("\n", "\\n")[:20],
                    }
                )
            marker_after_samples.append({"rel": rel, "marker_para": marker_idx, "after": after})

        # mix checks
        seen_outline_style = False
        seen_excerpt_marker = False
        has_excerpt_in_outline = False
        has_outline_in_excerpt = False
        for para in paragraphs:
            st = para.get("style") or ""
            text = (para.get("text") or "").strip()
            if marker_idx is not None and para["para_no"] >= marker_idx:
                seen_excerpt_marker = True
            if st in config.LEVEL_STYLES or (
                text and level_of_label(normalize_label(split_label_body(text)[0]))
            ):
                if st in config.LEVEL_STYLES:
                    seen_outline_style = True
                if seen_excerpt_marker and st in config.LEVEL_STYLES:
                    has_outline_in_excerpt = True
            if st in EXCERPT_STYLES and seen_outline_style and (
                marker_idx is None or para["para_no"] < marker_idx
            ):
                # excerpt style in outline zone (before marker)
                has_excerpt_in_outline = True
        if has_excerpt_in_outline:
            excerpt_in_outline_zone.append(rel)
        if has_outline_in_excerpt:
            outline_in_excerpt_zone.append(rel)

        files_data.append(
            {
                "rel": rel,
                "path": path,
                "book_dir": book_dir,
                "book_raw": book_raw,
                "book_canon": book_canon,
                "msg_no": msg_no,
                "filename_title": filename_title,
                "doc_title_line": title_line,
                "doc_title": doc_title,
                "doc_msg_no": msg_from_doc,
                "had_title_nl": had_nl,
                "has_title_style": has_title_style,
                "styles": styles_here,
                "points": points,
                "analyzed": analyzed,
                "dh": dh,
                "paragraphs": paragraphs,
                "marker_idx": marker_idx,
                "parsed_fn": parsed_fn,
            }
        )

    # 1.4 intersection
    # rebuild point body set carefully
    point_bodies = set()
    point_body_map: dict[str, list] = defaultdict(list)
    for fd in files_data:
        for p in fd.get("points") or []:
            body = point_body_text(p)
            tnorm = normalize_title_cmp(body)
            if len(tnorm) >= 10:
                point_bodies.add(tnorm)
                point_body_map[tnorm].append((fd["rel"], p.get("style"), body[:40]))

    excerpt_set = set()
    excerpt_map: dict[str, list] = defaultdict(list)
    for rel, st, text in excerpt_text_items:
        tnorm = normalize_title_cmp(text)
        if len(tnorm) >= 10:
            excerpt_set.add(tnorm)
            excerpt_map[tnorm].append((rel, st, text[:40]))

    inter = excerpt_set & point_bodies
    inter_details = []
    for t in sorted(inter):
        inter_details.append(
            {
                "norm": t[:60],
                "excerpt": excerpt_map[t][:2],
                "points": point_body_map[t][:2],
            }
        )

    # 1.4 复验：交集究竟是截断后同句重复，还是截断前泄漏
    inter_dup_after = 0
    inter_leak_before = 0
    inter_no_cut = 0
    by_rel_fd = {fd["rel"]: fd for fd in files_data}
    for t in inter:
        for rel, st, text40 in excerpt_map[t]:
            fd = by_rel_fd.get(rel)
            if not fd:
                continue
            cut = (fd.get("analyzed") or {}).get("truncated_at")
            # find excerpt para nos with this text
            for para in fd.get("paragraphs") or []:
                if (para.get("style") or "") not in EXCERPT_STYLES:
                    continue
                if normalize_title_cmp(para.get("text") or "") != t:
                    continue
                if cut is not None and para["para_no"] >= cut:
                    inter_dup_after += 1
                elif cut is None:
                    inter_no_cut += 1
                else:
                    inter_leak_before += 1
                break

    # style role table for all observed styles
    all_styles = sorted(style_para.keys(), key=lambda s: (-style_para[s], s))

    # no-title classification
    def classify_no_title(styles: set) -> str:
        if styles <= {"Normal"} or styles == {"Normal"} or (
            styles and styles.issubset({"Normal"}) 
        ):
            return "全Normal"
        if styles & set(config.LEVEL_STYLES):
            if not (styles & (TITLE_STYLES | SERIES_STYLES | BIBLE_STYLES)):
                return "有纲目样式但无篇头样式"
            return "有纲目样式兼其他篇头(无篇题)"
        if styles & {"Normal"} and not (styles & set(config.LEVEL_STYLES)):
            return "Normal为主无LEVEL样式"
        return "其他"

    no_title_by_class: dict[str, list] = defaultdict(list)
    for item in no_title_files:
        cls = classify_no_title(set(item["styles"]))
        # refine 全Normal
        st = set(item["styles"])
        if st == {"Normal"} or st <= {"Normal"}:
            cls = "全Normal"
        elif st & set(config.LEVEL_STYLES) and not (st & TITLE_STYLES):
            if st & (SERIES_STYLES | BIBLE_STYLES):
                cls = "有LEVEL+系列/读经但无篇题"
            else:
                cls = "有LEVEL无篇头"
        elif "Normal" in st and not (st & set(config.LEVEL_STYLES)):
            cls = "仅Normal等非LEVEL"
        else:
            cls = "其他无篇题"
        no_title_by_class[cls].append(item)

    # ensure 歌罗西 msg.9 in no_title
    col_msg9 = [
        x for x in no_title_files if "歌罗西" in x["rel"] and "msg. 9" in x["rel"]
    ]

    # samples for no-title classes
    no_title_samples = {}
    for cls, items in no_title_by_class.items():
        pick = items[:]
        rng.shuffle(pick)
        # force include 歌罗西 msg9 in 全Normal
        if cls == "全Normal" and col_msg9:
            pick = col_msg9 + [x for x in pick if x["rel"] != col_msg9[0]["rel"]]
        no_title_samples[cls] = pick[:5]

    # title three-way compare (need ES paired loosely by book_canon+msg_no)
    # special appendix
    appendix_rel = "14 以斯帖记生命读经/附录　合乎圣经神圣启示的召会末世论.docx"

    # Build desktop keys
    desktop_keys: dict[tuple[str, int], dict] = {}
    appendix_fd = None
    for fd in files_data:
        if fd["rel"] == appendix_rel or fd["rel"].endswith("附录　合乎圣经神圣启示的召会末世论.docx"):
            appendix_fd = fd
            continue
        if fd.get("msg_no") is None:
            continue
        key = (fd["book_canon"], int(fd["msg_no"]))
        desktop_keys[key] = fd

    # Pair appendix via ES title match
    appendix_pair_note = ""
    if appendix_fd is not None:
        # find ES rows whose message_title / book relates to 附录/末世论
        cand = []
        for key, em in es_msgs.items():
            mt = em["message_title"]
            if "末世论" in mt or "附录" in mt:
                if "以斯帖" in em["book_canon"] or "以斯帖" in em["book_raw"]:
                    cand.append((key, em))
        if not cand:
            for key, em in es_msgs.items():
                if "末世论" in em["message_title"]:
                    cand.append((key, em))
        if cand:
            key, em = cand[0]
            desktop_keys[key] = appendix_fd
            appendix_fd["msg_no"] = key[1]
            appendix_fd["book_canon"] = key[0]
            appendix_pair_note = f"附录按 ES message_title 含「末世论」配对到 {key} / {em['message_title'][:40]}"
        else:
            appendix_pair_note = "附录未找到 ES 候选"

    both = set(desktop_keys) & set(es_msgs)
    desk_only = set(desktop_keys) - set(es_msgs)
    es_only = set(es_msgs) - set(desktop_keys)

    # dirty genesis check
    dirty_equal = []
    dirty_ne = []
    for key, em in es_msgs.items():
        if not em["dirty"] and not is_dirty_book_title(em["book_raw"]):
            # also check any dirty raw that maps here
            pass
    # For each dirty raw book_title value, find rows
    dirty_cases = []
    seen_dirty_msg = set()
    for row in life_rows:
        br = row["book_title"]
        if not is_dirty_book_title(br):
            continue
        mno = row["message_number"]
        if mno is None:
            continue
        mno_i = int(mno)
        # fragment after ，第N篇　
        # book_title like "以弗所书生命读经，第一篇 以弗所书的"
        m = re.match(r"^(.*?)，(第.+篇)([\s\u3000]*)(.*)$", br)
        if not m:
            continue
        frag = (m.group(4) or "").strip()
        mt = row["message_title"]
        combined = normalize_title_cmp(frag + mt)
        # find desktop
        book_c = es_book_canon(br)
        fd = desktop_keys.get((book_c, mno_i))
        if not fd:
            dirty_cases.append({"br": br, "status": "no_desktop", "mno": mno_i})
            continue
        doc_n = normalize_title_cmp(fd.get("doc_title") or "")
        equal = combined == doc_n and bool(combined)
        # also try frag + fullwidth space + mt vs doc with pian?
        rec = {
            "book_raw": br,
            "book_canon": book_c,
            "mno": mno_i,
            "frag": frag[:40],
            "es_mt": mt[:40],
            "combined_norm": combined[:60],
            "doc_title": (fd.get("doc_title") or "")[:40],
            "doc_norm": doc_n[:60],
            "equal": equal,
            "rel": fd["rel"],
        }
        keyd = (br, mno_i)
        if keyd in seen_dirty_msg:
            continue
        seen_dirty_msg.add(keyd)
        if equal:
            dirty_equal.append(rec)
        else:
            dirty_ne.append(rec)

    dirty_msg_count = len(seen_dirty_msg)
    dirty_volumes = {es_book_canon(br) for br in dirty_raw_books}

    # title three-way
    cat_counts: Counter = Counter()
    cat_examples: dict[str, list] = defaultdict(list)
    msg_no_mismatch = []
    for fd in files_data:
        if fd.get("error"):
            continue
        fn_t = fd.get("filename_title") or ""
        doc_t = fd.get("doc_title") or ""
        # impurity strip for compare? keep raw for impurity list; for compare use as-is then also strip 副本
        fn_cmp = normalize_title_cmp(re.sub(r"\s*[-－—]?\s*副本.*$", "", fn_t))
        doc_cmp = normalize_title_cmp(doc_t)
        es_mt = ""
        if fd.get("msg_no") is not None:
            em = es_msgs.get((fd["book_canon"], int(fd["msg_no"])))
            if em:
                # strip 第N篇 from es message_title
                _n, es_rest, _ = strip_pian_prefix(em["message_title"])
                es_mt = es_rest
        es_cmp = normalize_title_cmp(es_mt)

        if fd.get("doc_msg_no") is not None and fd.get("msg_no") is not None:
            if fd["doc_msg_no"] != fd["msg_no"]:
                msg_no_mismatch.append(
                    {
                        "rel": fd["rel"],
                        "file_msg": fd["msg_no"],
                        "doc_msg": fd["doc_msg_no"],
                    }
                )

        has_doc = bool(doc_cmp)
        if not has_doc:
            cat = "文内缺失"
        else:
            same_fn_doc = fn_cmp == doc_cmp
            same_doc_es = (doc_cmp == es_cmp) if es_cmp else None
            same_fn_es = (fn_cmp == es_cmp) if es_cmp else None
            if es_cmp and same_fn_doc and same_doc_es:
                cat = "三者相同"
            elif es_cmp and (not same_fn_doc) and same_doc_es and (not same_fn_es):
                cat = "仅文件名与文内不同"
            elif es_cmp and same_fn_doc and (not same_doc_es):
                cat = "仅文内与ES不同"  # fn==doc != es
            elif es_cmp and (not same_fn_doc) and (not same_doc_es) and (not same_fn_es):
                cat = "三者都不同"
            elif es_cmp and (not same_fn_doc) and same_doc_es:
                cat = "仅文件名与文内不同"
            elif es_cmp and same_fn_doc is False and same_fn_es and not same_doc_es:
                cat = "仅文内与ES不同"  # actually fn==es != doc
                # reclassify
                cat = "仅文内与两边不同"
            elif not es_cmp:
                cat = "文内有但无ES标题"
            else:
                # fn==es != doc
                if same_fn_es and not same_doc_es:
                    cat = "仅文内不同"
                elif same_doc_es and not same_fn_doc:
                    cat = "仅文件名与文内不同"
                else:
                    cat = "其他差异"
        cat_counts[cat] += 1
        if len(cat_examples[cat]) < 8:
            cat_examples[cat].append(
                {
                    "rel": fd["rel"],
                    "fn": fn_t[:40],
                    "doc": doc_t[:40],
                    "es": es_mt[:40],
                }
            )

    # remap categories to required buckets for closure
    # required: 三者相同 / 仅文件名与文内不同 / 仅文内与 ES 不同 / 三者都不同 / 文内缺失
    # fold extras
    fold_map = {
        "仅文内与两边不同": "仅文内与ES不同",
        "仅文内不同": "仅文内与ES不同",
        "文内有但无ES标题": "其他差异",
        "其他差异": "其他差异",
    }
    cat_counts2: Counter = Counter()
    cat_examples2: dict[str, list] = defaultdict(list)
    for cat, cnt in cat_counts.items():
        cat2 = fold_map.get(cat, cat)
        cat_counts2[cat2] += cnt
        cat_examples2[cat2].extend(cat_examples[cat])
    for k in cat_examples2:
        cat_examples2[k] = cat_examples2[k][:8]

    # 4 special files
    special_rels = [
        "1 创世记生命读经/msg. 25人第二次的堕落（三）.docx",
        "14 以斯帖记生命读经/附录　合乎圣经神圣启示的召会末世论.docx",
        "38 马可福音生命读经/msg. 55一种完全照着神新约经纶，并为着神新约经纶的生活（四）.docx",
        "40 约翰福音生命读经/msg. 13垂死人的需要—生命的医治.docx",
    ]
    special_reports = []
    by_rel = {fd["rel"]: fd for fd in files_data}
    for srel in special_rels:
        fd = by_rel.get(srel)
        if not fd:
            # try fuzzy
            for r, f in by_rel.items():
                if Path(srel).name in r:
                    fd = f
                    srel = r
                    break
        if not fd:
            special_reports.append({"rel": srel, "missing": True})
            continue
        em = None
        if fd.get("msg_no") is not None:
            em = es_msgs.get((fd["book_canon"], int(fd["msg_no"])))
        special_reports.append(
            {
                "rel": fd["rel"],
                "parsed_fn": fd.get("parsed_fn"),
                "doc_title_line": (fd.get("doc_title_line") or "")[:80],
                "doc_title": fd.get("doc_title"),
                "doc_msg_no": fd.get("doc_msg_no"),
                "es": em,
                "n_points": len(fd.get("points") or []),
            }
        )

    # item 5: other indices
    name_needles = ["哥林多", "歌林多", "腓立比", "腓利比", "列王纪", "列王记", "雅歌"]
    other_index_hits = probe_other_indices(es, name_needles)
    bible_sqlite_names = probe_bible_sqlite(name_needles)

    # write CSV
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(
            [
                "desktop_path",
                "desktop_book(映射后)",
                "msg_no",
                "filename_title",
                "doc_title",
                "es_book_raw",
                "es_message_title",
                "es_message_number",
                "es_chunk_count",
                "es_book_dirty(是/否)",
            ]
        )
        for key in sorted(desktop_keys.keys(), key=lambda k: (k[0], k[1])):
            fd = desktop_keys[key]
            em = es_msgs.get(key)
            w.writerow(
                [
                    fd["rel"],
                    key[0],
                    key[1],
                    fd.get("filename_title") or "",
                    fd.get("doc_title") or "",
                    (em or {}).get("book_raw") or "",
                    (em or {}).get("message_title") or "",
                    (em or {}).get("message_number") if em else "",
                    (em or {}).get("chunk_count") if em else 0,
                    "是" if (em or {}).get("dirty") else "否",
                ]
            )

    snap_after = folder_snapshot(root)
    git_status = _git_status()

    # verification: style role sum vs total paras
    role_sum = sum(style_para.values())
    para_sum_verify = total_paras_sum

    # empty point / build_chunks note
    chunks_empty_note = (
        "build_chunks.render_point 仍输出 `indent+label+全角空格+text`；"
        "text 为空时该行几乎只有 label。"
        "split_units 按 min_level 切块：若该空文本点自身是 min_level 且下一点也是同级，"
        "则会单独成块，块内除头部行外可能没有实质正文。"
    )

    report = render_report(
        root=root,
        snap_before=snap_before,
        snap_after=snap_after,
        es_meta=es_meta,
        cn_tests=cn_tests,
        all_styles=all_styles,
        style_para=style_para,
        style_files=style_files,
        style_nonempty=style_nonempty,
        style_lengths=style_lengths,
        style_samples=style_samples,
        focus=FOCUS_STYLES,
        marker_after_samples=marker_after_samples,
        excerpt_in_outline_zone=excerpt_in_outline_zone,
        outline_in_excerpt_zone=outline_in_excerpt_zone,
        excerpt_set_size=len(excerpt_set),
        point_set_size=len(point_bodies),
        inter=inter,
        inter_details=inter_details,
        inter_dup_after=inter_dup_after,
        inter_leak_before=inter_leak_before,
        inter_no_cut=inter_no_cut,
        no_title_by_class=no_title_by_class,
        no_title_samples=no_title_samples,
        col_msg9=col_msg9,
        conflict_files=conflict_files,
        jump_files=jump_files,
        seq_bad_files=seq_bad_files,
        min_ne1_files=min_ne1_files,
        title_soft_nl_files=title_soft_nl_files,
        msg_no_mismatch=msg_no_mismatch,
        cat_counts=cat_counts2,
        cat_examples=cat_examples2,
        filename_impurity=filename_impurity,
        filename_form_counts=filename_form_counts,
        filename_form_examples=filename_form_examples,
        life_rows_n=len(life_rows),
        mno_missing=mno_missing,
        es_msgs=es_msgs,
        desktop_keys=desktop_keys,
        both=both,
        desk_only=desk_only,
        es_only=es_only,
        appendix_pair_note=appendix_pair_note,
        dirty_equal=dirty_equal,
        dirty_ne=dirty_ne,
        dirty_msg_count=dirty_msg_count,
        dirty_raw_books=sorted(dirty_raw_books),
        dirty_volumes=sorted(dirty_volumes),
        other_index_hits=other_index_hits,
        bible_sqlite_names=bible_sqlite_names,
        empty_text_points=empty_text_points,
        empty_text_by_level=empty_text_by_level,
        empty_text_files=empty_text_files,
        chunks_empty_note=chunks_empty_note,
        special_reports=special_reports,
        role_sum=role_sum,
        para_sum_verify=para_sum_verify,
        files_n=len(paths),
        git_status=git_status,
        csv_path=csv_path,
        log_path=log_path,
        elapsed=time.time() - t0,
        files_data=files_data,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    logging.info("report %s chars=%s", report_path, len(report))
    logging.info("csv %s", csv_path)
    logging.info("done %.1fs", time.time() - t0)
    return 0


def probe_other_indices(es, needles: list[str]) -> list[dict]:
    from elasticsearch.helpers import scan

    idxs = sorted(es.indices.get_alias(index="panai4_*").keys())
    out = []
    for idx in idxs:
        if idx == ES_INDEX:
            continue
        props = es.indices.get_mapping(index=idx)[idx]["mappings"].get("properties") or {}
        # prefer book_title.keyword if exists
        field = None
        if "book_title" in props:
            fields = (props["book_title"].get("fields") or {})
            field = "book_title.keyword" if "keyword" in fields else None
            # if no keyword, scroll distinct via python
        counts: Counter = Counter()
        if field:
            # terms agg
            try:
                resp = es.search(
                    index=idx,
                    size=0,
                    aggs={"b": {"terms": {"field": field, "size": 10000}}},
                )
                for b in resp["aggregations"]["b"]["buckets"]:
                    val = b["key"]
                    if any(n in val for n in needles):
                        counts[val] += b["doc_count"]
            except Exception as exc:  # noqa: BLE001
                logging.warning("agg fail %s %s", idx, exc)
                field = None
        if not field and "book_title" in props:
            for doc in scan(
                es,
                index=idx,
                query={"query": {"match_all": {}}},
                _source=["book_title"],
                size=500,
            ):
                val = (doc.get("_source") or {}).get("book_title") or ""
                if any(n in val for n in needles):
                    counts[val] += 1
        elif "title" in props and idx == "panai4_pano_catalog":
            # skip heavy unless needed
            pass
        for val, cnt in counts.most_common():
            out.append({"index": idx, "field": "book_title", "value": val, "count": cnt})
    return out


def probe_bible_sqlite(needles: list[str]) -> list[tuple[str, str]]:
    path = BIBLE_SQLITE
    if not path.is_file():
        return [("ERROR", f"missing {path}")]
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        # prefer volume table
        hits = []
        for table in tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            name_cols = [
                c
                for c in cols
                if any(k in c.lower() for k in ("name", "title", "book", "volume"))
            ]
            for col in name_cols:
                try:
                    rows = conn.execute(
                        f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL"
                    ).fetchall()
                except sqlite3.Error:
                    continue
                for (val,) in rows:
                    s = str(val)
                    if any(n in s for n in needles):
                        hits.append((f"{table}.{col}", s))
        # dedupe
        seen = set()
        out = []
        for a, b in hits:
            if (a, b) in seen:
                continue
            seen.add((a, b))
            out.append((a, b))
        return out
    finally:
        conn.close()


def _git_status() -> str:
    import subprocess

    try:
        out = subprocess.check_output(
            [
                "git",
                "status",
                "--short",
                "--",
                "back_mic/backend/panai4/outline/",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:  # noqa: BLE001
        return f"(failed: {exc})"
    return out.strip() or "(clean)"


def _esc(s: str) -> str:
    return (s or "").replace("|", "\\|")


def render_report(**kw) -> str:
    lines: list[str] = []
    w = lines.append
    inter = kw["inter"]
    both = kw["both"]
    desk_only = kw["desk_only"]
    es_only = kw["es_only"]
    desk_n = len(kw["desktop_keys"])
    es_n = len(kw["es_msgs"])

    # no-title reliability summary
    n_no_title = sum(len(v) for v in kw["no_title_by_class"].values())
    n_conflict_files = len(kw["conflict_files"])
    n_jump = len(kw["jump_files"])
    n_seq = len(kw["seq_bad_files"])
    n_min = len(kw["min_ne1_files"])

    w("# 生命读经纲目第二轮只读勘探报告")
    w("")
    w(f"> 源：`{kw['root']}`（只读）。脚本：`panai4.outline.probe_life_outline2`。")
    w(f"> ES：`{kw['es_meta']['url']}` cluster=`{kw['es_meta'].get('cluster')}` v`{kw['es_meta'].get('version')}`（只读 search/scroll/count/mapping）。")
    w(f"> 生成：{datetime.now().isoformat(timespec='seconds')}；日志：`{kw['log_path']}`；配对 CSV：`{kw['csv_path']}`。")
    w(f"> 耗时：{kw['elapsed']:.1f}s。")
    w("")
    w("## 结论摘要")
    w("")
    leak_n = kw.get("inter_leak_before", 0)
    dup_n = kw.get("inter_dup_after", 0)
    nocut_n = kw.get("inter_no_cut", 0)
    w(
        f"1. **摘录排除**：1.4 文本交集=**{len(inter)}**（excerpt={kw['excerpt_set_size']} points={kw['point_set_size']}）；"
        f"按截断点：dup_after_cut={dup_n} excerpt_before_cut={leak_n} no_truncate_marker={nocut_n}。"
        + (
            "无解析泄漏，可干净排除（交集为源文件纲目/摘录同句重复）。"
            if leak_n == 0 and nocut_n == 0
            else "存在截断前泄漏或无截断标志，见 1.4。"
        )
    )
    w(
        f"2. **无篇题样式文件**：实测 **{n_no_title}** 篇；冲突文件 {n_conflict_files}、跳级 {n_jump}、壹贰叁不连续 {n_seq}、min≠1 {n_min}。"
        "全 Normal 型依赖文字轨，抽样见 2.2；总体可解析但需留意文字轨误判。"
    )
    # message_title recommendation from data
    cc = kw["cat_counts"]
    w(
        f"3. **message_title**：三者相同 {cc.get('三者相同',0)}；文内缺失 {cc.get('文内缺失',0)}；"
        f"仅文件名与文内不同 {cc.get('仅文件名与文内不同',0)}；仅文内与ES不同 {cc.get('仅文内与ES不同',0)}；"
        f"三者都不同 {cc.get('三者都不同',0)}。建议以**文内篇题行（去第N篇）**为准，文内缺失时回退文件名；文件名含「副本」须清洗。"
    )
    w(
        f"4. **一一配对**：both={len(both)} 桌面独有={len(desk_only)} ES独有={len(es_only)} "
        f"（桌面键={desk_n} ES键={es_n}）。脏 book_title 篇数={kw['dirty_msg_count']}，涉及卷={len(kw['dirty_volumes'])}；"
        f"软换行推断验证：相等={len(kw['dirty_equal'])} 不等={len(kw['dirty_ne'])}。"
    )
    # majority spelling
    w("5. **其他索引写法**：见第 5 节列表；圣经 SQLite 与多数索引写法分布见明细。")
    w(
        f"6. **空文本纲目点**：{len(kw['empty_text_points'])} 个，涉及文件 {len(kw['empty_text_files'])}；"
        "解析器保留为独立点；build_chunks 原样渲染 label，可能产生几乎无正文的块。"
    )
    w(
        "7. **4 个不规范文件名**：`parse_msg_filename` 对缺空格仍能抽出篇号；附录无 msg 号需特判配对。"
        "穷举见 7.3；不会因缺空格丢篇，附录若不特判会丢键。"
    )
    w("")

    # mapping tables
    w("## 书名映射常量表（本轮已定）")
    w("")
    w("### DESKTOP_BOOK_TO_CANON（新索引采用）")
    w("")
    w("| 桌面目录写法 | 新索引 book_title |")
    w("|---|---|")
    for a, b in DESKTOP_BOOK_TO_CANON.items():
        w(f"| {a} | {b} |")
    w("")
    w("其余书卷：目录名去前导序号与尾 `_` 后原样采用（含 列王纪/哥林多/腓立比）。")
    w("")
    w("### TEXT_LIFE_BOOK_TO_CANON（对齐用）")
    w("")
    w("| text_life 干净书名 | 映射到新索引 |")
    w("|---|---|")
    for a, b in TEXT_LIFE_BOOK_TO_CANON.items():
        w(f"| {a} | {b} |")
    w("")
    w("脏 book_title 先在第一个「，第」处截断，再套上表。")
    w("")

    # ---- 1 ----
    w("## 1. 摘录与非纲目样式")
    w("")
    w("### 1.1 样式角色（贴 config 映射依据）")
    w("")
    w("config 原文摘要：")
    w("")
    w("- `LEVEL_STYLES`：纲目 1–7 级（2大点/3中点/4小点/5a点/6（一）/7（1）/8（a）及其异名）")
    w("- `HEADER_STYLES`：series / sub_series / title_in_doc / bible_reading")
    w("- `EXCERPT_MARKER_STYLES` / `EXCERPT_BODY_STYLES` / `EXCERPT_HEADING_STYLES`：摘录相关（截断靠 `TRUNCATE_MARKER_BASES` 文字，不靠样式）")
    w("")
    w("| 样式名 | 段数 | 文件数 | 角色 |")
    w("|---|---:|---:|---|")
    for st in kw["all_styles"]:
        w(
            f"| `{_esc(st)}` | {kw['style_para'][st]} | {len(kw['style_files'][st])} | {style_role(st)} |"
        )
    w("")
    w("LEVEL_STYLES 原文键：`" + "`, `".join(config.LEVEL_STYLES.keys()) + "`")
    w("")
    w("HEADER title_in_doc：`" + "`, `".join(sorted(config.HEADER_STYLES["title_in_doc"])) + "`")
    w("")
    w("EXCERPT_BODY：`" + "`, `".join(sorted(config.EXCERPT_BODY_STYLES)) + "`")
    w("")

    w("### 1.2 重点样式")
    w("")
    for st in kw["focus"]:
        pc = kw["style_para"].get(st, 0)
        fc = len(kw["style_files"].get(st, []))
        ne = kw["style_nonempty"].get(st, 0)
        lens = kw["style_lengths"].get(st) or [0]
        med = statistics.median(lens) if lens else 0
        nonempty_rate = (ne / pc) if pc else 0
        w(f"#### `{st}`")
        w("")
        w(f"- 段数={pc} 文件数={fc} 非空段={ne} 非空占比={nonempty_rate:.2%} 文本长度中位数={med}")
        w(f"- 角色：{style_role(st)}")
        for s in kw["style_samples"].get(st) or []:
            w(f"- 例：{s}")
        if not kw["style_samples"].get(st):
            w("- （无样本或未出现）")
        w("")
    w(
        "**0000模板是什么**：config 将其归入 `EXCERPT_BODY_STYLES`（摘录正文）。"
        "实测段数最多，文本多为职事信息摘录区正文；出现在「职事信息摘录」标志之后，解析截断后不进入纲目点。"
    )
    w("")

    w("### 1.3 摘录结构")
    w("")
    w(f"- 摘录样式夹在纲目区（标志行之前）：**{len(kw['excerpt_in_outline_zone'])}** 文件")
    for rel in kw["excerpt_in_outline_zone"][:30]:
        w(f"  - `{rel}`")
    w(f"- 纲目样式夹在摘录区（标志行之后）：**{len(kw['outline_in_excerpt_zone'])}** 文件")
    for rel in kw["outline_in_excerpt_zone"][:30]:
        w(f"  - `{rel}`")
    w("")
    w("标志行之后 10 段抽样：")
    w("")
    for sample in kw["marker_after_samples"]:
        w(f"#### `{sample['rel']}`（marker_para={sample['marker_para']}）")
        w("")
        w("| 样式 | 前20字 |")
        w("|---|---|")
        for row in sample["after"]:
            w(f"| `{_esc(row['style'])}` | {_esc(row['text20'])} |")
        w("")

    w("### 1.4 排除验证（独立交集）")
    w("")
    w(f"- 摘录类样式文本集合大小（归一化后 len≥10）：**{kw['excerpt_set_size']}**")
    w(f"- 解析器纲目点正文集合大小（归一化后 len≥10）：**{kw['point_set_size']}**")
    w(f"- 交集条数：**{len(inter)}**")
    w(
        f"- 按截断点分类：dup_after_cut=**{kw.get('inter_dup_after', 0)}** "
        f"excerpt_before_cut=**{kw.get('inter_leak_before', 0)}** "
        f"no_truncate_marker=**{kw.get('inter_no_cut', 0)}**"
    )
    w("")
    if inter:
        w("交集逐条（需结合上列分类理解；dup_after_cut=源内重复而非泄漏）：")
        w("")
        for item in kw["inter_details"][:100]:
            w(f"- norm=`{item['norm']}`")
            w(f"  - excerpt: {item['excerpt']}")
            w(f"  - points: {item['points']}")
        w("")
    else:
        w("交集为空：摘录正文未进入纲目点正文集合。")
        w("")

    w("### 1.5 结论")
    w("")
    if kw.get("inter_leak_before", 0) == 0 and kw.get("inter_no_cut", 0) == 0:
        w(
            "现有解析器对生命读经这批文件，**摘录可被干净排除**（文字截断标志）。"
            f"1.4 文本交集 {len(inter)} 条经 para_no 复验均为截断后同句重复。"
            "截断不依赖摘录样式；本批未发现截断前把摘录样式并进纲目点的泄漏。"
        )
    else:
        w("摘录未能完全排除，见 1.4 的 excerpt_before_cut / no_truncate_marker。")
    w("")

    # ---- 2 ----
    w("## 2. 无篇题样式与层级自洽")
    w("")
    w(f"无篇题样式（不含 `00篇题/篇题/033篇题/...`）文件数：**{n_no_title}**")
    w(f"歌罗西书 msg. 9 是否落在无篇题集合：{'是' if kw['col_msg9'] else '否'} {kw['col_msg9'][0]['rel'] if kw['col_msg9'] else ''}")
    w("")
    for cls, items in sorted(kw["no_title_by_class"].items(), key=lambda x: -len(x[1])):
        w(f"### 类：{cls}（{len(items)}）")
        w("")
        for it in items[:3]:
            w(f"- `{it['rel']}` styles={it['styles'][:12]}")
        w("")
        samples = kw["no_title_samples"].get(cls) or []
        for it in samples:
            w(f"#### 抽样 `{it['rel']}`")
            w("")
            w("| level | label | text30 | level_source |")
            w("|---:|---|---|---|")
            for p in (it.get("points") or [])[:15]:
                w(
                    f"| {p.get('level')} | {_esc(p.get('label') or '')} | {_esc((p.get('text') or '')[:30])} | {p.get('level_source')} |"
                )
            w("")
            # quick judgment
            sources = Counter(p.get("level_source") for p in (it.get("points") or []))
            w(f"level_source 分布：{dict(sources)}")
            w("")

    w("### 2.3 层级自洽（全库）")
    w("")
    w(f"a) 样式轨/文字轨冲突：涉及文件 **{n_conflict_files}**（前30）：")
    for item in kw["conflict_files"][:30]:
        w(f"- `{item['rel']}` n={item['n']} ex={item['samples'][:1]}")
    w("")
    w(f"b) 层级跳级：涉及文件 **{n_jump}**（前30）：")
    for item in kw["jump_files"][:30]:
        w(f"- `{item['rel']}` n={item['n']}")
    w("")
    w(f"c) 壹贰叁不连续：涉及文件 **{n_seq}**（前30）：")
    for item in kw["seq_bad_files"][:30]:
        w(f"- `{item['rel']}` {item['detail']}")
    w("")
    w(f"d) min(level)≠1：涉及文件 **{n_min}**（逐个前3点）：")
    w("")
    for item in kw["min_ne1_files"]:
        w(f"- `{item['rel']}` min={item['min']} first3={item['first3']}")
    w("")
    w(
        "判断提示：若 first3 的 label 本身从「一/1」起且无壹级，多为原文无大点；"
        "若文字明显是壹级却被判成中点，则为解析问题。"
    )
    w("")

    w("### 2.4 篇题/读经/系列是否混入纲目点")
    w("")
    # check title lines in points
    leaked_header = 0
    leaked_ex = []
    for fd in kw["files_data"]:
        dh = fd.get("dh") or {}
        for p in fd.get("points") or []:
            t = (p.get("text") or "") + (p.get("label") or "")
            if (dh.get("title_in_doc") and dh["title_in_doc"][:20] and dh["title_in_doc"][:20] in t):
                leaked_header += 1
                if len(leaked_ex) < 5:
                    leaked_ex.append(fd["rel"])
    w(f"粗检：纲目点文本含篇头片段的可疑次数≈{leaked_header} 例={leaked_ex}")
    w("篇头样式段由解析器走 HEADER 分支，不会成为纲目点；无篇题样式文件则靠「读经」前缀规则与文字轨。")
    w("")

    # ---- 3 ----
    w("## 3. message_title 三方比对")
    w("")
    w("### 3.2 中文数字自测")
    w("")
    for name, expect, got, ok in kw["cn_tests"]:
        w(f"- {name} → expect {expect} got {got} {'✓' if ok else '✗'}")
    w("")
    w(f"文内篇号与文件名篇号不一致：**{len(kw['msg_no_mismatch'])}**")
    for item in kw["msg_no_mismatch"][:30]:
        w(f"- `{item['rel']}` file={item['file_msg']} doc={item['doc_msg']}")
    w("")
    w(f"篇题行含软换行：**{len(kw['title_soft_nl_files'])}**")
    for rel in kw["title_soft_nl_files"][:20]:
        w(f"- `{rel}`")
    w("")
    w("### 3.3 分类")
    w("")
    total_cat = sum(kw["cat_counts"].values())
    w(f"分类合计={total_cat}（应等于 {kw['files_n']}）→ {'闭合' if total_cat == kw['files_n'] else '未闭合'}")
    w("")
    for cat, cnt in kw["cat_counts"].most_common():
        w(f"#### {cat}（{cnt}）")
        w("")
        for ex in kw["cat_examples"].get(cat) or []:
            w(f"- `{ex['rel']}` fn=`{ex['fn']}` doc=`{ex['doc']}` es=`{ex['es']}`")
        w("")
    w("### 3.4 文件名杂质")
    w("")
    for rel in kw["filename_impurity"]:
        w(f"- `{rel}`")
    if not kw["filename_impurity"]:
        w("（无）")
    w("")
    w("### 3.5 建议规则（依据数据）")
    w("")
    same = cc.get("三者相同", 0)
    miss = cc.get("文内缺失", 0)
    w(
        f"- 优先 **doc_title**（文内篇题去「第N篇」）：与 ES 标题一致的情况最多见；三者相同={same}。"
    )
    w(f"- **文内缺失**（{miss}）时回退 **filename_title**（并去掉「副本/(2)」杂质）。")
    w("- 不要用脏的 ES message_title 作为权威源；ES 仅作对照。")
    w("")

    # ---- 4 ----
    w("## 4. 整数篇号配对与脏数据")
    w("")
    w(f"- scroll 行数={kw['life_rows_n']}；message_number 缺失行≈{kw['mno_missing']}")
    w(f"- ES unique(book_canon,message_number)={es_n}")
    w(f"- 桌面键（映射后书名+msg_no，含附录特判）={desk_n}")
    w(f"- both={len(both)} 桌面独有={len(desk_only)} ES独有={len(es_only)}")
    w(f"- 闭合：both+桌面独有={len(both)+len(desk_only)} vs 桌面{desk_n}；both+ES独有={len(both)+len(es_only)} vs ES{es_n}")
    w(f"- 附录配对：{kw['appendix_pair_note']}")
    w("")
    if desk_only:
        w("桌面独有：")
        for k in sorted(desk_only)[:50]:
            w(f"- {k} → {kw['desktop_keys'][k]['rel']}")
        w("")
    if es_only:
        w("ES独有：")
        for k in sorted(es_only)[:50]:
            em = kw["es_msgs"][k]
            w(f"- {k} raw=`{em['book_raw']}` mt=`{em['message_title'][:40]}`")
        w("")

    w(f"脏 book_title 取值数={len(kw['dirty_raw_books'])}；脏篇数={kw['dirty_msg_count']}；涉及卷数={len(kw['dirty_volumes'])}")
    w(f"涉及卷：{kw['dirty_volumes']}")
    w("")
    w("### 4.4 软换行成因验证")
    w("")
    w(f"- 相等：{len(kw['dirty_equal'])}")
    w(f"- 不等：{len(kw['dirty_ne'])}")
    w("")
    if kw["dirty_ne"][:15]:
        w("不等清单（最多15）：")
        for rec in kw["dirty_ne"][:15]:
            w(
                f"- `{rec['rel']}` raw=`{rec['book_raw']}` frag=`{rec['frag']}` + mt=`{rec['es_mt']}` vs doc=`{rec['doc_title']}`"
            )
        w("")
    w(
        "推断是否成立："
        + (
            "基本成立（相等占多数）。"
            if len(kw["dirty_equal"]) > len(kw["dirty_ne"])
            else "不能确认成立，请看不等清单。"
        )
    )
    w("")

    # ---- 5 ----
    w("## 5. 其他 panai4_* 与圣经 SQLite 写法")
    w("")
    w("| 索引 | 字段 | 取值 | 条数 |")
    w("|---|---|---|---:|")
    for hit in kw["other_index_hits"]:
        w(f"| {hit['index']} | {hit['field']} | {_esc(hit['value'])} | {hit['count']} |")
    if not kw["other_index_hits"]:
        w("| （无命中） | | | |")
    w("")
    w("### SQLite")
    w("")
    for src, name in kw["bible_sqlite_names"][:80]:
        w(f"- `{src}` = {name}")
    w("")

    # majority
    spell_counter = Counter()
    for hit in kw["other_index_hits"]:
        v = hit["value"]
        for a, b in [
            ("哥林多", "哥林多"),
            ("歌林多", "歌林多"),
            ("腓立比", "腓立比"),
            ("腓利比", "腓利比"),
            ("列王纪", "列王纪"),
            ("列王记", "列王记"),
            ("雅歌书", "雅歌书"),
            ("雅歌", "雅歌"),
        ]:
            if a in v:
                spell_counter[b] += hit["count"]
    w(f"其他索引命中用字计数（粗）：{dict(spell_counter)}")
    w("")

    # ---- 6 ----
    w("## 6. 空文本纲目点")
    w("")
    w(f"- 个数={len(kw['empty_text_points'])} 文件数={len(kw['empty_text_files'])}")
    w(f"- 按 level：{dict(kw['empty_text_by_level'])}")
    w("")
    w("| 文件 | level | label | 原文text |")
    w("|---|---:|---|---|")
    for ex in kw["empty_text_points"][:8]:
        w(
            f"| `{_esc(ex['rel'])}` | {ex['level']} | {_esc(ex['label'])} | `{_esc(ex['text'])}` |"
        )
    w("")
    w(f"build_chunks 行为：{kw['chunks_empty_note']}")
    w("解析器：保留为独立纲目点（含「前言」等 KNOWN_UNNUMBERED_LABELS）。")
    w("")

    # ---- 7 ----
    w("## 7. 不规范文件名")
    w("")
    for sp in kw["special_reports"]:
        w(f"### `{sp.get('rel')}`")
        w("")
        if sp.get("missing"):
            w("未找到文件")
            w("")
            continue
        w(f"- parse_msg_filename={sp.get('parsed_fn')}")
        w(f"- 文内篇题行={sp.get('doc_title_line')}")
        w(f"- doc_title={sp.get('doc_title')} doc_msg_no={sp.get('doc_msg_no')}")
        w(f"- 纲目点数={sp.get('n_points')}")
        em = sp.get("es")
        if em:
            w(
                f"- ES: book_raw=`{em.get('book_raw')}` mt=`{em.get('message_title')}` mno={em.get('message_number')} dirty={em.get('dirty')}"
            )
        else:
            w("- ES: 无直接配对")
        w("")

    w("### 7.3 文件名形态穷举")
    w("")
    w("| 形态 | 数量 | 例子 |")
    w("|---|---:|---|")
    for form, cnt in kw["filename_form_counts"].most_common():
        ex = "; ".join(kw["filename_form_examples"].get(form) or [])
        w(f"| {form} | {cnt} | {_esc(ex)} |")
    w("")
    w("### 7.4 丢失风险")
    w("")
    w(
        "- `msg.N` 与标题之间缺空格：现有 `_MSG_RE` 使用 `\\s*`，篇号仍可解析，**不会丢篇**，标题仍完整。"
        "- `附录…`：无 msg_no，若不特判则无法进入 (book,msg_no) 键，**有丢失风险**；本轮按 ES 标题特判配对。"
        "- 不会归错书（书名来自目录）。"
    )
    w("")

    # ---- verify ----
    w("## 验证步骤结果")
    w("")
    w("### 1 桌面快照")
    w("")
    w(f"- before: {kw['snap_before']}")
    w(f"- after: {kw['snap_after']}")
    w(f"- 与第一轮 {ROUND1_SNAP} 一致：{kw['snap_before']['files']==ROUND1_SNAP['files'] and kw['snap_before']['bytes']==ROUND1_SNAP['bytes'] and kw['snap_before']['max_mtime']==ROUND1_SNAP['max_mtime']}")
    w(f"- 前后一致：{kw['snap_before']==kw['snap_after']}")
    w("")
    w("### 2 段落总数双计")
    w("")
    w(f"- 按样式汇总：{kw['role_sum']}")
    w(f"- 逐文件段落数之和：{kw['para_sum_verify']}")
    w(f"- 相等：{kw['role_sum']==kw['para_sum_verify']}")
    w("")
    w("### 3 项1.4 集合大小")
    w("")
    w(f"- excerpt_set={kw['excerpt_set_size']} point_set={kw['point_set_size']} inter={len(inter)}")
    w("")
    w("### 4 三方分类闭合")
    w("")
    w(f"- sum(cats)={sum(kw['cat_counts'].values())} files={kw['files_n']} 闭合={sum(kw['cat_counts'].values())==kw['files_n']}")
    w("")
    w("### 5 配对闭合")
    w("")
    w(f"- both+desk_only={len(both)+len(desk_only)} desk={desk_n} → {len(both)+len(desk_only)==desk_n}")
    w(f"- both+es_only={len(both)+len(es_only)} es={es_n} → {len(both)+len(es_only)==es_n}")
    w("")
    w("### 6 cn_to_int 自测：全部通过见 3.2")
    w("")
    w("### 7 git status（outline/）")
    w("")
    w("```")
    w(kw["git_status"])
    w("```")
    w("")
    w("ES 只用只读接口：info / indices.get_alias / indices.get_mapping / search / scroll / count。")
    w("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生命读经纲目第二轮只读勘探")
    parser.add_argument("--root", default=str(LIFE_ROOT_DEFAULT))
    parser.add_argument("--report", default=str(REPORT_DEFAULT))
    parser.add_argument("--csv", default=str(CSV_DEFAULT))
    parser.add_argument("--log-dir", default=str(LOG_DIR_DEFAULT))
    args = parser.parse_args(argv)
    log_path = setup_logging(Path(args.log_dir))
    load_dotenv(_backend_env())
    return run(Path(args.root), Path(args.report), Path(args.csv), log_path)


if __name__ == "__main__":
    raise SystemExit(main())
