# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import io
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from user.token import test_token

from features.progress_outline import format_service, group_edit_service, llm_client, new_entry_service, pano_series_service
from features.progress_outline import ministerialize_service
from features.progress_outline.prompts import (
    build_entry_segment_prompt,
    build_pano_segment_prompt,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/progress",
    tags=["progress_outline"],
    dependencies=[Depends(test_token)],
)
pano_router = APIRouter(prefix="/api/pano", tags=["pano"], dependencies=[Depends(test_token)])
entry_router = APIRouter(prefix="/api/entry", tags=["entry"], dependencies=[Depends(test_token)])


class PanoSearchRequest(BaseModel):
    series_no: int
    source_group_no: int = Field(ge=1, le=5)


class EntrySearchRequest(BaseModel):
    term: str
    source_group_no: int = Field(ge=1, le=5)
    top_k: int = Field(default=80, ge=1, le=200)


class GroupSegmentInput(BaseModel):
    title: str = ""
    burden: str = ""
    plain_text: str = ""
    record_count: int = Field(default=0, ge=0)


class GenerateRequest(BaseModel):
    content: str = ""
    term: str = ""
    groups: list[GroupSegmentInput] | None = None


class FormatRequest(BaseModel):
    text: str
    title: str = ""


class FormatGroupItem(BaseModel):
    text: str
    title: str = ""


class FormatBatchRequest(BaseModel):
    items: list[FormatGroupItem] = Field(default_factory=list)


class PanoGroupEditInput(BaseModel):
    title: str = ""
    burden: str = ""
    articles: list[dict] = Field(default_factory=list)


class EntryGroupEditInput(BaseModel):
    title: str = ""
    burden: str = ""
    items: list[dict] = Field(default_factory=list)


class RecomputePanoGroupsRequest(BaseModel):
    groups: list[PanoGroupEditInput] = Field(default_factory=list)


class RecomputeEntryGroupsRequest(BaseModel):
    groups: list[EntryGroupEditInput] = Field(default_factory=list)


@router.post("/groups/recompute/pano")
def recompute_pano_groups(req: RecomputePanoGroupsRequest):
    raw = [g.model_dump() for g in req.groups]
    groups = group_edit_service.recompute_pano_groups(raw)
    return {"groups": groups, "n_groups": len(groups)}


@router.post("/groups/recompute/entry")
def recompute_entry_groups(req: RecomputeEntryGroupsRequest):
    raw = [g.model_dump() for g in req.groups]
    groups = group_edit_service.recompute_entry_groups(raw)
    return {"groups": groups, "n_groups": len(groups)}


@router.get("/series-list")
def series_list():
    return {"series": pano_series_service.list_series()}


@pano_router.get("/series-list")
def pano_series_list():
    return series_list()


@router.post("/pano/search")
async def pano_search(req: PanoSearchRequest):
    result = pano_series_service.search_articles(req.series_no, req.source_group_no)
    grouped = await pano_series_service.group_articles_by_theme(result.get("articles") or [])
    result["groups"] = grouped["groups"]
    result["n_groups"] = grouped["n_groups"]
    result["grouping_usage"] = grouped.get("grouping_usage")
    return result


@pano_router.post("/articles")
async def pano_articles(req: PanoSearchRequest):
    return await pano_search(req)


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


@entry_router.post("/search")
async def entry_search_alias(req: EntrySearchRequest):
    return await entry_search(req)


async def _generate_json(prompt: str) -> dict:
    try:
        return await llm_client.call_claude("", prompt)
    except Exception as e:
        logger.exception("[progress_outline] 纲目生成失败 prompt_chars=%s", len(prompt))
        raise HTTPException(
            status_code=502,
            detail=f"Claude 调用失败（已自动重试）：{e}",
        ) from e


def _merge_usage(usages: list[dict | None]) -> dict | None:
    valid = [u for u in usages if u]
    if not valid:
        return None
    in_tok = sum(int(u.get("input_tokens") or 0) for u in valid)
    out_tok = sum(int(u.get("output_tokens") or 0) for u in valid)
    cost = sum(float(u.get("cost_usd") or 0) for u in valid)
    model = valid[0].get("model") or llm_client.CLAUDE_MODEL
    return {
        "model": model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": round(cost, 6),
    }


async def _generate_one_segment(
    g: GroupSegmentInput,
    *,
    term: str = "",
    entry: bool = False,
) -> dict:
    content = (g.plain_text or "").strip()
    title = (g.title or "").strip()
    burden = (g.burden or "").strip()
    if not content:
        return {"title": title, "burden": burden, "text": "", "usage": None}
    if g.record_count == 1:
        return {"title": title, "burden": burden, "text": content, "usage": None}
    if entry:
        prompt = build_entry_segment_prompt(
            term=term or "（未命名词条）",
            group_title=g.title,
            group_burden=g.burden,
            content=content,
        )
    else:
        prompt = build_pano_segment_prompt(
            group_title=g.title,
            group_burden=g.burden,
            content=content,
        )
    result = await _generate_json(prompt)
    return {
        "title": title,
        "burden": burden,
        "text": result.get("text") or "",
        "usage": result.get("usage"),
    }


def _usage_response(usage: dict | None) -> dict:
    return {"segment_usage": usage, "usage": usage}


