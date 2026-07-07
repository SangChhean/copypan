# -*- coding: utf-8 -*-
"""
reference_source_zh 解析与翻译。
从纲目行剥离出处标注，翻译为英文后拼接回去。
"""
from __future__ import annotations

import json
import re
import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from es_config import es as es_client
from features.enhanced_translate.pool import (
    append_source_pool_records,
    levenshtein_distance,
    lookup_source_pool_en,
    lookup_source_pool_zh,
    normalize_en,
    normalize_zh,
    zh_eq,
)
from features.enhanced_translate.prompts import (
    REFERENCE_SOURCE_TRANSLATE_PROMPT,
    REFERENCE_SOURCE_TRANSLATE_PROMPT_EN2ZH,
)

logger = logging.getLogger("ai_search.enhanced_translate_source")


# ── source_pairs.json 出处对照表 ──────────────────────────────────────────────

import os as _os

_SOURCE_PAIRS_PATH = _os.path.join(
    _os.path.dirname(__file__), "..", "..", "data", "enhanced_translate", "source_pairs.json"
)

# 中翻英：norm_zh → source_en（带半角括号）
_SOURCE_ZH_TO_EN: dict[str, str] = {}
# 英翻中：norm_en(source_en去括号) → source_zh（带全角括号）
_SOURCE_EN_TO_ZH: dict[str, str] = {}
# 书名子表（从 source_pairs.json 加载时提取）
_BOOK_TITLE_ZH_TO_EN: dict[str, str] = {}
_BOOK_TITLE_EN_TO_ZH: dict[str, str] = {}


def _load_source_pairs() -> None:
    global _SOURCE_ZH_TO_EN, _SOURCE_EN_TO_ZH, _BOOK_TITLE_ZH_TO_EN, _BOOK_TITLE_EN_TO_ZH
    try:
        with open(_SOURCE_PAIRS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        zh_to_en: dict[str, str] = {}
        en_to_zh: dict[str, str] = {}
        book_zh_to_en: dict[str, str] = {}
        book_en_to_zh: dict[str, str] = {}
        for index_name, index_data in data.items():
            if index_name == "meta":
                continue
            for v in index_data.values():
                source_zh = (v.get("source_zh") or "").strip()
                source_en = (v.get("source_en") or "").strip()
                norm_zh = (v.get("norm_zh") or "").strip()
                if source_zh and source_en and norm_zh:
                    zh_to_en[norm_zh] = source_en
                    en_inner = source_en.strip("()")
                    norm_en = normalize_en(en_inner)
                    if norm_en:
                        en_to_zh[norm_en] = source_zh
                # 提取书名子表（引号之间的英文书名 ↔ 对应中文书名）
                en_title_m = re.search(r'"([^"]+)"', source_en)
                if en_title_m:
                    en_title = en_title_m.group(1).strip().rstrip(",")
                    en_title = en_title.replace('\u201c', '"').replace('\u201d', '"').replace('\u2018', "'").replace('\u2019', "'")
                    zh_inner = source_zh.strip().strip("（）")
                    zh_parts = zh_inner.split("，")
                    if len(zh_parts) >= 3:
                        zh_title = "，".join(zh_parts[1:-1]).strip()
                        if zh_title and en_title:
                            book_zh_to_en[zh_title] = en_title
                            book_en_to_zh[en_title] = zh_title
        _SOURCE_ZH_TO_EN = zh_to_en
        _SOURCE_EN_TO_ZH = en_to_zh
        _BOOK_TITLE_ZH_TO_EN = book_zh_to_en
        _BOOK_TITLE_EN_TO_ZH = book_en_to_zh
        logger.info(
            "[source_translator] source_pairs 加载完成：zh→en %d 条，en→zh %d 条，书名 %d 条",
            len(_SOURCE_ZH_TO_EN), len(_SOURCE_EN_TO_ZH), len(_BOOK_TITLE_ZH_TO_EN),
        )
    except Exception as e:
        logger.warning("[source_translator] source_pairs 加载失败: %s", e)


_load_source_pairs()


def lookup_source_en(source_zh_base: str) -> str:
    """
    中翻英：用中文出处（已剥段号，无括号）查英文出处。
    命中返回带半角括号的英文出处，未命中返回空字符串。
    """
    if not source_zh_base:
        return ""
    key = normalize_zh(source_zh_base)
    return _SOURCE_ZH_TO_EN.get(key, "")


def lookup_source_zh(source_en_base: str) -> str:
    """
    英翻中：用英文出处（已剥段号和括号）查中文出处。
    命中返回带全角括号的中文出处，未命中返回空字符串。
    """
    if not source_en_base:
        return ""
    key = normalize_en(source_en_base)
    return _SOURCE_EN_TO_ZH.get(key, "")


# 出处翻译路径标签
SOURCE_PATH_POOL = "pool"       # source_pool / Additional Pool 命中（T7）
SOURCE_PATH_RAG = "rag"         # 路1a kg-rag / feasts pool ES 命中
SOURCE_PATH_TABLE = "table"     # 路1b source_pairs 查表命中
SOURCE_PATH_RULE = "rule"       # 路1c 规则解析（书名也走规则）
SOURCE_PATH_RULE_AI = "rule+ai" # 路1c 规则识别类型，书名未命中子表
SOURCE_PATH_INFER = "infer"     # 路1 infer（Gemini 基于候选推算）
SOURCE_PATH_AI = "ai"           # 路2 Gemini 直译

# ── 1. 解析剥离 ──────────────────────────────────────────────
# 纲目行出处格式：（***）没有「，第***段」
# 多条出处靠起始词切分，不依赖；等分隔符。

_SOURCE_ANCHORS_LITERAL = [
    # 生命读经（63卷，含上下合并卷）
    "创世记生命读经", "出埃及记生命读经", "利未记生命读经", "民数记生命读经",
    "申命记生命读经", "约书亚记生命读经", "士师记生命读经", "路得记生命读经",
    "撒母耳记上下生命读经", "撒母耳记上生命读经", "撒母耳记下生命读经",
    "列王纪上下生命读经", "列王纪上生命读经", "列王纪下生命读经",
    "历代志上下生命读经", "历代志上生命读经", "历代志下生命读经",
    "历代志生命读经",
    "以斯拉记生命读经", "尼希米记生命读经", "以斯帖记生命读经",
    "约伯记生命读经", "诗篇生命读经", "箴言生命读经", "传道书生命读经",
    "雅歌生命读经", "以赛亚书生命读经", "耶利米书生命读经",
    "耶利米哀歌生命读经", "以西结书生命读经", "但以理书生命读经",
    "何西阿书生命读经", "约珥书生命读经", "阿摩司书生命读经",
    "俄巴底亚书生命读经", "约拿书生命读经", "弥迦书生命读经",
    "那鸿书生命读经", "哈巴谷书生命读经", "西番雅书生命读经",
    "哈该书生命读经", "撒迦利亚书生命读经", "玛拉基书生命读经",
    "马太福音生命读经", "马可福音生命读经", "路加福音生命读经",
    "约翰福音生命读经", "使徒行传生命读经", "罗马书生命读经",
    "哥林多前书生命读经", "哥林多后书生命读经", "加拉太书生命读经",
    "以弗所书生命读经", "腓立比书生命读经", "歌罗西书生命读经",
    "帖撒罗尼迦前书生命读经", "帖撒罗尼迦后书生命读经",
    "提摩太前书生命读经", "提摩太后书生命读经", "提多书生命读经",
    "腓利门书生命读经", "希伯来书生命读经", "雅各书生命读经",
    "彼得前书生命读经", "彼得后书生命读经",
    "约翰书信生命读经", "约翰一书生命读经", "约翰二书生命读经", "约翰三书生命读经",
    "犹大书生命读经", "启示录生命读经",
    # 结晶读经（63卷，含上下合并卷）
    "创世记结晶读经", "出埃及记结晶读经", "利未记结晶读经", "民数记结晶读经",
    "申命记结晶读经", "约书亚记结晶读经", "士师记结晶读经", "路得记结晶读经",
    "撒母耳记上下结晶读经", "撒母耳记上结晶读经", "撒母耳记下结晶读经",
    "列王纪上下结晶读经", "列王纪上结晶读经", "列王纪下结晶读经",
    "历代志上下结晶读经", "历代志上结晶读经", "历代志下结晶读经",
    "历代志结晶读经",
    "以斯拉记结晶读经", "尼希米记结晶读经", "以斯帖记结晶读经",
    "约伯记结晶读经", "诗篇结晶读经", "箴言结晶读经", "传道书结晶读经",
    "雅歌结晶读经", "以赛亚书结晶读经", "耶利米书结晶读经",
    "耶利米哀歌结晶读经", "以西结书结晶读经", "但以理书结晶读经",
    "何西阿书结晶读经", "约珥书结晶读经", "阿摩司书结晶读经",
    "俄巴底亚书结晶读经", "约拿书结晶读经", "弥迦书结晶读经",
    "那鸿书结晶读经", "哈巴谷书结晶读经", "西番雅书结晶读经",
    "哈该书结晶读经", "撒迦利亚书结晶读经", "玛拉基书结晶读经",
    "马太福音结晶读经", "马可福音结晶读经", "路加福音结晶读经",
    "约翰福音结晶读经", "使徒行传结晶读经", "罗马书结晶读经",
    "哥林多前书结晶读经", "哥林多后书结晶读经", "加拉太书结晶读经",
    "以弗所书结晶读经", "腓立比书结晶读经", "歌罗西书结晶读经",
    "帖撒罗尼迦前书结晶读经", "帖撒罗尼迦后书结晶读经",
    "提摩太前书结晶读经", "提摩太后书结晶读经", "提多书结晶读经",
    "腓利门书结晶读经", "希伯来书结晶读经", "雅各书结晶读经",
    "彼得前书结晶读经", "彼得后书结晶读经",
    "约翰书信结晶读经", "约翰一书结晶读经", "约翰二书结晶读经", "约翰三书结晶读经",
    "犹大书结晶读经", "启示录结晶读经",
    # 不分上下合并卷（生命读经）
    "撒母耳记生命读经", "列王纪生命读经", "历代志生命读经",
    # 不分上下合并卷（结晶读经）
    "撒母耳记结晶读经", "列王纪结晶读经", "历代志结晶读经",
    # 文集
    "倪柝声文集", "李常受文集",
    # 其他
    "新约总论", "真理课程", "圣经恢复本", "诗歌", "今时代神圣启示的先见", "恢复本圣经",
]

_LITERAL_ANCHORS_SORTED = sorted(_SOURCE_ANCHORS_LITERAL, key=len, reverse=True)
_YEAR_ANCHOR_RE = re.compile(r"(?:\d{4}|[一二三四五六七八九〇]{4})年")


def _anchor_len_at(inner: str, pos: int) -> int:
    """返回 pos 处最长匹配的起始词长度，无匹配返回 0。"""
    best = 0
    m = _YEAR_ANCHOR_RE.match(inner, pos)
    if m:
        best = m.end() - pos
    for anchor in _LITERAL_ANCHORS_SORTED:
        if inner.startswith(anchor, pos) and len(anchor) > best:
            best = len(anchor)
    return best


def _find_source_starts(inner: str) -> list[int]:
    """扫描 inner，返回每条出处的起始下标（仅 anchor 边界，不按分隔符切）。"""
    starts: list[int] = []
    i = 0
    while i < len(inner):
        if _anchor_len_at(inner, i):
            starts.append(i)
        i += 1
    return starts


def _trim_source_segment(seg: str) -> str:
    return seg.strip().strip("；,，; \t")


def _split_sources(inner: str) -> list[str]:
    """
    对括号内容按分号切分出处，与英文方向逻辑对齐。
    分号（全角；或半角;）后紧跟 anchor 才切，否则视为出处内容的一部分。
    第一段必须以 anchor 开头，否则返回 []。
    """
    inner = inner.strip()
    if not inner:
        return []

    # 找候选切割点：; 或 ； 后面紧跟 anchor
    cut_points: list[int] = [0]
    i = 0
    while i < len(inner):
        if inner[i] in (";", "；"):
            rest = inner[i + 1:]
            rest_stripped = rest.lstrip()
            offset = len(rest) - len(rest_stripped)
            candidate_pos = i + 1 + offset
            if candidate_pos < len(inner) and _anchor_len_at(inner, candidate_pos) > 0:
                cut_points.append(candidate_pos)
        i += 1

    # 第一段必须以 anchor 开头
    if _anchor_len_at(inner, cut_points[0]) == 0:
        return []

    pieces: list[str] = []
    for k, start in enumerate(cut_points):
        end = cut_points[k + 1] if k + 1 < len(cut_points) else len(inner)
        seg = _trim_source_segment(inner[start:end])
        if seg:
            pieces.append(seg)
    return pieces


def format_source_zh(sources: list[str]) -> str:
    """将出处列表格式化为带外层括号的展示串。"""
    if not sources:
        return ""
    return "（" + "；".join(sources) + "）"


def bracket_has_star(reference_source_zh: str) -> bool:
    """原始括号内容去掉外层括号后，末尾是否带 *。"""
    inner = (reference_source_zh or "").strip().strip("（）()")
    return inner.rstrip().endswith("*")


def format_source_en(en_parts: list[str], has_star: bool = False) -> str:
    """
    纯净英文出处块，与 ``format_source_zh`` 结构对应：
    中文（a；b；c*）→ 英文 (a; b; c*)
    """
    parts = [
        _clean_source_en(p.strip().rstrip("*").strip())
        for p in en_parts
        if (p or "").strip()
    ]
    if not parts:
        return ""
    if has_star:
        parts[-1] = f"{parts[-1]}*"
    return "(" + "; ".join(parts) + ")"


def format_source_en_analysis(en_parts: list[str], has_star: bool) -> str:
    """
    带 Analysis_source[N] 标签的出处块，仅用于日志/调试输出。
    (Analysis_source[1]: {en_1}; Analysis_source[2]: {en_2}*)
    """
    parts = [p.strip().rstrip("*").strip() for p in en_parts if (p or "").strip()]
    if not parts:
        return ""
    items = [f"Analysis_source[{i}]: {p}" for i, p in enumerate(parts, 1)]
    if has_star:
        items[-1] = f"{items[-1]}*"
    return "(" + "; ".join(items) + ")"


def _outer_bracket_spans(line: str) -> list[tuple[int, int]]:
    """返回行内各最外层 （...） 的 (start, end)，按出现顺序。"""
    spans: list[tuple[int, int]] = []
    depth = 0
    start: int | None = None
    for i, ch in enumerate(line):
        if ch == "（":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "）":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, i + 1))
                start = None
    return spans


