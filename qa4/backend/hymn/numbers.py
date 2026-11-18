# -*- coding: utf-8 -*-
"""诗歌首数数字解析（阿拉伯/全角/中文千百十/廿/口语/数位直读）。

不依赖 vendor.cn2num（其对「千」会静默算错）。
"""

from __future__ import annotations

import re
from typing import Optional

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_TO_FULLWIDTH = str.maketrans("0123456789", "０１２３４５６７８９")

_DIGITS = {
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
_UNITS = {"十": 10, "百": 100, "千": 1000}
_CN_DIGIT_CHARS = "".join(_DIGITS.keys())
# 口语：…百+个位→…十（一百五=150）；…千+个位→…百（一千五=1500）
_COLLOQUIAL_TAIL = re.compile(r"^([一二三四五六七八九零〇○]*[百千])([一二三四五六七八九])$")
_D = "零一二三四五六七八九"
_COLLOQUIAL_FILL = {"百": "十", "千": "百"}


def fullwidth_digits(s: str) -> str:
    return (s or "").translate(_FULLWIDTH_DIGITS)


def to_fullwidth_digits(s: str) -> str:
    return (s or "").translate(_TO_FULLWIDTH)


def _cn_units_to_int(s: str) -> Optional[int]:
    """带十/百/千的中文数字；必须吃完整串，否则 None（避免静默截断）。"""
    if not s:
        return None
    total = 0
    cur = 0
    seen = False
    for ch in s:
        if ch in _DIGITS:
            cur = _DIGITS[ch]
            seen = True
        elif ch in _UNITS:
            u = _UNITS[ch]
            if cur == 0:
                cur = 1
            total += cur * u
            cur = 0
            seen = True
        else:
            return None
    if not seen:
        return None
    return total + cur


def _cn_digits_to_int(s: str) -> Optional[int]:
    """逐位直读：一一五→115，一〇〇五→1005。"""
    if not s or any(ch not in _DIGITS for ch in s):
        return None
    return int("".join(str(_DIGITS[ch]) for ch in s))


def cn_to_int(s: str) -> Optional[int]:
    """中文数字 → int（含千）。空串/非法 → None。"""
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace("廿", "二十").replace("卅", "三十").replace("两", "二")
    m = _COLLOQUIAL_TAIL.match(s)
    if m:
        head, dig = m.group(1), m.group(2)
        unit = head[-1]
        fill = _COLLOQUIAL_FILL.get(unit)
        if fill:
            s = head + dig + fill
    if any(ch in _UNITS for ch in s):
        return _cn_units_to_int(s)
    return _cn_digits_to_int(s)


def parse_hymn_number(raw: str) -> Optional[int]:
    """解析首数；允许 0（调用方标无此首）。失败返回 None。"""
    s = fullwidth_digits((raw or "").strip())
    if not s:
        return None
    if s.isdigit():
        return int(s)
    return cn_to_int(s)


def is_cn_or_arabic_number_token(s: str) -> bool:
    s = fullwidth_digits((s or "").strip())
    if not s:
        return False
    if s.isdigit():
        return True
    return all(ch in _CN_DIGIT_CHARS + "十百千廿卅两" for ch in s)


def int_to_cn_standard(n: int) -> str:
    """标准中文：105→一百零五，115→一百一十五，1000→一千，1005→一千零五，1015→一千零一十五。"""
    if n < 0:
        raise ValueError(n)
    if n == 0:
        return "零"
    if n < 10:
        return _D[n]
    if n < 20:
        return "十" + (_D[n % 10] if n % 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        return _D[tens] + "十" + (_D[ones] if ones else "")
    if n < 1000:
        h, rest = divmod(n, 100)
        body = _D[h] + "百"
        if rest == 0:
            return body
        if rest < 10:
            return body + "零" + _D[rest]
        if rest < 20:
            return body + "一十" + (_D[rest % 10] if rest % 10 else "")
        return body + int_to_cn_standard(rest)
    # n >= 1000
    q, r = divmod(n, 1000)
    head = ("一" if q == 1 else int_to_cn_standard(q)) + "千"
    if r == 0:
        return head
    if r < 10:
        return head + "零" + _D[r]
    if r < 20:
        return head + "零一十" + (_D[r % 10] if r % 10 else "")
    if r < 100:
        return head + "零" + int_to_cn_standard(r)
    return head + int_to_cn_standard(r)


def int_to_cn_omit_yi_shi(n: int) -> Optional[str]:
    """省略「一十」：115→一百十五；标准式不含「一十」则 None。"""
    std = int_to_cn_standard(n)
    if "一十" not in std:
        return None
    return std.replace("一十", "十")


def int_to_cn_digit_reading(n: int, *, zero_char: str = "〇") -> str:
    """逐位直读：115→一一五，1005→一〇〇五。"""
    out = []
    for ch in str(n):
        if ch == "0":
            out.append(zero_char)
        else:
            out.append(_D[int(ch)])
    return "".join(out)


def int_to_cn_nian(n: int) -> Optional[str]:
    """20–29 的「廿」写法。"""
    if 20 <= n <= 29:
        ones = n - 20
        return "廿" + (_D[ones] if ones else "")
    return None
