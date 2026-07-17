# -*- coding: utf-8 -*-
"""CN ministry search over the imported offline_* Elasticsearch indexes."""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache

from elasticsearch import Elasticsearch, NotFoundError
from fastapi import APIRouter, Depends, Form, HTTPException, Request

from back_cn.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cn/es_search", tags=["cn-es-search"])

DEFAULT_ARGS = "a-a-a-1-10"
VALID_CAT1 = frozenset("abc") | frozenset("1234567")
VALID_CAT2 = frozenset("abcdefghijklm")
VALID_CAT3 = frozenset("abc")

BASE_INDICES = {
    "1": "",
    "2": "life",
    "3": "cwwn",
    "4": "cwwl",
    "5": "others",
    "6": "hymn",
    "7": "feasts",
}

CAT_A = ["bib", "foo", "2", "3", "4", "5"]
CAT_B = CAT_A + ["6", "7"]
CAT_C = CAT_B
CATS = {"a": CAT_A, "b": CAT_B, "c": CAT_C}


def _require_user(request: Request) -> dict:
    return get_current_user(request)


def _es_url() -> str:
    host = os.getenv("ES_HOST", "http://127.0.0.1").strip() or "http://127.0.0.1"
    port = (os.getenv("ES_PORT", "9201") or "9201").strip()
    if host.startswith(("http://", "https://")):
        base = host.rstrip("/")
    else:
        base = f"http://{host.strip('/')}"
    if re.search(r":\d+$", base):
        return base
    return f"{base}:{port}"


@lru_cache(maxsize=1)
def _es_client() -> Elasticsearch:
    username = os.getenv("ES_USERNAME", "elastic").strip() or "elastic"
    password = os.getenv("ES_PASSWORD", "").strip()
    if not password:
        logger.warning("[cn-es-search] ES_PASSWORD is not configured")
    return Elasticsearch(_es_url(), basic_auth=(username, password) if password else None)


def _offline_index(index: str) -> str:
    return f"offline_{index}"


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fa5]", text or ""))


def _get_appendix(cat2: str) -> str:
    appendices = {
        "a": "",
        "b": "_booknames",
        "c": "_booknames",
        "d": "_titles",
        "e": "_headings",
        "f": "_ot1",
        "g": "_msg",
        "h": "",
        "i": "bib",
        "j": "foo",
        "k": "_booknames",
        "l": "_outlines",
        "m": "",
    }
    return appendices[cat2]


def _get_base_indices(cat1: str, cat2: str) -> list[str]:
    indices: list[str] = []

    if cat1 == "1":
        if cat2 not in "ij":
            return indices
    elif cat1 == "6":
        if cat2 != "h":
            return indices
    elif cat2 in "ijh":
        return indices

    if cat1 in "abc":
        for item in CATS[cat1]:
            if len(item) == 1:
                indices.extend(_get_base_indices(item, cat2))
            else:
                indices.append(item)
        if cat2 != "a":
            if "bib" in indices:
                indices.remove("bib")
            if "foo" in indices:
                indices.remove("foo")
    else:
        index = BASE_INDICES[cat1] + _get_appendix(cat2)
        indices.append(index)

    return indices


def _parse_args(args: str):
    raw = (args or "").strip()
    parts = raw.split("-") if raw else []
    default_parts = DEFAULT_ARGS.split("-")
    if len(parts) != 5:
        return (
            default_parts[0],
            default_parts[1],
            default_parts[2],
            int(default_parts[3]),
            int(default_parts[4]),
        )

    cat1, cat2, cat3, page_raw, page_size_raw = parts
    if cat1 not in VALID_CAT1:
        cat1 = default_parts[0]
    if cat2 not in VALID_CAT2:
        cat2 = default_parts[1]
    if cat3 not in VALID_CAT3:
        cat3 = default_parts[2]

    try:
        page = max(1, int(page_raw) if page_raw else 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(int(page_size_raw) if page_size_raw else 10, 100))
    except (TypeError, ValueError):
        page_size = 10

    return cat1, cat2, cat3, page, page_size


def _get_match_info(cat3: str, input_text: str):
    operator = "or"
    if _contains_chinese(input_text):
        field = "zh"
        if cat3 == "c":
            field = "text"
        elif cat3 == "b":
            operator = "and"
    else:
        field = "en"
        if cat3 in "bc":
            operator = "and"
    return field, operator


