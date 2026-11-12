# -*- coding: utf-8 -*-
"""防火墙：《神圣的辩理》篇题匹配与上下文注入（新测试台）。"""
from __future__ import annotations

import json
import logging
from typing import Any

from t35test.kg.llm_pricing import register_llm_usage

logger = logging.getLogger("t35test")

# 【4.0】防火墙资料改读图谱 neo4j-v4：词条上的「神圣的辩理」标注（devine_argument），73 个篇题；不再读 ES panai_new_dispute。
# 判断分三档：命中-主要内容 → 放该篇整篇纲目；命中-只是提到 → 放一句说明；未命中 → 不放。不限篇数与个数。

_neo4j_client: Any = None
_firewall_data: dict[str, dict[str, Any]] = {}
_firewall_titles: list[str] = []

FIREWALL_MATCH_PROMPT = """以下是 {count} 个《神圣的辩理》篇题：
{titles_block}

用户主题：{query}

请判断用户主题与《神圣的辩理》篇题的关系：
- 主要内容：这篇纲目主要讲的真理内容，就是某篇题所讨论的真理点（同一件事）。用经历性语言表达的主题，若其所经历的真理内容与某篇题是同一件事，也算主要。
- 非主要内容，只是提到：纲目主要讲的不是这个篇题，但主题会明显涉及这个篇题所讨论的真理点。
- 仅仅词语相似、没有实际涉及的，都不算。

只返回 JSON：{{"main": ["篇题原文", ...], "mentioned": ["篇题原文", ...]}}
- main 没有就是 []
- mentioned 不得包含 main 里的篇题，没有就是 []
不得有任何其他文字、解释或 markdown。"""

FIREWALL_MATCH_MODEL = "claude-opus-5-5"


def load_firewall(neo4j_client: Any = None) -> None:
    """启动时从图谱读《神圣的辩理》：按篇题归并（一句说明 description、整篇纲目 outline、所挂词条名）。
    读取失败或没有资料时不报错，防火墙本次不生效；之后 match_firewall 会再试着读一次。"""
    global _neo4j_client, _firewall_data, _firewall_titles
    if neo4j_client is not None:
        _neo4j_client = neo4j_client
    _firewall_data = {}
    _firewall_titles = []
    if _neo4j_client is None:
        logger.warning("[firewall] no neo4j client, loaded 0 titles")
        return
    rows = _neo4j_client.get_divine_arguments()
    for row in rows:
        try:
            obj = json.loads(row.get("raw") or "{}")
        except (TypeError, json.JSONDecodeError):
            logger.warning("[firewall] devine_argument JSON parse failed: name=%r", row.get("name"))
            continue
        name = str(row.get("name") or "").strip()
        for key in sorted(obj):
            for item in obj.get(key) or []:
                title = str((item or {}).get("title") or "").strip()
                if not title:
                    continue
                desc = str(item.get("description") or "").strip()
                outline = str(item.get("outline") or "").strip()
                doc = _firewall_data.get(title)
                if doc is None:
                    doc = {"title": title, "note": desc, "outline": outline, "names": []}
                    _firewall_data[title] = doc
                    _firewall_titles.append(title)
                else:
                    if not doc["note"] and desc:
                        doc["note"] = desc
                    if not doc["outline"] and outline:
                        doc["outline"] = outline
                # 括号节点（same_as）不算词条，只记正式词条名
                if name and not row.get("same_as") and name not in doc["names"]:
                    doc["names"].append(name)

    _firewall_titles.sort()
    logger.info(
        "[firewall] loaded %s titles / %s names from neo4j-v4 devine_argument",
        len(_firewall_titles),
        sum(len(d["names"]) for d in _firewall_data.values()),
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


def _as_title_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for t in v:
        s = str(t or "").strip()
        if s and s.lower() != "null" and s not in out:
            out.append(s)
    return out


async def match_firewall(
    query: str,
    llm_caller: Any,
    *,
    llm_calls: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]] | None:
    """
    判断用户主题与《神圣的辩理》篇题的关系（三档）。
    llm_caller: async function(prompt, model, temperature, max_tokens) -> (text, usage)
    llm_calls: 若提供，则将本次调用的 token/费用并入 KG-RAG 计价列表（step 名为 firewall）。
    返回: {"main": [doc...], "mentioned": [doc...]}；两者都为空、或出错时返回 None（当作未命中）。
    doc = {"title", "note", "outline", "names"}
    """
    if not _firewall_titles and _neo4j_client is not None:
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
            prompt, FIREWALL_MATCH_MODEL, temperature=0, max_tokens=600
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

        def _docs(titles: list[str]) -> list[dict[str, Any]]:
            out = []
            for t in titles:
                doc = get_firewall_doc(t)
                if doc:
                    out.append({
                        "title": doc["title"],
                        "note": doc["note"],
                        "outline": doc["outline"],
                        "names": list(doc.get("names") or []),
                    })
                else:
                    logger.warning("[firewall] LLM returned unknown title: %r", t)
            return out

        main = _docs(_as_title_list(parsed.get("main")))
        main_titles = {d["title"] for d in main}
        mentioned = [d for d in _docs(_as_title_list(parsed.get("mentioned"))) if d["title"] not in main_titles]
        if not main and not mentioned:
            logger.info("[KG-RAG DEBUG] firewall: no match (main and mentioned empty)")
            return None
        logger.info(
            "[firewall] matched main=%r mentioned=%r",
            [d["title"] for d in main],
            [d["title"] for d in mentioned],
        )
        return {"main": main, "mentioned": mentioned}
    except Exception as e:
        logger.warning("[firewall] match_firewall failed: %s", e)
        return None