def parse_source_from_line(line: str) -> tuple[str, list[str]]:
    """
    从纲目行中解析并剥离出处标注。
    返回：(剥离后的行内容, reference_source_zh 列表，每条不带外层括号)
    出处通常在行末；从右向左尝试各最外层括号，避免误命中正文内（犹3）等。
    """
    for start, end in reversed(_outer_bracket_spans(line)):
        inner = line[start + 1 : end - 1]
        sources = _split_sources(inner)
        if sources:
            stripped_line = (line[:start] + line[end:]).strip()
            return stripped_line, sources
    return line, []


# ── 英文出处识别 ──────────────────────────────────────────────────────────────

_EN_SOURCE_ANCHORS: list[str] = [
    "Holy Bible Recovery Version",
    "The Conclusion of the New Testament",
    "Conclusion of the New Testament",
    "The Collected Works of Witness Lee",
    "The Collected Works of Watchman Nee",
    "Life-study of",
    "Crystallization-study of",
    "Truth Lessons",
    "Hymns",
    "CWWN",
    "CWWL",
]
_EN_SOURCE_YEAR_RE = re.compile(r"^\d{4}\s+\w")

# ── 路1c 规则翻译常量 ──────────────────────────────────────────────────────────

# 书卷全称对照表（生命读经/结晶读经用）
_LIFE_STUDY_BOOK_ZH_TO_EN: dict[str, str] = {
    "创世记": "Genesis", "出埃及记": "Exodus", "利未记": "Leviticus",
    "民数记": "Numbers", "申命记": "Deuteronomy", "约书亚记": "Joshua",
    "士师记": "Judges", "路得记": "Ruth",
    "撒母耳记上": "1 Samuel", "撒母耳记下": "2 Samuel",
    "撒母耳记上下": "1 and 2 Samuel", "撒母耳记": "Samuel",
    "列王纪上": "1 Kings", "列王纪下": "2 Kings",
    "列王纪上下": "1 and 2 Kings", "列王纪": "Kings",
    "历代志上": "1 Chronicles", "历代志下": "2 Chronicles",
    "历代志上下": "1 and 2 Chronicles", "历代志": "Chronicles",
    "以斯拉记": "Ezra", "尼希米记": "Nehemiah", "以斯帖记": "Esther",
    "约伯记": "Job", "诗篇": "Psalms", "箴言": "Proverbs",
    "传道书": "Ecclesiastes", "雅歌": "Song of Songs",
    "以赛亚书": "Isaiah", "耶利米书": "Jeremiah",
    "耶利米哀歌": "Lamentations", "以西结书": "Ezekiel",
    "但以理书": "Daniel", "何西阿书": "Hosea", "约珥书": "Joel",
    "阿摩司书": "Amos", "俄巴底亚书": "Obadiah", "约拿书": "Jonah",
    "弥迦书": "Micah", "那鸿书": "Nahum", "哈巴谷书": "Habakkuk",
    "西番雅书": "Zephaniah", "哈该书": "Haggai",
    "撒迦利亚书": "Zechariah", "玛拉基书": "Malachi",
    "马太福音": "Matthew", "马可福音": "Mark", "路加福音": "Luke",
    "约翰福音": "John", "使徒行传": "Acts", "罗马书": "Romans",
    "哥林多前书": "1 Corinthians", "哥林多后书": "2 Corinthians",
    "加拉太书": "Galatians", "以弗所书": "Ephesians",
    "腓立比书": "Philippians", "歌罗西书": "Colossians",
    "帖撒罗尼迦前书": "1 Thessalonians", "帖撒罗尼迦后书": "2 Thessalonians",
    "提摩太前书": "1 Timothy", "提摩太后书": "2 Timothy",
    "提多书": "Titus", "腓利门书": "Philemon", "希伯来书": "Hebrews",
    "雅各书": "James", "彼得前书": "1 Peter", "彼得后书": "2 Peter",
    "约翰书信": "John's Epistles",
    "约翰一书": "1 John", "约翰二书": "2 John", "约翰三书": "3 John",
    "犹大书": "Jude", "启示录": "Revelation",
}
_LIFE_STUDY_BOOK_EN_TO_ZH: dict[str, str] = {
    v: k for k, v in _LIFE_STUDY_BOOK_ZH_TO_EN.items()
    if k not in ("撒母耳记上下", "列王纪上下", "历代志上下")
}
# 合并卷别名
for _combo, _zh in [
    ("1 and 2 Chronicles", "历代志上下"),
    ("1 & 2 Chronicles", "历代志上下"),
    ("1 and 2 Samuel", "撒母耳记上下"),
    ("1 & 2 Samuel", "撒母耳记上下"),
    ("1 and 2 Kings", "列王纪上下"),
    ("1 & 2 Kings", "列王纪上下"),
]:
    _LIFE_STUDY_BOOK_EN_TO_ZH[_combo] = _zh

# 书卷缩写对照表（圣经/注解用）
_BIBLE_ABBR_ZH_TO_EN: dict[str, str] = {
    "创": "Gen.", "出": "Exo.", "利": "Lev.", "民": "Num.", "申": "Deut.",
    "书": "Josh.", "士": "Judg.", "得": "Ruth",
    "撒上": "1 Sam.", "撒下": "2 Sam.",
    "王上": "1 Kings", "王下": "2 Kings",
    "代上": "1 Chron.", "代下": "2 Chron.",
    "拉": "Ezra", "尼": "Neh.", "斯": "Esth.", "伯": "Job",
    "诗": "Psa.", "箴": "Prov.", "传": "Eccl.", "歌": "S. S.",
    "赛": "Isa.", "耶": "Jer.", "哀": "Lam.", "结": "Ezek.", "但": "Dan.",
    "何": "Hosea", "珥": "Joel", "摩": "Amos", "俄": "Obad.",
    "拿": "Jonah", "弥": "Micah", "鸿": "Nahum", "哈": "Hab.",
    "番": "Zeph.", "该": "Hag.", "亚": "Zech.", "玛": "Mal.",
    "太": "Matt.", "可": "Mark", "路": "Luke", "约": "John",
    "徒": "Acts", "罗": "Rom.",
    "林前": "1 Cor.", "林后": "2 Cor.",
    "加": "Gal.", "弗": "Eph.", "腓": "Phil.", "西": "Col.",
    "帖前": "1 Thes.", "帖后": "2 Thes.",
    "提前": "1 Tim.", "提后": "2 Tim.",
    "多": "Titus", "门": "Philem.", "来": "Heb.", "雅": "James",
    "彼前": "1 Pet.", "彼后": "2 Pet.",
    "约壹": "1 John", "约贰": "2 John", "约叁": "3 John",
    "犹": "Jude", "启": "Rev.",
}
# 反向：优先匹配长缩写（如 1 Cor. 而不是误匹配 Cor.）
_BIBLE_ABBR_EN_TO_ZH: dict[str, str] = {
    v: k for k, v in sorted(
        _BIBLE_ABBR_ZH_TO_EN.items(), key=lambda x: len(x[1]), reverse=True
    )
}

# 节期对照表
_CONFERENCE_ZH_TO_EN: dict[str, str] = {
    "国际华语特会": "ICSC",
    "春季长老训练": "ITERO-Spring",
    "秋季长老训练": "ITERO-Fall",
    "国殇节特会": "MDC",
    "夏训": "ST", "夏季训练": "ST",
    "感恩节特会": "TGC",
    "冬训": "WT", "冬季训练": "WT",
    "安那翰春季全时间训练": "FTTA-Spring",
    "安那翰秋季全时间训练": "FTTA-Fall",
}
_CONFERENCE_EN_TO_ZH: dict[str, str] = {
    "ICSC": "国际华语特会",
    "ITERO-Spring": "春季长老训练",
    "ITERO-Fall": "秋季长老训练",
    "MDC": "国殇节特会",
    "ST": "夏训",
    "TGC": "感恩节特会",
    "WT": "冬训",
    "FTTA-Spring": "安那翰春季全时间训练",
    "FTTA-Fall": "安那翰秋季全时间训练",
}


def _is_en_source_like(inner: str) -> bool:
    """判断括号内容是否像英文出处。"""
    inner = inner.strip()
    if _EN_SOURCE_YEAR_RE.match(inner):
        return True
    inner_lower = inner.lower()
    return any(inner_lower.startswith(a.lower()) for a in _EN_SOURCE_ANCHORS)


def _outer_bracket_spans_en(line: str) -> list[tuple[int, int]]:
    """返回行内各最外层半角括号 (...) 的 (start, end)，按出现顺序。"""
    spans: list[tuple[int, int]] = []
    depth = 0
    start: int | None = None
    for i, ch in enumerate(line):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, i + 1))
                start = None
    return spans


def _split_sources_en(inner: str) -> list[str]:
    """
    切分同一括号内的多条英文出处，用 ; 分隔。
    每条出处必须以 anchor 开头；; 后若不紧跟 anchor 则认为是出处内容的一部分。
    """
    inner = inner.strip()
    if not inner:
        return []
    # 找所有候选切分点：; 后面紧跟 anchor
    cut_points: list[int] = [0]
    i = 0
    while i < len(inner):
        if inner[i] == ";":
            rest = inner[i + 1:].lstrip()
            offset = len(inner[i + 1:]) - len(rest)
            candidate_pos = i + 1 + offset
            if _is_en_source_like(rest):
                cut_points.append(candidate_pos)
        i += 1
    # 第一段必须以 anchor 开头，否则整体不认为是出处
    if not _is_en_source_like(inner[cut_points[0]:]):
        return []
    pieces: list[str] = []
    for k, start in enumerate(cut_points):
        end = cut_points[k + 1] if k + 1 < len(cut_points) else len(inner)
        seg = inner[start:end].strip().strip(";").strip()
        if seg:
            pieces.append(seg)
    return pieces


def parse_source_from_line_en(line: str) -> tuple[str, list[str]]:
    """
    从英文纲目行中识别并剥离行末出处标注（半角括号）。
    从右向左逐个尝试最外层括号，直到 _split_sources_en 成功。
    返回：(剥离后的行内容, 出处列表)
    """
    spans = _outer_bracket_spans_en(line)
    if not spans:
        return line, []

    for start, end in reversed(spans):
        inner = line[start + 1: end - 1]
        sources = _split_sources_en(inner)
        if sources:
            stripped_line = (line[:start] + line[end:]).strip()
            return stripped_line, sources

    return line, []


