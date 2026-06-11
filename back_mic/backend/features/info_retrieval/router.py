from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import asyncio
import base64
import json
import logging
from urllib.parse import quote

from user.token import test_token
from features.info_retrieval.service import info_retrieval_export

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["info_retrieval"])
_auth = APIRouter(dependencies=[Depends(test_token)])


class InfoRetrievalRequest(BaseModel):
    """信息检索请求：多关键词 AND、排除关键词 OR、DOCX 大小上限"""
    keyword: str = Field(..., min_length=1, max_length=500, description="搜索关键词，空格隔开，多词 AND")
    exclude_keywords: Optional[str] = Field(None, max_length=500, description="排除关键词，空格隔开，多词 OR")
    max_size_mb: Optional[int] = Field(100, description="单 DOCX 合并大小上限（MB），40 或 100")


@_auth.post("/ai_search/info_retrieval", summary="信息检索：多关键词/排除词导出 DOCX（单文件 40MB，超出则多个 DOCX 分别下载）")
async def info_retrieval_export_route(request: InfoRetrievalRequest):
    try:
        logger.info("info_retrieval 请求: keyword=%r, exclude_keywords=%r",
                    request.keyword, request.exclude_keywords)
        docx_bytes, filename, log_message = await asyncio.to_thread(
            info_retrieval_export,
            request.keyword,
            request.exclude_keywords or "",
        )
        if docx_bytes is None:
            body = json.dumps({"no_results": True, "message": log_message}, ensure_ascii=False).encode("utf-8")
            return Response(
                content=body,
                status_code=200,
                media_type="application/json; charset=utf-8",
                headers={"X-No-Results": "true"},
            )
        if isinstance(docx_bytes, list):
            payload = {
                "files": [
                    {"filename": fname, "content": base64.b64encode(content).decode("ascii")}
                    for content, fname in docx_bytes
                ],
                "log_message": log_message,
            }
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            log_b64 = base64.b64encode(log_message.encode("utf-8")).decode("ascii")
            return Response(
                content=body,
                status_code=200,
                media_type="application/json; charset=utf-8",
                headers={"X-Multiple-Files": "true", "X-Retrieval-Log": log_b64},
            )
        encoded_filename = quote(filename)
        log_b64 = base64.b64encode(log_message.encode("utf-8")).decode("ascii")
        headers = {
            "Content-Disposition": f'attachment; filename*=UTF-8\'\'{encoded_filename}',
            "Content-Length": str(len(docx_bytes)),
            "X-Retrieval-Log": log_b64,
        }
        return StreamingResponse(
            iter([docx_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )
    except Exception as e:
        logger.error("信息检索导出失败: %s", e, exc_info=True)
        msg = f"导出失败：{str(e)}"
        body = json.dumps({"no_results": True, "message": msg}, ensure_ascii=False).encode("utf-8")
        return Response(
            content=body,
            status_code=200,
            media_type="application/json; charset=utf-8",
            headers={"X-No-Results": "true"},
        )


router.include_router(_auth)
