# -*- coding: utf-8 -*-
"""只读解析 docx，并按方案做层级判定、截断与篇头提取。"""

from __future__ import annotations

import re
import zipfile
from collections import Counter
from typing import Optional

from lxml import etree

from . import config

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_HEADER_OF_STYLE = {}
for _role, _names in config.HEADER_STYLES.items():
    for _name in _names:
        _HEADER_OF_STYLE[_name] = _role

_MAPPED_STYLES = set(config.LEVEL_STYLES) | set(_HEADER_OF_STYLE) | set(
    config.EXCERPT_MARKER_STYLES
) | set(config.EXCERPT_BODY_STYLES) | set(config.EXCERPT_HEADING_STYLES)

_VOLUME_ONLY = re.compile(config.VOLUME_ONLY_RE)
_INDEX_PREFIX = re.compile(r"^\d+\s+")
_MSG_RE = re.compile(r"^(msg|lsn)\.\s*(\d+)\s*(.*)$", re.IGNORECASE)
_VERSION_RE = re.compile(r"^【([^】]*)】(.*)$")
_CONF_RE = re.compile(r"^(\d{4})-(\d{2})\s+(.*)$")
_WHITESPACE_RE = re.compile(r"[\s\u3000\u000b]+")
_HALF_PAREN_RE = re.compile(
    r"\(([0-9]+|[一二三四五六七八九十百千零〇两壹贰叁肆伍陆柒捌玖拾]+|[A-Za-z])\)"
)


def mapped_style_names() -> set:
    return set(_MAPPED_STYLES)


def _local(tag: str) -> str:
    return W + tag


def read_paragraphs(path: str) -> tuple[list[dict], Optional[str]]:
    """只读打开 docx，返回 w:body 直接子段落。失败时段落为空、第二项为原因。"""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            try:
                styles_xml = zf.read("word/styles.xml")
            except KeyError:
                styles_xml = None
            try:
                doc_xml = zf.read("word/document.xml")
            except KeyError:
                return [], "缺少 word/document.xml"
    except zipfile.BadZipFile:
        return [], "不是有效的 zip/docx"
    except OSError as exc:
        return [], f"无法打开：{exc}"

    style_names = {}
    if styles_xml:
        try:
            sroot = etree.fromstring(styles_xml)
        except etree.XMLSyntaxError as exc:
            return [], f"styles.xml 无法解析：{exc}"
        for node in sroot.iter(_local("style")):
            sid = node.get(_local("styleId"))
            name_el = node.find(_local("name"))
            if sid and name_el is not None:
                style_names[sid] = name_el.get(_local("val")) or sid

    try:
        root = etree.fromstring(doc_xml)
    except etree.XMLSyntaxError as exc:
        return [], f"document.xml 无法解析：{exc}"

    body = root.find(_local("body"))
    if body is None:
        return [], "缺少 w:body"

    paragraphs = []
    para_no = 0
    for child in body:
        if child.tag != _local("p"):
            continue
        style = "Normal"
        pPr = child.find(_local("pPr"))
        if pPr is not None:
            pStyle = pPr.find(_local("pStyle"))
            if pStyle is not None:
                sid = pStyle.get(_local("val")) or ""
                style = style_names.get(sid, sid or "Normal")
        paragraphs.append(
            {
                "para_no": para_no,
                "style": style,
                "text": _paragraph_text(child),
            }
        )
        para_no += 1
    return paragraphs, None


def _paragraph_text(p) -> str:
    parts = []
    for el in p.iter():
        tag = el.tag
        if tag == _local("t"):
            if el.text:
                parts.append(el.text)
        elif tag == _local("tab"):
            parts.append("\t")
        elif tag in (_local("br"), _local("cr")):
            parts.append("\n")
    return "".join(parts)


