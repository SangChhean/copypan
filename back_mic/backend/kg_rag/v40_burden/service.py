# -*- coding: utf-8 -*-
"""第1项（【原流程不变】4.0测试台）负担说明：校验、调用 Opus 5.5、切分、记录。

只读引用 3.5 的 claude_client 与 llm_pricing，不改动 3.5 的任何代码。
与 3.5 的差别：
  - 纲目性质为外在 / 内在 / 最内在 / 显出的外在，必选，全字比对，不在四个值里直接报错；
  - 模型固定 claude-opus-5-5，不传 temperature（该模型会拒绝），不降级，失败就报错；
  - 返回 stop_reason 与 API 实际返回的模型名，截断时标出；
  - 候选以【层次】标注并取出 layer，异常只给警示，不自动修正、不重跑；
  - 不用任何缓存，每次都是真实调用。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from kg_rag.llm_pricing import register_llm_usage
from kg_rag.v40_burden import term_layer_count as tlc
from kg_rag.v40_burden.prompts_v40 import BURDEN_PROMPT_V40, BURDEN_SYSTEM_V40, PROMPT_NAME

logger = logging.getLogger("kg_rag")

try:
    from ai_search.ai_service import claude_client
except Exception:  # pragma: no cover - 与 3.5 的兜底写法一致
    claude_client = None

MODEL = "claude-opus-5-5"
# 360 字 × 3 条的正文约 1100 字，3.5 的 1200 放不下。实测约 2.8 token/字，3 条各写满 360 字约需 3000 token；另有 1/11 的实测因 4096 用完被截断（只出 93 字，疑为先思考耗掉额度），故取 8192；截断会在页面和记录里标出。
MAX_TOKENS = 8192
CHAR_LIMIT = 360
# 情境 B 每条的目标下限。写给模型的下限是 280（模型会略低于所写下限，实测 260 时约一半不到 260），
# 这里按 260 给警示，只提示不重跑。
B_MIN_CHARS = 260
LAYERS = ("外在", "内在", "最内在", "显出的外在")
VERSION_LABEL = "第1项 纲目性质"
VERSION_KEY = "item1"

_RECORD_DIR = Path(__file__).resolve().parents[2] / "data" / "v40_burden"
# 删除不是真删：移到这里，需要时可手动移回；整个文件夹删掉才是彻底清除。
_DELETED_DIR = _RECORD_DIR / "_deleted"
_TERMS_PATH = Path(__file__).resolve().parent / "terms_2373.json"
_record_lock = threading.Lock()


class NatureError(ValueError):
    """纲目性质不在四个值里。"""


def validate_nature(nature: str | None) -> str:
    """全字比对（'内在' 是 '最内在' 的一部分，不能用包含判断）。不在四个值里直接报错，不退回默认。"""
    value = (nature or "").strip()
    if value not in LAYERS:
        raise NatureError(f"纲目性质必须是 {'、'.join(LAYERS)} 之一，收到：{value or '（空）'}")
    return value


def prompt_hash() -> str:
    h = hashlib.sha256()
    h.update(BURDEN_PROMPT_V40.encode("utf-8"))
    h.update(b"\n--system--\n")
    h.update(BURDEN_SYSTEM_V40.encode("utf-8"))
    return h.hexdigest()[:16]


def meta() -> dict[str, Any]:
    return {
        "layers": list(LAYERS),
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "char_limit": CHAR_LIMIT,
        "prompt_name": PROMPT_NAME,
        "prompt_hash": prompt_hash(),
        "version": VERSION_LABEL,
    }


def render_prompt(query: str, nature: str, audience: str, reference_excerpt: str) -> str:
    """与 3.5 同样的填充方式：未填写的项写成 '（未填）'，空摘录写成 '（空）'。"""
    return BURDEN_PROMPT_V40.format(
        query=(query or "").strip(),
        outline_nature=nature,
        audience=(audience or "").strip() or "（未填）",
        reference_excerpt=(reference_excerpt or "").strip() or "（空）",
    )


# ---------------------------------------------------------------------------
# 调用 Opus 5.5
# ---------------------------------------------------------------------------


def _get_client():
    client = claude_client
    if client:
        return client
    import os

    import anthropic

    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("Claude 客户端未配置（请设置 CLAUDE_API_KEY）")
    return anthropic.Anthropic(api_key=api_key)


def _call_opus_sync(prompt: str) -> dict[str, Any]:
    client = _get_client()
    # 不传 temperature：claude-opus-5-5 会返回 400 "temperature is deprecated for this model"。
    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=BURDEN_SYSTEM_V40,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        str(getattr(b, "text", "") or "") for b in (msg.content or []) if getattr(b, "type", None) == "text"
    )
    uobj = getattr(msg, "usage", None)
    usage = None
    if uobj is not None:
        usage = {
            "input_tokens": int(getattr(uobj, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(uobj, "output_tokens", 0) or 0),
        }
    return {
        "text": text,
        "block_types": [str(getattr(b, "type", "")) for b in (msg.content or [])],
        "stop_reason": getattr(msg, "stop_reason", None),
        "actual_model": getattr(msg, "model", None),
        "usage": usage,
    }


# ---------------------------------------------------------------------------
# 切分
# ---------------------------------------------------------------------------

_CAND_RE = re.compile(
    r"候选(一|二|三)\s*(?:【([^】]*)】)?\s*(?:（[^）]*）)?\s*[：:]\s*(.+?)(?=\n\s*候选[一二三]|\Z)",
    re.S,
)
_CAND_ORDER = ("一", "二", "三")


def split_output(raw: str) -> dict[str, Any]:
    """沿用 3.5 的判断：含 '候选一' 走情境 B；否则含 '负担说明' 走情境 A。每条另取出【层次】到 layer。"""
    text = (raw or "").strip()
    if not text:
        return {"scenario": None, "error": "解析失败", "reason": "empty_raw"}
    if "候选一" in text:
        found: dict[str, tuple[str | None, str]] = {}
        for m in _CAND_RE.finditer(text):
            order, layer, body = m.group(1), m.group(2), m.group(3)
            if order not in found:
                found[order] = ((layer or "").strip() or None, re.sub(r"\s+", " ", body.strip()))
        candidates = []
        for i, order in enumerate(_CAND_ORDER, 1):
            layer, body = found.get(order, (None, ""))
            candidates.append({"index": i, "layer": layer, "text": body})
        if not any(c["text"] for c in candidates):
            return {"scenario": "B", "error": "解析失败", "reason": "b_candidates_all_empty"}
        return {"scenario": "B", "candidates": candidates}
    if "负担说明" in text:
        m = re.search(r"负担说明[：:]\s*(.+)", text, re.S)
        if m:
            line = re.sub(r"\s+", " ", m.group(1).strip())
            if line:
                return {"scenario": "A", "result": line}
    return {"scenario": None, "error": "解析失败", "reason": "no_pattern_matched"}


def check_candidates(candidates: list[dict[str, Any]], nature: str) -> list[str]:
    """只给警示，不修正、不重跑。"""
    warnings: list[str] = []
    seen: list[str] = []
    for c in candidates:
        i, layer = c["index"], c["layer"]
        if not c["text"]:
            warnings.append(f"候选{_CAND_ORDER[i - 1]}缺少正文")
        if layer is None:
            warnings.append(f"候选{_CAND_ORDER[i - 1]}缺少层次标记")
            continue
        if layer not in LAYERS:
            warnings.append(f"候选{_CAND_ORDER[i - 1]}的层次「{layer}」不在四个值里")
            continue
        seen.append(layer)
    first = candidates[0]["layer"] if candidates else None
    if first is not None and first != nature:
        warnings.append(f"候选一的层次「{first}」不是所选纲目性质「{nature}」")
    dup = sorted({x for x in seen if seen.count(x) > 1})
    if dup:
        warnings.append(f"三条的层次有重复：{'、'.join(dup)}")
    return warnings


# ---------------------------------------------------------------------------
# 词条分层统计（4.2）：直接调用 term_layer_count 的 match / summarize
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _surface() -> dict:
    return tlc.load_terms(str(_TERMS_PATH))


def term_stats(text: str, include_single: bool = False) -> dict[str, Any]:
    return tlc.summarize(tlc.match(text or "", _surface()), include_single)


def term_analysis(text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """同一次匹配同时给统计和逐词位置（页面据此把本条性质的词标出来）。"""
    hits = tlc.match(text or "", _surface())
    return tlc.summarize(hits, False), hits


# ---------------------------------------------------------------------------
# 记录
# ---------------------------------------------------------------------------


def _safe_topic_no(raw: str | None) -> str:
    s = re.sub(r"[^0-9A-Za-z_\-一-鿿]", "", (raw or "").strip())[:40]
    return s or "NA"


def _next_record_id(topic_no: str) -> str:
    _RECORD_DIR.mkdir(parents=True, exist_ok=True)
    # 已删除的记录也算在内，避免新记录沿用旧编号造成混淆
    pat = re.compile(rf"^{re.escape(topic_no)}-{VERSION_KEY}-(\d+)(?:\.\d+)?\.json$")
    nums = [
        int(m.group(1))
        for d in (_RECORD_DIR, _DELETED_DIR)
        if d.exists()
        for p in d.glob(f"{topic_no}-{VERSION_KEY}-*.json")
        if (m := pat.match(p.name))
    ]
    return f"{topic_no}-{VERSION_KEY}-{(max(nums) if nums else 0) + 1}"


def save_record(record: dict[str, Any], topic_no: str) -> str:
    with _record_lock:
        rid = _next_record_id(topic_no)
        record["record_id"] = rid
        (_RECORD_DIR / f"{rid}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return rid


_RID_RE = re.compile(r"^[0-9A-Za-z_\-一-鿿]+-" + VERSION_KEY + r"-\d+$")


def get_record(record_id: str) -> dict[str, Any] | None:
    """按记录编号读取完整记录；编号格式不符（含路径字符）一律当作不存在。"""
    rid = (record_id or "").strip()
    if not _RID_RE.match(rid):
        return None
    p = _RECORD_DIR / f"{rid}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete_record(record_id: str) -> bool:
    """把记录移到 _deleted 文件夹（可找回）。编号格式不符或不存在返回 False。"""
    rid = (record_id or "").strip()
    if not _RID_RE.match(rid):
        return False
    with _record_lock:
        src = _RECORD_DIR / f"{rid}.json"
        if not src.is_file():
            return False
        _DELETED_DIR.mkdir(parents=True, exist_ok=True)
        dest = _DELETED_DIR / f"{rid}.json"
        if dest.exists():
            dest = _DELETED_DIR / f"{rid}.{int(time.time())}.json"
        src.replace(dest)
    return True


def list_records(topic_no: str | None = None) -> list[dict[str, Any]]:
    if not _RECORD_DIR.exists():
        return []
    key = _safe_topic_no(topic_no) if topic_no else None
    rows = []
    for p in sorted(_RECORD_DIR.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if key and r.get("topic_no") != key:
            continue
        if r.get("scenario") == "B":
            parts = [{"layer": c.get("layer"), "chars": c.get("chars")} for c in (r.get("candidates") or [])]
        else:
            parts = [{"layer": r.get("outline_nature"), "chars": r.get("result_chars")}]
        rows.append(
            {
                "record_id": r.get("record_id"),
                "time": r.get("time"),
                "topic_no": r.get("topic_no"),
                "query": r.get("query"),
                "outline_nature": r.get("outline_nature"),
                "scenario": r.get("scenario"),
                "parts": parts,
                "warnings": len(r.get("warnings") or []),
            }
        )
    rows.sort(key=lambda x: x.get("time") or "")
    return rows


def _stats_line(stats: dict[str, Any] | None) -> str:
    if not stats:
        return ""
    counts = stats.get("各层个数") or {}
    ratio = stats.get("各层比例") or {}
    parts = [f"{k} {counts.get(k, 0)}（{ratio.get(k, 0)}%）" for k in LAYERS]
    return f"计入词条 {stats.get('计入词条数', 0)}：" + "；".join(parts)


def export_markdown(topic_no: str) -> str:
    key = _safe_topic_no(topic_no)
    records = []
    for p in sorted(_RECORD_DIR.glob(f"{key}-{VERSION_KEY}-*.json")) if _RECORD_DIR.exists() else []:
        try:
            records.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    records.sort(key=lambda r: r.get("time") or "")
    lines = [f"# 篇题 {key}：4.0测试台（{VERSION_LABEL}）", ""]
    if not records:
        lines.append("（没有记录）")
    for r in records:
        lines += [
            f"## {r.get('record_id')}",
            "",
            f"- 篇题：{r.get('query')}",
            f"- 时间：{r.get('time')}",
            f"- 纲目性质：{r.get('outline_nature')}　情境：{r.get('scenario')}",
            f"- 模型：请求 {r.get('requested_model')}，实际 {r.get('actual_model')}；max_tokens {r.get('max_tokens')}；"
            f"temperature 未传；stop_reason {r.get('stop_reason')}",
            f"- prompt：{r.get('prompt_template')}（{r.get('prompt_hash')}）",
        ]
        for w in r.get("warnings") or []:
            lines.append(f"- ⚠ {w}")
        lines.append("")
        if r.get("scenario") == "A":
            lines += [r.get("result") or "", "", f"（{r.get('result_chars')} 字）", _stats_line(r.get("term_stats_result")), ""]
        else:
            for c in r.get("candidates") or []:
                lines += [
                    f"**候选{_CAND_ORDER[c['index'] - 1]}【{c.get('layer') or '无'}】**（{c.get('chars')} 字）",
                    "",
                    c.get("text") or "",
                    "",
                    _stats_line(c.get("term_stats")),
                    "",
                ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


async def generate(
    *,
    query: str,
    outline_nature: str,
    audience: str = "",
    reference_excerpt: str = "",
    topic_no: str = "",
    save: bool = True,
) -> dict[str, Any]:
    nature = validate_nature(outline_nature)
    q = (query or "").strip()
    prompt = render_prompt(q, nature, audience, reference_excerpt)

    t0 = time.perf_counter()
    called = await asyncio.to_thread(_call_opus_sync, prompt)  # 失败直接抛出，不降级
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    raw = called["text"]
    truncated = called["stop_reason"] == "max_tokens"
    parsed = split_output(raw)
    warnings: list[str] = []
    if truncated:
        warnings.append(f"输出因 max_tokens={MAX_TOKENS} 被截断，正文可能不完整")

    out: dict[str, Any] = {
        "topic_no": _safe_topic_no(topic_no),
        "query": q,
        "version": VERSION_LABEL,
        "outline_nature": nature,
        "audience": (audience or "").strip(),
        "reference_excerpt": (reference_excerpt or "").strip(),
        "time": datetime.now().isoformat(timespec="seconds"),
        "requested_model": MODEL,
        "actual_model": called["actual_model"],
        "temperature": "未传（claude-opus-5-5 不接受）",
        "max_tokens": MAX_TOKENS,
        "stop_reason": called["stop_reason"],
        "block_types": called["block_types"],
        "truncated": truncated,
        "prompt_template": PROMPT_NAME,
        "prompt_hash": prompt_hash(),
        "prompt": prompt,
        "system_prompt": BURDEN_SYSTEM_V40,
        "raw_output": raw,
        "elapsed_ms": elapsed_ms,
    }
    sn = register_llm_usage([], step="v40_burden", request_model=MODEL, usage=called["usage"])
    if sn:
        out["llm_usage"] = sn
        out["cost_usd"] = sn.get("cost_usd")

    scenario = parsed.get("scenario")
    out["scenario"] = scenario
    if parsed.get("error"):
        out["error"] = parsed["error"]
        out["parse_reason"] = parsed.get("reason")
        warnings.append(f"切分失败：{parsed.get('reason')}")
    elif scenario == "B":
        cands = parsed["candidates"]
        for c in cands:
            c["chars"] = len(c["text"])
            c["term_stats"], c["term_hits"] = term_analysis(c["text"]) if c["text"] else (None, [])
            if c["chars"] > CHAR_LIMIT:
                warnings.append(f"候选{_CAND_ORDER[c['index'] - 1]}共 {c['chars']} 字，超过 {CHAR_LIMIT} 字上限")
            elif c["text"] and c["chars"] < B_MIN_CHARS:
                warnings.append(f"候选{_CAND_ORDER[c['index'] - 1]}只有 {c['chars']} 字，低于 {B_MIN_CHARS} 字")
        warnings += check_candidates(cands, nature)
        out["candidates"] = cands
    elif scenario == "A":
        res = parsed["result"]
        out["result"] = res
        out["result_chars"] = len(res)
        out["term_stats_result"], out["term_hits_result"] = term_analysis(res)
        if len(res) > CHAR_LIMIT:
            warnings.append(f"负担说明共 {len(res)} 字，超过 {CHAR_LIMIT} 字上限")
    out["warnings"] = warnings

    if save:
        out["record_id"] = save_record(out, out["topic_no"])
    return out
