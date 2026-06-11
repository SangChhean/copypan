import asyncio
import os
import re
from dotenv import load_dotenv

# 双保险：本文件被直接导入时也能读到 .env（路径同 main.py 的 _ENV_PATH）
load_dotenv(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "back_mic", "backend", ".env")
))

from fastapi import APIRouter
from pydantic import BaseModel
from anthropic import Anthropic
from elasticsearch import Elasticsearch
from retrieval import bm25_search, dense_search, rrf_merge, rerank
from ministerialize_prompts import EXTRACT_PROMPT, JUDGE_PROMPT, EXTRACT_SYSTEM, JUDGE_SYSTEM

INDICES = ",".join([
    "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_bib", "kg-rag_map_note",
    "kg-rag_7feasts",
])

# 模型：练习版抽句和判断都用 Haiku（教材约定）。
# 主站抽句用的是 MINISTERIALIZE_CLAUDE_MODEL（Sonnet），
# 若日后想对齐主站质量，把 EXTRACT_MODEL 改成对应 Sonnet 型号即可。
EXTRACT_MODEL = "claude-haiku-4-5-20251001"
JUDGE_MODEL = "claude-haiku-4-5-20251001"

ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
es_client = Elasticsearch(
    hosts=[f"http://{ES_HOST}:{ES_PORT}"],
    basic_auth=(ES_USERNAME, ES_PASSWORD),
    request_timeout=60,
)

_anthropic = Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))


async def call_claude(prompt: str, model: str, system: str, max_tokens: int = 200) -> str:
    def _call():
        msg = _anthropic.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if not msg.content:
            return ""
        return (msg.content[0].text or "").strip()
    return await asyncio.to_thread(_call)


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


def _parse_judge_status(status_raw: str) -> str:
    s = (status_raw or "").strip().lower()
    if s in ("original", "minor", "replaced", "manual"):
        return s
    tokens = set(re.findall(r"[a-z]+", s))
    for word in ("original", "minor", "replaced", "manual"):
        if word in tokens:
            return word
    return "manual"


def _manual_result(line: str, prefix: str, body: str, suffix: str, **extra) -> dict:
    out = {
        "original": line,
        "status": "manual",
        "result": _assemble_outline_line(prefix, body, suffix),
        "suggestion": "",
        "source": "",
    }
    out.update(extra)
    return out


async def ministerialize_one_line(line: str) -> dict:
    prefix, body, suffix = _parse_outline_line(line)
    body_stripped = body.strip()
    try:
        if not body_stripped:
            return {
                "original": line,
                "status": "manual",
                "result": line,
                "suggestion": "",
                "source": "",
            }

        bm25_results = await bm25_search(es_client, body_stripped, INDICES, 5)
        dense_results = await dense_search(es_client, body_stripped, INDICES, 20, 100)
        merged = await rrf_merge(
            bm25_results, dense_results, k=60, bm25_weight=1.0, dense_weight=1.0
        )
        reranked = await rerank(merged, body_stripped, 3)

        if not reranked:
            return _manual_result(line, prefix, body, suffix)

        top1_text = reranked[0].get("text") or ""
        top1_source = _extract_source(reranked[0])

        if body_stripped in top1_text:
            return {
                "original": line,
                "status": "original",
                "result": _assemble_outline_line(prefix, body, suffix),
                "suggestion": "",
                "source": top1_source,
            }

        excerpt1 = reranked[0].get("text", "")
        excerpt2 = reranked[1].get("text", "") if len(reranked) > 1 else ""
        prompt = EXTRACT_PROMPT.format(
            line=body_stripped, excerpt1=excerpt1, excerpt2=excerpt2
        )
        raw = await call_claude(prompt, EXTRACT_MODEL, EXTRACT_SYSTEM, max_tokens=200)

        if raw and any(m in raw for m in ("自问", "检查", "**")):
            first_line = ""
            for ln in raw.splitlines():
                ln = ln.strip()
                if ln:
                    first_line = ln
                    break
            raw = first_line

        if not raw:
            return _manual_result(line, prefix, body, suffix)

        clean_output = re.sub(r"[。，、；：,;.]+$", "", raw.strip()).strip()
        if clean_output == body_stripped:
            return {
                "original": line,
                "status": "original",
                "result": _assemble_outline_line(prefix, body, suffix),
                "suggestion": "",
                "source": top1_source,
            }

        judge_prompt = JUDGE_PROMPT.format(original=body_stripped, result=clean_output)
        status_raw = await call_claude(judge_prompt, JUDGE_MODEL, JUDGE_SYSTEM, max_tokens=10)
        status = _parse_judge_status(status_raw)

        if status == "manual":
            return _manual_result(line, prefix, body, suffix)
        if status == "minor":
            return {
                "original": line,
                "status": "minor",
                "result": _assemble_outline_line(prefix, body, suffix),
                "suggestion": _assemble_outline_line(prefix, clean_output, suffix),
                "source": top1_source,
            }
        return {
            "original": line,
            "status": status,
            "result": _assemble_outline_line(prefix, clean_output, suffix),
            "suggestion": "",
            "source": top1_source,
        }
    except Exception as e:
        return _manual_result(line, prefix, body, suffix, error=str(e))


router = APIRouter(prefix="/api/testc/ministerialize")


class MinisterializeRequest(BaseModel):
    lines: list[str]  # 每行一条纲目，最多 200 条


@router.post("/process")
async def process(req: MinisterializeRequest):
    lines = [l for l in req.lines if l.strip()][:200]
    results = await asyncio.gather(
        *[ministerialize_one_line(line) for line in lines],
        return_exceptions=True,
    )
    out = []
    for line, r in zip(lines, results):
        if isinstance(r, Exception):
            out.append({
                "original": line,
                "status": "manual",
                "result": line,
                "suggestion": "",
                "source": "",
                "error": str(r),
            })
        else:
            out.append(r)
    return {"results": out}
