# -*- coding: utf-8 -*-
"""经文查询 SSE 路由（JWT 与 qa_router 一致：依赖 _require_user）。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from back_qa.qa.auth_router import _require_user
from back_qa.qa.auth import check_and_increment_daily_usage
from back_qa.qa import bible_service
from back_qa.qa.bible_ref_parser import parse_bible_ref

router = APIRouter(tags=["bible"])

DAILY_LIMIT = int(os.getenv("QA_DAILY_LIMIT", "30"))
_BIBLE_DATA_DIR = Path(__file__).resolve().parents[1] / "bible_data"


class BibleQueryRequest(BaseModel):
    book: int | None = None
    chapter: int | None = None
    verse: int | None = None
    question: str = ""
    history: list = Field(default_factory=list)


def _sse_line(event: str, data) -> dict:
    """与 qa_router `/stream` 一致：仅使用 `data` 字段，内容为 JSON 字符串。"""
    return {"data": json.dumps({"event": event, "data": data}, ensure_ascii=False)}


def _ensure_bible_loaded() -> None:
    if not bible_service._bible:
        bible_service.load_bible_data(str(_BIBLE_DATA_DIR))


@router.post("/bible/query")
async def bible_query(req: BibleQueryRequest, request: Request):
    """SSE：先推送经文 JSON，再经文问答流水线（token / done / error）。"""
    username = _require_user(request)
    usage = check_and_increment_daily_usage(username)
    if not usage["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"今日问答次数已达上限（{usage['limit']}次），请明天再来",
        )

    async def event_generator():
        try:
            _ensure_bible_loaded()
            if req.book is not None and req.chapter is not None and req.verse is not None:
                verse = bible_service.get_verse(req.book, req.chapter, req.verse)
                verse_sse = verse
            else:
                parsed = parse_bible_ref(req.question)
                if parsed is None:
                    yield _sse_line(
                        "error",
                        "无法从问题中识别经文，请使用「腓一1」或「Phil 1:1」等格式",
                    )
                    return
                t = parsed.get("type", "verse")
                if t == "verse":
                    verse = bible_service.get_verse(
                        parsed["book"], parsed["chapter"], parsed["verse"]
                    )
                    verse_sse = verse
                elif t == "range":
                    rows = bible_service.get_verse_range(
                        parsed["book"],
                        parsed["chapter"],
                        parsed["verse_start"],
                        parsed["verse_end"],
                    )
                    verse = bible_service.composite_verses(rows)
                    verse_sse = (
                        {"verses": rows, "query_type": "range"} if rows else None
                    )
                elif t == "chapter":
                    rows = bible_service.get_verse_range(
                        parsed["book"], parsed["chapter"], None, None
                    )
                    verse = bible_service.composite_verses(rows)
                    verse_sse = (
                        {"verses": rows, "query_type": "chapter"} if rows else None
                    )
                else:
                    verse = None
                    verse_sse = None
            if verse is None:
                yield _sse_line("error", "找不到指定经文，请检查卷章节是否有误")
                return
            yield _sse_line("verse_data", verse_sse)
            async for ev in bible_service.run_bible_pipeline(
                verse,
                (req.question or "").strip(),
                req.history or [],
            ):
                yield _sse_line(ev["event"], ev["data"])
        except Exception as e:
            yield _sse_line("error", str(e))

    return EventSourceResponse(event_generator())
