from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal
import sys
import os

# 引入正式后端的 ai_service
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../back_mic/backend"))
from ai_search.ai_service import AISearchService

router = APIRouter()
service = AISearchService()

class TranslateRequest(BaseModel):
    direction: Literal["zh2en", "en2zh"]  # 翻译方向
    content: str                           # 待翻译内容

@router.post("/practice/translate")
async def practice_translate(req: TranslateRequest):
    # 检查内容不能为空
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    # 检查内容不能超过 100000 字
    if len(req.content) > 100000:
        raise HTTPException(status_code=400, detail="content 不能超过 100000 字")

    # 调用正式翻译方法
    if req.direction == "zh2en":
        res = service.translate_outline(req.content)
        return {"result": res.get("answer_en") or res.get("result", ""), "error": res.get("error")}
    else:
        res = service.translate_outline_en2zh(req.content)
        return {"result": res.get("answer_zh") or res.get("result", ""), "error": res.get("error")}
