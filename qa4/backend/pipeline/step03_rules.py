# -*- coding: utf-8 -*-
"""第 3 步规则前置：经文出处 → 诗歌首数 → 歌词查找；截获则跳过 Haiku。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from hymn.catalog import SERIES_TO_ES, get_catalog
from hymn.parse import SERIES_LABEL, HymnRef, HymnRefList, format_hymn_refs, parse_hymn_refs
from pipeline.schemas import Locator, Plan, QType, SubQuestion
from scripture.ref_enhance import traditional_to_simplified

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_QA4_ROOT = _BACKEND_ROOT.parent
_REPO_ROOT = _QA4_ROOT.parent
_DEFAULT_LEXICON_PATH = _REPO_ROOT / "docs" / "panai4_graph" / "2373个词条（已确定一一对应为concept节点）.txt"


@dataclass
class RuleOutcome:
    """规则前置结果。"""

    plan: Optional[Plan] = None
    skip_llm: bool = False
    early_done: bool = False  # 本轮结束（歌词 too_*/choose）
    rule_hits: list[dict[str, Any]] = field(default_factory=list)
    lyrics_status: Optional[str] = None
    choose_candidates: list[dict[str, Any]] = field(default_factory=list)
    answer_text: str = ""
    awaiting_choice: bool = False


def _cfg(deps: Any) -> dict[str, Any]:
    return dict(getattr(deps, "cfg", None) or {})


def _norm_name(text: str) -> str:
    """词条/诗名比对用：繁简、去标点空白（与歌词 normalize 口径一致，不去提示词）。"""
    from hymn.lyrics import normalize_lyric_text

    return normalize_lyric_text(text or "", strip_hints=False)


@lru_cache(maxsize=4)
def _load_lexicon_norm_names(path_str: str) -> frozenset[str]:
    p = Path(path_str)
    if not p.is_file():
        return frozenset()
    names: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        n = _norm_name(t)
        if n:
            names.add(n)
    return frozenset(names)


def lexicon_norm_names(deps: Any = None, cfg: Optional[dict[str, Any]] = None) -> frozenset[str]:
    """规范化词条名集合；deps.lexicon_norm_names 可注入（单测）。"""
    if deps is not None:
        injected = getattr(deps, "lexicon_norm_names", None)
        if injected is not None:
            return frozenset(injected)
    c = cfg if cfg is not None else (_cfg(deps) if deps is not None else {})
    path = c.get("lexicon_names_path") or str(_DEFAULT_LEXICON_PATH)
    return _load_lexicon_norm_names(str(path))


_CN_NUM = set("零〇一二三四五六七八九十百千万两廿卅")
_SERIES_WORDS = [
    "补充本诗歌",
    "大本诗歌",
    "儿童诗歌",
    "诗歌附",
    "补充本",
    "大本",
    "诗歌",
    "附",
]
_LATIN_REF = re.compile(r"[A-Za-z][A-Za-z.\s]*\d+(?:\s*[:：.]\s*\d+)?")


def _clean_residual(s: str) -> str:
    out: list[str] = []
    for ch in s:
        if ch.isspace() or unicodedata.category(ch).startswith(("Z", "P")):
            continue
        out.append(ch)
    return "".join(out)


def _strip_fragments(text: str, fragments: list[str], request_words: list[str]) -> str:
    s = traditional_to_simplified(text or "")
    # 稳定排序：等长时按字符串，避免 set 哈希序导致剩余字数抖动
    for frag in sorted({f for f in fragments if f}, key=lambda x: (-len(x), x)):
        s = s.replace(frag, "")
        s = s.replace(traditional_to_simplified(frag), "")
    for w in sorted([x for x in request_words if x], key=lambda x: (-len(x), x)):
        s = s.replace(w, "")
    return s


def _strip_hymn_structural(s: str) -> str:
    """去掉系列词、第/首/号、阿拉伯与中文数字（出处外壳）。"""
    t = traditional_to_simplified(s or "")
    for w in _SERIES_WORDS:
        t = t.replace(w, "")
    for w in ("第", "首", "号", "NO.", "No.", "no.", "#", "NO", "No", "no"):
        t = t.replace(w, "")
    t = re.sub(r"\d+", "", t)
    t = "".join(ch for ch in t if ch not in _CN_NUM)
    return t


def _strip_scripture_structural(s: str) -> str:
    """去掉英文书卷+章节及残留数字。"""
    t = _LATIN_REF.sub("", s or "")
    t = re.sub(r"\d+", "", t)
    t = "".join(ch for ch in t if ch not in _CN_NUM)
    return t


def _has_block_keyword(text: str, keywords: list[str]) -> bool:
    s = traditional_to_simplified(text or "")
    return any(k and k in s for k in keywords)


def is_pure_citation(
    text: str,
    fragments: list[str],
    *,
    request_words: list[str],
    block_keywords: list[str],
    residual_max: int,
    kind: str = "scripture",
) -> bool:
    if _has_block_keyword(text, block_keywords):
        return False
    residual = _strip_fragments(text, fragments, request_words)
    if kind == "hymn":
        residual = _strip_hymn_structural(residual)
    else:
        residual = _strip_scripture_structural(residual)
    residual = _clean_residual(residual)
    return len(residual) <= int(residual_max)


def _scripture_fragments(text: str, refs: list[Any]) -> list[str]:
    """只收出处片段，不含整句（否则「纯出处」恒真）。

    不用「书名后 N 字」滑动窗：会吞掉「这两处…有什么关系」等实质问句，
    且等长 frag 的 set 序曾导致剩余字数随进程抖动。
    """
    frags: list[str] = []
    for r in refs:
        raw = getattr(r, "raw", None)
        if raw:
            frags.append(str(raw))
            frags.append(traditional_to_simplified(str(raw)))
        try:
            lab = r.label()
            if lab:
                frags.append(str(lab))
                frags.append(traditional_to_simplified(str(lab)))
        except Exception:
            pass
    return frags


def _hymn_fragments(text: str, refs: HymnRefList) -> list[str]:
    frags: list[str] = []
    for r in refs:
        n = int(r.number)
        lab = SERIES_LABEL.get(r.series, r.series)
        frags.extend(
            [
                f"诗歌第{n}首",
                f"诗歌{n}首",
                f"诗歌第{n}",
                f"诗歌{n}",
                f"大本第{n}首",
                f"大本{n}",
                f"补充本第{n}首",
                f"补充本诗歌第{n}首",
                f"补充本{n}",
                f"诗歌附{n}",
                f"第{n}首诗歌",
                f"第{n}号诗歌",
                f"{lab}{n}",
                f"{lab} {n}",
                f"诗{n}首",
                f"诗第{n}首",
            ]
        )
    return frags


def _plan_scripture(question: str, labels: list[str]) -> Plan:
    joined = "；".join(labels)
    return Plan(
        main_type=QType.经文.value,
        source="scripture_rule",
        complex=False,
        subquestions=[SubQuestion(text=question, qtype=QType.经文.value)],
        understanding=f"规则识别经文出处：{joined}",
        locator=Locator(scripture=joined),
    )


def _plan_hymn(question: str, refs: HymnRefList) -> Plan:
    first = refs[0]
    hrefs = [
        {
            "series": r.series,
            "number": int(r.number),
            "fallback": bool(r.fallback),
            "exists": bool(r.exists),
            "explicit_series": bool(r.explicit_series),
        }
        for r in refs
    ]
    notes: list[str] = []
    if refs.truncated:
        notes.append("识别到的首数较多，已按上限截断。")
    for r in refs:
        if r.fallback:
            notes.append(f"大本没有第{r.number}首，显示的是补充本第{r.number}首。")
    understanding = f"规则识别诗歌首数：{format_hymn_refs(refs)}"
    if notes:
        understanding += "；" + "；".join(notes)
    return Plan(
        main_type=QType.诗歌.value,
        source="hymn_rule",
        complex=False,
        subquestions=[SubQuestion(text=question, qtype=QType.诗歌.value)],
        understanding=understanding,
        locator=Locator(hymn_series=first.series, hymn_number=int(first.number)),
        hymn_refs=hrefs,
    )


def _plan_lyrics_single(question: str, match: dict[str, Any]) -> Plan:
    series = match.get("series_code") or match.get("series") or "big"
    # find_lyrics 返回 ES 名在 series、逻辑码在 series_code
    from hymn.catalog import ES_TO_SERIES

    if series in ES_TO_SERIES:
        logical = ES_TO_SERIES[series]
    elif series in SERIES_TO_ES:
        logical = series
    else:
        logical = "big"
    num = int(match.get("hymn_number") or 0)
    return Plan(
        main_type=QType.诗歌.value,
        source="lyrics_rule",
        complex=False,
        subquestions=[SubQuestion(text=question, qtype=QType.诗歌.value)],
        understanding=f"歌词命中唯一一首：{SERIES_LABEL.get(logical, logical)} {num}",
        locator=Locator(hymn_series=logical, hymn_number=num),
        hymn_refs=[
            {
                "series": logical,
                "number": num,
                "fallback": False,
                "exists": True,
                "explicit_series": True,
                "from_lyrics": True,
            }
        ],
    )


def _candidate_row(m: dict[str, Any]) -> dict[str, Any]:
    from hymn.catalog import ES_TO_SERIES

    series = m.get("series_code") or m.get("series") or ""
    if series in ES_TO_SERIES:
        logical = ES_TO_SERIES[series]
        series_zh = SERIES_TO_ES.get(logical, series)
    elif series in SERIES_TO_ES:
        logical = series
        series_zh = SERIES_TO_ES[series]
    else:
        logical = series
        series_zh = series
    snip = str(m.get("snippet") or "")
    return {
        "series": logical,
        "series_zh": series_zh,
        "hymn_number": int(m.get("hymn_number") or 0),
        "name": str(m.get("name") or ""),
        "unit_label": str(m.get("unit_label") or ""),
        "snippet": snip[:60],
        "snippet_len": len(snip),
        "match_type": m.get("match_type"),
    }


def apply_rule_plan(
    question_for_refs: str,
    question_orig: str,
    deps: Any,
    *,
    bible: Any = None,
) -> RuleOutcome:
    """经文 → 诗歌首数 → 歌词。返回是否短路 / 早退。"""
    cfg = _cfg(deps)
    out = RuleOutcome()
    if not bool(cfg.get("rule_preplan_enabled", True)):
        return out

    request_words = list(cfg.get("rule_request_words") or [])
    block_keywords = list(cfg.get("rule_block_keywords") or [])
    residual_max = int(cfg.get("rule_pure_residual_max", 4))
    bible = bible if bible is not None else getattr(deps, "bible", None)

    # ---- 1 经文 ----
    from scripture.normalize import parse_refs

    try:
        s_refs = parse_refs(question_for_refs, bible=bible, validate=bible is not None)
    except Exception:
        s_refs = []
    if s_refs:
        labels = [r.label() for r in s_refs]
        hit = {"kind": "scripture", "labels": labels, "n": len(s_refs)}
        out.rule_hits.append(hit)
        frags = _scripture_fragments(question_for_refs, s_refs)
        if is_pure_citation(
            question_for_refs,
            frags,
            request_words=request_words,
            block_keywords=block_keywords,
            residual_max=residual_max,
            kind="scripture",
        ):
            out.plan = _plan_scripture(question_for_refs, labels)
            out.skip_llm = True
            return out

    # ---- 2 诗歌首数 ----
    cat = get_catalog()
    try:
        cat.ensure_loaded()
    except Exception:
        pass
    try:
        h_refs = parse_hymn_refs(question_for_refs, catalog=cat)
    except Exception:
        h_refs = HymnRefList()
    if h_refs:
        out.rule_hits.append(
            {
                "kind": "hymn",
                "formatted": format_hymn_refs(h_refs),
                "n": len(h_refs),
                "truncated": bool(h_refs.truncated),
            }
        )
        frags = _hymn_fragments(question_for_refs, h_refs)
        if is_pure_citation(
            question_for_refs,
            frags,
            request_words=request_words,
            block_keywords=block_keywords,
            residual_max=residual_max,
            kind="hymn",
        ):
            out.plan = _plan_hymn(question_for_refs, h_refs)
            out.skip_llm = True
            return out

    # ---- 3 歌词（用原始输入）----
    # 非纯出处已命中经文/诗歌时：仅当「强档提示 + find_lyrics=found」才改走歌词；
    # too_short / too_common / not_found 仍交模型（保留 rule_hits）。
    q_lyrics = question_orig or question_for_refs
    lyrics_idx = getattr(deps, "lyrics_index", None)

    if out.rule_hits:
        from hymn.lyrics import find_lyrics, _first_hint_in, _hint_lists

        strong, _weak = _hint_lists()
        if _first_hint_in(q_lyrics, strong) is None:
            return out
        try:
            found = find_lyrics(q_lyrics, index=lyrics_idx) if lyrics_idx is not None else find_lyrics(q_lyrics)
        except Exception:
            return out
        status = str(found.get("status") or "not_found")
        matches = list(found.get("matches") or [])
        if status != "found" or not matches:
            # 不采纳歌词路径
            out.rule_hits.append(
                {"kind": "lyrics_skip", "status": status, "total": found.get("total"), "n_matches": len(matches)}
            )
            return out
        return _apply_lyrics_found(out, cfg, q_lyrics, status, matches)

    return _run_lyrics_primary(out, cfg, q_lyrics, cat, bible, lyrics_idx, deps)


def _apply_lyrics_found(
    out: RuleOutcome,
    cfg: dict[str, Any],
    q_lyrics: str,
    status: str,
    matches: list[dict[str, Any]],
) -> RuleOutcome:
    out.lyrics_status = status if len(matches) == 1 else "found_multi"
    out.rule_hits.append({"kind": "lyrics", "status": out.lyrics_status, "total": len(matches), "n_matches": len(matches)})
    if len(matches) == 1:
        out.plan = _plan_lyrics_single(q_lyrics, matches[0])
        out.skip_llm = True
        return out
    cands = [_candidate_row(m) for m in matches]
    out.early_done = True
    out.skip_llm = True
    out.awaiting_choice = True
    out.choose_candidates = cands
    lines = [str(cfg.get("lyrics_choose_preamble") or "找到多首可能的诗歌：")]
    for i, c in enumerate(cands, 1):
        lines.append(
            f"{i}. {c.get('series_zh') or c.get('series')} 第{c.get('hymn_number')}首"
            f"　{c.get('name') or ''}　「{c.get('snippet') or ''}」"
        )
    out.answer_text = "\n".join(lines)
    out.plan = Plan(
        main_type=QType.默认.value,
        source="lyrics_rule",
        understanding="歌词命中多首，待选择",
        subquestions=[SubQuestion(text=q_lyrics, qtype=QType.默认.value)],
    )
    return out


def _run_lyrics_primary(
    out: RuleOutcome,
    cfg: dict[str, Any],
    q_lyrics: str,
    cat: Any,
    bible: Any,
    lyrics_idx: Any,
    deps: Any = None,
) -> RuleOutcome:
    """无经文/诗歌命中时的歌词主路径（含 too_short / too_common）。"""
    from hymn.lyrics import (
        find_lyrics,
        lyric_intent,
        normalize_lyric_text,
        _cfg as _lyrics_cfg,
        _first_hint_in,
        _hint_lists,
    )

    stripped = normalize_lyric_text(q_lyrics, strip_hints=True)
    min_q = int((_lyrics_cfg() or {}).get("min_query_chars", 4))
    # 与 find_lyrics 一致：去提示后过短 → too_short（不调模型、不记 lyrics_rule 命中）
    if len(stripped) < min_q:
        out.lyrics_status = "too_short"
        out.early_done = True
        out.skip_llm = True
        out.answer_text = str(cfg.get("lyrics_too_short_message") or "请多给几个字。")
        # source 不用 lyrics_rule，避免格式负例短串被计为歌词命中
        out.plan = Plan(
            main_type=QType.默认.value,
            source="lyrics_too_short",
            understanding="歌词查询过短",
            subquestions=[SubQuestion(text=q_lyrics, qtype=QType.默认.value)],
        )
        return out

    try:
        intent = lyric_intent(q_lyrics, catalog=cat, bible=bible, index=lyrics_idx)
    except TypeError:
        try:
            intent = lyric_intent(q_lyrics, catalog=cat, bible=bible)
        except Exception:
            intent = False
    except Exception:
        intent = False

    try:
        found = find_lyrics(q_lyrics, index=lyrics_idx) if lyrics_idx is not None else find_lyrics(q_lyrics)
    except Exception:
        found = {"status": "not_found", "matches": [], "total": 0}
    status = str(found.get("status") or "not_found")
    matches = list(found.get("matches") or [])

    # intent 未覆盖「纯诗名」：title 命中可走歌词；若整句等于词条名且无强档提示 → 交模型
    if not intent:
        title_ms = [m for m in matches if str(m.get("match_type") or "") == "title"]
        exact = [m for m in title_ms if float(m.get("score") or 0) >= 1.0]
        use = exact or title_ms
        if status in {"found", "too_common"} and use:
            strong, _weak = _hint_lists()
            has_strong = _first_hint_in(q_lyrics, strong) is not None
            q_norm = _norm_name(stripped) if stripped else _norm_name(q_lyrics)
            lex = lexicon_norm_names(deps, cfg)
            if (q_norm in lex or _norm_name(q_lyrics) in lex) and not has_strong:
                return out
            return _apply_lyrics_found(out, cfg, q_lyrics, status, use)
        return out

    out.lyrics_status = status
    out.rule_hits.append({"kind": "lyrics", "status": status, "total": found.get("total"), "n_matches": len(matches)})

    if status == "too_short":
        out.early_done = True
        out.skip_llm = True
        out.answer_text = str(cfg.get("lyrics_too_short_message") or "请多给几个字。")
        out.plan = Plan(
            main_type=QType.默认.value,
            source="lyrics_rule",
            understanding="歌词查询过短",
            subquestions=[SubQuestion(text=q_lyrics, qtype=QType.默认.value)],
        )
        return out

    if status == "too_common":
        out.early_done = True
        out.skip_llm = True
        out.answer_text = str(cfg.get("lyrics_too_common_message") or "命中太多，请再补几个字。")
        out.plan = Plan(
            main_type=QType.默认.value,
            source="lyrics_rule",
            understanding="歌词命中过多",
            subquestions=[SubQuestion(text=q_lyrics, qtype=QType.默认.value)],
        )
        return out

    if status == "found" and matches:
        return _apply_lyrics_found(out, cfg, q_lyrics, status, matches)

    out.lyrics_status = "not_found"
    return out
