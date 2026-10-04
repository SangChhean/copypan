# -*- coding: utf-8 -*-
"""SC 引用统计：从加词条定义版输出 + 最终名单现算。

支持两种格式：
- outline（旧）：【职事界定】/【真理脉络】里的「参考材料」标记
- direct（直写版）：【用到的参考材料】名单 + 【负担说明】正文子串
"""
from __future__ import annotations

import re
from typing import Any

TIER_ORDER = ("最内在", "内在", "外在")
STATUS_RANK = {"uncited": 0, "defs_only": 1, "in_outline": 2}
STATUS_LABEL = {
    "in_outline": "入脉络",
    "defs_only": "仅界定",
    "uncited": "未引用",
    "listed": "已列出",
    "in_text": "文中出现",
    "both": "两者都有",
    "unused": "未使用",
}

_SECTION_TAGS = ("【职事界定】", "【真理脉络】", "【负担说明】", "【用到的参考材料】")
_MATERIALS_TAG = "【用到的参考材料】"
_REF_MARK = re.compile(r"参考材料\s*[·：:]")
_STOP_CHARS = set("；;｜）)\n\r")
_SPLIT = re.compile(r"[、，,和]")
_LINE_NO = re.compile(r"^(\d+)\.")
_QUOTES = "「」『』\"'"


def _norm_terms(final_terms: list) -> list[dict[str, Any]]:
    out = []
    for item in final_terms or []:
        if isinstance(item, str):
            out.append({"name": item, "tier": "", "has_3a": True})
        else:
            out.append(
                {
                    "name": str(item.get("name") or "").strip(),
                    "tier": str(item.get("tier") or item.get("tier_actual") or "").strip(),
                    "has_3a": bool(item.get("has_3a", True)),
                }
            )
    return [x for x in out if x["name"]]


def split_sections(text: str) -> dict[str, str]:
    """按标题切段；找不到的为空。"""
    raw = text or ""
    positions: list[tuple[int, str]] = []
    for tag in _SECTION_TAGS:
        idx = raw.find(tag)
        if idx >= 0:
            positions.append((idx, tag))
    positions.sort()
    sections = {tag: "" for tag in _SECTION_TAGS}
    for i, (start, tag) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(raw)
        body = raw[start + len(tag) : end]
        sections[tag] = body
    return sections


def _parse_line_no(line: str) -> int | None:
    m = _LINE_NO.match(line.lstrip())
    if not m:
        return None
    return int(m.group(1))


def _clean_name(piece: str) -> str:
    s = piece.strip().strip(_QUOTES).strip()
    return s


