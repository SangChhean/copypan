# -*- coding: utf-8 -*-
"""职事问答测试路由。"""
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator
from sse_starlette.sse import EventSourceResponse

from qa_service_b import run_pipeline, stream_query

router = APIRouter(prefix="/api/testb/qa")


class QueryRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question 不能为空")
        return v


@router.post("/query")
async def query(req: QueryRequest, request: Request):
    result = await run_pipeline(question=req.question, app=request.app)
    return result


@router.post("/stream")
async def stream_answer(req: QueryRequest, request: Request):
    async def event_generator():
        try:
            async for chunk in stream_query(question=req.question, app=request.app):
                yield {"data": json.dumps(chunk, ensure_ascii=False)}
        except Exception as e:
            yield {
                "data": json.dumps(
                    {"type": "error", "message": str(e)},
                    ensure_ascii=False,
                )
            }

    return EventSourceResponse(event_generator())
