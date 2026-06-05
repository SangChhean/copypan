# 简繁互转路由
import io
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from format_utils import format_zh, format_zhtw

logger = logging.getLogger(__name__)


def convert_to_traditional(content: str) -> Dict[str, Optional[str]]:
    """
    将简体中文转为台湾繁体：先按术语表替换，再 OpenCC s2t（失败回退 zhconv zh-hant）。

    Args:
        content: 简体中文全文

    Returns:
        {"answer_zh_tw": str} 成功时；{"answer_zh_tw": None, "error": str} 失败时
    """
    if not (content or "").strip():
        return {"answer_zh_tw": None, "error": "内容为空"}
    text = (content or "").strip()
    try:
        # 1. 加载台湾繁简术语表（简体 -> 繁体）
        terms_path = Path(__file__).resolve().parents[3] / "shared" / "zh_tw_terms.json"
        placeholders: List[tuple] = []  # (placeholder_str, target_value)
        if terms_path.exists():
            terms = json.loads(terms_path.read_text(encoding="utf-8"))
            # 按键长降序，先替换长词避免短词截断
            sorted_keys = sorted(terms.keys(), key=len, reverse=True)
            for idx, simp in enumerate(sorted_keys):
                trad = terms[simp]
                if simp and trad is not None:
                    # 用占位符替换，避免通用转换把术语表结果再改掉
                    ph = f"__TW_{idx}__"
                    placeholders.append((ph, trad))
                    text = text.replace(simp, ph)
        else:
            logger.warning("繁简术语表不存在: %s，仅做通用简繁转换", terms_path)
        # 2. 通用简→繁体（优先 OpenCC s2t，占位符为 ASCII 不会被改动）
        try:
            from opencc import OpenCC
            cc = OpenCC("s2t")
            text = cc.convert(text)
        except Exception:
            try:
                import zhconv
                text = zhconv.convert(text, "zh-hant")
            except ImportError:
                logger.warning("OpenCC/zhconv 未安装，无法做通用简繁转换")
                return {"answer_zh_tw": None, "error": "繁简转换依赖未安装（opencc 或 zhconv）"}
        # 3. 把占位符还原为术语表里的目标用字
        for ph, trad in placeholders:
            text = text.replace(ph, trad)
        return {"answer_zh_tw": text}
    except Exception as e:
        logger.error("简转繁失败: %s", e, exc_info=True)
        return {"answer_zh_tw": None, "error": str(e)}


def convert_to_simplified(content: str) -> Dict[str, Optional[str]]:
    """
    将台湾繁体转为简体：直接使用 OpenCC t2s（失败回退 zhconv zh-cn），不经过术语表。

    Args:
        content: 繁体中文全文

    Returns:
        {"answer_zh_cn": str} 成功时；{"answer_zh_cn": None, "error": str} 失败时
    """
    if not (content or "").strip():
        return {"answer_zh_cn": None, "error": "内容为空"}
    text = (content or "").strip()
    try:
        # 繁→简：优先 OpenCC t2s（繁体→简体），否则 zhconv
        try:
            from opencc import OpenCC
            cc = OpenCC("t2s")
            text = cc.convert(text)
        except Exception:
            try:
                import zhconv
                text = zhconv.convert(text, "zh-cn")
            except ImportError:
                logger.warning("OpenCC/zhconv 未安装，无法做繁简转换")
                return {"answer_zh_cn": None, "error": "繁简转换依赖未安装（opencc 或 zhconv）"}
        return {"answer_zh_cn": text}
    except Exception as e:
        logger.error("繁转简失败: %s", e, exc_info=True)
        return {"answer_zh_cn": None, "error": str(e)}


class ZhConvertRequest(BaseModel):
    content: str


class ZhToSimplifiedRequest(BaseModel):
    content: str


router = APIRouter(prefix="/api/testb")


