import asyncio
import logging
import os
import re

from anthropic import Anthropic
from elasticsearch import Elasticsearch
from fastapi import APIRouter
from pydantic import BaseModel

from ministerialize_prompts import EXTRACT_PROMPT, JUDGE_PROMPT
from retrieval import bm25_search, dense_search, rerank, rrf_merge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/testb/ministerialize")

_INDICES_BASE = ",".join([
    "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_bib", "kg-rag_map_note",
    "kg-rag_7feasts",
])

_MINISTERIALIZE_PREFIX_RE = re.compile(
    r"^[壹貳贰參叄叁参肆伍陸陆柒捌玖拾一二三四五六七八九十\da-z（）()]+[\t　]"
)
# 圣经 66 卷常用简称单字集（旧约+新约拆字去重，供 _BOOK_PAT 字符类使用）
_BIBLE_BOOKS_66 = (
    "创出利民申书士得撒上撒下王上王下代上代下拉尼斯伯诗箴传歌赛耶哀结但"
    "何珥摩俄拿弥鸿哈番该亚玛"
    "太可路约徒罗林前林后加弗腓西帖前帖后提前提后多门来雅彼前彼后约壹约贰约叁犹启"
    "参"  # 参书（纲目参考，非 66 卷正典简称）
)
_BIBLE_BOOKS = "".join(dict.fromkeys(_BIBLE_BOOKS_66))  # 去重保序
_BOOK_PAT = rf"[{_BIBLE_BOOKS}]{{1,4}}"
_CHAP_PAT = r"[\d一二三四五六七八九十百～~\-至、\s]+"
_REF_UNIT = rf"(?:{_BOOK_PAT})?{_CHAP_PAT}"  # 书卷名可选，支持「十四34」纯章节
_SCRIPTURE_REF_RE = re.compile(
    rf"(—{_BOOK_PAT}{_CHAP_PAT}(?:[,，；;]{_REF_UNIT})*[：:。]?\s*)$"
)
_PURE_VERSE_RE = re.compile(r"(—[\d～~\-至、\s\d]+节[。：:]?\s*)$")
_TRAILING_PUNCT = "：；。！？、"
_SCRIPTURE_DASH_FIND_RE = re.compile(
    rf"—{_BOOK_PAT}{_CHAP_PAT}(?:[,，；;]{_REF_UNIT})*[：:。]?"
)
_SCRIPTURE_PAREN_FIND_RE = re.compile(
    rf"[（(]{_BOOK_PAT}{_CHAP_PAT}(?:[,，；;]{_REF_UNIT})*[：:。]?[）)]"
)
_PURE_VERSE_FIND_RE = re.compile(r"—[\d～~\-至、\s\d]+节[。：:]?")

ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
es_client = Elasticsearch(
    hosts=[f"http://{ES_HOST}:{ES_PORT}"],
    basic_auth=(ES_USERNAME, ES_PASSWORD),
    request_timeout=30,
)


def _find_scripture_suffix(rest: str) -> tuple[str, str]:
    """从 rest 里识别经文 suffix，返回 (body, suffix)。"""
    matches = list(_SCRIPTURE_REF_RE.finditer(rest))
    if matches:
        m = matches[-1]
        return rest[: m.start()], m.group(0)
    m = _PURE_VERSE_RE.search(rest)
    if m:
        return rest[: m.start()], m.group(0)
    return rest, ""


def _parse_outline_line(line: str) -> tuple[str, str, str]:
    """
    返回 (prefix, body, suffix)
    prefix: 行首编号+分隔符，如 "壹\t"
    suffix: 经文引用后缀，如 "—哀三22~23："，没有则为 ""
    body: 中间正文
    """
    text = line
    m = _MINISTERIALIZE_PREFIX_RE.match(text)
    if m:
        prefix = m.group(0)
        rest = text[m.end() :]
    else:
        prefix = ""
        rest = text

    body, suffix = _find_scripture_suffix(rest)

    return prefix, body, suffix


def _assemble_outline_line(prefix: str, body: str, suffix: str) -> str:
    result_body = re.sub(r"[。，、；：,;.]+$", "", body.strip())
    result_body = result_body.replace("。", "；")  # 兜底：正文内句号改分号
    return prefix + result_body + suffix


def _find_all_scripture_refs(text: str) -> list[str]:
    """按原文出现顺序收集所有经文引用片段（不锚定行尾）。"""
    found: list[tuple[int, int, str]] = []
    for pat in (_SCRIPTURE_DASH_FIND_RE, _SCRIPTURE_PAREN_FIND_RE, _PURE_VERSE_FIND_RE):
        for m in pat.finditer(text):
            found.append((m.start(), m.end(), m.group(0)))
    found.sort(key=lambda x: x[0])
    refs: list[str] = []
    occupied: list[tuple[int, int]] = []
    for start, end, frag in found:
        if any(not (end <= s or start >= e) for s, e in occupied):
            continue
        occupied.append((start, end))
        refs.append(frag)
    return refs


def restore_original_elements(original_line: str, result_line: str) -> str:
    """拼回结果后兜底：补回缺失经文引用与行尾标点（只补不删）。"""
    result = result_line or ""

    missing_refs = [r for r in _find_all_scripture_refs(original_line) if r not in result]
    if missing_refs:
        base = result.rstrip()
        trailing = ""
        while base and base[-1] in _TRAILING_PUNCT + ",.;":
            trailing = base[-1] + trailing
            base = base[:-1]
        result = base + "".join(missing_refs) + trailing

    orig = (original_line or "").rstrip()
    if orig and orig[-1] in _TRAILING_PUNCT:
        ch = orig[-1]
        res = result.rstrip()
        if not res or res[-1] != ch:
            result = res + ch

    return result


