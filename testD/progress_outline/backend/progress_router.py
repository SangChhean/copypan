# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import format_service
import llm_client
import new_entry_service
import pano_series_service
from prompts.outline_prompt import (
    ENTRY_OVERVIEW_PROMPT,
    ENTRY_SEGMENT_PROMPT,
    PANO_OVERVIEW_PROMPT,
    PANO_SEGMENT_PROMPT,
)
from token_utils import default_output_length, estimate_tokens

router = APIRouter(prefix="/api/progress", tags=["progress_outline"])
pano_router = APIRouter(prefix="/api/pano", tags=["pano"])
entry_router = APIRouter(prefix="/api/entry", tags=["entry"])

STAGE_BUTTONS = [
    {"no": 1, "label": "壹 倪柝声"},
    {"no": 2, "label": "贰 第一阶段"},
    {"no": 3, "label": "叁 第二阶段"},
    {"no": 4, "label": "肆 第三阶段"},
    {"no": 5, "label": "伍 第四阶段"},
    {"no": 6, "label": "陆 高峰阶段"},
]


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


@router.get("/stages")
def get_stages():
    return {"stages": STAGE_BUTTONS}


def _series_list():
    return {"series": pano_series_service.list_series()}


def _pano_search(req: PanoSearchRequest):
    return pano_series_service.search_articles(req.series_no, req.source_group_no)


async def _entry_search(req: EntrySearchRequest):
    return await new_entry_service.search_entries(req.term, req.source_group_no, req.top_k)


@router.get("/series-list")
def series_list():
    return _series_list()


@pano_router.get("/series-list")
def pano_series_list():
    return _series_list()


@router.post("/pano/search")
def pano_search(req: PanoSearchRequest):
    try:
        return _pano_search(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@pano_router.post("/articles")
def pano_articles(req: PanoSearchRequest):
    try:
        return _pano_search(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/entry/search")
async def entry_search(req: EntrySearchRequest):
    try:
        return await _entry_search(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@entry_router.post("/search")
async def entry_search_alias(req: EntrySearchRequest):
    try:
        return await _entry_search(req)
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
    prompt = PANO_SEGMENT_PROMPT.format(content=req.content, output_length=req.output_length)
    return await _generate_json(prompt)


@router.post("/pano/generate/overview")
async def pano_generate_overview(req: GenerateRequest):
    prompt = PANO_OVERVIEW_PROMPT.format(content=req.content, output_length=req.output_length)
    return await _generate_json(prompt)


@router.post("/entry/generate/segment")
async def entry_generate_segment(req: GenerateRequest):
    prompt = ENTRY_SEGMENT_PROMPT.format(
        content=req.content, output_length=req.output_length, term=req.term or "（未命名词条）"
    )
    return await _generate_json(prompt)


@router.post("/entry/generate/overview")
async def entry_generate_overview(req: GenerateRequest):
    prompt = ENTRY_OVERVIEW_PROMPT.format(
        content=req.content, output_length=req.output_length, term=req.term or "（未命名词条）"
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