# ── 2. 出处查询预处理与 kg-rag 路1 ─────────────────────────────

_CN_DIGIT = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_CN_DIGIT_REV: dict[int, str] = {
    1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
    6: "六", 7: "七", 8: "八", 9: "九",
}


def _chinese_numeral_to_int(text: str) -> int:
    """汉字数字 → 阿拉伯数字，支持到百位以上（如 二十三、一百零三、一百一十四）。"""
    s = (text or "").strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    total = 0
    current = 0
    for ch in s:
        if ch in _CN_DIGIT:
            current = _CN_DIGIT[ch]
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        elif ch == "百":
            total += (current or 1) * 100
            current = 0
        elif ch == "千":
            total += (current or 1) * 1000
            current = 0
        else:
            raise ValueError(f"unsupported chinese numeral: {ch!r}")
    return total + current


def _int_to_chinese_numeral(n: int) -> str:
    """阿拉伯数字 → 系统A中文数字（位值式），用于篇数/章数。"""
    if n <= 0:
        return ""
    result = ""
    if n >= 1000:
        result += _CN_DIGIT_REV[n // 1000] + "千"
        n %= 1000
    if n >= 100:
        result += _CN_DIGIT_REV[n // 100] + "百"
        n %= 100
    if n >= 20:
        result += _CN_DIGIT_REV[n // 10] + "十"
        n %= 10
    elif n >= 10:
        result += "十"
        n %= 10
    if n > 0:
        result += _CN_DIGIT_REV[n]
    return result


def _parse_bible_chapter_zh(text: str) -> int:
    """系统B+整十例外：中文章节数 → 阿拉伯数字。"""
    text = (text or "").strip()
    if not text:
        return 0
    if text == "十":
        return 10
    m = re.match(r"^([二三四五六七八九])十$", text)
    if m:
        return _CN_DIGIT.get(m.group(1), 0) * 10
    # 十+个位（如十一=11，十二=12）
    m = re.match(r"^十([一二三四五六七八九])$", text)
    if m:
        return 10 + _CN_DIGIT.get(m.group(1), 0)
    result = 0
    for ch in text:
        if ch == "〇":
            result = result * 10
        elif ch in _CN_DIGIT:
            result = result * 10 + _CN_DIGIT[ch]
        else:
            return 0
    return result


def _int_to_bible_chapter_zh(n: int) -> str:
    """系统B+整十例外：阿拉伯数字 → 中文章节数字符串。"""
    if n <= 0:
        return ""
    if n % 10 == 0 and n <= 90:
        tens = n // 10
        return ("" if tens == 1 else _CN_DIGIT_REV.get(tens, "")) + "十"
    if 10 < n < 20:
        return "十" + _CN_DIGIT_REV[n - 10]
    s = str(n)
    result = ""
    for ch in s:
        d = int(ch)
        if d == 0:
            result += "〇"
        else:
            result += _CN_DIGIT_REV.get(d, ch)
    return result


_MSG_ZH_SINGLE_RE = re.compile(r"^第([一二三四五六七八九十百千\d]+)(篇|章|课)$")
_MSG_ZH_RANGE_RE = re.compile(r"^第([一二三四五六七八九十百千\d]+)(篇|章|课)[至到～]第([一二三四五六七八九十百千\d]+)(篇|章|课)$")
_MSG_ZH_MULTI_RE = re.compile(r"^第([一二三四五六七八九十百千\d]+)(篇|章|课)[、，,]第([一二三四五六七八九十百千\d]+)(篇|章|课)$")
_MSG_ZH_LIST_RE = re.compile(
    r"^(第[一二三四五六七八九十百千\d]+(篇|章|课))"
    r"(?:[、，,]第[一二三四五六七八九十百千\d]+(?:篇|章|课)){2,}$"
)


def _parse_msg_zh(text: str) -> str | None:
    """中文篇/章数 → 英文 msg./ch. 格式，失败返回 None。"""
    text = (text or "").strip()
    text = text.rstrip(".。")
    m = _MSG_ZH_SINGLE_RE.match(text)
    if m:
        n = _chinese_numeral_to_int(m.group(1))
        unit_map = {"篇": "msg.", "章": "ch.", "课": "lsn."}
        return f"{unit_map[m.group(2)]} {n}"
    m = _MSG_ZH_RANGE_RE.match(text)
    if m:
        n1 = _chinese_numeral_to_int(m.group(1))
        n2 = _chinese_numeral_to_int(m.group(3))
        unit_map_plural = {"篇": "msgs.", "章": "chs.", "课": "lsns."}
        return f"{unit_map_plural[m.group(2)]} {n1}-{n2}"
    m = _MSG_ZH_MULTI_RE.match(text)
    if m:
        n1 = _chinese_numeral_to_int(m.group(1))
        n2 = _chinese_numeral_to_int(m.group(3))
        unit_map_plural = {"篇": "msgs.", "章": "chs.", "课": "lsns."}
        return f"{unit_map_plural[m.group(2)]} {n1}, {n2}"
    m = _MSG_ZH_LIST_RE.match(text)
    if m:
        unit = m.group(2)
        unit_map_plural = {"篇": "msgs.", "章": "chs.", "课": "lsns."}
        nums = re.findall(r"第([一二三四五六七八九十百千\d]+)(?:篇|章|课)", text)
        ns = [str(_chinese_numeral_to_int(n)) for n in nums]
        return f"{unit_map_plural[unit]} {', '.join(ns)}"
    return None


def _split_tail_book_and_msgs(tail_parts: list[str]) -> tuple[str, str | None]:
    """
    从 tail_parts 末尾开始，连续能被 _parse_msg_zh 解析的段为篇/章，
    其余为书名。返回 (book_zh, msg_combined_str)。
    msg_combined_str 是拼合后可送 _parse_msg_zh 的字符串，或 None。
    """
    msg_indices: list[int] = []
    i = len(tail_parts) - 1
    while i >= 0:
        if _parse_msg_zh(tail_parts[i].strip()):
            msg_indices.insert(0, i)
            i -= 1
        else:
            break
    if not msg_indices:
        return "，".join(tail_parts), None
    book_parts = tail_parts[: msg_indices[0]]
    book_zh = "，".join(book_parts).strip()
    msg_parts = [tail_parts[j].strip() for j in msg_indices]
    if len(msg_parts) == 1:
        msg_combined = msg_parts[0]
    else:
        msg_combined = "、".join(msg_parts)
    return book_zh, msg_combined


_MSG_EN_SINGLE_RE = re.compile(r"^(msg|ch|lsn)\.\s*(\d+)$")
_MSG_EN_RANGE_RE = re.compile(r"^(msgs?|chs?|lsns?)\.\s*(\d+)-(\d+)$")
_MSG_EN_MULTI_RE = re.compile(r"^(msgs?|chs?|lsns?)\.\s*(\d+),\s*(\d+)$")
_MSG_EN_LIST_RE = re.compile(r"^(msgs?|chs?|lsns?)\.\s*\d+(?:,\s*\d+){2,}$")


def _parse_msg_en(text: str) -> str | None:
    """英文 msg./ch. 格式 → 中文篇/章数，失败返回 None。"""
    text = (text or "").strip()
    text = text.rstrip(".")
    m = _MSG_EN_SINGLE_RE.match(text)
    if m:
        n = int(m.group(2))
        unit = "篇" if m.group(1) == "msg" else ("课" if m.group(1) == "lsn" else "章")
        return f"第{_int_to_chinese_numeral(n)}{unit}"
    m = _MSG_EN_RANGE_RE.match(text)
    if m:
        n1, n2 = int(m.group(2)), int(m.group(3))
        unit = "篇" if m.group(1).startswith("msg") else ("课" if m.group(1).startswith("lsn") else "章")
        return f"第{_int_to_chinese_numeral(n1)}{unit}至第{_int_to_chinese_numeral(n2)}{unit}"
    m = _MSG_EN_MULTI_RE.match(text)
    if m:
        n1, n2 = int(m.group(2)), int(m.group(3))
        unit = "篇" if m.group(1).startswith("msg") else ("课" if m.group(1).startswith("lsn") else "章")
        return f"第{_int_to_chinese_numeral(n1)}{unit}、第{_int_to_chinese_numeral(n2)}{unit}"
    m = _MSG_EN_LIST_RE.match(text)
    if m:
        unit_key = m.group(1)
        unit = "篇" if unit_key.startswith("msg") else ("课" if unit_key.startswith("lsn") else "章")
        nums = re.findall(r"\d+", text)
        parts = [f"第{_int_to_chinese_numeral(int(n))}{unit}" for n in nums]
        return "、".join(parts)
    return None


_PARA_SUFFIX_END_RE = re.compile(r"，第([^，）\*]+)段\**$")
_PARA_SUFFIX_BEFORE_CLOSE_RE = re.compile(r"，第([^，）]+)段(?=）)")


def _strip_paragraph_suffix(source0: str) -> tuple[str, str]:
    """
    去掉末尾「，第***段」，返回 (去掉段号后的串, 段号汉字)。
    支持行内出处（末尾段/段*）及 ES 带闭括号形式。
    """
    s = (source0 or "").strip()
    m = _PARA_SUFFIX_END_RE.search(s)
    if m:
        return s[: m.start()].rstrip("*").rstrip(), m.group(1)
    m2 = _PARA_SUFFIX_BEFORE_CLOSE_RE.search(s)
    if m2:
        return s[: m2.start()].rstrip("*").rstrip(), m2.group(1)
    return s.rstrip("*").rstrip(), ""


def _normalize_for_source_pool(s: str) -> str:
    """剥外层括号、段号、末尾冒号，用于 source_pool 的存取键。"""
    s = (s or "").strip().strip("（）()")
    s, _ = _strip_paragraph_suffix(s)
    return s.rstrip("：:").strip()


def _paragraph_suffix_en(para_zh: str) -> str:
    if not para_zh:
        return ""
    try:
        n = _chinese_numeral_to_int(para_zh)
    except ValueError:
        return ""
    return f"p. {n}" if n else ""


def _normalize_source_query(source_zh: str) -> tuple[str, str]:
    """
    出处查询预处理。
    返回 (normalize_zh 后的查询词, 段号英文后缀如 ``p. 3``，无段号则空串)。
    """
    raw = (source_zh or "").strip()
    base, para_zh = _strip_paragraph_suffix(raw)
    base = base.rstrip("*").rstrip()
    return normalize_zh(base), _paragraph_suffix_en(para_zh)


def _source_zh_base_from_hit(hit_source_zh: str) -> str:
    inner = (hit_source_zh or "").strip().strip("（）()")
    base, _ = _strip_paragraph_suffix(inner)
    return base


def _clean_source_en(source_en: str) -> str:
    return (source_en or "").strip().strip("（）()")


def _route1_source_en(source_zh: str, line_refs: list[dict[str, Any]]) -> str:
    """旧路1（line_refs），保留但不再调用。"""
    for ref in line_refs:
        zh_src = (ref.get("ch_source") or ref.get("source") or "").strip()
        if not zh_src:
            continue
        stripped, _ = _strip_paragraph_suffix(zh_src)
        if zh_eq(stripped, source_zh):
            en_src = (ref.get("en_source") or "").strip()
            if en_src:
                return en_src
    return ""


_KG_RAG_SOURCE_INDICES = ",".join([
    "kg-rag_cwwl",
    "kg-rag_life",
    "kg-rag_cwwn",
    "kg-rag_others",
    "kg-rag_bib",
    "kg-rag_7feasts",
    "kg-rag_map_note",
])

_FEASTS_POOL_INDEX = "feasts"

_MSG_NUM_RE = re.compile(r"，第(.+?)篇$")
_CHAPTER_NUM_RE = re.compile(r"，第(.+?)章$")
_YEAR_TRAINING_RE = re.compile(r"^(\d{4}年[^，]+)，第(.+?)篇$")
_BIB_RECOVERY_RE = re.compile(r"^圣经恢复本，")


def _lookup_variants(base: str) -> list[str]:
    """节期/训练出处检索变体（缺字、特会 等）。含季节补全的变体优先。"""
    seen: set[str] = set()
    prioritized: list[str] = []
    fallback: list[str] = []

    def add(s: str, *, priority: bool = False) -> None:
        s = (s or "").strip()
        if not s or s in seen:
            return
        seen.add(s)
        (prioritized if priority else fallback).append(s)

    if "安那翰全时间训练" in base and "秋季" not in base and "春季" not in base:
        add(base.replace("安那翰全时间", "安那翰秋季全时间"), priority=True)
    if "特会" in base:
        add(base.replace("特会", ""), priority=True)
    add(base)
    return prioritized + fallback


def _structured_source_queries(base: str) -> list[dict[str, Any]]:
    """从出处 base 生成结构化 ES 查询（弥补 source_zh 不可检索）。"""
    queries: list[dict[str, Any]] = []
    base = (base or "").strip()
    if not base:
        return queries

    m_msg = _MSG_NUM_RE.search(base)
    if m_msg:
        book = base[: m_msg.start()]
        try:
            msg_num = _chinese_numeral_to_int(m_msg.group(1))
        except ValueError:
            msg_num = None
        if book and msg_num:
            for book_try in {book, book.replace("腓立比", "腓利比")}:
                queries.append({
                    "bool": {
                        "must": [
                            {"term": {"book_title": book_try}},
                            {"term": {"message_number": msg_num}},
                        ]
                    }
                })
            short = book.split("，")[0]
            if short != book:
                queries.append({
                    "bool": {
                        "must": [
                            {"wildcard": {"book_title": f"*{short}*"}},
                            {"term": {"message_number": msg_num}},
                        ]
                    }
                })

    if _BIB_RECOVERY_RE.match(base):
        queries.append({"match": {"text": {"query": base, "analyzer": "ik_smart"}}})

    m_ch = _CHAPTER_NUM_RE.search(base)
    if m_ch:
        book_prefix = base[: m_ch.start()]
        if book_prefix:
            queries.insert(0, {"match_phrase": {"text": base}})
            queries.append({"term": {"book_title": book_prefix}})
            subtitle = book_prefix.split("，", 1)[-1][:35]
            if subtitle:
                queries.append({"wildcard": {"book_title": f"*{subtitle}*"}})

    m_train = _YEAR_TRAINING_RE.match(base)
    if m_train:
        book_title, num_zh = m_train.groups()
        try:
            msg_num = _chinese_numeral_to_int(num_zh)
        except ValueError:
            msg_num = None
        if msg_num:
            queries.append({
                "bool": {
                    "must": [
                        {"term": {"book_title": book_title}},
                        {"term": {"message_number": msg_num}},
                    ]
                }
            })

    if "，" in base and not m_msg:
        tail = base.split("，", 1)[1]
        if tail and ("文集" in base or "新约总论" in base):
            key = tail.split("，")[0][:40]
            if key and "篇" not in key:
                queries.append({"wildcard": {"book_title": f"*{key}*"}})

    if base.startswith("李常受文集") or base.startswith("倪柝声文集"):
        queries.append({"wildcard": {"book_title": f"*{base[-30:]}*"}})

    return queries


async def _kg_rag_bm25_recall(base: str, top_k: int = 20) -> list[dict[str, Any]]:
    """
    kg-rag 出处召回。``source_zh`` 映射为 index:false，无法对其 BM25；
    改为对 ``text`` 字段 BM25（与 kg_rag retrieval 一致），并辅以结构化查询。
    """
    if not base:
        return []

    seen_ids: set[str] = set()
    out: list[dict[str, Any]] = []

    async def _collect(body: dict[str, Any], limit: int) -> None:
        nonlocal out
        if limit <= 0:
            return
        try:
            resp = await asyncio.to_thread(
                es_client.search,
                index=indices,
                body={**body, "size": limit},
                request_timeout=10,
            )
        except Exception as e:
            logger.warning("[source_translator] kg-rag 出处召回失败: %s", e)
            return
        for hit in (resp.get("hits") or {}).get("hits") or []:
            if len(out) >= top_k:
                return
            hid = hit.get("_id") or ""
            if hid and hid in seen_ids:
                continue
            if hid:
                seen_ids.add(hid)
            src = hit.get("_source") or {}
            if src.get("source_zh"):
                out.append(src)

    src_fields = ["source_zh", "source_en", "book_title", "message_number"]
    indices = _KG_RAG_SOURCE_INDICES
    if _BIB_RECOVERY_RE.match(base):
        indices = f"{_KG_RAG_SOURCE_INDICES},kg-rag_map_note"

    for q in _structured_source_queries(base):
        await _collect(
            {"query": q, "_source": src_fields},
            top_k - len(out),
        )

    if len(out) < top_k:
        await _collect(
            {
                "query": {"match": {"text": {"query": base, "analyzer": "ik_smart"}}},
                "_source": src_fields,
            },
            top_k - len(out),
        )

    return out


def _dedupe_source_candidates(
    hits: list[dict[str, Any]],
    nq: str = "",
) -> list[dict[str, str]]:
    seen: set[str] = set()
    pairs: list[dict[str, str]] = []
    for hit in hits:
        sz = (hit.get("source_zh") or "").strip()
        if not sz:
            continue
        base = _source_zh_base_from_hit(sz)
        key = normalize_zh(base)
        if not key or key in seen:
            continue
        seen.add(key)
        pairs.append({
            "source_zh": base,
            "source_en": _clean_source_en(hit.get("source_en") or ""),
            "hit_source_zh": sz,
        })
    if nq:
        pairs.sort(
            key=lambda c: (
                0 if normalize_zh(c["source_zh"]) == nq else 1,
                levenshtein_distance(normalize_zh(c["source_zh"]), nq),
                len(normalize_zh(c["source_zh"])),
            )
        )
    return pairs


async def _feasts_pool_lookup(base: str) -> str:
    """从 feasts pool 索引匹配节期/全时间训练出处 en_source（严格 zh 全等）。"""
    for variant in _lookup_variants(base):
        nqv = normalize_zh(variant)
        try:
            resp = await asyncio.to_thread(
                es_client.search,
                index=_FEASTS_POOL_INDEX,
                body={
                    "query": {"match_phrase": {"source": variant}},
                    "size": 15,
                    "_source": ["source", "title"],
                },
                request_timeout=8,
            )
        except Exception as e:
            logger.warning("[source_translator] feasts pool 检索失败: %s", e)
            continue
        for hit in (resp.get("hits") or {}).get("hits") or []:
            src = (hit.get("_source") or {}).get("source") or []
            if len(src) < 2:
                continue
            zh_inner = (src[0] or "").strip().strip("（）()")
            zh_base, _ = _strip_paragraph_suffix(zh_inner)
            en = _clean_source_en(src[1] or "")
            if not en:
                continue
            nzh = normalize_zh(zh_base)
            if nzh == nqv or nzh == normalize_zh(variant):
                return en
    return ""


_EN_PARA_SUFFIX_RE = re.compile(r",\s*(?:pp?\.|pars?\.)[\s\d\-]+\.?\s*$")
_EN_SOURCE_YEAR_PREFIX_RE = re.compile(r"^\d{4}\s+\w")


def _strip_en_paragraph_suffix(source_en: str) -> str:
    """剥离英文出处末尾段号（, p. 5 / , pp. 99-100.），返回剥离后的串。"""
    s = (source_en or "").strip().strip("()")
    m = _EN_PARA_SUFFIX_RE.search(s)
    if m:
        return s[: m.start()].strip()
    return s


async def _feasts_pool_lookup_en(source_en: str) -> str:
    """从 feasts pool 索引反向匹配英文出处，返回对应中文出处（不含括号和段号）。"""
    base = _strip_en_paragraph_suffix(source_en)
    if not base:
        return ""
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index=_FEASTS_POOL_INDEX,
            body={
                "query": {"match_phrase": {"source": base}},
                "size": 15,
                "_source": ["source", "title"],
            },
            request_timeout=8,
        )
    except Exception as e:
        logger.warning("[source_translator] feasts pool en2zh 检索失败: %s", e)
        return ""
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).get("source") or []
        if len(src) < 2:
            continue
        en_raw = (src[1] or "").strip().strip("()")
        if normalize_en(en_raw) == normalize_en(base):
            zh_raw = (src[0] or "").strip().strip("（）")
            zh_base, _ = _strip_paragraph_suffix(zh_raw)
            zh_base = re.sub(r"，篇题$", "", zh_base).strip()
            if zh_base:
                return zh_base
    return ""


def _ref_block_from_line_refs_en2zh(line_refs: list[dict[str, Any]]) -> str:
    """从 line_refs 取第一条同时有 en_source 和 ch_source 的记录，构建参考语料块。"""
    for ref in line_refs:
        en_src = (ref.get("en_source") or "").strip()
        zh_src = (ref.get("ch_source") or ref.get("source") or "").strip()
        if en_src and zh_src:
            return (
                f"\nParagraph 1"
                f"\nen_source: {en_src}"
                f"\nzh_source: {zh_src}"
            )
    return ""


async def _gemini_translate_sources_en2zh(
    numbered_sources: list[tuple[int, str]],
    line_refs: list[dict[str, Any]],
) -> tuple[dict[int, str], float]:
    """批量将英文出处翻译为中文，Gemini 兜底。"""
    if not numbered_sources:
        return {}, 0.0
    ref_block = _ref_block_from_line_refs_en2zh(line_refs)
    blocks: list[str] = []
    for pos, (_, source_en) in enumerate(numbered_sources, 1):
        blocks.append(
            f"Source {pos}: {source_en}"
            + (f"\n参考语料：{ref_block}" if ref_block else "")
        )
    contents = (
        REFERENCE_SOURCE_TRANSLATE_PROMPT_EN2ZH
        + "\n\n"
        + "\n\n".join(blocks)
        + "\n\n请逐条输出中文出处，格式：\n"
        + "\n".join(f"Source {pos}: {{中文出处}}" for pos in range(1, len(numbered_sources) + 1))
    )
    out: dict[int, str] = {}
    cost_usd = 0.0
    try:
        from features.enhanced_translate.service import _call_gemini_sync

        cumulative: dict[str, Any] = {"in_tok": 0, "out_tok": 0, "cost_usd": 0.0}
        use_terminology = not bool(ref_block)
        text, cumulative = await asyncio.to_thread(
            _call_gemini_sync,
            contents,
            0,
            None,
            cumulative,
            use_terminology=use_terminology,
        )
        cost_usd = float(cumulative.get("cost_usd", 0.0) or 0.0)
        if text:
            pattern = re.compile(r"^Source\s+(\d+)\s*:\s*(.+)$", re.MULTILINE)
            for m in pattern.finditer(text):
                pos = int(m.group(1)) - 1
                if 0 <= pos < len(numbered_sources):
                    src_idx = numbered_sources[pos][0]
                    out[src_idx] = m.group(2).strip()
    except Exception as e:
        logger.warning("[source_translator] Gemini en2zh 出处翻译失败: %s", e)
    for src_idx, source_en in numbered_sources:
        if src_idx not in out:
            out[src_idx] = source_en
    return out, cost_usd


async def translate_source_en_batch(
    items: list[tuple[int, list[str], list[dict[str, Any]], bool]],
) -> tuple[dict[int, str], dict[int, list[str]], float]:
    """
    批量翻译英文出处为中文。
    items: [(prep_index, source_en_list, line_refs, has_star), ...]
    整单一次 Gemini 处理所有路2 未命中出处。
    返回：(译文 map, 路径标签 map, 费用 USD)
    """
    if not items:
        return {}, {}, 0.0
    results: dict[int, str] = {}
    paths_map: dict[int, list[str]] = {}
    total_cost_usd = 0.0
    road2_tasks: list[_SourceRoad2TaskEn2zh] = []
    road2_keys: set[tuple[int, int]] = set()
    pending: dict[int, tuple[list[str], list[str], list[str]]] = {}

    for prep_idx, source_list, line_refs, _has_star in items:
        if not source_list:
            continue
        zh_parts = [""] * len(source_list)
        path_parts = [""] * len(source_list)
        for i, source_en in enumerate(source_list):
            _sp_base = _normalize_for_source_pool(source_en)
            _sp_zh = lookup_source_pool_zh(_sp_base)
            if _sp_zh:
                if source_en.strip().endswith(":"):
                    _sp_zh = _sp_zh + "："
                zh_parts[i] = _sp_zh.strip("（）")
                path_parts[i] = SOURCE_PATH_POOL
                continue
            base = _strip_en_paragraph_suffix(source_en)
            if _EN_SOURCE_YEAR_PREFIX_RE.match(base):
                hit_zh = await _feasts_pool_lookup_en(source_en)
                if hit_zh:
                    zh_parts[i] = hit_zh
                    path_parts[i] = SOURCE_PATH_RAG
                    logger.info("[source_translator] 路1a命中: %s → %s", source_en, zh_parts[i])
                    continue
            table_zh = lookup_source_zh(base)
            if table_zh:
                zh_parts[i] = table_zh.strip("（）")
                path_parts[i] = SOURCE_PATH_TABLE
                logger.info("[source_translator] 路1b表命中: %s → %s", source_en, table_zh)
                continue
            # 路1c：规则翻译兜底
            rule_zh, rule_path = _rule_translate_source_en(source_en)
            if rule_zh:
                if rule_path == SOURCE_PATH_RULE_AI:
                    road2_tasks.append(
                        _SourceRoad2TaskEn2zh(
                            prep_idx=prep_idx,
                            src_idx=i,
                            source_en=rule_zh,
                            line_refs=[],
                        )
                    )
                    road2_keys.add((prep_idx, i))
                    path_parts[i] = SOURCE_PATH_RULE_AI
                else:
                    zh_parts[i] = rule_zh
                    path_parts[i] = rule_path
                logger.info("[source_translator] 路1c规则命中: %s → %s", source_en, rule_zh)
            else:
                road2_keys.add((prep_idx, i))
                road2_tasks.append(
                    _SourceRoad2TaskEn2zh(
                        prep_idx=prep_idx,
                        src_idx=i,
                        source_en=source_en,
                        line_refs=line_refs,
                    )
                )
        pending[prep_idx] = (zh_parts, source_list, path_parts)

    if road2_tasks:
        logger.info("[source_translator] en2zh 出处整单 Gemini: road2=%d", len(road2_tasks))
        gemini_map, gemini_cost = await _gemini_sources_once_en2zh(road2_tasks)
        total_cost_usd += gemini_cost
        for (prep_idx, src_idx), translated in gemini_map.items():
            zh_parts, _, path_parts = pending[prep_idx]
            zh_parts[src_idx] = translated.strip().strip("（）")
            if (prep_idx, src_idx) in road2_keys:
                if not path_parts[src_idx]:
                    path_parts[src_idx] = SOURCE_PATH_AI

    for prep_idx, (zh_parts, source_list, path_parts) in pending.items():
        for i, source_en in enumerate(source_list):
            if not zh_parts[i]:
                zh_parts[i] = source_en
                path_parts[i] = ""
        parts = [p for p in zh_parts if p]
        results[prep_idx] = "（" + "；".join(parts) + "）" if parts else ""
        paths_map[prep_idx] = path_parts

    _sp_rows: list[dict[str, str]] = []
    for _prep_idx, (_zh_parts, _source_list, _path_parts) in pending.items():
        for _i, (_zh, _path) in enumerate(zip(_zh_parts, _path_parts)):
            if _path not in (SOURCE_PATH_RULE_AI, SOURCE_PATH_AI):
                continue
            _en_stripped = _strip_en_paragraph_suffix(_source_list[_i])
            _en_clean = _normalize_for_source_pool(_en_stripped)
            _zh_clean = _zh.strip().strip("（）")
            if _zh_clean and _en_clean:
                _sp_rows.append({"zh": _zh_clean, "en": _en_clean, "source_type": _path})
    if _sp_rows:
        append_source_pool_records(_sp_rows)

    return results, paths_map, total_cost_usd


async def _gemini_infer_source_en(
    source_zh: str,
    ref_pairs: list[dict[str, str]],
) -> tuple[str, float]:
    """距离推算：用 top 参考语料让 Gemini 翻译出处（段号原样交给 Gemini）。"""
    if not ref_pairs:
        return "", 0.0
    ref_lines: list[str] = []
    for i, pair in enumerate(ref_pairs[:6], 1):
        ref_lines.append(
            f"参考 {i}:\nzh_source: {pair['source_zh']}\nen_source: {pair['source_en']}"
        )
    contents = (
        REFERENCE_SOURCE_TRANSLATE_PROMPT
        + "\n\n"
        + "\n".join(ref_lines)
        + f"\n\n待译出处：{source_zh}\n\n请只输出英文出处，格式：Source 1: {{英文出处}}"
        + "\n不要在外层再加括号。"
    )
    try:
        from features.enhanced_translate.service import _call_gemini_sync

        cumulative: dict[str, Any] = {"in_tok": 0, "out_tok": 0, "cost_usd": 0.0}
        text, cumulative = await asyncio.to_thread(
            _call_gemini_sync,
            contents,
            0,
            None,
            cumulative,
            use_terminology=False,
        )
        cost_usd = float(cumulative.get("cost_usd", 0.0) or 0.0)
        if text:
            m = re.search(r"^Source\s+1\s*:\s*(.+)$", text.strip(), re.MULTILINE)
            if m:
                return _clean_source_en(m.group(1).strip()), cost_usd
            line = text.strip().splitlines()[0].strip()
            return _clean_source_en(re.sub(r"^Source\s+1\s*:\s*", "", line).strip()), cost_usd
    except Exception as e:
        logger.warning("[source_translator] kg-rag 距离推算 Gemini 失败: %s", e)
    return "", 0.0


async def _kg_rag_source_lookup(
    source_zh: str,
    *,
    defer_infer: bool = False,
) -> tuple[str, str, float, dict[str, Any] | None]:
    """
    新路1：查 kg-rag 索引 source_zh/source_en。
    返回 (英文出处, 段号英文如 p. 3, Gemini 费用 USD, 推迟推算元数据)；
    第四项非空时表示需 Gemini 距离推算（batch 模式 defer_infer=True）。
    """
    cost_usd = 0.0
    raw = (source_zh or "").strip()
    _, para_zh = _strip_paragraph_suffix(raw)
    para_display = _paragraph_suffix_en(para_zh)
    para_append = f", {para_display}" if para_display else ""

    base, _ = _strip_paragraph_suffix(raw)
    base = base.rstrip("*").rstrip()
    nq = normalize_zh(base)

    if _YEAR_TRAINING_RE.match(base) or "感恩节" in base or "训练" in base:
        for variant in _lookup_variants(base):
            feast_en = await _feasts_pool_lookup(variant)
            if feast_en:
                return f"{feast_en}{para_append}", para_display, cost_usd, None

    hits = await _kg_rag_bm25_recall(base, top_k=20)
    candidates = _dedupe_source_candidates(hits, nq)

    for cand in candidates:
        nz = normalize_zh(cand["source_zh"])
        if nz == nq or levenshtein_distance(nz, nq) <= 1:
            en = cand["source_en"]
            if en:
                return f"{en}{para_append}", para_display, cost_usd, None
            if _YEAR_TRAINING_RE.match(base) or "训练" in base or "感恩节" in base:
                feast_en = await _feasts_pool_lookup(base)
                if feast_en:
                    return f"{feast_en}{para_append}", para_display, cost_usd, None

    if not candidates:
        feast_en = await _feasts_pool_lookup(base)
        if feast_en:
            return f"{feast_en}{para_append}", para_display, cost_usd, None
        return "", para_display, cost_usd, None

    ranked = sorted(
        candidates,
        key=lambda c: (
            levenshtein_distance(normalize_zh(c["source_zh"]), nq),
            len(normalize_zh(c["source_zh"])),
        ),
    )[:6]
    if defer_infer:
        return "", para_display, cost_usd, {
            "raw": raw,
            "ranked": ranked,
            "para_append": para_append,
        }
    inferred, infer_cost = await _gemini_infer_source_en(raw, ranked)
    cost_usd += infer_cost
    if inferred:
        return f"{inferred}{para_append}", para_display, cost_usd, None
    return "", para_display, cost_usd, None


class SourceLookupResult:
    """调试用：单条出处匹配详情。"""

    __slots__ = (
        "source_zh", "query", "match_method", "source_en",
        "para_en", "final_part",
    )

    def __init__(
        self,
        source_zh: str,
        query: str,
        match_method: str,
        source_en: str,
        para_en: str,
        final_part: str,
    ):
        self.source_zh = source_zh
        self.query = query
        self.match_method = match_method
        self.source_en = source_en
        self.para_en = para_en
        self.final_part = final_part


async def _kg_rag_source_lookup_debug(source_zh: str) -> SourceLookupResult:
    """带匹配方式标注的出处查询（验证用）。"""
    raw = (source_zh or "").strip()
    query, para_display = _normalize_source_query(raw)
    base = raw.rstrip("*").rstrip()
    base, _ = _strip_paragraph_suffix(base)
    base = base.rstrip("*").rstrip()
    nq = normalize_zh(base)
    para_append = f", {para_display}" if para_display else ""

    if _YEAR_TRAINING_RE.match(base) or "感恩节" in base or "训练" in base:
        for variant in _lookup_variants(base):
            feast_en = await _feasts_pool_lookup(variant)
            if feast_en:
                part = f"{feast_en}{para_append}"
                return SourceLookupResult(
                    source_zh=raw, query=base, match_method="全等命中(feasts)",
                    source_en=feast_en, para_en=para_display, final_part=part,
                )

    hits = await _kg_rag_bm25_recall(base, top_k=20)
    candidates = _dedupe_source_candidates(hits, nq)

    for cand in candidates:
        nz = normalize_zh(cand["source_zh"])
        if nz == nq or levenshtein_distance(nz, nq) <= 1:
            en = cand["source_en"]
            if en:
                part = f"{en}{para_append}"
                return SourceLookupResult(
                    source_zh=raw, query=base, match_method="全等命中",
                    source_en=en, para_en=para_display, final_part=part,
                )

    if candidates:
        ranked = candidates[:6]
        inferred, _ = await _gemini_infer_source_en(raw, ranked)
        if inferred:
            part = f"{inferred}{para_append}" if para_display else inferred
            return SourceLookupResult(
                source_zh=raw, query=base, match_method="距离推算(top6)",
                source_en=inferred, para_en=para_display, final_part=part,
            )

    feast_en = await _feasts_pool_lookup(base)
    if feast_en:
        part = f"{feast_en}{para_append}"
        return SourceLookupResult(
            source_zh=raw, query=base, match_method="全等命中(feasts)",
            source_en=feast_en, para_en=para_display, final_part=part,
        )

    return SourceLookupResult(
        source_zh=raw, query=base, match_method="无命中",
        source_en="", para_en=para_display, final_part="",
    )


# ── 3. ES BM25 检索 title 字段 ────────────────────────────────

_POOL_INDICES = ",".join([
    "life", "cwwn", "cwwl", "others",
    "bib", "foo", "hymn", "feasts",
])


async def _bm25_source_search(source_zh: str, top_k: int = 5) -> list[dict[str, Any]]:
    """
    用 reference_source_zh（去掉括号）检索 title 字段，
    返回 top_k 条含 zh_source + en_source 的结果。
    """
    query = re.sub(r'[（）]', '', source_zh).strip()
    if not query:
        return []
    body = {
        "query": {
            "match": {
                "title": {"query": query, "operator": "and"}
            }
        },
        "size": top_k,
        "_source": ["source", "title"],
    }
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index=_POOL_INDICES,
            body=body,
            request_timeout=8,
        )
    except Exception as e:
        logger.warning("[source_translator] BM25 source 检索失败: %s", e)
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        source = src.get("source") or []
        zh_src = source[0] if len(source) > 0 else ""
        en_src = source[1] if len(source) > 1 else ""
        if zh_src:
            out.append({
                "zh_source": zh_src,
                "en_source": en_src,
                "title": src.get("title") or "",
            })
    return out