async def _generate_segment_by_groups(
    req: GenerateRequest,
    *,
    term: str = "",
    entry: bool = False,
) -> dict:
    groups = [g for g in (req.groups or []) if (g.plain_text or "").strip()]
    if not groups:
        return _usage_response(None) | {"text": "", "group_results": []}
    results = await asyncio.gather(
        *(_generate_one_segment(g, term=term, entry=entry) for g in groups)
    )
    group_results = [r for r in results if (r.get("text") or "").strip()]
    usage = _merge_usage([r.get("usage") for r in results])
    return _usage_response(usage) | {
        "group_results": group_results,
        "text": "",
    }


@router.post("/pano/generate/segment")
async def pano_generate_segment(req: GenerateRequest):
    if req.groups:
        return await _generate_segment_by_groups(req, entry=False)
    if not (req.content or "").strip():
        raise HTTPException(status_code=400, detail="content 或 groups 不能为空")
    prompt = build_pano_segment_prompt(
        group_title="（根据以下职事材料生成纲目）",
        group_burden="",
        content=req.content,
    )
    result = await _generate_json(prompt)
    text = result.get("text") or ""
    return _usage_response(result.get("usage")) | {
        "text": text,
        "group_results": [
            {
                "title": "（根据以下职事材料生成纲目）",
                "burden": "",
                "text": text,
                "usage": result.get("usage"),
            }
        ]
        if text
        else [],
    }


@router.post("/entry/generate/segment")
async def entry_generate_segment(req: GenerateRequest):
    if req.groups:
        return await _generate_segment_by_groups(
            req,
            term=req.term or "（未命名词条）",
            entry=True,
        )
    if not (req.content or "").strip():
        raise HTTPException(status_code=400, detail="content 或 groups 不能为空")
    prompt = build_entry_segment_prompt(
        term=req.term or "（未命名词条）",
        group_title="（根据以下职事材料生成纲目）",
        group_burden="",
        content=req.content,
    )
    result = await _generate_json(prompt)
    text = result.get("text") or ""
    return _usage_response(result.get("usage")) | {
        "text": text,
        "group_results": [
            {
                "title": "（根据以下职事材料生成纲目）",
                "burden": "",
                "text": text,
                "usage": result.get("usage"),
            }
        ]
        if text
        else [],
    }


@router.post("/format_download")
async def format_download(req: FormatRequest):
    try:
        docx_bytes, filename = format_service.format_zh_docx(
            req.text, header_title=req.title or None
        )
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


@router.post("/format_download_batch")
async def format_download_batch(req: FormatBatchRequest):
    try:
        zip_bytes, zip_name = format_service.format_zh_docx_zip(
            [item.model_dump() for item in req.items]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    ascii_name = zip_name.encode("ascii", "ignore").decode() or "segments.zip"
    disposition = (
        f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(zip_name)}'
    )
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": disposition},
    )


class MinisterializeSegmentArticle(BaseModel):
    title: str = ""
    text: str = ""


class MinisterializeSegmentRequest(BaseModel):
    group_results: list[MinisterializeSegmentArticle] = Field(default_factory=list)
    series_title: str = ""
    stage_no: int = Field(ge=1, le=5)
    outline_sources: list[dict] = Field(default_factory=list)
    is_pano: bool = False
    series_no: int | None = None
    active_stage_no: int | None = None
    global_article_offset: int | None = None


@router.post("/ministerialize_segment")
async def ministerialize_segment(req: MinisterializeSegmentRequest):
    valid = [g for g in req.group_results if (g.text or "").strip()]
    if not valid:
        raise HTTPException(status_code=400, detail="没有有效的纲目文本，无法职事化")
    try:
        result = await ministerialize_service.ministerialize_segment(
            group_results=[g.model_dump() for g in valid],
            series_title=req.series_title or "",
            stage_no=req.stage_no,
            outline_sources=req.outline_sources or [],
            is_pano=req.is_pano,
            series_no=req.series_no,
            active_stage_no=req.active_stage_no,
            global_article_offset=req.global_article_offset,
        )
        return result
    except Exception as e:
        logger.exception("[progress] ministerialize_segment 失败")
        raise HTTPException(status_code=500, detail=str(e)) from e


class MinisterializeDownloadLine(BaseModel):
    text: str = ""
    footnote_no: int | None = None


class MinisterializeDownloadRequest(BaseModel):
    header_lines: list[str] = Field(default_factory=list)
    outline_lines: list[MinisterializeDownloadLine] = Field(default_factory=list)
    footnotes: list[dict] = Field(default_factory=list)
    article_title: str = ""


@router.post("/ministerialize_download")
async def ministerialize_download(req: MinisterializeDownloadRequest):
    try:
        docx_bytes, filename = format_service.format_ministerialize_docx(
            header_lines=req.header_lines,
            outline_lines=[l.model_dump() for l in req.outline_lines],
            footnotes=req.footnotes,
            article_title=req.article_title,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    ascii_name = filename.encode("ascii", "ignore").decode() or "ministerialize.docx"
    disposition = (
        f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
    )
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": disposition},
    )


@router.post("/parse_docx_text")
async def parse_docx_text(file: UploadFile = File(...)):
    """
    解析上传的 DOCX 文件，提取纯文字纲目内容。
    跳过页眉行（读经行之前的 00篇题 样式段落），
    从读经行开始提取。
    """
    try:
        from docx import Document

        contents = await file.read()
        doc = Document(io.BytesIO(contents))
        lines = []
        found_reading = False
        reading_markers = ("读经：", "讀經：", "读经∶", "讀經∶")
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            if not found_reading:
                if any(text.startswith(m) for m in reading_markers):
                    found_reading = True
                    lines.append(para.text)
                continue
            lines.append(para.text)
        return {"text": "\n".join(lines), "found_reading": found_reading}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DOCX 解析失败：{e}") from e
