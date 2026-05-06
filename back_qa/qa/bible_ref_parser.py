# -*- coding: utf-8 -*-
"""从用户自然语言问题中抽取圣经卷、章、节（依赖 bible_service._bible 已加载）。"""

from __future__ import annotations

import re
from typing import Any

from back_qa.qa import bible_service

# -----------------------------------------------------------------------------
# 懒加载缓存
# -----------------------------------------------------------------------------

_name_map: dict[str, int] | None = None
_abbr_en_map: dict[str, int] | None = None

# （名称字符串 → book）；与 JSON 互不冲突的常见省略（短名后出现则覆盖同名键仍可接受）
_COMMON_ALIASES: tuple[tuple[str, int], ...] = (
    ("约翰福音", 43),
    ("约翰", 43),
    ("约", 43),
    ("创世记", 1),
    ("创世", 1),
    ("创", 1),
    ("腓立比书", 50),
    ("腓立比", 50),
    ("腓", 50),
    ("马太福音", 40),
    ("马太", 40),
    ("太", 40),
    ("马可福音", 41),
    ("马可", 41),
    ("可", 41),
    ("路加福音", 42),
    ("路加", 42),
    ("路", 42),
    ("使徒行传", 44),
    ("使徒", 44),
    ("徒", 44),
    ("罗马书", 45),
    ("罗马", 45),
    ("罗", 45),
    ("启示录", 66),
    ("启示", 66),
    ("启", 66),
    ("诗篇", 19),
    ("诗", 19),
)