def _ref_block_from_line_refs(line_refs: list[dict[str, Any]]) -> str:
    for ref in line_refs:
        zh_src = (ref.get("ch_source") or ref.get("source") or "").strip()
        en_src = (ref.get("en_source") or "").strip()
        if zh_src and en_src:
            return (
                f"\nParagraph 1"
                f"\nzh_source: {zh_src}"
                f"\nen_source: {en_src}"
            )
    return ""


@dataclass
class _SourceInferTask:
    prep_idx: int
    src_idx: int
    source_zh: str
    ranked: list[dict[str, Any]]
    para_append: str


@dataclass
class _SourceRoad2Task:
    prep_idx: int
    src_idx: int
    source_zh: str
    line_refs: list[dict[str, Any]]


@dataclass
class _SourceRoad2TaskEn2zh:
    prep_idx: int
    src_idx: int
    source_en: str
    line_refs: list[dict[str, Any]]


async def _gemini_sources_once(
    infer_tasks: list[_SourceInferTask],
    road2_tasks: list[_SourceRoad2Task],
) -> tuple[dict[tuple[int, int], str], float]:
    """整单一次 Gemini：路1 距离推算 + 路2 未命中出处。"""
    if not infer_tasks and not road2_tasks:
        return {}, 0.0

    blocks: list[str] = []
    keys: list[tuple[int, int, str, str]] = []
    pos = 1
    for task in infer_tasks:
        ref_lines = [
            f"参考 {i}:\nzh_source: {pair['source_zh']}\nen_source: {pair['source_en']}"
            for i, pair in enumerate(task.ranked[:6], 1)
        ]
        blocks.append(
            f"Source {pos}:\n待译出处：{task.source_zh}\n" + "\n".join(ref_lines)
        )
        keys.append((task.prep_idx, task.src_idx, task.para_append, "infer"))
        pos += 1
    for task in road2_tasks:
        ref_block = _ref_block_from_line_refs(task.line_refs)
        blocks.append(
            f"Source {pos}: {task.source_zh}"
            + (f"\n参考语料：{ref_block}" if ref_block else "")
        )
        keys.append((task.prep_idx, task.src_idx, "", "road2"))
        pos += 1

    contents = (
        REFERENCE_SOURCE_TRANSLATE_PROMPT
        + "\n\n"
        + "\n\n".join(blocks)
        + "\n\n请逐条输出英文出处，格式：\n"
        + "\n".join(f"Source {pos_i}: {{英文出处}}" for pos_i in range(1, len(keys) + 1))
        + "\n不要在外层再加括号。"
    )
    use_terminology = not infer_tasks and all(
        not _ref_block_from_line_refs(t.line_refs) for t in road2_tasks
    )
    out: dict[tuple[int, int], str] = {}
    cost_usd = 0.0
    try:
        from features.enhanced_translate.service import _call_gemini_sync

        cumulative: dict[str, Any] = {"in_tok": 0, "out_tok": 0, "cost_usd": 0.0}
        text, cumulative = await asyncio.to_thread(
            _call_gemini_sync,
            contents,
            0,
            None,
            cumulative,
            use_terminology=use_terminology,
        )
        cost_usd = float(cumulative.get("cost_usd", 0.0) or 0.0)
        if text:
            pattern = re.compile(r"^Source\s+(\d+)\s*:\s*(.+)$", re.MULTILINE)
            for m in pattern.finditer(text):
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(keys):
                    prep_idx, src_idx, para_append, kind = keys[idx]
                    translated = _clean_source_en(m.group(2).strip())
                    if kind == "infer" and para_append:
                        translated = f"{translated}{para_append}"
                    out[(prep_idx, src_idx)] = translated
    except Exception as e:
        logger.warning("[source_translator] 出处整单 Gemini 失败: %s", e)
    return out, cost_usd


