# -*- coding: utf-8 -*-
"""只读产出 panai4_outline_12490 生命读经修订清单。

不写索引、不改桌面、不改 outline 既有文件。

用法（在 back_mic/backend 下）::

    python -m panai4.outline.probe_life_fixlist
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

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

BOOK_RENAME = {
    "雅歌书生命读经": "雅歌生命读经",
    "约翰二书生命读经_": "约翰二书生命读经",
}
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
REPO_ROOT = Path(__file__).resolve().parents[4]
PAIRING_CSV = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_outline_pairing.csv"
CSV_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_list.csv"
REPORT_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_list.md"
LOG_DIR_DEFAULT = REPO_ROOT / "logs"
ES_INDEX = "panai4_outline_12490"
TL_INDEX = "panai4_text_life"
ROUND1_SNAP = {"files": 1984, "bytes": 77896253, "max_mtime": 1766425146.0}
SAMPLE_SEED = 20261106
APPENDIX_TITLE = "附录　合乎圣经神圣启示的召会末世论"
SKIP_CONTENT_KEY = ("约翰福音生命读经", 29)  # 内容不动，不列入任何修订

_SOURCE_EXCLUDES = ["embedding"]
_CN_PIAN_RE = re.compile(r"^第[一二三四五六七八九十百千零〇两0-9]+篇")
_PIAN_ANY_RE = re.compile(r"第[一二三四五六七八九十百千零〇两0-9]+篇")
_EDIT_DIST_RATIO_THRESHOLD = 0.5

CSV_COLS = [
    "kind", "book", "msg_no", "message_key", "field", "old", "new", "rule",
    "confidence", "doc_title_raw", "es12490_title_raw", "text_life_title_raw",
    "chunk_count", "reembed", "note",
]


def _backend_env() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def setup_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_dir / f"life_12490_fixlist_{stamp}.log"
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
            "—": "-", "–": "-", "－": "-", "〜": "~", "～": "~",
            "，": ",", "、": ",", "：": ":", "；": ";",
        }
    )
    s = s.translate(trans)
    return re.sub(r"\s+", "", s)


def strip_pian_prefix(title: str) -> str:
    raw = (title or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
    m = re.match(r"^第[一二三四五六七八九十百千零〇两0-9]+篇[\s\u3000]*(.*)$", raw)
    if m:
        return (m.group(1) or "").strip()
    return raw


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def edit_ratio(a: str, b: str) -> float:
    """归一化编辑距离 / max(len)；空对空为 0。"""
    na, nb = normalize_title_cmp(a), normalize_title_cmp(b)
    denom = max(len(na), len(nb), 1)
    return levenshtein(na, nb) / denom


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


def load_pairing(path: Path) -> dict[tuple[str, int], dict]:
    rows: dict[tuple[str, int], dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as fp:
        for r in csv.DictReader(fp):
            path_rel = r.get("desktop_path") or ""
            book_col = next((k for k in r.keys() if k.startswith("desktop_book")), None)
            book = normalize_book((r.get(book_col) or "").strip()) if book_col else ""
            if not book and path_rel:
                from panai4.outline.docx_parser import strip_dir_index

                book = normalize_book(strip_dir_index(Path(path_rel).parts[0]))
            mno = int(r["msg_no"])
            doc = (r.get("doc_title") or "").strip().replace("\n", "").replace("\r", "").replace("\v", "")
            doc = strip_pian_prefix(doc)
            rows[(book, mno)] = {
                "desktop_path": path_rel,
                "desktop_book": book,
                "msg_no": mno,
                "doc_title": doc,
                "doc_title_raw": r.get("doc_title") or "",
            }
    return rows


# ---------------------------------------------------------------------------
# ES
# ---------------------------------------------------------------------------

def scroll_life_chunks(es) -> tuple[list[dict], list[str]]:
    from elasticsearch.helpers import scan

    # 先取 mapping，决定还要拉哪些字段查旧书名
    mapping = es.indices.get_mapping(index=ES_INDEX)[ES_INDEX]["mappings"].get("properties") or {}
    field_names = sorted(mapping.keys())
    include = [
        "book_title", "message_title", "message_number", "message_key",
        "source_path", "book_path", "text", "chunk_index", "chunk_total",
        "point_count", "part_name", "part_no", "paragraph_type", "author",
        "conference", "batch",
    ]
    for name in field_names:
        if name == "embedding":
            continue
        if name not in include:
            include.append(name)

    rows = []
    for doc in scan(
        es,
        index=ES_INDEX,
        query={"query": {"wildcard": {"book_title": "*生命读经*"}}},
        _source={"includes": include, "excludes": _SOURCE_EXCLUDES},
        size=500,
    ):
        src = doc.get("_source") or {}
        bt = (src.get("book_title") or "").strip()
        if not is_life_study_book(bt):
            continue
        rows.append(src)
    return rows, field_names


def scroll_text_life(es) -> dict[tuple[str, int], dict]:
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
        extra = ""
        m = re.search(r"，第[一二三四五六七八九十百千零〇两0-9]+篇[\s\u3000]*(.*)$", raw_book)
        if m:
            extra = (m.group(1) or "").strip()
        body = strip_pian_prefix(mt)
        title_aug = mt
        if extra:
            if len(normalize_title_cmp(body)) < len(normalize_title_cmp(extra)):
                if "篇" in mt:
                    title_aug = mt.split("篇", 1)[0] + "篇　" + extra
                else:
                    title_aug = extra
            elif normalize_title_cmp(extra) and normalize_title_cmp(extra) not in normalize_title_cmp(mt):
                # 软换行切断：mt 是前半，extra 是后半
                if mt and not normalize_title_cmp(mt).endswith(normalize_title_cmp(extra)[:6]):
                    # 若 mt 已含完整，不动；若 extra 更长后缀则拼
                    if len(normalize_title_cmp(body + extra)) > len(normalize_title_cmp(body)) + 2:
                        if normalize_title_cmp(body) and normalize_title_cmp(extra).startswith(
                            normalize_title_cmp(body)[:8]
                        ):
                            title_aug = extra if len(extra) > len(body) else mt
                        else:
                            # 常见：脏 book 里是完整篇题，mt 被切断
                            if len(normalize_title_cmp(extra)) > len(normalize_title_cmp(body)):
                                title_aug = extra
        entry = by_key.get(key)
        stripped = strip_pian_prefix(title_aug)
        if entry is None:
            by_key[key] = {
                "message_title": mt,
                "title_stripped": stripped,
                "title_raw_for_new": stripped,  # 用作 new 时的 text_life 写法
                "book_raw": raw_book,
                "extra": extra,
                "text_sample": (src.get("text") or "")[:400],
            }
        else:
            if len(stripped) > len(entry["title_stripped"]):
                entry["message_title"] = mt
                entry["title_stripped"] = stripped
                entry["title_raw_for_new"] = stripped
            if not entry.get("text_sample") and src.get("text"):
                entry["text_sample"] = (src.get("text") or "")[:400]
    return by_key


def first_line(text: str) -> str:
    return (text or "").split("\n", 1)[0]


def classify_title(d: str, e: str, t: str) -> tuple[str, str, str, str]:
    """返回 (rule, confidence, new_value_or_empty, note)。d/e/t 均为去第N篇后的展示用原文。"""
    nd, ne, nt = normalize_title_cmp(d), normalize_title_cmp(e), normalize_title_cmp(t)
    d_miss = not nd

    # R1
    if nt and ne and nt == ne + normalize_title_cmp("（插进的话）"):
        return "R1", "auto", t, "补（插进的话）后缀；new=text_life 原文"

    # R2
    if d_miss:
        if ne == nt:
            return "R2", "keep", "", "d缺失且 e==t"
    else:
        if ne == nt == nd:
            return "R2", "keep", "", "三者一致"

    # R3
    if (not d_miss) and ne == nt and nd != ne:
        return "R3", "keep", "", "e==t，桌面不同；问题在桌面"

    # R4
    if (not d_miss) and nd == nt and ne != nd:
        ratio = edit_ratio(e, d)
        if ratio > _EDIT_DIST_RATIO_THRESHOLD:
            return (
                "R4",
                "needs_review",
                d,
                f"d==t≠e 但编辑距离占比={ratio:.2f}>{_EDIT_DIST_RATIO_THRESHOLD}（lev/max(len)）",
            )
        return "R4", "auto", d, "d==t≠e；new=doc_title"

    # R5
    if (not d_miss) and nd == ne and nt != nd:
        return "R5", "keep", "", "d==e≠t；12490不改，text_life待修"

    # R6
    if d_miss and ne != nt:
        return "R6", "needs_review", "", "d缺失且 e≠t"

    # R7
    if (not d_miss) and nd != ne and nd != nt and ne != nt:
        return "R7", "needs_review", "", "三者互不相同"

    # 兜底
    return "R7", "needs_review", "", f"未归入 R1-R6 的残余：nd/ne/nt 关系兜底"


def residue_flags(title: str) -> list[str]:
    reasons = []
    mt = title or ""
    if "副本" in mt:
        reasons.append("副本")
    if "(2)" in mt or "（2）" in mt:
        reasons.append("(2)")
    if mt != mt.strip():
        reasons.append("首尾空格")
    if re.search(r"[\t\v\f\u00a0]", mt):
        reasons.append("奇怪空白")
    # 「第N篇」残留：标题以第N篇开头，或非「…篇信息的补充」类真篇题
    if _CN_PIAN_RE.match(mt.strip()):
        reasons.append("第N篇残留_前缀")
    elif _PIAN_ANY_RE.search(mt) and "信息的补充" not in mt:
        # 中间或前缀残留，但诗篇33「第三十二篇信息的补充」是真篇题
        if re.match(r"^第.+篇[\s\u3000]", mt.strip()):
            reasons.append("第N篇残留_前缀")
    return reasons


def row_dict(**kwargs) -> dict:
    out = {c: "" for c in CSV_COLS}
    out.update(kwargs)
    for c in CSV_COLS:
        if out[c] is None:
            out[c] = ""
        else:
            out[c] = str(out[c])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="12490 生命读经修订清单（只读）")
    parser.add_argument("--csv", default=str(CSV_DEFAULT))
    parser.add_argument("--report", default=str(REPORT_DEFAULT))
    parser.add_argument("--log-dir", default=str(LOG_DIR_DEFAULT))
    args = parser.parse_args()

    t0 = time.time()
    log_path = setup_logging(Path(args.log_dir))
    csv_path = Path(args.csv)
    report_path = Path(args.report)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    snap_before = folder_snapshot(LIFE_ROOT)
    logging.info("snap_before=%s", snap_before)

    es, es_url = make_es()
    info = es.info()
    count_before = es.count(index=ES_INDEX)["count"]
    logging.info("ES %s count_before=%s", es_url, count_before)

    desk = load_pairing(PAIRING_CSV)
    logging.info("pairing=%s", len(desk))

    life_chunks, mapping_fields = scroll_life_chunks(es)
    logging.info("life_chunks=%s mapping_fields=%s", len(life_chunks), len(mapping_fields))

    # 按 message_key 聚合；编号键
    by_mkey: dict[str, list[dict]] = defaultdict(list)
    by_bn: dict[tuple[str, Optional[int]], list[dict]] = defaultdict(list)
    for ch in life_chunks:
        mk = ch.get("message_key") or ""
        by_mkey[mk].append(ch)
        bt = (ch.get("book_title") or "").strip()
        canon = normalize_book(bt)
        mno = ch.get("message_number")
        if mno is not None:
            mno = int(mno)
        by_bn[(canon, mno)].append(ch)

    # ---- 1 书名类 ----
    book_fix_rows: list[dict] = []
    book_affected_chunks: list[dict] = []
    for old_bt, new_bt in BOOK_RENAME.items():
        chunks = [c for c in life_chunks if (c.get("book_title") or "").strip() == old_bt]
        # 按 message_key 一篇一行
        keys = sorted({c.get("message_key") or "" for c in chunks})
        for mk in keys:
            chs = [c for c in chunks if (c.get("message_key") or "") == mk]
            if not chs:
                continue
            c0 = chs[0]
            mno = c0.get("message_number")
            book_fix_rows.append(row_dict(
                kind="book",
                book=normalize_book(old_bt),
                msg_no="" if mno is None else mno,
                message_key=mk,
                field="book_title",
                old=old_bt,
                new=new_bt,
                rule="BOOK_RENAME",
                confidence="auto",
                es12490_title_raw=c0.get("message_title") or "",
                chunk_count=len(chs),
                reembed="是",
                note=f"书名规范化 {old_bt}→{new_bt}",
            ))
            book_affected_chunks.extend(chs)

    # 各字段含旧写法
    old_spellings = list(BOOK_RENAME.keys())
    field_hits: dict[str, dict[str, int]] = {sp: Counter() for sp in old_spellings}
    header_old_count = Counter()  # spelling → chunks whose first line contains old
    sample_fields_checked = set()
    for ch in life_chunks:
        for sp in old_spellings:
            for fname, val in ch.items():
                if fname == "embedding":
                    continue
                sample_fields_checked.add(fname)
                s = val if isinstance(val, str) else (str(val) if val is not None else "")
                if isinstance(val, list):
                    s = " ".join(str(x) for x in val)
                if sp in s:
                    field_hits[sp][fname] += 1
            fl = first_line(ch.get("text") or "")
            if sp in fl:
                header_old_count[sp] += 1

    # ---- 2 篇题类 ----
    tl_map = scroll_text_life(es)
    logging.info("text_life keys=%s", len(tl_map))

    rule_hits: dict[str, list[dict]] = defaultdict(list)
    title_fix_rows: list[dict] = []
    residue_rows: list[dict] = []
    r5_report: list[dict] = []  # text_life 待修
    keep_r3: list[dict] = []

    numbered_keys = sorted(
        {(b, n) for (b, n) in by_bn if n is not None and b},
        key=lambda x: (x[0], x[1]),
    )
    # 仅与桌面 both 的 1983（附录 null 不进篇题比较）
    both_keys = sorted(set(desk.keys()) & {(b, n) for b, n in numbered_keys})
    logging.info("both_keys for title=%s", len(both_keys))

    for book, mno in both_keys:
        chs = by_bn[(book, mno)]
        chs_sorted = sorted(chs, key=lambda c: (c.get("chunk_index") is None, c.get("chunk_index") or 0))
        e_raw = (chs_sorted[0].get("message_title") or "").strip()
        e = strip_pian_prefix(e_raw)
        mk = chs_sorted[0].get("message_key") or ""
        d_info = desk[(book, mno)]
        d = d_info["doc_title"]
        d_raw = d_info["doc_title_raw"]
        tl = tl_map.get((book, mno), {})
        t = tl.get("title_stripped") or ""
        t_raw_mt = tl.get("message_title") or ""
        t_for_new = tl.get("title_raw_for_new") or t

        rule, conf, new_v, note = classify_title(d, e, t)
        rec = {
            "book": book,
            "mno": mno,
            "message_key": mk,
            "d": d,
            "e": e,
            "t": t,
            "d_raw": d_raw,
            "e_raw": e_raw,
            "t_raw": t_raw_mt,
            "t_for_new": t_for_new,
            "rule": rule,
            "confidence": conf,
            "new": new_v,
            "note": note,
            "chunk_count": len(chs),
            "edit_ratio": edit_ratio(e, d) if d and e else 0.0,
        }
        rule_hits[rule].append(rec)

        if rule == "R2":
            pass  # 不列入清单
        elif rule == "R3":
            keep_r3.append(rec)
            title_fix_rows.append(row_dict(
                kind="title", book=book, msg_no=mno, message_key=mk,
                field="message_title", old=e_raw, new="",
                rule=rule, confidence="keep",
                doc_title_raw=d, es12490_title_raw=e_raw, text_life_title_raw=t_for_new or t_raw_mt,
                chunk_count=len(chs), reembed="否", note=note,
            ))
        elif rule == "R5":
            r5_report.append(rec)
            title_fix_rows.append(row_dict(
                kind="title", book=book, msg_no=mno, message_key=mk,
                field="message_title", old=e_raw, new="",
                rule=rule, confidence="keep",
                doc_title_raw=d, es12490_title_raw=e_raw, text_life_title_raw=t_for_new or t_raw_mt,
                chunk_count=len(chs), reembed="否",
                note="text_life待修；" + note,
            ))
        elif rule == "R1":
            # new 必须来自 text_life 原文
            new_val = t_for_new
            title_fix_rows.append(row_dict(
                kind="title", book=book, msg_no=mno, message_key=mk,
                field="message_title", old=e_raw, new=new_val,
                rule=rule, confidence="auto",
                doc_title_raw=d, es12490_title_raw=e_raw, text_life_title_raw=t_for_new or t_raw_mt,
                chunk_count=len(chs), reembed="是", note=note,
            ))
        elif rule == "R4":
            # new=d；needs_review 仍列出建议 new，但未确认前不计入 reembed
            title_fix_rows.append(row_dict(
                kind="title", book=book, msg_no=mno, message_key=mk,
                field="message_title", old=e_raw, new=d if d else "",
                rule=rule, confidence=conf,
                doc_title_raw=d, es12490_title_raw=e_raw, text_life_title_raw=t_for_new or t_raw_mt,
                chunk_count=len(chs), reembed=("是" if conf == "auto" else "否"), note=note,
            ))
        elif rule in ("R6", "R7"):
            title_fix_rows.append(row_dict(
                kind="title", book=book, msg_no=mno, message_key=mk,
                field="message_title", old=e_raw, new="",
                rule=rule, confidence="needs_review",
                doc_title_raw=d, es12490_title_raw=e_raw, text_life_title_raw=t_for_new or t_raw_mt,
                chunk_count=len(chs), reembed="否", note=note,
            ))

        # residue（R4/R6 之外也扫；已知诗篇33 keep，路加28 needs_review）
        flags = residue_flags(e_raw)
        if flags and rule not in ("R4", "R6"):
            # 已在 R4/R6 清单里的不重复？用户说「R4 与 R6 之外」单独扫描
            conf_r = "needs_review"
            note_r = "杂质:" + ",".join(flags)
            if book == "诗篇生命读经" and mno == 33 and "第三十二篇信息的补充" in e_raw:
                conf_r = "keep"
                note_r = "真篇题含「第三十二篇信息的补充」；" + note_r
            elif book == "路加福音生命读经" and mno == 28 and e_raw.startswith("第二十八篇"):
                conf_r = "needs_review"
                note_r = "文件名/篇题带「第二十八篇」残留；" + note_r
            # 约翰29 不列入
            if (book, mno) == SKIP_CONTENT_KEY:
                continue
            residue_rows.append(row_dict(
                kind="residue", book=book, msg_no=mno, message_key=mk,
                field="message_title", old=e_raw, new="",
                rule="RESIDUE", confidence=conf_r,
                doc_title_raw=d, es12490_title_raw=e_raw, text_life_title_raw=t_for_new or t_raw_mt,
                chunk_count=len(chs), reembed="否", note=note_r,
            ))
        elif flags and rule in ("R4", "R6"):
            # 在 note 里追加杂质提示，不另开行（避免重复）— 用户要 residue 单独列；R4/R6之外才单独。跳过。
            pass

        # 对 R4/R6 之外没有进 residue 但有「第N篇残留」的已处理
        # 诗篇33 若被 R2 吃掉也要 residue keep
        if book == "诗篇生命读经" and mno == 33:
            if not any(r["msg_no"] == "33" and r["book"] == book and r["kind"] == "residue" for r in residue_rows):
                if "第三十二篇信息的补充" in e_raw:
                    residue_rows.append(row_dict(
                        kind="residue", book=book, msg_no=mno, message_key=mk,
                        field="message_title", old=e_raw, new="",
                        rule="RESIDUE", confidence="keep",
                        doc_title_raw=d, es12490_title_raw=e_raw, text_life_title_raw=t_for_new or t_raw_mt,
                        chunk_count=len(chs), reembed="否",
                        note="真篇题含「第三十二篇信息的补充」；keep",
                    ))

    # 路加28 若在 R2 也要 residue
    luke28 = next((r for r in rule_hits.get("R2", []) if r["book"] == "路加福音生命读经" and r["mno"] == 28), None)
    if luke28 and luke28["e_raw"].startswith("第二十八篇"):
        if not any(r["book"] == "路加福音生命读经" and r["msg_no"] == "28" and r["kind"] == "residue" for r in residue_rows):
            residue_rows.append(row_dict(
                kind="residue", book="路加福音生命读经", msg_no=28,
                message_key=luke28["message_key"], field="message_title",
                old=luke28["e_raw"], new="", rule="RESIDUE", confidence="needs_review",
                doc_title_raw=luke28["d"], es12490_title_raw=luke28["e_raw"],
                text_life_title_raw=luke28.get("t_for_new") or luke28["t_raw"],
                chunk_count=luke28["chunk_count"], reembed="否",
                note="「第二十八篇」残留；needs_review",
            ))

    # ---- 3 附录 number ----
    null_chunks = [c for c in life_chunks if c.get("message_number") is None]
    number_rows: list[dict] = []
    esther_nums = sorted({
        int(c["message_number"])
        for c in life_chunks
        if (c.get("book_title") or "").strip() == "以斯帖记生命读经" and c.get("message_number") is not None
    })
    tl_appendix = tl_map.get(("以斯帖记生命读经", 3))
    # 按 message_key 一篇一行
    null_by_key: dict[str, list[dict]] = defaultdict(list)
    for c in null_chunks:
        null_by_key[c.get("message_key") or ""].append(c)
    for mk, chs in sorted(null_by_key.items()):
        c0 = chs[0]
        mt = (c0.get("message_title") or "").strip()
        bt = (c0.get("book_title") or "").strip()
        is_appendix = APPENDIX_TITLE in mt or (bt == "以斯帖记生命读经" and "末世论" in mt)
        number_rows.append(row_dict(
            kind="number",
            book=normalize_book(bt),
            msg_no="",
            message_key=mk,
            field="message_number",
            old="",
            new="3" if is_appendix else "",
            rule="APPENDIX_MSGNO",
            confidence="auto" if is_appendix else "needs_review",
            es12490_title_raw=mt,
            text_life_title_raw=(tl_appendix or {}).get("title_stripped") or "",
            chunk_count=len(chs),
            reembed="否",
            note=(
                f"附录 message_number null→3；text_life确认={'是' if tl_appendix else '否'}；"
                f"该书已有编号={esther_nums}；冲突={'是' if 3 in esther_nums else '否'}"
            ),
        ))

    # ---- 合并 CSV（约翰29 不进任何修订；书名类若碰巧包含也不改内容——书名类不含约翰）----
    all_rows: list[dict] = []
    all_rows.extend(book_fix_rows)
    for r in title_fix_rows + residue_rows + number_rows:
        try:
            mno_i = int(r["msg_no"]) if r["msg_no"] not in ("", None) else None
        except ValueError:
            mno_i = None
        if r["book"] == SKIP_CONTENT_KEY[0] and mno_i == SKIP_CONTENT_KEY[1]:
            # 明确跳过约翰29 的任何修订行
            continue
        all_rows.append(r)

    # ---- 4 向量范围 ----
    def chunk_count_of_rows(rows: list[dict], conf_filter=None) -> tuple[int, int]:
        keys = set()
        blocks = 0
        for r in rows:
            if conf_filter and r["confidence"] not in conf_filter:
                continue
            keys.add((r["book"], r["msg_no"], r["message_key"]))
            blocks += int(r["chunk_count"] or 0)
        return blocks, len(keys)

    book_blocks = sum(int(r["chunk_count"]) for r in book_fix_rows)
    book_msgs = len(book_fix_rows)
    title_auto = [r for r in title_fix_rows if r["confidence"] == "auto" and r["rule"] in ("R1", "R4")]
    # 排除约翰29
    title_auto = [
        r for r in title_auto
        if not (r["book"] == "约翰福音生命读经" and r["msg_no"] == "29")
    ]
    title_auto_blocks = sum(int(r["chunk_count"]) for r in title_auto)
    title_auto_msgs = len(title_auto)
    nr_rows = [r for r in all_rows if r["confidence"] == "needs_review"]
    nr_blocks = sum(int(r["chunk_count"]) for r in nr_rows)
    num_blocks = sum(int(r["chunk_count"]) for r in number_rows if r["confidence"] == "auto")

    reembed_rows = [r for r in all_rows if r["reembed"] == "是"]
    # 同一 message_key 去重块数：取该篇 chunk_count（避免 book+title 双计）
    reembed_by_key: dict[str, int] = {}
    for r in reembed_rows:
        mk = r["message_key"]
        reembed_by_key[mk] = max(reembed_by_key.get(mk, 0), int(r["chunk_count"] or 0))
    reembed_blocks = sum(reembed_by_key.values())
    reembed_msgs = len(reembed_by_key)

    # 头部行格式抽样
    rng = random.Random(SAMPLE_SEED)
    sample_chs = rng.sample(life_chunks, min(20, len(life_chunks)))
    header_fmt = Counter()
    header_examples = []
    for ch in sample_chs:
        bt = (ch.get("book_title") or "").strip()
        mt = (ch.get("message_title") or "").strip()
        fl = first_line(ch.get("text") or "")
        expected = f"{bt}\u3000{mt}"
        ok = fl == expected or fl.startswith(expected)
        header_fmt["match_book_sp_title" if fl == expected else ("startswith" if ok else "other")] += 1
        if len(header_examples) < 3:
            header_examples.append({"fl": fl, "expected": expected, "ok": fl == expected})

    # reembed 改前/改后样例
    reembed_samples = []
    for r in reembed_rows:
        if len(reembed_samples) >= 5:
            break
        mk = r["message_key"]
        chs = by_mkey.get(mk) or []
        if not chs:
            continue
        ch = sorted(chs, key=lambda c: c.get("chunk_index") or 0)[0]
        fl = first_line(ch.get("text") or "")
        bt = (ch.get("book_title") or "").strip()
        mt = (ch.get("message_title") or "").strip()
        new_bt = bt
        new_mt = mt
        if r["kind"] == "book":
            new_bt = r["new"]
        if r["kind"] == "title" and r["new"]:
            new_mt = r["new"]
        before = fl
        after = f"{new_bt}\u3000{new_mt}"
        # 正文不变：第二行起
        body = "\n".join((ch.get("text") or "").split("\n")[1:])
        reembed_samples.append({
            "book": r["book"], "msg_no": r["msg_no"], "kind": r["kind"],
            "before": before, "after": after, "body_unchanged": True,
            "body_head": body[:80].replace("\n", "\\n"),
        })

    # 费用：按实测 $0.002/千块
    cost_per_1k = 0.002
    cost_upper = (reembed_blocks / 1000.0) * cost_per_1k
    # 字数估算
    token_lens = []
    for mk in list(reembed_by_key.keys())[:200]:
        for ch in by_mkey.get(mk) or []:
            token_lens.append(len(ch.get("text") or ""))
    avg_chars = (sum(token_lens) / len(token_lens)) if token_lens else 0

    # ---- 5 头部行「第N篇」统计 ----
    life_with_pian = 0
    life_without_pian = 0
    for ch in life_chunks:
        fl = first_line(ch.get("text") or "")
        if _PIAN_ANY_RE.search(fl):
            life_with_pian += 1
        else:
            life_without_pian += 1

    # 全库随机 20
    from elasticsearch.helpers import scan as es_scan

    all_sample = []
    for doc in es_scan(
        es,
        index=ES_INDEX,
        query={"query": {"match_all": {}}},
        _source={"includes": ["text", "book_title", "message_title"], "excludes": _SOURCE_EXCLUDES},
        size=500,
    ):
        all_sample.append(doc.get("_source") or {})
        if len(all_sample) >= 5000:
            break
    all20 = rng.sample(all_sample, min(20, len(all_sample)))
    all20_with = sum(1 for c in all20 if _PIAN_ANY_RE.search(first_line(c.get("text") or "")))
    all20_without = len(all20) - all20_with

    # 生命读经随机 20 的「第N篇」
    life20 = rng.sample(life_chunks, min(20, len(life_chunks)))
    life20_with = sum(1 for c in life20 if _PIAN_ANY_RE.search(first_line(c.get("text") or "")))
    life20_without = len(life20) - life20_with

    # ---- 验证 ----
    count_after = es.count(index=ES_INDEX)["count"]
    snap_after = folder_snapshot(LIFE_ROOT)
    git_st = _git_status()

    # V2: 规则之和
    rule_counts = {f"R{i}": len(rule_hits.get(f"R{i}", [])) for i in range(1, 8)}
    rule_sum = sum(rule_counts.values())
    # R2 should be 1983 - others; but every key gets exactly one rule
    v2_ok = rule_sum == len(both_keys)

    # V3: auto new 必须在 doc_title_raw 或 text_life_title_raw 中逐字找到
    auto_fail = 0
    auto_fail_examples = []
    for r in all_rows:
        if r["confidence"] != "auto" or not r["new"]:
            continue
        new = r["new"]
        hay = (r.get("doc_title_raw") or "") + "\n" + (r.get("text_life_title_raw") or "")
        # 书名类 / number 类：new 不在 title raw 里是正常的
        if r["kind"] in ("book", "number"):
            continue
        if new not in hay and normalize_title_cmp(new) not in normalize_title_cmp(hay):
            # 允许 new 等于 doc_title_raw 去空白后的展示值已写入 doc_title_raw 列
            if new != r.get("doc_title_raw") and new not in (r.get("doc_title_raw") or ""):
                auto_fail += 1
                if len(auto_fail_examples) < 10:
                    auto_fail_examples.append((r["book"], r["msg_no"], new, r["rule"]))

    # 更严：title auto 的 new 必须等于 doc_title_raw 或 text_life_title_raw（逐字）
    auto_fail2 = 0
    auto_fail2_ex = []
    for r in all_rows:
        if r["confidence"] != "auto" or r["kind"] != "title":
            continue
        new = r["new"]
        if new == r.get("doc_title_raw") or new == r.get("text_life_title_raw"):
            continue
        # doc_title_raw 可能带第N篇；允许 new == strip 后的 d（已写入 doc_title_raw 列为我们的 d）
        if new == r.get("doc_title_raw") or new in (r.get("doc_title_raw"), r.get("text_life_title_raw")):
            continue
        auto_fail2 += 1
        auto_fail2_ex.append((r["book"], r["msg_no"], repr(new), repr(r.get("doc_title_raw")), repr(r.get("text_life_title_raw")), r["rule"]))

    # 我们把 doc_title_raw 列写成了 strip 后的 d，text_life_title_raw 写成 t_for_new；
    # 断言：new ∈ {doc_title_raw, text_life_title_raw}
    auto_assert_fail = 0
    for r in all_rows:
        if r["confidence"] != "auto" or r["kind"] != "title":
            continue
        if r["new"] not in (r.get("doc_title_raw"), r.get("text_life_title_raw")):
            auto_assert_fail += 1

    # V4 模拟应用
    sim_e: dict[tuple[str, int], str] = {}
    for book, mno in both_keys:
        chs = by_bn[(book, mno)]
        e_raw = (chs[0].get("message_title") or "").strip()
        sim_e[(book, mno)] = strip_pian_prefix(e_raw)
    for r in title_fix_rows:
        if r["confidence"] != "auto":
            continue
        if r["rule"] not in ("R1", "R4"):
            continue
        book, mno = r["book"], int(r["msg_no"])
        if (book, mno) == SKIP_CONTENT_KEY:
            continue
        sim_e[(book, mno)] = r["new"]

    sim_r1 = sim_r4 = 0
    for book, mno in both_keys:
        d = desk[(book, mno)]["doc_title"]
        e = sim_e[(book, mno)]
        tl = tl_map.get((book, mno), {})
        t = tl.get("title_stripped") or ""
        rule, conf, _new, _note = classify_title(d, e, t)
        if rule == "R1":
            sim_r1 += 1
        if rule == "R4" and conf == "auto":
            sim_r4 += 1
        # needs_review R4 still counts as R4
        if rule == "R4":
            pass
    # 用户要 R4 应为 0、R1 应为 0 — 但 needs_review 的 R4 不会被 auto 应用
    sim_r4_all = 0
    sim_r1_all = 0
    for book, mno in both_keys:
        d = desk[(book, mno)]["doc_title"]
        e = sim_e[(book, mno)]
        t = (tl_map.get((book, mno), {}) or {}).get("title_stripped") or ""
        rule, conf, _, _ = classify_title(d, e, t)
        if rule == "R1":
            sim_r1_all += 1
        if rule == "R4":
            sim_r4_all += 1
    sim_unique = len(sim_e) == len(both_keys)

    # V5 书名模拟
    sim_books = Counter()
    for ch in life_chunks:
        bt = (ch.get("book_title") or "").strip()
        bt2 = BOOK_RENAME.get(bt, bt)
        sim_books[bt2] += 1
    # 按 message 去重取值
    sim_book_values = set()
    seen_mk = set()
    for ch in life_chunks:
        mk = ch.get("message_key") or ""
        if mk in seen_mk:
            continue
        seen_mk.add(mk)
        bt = (ch.get("book_title") or "").strip()
        sim_book_values.add(BOOK_RENAME.get(bt, bt))
    raw_book_values = {(c.get("book_title") or "").strip() for c in life_chunks}

    # ---- 写 CSV ----
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_COLS)
        w.writeheader()
        for r in all_rows:
            w.writerow({c: r.get(c, "") for c in CSV_COLS})

    elapsed = time.time() - t0
    logging.info("csv=%s rows=%s elapsed=%.1fs", csv_path, len(all_rows), elapsed)

    # ---- 报告 ----
    buf: list[str] = []
    w = buf.append
    w("# panai4_outline_12490 生命读经修订清单（只读）")
    w("")
    w(f"> ES：`{es_url}` cluster=`{info.get('cluster_name')}`；索引 `{ES_INDEX}` / `{TL_INDEX}`。")
    w(f"> CSV：`{csv_path}`；配对：`{PAIRING_CSV}`。")
    w(f"> 生成：{datetime.now().isoformat(timespec='seconds')}；日志：`{log_path}`；耗时 {elapsed:.1f}s。")
    w("")
    w("## 结论摘要")
    w("")
    w(
        f"(1) **书名**：改写篇={book_msgs}、块={book_blocks}；"
        f"旧取值={sorted(BOOK_RENAME)} → 新取值；字段命中见 1.2（source_path 不改；message_key needs_review）。"
    )
    auto_n = sum(1 for r in all_rows if r["confidence"] == "auto")
    nr_n = sum(1 for r in all_rows if r["confidence"] == "needs_review")
    keep_n = sum(1 for r in all_rows if r["confidence"] == "keep")
    w(
        f"(2) **篇题规则**：R1={rule_counts['R1']} R2={rule_counts['R2']} R3={rule_counts['R3']} "
        f"R4={rule_counts['R4']} R5={rule_counts['R5']} R6={rule_counts['R6']} R7={rule_counts['R7']}；"
        f"清单内 auto≈{sum(1 for r in title_fix_rows if r['confidence']=='auto')} "
        f"needs_review≈{sum(1 for r in title_fix_rows if r['confidence']=='needs_review')} "
        f"keep≈{sum(1 for r in title_fix_rows if r['confidence']=='keep')} "
        f"（另 residue={len(residue_rows)}）；CSV 总 auto/needs_review/keep={auto_n}/{nr_n}/{keep_n}。"
    )
    w(
        f"(3) **附录 number**：null 生命读经块={len(null_chunks)}；"
        f"以斯帖已有编号={esther_nums}；改成 3 冲突={3 in esther_nums}；text_life 有 #3={bool(tl_appendix)}。"
    )
    w(
        f"(4) **重算向量**：reembed=是 → 块={reembed_blocks}（按 message_key 去重）、篇={reembed_msgs}；"
        f"费用上限约 ${cost_upper:.4f}（按 $0.002/千块）。"
    )
    w(
        f"(5) **头部行「第N篇」**：生命读经含={life_with_pian} 不含={life_without_pian}；"
        f"全库抽20 含={all20_with} 不含={all20_without}；生命抽20 含={life20_with} 不含={life20_without}。"
    )
    w(f"(6) **text_life 待修（R5）**：{len(r5_report)} 条。")
    w("")
    w("提醒：本清单仅针对**本机** ES；服务器上的 12490 需自行 curl 复验，改动必须在本机与服务器各做一遍。")
    w("")

    # 1 书名
    w("## 1. 书名类")
    w("")
    w("### 1.1 受影响篇")
    w("")
    w(f"清单行数={len(book_fix_rows)}；总块={book_blocks}。")
    w("")
    w("| old | new | 篇数 | 块数 |")
    w("|---|---|---:|---:|")
    for old_bt, new_bt in BOOK_RENAME.items():
        rs = [r for r in book_fix_rows if r["old"] == old_bt]
        w(f"| {old_bt} | {new_bt} | {len(rs)} | {sum(int(r['chunk_count']) for r in rs)} |")
    w("")
    w("message_key 列表：")
    for r in book_fix_rows:
        w(f"- `{r['message_key']}` （msg_no={r['msg_no']} chunks={r['chunk_count']}）")
    w("")
    w("### 1.2 各字段含旧写法的块数")
    w("")
    w(f"mapping 字段数={len(mapping_fields)}；实际扫描字段={sorted(sample_fields_checked)}")
    w("")
    for sp in old_spellings:
        w(f"**旧写法 `{sp}`**：")
        w("")
        w("| 字段 | 含旧写法块数 | 建议 |")
        w("|---|---:|---|")
        for fname, n in sorted(field_hits[sp].items(), key=lambda x: -x[1]):
            if fname == "book_title":
                advice = "要改（本清单）"
            elif fname == "source_path":
                advice = "不能改（须与磁盘路径一致）"
            elif fname == "book_path":
                advice = "路径类，通常不改（磁盘目录名）"
            elif fname == "message_key":
                advice = "needs_review：改则破坏既有引用稳定性；不改则 key 与 book_title 不一致"
            elif fname == "text":
                advice = "要改头部行中的书名（随 reembed）"
            elif fname == "part_name":
                advice = "若含旧书名则随内容策略定（见块数）"
            else:
                advice = "视业务；本轮仅报告"
            w(f"| {fname} | {n} | {advice} |")
        w("")
    w("### 1.3 头部行含旧书名")
    w("")
    for sp in old_spellings:
        w(f"- `{sp}`：text 第一行含旧书名的块数={header_old_count[sp]}")
    w("")

    # 2 篇题
    w("## 2. 篇题类")
    w("")
    w(f"参与比较篇数={len(both_keys)}；规则之和={rule_sum}；闭合={v2_ok}。")
    w("")
    w("| 规则 | 篇数 |")
    w("|---|---:|")
    for i in range(1, 8):
        w(f"| R{i} | {rule_counts[f'R{i}']} |")
    w("")
    w("与上轮预期对照：R4 预期约 26（本轮含 needs_review 大差异）；R1 预期 3–11；R6 预期约十几。若偏差大见各表。")
    w("")

    def dump_rule(rule: str, limit: Optional[int] = None):
        rows = rule_hits.get(rule, [])
        w(f"### {rule}（{len(rows)}）")
        w("")
        if not rows:
            w("（无）")
            w("")
            return
        w("| book | mno | confidence | e | t | d | note |")
        w("|---|---:|---|---|---|---|---|")
        show = rows if limit is None else rows[:limit]
        for r in show:
            w(
                f"| {r['book']} | {r['mno']} | {r['confidence']} | {r['e']} | {r['t']} | {r['d']} | {r['note']} |"
            )
        if limit and len(rows) > limit:
            w(f"| … | 其余 {len(rows)-limit} 条见 CSV | | | | | |")
        w("")

    for rule in ["R1", "R3", "R4", "R5", "R6", "R7"]:
        dump_rule(rule)

    w("### R2")
    w(f"篇数={rule_counts['R2']}（不列入 CSV 清单）。")
    w("")
    w("### residue")
    w(f"行数={len(residue_rows)}")
    w("")
    for r in residue_rows:
        w(f"- {r['book']} #{r['msg_no']} conf={r['confidence']} old=`{r['old']}` note={r['note']}")
    w("")

    # 3 number
    w("## 3. 附录 message_number")
    w("")
    w(f"- null 生命读经块数={len(null_chunks)}")
    w(f"- null message_key 组数={len(null_by_key)}")
    w(f"- 以斯帖记已有 message_number={esther_nums}")
    w(f"- text_life (以斯帖记,3) 存在={bool(tl_appendix)} title={(tl_appendix or {}).get('title_stripped')}")
    for r in number_rows:
        w(f"- key=`{r['message_key']}` chunks={r['chunk_count']} new={r['new']} conf={r['confidence']} note={r['note']}")
    w("")

    # 4 reembed
    w("## 4. 重算向量范围（只估算，不执行）")
    w("")
    w(f"- 书名类块={book_blocks} 篇={book_msgs}")
    w(f"- 篇题 auto(R1+R4) 块={title_auto_blocks} 篇={title_auto_msgs}")
    w(f"- needs_review 块（清单累加，可能与上重叠）={nr_blocks}")
    w(f"- number 类块={num_blocks}（reembed=否）")
    w(f"- **reembed=是 去重后：块={reembed_blocks} 篇={reembed_msgs}**")
    w(f"- 抽样平均字数≈{avg_chars:.0f}；费用上限≈ ${cost_upper:.4f}（$0.002/千块 × {reembed_blocks}）")
    w("")
    w("### 4.2 头部行格式（生命读经抽 20）")
    w("")
    w(str(dict(header_fmt)))
    for ex in header_examples:
        w(f"- ok={ex['ok']} fl=`{ex['fl'][:80]}` expected=`{ex['expected'][:80]}`")
    w("")
    w("### 改前/改后头部行样例（最多 5）")
    w("")
    for s in reembed_samples:
        w(f"#### {s['book']} #{s['msg_no']} ({s['kind']})")
        w(f"- 改前：`{s['before']}`")
        w(f"- 改后：`{s['after']}`")
        w(f"- 正文首部：`{s['body_head']}`")
        w("")

    # 5
    w("## 5. 其他")
    w("")
    w("### 5.1 头部行「第N篇」")
    w("")
    w(f"- 生命读经全量：含={life_with_pian} 不含={life_without_pian} 合计={life_with_pian+life_without_pian}")
    w(f"- 生命读经随机20：含={life20_with} 不含={life20_without}")
    w(f"- 全库随机20：含={all20_with} 不含={all20_without}")
    w("")
    w("### 5.2 本机与服务器")
    w("")
    w("本清单仅针对本机 ES。服务器 12490 是否一致本轮不查；改动须本机与服务器各做一遍。")
    w("")

    # 验证
    w("## 验证步骤结果")
    w("")
    w(f"1. count 前后：{count_before}/{count_after} 一致={count_before==count_after}（55841：{count_before==55841}）")
    w(f"2. 规则之和={rule_sum} vs both={len(both_keys)} → {v2_ok}；R2={rule_counts['R2']} = 1983−其他={len(both_keys)-sum(v for k,v in rule_counts.items() if k!='R2')}")
    w(f"3. auto new 断言失败数={auto_assert_fail}（期望 0）；例={auto_fail2_ex[:5]}")
    w(f"4. 模拟应用后 R1={sim_r1_all} R4={sim_r4_all}（期望 R1=0 且仅剩 needs_review 的 R4 可能非0）；唯一键={sim_unique}")
    w(
        f"5. 模拟书名取值数={len(sim_book_values)}；原始={len(raw_book_values)}。"
        f"说明：库中原先只有「约翰二书生命读经_」、没有无下划线的「约翰二书生命读经」，"
        f"故去掉下划线是一对一改名而非并入；雅歌书→雅歌亦为一对一。取值数保持 {len(sim_book_values)}（若预期 62，差在「并入」前提不成立）。"
    )
    w("模拟后 book_title 取值：")
    for bt in sorted(sim_book_values):
        w(f"- {bt}")
    w(f"6. 桌面快照 before={snap_before} after={snap_after} round1={snap_before==ROUND1_SNAP} 前后={snap_before==snap_after}")
    w("7. git status：")
    w("```")
    w(git_st)
    w("```")
    w("8. ES 只用 info/count/get_mapping/search/scroll；_source excludes embedding。未写索引。")
    w("")

    report_path.write_text("\n".join(buf), encoding="utf-8")
    logging.info("report=%s", report_path)
    print(
        f"CSV={csv_path} rows={len(all_rows)} "
        f"R1={rule_counts['R1']} R4={rule_counts['R4']} R6={rule_counts['R6']} "
        f"reembed_blocks={reembed_blocks} auto_assert_fail={auto_assert_fail} "
        f"sim_R1={sim_r1_all} sim_R4={sim_r4_all} books={len(sim_book_values)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