def _strip_en_abbr(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _add_name(m: dict[str, int], key: str, book: int) -> None:
    k = (key or "").strip()
    if not k:
        return
    m[k] = book


def _build_lookup_tables() -> tuple[dict[str, int], dict[str, int]]:
    """
    从 _bible 内存数据构建两张对照表：
    - name_map: {名称字符串 → book编号}，收录每卷的
      name_gb、name_big5、name_en、abbr_gb、abbr_big5、abbr_en
      以及常见省略形式
    - abbr_en_map: {英文缩写（小写，去点）→ book编号}
    """
    name_map: dict[str, int] = {}
    abbr_en_map: dict[str, int] = {}

    for book_id, vol in bible_service._bible.items():
        if not isinstance(vol, dict):
            continue
        b = vol.get("book", book_id)
        try:
            b = int(b)
        except (TypeError, ValueError):
            continue

        for field in ("name_gb", "name_big5", "name_en", "abbr_gb", "abbr_big5", "abbr_en"):
            v = vol.get(field)
            if isinstance(v, str) and v.strip():
                _add_name(name_map, v.strip(), b)

        abbr_en = vol.get("abbr_en")
        if isinstance(abbr_en, str) and abbr_en.strip():
            raw = abbr_en.strip()
            key = _strip_en_abbr(raw)
            if key:
                abbr_en_map[key] = b
            no_dot = raw.replace(".", "").strip()
            if no_dot:
                k2 = _strip_en_abbr(no_dot)
                if k2:
                    abbr_en_map[k2] = b

        name_en = vol.get("name_en")
        if isinstance(name_en, str) and name_en.strip():
            k3 = _strip_en_abbr(name_en)
            if k3:
                abbr_en_map[k3] = b

    for alias, bid in _COMMON_ALIASES:
        _add_name(name_map, alias, bid)

    return name_map, abbr_en_map


def _ensure_tables() -> tuple[dict[str, int], dict[str, int]]:
    global _name_map, _abbr_en_map
    if _name_map is None or _abbr_en_map is None:
        _name_map, _abbr_en_map = _build_lookup_tables()
    return _name_map, _abbr_en_map


# -----------------------------------------------------------------------------
# 中文数字（1–200）
# -----------------------------------------------------------------------------

_CN_DIGITS: dict[str, int] = {
    "〇": 0,
    "零": 0,
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


def _parse_under_hundred(s: str) -> int | None:
    """解析 1–99（含）：十、十一、二十三、九十九等。"""
    if not s:
        return None
    s = s.replace("〇", "零")

    if s == "十":
        return 10

    if s.startswith("十"):
        rest = s[1:]
        if not rest:
            return 10
        ones = _CN_DIGITS.get(rest)
        if ones is None or ones > 9:
            return None
        return 10 + ones

    if "十" in s:
        left, _, right = s.partition("十")
        tens_digit = _CN_DIGITS.get(left) if left else 1
        if tens_digit is None or tens_digit > 9:
            return None
        if not right:
            return tens_digit * 10
        ones = _CN_DIGITS.get(right)
        if ones is None:
            return None
        return tens_digit * 10 + ones

    if len(s) == 1 and s in _CN_DIGITS:
        v = _CN_DIGITS[s]
        return v if v > 0 else None

    return None


def chinese_to_int(s: str) -> int | None:
    """
    支持范围到 200，必须正确处理：
    一→1，十→10，十一→11，二十三→23
    一百→100，百→100，百七十六→176
    一百一十九→119，一百七十六→176
    纯阿拉伯数字字符串也接受（「1」→1）
    无法解析返回 None
    """
    s = (s or "").strip().replace("〇", "零")
    if not s:
        return None

    if re.fullmatch(r"\d+", s):
        n = int(s)
        return n if 1 <= n <= 200 else None

    s = s.lstrip("第")

    if s.startswith("二百") and len(s) == 2:
        return 200

    if s.startswith("一百"):
        rest = s[len("一百") :]
        if not rest:
            return 100
        sub = _parse_under_hundred(rest)
        if sub is None:
            return None
        total = 100 + sub
        return total if total <= 200 else None

    if s.startswith("百"):
        rest = s[1:]
        if not rest:
            return 100
        sub = _parse_under_hundred(rest)
        if sub is None:
            return None
        total = 100 + sub
        return total if total <= 200 else None

    v = _parse_under_hundred(s)
    return v if v is not None and 1 <= v <= 200 else None


# -----------------------------------------------------------------------------
# 主解析
# -----------------------------------------------------------------------------

# 英文：单节（须有 :verse）；整段匹配范围时由 _EN_RANGE 优先
_EN_VERSE = re.compile(r"([A-Za-z]+\.?)\s*(\d+)\s*:\s*(\d+)")

# 英文：范围节（优先级高于单节）
_EN_RANGE = re.compile(
    r"([A-Za-z]+\.?)\s*(\d+)\s*:\s*(\d+)\s*[-~～]\s*(\d+)"
)

# 英文：整章（无节号；不能接 :数字）
_EN_CHAPTER = re.compile(r"([A-Za-z]+\.?)\s*(\d+)(?!\s*:\s*\d)")


def _pattern_layer2_verse(book_alt: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?P<book>{book_alt})(?:第)?(?P<ch>[一二三四五六七八九十百千〇零\d]+)(?:章)?"
        rf"(?:第)?(?P<vs>[一二三四五六七八九十百千〇零\d]+)(?:节|篇)?"
    )


def _pattern_layer3_verse(book_alt: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?P<book>{book_alt})(?:第)?(?P<ch>[一二三四五六七八九十百千〇零\d]+)(?:章|篇)"
        rf"(?:第)?(?P<vs>[一二三四五六七八九十百千〇零\d]+)节"
    )


def _pattern_cn_range_l3(book_alt: str) -> re.Pattern[str]:
    """创世记一章一节至十六节、创世记一章1到16节"""
    return re.compile(
        rf"(?P<book>{book_alt})(?:第)?(?P<ch>[一二三四五六七八九十百千〇零\d]+)(?:章|篇)"
        rf"(?:第)?(?P<vs1>[一二三四五六七八九十百千〇零\d]+)(?:节)?"
        rf"\s*(?:到|至|[-~～])\s*"
        rf"(?:第)?(?P<vs2>[一二三四五六七八九十百千〇零\d]+)节"
    )