def classify_style_system(style_names: set) -> str:
    """六套样式体系。先看 t_（且没有强标准样式），再三位数字、大题、无数字前缀，最后标准。"""
    has_t = any(name.startswith("t_") for name in style_names)
    strong = style_names & config.STYLE_SYSTEM_STANDARD_STRONG
    standard = style_names & config.STYLE_SYSTEM_STANDARD
    if has_t and not strong:
        return "t_ 前缀"
    if style_names & config.STYLE_SYSTEM_DIGIT3:
        return "三位数字"
    if style_names & config.STYLE_SYSTEM_DATI:
        return "大题中题"
    plain = style_names & config.STYLE_SYSTEM_PLAIN
    if plain and not standard:
        return "大点中点小点"
    if standard or strong:
        return "标准"
    if plain:
        return "大点中点小点"
    return "Normal"


def normalize_label(label: str) -> str:
    """异体归一。只用于编号 label，不改正文。"""
    s = (label or "").strip().translate(config.FULLWIDTH_ALNUM_TABLE)
    for src, dst in config.LABEL_CHAR_MAP.items():
        s = s.replace(src, dst)
    for src, dst in config.CIRCLED_LABEL_MAP.items():
        if src in s:
            s = s.replace(src, dst)

    def _paren(m):
        inner = m.group(1)
        if len(inner) == 1 and "A" <= inner <= "Z":
            inner = inner.lower()
        elif len(inner) == 1 and "a" <= inner <= "z":
            inner = inner.lower()
        return "（" + inner + "）"

    s = _HALF_PAREN_RE.sub(_paren, s)
    s = "".join(ch.lower() if "A" <= ch <= "Z" else ch for ch in s)
    if s and s[-1] in "、.．":
        s = s[:-1]
    return s.strip()


def level_of_label(normalized: str) -> Optional[int]:
    """归一后的 label → 1~7；不是编号则 None。"""
    if not normalized:
        return None
    if re.fullmatch(r"（[a-z]）", normalized):
        return 7
    if re.fullmatch(r"（[0-9]+）", normalized):
        return 6
    if re.fullmatch(r"（[一二三四五六七八九十百千零〇两]+）", normalized):
        return 5
    if normalized in config.LEVEL4_DOUBLE_LETTERS or normalized in config.LEVEL4_SINGLE_LETTERS:
        return 4
    if re.fullmatch(r"[0-9]+", normalized):
        return 3
    chars = set(normalized)
    if normalized[0] in config.LEVEL1_CHARS and chars <= (
        config.LEVEL1_CHARS | config.LEVEL2_CHARS
    ):
        return 1
    if chars <= config.LEVEL2_CHARS:
        return 2
    return None


def split_label_body(raw: str) -> tuple[str, str, bool]:
    """返回 (label 原文, 正文, 是否有 Tab)。

    有 Tab 时，label 是第一个 Tab 之前的文字。
    无 Tab 时，label 取到第一个标点为止，正文是标点之后的文字。
    """
    if "\t" in raw:
        left, right = raw.split("\t", 1)
        return left.strip(), right.strip(), True
    text = raw.strip()
    for i, ch in enumerate(text):
        if ch in config.LABEL_PUNCT:
            return text[:i].strip(), text[i + 1 :].strip(), False
    return text, "", False


def match_truncate_rule(text: str) -> Optional[str]:
    """命中截断文字规则时返回 truncate_rule，否则 None。"""
    compact = _WHITESPACE_RE.sub("", text or "")
    if not compact:
        return None
    for prefix in config.TRUNCATE_FU_PREFIXES:
        if compact.startswith(prefix):
            return "text:附："
    for base in config.TRUNCATE_MARKER_BASES:
        for suffix in config.TRUNCATE_MARKER_SUFFIXES:
            if suffix == "" and base not in config.TRUNCATE_BARE_OK:
                continue
            if compact == base + suffix:
                if suffix == "":
                    return "text:" + base
                shown = "：" if suffix in (":", "：") else "。"
                return "text:" + base + shown
    return None


