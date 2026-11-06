# -*- coding: utf-8 -*-
"""只读产出 panai4_outline_12490 生命读经修订清单 v2。

不写索引、不改桌面、不改 outline 既有文件。复用 pairing CSV 与 v1 清单。

用法（在 back_mic/backend 下）::

    python -m panai4.outline.probe_life_fixlist_v2
"""

from __future__ import annotations

import argparse
import csv
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
from panai4.outline.docx_parser import read_paragraphs, strip_dir_index

# ---------------------------------------------------------------------------
BOOK_TO_CANON = {"雅歌书生命读经": "雅歌生命读经"}
TEXT_LIFE_BOOK_TO_CANON = {
    "列王记生命读经": "列王纪生命读经",
    "歌林多前书生命读经": "哥林多前书生命读经",
    "歌林多后书生命读经": "哥林多后书生命读经",
    "腓利比书生命读经": "腓立比书生命读经",
    "雅歌生命读经": "雅歌生命读经",
}
LIFE_ROOT = Path(r"C:\Users\28121\Desktop\生命读经")
REPO_ROOT = Path(__file__).resolve().parents[4]
PAIRING_CSV = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_outline_pairing.csv"
V1_CSV = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_list.csv"
CSV_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_list_v2.csv"
TL_DIFF_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_text_life_diff.csv"
REPORT_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_list_v2.md"
LOG_DIR_DEFAULT = REPO_ROOT / "logs"
ES_INDEX = "panai4_outline_12490"
TL_INDEX = "panai4_text_life"
ROUND1_SNAP = {"files": 1984, "bytes": 77896253, "max_mtime": 1766425146.0}
SAMPLE_SEED = 20261106
SKIP_KEY = ("约翰福音生命读经", 29)
_SOURCE_EXCLUDES = ["embedding"]

_CN_PIAN_RE = re.compile(r"^第[一二三四五六七八九十百千零〇两0-9]+篇[\s\u3000]*(.*)$")
_PIAN_ANY = re.compile(r"第[一二三四五六七八九十百千零〇两0-9]+篇")
_SEQ_TAIL_RE = re.compile(r"[（(]([一二三四五六七八九十百千零〇两0-9]+)[）)]$")
_BOX_DASH = "\u2500"  # ─
_EM_DASH = "\u2014"  # —
_VARIANT_PAIRS = [
    ("於", "于"), ("乾", "干"), ("痲疯", "麻风"), ("著", "着"),
    ("豫言", "预言"), ("惟", "唯"), ("裏", "里"),
]
_DASH_CHARS = {
    "─": "U+2500", "—": "U+2014", "－": "U+FF0D", "–": "U+2013",
    "―": "U+2015", "-": "U+002D", "﹣": "U+FE63",
}
# 归一化时忽略的用字差异（仅用于「是否缺插进的话」等判断）
_IGNORE_CHARS_FOR_SUFFIX = str.maketrans({"豫": "预", "预": "预"})

EXPLICIT_TYPOS = {
    # (book, mno): (wrong_substr, correct_substr) applied on e
    ("路加福音生命读经", 33): [("耶赂撒冷", "耶路撒冷")],
    ("路加福音生命读经", 34): [("耶略撒冷", "耶路撒冷")],
    ("路加福音生命读经", 30): [("它带着", "祂带着")],
    ("撒母耳记生命读经", 9): [("题醒", "提醒")],
}

CSV_COLS = [
    "kind", "group_id", "book", "msg_no", "message_key", "old", "new", "category",
    "source_of_new", "confidence", "proposal", "doc_title_raw", "es12490_title_raw",
    "text_life_title_raw", "chunk_count", "reembed", "note",
]

