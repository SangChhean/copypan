# -*- coding: utf-8 -*-
"""防火墙：职事文档标题匹配与上下文注入。"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from kg_rag.llm_pricing import register_llm_usage

logger = logging.getLogger("kg_rag")

_backend_dir = Path(__file__).resolve().parents[1]
_rules_path = _backend_dir / "firewall_rules.json"
_docs_path = _backend_dir / "firewall.json"

_firewall_data: dict[str, dict[str, str]] = {}
_firewall_titles: list[str] = []

FIREWALL_MATCH_PROMPT = """以下是 {count} 个标题：
{titles_block}

用户主题：{query}

请判断用户主题是否明确对应上面某个标题。
判断标准：
- 主题所讨论的真理内容，与某标题所讨论的真理点是同一件事，就算命中
- 仅仅词语相似、或主题只是提到相关概念，不算命中
- 用经历性语言表达的主题，若其所经历的真理内容与某标题是同一件事，也算命中
- 没有明确对应的标题时返回 null

命中时只返回 JSON：{{"matched": "标题原文"}}
未命中时只返回 JSON：{{"matched": null}}
不得有任何其他文字、解释或 markdown。"""

# 与 kg_rag_service 中 Step5 等一致，防火墙匹配走 Sonnet 标准价
FIREWALL_MATCH_MODEL = "claude-sonnet-4-6"


def load_firewall() -> None:
    """启动时加载 firewall_rules.json 与 firewall.json。"""
    global _firewall_data, _firewall_titles
    _firewall_data = {}
    _firewall_titles = []

    rules_map: dict[str, str] = {}
    if _rules_path.is_file():
        with open(_rules_path, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    t = str(item.get("title", "")).strip()
                    n = str(item.get("note", "")).strip()
                    if t:
                        rules_map[t] = n
    else:
        logger.warning("[firewall] missing %s", _rules_path)

    if not _docs_path.is_file():
        logger.warning("[firewall] missing %s", _docs_path)
        logger.info("[firewall] loaded 0 documents (no firewall.json)")
        return

    with open(_docs_path, encoding="utf-8") as f:
        docs = json.load(f)
    if not isinstance(docs, list):
        logger.warning("[firewall] firewall.json is not a list")
        return

    prefix_re = re.compile(r"^第.+?题\s*")

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        msg = doc.get("msg")
        if not isinstance(msg, list):
            continue
        long_title = ""
        for m in msg:
            if not isinstance(m, dict):
                continue
            if m.get("type") == "title":
                long_title = str(m.get("text", "")).strip()
                break
        if not long_title:
            continue
        short_title = prefix_re.sub("", long_title).strip()
        lines: list[str] = []
        for m in msg:
            if not isinstance(m, dict):
                continue
            if m.get("type") == "bookname":
                continue
            tx = m.get("text")
            if tx is not None and str(tx).strip():
                lines.append(str(tx).strip())
        full_text = "\n".join(lines)
        note = rules_map.get(short_title, "")
        _firewall_data[short_title] = {
            "title": short_title,
            "note": note,
            "full_text": full_text,
        }
        _firewall_titles.append(short_title)

    logger.info("[firewall] loaded %s firewall documents", len(_firewall_titles))


def get_firewall_titles() -> list[str]:
    return list(_firewall_titles)


def get_firewall_doc(title: str) -> dict[str, str] | None:
    if not title or not title.strip():
        return None
    return _firewall_data.get(title.strip())


def _safe_parse_matched_json(text: str) -> Any:
    if not text or not str(text).strip():
        return None
    s = str(text).strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        last = s.rfind("}")
        if last > 0:
            try:
                obj = json.loads(s[: last + 1])
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                pass
        return None


async def match_firewall(
    query: str,
    llm_caller: Any,
    *,
    llm_calls: list[dict[str, Any]] | None = None,
) -> dict[str, str] | None:
    """
    判断用户主题是否命中防火墙。
    llm_caller: async function(prompt, model, temperature, max_tokens) -> (text, usage)
    llm_calls: 若提供，则将本次调用的 token/费用并入 KG-RAG 计价列表（step 名为 firewall）。
    返回: {"title": str, "note": str, "full_text": str} 或 None
    """
    if not _firewall_titles:
        logger.info("[KG-RAG DEBUG] firewall: skip match (no titles loaded)")
        return None
    titles_block = "\n".join(f"- {t}" for t in _firewall_titles)
    prompt = FIREWALL_MATCH_PROMPT.format(
        count=len(_firewall_titles),
        titles_block=titles_block,
        query=(query or "").strip(),
    )
    try:
        raw, usage = await llm_caller(
            prompt, FIREWALL_MATCH_MODEL, temperature=0, max_tokens=100
        )
        if llm_calls is not None:
            sn = register_llm_usage(
                llm_calls,
                step="firewall",
                request_model=FIREWALL_MATCH_MODEL,
                usage=usage,
            )
            if sn:
                logger.info(
                    "[KG-RAG LLM] firewall model=%s billing=%s in=%s out=%s cost_usd≈%s",
                    FIREWALL_MATCH_MODEL,
                    sn["billing_model"],
                    sn["input_tokens"],
                    sn["output_tokens"],
                    sn["cost_usd"],
                )
        preview = (raw or "").strip()
        logger.info(
            "[KG-RAG DEBUG] firewall: match LLM raw preview=%s",
            preview[:300] + ("…" if len(preview) > 300 else ""),
        )
        parsed = _safe_parse_matched_json(raw or "")
        if not parsed:
            logger.info("[KG-RAG DEBUG] firewall: no match (JSON parse failed or empty)")
            return None
        matched = parsed.get("matched")
        if matched is None:
            logger.info("[KG-RAG DEBUG] firewall: no match (matched is null)")
            return None
        ms = str(matched).strip()
        if not ms or ms.lower() == "null":
            logger.info("[KG-RAG DEBUG] firewall: no match (matched empty string)")
            return None
        doc = get_firewall_doc(ms)
        if doc:
            logger.info("[firewall] matched title=%r", doc.get("title"))
            return {
                "title": doc["title"],
                "note": doc["note"],
                "full_text": doc["full_text"],
            }
        logger.warning("[firewall] LLM returned unmatched title: %r", ms)
        logger.info("[KG-RAG DEBUG] firewall: no match (title not in local map)")
        return None
    except Exception as e:
        logger.warning("[firewall] match_firewall failed: %s", e)
        return None