def _join_header(existing: str, piece: str) -> str:
    piece = piece.strip()
    if not piece:
        return existing
    if not existing:
        return piece
    return existing + "\n" + piece


def analyze_document(paragraphs: list[dict], hardcoded_para: Optional[int]) -> dict:
    """对一篇的段落做截断、层级判定和异常收集（不含文件级 id）。"""
    style_counts: Counter = Counter()
    marker_paras = []
    text_cut = None
    text_rule = None
    for para in paragraphs:
        style_counts[para["style"]] += 1
        if para["style"] in config.EXCERPT_MARKER_STYLES:
            marker_paras.append(para["para_no"])
        if text_cut is None:
            rule = match_truncate_rule(para["text"])
            if rule:
                text_cut = para["para_no"]
                text_rule = rule

    if hardcoded_para is not None:
        cut = hardcoded_para
        rule = "hardcoded"
    else:
        cut = text_cut
        rule = text_rule

    doc_header = {
        "series": "",
        "sub_series": "",
        "title_in_doc": "",
        "bible_reading": "",
    }
    points = []
    anomalies = []

    if text_cut is None and marker_paras:
        anomalies.append(
            {
                "type": "truncate_by_style_only",
                "para_no": marker_paras[0],
                "detail": "摘录样式段号=" + ",".join(str(n) for n in marker_paras),
            }
        )
    if text_cut is not None:
        early = [n for n in marker_paras if n < text_cut]
        if early:
            anomalies.append(
                {
                    "type": "truncate_text_late",
                    "para_no": text_cut,
                    "detail": "文字规则段号={0}；更早的摘录样式段号={1}".format(
                        text_cut, ",".join(str(n) for n in early)
                    ),
                }
            )

    prev_level = 0
    for para in paragraphs:
        if cut is not None and para["para_no"] >= cut:
            break
        style = para["style"]
        raw = para["text"]
        if not raw.strip():
            continue
        role = _HEADER_OF_STYLE.get(style)
        if role:
            doc_header[role] = _join_header(doc_header[role], raw)
            continue

        style_level = config.LEVEL_STYLES.get(style)
        raw_label, body, had_tab = split_label_body(raw)
        normalized = normalize_label(raw_label)
        # 文字轨：有 Tab 才认；无 Tab 时只有层级样式上的段首编号才认（方案 2.2 / 2.5）
        text_level = None
        if had_tab or style_level:
            text_level = level_of_label(normalized)

        if style_level and text_level:
            if style_level == text_level:
                level = style_level
                source = "both"
            else:
                level = style_level
                source = "style"
                anomalies.append(
                    {
                        "type": "level_conflict",
                        "para_no": para["para_no"],
                        "detail": "样式层级={0} 文字层级={1} label={2}".format(
                            style_level, text_level, normalized
                        ),
                    }
                )
            label = normalized
        elif style_level:
            level = style_level
            source = "style"
            label = raw_label.strip()
            if label not in config.KNOWN_UNNUMBERED_LABELS:
                anomalies.append(
                    {
                        "type": "unknown_label",
                        "para_no": para["para_no"],
                        "detail": "label=" + (label or "（空）"),
                    }
                )
        elif text_level:
            level = text_level
            source = "text"
            label = normalized
        else:
            continue

        jumped = (prev_level > 0 and level > prev_level + 1) or (
            prev_level == 0 and level > 1
        )
        if jumped:
            anomalies.append(
                {
                    "type": "level_jump",
                    "para_no": para["para_no"],
                    "detail": "上一点层级={0} 本点层级={1} label={2}".format(
                        prev_level, level, label
                    ),
                }
            )
        prev_level = level
        points.append(
            {
                "idx": len(points),
                "level": level,
                "label": label,
                "text": body,
                "style": style,
                "level_source": source,
                "para_no": para["para_no"],
            }
        )

    if points and not any(p["level"] == 1 for p in points):
        anomalies.append(
            {
                "type": "no_level1",
                "para_no": points[0]["para_no"],
                "detail": "纲目点 {0} 个，层级={1}".format(
                    len(points), sorted({p["level"] for p in points})
                ),
            }
        )

    if not any(doc_header.values()):
        anomalies.append(
            {
                "type": "empty_header",
                "para_no": None,
                "detail": "篇头四项全缺",
            }
        )

    for name, count in sorted(style_counts.items()):
        if name not in _MAPPED_STYLES:
            anomalies.append(
                {
                    "type": "unknown_style",
                    "para_no": None,
                    "detail": "{0} × {1}".format(name, count),
                }
            )

    levels = sorted({p["level"] for p in points})
    same_level = len(levels) == 1
    candidate = bool(
        points
        and same_level
        and levels[0] != 1
        and text_cut is None
        and hardcoded_para is None
    )

    level_counts = {}
    for p in points:
        key = str(p["level"])
        level_counts[key] = level_counts.get(key, 0) + 1

    return {
        "points": points,
        "doc_header": doc_header,
        "anomalies": anomalies,
        "style_counts": style_counts,
        "style_system": classify_style_system(set(style_counts)),
        "truncated_at": cut,
        "truncate_rule": rule,
        "text_cut": text_cut,
        "text_rule": text_rule,
        "candidate": candidate,
        "candidate_level": levels[0] if candidate else None,
        "level_counts": level_counts,
        "para_total": len(paragraphs),
    }