async def _gemini_sources_once_en2zh(
    road2_tasks: list[_SourceRoad2TaskEn2zh],
) -> tuple[dict[tuple[int, int], str], float]:
    """英翻中：整单一次 Gemini 翻译未命中英文出处。"""
    if not road2_tasks:
        return {}, 0.0
    blocks: list[str] = []
    keys: list[tuple[int, int]] = []
    for pos, task in enumerate(road2_tasks, 1):
        ref_block = _ref_block_from_line_refs_en2zh(task.line_refs)
        blocks.append(
            f"Source {pos}: {task.source_en}"
            + (f"\n参考语料：{ref_block}" if ref_block else "")
        )
        keys.append((task.prep_idx, task.src_idx))
    contents = (
        REFERENCE_SOURCE_TRANSLATE_PROMPT_EN2ZH
        + "\n\n"
        + "\n\n".join(blocks)
        + "\n\n请逐条输出中文出处，格式：\n"
        + "\n".join(f"Source {pos}: {{中文出处}}" for pos in range(1, len(keys) + 1))
    )
    use_terminology = all(
        not _ref_block_from_line_refs_en2zh(t.line_refs) for t in road2_tasks
    )
    out: dict[tuple[int, int], str] = {}
    cost_usd = 0.0
    try:
        from features.enhanced_translate.service import _call_gemini_sync

        cumulative: dict[str, Any] = {"in_tok": 0, "out_tok": 0, "cost_usd": 0.0}
        text, cumulative = await asyncio.to_thread(
            _call_gemini_sync,
            contents,
            0,
            None,
            cumulative,
            use_terminology=use_terminology,
        )
        cost_usd = float(cumulative.get("cost_usd", 0.0) or 0.0)
        if text:
            pattern = re.compile(r"^Source\s+(\d+)\s*:\s*(.+)$", re.MULTILINE)
            for m in pattern.finditer(text):
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(keys):
                    out[keys[idx]] = m.group(2).strip()
    except Exception as e:
        logger.warning("[source_translator] en2zh 出处整单 Gemini 失败: %s", e)
    return out, cost_usd


