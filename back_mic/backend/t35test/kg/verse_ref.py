# -*- coding: utf-8 -*-
"""【新测试台】人工关键圣经节：把各种写法统一成资料（纲目、注解、文集）里的经节简写，例如“弗四16”。

为什么要统一：每个人输入经节的写法不同（弗4:16、以弗所书4章16节、以弗所四章十六节……），
而资料里的出处一律写成“弗四16”这种简写；统一以后才能按经节检索到引用这节的原文，生成纲目的指示也一致。

资料里章数的写法（2026-11-12 查 ES 确认）：
  1～10：一……十；11～19：十一……十九；整十：二十、三十……九十；
  21～99（非整十）：一位一位写，如 二三、五三、八九；100 以上：一位一位写，0 写成〇，如 一〇〇、一一〇、一一九。
节数用阿拉伯数字；范围用“～”；节后可带“上/下”。
"""
from __future__ import annotations

import re
import unicodedata

# (简写, 其他写法...)；其他写法按“越长越先比”配对
_BOOKS: list[tuple[str, ...]] = [
    ("创", "创世记", "创世纪", "创世"),
    ("出", "出埃及记", "出埃及"),
    ("利", "利未记", "利未"),
    ("民", "民数记", "民数"),
    ("申", "申命记", "申命"),
    ("书", "约书亚记", "约书亚"),
    ("士", "士师记", "士师"),
    ("得", "路得记", "路得"),
    ("撒上", "撒母耳记上", "撒母耳上"),
    ("撒下", "撒母耳记下", "撒母耳下"),
    ("王上", "列王纪上", "列王记上", "列王上"),
    ("王下", "列王纪下", "列王记下", "列王下"),
    ("代上", "历代志上", "历代上"),
    ("代下", "历代志下", "历代下"),
    ("拉", "以斯拉记", "以斯拉"),
    ("尼", "尼希米记", "尼希米"),
    ("斯", "以斯帖记", "以斯帖"),
    ("伯", "约伯记", "约伯"),
    ("诗", "诗篇"),
    ("箴", "箴言"),
    ("传", "传道书", "传道"),
    ("歌", "雅歌"),
    ("赛", "以赛亚书", "以赛亚"),
    ("耶", "耶利米书", "耶利米"),
    ("哀", "耶利米哀歌", "哀歌"),
    ("结", "以西结书", "以西结"),
    ("但", "但以理书", "但以理"),
    ("何", "何西阿书", "何西阿"),
    ("珥", "约珥书", "约珥"),
    ("摩", "阿摩司书", "阿摩司"),
    ("俄", "俄巴底亚书", "俄巴底亚"),
    ("拿", "约拿书", "约拿"),
    ("弥", "弥迦书", "弥迦"),
    ("鸿", "那鸿书", "那鸿"),
    ("哈", "哈巴谷书", "哈巴谷"),
    ("番", "西番雅书", "西番雅"),
    ("该", "哈该书", "哈该"),
    ("亚", "撒迦利亚书", "撒迦利亚"),
    ("玛", "玛拉基书", "玛拉基"),
    ("太", "马太福音", "马太"),
    ("可", "马可福音", "马可"),
    ("路", "路加福音", "路加"),
    ("约", "约翰福音", "约翰"),
    ("徒", "使徒行传", "行传"),
    ("罗", "罗马书", "罗马"),
    ("林前", "哥林多前书", "哥林多前", "林前书"),
    ("林后", "哥林多后书", "哥林多后", "林后书"),
    ("加", "加拉太书", "加拉太"),
    ("弗", "以弗所书", "以弗所"),
    ("腓", "腓立比书", "腓立比"),
    ("西", "歌罗西书", "歌罗西"),
    ("帖前", "帖撒罗尼迦前书", "帖撒罗尼迦前"),
    ("帖后", "帖撒罗尼迦后书", "帖撒罗尼迦后"),
    ("提前", "提摩太前书", "提摩太前"),
    ("提后", "提摩太后书", "提摩太后"),
    ("多", "提多书", "提多"),
    ("门", "腓利门书", "腓利门"),
    ("来", "希伯来书", "希伯来"),
    ("雅", "雅各书", "雅各"),
    ("彼前", "彼得前书", "彼得前"),
    ("彼后", "彼得后书", "彼得后"),
    ("约壹", "约翰一书", "约翰壹书", "约壹书", "约一书"),
    ("约贰", "约翰二书", "约翰贰书", "约贰书", "约二书"),
    ("约叁", "约翰三书", "约翰叁书", "约叁书", "约三书"),
    ("犹", "犹大书", "犹大"),
    ("启", "启示录", "启示"),
]
_SINGLE_CHAPTER = {"俄", "门", "约贰", "约叁", "犹"}