def strip_dir_index(name: str) -> str:
    return _INDEX_PREFIX.sub("", name, count=1)


def category_from_dirname(dirname: str) -> str:
    name = strip_dir_index(dirname)
    if name.endswith("纲目"):
        name = name[: -len("纲目")]
    return name


def book_from_dirs(dirs: list[str]) -> str:
    """最深一层含书名的目录。纯「卷一 / 卷三」再往上取。"""
    if not dirs:
        return ""
    for i in range(len(dirs) - 1, 0, -1):
        stripped = strip_dir_index(dirs[i])
        if _VOLUME_ONLY.match(stripped):
            continue
        return stripped
    return strip_dir_index(dirs[-1])


def parse_msg_filename(filename: str) -> dict:
    stem = filename[:-5] if filename.lower().endswith(".docx") else filename
    version = ""
    rest = stem
    m = _VERSION_RE.match(stem)
    if m:
        version = m.group(1)
        rest = m.group(2)
    msg_label = None
    msg_no = None
    title = rest.strip()
    m2 = _MSG_RE.match(rest.strip())
    if m2:
        msg_label = m2.group(1).lower()
        msg_no = int(m2.group(2))
        title = m2.group(3).strip()
    return {
        "version": version,
        "msg_label": msg_label,
        "msg_no": msg_no,
        "title": title,
        "stem": stem,
    }


def parse_conference_dirname(dirname: str) -> dict:
    m = _CONF_RE.match(dirname)
    if not m:
        return {"year": None, "month": None, "conference_name": dirname}
    return {
        "year": int(m.group(1)),
        "month": int(m.group(2)),
        "conference_name": m.group(3).strip(),
    }


def level1_group_token(points: list[dict]) -> list[int]:
    """每个「第 1 级点 + 其下属」的 token 估算：len(text)/1.5，与 v7 同为 int。"""
    tokens = []
    i = 0
    n = len(points)
    while i < n:
        if points[i]["level"] != 1:
            i += 1
            continue
        j = i + 1
        while j < n and points[j]["level"] > 1:
            j += 1
        lines = []
        for p in points[i:j]:
            if p["text"]:
                lines.append(p["label"] + "\t" + p["text"])
            else:
                lines.append(p["label"])
        blob = "\n".join(lines)
        tokens.append(max(0, int(len(blob) / 1.5)))
        i = j
    return tokens