def _normalize_line_whitespace(text: str) -> str:
    text = (text or "").strip()
    return re.sub(r"[\t\u3000 ]+", " ", text)


def _finalize_line_result(line: str, result: str, status: str, source: str) -> dict:
    final_result = restore_original_elements(line, result)
    if _normalize_line_whitespace(line) == _normalize_line_whitespace(final_result):
        status = "original"
    return {
        "original": line,
        "status": status,
        "result": final_result,
        "source": source,
    }


def _extract_source(hit: dict) -> str:
    source_zh = (hit.get("source_zh") or "").strip()
    if not source_zh:
        return (hit.get("book_title") or "").strip()
    s = re.sub(
        r"，第[零一二三四五六七八九十百千\d]+[段节](?=[）)]*$)",
        "",
        source_zh,
    ).strip()
    while len(s) >= 2 and (
        (s[0] == "（" and s[-1] == "）") or (s[0] == "(" and s[-1] == ")")
    ):
        s = s[1:-1]
    return s.strip()


def _clean_claude_extract_output(claude_output: str) -> str:
    raw_output = (claude_output or "").strip()
    if raw_output and any(m in raw_output for m in ("自问", "检查", "**")):
        first_line = ""
        for ln in raw_output.splitlines():
            ln = ln.strip()
            if ln:
                first_line = ln
                break
        raw_output = first_line
    output = raw_output
    if output:
        return re.sub(r"[。，、；：,;.]+$", "", output.strip()).strip()
    return ""


async def call_haiku(prompt: str) -> str:
    api_key = os.getenv("CLAUDE_API_KEY")
    client = Anthropic(api_key=api_key)

    def _run() -> str:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )

    return await asyncio.to_thread(_run)


async def _judge_ministerialize_status(original_body: str, clean_output: str) -> str:
    prompt = JUDGE_PROMPT.format(original=original_body, result=clean_output)
    try:
        output = await call_haiku(prompt)
        status = (output or "").strip().lower()
        if status in ("original", "minor", "replaced", "manual"):
            return status
        logger.warning("[职事化判断] Haiku 返回非预期值: %s，fallback 到 manual", status)
        return "manual"
    except Exception as e:
        logger.warning("[职事化判断] Haiku 调用失败: %s，fallback 到 manual", e)
        return "manual"


async def ministerialize_one_line(line: str) -> dict:
    """单条纲目：解析结构 → BM25/Dense 仅用 body → 拼回 prefix/suffix。"""
    prefix, body, suffix = _parse_outline_line(line)
    body_stripped = body.strip()

    if not body_stripped:
        return _finalize_line_result(line, line, "manual", "")

    bm25_results = await bm25_search(es_client, body_stripped, _INDICES_BASE, 5)
    dense_results = await dense_search(es_client, body_stripped, _INDICES_BASE, 20, 100)
    merged = await rrf_merge(bm25_results, dense_results, k=60, bm25_weight=1.0, dense_weight=1.0)
    reranked = await rerank(merged, body_stripped, 3)

    if not reranked:
        return _finalize_line_result(
            line, _assemble_outline_line(prefix, body, suffix), "manual", ""
        )

    top1_source = _extract_source(reranked[0])
    top1_text = reranked[0].get("text") or ""
    if body_stripped in top1_text:
        return _finalize_line_result(
            line,
            _assemble_outline_line(prefix, body, suffix),
            "original",
            top1_source,
        )

    excerpt1 = reranked[0].get("text", "") if len(reranked) > 0 else ""
    excerpt2 = reranked[1].get("text", "") if len(reranked) > 1 else ""
    prompt = EXTRACT_PROMPT.format(
        line=body_stripped,
        excerpt1=excerpt1,
        excerpt2=excerpt2,
    )
    try:
        claude_output = await call_haiku(prompt)
        clean_output = _clean_claude_extract_output(claude_output)
        if clean_output:
            if clean_output == body_stripped:
                return _finalize_line_result(
                    line,
                    _assemble_outline_line(prefix, body, suffix),
                    "original",
                    top1_source,
                )
            status = await _judge_ministerialize_status(body_stripped, clean_output)
            if status == "manual":
                return _finalize_line_result(
                    line,
                    _assemble_outline_line(prefix, body, suffix),
                    status,
                    "",
                )
            if status == "minor":
                return _finalize_line_result(
                    line,
                    _assemble_outline_line(prefix, body, suffix),
                    status,
                    top1_source,
                )
            return _finalize_line_result(
                line,
                _assemble_outline_line(prefix, clean_output, suffix),
                status,
                top1_source,
            )
    except Exception as e:
        logger.warning("[纲目职事化] Claude 调用失败: %s", e)

    return _finalize_line_result(
        line, _assemble_outline_line(prefix, body, suffix), "manual", ""
    )


class MinisterializeRequest(BaseModel):
    lines: list[str]


@router.get("/ping")
async def ping():
    return {"status": "ok"}


@router.post("/process")
async def process(req: MinisterializeRequest):
    lines = [line for line in req.lines if (line or "").strip()]
    lines = lines[:200]

    raw_results = await asyncio.gather(
        *[ministerialize_one_line(line) for line in lines],
        return_exceptions=True,
    )

    results = []
    for line, item in zip(lines, raw_results):
        if isinstance(item, Exception):
            results.append({
                "original": line,
                "result": line,
                "status": "manual",
                "source": "",
                "error": str(item),
            })
        else:
            results.append(item)

    return {"results": results}
