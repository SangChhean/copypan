# -*- coding: utf-8 -*-
"""节期纲目制作：Redis 序号与 pan_reading 数据接口。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from user.token import test_token
from ai_search.ai_service import redis_client
from es_config import es

feast_router = APIRouter(prefix="/api/feast", tags=["feast"])
logger = logging.getLogger("feast_outline_maker")

FEAST_SEQUENCE_KEY = "feast:sequence"
PAN_READING_INDEX = "pan_reading"


class FeastSequenceBody(BaseModel):
    """节期纲目序号：bookname sn / title sn。"""

    bsn: int = Field(..., ge=0, description="bookname 序号")
    csn: int = Field(..., ge=0, description="title 序号")


def _feast_redis():
    return redis_client


def _feast_sequence_default() -> dict:
    return {"bsn": 0, "csn": 0, "updated_at": ""}


def _feast_sequence_load() -> dict:
    client = _feast_redis()
    if not client:
        return _feast_sequence_default()
    try:
        raw = client.get(FEAST_SEQUENCE_KEY)
        if not raw:
            return _feast_sequence_default()
        data = json.loads(raw)
        return {
            "bsn": int(data.get("bsn", 0)),
            "csn": int(data.get("csn", 0)),
            "updated_at": str(data.get("updated_at") or ""),
        }
    except Exception as e:
        logger.warning("[feast_sequence] load failed: %s", e)
        return _feast_sequence_default()


def _feast_sequence_save(bsn: int, csn: int) -> dict:
    payload = {
        "bsn": bsn,
        "csn": csn,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client = _feast_redis()
    if not client:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    try:
        client.set(FEAST_SEQUENCE_KEY, json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        logger.exception("[feast_sequence] save failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return payload


@feast_router.get("/sequence", dependencies=[Depends(test_token)])
async def get_feast_sequence():
    """读取节期纲目 bookname/title 序号。"""
    return _feast_sequence_load()


@feast_router.post("/sequence", dependencies=[Depends(test_token)])
async def set_feast_sequence(req: FeastSequenceBody):
    """写入节期纲目 bookname/title 序号。"""
    return _feast_sequence_save(req.bsn, req.csn)


def _parse_pan_reading_ids(ids: str) -> List[str]:
    return [part.strip() for part in (ids or "").split(",") if part.strip()]


def _fetch_pan_reading_by_ids(ids: str) -> dict:
    from elasticsearch import NotFoundError

    id_list = _parse_pan_reading_ids(ids)
    result: dict = {}
    try:
        for doc_id in id_list:
            try:
                res = es.get(index=PAN_READING_INDEX, id=doc_id)
                result[doc_id] = res.get("_source")
            except NotFoundError:
                result[doc_id] = None
    except Exception as e:
        logger.exception("[feast_pan_reading] ES fetch failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return result


@feast_router.get("/pan-reading", dependencies=[Depends(test_token)])
async def get_feast_pan_reading(
    ids: str = Query(..., description="逗号分隔的 pan_reading 文档 id"),
):
    """批量读取 pan_reading 文档；不存在的 id 对应值为 null。"""
    return _fetch_pan_reading_by_ids(ids)
