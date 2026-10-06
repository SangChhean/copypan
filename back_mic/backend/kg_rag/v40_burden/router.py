# -*- coding: utf-8 -*-
"""FastAPI 路由：/api/v40burden（【原流程不变】4.0测试台，第1项：纲目性质 + 负担说明）。

与 3.5 的 /api/kg_rag/generate_burden 互相独立。登录用户可用（与 3.5 的 generate_burden 一致）。
"""
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from user.token import test_token
from kg_rag.v40_burden import service

router = APIRouter(prefix="/api/v40burden", tags=["v40_burden"], dependencies=[Depends(test_token)])
logger = logging.getLogger("kg_rag")


class GenerateRequest(BaseModel):
    topic_no: str = Field(default="", max_length=40, description="篇题编号，如 T1，用于记录编号与导出")
    query: str = Field(..., min_length=1, max_length=500, description="篇题/主题")
    outline_nature: str = Field(default="", description="外在 / 内在 / 最内在 / 显出的外在，必选")
    audience: str = Field(default="", description="面对对象（选填）")
    reference_excerpt: str = Field(default="", description="参考摘录（选填；有则走情境 A）")


class TermStatsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    include_single: bool = False


@router.get("/meta")
async def get_meta():
    return service.meta()


@router.post("/generate")
async def generate(req: GenerateRequest):
    try:
        service.validate_nature(req.outline_nature)
    except service.NatureError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        return await service.generate(
            query=req.query,
            outline_nature=req.outline_nature,
            audience=req.audience,
            reference_excerpt=req.reference_excerpt,
            topic_no=req.topic_no,
        )
    except Exception as e:  # 不降级：失败就报错
        logger.exception("[V40 BURDEN] generate 失败")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/term_stats")
async def term_stats(req: TermStatsRequest):
    return service.term_stats(req.text, req.include_single)


@router.get("/records")
async def records(topic_no: str = Query("", description="篇题编号；留空返回全部")):
    return {"records": service.list_records(topic_no or None)}


@router.get("/records/{record_id}")
async def record_detail(record_id: str):
    rec = service.get_record(record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"找不到记录：{record_id}")
    return rec


@router.get("/export")
async def export(topic_no: str = Query(..., min_length=1, max_length=40)):
    md = service.export_markdown(topic_no)
    name = f"{service._safe_topic_no(topic_no)}-v40-item1.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )
