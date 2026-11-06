# -*- coding: utf-8 -*-
"""防火墙：《神圣的辩理》篇题匹配与上下文注入（新测试台）。"""
from __future__ import annotations

import json
import logging
from typing import Any

from t35test.kg.llm_pricing import register_llm_usage

logger = logging.getLogger("t35test")

# 【新测试台】防火墙资料换成《神圣的辩理》（ES 索引 panai_new_dispute，73 个篇题；词条索引表记 187 个词条）。
# 名字仍叫防火墙；命中后放进上下文的是「篇题 + 简短说明」，不再放全文。
DISPUTE_INDEX = "panai_new_dispute"

_es_client: Any = None
_firewall_data: dict[str, dict[str, Any]] = {}
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

FIREWALL_MATCH_MODEL = "claude-opus-5-5"


def load_firewall(es: Any = None) -> None:
    """启动时从 ES 读《神圣的辩理》：每个篇题一条（说明取该篇题的 description，词条名一并记下）。
    读取失败或索引为空时不报错，防火墙本次不生效；之后 match_firewall 会再试着读一次。"""
    global _es_client, _firewall_data, _firewall_titles
    if es is not None:
        _es_client = es
    _firewall_data = {}
    _firewall_titles = []
    if _es_client is None:
        logger.warning("[firewall] no ES client, loaded 0 titles")
        return
    try:
        resp = _es_client.search(
            index=DISPUTE_INDEX,
            body={
                "size": 1000,
                "query": {"match_all": {}},
                "_source": ["name", "title", "description"],
            },
        )
    except Exception as e:
        logger.warning("[firewall] read %s failed, loaded 0 titles: %s", DISPUTE_INDEX, e)
        return

    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        title = str(src.get("title") or "").strip()
        if not title:
            continue
        name = str(src.get("name") or "").strip()
        desc = str(src.get("description") or "").strip()
        doc = _firewall_data.get(title)
        if doc is None:
            doc = {"title": title, "note": desc, "names": []}
            _firewall_data[title] = doc
            _firewall_titles.append(title)
        elif not doc["note"] and desc:
            doc["note"] = desc
        if name and name not in doc["names"]:
            doc["names"].append(name)

    _firewall_titles.sort()
    for doc in _firewall_data.values():
        # 命中后插到检索结果最前面的内容：篇题 + 简短说明
        doc["full_text"] = f"篇题：{doc['title']}\n说明：{doc['note']}" if doc["note"] else f"篇题：{doc['title']}"
    logger.info(
        "[firewall] loaded %s titles / %s names from %s",
        len(_firewall_titles),
        sum(len(d["names"]) for d in _firewall_data.values()),
        DISPUTE_INDEX,
    )


def get_firewall_titles() -> list[str]:
    return list(_firewall_titles)


def get_firewall_doc(title: str) -> dict[str, Any] | None:
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
    返回: {"title": str, "note": str, "full_text": str, "names": list[str]} 或 None
    """
    if not _firewall_titles and _es_client is not None:
        load_firewall()
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
                "names": list(doc.get("names") or []),
            }
        logger.warning("[firewall] LLM returned unmatched title: %r", ms)
        logger.info("[KG-RAG DEBUG] firewall: no match (title not in local map)")
        return None
    except Exception as e:
        logger.warning("[firewall] match_firewall failed: %s", e)
        return None