# 所有写法 → 简写，按长度由长到短（先配“约翰一书”，再配“约翰”，最后配“约”）
_ALIASES: list[tuple[str, str]] = sorted(
    ((alias, b[0]) for b in _BOOKS for alias in b),
    key=lambda x: -len(x[0]),
)

_CN_DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_CHARS = "〇零一二三四五六七八九十百两"
_DIGIT_CN = "〇一二三四五六七八九"


def _cn_to_int(s: str) -> int | None:
    """中文数字转整数：标准写法（五十三、一百一十九）和资料简写（五三、一一九、一〇〇）都认得。"""
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if "十" in s or "百" in s:
        total, num = 0, 0
        for ch in s:
            if ch in _CN_DIGIT:
                num = _CN_DIGIT[ch]
            elif ch == "百":
                total += (num or 1) * 100
                num = 0
            elif ch == "十":
                total += (num or 1) * 10
                num = 0
            else:
                return None
        return total + num
    if all(ch in _CN_DIGIT for ch in s):  # 一位一位写的：五三 → 53
        return int("".join(str(_CN_DIGIT[ch]) for ch in s))
    return None


def chapter_abbr(n: int) -> str:
    """整数章数 → 资料里的写法。"""
    if n <= 0:
        return str(n)
    if n <= 10:
        return "十" if n == 10 else _DIGIT_CN[n]
    if n < 20:
        return "十" + _DIGIT_CN[n - 10]
    if n < 100:
        return _DIGIT_CN[n // 10] + ("十" if n % 10 == 0 else _DIGIT_CN[n % 10])
    return "".join(_DIGIT_CN[int(d)] for d in str(n))


_NUM = rf"(?:\d+|[{_CN_CHARS}]+)"
_SUFFIX = r"(?:上|下|上半|下半|a|b)?"
_RANGE = rf"(?:\s*(?:-|~|～|—|–|至|到)\s*({_NUM})\s*节?\s*({_SUFFIX}))?"
# 章与节之间的写法：4:16、4：16、4.16、4章16节、四章十六节、四16（资料简写）、4 16
_CH_VS = re.compile(
    rf"^\s*({_NUM})\s*(章|篇|[:：.．,，]|\s)?\s*({_NUM}|\d+)\s*节?\s*({_SUFFIX}){_RANGE}\s*$"
)
_VS_ONLY = re.compile(rf"^\s*({_NUM})\s*节?\s*({_SUFFIX}){_RANGE}\s*$")


def _split_chapter_verse(rest: str) -> tuple[int, int, str, int | None, str] | None:
    """“四16”这种没有分隔的资料简写：中文章数后面直接接阿拉伯节数。"""
    m = re.match(rf"^\s*([{_CN_CHARS}]+)\s*(\d+)\s*({_SUFFIX}){_RANGE}\s*$", rest)
    if m:
        ch = _cn_to_int(m.group(1))
        v1 = int(m.group(2))
        v2 = _cn_to_int(m.group(4)) if m.group(4) else None
        if ch:
            return ch, v1, m.group(3) or "", v2, m.group(5) or ""
    m = _CH_VS.match(rest)
    if m:
        if not m.group(2) and m.group(1).isdigit() and m.group(3).isdigit():
            return None  # “416”分不出章节，不猜
        ch, v1 = _cn_to_int(m.group(1)), _cn_to_int(m.group(3))
        v2 = _cn_to_int(m.group(5)) if m.group(5) else None
        if ch and v1:
            return ch, v1, m.group(4) or "", v2, m.group(6) or ""
    return None


def _clean_suffix(s: str) -> str:
    return {"上半": "上", "下半": "下", "a": "上", "b": "下"}.get(s, s)


def normalize_verse(raw: str) -> str | None:
    """把一处经节换成资料里的简写；认不出就回传 None。例：弗4:16 / 以弗所书四章十六节 → 弗四16。"""
    s = unicodedata.normalize("NFKC", str(raw or "")).strip()
    s = re.sub(r"\s+", " ", s).strip("，,。.;；")
    s = s.replace("〜", "～")
    if not s:
        return None
    book = None
    for alias, abbr in _ALIASES:
        if s.startswith(alias):
            book, rest = abbr, s[len(alias):]
            break
    if not book:
        return None
    rest = rest.replace("第", "").strip()  # 以弗所书第四章第十六节
    if book in _SINGLE_CHAPTER:  # 只有一章的书：犹20、门1
        m = _VS_ONLY.match(rest)
        if m:
            v1 = _cn_to_int(m.group(1))
            v2 = _cn_to_int(m.group(3)) if m.group(3) else None
            if v1:
                out = f"{book}{v1}{_clean_suffix(m.group(2) or '')}"
                if v2 and v2 != v1:
                    out += f"～{v2}{_clean_suffix(m.group(4) or '')}"
                return out
    parsed = _split_chapter_verse(rest)
    if not parsed:
        return None
    ch, v1, suf1, v2, suf2 = parsed
    out = f"{book}{chapter_abbr(ch)}{v1}{_clean_suffix(suf1)}"
    if v2 and v2 != v1:
        out += f"～{v2}{_clean_suffix(suf2)}"
    return out


def normalize_verses(items: list[str]) -> tuple[list[str], list[str]]:
    """一组经节统一写法。回传 (统一后的经节, 认不出的原文)；一格里写了几处（用逗号、顿号、分号隔开）也会拆开。"""
    out: list[str] = []
    bad: list[str] = []
    for raw in items:
        parts = [p for p in re.split(r"[，,；;、/\n]+", str(raw or "")) if p.strip()]
        last_book = last_chapter = None
        for p in parts:
            p = p.strip()
            v = normalize_verse(p)
            if v is None and last_book and last_chapter and re.fullmatch(
                rf"\d+\s*节?\s*{_SUFFIX}(?:\s*(?:-|~|～|至|到)\s*\d+\s*节?\s*{_SUFFIX})?", p
            ):  # “林前十二13、27”：后一处只写节数，接上前一处的书名和章数
                v = normalize_verse(f"{last_book}{last_chapter}{p}")
            if v is None and last_book:  # “弗四16，五25”：后一处省略书名，接上前一处的书名
                v = normalize_verse(last_book + p)
            if v is None:
                bad.append(p)
                continue
            last_book = next(abbr for b in _BOOKS for abbr in [b[0]] if v.startswith(abbr) and
                             not any(v.startswith(o[0]) and len(o[0]) > len(abbr) for o in _BOOKS))
            m = re.match(rf"^{re.escape(last_book)}([{_CN_CHARS}]*)", v)
            last_chapter = m.group(1) if m else None
            if v not in out:
                out.append(v)
    return out, bad


def verse_start(verse: str) -> str:
    """范围经节的起头一节（检索用）：约十四9～10 → 约十四9。"""
    return re.split(r"[～~]", verse, maxsplit=1)[0].rstrip("上下")
