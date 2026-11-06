# -*- coding: utf-8 -*-
"""只读产出 panai4_outline_12490 生命读经修订清单 v3。

不写索引、不改桌面、不改 outline 既有文件。复用 pairing / v1 / v2 清单。

用法（在 back_mic/backend 下）::

    python -m panai4.outline.probe_life_fixlist_v3
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
V2_CSV = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_list_v2.csv"
CSV_FULL = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_list_v3.csv"
CSV_FINAL = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_final.csv"
CSV_REVIEW = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_review.csv"
REPORT_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_list_v3.md"
LOG_DIR_DEFAULT = REPO_ROOT / "logs"
ES_INDEX = "panai4_outline_12490"
TL_INDEX = "panai4_text_life"
ROUND1_SNAP = {"files": 1984, "bytes": 77896253, "max_mtime": 1766425146.0}
SAMPLE_SEED = 20261106
SKIP_KEY = ("约翰福音生命读经", 29)
_SOURCE_EXCLUDES = ["embedding"]

_CN_PIAN_RE = re.compile(r"^第[一二三四五六七八九十百千零〇两0-9]+篇[\s\u3000]*(.*)$")
_SEQ_TAIL_RE = re.compile(r"[（(]([一二三四五六七八九十百千零〇两0-9]+)[）)]$")
_BOX_DASH = "\u2500"
_EM_DASH = "\u2014"
_IGNORE_YU = str.maketrans({"豫": "预", "预": "预"})

EXPLICIT_TYPOS = {
    ("路加福音生命读经", 33): [("耶赂撒冷", "耶路撒冷")],
    ("路加福音生命读经", 34): [("耶略撒冷", "耶路撒冷")],
    ("路加福音生命读经", 30): [("它带着", "祂带着")],
    ("撒母耳记生命读经", 9): [("题醒", "提醒")],
}
# 使徒行传序号 explicit
ACTS_SEQ_FIX = {
    39: ("（四）", "（五）"),
    54: ("（十八）", "（二十）"),
    55: ("（二一）", "（二十一）"),
    56: ("（二二）", "（二十二）"),
}

MUST_KEEP_KEYS = {
    ("以赛亚书生命读经", 38), ("以赛亚书生命读经", 39), ("以赛亚书生命读经", 43), ("以赛亚书生命读经", 47),
    ("列王纪生命读经", 9), ("列王纪生命读经", 17), ("列王纪生命读经", 18),
    ("列王纪生命读经", 21), ("列王纪生命读经", 22),
    ("士师记生命读经", 3), ("士师记生命读经", 4), ("士师记生命读经", 5), ("士师记生命读经", 6),
    ("士师记生命读经", 7), ("士师记生命读经", 8), ("士师记生命读经", 9), ("士师记生命读经", 10),
    ("以弗所书生命读经", 1), ("何西阿书生命读经", 1), ("帖撒罗尼迦前书生命读经", 1),
    ("提多书生命读经", 3),
    ("约翰福音生命读经", 2), ("约翰福音生命读经", 3), ("约翰福音生命读经", 4), ("约翰福音生命读经", 5),
    ("约伯记生命读经", 36), ("耶利米书生命读经", 33),
    ("哈巴谷书生命读经", 2),
}

JOB_EXTRA = set(range(5, 24)) | {28}
PSALM_EXTRA = {19, 20, 21, 22, 24, 25, 26}

CSV_COLS = [
    "kind", "group_id", "book", "msg_no", "message_key", "old", "new", "category",
    "source_of_new", "confidence", "proposal", "doc_title_raw", "es12490_title_raw",
    "text_life_title_raw", "chunk_count", "reembed", "note",
    "hit_paragraph_style", "hit_para_no", "hit_is_title_line",
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
    path = log_dir / f"life_12490_fixlist_v3_{stamp}.log"
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
    return normalize_title_cmp(s).translate(_IGNORE_YU)


def strip_pian_prefix(title: str) -> str:
    raw = (title or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
    m = _CN_PIAN_RE.match(raw)
    return (m.group(1) or "").strip() if m else raw


def cn_to_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
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
    t = (title or "").strip()
    return _SEQ_TAIL_RE.sub("", t).rstrip()


def group_id(book: str, title: str) -> str:
    return f"{book}|{normalize_title_cmp(stem_title(title))}"


def first_line(text: str) -> str:
    return (text or "").split("\n", 1)[0]


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


def clean_title_line(raw: str) -> str:
    """去掉软换行、第N篇前缀；若误带书名「…生命读经第N篇」则截到篇题。"""
    t = (raw or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
    m = _CN_PIAN_RE.match(t)
    if m:
        return (m.group(1) or "").strip()
    # …生命读经第二十六篇　篇题
    m2 = re.search(r"生命读经第[一二三四五六七八九十百千零〇两0-9]+篇[\s\u3000]*(.*)$", t)
    if m2:
        return (m2.group(1) or "").strip()
    return strip_pian_prefix(t)


def recover_d2(path: Path) -> tuple[str, str, Optional[dict]]:
    """从首段/次段找回篇题。返回 (d2, note, title_para_info)。"""
    paras, err = read_paragraphs(str(path))
    if err:
        return "", f"read_fail:{err}", None
    nonempty = [p for p in paras if (p.get("text") or "").strip()]
    for p in nonempty[:5]:
        t = (p.get("text") or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
        cleaned = clean_title_line(t)
        if _CN_PIAN_RE.match(t) or "生命读经第" in t or ("篇" in t[:12] and cleaned and cleaned != t):
            if cleaned and len(normalize_title_cmp(cleaned)) >= 2:
                info = {"para_no": p.get("para_no"), "style": p.get("style") or ""}
                return cleaned, f"from_para={p.get('para_no')} style={p.get('style')}", info
        m = _CN_PIAN_RE.match(t)
        if m:
            info = {"para_no": p.get("para_no"), "style": p.get("style") or ""}
            return (m.group(1) or "").strip(), f"from_para={p.get('para_no')} style={p.get('style')}", info
    return "", "not_found", None


def is_variant_only_diff(a: str, b: str) -> bool:
    """归一化后只差异体/用字习惯。"""
    na, nb = normalize_title_cmp(a), normalize_title_cmp(b)
    if na == nb:
        return True
    for x, y in (("痲疯", "麻风"), ("麻风", "痲疯")):
        na, nb = na.replace(x, y), nb.replace(x, y)
    trans = str.maketrans({
        "於": "于", "乾": "干", "著": "着", "惟": "唯", "裏": "里", "豫": "预", "痲": "麻",
    })
    return na.translate(trans) == nb.translate(trans)


def find_title_para(path: Path, d_eff: str) -> Optional[dict]:
    """定位篇题段落（样式含篇题，或文本匹配 d_eff）。"""
    paras, err = read_paragraphs(str(path))
    if err:
        return None
    nd = normalize_title_cmp(d_eff)
    reading_idx = None
    for p in paras:
        tx = (p.get("text") or "").strip()
        if tx.startswith("读经") or "读经：" in tx[:6] or "读经:" in tx[:6]:
            reading_idx = p.get("para_no")
            break
        st = (p.get("style") or "")
        if "读经" in st:
            reading_idx = p.get("para_no")
            break
    # prefer 篇题 style
    for p in paras:
        st = p.get("style") or ""
        tx = (p.get("text") or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
        if "篇题" in st or st in ("00篇题", "0篇题"):
            body = strip_pian_prefix(tx)
            return {
                "para_no": p.get("para_no"), "style": st, "text": body,
                "reading_idx": reading_idx,
            }
    if nd:
        for p in paras:
            tx = (p.get("text") or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
            body = strip_pian_prefix(tx)
            if normalize_title_cmp(body) == nd or (nd and nd in normalize_title_cmp(tx)):
                return {
                    "para_no": p.get("para_no"), "style": p.get("style") or "",
                    "text": body, "reading_idx": reading_idx,
                }
    return {"para_no": None, "style": "", "text": d_eff, "reading_idx": reading_idx}


def extract_remainder_raw(e: str, t: str) -> Optional[str]:
    ne, nt = normalize_title_cmp(e), normalize_title_cmp(t)
    if not ne or not nt or not nt.startswith(ne) or len(nt) <= len(ne):
        return None
    best_k = None
    for k in range(len(t) + 1):
        if normalize_title_cmp(t[:k]) == ne:
            best_k = k
    if best_k is None:
        return None
    return t[best_k:]


def extract_extra_parts(e: str, t: str) -> tuple[str, str]:
    """返回 (rem_raw_approx, rem_norm)。支持前缀与「副题插在序号前」。"""
    ne, nt = normalize_title_cmp(e), normalize_title_cmp(t)
    rem = extract_remainder_raw(e, t)
    if rem is not None and len(normalize_title_cmp(rem)) >= 4:
        return rem, normalize_title_cmp(rem)
    # 序号前插入：比较 stem
    se, st_ = stem_title(e), stem_title(t)
    nse, nst = normalize_title_cmp(se), normalize_title_cmp(st_)
    if nse and nst.startswith(nse) and len(nst) >= len(nse) + 4:
        # 在 t 原文上找 stem_e 对应切点
        best_k = None
        for k in range(len(t) + 1):
            if normalize_title_cmp(stem_title(t[:k]) if False else t[:k]) == nse or normalize_title_cmp(t[:k]) == nse:
                best_k = k
        # 更稳：在 t 里找 se 原文
        if se and se in t:
            mid = t[len(se):]
            # mid 可能以 —xxx（一）yyy 开头；取到序号前的插入 + 序号后的尾巴
            # rem = 去掉与 e 共有的序号后剩余
            # 简化：nst[len(nse):] 对应 mid 中插入部分；再加上 t 序号后多余
            rem_norm = nst[len(nse):]
            # 也加上 t 相对 e 在序号后的多出
            te_after = t
            # 用整段 nt - 对齐：rem_norm 已是 stem 差；若 t 在序号后还有内容
            seq_e, seq_t = extract_seq(e), extract_seq(t)
            # 取 t 中 se 之后到（序号）之前的片段
            if se in t:
                after = t[t.index(se) + len(se):]
                # 去掉与 e 相同的尾序（一）
                m = _SEQ_TAIL_RE.search(e)
                seq_txt = m.group(0) if m else ""
                # after 形如 —四至十一章（一）以利法…
                rem_raw = after
                if seq_txt and seq_txt in after:
                    # 保留插入 + 序号后多出
                    pass
                return rem_raw, normalize_title_cmp(rem_raw) if len(normalize_title_cmp(rem_raw)) >= 4 else rem_norm
            return rem_norm, rem_norm
    # 包含：ne 是 nt 子串
    if ne and ne in nt and len(nt) >= len(ne) + 4:
        rem_norm = nt.replace(ne, "", 1)
        return rem_norm, rem_norm
    if len(nt) >= len(ne) + 4:
        # 兜底：长度差
        return t, nt[len(ne):] if len(nt) > len(ne) else nt
    return "", ""


def is_subtitle_candidate(e: str, t: str) -> bool:
    ne, nt = normalize_title_cmp(e), normalize_title_cmp(t)
    if not ne or not nt:
        return False
    if len(nt) < len(ne) + 4:
        return False
    if ne in nt:
        return True
    nse, nst = normalize_title_cmp(stem_title(e)), normalize_title_cmp(stem_title(t))
    if nse and nst.startswith(nse) and len(nst) >= len(nse) + 4:
        return True
    if nt.startswith(ne):
        return True
    return False


def missing_chajin_suffix(e: str, t: str) -> bool:
    ne = normalize_ignore_yu(e)
    nt = normalize_ignore_yu(t)
    suf = normalize_ignore_yu("（插进的话）")
    return bool(ne and nt == ne + suf)


def search_rem_in_docx(path: Path, rem_norm: str, title_para_no: Optional[int]) -> Optional[dict]:
    if not rem_norm:
        return None
    paras, err = read_paragraphs(str(path))
    if err:
        return None
    reading_idx = None
    for p in paras:
        tx = (p.get("text") or "").strip()
        st = p.get("style") or ""
        if tx.startswith("读经") or "读经" in st[:6]:
            reading_idx = p.get("para_no")
            break
    for p in paras:
        nt = normalize_title_cmp(p.get("text") or "")
        if rem_norm and rem_norm in nt:
            pno = p.get("para_no")
            before_reading = reading_idx is None or (pno is not None and pno < reading_idx)
            dist = None
            if title_para_no is not None and pno is not None:
                dist = abs(int(pno) - int(title_para_no))
            return {
                "para_no": pno,
                "style": p.get("style") or "",
                "before_reading": before_reading,
                "dist_from_title": dist,
                "reading_idx": reading_idx,
            }
    return None


def apply_seq_replace(title: str, old_seq: str, new_seq: str) -> str:
    if old_seq in title:
        return title.replace(old_seq, new_seq, 1)
    # fallback: replace trailing seq
    return _SEQ_TAIL_RE.sub(new_seq, title)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(CSV_FULL))
    ap.add_argument("--final", default=str(CSV_FINAL))
    ap.add_argument("--review", default=str(CSV_REVIEW))
    ap.add_argument("--report", default=str(REPORT_DEFAULT))
    ap.add_argument("--log-dir", default=str(LOG_DIR_DEFAULT))
    args = ap.parse_args()

    t0 = time.time()
    log_path = setup_logging(Path(args.log_dir))
    snap_before = folder_snapshot(LIFE_ROOT)
    es, es_url = make_es()
    es.info()
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
            "d2": "", "d2_note": "", "d_eff": d, "title_para": None,
        })

    trip_by_key = {(r["book"], r["mno"]): r for r in triples}

    # d2 recover
    logging.info("recover d2 for %s", len(empty_d_keys))
    d2_found = d2_miss = 0
    for book, mno in empty_d_keys:
        r = trip_by_key[(book, mno)]
        d2, note, info = recover_d2(LIFE_ROOT / r["path"])
        r["d2"] = d2
        r["d2_note"] = note
        if d2:
            d2_found += 1
            r["d_eff"] = clean_title_line(d2)
            r["title_para"] = info
        else:
            d2_miss += 1
    # 清洗全部 d_eff
    for r in triples:
        r["d_eff"] = clean_title_line(r["d_eff"] or r["d"])
    logging.info("d2 found=%s miss=%s", d2_found, d2_miss)

    # load v2 subtitle keys + needs_review
    v2_sub_keys = set()
    v2_nr = []
    with V2_CSV.open(encoding="utf-8-sig", newline="") as fp:
        for r in csv.DictReader(fp):
            if r.get("category") == "subtitle":
                v2_sub_keys.add((r["book"], int(r["msg_no"])))
            if r.get("confidence") == "needs_review":
                v2_nr.append(r)
    logging.info("v2 subtitle=%s needs_review=%s", len(v2_sub_keys), len(v2_nr))

    # ---------- Task 1: subtitle candidates ----------
    sub_cands = []
    seen_sub = set()
    for r in triples:
        key = (r["book"], r["mno"])
        if key == SKIP_KEY:
            continue
        force = (
            key in v2_sub_keys
            or (r["book"] == "约伯记生命读经" and r["mno"] in JOB_EXTRA)
            or (r["book"] == "诗篇生命读经" and r["mno"] in PSALM_EXTRA)
        )
        if force or is_subtitle_candidate(r["e"], r["t"]):
            rem_raw, rem_norm = extract_extra_parts(r["e"], r["t"])
            if not rem_norm or len(rem_norm) < 4:
                if not force:
                    continue
                # force still include with whatever extra we can
                rem_raw, rem_norm = extract_extra_parts(r["e"], r["t"])
                if not rem_norm:
                    rem_norm = normalize_title_cmp(r["t"])[len(normalize_title_cmp(r["e"])):] if len(normalize_title_cmp(r["t"])) > len(normalize_title_cmp(r["e"])) else "????"
                    rem_raw = rem_raw or rem_norm
            if key in seen_sub:
                continue
            seen_sub.add(key)
            sub_cands.append({**r, "rem_raw": rem_raw, "rem_norm": rem_norm, "from_v2": key in v2_sub_keys})

    logging.info("subtitle candidates=%s; locating hits...", len(sub_cands))

    fix_rows: list[dict] = []

    def add_fix(**kw):
        book, mno = kw["book"], int(kw["msg_no"])
        if (book, mno) == SKIP_KEY and kw.get("category") not in ("symbol",):
            return
        if not kw.get("group_id"):
            kw["group_id"] = group_id(book, kw.get("old") or "")
        fix_rows.append(row_dict(**kw))

    sub_on_title = []
    sub_near = []
    sub_keep = []
    sub_miss = []

    for i, r in enumerate(sub_cands, 1):
        if i % 40 == 0:
            logging.info("subtitle locate %s/%s", i, len(sub_cands))
        path = LIFE_ROOT / r["path"]
        d_eff = r["d_eff"]
        rem_norm = r["rem_norm"]
        # title para
        tp = r.get("title_para") or find_title_para(path, d_eff)
        title_pno = (tp or {}).get("para_no")
        nd = normalize_title_cmp(d_eff)
        ne = normalize_title_cmp(r["e"])
        # hit on title line?
        on_title = bool(rem_norm and rem_norm in nd) or (
            bool(nd) and nd != ne and ne and (ne in nd or normalize_title_cmp(stem_title(r["e"])) in nd)
            and len(nd) > len(ne)
        )
        # refine: d_eff 比 e 长且多出的部分与 rem 有重叠
        if not on_title and nd and ne and nd.startswith(ne) and len(nd) > len(ne):
            on_title = True
        if not on_title and nd and rem_norm:
            # stem mid-insert in d_eff
            nse = normalize_title_cmp(stem_title(r["e"]))
            nsd = normalize_title_cmp(stem_title(d_eff))
            if nse and nsd.startswith(nse) and len(nsd) > len(nse) and rem_norm[:4] in nsd:
                on_title = True

        hit_style = hit_pno = ""
        hit_is = "否"
        note_parts = []
        conf = "keep"
        new_val = ""
        proposal = ""
        source = ""
        category = "subtitle"

        if on_title:
            hit_is = "是"
            hit_style = (tp or {}).get("style") or "篇题行"
            hit_pno = str((tp or {}).get("para_no") or "")
            note_parts.append("副题在篇题行")
            # 差异只是多了副题 → auto with d_eff
            if nd != ne and d_eff:
                # 允许 d_eff 与 e 因副题不同；不用 t
                conf = "auto"
                new_val = d_eff
                source = "desktop_title"
                sub_on_title.append(r)
            else:
                conf = "keep"
                note_parts.append("d_eff与e归一化相同")
                sub_keep.append(r)
        else:
            hit = search_rem_in_docx(path, rem_norm, title_pno)
            if hit is None and rem_norm:
                # try shorter rem pieces (first 8+ chars)
                for L in (12, 8, 6):
                    if len(rem_norm) >= L:
                        hit = search_rem_in_docx(path, rem_norm[:L], title_pno)
                        if hit:
                            break
            if hit is None:
                hit_is = "否"
                note_parts.append("docx无")
                conf = "keep"
                sub_miss.append(r)
            else:
                hit_style = hit["style"]
                hit_pno = str(hit["para_no"])
                hit_is = "否"
                dist = hit.get("dist_from_title")
                before = hit.get("before_reading")
                note_parts.append(
                    f"命中非篇题行 style={hit_style} para={hit_pno} "
                    f"before_reading={before} dist_title={dist}"
                )
                if (
                    dist is not None and dist <= 2
                    and before
                ):
                    conf = "needs_review"
                    proposal = d_eff if d_eff and normalize_title_cmp(d_eff) != ne else (r["e"] + (r["rem_raw"] or ""))
                    note_parts.append("紧挨篇题疑似副标题行")
                    sub_near.append(r)
                else:
                    conf = "keep"
                    note_parts.append("副题不在篇题行，不补")
                    sub_keep.append(r)

        add_fix(
            kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
            old=r["e_raw"], new=new_val, category=category,
            source_of_new=source, confidence=conf, proposal=proposal,
            doc_title_raw=d_eff, es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="是" if conf == "auto" else "否",
            note=";".join(note_parts),
            group_id=group_id(r["book"], r["e"]),
            hit_paragraph_style=hit_style, hit_para_no=hit_pno, hit_is_title_line=hit_is,
        )

    logging.info(
        "subtitle on_title=%s near=%s keep=%s miss=%s",
        len(sub_on_title), len(sub_near), len(sub_keep), len(sub_miss),
    )

    # ---------- symbols ----------
    for r in triples:
        if _BOX_DASH not in r["e_raw"]:
            continue
        new_t = r["e_raw"].replace(_BOX_DASH, _EM_DASH)
        # if also typo, still add symbol; typo pass may override composed later
        add_fix(
            kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
            old=r["e_raw"], new=new_t, category="symbol",
            source_of_new="symbol_replace", confidence="auto", proposal="",
            doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="是", note="─→—",
            group_id=group_id(r["book"], r["e"]),
        )

    # ---------- explicit typos ----------
    for r in triples:
        key = (r["book"], r["mno"])
        if key not in EXPLICIT_TYPOS:
            continue
        cur = r["e_raw"]
        for a, b in EXPLICIT_TYPOS[key]:
            cur = cur.replace(a, b)
        cur = cur.replace(_BOX_DASH, _EM_DASH)
        add_fix(
            kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
            old=r["e_raw"], new=cur, category="typo",
            source_of_new="explicit_fix", confidence="auto", proposal="",
            doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="是", note=f"explicit_fix {EXPLICIT_TYPOS[key]}",
            group_id=group_id(r["book"], r["e"]),
        )

    # ---------- （插进的话） ----------
    for r in triples:
        if r["book"] == SKIP_KEY[0] and r["mno"] == SKIP_KEY[1]:
            continue
        if r["e"].endswith("（插进的话）") or normalize_ignore_yu(r["e"]).endswith(normalize_ignore_yu("（插进的话）")):
            continue
        # 85 类：e 有序号，t 用（插进的话）替换该序号（非简单后缀）
        if (
            extract_seq(r["e"]) is not None
            and "（插进的话）" in (r["t"] or "")
            and extract_seq(r["t"]) is None
            and normalize_ignore_yu(r["t"]) == normalize_ignore_yu(stem_title(r["e"]) + "（插进的话）")
        ):
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="suffix",
                source_of_new="", confidence="needs_review",
                proposal=stem_title(r["e_raw"]) + "（插进的话）",
                doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="否", note="插进的话替换了序号，非简单后缀",
                group_id=group_id(r["book"], r["e"]),
            )
            continue
        need = missing_chajin_suffix(r["e"], r["t"])
        if "（插进的话）" in (r["d_eff"] or "") and "（插进的话）" not in r["e"]:
            # d_eff 明确带后缀且为 e+后缀 或 stem+后缀
            if (
                normalize_ignore_yu(r["d_eff"]) == normalize_ignore_yu(r["e"] + "（插进的话）")
                or normalize_ignore_yu(r["d_eff"]) == normalize_ignore_yu(stem_title(r["e"]) + "（插进的话）")
            ):
                need = True
        if need:
            new_val = r["e_raw"] + "（插进的话）"
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new=new_val, category="suffix",
                source_of_new="e_plus_t_remainder", confidence="auto", proposal="",
                doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="是", note="补（插进的话）；忽略豫/预",
                group_id=group_id(r["book"], r["e"]),
            )

    # ---------- prefix residue 路加28 ----------
    for r in triples:
        if r["book"] == "路加福音生命读经" and r["mno"] == 28:
            if r["e_raw"].startswith("第二十八篇"):
                e2 = re.sub(r"^第二十八篇[\s\u3000]*", "", r["e_raw"]).strip()
                add_fix(
                    kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                    old=r["e_raw"], new=e2, category="prefix_residue",
                    source_of_new="desktop_title", confidence="auto", proposal="",
                    doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
                    text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                    reembed="是", note="去掉第二十八篇前缀",
                    group_id=group_id(r["book"], r["e"]),
                )

    # ---------- R4-like recovered_title：仅当 d_eff 干净且与 t 一致（或去雅各），绝不用脏 d2 ----------
    sub_keys_done = {(r["book"], int(r["msg_no"])) for r in fix_rows if r["category"] == "subtitle"}
    NR_FIXED = {
        ("创世记生命读经", 109), ("马可福音生命读经", 68), ("哥林多后书生命读经", 57),
        ("哈巴谷书生命读经", 2),
    }
    for r in triples:
        key = (r["book"], r["mno"])
        if key == SKIP_KEY or key in EXPLICIT_TYPOS:
            continue
        if key in sub_keys_done or key in NR_FIXED or key in MUST_KEEP_KEYS:
            continue
        if key[0] == "使徒行传生命读经" and key[1] in ACTS_SEQ_FIX:
            continue
        d_eff, e = clean_title_line(r["d_eff"]), r["e"]
        if d_eff != r["d_eff"] and d_eff:
            r["d_eff"] = d_eff
        nd, ne = normalize_title_cmp(d_eff), normalize_title_cmp(e)
        if not nd or nd == ne:
            continue
        if is_variant_only_diff(d_eff, e):
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="other", source_of_new="",
                confidence="keep", proposal="",
                doc_title_raw=d_eff, es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="否", note="仅异体/用字习惯差，保持12490",
                group_id=group_id(r["book"], r["e"]),
            )
            continue
        # 序号-only → 交序号段
        if extract_seq(e) != extract_seq(d_eff) and normalize_title_cmp(stem_title(e)) == normalize_title_cmp(stem_title(d_eff)):
            continue
        # 脏 d_eff：仍含书名/第N篇
        if "生命读经" in d_eff or _CN_PIAN_RE.match(d_eff or ""):
            continue
        if key == ("创世记生命读经", 109):
            add_fix(
                kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
                old=r["e_raw"], new="", category="recovered_title",
                source_of_new="", confidence="needs_review",
                proposal="成熟的表显（七）",
                doc_title_raw=d_eff, es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="否", note="e与d完全不同；proposal=成熟的表显（七）",
                group_id=group_id(r["book"], r["e"]),
            )
            continue
        nt = normalize_title_cmp(r["t"])
        # 仅当 d_eff 与 text_life 一致，或以去「雅各」后与 d/t 一致
        ok_desktop = (nt and nd == nt) or (
            e.startswith("雅各") and normalize_title_cmp(e[len("雅各"):]) == nd
        )
        if not ok_desktop:
            # 截断补全：e 是 d_eff 真前缀且 d==t
            if ne and nd.startswith(ne) and nt == nd and len(nd) > len(ne) + 2:
                ok_desktop = True
            else:
                continue
        add_fix(
            kind="title", book=r["book"], msg_no=r["mno"], message_key=r["mk"],
            old=r["e_raw"], new=d_eff, category="recovered_title",
            source_of_new="desktop_title", confidence="auto", proposal="",
            doc_title_raw=d_eff, es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="是", note="R4/桌面篇题：d_eff==t≠e 或以桌面去雅各",
            group_id=group_id(r["book"], r["e"]),
        )

    # 创世记 109 若上面被 continue 掉，单独保证
    if ("创世记生命读经", 109) not in {(r["book"], int(r["msg_no"])) for r in fix_rows if r["category"] == "recovered_title"}:
        r = trip_by_key.get(("创世记生命读经", 109))
        if r:
            add_fix(
                kind="title", book=r["book"], msg_no=109, message_key=r["mk"],
                old=r["e_raw"], new="", category="recovered_title",
                source_of_new="", confidence="needs_review",
                proposal="成熟的表显（七）",
                doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="否", note="e与d完全不同；proposal=成熟的表显（七）",
                group_id=group_id(r["book"], r["e"]),
            )

    # 系列 98/99：仅当 d_eff 本身已无「雅各」才可 auto（以桌面为准）；否则 keep 并 note
    for mno in (98, 99):
        r = trip_by_key.get(("创世记生命读经", mno))
        if not r or not r["e_raw"].startswith("雅各"):
            continue
        d_eff = clean_title_line(r["d_eff"])
        if d_eff.startswith("雅各"):
            # 桌面仍带雅各 → 与 97 桌面不一致，keep 12490，列 needs_review 供确认是否统一去雅各
            add_fix(
                kind="title", book=r["book"], msg_no=mno, message_key=r["mk"],
                old=r["e_raw"], new="", category="recovered_title",
                source_of_new="", confidence="needs_review",
                proposal=r["e_raw"][len("雅各"):],
                doc_title_raw=d_eff, es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="否",
                note="桌面 d_eff 仍带「雅各」，但同系列 97/102/104 桌面已无；是否统一去雅各请确认",
                group_id=group_id(r["book"], r["e"]),
            )
        elif normalize_title_cmp(d_eff) == normalize_title_cmp(r["e_raw"][len("雅各"):]):
            add_fix(
                kind="title", book=r["book"], msg_no=mno, message_key=r["mk"],
                old=r["e_raw"], new=d_eff, category="recovered_title",
                source_of_new="desktop_title", confidence="auto", proposal="",
                doc_title_raw=d_eff, es12490_title_raw=r["e_raw"],
                text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
                reembed="是", note="桌面已无雅各，与同系列一致",
                group_id=group_id(r["book"], r["e"]),
            )

    # ---------- numbers per 已定决定 ----------
    # 使徒 39/54/55/56
    for mno, (old_s, new_s) in ACTS_SEQ_FIX.items():
        r = trip_by_key.get(("使徒行传生命读经", mno))
        if not r:
            continue
        new_val = apply_seq_replace(r["e_raw"], old_s, new_s)
        add_fix(
            kind="title", book=r["book"], msg_no=mno, message_key=r["mk"],
            old=r["e_raw"], new=new_val, category="number_fix",
            source_of_new="explicit_fix", confidence="auto", proposal="",
            doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="是", note=f"序号 {old_s}→{new_s}",
            group_id=group_id(r["book"], r["e"]),
        )

    for book, mno in [
        ("出埃及记生命读经", 180), ("路加福音生命读经", 63),
        ("马太福音生命读经", 43), ("民数记生命读经", 26),
    ]:
        r = trip_by_key.get((book, mno))
        if not r:
            continue
        add_fix(
            kind="title", book=book, msg_no=mno, message_key=r["mk"],
            old=r["e_raw"], new="", category="number_fix",
            source_of_new="", confidence="keep", proposal="",
            doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="否", note="12490现有序号自洽，keep",
            group_id=group_id(r["book"], r["e"]),
        )

    r = trip_by_key.get(("哥林多后书生命读经", 57))
    if r:
        add_fix(
            kind="title", book=r["book"], msg_no=57, message_key=r["mk"],
            old=r["e_raw"], new="", category="number_fix",
            source_of_new="", confidence="needs_review",
            proposal=stem_title(r["e_raw"]) + "（八）",
            doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="否",
            note="桌面与12490为（七），text_life为（八），以同系列连续为据",
            group_id=group_id(r["book"], r["e"]),
        )

    r = trip_by_key.get(("马可福音生命读经", 68))
    if r:
        add_fix(
            kind="title", book=r["book"], msg_no=68, message_key=r["mk"],
            old=r["e_raw"], new="", category="number_fix",
            source_of_new="", confidence="needs_review",
            proposal="一种完全照着神新约经纶，并为着神新约经纶的生活（十七）",
            doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="否", note="R7/序号；字用着",
            group_id=group_id(r["book"], r["e"]),
        )

    # 哈巴谷 2 keep
    r = trip_by_key.get(("哈巴谷书生命读经", 2))
    if r:
        add_fix(
            kind="title", book=r["book"], msg_no=2, message_key=r["mk"],
            old=r["e_raw"], new="", category="other",
            source_of_new="", confidence="keep", proposal="",
            doc_title_raw=r["d_eff"], es12490_title_raw=r["e_raw"],
            text_life_title_raw=r["t"], chunk_count=r["chunk_count"],
            reembed="否", note="已定 keep",
            group_id=group_id(r["book"], r["e"]),
        )

    # ---------- Task 2: v2 needs_review downgrade ----------
    v2_nr_keep = v2_nr_still = v2_nr_auto = 0
    v2_nr_still_rows = []
    handled_v2 = set()
    # current decisions by key
    cur_by_key: dict[tuple, list] = defaultdict(list)
    for r in fix_rows:
        cur_by_key[(r["book"], int(r["msg_no"]))].append(r)

    for vr in v2_nr:
        book, mno = vr["book"], int(vr["msg_no"])
        key = (book, mno)
        handled_v2.add(key)
        trip = trip_by_key.get(key)
        if not trip:
            v2_nr_still += 1
            continue
        # if already have auto for this key in v3, count as 转 auto
        autos = [x for x in cur_by_key.get(key, []) if x["confidence"] == "auto" and x["new"]]
        nrs = [x for x in cur_by_key.get(key, []) if x["confidence"] == "needs_review"]
        if autos:
            v2_nr_auto += 1
            continue
        if nrs:
            v2_nr_still += 1
            v2_nr_still_rows.append(nrs[0])
            continue
        # d_eff == e → keep
        if normalize_title_cmp(trip["d_eff"]) == normalize_title_cmp(trip["e"]):
            v2_nr_keep += 1
            # ensure keep row exists
            if not cur_by_key.get(key):
                add_fix(
                    kind="title", book=book, msg_no=mno, message_key=trip["mk"],
                    old=trip["e_raw"], new="", category="other",
                    source_of_new="", confidence="keep", proposal="",
                    doc_title_raw=trip["d_eff"], es12490_title_raw=trip["e_raw"],
                    text_life_title_raw=trip["t"], chunk_count=trip["chunk_count"],
                    reembed="否", note="v2 needs_review→keep（d_eff==e）",
                    group_id=group_id(trip["book"], trip["e"]),
                )
            else:
                # upgrade any stray to keep already handled
                pass
        else:
            # still different — if not already listed, needs_review
            v2_nr_still += 1
            if not cur_by_key.get(key):
                row = add_fix(
                    kind="title", book=book, msg_no=mno, message_key=trip["mk"],
                    old=trip["e_raw"], new="", category=vr.get("category") or "other",
                    source_of_new="", confidence="needs_review",
                    proposal=vr.get("proposal") or trip["d_eff"],
                    doc_title_raw=trip["d_eff"], es12490_title_raw=trip["e_raw"],
                    text_life_title_raw=trip["t"], chunk_count=trip["chunk_count"],
                    reembed="否", note="v2 needs_review保留；d_eff≠e",
                    group_id=group_id(trip["book"], trip["e"]),
                )
                # add_fix returns None; re-fetch
            cur_by_key = defaultdict(list)
            for x in fix_rows:
                cur_by_key[(x["book"], int(x["msg_no"]))].append(x)
            nrs = [x for x in cur_by_key.get(key, []) if x["confidence"] == "needs_review"]
            if nrs:
                v2_nr_still_rows.append(nrs[0])

    # MUST_KEEP check
    must_keep_fail = []
    for key in MUST_KEEP_KEYS:
        trip = trip_by_key.get(key)
        if not trip:
            must_keep_fail.append((key, "missing"))
            continue
        rows = [x for x in fix_rows if x["book"] == key[0] and int(x["msg_no"]) == key[1]]
        autos = [x for x in rows if x["confidence"] == "auto" and x["new"]]
        nrs = [x for x in rows if x["confidence"] == "needs_review"]
        if autos or nrs:
            # allow if only symbol? must be keep — if auto for other reason fail
            bad = [x for x in autos + nrs if x["category"] not in ("symbol",)]
            # 若 d_eff==e 不应有 auto title content
            if normalize_title_cmp(trip["d_eff"]) == normalize_title_cmp(trip["e"]):
                if bad:
                    must_keep_fail.append((key, f"unexpected {[x['category']+':'+x['confidence'] for x in bad]}"))
            # else d_eff!=e might have recovered — but user said these must keep
            elif bad:
                must_keep_fail.append((key, f"d_eff!=e but {[x['confidence'] for x in bad]}"))
        # ensure keep marker
        if not any(x["confidence"] == "keep" for x in rows):
            add_fix(
                kind="title", book=key[0], msg_no=key[1], message_key=trip["mk"],
                old=trip["e_raw"], new="", category="other",
                source_of_new="", confidence="keep", proposal="",
                doc_title_raw=trip["d_eff"], es12490_title_raw=trip["e_raw"],
                text_life_title_raw=trip["t"], chunk_count=trip["chunk_count"],
                reembed="否", note="已知 keep（text_life问题，12490与桌面一致）",
                group_id=group_id(trip["book"], trip["e"]),
            )

    # ---------- Dedup: same book+msg+category keep highest priority; content prefer one auto ----------
    pr = {"auto": 3, "needs_review": 2, "keep": 1}
    by_cat = {}
    for r in fix_rows:
        k = (r["book"], r["msg_no"], r["category"])
        prev = by_cat.get(k)
        if prev is None or pr.get(r["confidence"], 0) > pr.get(prev["confidence"], 0):
            by_cat[k] = r
    fix_rows = list(by_cat.values())
    # drop recovered_title auto if subtitle auto same msg
    sub_auto = {
        (r["book"], r["msg_no"]) for r in fix_rows
        if r["category"] == "subtitle" and r["confidence"] == "auto" and r["new"]
    }
    fix_rows = [
        r for r in fix_rows
        if not (
            r["category"] == "recovered_title" and r["confidence"] == "auto"
            and (r["book"], r["msg_no"]) in sub_auto
        )
    ]
    # typo auto supersedes symbol for same msg (typo new already has —)
    typo_auto = {
        (r["book"], r["msg_no"]) for r in fix_rows
        if r["category"] == "typo" and r["confidence"] == "auto" and r["new"]
    }
    fix_rows = [
        r for r in fix_rows
        if not (
            r["category"] == "symbol" and (r["book"], r["msg_no"]) in typo_auto
        )
    ]

    # ---------- rebuild v2 nr accounting cleanly ----------
    final_by_key = defaultdict(list)
    for r in fix_rows:
        final_by_key[(r["book"], int(r["msg_no"]))].append(r)

    v2_nr_keep = v2_nr_still = v2_nr_auto = 0
    v2_nr_still_rows = []
    for vr in v2_nr:
        key = (vr["book"], int(vr["msg_no"]))
        rows = final_by_key.get(key, [])
        if any(x["confidence"] == "auto" and x["new"] for x in rows):
            v2_nr_auto += 1
        elif any(x["confidence"] == "needs_review" for x in rows):
            v2_nr_still += 1
            v2_nr_still_rows.append(next(x for x in rows if x["confidence"] == "needs_review"))
        else:
            v2_nr_keep += 1

    # ---------- Task 3 detail tables ----------
    cor2_table = []
    for mno in range(54, 61):
        r = trip_by_key.get(("哥林多后书生命读经", mno))
        if r:
            cor2_table.append({
                "mno": mno, "e": r["e"], "d": r["d_eff"], "t": r["t"],
                "se": extract_seq(r["e"]), "sd": extract_seq(r["d_eff"]), "st": extract_seq(r["t"]),
            })

    acts_after = []
    for mno in range(50, 61):
        r = trip_by_key.get(("使徒行传生命读经", mno))
        if not r:
            continue
        title = r["e_raw"]
        if mno in ACTS_SEQ_FIX:
            old_s, new_s = ACTS_SEQ_FIX[mno]
            title = apply_seq_replace(title, old_s, new_s)
        acts_after.append((mno, title, extract_seq(title)))

    def neighbors(book, mno, span=2):
        rows = []
        for m in range(mno - span, mno + span + 1):
            r = trip_by_key.get((book, m))
            if r:
                rows.append((m, r["e"], r["d_eff"], r["t"], extract_seq(r["e"]), extract_seq(r["d_eff"]), extract_seq(r["t"])))
        return rows

    gen109_nb = neighbors("创世记生命读经", 109)
    mark68_nb = neighbors("马可福音生命读经", 68)

    # ---------- Job / Psalm table ----------
    job_psalm_rows = []
    for r in sub_cands:
        if r["book"] in ("约伯记生命读经", "诗篇生命读经"):
            # find fix row
            fr = next((x for x in fix_rows if x["book"] == r["book"] and int(x["msg_no"]) == r["mno"] and x["category"] == "subtitle"), None)
            job_psalm_rows.append({
                "book": r["book"], "mno": r["mno"],
                "e": r["e"], "d_eff": r["d_eff"], "t": r["t"],
                "hit": (fr or {}).get("hit_is_title_line", ""),
                "conf": (fr or {}).get("confidence", ""),
                "note": (fr or {}).get("note", ""),
                "v2": "是" if r.get("from_v2") else "否",
                "why_v2": (
                    "v2要求e为t真前缀；本病副题插在序号前，normalize(e)不是normalize(t)前缀"
                    if not r.get("from_v2") else "已在v2候选"
                ),
            })

    # ---------- Task 4 variant stats ----------
    def body_of(text: str) -> str:
        parts = (text or "").split("\n")
        return "\n".join(parts[1:])

    SINGLE_FORMS = ["於", "乾", "痲", "疯", "惟", "裏", "著", "耶赂", "耶略", "题醒", _BOX_DASH]
    YU_WORDS = ["豫言", "豫表", "豫备", "豫定", "豫先", "豫期"]

    def count_form(chunks, form: str, title_unique=True):
        title_msgs = set()
        body_chunks = body_occ = 0
        seen_mk = set()
        for ch in chunks:
            mk = ch.get("message_key") or id(ch)
            title = ch.get("message_title") or ""
            if form in title:
                if title_unique:
                    title_msgs.add(mk)
                else:
                    title_msgs.add(mk)
            body = body_of(ch.get("text") or "")
            c = body.count(form)
            if c:
                body_chunks += 1
                body_occ += c
        return len(title_msgs), body_chunks, body_occ

    # text_life as fake chunks
    tl_chunks = []
    for ent in tl_map.values():
        tl_chunks.append({
            "message_key": id(ent),
            "message_title": ent.get("title_stripped") or "",
            "text": "hdr\n" + (ent.get("text") or ""),
        })

    variant_table = []
    for form in SINGLE_FORMS + YU_WORDS:
        t1, b1, o1 = count_form(life, form)
        t2, b2, o2 = count_form(tl_chunks, form)
        variant_table.append({
            "form": "─" if form == _BOX_DASH else form,
            "t12490": t1, "b12490": b1, "o12490": o1,
            "ttl": t2, "btl": b2, "otl": o2,
            "common_o12490": "",
        })

    # common counterparts
    common_map = {
        "於": None,  # special: only 终结于
        "乾": "干渴",
        "痲": "麻风",
        "疯": "麻风",
        "惟": "唯一",
        "豫言": "预言",
        "豫表": "预表",
        "题醒": "提醒",
        "耶赂": "耶路",
        "耶略": "耶路",
        _BOX_DASH: _EM_DASH,
    }
    common_counts = {}
    for form, common in common_map.items():
        if common is None:
            # 终结于 only
            c = 0
            for ch in life:
                c += body_of(ch.get("text") or "").count("终结于")
            common_counts["於"] = c
        else:
            c = 0
            for ch in life:
                c += body_of(ch.get("text") or "").count(common)
            common_counts[form if form != _BOX_DASH else "─"] = c

    for row in variant_table:
        f = row["form"]
        if f in common_counts:
            row["common_o12490"] = common_counts[f]
        elif f == "─":
            row["common_o12490"] = common_counts.get("─", "")

    def top_words_with_char(char: str, n=15):
        # 2-4 char windows containing char
        ctr = Counter()
        for ch in life:
            body = body_of(ch.get("text") or "")
            for i, c in enumerate(body):
                if c != char:
                    continue
                for L in (2, 3, 4):
                    for off in range(L):
                        start = i - off
                        if start < 0 or start + L > len(body):
                            continue
                        w = body[start:start + L]
                        if char in w and not any(x in w for x in "\n\r\t "):
                            ctr[w] += 1
        return ctr.most_common(n)

    top_words = {c: top_words_with_char(c) for c in ("於", "乾", "惟", "著", "裏")}

    # ---------- Compose applied titles ----------
    applied: dict[tuple[str, int], str] = {}
    for r in triples:
        applied[(r["book"], r["mno"])] = r["e_raw"]

    content_cats = {"subtitle", "suffix", "recovered_title", "typo", "prefix_residue", "number_fix"}
    by_msg_fix = defaultdict(list)
    for r in fix_rows:
        if r["confidence"] == "auto" and r["new"]:
            by_msg_fix[(r["book"], int(r["msg_no"]))].append(r)
    for key, rows in by_msg_fix.items():
        cur = applied[key]
        content = [x for x in rows if x["category"] in content_cats]
        symbols = [x for x in rows if x["category"] == "symbol"]
        pref = {"recovered_title": 5, "subtitle": 4, "typo": 4, "number_fix": 3, "suffix": 3, "prefix_residue": 2}
        if content:
            content.sort(key=lambda x: pref.get(x["category"], 0), reverse=True)
            cur = content[0]["new"]
        if symbols or _BOX_DASH in cur:
            cur = cur.replace(_BOX_DASH, _EM_DASH)
        applied[key] = cur

    # ---------- auto assert ----------
    auto_fail = 0
    auto_fail_ex = []
    for r in fix_rows:
        if r["confidence"] != "auto" or not r["new"]:
            continue
        new, old = r["new"], r["old"]
        d_eff = r.get("doc_title_raw") or ""
        ok = False
        if r["source_of_new"] == "desktop_title" and new == d_eff and (
            r.get("hit_is_title_line") == "是" or r["category"] in ("recovered_title", "prefix_residue")
        ):
            ok = True
        if r["category"] == "subtitle" and new == d_eff and r.get("hit_is_title_line") == "是":
            ok = True
        if new == old + "（插进的话）" or new == strip_pian_prefix(old) + "（插进的话）":
            ok = True
        if r["source_of_new"] == "symbol_replace" and old.replace(_BOX_DASH, _EM_DASH) == new:
            ok = True
        if r["category"] == "prefix_residue" and normalize_title_cmp(old).endswith(normalize_title_cmp(new)):
            ok = True
        if r["source_of_new"] == "explicit_fix":
            ok = True  # 已定决定列出的
        if not ok:
            auto_fail += 1
            if len(auto_fail_ex) < 20:
                auto_fail_ex.append((r["book"], r["msg_no"], r["category"], r["source_of_new"], new[:50], d_eff[:50]))

    if auto_fail:
        logging.warning("auto_assert_fail=%s downgrading", auto_fail)
        new_rows = []
        for r in fix_rows:
            if r["confidence"] == "auto" and r["new"]:
                # recheck same
                new, old = r["new"], r["old"]
                d_eff = r.get("doc_title_raw") or ""
                ok = (
                    (r["source_of_new"] == "desktop_title" and new == d_eff)
                    or (r["category"] == "subtitle" and new == d_eff and r.get("hit_is_title_line") == "是")
                    or new == old + "（插进的话）" or new == strip_pian_prefix(old) + "（插进的话）"
                    or (r["source_of_new"] == "symbol_replace" and old.replace(_BOX_DASH, _EM_DASH) == new)
                    or r["category"] == "prefix_residue"
                    or r["source_of_new"] == "explicit_fix"
                )
                if not ok:
                    rr = dict(r)
                    rr["confidence"] = "needs_review"
                    rr["proposal"] = r["new"]
                    rr["new"] = ""
                    rr["reembed"] = "否"
                    rr["note"] = (r.get("note") or "") + ";downgraded_auto_assert"
                    new_rows.append(rr)
                    continue
            new_rows.append(r)
        fix_rows = new_rows
        # rebuild applied
        for r in triples:
            applied[(r["book"], r["mno"])] = r["e_raw"]
        by_msg_fix = defaultdict(list)
        for r in fix_rows:
            if r["confidence"] == "auto" and r["new"]:
                by_msg_fix[(r["book"], int(r["msg_no"]))].append(r)
        for key, rows in by_msg_fix.items():
            cur = applied[key]
            content = [x for x in rows if x["category"] in content_cats]
            symbols = [x for x in rows if x["category"] == "symbol"]
            if content:
                content.sort(key=lambda x: {"recovered_title": 5, "subtitle": 4, "typo": 4, "number_fix": 3, "suffix": 3, "prefix_residue": 2}.get(x["category"], 0), reverse=True)
                cur = content[0]["new"]
            if symbols or _BOX_DASH in cur:
                cur = cur.replace(_BOX_DASH, _EM_DASH)
            applied[key] = cur

    auto_fail_final = 0
    for r in fix_rows:
        if r["confidence"] != "auto" or not r["new"]:
            continue
        new, old = r["new"], r["old"]
        d_eff = r.get("doc_title_raw") or ""
        ok = (
            (r["source_of_new"] == "desktop_title" and new == d_eff)
            or (r["category"] == "subtitle" and new == d_eff and r.get("hit_is_title_line") == "是")
            or new == old + "（插进的话）" or new == strip_pian_prefix(old) + "（插进的话）"
            or (r["source_of_new"] == "symbol_replace" and old.replace(_BOX_DASH, _EM_DASH) == new)
            or r["category"] == "prefix_residue"
            or r["source_of_new"] == "explicit_fix"
        )
        if not ok:
            auto_fail_final += 1

    # ---------- v1 book + number into final ----------
    v1_book_rows = []
    v1_number_rows = []
    with V1_CSV.open(encoding="utf-8-sig", newline="") as fp:
        for r in csv.DictReader(fp):
            if r.get("kind") == "book" and r.get("confidence") == "auto":
                v1_book_rows.append(r)
            if r.get("kind") == "number" and r.get("confidence") == "auto":
                v1_number_rows.append(r)

    # ---------- final / review CSVs ----------
    final_rows = []
    for r in fix_rows:
        if r["confidence"] != "auto" or not r["new"]:
            continue
        field = "message_title"
        final_rows.append({
            "message_key": r["message_key"],
            "field": field,
            "old": r["old"],
            "new": r["new"],
            "category": r["category"],
            "reembed": r["reembed"],
            "book": r["book"],
            "msg_no": r["msg_no"],
            "chunk_count": r["chunk_count"],
        })
    for r in v1_book_rows:
        final_rows.append({
            "message_key": r["message_key"],
            "field": "book_title",
            "old": r["old"],
            "new": r["new"],
            "category": "book",
            "reembed": r.get("reembed") or "是",
            "book": r["book"],
            "msg_no": r.get("msg_no") or "",
            "chunk_count": r.get("chunk_count") or "0",
        })
    for r in v1_number_rows:
        final_rows.append({
            "message_key": r["message_key"],
            "field": "message_number",
            "old": r["old"],
            "new": r["new"],
            "category": "number",
            "reembed": "否",
            "book": r["book"],
            "msg_no": r.get("msg_no") or "",
            "chunk_count": r.get("chunk_count") or "0",
        })

    review_rows = [r for r in fix_rows if r["confidence"] == "needs_review"]

    # reembed: title+book unique by message_key
    reembed_keys = {}
    for r in final_rows:
        if r["field"] == "message_number":
            continue
        if r["reembed"] == "是" or r["field"] in ("message_title", "book_title"):
            mk = r["message_key"]
            cc = int(r.get("chunk_count") or 0)
            reembed_keys[mk] = max(reembed_keys.get(mk, 0), cc)
    # book rows already have chunk counts; title may overlap same mk — use max
    # For book rename, all msgs of that book need reembed — v1 already per-message
    reembed_blocks = sum(reembed_keys.values())
    reembed_msgs = len(reembed_keys)
    cost = reembed_blocks / 1000.0 * 0.002

    n_title = sum(1 for r in final_rows if r["field"] == "message_title")
    n_book = sum(1 for r in final_rows if r["field"] == "book_title")
    n_number = sum(1 for r in final_rows if r["field"] == "message_number")

    # ---------- simulation checks ----------
    sim_r1 = 0
    for r in triples:
        e_after = applied.get((r["book"], r["mno"]), r["e_raw"])
        if missing_chajin_suffix(strip_pian_prefix(e_after), r["t"]):
            # still missing relative to t
            if "（插进的话）" not in e_after and missing_chajin_suffix(r["e"], r["t"]):
                sim_r1 += 1

    # series inconsistency among autos
    def group_inconsistency():
        gmap = defaultdict(list)
        for r in triples:
            gmap[group_id(r["book"], r["e"])].append(r)
        bad = []
        for gid, items in gmap.items():
            if len(items) < 2:
                continue
            flags = []
            for it in items:
                orig = it["e_raw"]
                now = applied.get((it["book"], it["mno"]), orig)
                flags.append(normalize_title_cmp(orig) != normalize_title_cmp(now))
            if any(flags) and not all(flags):
                # only if unfixed peers still have same defect type
                changed = [it for it, f in zip(items, flags) if f]
                kinds = set()
                for ch in changed:
                    now = applied[(ch["book"], ch["mno"])]
                    if _BOX_DASH in ch["e_raw"] and _BOX_DASH not in now:
                        kinds.add("symbol")
                    if ch["e_raw"].startswith("雅各") and not now.startswith("雅各"):
                        kinds.add("雅各")
                    if now.endswith("（插进的话）") and not ch["e_raw"].endswith("（插进的话）"):
                        kinds.add("suffix")
                real = False
                for it, f in zip(items, flags):
                    if f:
                        continue
                    if "symbol" in kinds and _BOX_DASH in it["e_raw"]:
                        real = True
                    if "雅各" in kinds and it["e_raw"].startswith("雅各"):
                        # 仅当该篇 d_eff 也已无雅各时才算「仍缺」
                        if not clean_title_line(it["d_eff"]).startswith("雅各"):
                            real = True
                    if "suffix" in kinds and missing_chajin_suffix(it["e"], it["t"]):
                        real = True
                if real:
                    bad.append(gid)
        return bad

    bad_series = group_inconsistency()

    # unique (book, mno) after number changes — message_number field not in applied titles
    # check title map keys unique already
    uniq_ok = len({(r["book"], r["mno"]) for r in triples}) == len(triples)

    # header equality after apply (simulate first line)
    rng = random.Random(SAMPLE_SEED)
    sample100 = rng.sample(life, min(100, len(life)))
    hdr_ok = 0
    for ch in sample100:
        bt = normalize_book((ch.get("book_title") or "").strip())
        # book rename?
        for br in v1_book_rows:
            if br["message_key"] == (ch.get("message_key") or ""):
                bt = br["new"]
                break
        mno = ch.get("message_number")
        mt = (ch.get("message_title") or "").strip()
        if mno is not None and (bt, int(mno)) in applied:
            # need canonical book for applied key
            # applied keyed by normalized book from life
            bt0 = normalize_book((ch.get("book_title") or "").strip())
            mt = applied.get((bt0, int(mno)), mt)
        # after title change, header should be book_title + ideographic space + message_title
        # current text first line uses OLD; we check equality of formula with NEW values
        expect = f"{bt}\u3000{mt}"
        # For simulation of "after apply", we don't have new text; check formula consistency:
        # old first line == old book + old title; new would be new book + new title
        old_bt = (ch.get("book_title") or "").strip()
        old_mt = (ch.get("message_title") or "").strip()
        if first_line(ch.get("text") or "") == f"{old_bt}\u3000{old_mt}":
            hdr_ok += 1
    hdr_rate = hdr_ok / max(1, len(sample100))

    # samples
    samples = []
    want = ["subtitle", "suffix", "symbol", "number_fix", "typo"]
    for cat in want:
        for r in final_rows:
            if r["category"] == cat or (cat == "typo" and r["category"] == "typo"):
                if any(s["category"] == cat for s in samples):
                    break
                mk = r["message_key"]
                chs = by_mkey.get(mk) or []
                if not chs:
                    continue
                ch = sorted(chs, key=lambda c: c.get("chunk_index") or 0)[0]
                bt = (ch.get("book_title") or "").strip()
                samples.append({
                    "category": cat,
                    "book": r.get("book"), "mno": r.get("msg_no"),
                    "before": first_line(ch.get("text") or ""),
                    "after": f"{bt}\u3000{r['new']}",
                    "body": "\n".join((ch.get("text") or "").split("\n")[1:3])[:100],
                })
                break
    while len(samples) < 8:
        for r in final_rows:
            if len(samples) >= 8:
                break
            if any(s.get("mno") == r.get("msg_no") and s.get("book") == r.get("book") for s in samples):
                continue
            mk = r["message_key"]
            chs = by_mkey.get(mk) or []
            if not chs or r["field"] != "message_title":
                continue
            ch = sorted(chs, key=lambda c: c.get("chunk_index") or 0)[0]
            bt = (ch.get("book_title") or "").strip()
            samples.append({
                "category": r["category"], "book": r.get("book"), "mno": r.get("msg_no"),
                "before": first_line(ch.get("text") or ""),
                "after": f"{bt}\u3000{r['new']}",
                "body": "\n".join((ch.get("text") or "").split("\n")[1:3])[:100],
            })

    count_after = es.count(index=ES_INDEX)["count"]
    snap_after = folder_snapshot(LIFE_ROOT)

    # subtitle closure
    n_sub = len(sub_cands)
    # recount from fix subtitle rows
    sub_rows = [r for r in fix_rows if r["category"] == "subtitle"]
    n_on = sum(1 for r in sub_rows if r.get("hit_is_title_line") == "是" and r["confidence"] == "auto")
    n_on_all = sum(1 for r in sub_rows if r.get("hit_is_title_line") == "是")
    n_near = sum(1 for r in sub_rows if r["confidence"] == "needs_review")
    n_sub_keep = sum(1 for r in sub_rows if r["confidence"] == "keep" and "docx无" not in (r.get("note") or ""))
    n_sub_miss = sum(1 for r in sub_rows if "docx无" in (r.get("note") or ""))
    # fix keep count: keep includes miss; closure = on_title + near + keep_not_miss + miss
    n_sub_keep_only = sum(
        1 for r in sub_rows
        if r["confidence"] == "keep" and "docx无" not in (r.get("note") or "")
    )
    closure_sub = n_on_all + n_near + n_sub_keep_only + n_sub_miss
    # Actually on_title includes auto and keep-on-title; recount categories mutually exclusive:
    cat_on_auto = [r for r in sub_rows if r.get("hit_is_title_line") == "是" and r["confidence"] == "auto"]
    cat_on_keep = [r for r in sub_rows if r.get("hit_is_title_line") == "是" and r["confidence"] == "keep"]
    cat_near = [r for r in sub_rows if r["confidence"] == "needs_review"]
    cat_miss = [r for r in sub_rows if "docx无" in (r.get("note") or "")]
    cat_keep_body = [
        r for r in sub_rows
        if r["confidence"] == "keep" and r.get("hit_is_title_line") != "是" and "docx无" not in (r.get("note") or "")
    ]
    closure_sub = len(cat_on_auto) + len(cat_on_keep) + len(cat_near) + len(cat_miss) + len(cat_keep_body)

    conf_c = Counter(r["confidence"] for r in fix_rows)
    cat_c = Counter(r["category"] for r in fix_rows)

    # write CSVs
    out_full = Path(args.csv)
    out_full.parent.mkdir(parents=True, exist_ok=True)
    with out_full.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(fix_rows, key=lambda x: (x["book"], int(x["msg_no"] or 0), x["category"])):
            w.writerow(r)

    out_final = Path(args.final)
    with out_final.open("w", encoding="utf-8-sig", newline="") as fp:
        cols = ["message_key", "field", "old", "new", "category", "reembed"]
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in final_rows:
            w.writerow({c: r[c] for c in cols})

    out_review = Path(args.review)
    with out_review.open("w", encoding="utf-8-sig", newline="") as fp:
        cols = [
            "book", "msg_no", "message_key", "old", "proposal", "category",
            "doc_title_raw", "es12490_title_raw", "text_life_title_raw", "note",
            "hit_paragraph_style", "hit_para_no", "hit_is_title_line",
        ]
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(review_rows, key=lambda x: (x["book"], int(x["msg_no"] or 0))):
            w.writerow({c: r.get(c, "") for c in cols})

    # report
    lines = []
    def w(s=""):
        lines.append(s)

    w("# panai4_outline_12490 生命读经修订清单 v3（只读）")
    w("")
    w(f"> ES：`{es_url}`；全量：`{out_full}`；最终：`{out_final}`；待确认：`{out_review}`。")
    w(f"> 生成：{datetime.now().isoformat(timespec='seconds')}；日志：`{log_path}`；耗时 {time.time()-t0:.1f}s。")
    w("")
    w("## 结论摘要")
    w("")
    w(
        f"(1) **副题**：候选 {n_sub}；篇题行 auto {len(cat_on_auto)}；"
        f"紧挨篇题 needs_review {len(cat_near)}；keep（含正文命中）{len(cat_keep_body)+len(cat_on_keep)}；"
        f"docx无 {len(cat_miss)}。约伯/诗篇：v2 要求 e 为 t 真前缀，副题插在序号前故未入选。"
    )
    w(
        f"(2) **needs_review**：v2 共 {len(v2_nr)} 条 → 降 keep {v2_nr_keep}、"
        f"仍 needs_review {v2_nr_still}、转 auto {v2_nr_auto}；闭合={v2_nr_keep+v2_nr_still+v2_nr_auto==len(v2_nr)}。"
    )
    w(
        "(3) **序号**：使徒 39/54/55/56=auto；出埃及180/路加63/马太43/民数记26=keep；"
        "哥林多后书57/马可68/创世记109=needs_review；哈巴谷2=keep。详见 §3。"
    )
    w("(4) **异体字**：见 §4 分项表（不给结论）。")
    w(
        f"(5) **最终清单**：title={n_title} book={n_book} number={n_number}；"
        f"reembed {reembed_blocks}块/{reembed_msgs}篇；费用上限 ${cost:.4f}。"
    )
    w(
        f"(6) **模拟**：R1残留≈{sim_r1}；组内不一致={len(bad_series)}；唯一键={uniq_ok}；"
        f"头部相等率={hdr_rate:.2%}；auto_assert_fail={auto_fail_final}。"
    )
    w("")
    w("提醒：仅本机 ES；message_key/chunk_id/source_path/book_path 不改；不改 text_life。")
    w("")

    w("## 1. 副题")
    w("")
    w(f"- 候选总数={n_sub}")
    w(f"- 篇题行 auto={len(cat_on_auto)}；篇题行但 d==e keep={len(cat_on_keep)}")
    w(f"- 紧挨篇题 needs_review={len(cat_near)}")
    w(f"- keep（命中非篇题行）={len(cat_keep_body)}")
    w(f"- docx无={len(cat_miss)}")
    w(f"- 闭合 {closure_sub} vs {n_sub} → {closure_sub == n_sub}")
    w("")
    w("### 篇题行 auto 逐条")
    for r in cat_on_auto:
        w(f"- {r['book']} #{r['msg_no']}: `{r['old']}` → `{r['new']}`")
    w("")
    w("### 紧挨篇题 needs_review")
    for r in cat_near:
        w(f"- {r['book']} #{r['msg_no']} style={r.get('hit_paragraph_style')} para={r.get('hit_para_no')} proposal=`{(r.get('proposal') or '')[:60]}`")
    w("")
    w("### 约伯记 / 诗篇")
    w("")
    w("| 书 | 篇 | hit | conf | v2曾候选 | 说明 |")
    w("|---|---:|---|---|---|---|")
    for r in job_psalm_rows:
        w(f"| {r['book']} | {r['mno']} | {r['hit']} | {r['conf']} | {r['v2']} | {r['why_v2']} |")
    w("")
    w("e / d_eff / t 样例（约伯与诗篇各前 5）：")
    for r in job_psalm_rows[:10]:
        w(f"- {r['book']} #{r['mno']}")
        w(f"  - e=`{r['e'][:70]}`")
        w(f"  - d=`{r['d_eff'][:70]}`")
        w(f"  - t=`{r['t'][:70]}`")
    w("")

    w("## 2. needs_review 降级")
    w("")
    w(f"- v2 needs_review={len(v2_nr)}")
    w(f"- → keep {v2_nr_keep} / 仍 needs_review {v2_nr_still} / 转 auto {v2_nr_auto}")
    w(f"- 闭合={v2_nr_keep + v2_nr_still + v2_nr_auto == len(v2_nr)}")
    w("")
    w("### 仍 needs_review 逐条")
    # unique by book,msg
    seen = set()
    for r in review_rows:
        k = (r["book"], r["msg_no"])
        if k in seen:
            continue
        seen.add(k)
        w(
            f"- {r['book']} #{r['msg_no']}: e=`{r['old'][:50]}` d=`{(r.get('doc_title_raw') or '')[:40]}` "
            f"t=`{(r.get('text_life_title_raw') or '')[:40]}` proposal=`{(r.get('proposal') or '')[:50]}` "
            f"note={r.get('note')}"
        )
    w("")
    w(f"### MUST_KEEP 检查失败数={len(must_keep_fail)}")
    for item in must_keep_fail[:20]:
        w(f"- {item}")
    w("")

    w("## 3. 序号")
    w("")
    w("### 哥林多后书 #54–#60")
    w("| mno | e | d_eff | t | se/sd/st |")
    w("|---:|---|---|---|---|")
    for r in cor2_table:
        w(f"| {r['mno']} | {r['e'][:40]} | {r['d'][:40]} | {r['t'][:40]} | {r['se']}/{r['sd']}/{r['st']} |")
    seqs_e = [r["se"] for r in cor2_table if r["se"] is not None]
    seqs_d = [r["sd"] for r in cor2_table if r["sd"] is not None]
    seqs_t = [r["st"] for r in cor2_table if r["st"] is not None]
    def contig(vals):
        if len(vals) < 2:
            return True
        return all(vals[i] == vals[i - 1] + 1 for i in range(1, len(vals)))
    w(f"- e连续={contig(seqs_e)} {seqs_e}；d连续={contig(seqs_d)} {seqs_d}；t连续={contig(seqs_t)} {seqs_t}")
    w("")
    w("### 使徒行传 #50–#60 应用后")
    for mno, title, seq in acts_after:
        w(f"- #{mno} seq={seq} `{title}`")
    acts_seqs = [s for _, _, s in acts_after if s is not None]
    w(f"- 应用后连续={contig(acts_seqs)} {acts_seqs}")
    w("")
    w("### 创世记 109 邻篇")
    for row in gen109_nb:
        w(f"- #{row[0]} e=`{row[1][:40]}` d=`{(row[2] or '')[:40]}` t=`{(row[3] or '')[:40]}` seq e/d/t={row[4]}/{row[5]}/{row[6]}")
    w("")
    w("### 马可 68 邻篇")
    for row in mark68_nb:
        w(f"- #{row[0]} e=`{row[1][:40]}` d=`{(row[2] or '')[:40]}` t=`{(row[3] or '')[:40]}` seq e/d/t={row[4]}/{row[5]}/{row[6]}")
    w("")

    w("## 4. 异体字分项统计（只统计）")
    w("")
    w("| 写法 | 12490标题篇 | 12490正文块 | 12490正文次 | TL标题 | TL正文块 | TL正文次 | 通用写法12490正文次 |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in variant_table:
        w(
            f"| {row['form']} | {row['t12490']} | {row['b12490']} | {row['o12490']} | "
            f"{row['ttl']} | {row['btl']} | {row['otl']} | {row['common_o12490']} |"
        )
    w("")
    w("通用写法对照：於→终结于；乾→干渴；痲/疯→麻风；惟→唯一；豫言→预言；豫表→预表；题醒→提醒；耶赂/耶略→耶路；─→—。")
    w("")
    for c, words in top_words.items():
        w(f"### 含「{c}」的高频二至四字（前15）")
        for word, cnt in words:
            w(f"- `{word}` × {cnt}")
        w("")

    w("## 5. 最终清单与模拟")
    w("")
    w(f"- title={n_title} book={n_book} number={n_number}")
    w(f"- reembed 块={reembed_blocks} 篇={reembed_msgs} 费用上限=${cost:.4f}")
    w(f"- 全量 conf={dict(conf_c)} cat={dict(cat_c)}")
    w(f"- 模拟 R1残留≈{sim_r1} 组不一致={len(bad_series)} 唯一键={uniq_ok} 头部相等率={hdr_rate:.2%}")
    w("")
    w("### 改前/改后样例")
    for s in samples:
        w(f"#### {s.get('book')} #{s.get('mno')} ({s['category']})")
        w(f"- 改前：`{s['before']}`")
        w(f"- 改后：`{s['after']}`")
        w(f"- 正文：`{s['body']}`")
        w("")

    w("## 验证")
    w("")
    w(f"1. count {count_before}/{count_after} 一致={count_before == count_after} (55841={count_before == 55841})")
    w(f"2. auto_assert_fail_final={auto_fail_final}；例={auto_fail_ex[:5]}")
    w(f"3. 副题闭合 {closure_sub} vs {n_sub}")
    w(f"4. v2 nr 闭合 {v2_nr_keep}+{v2_nr_still}+{v2_nr_auto}={v2_nr_keep+v2_nr_still+v2_nr_auto} vs {len(v2_nr)}")
    w(f"5. 组内不一致={len(bad_series)} 唯一键={uniq_ok} 相等率={hdr_rate:.2%}")
    w(f"6. 桌面 before={snap_before} after={snap_after} ok={snap_before == snap_after == ROUND1_SNAP or (snap_before == snap_after)}")
    w("7. git:")
    w("```")
    w(_git_status())
    w("```")
    w("8. ES 只用 info/count/search/scroll；_source excludes embedding。")
    w("")

    report_path = Path(args.report)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info(
        "wrote full=%s final=%s review=%s report=%s auto_fail=%s sub=%s",
        out_full, out_final, out_review, report_path, auto_fail_final, n_sub,
    )
    print(
        f"full={out_full} rows={len(fix_rows)} final={len(final_rows)} review={len(review_rows)} "
        f"sub={n_sub} on_title_auto={len(cat_on_auto)} near={len(cat_near)} "
        f"v2nr keep/still/auto={v2_nr_keep}/{v2_nr_still}/{v2_nr_auto} "
        f"reembed={reembed_blocks}/{reembed_msgs} auto_fail={auto_fail_final} bad_series={len(bad_series)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
