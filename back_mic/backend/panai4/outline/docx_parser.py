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


_LINE_SPLIT = re.compile(r"[\n\r\v\x0b]+")
_PAREN_LEAD = re.compile(r"^[（(][^）)]{1,8}[）)]")
_PART_RE = re.compile(r"第([一二三123])部分")


def split_label_body(raw: str, separators=None) -> tuple[str, str, str]:
    """返回 (label 原文, 正文, 切分方式)。

    切分方式：paren / sep / punct / plain。
    先剥段首 Tab 与空白（方案 2.6），再认括号编号或分隔符（方案 2.2）。
    非括号编号没有分隔符时不按编号切开。
    separators 默认只用主分隔符表；兜底重试时把全角逗号并进去。
    """
    if separators is None:
        separators = config.LABEL_SEPARATORS
    text = (raw or "").lstrip(" \t\u3000\n\r\v\x0b")
    matched = _PAREN_LEAD.match(text)
    if matched:
        token = matched.group(0)
        if level_of_label(normalize_label(token)):
            rest = text[matched.end() :]
            if rest[:1] in separators:
                rest = rest[1:]
            return token, rest.strip(), "paren"
    positions = []
    for sep in separators:
        idx = text.find(sep)
        if idx > 0:
            positions.append(idx)
    if positions:
        cut = min(positions)
        left = text[:cut].strip()
        right = text[cut + 1 :].strip()
        if left and level_of_label(normalize_label(left)):
            return left, right, "sep"
    stripped = text.strip()
    for i, ch in enumerate(stripped):
        if ch in config.LABEL_PUNCT:
            return stripped[:i].strip(), stripped[i + 1 :].strip(), "punct"
    return stripped, "", "plain"


def _marker_display(base: str, suffix: str) -> str:
    if suffix == "":
        return "text:" + base
    shown = "：" if suffix in (":", "：") else "。"
    return "text:" + base + shown


def marker_line_rule(line: str) -> Optional[str]:
    """一行去掉首尾空白后等于条件 A 标志时，返回 text:标志。"""
    compact = (line or "").strip()
    if not compact:
        return None
    for base in config.TRUNCATE_MARKER_BASES:
        for suffix in config.TRUNCATE_MARKER_SUFFIXES:
            if suffix == "" and base not in config.TRUNCATE_BARE_OK:
                continue
            if compact == base + suffix:
                return _marker_display(base, suffix)
    return None


def match_truncate_rule(text: str) -> Optional[str]:
    """兼容旧调用：整段压成一行后的标志，或段首「附：」。"""
    for line in _LINE_SPLIT.split(text or ""):
        hit = marker_line_rule(line)
        if hit:
            return hit
    compact = (text or "").lstrip()
    for prefix in config.TRUNCATE_FU_PREFIXES:
        if compact.startswith(prefix):
            return "text:附："
    return None


def _scan_truncation(paragraphs: list[dict]) -> dict:
    """先扫全文定截断点。条件 A 优先于「附：」。"""
    found = None
    fu_cut = None
    for para in paragraphs:
        lines = _LINE_SPLIT.split(para["text"] or "")
        if found is None:
            for index, line in enumerate(lines):
                hit = marker_line_rule(line)
                if not hit:
                    continue
                before = "\n".join(lines[:index]).strip()
                if before:
                    found = {
                        "kind": "inline",
                        "para_no": para["para_no"],
                        "rule": "text_inline:" + hit[len("text:") :],
                        "kept_text": before,
                        "cut": para["para_no"] + 1,
                        "marker_para": para["para_no"],
                    }
                else:
                    found = {
                        "kind": "whole",
                        "para_no": para["para_no"],
                        "rule": hit,
                        "kept_text": None,
                        "cut": para["para_no"],
                        "marker_para": para["para_no"],
                    }
                break
        if fu_cut is None:
            lead = (para["text"] or "").lstrip()
            if lead.startswith(config.TRUNCATE_FU_PREFIXES):
                fu_cut = para["para_no"]
    return {"marker": found, "fu_cut": fu_cut}