def _split_keywords(input_text: str) -> list[str]:
    return [item for item in re.split(r"[\n\t 　]+", input_text) if item]


def _escape_wildcard(value: str) -> str:
    return value.replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")


def _get_matches(field: str, operator: str, input_text: str) -> list[dict]:
    query = (input_text or "").strip()
    should: list[dict] = []

    if field == "text":
        keywords = _split_keywords(query)
        if keywords:
            should.append({"bool": {"must": [{"match_phrase": {"text": kw}} for kw in keywords]}})
        else:
            should.append({"match": {"text": {"query": query, "operator": "or"}}})
    else:
        should.append({"match": {field: {"query": query, "operator": operator}}})

    if field != "text":
        should.append({"match": {"text": {"query": query, "operator": operator}}})

    if query:
        should.append({"wildcard": {"title": f"*{_escape_wildcard(query)}*"}})

    return should


def _get_search_info(args: str, input_text: str):
    query = (input_text or "").strip()
    if len(query) > 240:
        query = query[:240]
    cat1, cat2, cat3, page, page_size = _parse_args(args)
    indices = [_offline_index(index) for index in _get_base_indices(cat1, cat2)]
    field, operator = _get_match_info(cat3, query)
    matches = _get_matches(field, operator, query)
    return indices, matches, field, page, page_size


def _page_offset(page: int, page_size: int) -> int:
    return (int(page) - 1) * int(page_size)


def _get_total(total_field) -> int:
    if isinstance(total_field, dict):
        return int(total_field.get("value", 0) or 0)
    return int(total_field) if total_field is not None else 0


def _highlight_text(hit: dict, preferred_field: str) -> str:
    highlight = hit.get("highlight") or {}
    for key in (preferred_field, "zh", "text", "en", "title"):
        values = highlight.get(key)
        if values:
            return values[0]
    return ""


def _format_hit(hit: dict, field: str) -> dict:
    source = hit.get("_source") or {}
    highlight = _highlight_text(hit, field)
    zh = source.get("zh") or ""
    en = source.get("en") or ""
    return {
        "id": hit.get("_id"),
        "up": highlight or (zh if field == "en" else en),
        "down": zh if field == "en" else en,
        "title": source.get("title") or "",
        "tags": source.get("tags") or [],
        "source": source.get("source") or [],
    }


def _format_search_response(response, field: str) -> dict:
    hits_root = response.get("hits", {})
    hits = hits_root.get("hits", [])
    rows = []
    for hit in hits:
        try:
            rows.append(_format_hit(hit, field))
        except (KeyError, TypeError, IndexError):
            continue
    return {"total": _get_total(hits_root.get("total", 0)), "msg": rows}


@router.post("/search")
def search_ministry(
    input: str = Form(""),
    args: str = Form(DEFAULT_ARGS),
    _user: dict = Depends(_require_user),
):
    indices, matches, field, page, page_size = _get_search_info(args, input)
    if not indices or not (input or "").strip():
        return {"total": 0, "msg": []}

    body = {
        "size": page_size,
        "from": _page_offset(page, page_size),
        "track_total_hits": True,
        "query": {
            "bool": {
                "should": matches,
                "minimum_should_match": 1,
            }
        },
        "highlight": {
            "number_of_fragments": 0,
            "fields": {"zh": {}, "text": {}, "en": {}, "title": {}},
        },
    }
    try:
        response = _es_client().search(index=indices, body=body, ignore_unavailable=True)
    except Exception as exc:
        logger.exception("[cn-es-search] search failed")
        raise HTTPException(status_code=502, detail="搜索服务暂时不可用") from exc

    return _format_search_response(response, field)


@router.post("/reading")
def read_ministry_source(
    refid: str = Form(...),
    _user: dict = Depends(_require_user),
):
    try:
        return dict(_es_client().get(index="offline_pan_reading", id=refid))
    except NotFoundError:
        raise HTTPException(status_code=404, detail="原文不存在")
    except Exception as exc:
        logger.exception("[cn-es-search] reading failed")
        raise HTTPException(status_code=502, detail="阅读服务暂时不可用") from exc
