# -*- coding: utf-8 -*-
"""出处格式化（与 ministerialize_router 同源逻辑）。"""
import re

_MSG_LABEL_RE = re.compile(
    r"^\s*第[零一二三四五六七八九十百千\d]+[篇章课节题期]"
)


def _int_to_chinese(n: int) -> str:
    if n <= 0:
        return str(n)
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n - 10] if n > 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        result = digits[tens] + "十"
        if ones:
            result += digits[ones]
        return result
    if n < 1000:
        hundreds, rem = divmod(n, 100)
        result = digits[hundreds] + "百"
        if rem == 0:
            return result
        if rem < 10:
            result += "零" + digits[rem]
        else:
            result += _int_to_chinese(rem)
        return result
    if n < 10000:
        thousands, rem = divmod(n, 1000)
        result = digits[thousands] + "千"
        if rem == 0:
            return result
        if rem < 100:
            result += "零" + _int_to_chinese(rem)
        else:
            result += _int_to_chinese(rem)
        return result
    return str(n)


def _format_msg_num(num) -> str:
    try:
        return f"第{_int_to_chinese(int(num))}篇"
    except (ValueError, TypeError):
        return f"第{num}篇"


def _strip_one_outer_bracket_pair(s: str) -> str:
    """仅当首尾括号为最外层配对时剥一层，嵌套内层括号不误剥。"""
    s = s.strip()
    if len(s) < 2:
        return s
    for open_ch, close_ch in (("（", "）"), ("(", ")")):
        if s[0] != open_ch or s[-1] != close_ch:
            continue
        depth = 0
        for i, ch in enumerate(s):
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0 and i == len(s) - 1:
                    return s[1:-1].strip()
                if depth == 0:
                    break
        break
    return s


def _clean_source_zh(source_zh: str) -> str:
    s = source_zh.strip()
    if not s:
        return ""
    s = re.sub(
        r"，第[零一二三四五六七八九十百千\d]+[段节](?=[）)]*$)",
        "",
        s,
    ).strip()
    return _strip_one_outer_bracket_pair(s)


def _format_source_from_metadata(hit: dict) -> str:
    book = (hit.get("book_title") or "").strip()
    msg_title = (hit.get("message_title") or "").strip()
    msg_num = hit.get("message_number")

    if book and msg_title:
        m = _MSG_LABEL_RE.match(msg_title)
        if m:
            return f"{book}，{m.group(0).strip()}"
        if msg_num is not None and str(msg_num).strip() != "":
            return f"{book}，{_format_msg_num(msg_num)}"
        return book
    if book and msg_num is not None and str(msg_num).strip() != "":
        return f"{book}，{_format_msg_num(msg_num)}"
    if book:
        return book
    return ""


def format_source(hit: dict | None) -> str:
    """Build readable citation from reranked hit metadata."""
    if not hit:
        return ""
    source_zh = (hit.get("source_zh") or "").strip()
    if source_zh:
        return _clean_source_zh(source_zh)
    result = _format_source_from_metadata(hit)
    if result:
        return result
    return (hit.get("source_en") or "").strip()
