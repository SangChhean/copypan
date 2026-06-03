# 简繁互转路由
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
from opencc import OpenCC
import json

router = APIRouter(prefix="/api/testc")

# ── 转换函数 ──────────────────────────────────────────
def convert_to_traditional(content: str) -> dict:
    """简体转繁体：先用术语表保护职事词汇，再用 OpenCC 通用转换，最后还原术语"""
    try:
        # 读取术语表
        terms_path = Path(__file__).resolve().parents[3] / "shared" / "zh_tw_terms.json"
        if terms_path.exists():
            with open(terms_path, encoding="utf-8") as f:
                terms = json.load(f)
        else:
            terms = {}

        # 按键长降序排列，长词优先匹配
        sorted_terms = sorted(terms.items(), key=lambda x: len(x[0]), reverse=True)

        # 第一步：把简体术语替换为占位符
        placeholders = {}
        text = content
        for i, (zh, tw) in enumerate(sorted_terms):
            placeholder = f"__TW_{i}__"
            if zh in text:
                text = text.replace(zh, placeholder)
                placeholders[placeholder] = tw

        # 第二步：OpenCC 通用简转繁
        cc = OpenCC("s2t")
        text = cc.convert(text)

        # 第三步：把占位符还原为正确繁体词
        for placeholder, tw in placeholders.items():
            text = text.replace(placeholder, tw)

        return {"answer_zh_tw": text}

    except Exception as e:
        return {"answer_zh_tw": None, "error": str(e)}


def convert_to_simplified(content: str) -> dict:
    """繁体转简体：用 OpenCC t2s 通用转换"""
    try:
        cc = OpenCC("t2s")
        text = cc.convert(content)
        return {"answer_zh_tw": text}
    except Exception as e:
        return {"answer_zh_tw": None, "error": str(e)}


# ── 请求模型 ──────────────────────────────────────────
class ZhConvertRequest(BaseModel):
    content: str
    direction: str = "zh2tw"  # 默认简转繁


# ── 路由 ─────────────────────────────────────────────
@router.post("/zh_convert")
async def zh_convert(req: ZhConvertRequest):
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    if req.direction == "tw2zh":
        return convert_to_simplified(req.content)
    else:
        return convert_to_traditional(req.content)
