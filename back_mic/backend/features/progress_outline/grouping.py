# -*- coding: utf-8 -*-
"""检索结果主题分组（进展篇目 / 新增词条共用）。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from features.progress_outline import llm_client

logger = logging.getLogger(__name__)


def compute_n_groups(count: int) -> int:
    return max(1, round(count * 1.5 / 10))


def _default_record_title(record: dict[str, Any], id_key: str) -> str:
    if id_key == "id":
        return record.get("title") or f"第{record.get('article_no')}篇"
    return (
        record.get("source_zh")
        or record.get("book_title")
        or record.get("chunk_id")
        or ""
    )


def _group_dict(
    *,
    title: str,
    burden: str,
    record_ids: list[str],
    records: list[dict[str, Any]],
    plain_text: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "burden": burden,
        "record_ids": record_ids,
        "records": records,
        "plain_text": plain_text,
        "record_count": len(records),
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("LLM 返回为空")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("未找到 JSON 对象")
    return json.loads(raw[start : end + 1])


def _ids_complete_and_unique(groups: list[dict[str, Any]], all_ids: set[str]) -> bool:
    seen: set[str] = set()
    for g in groups:
        for rid in g.get("record_ids") or []:
            sid = str(rid).strip()
            if not sid or sid in seen or sid not in all_ids:
                return False
            seen.add(sid)
    return seen == all_ids


async def group_records_by_theme(
    records: list[dict[str, Any]],
    *,
    id_key: str,
    record_list: str,
    prompt_template: str,
    to_plain_text: Callable[[list[dict[str, Any]]], str],
    fallback_title: str = "全部",
) -> dict[str, Any]:
    """按主题分组；整次仅 1 条时不调 LLM；失败时全部归入一组。"""
    n = len(records)
    if n == 0:
        return {"groups": [], "n_groups": 0, "usage": None}

    by_id = {str(r[id_key]): r for r in records if r.get(id_key)}
    all_ids = set(by_id.keys())

    if n == 1:
        record = records[0]
        rid = str(record.get(id_key) or "")
        return {
            "groups": [
                _group_dict(
                    title=_default_record_title(record, id_key),
                    burden="",
                    record_ids=[rid] if rid else [],
                    records=records,
                    plain_text=to_plain_text(records),
                )
            ],
            "n_groups": 1,
            "usage": None,
        }

    n_groups = compute_n_groups(n)

    def _single_group(reason: str = "") -> dict[str, Any]:
        if reason:
            logger.warning("[progress_outline] 分组 fallback: %s", reason)
        return {
            "groups": [
                _group_dict(
                    title=fallback_title,
                    burden="",
                    record_ids=list(by_id.keys()),
                    records=list(records),
                    plain_text=to_plain_text(records),
                )
            ],
            "n_groups": 1,
            "usage": None,
        }

    prompt = prompt_template.format(
        total=n,
        n_groups=n_groups,
        record_list=record_list,
    )

    try:
        llm_result = await llm_client.call_sync(prompt, max_tokens=2048)
        raw_text = llm_result.get("text") or ""
        usage = llm_result.get("usage")
        parsed = _extract_json_object(raw_text)
        raw_groups = parsed.get("groups") or []
        if not isinstance(raw_groups, list) or not raw_groups:
            return _single_group("groups 为空")

        built: list[dict[str, Any]] = []
        for g in raw_groups:
            if not isinstance(g, dict):
                return _single_group("group 项非对象")
            ids = [str(x).strip() for x in (g.get("record_ids") or []) if str(x).strip()]
            group_records = [by_id[i] for i in ids if i in by_id]
            built.append(
                _group_dict(
                    title=(g.get("title") or "").strip() or fallback_title,
                    burden=(g.get("burden") or "").strip(),
                    record_ids=ids,
                    records=group_records,
                    plain_text=to_plain_text(group_records),
                )
            )

        if not _ids_complete_and_unique(built, all_ids):
            return _single_group("record_ids 遗漏或重复")

        return {"groups": built, "n_groups": n_groups, "usage": usage}
    except Exception as e:
        logger.warning("[progress_outline] 主题分组失败: %s", e)
        return _single_group(str(e))


def format_pano_group_response(
    grouped: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in grouped.get("groups") or []:
        out.append({
            "title": g.get("title") or "",
            "burden": g.get("burden") or "",
            "record_ids": g.get("record_ids") or [],
            "record_count": g.get("record_count") or len(g.get("records") or []),
            "articles": g.get("records") or [],
            "plain_text": g.get("plain_text") or "",
        })
    return out


def format_entry_group_response(
    grouped: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in grouped.get("groups") or []:
        out.append({
            "title": g.get("title") or "",
            "burden": g.get("burden") or "",
            "record_ids": g.get("record_ids") or [],
            "record_count": g.get("record_count") or len(g.get("records") or []),
            "items": g.get("records") or [],
            "plain_text": g.get("plain_text") or "",
        })
    return out
