# 简繁互转路由
from fastapi import APIRouter
from pydantic import BaseModel, Field
import json
import re
import opencc
from pathlib import Path

router = APIRouter()

# ── 术语表路径 ──────────────────────────────────────────
TERMS_PATH = Path(__file__).resolve().parents[3] / "shared" / "zh_tw_terms.json"

# ── 启动时加载术语表 ────────────────────────────────────
def _load_terms() -> dict:
    with open(TERMS_PATH, encoding="utf-8") as f:
        return json.load(f)

TERMS: dict = _load_terms()

# 按简体词长度降序排列，避免短词先替换导致长词漏匹配
SORTED_TERMS = sorted(TERMS.keys(), key=len, reverse=True)

# ── OpenCC 转换器（s2t：简体→繁体）──────────────────────
converter = opencc.OpenCC("s2t")

# ── 核心转换函数 ────────────────────────────────────────
def convert_zh2tw(text: str) -> str:
    """
    步骤：
    ① 把术语表中的简体词替换为占位符 __TW_n__
    ② 调用 OpenCC s2t 做通用简繁转换
    ③ 把占位符还原为术语表中对应的繁体词
    """
    placeholders = {}

    # ① 占位符替换（按词长降序，避免短词覆盖长词）
    working = text
    for i, simplified in enumerate(SORTED_TERMS):
        placeholder = f"__TW_{i}__"
        if simplified in working:
            working = working.replace(simplified, placeholder)
            placeholders[placeholder] = TERMS[simplified]

    # ② OpenCC 通用转换
    working = converter.convert(working)

    # ③ 还原占位符 → 繁体词
    for placeholder, traditional in placeholders.items():
        working = working.replace(placeholder, traditional)

    return working


def convert_tw2zh(text: str) -> str:
    """繁→简：直接用 OpenCC t2s，不走术语表"""
    return opencc.OpenCC("t2s").convert(text)

# ── 请求 / 响应模型 ─────────────────────────────────────
class ZhConvertRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)

class ZhConvertResponse(BaseModel):
    result: str
    error: str | None = None

# ── API 路由 ────────────────────────────────────────────
@router.post("/api/testa/zh_convert", response_model=ZhConvertResponse)
def zh_convert(request: ZhConvertRequest):
    try:
        result = convert_zh2tw(request.content)
        return ZhConvertResponse(result=result)
    except Exception as e:
        return ZhConvertResponse(result="", error=str(e))

@router.post("/api/testa/tw_convert", response_model=ZhConvertResponse)
def tw_convert(request: ZhConvertRequest):
    try:
        result = convert_tw2zh(request.content)
        return ZhConvertResponse(result=result)
    except Exception as e:
        return ZhConvertResponse(result="", error=str(e))