async def _gemini_translate_sources(
    numbered_sources: list[tuple[int, str]],
    line_refs: list[dict[str, Any]],
) -> tuple[dict[int, str], float]:
    """方案 A：同一条纲目行的多条未命中出处合并一次 Gemini。"""
    if not numbered_sources:
        return {}, 0.0

    ref_block = _ref_block_from_line_refs(line_refs)
    blocks: list[str] = []
    for pos, (_, source_zh) in enumerate(numbered_sources, 1):
        blocks.append(
            f"Source {pos}: {source_zh}"
            + (f"\n参考语料：{ref_block}" if ref_block else "")
        )

    contents = (
        REFERENCE_SOURCE_TRANSLATE_PROMPT
        + "\n\n"
        + "\n\n".join(blocks)
        + "\n\n请逐条输出英文出处，格式：\n"
        + "\n".join(f"Source {pos}: {{英文出处}}" for pos in range(1, len(numbered_sources) + 1))
    )

    out: dict[int, str] = {}
    cost_usd = 0.0
    try:
        from features.enhanced_translate.service import _call_gemini_sync

        cumulative: dict[str, Any] = {"in_tok": 0, "out_tok": 0, "cost_usd": 0.0}
        use_terminology = not bool(ref_block)
        text, cumulative = await asyncio.to_thread(
            _call_gemini_sync,
            contents,
            0,
            None,
            cumulative,
            use_terminology=use_terminology,
        )
        cost_usd = float(cumulative.get("cost_usd", 0.0) or 0.0)
        if text:
            pattern = re.compile(r"^Source\s+(\d+)\s*:\s*(.+)$", re.MULTILINE)
            for m in pattern.finditer(text):
                pos = int(m.group(1)) - 1
                if 0 <= pos < len(numbered_sources):
                    src_idx = numbered_sources[pos][0]
                    out[src_idx] = m.group(2).strip()
    except Exception as e:
        logger.warning("[source_translator] Gemini 调用失败: %s", e)

    for src_idx, source_zh in numbered_sources:
        if src_idx not in out:
            out[src_idx] = source_zh
    return out, cost_usd


# ── 4. 翻译出处 ───────────────────────────────────────────────

async def translate_source_zh(
    source_list: list[str],
    line_refs: list[dict[str, Any]],
    *,
    has_star: bool = False,
) -> str:
    """
    翻译 reference_source_zh 列表 → reference_source_en。
    路1：kg-rag source_zh/source_en；路2：同条纲目未命中项合并一次 Gemini。
    """
    if not source_list:
        return ""

    en_parts = [""] * len(source_list)
    miss: list[tuple[int, str]] = []
    cost_usd = 0.0

    for i, source_zh in enumerate(source_list):
        hit_en, _, lookup_cost, _ = await _kg_rag_source_lookup(source_zh)
        cost_usd += lookup_cost
        if hit_en:
            en_parts[i] = hit_en
            logger.info("[source_translator] 路1命中: %s → %s", source_zh, hit_en)
        else:
            miss.append((i, source_zh))

    if miss:
        logger.info("[source_translator] 路2: %d 条出处合并一次 Gemini", len(miss))
        gemini_map, gemini_cost = await _gemini_translate_sources(miss, line_refs)
        cost_usd += gemini_cost
        for i, source_zh in miss:
            en_parts[i] = gemini_map.get(i, source_zh)

    formatted = format_source_en(en_parts, has_star)
    logger.info(
        "[source_translator] 出处译文 %s | debug %s | cost_usd=%.6f",
        formatted,
        format_source_en_analysis(en_parts, has_star),
        cost_usd,
    )
    return formatted


# ── 路1c 规则解析辅助 ──────────────────────────────────────────────────────────

_ZH_YEAR_RE = re.compile(r"^([一二三四五六七八九〇]{4}|\d{4})年")
_ZH_VOL_RE = re.compile(r"第([一二三四五六七八九十百千\d]+)册")
_ZH_CWWL_RE = re.compile(r"^李常受文集([一二三四五六七八九〇]{4})(?:至[一二三四五六七八九〇]{4})?年第([一二三四五六七八九十百千\d]+)册")
_ZH_CWWN_RE = re.compile(r"^倪柝声文集第([一二三四五六七八九十百千\d]+)辑第([一二三四五六七八九十百千\d]+)册")
_ZH_BIBLE_RE = re.compile(r"^(?:恢复本圣经|圣经恢复本)")
_ZH_FOOTNOTE_RE = re.compile(r"注(\d+)[.。]?$")

# 纲目分段标记（大贰、大叁、大肆等），出处翻译时直接忽略
_ZH_SECTION_MARK_RE = re.compile(r"[，,]\s*大[一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]+$")

_EN_YEAR_RE = re.compile(r"^(\d{4})\s+(\S+)")
_EN_CWWL_RE = re.compile(r"^(?:CWWL|The Collected Works of Witness Lee),?\s*(\d{4})(?:-\d{4})?,\s*vol\.\s*(\d+)")
_EN_CWWL_LG_RE = re.compile(
    r"^(?:CWWL|The Collected Works of Witness Lee),\s*Letters\s*&\s*Gleanings,\s*vol\.\s*(\d+)"
)
_EN_TRUTH_LESSONS_RE = re.compile(
    r"^Truth Lessons,\s*Level\s*(\d+),\s*vol\.\s*(\d+)"
)
_ZH_TRUTH_LESSONS_RE = re.compile(
    r"^真理课程，?第?([一二三四五六七八九十\d]+)级[，]?(?:第?([一二三四五六七八九十\d]+)[册卷]|卷([一二三四五六七八九十\d]+))$"
)
_EN_CWWN_RE = re.compile(r"^(?:CWWN|The Collected Works of Watchman Nee),?\s*vol\.\s*(\d+)")
_EN_BIBLE_RE = re.compile(r"^Holy Bible Recovery Version,?\s*")
_EN_BOOK_RE = re.compile(r"^([1-3]\s+\w+\.?|\w+\.?)\s+(\d+):(\d+)")
_EN_FOOTNOTE_RE = re.compile(r",?\s*(?:footnote|note)\s*(\d+)\.?$", re.IGNORECASE)


