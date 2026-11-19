# -*- coding: utf-8 -*-
"""答案三语：简→繁（OpenCC + 术语表）；简→英（Gemini REST，需 GEMINI_API_KEY）。

改写自 3.0 back_qa/qa/translation_service.py；不 import back_qa。
书目英译：前端带来的 source_en → 规则函数 → 保留中文；不写新词典、不交给 Gemini。
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger("qa4.translate")

_QA4_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _QA4_ROOT.parent
_TERMS_PATH = _REPO_ROOT / "shared" / "zh_tw_terms.json"
# 只读模型名环境变量，不读/不打印 API key
_GEMINI_MODEL = (os.environ.get("QA4_GEMINI_MODEL") or "gemini-3.8-flash").strip()

_GEMINI_SYSTEM = (
    "你是专业的职事信息中翻英助手。请将用户给出的中文准确翻译为英文。\n"
    "要求：直接输出译文，不加任何前缀或解释；保留原文语气和神学术语；\n"
    "专有词参考：召会=church, 那灵=the Spirit, 职事=ministry, 三一神=the Triune God 等\n"
    "- 文中形如 [REF:0]、[REF:1] 等标记是引用编号占位符，必须原样保留在对应位置，不得删除、移动或翻译"
)

# 3.0：右引号后的 1～2 位编号；qa4：正文 [n]
_citation_quote_re = re.compile(
    r'([」"\u201d\u2019\u0022\u0027])\s*(\d{1,2})(?=\s|<|$|\n|—|-)',
    re.MULTILINE,
)
_citation_bracket_re = re.compile(r"\[(\d{1,3})\]")

# ---- 书目规则（自 3.0 translation_service.translate_source_zh_to_en 原样搬入）----
_BIBLE_BOOK_MAP: dict[str, str] = {
    "创": "Gen.", "出": "Exo.", "利": "Lev.", "民": "Num.", "申": "Deut.",
    "书": "Josh.", "士": "Judg.", "得": "Ruth",
    "撒上": "1 Sam.", "撒下": "2 Sam.",
    "王上": "1 Kings", "王下": "2 Kings",
    "代上": "1 Chron.", "代下": "2 Chron.",
    "拉": "Ezra", "尼": "Neh.", "斯": "Esth.",
    "伯": "Job", "诗": "Psa.", "箴": "Prov.", "传": "Eccl.", "歌": "S.S.",
    "赛": "Isa.", "耶": "Jer.", "哀": "Lam.", "结": "Ezek.", "但": "Dan.",
    "何": "Hos.", "珥": "Joel", "摩": "Amos", "俄": "Obad.", "拿": "Jonah",
    "弥": "Mic.", "鸿": "Nah.", "哈": "Hab.", "番": "Zeph.", "该": "Hag.",
    "亚": "Zech.", "玛": "Mal.",
    "太": "Matt.", "可": "Mark", "路": "Luke", "约": "John",
    "徒": "Acts",
    "罗": "Rom.", "林前": "1 Cor.", "林后": "2 Cor.", "加": "Gal.",
    "弗": "Eph.", "腓": "Phil.", "西": "Col.",
    "帖前": "1 Thes.", "帖后": "2 Thes.",
    "提前": "1 Tim.", "提后": "2 Tim.", "多": "Titus", "门": "Philem.",
    "来": "Heb.", "雅": "James",
    "彼前": "1 Pet.", "彼后": "2 Pet.",
    "约壹": "1 John", "约贰": "2 John", "约叁": "3 John",
    "犹": "Jude", "启": "Rev.",
}

_ZH_NUM_MAP: dict[str, int] = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
    "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29, "三十": 30,
    "三十一": 31, "三十二": 32, "三十三": 33, "三十四": 34, "三十五": 35,
    "三十六": 36, "三十七": 37, "三十八": 38, "三十九": 39, "四十": 40,
    "四十一": 41, "四十二": 42, "四十三": 43, "四十四": 44, "四十五": 45,
    "四十六": 46, "四十七": 47, "四十八": 48, "四十九": 49, "五十": 50,
}

_FEAST_TYPE_MAP: dict[str, str] = {
    "国际华语特会": "ICSC",
    "春季长老训练": "ITERO-Spring",
    "秋季长老训练": "ITERO-Fall",
    "安那翰春季全时间训练": "FTTA-Spring",
    "安那翰秋季全时间训练": "FTTA-Fall",
    "安那翰全时间训练": "FTTA",
    "夏季训练": "ST", "夏训": "ST",
    "冬季训练": "WT", "冬训": "WT",
    "国殇节特会": "MDC", "国殇节": "MDC",
    "感恩节特会": "TGC", "感恩节": "TGC",
    "感恩节相调特会": "TGC",
}

SourceItem = Union[str, dict[str, Any]]


def to_traditional(text: str) -> str:
    src = text or ""
    if not src.strip():
        return src
    out = src
    placeholders: list[tuple[str, str]] = []
    try:
        if _TERMS_PATH.is_file():
            terms = json.loads(_TERMS_PATH.read_text(encoding="utf-8"))
            if isinstance(terms, dict):
                for idx, simp in enumerate(sorted(terms.keys(), key=len, reverse=True)):
                    trad = terms.get(simp)
                    if simp and trad is not None:
                        ph = f"__TW_{idx}__"
                        placeholders.append((ph, str(trad)))
                        out = out.replace(simp, ph)
        try:
            from opencc import OpenCC

            out = OpenCC("s2t").convert(out)
        except ImportError:
            try:
                import zhconv

                out = zhconv.convert(out, "zh-hant")
            except ImportError as e:
                logger.warning("OpenCC/zhconv 未安装，无法简繁转换")
                raise RuntimeError("OpenCC/zhconv 未安装，无法简繁转换") from e
        except Exception:
            try:
                import zhconv

                out = zhconv.convert(out, "zh-hant")
            except Exception as e:
                logger.error("简转繁失败: %s", e)
                raise RuntimeError(f"简繁转换失败：{type(e).__name__}") from e
        for ph, trad in placeholders:
            out = out.replace(ph, trad)
        return out
    except RuntimeError:
        raise
    except Exception as e:
        logger.error("简转繁失败: %s", e)
        raise RuntimeError(f"简繁转换失败：{type(e).__name__}") from e


def mask_en_citations(text: str) -> tuple[str, dict[str, str]]:
    """送 Gemini 前保护引用编号：先「引号+数字」，再「[n]」→ [REF:i]。"""
    src = text or ""
    placeholders: dict[str, str] = {}
    counter = [0]

    def repl(m: re.Match) -> str:
        ph = f"[REF:{counter[0]}]"
        placeholders[ph] = m.group(0)
        counter[0] += 1
        return ph

    out = _citation_quote_re.sub(repl, src)
    out = _citation_bracket_re.sub(repl, out)
    return out, placeholders


def unmask_en_citations(text: str, placeholders: dict[str, str]) -> str:
    """还原 [REF:i]；若还原后遗漏占位符或编号个数对不上，打一行 warning。"""
    out = text or ""
    for ph, raw in placeholders.items():
        out = out.replace(ph, raw)
    left = [ph for ph in placeholders if ph in out]
    expected_n = len(placeholders)
    restored_quote = len(_citation_quote_re.findall(out))
    restored_bracket = len(_citation_bracket_re.findall(out))
    restored_n = restored_quote + restored_bracket
    if left or restored_n != expected_n:
        logger.warning(
            "en citation unmask mismatch: expected=%d restored=%d leftover_placeholders=%d",
            expected_n,
            restored_n,
            len(left),
        )
    return out


def translate_source_zh_to_en(source_zh: str) -> str:
    """规则翻译书目（恢复本注释 / 7feasts 特会）。无法识别返回空串。"""
    s = (source_zh or "").strip()
    s = s.strip("（）()").strip()
    s = s.strip("， ").strip()

    m = re.match(r"恢复本圣经，(.+?)(\d+)，注(\d+)\s*$", s)
    if m:
        book_chapter_raw = m.group(1)
        verse = m.group(2)
        footnote = m.group(3)
        book_en = None
        chapter_zh = None
        for abbr in sorted(_BIBLE_BOOK_MAP.keys(), key=len, reverse=True):
            if book_chapter_raw.startswith(abbr):
                book_en = _BIBLE_BOOK_MAP[abbr]
                chapter_zh = book_chapter_raw[len(abbr) :]
                break
        if book_en and chapter_zh:
            chapter = _ZH_NUM_MAP.get(chapter_zh)
            if chapter:
                return (
                    f"Holy Bible Recovery Version, {book_en} {chapter}:{verse}, "
                    f"footnote {footnote}"
                )

    m = re.match(r"(\d{4})年(.+?)，第(.+?)篇", s)
    if m:
        year = m.group(1)
        feast_type = m.group(2).strip()
        msg_zh = m.group(3).strip()
        feast_en = None
        for key in sorted(_FEAST_TYPE_MAP.keys(), key=len, reverse=True):
            if feast_type == key or feast_type.startswith(key):
                feast_en = _FEAST_TYPE_MAP[key]
                break
        msg_num = _ZH_NUM_MAP.get(msg_zh) or _ZH_NUM_MAP.get(msg_zh.lstrip("第"))
        if msg_num is None and msg_zh.isdigit():
            msg_num = int(msg_zh)
        if feast_en and msg_num:
            return f"{year} {feast_en}, msg. {msg_num}"

    return ""


def strip_source_en_trailing_segments(source_en: str) -> str:
    """与 3.0 _strip_source_en_trailing_segments 一致：去外层括号后再剥段号后缀。"""
    t = (source_en or "").strip()
    t = t.strip("（）()").strip()
    patterns = (
        r",?\s*paragraph\s+\d+\s*$",
        r",?\s*par(a|agraph)?\.?\s*\d+\s*$",
        r",?\s*section\s+\d+\s*$",
        r",?\s*sect\.?\s*\d+\s*$",
        r",?\s*sec\.?\s*\d+\s*$",
        r",?\s*§\s*\d+\s*$",
        r",?\s*no\.?\s*\d+\s*$",
    )
    for _ in range(8):
        prev = t
        for pat in patterns:
            t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()
        if t == prev:
            break
    return t


def _normalize_source_item(item: SourceItem, index: int) -> dict[str, Any]:
    """统一为 {n, zh, en, source_zh, book_title, message_number}。缺字段不报错。"""
    if isinstance(item, str):
        s = item.strip()
        m = re.match(r"^\[(\d+)\]\s*(.*)$", s)
        if m:
            return {
                "n": int(m.group(1)),
                "zh": s,
                "en": "",
                "source_zh": m.group(2).strip(),
                "book_title": "",
                "message_number": None,
            }
        m2 = re.match(r"^(\d+)\s+(.*)$", s)
        if m2:
            return {
                "n": int(m2.group(1)),
                "zh": f"[{m2.group(1)}] {m2.group(2).strip()}".strip(),
                "en": "",
                "source_zh": m2.group(2).strip(),
                "book_title": "",
                "message_number": None,
            }
        return {
            "n": index + 1,
            "zh": s,
            "en": "",
            "source_zh": s,
            "book_title": "",
            "message_number": None,
        }
    if not isinstance(item, dict):
        return {
            "n": index + 1,
            "zh": str(item),
            "en": "",
            "source_zh": "",
            "book_title": "",
            "message_number": None,
        }
    n = item.get("n")
    try:
        n_int = int(n) if n is not None and str(n).strip() != "" else index + 1
    except (TypeError, ValueError):
        n_int = index + 1
    zh = str(item.get("zh") or "").strip()
    if not zh:
        bt = str(item.get("book_title") or "").strip()
        mt = str(item.get("message_title") or "").strip()
        zh = f"[{n_int}] {bt} {mt}".strip()
    en = str(item.get("en") or item.get("source_en") or "").strip()
    source_zh = str(item.get("source_zh") or "").strip()
    book_title = str(item.get("book_title") or "").strip()
    msg_no = item.get("message_number")
    try:
        msg_no_i = int(msg_no) if msg_no is not None and str(msg_no).strip() != "" else None
    except (TypeError, ValueError):
        msg_no_i = None
    return {
        "n": n_int,
        "zh": zh,
        "en": en,
        "source_zh": source_zh,
        "book_title": book_title,
        "message_number": msg_no_i,
    }


def _rule_input_for(item: dict[str, Any]) -> str:
    """规则函数输入：优先 source_zh；节期可拼「{book_title}，第{N}篇」。"""
    if item.get("source_zh"):
        return str(item["source_zh"])
    bt = str(item.get("book_title") or "").strip()
    mn = item.get("message_number")
    if bt and re.match(r"^\d{4}年", bt) and mn is not None:
        return f"{bt}，第{int(mn)}篇"
    # 从展示中文剥掉 [n] 前缀再试
    zh = str(item.get("zh") or "")
    m = re.match(r"^\[\d+\]\s*(.*)$", zh)
    body = (m.group(1) if m else zh).strip()
    # 若是「2015年冬季训练 …」且带 message_number，仍可拼
    if mn is not None and re.match(r"^\d{4}年", body):
        head = body.split("，", 1)[0].split(None, 1)[0] if body else bt
        # book_title 更干净
        if bt and re.match(r"^\d{4}年", bt):
            return f"{bt}，第{int(mn)}篇"
        feast_head = re.match(r"^(\d{4}年\S+)", body)
        if feast_head:
            return f"{feast_head.group(1)}，第{int(mn)}篇"
    return body or bt


def resolve_source_en_line(item: SourceItem, index: int = 0) -> tuple[str, str]:
    """返回 (展示行, 路径：source_en|rule|zh)。编号与正文一致。"""
    norm = _normalize_source_item(item, index)
    n = norm["n"]
    prefix = f"[{n}]"
    zh_line = norm["zh"] if norm["zh"].startswith("[") else f"{prefix} {norm['zh']}".strip()

    raw_en = norm.get("en") or ""
    if raw_en:
        cleaned = strip_source_en_trailing_segments(raw_en)
        if cleaned and "missing" not in cleaned.lower():
            return f"{prefix} {cleaned}".strip(), "source_en"

    rule_in = _rule_input_for(norm)
    rule_en = translate_source_zh_to_en(rule_in) if rule_in else ""
    if rule_en:
        return f"{prefix} {rule_en}".strip(), "rule"

    return zh_line, "zh"


def translate_sources_to_en(sources: Optional[list[SourceItem]]) -> list[str]:
    out: list[str] = []
    for i, item in enumerate(sources or []):
        line, _path = resolve_source_en_line(item, i)
        out.append(line)
    return out


def gemini_translate_en(text: str) -> str:
    """同步：中文→英文。缺 key 抛 RuntimeError。"""
    if not (text or "").strip():
        return ""
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("QA4_GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY 未配置")
    import httpx

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{_GEMINI_MODEL}:generateContent?key={key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": _GEMINI_SYSTEM}]},
        "contents": [{"parts": [{"text": text}]}],
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini 翻译失败：{resp.text[:200]}")
        data = resp.json()
        try:
            out = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Gemini 响应解析失败：{e}") from e
    out = (out or "").strip()
    if not out:
        raise RuntimeError("Gemini 返回空响应")
    return out


def _sources_zh_tw(sources: list[SourceItem]) -> list[str]:
    out: list[str] = []
    for i, item in enumerate(sources):
        if isinstance(item, dict):
            zh = str(item.get("zh") or "").strip()
            if not zh:
                n = item.get("n", i + 1)
                zh = f"[{n}] {item.get('book_title') or ''} {item.get('message_title') or ''}".strip()
            out.append(to_traditional(zh))
        else:
            out.append(to_traditional(str(item)))
    return out


def translate_answer(
    *,
    text: str,
    sources: Optional[list[SourceItem]] = None,
    target_lang: str,
) -> dict[str, Any]:
    """返回 {answer, sources}。target_lang ∈ zh_tw / en。"""
    sources = list(sources or [])
    lang = (target_lang or "").strip()
    if lang == "zh_tw":
        return {
            "answer": to_traditional(text),
            "sources": _sources_zh_tw(sources),
        }
    if lang == "en":
        body = text or ""
        for marker in ("\n\n【引用书目】", "\n\n引用书目", "\n\n[References]", "【引用书目】", "[References]"):
            if marker in body:
                body = body.split(marker, 1)[0]
                break
        body = body.rstrip()
        masked, ph_map = mask_en_citations(body)
        translated = gemini_translate_en(masked) if masked.strip() else ""
        translated = unmask_en_citations(translated, ph_map)
        en_sources = translate_sources_to_en(sources)
        return {"answer": translated, "sources": en_sources}
    raise ValueError(f"不支持的目标语言: {target_lang}")