def _pattern_cn_range_l2(book_alt: str) -> re.Pattern[str]:
    """创一1～16、创一1-16"""
    return re.compile(
        rf"(?P<book>{book_alt})(?:第)?(?P<ch>[一二三四五六七八九十百千〇零]+)(?:章)?"
        rf"(?:第)?(?P<vs1>[一二三四五六七八九十百千〇零\d]+)(?:节)?"
        rf"\s*(?:到|至|[-~～])\s*"
        rf"(?:第)?(?P<vs2>[一二三四五六七八九十百千〇零\d]+)(?:节)?"
    )


def _pattern_cn_chapter_l3(book_alt: str) -> re.Pattern[str]:
    """创世记一章、创世记第一章（后不接 节）"""
    return re.compile(
        rf"(?P<book>{book_alt})(?:第)?(?P<ch>[一二三四五六七八九十百千〇零\d]+)(?:章|篇)"
        rf"(?!(?:第)?[一二三四五六七八九十百千〇零\d]+节)"
    )


def _pattern_cn_chapter_l2(book_alt: str) -> re.Pattern[str]:
    """创一章、创第一章"""
    return re.compile(
        rf"(?P<book>{book_alt})(?:第)?(?P<ch>[一二三四五六七八九十百千〇零]+)章"
        rf"(?!(?:第)?[一二三四五六七八九十百千〇零\d]+节)"
    )


