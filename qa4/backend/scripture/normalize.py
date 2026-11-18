# -*- coding: utf-8 -*-
"""经节规范化：在 vendor v2.1 外包一层稳定接口。

键的约定【暂定】：
  Ref.key = (卷号, 章, 起节, 止章, 止节)
  - verse_range：止章 = 章；不展开成单节
  - whole_chapter：起节 = 止节 = 0
  - cross_chapter：止章 > 章
  - whole_book：章=起节=止章=止节=0（新增；取篇层暂不支持）
  - chapter_range：起节=止节=0，止章>章（新增；取篇层暂不支持）
  与指令里的 (卷, 章, 起节, 止节) 相同，只多一位「止章」以容纳跨章；同章时止章恒等于章。

诗篇第 0 节【暂定】：config/scripture.json 的 psalm_verse0_as_title 打开时，
「诗篇三0～8」这类写法按第 1 节起算，flags 含「含标题」；关闭时按失败（不出 Ref）。
实现方式：只放宽校验器对 (诗, 章, 0) 的判定，v2.1 规则本身不改。

补强（A–J）见 scripture/ref_enhance.py 与 scripture/data/*.json；不改 vendor。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, Optional

from scripture import vendor_get_vers_v21 as v21
from scripture.ref_enhance import (
    bare_chapter_forms,
    enhance_ref_text,
    match_chapter_range,
    match_whole_book,
    merge_chapter_with_verse,
    traditional_to_simplified,
)
from scripture.vendor_get_vers_v21 import STD2IDX, STD_ORDER

KIND_VERSE = "verse_range"
KIND_CHAPTER = "whole_chapter"
KIND_CROSS = "cross_chapter"
KIND_BOOK = "whole_book"
KIND_CHAPTER_RANGE = "chapter_range"

_OUT_RE = re.compile(r"^(?P<b>\D+?)?(?P<c>\d+)(?::(?P<v1>\d+)(?:-(?P<v2>\d+))?)?$")

# 「十〇二」=102 的误写（应为「一〇二」）。仅改「十〇+个位汉字」；不动「一〇二」「二十三」「一百〇二」。
_SHI_LING_DIGIT = re.compile(r"十〇([一二三四五六七八九])")


def _int_to_cn_chapter(n: int) -> str:
    """阿拉伯章号 → 中文章号（供 vendor 简写 C 型：书+中文章+阿拉伯节）。"""
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
    if n < 200:  # 诗篇至 150
        h, rest = divmod(n, 100)
        body = digits[h] + "百"
        if rest == 0:
            return body
        if rest < 10:
            return body + "零" + digits[rest]
        return body + _int_to_cn_chapter(rest)
    return str(n)


_ARABIC_CH_VERSE = re.compile(
    r"(?<=[\u4e00-\u9fff])[ \u3000]*(\d+)[ \u3000]*:[ \u3000]*(\d+)"
)


def preprocess_ref_text(text: str) -> str:
    """包装层预处理（不改 vendor）。含 A–G/I 补强，再接原有阿拉伯章:节与十〇 规则。

    - 繁→简、廿/卅、别名、英文、章篇节、跨章改写等见 ref_enhance.enhance_ref_text
    - 「十〇二」→「一〇二」
    - 全角冒号「：」→「:」，并把「书+阿拉伯章:节」改成 vendor 可认的「书+中文章+阿拉伯节」
    """
    if not text:
        return text or ""
    s = enhance_ref_text(text)
    s = s.replace("\t", " ").replace("：", ":")
    s = re.sub(r"[ \u3000]+", " ", s).strip()

    def _arab_ch_verse(m: re.Match[str]) -> str:
        return _int_to_cn_chapter(int(m.group(1))) + m.group(2)

    s = _ARABIC_CH_VERSE.sub(_arab_ch_verse, s)
    return _SHI_LING_DIGIT.sub(r"一〇\1", s)


# 照搬 probe6 b_verse.py 的 DIGITISH_RE
DIGITISH_RE = re.compile(
    r"(?:[一二三四五六七八九十百千〇零○]+|\d+)(?:[～~－—\-](?:[一二三四五六七八九十百千〇零○]+|\d+))?"
)


@lru_cache(maxsize=1)
def _cfg() -> dict[str, Any]:
    from config import load_config_json

    return load_config_json("scripture.json")


@dataclass(frozen=True)
class Ref:
    book: str  # 标准简称，如「诗」「林前」
    book_no: int  # 1–66
    chapter: int
    v_start: int  # whole_chapter / whole_book / chapter_range 为 0
    v_end: int  # whole_chapter / whole_book / chapter_range 为 0
    kind: str
    chapter_end: int = 0  # 0 表示与 chapter 相同；chapter_range / cross 用
    flags: tuple[str, ...] = field(default_factory=tuple)
    raw: str = ""

    @property
    def end_chapter(self) -> int:
        return self.chapter_end or self.chapter

    def key(self) -> tuple[int, int, int, int, int]:
        return (self.book_no, self.chapter, self.v_start, self.end_chapter, self.v_end)

    def label(self) -> str:
        if self.kind == KIND_BOOK:
            return f"{self.book}"
        if self.kind == KIND_CHAPTER_RANGE:
            return f"{self.book}{self.chapter}-{self.end_chapter}"
        if self.kind == KIND_CHAPTER:
            return f"{self.book}{self.chapter}"
        if self.kind == KIND_CROSS:
            return f"{self.book}{self.chapter}:{self.v_start}-{self.end_chapter}:{self.v_end}"
        if self.v_start == self.v_end:
            return f"{self.book}{self.chapter}:{self.v_start}"
        return f"{self.book}{self.chapter}:{self.v_start}-{self.v_end}"


Validator = Callable[..., bool]


def build_validator(bible: Any, *, psalm_title: bool) -> Validator:
    """bible：scripture.bible_text.BibleText。psalm_title 打开时放行 (诗, 章, 0)。"""
    psalm_std = _cfg().get("psalm_book_std", "诗")

    def validate(std: str, chap: int, verse: Optional[int] = None) -> bool:
        bno = STD2IDX.get(std)
        if bno is None:
            return False
        try:
            chap = int(chap)
        except (TypeError, ValueError):
            return False
        if not bible.chapter_exists(bno, chap):
            return False
        if verse is None:
            return True
        try:
            verse = int(verse)
        except (TypeError, ValueError):
            return False
        if verse == 0 and psalm_title and std == psalm_std:
            return True
        return bible.verse_exists(bno, chap, verse)

    return validate


def _tok_to_ref(tok: str, raw: str, *, psalm_title: bool) -> Optional[Ref]:
    title_flag = _cfg().get("title_flag", "含标题")
    psalm_std = _cfg().get("psalm_book_std", "诗")
    if "_" in tok:
        head, tail = tok.split("_", 1)
        m1 = _OUT_RE.match(head)
        m2 = _OUT_RE.match(tail)
        if not m1 or not m2 or not m1.group("b"):
            return None
        std = m1.group("b")
        bno = STD2IDX.get(std)
        if bno is None or not m1.group("v1") or not m2.group("v1"):
            return None
        return Ref(
            book=std,
            book_no=bno,
            chapter=int(m1.group("c")),
            v_start=int(m1.group("v1")),
            v_end=int(m2.group("v1")),
            kind=KIND_CROSS,
            chapter_end=int(m2.group("c")),
            raw=raw,
        )
    m = _OUT_RE.match(tok)
    if not m or not m.group("b"):
        return None
    std = m.group("b")
    bno = STD2IDX.get(std)
    if bno is None:
        return None
    chap = int(m.group("c"))
    if m.group("v1") is None:
        return Ref(book=std, book_no=bno, chapter=chap, v_start=0, v_end=0, kind=KIND_CHAPTER, raw=raw)
    vs = int(m.group("v1"))
    ve = int(m.group("v2")) if m.group("v2") else vs
    flags: tuple[str, ...] = ()
    if vs == 0:
        if not (psalm_title and std == psalm_std):
            return None
        vs = 1
        ve = max(ve, 1)
        flags = (title_flag,)
    if vs > ve:
        vs, ve = ve, vs
    return Ref(book=std, book_no=bno, chapter=chap, v_start=vs, v_end=ve, kind=KIND_VERSE, flags=flags, raw=raw)


def _try_scope_refs(text: str, *, bible: Any, validate: bool) -> Optional[list[Ref]]:
    """H：整卷 / 整章范围（整段匹配时优先于 vendor）。"""
    # 整章范围
    cr = match_chapter_range(text)
    if cr is not None:
        std, c1, c2 = cr
        bno = STD2IDX.get(std)
        if bno is None:
            return None
        if validate and bible is not None:
            if not bible.chapter_exists(bno, c1) or not bible.chapter_exists(bno, c2):
                return []
        return [
            Ref(
                book=std,
                book_no=bno,
                chapter=c1,
                v_start=0,
                v_end=0,
                kind=KIND_CHAPTER_RANGE,
                chapter_end=c2,
                raw=text,
            )
        ]
    # 整卷
    std = match_whole_book(text)
    if std is not None:
        bno = STD2IDX.get(std)
        if bno is None:
            return None
        return [
            Ref(
                book=std,
                book_no=bno,
                chapter=0,
                v_start=0,
                v_end=0,
                kind=KIND_BOOK,
                raw=text,
            )
        ]
    return None


def parse_refs(
    text: str,
    *,
    bible: Any = None,
    validate: bool = True,
    psalm_title: Optional[bool] = None,
    volume_book: Optional[str] = None,
) -> list[Ref]:
    """整段（整行）解析，不先按逗号切开；返回出现顺序的 Ref 列表。

    bible：BibleText；validate=True 且未给 bible 时用 settings 下的 bible_data。
    新增 whole_book / chapter_range 仅在整段匹配时返回；现有 verse/chapter/cross 形状不变。
    """
    if not text:
        return []
    # 保留原始供整卷/章范围（enhance 前）；人名单书名判定用原文语义
    raw_in = text
    text = preprocess_ref_text(text)
    if psalm_title is None:
        psalm_title = bool(_cfg().get("psalm_verse0_as_title", True))
    validator = None
    if validate:
        if bible is None:
            from scripture.bible_text import get_bible

            bible = get_bible()
        validator = build_validator(bible, psalm_title=psalm_title)

    scoped = _try_scope_refs(raw_in, bible=bible, validate=validate)
    if scoped is not None:
        return scoped
    # 预处理后的文本也可能整段是章范围（如 创世记1-3章）
    scoped2 = _try_scope_refs(text, bible=bible, validate=validate)
    if scoped2 is not None:
        return scoped2

    def _run_vendor(src: str) -> list[Ref]:
        # 带校验解析（保留 vendor 消歧）；再捞回因跨章一端非法被整段丢掉的 tok
        parser = v21.VerseParser(validate=validator, volume_book=volume_book)
        parser.start_paragraph()
        got: list[Ref] = []
        for g in parser.parse_text(src):
            raw = g.get("text") or ""
            for part in (g.get("verses") or "").split("，"):
                part = part.strip()
                if not part:
                    continue
                ref = _tok_to_ref(part, raw, psalm_title=psalm_title)
                if ref is not None:
                    got.append(ref)
        got = _recover_partial_cross_refs(
            src, got, validator=validator, psalm_title=psalm_title, volume_book=volume_book
        )
        return merge_chapter_with_verse(got)

    out = _run_vendor(text)
    if not out:
        # 回退：整段「创一」「诗23」→ 补章/篇后再解析（不污染 preprocess）
        alt = bare_chapter_forms(text)
        if alt != text:
            out = _run_vendor(alt)
    return out


def _ref_endpoints(ref: Ref) -> tuple[tuple[int, int], tuple[int, int]]:
    if ref.kind == KIND_CHAPTER:
        return (ref.chapter, 1), (ref.chapter, 10_000)
    if ref.kind == KIND_CHAPTER_RANGE:
        return (ref.chapter, 1), (ref.end_chapter, 10_000)
    if ref.kind == KIND_CROSS:
        return (ref.chapter, ref.v_start), (ref.end_chapter, ref.v_end)
    if ref.kind == KIND_BOOK:
        return (0, 0), (10_000, 10_000)
    return (ref.chapter, ref.v_start), (ref.chapter, ref.v_end)


def _ref_covers(outer: Ref, inner: Ref) -> bool:
    if outer.book_no != inner.book_no:
        return False
    os_, oe = _ref_endpoints(outer)
    is_, ie = _ref_endpoints(inner)
    return os_ <= is_ and oe >= ie


def _single_verse_ref(book: str, book_no: int, chapter: int, verse: int, raw: str) -> Ref:
    return Ref(
        book=book,
        book_no=book_no,
        chapter=chapter,
        v_start=verse,
        v_end=verse,
        kind=KIND_VERSE,
        raw=raw,
    )


def _recover_partial_cross_refs(
    src: str,
    existing: list[Ref],
    *,
    validator: Optional[Validator],
    psalm_title: bool,
    volume_book: Optional[str],
) -> list[Ref]:
    """跨章 tok 任一端非法时，vendor 会整段丢弃；此处无校验再解析，合法端点保留为单节。"""
    parser = v21.VerseParser(validate=None, volume_book=volume_book)
    parser.start_paragraph()
    extras: list[tuple[int, Ref]] = []
    for g in parser.parse_text(src):
        raw = g.get("text") or ""
        pos = int(g.get("start") or 0)
        for part in (g.get("verses") or "").split("，"):
            part = part.strip()
            if "_" not in part:
                continue
            cross = _tok_to_ref(part, raw, psalm_title=psalm_title)
            if cross is None or cross.kind != KIND_CROSS:
                continue
            if any(_ref_covers(e, cross) or e.label() == cross.label() for e in existing):
                continue
            start_ok = True
            end_ok = True
            if validator is not None:
                start_ok = bool(validator(cross.book, cross.chapter, cross.v_start))
                end_ok = bool(validator(cross.book, cross.end_chapter, cross.v_end))
            pieces: list[Ref] = []
            if start_ok and end_ok:
                pieces = [cross]
            else:
                if start_ok:
                    pieces.append(
                        _single_verse_ref(
                            cross.book, cross.book_no, cross.chapter, cross.v_start, raw
                        )
                    )
                if end_ok:
                    pieces.append(
                        _single_verse_ref(
                            cross.book, cross.book_no, cross.end_chapter, cross.v_end, raw
                        )
                    )
            for p in pieces:
                if any(e.label() == p.label() for e in existing):
                    continue
                if any(e.label() == p.label() for _, e in extras):
                    continue
                extras.append((pos, p))
    if not extras:
        return existing
    # 按原文出现位置插入：先收集 existing 的大致顺序，再按 pos 归并
    # existing 无偏移，按 raw 在 src 中首次出现近似定位
    timed: list[tuple[int, int, Ref]] = []
    for i, e in enumerate(existing):
        pos = src.find(e.raw) if e.raw else i
        if pos < 0:
            pos = i
        timed.append((pos, i, e))
    for j, (pos, p) in enumerate(extras):
        timed.append((pos, len(existing) + j, p))
    timed.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in timed]


def _span(ref: Ref) -> tuple[tuple[int, int], tuple[int, int]]:
    if ref.kind == KIND_BOOK:
        return (0, 0), (10_000, 10_000)
    if ref.kind == KIND_CHAPTER_RANGE:
        return (ref.chapter, 1), (ref.end_chapter, 10_000)
    if ref.kind == KIND_CHAPTER:
        return (ref.chapter, 1), (ref.chapter, 10_000)
    return (ref.chapter, ref.v_start), (ref.end_chapter, ref.v_end)


def overlaps(a: Ref, b: Ref) -> bool:
    """同卷且章节区间有交集即重叠。"""
    if a.book_no != b.book_no:
        return False
    a0, a1 = _span(a)
    b0, b1 = _span(b)
    return not (a1 < b0 or b1 < a0)


def expand_verses(ref: Ref, max_n: Optional[int] = None, *, bible: Any = None) -> list[tuple[int, int, int]]:
    """需要时才展开成单节 (卷号, 章, 节)；整章/跨章需要 bible 才知道每章节数。"""
    if max_n is None:
        max_n = int(_cfg().get("expand_max_default", 200))
    out: list[tuple[int, int, int]] = []
    if ref.kind == KIND_VERSE:
        for v in range(ref.v_start, ref.v_end + 1):
            out.append((ref.book_no, ref.chapter, v))
            if len(out) >= max_n:
                break
        return out
    if ref.kind in (KIND_BOOK, KIND_CHAPTER_RANGE):
        # 取篇层未接这两类；展开时尽力按 bible 章列表
        if bible is None:
            from scripture.bible_text import get_bible

            bible = get_bible()
        if ref.kind == KIND_BOOK:
            # 无统一 list_chapters API 时保守返回空，避免误展开
            return out
        for ch in range(ref.chapter, ref.end_chapter + 1):
            rows = bible.get_chapter(ref.book_no, ch)
            for r in rows:
                out.append((ref.book_no, int(r["chapter"]), int(r["verse"])))
                if len(out) >= max_n:
                    return out
        return out
    if bible is None:
        from scripture.bible_text import get_bible

        bible = get_bible()
    rows = (
        bible.get_chapter(ref.book_no, ref.chapter)
        if ref.kind == KIND_CHAPTER
        else bible.get_cross(ref.book_no, ref.chapter, ref.v_start, ref.end_chapter, ref.v_end)
    )
    for r in rows:
        out.append((ref.book_no, int(r["chapter"]), int(r["verse"])))
        if len(out) >= max_n:
            break
    return out


def ref_in_bible(ref: Ref, bible: Any) -> bool:
    """出处是否能在 bible_data 里找到（整章看章存在，范围看每节存在）。"""
    if ref.kind == KIND_BOOK:
        return ref.book_no in STD2IDX.values() or ref.book in STD2IDX
    if ref.kind == KIND_CHAPTER_RANGE:
        return bible.chapter_exists(ref.book_no, ref.chapter) and bible.chapter_exists(
            ref.book_no, ref.end_chapter
        )
    if ref.kind == KIND_CHAPTER:
        return bible.chapter_exists(ref.book_no, ref.chapter)
    if ref.kind == KIND_CROSS:
        return bible.verse_exists(ref.book_no, ref.chapter, ref.v_start) and bible.verse_exists(
            ref.book_no, ref.end_chapter, ref.v_end
        )
    return all(bible.verse_exists(ref.book_no, ref.chapter, v) for v in range(ref.v_start, ref.v_end + 1))


# ---------------- 3a 读经行 ----------------
def reading_line_of(content_3a: str) -> Optional[str]:
    """取 3a 正文首行的「读经：」后内容；没有读经行返回 None。"""
    if not content_3a:
        return None
    first = content_3a.splitlines()[0].strip()
    for pre in _cfg().get("reading_line_prefixes", ["读经：", "读经:"]):
        if first.startswith(pre):
            return first[len(pre) :].strip()
    return None


def heuristic_miss(line: str, n_refs: int) -> bool:
    """疑似遗漏（照搬 probe6 heuristic_miss）。"""
    cfg = _cfg().get("miss_heuristic") or {}
    chars = re.escape(cfg.get("split_chars", "，,、；;"))
    segs = [s.strip() for s in re.split(f"[{chars}]", line) if s.strip()]
    seg_n = sum(1 for s in segs if DIGITISH_RE.search(s))
    return seg_n >= int(cfg.get("min_segments", 3)) and seg_n >= n_refs + int(cfg.get("min_gap", 2))


def std_order() -> list[str]:
    return list(STD_ORDER)


def reset_config_cache() -> None:
    _cfg.cache_clear()
    traditional_to_simplified  # noqa: B018 — keep import used
    try:
        from scripture.ref_enhance import _load_aliases, _load_en, _load_t2s, _std_to_full

        _load_t2s.cache_clear()
        _load_aliases.cache_clear()
        _load_en.cache_clear()
        _std_to_full.cache_clear()
    except Exception:
        pass
