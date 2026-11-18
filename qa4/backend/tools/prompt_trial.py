# -*- coding: utf-8 -*-
"""草稿通道试答工具。

默认 / --dry-run：假模型 + 假检索，不联网。
--live：需 QA4_ANTHROPIC_API_KEY，受 --budget-usd 约束。
--retrieval {fake,real}：默认 fake；real 复用 main/deps 真实 ES+嵌入+重排。

输出与临时库一律写 G:\\PanAI4.0专用\\logs\\prompt_trial\\（不进仓库）。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
_QA4 = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_CSV = _QA4 / "notes" / "dev_questions_draft.csv"
DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\prompt_trial")

# 可选列：缺列不报错
_OPTIONAL_COLS = ("预期题型（假设）", "是否拆分（假设）", "限定", "备注", "上文", "优先级")

HINT_SPLIT = "\n\n【试验】本题请判定 complex=true，并拆成 2–4 个子问题。"
HINT_NOSPLIT = "\n\n【试验】本题请判定 complex=false，只给 1 个子问题。"

PRICES_PATH = _BACKEND / "config" / "prices.json"

_SK_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b")


def redact_secrets(text: str) -> str:
    """脱敏：环境变量中的 API 密钥 + sk-… 形态串 → ***。"""
    s = str(text or "")
    key = (os.environ.get("QA4_ANTHROPIC_API_KEY") or "").strip()
    if key:
        s = s.replace(key, "***")
    s = _SK_RE.sub("***", s)
    return s


def format_error(exc: BaseException) -> dict[str, Any]:
    """异常类型、消息、最后 8 帧简化栈（均已脱敏）。"""
    import traceback

    tb = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    frames = tb[-8:] if len(tb) > 8 else tb
    stack = [
        f"{f.filename}:{f.lineno} {f.name}"
        for f in frames
    ]
    return {
        "type": type(exc).__name__,
        "message": redact_secrets(str(exc)),
        "stack": [redact_secrets(x) for x in stack],
    }


def resolve_prices_path(path: Path | None = None) -> Path:
    """显式路径 > 环境变量 QA4_PRICES_PATH > 默认 config/prices.json。"""
    if path is not None:
        return Path(path)
    env = (os.environ.get("QA4_PRICES_PATH") or "").strip()
    if env:
        return Path(env)
    return PRICES_PATH


def load_prices(path: Path | None = None) -> dict[str, Any]:
    p = resolve_prices_path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def prices_incomplete(prices: dict[str, Any]) -> bool:
    """任一模型缺价或 status=待核实 → 视为未就绪。"""
    if str(prices.get("status") or "") == "待核实":
        return True
    models = prices.get("models") or {}
    if not models:
        return True
    for _name, row in models.items():
        if not isinstance(row, dict):
            return True
        for k in ("input", "output", "cache_write_5m", "cache_read"):
            if row.get(k) is None:
                return True
    return False


def _model_rates(prices: dict[str, Any], model: Optional[str]) -> Optional[dict[str, Any]]:
    models = prices.get("models") or {}
    if model and model in models:
        return models[model]
    # 后缀/别名宽松匹配
    if model:
        for k, v in models.items():
            if model.endswith(k) or k.endswith(model) or model in k or k in model:
                return v
    return None


def _numeric_tokens(val: Any) -> Optional[int]:
    """可识别的数字 token 数；bool 不当数字。"""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return int(val)
    return None


def parse_cache_creation(usage: dict[str, Any]) -> dict[str, Any]:
    """解析 usage 的 cache_creation / cache_creation_input_tokens。

    返回：
      tokens_5m: 可按 5 分钟档计价的写入量
      usage_unparsed: 有未识别或未完整计价部分
      price_missing_1h: 出现 1h 缓存写入但价格表无 1h 档（本工具亦不计价 1h）
    """
    out = {"tokens_5m": 0, "usage_unparsed": False, "price_missing_1h": False}
    total = _numeric_tokens(usage.get("cache_creation_input_tokens"))
    cc = usage.get("cache_creation")

    if total is not None:
        out["tokens_5m"] = total
        if isinstance(cc, dict):
            one_h = _numeric_tokens(cc.get("ephemeral_1h_input_tokens"))
            if one_h is not None and one_h > 0:
                out["usage_unparsed"] = True
                out["price_missing_1h"] = True
            for k, v in cc.items():
                if k not in {"ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"} and v not in (None, 0, ""):
                    out["usage_unparsed"] = True
        elif cc is not None and _numeric_tokens(cc) is None and not isinstance(cc, dict):
            out["usage_unparsed"] = True
        return out

    if cc is None:
        return out
    n = _numeric_tokens(cc)
    if n is not None:
        out["tokens_5m"] = n
        return out
    if isinstance(cc, dict):
        known = {"ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"}
        five = _numeric_tokens(cc.get("ephemeral_5m_input_tokens"))
        one_h = _numeric_tokens(cc.get("ephemeral_1h_input_tokens"))
        if "ephemeral_5m_input_tokens" in cc and five is None and cc.get("ephemeral_5m_input_tokens") is not None:
            out["usage_unparsed"] = True
        if five is not None:
            out["tokens_5m"] = five
        if one_h is not None and one_h > 0:
            out["usage_unparsed"] = True
            out["price_missing_1h"] = True
        elif "ephemeral_1h_input_tokens" in cc and cc.get("ephemeral_1h_input_tokens") is not None and one_h is None:
            out["usage_unparsed"] = True
        for k, v in cc.items():
            if k not in known and v not in (None, 0, ""):
                out["usage_unparsed"] = True
        return out
    # 未知结构
    out["usage_unparsed"] = True
    return out


def parse_usage_counts(usage: dict[str, Any]) -> dict[str, Any]:
    """从一步 usage 抽出 input/output/cache_*；不抛异常。"""
    u = dict(usage or {}) if isinstance(usage, dict) else {}
    inp = _numeric_tokens(u.get("input_tokens") if u.get("input_tokens") is not None else u.get("input"))
    out_n = _numeric_tokens(u.get("output_tokens") if u.get("output_tokens") is not None else u.get("output"))
    cread = _numeric_tokens(
        u.get("cache_read_input_tokens") if u.get("cache_read_input_tokens") is not None else u.get("cache_read")
    )
    cache = parse_cache_creation(u)
    unparsed = bool(cache["usage_unparsed"])
    # input/output/cache_read 若存在却非数字 → unparsed
    for key, raw in (
        ("input", u.get("input_tokens", u.get("input"))),
        ("output", u.get("output_tokens", u.get("output"))),
        ("cache_read", u.get("cache_read_input_tokens", u.get("cache_read"))),
    ):
        if raw is not None and _numeric_tokens(raw) is None and not isinstance(raw, dict):
            unparsed = True
        if isinstance(raw, dict):
            unparsed = True
    return {
        "input": int(inp or 0),
        "output": int(out_n or 0),
        "cache_creation": int(cache["tokens_5m"] or 0),
        "cache_read": int(cread or 0),
        "usage_unparsed": unparsed,
        "price_missing_1h": bool(cache["price_missing_1h"]),
    }


def _est_usd_for_usage(
    usage: dict[str, Any],
    *,
    model: Optional[str],
    prices: dict[str, Any],
) -> tuple[Optional[float], bool, bool, bool]:
    """返回 (估算美元或 None, price_missing, usage_unparsed, price_missing_1h)。

    按已识别部分计价；1h 缓存写入无法计价时只打标，不抛异常。
    """
    counts = parse_usage_counts(usage)
    rates = _model_rates(prices, model)
    if rates is None:
        return None, True, counts["usage_unparsed"], counts["price_missing_1h"]
    keys = ("input", "output", "cache_write_5m", "cache_read")
    if any(rates.get(k) is None for k in keys):
        return None, True, counts["usage_unparsed"], counts["price_missing_1h"]
    usd = (
        counts["input"] * float(rates["input"])
        + counts["output"] * float(rates["output"])
        + counts["cache_creation"] * float(rates["cache_write_5m"])
        + counts["cache_read"] * float(rates["cache_read"])
    ) / 1_000_000.0
    return usd, False, counts["usage_unparsed"], counts["price_missing_1h"]


_REAL_RETRIEVAL_ENV = (
    "QA4_ES_URL",
    "QA4_ES_PASSWORD",
    "QA4_EMBED_BASE_URL",
    "QA4_EMBED_API_KEY",
    "QA4_RERANK_BASE_URL",
    "QA4_RERANK_API_KEY",
    "QA4_NEO4J_URI",
    "QA4_NEO4J_PASSWORD",
)

_LIVE_SECRET_ENV = ("QA4_ANTHROPIC_API_KEY",)

_FILL_ME = "__FILL_ME__"


def load_qa4_env_file_if_set() -> Optional[Path]:
    """若进程已设 QA4_ENV_FILE：复用 settings._load_env_file 载入（不覆盖已有环境变量）。

    未设置时不做任何事。文件不存在则抛 FileNotFoundError。
    """
    raw = (os.environ.get("QA4_ENV_FILE") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        raise FileNotFoundError(f"QA4_ENV_FILE 指向的文件不存在：{path}")
    from config.settings import _load_env_file

    _load_env_file(path)
    return path


def env_missing(names: tuple[str, ...] | list[str]) -> list[str]:
    """值为空的变量名（不读、不打印值）。"""
    return [n for n in names if not (os.environ.get(n) or "").strip()]


def env_unfilled(names: tuple[str, ...] | list[str]) -> list[str]:
    """值为 __FILL_ME__（或 URL 中含该占位）的变量名。"""
    out: list[str] = []
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v == _FILL_ME or _FILL_ME in v:
            out.append(n)
    return out


def missing_real_retrieval_env() -> list[str]:
    """真实检索缺少的环境变量名（不读、不打印值）。"""
    return env_missing(_REAL_RETRIEVAL_ENV)


def unfilled_real_retrieval_env() -> list[str]:
    """真实检索相关仍为 __FILL_ME__ 的变量名。"""
    return env_unfilled(_REAL_RETRIEVAL_ENV)


def parse_history(raw: str) -> list[dict[str, str]]:
    """把题集「上文」列解析为 pipeline history 列表。

    接受格式（见 notes/stage4_prompt_contracts.md）：
    - 标准多轮：连续的「问：…\\n答：…」块（块与块之间可空行或以「问：」起头）
    - 单轮简写：「上一轮问：…答：…」
    - 多轮简写：上述简写用「---」分隔
    """
    text = (raw or "").strip()
    if not text:
        return []
    turns: list[dict[str, str]] = []

    if "问：" in text:
        chunks = re.split(r"\n(?=问：)", text)
        for ch in chunks:
            ch = ch.strip()
            if not ch.startswith("问："):
                continue
            body = ch[2:]
            if "\n答：" in body:
                q, a = body.split("\n答：", 1)
            elif "答：" in body:
                q, a = body.split("答：", 1)
            else:
                q, a = body, ""
            turns.append({"question": q.strip(), "answer": a.strip()})
        if turns:
            return turns

    parts = [p.strip() for p in re.split(r"\n---\n|\n---\s*\n", text) if p.strip()]
    for part in parts:
        m = re.match(r"上一轮问[：:]\s*(.+?)答[：:]\s*(.+)\s*$", part, re.S)
        if m:
            turns.append({"question": m.group(1).strip(), "answer": m.group(2).strip()})
            continue
        m2 = re.match(r"问[：:]\s*(.+?)答[：:]\s*(.+)\s*$", part, re.S)
        if m2:
            turns.append({"question": m2.group(1).strip(), "answer": m2.group(2).strip()})
    return turns


def load_questions(path: Path) -> list[dict[str, str]]:
    """UTF-8-SIG CSV。必有有效 id + 问题；可选列缺省不报错。"""
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = (row.get("id") or "").strip()
            if not qid or qid.startswith("_"):
                continue
            q = (row.get("问题") or "").strip()
            if not q:
                continue
            # 规范化：缺可选列当空串
            out = {k: (row.get(k) or "") for k in (reader.fieldnames or [])}
            out["id"] = qid
            out["问题"] = q
            for col in _OPTIONAL_COLS:
                out.setdefault(col, "")
            rows.append(out)
    return rows


def filter_questions(
    rows: list[dict[str, str]],
    *,
    priority: Optional[str],
    only_ids: Optional[list[str]],
    max_questions: int,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """先按 priority / only-ids 过滤，再按 max_questions 截断。"""
    filtered = list(rows)
    if only_ids:
        want = {x.strip() for x in only_ids if x.strip()}
        filtered = [r for r in filtered if r.get("id") in want]
    if priority:
        p = priority.strip()
        filtered = [r for r in filtered if (r.get("优先级") or "").strip() == p]
    before_cap = len(filtered)
    if max_questions > 0 and len(filtered) > max_questions:
        kept = filtered[:max_questions]
    else:
        kept = filtered
    meta = {
        "source_n": len(rows),
        "after_filter": before_cap,
        "kept": len(kept),
        "truncated": max(0, before_cap - len(kept)),
    }
    return kept, meta


def install_force_split(llm: Any, mode: str) -> None:
    """仅在 prompt_trial 内：给 step3 的 user 消息末尾追加试验提示。不改 pipeline。"""
    if mode == "auto":
        return
    hint = HINT_SPLIT if mode == "split" else HINT_NOSPLIT
    orig = llm.complete_json

    async def wrapped(role, system, messages, *, step, max_tokens=None, cache=None):
        msgs = messages
        if step == "step3" and messages:
            msgs = [dict(m) for m in messages]
            for m in reversed(msgs):
                if m.get("role") == "user":
                    m["content"] = str(m.get("content") or "") + hint
                    break
        return await orig(role, system, msgs, step=step, max_tokens=max_tokens, cache=cache)

    llm.complete_json = wrapped  # type: ignore[method-assign]


def _plan_summary(plan_ev: Optional[dict[str, Any]], ctx: Any = None) -> dict[str, Any]:
    """完整 plan 摘要：子问题含 angle/scope/synthesis；含 understanding。"""
    src = plan_ev or {}
    understanding = src.get("understanding")
    if understanding is None and ctx is not None and getattr(ctx, "plan", None):
        understanding = ctx.plan.understanding
    subs_src = src.get("subquestions")
    if not subs_src and ctx is not None and getattr(ctx, "plan", None):
        subs_src = [sq.model_dump() for sq in ctx.plan.subquestions]
    subs = []
    for sq in subs_src or []:
        if not isinstance(sq, dict):
            continue
        subs.append(
            {
                "text": sq.get("text"),
                "qtype": sq.get("qtype"),
                "scope": sq.get("scope"),
                "angle": sq.get("angle"),
                "synthesis": bool(sq.get("synthesis")),
                "depends_on": sq.get("depends_on") or [],
                "compare_objects": sq.get("compare_objects") or [],
            }
        )
    return {
        "main_type": src.get("main_type") or (ctx.plan.main_type if ctx and ctx.plan else None),
        "complex": src.get("complex") if "complex" in src else (ctx.plan.complex if ctx and ctx.plan else None),
        "sensitive": src.get("sensitive") if "sensitive" in src else (ctx.plan.sensitive if ctx and ctx.plan else None),
        "understanding": understanding,
        "restrictions": src.get("restrictions")
        or ([r.model_dump() for r in ctx.plan.restrictions] if ctx and ctx.plan else []),
        "locator": src.get("locator")
        or (ctx.plan.locator.model_dump() if ctx and ctx.plan and ctx.plan.locator else None),
        "subquestions": subs,
    }


def _layers_payload(ctx: Any) -> dict[str, Any]:
    """第 1–5 层词。逐词丢弃明细 pipeline 未暴露，仅有 step5 计数。"""
    by_subq = []
    for i, l in enumerate(getattr(ctx, "layers", None) or []):
        by_subq.append(
            {
                "subq": i,
                "layer1": list(getattr(l, "layer1", None) or []),
                "revelation": list(getattr(l, "revelation", None) or []),
                "intrinsic": list(getattr(l, "intrinsic", None) or []),
                "experience": list(getattr(l, "experience", None) or []),
                "practice": list(getattr(l, "practice", None) or []),
                "object_of": dict(getattr(l, "object_of", None) or {}),
            }
        )
    step5 = (getattr(ctx, "steps", None) or {}).get("step5") or {}
    step4 = (getattr(ctx, "steps", None) or {}).get("step4") or {}
    return {
        "by_subq": by_subq,
        "dropped": [],
        "dropped_note": (
            "pipeline 未逐词记录丢弃原因（step04/step05 只写计数）；"
            "需改 pipeline 才能列出「不在名单/超上限/与其他层重复/不在原文」的逐词明细"
        ),
        "dropped_stats": {
            "step4_model_words": step4.get("model_words"),
            "step4_kept_words": step4.get("kept_words"),
            "step5_dropped_not_in_list": step5.get("dropped_not_in_list"),
            "step5_dropped_dup": step5.get("dropped_dup"),
        },
    }


def _retrieval_payload(ctx: Any) -> list[dict[str, Any]]:
    out = []
    by_subq = getattr(ctx, "passages_by_subq", None) or {}
    cov = getattr(ctx, "retrieval_cov", None) or {}
    verdicts = {getattr(v, "subq", i): v for i, v in enumerate(getattr(ctx, "verdicts", None) or [])}
    keys = sorted({int(k) for k in list(by_subq.keys()) + [int(x) for x in cov.keys() if str(x).isdigit()]})
    if not keys and getattr(ctx, "plan", None):
        keys = list(range(len(ctx.plan.subquestions)))
    for i in keys:
        passages = list(by_subq.get(i) or [])
        v = verdicts.get(i)
        kept_n = 0
        if v is not None:
            kept_n = sum(1 for ok in (getattr(v, "keep", None) or {}).values() if ok)
        index_dist: dict[str, int] = {}
        for p in passages:
            idx = str(getattr(p, "index", "") or "")
            index_dist[idx] = index_dist.get(idx, 0) + 1
        meta = cov.get(str(i)) or cov.get(i) or {}
        out.append(
            {
                "subq": i,
                "retrieved": len(passages),
                "kept": kept_n,
                "index_dist": index_dist,
                "coverage": meta.get("coverage"),
                "none_flag": meta.get("none_flag"),
                "degraded": meta.get("degraded"),
            }
        )
    return out


def _verdicts_payload(ctx: Any) -> list[dict[str, Any]]:
    out = []
    for v in getattr(ctx, "verdicts", None) or []:
        keep = getattr(v, "keep", None) or {}
        out.append(
            {
                "subq": getattr(v, "subq", None),
                "overall": getattr(v, "overall", None),
                "note": getattr(v, "note", None) or "",
                "kept_passages": sum(1 for ok in keep.values() if ok),
                "retried": bool(getattr(v, "retried", False)),
                "defaulted": bool(getattr(v, "defaulted", False)),
            }
        )
    return out


def _quote_fail_details(done: Optional[dict[str, Any]], ctx: Any) -> list[dict[str, Any]]:
    raw = list((done or {}).get("quote_checks") or [])
    if not raw and ctx is not None and getattr(ctx, "answer", None):
        raw = [c.model_dump() for c in (ctx.answer.quote_checks or [])]
    out = []
    for c in raw:
        if not isinstance(c, dict) or c.get("ok") is not False:
            continue
        quote = str(c.get("quote") or "")
        out.append(
            {
                "quote_preview": quote[:30],
                "reason": "未在同一段落按原文顺序找到连续子串（含省略号两半）",
                "passage_n": c.get("passage_n"),
                "parts": c.get("parts"),
            }
        )
    return out


def _parse_degraded(reasons: list[str]) -> list[dict[str, str]]:
    out = []
    for r in reasons or []:
        s = str(r)
        if ":" in s:
            step, reason = s.split(":", 1)
            out.append({"step": step.strip(), "reason": reason.strip()})
        else:
            out.append({"step": "unknown", "reason": s})
    return out


def _normalize_tokens(ctx: Any) -> tuple[dict[str, dict[str, Any]], bool, bool]:
    """每步 {model, input, output, cache_creation, cache_read}。

    返回 (tokens, any_usage_unparsed, any_price_missing_1h)。
    cache_creation 嵌套 dict / 未知结构不抛异常。
    """
    tokens_raw = dict(getattr(ctx, "tokens", None) or {})
    models = dict(getattr(ctx, "models", None) or {})
    out: dict[str, dict[str, Any]] = {}
    any_unparsed = False
    any_1h = False
    for step, usage in tokens_raw.items():
        u = dict(usage or {}) if isinstance(usage, dict) else {}
        if usage is not None and not isinstance(usage, dict):
            any_unparsed = True
        counts = parse_usage_counts(u)
        if counts["usage_unparsed"]:
            any_unparsed = True
        if counts["price_missing_1h"]:
            any_1h = True
        m = (models.get(step) or {}).get("request_model") or (models.get(step) or {}).get("response_model")
        out[step] = {
            "model": m,
            "input": counts["input"],
            "output": counts["output"],
            "cache_creation": counts["cache_creation"],
            "cache_read": counts["cache_read"],
            "usage_unparsed": counts["usage_unparsed"],
            "price_missing_1h": counts["price_missing_1h"],
        }
    return out, any_unparsed, any_1h


def _layer1_by_subq(ctx: Any) -> list[list[str]]:
    layers = getattr(ctx, "layers", None) or []
    return [list(getattr(l, "layer1", None) or []) for l in layers]


def _year_or_volume_from_passage(p: Any) -> Any:
    meta = dict(getattr(p, "meta", None) or {})
    y = meta.get("year")
    if y is None or y == "":
        return None
    ye = meta.get("year_end")
    if ye not in (None, "") and ye != y:
        return f"{y}-{ye}"
    return y


def _citation_row_from_passage(p: Any) -> dict[str, Any]:
    """送入第8步的段落 → JSONL citations 一项。"""
    meta = dict(getattr(p, "meta", None) or {})
    loc = dict(getattr(p, "location", None) or {})
    text = str(getattr(p, "text", "") or "")
    source = getattr(p, "book_title", None) or loc.get("source_zh") or None
    if source == "":
        source = None
    title = getattr(p, "message_title", None) or None
    if title == "":
        title = None
    author = meta.get("author")
    if author == "":
        author = None
    chunk_id = getattr(p, "id", None) or None
    if chunk_id == "":
        chunk_id = None
    index = getattr(p, "index", None) or None
    if index == "":
        index = None
    return {
        "n": getattr(p, "number", None),
        "index": index,
        "source": source,
        "title": title,
        "author": author,
        "year_or_volume": _year_or_volume_from_passage(p),
        "chunk_id": chunk_id,
        "text_head": text[:60],
    }


def _citations_for_log(ctx: Any) -> list[dict[str, Any]]:
    """与 step08 相同：kept_passages，若空则回退 ctx.passages。"""
    if ctx is None:
        return []
    from pipeline.step07_judge import kept_passages

    passages = kept_passages(ctx) or list(getattr(ctx, "passages", None) or [])
    return [_citation_row_from_passage(p) for p in passages]


def _cited_numbers_in_order(text: str) -> list[int]:
    """正文 [n] 按首次出现顺序去重（与 citations.extract_refs 一致）。"""
    from pipeline.citations import extract_refs

    return list(extract_refs(text or ""))


def _step_timings_ms(ctx: Any, deps: Any) -> dict[str, Any]:
    """ctx.timings_ms + 流式首字（若 deps.llm.last_stream_result.ttft_s 可得）。"""
    out: dict[str, Any] = dict(getattr(ctx, "timings_ms", None) or {}) if ctx else {}
    first_token_ms: Optional[int] = None
    llm = getattr(deps, "llm", None) if deps is not None else None
    res = getattr(llm, "last_stream_result", None) if llm is not None else None
    ttft = getattr(res, "ttft_s", None) if res is not None else None
    if ttft is not None:
        try:
            first_token_ms = int(round(float(ttft) * 1000))
        except (TypeError, ValueError):
            first_token_ms = None
    out["first_token_ms"] = first_token_ms
    return out


def _rewrite_info(ctx: Any, history: list[dict[str, str]], deps: Any) -> dict[str, Any]:
    """改写是否带上文：轮数、是否跳过/调用、step2 输入字符数。"""
    hist = list(history or [])
    history_turns_passed = len(hist)
    rewrite_skipped = not bool(hist)
    rewrite_called = False
    step2_input_chars: Optional[int] = None

    if ctx is not None:
        step2 = (getattr(ctx, "steps", None) or {}).get("step2") or {}
        if "history_turns" in step2 and step2.get("history_turns") is not None:
            try:
                history_turns_passed = int(step2["history_turns"])
            except (TypeError, ValueError):
                pass
        if step2.get("skipped"):
            rewrite_skipped = True
            rewrite_called = False
        elif hist:
            rewrite_skipped = False
            rewrite_called = True
        if rewrite_called:
            try:
                from pipeline.step02_rewrite import build_history, history_text

                cfg = getattr(deps, "cfg", None) or {}
                turns = getattr(ctx, "history_for_rewrite", None)
                if not turns:
                    turns = build_history(
                        hist,
                        turns=int(cfg.get("history_turns", 3)),
                        answer_chars=int(cfg.get("history_answer_chars", 300)),
                    )
                tpl = deps.prompts.get("step2") if deps is not None else None
                if tpl is not None:
                    prompt = tpl.render(
                        history=history_text(list(turns)),
                        question=getattr(ctx, "question_orig", "") or "",
                    )
                    step2_input_chars = len(prompt)
            except Exception:
                step2_input_chars = None
    elif hist:
        rewrite_skipped = False
        rewrite_called = True

    return {
        "history_turns_passed": history_turns_passed,
        "rewrite_skipped": rewrite_skipped,
        "rewrite_called": rewrite_called,
        "step2_input_chars": step2_input_chars,
    }


async def _run_one(
    deps: Any,
    *,
    question: str,
    history: list[dict[str, str]],
    force_split: str,
    prices: dict[str, Any],
) -> dict[str, Any]:
    from pipeline import step09_record
    from pipeline.orchestrator import run_pipeline

    captured: dict[str, Any] = {}
    orig_write = step09_record.write_trace

    def _capture(ctx, d):
        captured["ctx"] = ctx
        return orig_write(ctx, d)

    step09_record.write_trace = _capture  # type: ignore[assignment]
    plan_ev = None
    done = None
    t0 = time.perf_counter()
    try:
        async for ev in run_pipeline(deps, question=question, history=history):
            if ev.get("event") == "plan":
                plan_ev = ev
            if ev.get("event") == "done":
                done = ev
    finally:
        step09_record.write_trace = orig_write  # type: ignore[assignment]

    ctx = captured.get("ctx")
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    tokens: dict[str, dict[str, Any]] = {}
    cost_sum = 0.0
    price_missing = False
    usage_unparsed = False
    price_missing_1h = False
    cost_unknown = False
    try:
        if ctx:
            tokens, usage_unparsed, price_missing_1h = _normalize_tokens(ctx)
        for _step, tu in tokens.items():
            part, miss, unp, miss_1h = _est_usd_for_usage(
                tu, model=tu.get("model"), prices=prices
            )
            if unp:
                usage_unparsed = True
            if miss_1h:
                price_missing_1h = True
            if miss or part is None:
                price_missing = True
            else:
                cost_sum += part
    except Exception:
        # 成本路径不得拖垮整题记录
        price_missing = True
        usage_unparsed = True
        cost_unknown = True
        tokens = tokens or {}

    # 缺价 / 有 1h 未计价 / 成本路径异常 → 整题花费未知（仍可保留已识别部分的 est）
    if price_missing or price_missing_1h or cost_unknown:
        cost_unknown = True

    rewrite_skipped = not bool(history)
    rewritten = question
    if ctx is not None:
        rewritten = getattr(ctx, "question", None) or question
        step2 = (getattr(ctx, "steps", None) or {}).get("step2") or {}
        if step2.get("skipped"):
            rewrite_skipped = True

    q_fail = _quote_fail_details(done, ctx)
    complex_val = bool((plan_ev or {}).get("complex")) if plan_ev else bool(
        ctx.plan.complex if ctx and ctx.plan else False
    )
    force_failed = False
    if force_split == "split" and not complex_val:
        force_failed = True
    if force_split == "nosplit" and complex_val:
        force_failed = True

    cites = list((done or {}).get("citations") or [])
    if not cites and ctx is not None and getattr(ctx, "answer", None):
        cites = list(ctx.answer.citations or [])

    answer_text = (done or {}).get("answer") or ""
    if not answer_text and ctx is not None and getattr(ctx, "answer", None):
        answer_text = getattr(ctx.answer, "text", "") or ""

    citations_log = _citations_for_log(ctx)
    cited_order = _cited_numbers_in_order(answer_text)
    timings_log = _step_timings_ms(ctx, deps)
    rewrite_log = _rewrite_info(ctx, history, deps)

    return {
        "question": question,
        "rewritten_question": rewritten,
        "rewrite_skipped": rewrite_skipped,
        "rewrite_info": rewrite_log,
        "plan": _plan_summary(plan_ev, ctx),
        "layer1_words": _layer1_by_subq(ctx) if ctx else [],
        "layers": _layers_payload(ctx) if ctx else {"by_subq": [], "dropped": [], "dropped_note": "no ctx", "dropped_stats": {}},
        "retrieval": _retrieval_payload(ctx) if ctx else [],
        "verdicts": _verdicts_payload(ctx) if ctx else [],
        "answer": answer_text,
        "quote_checks_ok_false": len(q_fail),
        "quote_checks_failed": q_fail,
        "degraded_reasons": _parse_degraded(list(getattr(ctx, "degraded_reasons", None) or [])),
        "cache_hit": bool((done or {}).get("cache_hit") or (getattr(ctx, "cache_hit", False) if ctx else False)),
        "citations": citations_log,
        "cited_numbers_in_order": cited_order,
        "citations_count": len(cites),
        "step_timings_ms": timings_log,
        "tokens": tokens,
        "est_cost_usd": None if price_missing else round(cost_sum, 6),
        "price_missing": price_missing,
        "usage_unparsed": usage_unparsed,
        "price_missing_1h": price_missing_1h,
        "cost_unknown": cost_unknown,
        "elapsed_ms": (done or {}).get("elapsed_ms") or elapsed_ms,
        "force_failed": force_failed,
        "degraded": bool((done or {}).get("degraded")),
        "main_type": (done or {}).get("main_type") or (plan_ev or {}).get("main_type"),
    }


def _build_deps(*, live: bool, retrieval: str, work: Path) -> Any:
    """装配流水线依赖。retrieval: fake|real（CLI）；settings 内映射为 fake|live。"""
    from config import get_settings, reset_settings_cache
    from core.redis_store import MemoryStore
    from pipeline.deps import build_deps

    os.environ.setdefault("QA4_PROMPT_CHANNEL", "draft")
    if live:
        os.environ.pop("QA4_LLM_MODE", None)
    else:
        os.environ["QA4_LLM_MODE"] = "fake"
    # deps.build_deps 读 settings.retrieval_mode ∈ {fake, live}
    os.environ["QA4_RETRIEVAL_MODE"] = "live" if retrieval == "real" else "fake"
    os.environ.setdefault("QA4_DATA_DIR", str(_QA4 / "data"))
    os.environ.setdefault("QA4_LOOKUP_DIR", str(_QA4 / "data" / "lookups"))
    os.environ.setdefault("QA4_GRAPH_ANNOTATIONS_DIR", str(_QA4 / "data" / "graph_annotations"))
    os.environ.setdefault("QA4_JWT_SECRET", "prompt-trial-jwt")

    reset_settings_cache()
    settings = get_settings(require_runtime=False)
    work.mkdir(parents=True, exist_ok=True)
    settings.traces_db_path = work / "traces.db"
    store = MemoryStore(prefix=f"pt:{int(time.time())}:")

    if retrieval == "real":
        from core.es_client import EsClient
        from core.neo4j_client import Neo4jClient

        # 与 main.create_app 相同：真实 EsClient / Neo4jClient，再交给 build_deps
        es = EsClient(
            settings.es_url,
            settings.es_user,
            settings.es_secret,
            verify=settings.es_verify,
            index_map=settings.index_map,
        )
        neo = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_secret)
        deps = build_deps(
            settings,
            store=store,
            es=es,
            neo4j=neo,
            traces_db=work / "traces.db",
        )
    else:
        from core.es_client import FakeEsClient
        from core.neo4j_client import FakeNeo4jClient

        deps = build_deps(
            settings,
            store=store,
            es=FakeEsClient(reachable=True),
            neo4j=FakeNeo4jClient(reachable=True),
            traces_db=work / "traces.db",
        )
    return deps


def _write_compare_md(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# prompt_trial --compare（split vs nosplit）",
        "",
        "| id | split 正文（截断） | nosplit 正文（截断） | split$ | nosplit$ |",
        "|---|---|---|---:|---:|",
    ]
    for r in rows:
        sid = r.get("id", "")
        a = str(r.get("split_answer") or "").replace("|", "\\|").replace("\n", " ")[:120]
        b = str(r.get("nosplit_answer") or "").replace("|", "\\|").replace("\n", " ")[:120]
        lines.append(
            f"| {sid} | {a} | {b} | {r.get('split_cost', 0)} | {r.get('nosplit_cost', 0)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="qa4 草稿通道试答（默认 dry-run / 假模型）")
    ap.add_argument("--csv", type=Path, default=None, help="题集 CSV（兼容旧参数）")
    ap.add_argument("--questions-file", type=Path, default=None, help="题集 CSV（UTF-8-SIG），优先于 --csv")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-questions", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--live", action="store_true", default=False)
    ap.add_argument("--budget-usd", type=float, default=1.0)
    ap.add_argument("--priority", type=str, default=None, help="只跑「优先级」列等于该值的题")
    ap.add_argument("--only-ids", type=str, default=None, help="逗号分隔 id 白名单")
    ap.add_argument(
        "--force-split",
        choices=("auto", "split", "nosplit"),
        default="auto",
        help="试验提示追加到 step3 user；不符则 force_failed",
    )
    ap.add_argument(
        "--compare",
        action="store_true",
        default=False,
        help="同一题集各跑 split 与 nosplit，写并排 Markdown",
    )
    ap.add_argument(
        "--render-only",
        action="store_true",
        default=False,
        help="仅渲染提示词做变量检查（旧 dry-run 行为，不跑流水线）",
    )
    ap.add_argument(
        "--prices-file",
        type=Path,
        default=None,
        help="价格表 JSON（默认 config/prices.json；也可用环境变量 QA4_PRICES_PATH）",
    )
    ap.add_argument(
        "--retrieval",
        choices=("fake", "real"),
        default="fake",
        help="检索模式：fake=夹具；real=与问答服务相同的真实 ES/嵌入/重排（可与 dry-run 组合）",
    )
    args = ap.parse_args(argv)

    # 仅当进程已设 QA4_ENV_FILE 时加载；不默认读 backend/.env
    try:
        load_qa4_env_file_if_set()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 2

    csv_path = args.questions_file or args.csv or DEFAULT_CSV
    only_ids = [x.strip() for x in (args.only_ids or "").split(",") if x.strip()] or None
    retrieval_mode = str(args.retrieval or "fake")

    prices = load_prices(args.prices_file)
    if args.live:
        miss_live = env_missing(_LIVE_SECRET_ENV)
        fill_live = env_unfilled(_LIVE_SECRET_ENV)
        if miss_live:
            print(
                "ERROR: --live 缺少环境变量 "
                + ", ".join(miss_live)
                + "（请用 Read-Host -AsSecureString 或 QA4_ENV_FILE 设置，勿写进命令行）。"
            )
            return 2
        if fill_live:
            print(
                "ERROR: --live 拒绝启动：以下变量尚未填写（仍为 __FILL_ME__）："
                + ", ".join(fill_live)
            )
            return 2
        if prices_incomplete(prices):
            print(
                "ERROR: --live 拒绝启动：config/prices.json 价格未填齐（status=待核实 或存在 null）。"
                "请先核实并填写各模型 input/output/cache_write_5m/cache_read。"
            )
            return 2
        if args.max_questions <= 0 or args.budget_usd <= 0:
            print("ERROR: --live 必须同时指定正的 --max-questions 与 --budget-usd")
            return 2
        args.dry_run = False

    if retrieval_mode == "real":
        miss = missing_real_retrieval_env()
        if miss:
            print(
                "ERROR: --retrieval real 拒绝启动：缺少环境变量 "
                + ", ".join(miss)
                + "（值不打印）。"
            )
            return 2
        unfilled = unfilled_real_retrieval_env()
        if unfilled:
            print(
                "ERROR: --retrieval real 拒绝启动：以下变量尚未填写（仍为 __FILL_ME__）："
                + ", ".join(unfilled)
            )
            return 2

    fake_retrieval_warn = bool(args.live) and retrieval_mode == "fake"
    if fake_retrieval_warn:
        print("WARN: 检索为假数据，第 7、8 步结果不能用于评价回答")

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    work = args.out / f"_work_{stamp}"
    work.mkdir(parents=True, exist_ok=True)

    all_rows = load_questions(csv_path)
    rows, filt = filter_questions(
        all_rows,
        priority=args.priority,
        only_ids=only_ids,
        max_questions=args.max_questions,
    )
    print(
        json.dumps(
            {
                "csv": str(csv_path),
                "filter": filt,
                "priority": args.priority,
                "only_ids": only_ids,
                "force_split": args.force_split,
                "compare": bool(args.compare),
                "live": bool(args.live),
                "retrieval_mode": retrieval_mode,
                "prices_status": prices.get("status"),
            },
            ensure_ascii=False,
        )
    )
    if filt["truncated"]:
        print(f"TRUNCATED: after_filter={filt['after_filter']} kept={filt['kept']} truncated={filt['truncated']}")

    if args.render_only:
        return _main_render_only(args, rows, stamp)

    modes = ["split", "nosplit"] if args.compare else [args.force_split]
    if args.compare:
        print(
            "COMPARE_NOTE: --compare 会按 split 与 nosplit 各跑一遍，"
            "预算（--budget-usd）由两遍共同消耗。"
        )
        if prices_incomplete(prices):
            print(
                "COMPARE_WARN: 价格表未填齐，无法估算「单遍费用×2」；"
                "仍会跑两遍，请自行控制题量与预算。"
            )
        else:
            # 粗估：每题按 haiku+sonnet 各 2k in / 500 out 占位（仅警告用）
            sample_model = next(iter((prices.get("models") or {})), None)
            rough, miss, _unp, _m1h = _est_usd_for_usage(
                {"input": 2000, "output": 500, "cache_creation": 0, "cache_read": 0},
                model=sample_model,
                prices=prices,
            )
            if not miss and rough is not None:
                one_pass = rough * max(1, len(rows))
                need = one_pass * 2
                if args.budget_usd < need:
                    print(
                        f"COMPARE_WARN: budget={args.budget_usd} < 单遍估算×2≈{need:.4f} "
                        f"（单遍≈{one_pass:.4f}，题数={len(rows)}）；两遍可能中途停。"
                    )

    compare_rows: list[dict[str, Any]] = []
    jsonl_path = args.out / f"{'live' if args.live else 'dry_run'}_{stamp}.jsonl"
    cumulative = 0.0
    ok = fail = 0
    stopped_at: Optional[str] = None
    stop_reason: Optional[str] = None
    fail_items: list[dict[str, str]] = []

    async def _drive() -> None:
        nonlocal cumulative, ok, fail, stopped_at, stop_reason
        mode_results: dict[str, dict[str, dict[str, Any]]] = {}
        with jsonl_path.open("w", encoding="utf-8") as jf:
            for mode in modes:
                deps = _build_deps(
                    live=bool(args.live),
                    retrieval=retrieval_mode,
                    work=work / mode,
                )
                install_force_split(deps.llm, mode)
                by_id: dict[str, dict[str, Any]] = {}
                for row in rows:
                    if args.live and cumulative >= args.budget_usd:
                        stopped_at = row.get("id")
                        stop_reason = "budget"
                        print(
                            f"BUDGET_STOP before id={stopped_at} "
                            f"cumulative_usd={cumulative:.6f} budget={args.budget_usd}"
                        )
                        return
                    qid = row.get("id") or ""
                    q = (row.get("问题") or "").strip()
                    hist = parse_history(row.get("上文") or "")
                    try:
                        result = await _run_one(
                            deps,
                            question=q,
                            history=hist,
                            force_split=mode,
                            prices=prices,
                        )
                        cost_unknown = bool(result.get("cost_unknown"))
                        if cost_unknown:
                            cum_val: Any = "cost_unknown"
                        elif result.get("price_missing") or result.get("est_cost_usd") is None:
                            cum_val = "cost_unknown"
                            cost_unknown = True
                            result = dict(result)
                            result["cost_unknown"] = True
                        else:
                            add_cost = float(result["est_cost_usd"] or 0)
                            cum_val = round(cumulative + add_cost, 6)
                            cumulative = float(cum_val)
                        record = {
                            "id": qid,
                            "force_split": mode,
                            "retrieval_mode": retrieval_mode,
                            **result,
                            "cost_unknown": cost_unknown,
                            "cumulative_est_usd": cum_val,
                            "filter": filt,
                        }
                        print(
                            f"id={qid} mode={mode} cost={result.get('est_cost_usd')} "
                            f"cum={record.get('cumulative_est_usd')} "
                            f"price_missing={result.get('price_missing')} "
                            f"cost_unknown={cost_unknown} "
                            f"force_failed={result['force_failed']} "
                            f"complex={result.get('plan', {}).get('complex')} "
                            f"retrieval={retrieval_mode}"
                        )
                        if retrieval_mode == "real" and record.get("retrieval") is not None:
                            print(f"  retrieval={json.dumps(record['retrieval'], ensure_ascii=False)}")
                        jf.write(json.dumps(record, ensure_ascii=False) + "\n")
                        ok += 1
                        by_id[qid] = result
                        if args.live and cost_unknown:
                            stopped_at = qid
                            stop_reason = "cost_unknown"
                            print(
                                f"COST_UNKNOWN_STOP after id={stopped_at} "
                                "（花费未知，停止后续题目以免继续调用）"
                            )
                            return
                        if args.live and cumulative >= args.budget_usd:
                            stopped_at = qid
                            stop_reason = "budget"
                            print(f"BUDGET_STOP after id={stopped_at} cumulative_usd={cumulative:.6f}")
                            return
                    except Exception as e:
                        fail += 1
                        err = format_error(e)
                        fail_items.append({"id": qid, "type": err["type"]})
                        rec = {
                            "id": qid,
                            "force_split": mode,
                            "retrieval_mode": retrieval_mode,
                            "ok": False,
                            "error": err,
                            "cost_unknown": True,
                            "cumulative_est_usd": "cost_unknown",
                        }
                        jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        print(
                            f"id={qid} ERROR type={err['type']}\n"
                            f"  message={err['message']}\n"
                            f"  stack={err['stack']}"
                        )
                        if args.live:
                            stopped_at = qid
                            stop_reason = "cost_unknown"
                            print(
                                f"COST_UNKNOWN_STOP after id={stopped_at} "
                                "（异常导致花费未知，停止后续题目）"
                            )
                            return
                        # dry-run：继续下一题
                mode_results[mode] = by_id

        if args.compare:
            for row in rows:
                qid = row.get("id") or ""
                s = (mode_results.get("split") or {}).get(qid) or {}
                n = (mode_results.get("nosplit") or {}).get(qid) or {}
                compare_rows.append(
                    {
                        "id": qid,
                        "split_answer": s.get("answer"),
                        "nosplit_answer": n.get("answer"),
                        "split_cost": s.get("est_cost_usd"),
                        "nosplit_cost": n.get("est_cost_usd"),
                    }
                )

    asyncio.run(_drive())

    if args.compare and compare_rows:
        md = args.out / f"compare_{stamp}.md"
        _write_compare_md(md, compare_rows)
        print(json.dumps({"compare_md": str(md)}, ensure_ascii=False))

    summary = {
        "n": len(rows) * len(modes),
        "ok": ok,
        "fail": fail,
        "fail_items": fail_items,
        "out": str(jsonl_path),
        "cumulative_est_usd": round(cumulative, 6),
        "stopped_at": stopped_at,
        "stop_reason": stop_reason,
        "retrieval_mode": retrieval_mode,
        "filter": filt,
    }
    if fake_retrieval_warn:
        summary["retrieval_warning"] = "检索为假数据，第 7、8 步结果不能用于评价回答"
    (args.out / f"summary_{stamp}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if fail == 0 else 1


def _main_render_only(args: Any, rows: list[dict[str, str]], stamp: int) -> int:
    """旧行为：只渲染提示词，检查 leftover 占位。"""
    from prompts.loader import PromptRegistry

    os.environ.setdefault("QA4_PROMPT_CHANNEL", "draft")
    reg = PromptRegistry(channel="draft")
    summary = {"n": len(rows), "ok": 0, "fail": 0, "items": []}
    for row in rows:
        q = (row.get("问题") or "").strip()
        qid = row.get("id") or ""
        hist = (row.get("上文") or "").strip()
        try:
            steps = {}
            leftover = False
            for step in reg.steps():
                tpl = reg.get(step)
                vals = {v: f"<{v}>" for v in tpl.variables}
                if "question" in vals:
                    vals["question"] = q
                if "subquestion" in vals:
                    vals["subquestion"] = q
                if "history" in vals:
                    vals["history"] = hist or "(无)"
                if "subquestions" in vals:
                    vals["subquestions"] = f"子问题#0（默认）：{q}"
                for k in (
                    "layer1",
                    "caps",
                    "passages",
                    "passage_chars",
                    "rule_hits",
                    "life_book_titles",
                    "feast_list",
                    "qtype",
                    "understanding",
                    "verdict",
                    "definitions",
                    "layers",
                    "devine",
                    "scope_options",
                ):
                    if k in vals and str(vals[k]).startswith("<"):
                        vals[k] = "" if k not in ("passage_chars",) else "600"
                if "layer1" in vals and not vals["layer1"]:
                    vals["layer1"] = "#0:示例"
                if "passages" in vals and not vals["passages"]:
                    vals["passages"] = "[1] 示例段落"
                if "life_book_titles" in vals and not vals["life_book_titles"]:
                    vals["life_book_titles"] = "罗马书生命读经"
                if "feast_list" in vals and not vals["feast_list"]:
                    vals["feast_list"] = "2020-07-夏训"
                if "rule_hits" in vals and not vals["rule_hits"]:
                    vals["rule_hits"] = "[]"
                if "caps" in vals and not vals["caps"]:
                    vals["caps"] = "{}"
                text = tpl.render(**vals)
                bad = any(f"{{{v}}}" in text for v in tpl.variables)
                leftover = leftover or bad
                steps[step] = {"chars": len(text), "est_tokens": round(len(text) * 1.2, 1), "leftover": bad}
            ok = not leftover
            summary["ok" if ok else "fail"] += 1
            summary["items"].append({"id": qid, "ok": ok, "steps": steps})
        except Exception as e:
            summary["fail"] += 1
            summary["items"].append({"id": qid, "ok": False, "error": type(e).__name__})

    out_path = args.out / f"dry_run_render_{stamp}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"n": summary["n"], "ok": summary["ok"], "fail": summary["fail"], "out": str(out_path)}, ensure_ascii=False))
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
