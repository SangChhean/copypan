# -*- coding: utf-8 -*-
"""只读勘探桌面「生命读经」纲目 docx，并与本机 panai4_text_life 对齐。

约束：
- 桌面源目录只读（不写、不移、不改名）
- 不改 outline/ 既有代码（只 import）
- 不碰 3.5 / kg_rag；不对 ES 做任何写入
- 不打印 / 不落盘密钥

用法（在 back_mic/backend 下）::

    python -m panai4.outline.probe_life_outline
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import random
import re
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
    mapped_style_names,
    normalize_label,
    parse_msg_filename,
    read_paragraphs,
    split_label_body,
    strip_dir_index,
)

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

LIFE_ROOT_DEFAULT = Path(r"C:\Users\28121\Desktop\生命读经")
REPO_ROOT = Path(__file__).resolve().parents[4]
REPORT_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_outline_probe.md"
LOG_DIR_DEFAULT = REPO_ROOT / "logs"
ES_INDEX = "panai4_text_life"
SAMPLE_SEED = 20261106

_MSG_STEM_RE = re.compile(r"^msg\.\s*(\d+)\s+(.+)$", re.IGNORECASE)
_CN_MSG_RE = re.compile(
    r"^第([一二三四五六七八九十百千零〇两0-9]+)篇([\s\u3000].*)?$"
)
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
    log_path = log_dir / f"life_outline_probe_{stamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.info("log_path=%s", log_path)
    return log_path


# ---------------------------------------------------------------------------
# 快照 / 清单
# ---------------------------------------------------------------------------


def folder_snapshot(root: Path) -> dict:
    """文件数 + 总字节数 + 最大修改时间（只读 stat）。"""
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


def count_files_two_ways(root: Path) -> dict:
    walk_n = 0
    for _dirpath, _dirs, names in os.walk(root):
        walk_n += len(names)
    rglob_n = sum(1 for p in root.rglob("*") if p.is_file())
    return {"os_walk": walk_n, "pathlib_rglob": rglob_n, "equal": walk_n == rglob_n}


def inventory(root: Path) -> dict:
    docx: list[Path] = []
    non_docx: list[dict] = []
    empty: list[str] = []
    temp: list[str] = []
    by_subdir: dict[str, int] = Counter()
    depths: Counter = Counter()
    all_rel_dirs: set[str] = set()

    for dirpath, dirnames, names in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""
            depth = 0
        else:
            depth = rel_dir.count(os.sep) + 1
            all_rel_dirs.add(rel_dir.replace("\\", "/"))
        depths[depth] += 1
        for name in names:
            abs_path = Path(dirpath) / name
            rel = abs_path.relative_to(root).as_posix()
            try:
                size = abs_path.stat().st_size
            except OSError:
                size = -1
            if name.startswith("~$"):
                temp.append(rel)
                non_docx.append({"rel": rel, "kind": "temp_~$", "size": size})
                continue
            lower = name.lower()
            if lower.endswith(".docx"):
                docx.append(abs_path)
                top = rel.split("/", 1)[0] if "/" in rel else "(root)"
                by_subdir[top] += 1
                if size == 0:
                    empty.append(rel)
            else:
                ext = Path(name).suffix.lower() or "(noext)"
                kind = "doc" if lower.endswith(".doc") else f"other{ext}"
                non_docx.append({"rel": rel, "kind": kind, "size": size})
                if size == 0:
                    empty.append(rel)

    docx.sort(key=lambda p: p.as_posix().lower())
    return {
        "docx": docx,
        "docx_n": len(docx),
        "non_docx": non_docx,
        "empty": empty,
        "temp": temp,
        "by_subdir": dict(sorted(by_subdir.items(), key=lambda kv: _subdir_sort_key(kv[0]))),
        "depths": dict(sorted(depths.items())),
        "rel_dirs": sorted(all_rel_dirs),
        "max_depth": max(depths) if depths else 0,
    }


def _subdir_sort_key(name: str):
    m = re.match(r"^(\d+)\s+", name)
    if m:
        return (0, int(m.group(1)), name)
    return (1, 0, name)


def parse_life_filename(path: Path, root: Path) -> dict:
    """从相对路径推出书名 / 篇号 / 篇题。"""
    rel = path.relative_to(root).as_posix()
    parts = rel.split("/")
    book_dir = parts[0] if len(parts) >= 2 else ""
    book_title = strip_dir_index(book_dir) if book_dir else ""
    # 个别目录末尾带下划线
    book_title_clean = book_title.rstrip("_").strip()
    parsed = parse_msg_filename(path.name)
    stem = path.stem
    m = _MSG_STEM_RE.match(stem)
    pattern_ok = bool(m) and parsed.get("msg_no") is not None
    return {
        "rel": rel,
        "book_dir": book_dir,
        "book_title": book_title_clean,
        "book_title_raw": book_title,
        "msg_no": parsed.get("msg_no"),
        "title": parsed.get("title") or "",
        "msg_label": parsed.get("msg_label"),
        "pattern_ok": pattern_ok,
        "stem": stem,
    }


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


def int_to_cn(n: int) -> str:
    """1..999 → 中文数字（生命读经篇号常用）。"""
    if n <= 0:
        return str(n)
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n - 10] if n > 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        return digits[tens] + "十" + (digits[ones] if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        if rest == 0:
            return digits[hundreds] + "百"
        if rest < 10:
            return digits[hundreds] + "百零" + digits[rest]
        return digits[hundreds] + "百" + int_to_cn(rest)
    return str(n)


def normalize_space(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u3000", " ").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# 桌面目录名 ↔ text_life book_title 的已知用字差异（勘探用，不写回解析器）
BOOK_ALIASES = {
    "列王纪生命读经": "列王记生命读经",
    "列王记生命读经": "列王记生命读经",
    "哥林多前书生命读经": "歌林多前书生命读经",
    "歌林多前书生命读经": "歌林多前书生命读经",
    "哥林多后书生命读经": "歌林多后书生命读经",
    "歌林多后书生命读经": "歌林多后书生命读经",
    "腓立比书生命读经": "腓利比书生命读经",
    "腓利比书生命读经": "腓利比书生命读经",
    "雅歌书生命读经": "雅歌生命读经",
    "雅歌生命读经": "雅歌生命读经",
}


def normalize_book_title(s: str) -> str:
    s = normalize_space(s)
    return BOOK_ALIASES.get(s, s)


def is_dirty_book_title(s: str) -> bool:
    """ES 里偶发把篇题片段拼进 book_title（含逗号/「第…篇」）。"""
    if not s:
        return True
    if "，" in s or "," in s:
        return True
    if re.search(r"第.+篇", s):
        return True
    return False


def desktop_pair_key(meta: dict) -> tuple[str, int, str]:
    return (
        normalize_space(meta.get("book_title") or ""),
        int(meta["msg_no"]) if meta.get("msg_no") is not None else -1,
        normalize_space(meta.get("title") or ""),
    )


def parse_es_message_title(message_title: str) -> dict:
    """解析 text_life 的 message_title：通常「第N篇　篇题」。"""
    raw = message_title or ""
    m = _CN_MSG_RE.match(raw.strip())
    if not m:
        return {"msg_no": None, "title": raw.strip(), "raw": raw, "has_cn_pian": False}
    msg_no = cn_to_int(m.group(1))
    rest = (m.group(2) or "").lstrip(" \u3000")
    return {
        "msg_no": msg_no,
        "title": rest,
        "raw": raw,
        "has_cn_pian": True,
        "cn_num": m.group(1),
    }


# ---------------------------------------------------------------------------
# 段首编号分类
# ---------------------------------------------------------------------------

_LEVEL1_RE = re.compile(r"^[壹贰叁肆伍陆柒捌玖拾]+")
_LEVEL2_RE = re.compile(r"^[一二三四五六七八九十百千零〇两]+")
_ABC_RE = re.compile(r"^[A-Za-zａ-ｚＡ-Ｚ]+")
_DIGIT_RE = re.compile(r"^[0-9０-９]+")
_PAREN_RE = re.compile(r"^[（(]")


def classify_lead_number(text: str) -> str:
    raw = (text or "").lstrip(" \t\u3000")
    if not raw:
        return "empty"
    label, _body, kind = split_label_body(raw)
    norm = normalize_label(label)
    if not norm:
        return "other"
    if re.fullmatch(r"[壹贰叁肆伍陆柒捌玖拾]+", norm):
        return "壹贰叁"
    if re.fullmatch(r"[一二三四五六七八九十百千零〇两]+", norm):
        return "一二三"
    if re.fullmatch(r"[a-z]+", norm):
        return "ABC"
    if re.fullmatch(r"[0-9]+", norm):
        return "123"
    if norm.startswith("（"):
        inner = norm.strip("（）")
        if re.fullmatch(r"[一二三四五六七八九十百千零〇两]+", inner):
            return "（一二三）"
        if re.fullmatch(r"[0-9]+", inner):
            return "（123）"
        if re.fullmatch(r"[a-z]+", inner):
            return "（abc）"
        return "（其他）"
    # 有样式编号但切开失败
    if _LEVEL1_RE.match(raw):
        return "壹贰叁"
    if _LEVEL2_RE.match(raw):
        return "一二三"
    if _ABC_RE.match(raw):
        return "ABC"
    if _DIGIT_RE.match(raw):
        return "123"
    if _PAREN_RE.match(raw):
        return "（其他）"
    return "other"


# ---------------------------------------------------------------------------
# B：python-docx 读样式
# ---------------------------------------------------------------------------


def read_with_python_docx(path: Path) -> tuple[list[dict], Optional[str]]:
    try:
        from docx import Document
    except ImportError:
        return [], "python-docx 未安装"
    try:
        doc = Document(str(path))
    except Exception as exc:  # noqa: BLE001
        return [], f"python-docx 打开失败：{exc}"
    out = []
    for i, para in enumerate(doc.paragraphs):
        style = para.style.name if para.style is not None else ""
        text = para.text or ""
        out.append({"para_no": i, "style": style, "text": text})
    return out, None


# ---------------------------------------------------------------------------
# ES 只读
# ---------------------------------------------------------------------------


def make_local_es():
    from elasticsearch import Elasticsearch

    load_dotenv(_backend_env())
    host = os.getenv("ES_HOST", "localhost")
    port = os.getenv("ES_PORT", "9200")
    user = os.getenv("ES_USERNAME", "elastic")
    pw = os.getenv("ES_PASSWORD", "")
    url = f"http://{host}:{port}"
    es = Elasticsearch(
        hosts=[url],
        basic_auth=(user, pw),
        request_timeout=60,
        max_retries=0,
        retry_on_timeout=False,
    )
    return es, {"url": url, "host": host, "port": port, "auth": bool(pw)}


def fetch_text_life_pairs(es) -> dict:
    """只读 scan 收集不重复 (book_title, message_title)。

    注意：本机 mapping 里 `message_title` 是 text、无 `.keyword`；
    另有整型 `message_number`，一并取回便于对齐。
    """
    from elasticsearch.helpers import scan

    pairs: set[tuple[str, str]] = set()
    # (book, message_title) -> message_number（众数）
    pair_msg_no: dict[tuple[str, str], Counter] = defaultdict(Counter)
    book_counts: Counter = Counter()
    scanned = 0
    for doc in scan(
        es,
        index=ES_INDEX,
        query={"query": {"match_all": {}}},
        _source=["book_title", "message_title", "message_number"],
        size=500,
        preserve_order=False,
    ):
        scanned += 1
        src = doc.get("_source") or {}
        book = (src.get("book_title") or "").strip()
        msg = (src.get("message_title") or "").strip()
        if not book and not msg:
            continue
        key = (book, msg)
        if key not in pairs:
            pairs.add(key)
            book_counts[book] += 1
        mno = src.get("message_number")
        if mno is not None:
            try:
                pair_msg_no[key][int(mno)] += 1
            except (TypeError, ValueError):
                pass
    # 每个 pair 取出现最多的 message_number
    pair_number = {
        k: (c.most_common(1)[0][0] if c else None) for k, c in pair_msg_no.items()
    }
    return {
        "pairs": pairs,
        "pair_number": pair_number,
        "book_counts": book_counts,
        "scanned": scanned,
        "pages": None,
        "doc_count": es.count(index=ES_INDEX)["count"],
        "note": "message_title 无 keyword；用 scan 去重。对齐优先用 message_number。",
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run(root: Path, report_path: Path, log_path: Path) -> int:
    t0 = time.time()
    logging.info("LIFE_ROOT=%s", root)
    if not root.is_dir():
        logging.error("源目录不存在：%s", root)
        return 2

    snap_before = folder_snapshot(root)
    logging.info("snapshot_before=%s", snap_before)

    counts = count_files_two_ways(root)
    logging.info("file_counts=%s", counts)

    inv = inventory(root)
    logging.info("docx=%s non_docx=%s empty=%s temp=%s", inv["docx_n"], len(inv["non_docx"]), len(inv["empty"]), len(inv["temp"]))

    # ---- A3 命名 ----
    metas = [parse_life_filename(p, root) for p in inv["docx"]]
    bad_names = [m for m in metas if not m["pattern_ok"]]
    n = len(metas)
    sample_idx = sorted(
        set(
            list(range(min(10, n)))
            + list(range(max(0, n // 2 - 5), min(n, n // 2 + 5)))
            + list(range(max(0, n - 10), n))
        )
    )[:30]
    name_samples = [metas[i] for i in sample_idx]

    # ---- 段落长度（用现有 zip 解析，顺带为 C 做准备）----
    rng = random.Random(SAMPLE_SEED)
    mapped = mapped_style_names()

    style_para_counts: Counter = Counter()
    style_file_counts: Counter = Counter()
    lead_counts: Counter = Counter()
    unmapped_style_paras: Counter = Counter()
    unmapped_style_files: dict[str, set] = defaultdict(set)

    header_role_files = {
        "title_in_doc": [],
        "bible_reading": [],
        "series": [],
        "excerpt_marker": [],
        "summary_like": [],
    }

    parse_ok: list[dict] = []
    parse_fail: list[dict] = []
    blank_or_unopenable: list[dict] = []
    zero_level: list[str] = []
    single_level: list[dict] = []
    min_level_hist: Counter = Counter()
    max_level_hist: Counter = Counter()
    level_span_hist: Counter = Counter()  # (min,max) as "a-b"
    content_hashes: dict[str, list[str]] = defaultdict(list)
    book_msg_files: dict[tuple[str, int], list[str]] = defaultdict(list)
    para_lens: list[tuple[int, str, Path]] = []  # (n_para, rel, path)

    # python-docx 样例缓存
    py_docx_cache: dict[str, list[dict]] = {}

    total = inv["docx_n"]
    for i, path in enumerate(inv["docx"], 1):
        meta = metas[i - 1]
        rel = meta["rel"]
        if i % 200 == 0 or i == total:
            logging.info("parse progress %s/%s", i, total)

        paragraphs, err = read_paragraphs(str(path))
        if err:
            blank_or_unopenable.append({"rel": rel, "reason": err, "kind": "unopenable"})
            parse_fail.append({"rel": rel, "error": err})
            continue
        if not paragraphs:
            blank_or_unopenable.append({"rel": rel, "reason": "无段落", "kind": "blank"})
            parse_fail.append({"rel": rel, "error": "无段落"})
            continue
        nonempty = [p for p in paragraphs if (p.get("text") or "").strip()]
        if not nonempty:
            blank_or_unopenable.append({"rel": rel, "reason": "全部空白段落", "kind": "blank"})
            # 仍算「打开成功但空白」；C 闭合时单独计
            analyzed = analyze_document(paragraphs, None, title_hint=meta.get("title") or "")
            parse_ok.append(
                {
                    "rel": rel,
                    "meta": meta,
                    "points": [],
                    "analyzed": analyzed,
                    "blank": True,
                }
            )
            zero_level.append(rel)
            para_lens.append((0, rel, path))
            continue

        # 样式 / 段首编号
        styles_in_file = set()
        for para in paragraphs:
            st = para.get("style") or ""
            style_para_counts[st] += 1
            styles_in_file.add(st)
            text = para.get("text") or ""
            if text.strip():
                lead_counts[classify_lead_number(text)] += 1
        for st in styles_in_file:
            style_file_counts[st] += 1
            if st not in mapped:
                unmapped_style_paras[st] += style_para_counts[st]  # will overcount; fix below
                unmapped_style_files[st].add(rel)

        # 修正未覆盖样式段落数：上面循环里重复累加了，下面重算
        # （放循环外统一重算更干净；此处先记 file 集合）

        # 内容 hash（非空段落文本）
        blob = "\n".join((p.get("text") or "") for p in paragraphs)
        digest = hashlib.sha1(blob.encode("utf-8", errors="replace")).hexdigest()
        content_hashes[digest].append(rel)

        if meta.get("msg_no") is not None:
            book_msg_files[(meta["book_title"], meta["msg_no"])].append(rel)

        para_lens.append((len(paragraphs), rel, path))

        analyzed = analyze_document(
            paragraphs,
            None,
            title_hint=meta.get("title") or "",
        )
        points = analyzed.get("points") or []
        parse_ok.append(
            {
                "rel": rel,
                "meta": meta,
                "points": points,
                "analyzed": analyzed,
                "blank": False,
            }
        )

        # 篇头非纲目
        dh = analyzed.get("doc_header") or {}
        for role in ("title_in_doc", "bible_reading", "series"):
            if dh.get(role):
                key = f"_{role}_n"
                header_role_files[key] = header_role_files.get(key, 0) + 1
                if len(header_role_files[role]) < 3:
                    header_role_files[role].append((rel, (dh.get(role) or "")[:80]))
        # 摘录 / 摘要类
        style_set = set(analyzed.get("style_counts") or {})
        if style_set & config.EXCERPT_MARKER_STYLES:
            header_role_files["_excerpt_n"] = header_role_files.get("_excerpt_n", 0) + 1
            if len(header_role_files["excerpt_marker"]) < 3:
                header_role_files["excerpt_marker"].append((rel, "含摘录标志样式"))
        # 文本命中摘要标志
        joined = "\n".join((p.get("text") or "") for p in paragraphs[:30])
        if any(m in joined for m in ("职事信息摘要", "职事信息摘录", "信息摘要", "听抄信息")):
            header_role_files["_summary_n"] = header_role_files.get("_summary_n", 0) + 1
            if len(header_role_files["summary_like"]) < 3:
                header_role_files["summary_like"].append((rel, "篇首区出现摘要/摘录文字"))

        if not points:
            zero_level.append(rel)
            min_level_hist["none"] += 1
            max_level_hist["none"] += 1
        else:
            levels = [p["level"] for p in points]
            mn, mx = min(levels), max(levels)
            min_level_hist[mn] += 1
            max_level_hist[mx] += 1
            level_span_hist[f"{mn}-{mx}"] += 1
            if mn == mx:
                single_level.append({"rel": rel, "level": mn, "n_points": len(points)})

    # 重算未覆盖样式段落数（按 style_para_counts）
    unmapped_style_paras = Counter(
        {st: style_para_counts[st] for st in style_para_counts if st not in mapped}
    )

    # ---- B1 随机 10 篇（含最短最长）----
    para_lens_sorted = sorted(para_lens, key=lambda x: x[0])
    shortest = para_lens_sorted[0] if para_lens_sorted else None
    longest = para_lens_sorted[-1] if para_lens_sorted else None
    candidates = [x for x in para_lens if x[0] > 0]
    pick_set: list[tuple[int, str, Path]] = []
    if shortest:
        pick_set.append(shortest)
    if longest and (not shortest or longest[1] != shortest[1]):
        pick_set.append(longest)
    remain = [x for x in candidates if x[1] not in {p[1] for p in pick_set}]
    rng.shuffle(remain)
    for item in remain:
        if len(pick_set) >= 10:
            break
        pick_set.append(item)
    # 若全空白导致不够，再补
    while len(pick_set) < min(10, len(para_lens)):
        for item in para_lens:
            if item[1] not in {p[1] for p in pick_set}:
                pick_set.append(item)
                break
        else:
            break

    sample_paras_report = []
    for npara, rel, path in pick_set[:10]:
        paras, err = read_with_python_docx(path)
        if err:
            # 回退现有解析器
            paras, err2 = read_paragraphs(str(path))
            note = f"python-docx失败({err})；回退 zip 解析"
            if err2:
                sample_paras_report.append({"rel": rel, "npara": npara, "error": err2, "note": note})
                continue
        else:
            note = "python-docx"
        rows = []
        for para in paras[:15]:
            text = (para.get("text") or "").replace("\n", "\\n")
            rows.append({"style": para.get("style") or "", "text20": text[:20]})
        sample_paras_report.append(
            {"rel": rel, "npara": npara if npara else len(paras), "rows": rows, "note": note}
        )
        py_docx_cache[rel] = paras

    # ---- C2 随机 5 篇对照 ----
    ok_with_points = [r for r in parse_ok if r["points"]]
    rng2 = random.Random(SAMPLE_SEED + 1)
    spot = ok_with_points[:]
    rng2.shuffle(spot)
    spot = spot[:5]
    spot_report = []
    for rec in spot:
        pts = rec["points"][:10]
        spot_report.append(
            {
                "rel": rec["rel"],
                "items": [
                    {
                        "level": p["level"],
                        "label": p.get("label") or "",
                        "text40": (p.get("text") or "")[:40],
                        "style": p.get("style") or "",
                        "para_no": p.get("para_no"),
                    }
                    for p in pts
                ],
            }
        )

    # ---- D ES ----
    es_section: dict[str, Any] = {"ok": False}
    try:
        es, es_meta = make_local_es()
        # 短超时探测
        if not es.ping():
            raise ConnectionError("es.ping() returned False")
        info = es.info()
        if not es.indices.exists(index=ES_INDEX):
            raise RuntimeError(f"index {ES_INDEX} missing")
        life = fetch_text_life_pairs(es)
        es_section = {
            "ok": True,
            "url": es_meta["url"],
            "cluster": info.get("cluster_name"),
            "version": info.get("version", {}).get("number"),
            "doc_count": life["doc_count"],
            "pair_count": len(life["pairs"]),
            "book_counts": dict(sorted(life["book_counts"].items())),
            "books": sorted(life["book_counts"].keys()),
            "pairs": life["pairs"],
            "pair_number": life["pair_number"],
            "scanned": life["scanned"],
            "pages": life["pages"],
            "note": life.get("note"),
        }
        logging.info(
            "ES ok url=%s pairs=%s docs=%s scanned=%s",
            es_meta["url"],
            len(life["pairs"]),
            life["doc_count"],
            life["scanned"],
        )
    except Exception as exc:  # noqa: BLE001
        es_section = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "url": f"http://{os.getenv('ES_HOST', 'localhost')}:{os.getenv('ES_PORT', '9200')}",
        }
        logging.exception("ES read failed")

    # ---- 对齐 ----
    align: dict[str, Any] = {}
    if es_section.get("ok"):
        # 桌面侧键：多种匹配策略
        desktop_records = []
        for rec in parse_ok:
            meta = rec["meta"]
            if meta.get("msg_no") is None:
                continue
            desktop_records.append(meta)
        # 也包含打不开的？对齐按「桌面有文件名可推出的篇」——用全部 metas
        desktop_all = [m for m in metas if m.get("msg_no") is not None]

        es_parsed = []
        pair_number = es_section.get("pair_number") or {}
        for book, msg in es_section["pairs"]:
            parsed = parse_es_message_title(msg)
            mno_field = pair_number.get((book, msg))
            mno = mno_field if mno_field is not None else parsed.get("msg_no")
            es_parsed.append(
                {
                    "book_title": book,
                    "message_title": msg,
                    "msg_no": mno,
                    "title": parsed.get("title") or "",
                    "has_cn_pian": parsed.get("has_cn_pian"),
                    "cn_num": parsed.get("cn_num"),
                    "msg_no_from": "message_number"
                    if mno_field is not None
                    else ("title_parse" if parsed.get("msg_no") is not None else None),
                }
            )

        # 精确：归一化 book + msg_no + 归一化 title
        def dkey(m):
            return (
                normalize_book_title(m["book_title"]),
                m["msg_no"],
                normalize_space(m["title"]),
            )

        def ekey(e):
            return (
                normalize_book_title(e["book_title"]),
                e["msg_no"] if e["msg_no"] is not None else -1,
                normalize_space(e["title"]),
            )

        # 宽松：只 book + msg_no（含书名别名归一）
        def dkey_bn(m):
            return (normalize_book_title(m["book_title"]), m["msg_no"])

        def ekey_bn(e):
            return (
                normalize_book_title(e["book_title"]),
                e["msg_no"] if e["msg_no"] is not None else -1,
            )

        # 原始（不做书名别名）对照，用于报告「别名可挽回多少」
        def dkey_bn_raw(m):
            return (normalize_space(m["book_title"]), m["msg_no"])

        def ekey_bn_raw(e):
            return (
                normalize_space(e["book_title"]),
                e["msg_no"] if e["msg_no"] is not None else -1,
            )

        dset = {dkey(m) for m in desktop_all}
        eset = {ekey(e) for e in es_parsed if e["msg_no"] is not None}
        both_exact = dset & eset
        desk_only_exact = dset - eset
        es_only_exact = eset - dset

        dset_bn = {dkey_bn(m) for m in desktop_all}
        eset_bn = {ekey_bn(e) for e in es_parsed if e["msg_no"] is not None}
        both_bn = dset_bn & eset_bn
        desk_only_bn = dset_bn - eset_bn
        es_only_bn = eset_bn - dset_bn

        dset_bn_raw = {dkey_bn_raw(m) for m in desktop_all}
        eset_bn_raw = {ekey_bn_raw(e) for e in es_parsed if e["msg_no"] is not None}
        both_bn_raw = len(dset_bn_raw & eset_bn_raw)

        # 书名差异探测（原始名 / 别名归一后 / 脏 book_title）
        desk_books = {normalize_space(m["book_title"]) for m in desktop_all}
        es_books_all = {normalize_space(e["book_title"]) for e in es_parsed}
        es_books_clean = {b for b in es_books_all if not is_dirty_book_title(b)}
        es_books_dirty = sorted(b for b in es_books_all if is_dirty_book_title(b))
        books_both = sorted(desk_books & es_books_clean)
        books_desk_only = sorted(desk_books - es_books_clean)
        books_es_only = sorted(es_books_clean - desk_books)
        desk_books_alias = {normalize_book_title(b) for b in desk_books}
        es_books_alias = {normalize_book_title(b) for b in es_books_clean}
        books_both_alias = sorted(desk_books_alias & es_books_alias)
        books_desk_only_alias = sorted(desk_books_alias - es_books_alias)
        books_es_only_alias = sorted(es_books_alias - desk_books_alias)

        # 对 bn 未匹配的分类
        mismatch_examples = {
            "book_diff": [],
            "title_diff_same_no": [],
            "space_variant": [],
            "msg_no_parse_fail": [],
            "dirty_es_book": [],
            "other": [],
        }
        # 建索引：book_norm -> msg_no -> [titles]
        desk_by_bn: dict[tuple[str, int], list[str]] = defaultdict(list)
        for m in desktop_all:
            desk_by_bn[dkey_bn(m)].append(m["title"])
        es_by_bn: dict[tuple[str, int], list[str]] = defaultdict(list)
        for e in es_parsed:
            if e["msg_no"] is None:
                mismatch_examples["msg_no_parse_fail"].append(
                    (e["book_title"], e["message_title"])
                )
                continue
            es_by_bn[ekey_bn(e)].append(e["title"])
            if is_dirty_book_title(e["book_title"]) and len(mismatch_examples["dirty_es_book"]) < 5:
                mismatch_examples["dirty_es_book"].append(
                    (e["book_title"], e["message_title"], e["msg_no"])
                )

        for key in sorted(desk_only_bn)[:5000]:
            book, mno = key
            alt_books = [
                b
                for b in es_books_alias
                if b != book and (book.replace("生命读经", "") in b or b.replace("生命读经", "") in book)
            ]
            if book not in es_books_alias:
                if len(mismatch_examples["book_diff"]) < 5:
                    mismatch_examples["book_diff"].append(
                        {
                            "desktop": (book, mno, desk_by_bn[key][:1]),
                            "hint_es_books": alt_books[:5] or books_es_only_alias[:5],
                        }
                    )
                continue
            if len(mismatch_examples["other"]) < 5:
                mismatch_examples["other"].append(
                    {"desktop": (book, mno, desk_by_bn[key]), "reason": "ES 无此 book+msg_no（别名归一后）"}
                )

        # 同 book+no 两边都有但 title 不同（exact 失败、bn 成功）
        for key in both_bn:
            dtitles = {normalize_space(t) for t in desk_by_bn[key]}
            etitles = {normalize_space(t) for t in es_by_bn[key]}
            if dtitles != etitles:
                # 检查空格变体
                dt2 = {re.sub(r"\s+", "", t) for t in dtitles}
                et2 = {re.sub(r"\s+", "", t) for t in etitles}
                if dt2 & et2:
                    if len(mismatch_examples["space_variant"]) < 5:
                        mismatch_examples["space_variant"].append(
                            {
                                "book": key[0],
                                "msg_no": key[1],
                                "desktop_titles": sorted(dtitles),
                                "es_titles": sorted(etitles),
                            }
                        )
                else:
                    if len(mismatch_examples["title_diff_same_no"]) < 5:
                        mismatch_examples["title_diff_same_no"].append(
                            {
                                "book": key[0],
                                "msg_no": key[1],
                                "desktop_titles": sorted(dtitles),
                                "es_titles": sorted(etitles),
                            }
                        )

        # 篇号写法
        desktop_msg_forms = Counter()
        for m in desktop_all:
            desktop_msg_forms["filename:msg. N"] += 1
        # 抽 doc 内篇题行
        cn_in_doc = 0
        arabic_in_doc = 0
        samples_doc_title = []
        for rec in parse_ok[:]:
            title_line = (rec["analyzed"].get("doc_header") or {}).get("title_in_doc") or ""
            first = title_line.split("\n", 1)[0].strip()
            if first.startswith("第") and "篇" in first[:12]:
                cn_in_doc += 1
                if len(samples_doc_title) < 5:
                    samples_doc_title.append((rec["rel"], first[:60]))
            elif re.match(r"^\d+", first):
                arabic_in_doc += 1

        es_msg_forms = Counter()
        for e in es_parsed:
            if e.get("has_cn_pian"):
                es_msg_forms["第N篇＋篇题"] += 1
            else:
                es_msg_forms["其他"] += 1

        # ES 独有按书统计
        es_only_by_book: Counter = Counter()
        es_only_list = []
        es_lookup = {(normalize_space(e["book_title"]), e["msg_no"]): e for e in es_parsed if e["msg_no"] is not None}
        for key in sorted(es_only_bn):
            book, mno = key
            es_only_by_book[book] += 1
            e = es_lookup.get(key)
            es_only_list.append(
                {
                    "book": book,
                    "msg_no": mno,
                    "message_title": (e or {}).get("message_title", ""),
                }
            )

        desk_only_list = []
        for key in sorted(desk_only_bn):
            book, mno = key
            desk_only_list.append(
                {
                    "book": book,
                    "msg_no": mno,
                    "titles": desk_by_bn[key],
                }
            )

        align = {
            "desktop_n": len(desktop_all),
            "es_pair_n": len(es_section["pairs"]),
            "es_parsed_n": len([e for e in es_parsed if e["msg_no"] is not None]),
            "both_exact": len(both_exact),
            "desk_only_exact": len(desk_only_exact),
            "es_only_exact": len(es_only_exact),
            "both_bn": len(both_bn),
            "desk_only_bn": len(desk_only_bn),
            "es_only_bn": len(es_only_bn),
            "both_bn_raw": both_bn_raw,
            "books_both": books_both,
            "books_desk_only": books_desk_only,
            "books_es_only": books_es_only,
            "books_both_alias": books_both_alias,
            "books_desk_only_alias": books_desk_only_alias,
            "books_es_only_alias": books_es_only_alias,
            "es_books_dirty": es_books_dirty,
            "book_aliases": BOOK_ALIASES,
            "desk_only_list": desk_only_list,
            "es_only_list": es_only_list,
            "es_only_by_book": dict(es_only_by_book.most_common()),
            "mismatch_examples": mismatch_examples,
            "desktop_msg_forms": dict(desktop_msg_forms),
            "es_msg_forms": dict(es_msg_forms),
            "cn_in_doc": cn_in_doc,
            "arabic_in_doc": arabic_in_doc,
            "samples_doc_title": samples_doc_title,
            "closure_desk": len(both_bn) + len(desk_only_bn) == len(dset_bn),
            "closure_es": len(both_bn) + len(es_only_bn) == len(eset_bn),
            "desk_unique_bn": len(dset_bn),
            "es_unique_bn": len(eset_bn),
        }
        # 若桌面同书同篇多文件，dset_bn 会小于 desktop_all
        align["desktop_files_with_msg"] = len(desktop_all)
        align["desktop_unique_bn_vs_files"] = (
            f"unique(book,msg_no)={len(dset_bn)} files={len(desktop_all)}"
        )

    # ---- E 重复 ----
    dup_msg = {k: v for k, v in book_msg_files.items() if len(v) > 1}
    dup_hash = {h: v for h, v in content_hashes.items() if len(v) > 1}

    # 疑似非纲目：零层级且无标题样式
    suspect_non_outline = []
    for rec in parse_ok:
        if rec["points"]:
            continue
        styles = set((rec["analyzed"].get("style_counts") or {}))
        if not (styles & set(config.LEVEL_STYLES)):
            suspect_non_outline.append(rec["rel"])

    snap_after = folder_snapshot(root)
    logging.info("snapshot_after=%s", snap_after)

    # git status（只看 outline 目录）
    git_status = _git_outline_status()

    # C 闭合
    # A.docx = C成功 + C失败 + 空白/打不开
    # 我们把 unopenable/blank 放在 blank_or_unopenable；parse_fail 含这些
    # parse_ok 含空白段落篇；真正失败 = parse_fail
    # 更清晰：
    n_unopenable = len([x for x in blank_or_unopenable if x["kind"] == "unopenable"])
    n_blank = len([x for x in blank_or_unopenable if x["kind"] == "blank"])
    # parse_ok 包含 blank 中「可打开」的；unopenable 不在 parse_ok
    n_success = len(parse_ok)  # 含空白
    n_fail = len([x for x in parse_fail if x["rel"] not in {b["rel"] for b in blank_or_unopenable if b["kind"] == "blank"}])
    # 实际上 blank 也在 parse_fail 里对「无段落」；「全部空白」在 parse_ok
    n_fail_hard = len([f for f in parse_fail if f["rel"] in {b["rel"] for b in blank_or_unopenable if b["kind"] == "unopenable"} or f["error"] == "无段落"])
    # 简化闭合：docx = parse_ok + unopenable(+无段落)
    closure_c = inv["docx_n"] == n_success + n_unopenable + len(
        [b for b in blank_or_unopenable if b["kind"] == "blank" and b["rel"] not in {r["rel"] for r in parse_ok}]
    )
    # 更干净：每个 docx 恰好落在 parse_ok 或 hard_fail
    hard_fail_rels = {b["rel"] for b in blank_or_unopenable if b["kind"] == "unopenable"}
    hard_fail_rels |= {f["rel"] for f in parse_fail if f["error"] == "无段落"}
    ok_rels = {r["rel"] for r in parse_ok}
    closure_c = inv["docx_n"] == len(ok_rels | hard_fail_rels) and ok_rels.isdisjoint(hard_fail_rels) and len(ok_rels) + len(hard_fail_rels) == inv["docx_n"]

    report = render_report(
        root=root,
        snap_before=snap_before,
        snap_after=snap_after,
        counts=counts,
        inv=inv,
        name_samples=name_samples,
        bad_names=bad_names,
        metas=metas,
        sample_paras_report=sample_paras_report,
        style_para_counts=style_para_counts,
        style_file_counts=style_file_counts,
        lead_counts=lead_counts,
        unmapped_style_paras=unmapped_style_paras,
        unmapped_style_files=unmapped_style_files,
        mapped=mapped,
        header_role_files=header_role_files,
        parse_ok=parse_ok,
        parse_fail=[f for f in parse_fail if f["rel"] in hard_fail_rels],
        hard_fail_rels=hard_fail_rels,
        zero_level=zero_level,
        single_level=single_level,
        min_level_hist=min_level_hist,
        max_level_hist=max_level_hist,
        level_span_hist=level_span_hist,
        spot_report=spot_report,
        es_section=es_section,
        align=align,
        dup_msg=dup_msg,
        dup_hash=dup_hash,
        suspect_non_outline=suspect_non_outline,
        blank_or_unopenable=blank_or_unopenable,
        closure_c=closure_c,
        git_status=git_status,
        log_path=log_path,
        elapsed=time.time() - t0,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    logging.info("report written %s (%s chars)", report_path, len(report))
    logging.info("done in %.1fs", time.time() - t0)
    return 0


def _git_outline_status() -> str:
    import subprocess

    outline_dir = Path(__file__).resolve().parent
    try:
        out = subprocess.check_output(
            ["git", "status", "--short", "--", str(outline_dir)],
            cwd=str(REPO_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:  # noqa: BLE001
        return f"(git status failed: {exc})"
    return out.strip() or "(clean)"


def _md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|")


def render_report(**kw) -> str:
    root: Path = kw["root"]
    inv = kw["inv"]
    snap_before = kw["snap_before"]
    snap_after = kw["snap_after"]
    counts = kw["counts"]
    es = kw["es_section"]
    align = kw["align"]
    parse_ok = kw["parse_ok"]
    hard_fail = kw["parse_fail"]
    mapped = kw["mapped"]
    unmapped = kw["unmapped_style_paras"]

    n_ok_points = sum(1 for r in parse_ok if r["points"])
    n_zero = len(kw["zero_level"])
    n_fail = len(hard_fail)

    # 结论摘要
    style_cover = len(unmapped) == 0
    if es.get("ok") and align:
        both = align["both_bn"]
        desk_n = align["desk_unique_bn"]
        match_ratio = f"{both}/{desk_n}"
    else:
        match_ratio = "ES 未连通，对齐未做"

    lines: list[str] = []
    w = lines.append

    w("# 生命读经纲目只读勘探报告")
    w("")
    w(f"> 源目录：`{root}`（只读）。解析器：`panai4.outline.docx_parser`（只 import，不改）。")
    w(f"> 报告生成：{datetime.now().isoformat(timespec='seconds')}；日志：`{kw['log_path']}`。")
    w(f"> 耗时：{kw['elapsed']:.1f}s。")
    w("")
    w("## 结论摘要")
    w("")
    w(
        f"1. 桌面共 **{inv['docx_n']}** 个 docx，目录一层书卷（63 卷），命名主规律为 `msg. N 篇题.docx`，与 A 批倪李文集纲目一致（可用 `parse_msg_filename`）。"
    )
    w(
        f"2. 样式体系以 `0系列/00篇题/11读经/2大点/3中点/4小点/5a点…` 为主，与 A 批标准体系相同；未覆盖样式名 **{len(unmapped)}** 种。"
    )
    w(
        f"3. 现有解析器试解析：可打开并分析 **{len(parse_ok)}** 篇，硬失败 **{n_fail}** 篇；其中解析出 ≥1 个纲目点 **{n_ok_points}** 篇，零层级 **{n_zero}** 篇。"
    )
    if es.get("ok") and align:
        w(
            f"4. 与 `panai4_text_life` 对齐（书名别名归一 + 篇号）：**{match_ratio}**"
            f"（未做书名别名时 both={align.get('both_bn_raw')}；"
            f"桌面独有 {align.get('desk_only_bn')}，ES 独有 {align.get('es_only_bn')}）。"
        )
    else:
        w(f"4. 与 `panai4_text_life` 对齐：**{match_ratio}**。")
    if es.get("ok"):
        w(
            f"5. ES：`{es['url']}` cluster=`{es.get('cluster')}` v`{es.get('version')}`；index docs={es.get('doc_count')}；unique(book,message_title)={es.get('pair_count')}。"
        )
    else:
        w(f"5. ES 只读查询失败：`{es.get('error')}`（配置 url=`{es.get('url')}`）。")
    w(
        "6. 篇号：文件名 `msg. N`（阿拉伯）；文内 `00篇题` 与 text_life `message_title` 为「第N篇　…」；ES 另有整型 `message_number` 可直接对齐。"
    )
    w(
        "7. 待决定：生命读经是否作为新 batch；书名别名表（纪/记、哥/歌、立/利、雅歌书/雅歌）；"
        "ES 脏 book_title（夹带「第N篇」片段）是否清洗；message_title 取文件名还是文内篇题行。"
    )
    w(f"8. 快照前后一致：{snap_before == snap_after}；文件双计数一致：{counts['equal']}；C 闭合：{kw['closure_c']}。")
    w("")

    # ---- A ----
    w("## A. 文件清单")
    w("")
    w("### A1 数量")
    w("")
    w(f"- docx：**{inv['docx_n']}**")
    w(f"- 非 docx：**{len(inv['non_docx'])}**")
    w(f"- 空文件（size=0）：**{len(inv['empty'])}**")
    w(f"- 临时 `~$`：**{len(inv['temp'])}**")
    w(f"- 打不开 / 无段落：见 E / C（硬失败 {n_fail}）")
    w("")
    if inv["non_docx"]:
        w("非 docx 清单：")
        w("")
        w("| 相对路径 | 类型 | size |")
        w("|---|---|---:|")
        for item in inv["non_docx"][:200]:
            w(f"| {_md_escape(item['rel'])} | {item['kind']} | {item['size']} |")
        if len(inv["non_docx"]) > 200:
            w(f"| … | 其余 {len(inv['non_docx'])-200} 条略 | |")
        w("")
    else:
        w("非 docx：无。")
        w("")
    if inv["empty"]:
        w("空文件：")
        for rel in inv["empty"]:
            w(f"- `{rel}`")
        w("")
    else:
        w("空文件：无。")
        w("")

    w("### A2 目录结构")
    w("")
    w(f"- 最大子文件夹深度（相对根）：**{inv['max_depth']}**（生命读经为「根 / 书卷目录 / 文件」，深度 1）")
    w(f"- 子文件夹数：**{len(inv['rel_dirs'])}**")
    w("")
    w("| 子文件夹 | docx 数 |")
    w("|---|---:|")
    for name, cnt in inv["by_subdir"].items():
        w(f"| {_md_escape(name)} | {cnt} |")
    w("")
    w(f"子文件夹 docx 合计验证：{sum(inv['by_subdir'].values())} （应等于 {inv['docx_n']}）")
    w("")

    w("### A3 命名规律")
    w("")
    w("主规律：`{书卷目录}/msg. {N} {篇题}.docx`，书名 = 目录名去掉前导序号（及尾 `_`），篇号 = N，篇题 = 余下文字。")
    w(f"符合主规律：{sum(1 for m in kw['metas'] if m['pattern_ok'])} / {len(kw['metas'])}")
    w("")
    w("代表性文件名（30）：")
    w("")
    w("| # | 相对路径 | 推出的 书名 / 篇号 / 篇题 |")
    w("|---:|---|---|")
    for i, m in enumerate(kw["name_samples"], 1):
        w(
            f"| {i} | {_md_escape(m['rel'])} | { _md_escape(m['book_title'])} / {m['msg_no']} / {_md_escape(m['title'])} |"
        )
    w("")
    if kw["bad_names"]:
        w("不符合主规律（逐条）：")
        w("")
        for m in kw["bad_names"]:
            w(f"- `{m['rel']}`")
        w("")
    else:
        w("不符合主规律：无。")
        w("")

    # ---- B ----
    w("## B. 内容与样式")
    w("")
    w("### B1 随机 10 篇前 15 段（含最短/最长）")
    w("")
    for sample in kw["sample_paras_report"]:
        w(f"#### `{sample['rel']}`（段落数≈{sample.get('npara')}；{sample.get('note','')}）")
        w("")
        if sample.get("error"):
            w(f"打开失败：{sample['error']}")
            w("")
            continue
        w("| 样式 | 段首前 20 字 |")
        w("|---|---|")
        for row in sample.get("rows") or []:
            w(f"| `{_md_escape(row['style'])}` | {_md_escape(row['text20'])} |")
        w("")

    w("### B2 样式名统计（全库）")
    w("")
    w("| 样式名 | 段落数 | 出现文件数 | 已映射? |")
    w("|---|---:|---:|:---:|")
    for st, pc in kw["style_para_counts"].most_common():
        fc = kw["style_file_counts"].get(st, 0)
        flag = "Y" if st in mapped else "N"
        w(f"| `{_md_escape(st)}` | {pc} | {fc} | {flag} |")
    w("")

    w("### B3 段首编号写法")
    w("")
    w("| 类别 | 次数 |")
    w("|---|---:|")
    for k, v in kw["lead_counts"].most_common():
        w(f"| {k} | {v} |")
    w("")

    w("### B4 与 A 批样式映射覆盖")
    w("")
    w(f"config 已映射样式数：{len(mapped)}；本批出现样式数：{len(kw['style_para_counts'])}；未覆盖：**{len(unmapped)}**")
    w("")
    if unmapped:
        w("| 未覆盖样式 | 段落数 | 文件数 |")
        w("|---|---:|---:|")
        for st, pc in unmapped.most_common():
            fc = len(kw["unmapped_style_files"].get(st, []))
            w(f"| `{_md_escape(st)}` | {pc} | {fc} |")
        w("")
    else:
        w("未覆盖样式：无（全部样式名落在 LEVEL/HEADER/EXCERPT 映射表内，或仅 Normal 等已映射集合）。")
        w("")
        # Normal 若在 mapped？ mapped 不含 Normal。再确认
        if any(st not in mapped for st in kw["style_para_counts"]):
            w("（内部校验：仍有未映射，见上表逻辑）")
            w("")

    # Normal 通常不在 mapped 里——需要说明
    if "Normal" in unmapped or any(st == "Normal" for st in unmapped):
        w("说明：`Normal` 不在 LEVEL/HEADER 映射表中属预期（正文/空段），解析器靠文字轨编号识别。")
        w("")

    w("### B5 篇首非纲目内容")
    w("")
    hr = kw["header_role_files"]
    w(f"- 篇题行（title_in_doc 样式）：**{hr.get('_title_in_doc_n', 0)}** 个文件")
    for rel, text in hr.get("title_in_doc", [])[:3]:
        w(f"  - 例：`{rel}` → {text}")
    w(f"- 读经行（bible_reading / 段首「读经」）：**{hr.get('_bible_reading_n', 0)}** 个文件")
    for rel, text in hr.get("bible_reading", [])[:3]:
        w(f"  - 例：`{rel}` → {text}")
    w(f"- 系列行（series）：**{hr.get('_series_n', 0)}** 个文件")
    for rel, text in hr.get("series", [])[:3]:
        w(f"  - 例：`{rel}` → {text}")
    w(f"- 摘录标志样式：**{hr.get('_excerpt_n', 0)}** 个文件")
    for rel, text in hr.get("excerpt_marker", [])[:3]:
        w(f"  - 例：`{rel}` → {text}")
    w(f"- 篇首区出现摘要/摘录文字：**{hr.get('_summary_n', 0)}** 个文件")
    for rel, text in hr.get("summary_like", [])[:3]:
        w(f"  - 例：`{rel}` → {text}")
    w("")

    # ---- C ----
    w("## C. 试解析（内存，不写产出目录）")
    w("")
    w(f"- 成功分析（含零层级/空白正文）：**{len(parse_ok)}**")
    w(f"- 硬失败（打不开/无段落）：**{n_fail}**")
    w(f"- 其中有纲目点：**{n_ok_points}**；零层级：**{n_zero}**；单层（min=max）：**{len(kw['single_level'])}**")
    w("")
    if hard_fail:
        w("失败清单：")
        w("")
        for f in hard_fail:
            w(f"- `{f['rel']}` — {f['error']}")
        w("")
    else:
        w("失败清单：无。")
        w("")

    w("### 层级数分布")
    w("")
    w("min(level) 分布：")
    w("")
    w("| min | 篇数 |")
    w("|---|---:|")
    for k, v in sorted(kw["min_level_hist"].items(), key=lambda x: str(x[0])):
        w(f"| {k} | {v} |")
    w("")
    w("max(level) 分布：")
    w("")
    w("| max | 篇数 |")
    w("|---|---:|")
    for k, v in sorted(kw["max_level_hist"].items(), key=lambda x: str(x[0])):
        w(f"| {k} | {v} |")
    w("")
    w("span (min-max) 分布（前 30）：")
    w("")
    w("| span | 篇数 |")
    w("|---|---:|")
    for k, v in kw["level_span_hist"].most_common(30):
        w(f"| {k} | {v} |")
    w("")
    if kw["zero_level"]:
        w(f"零层级篇（{len(kw['zero_level'])}），最多列 50：")
        for rel in kw["zero_level"][:50]:
            w(f"- `{rel}`")
        if len(kw["zero_level"]) > 50:
            w(f"- … 其余 {len(kw['zero_level'])-50} 篇")
        w("")
    if kw["single_level"]:
        w(f"单层篇（{len(kw['single_level'])}），最多列 30：")
        for item in kw["single_level"][:30]:
            w(f"- `{item['rel']}` level={item['level']} points={item['n_points']}")
        w("")

    w("### C2 随机 5 篇解析对照（前 10 点）")
    w("")
    for spot in kw["spot_report"]:
        w(f"#### `{spot['rel']}`")
        w("")
        w("| level | label | text40 | style | para_no |")
        w("|---:|---|---|---|---:|")
        for it in spot["items"]:
            w(
                f"| {it['level']} | {_md_escape(it['label'])} | {_md_escape(it['text40'])} | `{_md_escape(it['style'])}` | {it['para_no']} |"
            )
        w("")

    # ---- D ----
    w("## D. 与 panai4_text_life 对齐")
    w("")
    if not es.get("ok"):
        w(f"ES 只读查询失败，本节无法完成。错误：`{es.get('error')}`")
        w(f"尝试连接：`{es.get('url')}`（来自 `back_mic/backend/.env` 的 ES_HOST/ES_PORT，不打印密钥）。")
        w("")
    else:
        w(f"- 使用的 ES：`{es['url']}`（本机；cluster=`{es.get('cluster')}` version=`{es.get('version')}`）")
        w(f"- 索引：`{ES_INDEX}` 文档数={es['doc_count']}；scan 文档数={es.get('scanned')}")
        w(f"- 说明：{es.get('note') or '—'}")
        w(f"- 不重复 (book_title, message_title)：**{es['pair_count']}**")
        w("")
        w("### D1 book_title 分布（全部）")
        w("")
        w("| book_title | 篇数(unique message_title) |")
        w("|---|---:|")
        for book, cnt in es["book_counts"].items():
            w(f"| {_md_escape(book)} | {cnt} |")
        w("")
        w("全部 book_title 列表：")
        w("")
        for book in es["books"]:
            w(f"- {book}")
        w("")

        w("### D2 集合比对（主键 = 书名别名归一 + 篇号）")
        w("")
        w("书名别名表（勘探用，差异对）：")
        w("")
        w("| 写法 A | 对齐键 |")
        w("|---|---|")
        for a, b in sorted((align.get("book_aliases") or {}).items()):
            if a != b:
                w(f"| {_md_escape(a)} | {_md_escape(b)} |")
        w("")
        w("差异类型：纪/记、哥/歌、立/利、雅歌书/雅歌。")
        w("")
        w(f"- 桌面可解析篇文件数：{align['desktop_files_with_msg']}；unique(book_alias,msg_no)={align['desk_unique_bn']}")
        w(f"- text_life unique(book_alias,msg_no)：{align['es_unique_bn']}（原始 pair={align['es_pair_n']}）")
        w(f"- **未做书名别名**时 both(book_raw,msg_no)={align.get('both_bn_raw')}")
        w(f"- **做书名别名后**两边都有：**{align['both_bn']}**")
        w(f"- 桌面有而 text_life 没有：**{align['desk_only_bn']}**")
        w(f"- text_life 有而桌面没有：**{align['es_only_bn']}**")
        w(f"- 精确三元组(book_alias,msg_no,title) 两边都有：{align['both_exact']}")
        w("")
        w("闭合验证：")
        w(f"- both+桌面独有 = 桌面 unique ? {align['both_bn']}+{align['desk_only_bn']}={align['both_bn']+align['desk_only_bn']} vs {align['desk_unique_bn']} → {align['closure_desk']}")
        w(f"- both+ES独有 = ES unique ? {align['both_bn']}+{align['es_only_bn']}={align['both_bn']+align['es_only_bn']} vs {align['es_unique_bn']} → {align['closure_es']}")
        w("")

        w("书名集合（原始，未别名；ES 已剔除脏 book_title）：")
        w(f"- 两边都有的书：{len(align['books_both'])}")
        w(f"- 仅桌面：{align['books_desk_only'] or '无'}")
        w(f"- 仅 ES（干净）：{align['books_es_only'] or '无'}")
        w(f"- ES 脏 book_title 取值数：{len(align.get('es_books_dirty') or [])}")
        w("")
        w("书名集合（别名归一后）：")
        w(f"- 两边都有：{len(align.get('books_both_alias') or [])}")
        w(f"- 仅桌面：{align.get('books_desk_only_alias') or '无'}")
        w(f"- 仅 ES：{align.get('books_es_only_alias') or '无'}")
        w("")
        if align.get("es_books_dirty"):
            w("ES 脏 book_title 样例（最多 20）：")
            w("")
            for b in (align.get("es_books_dirty") or [])[:20]:
                w(f"- `{_md_escape(b)}`")
            w("")

        w("桌面独有清单（按书+篇号）：")
        w("")
        if not align["desk_only_list"]:
            w("（空）")
        else:
            w("| book | msg_no | titles |")
            w("|---|---:|---|")
            for item in align["desk_only_list"][:300]:
                titles = " / ".join(_md_escape(t) for t in item["titles"][:3])
                w(f"| {_md_escape(item['book'])} | {item['msg_no']} | {titles} |")
            if len(align["desk_only_list"]) > 300:
                w(f"| … | | 其余 {len(align['desk_only_list'])-300} 条 |")
        w("")

        w("text_life 独有：按书缺篇数")
        w("")
        w("| book | 缺篇数 |")
        w("|---|---:|")
        for book, cnt in align["es_only_by_book"].items():
            w(f"| {_md_escape(book)} | {cnt} |")
        w("")
        w("text_life 独有明细（最多 300）：")
        w("")
        w("| book | msg_no | message_title |")
        w("|---|---:|---|")
        for item in align["es_only_list"][:300]:
            w(
                f"| {_md_escape(item['book'])} | {item['msg_no']} | {_md_escape(item['message_title'][:80])} |"
            )
        if len(align["es_only_list"]) > 300:
            w(f"| … | | 其余 {len(align['es_only_list'])-300} 条 |")
        w("")

        w("### D3 不匹配原因类型（各举至多 5 例）")
        w("")
        mex = align["mismatch_examples"]
        w("**书名写法不同**（初步：可归一化——去空白/统一「书/福音」后缀等，需人工表）")
        w("")
        for ex in mex.get("book_diff") or []:
            w(f"- desktop={ex['desktop']} hint_es={ex.get('hint_es_books')}")
        if not mex.get("book_diff"):
            w("- （无样本或书名集合已对齐）")
        w("")
        w("**同书同篇号但篇题不同**（初步：部分可接受——text_life 篇题含副题/读经摘要；建议对齐键用 book+msg_no）")
        w("")
        for ex in mex.get("title_diff_same_no") or []:
            w(
                f"- {ex['book']} #{ex['msg_no']}: desk={ex['desktop_titles']} es={ex['es_titles']}"
            )
        if not mex.get("title_diff_same_no"):
            w("- （无）")
        w("")
        w("**空格/全角变体**（初步：可用 NFKC + 空白压缩归一化解决）")
        w("")
        for ex in mex.get("space_variant") or []:
            w(
                f"- {ex['book']} #{ex['msg_no']}: desk={ex['desktop_titles']} es={ex['es_titles']}"
            )
        if not mex.get("space_variant"):
            w("- （无）")
        w("")
        w("**ES message_title 无法拆篇号**")
        w("")
        for ex in (mex.get("msg_no_parse_fail") or [])[:5]:
            w(f"- {ex}")
        if not mex.get("msg_no_parse_fail"):
            w("- （无）")
        w("")
        w("**ES 脏 book_title**（初步：需清洗或从 message_title/message_number 回填，不能单靠空白归一）")
        w("")
        for ex in mex.get("dirty_es_book") or []:
            w(f"- {ex}")
        if not mex.get("dirty_es_book"):
            w("- （无）")
        w("")
        w("**其他（别名归一后 ES 仍无此 book+msg_no）**")
        w("")
        for ex in mex.get("other") or []:
            w(f"- {ex}")
        if not mex.get("other"):
            w("- （无）")
        w("")

        w("### D4 篇号写法")
        w("")
        w(f"- 桌面文件名：{align['desktop_msg_forms']}（阿拉伯数字）")
        w(f"- 桌面文内篇题行含「第…篇」：{align['cn_in_doc']} 篇；阿拉伯开头：{align['arabic_in_doc']} 篇")
        for rel, t in align.get("samples_doc_title") or []:
            w(f"  - 例：`{rel}` → {t}")
        w(f"- text_life message_title：{align['es_msg_forms']}")
        w("- 结论：文件名篇号与 text_life 不一致（阿拉伯 vs 中文「第N篇」）；文内 `00篇题` 行与 text_life 形式一致。对齐应用整数篇号，展示用中文。")
        w("")

    # ---- E ----
    w("## E. 重复与异常")
    w("")
    w(f"### E1 同书同篇号多文件：{len(kw['dup_msg'])} 组")
    w("")
    if kw["dup_msg"]:
        for (book, mno), paths in sorted(kw["dup_msg"].items())[:100]:
            w(f"- {book} #{mno}:")
            for p in paths:
                w(f"  - `{p}`")
    else:
        w("无。")
    w("")
    w(f"### 内容重复（段落文本 SHA1）：{len(kw['dup_hash'])} 组")
    w("")
    if kw["dup_hash"]:
        for i, (_h, paths) in enumerate(kw["dup_hash"].items()):
            if i >= 50:
                w(f"- … 其余 {len(kw['dup_hash'])-50} 组")
                break
            w(f"- 组{i+1}（{len(paths)} 个文件）:")
            for p in paths:
                w(f"  - `{p}`")
    else:
        w("无。")
    w("")

    w("### E2 异常清单")
    w("")
    w(f"- 打不开/无段落：{len(kw['blank_or_unopenable'])}")
    for item in kw["blank_or_unopenable"][:100]:
        w(f"  - `{item['rel']}` — {item['reason']}")
    w(f"- 零层级：{len(kw['zero_level'])}（见 C）")
    w(f"- 疑似非纲目（零层级且无 LEVEL 样式）：{len(kw['suspect_non_outline'])}")
    for rel in kw["suspect_non_outline"][:50]:
        w(f"  - `{rel}`")
    w("")

    # ---- 验证 ----
    w("## 验证步骤结果")
    w("")
    w("### 1. 文件总数双计数")
    w("")
    w(f"- os.walk：{counts['os_walk']}")
    w(f"- pathlib.rglob：{counts['pathlib_rglob']}")
    w(f"- 相等：{counts['equal']}")
    w("")
    w("### 2. A.docx = C成功 + 硬失败")
    w("")
    w(f"- A.docx={inv['docx_n']}")
    w(f"- C成功(parse_ok)={len(parse_ok)}")
    w(f"- 硬失败={n_fail}")
    w(f"- 合计={len(parse_ok)+n_fail}；闭合={kw['closure_c']}")
    w("")
    w("### 3. D 集合闭合")
    w("")
    if es.get("ok") and align:
        w(f"- both+桌面独有={align['both_bn']}+{align['desk_only_bn']}={align['both_bn']+align['desk_only_bn']}；桌面 unique={align['desk_unique_bn']}；闭合={align['closure_desk']}")
        w(f"- both+ES独有={align['both_bn']}+{align['es_only_bn']}={align['both_bn']+align['es_only_bn']}；ES unique={align['es_unique_bn']}；闭合={align['closure_es']}")
    else:
        w("- ES 未成功，跳过（见上）。")
    w("")
    w("### 4. 桌面快照前后")
    w("")
    w(f"- before: files={snap_before['files']} bytes={snap_before['bytes']} max_mtime={snap_before['max_mtime']} ({snap_before['max_mtime_iso']})")
    w(f"- after:  files={snap_after['files']} bytes={snap_after['bytes']} max_mtime={snap_after['max_mtime']} ({snap_after['max_mtime_iso']})")
    w(f"- 一致：{snap_before == snap_after}")
    w("")
    w("### 5. git status（panai4/outline/）")
    w("")
    w("```")
    w(kw["git_status"])
    w("```")
    w("")
    w("期望：仅新增 `probe_life_outline.py`（及本报告在 docs/ 下），outline 既有文件无改动。")
    w("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读勘探生命读经纲目 docx")
    parser.add_argument("--root", default=str(LIFE_ROOT_DEFAULT))
    parser.add_argument("--report", default=str(REPORT_DEFAULT))
    parser.add_argument("--log-dir", default=str(LOG_DIR_DEFAULT))
    args = parser.parse_args(argv)
    log_path = setup_logging(Path(args.log_dir))
    # 加载 env 但不打印密钥
    load_dotenv(_backend_env())
    return run(Path(args.root), Path(args.report), log_path)


if __name__ == "__main__":
    raise SystemExit(main())
