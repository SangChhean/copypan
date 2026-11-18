# -*- coding: utf-8 -*-
"""答案三语：简→繁（OpenCC + 术语表）；简→英（Gemini REST，需 GEMINI_API_KEY）。

改写自 3.0 back_qa/qa/translation_service.py；不 import back_qa。
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("qa4.translate")

_QA4_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _QA4_ROOT.parent
_TERMS_PATH = _REPO_ROOT / "shared" / "zh_tw_terms.json"
_GEMINI_MODEL = os.environ.get("QA4_TRANSLATION_GEMINI_MODEL") or os.environ.get(
    "QA_TRANSLATION_GEMINI_MODEL", "gemini-2.0-flash"
)

_GEMINI_SYSTEM = (
    "你是专业的职事信息中翻英助手。请将用户给出的中文准确翻译为英文。\n"
    "要求：直接输出译文，不加任何前缀或解释；保留原文语气和神学术语；\n"
    "专有词参考：召会=church, 那灵=the Spirit, 职事=ministry, 三一神=the Triune God 等\n"
    "- 文中形如 [REF:0]、[REF:1] 等标记是引用编号占位符，必须原样保留在对应位置，不得删除、移动或翻译"
)

_citation_re = re.compile(
    r'([」"\u201d\u2019\u0022\u0027])\s*(\d{1,2})(?=\s|<|$|\n|—|-)',
    re.MULTILINE,
)


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
        except Exception:
            try:
                import zhconv

                out = zhconv.convert(out, "zh-hant")
            except ImportError:
                logger.warning("OpenCC/zhconv 未安装，无法简繁转换")
                return src
        for ph, trad in placeholders:
            out = out.replace(ph, trad)
        return out
    except Exception as e:
        logger.error("简转繁失败: %s", e)
        return src


def mask_en_citations(text: str) -> tuple[str, dict[str, str]]:
    src = text or ""
    placeholders: dict[str, str] = {}
    counter = [0]

    def repl(m: re.Match) -> str:
        ph = f"[REF:{counter[0]}]"
        placeholders[ph] = m.group(0)
        counter[0] += 1
        return ph

    return _citation_re.sub(repl, src), placeholders


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


def translate_answer(
    *,
    text: str,
    sources: Optional[list[str]] = None,
    target_lang: str,
) -> dict[str, Any]:
    """返回 {answer, sources}。target_lang ∈ zh_tw / en。"""
    sources = list(sources or [])
    lang = (target_lang or "").strip()
    if lang == "zh_tw":
        return {
            "answer": to_traditional(text),
            "sources": [to_traditional(s) for s in sources],
        }
    if lang == "en":
        body = text or ""
        # 剥离书目块（与 3.0 类似：仅翻正文）
        for marker in ("\n\n【引用书目】", "\n\n引用书目", "\n\n[References]"):
            if marker in body:
                body = body.split(marker, 1)[0]
                break
        masked, ph_map = mask_en_citations(body)
        translated = gemini_translate_en(masked)
        for ph, raw in ph_map.items():
            translated = translated.replace(ph, raw)
        en_sources = list(sources)  # 书目英译依赖缓存 passages，qa4 暂原样返回
        if en_sources:
            translated = translated + "\n\n[References]\n" + "\n".join(en_sources)
        return {"answer": translated, "sources": en_sources}
    raise ValueError(f"不支持的目标语言: {target_lang}")
