# -*- coding: utf-8 -*-
"""歌词查找：用户输入歌词片段 → 对应诗歌（纯程序）。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

from hymn.catalog import SERIES_TO_ES, HymnCatalog, get_catalog
from scripture.ref_enhance import traditional_to_simplified

_FULLWIDTH = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ　",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ",
)
_STANZA_MARK = re.compile(
    r"^\s*([一二三四五六七八九十百千零〇○两廿卅]+|副)\s*　\s*"
)
_QUOTE_PAIRS = [
    ("「", "」"),
    ("『", "』"),
    ("“", "”"),
    ("‘", "’"),
    ('"', '"'),
    ("'", "'"),
]
_CLAUSE_SPLIT = re.compile(r"[，。！？；、；;,.!?\n]+")


@lru_cache(maxsize=1)
def _lyrics_cfg() -> dict[str, Any]:
    from config import load_config_json

    raw = load_config_json("hymn.json")
    return dict(raw.get("lyrics") or {})


def _cfg() -> dict[str, Any]:
    return _lyrics_cfg()


def _strip_hint_phrases_at_edges(s: str, phrases: list[str]) -> str:
    """只从首尾剥提示词，避免歌词正文中间的「出自」「这句」等被误删。"""
    ordered = sorted([p for p in phrases if p], key=len, reverse=True)
    changed = True
    while changed and s:
        changed = False
        for p in ordered:
            if s.startswith(p):
                s = s[len(p) :]
                changed = True
                break
            if s.endswith(p):
                s = s[: -len(p)]
                changed = True
                break
    return s


def normalize_lyric_text(text: str, *, strip_hints: bool = False) -> str:
    """繁简、全角、去标点空白；可选去掉提示词与成对引号。

    提示词只从首尾剥（去标点之后），避免歌词中间的「出自」等被误删。
    """
    if not text:
        return ""
    s = traditional_to_simplified(text)
    s = s.translate(_FULLWIDTH)
    if strip_hints:
        for a, b in _QUOTE_PAIRS:
            s = s.replace(a, "").replace(b, "")
    out: list[str] = []
    for ch in s:
        if ch.isspace() or unicodedata.category(ch) in {"Zs", "Zl", "Zp"}:
            continue
        if unicodedata.category(ch).startswith("P"):
            continue
        out.append(ch)
    s = "".join(out)
    if strip_hints:
        s = _strip_hint_phrases_at_edges(s, list(_cfg().get("strip_phrases") or []))
    return s


def _title_body(title: str, name: str) -> str:
    t = (title or "").strip()
    if t:
        return t
    # 从 name 去掉「系列第N首」前缀
    n = name or ""
    m = re.match(r"^(?:诗歌附|补充本诗歌|大本诗歌|诗歌|大本|补充本)\s*第?\s*\d+\s*首?\s*", n)
    if m:
        return n[m.end() :].lstrip("　 \t")
    m2 = re.match(r"^诗歌附\s*\d+\s*", n)
    if m2:
        return n[m2.end() :].lstrip("　 \t")
    return n


def _split_clauses(body: str) -> list[str]:
    parts = [p.strip() for p in _CLAUSE_SPLIT.split(body) if p and p.strip()]
    return parts or ([body.strip()] if body.strip() else [])


@dataclass
class _HymnDoc:
    series: str
    hymn_number: int
    name: str
    title: str
    title_norm: str
    body_norm: str
    # body_norm 每位 → (unit_label, clause_original)
    pos_map: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class LyricMatch:
    series: str
    hymn_number: int
    match_type: str  # exact / fuzzy / title
    unit_label: str
    snippet: str
    name: str
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "series": SERIES_TO_ES.get(self.series, self.series),
            "series_code": self.series,
            "hymn_number": self.hymn_number,
            "match_type": self.match_type,
            "unit_label": self.unit_label,
            "snippet": self.snippet,
            "name": self.name,
        }


class LyricsIndex:
    def __init__(self, docs: list[_HymnDoc]):
        self.docs = docs
        self._bigrams: dict[str, list[int]] = {}
        for i, d in enumerate(docs):
            seen = set()
            for bg in _bigrams_of(d.body_norm):
                if bg in seen:
                    continue
                seen.add(bg)
                self._bigrams.setdefault(bg, []).append(i)

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> "LyricsIndex":
        docs = [_build_doc(r) for r in rows if (r.get("text") or "").strip()]
        return cls(docs)

    @classmethod
    def from_catalog(cls, catalog: Optional[HymnCatalog] = None) -> "LyricsIndex":
        cat = catalog or get_catalog()
        cat.ensure_loaded()
        return cls.from_rows(cat.full_rows())


def _bigrams_of(s: str) -> list[str]:
    if len(s) < 2:
        return [s] if s else []
    return [s[i : i + 2] for i in range(len(s) - 1)]


def _build_doc(row: dict[str, Any]) -> _HymnDoc:
    text = str(row.get("text") or "")
    lines = text.split("\n")
    body_lines = lines[1:] if lines else []
    title = _title_body(str(row.get("title") or ""), str(row.get("name") or ""))
    body_norm_chars: list[str] = []
    pos_map: list[tuple[str, str]] = []
    current_label = "一"
    for raw_line in body_lines:
        line = raw_line
        m = _STANZA_MARK.match(line)
        if m:
            current_label = m.group(1)
            line = line[m.end() :]
        line = line.strip()
        if not line:
            continue
        for clause in _split_clauses(line):
            for ch in clause:
                # 规范化单字：去标点空白已在 clause 级再滤
                if ch.isspace() or unicodedata.category(ch).startswith("P"):
                    continue
                # 全角已在查询侧；正文也统一
                ch2 = ch.translate(_FULLWIDTH)
                if ch2.isspace() or unicodedata.category(ch2).startswith("P"):
                    continue
                body_norm_chars.append(traditional_to_simplified(ch2))
                pos_map.append((current_label, clause))
    title_norm = normalize_lyric_text(title, strip_hints=False)
    return _HymnDoc(
        series=str(row.get("series") or ""),
        hymn_number=int(row.get("hymn_number") or 0),
        name=str(row.get("name") or ""),
        title=title,
        title_norm=title_norm,
        body_norm="".join(body_norm_chars),
        pos_map=pos_map,
    )


def _snippet_at(doc: _HymnDoc, start: int, length: int, cfg: dict[str, Any]) -> tuple[str, str]:
    if not doc.pos_map or start < 0 or start >= len(doc.pos_map):
        return "", ""
    label, clause = doc.pos_map[start]
    max_n = int(cfg.get("snippet_max_chars", 60))
    snip = clause if len(clause) <= max_n else clause[:max_n]
    return label, snip


def _edit_distance_le(a: str, b: str, max_err: int) -> bool:
    """判定 edit distance(a,b) ≤ max_err（banded）。"""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > max_err:
        return False
    # 短串 DP
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * lb
        row_min = i
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if cur[j] < row_min:
                row_min = cur[j]
        if row_min > max_err:
            return False
        prev = cur
    return prev[lb] <= max_err


def _fuzzy_window_hit(body: str, q: str, max_err: int) -> Optional[int]:
    """滑窗：返回首次命中起始下标。"""
    n, m = len(body), len(q)
    if m == 0 or n == 0:
        return None
    lo = max(1, m - max_err)
    hi = m + max_err
    for win in range(lo, hi + 1):
        if win > n:
            break
        for i in range(0, n - win + 1):
            if _edit_distance_le(body[i : i + win], q, max_err):
                return i
    return None


def _type_rank(t: str) -> int:
    return {"exact": 0, "fuzzy": 1, "title": 2}.get(t, 9)


_INDEX: Optional[LyricsIndex] = None


def get_lyrics_index(*, catalog: Optional[HymnCatalog] = None, force: bool = False) -> LyricsIndex:
    global _INDEX
    if _INDEX is not None and not force and catalog is None:
        return _INDEX
    idx = LyricsIndex.from_catalog(catalog)
    if catalog is None:
        _INDEX = idx
    return idx


def reset_lyrics_index() -> None:
    global _INDEX
    _INDEX = None
    _lyrics_cfg.cache_clear()


def find_lyrics(
    text: str,
    *,
    index: Optional[LyricsIndex] = None,
    catalog: Optional[HymnCatalog] = None,
) -> dict[str, Any]:
    cfg = _cfg()
    q = normalize_lyric_text(text, strip_hints=True)
    min_q = int(cfg.get("min_query_chars", 4))
    if len(q) < min_q:
        return {"status": "too_short", "matches": [], "total": 0, "query_norm": q}

    idx = index or get_lyrics_index(catalog=catalog)
    max_matches = int(cfg.get("max_matches", 5))
    too_common_n = int(cfg.get("too_common_threshold", 5))
    hits: list[LyricMatch] = []

    # a) exact
    for doc in idx.docs:
        pos = doc.body_norm.find(q)
        if pos < 0:
            continue
        label, snip = _snippet_at(doc, pos, len(q), cfg)
        hits.append(
            LyricMatch(
                series=doc.series,
                hymn_number=doc.hymn_number,
                match_type="exact",
                unit_label=label,
                snippet=snip,
                name=doc.name,
                score=1.0,
            )
        )

    # b) fuzzy（仅精确未命中时）
    if not hits and len(q) >= int(cfg.get("min_fuzzy_chars", 6)):
        max_err = max(int(cfg.get("fuzzy_min_errors", 1)), len(q) // int(cfg.get("fuzzy_errors_divisor", 8)))
        q_bg = set(_bigrams_of(q))
        min_ov = float(cfg.get("fuzzy_bigram_min_overlap", 0.4))
        cap = int(cfg.get("fuzzy_candidate_cap", 80))
        scored: list[tuple[float, int]] = []
        if q_bg:
            cand_counts: dict[int, int] = {}
            for bg in q_bg:
                for di in idx._bigrams.get(bg, []):
                    cand_counts[di] = cand_counts.get(di, 0) + 1
            for di, cnt in cand_counts.items():
                ov = cnt / max(len(q_bg), 1)
                if ov >= min_ov:
                    scored.append((ov, di))
            scored.sort(reverse=True)
            scored = scored[:cap]
        for ov, di in scored:
            doc = idx.docs[di]
            start = _fuzzy_window_hit(doc.body_norm, q, max_err)
            if start is None:
                continue
            label, snip = _snippet_at(doc, start, len(q), cfg)
            hits.append(
                LyricMatch(
                    series=doc.series,
                    hymn_number=doc.hymn_number,
                    match_type="fuzzy",
                    unit_label=label,
                    snippet=snip,
                    name=doc.name,
                    score=ov,
                )
            )

    # c) title：查询等于诗名，或查询包含诗名且诗名占查询足够比例（避免长文误触）
    min_title = int(cfg.get("min_title_chars", 3))
    title_cov = float(cfg.get("title_contain_min_coverage", 0.5))
    if len(q) >= min_title:
        for doc in idx.docs:
            t = doc.title_norm
            if len(t) < min_title:
                continue
            eq = q == t
            contained = (not eq) and (t in q) and (len(t) / max(len(q), 1) >= title_cov)
            if not (eq or contained):
                continue
            # 查询本身就是诗名时：即便正文 exact 已命中，仍标为 title
            existing = [
                h
                for h in hits
                if h.hymn_number == doc.hymn_number and h.series == doc.series
            ]
            if existing and not eq:
                continue
            if existing and eq:
                for h in existing:
                    hits.remove(h)
            hits.append(
                LyricMatch(
                    series=doc.series,
                    hymn_number=doc.hymn_number,
                    match_type="title",
                    unit_label="",
                    snippet=doc.title[: int(cfg.get("snippet_max_chars", 60))],
                    name=doc.name,
                    score=1.0 if eq else len(t) / max(len(q), 1),
                )
            )

    # 同首去重：诗名全等优先；否则精确 > 近似 > 诗名
    dedup: dict[tuple[str, int], LyricMatch] = {}
    for h in hits:
        key = (h.series, h.hymn_number)
        prev = dedup.get(key)
        if prev is None:
            dedup[key] = h
            continue
        if h.match_type == "title" and h.score >= 1.0:
            dedup[key] = h
            continue
        if prev.match_type == "title" and prev.score >= 1.0:
            continue
        if _type_rank(h.match_type) < _type_rank(prev.match_type):
            dedup[key] = h
        elif h.match_type == prev.match_type and h.score > prev.score:
            dedup[key] = h
    hits = list(dedup.values())
    hits.sort(key=lambda h: (_type_rank(h.match_type), -h.score, h.series, h.hymn_number))
    total = len(hits)
    if total == 0:
        return {"status": "not_found", "matches": [], "total": 0, "query_norm": q}
    status = "too_common" if total > too_common_n else "found"
    top = hits[:max_matches]
    return {
        "status": status,
        "matches": [m.to_dict() for m in top],
        "total": total,
        "query_norm": q,
    }


def _hint_lists(cfg: Optional[dict[str, Any]] = None) -> tuple[list[str], list[str]]:
    c = cfg or _cfg()
    strong = list(c.get("hint_phrases_strong") or [])
    weak = list(c.get("hint_phrases_weak") or [])
    # 兼容旧配置 hint_phrases：全部当作强档
    if not strong and not weak:
        strong = list(c.get("hint_phrases") or [])
    return strong, weak


def _first_hint_in(text: str, phrases: list[str]) -> Optional[str]:
    s = traditional_to_simplified(text or "")
    # 长词优先，避免「哪首」抢在「哪首诗歌」前
    for p in sorted([x for x in phrases if x], key=len, reverse=True):
        if p in s:
            return p
    return None


def _has_hint(text: str) -> bool:
    strong, weak = _hint_lists()
    return _first_hint_in(text, strong + weak) is not None


def lyric_intent(
    text: str,
    *,
    index: Optional[LyricsIndex] = None,
    catalog: Optional[HymnCatalog] = None,
    bible: Any = None,
) -> bool:
    """是否应按歌词查找触发。"""
    if not (text or "").strip():
        return False

    cfg = _cfg()
    strong, weak = _hint_lists(cfg)
    has_strong = _first_hint_in(text, strong) is not None

    # 已被诗歌首数识别 → 不触发（明确在查「第N首」）
    try:
        from hymn.parse import parse_hymn_refs

        if parse_hymn_refs(text, catalog=catalog):
            return False
    except Exception:
        pass
    # 经文出处识别：无强档歌词提示时才拦截。
    # 强档（如「是哪首诗歌的歌词」）优先，避免歌词正文被 parse_refs 误判为经文而不触发。
    if not has_strong:
        try:
            from scripture.normalize import parse_refs

            if parse_refs(text, bible=bible, validate=bible is not None):
                return False
        except Exception:
            pass

    stripped_norm = normalize_lyric_text(text, strip_hints=True)
    min_hint = int(cfg.get("intent_hint_min_chars", 4))
    # 强档：含提示词且去提示后 ≥ min → 直接触发
    if has_strong and len(stripped_norm) >= min_hint:
        return True
    # 弱档：仅当实际检索命中才触发
    if _first_hint_in(text, weak) and len(stripped_norm) >= min_hint:
        res = find_lyrics(text, index=index, catalog=catalog)
        if res.get("status") in {"found", "too_common"} and res.get("matches"):
            return True
    if len(stripped_norm) >= int(cfg.get("intent_long_min_chars", 8)):
        res = find_lyrics(text, index=index, catalog=catalog)
        if res.get("status") in {"found", "too_common"} and res.get("matches"):
            # 精确匹配且覆盖率
            m0 = res["matches"][0]
            if m0.get("match_type") == "exact":
                qn = res.get("query_norm") or stripped_norm
                cov = len(qn) / max(len(stripped_norm), 1)
                # 匹配长度占输入：精确时匹配长=查询长
                if cov >= float(cfg.get("intent_long_coverage", 0.7)):
                    return True
    return False