def _split_name_list(chunk: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for part in _SPLIT.split(chunk):
        name = _clean_name(part)
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def extract_ref_hits(section_text: str) -> list[tuple[str, int | None]]:
    """返回 [(name, line_no), ...]；同一行多个「参考材料」都匹配。"""
    hits: list[tuple[str, int | None]] = []
    for line in (section_text or "").splitlines():
        line_no = _parse_line_no(line)
        for m in _REF_MARK.finditer(line):
            start = m.end()
            end = start
            while end < len(line) and line[end] not in _STOP_CHARS:
                end += 1
            chunk = line[start:end]
            for name in _split_name_list(chunk):
                hits.append((name, line_no))
    return hits


def _build_groups(
    terms: list[dict[str, Any]],
    skipped: list[str],
    merged: list[str],
    content_3a: dict[str, str | None] | None,
) -> list[list[dict[str, Any]]]:
    """有 3a 的词条按定义内容分组；同内容合并对只占一组。"""
    skipped_set = set(skipped or [])
    merged_set = set(merged or [])
    candidates: list[dict[str, Any]] = []
    for t in terms:
        name = t["name"]
        if name in skipped_set:
            continue
        if t.get("has_3a") is False:
            continue
        if content_3a is not None:
            c = content_3a.get(name)
            if c is None or not str(c).strip():
                continue
        candidates.append(t)

    if content_3a is None:
        groups: list[list[dict[str, Any]]] = []
        last_primary: list[dict[str, Any]] | None = None
        for t in candidates:
            name = t["name"]
            if name in merged_set and last_primary is not None:
                last_primary.append(t)
            else:
                g = [t]
                groups.append(g)
                last_primary = g
        return groups

    by_content: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for t in candidates:
        c = str(content_3a.get(t["name"]) or "")
        if c not in by_content:
            by_content[c] = []
            order.append(c)
        by_content[c].append(t)
    return [by_content[c] for c in order]


def _max_status(a: str, b: str) -> str:
    return a if STATUS_RANK[a] >= STATUS_RANK[b] else b


def _name_in_text(name: str, body: str) -> bool:
    return bool(name) and name in (body or "")


def _build_groups_direct(
    terms: list[dict[str, Any]],
    skipped: list[str],
    merged: list[str],
    content_3a: dict[str, str | None] | None,
) -> list[list[dict[str, Any]]]:
    """直写版基数：内在/最内在仍按 3a 合并；外在不论有无 3a 均各占一组。"""
    skipped_set = set(skipped or [])
    inner_terms = [t for t in terms if (t.get("tier") or "") != "外在"]
    outer_terms = [t for t in terms if (t.get("tier") or "") == "外在" and t["name"] not in skipped_set]
    groups = _build_groups(inner_terms, skipped, merged, content_3a)
    for t in outer_terms:
        groups.append([t])
    return groups


def _compute_direct(
    *,
    ref_output: str,
    terms: list[dict[str, Any]],
    skipped: list[str],
    merged: list[str],
    content_3a: dict[str, str | None] | None,
) -> dict[str, Any]:
    sections = split_sections(ref_output)
    materials_raw = sections.get(_MATERIALS_TAG) or ""
    listed_names = _split_name_list(materials_raw)
    listed_set = set(listed_names)
    burden = sections.get("【负担说明】") or ""

    groups = _build_groups_direct(terms, skipped, merged, content_3a)
    sent_names = {m["name"] for g in groups for m in g}

    by_tier = {
        tier: {"total": 0, "listed": 0, "in_text": 0, "both": 0, "unused": 0}
        for tier in TIER_ORDER
    }
    term_rows: list[dict[str, Any]] = []

    for group in groups:
        in_list = any(m["name"] in listed_set for m in group)
        in_body = any(_name_in_text(m["name"], burden) for m in group)
        if in_list and in_body:
            status = "both"
        elif in_list:
            status = "listed"
        elif in_body:
            status = "in_text"
        else:
            status = "unused"

        primary = group[0]
        tier = primary["tier"] if primary["tier"] in by_tier else "外在"
        by_tier[tier]["total"] += 1
        by_tier[tier][status] += 1

        for member in group:
            term_rows.append(
                {
                    "name": member["name"],
                    "tier": member["tier"] or tier,
                    "status": status,
                    "status_label": STATUS_LABEL[status],
                    "def_items": [],
                    "outline_items": [],
                }
            )

    unknown: list[dict[str, Any]] = []
    for name in sorted(listed_set):
        if name in sent_names:
            continue
        unknown.append({"name": name, "def_items": [], "outline_items": []})

    return {
        "format": "direct",
        "sent_total": len(groups),
        "by_tier": by_tier,
        "terms": term_rows,
        "unknown_cited": unknown,
        "note": None,
        "format_note": "直写版：不区分入脉络与仅界定",
    }


def _compute_outline(
    *,
    ref_output: str,
    terms: list[dict[str, Any]],
    skipped: list[str],
    merged: list[str],
    content_3a: dict[str, str | None] | None,
) -> dict[str, Any]:
    empty_by_tier = {
        tier: {"total": 0, "in_outline": 0, "defs_only": 0, "uncited": 0} for tier in TIER_ORDER
    }
    sections = split_sections(ref_output)
    defs_hits = extract_ref_hits(sections["【职事界定】"])
    outline_hits = extract_ref_hits(sections["【真理脉络】"])

    if not defs_hits and not outline_hits:
        groups = _build_groups(terms, skipped, merged, content_3a)
        return {
            "format": "outline",
            "sent_total": len(groups),
            "by_tier": empty_by_tier,
            "terms": [],
            "unknown_cited": [],
            "note": "输出中没有参考材料标记，无法统计",
        }

    def_map: dict[str, list[int]] = {}
    outline_map: dict[str, list[int]] = {}
    for name, no in defs_hits:
        def_map.setdefault(name, [])
        if no is not None and no not in def_map[name]:
            def_map[name].append(no)
    for name, no in outline_hits:
        outline_map.setdefault(name, [])
        if no is not None and no not in outline_map[name]:
            outline_map[name].append(no)

    groups = _build_groups(terms, skipped, merged, content_3a)
    sent_names = {m["name"] for g in groups for m in g}

    term_rows: list[dict[str, Any]] = []
    by_tier = {
        tier: {"total": 0, "in_outline": 0, "defs_only": 0, "uncited": 0} for tier in TIER_ORDER
    }

    for group in groups:
        status = "uncited"
        def_items: list[int] = []
        outline_items: list[int] = []
        for member in group:
            name = member["name"]
            if name in outline_map:
                status = _max_status(status, "in_outline")
                for n in outline_map[name]:
                    if n not in outline_items:
                        outline_items.append(n)
            if name in def_map:
                if status != "in_outline":
                    status = _max_status(status, "defs_only")
                for n in def_map[name]:
                    if n not in def_items:
                        def_items.append(n)
        def_items.sort()
        outline_items.sort()

        primary = group[0]
        tier = primary["tier"] if primary["tier"] in by_tier else "外在"
        by_tier[tier]["total"] += 1
        by_tier[tier][status] += 1

        for member in group:
            term_rows.append(
                {
                    "name": member["name"],
                    "tier": member["tier"] or tier,
                    "status": status,
                    "status_label": STATUS_LABEL[status],
                    "def_items": list(def_items),
                    "outline_items": list(outline_items),
                }
            )

    unknown: list[dict[str, Any]] = []
    all_cited = set(def_map) | set(outline_map)
    for name in sorted(all_cited):
        if name in sent_names:
            continue
        unknown.append(
            {
                "name": name,
                "def_items": sorted(def_map.get(name) or []),
                "outline_items": sorted(outline_map.get(name) or []),
            }
        )

    return {
        "format": "outline",
        "sent_total": len(groups),
        "by_tier": by_tier,
        "terms": term_rows,
        "unknown_cited": unknown,
        "note": None,
    }


def compute_citation_stats(
    *,
    ref_output: str | None,
    final_terms: list,
    skipped: list[str] | None = None,
    merged: list[str] | None = None,
    content_3a: dict[str, str | None] | None = None,
    tier_of: dict[str, str] | None = None,
) -> dict[str, Any]:
    skipped = list(skipped or [])
    merged = list(merged or [])
    terms = _norm_terms(final_terms)
    for t in terms:
        if not t["tier"] and tier_of:
            t["tier"] = tier_of.get(t["name"]) or ""

    empty_outline = {
        tier: {"total": 0, "in_outline": 0, "defs_only": 0, "uncited": 0} for tier in TIER_ORDER
    }

    if not (ref_output or "").strip():
        return {
            "format": "outline",
            "sent_total": 0,
            "by_tier": empty_outline,
            "terms": [],
            "unknown_cited": [],
            "note": "没有加词条定义版输出，无法统计",
        }

    raw = ref_output or ""
    if _MATERIALS_TAG in raw:
        return _compute_direct(
            ref_output=raw,
            terms=terms,
            skipped=skipped,
            merged=merged,
            content_3a=content_3a,
        )
    return _compute_outline(
        ref_output=raw,
        terms=terms,
        skipped=skipped,
        merged=merged,
        content_3a=content_3a,
    )
