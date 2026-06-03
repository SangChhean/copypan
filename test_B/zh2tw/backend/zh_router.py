# 简繁互转路由
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
