# -*- coding: utf-8 -*-
"""QA 翻译服务：简体→台湾繁体（OpenCC + 术语表），以及通用中文→英文（Gemini）。

入口函数:
- to_traditional(text)                       简→繁
- translate_answer_to_traditional(answer)    Step4 答案简→繁
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("qa")

# 术语表：仓库根目录 shared/zh_tw_terms.json（与 back_mic 共用）
_TERMS_PATH = Path(__file__).resolve().parents[2] / "shared" / "zh_tw_terms.json"

# Gemini 客户端懒加载（参考 asr_service 中 _get_client 的写法）
_gemini_client: Any = None
_GEMINI_MODEL = os.environ.get("QA_TRANSLATION_GEMINI_MODEL", "gemini-3.5-flash")

_GEMINI_TRANSLATION_SYSTEM = (
    "你是专业的职事信息中翻英助手。请将用户给出的中文准确翻译为英文。\n"
    "要求：直接输出译文，不加任何前缀或解释；保留原文语气和神学术语；\n"
    "专有词参考：召会=church, 那灵=the Spirit, 职事=ministry, 三一神=the Triune God 等\n"
    "- 文中形如 [REF:0]、[REF:1] 等标记是引用编号占位符，必须原样保留在对应位置，不得删除、移动或翻译"
)

# 英译正文：引号后的引用编号；送入 Gemini 前占位保护（前瞻含换行、破折号、连字符等）
citation_pattern = re.compile(
    r'([」"\u201d\u2019\u0022\u0027])\s*(\d{1,2})(?=\s|<|$|\n|—|-)',
    re.MULTILINE,
)


def mask_en_citations_for_translation(text: str) -> tuple[str, dict[str, str]]:
    """将「右引号 + 可选空白 + 1～2 位编号」替换为 [REF:n]，返回 (masked, {token: 原文片段})。"""
    src = text or ""
    placeholders: dict[str, str] = {}
    if not src.strip():
        return src, placeholders
    counter = [0]

    def repl(m: re.Match) -> str:
        ph = f"[REF:{counter[0]}]"
        placeholders[ph] = m.group(0)
        counter[0] += 1
        return ph

    return citation_pattern.sub(repl, src), placeholders


# 恢复本圣经中文书卷缩写 → 英文书名
_BIBLE_BOOK_MAP: dict[str, str] = {
    # 旧约
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
    # 新约
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

# 中文数字 → 阿拉伯数字（章号 / 篇号等，支持常用范围）
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

# 7feasts 特会类型映射
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


def translate_source_zh_to_en(source_zh: str) -> str:
    """将 source_zh 按规则转换为英文，支持恢复本圣经注释和 7feasts 特会两种格式。
    无法识别时返回空字符串（由调用方决定是否保留中文）。
    """
    s = (source_zh or "").strip()
    s = s.strip("（）()").strip()
    s = s.strip("， ").strip()

    # --- 恢复本圣经注释 ---
    # 格式：恢复本圣经，{书卷}{章}{节}，注{N}
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
                chapter_zh = book_chapter_raw[len(abbr):]
                break

        if book_en and chapter_zh:
            chapter = _ZH_NUM_MAP.get(chapter_zh)
            if chapter:
                return (
                    f"Holy Bible Recovery Version, {book_en} {chapter}:{verse}, "
                    f"footnote {footnote}"
                )

    # --- 7feasts 特会 ---
    # 格式：{年份}年{特会类型}，第{N}篇（后可跟「，第…段」等）
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


def _get_gemini_client() -> Any:
    global _gemini_client
    if _gemini_client is None:
        api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("未配置 GEMINI_API_KEY")
        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


# ---------------------------------------------------------------------------
# 简 → 繁
# ---------------------------------------------------------------------------

def to_traditional(text: str) -> str:
    """简体 → 繁体：先按术语表占位替换，再 OpenCC s2t（失败回退 zhconv zh-hant）。
    依赖全部缺失或异常时返回原文（不抛错）。
    """
    src = text or ""
    if not src.strip():
        return src
    out = src
    try:
        placeholders: list[tuple[str, str]] = []
        if _TERMS_PATH.exists():
            try:
                terms = json.loads(_TERMS_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("[QA] 繁简术语表解析失败: %s", e)
                terms = {}
            sorted_keys = sorted(terms.keys(), key=len, reverse=True)
            for idx, simp in enumerate(sorted_keys):
                trad = terms.get(simp)
                if simp and trad is not None:
                    ph = f"__TW_{idx}__"
                    placeholders.append((ph, trad))
                    out = out.replace(simp, ph)
        else:
            logger.warning("[QA] 繁简术语表不存在: %s，仅做通用简繁转换", _TERMS_PATH)

        try:
            from opencc import OpenCC
            cc = OpenCC("s2t")
            out = cc.convert(out)
        except Exception:
            try:
                import zhconv
                out = zhconv.convert(out, "zh-hant")
            except ImportError:
                logger.warning("[QA] OpenCC/zhconv 未安装，无法做通用简繁转换")
                return src

        for ph, trad in placeholders:
            out = out.replace(ph, trad)
        return out
    except Exception as e:
        logger.error("[QA] 简转繁失败: %s", e, exc_info=True)
        return src


def translate_answer_to_traditional(answer: str) -> str:
    """Step4 答案简体 → 台湾繁体。"""
    return to_traditional(answer)


def _call_gemini(model: str, text: str) -> str:
    """单次调用 Gemini 生成译文；空响应抛 RuntimeError。"""
    client = _get_gemini_client()
    from google.genai import types

    response = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=_GEMINI_TRANSLATION_SYSTEM,
        ),
    )
    out = (getattr(response, "text", "") or "").strip()
    if not out:
        raise RuntimeError("Gemini 返回空响应")
    return out


def _generate_with_retries(model: str, text: str, max_retries: int = 3) -> str:
    """针对 503 / UNAVAILABLE 做指数退避重试（1s / 2s / 4s），其余错误立即抛出。"""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return _call_gemini(model, text)
        except Exception as e:
            last_exc = e
            err_str = str(e)
            if "503" not in err_str and "UNAVAILABLE" not in err_str:
                raise
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    "[QA] Gemini 503，第 %d 次重试，等待 %ds: %s",
                    attempt + 1, wait, e,
                )
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def _gemini_translate(text: str, max_retries: int = 2) -> str:
    """同步：把单段中文翻译成英文。空输入返回空串；失败抛异常由调用方处理。"""
    if not (text or "").strip():
        return ""
    return _generate_with_retries(_GEMINI_MODEL, text, max_retries)
