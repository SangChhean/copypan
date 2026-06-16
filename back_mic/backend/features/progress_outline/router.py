# -*- coding: utf-8 -*-
from __future__ import annotations

import io
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from user.token import test_token

from features.progress_outline import format_service, llm_client, new_entry_service, pano_series_service
from features.progress_outline.prompts import (
    ENTRY_OVERVIEW_PROMPT,
    ENTRY_SEGMENT_PROMPT,
    PANO_OVERVIEW_PROMPT,
    PANO_SEGMENT_PROMPT,
)
from features.progress_outline.token_utils import default_output_length, estimate_tokens

router = APIRouter(
    prefix="/api/progress",
    tags=["progress_outline"],
    dependencies=[Depends(test_token)],
)


class PanoSearchRequest(BaseModel):
    series_no: int
    source_group_no: int = Field(ge=1, le=6)


class EntrySearchRequest(BaseModel):
    term: str
    source_group_no: int = Field(ge=1, le=6)
    top_k: int = Field(default=80, ge=1, le=200)


class GenerateRequest(BaseModel):
    content: str
    output_length: int = Field(default=3000, ge=500, le=20000)
    term: str = ""


class FormatRequest(BaseModel):
    text: str


@router.get("/series-list")
def series_list():
    return {"series": pano_series_service.list_series()}


@router.post("/pano/search")
def pano_search(req: PanoSearchRequest):
    return pano_series_service.search_articles(req.series_no, req.source_group_no)


@router.post("/entry/search")
async def entry_search(req: EntrySearchRequest):
    try:
        return await new_entry_service.search_entries(
            req.term, req.source_group_no, req.top_k
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/upload-text")
async def upload_text(file: UploadFile = File(...)):
    name = (file.filename or "").lower()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    try:
        if name.endswith(".docx"):
            from docx import Document

            doc = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs if p.text and p.text.strip())
        elif name.endswith(".txt"):
            text = data.decode("utf-8", errors="ignore")
        else:
            raise HTTPException(status_code=400, detail="仅支持 .docx / .txt")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {e}") from e
    tokens = estimate_tokens(text)
    return {
        "text": text,
        "estimated_tokens": tokens,
        "default_output_length": default_output_length(tokens),
    }


async def _generate_json(prompt: str) -> dict:
    return await llm_client.call_claude("", prompt)


@router.post("/pano/generate/segment")
async def pano_generate_segment(req: GenerateRequest):
    prompt = PANO_SEGMENT_PROMPT.format(
        content=req.content, output_length=req.output_length
    )
    return await _generate_json(prompt)


@router.post("/pano/generate/overview")
async def pano_generate_overview(req: GenerateRequest):
    prompt = PANO_OVERVIEW_PROMPT.format(
        content=req.content, output_length=req.output_length
    )
    return await _generate_json(prompt)


@router.post("/entry/generate/segment")
async def entry_generate_segment(req: GenerateRequest):
    prompt = ENTRY_SEGMENT_PROMPT.format(
        content=req.content,
        output_length=req.output_length,
        term=req.term or "（未命名词条）",
    )
    return await _generate_json(prompt)


@router.post("/entry/generate/overview")
async def entry_generate_overview(req: GenerateRequest):
    prompt = ENTRY_OVERVIEW_PROMPT.format(
        content=req.content,
        output_length=req.output_length,
        term=req.term or "（未命名词条）",
    )
    return await _generate_json(prompt)


@router.post("/format_download")
async def format_download(req: FormatRequest):
    try:
        docx_bytes, filename = format_service.format_zh_docx(req.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    ascii_name = filename.encode("ascii", "ignore").decode() or "formatted.docx"
    disposition = (
        f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
    )
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": disposition},
    )