def _year_zh_to_en(year_zh: str) -> str:
    """中文四位年份 → 阿拉伯数字字符串，如 一九六五 → 1965。"""
    mapping = {"〇": "0", "一": "1", "二": "2", "三": "3", "四": "4",
               "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
    return "".join(mapping.get(c, c) for c in year_zh)


def _year_en_to_zh(year_en: str) -> str:
    """阿拉伯数字年份 → 中文四位，如 1965 → 一九六五。"""
    mapping = {"0": "〇", "1": "一", "2": "二", "3": "三", "4": "四",
               "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
    return "".join(mapping.get(c, c) for c in str(year_en))


def _cwwn_zh_to_vol(ji: int, ce: int) -> int:
    """倪柝声文集辑册 → 卷号。第一辑X册→X，第二辑X册→20+X，第三辑X册→46+X。"""
    if ji == 1:
        return ce
    elif ji == 2:
        return 20 + ce
    elif ji == 3:
        return 46 + ce
    return ce


def _cwwn_vol_to_zh(vol: int) -> tuple[int, int]:
    """卷号 → 倪柝声文集辑册 (ji, ce)。"""
    if vol <= 20:
        return 1, vol
    elif vol <= 46:
        return 2, vol - 20
    else:
        return 3, vol - 46


def _zh_book_title_to_en(book_zh: str) -> tuple[str, str]:
    mapped = _BOOK_TITLE_ZH_TO_EN.get(book_zh)
    if mapped is not None:
        return mapped, SOURCE_PATH_RULE
    return book_zh, SOURCE_PATH_RULE_AI


def _en_book_title_to_zh(book_en: str) -> tuple[str, str]:
    mapped = _BOOK_TITLE_EN_TO_ZH.get(book_en)
    if mapped is not None:
        return mapped, SOURCE_PATH_RULE
    return book_en, SOURCE_PATH_RULE_AI


def _rule_translate_source_zh(source_zh: str) -> tuple[str | None, str]:
    """
    路1c：中翻英规则解析出处。
    成功返回 (英文出处, 路径标签)，失败返回 (None, "")。
    """
    s = (source_zh or "").strip().strip("（）")
    s = s.replace('\u201c', '"').replace('\u201d', '"').replace('\u2018', "'").replace('\u2019', "'")
    if not s:
        return None, ""

    # 先剥段号
    base, _ = _strip_paragraph_suffix(s)
    base = base.strip()
    # 剥分段标记（大贰、大叁等）
    base = _ZH_SECTION_MARK_RE.sub("", base).strip()

    # 按第一个逗号切分
    parts = base.split("，", 1)
    head = parts[0].strip()
    tail = parts[1].strip() if len(parts) > 1 else ""

    # ── 圣经/注解 ─────────────────────────────────────────────────────────────
    if _ZH_BIBLE_RE.match(head) or _ZH_BIBLE_RE.match(base):
        # 去掉所有逗号，重新解析
        body = re.sub(r"[，,]", "", base)
        body = _ZH_BIBLE_RE.sub("", body).strip()
        # 提取注解
        footnote = ""
        fn_m = _ZH_FOOTNOTE_RE.search(body)
        if fn_m:
            footnote = f", footnote {fn_m.group(1)}"
            body = body[: fn_m.start()].strip()
        # 解析书卷+章节：优先匹配长缩写
        book_en = None
        rest = body
        for abbr_zh in sorted(_BIBLE_ABBR_ZH_TO_EN, key=len, reverse=True):
            if rest.startswith(abbr_zh):
                book_en = _BIBLE_ABBR_ZH_TO_EN[abbr_zh]
                rest = rest[len(abbr_zh):].strip()
                break
        if not book_en:
            return None, ""
        # 解析章节：章（系统B）+ 节（阿拉伯数字）
        ch_m = re.match(r"^([一二三四五六七八九十〇百千\d]+?)(\d+)[.。]?$", rest)
        if not ch_m:
            return None, ""
        ch_zh = ch_m.group(1).strip()
        verse = ch_m.group(2)
        ch_num = _parse_bible_chapter_zh(ch_zh)
        if not ch_num:
            return None, ""
        return (
            f"Holy Bible Recovery Version, {book_en} {ch_num}:{verse}{footnote}",
            SOURCE_PATH_RULE,
        )

    # ── 生命读经 ────────────────────────────────────────────────────────────────
    if "生命读经" in head:
        book_zh = head.replace("生命读经", "").strip()
        book_en = _LIFE_STUDY_BOOK_ZH_TO_EN.get(book_zh)
        if not book_en:
            return None, ""
        if not tail:
            return None, ""
        msg = _parse_msg_zh(tail)
        if not msg:
            return None, ""
        return f"Life-study of {book_en}, {msg}", SOURCE_PATH_RULE

    # ── 结晶读经 ────────────────────────────────────────────────────────────────
    if "结晶读经" in head:
        book_zh = head.replace("结晶读经", "").strip()
        book_en = _LIFE_STUDY_BOOK_ZH_TO_EN.get(book_zh)
        if not book_en:
            return None, ""
        if not tail:
            return None, ""
        msg = _parse_msg_zh(tail)
        if not msg:
            return None, ""
        return f"Crystallization-study of {book_en}, {msg}", SOURCE_PATH_RULE

    # ── 新约总论 ────────────────────────────────────────────────────────────────
    if head == "新约总论":
        msg = _parse_msg_zh(tail)
        if not msg:
            return None, ""
        return f"The Conclusion of the New Testament, {msg}", SOURCE_PATH_RULE

    # ── 李常受文集·信函与拾遗 ─────────────────────────────────────────────────
    if head.startswith("李常受文集信函与拾遗"):
        vol_m = re.match(r"^李常受文集信函与拾遗第([一二三四五六七八九十百千\d]+)册$", head)
        if not vol_m:
            return None, ""
        vol = _chinese_numeral_to_int(vol_m.group(1))
        prefix = f"CWWL, Letters & Gleanings, vol. {vol}"
        if not tail:
            return prefix, SOURCE_PATH_RULE
        tail_parts = tail.split("，")
        msg_str = _parse_msg_zh(tail_parts[-1].strip())
        if not msg_str:
            return None, ""
        if len(tail_parts) == 1:
            return f"{prefix}, {msg_str}", SOURCE_PATH_RULE
        book_zh = "，".join(tail_parts[:-1]).strip()
        book_en, book_path = _zh_book_title_to_en(book_zh)
        if book_path == SOURCE_PATH_RULE_AI:
            return f'{prefix}, "{book_en}," {msg_str}', SOURCE_PATH_RULE_AI
        return f'{prefix}, "{book_en}," {msg_str}', SOURCE_PATH_RULE

    # ── 李常受文集 ──────────────────────────────────────────────────────────────
    m = _ZH_CWWL_RE.match(head)
    if m:
        year_en = _year_zh_to_en(m.group(1))
        vol = _chinese_numeral_to_int(m.group(2))
        prefix = f"CWWL, {year_en}, vol. {vol}"
        if not tail:
            return prefix, SOURCE_PATH_RULE
        # 按逗号切分尾部，最后一段是篇/章数
        tail_parts = tail.split("，")
        book_zh, msg_combined = _split_tail_book_and_msgs(tail_parts)
        if not msg_combined:
            return None, ""
        msg_str = _parse_msg_zh(msg_combined)
        if not msg_str:
            return None, ""
        if not book_zh:
            return f"{prefix}, {msg_str}", SOURCE_PATH_RULE
        book_en, book_path = _zh_book_title_to_en(book_zh)
        return f'{prefix}, "{book_en}," {msg_str}', book_path

    # ── 倪柝声文集 ──────────────────────────────────────────────────────────────
    m = _ZH_CWWN_RE.match(head)
    if m:
        ji = _chinese_numeral_to_int(m.group(1))
        ce = _chinese_numeral_to_int(m.group(2))
        vol = _cwwn_zh_to_vol(ji, ce)
        prefix = f"CWWN, vol. {vol}"
        if not tail:
            return prefix, SOURCE_PATH_RULE
        tail_parts = tail.split("，")
        book_zh, msg_combined = _split_tail_book_and_msgs(tail_parts)
        if not msg_combined:
            return None, ""
        msg_str = _parse_msg_zh(msg_combined)
        if not msg_str:
            return None, ""
        if not book_zh:
            return f"{prefix}, {msg_str}", SOURCE_PATH_RULE
        book_en, book_path = _zh_book_title_to_en(book_zh)
        return f'{prefix}, "{book_en}," {msg_str}', book_path

    # ── 节期类 ──────────────────────────────────────────────────────────────────
    m = _ZH_YEAR_RE.match(head)
    if m:
        year_raw = m.group(1)
        year_en = year_raw if year_raw.isdigit() else _year_zh_to_en(year_raw)
        conf_zh = head[m.end():].strip()
        conf_en = _CONFERENCE_ZH_TO_EN.get(conf_zh)
        if not conf_en:
            return None, ""
        tail_parts = tail.split("，")
        book_zh, msg_combined = _split_tail_book_and_msgs(tail_parts)
        if not msg_combined:
            return None, ""
        msg_str = _parse_msg_zh(msg_combined)
        if not msg_str:
            return None, ""
        if not book_zh:
            return f"{year_en} {conf_en}, {msg_str}", SOURCE_PATH_RULE
        book_zh = book_zh.strip('"“"')
        book_en, book_path = _zh_book_title_to_en(book_zh)
        return f'{year_en} {conf_en}, "{book_en}," {msg_str}', book_path

    # ── 真理课程 ────────────────────────────────────────────────────────────────
    if head == "真理课程":
        tl_m = _ZH_TRUTH_LESSONS_RE.match(base)
        if not tl_m and tail:
            tp = tail.split("，")
            if tp:
                tl_m = _ZH_TRUTH_LESSONS_RE.match(f"真理课程，{tp[0]}")
            if not tl_m and len(tp) >= 2:
                tl_m = _ZH_TRUTH_LESSONS_RE.match(f"真理课程，{tp[0]}，{tp[1]}")
        if not tl_m:
            return None, ""
        g1 = tl_m.group(1)
        g2 = tl_m.group(2) or tl_m.group(3)
        level = int(g1) if g1.isdigit() else _chinese_numeral_to_int(g1)
        vol = int(g2) if g2.isdigit() else _chinese_numeral_to_int(g2)
        prefix = f"Truth Lessons, Level {level}, vol. {vol}"
        if not tail:
            return prefix, SOURCE_PATH_RULE
        tail_parts = tail.split("，")
        _, msg_combined = _split_tail_book_and_msgs(tail_parts)
        if not msg_combined:
            return None, ""
        msg_str = _parse_msg_zh(msg_combined)
        if not msg_str:
            return None, ""
        return f"{prefix}, {msg_str}", SOURCE_PATH_RULE

    return None, ""


def _rule_translate_source_en(source_en: str) -> tuple[str | None, str]:
    """
    路1c：英翻中规则解析出处。
    成功返回 (中文出处, 路径标签)，失败返回 (None, "")。
    """
    s = (source_en or "").strip().strip("()")
    s = s.replace('\u201c', '"').replace('\u201d', '"').replace('\u2018', "'").replace('\u2019', "'")
    if not s:
        return None, ""

    base = _strip_en_paragraph_suffix(s).strip()
    parts = base.split(",", 2)
    head = parts[0].strip()

    # ── 圣经/注解 ─────────────────────────────────────────────────────────────
    if head == "Holy Bible Recovery Version":
        rest = base[len("Holy Bible Recovery Version"):].lstrip(",").strip()
        fn_m = _EN_FOOTNOTE_RE.search(rest)
        footnote = ""
        if fn_m:
            footnote = f"，注{fn_m.group(1)}"
            rest = rest[: fn_m.start()].strip().rstrip(",").strip()
        # 解析书卷+章:节
        bk_m = re.match(
            r"^([1-3]\s+\w+\.?|\w+\.?)\s+(\d+):(\d+)\.?$", rest
        )
        if not bk_m:
            return None, ""
        book_en = bk_m.group(1).strip()
        ch_num = int(bk_m.group(2))
        verse = bk_m.group(3)
        book_zh = _BIBLE_ABBR_EN_TO_ZH.get(book_en)
        if not book_zh:
            return None, ""
        ch_zh = _int_to_bible_chapter_zh(ch_num)
        return f"恢复本圣经{book_zh}{ch_zh}{verse}{footnote}", SOURCE_PATH_RULE

    # ── 生命读经 ────────────────────────────────────────────────────────────────
    if head.lower().startswith("life-study of"):
        book_en = re.sub(r"^life-study of\s*", "", head, flags=re.IGNORECASE).strip()
        book_zh = _LIFE_STUDY_BOOK_EN_TO_ZH.get(book_en)
        if not book_zh:
            return None, ""
        tail = base[base.index(",") + 1:].strip() if "," in base else ""
        if not tail:
            return None, ""
        msg = _parse_msg_en(tail)
        if not msg:
            return None, ""
        return f"{book_zh}生命读经，{msg}", SOURCE_PATH_RULE

    # ── 结晶读经 ────────────────────────────────────────────────────────────────
    if head.lower().startswith("crystallization-study of"):
        book_en = re.sub(
            r"^crystallization-study of\s*", "", head, flags=re.IGNORECASE
        ).strip()
        book_zh = _LIFE_STUDY_BOOK_EN_TO_ZH.get(book_en)
        if not book_zh:
            return None, ""
        tail = base[base.index(",") + 1:].strip() if "," in base else ""
        if not tail:
            return None, ""
        msg = _parse_msg_en(tail)
        if not msg:
            return None, ""
        return f"{book_zh}结晶读经，{msg}", SOURCE_PATH_RULE

    # ── 新约总论 ────────────────────────────────────────────────────────────────
    if head in ("The Conclusion of the New Testament",
                "Conclusion of the New Testament"):
        tail = base[base.index(",") + 1:].strip() if "," in base else ""
        msg = _parse_msg_en(tail)
        if not msg:
            return None, ""
        return f"新约总论，{msg}", SOURCE_PATH_RULE

    # ── 李常受文集 ──────────────────────────────────────────────────────────────
    if head in ("CWWL", "The Collected Works of Witness Lee"):
        lg_m = _EN_CWWL_LG_RE.match(base)
        if lg_m:
            vol = int(lg_m.group(1))
            prefix = f"李常受文集信函与拾遗第{_int_to_chinese_numeral(vol)}册"
            rest = base[lg_m.end():].lstrip(",").strip()
            if not rest:
                return prefix, SOURCE_PATH_RULE
            msg_kw_m = re.search(r"(msgs?\.|chs?\.)\s*\d", rest)
            if msg_kw_m:
                book_part = rest[: msg_kw_m.start()].strip().strip('",').strip()
                msg_str = rest[msg_kw_m.start() :].strip()
                msg = _parse_msg_en(msg_str)
                if not msg:
                    return None, ""
                if book_part:
                    book_zh, book_path = _en_book_title_to_zh(book_part)
                    return f"{prefix}，{book_zh}，{msg}", book_path
                return f"{prefix}，{msg}", SOURCE_PATH_RULE
            return None, ""
        m = _EN_CWWL_RE.match(base)
        if not m:
            return None, ""
        year_zh = _year_en_to_zh(m.group(1))
        vol = int(m.group(2))
        prefix = f"李常受文集{year_zh}年第{_int_to_chinese_numeral(vol)}册"
        rest = base[m.end():].lstrip(",").strip()
        if not rest:
            return prefix, SOURCE_PATH_RULE
        # 用篇/章关键词从右定位，兼容有引号、无引号、缺引号
        msg_kw_m = re.search(r"(msgs?\.|chs?\.)\s*\d", rest)
        if msg_kw_m:
            book_part = rest[: msg_kw_m.start()].strip().strip('",').strip()
            msg_str = rest[msg_kw_m.start() :].strip()
            msg = _parse_msg_en(msg_str)
            if not msg:
                return None, ""
            if book_part:
                book_zh, book_path = _en_book_title_to_zh(book_part)
                return f"{prefix}，{book_zh}，{msg}", book_path
            return f"{prefix}，{msg}", SOURCE_PATH_RULE
        # 无书名无篇章关键词，尝试直接解析
        msg = _parse_msg_en(rest)
        if not msg:
            return None, ""
        return f"{prefix}，{msg}", SOURCE_PATH_RULE

    # ── 倪柝声文集 ──────────────────────────────────────────────────────────────
    if head in ("CWWN", "The Collected Works of Watchman Nee"):
        m = _EN_CWWN_RE.match(base)
        if not m:
            return None, ""
        vol = int(m.group(1))
        ji, ce = _cwwn_vol_to_zh(vol)
        prefix = f"倪柝声文集第{_int_to_chinese_numeral(ji)}辑第{_int_to_chinese_numeral(ce)}册"
        rest = base[m.end():].lstrip(",").strip()
        if not rest:
            return prefix, SOURCE_PATH_RULE
        msg_kw_m = re.search(r"(msgs?\.|chs?\.)\s*\d", rest)
        if msg_kw_m:
            book_part = rest[: msg_kw_m.start()].strip().strip('",').strip()
            msg_str = rest[msg_kw_m.start() :].strip()
            msg = _parse_msg_en(msg_str)
            if not msg:
                return None, ""
            if book_part:
                book_zh, book_path = _en_book_title_to_zh(book_part)
                return f"{prefix}，{book_zh}，{msg}", book_path
            return f"{prefix}，{msg}", SOURCE_PATH_RULE
        msg = _parse_msg_en(rest)
        if not msg:
            return None, ""
        return f"{prefix}，{msg}", SOURCE_PATH_RULE

    # ── 真理课程 ────────────────────────────────────────────────────────────────
    if head == "Truth Lessons":
        tl_m = _EN_TRUTH_LESSONS_RE.match(base)
        if not tl_m:
            return None, ""
        level = int(tl_m.group(1))
        vol = int(tl_m.group(2))
        level_zh = _int_to_chinese_numeral(level)
        vol_zh = _int_to_chinese_numeral(vol)
        prefix = f"真理课程，{level_zh}级卷{vol_zh}"
        rest = base[tl_m.end():].lstrip(",").strip()
        if not rest:
            return prefix, SOURCE_PATH_RULE
        msg = _parse_msg_en(rest)
        if not msg:
            return None, ""
        return f"{prefix}，{msg}", SOURCE_PATH_RULE

    # ── 节期类 ──────────────────────────────────────────────────────────────────
    m = _EN_YEAR_RE.match(base)
    if m:
        year_en = m.group(1)
        conf_en = m.group(2).strip().rstrip(",")
        conf_zh = _CONFERENCE_EN_TO_ZH.get(conf_en)
        if not conf_zh:
            return None, ""
        tail = base[m.end():].lstrip(",").strip()
        msg = _parse_msg_en(tail)
        if not msg:
            return None, ""
        return f"{year_en}年{conf_zh}，{msg}", SOURCE_PATH_RULE

    return None, ""


async def translate_source_zh_batch(
    items: list[tuple[int, list[str], list[dict[str, Any]], bool]],
) -> tuple[dict[int, str], dict[int, list[str]], float]:
    """
    批量翻译 reference_source_zh 列表。
    items: [(prep_index, source_list, line_refs, has_star), ...]
    整单一次 Gemini 处理所有路1推算 + 路2 未命中出处。
    返回：(译文 map, 路径标签 map, 费用 USD)
    """
    if not items:
        return {}, {}, 0.0

    results: dict[int, str] = {}
    paths_map: dict[int, list[str]] = {}
    total_cost_usd = 0.0
    road2_tasks: list[_SourceRoad2Task] = []
    road2_keys: set[tuple[int, int]] = set()
    pending: dict[int, tuple[list[str], bool, list[str], list[str]]] = {}

    for prep_idx, source_list, line_refs, has_star in items:
        if not source_list:
            continue

        en_parts = [""] * len(source_list)
        path_parts = [""] * len(source_list)

        for i, source_zh in enumerate(source_list):
            _sp_base = _normalize_for_source_pool(source_zh)
            _sp_en = lookup_source_pool_en(_sp_base)
            if _sp_en:
                if source_zh.strip().endswith(("：", ":")):
                    _sp_en = _sp_en + ":"
                en_parts[i] = f"({_sp_en})"
                path_parts[i] = SOURCE_PATH_POOL
                continue
            base, _ = _strip_paragraph_suffix(source_zh)
            base = base.strip().strip("（）")
            # 路1a：节期类出处查 feasts pool（仅年份开头）
            if _ZH_YEAR_RE.match(base):
                feast_en = await _feasts_pool_lookup(base)
                if feast_en:
                    en_parts[i] = f"({feast_en})"
                    path_parts[i] = SOURCE_PATH_RAG
                    logger.info("[source_translator] 路1a节期命中: %s → %s", source_zh, feast_en)
                    continue
            table_en = lookup_source_en(base)
            if table_en:
                en_parts[i] = table_en
                path_parts[i] = SOURCE_PATH_TABLE
                logger.info("[source_translator] 路1b表命中: %s → %s", source_zh, table_en)
                continue
            # 路1c：规则翻译兜底
            rule_en, rule_path = _rule_translate_source_zh(source_zh)
            if rule_en:
                if rule_path == SOURCE_PATH_RULE_AI:
                    road2_tasks.append(
                        _SourceRoad2Task(
                            prep_idx=prep_idx,
                            src_idx=i,
                            source_zh=rule_en,
                            line_refs=[],
                        )
                    )
                    road2_keys.add((prep_idx, i))
                    path_parts[i] = SOURCE_PATH_RULE_AI
                else:
                    en_parts[i] = rule_en
                    path_parts[i] = rule_path
                logger.info("[source_translator] 路1c规则命中: %s → %s", source_zh, rule_en)
                continue
            # 路2 Gemini
            road2_keys.add((prep_idx, i))
            road2_tasks.append(
                _SourceRoad2Task(
                    prep_idx=prep_idx,
                    src_idx=i,
                    source_zh=source_zh,
                    line_refs=line_refs,
                )
            )

        pending[prep_idx] = (en_parts, has_star, source_list, path_parts)

    if road2_tasks:
        logger.info(
            "[source_translator] 出处整单 Gemini: road2=%d",
            len(road2_tasks),
        )
        gemini_map, gemini_cost = await _gemini_sources_once([], road2_tasks)
        total_cost_usd += gemini_cost
        for (prep_idx, src_idx), translated in gemini_map.items():
            en_parts, _, _, path_parts = pending[prep_idx]
            en_parts[src_idx] = _clean_source_en(translated) if translated else ""
            if (prep_idx, src_idx) in road2_keys:
                if not path_parts[src_idx]:
                    path_parts[src_idx] = SOURCE_PATH_AI
            logger.info(
                "[source_translator] Gemini出处: prep=%s idx=%s → %s",
                prep_idx,
                src_idx,
                translated,
            )

    for prep_idx, (en_parts, has_star, source_list, path_parts) in pending.items():
        for i, source_zh in enumerate(source_list):
            if not en_parts[i]:
                en_parts[i] = source_zh
                path_parts[i] = ""
        formatted = format_source_en(en_parts, has_star)
        results[prep_idx] = formatted
        paths_map[prep_idx] = path_parts
        logger.info(
            "[source_translator] 出处译文 prep=%s %s | debug %s",
            prep_idx,
            formatted,
            format_source_en_analysis(en_parts, has_star),
        )

    _sp_rows: list[dict[str, str]] = []
    for _prep_idx, (_en_parts, _has_star, _source_list, _path_parts) in pending.items():
        for _i, (_en, _path) in enumerate(zip(_en_parts, _path_parts)):
            if _path not in (SOURCE_PATH_RULE_AI, SOURCE_PATH_AI):
                continue
            _zh_clean = _normalize_for_source_pool(_source_list[_i])
            _en_clean = _en.strip().strip("()")
            if _zh_clean and _en_clean:
                _sp_rows.append({"zh": _zh_clean, "en": _en_clean, "source_type": _path})
    if _sp_rows:
        append_source_pool_records(_sp_rows)

    return results, paths_map, total_cost_usd


async def verify_source_lines(lines: list[str]) -> None:
    """解析 + 路1出处查询，打印每条出处的匹配与译文（验证用）。"""
    for line_no, line in enumerate(lines, 1):
        print(f"\n{'='*60}")
        print(f"行 {line_no}: {line[:80]}...")
        stripped, sources = parse_source_from_line(line)
        has_star = bracket_has_star(format_source_zh(sources))
        print(f"剥离正文: {stripped[:60]}...")
        print(f"出处数: {len(sources)}, has_star={has_star}")

        en_parts: list[str] = []
        for i, src in enumerate(sources, 1):
            detail = await _kg_rag_source_lookup_debug(src)
            print(f"[出处{i}] source_zh查询词: {detail.query}")
            print(f"[出处{i}] 匹配方式: {detail.match_method}")
            print(f"[出处{i}] source_en: {detail.source_en or '(空)'}")
            print(f"[出处{i}] para_en: {detail.para_en or '(空)'}")
            print(f"[出处{i}] 最终拼接: {detail.final_part or '(空)'}")
            en_parts.append(detail.final_part)

        print(f"全行出处块(debug): {format_source_en_analysis(en_parts, has_star) or '(空)'}")
        print(f"全行出处块: {format_source_en(en_parts, has_star) or '(空)'}")


if __name__ == "__main__":
    _TEST_LINES = [
        "1\u3000亚当是旧团体人（人类）的元首，凡他所行的，以及一切发生在他身上的，全人类都有分─12节。（2000年安那翰秋季全时间训练，第二篇；李常受文集一九九〇年第一册，三一神作三部分人的生命，第一章，第一段；李常受文集一九八〇年第一册，成全训练，第二十二章，第一段）",
        "1\u3000亚当是旧团体人（人类）的元首，凡他所行的，以及一切发生在他身上的，全人类都有分─12节。（2000年安那翰秋季全时间训练，第二篇；路加福音生命读经，第五十六篇，第三段*）",
        "1\u3000亚当是旧团体人（人类）的元首，凡他所行的，以及一切发生在他身上的，全人类都有分─12节。（2000年感恩节特会，第四篇；腓立比书生命读经，第三十六篇，第四段*）",
        "1\u3000亚当是旧团体人（人类）的元首，凡他所行的，以及一切发生在他身上的，全人类都有分─12节。（2000年安那翰秋季全时间训练，第二篇；新约总论，第一百一十四篇，第十七段*）",
    ]
    asyncio.run(verify_source_lines(_TEST_LINES))
