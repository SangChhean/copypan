# -*- coding: utf-8 -*-
"""从文本识别诗歌首数（纯程序，不用模型）。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from hymn.catalog import HymnCatalog, get_catalog
from hymn.numbers import parse_hymn_number
from scripture.ref_enhance import traditional_to_simplified

MAX_REFS = 10

SERIES_LABEL = {
    "big": "大本",
    "sup": "补充本",
    "fu": "诗歌附",
    "child": "儿童诗歌",
}

# 长触发词优先。補充/兒童 等字不在 scripture t2s 表内时，保留繁体触发形态（不另造字表）。
_SERIES_TRIGGERS: list[tuple[str, str, bool]] = [
    ("儿童诗歌", "child", True),
    ("兒童诗歌", "child", True),
    ("补充本诗歌", "sup", True),
    ("補充本诗歌", "sup", True),
    ("大本诗歌", "big", True),
    ("诗歌附", "fu", True),
    ("补充本", "sup", True),
    ("補充本", "sup", True),
    ("大本", "big", True),
    ("诗歌", "big", False),
]

_NUM_RE = re.compile(r"[0-9]+|[一二三四五六七八九十百千零〇○两廿卅]+")
_NO_RE = re.compile(r"(?:NO|No|no)\s*\.?", re.I)
_SEP_RE = re.compile(r"[、，,和与及]")
_RANGE_RE = re.compile(r"[到至～~\-－—]")
_TRAIL_RE = re.compile(
    r"第(?P<num>[0-9]+|[一二三四五六七八九十百千零〇○两廿卅]+)[首号]诗歌"
)


@dataclass(frozen=True)
class HymnRef:
    series: str  # big / sup / fu / child
    number: int
    explicit_series: bool
    fallback: bool
    exists: bool

    @property
    def label_zh(self) -> str:
        return SERIES_LABEL.get(self.series, self.series)


class HymnRefList(list):
    """parse_hymn_refs 返回值：list[HymnRef]，带 truncated。"""

    def __init__(self, iterable=(), *, truncated: bool = False):
        super().__init__(iterable)
        self.truncated = bool(truncated)


def normalize_hymn_text(text: str) -> str:
    """繁体→简体、全角数字、去掉各类空白。"""
    if not text:
        return ""
    s = traditional_to_simplified(text)
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    # 去掉所有空白（含全角空格）
    s = "".join(ch for ch in s if not ch.isspace() and unicodedata.category(ch) != "Zs")
    return s


def _looks_like_series(s: str, i: int) -> bool:
    if i >= len(s):
        return False
    # 短「诗」单独不算系列延续（需带首）
    for name, _, _ in _SERIES_TRIGGERS:
        if s.startswith(name, i):
            return True
    return False


def _match_series_at(s: str, i: int) -> Optional[tuple[str, bool, int]]:
    """在位置 i 匹配系列触发词 → (series, explicit, end)。不含短「诗」。"""
    for name, series, explicit in _SERIES_TRIGGERS:
        if s.startswith(name, i):
            return series, explicit, i + len(name)
    return None


def _match_shi_short(s: str, i: int) -> Optional[int]:
    """「诗15首」「诗第15首」；排除诗篇/诗歌。"""
    if not s.startswith("诗", i):
        return None
    if s.startswith("诗歌", i) or s.startswith("诗篇", i):
        return None
    return i + 1


def _take_optional_di_no(s: str, i: int) -> int:
    if s.startswith("第", i):
        i += 1
    m = _NO_RE.match(s, i)
    if m:
        i = m.end()
    if i < len(s) and s[i] == "#":
        i += 1
    return i


def _take_number(s: str, i: int) -> Optional[tuple[int, int]]:
    m = _NUM_RE.match(s, i)
    if not m:
        return None
    n = parse_hymn_number(m.group(0))
    if n is None:
        return None
    return n, m.end()


def _blocked_unit_suffix(s: str, i: int) -> bool:
    """数字后若直接接章/篇（且不是首），不是诗歌首数。"""
    return i < len(s) and s[i] in "章篇"


def _bare_number_boundary_ok(s: str, i: int) -> bool:
    """无「首/号」时：须在句末、标点或并列/范围连接处（避免「大本一共有多少首」）。"""
    if i >= len(s):
        return True
    return s[i] in "。！？；;、，,和与及到至～~-－—）)」》】"


def _parse_one_item(s: str, i: int, *, require_shou: bool = False) -> Optional[tuple[int, int]]:
    """解析一个首数项 → (number, end)。"""
    j = _take_optional_di_no(s, i)
    got = _take_number(s, j)
    if not got:
        return None
    n, k = got
    if _blocked_unit_suffix(s, k):
        return None
    if k < len(s) and s[k] in "首号":
        k += 1
    elif require_shou:
        return None
    elif not _bare_number_boundary_ok(s, k):
        return None
    return n, k


def _parse_number_list(
    s: str, i: int
) -> tuple[list[int], int, bool]:
    """从系列词后解析号码列表/范围。返回 (numbers, end, hit_any)。"""
    first = _parse_one_item(s, i, require_shou=False)
    if not first:
        return [], i, False
    n0, j = first
    nums = [n0]
    while j < len(s):
        # 范围
        if _RANGE_RE.match(s, j):
            j2 = _RANGE_RE.match(s, j).end()  # type: ignore[union-attr]
            nxt = _parse_one_item(s, j2, require_shou=False)
            if not nxt:
                break
            n1, j = nxt
            a, b = (n0, n1) if n0 <= n1 else (n1, n0)
            # 用当前段起点到终点展开：替换最后一项为整段
            nums.pop()
            nums.extend(range(a, b + 1))
            n0 = n1
            continue
        # 并列分隔
        sep = _SEP_RE.match(s, j)
        if not sep:
            break
        j2 = sep.end()
        if _looks_like_series(s, j2):
            break
        nxt = _parse_one_item(s, j2, require_shou=False)
        if not nxt:
            break
        n1, j = nxt
        nums.append(n1)
        n0 = n1
    return nums, j, True


def _resolve(
    series: str,
    number: int,
    explicit: bool,
    catalog: HymnCatalog,
) -> HymnRef:
    if series == "child":
        return HymnRef("child", number, True, False, False)
    if number < 0:
        return HymnRef(series, number, explicit, False, False)
    if catalog.exists(series, number):
        return HymnRef(series, number, explicit, False, True)
    # 无系列限定的「诗歌N」：N>780 且补充本有 → 回退
    if series == "big" and not explicit and number > 780 and catalog.exists("sup", number):
        return HymnRef("sup", number, False, True, True)
    return HymnRef(series, number, explicit, False, False)


def parse_hymn_refs(
    text: str,
    *,
    catalog: Optional[HymnCatalog] = None,
    max_refs: int = MAX_REFS,
) -> HymnRefList:
    """识别文本中的诗歌首数。"""
    cat = catalog or get_catalog()
    cat.ensure_loaded()
    s = normalize_hymn_text(text)
    if not s:
        return HymnRefList()

    refs: list[HymnRef] = []
    truncated = False
    covered = [False] * len(s)

    def add_numbers(series: str, explicit: bool, numbers: list[int]) -> None:
        nonlocal truncated
        for n in numbers:
            if len(refs) >= max_refs:
                truncated = True
                return
            refs.append(_resolve(series, n, explicit, cat))

    def mark(a: int, b: int) -> None:
        for k in range(a, min(b, len(covered))):
            covered[k] = True

    i = 0
    while i < len(s):
        if covered[i]:
            i += 1
            continue

        # 短「诗…首」
        shi = _match_shi_short(s, i)
        if shi is not None:
            item = _parse_one_item(s, shi, require_shou=True)
            if item:
                n, j = item
                # 短诗后也可并列「诗第1首和第2首」？用例无；仅单点。允许列表但每项需首
                nums = [n]
                k = j
                while k < len(s):
                    sep = _SEP_RE.match(s, k)
                    if not sep:
                        break
                    k2 = sep.end()
                    if _looks_like_series(s, k2) or s.startswith("诗", k2):
                        break
                    nxt = _parse_one_item(s, k2, require_shou=True)
                    if not nxt:
                        # 尝试无强制首的并列数字
                        nxt = _parse_one_item(s, k2, require_shou=False)
                        if not nxt:
                            break
                    n2, k = nxt
                    nums.append(n2)
                add_numbers("big", False, nums)
                mark(i, k)
                i = k
                continue

        # 系列触发
        mseries = _match_series_at(s, i)
        if mseries:
            series, explicit, j = mseries
            nums, end, ok = _parse_number_list(s, j)
            if ok and nums:
                add_numbers(series, explicit, nums)
                mark(i, end)
                i = end
                continue

        # 第N首/号诗歌
        tm = _TRAIL_RE.match(s, i)
        if tm:
            n = parse_hymn_number(tm.group("num"))
            if n is not None:
                add_numbers("big", False, [n])
                mark(i, tm.end())
                i = tm.end()
                continue

        i += 1

    return HymnRefList(refs, truncated=truncated)


def format_hymn_refs(refs: HymnRefList) -> str:
    """探针期望语法。"""
    if not refs:
        return "无首数"
    parts: list[str] = []
    for r in refs:
        lab = r.label_zh
        if r.series == "child":
            parts.append(f"{lab} {r.number} 未收录")
        elif not r.exists:
            parts.append(f"无此首 {lab} {r.number}")
        elif r.fallback:
            parts.append(f"{lab} {r.number} *")
        else:
            parts.append(f"{lab} {r.number}")
    out = " ; ".join(parts)
    if refs.truncated:
        out += " +截断"
    return out