def parse_bible_ref(question: str) -> dict[str, Any] | None:
    """
    从问题中取出书卷、章、节（或范围、整章）。
    优先级：范围节 > 单节 > 整章。

    返回示例：
    - {"book", "chapter", "verse", "type": "verse", "ref_raw"}
    - {"book", "chapter", "verse_start", "verse_end", "type": "range", "ref_raw"}
    - {"book", "chapter", "type": "chapter", "ref_raw"}
    """
    if not (question or "").strip():
        return None

    _ensure_tables()
    assert _name_map is not None and _abbr_en_map is not None
    name_map, abbr_en_map = _name_map, _abbr_en_map

    # --- 英文：范围 > 单节 > 整章 ---
    m_en_r = _EN_RANGE.search(question)
    if m_en_r:
        book_key = _strip_en_abbr(m_en_r.group(1))
        if book_key in abbr_en_map:
            try:
                ch = int(m_en_r.group(2))
                vs1 = int(m_en_r.group(3))
                vs2 = int(m_en_r.group(4))
            except ValueError:
                ch = vs1 = vs2 = -1
            if ch >= 1 and vs1 >= 1 and vs2 >= 1 and vs1 <= vs2:
                return {
                    "book": abbr_en_map[book_key],
                    "chapter": ch,
                    "verse_start": vs1,
                    "verse_end": vs2,
                    "type": "range",
                    "ref_raw": m_en_r.group(0).strip(),
                }

    m_en_v = _EN_VERSE.search(question)
    if m_en_v:
        book_key = _strip_en_abbr(m_en_v.group(1))
        if book_key in abbr_en_map:
            try:
                ch = int(m_en_v.group(2))
                vs = int(m_en_v.group(3))
            except ValueError:
                ch = vs = -1
            if ch >= 1 and vs >= 1:
                return {
                    "book": abbr_en_map[book_key],
                    "chapter": ch,
                    "verse": vs,
                    "type": "verse",
                    "ref_raw": m_en_v.group(0).strip(),
                }

    m_en_c = _EN_CHAPTER.search(question)
    if m_en_c:
        book_key = _strip_en_abbr(m_en_c.group(1))
        if book_key in abbr_en_map:
            try:
                ch = int(m_en_c.group(2))
            except ValueError:
                ch = -1
            if ch >= 1:
                return {
                    "book": abbr_en_map[book_key],
                    "chapter": ch,
                    "type": "chapter",
                    "ref_raw": m_en_c.group(0).strip(),
                }

    sorted_names = sorted(name_map.keys(), key=len, reverse=True)
    book_alt = "(?:" + "|".join(re.escape(k) for k in sorted_names) + ")"

    pat_r3 = _pattern_cn_range_l3(book_alt)
    m_r3 = pat_r3.search(question)
    if m_r3:
        b = name_map.get(m_r3.group("book"))
        if b is not None:
            ch = chinese_to_int(m_r3.group("ch"))
            vs1 = chinese_to_int(m_r3.group("vs1"))
            vs2 = chinese_to_int(m_r3.group("vs2"))
            if ch is not None and vs1 is not None and vs2 is not None and vs1 <= vs2:
                return {
                    "book": b,
                    "chapter": ch,
                    "verse_start": vs1,
                    "verse_end": vs2,
                    "type": "range",
                    "ref_raw": m_r3.group(0).strip(),
                }

    pat_r2 = _pattern_cn_range_l2(book_alt)
    m_r2 = pat_r2.search(question)
    if m_r2:
        b = name_map.get(m_r2.group("book"))
        if b is not None:
            ch = chinese_to_int(m_r2.group("ch"))
            vs1 = chinese_to_int(m_r2.group("vs1"))
            vs2 = chinese_to_int(m_r2.group("vs2"))
            if ch is not None and vs1 is not None and vs2 is not None and vs1 <= vs2:
                return {
                    "book": b,
                    "chapter": ch,
                    "verse_start": vs1,
                    "verse_end": vs2,
                    "type": "range",
                    "ref_raw": m_r2.group(0).strip(),
                }

    # --- 中文单节：第三层先于第二层 ---
    pat3 = _pattern_layer3_verse(book_alt)
    m3 = pat3.search(question)
    if m3:
        book_word = m3.group("book")
        ch_raw = m3.group("ch")
        vs_raw = m3.group("vs")
        b = name_map.get(book_word)
        if b is not None:
            ch = chinese_to_int(ch_raw)
            vs = chinese_to_int(vs_raw)
            if ch is not None and vs is not None:
                return {
                    "book": b,
                    "chapter": ch,
                    "verse": vs,
                    "type": "verse",
                    "ref_raw": m3.group(0).strip(),
                }

    pat2 = _pattern_layer2_verse(book_alt)
    m2 = pat2.search(question)
    if m2:
        book_word = m2.group("book")
        ch_raw = m2.group("ch")
        vs_raw = m2.group("vs")
        b = name_map.get(book_word)
        if b is not None:
            ch = chinese_to_int(ch_raw)
            vs = chinese_to_int(vs_raw)
            if ch is not None and vs is not None:
                return {
                    "book": b,
                    "chapter": ch,
                    "verse": vs,
                    "type": "verse",
                    "ref_raw": m2.group(0).strip(),
                }

    pat_c3 = _pattern_cn_chapter_l3(book_alt)
    m_c3 = pat_c3.search(question)
    if m_c3:
        book_word = m_c3.group("book")
        ch_raw = m_c3.group("ch")
        b = name_map.get(book_word)
        if b is not None:
            ch = chinese_to_int(ch_raw)
            if ch is not None:
                return {
                    "book": b,
                    "chapter": ch,
                    "type": "chapter",
                    "ref_raw": m_c3.group(0).strip(),
                }

    pat_c2 = _pattern_cn_chapter_l2(book_alt)
    m_c2 = pat_c2.search(question)
    if m_c2:
        book_word = m_c2.group("book")
        ch_raw = m_c2.group("ch")
        b = name_map.get(book_word)
        if b is not None:
            ch = chinese_to_int(ch_raw)
            if ch is not None:
                return {
                    "book": b,
                    "chapter": ch,
                    "type": "chapter",
                    "ref_raw": m_c2.group(0).strip(),
                }

    return None


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    _here = Path(__file__).resolve().parent
    _bdir = _here.parent / "bible_data"
    bible_service.load_bible_data(str(_bdir))

    cases = [
        "创一1～16讲了什么",
        "创世记一章讲了什么",
        "创一1说了什么",
        "Gen. 1:1-16",
        "Gen. 1",
        "约翰福音三章十六节",
        "腓立比书一章1到5节",
    ]

    for q in cases:
        r = parse_bible_ref(q)
        print(f"{q}\n  → {json.dumps(r, ensure_ascii=False)}", flush=True)
