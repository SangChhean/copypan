# -*- coding: utf-8 -*-
"""第 8 步后处理：[n] → citations；引文核对 verify_quotes。

引文核对：取「」内文字，与送入段落都去掉空白和标点、统一全半角，检查是否为某一段的连续子串；
带「……」的按省略号拆开分别核对，且要求各部分在同一段内（按顺序）连续出现；
核对不过的标 unverified 并在正文该处加小标记【暂定】；不自动重生成。
"""

from __future__ import annotations

import re
from typing import Any

from pipeline.schemas import Citation, Passage, QuoteCheck
from pipeline.textutil import norm_for_quote

_REF_RE = re.compile(r"\[(\d+)\]")
_QUOTE_RE = re.compile(r"「([^「」]+)」")
_ELLIPSIS_RE = re.compile(r"(?:……|…|\.\.\.)")


def extract_refs(text: str) -> list[int]:
    out: list[int] = []
    for m in _REF_RE.finditer(text or ""):
        n = int(m.group(1))
        if n not in out:
            out.append(n)
    return out


def build_citations(text: str, passages: list[Passage], *, years_by_n: dict[int, list[int]] | None = None) -> tuple[list[Citation], list[int]]:
    by_n = {p.number: p for p in passages}
    cites: list[Citation] = []
    invalid: list[int] = []
    for n in extract_refs(text):
        p = by_n.get(n)
        if p is None:
            invalid.append(n)
            cites.append(Citation(n=n, out_of_range=True))
            continue
        years = (years_by_n or {}).get(n)
        if years is None and p.meta.get("year"):
            y = int(p.meta["year"])
            years = [y, int(p.meta.get("year_end") or y)]
        src_en = p.location.get("source_en") or p.meta.get("source_en")
        if src_en in (None, ""):
            src_en = None
        else:
            src_en = str(src_en)
        cites.append(
            Citation(
                n=n,
                book_title=p.book_title,
                message_title=p.message_title,
                location=dict(p.location),
                index=p.index,
                years=years,
                source_en=src_en,
            )
        )
    return cites, invalid


def _in_one_passage(parts: list[str], norm_passages: list[tuple[int, str]]) -> int | None:
    for n, body in norm_passages:
        pos = 0
        ok = True
        for part in parts:
            i = body.find(part, pos)
            if i < 0:
                ok = False
                break
            pos = i + len(part)
        if ok:
            return n
    return None


def _on_md_heading_line(text: str, pos: int) -> bool:
    """「」若落在以「## 」或「### 」开头的行上，跳过核对（标题行不应含引文）。"""
    line_start = max(text.rfind("\n", 0, pos), text.rfind("\r", 0, pos)) + 1
    line = text[line_start:].splitlines()[0] if text[line_start:] else ""
    return line.startswith("## ") or line.startswith("### ")

def verify_quotes(text: str, passages: list[Passage]) -> list[QuoteCheck]:
    norm_passages = [(p.number, norm_for_quote(p.text)) for p in passages]
    checks: list[QuoteCheck] = []
    src = text or ""
    for m in _QUOTE_RE.finditer(src):
        if _on_md_heading_line(src, m.start()):
            continue
        raw = m.group(1)
        parts = [norm_for_quote(x) for x in _ELLIPSIS_RE.split(raw)]
        parts = [x for x in parts if x]
        if not parts:
            continue
        n = _in_one_passage(parts, norm_passages)
        checks.append(QuoteCheck(quote=raw, ok=n is not None, passage_n=n, parts=len(parts)))
    return checks


def mark_unverified(text: str, checks: list[QuoteCheck], mark: str) -> str:
    out = text
    for c in checks:
        if not c.ok:
            out = out.replace(f"「{c.quote}」", f"「{c.quote}」{mark}", 1)
    return out


def citations_to_dicts(cites: list[Citation]) -> list[dict[str, Any]]:
    return [c.model_dump() for c in cites]
