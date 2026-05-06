# -*- coding: utf-8 -*-
"""内存圣经 JSON 加载、按书卷/章/节查询，以及经文问答流水线。"""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from back_qa.qa.dependencies import get_es_client, get_neo4j_client
from back_qa.qa.prompts import BIBLE_STEP4_ANSWER_GENERATION
from back_qa.qa.qa_service import (
    STEP3_MODEL,
    STEP4_MODEL,
    _calc_cost,
    _step1,
    _build_history_context,
    _call_llm,
    _extract_step4_sources,
    _get_async_claude_client,
    _step2_with_expansion,
)

logger = logging.getLogger(__name__)

_bible: dict[int, dict] = {}

STEP3_MODEL_REWRITE = os.environ.get("QA_STEP3_MODEL", STEP3_MODEL)


def load_bible_data(bible_dir: str) -> None:
    """遍历 bible_dir，加载所有 *.json（跳过 index.json），
    以 data["book"] 为 key 存入 _bible。单文件失败时 log error 继续；目录不可用时不抛出。"""
    global _bible
    _bible = {}
    root = Path(bible_dir)
    if not root.is_dir():
        logger.error("[Bible] bible_dir 不存在或不是目录: %s", bible_dir)
        return

    for path in sorted(root.glob("*.json")):
        if path.name.lower() == "index.json":
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            book = data.get("book")
            if book is None:
                logger.error("[Bible] 跳过（无 book 字段）: %s", path)
                continue
            if not isinstance(book, int):
                try:
                    book = int(book)
                except (TypeError, ValueError):
                    logger.error("[Bible] 跳过（book 非法）: %s book=%r", path, book)
                    continue
            _bible[book] = data
        except Exception as e:
            logger.error("[Bible] 加载失败 %s: %s", path, e, exc_info=True)

    n = len(_bible)
    logger.info("Bible data loaded: %d books", n)


def get_verse(book: int, chapter: int, verse: int) -> dict | None:
    """从内存中精确查找，返回完整 verse 对象，找不到返回 None。"""
    vol = _bible.get(book)
    if not vol:
        return None
    chapters = vol.get("chapters")
    if not isinstance(chapters, list):
        return None
    ch_obj = None
    for c in chapters:
        if isinstance(c, dict) and c.get("chapter") == chapter:
            ch_obj = c
            break
    if not ch_obj:
        return None
    verses = ch_obj.get("verses")
    if not isinstance(verses, list):
        return None
    for v in verses:
        if isinstance(v, dict) and v.get("verse") == verse:
            return v
    return None


def get_verse_range(
    book: int,
    chapter: int,
    verse_start: int | None = None,
    verse_end: int | None = None,
) -> list[dict]:
    """
    返回指定范围的 verse 列表。
    verse_start/verse_end 为 None 时返回整章。
    """
    vol = _bible.get(book)
    if not isinstance(vol, dict):
        return []
    chapters = vol.get("chapters")
    if not isinstance(chapters, list):
        return []
    ch_obj = None
    for c in chapters:
        if isinstance(c, dict) and c.get("chapter") == chapter:
            ch_obj = c
            break
    if not ch_obj:
        return []
    verses = ch_obj.get("verses")
    if not isinstance(verses, list):
        return []
    if verse_start is None and verse_end is None:
        out = [v for v in verses if isinstance(v, dict)]
        out.sort(key=lambda x: int(x.get("verse") or 0))
        return out
    try:
        vs = int(verse_start) if verse_start is not None else 1
        ve = int(verse_end) if verse_end is not None else vs
    except (TypeError, ValueError):
        return []
    if vs > ve:
        vs, ve = ve, vs
    out: list[dict] = []
    for v in verses:
        if not isinstance(v, dict):
            continue
        try:
            n = int(v.get("verse", -1))
        except (TypeError, ValueError):
            continue
        if vs <= n <= ve:
            out.append(v)
    out.sort(key=lambda x: int(x.get("verse") or 0))
    return out


def composite_verses(verses: list[dict]) -> dict | None:
    """将多节合并为供流水线 / 前端使用的一条 verse 结构（单节则原样返回）。"""
    if not verses:
        return None
    if len(verses) == 1:
        return verses[0]
    first, last = verses[0], verses[-1]
    base = dict(first)

    def join_field(key: str) -> str:
        return "\n".join(
            (v.get(key) or "").strip()
            for v in verses
            if isinstance(v.get(key), str) and (v.get(key) or "").strip()
        )

    for key in ("text_gb", "text_big5", "text_en", "text_gb_plain", "text_big5_plain"):
        base[key] = join_field(key)
    try:
        nv0 = int(first.get("verse") or 0)
        nv1 = int(last.get("verse") or 0)
    except (TypeError, ValueError):
        nv0, nv1 = 0, 0
    r0 = str(first.get("ref_gb") or "").strip()
    if r0 and nv1:
        stem = r0.split("～")[0].split("-")[0]
        base["ref_gb"] = f"{stem}～{nv1}"
    r0b = str(first.get("ref_big5") or "").strip()
    if r0b and nv1:
        stem = r0b.split("～")[0].split("-")[0]
        base["ref_big5"] = f"{stem}～{nv1}"
    re0 = str(first.get("ref_en") or "").strip()
    if re0 and ":" in re0 and nv0 and nv1:
        prefix = re0.rsplit(":", 1)[0]
        base["ref_en"] = f"{prefix}:{nv0}-{nv1}"
    merged_fn: list = []
    merged_cr: list = []
    for v in verses:
        fn = v.get("footnotes")
        if isinstance(fn, list):
            merged_fn.extend(fn)
        cr = v.get("crossrefs")
        if isinstance(cr, list):
            merged_cr.extend(cr)
    if merged_fn:
        base["footnotes"] = merged_fn
    if merged_cr:
        base["crossrefs"] = merged_cr
    return base