@router.post("/zh_convert")
def zh_convert(request: ZhConvertRequest):
    if not (request.content or "").strip():
        raise HTTPException(status_code=400, detail="内容为空")
    result = convert_to_traditional(request.content)
    if result.get("error") and result.get("answer_zh_tw") is None:
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/zh_to_simplified")
def zh_to_simplified(request: ZhToSimplifiedRequest):
    if not (request.content or "").strip():
        raise HTTPException(status_code=400, detail="内容为空")
    result = convert_to_simplified(request.content)
    if result.get("error") and result.get("answer_zh_cn") is None:
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# ── 易错字检查 ──────────────────────────────────────────

def _load_error_chars() -> list[str]:
    p = Path(__file__).resolve().parents[1] / "error_chars.txt"
    if not p.exists():
        return []
    words = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
    words = [w for w in words if w]
    words.sort(key=len, reverse=True)
    return words

def _load_colon_dict(filename: str) -> dict[str, str]:
    p = Path(__file__).resolve().parents[1] / filename
    mapping: dict[str, str] = {}
    if not p.exists():
        return mapping
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sep = "\uff1a" if "\uff1a" in line else "："
        if sep not in line:
            continue
        src, tgt = line.split(sep, 1)
        src, tgt = src.strip(), tgt.strip()
        if src and tgt:
            mapping[src] = tgt
    return mapping

def _build_suggestion_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for simp, trad in _load_colon_dict("自定义词典.txt").items():
        if simp != trad:
            result[simp] = trad
    for wrong, correct in _load_colon_dict("post_trad_rules.txt").items():
        if wrong != correct:
            result[wrong] = correct
    return result

def scan_error_chars(text: str) -> list[dict]:
    error_words = _load_error_chars()
    post_rules = _load_colon_dict("post_trad_rules.txt")
    all_scan_words = list({*error_words, *post_rules.keys()})
    all_scan_words.sort(key=len, reverse=True)
    suggestion_map = _build_suggestion_map()
    if not all_scan_words or not text:
        return []
    seen: set[str] = set()
    hits: list[dict] = []
    for word in all_scan_words:
        if not word or word in seen:
            continue
        positions = [i for i in range(len(text)) if text.startswith(word, i)]
        if not positions:
            continue
        seen.add(word)
        suggestion = suggestion_map.get(word)
        if suggestion == word:
            suggestion = None
        hits.append({
            "word": word,
            "suggestion": suggestion,
            "positions": positions,
        })
    hits.sort(key=lambda h: h["positions"][0])

    # 去重：若某词的每个位置都已被更长的词覆盖，则跳过
    def _is_covered(word: str, positions: list[int], accepted: list[dict]) -> bool:
        for pos in positions:
            covered = any(
                pos >= a_pos and pos + len(word) <= a_pos + len(a["word"])
                for a in accepted
                for a_pos in a["positions"]
            )
            if not covered:
                return False
        return True

    deduped: list[dict] = []
    for hit in hits:
        if not _is_covered(hit["word"], hit["positions"], deduped):
            deduped.append(hit)

    return deduped


class CheckErrorsRequest(BaseModel):
    content: str

@router.post("/check_errors")
def check_errors(request: CheckErrorsRequest):
    text = (request.content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="内容为空")
    hits = scan_error_chars(text)
    return {"hits": hits}


# ── 刷格式（生成 docx） ──────────────────────────────────

class FormatRequest(BaseModel):
    text: str


async def _docx_response(result: tuple[bytes, str]) -> Response:
    docx_bytes, filename = result
    encoded = quote(filename + ".docx")
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"}
    )


@router.post("/format/zh")
async def format_zh_route(req: FormatRequest):
    import asyncio
    result = await asyncio.to_thread(format_zh, req.text)
    return await _docx_response(result)


@router.post("/format/zhtw")
async def format_zhtw_route(req: FormatRequest):
    import asyncio
    result = await asyncio.to_thread(format_zhtw, req.text)
    return await _docx_response(result)
