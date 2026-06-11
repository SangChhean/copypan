# -*- coding: utf-8 -*-
import asyncio
import logging
import os
import re
import unicodedata

import anthropic
from elasticsearch import Elasticsearch
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ministerialize_prompts import EXTRACT_PROMPT, JUDGE_PROMPT
import retrieval

logger = logging.getLogger("ministerialize")

router = APIRouter(prefix="/api/testa/ministerialize")

HAIKU_MODEL = "claude-haiku-4-5-20251001"
INDICES = ",".join([
    "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_bib", "kg-rag_map_note", "kg-rag_7feasts",
])

es = Elasticsearch(
    ["http://localhost:9200"],
    basic_auth=("elastic", "qwSD4AF2Dcv"),
)

_PREFIX_RE = re.compile(
    r"^[壹貳贰參叄叁参肆伍陸陆柒捌玖拾一二三四五六七八九十\da-zA-Z（）()\.]+[\t　\s、.]"
)
_BIBLE_BOOKS_66 = (
    "创出利民申书士得撒上撒下王上王下代上代下拉尼斯伯诗箴传歌赛耶哀结但"
    "何珥摩俄拿弥鸿哈番该亚玛"
    "太可路约徒罗林前林后加弗腓西帖前帖后提前提后多门来雅彼前彼后约壹约贰约叁犹启"
    "参"
)
_BIBLE_BOOKS = "".join(dict.fromkeys(_BIBLE_BOOKS_66))
_BOOK_PAT = rf"[{_BIBLE_BOOKS}]{{1,4}}"
_CHAP_PAT = r"[\d一二三四五六七八九十百～~\-至、\s]+"
_REF_UNIT = rf"(?:{_BOOK_PAT})?{_CHAP_PAT}"
_SCRIPTURE_REF_RE = re.compile(
    rf"(—{_BOOK_PAT}{_CHAP_PAT}(?:[,，；;]{_REF_UNIT})*[：:。]?\s*)$"
)
_PURE_VERSE_RE = re.compile(r"(—[\d～~\-至、\s\d]+节[。：:]?\s*)$")
_MSG_LABEL_RE = re.compile(
    r"^\s*第[零一二三四五六七八九十百千\d]+[篇章课节题期]"
)

_STATUS_MAP = {
    "original": "original",
    "minor": "adjusted",
    "replaced": "replaced",
    "manual": "manual",
}


class ProcessRequest(BaseModel):
    lines: list[str]


def _find_scripture_suffix(rest: str) -> tuple[str, str]:
    matches = list(_SCRIPTURE_REF_RE.finditer(rest))
    if matches:
        m = matches[-1]
        return rest[: m.start()], m.group(0)
    m = _PURE_VERSE_RE.search(rest)
    if m:
        return rest[: m.start()], m.group(0)
    return rest, ""


def parse_line(line: str) -> tuple[str, str, str]:
    text = line
    m = _PREFIX_RE.match(text)
    if m:
        prefix = m.group(0)
        rest = text[m.end():]
    else:
        prefix = ""
        rest = text
    body, suffix = _find_scripture_suffix(rest)
    return prefix, body, suffix


def _assemble_line(prefix: str, body: str, suffix: str) -> str:
    result_body = re.sub(r"[。，、；：,;.]+$", "", body.strip())
    result_body = result_body.replace("。", "；")
    return prefix + result_body + suffix


def _normalize(text: str) -> str:
    """去除所有中英文标点和空白，仅用于比对。"""
    if not text:
        return ""
    return "".join(
        ch for ch in text
        if unicodedata.category(ch)[0] not in ("P", "Z")
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


def _finalize_result(result: dict) -> dict:
    if result.get("status") == "manual":
        result["source"] = ""
    return result


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


def _format_source(hit: dict | None) -> str:
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


async def call_haiku(prompt: str, *, max_tokens: int = 200, system: str | None = None) -> str:
    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("Claude 客户端未配置（请设置 CLAUDE_API_KEY）")

    def _sync():
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=max_tokens,
            temperature=0,
            system=system or "你是一位专业、精确的助手。请严格按要求的格式输出。",
            messages=[{"role": "user", "content": prompt}],
        )
        return (msg.content[0].text or "").strip()

    return await asyncio.to_thread(_sync)