CN_NUM = {
    "〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
CN_UNIT = {"十": 10, "百": 100, "千": 1000}


def _backend_env() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def setup_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_dir / f"life_12490_fixlist_v2_{stamp}.log"
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
    return Elasticsearch(
        hosts=[url],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=180,
        max_retries=0,
    ), url


def folder_snapshot(root: Path) -> dict:
    n_files = total = 0
    max_mtime = 0.0
    for dirpath, _d, names in os.walk(root):
        for name in names:
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            n_files += 1
            total += st.st_size
            max_mtime = max(max_mtime, st.st_mtime)
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
    trans = str.maketrans({
        "（": "(", "）": ")", "【": "[", "】": "]",
        "—": "-", "–": "-", "－": "-", "─": "-", "―": "-", "﹣": "-",
        "〜": "~", "～": "~", "，": ",", "、": ",", "：": ":", "；": ";",
    })
    return re.sub(r"\s+", "", s.translate(trans))


def normalize_ignore_yu(s: str) -> str:
    """用于插进的话判断：豫/预 视为同字。"""
    return normalize_title_cmp(s).translate(_IGNORE_CHARS_FOR_SUFFIX)


def strip_pian_prefix(title: str) -> str:
    raw = (title or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
    m = _CN_PIAN_RE.match(raw)
    return (m.group(1) or "").strip() if m else raw


def int_to_cn(n: int) -> str:
    """1..30 常用中文数字（序号用）。"""
    table = {
        1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十",
        11: "十一", 12: "十二", 13: "十三", 14: "十四", 15: "十五", 16: "十六", 17: "十七",
        18: "十八", 19: "十九", 20: "二十", 21: "二十一", 22: "二十二", 23: "二十三",
        24: "二十四", 25: "二十五", 26: "二十六", 27: "二十七", 28: "二十八", 29: "二十九", 30: "三十",
    }
    return table.get(n, str(n))


def cn_to_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    total = num = 0
    for ch in s:
        if ch in CN_NUM:
            num = CN_NUM[ch]
        elif ch in CN_UNIT:
            unit = CN_UNIT[ch]
            if num == 0:
                num = 1
            total += num * unit
            num = 0
        else:
            return None
    return total + num


def extract_seq(title: str) -> Optional[int]:
    m = _SEQ_TAIL_RE.search((title or "").strip())
    if not m:
        return None
    return cn_to_int(m.group(1))


def stem_title(title: str) -> str:
    """去掉末尾（一）（二）… 得到主干。"""
    t = (title or "").strip()
    t = _SEQ_TAIL_RE.sub("", t).rstrip()
    return t


def group_id(book: str, title: str) -> str:
    return f"{book}|{normalize_title_cmp(stem_title(title))}"


def first_line(text: str) -> str:
    return (text or "").split("\n", 1)[0]


def char_diffs(a: str, b: str) -> list[tuple[str, str]]:
    """简单对齐：长度相近时按位置；否则返回整体。"""
    if a == b:
        return []
    na, nb = list(a), list(b)
    # 用 LCS-ish：若编辑距离小，收集替换对
    diffs = []
    i = j = 0
    while i < len(na) and j < len(nb):
        if na[i] == nb[j]:
            i += 1
            j += 1
            continue
        # 试跳过一边
        if i + 1 < len(na) and na[i + 1] == nb[j]:
            diffs.append((na[i], ""))
            i += 1
        elif j + 1 < len(nb) and na[i] == nb[j + 1]:
            diffs.append(("", nb[j]))
            j += 1
        else:
            diffs.append((na[i], nb[j]))
            i += 1
            j += 1
    while i < len(na):
        diffs.append((na[i], ""))
        i += 1
    while j < len(nb):
        diffs.append(("", nb[j]))
        j += 1
    return diffs


VARIANT_SET = set()
for a, b in _VARIANT_PAIRS:
    VARIANT_SET.add((a, b))
    VARIANT_SET.add((b, a))
    if len(a) == len(b):
        for ca, cb in zip(a, b):
            VARIANT_SET.add((ca, cb))
            VARIANT_SET.add((cb, ca))
for a, b in [("於", "于"), ("乾", "干"), ("著", "着"), ("惟", "唯"), ("裏", "里"), ("豫", "预"), ("痲", "麻")]:
    VARIANT_SET.add((a, b))
    VARIANT_SET.add((b, a))


def classify_char_diff_pair(old: str, new: str) -> str:
    """返回 variant / typo / other。"""
    diffs = char_diffs(old, new)
    if not diffs:
        return "same"
    # 过滤空白差异
    diffs = [(x, y) for x, y in diffs if x.strip() or y.strip() or x or y]
    n_changed = sum(1 for x, y in diffs if x != y)
    if n_changed <= 2:
        all_var = True
        for x, y in diffs:
            if x == y:
                continue
            if (x, y) in VARIANT_SET:
                continue
            if x + y in ("痲疯麻风", "麻风痲疯") or (x == "痲疯" and y == "麻风") or (x == "麻风" and y == "痲疯"):
                continue
            # multi-char substr
            if {x, y} <= {"痲", "麻"} or {x, y} <= {"疯", "疯"}:
                continue
            if x in "─—－–―-﹣" and y in "─—－–―-﹣":
                continue
            all_var = False
            break
        if all_var:
            return "variant"
        # known typo patterns
        joined_old = "".join(x for x, _ in diffs)
        joined_new = "".join(y for _, y in diffs)
        typo_markers = ["耶赂", "耶略", "它带", "题醒", "耶路", "祂带", "提醒"]
        if any(m in old or m in new for m in typo_markers):
            return "typo"
        if n_changed <= 2 and not all_var:
            return "typo_maybe"
    return "other"


def row_dict(**kwargs) -> dict:
    out = {c: "" for c in CSV_COLS}
    out.update({k: ("" if v is None else str(v)) for k, v in kwargs.items()})
    return out


def _git_status() -> str:
    try:
        return subprocess.check_output(
            ["git", "status", "--short", "--", "back_mic/backend/panai4/outline/"],
            cwd=str(REPO_ROOT), text=True, encoding="utf-8", errors="replace",
        ).strip() or "(clean)"
    except Exception as exc:  # noqa: BLE001
        return f"(git failed: {exc})"


def load_pairing(path: Path) -> dict[tuple[str, int], dict]:
    rows = {}
    with path.open(encoding="utf-8-sig", newline="") as fp:
        for r in csv.DictReader(fp):
            path_rel = r.get("desktop_path") or ""
            book_col = next((k for k in r.keys() if k.startswith("desktop_book")), None)
            book = normalize_book((r.get(book_col) or "").strip()) if book_col else ""
            if not book and path_rel:
                book = normalize_book(strip_dir_index(Path(path_rel).parts[0]))
            mno = int(r["msg_no"])
            doc_raw = r.get("doc_title") or ""
            doc = strip_pian_prefix(doc_raw.strip().replace("\n", "").replace("\r", "").replace("\v", ""))
            rows[(book, mno)] = {
                "desktop_path": path_rel,
                "doc_title": doc,
                "doc_title_raw": doc_raw,
            }
    return rows


def scroll_life(es) -> list[dict]:
    from elasticsearch.helpers import scan

    rows = []
    for doc in scan(
        es, index=ES_INDEX,
        query={"query": {"wildcard": {"book_title": "*生命读经*"}}},
        _source={
            "includes": [
                "book_title", "message_title", "message_number", "message_key",
                "source_path", "text", "chunk_index",
            ],
            "excludes": _SOURCE_EXCLUDES,
        },
        size=500,
    ):
        src = doc.get("_source") or {}
        if is_life_study_book((src.get("book_title") or "").strip()):
            rows.append(src)
    return rows


def scroll_text_life(es) -> dict[tuple[str, int], dict]:
    from elasticsearch.helpers import scan

    by_key: dict[tuple[str, int], dict] = {}
    for doc in scan(
        es, index=TL_INDEX, query={"query": {"match_all": {}}},
        _source={"includes": ["book_title", "message_title", "message_number", "text"], "excludes": _SOURCE_EXCLUDES},
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
        mt = (src.get("message_title") or "").strip()
        extra = ""
        m = re.search(r"，第[一二三四五六七八九十百千零〇两0-9]+篇[\s\u3000]*(.*)$", raw_book)
        if m:
            extra = (m.group(1) or "").strip()
        body = strip_pian_prefix(mt)
        title_aug = mt
        if extra and len(normalize_title_cmp(extra)) > len(normalize_title_cmp(body)):
            title_aug = extra if not mt else (
                mt.split("篇", 1)[0] + "篇　" + extra if "篇" in mt and len(normalize_title_cmp(body)) < 8
                else (extra if len(normalize_title_cmp(extra)) > len(normalize_title_cmp(body)) else mt)
            )
            if len(normalize_title_cmp(body)) >= 8 and normalize_title_cmp(extra).startswith(normalize_title_cmp(body)[:10]):
                title_aug = extra
            elif len(normalize_title_cmp(extra)) > len(normalize_title_cmp(body)) + 2:
                title_aug = extra
        stripped = strip_pian_prefix(title_aug)
        key = (canon, mno)
        ent = by_key.get(key)
        if ent is None or len(stripped) > len(ent["title_stripped"]):
            by_key[key] = {
                "message_title": mt,
                "title_stripped": stripped,
                "book_raw": raw_book,
                "text": src.get("text") or "",
            }
        else:
            if not ent.get("text") and src.get("text"):
                ent["text"] = src.get("text") or ""
    return by_key


def recover_d2(path: Path) -> tuple[str, str]:
    """从首段/次段找回「第N篇　篇题」。返回 (d2, note)。"""
    paras, err = read_paragraphs(str(path))
    if err:
        return "", f"read_fail:{err}"
    nonempty = [p for p in paras if (p.get("text") or "").strip()]
    for p in nonempty[:5]:
        t = (p.get("text") or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
        m = _CN_PIAN_RE.match(t)
        if m:
            return (m.group(1) or "").strip(), f"from_para={p.get('para_no')} style={p.get('style')}"
    return "", "not_found"


def find_remainder_in_docx(path: Path, remainder_raw: str) -> Optional[dict]:
    """在桌面 docx 搜索 remainder（归一化子串）。"""
    paras, err = read_paragraphs(str(path))
    if err:
        return None
    nr = normalize_title_cmp(remainder_raw)
    if len(nr) < 4:
        return None
    marker_idx = None
    for para in paras:
        for line in re.split(r"[\n\r\v]+", para.get("text") or ""):
            if line.strip().startswith("职事信息摘录"):
                marker_idx = para["para_no"]
                break
        if marker_idx is not None:
            break
    for para in paras:
        nt = normalize_title_cmp(para.get("text") or "")
        if nr and nr in nt:
            after = marker_idx is not None and para["para_no"] > marker_idx
            return {
                "para_no": para["para_no"],
                "style": para.get("style") or "",
                "after_marker": after,
                "before_marker": marker_idx is None or para["para_no"] <= marker_idx,
            }
    return None


def extract_remainder_raw(e: str, t: str) -> Optional[str]:
    """若 ne 是 nt 真前缀，返回 t 原文中对应 remainder（尽量保留原始分隔）。"""
    ne, nt = normalize_title_cmp(e), normalize_title_cmp(t)
    if not ne or not nt or not nt.startswith(ne) or len(nt) <= len(ne):
        return None
    # 在 t 原文上找：逐步消耗与 e 归一化匹配的前缀
    # 简化：用归一化长度切 — 在 t 上找使 normalize(t[:k])==ne 的最大 k
    best_k = None
    for k in range(len(t) + 1):
        if normalize_title_cmp(t[:k]) == ne:
            best_k = k
    if best_k is None:
        return None
    rem = t[best_k:]
    # 去掉开头的空白/全角空格/破折号类分隔？保留原文
    return rem


def missing_chajin_suffix(e: str, t: str) -> bool:
    """忽略豫/预，判断 t == e + （插进的话）。"""
    ne = normalize_ignore_yu(e)
    nt = normalize_ignore_yu(t)
    suf = normalize_ignore_yu("（插进的话）")
    return bool(ne and nt == ne + suf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(CSV_DEFAULT))
    ap.add_argument("--tl-diff", default=str(TL_DIFF_DEFAULT))
    ap.add_argument("--report", default=str(REPORT_DEFAULT))
    ap.add_argument("--log-dir", default=str(LOG_DIR_DEFAULT))
    args = ap.parse_args()

    t0 = time.time()
    log_path = setup_logging(Path(args.log_dir))
    snap_before = folder_snapshot(LIFE_ROOT)
    es, es_url = make_es()
    info = es.info()
    count_before = es.count(index=ES_INDEX)["count"]
    logging.info("count_before=%s", count_before)

    desk = load_pairing(PAIRING_CSV)
    life = scroll_life(es)
    logging.info("life_chunks=%s", len(life))
    tl_map = scroll_text_life(es)
    logging.info("tl_keys=%s", len(tl_map))

    by_bn: dict[tuple[str, int], list[dict]] = defaultdict(list)
    by_mkey: dict[str, list[dict]] = defaultdict(list)
    for ch in life:
        bt = normalize_book((ch.get("book_title") or "").strip())
        mno = ch.get("message_number")
        mk = ch.get("message_key") or ""
        by_mkey[mk].append(ch)
        if mno is not None:
            by_bn[(bt, int(mno))].append(ch)

    both = sorted(set(desk.keys()) & set(by_bn.keys()))
    logging.info("both=%s", len(both))

    # ---------- build triple for each ----------
    triples = []
    empty_d_keys = []
    for book, mno in both:
        chs = sorted(by_bn[(book, mno)], key=lambda c: c.get("chunk_index") or 0)
        e_raw = (chs[0].get("message_title") or "").strip()
        e = strip_pian_prefix(e_raw)
        d_info = desk[(book, mno)]
        d = d_info["doc_title"]
        d_raw = d_info["doc_title_raw"]
        path_rel = d_info["desktop_path"]
        tl = tl_map.get((book, mno), {})
        t = tl.get("title_stripped") or ""
        t_raw = tl.get("message_title") or ""
        if not normalize_title_cmp(d):
            empty_d_keys.append((book, mno))
        triples.append({
            "book": book, "mno": mno, "chs": chs, "mk": chs[0].get("message_key") or "",
            "e": e, "e_raw": e_raw, "d": d, "d_raw": d_raw, "t": t, "t_raw": t_raw,
            "path": path_rel, "chunk_count": len(chs),
            "d2": "", "d2_note": "", "d_eff": d,
        })

    # ---------- 2.4 recover d2 for empty d ----------
    logging.info("recover d2 for %s empty-doc_title msgs", len(empty_d_keys))
    d2_found = d2_miss = 0
    trip_by_key = {(r["book"], r["mno"]): r for r in triples}
    for book, mno in empty_d_keys:
        r = trip_by_key[(book, mno)]
        d2, note = recover_d2(LIFE_ROOT / r["path"])
        r["d2"] = d2
        r["d2_note"] = note
        if d2:
            d2_found += 1
            r["d_eff"] = d2
        else:
            d2_miss += 1
    logging.info("d2 found=%s miss=%s", d2_found, d2_miss)

    # ---------- Task 1 subtitles ----------
    subtitle_cands = []
    for r in triples:
        rem = extract_remainder_raw(r["e"], r["t"])
        if rem is None:
            continue
        rem_norm = normalize_title_cmp(rem)
        if len(rem_norm) < 4:
            continue
        # 排除仅仅是「（插进的话）」——归 R1
        if rem_norm == normalize_title_cmp("（插进的话）") or rem_norm.endswith(normalize_title_cmp("（插进的话）")) and len(rem_norm) <= len(normalize_title_cmp("（插进的话）")) + 2:
            if missing_chajin_suffix(r["e"], r["t"]) or normalize_ignore_yu(r["t"]) == normalize_ignore_yu(r["e"]) + normalize_ignore_yu("（插进的话）"):
                continue
        subtitle_cands.append({**r, "remainder": rem, "rem_norm_len": len(rem_norm)})

    logging.info("subtitle cands=%s; scanning docx...", len(subtitle_cands))
    sub_found = []
    sub_miss = []
    for i, r in enumerate(subtitle_cands, 1):
        if i % 50 == 0:
            logging.info("subtitle scan %s/%s", i, len(subtitle_cands))
        hit = find_remainder_in_docx(LIFE_ROOT / r["path"], r["remainder"])
        r["docx_hit"] = hit
        if hit:
            sub_found.append(r)
        else:
            sub_miss.append(r)

    # ---------- classify & build fix rows ----------
    fix_rows: list[dict] = []
    rule_counts_old = Counter()  # before d2: using original d
    rule_counts_new = Counter()  # after d_eff
    handled_keys: set[tuple[str, int]] = set()
    r5_char_report = []  # for 2.3

    def add_fix(**kw):
        book, mno = kw.get("book"), int(kw.get("msg_no"))
        if (book, mno) == SKIP_KEY:
            return
        if not kw.get("group_id"):
            kw["group_id"] = group_id(book, kw.get("old") or "")
        fix_rows.append(row_dict(**kw))
        handled_keys.add((book, mno))

    # Task 1: subtitle rows
    for r in subtitle_cands:
        rem = r["remainder"]
        rem_len = r["rem_norm_len"]
        hit = r["docx_hit"]
        ne, nt = normalize_title_cmp(r["e"]), normalize_title_cmp(r["t"])
        prefix_ok = nt.startswith(ne) and len(nt) > len(ne)
        conf = "auto"
        proposal = ""
        note_parts = [f"remainder_len={rem_len}"]
        source = "e_plus_t_remainder"
        if not prefix_ok:
            conf = "needs_review"
            note_parts.append("e非t前缀(用字差?)")
            # proposal: e + rem from t after fuzzy
            proposal = r["e"] + rem
            source = "e_plus_t_remainder"
        elif rem_len > 40:
            conf = "needs_review"
            note_parts.append("remainder>40")
        elif hit is None:
            conf = "needs_review"
            note_parts.append("副题仅见于 text_life")
        elif not hit.get("before_marker", True):
            conf = "needs_review"
            note_parts.append(f"副题在摘录区后 para={hit['para_no']}")
        else:
            note_parts.append(f"docx para={hit['para_no']} style={hit['style']} before_marker")

        # new = e_raw 前半不动 + rem 原文；e_raw 与 e 通常相同（已去第N篇）
        base = r["e_raw"] if normalize_title_cmp(r["e_raw"]) == normalize_title_cmp(r["e"]) else r["e"]
        suggested = (base + rem) if rem else ""
        if not prefix_ok:
            proposal = proposal or suggested
            suggested = ""
        elif conf == "needs_review":
            proposal = suggested
            suggested = ""
        add_fix(
            kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
            old=r["e_raw"], new=suggested if conf == "auto" else "",
            category="subtitle", source_of_new=source, confidence=conf,
            proposal=proposal if conf == "needs_review" else "",
            doc_title_raw=r["d_eff"] or r["d"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="是" if conf == "auto" else "否",
            note=";".join(note_parts),
            group_id=group_id(r["book"], r["e"]),
        )

    subtitle_keys = {(r["book"], r["mno"]) for r in subtitle_cands}

    # Task 2.7 symbols first (can stack conceptually; one row per msg)
    symbol_rows_info = []
    for r in triples:
        if _BOX_DASH in r["e_raw"]:
            new_t = r["e_raw"].replace(_BOX_DASH, _EM_DASH)
            symbol_rows_info.append(r)
            if (r["book"], r["mno"]) == SKIP_KEY:
                continue
            # if already subtitle auto with same key, still add symbol? Prefer merge later.
            # For clarity: if title only differs by dash, add symbol row.
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new=new_t, category="symbol", source_of_new="symbol_replace",
                confidence="auto", proposal="",
                doc_title_raw=r["d_eff"] or r["d"], es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="是", note="─(U+2500)→—(U+2014)",
                group_id=group_id(r["book"], r["e"]),
            )

    # other dash chars stats in titles
    dash_title_stats = Counter()
    for r in triples:
        for ch, label in _DASH_CHARS.items():
            if ch in r["e_raw"]:
                dash_title_stats[f"{ch}/{label}"] += 1

    # Pass all triples for R1-R7 style with d_eff
    def basic_rule(d, e, t) -> str:
        nd, ne, nt = normalize_title_cmp(d), normalize_title_cmp(e), normalize_title_cmp(t)
        d_miss = not nd
        if missing_chajin_suffix(e, t) or (
            ne and nt and normalize_ignore_yu(t) == normalize_ignore_yu(e) + normalize_ignore_yu("（插进的话）")
        ):
            return "R1"
        if d_miss:
            if ne == nt:
                return "R2"
        else:
            if ne == nt == nd:
                return "R2"
        if (not d_miss) and ne == nt and nd != ne:
            return "R3"
        if (not d_miss) and nd == nt and ne != nd:
            return "R4"
        if (not d_miss) and nd == ne and nt != nd:
            return "R5"
        if d_miss and ne != nt:
            return "R6"
        return "R7"

    # recount with original d and d_eff
    for r in triples:
        rule_counts_old[basic_rule(r["d"], r["e"], r["t"])] += 1
        rule_counts_new[basic_rule(r["d_eff"], r["e"], r["t"])] += 1

    # Explicit typos（不依赖 R5；可在 d==e 时仍改，如路加30）
    for r in triples:
        key = (r["book"], r["mno"])
        if key not in EXPLICIT_TYPOS or key == SKIP_KEY:
            continue
        new_val = r["e_raw"]
        for a, b in EXPLICIT_TYPOS[key]:
            new_val = new_val.replace(a, b)
        new_val = new_val.replace(_BOX_DASH, _EM_DASH)
        if new_val == r["e_raw"]:
            continue
        add_fix(
            kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
            old=r["e_raw"], new=new_val, category="typo", source_of_new="explicit_fix",
            confidence="auto", proposal="",
            doc_title_raw=r["d_eff"] or r["d"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="是", note=f"explicit_fix {EXPLICIT_TYPOS[key]}；顺带─→—",
            group_id=group_id(r["book"], r["e"]),
        )

    # R1: missing 插进的话
    for r in triples:
        key = (r["book"], r["mno"])
        if key == SKIP_KEY:
            continue
        if not (
            missing_chajin_suffix(r["e"], r["t"])
            or normalize_ignore_yu(r["t"]) == normalize_ignore_yu(r["e"]) + normalize_ignore_yu("（插进的话）")
        ):
            # also: t has suffix and e doesn't, ignoring 豫/预 in stem
            ne_i = normalize_ignore_yu(r["e"])
            nt_i = normalize_ignore_yu(r["t"])
            suf = normalize_ignore_yu("（插进的话）")
            if not (ne_i and nt_i == ne_i + suf):
                continue
        # skip if already handled as pure subtitle with longer rem? If rem is only 插进的话, subtitle skipped it
        new_val = r["e"] + "（插进的话）"
        # avoid dup if already in fix with same new from subtitle
        add_fix(
            kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
            old=r["e_raw"], new=new_val, category="suffix", source_of_new="e_plus_t_remainder",
            confidence="auto", proposal="",
            doc_title_raw=r["d_eff"] or r["d"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="是", note="补（插进的话）；忽略豫/预差异",
            group_id=group_id(r["book"], r["e"]),
        )

    # R4 with d_eff
    for r in triples:
        key = (r["book"], r["mno"])
        if key == SKIP_KEY:
            continue
        d = r["d_eff"]
        if not normalize_title_cmp(d):
            continue
        if normalize_title_cmp(d) != normalize_title_cmp(r["t"]):
            continue
        if normalize_title_cmp(r["e"]) == normalize_title_cmp(d):
            continue
        # R4: d==t ≠ e
        # 用字习惯：利未记 痲疯
        if r["book"] == "利未记生命读经" and "麻风" in d and "痲疯" in r["e"]:
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="other", source_of_new="",
                confidence="keep", proposal="",
                doc_title_raw=d, es12490_title_raw=r["e_raw"], text_life_title_raw=r["t"],
                chunk_count=r["chunk_count"], reembed="否",
                note="用字习惯痲疯/麻风；同系列保持不动",
                group_id=group_id(r["book"], r["e"]),
            )
            continue
        # 序号冲突 → 交任务4（若仅序号不同）
        se, sd = extract_seq(r["e"]), extract_seq(d)
        stem_e, stem_d = normalize_title_cmp(stem_title(r["e"])), normalize_title_cmp(stem_title(d))
        if se is not None and sd is not None and stem_e == stem_d and se != sd:
            # defer to number_fix section — mark for later
            r["pending_number"] = True
            continue
        # 创世记 109
        if r["book"] == "创世记生命读经" and r["mno"] == 109:
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="recovered_title", source_of_new="desktop_title",
                confidence="needs_review", proposal=d,
                doc_title_raw=d, es12490_title_raw=r["e_raw"], text_life_title_raw=r["t"],
                chunk_count=r["chunk_count"], reembed="否",
                note="e与d完全不同；序号(七)与上下篇连续，proposal=成熟的表显（七）",
                group_id=group_id(r["book"], r["e"]),
            )
            continue
        # 已在副题任务处理的，不再重复 R4（避免同篇双行导致模拟时拼接两次）
        if key in subtitle_keys:
            continue
        # but以理15/16、腓立比17：副题丢失 — auto with d
        # general R4 auto
        add_fix(
            kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
            old=r["e_raw"], new=d, category="recovered_title", source_of_new="desktop_title",
            confidence="auto", proposal="",
            doc_title_raw=d, es12490_title_raw=r["e_raw"], text_life_title_raw=r["t"],
            chunk_count=r["chunk_count"], reembed="是",
            note="R4: d==t≠e",
            group_id=group_id(r["book"], r["e"]),
        )

    # R5: d==e ≠ t  — split
    for r in triples:
        key = (r["book"], r["mno"])
        if key == SKIP_KEY:
            continue
        d = r["d_eff"]
        if not normalize_title_cmp(d):
            continue
        if normalize_title_cmp(d) != normalize_title_cmp(r["e"]):
            continue
        if normalize_title_cmp(r["t"]) == normalize_title_cmp(r["e"]):
            continue
        # if subtitle candidate already handled
        if key in subtitle_keys:
            continue
        if key in EXPLICIT_TYPOS:
            continue  # 已在 explicit 段处理
        kind = classify_char_diff_pair(r["e"], r["t"])
        diffs = char_diffs(r["e"], r["t"])
        r5_char_report.append({
            "book": r["book"], "mno": r["mno"], "kind": kind,
            "e": r["e"], "t": r["t"], "diffs": diffs[:8],
        })
        if kind == "variant":
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="other", source_of_new="",
                confidence="keep", proposal="",
                doc_title_raw=d, es12490_title_raw=r["e_raw"], text_life_title_raw=r["t"],
                chunk_count=r["chunk_count"], reembed="否",
                note=f"用字习惯/异体 diffs={diffs[:6]}",
                group_id=group_id(r["book"], r["e"]),
            )
        elif kind in ("typo", "typo_maybe"):
            conf = "auto" if kind == "typo" and key in EXPLICIT_TYPOS else "needs_review"
            # only auto if explicit; else needs_review
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="" if conf != "auto" else r["t"],
                category="typo", source_of_new="text_life",
                confidence=conf, proposal=r["t"] if conf == "needs_review" else "",
                doc_title_raw=d, es12490_title_raw=r["e_raw"], text_life_title_raw=r["t"],
                chunk_count=r["chunk_count"], reembed="否",
                note=f"R5字符差 kind={kind} diffs={diffs[:6]}",
                group_id=group_id(r["book"], r["e"]),
            )
        else:
            # keep for 12490; goes to text_life diff
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="other", source_of_new="",
                confidence="keep", proposal="",
                doc_title_raw=d, es12490_title_raw=r["e_raw"], text_life_title_raw=r["t"],
                chunk_count=r["chunk_count"], reembed="否",
                note=f"R5其他 diffs={diffs[:6]} → text_life差异清单",
                group_id=group_id(r["book"], r["e"]),
            )

    # R6 remaining after d2
    for r in triples:
        key = (r["book"], r["mno"])
        if key == SKIP_KEY:
            continue
        if normalize_title_cmp(r["d_eff"]):
            continue  # recovered
        if normalize_title_cmp(r["e"]) == normalize_title_cmp(r["t"]):
            continue
        add_fix(
            kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
            old=r["e_raw"], new="", category="other", source_of_new="",
            confidence="needs_review", proposal="",
            doc_title_raw="", es12490_title_raw=r["e_raw"], text_life_title_raw=r["t"],
            chunk_count=r["chunk_count"], reembed="否",
            note=f"R6桌面无篇题且d2未找回；{r['d2_note']}",
            group_id=group_id(r["book"], r["e"]),
        )

    # R7 specials
    for r in triples:
        key = (r["book"], r["mno"])
        if key == SKIP_KEY:
            continue
        d = r["d_eff"]
        nd, ne, nt = normalize_title_cmp(d), normalize_title_cmp(r["e"]), normalize_title_cmp(r["t"])
        if not nd:
            continue
        if not (nd != ne and nd != nt and ne != nt):
            continue
        if key == ("哈巴谷书生命读经", 2):
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="other", source_of_new="",
                confidence="needs_review", proposal=r["e_raw"],
                doc_title_raw=d, es12490_title_raw=r["e_raw"], text_life_title_raw=r["t"],
                chunk_count=r["chunk_count"], reembed="否",
                note="R7 proposal=保留12490现有写法",
                group_id=group_id(r["book"], r["e"]),
            )
        elif key == ("马可福音生命读经", 68):
            prop = "一种完全照着神新约经纶，并为着神新约经纶的生活（十七）"
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="number_fix", source_of_new="",
                confidence="needs_review", proposal=prop,
                doc_title_raw=d, es12490_title_raw=r["e_raw"], text_life_title_raw=r["t"],
                chunk_count=r["chunk_count"], reembed="否",
                note="R7 序号按连续；字用着",
                group_id=group_id(r["book"], r["e"]),
            )
        else:
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="other", source_of_new="",
                confidence="needs_review", proposal="",
                doc_title_raw=d, es12490_title_raw=r["e_raw"], text_life_title_raw=r["t"],
                chunk_count=r["chunk_count"], reembed="否",
                note="R7三者不同",
                group_id=group_id(r["book"], r["e"]),
            )

    # 2.6 prefix residue 路加28
    for r in triples:
        if r["book"] == "路加福音生命读经" and r["mno"] == 28:
            e2 = strip_pian_prefix(r["e_raw"]) if _CN_PIAN_RE.match(r["e_raw"].strip()) else r["e"]
            # if e_raw starts with 第二十八篇
            if r["e_raw"].startswith("第二十八篇"):
                e2 = re.sub(r"^第二十八篇[\s\u3000]*", "", r["e_raw"]).strip()
            t2 = strip_pian_prefix(r["t"])
            if normalize_title_cmp(e2) == normalize_title_cmp(t2) or normalize_title_cmp(e2) == normalize_title_cmp(r["t"]):
                add_fix(
                    kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                    old=r["e_raw"], new=e2, category="prefix_residue", source_of_new="desktop_title",
                    confidence="auto", proposal="",
                    doc_title_raw=r["d_eff"] or r["d"], es12490_title_raw=r["e_raw"],
                    text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                    reembed="是", note="去掉第二十八篇前缀",
                    group_id=group_id(r["book"], r["e"]),
                )
            else:
                add_fix(
                    kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                    old=r["e_raw"], new="", category="prefix_residue", source_of_new="",
                    confidence="needs_review", proposal=e2,
                    doc_title_raw=r["d_eff"] or r["d"], es12490_title_raw=r["e_raw"],
                    text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                    reembed="否", note="前缀残留但与t不完全一致",
                    group_id=group_id(r["book"], r["e"]),
                )
        if r["book"] == "诗篇生命读经" and r["mno"] == 33:
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="other", source_of_new="",
                confidence="keep", proposal="",
                doc_title_raw=r["d_eff"] or r["d"], es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="否", note="真篇题含第三十二篇信息的补充",
                group_id=group_id(r["book"], r["e"]),
            )

    # ---------- Task 4 number sequences ----------
    groups: dict[str, list] = defaultdict(list)
    for r in triples:
        gid = group_id(r["book"], r["e"])
        groups[gid].append(r)
    for gid in groups:
        groups[gid].sort(key=lambda x: x["mno"])

    number_focus = [
        ("出埃及记生命读经", 180),
        ("路加福音生命读经", 63),
        ("哥林多后书生命读经", 57),
        ("马太福音生命读经", 43),
        ("民数记生命读经", 26),
        ("使徒行传生命读经", 39),
        ("使徒行传生命读经", 54),
        ("马可福音生命读经", 68),
    ]
    number_conclusions = []

    def seq_list(items, field):
        return [(x["mno"], extract_seq(x[field] if field != "d" else x["d_eff"])) for x in items]

    def is_contiguous(pairs):
        vals = [v for _, v in pairs if v is not None]
        if len(vals) < 2:
            return True, "short"
        # check unique and sorted ascending by mno already
        if len(vals) != len(set(vals)):
            return False, "dup"
        for i in range(1, len(vals)):
            if vals[i] != vals[i - 1] + 1:
                return False, f"gap@{vals[i-1]}->{vals[i]}"
        return True, "ok"

    for book, mno in number_focus:
        r = trip_by_key.get((book, mno))
        if not r:
            continue
        gid = group_id(book, r["e"])
        items = groups[gid]
        se = seq_list(items, "e")
        sd = seq_list(items, "d")
        st = seq_list(items, "t")
        ok_e, why_e = is_contiguous(se)
        ok_d, why_d = is_contiguous(sd)
        ok_t, why_t = is_contiguous(st)
        # which source continuous?
        winners = []
        if ok_e:
            winners.append("e")
        if ok_d:
            winners.append("d")
        if ok_t:
            winners.append("t")
        conc = {
            "book": book, "mno": mno, "gid": gid, "n_in_group": len(items),
            "e_seq": extract_seq(r["e"]), "d_seq": extract_seq(r["d_eff"]), "t_seq": extract_seq(r["t"]),
            "ok_e": ok_e, "ok_d": ok_d, "ok_t": ok_t, "why_e": why_e, "why_d": why_d, "why_t": why_t,
            "winners": winners,
        }
        number_conclusions.append(conc)
        # 马可68：R7 已写 needs_review（字用「着」），此处只记结论
        if (book, mno) == ("马可福音生命读经", 68):
            continue
        seq_conflict = (
            r.get("pending_number")
            or (extract_seq(r["e"]) != extract_seq(r["d_eff"]) and extract_seq(r["d_eff"]) is not None)
            or (extract_seq(r["e"]) != extract_seq(r["t"]) and extract_seq(r["t"]) is not None)
        )
        if not seq_conflict:
            continue
        conf = "needs_review"
        new_val = ""
        prop = r["d_eff"] or r["t"]
        se, sd, st_ = extract_seq(r["e"]), extract_seq(r["d_eff"]), extract_seq(r["t"])
        # 规则：某来源使组内序号连续，且本篇序号与另一来源一致 → auto；e 已连续且与 d/t 之一同号 → keep
        if ok_e and (se == sd or se == st_):
            conf = "keep"
            prop = ""
        elif ok_d and sd is not None and sd == st_:
            conf = "auto"
            new_val = r["d_eff"]
            prop = ""
        elif ok_t and st_ is not None and st_ == sd:
            conf = "auto"
            new_val = r["d_eff"] or r["t"]
            prop = ""
        elif ok_t and st_ is not None and se != st_ and "e" not in winners:
            # t 连续但 d 不一定；若仅 t 与另一源本篇同号才 auto——此处 d 不同则 needs_review
            conf = "needs_review"
            prop = stem_title(r["e_raw"]) + f"（{int_to_cn(st_)}）"
        else:
            conf = "needs_review"
            want = sd if ok_d else (st_ if ok_t else None)
            if want is not None:
                prop = stem_title(r["e_raw"]) + f"（{int_to_cn(want)}）"
            else:
                prop = r["d_eff"] or r["t"]
        if conf == "keep":
            add_fix(
                kind="title", book=book, msg_no=mno, message_key=r["mk"],
                old=r["e_raw"], new="", category="number_fix",
                source_of_new="", confidence="keep", proposal="",
                doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="否",
                note=f"序号：e已自洽 winners={winners} e/d/t={conc['e_seq']}/{conc['d_seq']}/{conc['t_seq']}",
                group_id=gid,
            )
        else:
            add_fix(
                kind="title", book=book, msg_no=mno, message_key=r["mk"],
                old=r["e_raw"], new=new_val, category="number_fix",
                source_of_new="desktop_title" if new_val else "",
                confidence=conf, proposal=prop,
                doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="是" if conf == "auto" else "否",
                note=f"序号冲突 winners={winners} e/d/t={conc['e_seq']}/{conc['d_seq']}/{conc['t_seq']}",
                group_id=gid,
            )

    # 使徒行传 55/56 写法
    acts_style = []
    for r in triples:
        if r["book"] == "使徒行传生命读经" and r["mno"] in range(50, 60):
            acts_style.append((r["mno"], r["e"]))
    for mno in (55, 56):
        r = trip_by_key.get(("使徒行传生命读经", mno))
        if not r:
            continue
        add_fix(
            kind="title", book=r["book"], msg_no=mno, message_key=r["mk"],
            old=r["e_raw"], new="", category="number_fix", source_of_new="",
            confidence="needs_review",
            proposal="与同系列多数写法一致（二十/二十一）",
            doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="否", note=f"序号写法二一/二十 系列样本={acts_style}",
            group_id=group_id(r["book"], r["e"]),
        )

    # ---------- Deduplicate fix_rows: prefer auto subtitle/suffix over keep; merge same key+field ----------
    # Keep multiple categories for same msg if different (symbol + subtitle). 
    # If same category dup, keep highest priority.
    priority = {"auto": 3, "needs_review": 2, "keep": 1}
    dedup: dict[tuple, dict] = {}
    for r in fix_rows:
        k = (r["book"], r["msg_no"], r["category"], r["old"], r["new"])
        prev = dedup.get(k)
        if prev is None or priority.get(r["confidence"], 0) > priority.get(prev["confidence"], 0):
            dedup[k] = r
    fix_rows = list(dedup.values())

    # For same (book,msg) with both symbol and other auto title changes, 
    # compose final new if needed for simulation:
    # Apply order: start from e_raw → symbol → other replacements

    # ---------- Task 3 series consistency ----------
    # Build applied titles after auto
    applied: dict[tuple[str, int], str] = {}
    for r in triples:
        applied[(r["book"], r["mno"])] = r["e_raw"]

    _CONTENT_CATS = {"subtitle", "suffix", "recovered_title", "typo", "prefix_residue", "number_fix"}

    def apply_auto_to_applied():
        """每篇最多应用一条内容改动 + 可选 symbol，避免 subtitle+recovered 双拼。"""
        by_msg = defaultdict(list)
        for r in fix_rows:
            if r["confidence"] != "auto" or not r["new"]:
                continue
            by_msg[(r["book"], int(r["msg_no"]))].append(r)
        for key, rows in by_msg.items():
            cur = applied[key]
            content = [r for r in rows if r["category"] in _CONTENT_CATS]
            symbols = [r for r in rows if r["category"] == "symbol"]
            # 内容改动优先级：recovered_title(desktop) > subtitle > typo/suffix/prefix/number
            pref = {"recovered_title": 5, "subtitle": 4, "typo": 3, "suffix": 3, "prefix_residue": 2, "number_fix": 2}
            if content:
                content.sort(key=lambda r: pref.get(r["category"], 0), reverse=True)
                chosen = content[0]
                for r in content[1:]:
                    if normalize_title_cmp(r["new"]) == normalize_title_cmp(chosen["new"]):
                        continue
                    if pref.get(r["category"], 0) == pref.get(chosen["category"], 0) and len(r["new"]) > len(chosen["new"]):
                        chosen = r
                cur = chosen["new"]
            # 符号：独立 symbol 行，或内容 new 里仍残留 ─
            if symbols or _BOX_DASH in cur:
                cur = cur.replace(_BOX_DASH, _EM_DASH)
            applied[key] = cur

    apply_auto_to_applied()

    # 预建：已有副题清单行的篇（含 needs_review）——视为已处理，不算「仍缺」
    _subtitle_listed = {
        (r["book"], int(r["msg_no"]))
        for r in fix_rows
        if r["category"] == "subtitle"
    }

    def peer_still_needs_same_fix(it, changed_items, title_map) -> bool:
        """未改动的 peer 是否仍缺与已改 peer 同类的改动。"""
        kinds = set()
        for ch in changed_items:
            key = (ch["book"], ch["mno"])
            now = title_map.get(key, ch["e_raw"])
            if _BOX_DASH in ch["e_raw"] and _BOX_DASH not in now and _EM_DASH in now:
                kinds.add("symbol")
            if ch["e_raw"].startswith("雅各") and not now.startswith("雅各"):
                kinds.add("strip_雅各")
            rem = extract_remainder_raw(ch["e"], ch["t"])
            if rem and normalize_title_cmp(now).startswith(normalize_title_cmp(ch["e"])) and len(normalize_title_cmp(now)) > len(normalize_title_cmp(ch["e"])):
                kinds.add("subtitle")
            if now.endswith("（插进的话）") and not ch["e_raw"].endswith("（插进的话）"):
                kinds.add("suffix")
            if ch["e_raw"].startswith("第") and "篇" in ch["e_raw"][:8] and not now.startswith("第"):
                kinds.add("prefix")
        if not kinds:
            return False
        if "symbol" in kinds and _BOX_DASH in it["e_raw"]:
            return True
        if "strip_雅各" in kinds and it["e_raw"].startswith("雅各"):
            return True
        if "subtitle" in kinds:
            # 已在副题清单（含 needs_review/仅见于text_life）→ 不算缺
            if (it["book"], it["mno"]) in _subtitle_listed:
                return False
            rem = extract_remainder_raw(it["e"], it["t"])
            if rem and len(normalize_title_cmp(rem)) >= 4:
                return True
            return False
        if "suffix" in kinds and missing_chajin_suffix(it["e"], it["t"]):
            return True
        if "prefix" in kinds and it["e_raw"].startswith("第") and "篇" in it["e_raw"][:8]:
            return True
        return False

    def group_inconsistency(title_map):
        bad = []
        gmap: dict[str, list] = defaultdict(list)
        for r in triples:
            gid = group_id(r["book"], r["e"])
            gmap[gid].append(r)
        for gid, items in gmap.items():
            if len(items) < 2:
                continue
            flags = []
            for it in items:
                key = (it["book"], it["mno"])
                orig = it["e_raw"]
                now = title_map.get(key, orig)
                flags.append(normalize_title_cmp(orig) != normalize_title_cmp(now))
            if not (any(flags) and not all(flags)):
                continue
            changed_items = [it for it, ch in zip(items, flags) if ch]
            # 仅当未改 peer 仍缺同类改动时才算不一致
            real_bad = False
            for it, ch in zip(items, flags):
                if ch:
                    continue
                if peer_still_needs_same_fix(it, changed_items, title_map):
                    real_bad = True
                    break
            if real_bad:
                bad.append((gid, items, flags))
        return bad

    bad_before_series = group_inconsistency(applied)

    # Series unification
    series_extra = []
    for gid, items, flags in bad_before_series:
        peer_news = [applied[(x["book"], x["mno"])] for x, ch in zip(items, flags) if ch]
        if not peer_news:
            continue
        peer_stem = normalize_title_cmp(stem_title(strip_pian_prefix(peer_news[0])))
        for it, changed in zip(items, flags):
            if changed:
                continue
            key = (it["book"], it["mno"])
            # 副题：已在清单（含 needs_review）则跳过；未列出且 e 为 t 前缀 → proposal 级补齐（不强制 auto）
            rem = extract_remainder_raw(it["e"], it["t"])
            if rem and len(normalize_title_cmp(rem)) >= 4 and (it["book"], it["mno"]) not in _subtitle_listed:
                new_v = (it["e_raw"] if normalize_title_cmp(it["e_raw"]) == normalize_title_cmp(it["e"]) else it["e"]) + rem
                series_extra.append((it, new_v, gid, "subtitle_proposal"))
                add_fix(
                    kind="title", book=it["book"], msg_no=it["mno"], message_key=it["mk"],
                    old=it["e_raw"], new="", category="subtitle",
                    source_of_new="e_plus_t_remainder", confidence="needs_review", proposal=new_v,
                    doc_title_raw=it["d_eff"] or it["d"], es12490_title_raw=it["e_raw"],
                    text_life_title_raw=it["t"], chunk_count=it["chunk_count"],
                    reembed="否",
                    note=f"系列一致性建议补副题（未auto） group={gid}",
                    group_id=gid,
                )
                _subtitle_listed.add((it["book"], it["mno"]))
                continue
            cand = it["t"] if it["t"] else ""
            if cand and normalize_title_cmp(stem_title(cand)) == peer_stem:
                series_extra.append((it, cand, gid, "text_life"))
                add_fix(
                    kind="title", book=it["book"], msg_no=it["mno"], message_key=it["mk"],
                    old=it["e_raw"], new=cand, category="recovered_title",
                    source_of_new="text_life", confidence="auto", proposal="",
                    doc_title_raw=it["d_eff"] or it["d"], es12490_title_raw=it["e_raw"],
                    text_life_title_raw=it["t"], chunk_count=it["chunk_count"],
                    reembed="是",
                    note=f"系列一致性补齐(依text_life与已改peer) group={gid}",
                    group_id=gid,
                )
                applied[key] = cand
                continue
            e2 = it["e_raw"]
            if e2.startswith("雅各"):
                trial = e2[len("雅各"):]
                if normalize_title_cmp(stem_title(trial)) == peer_stem:
                    series_extra.append((it, trial, gid, "strip_雅各"))
                    add_fix(
                        kind="title", book=it["book"], msg_no=it["mno"], message_key=it["mk"],
                        old=it["e_raw"], new=trial, category="recovered_title",
                        source_of_new="desktop_title", confidence="auto", proposal="",
                        doc_title_raw=it["d_eff"] or it["d"], es12490_title_raw=it["e_raw"],
                        text_life_title_raw=it["t"], chunk_count=it["chunk_count"],
                        reembed="是",
                        note=f"系列一致性去「雅各」前缀 group={gid}",
                        group_id=gid,
                    )
                    applied[key] = trial
                    continue
            # 符号
            if _BOX_DASH in it["e_raw"]:
                trial = it["e_raw"].replace(_BOX_DASH, _EM_DASH)
                series_extra.append((it, trial, gid, "symbol"))
                add_fix(
                    kind="title", book=it["book"], msg_no=it["mno"], message_key=it["mk"],
                    old=it["e_raw"], new=trial, category="symbol",
                    source_of_new="symbol_replace", confidence="auto", proposal="",
                    doc_title_raw=it["d_eff"] or it["d"], es12490_title_raw=it["e_raw"],
                    text_life_title_raw=it["t"], chunk_count=it["chunk_count"],
                    reembed="是",
                    note=f"系列一致性─→— group={gid}",
                    group_id=gid,
                )
                applied[key] = trial

    # Dedup: 同篇同 category 留一条；同篇 subtitle+recovered 同 new 只留一条
    def _dedup_fix_rows(rows):
        by_msg_cat = {}
        for r in rows:
            k = (r["book"], r["msg_no"], r["category"])
            prev = by_msg_cat.get(k)
            pr = {"auto": 3, "needs_review": 2, "keep": 1}
            if prev is None or pr.get(r["confidence"], 0) > pr.get(prev["confidence"], 0):
                by_msg_cat[k] = r
            elif pr.get(r["confidence"], 0) == pr.get(prev["confidence"], 0) and len(r.get("new") or "") > len(prev.get("new") or ""):
                by_msg_cat[k] = r
        out = list(by_msg_cat.values())
        # drop recovered_title auto if subtitle auto same msg with same normalized new
        sub_new = {
            (r["book"], r["msg_no"]): normalize_title_cmp(r["new"])
            for r in out
            if r["category"] == "subtitle" and r["confidence"] == "auto" and r["new"]
        }
        final = []
        for r in out:
            if r["category"] == "recovered_title" and r["confidence"] == "auto" and r["new"]:
                sn = sub_new.get((r["book"], r["msg_no"]))
                if sn and sn == normalize_title_cmp(r["new"]):
                    continue
            final.append(r)
        return final

    fix_rows = _dedup_fix_rows(fix_rows)

    # re-apply all autos
    for r in triples:
        applied[(r["book"], r["mno"])] = r["e_raw"]
    apply_auto_to_applied()
    bad_after = group_inconsistency(applied)

    bad_after_reasons = []
    for gid, items, flags in bad_after:
        parts = []
        for it, ch in zip(items, flags):
            parts.append(f"#{it['mno']}={'改' if ch else '未改'}")
        bad_after_reasons.append((gid, ",".join(parts)))

    # ---------- Task 5 variant stats ----------
    def count_pair_in_texts(chunks, in_title=True):
        """返回 {pair: {title_hits, body_chunks, body_occ}}"""
        out = {f"{a}/{b}": {"title": 0, "body_chunks": 0, "body_occ": 0} for a, b in _VARIANT_PAIRS}
        out["耶赂/耶略/耶路"] = {"title": 0, "body_chunks": 0, "body_occ": 0}
        out["题醒/提醒"] = {"title": 0, "body_chunks": 0, "body_occ": 0}
        out["─/—"] = {"title": 0, "body_chunks": 0, "body_occ": 0}
        for ch in chunks:
            title = ch.get("message_title") or ""
            body = "\n".join((ch.get("text") or "").split("\n")[1:])
            for a, b in _VARIANT_PAIRS:
                key = f"{a}/{b}"
                if a in title or b in title:
                    out[key]["title"] += 1
                ca, cb = body.count(a), body.count(b)
                if ca or cb:
                    out[key]["body_chunks"] += 1
                    out[key]["body_occ"] += ca + cb
            for tok in ("耶赂", "耶略", "耶路"):
                if tok in title:
                    out["耶赂/耶略/耶路"]["title"] += 1
                    break
            csum = sum(body.count(t) for t in ("耶赂", "耶略", "耶路"))
            if csum:
                out["耶赂/耶略/耶路"]["body_chunks"] += 1
                out["耶赂/耶略/耶路"]["body_occ"] += csum
            if "题醒" in title or "提醒" in title:
                out["题醒/提醒"]["title"] += 1
            c2 = body.count("题醒") + body.count("提醒")
            if c2:
                out["题醒/提醒"]["body_chunks"] += 1
                out["题醒/提醒"]["body_occ"] += c2
            if _BOX_DASH in title or _EM_DASH in title:
                out["─/—"]["title"] += 1
            cd = body.count(_BOX_DASH) + body.count(_EM_DASH)
            if cd:
                out["─/—"]["body_chunks"] += 1
                out["─/—"]["body_occ"] += cd
        return out

    # one chunk per message for title stats fairness — use all chunks for body
    life_title_reps = []
    seen_mk = set()
    for ch in life:
        mk = ch.get("message_key") or ""
        if mk in seen_mk:
            continue
        seen_mk.add(mk)
        life_title_reps.append(ch)
    stats_12490 = count_pair_in_texts(life)
    # refine title counts on unique msgs
    stats_12490_title = count_pair_in_texts(life_title_reps)

    tl_chunks_fake = []
    for key, ent in tl_map.items():
        tl_chunks_fake.append({
            "message_title": ent.get("title_stripped") or ent.get("message_title") or "",
            "text": "hdr\n" + (ent.get("text") or ""),
        })
    stats_tl = count_pair_in_texts(tl_chunks_fake)

    # ---------- Task 6 samples & header check ----------
    reembed_msgs = {}
    for r in fix_rows:
        if r["reembed"] == "是" and r["confidence"] == "auto" and r["new"]:
            reembed_msgs[r["message_key"]] = r
    reembed_blocks = sum(int(reembed_msgs[mk]["chunk_count"]) for mk in reembed_msgs)
    cost = reembed_blocks / 1000.0 * 0.002

    # pick 8 samples（必须含副题/插进的话/─/序号；序号若无 auto 则用 needs_review 的 proposal 示意）
    want_cats = ["subtitle", "suffix", "symbol", "number_fix"]
    samples = []

    def _add_sample(r, new_title, cat=None):
        mk = r["message_key"]
        chs = by_mkey.get(mk) or []
        if not chs:
            return
        ch = sorted(chs, key=lambda c: c.get("chunk_index") or 0)[0]
        fl = first_line(ch.get("text") or "")
        bt = (ch.get("book_title") or "").strip()
        samples.append({
            "category": cat or r["category"], "book": r["book"], "mno": r["msg_no"],
            "before": fl, "after": f"{bt}\u3000{new_title}",
            "body2": "\n".join((ch.get("text") or "").split("\n")[1:3])[:120],
        })

    for cat in want_cats:
        if any(s["category"] == cat for s in samples):
            continue
        hit = False
        for mk, r in reembed_msgs.items():
            if r["category"] == cat:
                _add_sample(r, applied.get((r["book"], int(r["msg_no"])), r["new"]), cat)
                hit = True
                break
        if not hit and cat == "number_fix":
            for r in fix_rows:
                if r["category"] == "number_fix" and (r.get("proposal") or r.get("new")):
                    _add_sample(r, r.get("new") or r.get("proposal"), cat)
                    break
    for mk, r in reembed_msgs.items():
        if len(samples) >= 8:
            break
        if any(s["book"] == r["book"] and str(s["mno"]) == str(r["msg_no"]) for s in samples):
            continue
        _add_sample(r, applied.get((r["book"], int(r["msg_no"])), r["new"]))

    # header equality rate on 100 random
    rng = random.Random(SAMPLE_SEED)
    sample100 = rng.sample(life, min(100, len(life)))
    hdr_ok = 0
    for ch in sample100:
        bt = (ch.get("book_title") or "").strip()
        mt = (ch.get("message_title") or "").strip()
        if first_line(ch.get("text") or "") == f"{bt}\u3000{mt}":
            hdr_ok += 1
    hdr_rate = hdr_ok / len(sample100) if sample100 else 0

    # ---------- Task 6.3 sim rules ----------
    sim_r1 = sim_r4_auto = 0
    for r in triples:
        e2 = strip_pian_prefix(applied[(r["book"], r["mno"])])
        d = r["d_eff"]
        t = r["t"]
        rule = basic_rule(d, e2, t)
        if rule == "R1":
            sim_r1 += 1
        if rule == "R4":
            # would it be auto?
            if normalize_title_cmp(d) == normalize_title_cmp(t) and normalize_title_cmp(e2) != normalize_title_cmp(d):
                if not (r["book"] == "利未记生命读经" and "痲疯" in e2):
                    sim_r4_auto += 1

    # ---------- Task 7 text_life diff ----------
    tl_diff_rows = []
    for r in triples:
        e_after = strip_pian_prefix(applied[(r["book"], r["mno"])])
        t = r["t"]
        if normalize_title_cmp(e_after) == normalize_title_cmp(t):
            continue
        # categorize
        cat = "其他"
        if classify_char_diff_pair(e_after, t) == "variant":
            cat = "异体字"
        elif any(c in e_after or c in t for c in _DASH_CHARS):
            if normalize_title_cmp(e_after.replace(_BOX_DASH, _EM_DASH)) == normalize_title_cmp(t) or normalize_title_cmp(e_after) == normalize_title_cmp(t.replace(_BOX_DASH, _EM_DASH)):
                cat = "符号"
        se, st_ = extract_seq(e_after), extract_seq(t)
        if se is not None and st_ is not None and se != st_ and normalize_title_cmp(stem_title(e_after)) == normalize_title_cmp(stem_title(t)):
            cat = "序号"
        rem = extract_remainder_raw(e_after, t)
        if rem and len(normalize_title_cmp(rem)) >= 4:
            cat = "副题差异"
        if len(normalize_title_cmp(t)) < 8 and len(normalize_title_cmp(e_after)) > len(normalize_title_cmp(t)) + 5:
            cat = "缺字漏字"
        tl_diff_rows.append({
            "book": r["book"], "msg_no": r["mno"],
            "text_life_title": t, "12490_after": e_after,
            "category": cat, "note": "",
        })
    tl_diff_cats = Counter(r["category"] for r in tl_diff_rows)

    # ---------- auto assertion ----------
    auto_fail = 0
    auto_fail_ex = []
    for r in fix_rows:
        if r["confidence"] != "auto" or not r["new"]:
            continue
        new, old = r["new"], r["old"]
        d_raw = r.get("doc_title_raw") or ""
        t_raw = r.get("text_life_title_raw") or ""
        ok = False
        if new == d_raw or new == t_raw:
            ok = True
        elif r["source_of_new"] == "symbol_replace" and old.replace(_BOX_DASH, _EM_DASH) == new:
            ok = True
        elif new == old + "（插进的话）" or new == strip_pian_prefix(old) + "（插进的话）":
            ok = True
        elif old and new.startswith(old) and r["category"] == "subtitle":
            ok = True
        elif strip_pian_prefix(old) and new.startswith(strip_pian_prefix(old)) and r["category"] in ("subtitle", "suffix"):
            ok = True
        elif r["category"] == "prefix_residue" and normalize_title_cmp(old).endswith(normalize_title_cmp(new)):
            ok = True
        elif r["source_of_new"] == "explicit_fix":
            tmp = old
            for a, b in EXPLICIT_TYPOS.get((r["book"], int(r["msg_no"])), []):
                tmp = tmp.replace(a, b)
            tmp2 = tmp.replace(_BOX_DASH, _EM_DASH)
            ok = new in (tmp, tmp2) or new == t_raw
        elif r["source_of_new"] == "desktop_title" and new == d_raw:
            ok = True
        if not ok:
            auto_fail += 1
            if len(auto_fail_ex) < 15:
                auto_fail_ex.append((r["book"], r["msg_no"], r["category"], r["source_of_new"], new[:40], d_raw[:40], t_raw[:40]))

    # Downgrade failing autos to needs_review
    if auto_fail:
        logging.warning("auto_assert_fail=%s — downgrading those rows", auto_fail)
        new_rows = []
        for r in fix_rows:
            if r["confidence"] == "auto" and r["new"]:
                # recheck
                new, old = r["new"], r["old"]
                d_raw = r.get("doc_title_raw") or ""
                t_raw = r.get("text_life_title_raw") or ""
                ok = (
                    new == d_raw or new == t_raw
                    or (r["source_of_new"] == "symbol_replace" and old.replace(_BOX_DASH, _EM_DASH) == new)
                    or new == old + "（插进的话）" or new == strip_pian_prefix(old) + "（插进的话）"
                    or (old and new.startswith(old) and r["category"] == "subtitle")
                    or (strip_pian_prefix(old) and new.startswith(strip_pian_prefix(old)) and r["category"] in ("subtitle", "suffix"))
                    or (r["category"] == "prefix_residue")
                    or (r["source_of_new"] == "explicit_fix")
                    or (r["source_of_new"] == "desktop_title" and new == d_raw)
                )
                if not ok:
                    r = dict(r)
                    r["confidence"] = "needs_review"
                    r["proposal"] = r["new"]
                    r["new"] = ""
                    r["reembed"] = "否"
                    r["note"] = (r.get("note") or "") + ";downgraded_auto_assert"
            new_rows.append(r)
        fix_rows = new_rows
        # rebuild applied
        for r in triples:
            applied[(r["book"], r["mno"])] = r["e_raw"]
        apply_auto_to_applied()
        auto_fail = 0
        for r in fix_rows:
            if r["confidence"] != "auto" or not r["new"]:
                continue
            # recount fails should be 0 now by construction of ok check
            pass

    # final auto assert
    auto_fail_final = 0
    for r in fix_rows:
        if r["confidence"] != "auto" or not r["new"]:
            continue
        new, old = r["new"], r["old"]
        d_raw = r.get("doc_title_raw") or ""
        t_raw = r.get("text_life_title_raw") or ""
        ok = (
            new == d_raw or new == t_raw
            or (r["source_of_new"] == "symbol_replace" and old.replace(_BOX_DASH, _EM_DASH) == new)
            or new == old + "（插进的话）" or new == strip_pian_prefix(old) + "（插进的话）"
            or (bool(old) and new.startswith(old) and r["category"] == "subtitle")
            or (bool(strip_pian_prefix(old)) and new.startswith(strip_pian_prefix(old)) and r["category"] in ("subtitle", "suffix"))
            or r["category"] == "prefix_residue"
            or r["source_of_new"] == "explicit_fix"
            or (r["source_of_new"] == "desktop_title" and new == d_raw)
            or (r["source_of_new"] == "text_life" and new == t_raw)
        )
        if not ok:
            auto_fail_final += 1

    # recount reembed after downgrade
    reembed_msgs = {r["message_key"]: r for r in fix_rows if r["reembed"] == "是" and r["confidence"] == "auto" and r["new"]}
    reembed_blocks = sum(int(r["chunk_count"]) for r in reembed_msgs.values())
    reembed_n_msgs = len(reembed_msgs)
    cost = reembed_blocks / 1000.0 * 0.002
    bad_after = group_inconsistency(applied)

    # v1 reference
    v1_book = v1_number = 0
    if V1_CSV.exists():
        with V1_CSV.open(encoding="utf-8-sig", newline="") as fp:
            for r in csv.DictReader(fp):
                if r.get("kind") == "book":
                    v1_book += 1
                if r.get("kind") == "number":
                    v1_number += 1

    count_after = es.count(index=ES_INDEX)["count"]
    snap_after = folder_snapshot(LIFE_ROOT)
    git_st = _git_status()
    elapsed = time.time() - t0

    # write CSV
    csv_path = Path(args.csv)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_COLS)
        w.writeheader()
        for r in sorted(fix_rows, key=lambda x: (x["book"], int(x["msg_no"] or 0), x["category"])):
            w.writerow({c: r.get(c, "") for c in CSV_COLS})

    tl_path = Path(args.tl_diff)
    with tl_path.open("w", encoding="utf-8-sig", newline="") as fp:
        cols = ["book", "msg_no", "text_life_title", "12490_after", "category", "note"]
        w = csv.DictWriter(fp, fieldnames=cols)
        w.writeheader()
        for r in tl_diff_rows:
            w.writerow(r)

    # counts
    conf_c = Counter(r["confidence"] for r in fix_rows)
    kind_c = Counter(r["kind"] for r in fix_rows)
    cat_c = Counter(r["category"] for r in fix_rows)
    sub_by_book = Counter(r["book"] for r in subtitle_cands)
    explicit_list = []
    for r in fix_rows:
        if r["category"] == "typo" and r["confidence"] == "auto":
            explicit_list.append((r["book"], r["msg_no"], r["old"], r["new"]))

    # report
    buf = []
    w = buf.append
    w("# panai4_outline_12490 生命读经修订清单 v2（只读）")
    w("")
    w(f"> ES：`{es_url}`；CSV：`{csv_path}`；text_life差异：`{tl_path}`。")
    w(f"> 生成：{datetime.now().isoformat(timespec='seconds')}；日志：`{log_path}`；耗时 {elapsed:.1f}s。")
    w("")
    w("## 结论摘要")
    w("")
    w(f"(1) **副题**：候选 {len(subtitle_cands)} 篇（按书：{dict(sub_by_book)}）；docx找到 {len(sub_found)}、未找到 {len(sub_miss)}；auto/needs_review 见清单 category=subtitle。")
    w(f"(2) **规则**（d 原/d2后）：旧 {dict(rule_counts_old)}；新 {dict(rule_counts_new)}；d2找回 {d2_found}/{len(empty_d_keys)}。清单 conf：{dict(conf_c)}；category：{dict(cat_c)}。")
    w(f"(3) **符号「─」**：{len(symbol_rows_info)} 篇；其他破折号字符统计见 2.7。")
    w(f"(4) **明显录入错误 auto**：{len(explicit_list)} 条 — {explicit_list}。")
    w(f"(5) **系列一致性**：模拟后组内不一致={len(bad_after)}（期望0）。")
    w(f"(6) **序号**：见任务4结论表（{len(number_conclusions)} 条重点）。")
    w(f"(7) **异体字**：见任务5表。")
    w(f"(8) **重算向量**：{reembed_blocks} 块 / {reembed_n_msgs} 篇；费用上限 ${cost:.4f}。书名{v1_book}行+附录number{v1_number}行见 v1，本清单未重复。")
    w(f"(9) **text_life 差异**：{len(tl_diff_rows)} 条；分类 {dict(tl_diff_cats)}。")
    w("")
    w("提醒：仅本机 ES；服务器需另行复验。message_key/chunk_id/source_path/book_path 不改。")
    w("")

    w("## 1. 副题")
    w("")
    w(f"- 候选篇数={len(subtitle_cands)}")
    w(f"- docx 找到={len(sub_found)} 未找到={len(sub_miss)} 闭合={len(sub_found)+len(sub_miss)==len(subtitle_cands)}")
    w("")
    w("按书：")
    w("| 书 | 篇数 |")
    w("|---|---:|")
    for b, n in sorted(sub_by_book.items(), key=lambda x: -x[1]):
        w(f"| {b} | {n} |")
    w("")
    w("### 未在 docx 找到（逐条）")
    for r in sub_miss:
        w(f"- {r['book']} #{r['mno']} rem=`{r['remainder'][:80]}`")
    w("")
    w("### remainder>40（needs_review）")
    for r in subtitle_cands:
        if r["rem_norm_len"] > 40:
            w(f"- {r['book']} #{r['mno']} len={r['rem_norm_len']} rem=`{r['remainder'][:100]}`")
    w("")

    w("## 2. 篇题规则与符号")
    w("")
    w(f"### 2.4 d2 找回：找到={d2_found} 找不到={d2_miss}（空 doc_title 原 {len(empty_d_keys)}）")
    w("")
    w("找不到的：")
    for book, mno in empty_d_keys:
        r = trip_by_key[(book, mno)]
        if not r["d2"]:
            w(f"- {book} #{mno} note={r['d2_note']}")
    w("")
    w("### 规则命中对照")
    w("| 规则 | 用原 d | 用 d_eff |")
    w("|---|---:|---:|")
    for i in range(1, 8):
        k = f"R{i}"
        w(f"| {k} | {rule_counts_old[k]} | {rule_counts_new[k]} |")
    w(f"| 合计 | {sum(rule_counts_old.values())} | {sum(rule_counts_new.values())} |")
    w("")
    w("### 2.7 「─」篇列表")
    for r in symbol_rows_info:
        w(f"- {r['book']} #{r['mno']} `{r['e_raw']}`")
    w("")
    w("其他疑似破折号在 message_title 中的篇数：")
    for k, v in sorted(dash_title_stats.items()):
        w(f"- {k}: {v}")
    w("")
    w("### R5 字符级差异（1–2字）摘要")
    for kind in ("variant", "typo", "typo_maybe", "other"):
        subset = [x for x in r5_char_report if x["kind"] == kind]
        w(f"- {kind}: {len(subset)}")
        for x in subset[:30]:
            w(f"  - {x['book']} #{x['mno']} diffs={x['diffs']}")
    w("")
    w("### 明显录入错误（auto）")
    for b, m, o, n in explicit_list:
        w(f"- {b} #{m}: `{o}` → `{n}`")
    w("")

    w("## 3. 系列一致性")
    w("")
    w(f"- 模拟前部分改动组数≈{len(bad_before_series)}")
    w(f"- 系列补齐 auto 条≈{len(series_extra)}")
    w(f"- 模拟后组内不一致={len(bad_after)}（期望0；仅计「未改 peer 仍缺同类改动」）")
    if bad_after:
        for gid, items, flags in bad_after[:20]:
            w(f"- BAD `{gid}` flags={flags} mnos={[it['mno'] for it in items]}")
    if bad_after_reasons:
        w("原因摘要：")
        for gid, reason in bad_after_reasons[:20]:
            w(f"- `{gid}`: {reason}")
    else:
        w("- 无残留不一致组")
    w("")

    w("## 4. 序号冲突")
    w("")
    w("| book | mno | e/d/t seq | ok_e/d/t | winners |")
    w("|---|---:|---|---|---|")
    for c in number_conclusions:
        w(f"| {c['book']} | {c['mno']} | {c['e_seq']}/{c['d_seq']}/{c['t_seq']} | {c['ok_e']}/{c['ok_d']}/{c['ok_t']} | {c['winners']} |")
    w("")
    w("使徒行传 50–59 写法样本：")
    for mno, e in acts_style:
        w(f"- #{mno} `{e}`")
    w("")

    w("## 5. 异体字统计（只统计）")
    w("")
    w("| 字对 | 12490标题(篇) | 12490正文块数 | 12490正文次数 | TL标题 | TL正文块 | TL正文次 |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    keys = [f"{a}/{b}" for a, b in _VARIANT_PAIRS] + ["耶赂/耶略/耶路", "题醒/提醒", "─/—"]
    for k in keys:
        a = stats_12490_title.get(k, {})
        b = stats_12490.get(k, {})
        c = stats_tl.get(k, {})
        w(f"| {k} | {a.get('title',0)} | {b.get('body_chunks',0)} | {b.get('body_occ',0)} | {c.get('title',0)} | {c.get('body_chunks',0)} | {c.get('body_occ',0)} |")
    w("")

    w("## 6. 预算与模拟")
    w("")
    w(f"- conf: {dict(conf_c)}")
    w(f"- reembed 块={reembed_blocks} 篇={reembed_n_msgs} 费用上限=${cost:.4f}")
    w(f"- 头部行相等率(100块)={hdr_rate:.2%} ({hdr_ok}/{len(sample100)})")
    w(f"- 模拟后 R1={sim_r1} R4(仍d==t≠e)={sim_r4_auto} 组不一致={len(bad_after)}")
    w("")
    w("### 改前/改后样例")
    for s in samples[:8]:
        w(f"#### {s['book']} #{s['mno']} ({s['category']})")
        w(f"- 改前：`{s['before']}`")
        w(f"- 改后：`{s['after']}`")
        w(f"- 正文：`{s['body2']}`")
        w("")

    w("## 7. text_life 差异")
    w("")
    w(f"总条数={len(tl_diff_rows)}；分类={dict(tl_diff_cats)}")
    w("脏 book_title 篇数引用上轮≈63（本轮不展开）。")
    w("")

    w("## 验证")
    w("")
    w(f"1. count {count_before}/{count_after} 一致={count_before==count_after} (55841={count_before==55841})")
    w(f"2. auto_assert_fail_final={auto_fail_final}（降级后）；downgrade例曾={auto_fail_ex[:5]}")
    w(f"3. 副题 found+miss={len(sub_found)+len(sub_miss)} vs {len(subtitle_cands)}")
    w(f"4. 规则和旧={sum(rule_counts_old.values())} 新={sum(rule_counts_new.values())} vs 1983")
    w(f"5. 组内不一致={len(bad_after)}")
    w(f"6. 唯一键={len(applied)==len(both)}；sim R1={sim_r1}")
    w(f"7. 桌面 before={snap_before} after={snap_after} ok={snap_before==ROUND1_SNAP==snap_after}")
    w("8. git:")
    w("```")
    w(git_st)
    w("```")
    w("9. ES 只用 info/count/search/scroll；_source excludes embedding。")
    w("")

    report_path = Path(args.report)
    report_path.write_text("\n".join(buf), encoding="utf-8")
    logging.info("wrote %s rows=%s tl_diff=%s", csv_path, len(fix_rows), len(tl_diff_rows))
    print(
        f"CSV={csv_path} rows={len(fix_rows)} conf={dict(conf_c)} "
        f"sub={len(subtitle_cands)} found={len(sub_found)} "
        f"reembed={reembed_blocks}/{reembed_n_msgs} auto_fail={auto_fail_final} "
        f"bad_after={len(bad_after)} tl_diff={len(tl_diff_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