def _format_passages_for_step4(passages: list[dict]) -> str:
    """与 qa_service._step4_build_prompt 中段落块格式一致。"""
    passage_lines: list[str] = []
    for p in passages:
        book = p.get("book_title", "")
        text = (p.get("text") or "").strip()
        source_zh = (p.get("source_zh") or "").strip()
        source_zh_clean = re.sub(
            r"，第[零一二三四五六七八九十百千]+[段节].*$",
            "",
            source_zh,
        ).strip()
        source_zh_clean = source_zh_clean.strip("（）()").strip()
        header = f"[来源：{source_zh_clean or book}]"
        passage_lines.append(f"{header}\n{text}")
    return "\n---\n".join(passage_lines)


async def _bible_query_rewrite(verse: dict, question: str) -> str:
    """
    用 Haiku 消解指代词，返回改写后的 query。
    输入：经文 text_gb_plain + 用户问题
    失败时静默返回原始拼接：f"{verse['text_gb_plain']} {question}"
    """
    ref_gb = str(verse.get("ref_gb") or "").strip()
    text_gb_plain = str(verse.get("text_gb_plain") or "").strip()
    fallback = f"{text_gb_plain} {question}".strip() or question
    prompt = (
        f"用户正在查考经文「{ref_gb}：{text_gb_plain}」，\n"
        f'提问：「{question}」\n'
        "请将问题中的指代词（它、这、此处等）替换为具体内容，\n"
        "只输出改写后的问题，不输出其他任何内容。\n"
        "若问题无指代词，原样输出问题。"
    )
    try:
        raw, _usage = await _call_llm(
            prompt,
            STEP3_MODEL_REWRITE,
            temperature=0,
            max_tokens=256,
            system="你是一位精确的助手，只按要求输出改写后的问题。",
        )
        out = (raw or "").strip()
        return out if out else fallback
    except Exception:
        return fallback


async def run_bible_pipeline(
    verse: dict,
    question: str,
    history: list,
) -> AsyncGenerator[dict, None]:
    """
    yield 格式与 qa_router 的 SSE JSON 外层一致：
    {"event": "token", "data": "字符"}
    {"event": "done", "data": {"bibliography": [...]}}
    {"event": "error", "data": "错误信息"}
    """
    history = history or []
    ref_gb = str(verse.get("ref_gb") or "").strip()
    text_gb_plain = str(verse.get("text_gb_plain") or "").strip()
    step1_cost = 0.0

    try:
        rewritten = await _bible_query_rewrite(verse, question)
        rewritten_query = rewritten.strip() or question
        neo4j_client = get_neo4j_client()
        # Step1：概念抽取（复用 qa_service）
        step1_result = await _step1(rewritten_query, neo4j_client, history=history)
        deep = step1_result.get("deep", []) or []
        step1_cost = float(step1_result.get("cost_usd", 0) or 0)
        es_client = get_es_client()
        # Step2：deep 概念扩展检索
        passages = await _step2_with_expansion(
            rewritten_query,
            deep,
            es_client,
        )
        passages_text = _format_passages_for_step4(passages)
        history_context = _build_history_context(history)
        firewall_instruction = ""
        prompt = BIBLE_STEP4_ANSWER_GENERATION.format(
            history_context=history_context or "",
            ref_gb=ref_gb,
            text_gb_plain=text_gb_plain,
            question=rewritten_query,
            passages=passages_text,
            firewall_instruction=firewall_instruction,
        )
    except Exception as e:
        logger.exception("[Bible] pipeline prepare failed: %s", e)
        yield {"event": "error", "data": str(e)}
        return

    client = _get_async_claude_client()
    system = (
        "你是一位专注于倪柝声与李常受弟兄职事著作的经文查考助手，"
        "严格基于所提供的段落作答。回答要有清晰的主线，用原文支撑论述，不编造，不拼凑。"
    )
    kwargs: dict[str, Any] = dict(
        model=STEP4_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    if not STEP4_MODEL.startswith("claude-opus-4-7"):
        kwargs["temperature"] = 0.3

    full_text_parts: list[str] = []
    usage = None
    try:
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                if text:
                    full_text_parts.append(text)
                    yield {"event": "token", "data": text}
            try:
                fm = await stream.get_final_message()
                usage = getattr(fm, "usage", None)
            except Exception:
                usage = None
    except Exception as e:
        logger.error("[Bible] Step4 stream 失败: %s", e)
        yield {"event": "error", "data": str(e)}
        return

    full_text = "".join(full_text_parts)
    sources = _extract_step4_sources(full_text)
    step4_cost = _calc_cost(STEP4_MODEL, usage) if usage else 0
    total_cost = step4_cost + step1_cost
    yield {
        "event": "done",
        "data": {
            "bibliography": sources,
            "cost": total_cost,
            "passages": passages,
        },
    }


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    logging.basicConfig(level=logging.INFO)
    _here = Path(__file__).resolve().parent
    _bible_data_dir = _here.parent / "bible_data"
    load_bible_data(str(_bible_data_dir))
    sample = get_verse(50, 1, 1)
    print("get_verse(50, 1, 1):")
    if sample is None:
        print(None)
    else:
        print(json.dumps(sample, ensure_ascii=False, indent=2))