def _gospel_part(raw: str):
    """返回 (写入篇头的文字, (part_no, part_name) 或 None, 错字原文或 None)。"""
    original = raw or ""
    normalized = original.replace(config.GOSPEL_TYPO_FROM, config.GOSPEL_TYPO_TO)
    typo_from = original if normalized != original else None
    matched = _PART_RE.search(normalized)
    part_hit = None
    if matched:
        part_hit = config.GOSPEL_PART_NAMES.get(matched.group(1))
    return normalized, part_hit, typo_from


def is_header_bible_reading(raw: str) -> bool:
    """方案 4.5：去掉首尾空白后以「读经」开头（含各种冒号）。"""
    return (raw or "").strip().startswith(config.BIBLE_READING_LEAD)


def _join_header(existing: str, piece: str) -> str:
    piece = piece.strip()
    if not piece:
        return existing
    if not existing:
        return piece
    return existing + "\n" + piece


def analyze_document(
    paragraphs: list[dict],
    hardcoded_para: Optional[int],
    single_point: bool = False,
    title_hint: str = "",
) -> dict:
    """对一篇的段落做截断、层级判定和异常收集（不含文件级 id）。"""
    style_counts: Counter = Counter()
    marker_paras = []
    for para in paragraphs:
        style_counts[para["style"]] += 1
        if para["style"] in config.EXCERPT_MARKER_STYLES:
            marker_paras.append(para["para_no"])
    scanned = _scan_truncation(paragraphs)
    marker = scanned["marker"]
    fu_cut = scanned["fu_cut"]
    text_overrides = {}
    inline_para = None
    if hardcoded_para is not None:
        cut = hardcoded_para
        rule = "hardcoded"
        text_cut_para = None
    elif marker is not None:
        cut = marker["cut"]
        rule = marker["rule"]
        text_cut_para = marker["marker_para"]
        if marker["kind"] == "inline":
            text_overrides[marker["para_no"]] = marker["kept_text"]
            inline_para = marker["para_no"]
    elif fu_cut is not None:
        cut = fu_cut
        rule = "text:附："
        text_cut_para = fu_cut
    else:
        cut = None
        rule = None
        text_cut_para = None

    def _collect(separators):
        doc_header = {
            "series": "",
            "sub_series": "",
            "title_in_doc": "",
            "bible_reading": "",
        }
        points = []
        point_anomalies = []
        bible_prefix_hits = []
        continuations = []
        seen_outline = False
        part_no = None
        part_name = None
        merged_notes = 0
        prev_level = 0
        for para in paragraphs:
            if cut is not None and para["para_no"] >= cut:
                break
            style = para["style"]
            raw = text_overrides.get(para["para_no"], para["text"])
            if not raw.strip():
                continue
            role = _HEADER_OF_STYLE.get(style)
            if role:
                stored = raw
                if style == "11111西列":
                    stored, part_hit, typo_from = _gospel_part(raw)
                    if part_hit and part_no is None:
                        part_no, part_name = part_hit
                    if typo_from:
                        point_anomalies.append(
                            {
                                "type": "text_typo",
                                "para_no": para["para_no"],
                                "detail": "原文=" + typo_from,
                            }
                        )
                doc_header[role] = _join_header(doc_header[role], stored)
                continue

            # 方案 4.5：只认「第一个纲目点之前」。已出现纲目点之后的「读经……」仍是正文。
            if not seen_outline and is_header_bible_reading(raw):
                doc_header["bible_reading"] = _join_header(doc_header["bible_reading"], raw)
                bible_prefix_hits.append(
                    {
                        "para_no": para["para_no"],
                        "style": style,
                        "text": raw.strip(),
                    }
                )
                continue

            style_level = config.LEVEL_STYLES.get(style)
            raw_label, body, kind = split_label_body(raw, separators)
            normalized = normalize_label(raw_label)
            # 文字轨：括号编号，或带分隔符的非括号编号。层级样式上的段首编号也认。
            text_level = None
            if kind in ("paren", "sep") or style_level:
                text_level = level_of_label(normalized)

            if style_level and text_level:
                if style_level == text_level:
                    level = style_level
                    source = "both"
                else:
                    level = text_level
                    source = "text_over_style"
                    point_anomalies.append(
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
                # 段首就是标点（常见于 Word 把一句话拆成两段）。label 为空，并入上一点正文。
                if not label and points and (raw or "").lstrip()[:1] in config.LABEL_PUNCT:
                    extra = (raw or "").lstrip()
                    prev = points[-1]
                    prev["text"] = (prev["text"] + extra) if prev["text"] else extra
                    continuations.append(
                        {
                            "para_no": para["para_no"],
                            "style": style,
                            "text": extra,
                            "into_para_no": prev["para_no"],
                        }
                    )
                    continue
                if label not in config.KNOWN_UNNUMBERED_LABELS:
                    point_anomalies.append(
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
                # 方案 2.7：截断前、已有纲目点之后的无编号段并入上一点。空段前面已跳过。
                if points:
                    piece = raw.strip()
                    prev = points[-1]
                    prev["text"] = (prev["text"] + "\n" + piece) if prev["text"] else piece
                    prev["has_note"] = True
                    prev["note_para_nos"].append(para["para_no"])
                    merged_notes += 1
                continue

            jumped = (prev_level > 0 and level > prev_level + 1) or (
                prev_level == 0 and level > 1
            )
            if jumped:
                point_anomalies.append(
                    {
                        "type": "level_jump",
                        "para_no": para["para_no"],
                        "detail": "上一点层级={0} 本点层级={1} label={2}".format(
                            prev_level, level, label
                        ),
                    }
                )
            prev_level = level
            seen_outline = True
            points.append(
                {
                    "idx": len(points),
                    "level": level,
                    "label": label,
                    "text": body,
                    "style": style,
                    "level_source": source,
                    "para_no": para["para_no"],
                    "has_note": False,
                    "note_para_nos": [],
                }
            )

        return {
            "points": points,
            "doc_header": doc_header,
            "point_anomalies": point_anomalies,
            "bible_prefix_hits": bible_prefix_hits,
            "continuations": continuations,
            "part_no": part_no,
            "part_name": part_name,
            "merged_notes": merged_notes,
        }

    anomalies = []
    if text_cut_para is None and marker_paras:
        anomalies.append(
            {
                "type": "truncate_by_style_only",
                "para_no": marker_paras[0],
                "detail": "摘录样式段号=" + ",".join(str(n) for n in marker_paras),
            }
        )
    if text_cut_para is not None:
        early = [n for n in marker_paras if n < text_cut_para]
        if early:
            anomalies.append(
                {
                    "type": "truncate_text_late",
                    "para_no": text_cut_para,
                    "detail": "文字规则段号={0}；更早的摘录样式段号={1}".format(
                        text_cut_para, ",".join(str(n) for n in early)
                    ),
                }
            )
    if inline_para is not None:
        anomalies.append(
            {
                "type": "truncate_inline",
                "para_no": inline_para,
                "detail": rule or "",
            }
        )

    chosen = _collect(config.LABEL_SEPARATORS)
    if (not chosen["points"]) and (not single_point) and config.FALLBACK_SEPARATORS:
        alt_seps = tuple(config.LABEL_SEPARATORS) + tuple(config.FALLBACK_SEPARATORS)
        alt = _collect(alt_seps)
        if len(alt["points"]) >= 2:
            chosen = alt
            chosen["point_anomalies"].append(
                {
                    "type": "fallback_separator",
                    "para_no": None,
                    "detail": "点数={0}".format(len(alt["points"])),
                }
            )
    points = chosen["points"]
    doc_header = chosen["doc_header"]
    bible_prefix_hits = chosen["bible_prefix_hits"]
    continuations = chosen["continuations"]
    part_no = chosen["part_no"]
    part_name = chosen["part_name"]
    merged_notes = chosen["merged_notes"]
    anomalies.extend(chosen["point_anomalies"])

    if single_point:
        body_bits = []
        body_nos = []
        body_styles = []
        for para in paragraphs:
            if cut is not None and para["para_no"] >= cut:
                break
            raw = text_overrides.get(para["para_no"], para["text"])
            if not (raw or "").strip():
                continue
            if _HEADER_OF_STYLE.get(para["style"]):
                continue
            if is_header_bible_reading(raw):
                continue
            body_bits.append(raw.strip())
            body_nos.append(para["para_no"])
            body_styles.append(para["style"])
        label = (doc_header.get("title_in_doc") or "").strip() or (title_hint or "").strip()
        points = [
            {
                "idx": 0,
                "level": 1,
                "label": label,
                "text": "\n".join(body_bits),
                "style": body_styles[0] if body_styles else "",
                "level_source": "single_point",
                "para_no": body_nos[0] if body_nos else None,
                "has_note": True,
                "note_para_nos": body_nos[1:],
            }
        ]
        merged_notes = len(body_nos[1:])
        # 单点篇的说明段是题面本身，不按 note_overflow 计。
        if merged_notes > len(points):
            merged_notes = len(points)

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

    if points and merged_notes > len(points):
        anomalies.append(
            {
                "type": "note_overflow",
                "para_no": None,
                "detail": "说明段={0} 纲目点={1}".format(merged_notes, len(points)),
            }
        )

    levels = sorted({p["level"] for p in points})
    same_level = len(levels) == 1
    # 方案 5.1：全部同一层级，且没有截断。
    candidate = bool(points and same_level and cut is None and not single_point)

    level_counts = {}
    for p in points:
        key = str(p["level"])
        level_counts[key] = level_counts.get(key, 0) + 1

    bible_nos = {hit["para_no"] for hit in bible_prefix_hits}
    header_paras = 0
    empty_paras = 0
    for para in paragraphs:
        if cut is not None and para["para_no"] >= cut:
            break
        raw = text_overrides.get(para["para_no"], para["text"])
        if not (raw or "").strip():
            empty_paras += 1
            continue
        if _HEADER_OF_STYLE.get(para["style"]) or para["para_no"] in bible_nos:
            header_paras += 1

    return {
        "points": points,
        "doc_header": doc_header,
        "anomalies": anomalies,
        "style_counts": style_counts,
        "style_system": classify_style_system(set(style_counts)),
        "truncated_at": cut,
        "truncate_rule": rule,
        "candidate": candidate,
        "candidate_level": levels[0] if candidate else None,
        "level_counts": level_counts,
        "para_total": len(paragraphs),
        "bible_prefix_hits": bible_prefix_hits,
        "continuations": continuations,
        "min_level": min(p["level"] for p in points) if points else None,
        "merged_note_paras": merged_notes,
        "part_no": part_no,
        "part_name": part_name,
        "header_paras": header_paras,
        "empty_paras": empty_paras,
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


def _point_line(point: dict) -> str:
    if point["text"]:
        return point["label"] + "\t" + point["text"]
    return point["label"]


def estimate_token(points: list[dict]) -> int:
    """len(text)/1.5，与 v7 的 estimate_tokens 同为 int。"""
    blob = "\n".join(_point_line(p) for p in points)
    return max(0, int(len(blob) / 1.5))


def level1_group_token(points: list[dict]) -> list[int]:
    """每个「第 1 级点 + 其下属」的 token。第 1 级之前的点不计入。"""
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
        tokens.append(estimate_token(points[i:j]))
        i = j
    return tokens


def group_by_min_level(points: list[dict]) -> dict:
    """按本篇 min(level) 切单位。残留点只返回，不并入第一个单位。

    没有纲目点时单位数为 0。有纲目点时至少有一个单位。
    """
    if not points:
        return {
            "min_level": None,
            "tokens": [],
            "residue": [],
            "units": [],
        }
    min_level = min(p["level"] for p in points)
    first = 0
    while first < len(points) and points[first]["level"] != min_level:
        first += 1
    residue = points[:first]
    units = []
    tokens = []
    i = first
    n = len(points)
    while i < n:
        if points[i]["level"] != min_level:
            i += 1
            continue
        j = i + 1
        while j < n and points[j]["level"] != min_level:
            j += 1
        chunk = points[i:j]
        units.append(chunk)
        tokens.append(estimate_token(chunk))
        i = j
    return {
        "min_level": min_level,
        "tokens": tokens,
        "residue": residue,
        "units": units,
    }