async def _retrieve_excerpts(body: str) -> list[dict]:
    bm25_results = await retrieval.bm25_search(es, body, INDICES, 5)
    dense_results = await retrieval.dense_search(es, body, INDICES, 20, 100)
    merged = await retrieval.rrf_merge(bm25_results, dense_results, k=60, bm25_weight=1.0, dense_weight=1.0)
    return await retrieval.rerank(merged, body, 2)


def _clean_extract_output(raw_output: str) -> str:
    output = (raw_output or "").strip()
    if output and any(m in output for m in ("自问", "检查", "**")):
        for ln in output.splitlines():
            ln = ln.strip()
            if ln:
                output = ln
                break
    if not output:
        return ""
    return re.sub(r"[。，、；：,;.]+$", "", output.strip()).strip()


def _parse_judge_status(raw: str) -> str | None:
    status = (raw or "").strip().lower()
    if status in _STATUS_MAP:
        return _STATUS_MAP[status]
    return None


async def process_line(line: str) -> dict:
    prefix, body, suffix = parse_line(line)
    body_stripped = body.strip()

    if not body_stripped:
        return _finalize_result({"original": line, "result": line, "status": "original", "source": ""})

    reranked = await _retrieve_excerpts(body_stripped)
    source = _format_source(reranked[0]) if reranked else ""
    original_result = _assemble_line(prefix, body, suffix)
    norm_body = _normalize(body_stripped)

    if reranked:
        top1_text = reranked[0].get("text") or ""
        if norm_body and norm_body in _normalize(top1_text):
            return _finalize_result({
                "original": line,
                "result": original_result,
                "status": "original",
                "source": source,
            })

    excerpt1 = reranked[0].get("text", "") if len(reranked) > 0 else ""
    excerpt2 = reranked[1].get("text", "") if len(reranked) > 1 else ""
    extract_prompt = EXTRACT_PROMPT.format(
        line=body_stripped,
        excerpt1=excerpt1,
        excerpt2=excerpt2,
    )

    try:
        extracted_raw = await call_haiku(extract_prompt, max_tokens=200)
    except Exception as e:
        logger.warning("[ministerialize] Haiku 抽句失败: %s", e)
        return _finalize_result({
            "original": line,
            "result": original_result,
            "status": "manual",
            "source": source,
        })

    clean_output = _clean_extract_output(extracted_raw)
    norm_clean = _normalize(clean_output)
    norm_excerpt1 = _normalize(excerpt1)
    norm_excerpt2 = _normalize(excerpt2)

    if not clean_output:
        return _finalize_result({
            "original": line,
            "result": original_result,
            "status": "manual",
            "source": "",
        })

    if norm_clean == norm_body:
        in_excerpts = norm_body in norm_excerpt1 or norm_body in norm_excerpt2
        if not in_excerpts:
            return _finalize_result({
                "original": line,
                "result": original_result,
                "status": "manual",
                "source": "",
            })
        return _finalize_result({
            "original": line,
            "result": original_result,
            "status": "original",
            "source": source,
        })

    judge_prompt = JUDGE_PROMPT.format(original=body_stripped, result=clean_output)
    try:
        judge_raw = await call_haiku(
            judge_prompt,
            max_tokens=10,
            system="你是一位专业编辑助手，只输出一个判断词。",
        )
        status = _parse_judge_status(judge_raw)
        if status is None:
            status = "manual"
    except Exception as e:
        logger.warning("[ministerialize] Haiku 判断失败: %s", e)
        status = "manual"

    if status == "manual":
        return _finalize_result({
            "original": line,
            "result": original_result,
            "status": "manual",
            "source": source,
        })

    return _finalize_result({
        "original": line,
        "result": _assemble_line(prefix, clean_output, suffix),
        "status": status,
        "source": source,
    })


@router.post("/process")
async def process_outline(req: ProcessRequest):
    if len(req.lines) > 200:
        raise HTTPException(status_code=400, detail="lines 不得超过 200 条")

    sem = asyncio.Semaphore(5)

    async def _run(line: str) -> dict:
        async with sem:
            return await process_line(line)

    results = await asyncio.gather(*[_run(line) for line in req.lines])
    return {"results": list(results)}
