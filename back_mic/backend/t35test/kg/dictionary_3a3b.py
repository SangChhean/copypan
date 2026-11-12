# -*- coding: utf-8 -*-
"""【4.0】真理辞典 3a：按词名取定义纲目，按大点切块，精排后每词取前几块，放进生成纲目 Prompt 的单独一段。

2026-11-12 定：只要 3a，一直放（研究开关、3b、导出 docx 标色均已拆除）。
资料：panai4/data/graph_annotations/truth_dictionary_3a3b.json（按 title 对应词名，只读 content_3a）。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from t35test.kg.retrieval import rerank

logger = logging.getLogger("t35test")

DICT_PATH = Path(__file__).resolve().parents[2] / "panai4" / "data" / "graph_annotations" / "truth_dictionary_3a3b.json"
PER_WORD = 2  # 每词取几块

_BIG_POINT = re.compile(r"^[壹贰叁肆伍陆柒捌玖拾]+[\t 　]")
_dict: dict[str, dict[str, Any]] | None = None


def _load() -> dict[str, dict[str, Any]]:
    global _dict
    if _dict is None:
        try:
            data = json.loads(DICT_PATH.read_text(encoding="utf-8"))
            _dict = {str(x.get("title") or "").strip(): x for x in data if str(x.get("title") or "").strip()}
            logger.info("[3a] loaded %s terms from %s", len(_dict), DICT_PATH.name)
        except Exception as e:
            logger.warning("[3a] load %s failed: %s", DICT_PATH, e)
            return {}
    return _dict


def split_big_points(text: str) -> list[str]:
    """按大点（壹、贰、叁…开头的行）切块；大点前的读经等内容并入第一块；没有大点时整段为一块。"""
    lines = (text or "").strip().splitlines()
    if not lines:
        return []
    head: list[str] = []
    blocks: list[list[str]] = []
    for ln in lines:
        if _BIG_POINT.match(ln.strip()):
            blocks.append([ln])
        elif blocks:
            blocks[-1].append(ln)
        else:
            head.append(ln)
    if not blocks:
        return ["\n".join(head).strip()]
    out = ["\n".join(b).strip() for b in blocks]
    if head:
        out[0] = "\n".join(head).strip() + "\n" + out[0]
    return out


async def select_dict_chunks(words: list[str], query: str, per_word: int = PER_WORD) -> list[dict[str, Any]]:
    """取选中词的 3a 定义，切块后与题目一起精排，每词取前 per_word 块。
    返回块列表（按词的次序、块号由小到大），每块含 chunk_id / text / display_title / source。"""
    if not words:
        return []
    d = _load()
    cands: list[dict[str, Any]] = []
    for wi, w in enumerate(words):
        item = d.get(w)
        if not item:
            continue
        for bi, blk in enumerate(split_big_points(item.get("content_3a") or ""), start=1):
            if not blk:
                continue
            cands.append({
                "chunk_id": f"3a:{w}#{bi}",
                "text": blk,
                "display_title": f"{w}（3a）第 {bi} 块",
                "dict_word": w,
                "_order": (wi, bi),
            })
    if not cands:
        return []
    ranked = await rerank(cands, query, top_n=len(cands))  # 一次精排全部块；失败时按原序
    picked: list[dict[str, Any]] = []
    count: dict[str, int] = {}
    for c in ranked:
        w = c["dict_word"]
        if count.get(w, 0) >= per_word:
            continue
        count[w] = count.get(w, 0) + 1
        c = dict(c)
        c["source"] = "dict_3a"
        picked.append(c)
    picked.sort(key=lambda c: c["_order"])
    for c in picked:
        c.pop("_order", None)
    logger.info(
        "[3a] words=%s candidates=%s picked=%s chars=%s",
        len(words), len(cands), len(picked), sum(len(c["text"]) for c in picked),
    )
    return picked


def format_dict_block(chunks: list[dict[str, Any]]) -> str:
    """生成纲目 Prompt 里单独的一段（2026-11-12 用户定 A：删去"；3b 为参考资料"）。没有块时不放。"""
    if not chunks:
        return ""
    lines = [
        "## 词条定义（真理辞典）",
        "以下是本主题所选词条在真理辞典中的定义片段，供参考。3a 属职事范围：",
    ]
    for c in chunks:
        lines.append(f"[{c['chunk_id']}] {c['text']}")
    return "\n" + "\n".join(lines) + "\n"
