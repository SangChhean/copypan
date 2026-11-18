# -*- coding: utf-8 -*-
"""vendor 之外的经文出处补强：繁简、别名、英文、章篇节、范围与整卷等。

所有规则均为通用改写；不针对单个测试用例硬编码。数据表见 scripture/data/。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from scripture.vendor_get_vers_v21 import BOOK_MAP, STD2IDX, STD_ORDER

_DATA = Path(__file__).resolve().parent / "data"

# 章号位置「X百Y」（Y 单个汉字数字、无零）→ X百Y十
_COLLOQUIAL_HUNDRED = re.compile(
    r"(?<![零〇○一二三四五六七八九十百千])([一二三四五六七八九]?百)([一二三四五六七八九])(?![零〇○十一二三四五六七八九百千])"
)

# 书名号
_BOOK_MARKS = re.compile(r"[《》『』「」]")

# 空白类
_WS = re.compile(r"[\s\u00a0\u3000]+")

# 范围符统一
_RANGE_SEP = re.compile(r"[～~－—–−]")

# 同章：书+中文章+阿拉伯节 + 至/到 + 阿拉伯节（无章）
_SAME_CH_ZHI = re.compile(
    r"(?P<head>[\u4e00-\u9fff]{1,8}[一二三四五六七八九十百千〇零○]+)"
    r"(?P<v1>\d+)\s*(?:至|到)\s*(?P<v2>\d+)(?!\s*[章节篇])"
)

# 跨章简写：太三1-四2 / 太三1至四2 / 约三16-四1
_CROSS_SHORT = re.compile(
    r"(?P<book>[\u4e00-\u9fff]{1,12}?)"
    r"(?P<c1>[一二三四五六七八九十百千〇零○]+)"
    r"(?P<v1>\d+)\s*(?:[-~～－—–]|至|到)\s*"
    r"(?P<c2>[一二三四五六七八九十百千〇零○]+)"
    r"(?P<v2>\d+)"
)

# 冒号跨章：创1:1-2:3 或 创世记1:1-2:3（在阿拉伯章改写之前处理）
_CROSS_COLON = re.compile(
    r"(?P<book>[\u4e00-\u9fff]{1,12}?)"
    r"(?P<c1>\d+)\s*:\s*(?P<v1>\d+)\s*[-~～－—–至到]\s*"
    r"(?P<c2>\d+)\s*:\s*(?P<v2>\d+)"
)

# 中文「N章N节至N章N节」已由 vendor 支持；「N章十六节至十八节」同章
_SAME_CH_CN_ZHI = re.compile(
    r"(?P<head>[\u4e00-\u9fff]{1,12}第?[一二三四五六七八九十百千〇零○\d]+章)"
    r"第?(?P<v1>[一二三四五六七八九十百千〇零○\d]+)节\s*(?:至|到)\s*"
    r"第?(?P<v2>[一二三四五六七八九十百千〇零○\d]+)节"
)

# 单章书（数字直接当节号）
_SINGLE_CHAPTER_STD = frozenset({"俄", "门", "约贰", "约叁", "犹"})

# 阿拉伯 + 章/篇 + 可选节（不把孤立「N节」收成章）
_ARABIC_CHAPTER_UNIT = re.compile(
    r"(?P<book>[\u4e00-\u9fff]{1,12}?)"
    r"第?(?P<ch>\d+)\s*(?P<unit>[章节篇])"
    r"(?:第?(?P<v1>\d+)(?:\s*[-~～－—–至到]\s*(?P<v2>\d+))?\s*节?)?"
)

# 整章范围：创一至三章 / 约三到五章 / 约翰福音三章到五章 / 诗一至十篇 / 创世记1-3章
# 单位只允许章/篇（不含节），且章号不含「中文+阿拉伯」混写，避免「三16-18节」误伤
_CH_RANGE = re.compile(
    r"^(?P<book>.+?)"
    r"(?:第)?(?P<c1>(?:[一二三四五六七八九十百千〇零○]+|\d+))\s*(?:[章篇])?\s*"
    r"(?:至|到|[-~～－—–])\s*"
    r"(?:第)?(?P<c2>(?:[一二三四五六七八九十百千〇零○]+|\d+))\s*"
    r"(?P<unit>[章篇])\s*$"
)

# 仅书名（可带全书/整卷/整本）
_WHOLE_BOOK_SUFFIX = re.compile(r"(?:全书|整卷|整本)$")

# 英文出处：书名 + 章节
_EN_REF = re.compile(
    r"(?P<book>(?:(?:[123]|I{1,3}|III)\s*)?[A-Za-z][A-Za-z.]*(?:\s+of\s+[A-Za-z]+)?)"
    r"\s+"
    r"(?P<body>\d+\s*:\s*\d+(?:\s*[-–—−~～至到]\s*\d+(?:\s*:\s*\d+)?)?|\d+)",
    re.I,
)

_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "○": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _int_to_cn(n: int) -> str:
    digits = "零一二三四五六七八九"
    if n <= 0:
        return str(n)
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n % 10] if n % 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        return digits[tens] + "十" + (digits[ones] if ones else "")
    if n < 1000:
        h, rest = divmod(n, 100)
        body = digits[h] + "百"
        if rest == 0:
            return body
        if rest < 10:
            return body + "零" + digits[rest]
        return body + _int_to_cn(rest)
    return str(n)


def cn_num_to_int(s: str) -> Optional[int]:
    """中文数字 → int；支持廿/卅预处理后的常规形式与阿拉伯数字。"""
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    try:
        from scripture.vendor_get_vers_v21 import cn2num

        n = cn2num(s)
        if n is None:
            return None
        n = int(n)
        return n if n > 0 else None
    except Exception:
        return None


@lru_cache(maxsize=1)
def _load_t2s() -> dict[str, str]:
    raw = json.loads((_DATA / "t2s_chars.json").read_text(encoding="utf-8"))
    chars: dict[str, str] = dict(raw.get("chars") or {})
    # 长词优先
    return dict(sorted(chars.items(), key=lambda kv: len(kv[0]), reverse=True))


@lru_cache(maxsize=1)
def _load_aliases() -> tuple[list[tuple[str, str]], set[str]]:
    raw = json.loads((_DATA / "book_aliases.json").read_text(encoding="utf-8"))
    aliases = [(k, v) for k, v in (raw.get("aliases") or {}).items()]
    aliases.sort(key=lambda kv: len(kv[0]), reverse=True)
    person = set(raw.get("person_like") or [])
    return aliases, person


@lru_cache(maxsize=1)
def _load_en() -> tuple[list[tuple[str, str]], set[str], set[str]]:
    raw = json.loads((_DATA / "en_books.json").read_text(encoding="utf-8"))
    books = [(k, v) for k, v in (raw.get("books") or {}).items()]
    books.sort(key=lambda kv: len(kv[0]), reverse=True)
    excluded = {x.lower().rstrip(".") for x in (raw.get("excluded_abbreviations") or [])}
    person = {x.lower() for x in (raw.get("person_like_english") or [])}
    return books, excluded, person


@lru_cache(maxsize=1)
def _std_to_full() -> dict[str, str]:
    cands: dict[str, list[str]] = {s: [] for s in STD_ORDER}
    for alias, std in BOOK_MAP.items():
        if alias != std:
            cands.setdefault(std, []).append(alias)
    out: dict[str, str] = {}
    for std in STD_ORDER:
        aliases = cands.get(std) or []
        if not aliases:
            out[std] = std
            continue

        def score(a: str) -> tuple:
            suf = any(a.endswith(x) for x in ("福音", "书", "记", "纪")) or a in (
                "诗篇",
                "使徒行传",
                "雅歌",
                "传道书",
            )
            return (1 if suf else 0, len(a))

        out[std] = sorted(aliases, key=score, reverse=True)[0]
    return out


@lru_cache(maxsize=1)
def _full_and_std_names() -> list[str]:
    """全称 + 标准简称，长优先。"""
    fulls = list(_std_to_full().values())
    names = list(dict.fromkeys(fulls + list(STD_ORDER)))
    names.sort(key=len, reverse=True)
    return names


def traditional_to_simplified(text: str) -> str:
    """A：繁体 → 简体（本地对照表，非 OpenCC）。"""
    if not text:
        return text or ""
    table = _load_t2s()
    # 先替换多字符词
    for k, v in table.items():
        if len(k) > 1 and k in text:
            text = text.replace(k, v)
    # 再逐字
    return "".join(table.get(ch, ch) for ch in text)


def _apply_aliases(text: str) -> str:
    """C：最长匹配别名；人名同形仅在后接章节数字时替换。"""
    aliases, person = _load_aliases()
    # 章节起始：第? + 数字；不可是「一书/福音/书/记」等书名续写
    follow = re.compile(
        r"^(?:第?[一二三四五六七八九十百千〇零○廿卅\d]|[一二三四五六七八九十百千〇零○廿卅\d])"
    )
    book_cont = re.compile(r"^(?:福音|书|记|纪|一书|二书|三书|前书|后书|前|后)")
    i = 0
    out: list[str] = []
    while i < len(text):
        matched = False
        for alias, target in aliases:
            if not text.startswith(alias, i):
                continue
            after = text[i + len(alias) :]
            if alias in person:
                if not follow.match(after) or book_cont.match(after):
                    continue
            if target.startswith(alias) and after.startswith(target[len(alias) :]):
                continue
            out.append(target)
            i += len(alias)
            matched = True
            break
        if not matched:
            out.append(text[i])
            i += 1
    return "".join(out)


def _apply_en_books(text: str, *, whole_ok: bool) -> str:
    """I：英文书名 → 中文全称；仅后接章节，或整句书名（whole_ok）。"""
    books, excluded, person_en = _load_en()
    # 先处理整句
    stripped = text.strip()
    if whole_ok and stripped:
        low = stripped.lower().rstrip(".")
        for name, full in books:
            if name.lower().rstrip(".") == low:
                if name.lower().rstrip(".") in person_en:
                    return text  # 人名同形整句不当整卷
                return full
    # 文中替换：最长匹配 + 后接数字
    pattern_names = []
    for name, full in books:
        key = name.lower().rstrip(".")
        if key in excluded:
            continue
        pattern_names.append((name, full))

    def repl(m: re.Match[str]) -> str:
        raw_book = m.group("book")
        body = m.group("body")
        key = re.sub(r"\s+", " ", raw_book.strip()).lower().rstrip(".")
        key_nospace = key.replace(" ", "")
        for name, full in pattern_names:
            n = name.lower().rstrip(".")
            n2 = n.replace(" ", "")
            if key == n or key_nospace == n2:
                # 规范化 body 内空白与 en dash
                b = _RANGE_SEP.sub("-", body)
                b = re.sub(r"\s*", "", b)
                return f"{full}{b}"
        return m.group(0)

    # 允许 1Cor / I Cor. 等：扩展匹配
    en_pat = re.compile(
        r"(?P<book>(?:(?:[123]|I{1,3})\s*)?[A-Za-z][A-Za-z.]*(?:\s+of\s+[A-Za-z]+)?|"
        r"(?:(?:[123]|I{1,3})\s*)?[A-Za-z]+)"
        r"(?:\s+|\s*)"
        r"(?P<body>\d+\s*:\s*\d+(?:\s*[-–—−~～至到]\s*\d+(?:\s*:\s*\d+)?)?|\d+)",
        re.I,
    )
    return en_pat.sub(repl, text)


def _fix_nian_sa(text: str) -> str:
    """G：廿→二十，卅→三十。"""
    return text.replace("廿", "二十").replace("卅", "三十")


def _fix_colloquial_hundreds(text: str) -> str:
    """G：章号位置「一百二」→「一百二十」。"""

    def repl(m: re.Match[str]) -> str:
        return m.group(1) + m.group(2) + "十"

    return _COLLOQUIAL_HUNDRED.sub(repl, text)


def _rewrite_cross_colon(text: str) -> str:
    """E：创1:1-2:3 → 创一章一节至二章三节（vendor 可解析的跨章形）。"""

    def repl(m: re.Match[str]) -> str:
        book, c1, v1, c2, v2 = m.group("book", "c1", "v1", "c2", "v2")
        return (
            f"{book}{_int_to_cn(int(c1))}章{_int_to_cn(int(v1))}节至"
            f"{_int_to_cn(int(c2))}章{_int_to_cn(int(v2))}节"
        )

    return _CROSS_COLON.sub(repl, text)


def _rewrite_cross_short(text: str) -> str:
    """E：太三1-四2 → 太三章一节至四章二节。"""

    def repl(m: re.Match[str]) -> str:
        book, c1, v1, c2, v2 = m.group("book", "c1", "v1", "c2", "v2")
        # 避免把同章 三16-18 误当成跨章：c1/c2 都是纯中文章号且不同
        if c1 == c2:
            return m.group(0)
        return f"{book}{c1}章{_int_to_cn(int(v1))}节至{c2}章{_int_to_cn(int(v2))}节"

    return _CROSS_SHORT.sub(repl, text)


def _rewrite_same_ch_zhi(text: str) -> str:
    """E：腓二5至11 → 腓二5-11；三章十六节至十八节 → 三章16-18节。"""

    def repl_arab(m: re.Match[str]) -> str:
        return f"{m.group('head')}{m.group('v1')}-{m.group('v2')}"

    text = _SAME_CH_ZHI.sub(repl_arab, text)

    def repl_cn(m: re.Match[str]) -> str:
        v1 = cn_num_to_int(m.group("v1"))
        v2 = cn_num_to_int(m.group("v2"))
        if v1 is None or v2 is None:
            return m.group(0)
        return f"{m.group('head')}{v1}-{v2}节"

    return _SAME_CH_CN_ZHI.sub(repl_cn, text)


def _rewrite_arabic_chapter_units(text: str) -> str:
    """D：创1章 / 诗篇23篇 / 约翰福音3章16节 / 罗马书8章28-30节。"""

    def repl(m: re.Match[str]) -> str:
        book = m.group("book")
        ch = int(m.group("ch"))
        unit = m.group("unit")
        v1 = m.group("v1")
        v2 = m.group("v2")
        # 「N节」且 book 已含「章」：把 N 当节号，不改写成章
        if unit == "节" and v1 is None:
            if "章" in book or "篇" in book:
                return f"{book}{ch}"
            return m.group(0)
        cn_ch = _int_to_cn(ch)
        if v1 is None:
            if unit == "篇":
                return f"{book}{cn_ch}篇" if not book.endswith("篇") else f"{book[:-1]}{cn_ch}篇"
            if unit == "章":
                return f"{book}{cn_ch}章"
            return m.group(0)
        if v2:
            return f"{book}{cn_ch}{v1}-{v2}"
        return f"{book}{cn_ch}{v1}"

    return _ARABIC_CHAPTER_UNIT.sub(repl, text)


def _strip_marks_and_spaces(text: str) -> str:
    """B：去书名号；压缩空白（半角/全角/NBSP/换行）。"""
    text = _BOOK_MARKS.sub("", text)
    # CJK↔CJK、CJK↔数字 之间的空白去掉（约 三 16 / 约三\u300016）
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=\d)", "", text)
    text = re.sub(r"(?<=\d)\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"\s*([:：.\-–—−~～])\s*", r"\1", text)
    text = _WS.sub(" ", text)
    return text.strip()


def _dot_as_colon(text: str) -> str:
    """约3.16 → 约3:16（仅数字.数字）。"""
    return re.sub(r"(?<=\d)\.(?=\d)", ":", text)


def _strip_di_before_chapter(text: str) -> str:
    """第一章和第二章 → 一章和二章（vendor 对「第…和…」只收前半）。"""
    return re.sub(r"第([一二三四五六七八九十百千〇零○\d]+[章篇])", r"\1", text)


def bare_chapter_forms(text: str) -> str:
    """补整章简写：创一→创一章；诗23→诗二三篇；单章书「俄1」→「俄1」（节号，不改章）。"""
    m = re.fullmatch(
        r"([\u4e00-\u9fff]{1,12}?)([一二三四五六七八九十百千〇零○]+)",
        text,
    )
    if m and not text.endswith(("章", "节", "篇")):
        book, ch = m.group(1), m.group(2)
        std = _resolve_book_exact(book)
        if std:
            if std in _SINGLE_CHAPTER_STD:
                # 单章书：中文数字当节 → 书+1+阿拉伯节 形如 俄1 / 门6
                n = cn_num_to_int(ch)
                if n is not None:
                    return f"{book}{n}" if std != BOOK_MAP.get(book, std) else f"{std}{n}"
                return text
            unit = "篇" if book in ("诗", "诗篇") or book.endswith("诗篇") else "章"
            if book.endswith("篇"):
                return f"{book[:-1]}{ch}篇"
            return f"{book}{ch}{unit}"
    m2 = re.fullmatch(r"([\u4e00-\u9fff]{1,12}?)(\d+)", text)
    if m2 and ":" not in text:
        book, ch = m2.group(1), int(m2.group(2))
        std = _resolve_book_exact(book)
        if std:
            if std in _SINGLE_CHAPTER_STD:
                # 保持「书+阿拉伯节」，vendor 会收成 1:节
                return f"{book}{ch}"
            cn = _int_to_cn(ch)
            if book in ("诗", "诗篇") or book.endswith("诗篇"):
                base = book[:-1] if book.endswith("篇") else book
                return f"{base}{cn}篇"
            return f"{book}{cn}章"
    return text


def _resolve_book_exact(book: str) -> Optional[str]:
    """书名 → 标准简称；要求整段为已知全称/简称/别名，不做「约三」这类截断。"""
    if not book:
        return None
    if book in BOOK_MAP:
        return BOOK_MAP[book]
    full_map = _std_to_full()
    for std, full in full_map.items():
        if book == full:
            return std
    aliases, _person = _load_aliases()
    for alias, target in aliases:
        if book == alias or book == target:
            return BOOK_MAP.get(target) or BOOK_MAP.get(alias)
    return None


def _resolve_book_prefix(book: str) -> Optional[str]:
    """书名前缀 → 标准简称（允许全称前缀；不做把「约三」收成「约」）。"""
    exact = _resolve_book_exact(book)
    if exact:
        return exact
    if not book:
        return None
    # 仅当 book 是某全称的前缀且自身不是「简称+残留汉字」时
    for std, full in _std_to_full().items():
        if full.startswith(book) and len(book) >= 2:
            return std
    return None


def match_whole_book(text: str) -> Optional[str]:
    """H：整句只有书名（全称/简称/英文）时可返回标准简称；人名同形简称除外。"""
    s = traditional_to_simplified(text)
    s = _BOOK_MARKS.sub("", s)
    s = _WS.sub("", s)
    s = _WHOLE_BOOK_SUFFIX.sub("", s)
    if not s:
        return None
    # 英文整卷
    books, _exc, person_en = _load_en()
    low = s.lower().rstrip(".")
    for name, full in books:
        if name.lower().rstrip(".") == low:
            if name.lower().rstrip(".") in person_en:
                return None
            std = BOOK_MAP.get(full)
            return std
    # 中文全称/简称
    aliases, person = _load_aliases()
    if s in person:
        return None  # 人名同形裸名
    if s in BOOK_MAP:
        std = BOOK_MAP[s]
        # 简称若在 person_like 的目标书对应的短名，且输入是短人名，已在上面处理
        # 「犹大」在 person；「犹大书」不在
        return std
    for full in _full_and_std_names():
        if s == full:
            return BOOK_MAP.get(full, _resolve_book_prefix(full))
    for alias, target in aliases:
        if s == alias and alias not in person:
            return BOOK_MAP.get(target) or _resolve_book_prefix(target)
        if s == target:
            return BOOK_MAP.get(target)
    return None


# 无「章/篇」字的整章范围：番一~三 / 士六-九（两端均为纯中文章号）
_CH_RANGE_BARE = re.compile(
    r"^(?P<book>.+?)"
    r"(?P<c1>[一二三四五六七八九十百千〇零○]+)\s*"
    r"(?:至|到|[-~～－—–])\s*"
    r"(?P<c2>[一二三四五六七八九十百千〇零○]+)\s*$"
)


def match_chapter_range(text: str) -> Optional[tuple[str, int, int]]:
    """H：整段为整章范围时返回 (std, c1, c2)。"""
    s = traditional_to_simplified(text)
    s = _BOOK_MARKS.sub("", s)
    s = _WS.sub("", s)
    s = _fix_nian_sa(s)
    s = _RANGE_SEP.sub("-", s)
    s = _apply_aliases(s)
    m = _CH_RANGE.match(s) or _CH_RANGE_BARE.match(s)
    if not m:
        return None
    book = m.group("book")
    c1 = cn_num_to_int(m.group("c1"))
    c2 = cn_num_to_int(m.group("c2"))
    if c1 is None or c2 is None or c1 > c2:
        return None
    std = _resolve_book_exact(book) or _resolve_book_prefix(book)
    if not std:
        return None
    return std, c1, c2


def enhance_ref_text(text: str) -> str:
    """主预处理管线（A–G、I 的改写部分）。不 strip 调用方未要求去掉的语义字符之外的内容前，先做结构规范化。"""
    if not text:
        return text or ""
    s = traditional_to_simplified(text)
    s = _fix_nian_sa(s)
    s = s.replace("：", ":")
    s = _RANGE_SEP.sub("-", s)
    s = _strip_marks_and_spaces(s)
    s = _dot_as_colon(s)
    # 英文先于中文别名，避免「1 John」→「约翰一书」后再被「约翰」吞掉
    s = _apply_en_books(s, whole_ok=False)
    s = _apply_aliases(s)
    s = _strip_di_before_chapter(s)
    s = _fix_colloquial_hundreds(s)
    s = _rewrite_cross_colon(s)
    s = _rewrite_cross_short(s)
    s = _rewrite_same_ch_zhi(s)
    s = _rewrite_arabic_chapter_units(s)
    s = _WS.sub(" ", s).strip()
    # 整段「创一」「诗23」等补「章/篇」改写放到 parse_refs 回退里，
    # 避免 preprocess 把「诗二十三」改成「诗二十三篇」影响既有用例。
    return s


def merge_chapter_with_verse(refs: list[Any]) -> list[Any]:
    """F：同一表达式里的整章+同章经节合并为经节；跨章「一章26节和二章7节」保留两节、去掉整章。

    vendor 的 group 带 start/end；同 raw 内先按章去整章。
    相邻两组若为「…章」+「…节」且同书同章，也合并（第一章第一节）。
    局限：无更细 token 偏移时，只能按 Ref 序列与 raw 启发式。【保守】
    """
    if not refs:
        return refs
    KIND_CHAPTER = "whole_chapter"
    KIND_VERSE = "verse_range"
    KIND_CROSS = "cross_chapter"

    # 1) 按 raw 分组去掉同章整章
    by_raw: dict[str, list] = {}
    order: list[str] = []
    for r in refs:
        key = r.raw or id(r)
        if key not in by_raw:
            by_raw[key] = []
            order.append(key)
        by_raw[key].append(r)
    step1: list = []
    for key in order:
        group = by_raw[key]
        verse_chs = {
            (r.book, r.chapter)
            for r in group
            if r.kind in (KIND_VERSE, KIND_CROSS)
        }
        for r in group:
            if r.kind == KIND_CHAPTER and (r.book, r.chapter) in verse_chs:
                continue
            step1.append(r)

    # 2) 相邻组：整章 + 同书同章经节
    out: list = []
    i = 0
    while i < len(step1):
        if (
            i + 1 < len(step1)
            and step1[i].kind == KIND_CHAPTER
            and step1[i + 1].kind in (KIND_VERSE, KIND_CROSS)
            and step1[i].book == step1[i + 1].book
            and step1[i].chapter == step1[i + 1].chapter
        ):
            out.append(step1[i + 1])
            i += 2
            continue
        out.append(step1[i])
        i += 1
    return out
