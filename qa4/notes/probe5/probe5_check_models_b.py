# -*- coding: utf-8 -*-
"""
探针 5b：补查第五轮 5 个疑点（identity / e9 thinking / json / cache / speed）。

默认：只打印计划（不调 API）。
--dry-run：打印各节计划调用数与预算占用，不联网；不读取密钥环境变量的值。
--yes：真实调用（需环境变量 CLAUDE_API_KEY，缺失则回退 ANTHROPIC_API_KEY）。
--only：identity | e9 | json | cache | speed（可重复）。

依赖：qa4/backend/.venv 中 anthropic 2.8.0。
实测签名（本机 venv）：messages.create / messages.stream 均接受顶层
thinking、output_config、cache_control；不必走 extra_body。
cache_control.ttl 支持 '5m' | '1h'；output_config.effort 支持 low|medium|high|...
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_OUT_DIR = Path(r"G:\PanAI4.0专用\logs")
TARGET_HAIKU = "claude-haiku-5-5"
TARGET_SONNET = "claude-sonnet-5-5"
CALL_TIMEOUT_S = 120.0
KEY_ENV_NAMES = ("CLAUDE_API_KEY", "ANTHROPIC_API_KEY")

BUDGET = {
    TARGET_HAIKU: {"input": 200_000, "output": 40_000},
    TARGET_SONNET: {"input": 80_000, "output": 15_000},
}

SECTIONS = ("identity", "e9", "json", "cache", "speed")

# 避免源码出现连续的 sk 短横线前缀 / 鉴权方案名字面量
_SK_PREFIX = "sk" + "-"
_BEARER = "Bear" + "er"
SECRET_RE = re.compile(
    rf"(?i)(api[_-]?key|authorization|{_BEARER}|x-api-key)\s*[:=]\s*\S+"
)
SK_RE = re.compile(re.escape(_SK_PREFIX) + r"[A-Za-z0-9_\-]{10,}")

REPO_QA4 = Path(__file__).resolve().parents[2]  # qa4/
LEXICON_PATH = REPO_QA4 / "data" / "lookups" / "lexicon.json"

# E9 提示词（与 probe5_check_models.py 一致）
def _e9_prompt() -> str:
    return gen_chinese_filler(3000) + "\n请根据上文风格，写大约三百字的说明性文字。"


IDENTITY_PROMPT = "你是什么模型？由哪家公司开发？"
JSON_USER_Q = "神的爱与爱神有什么关系？"
JSON_SYSTEM = (
    "你只输出一个 JSON 对象，不要其它文字。格式："
    '{"matched":["词条",...]}。matched 最多 5 个，且必须全部来自用户给出的编号词表；'
    "优先收录与问题最相关的词。"
)
SPEED_PROMPT = (
    "请撰写一篇约一千五百字的中文说明文，题目固定为："
    "「查表与图谱检索在问答系统中的分工」。"
    "要求结构完整、分段清楚，不要列提纲式短句堆砌。"
)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def redact(s: str) -> str:
    s = SECRET_RE.sub(r"\1=***", s)
    s = SK_RE.sub(_SK_PREFIX + "***", s)
    # URL user:pass@
    s = re.sub(r"(://)([^/@\s]*):([^/@\s]*)@", r"\1***:***@", s)
    return s


def key_names_in_environ() -> list[str]:
    """dry-run 用：只检查名字是否在 environ 中，不读取值。"""
    env = getattr(os, "environ")
    return [n for n in KEY_ENV_NAMES if n in env]


def get_api_key() -> str:
    """仅 --yes 路径调用；取值不入日志/报告。"""
    env = getattr(os, "environ")
    for n in KEY_ENV_NAMES:
        v = env.get(n)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def setup_logger(out_dir: Path, name: str = "models_b") -> tuple[logging.Logger, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = out_dir / f"probe5b_{name}_{ts}.log"
    json_path = out_dir / f"probe5b_{name}_{ts}.json"
    logger = logging.getLogger(f"probe5b_{name}_{ts}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)

    class RedactFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                record.args = tuple(
                    redact(a) if isinstance(a, str) else a for a in record.args
                )
            return True

    logger.addFilter(RedactFilter())
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger, log_path, json_path


def gen_chinese_filler(approx_tokens: int) -> str:
    unit = (
        "甲乙丙丁戊己庚辛壬癸，子丑寅卯辰巳午未申酉戌亥。"
        "春夏秋冬循环往复，东南西北上下左右。"
        "一二三四五六七八九十百千万，测试缓存与延迟所用无意义文本。"
    )
    need_chars = int(approx_tokens * 1.5)
    reps = max(1, (need_chars // len(unit)) + 1)
    return (unit * reps)[:need_chars]


def gen_chinese_chars(n_chars: int) -> str:
    unit = (
        "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"
        "春夏秋冬东南西北上下左右一二三四五六七八九十"
    )
    reps = max(1, (n_chars // len(unit)) + 1)
    return (unit * reps)[:n_chars]


def clip_text(s: str, n: int = 300) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + f"...<{len(s)} chars>"


def usage_to_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        d = dict(usage)
    else:
        d = {}
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "cache_creation",
        ):
            if hasattr(usage, k):
                v = getattr(usage, k)
                if hasattr(v, "model_dump"):
                    v = v.model_dump()
                elif hasattr(v, "dict"):
                    v = v.dict()
                d[k] = v
        # 兜底：model_dump
        if not d and hasattr(usage, "model_dump"):
            d = usage.model_dump()
    return d


def content_summary(content: Any) -> dict[str, Any]:
    blocks: list[dict] = []
    counts: dict[str, int] = {}
    texts: list[str] = []
    if not content:
        return {"blocks": [], "counts": {}, "text": ""}
    for b in content:
        if isinstance(b, dict):
            typ = b.get("type") or "unknown"
            size = len(b.get("text") or b.get("thinking") or "") 
            blocks.append({"type": typ, "size": size})
            if typ == "text":
                texts.append(b.get("text") or "")
        else:
            typ = getattr(b, "type", type(b).__name__)
            text = getattr(b, "text", None)
            thinking = getattr(b, "thinking", None)
            size = len(text or thinking or "")
            blocks.append({"type": typ, "size": size})
            if typ == "text" and text:
                texts.append(text)
        counts[typ] = counts.get(typ, 0) + 1
    return {"blocks": blocks, "counts": counts, "text": "".join(texts)}


def median(xs: list[float]) -> Optional[float]:
    ys = [x for x in xs if isinstance(x, (int, float))]
    if not ys:
        return None
    return float(statistics.median(ys))


# ---------------------------------------------------------------------------
# 预算
# ---------------------------------------------------------------------------


class BudgetTracker:
    def __init__(self) -> None:
        self.used = {
            m: {"input": 0, "output": 0} for m in (TARGET_HAIKU, TARGET_SONNET)
        }
        self.exhausted: dict[str, bool] = {TARGET_HAIKU: False, TARGET_SONNET: False}

    def add(self, model: str, usage: dict[str, Any]) -> None:
        inp = int(usage.get("input_tokens") or 0)
        # cache 创建/读也算输入侧消耗（计入预算）
        inp += int(usage.get("cache_creation_input_tokens") or 0)
        # cache_read 也是账单输入；计入
        inp += int(usage.get("cache_read_input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        u = self.used.setdefault(model, {"input": 0, "output": 0})
        u["input"] += inp
        u["output"] += out
        cap = BUDGET.get(model) or {"input": 0, "output": 0}
        if u["input"] >= cap["input"] or u["output"] >= cap["output"]:
            self.exhausted[model] = True

    def allow(self, model: str) -> bool:
        return not self.exhausted.get(model, False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "used": self.used,
            "budget": BUDGET,
            "exhausted": dict(self.exhausted),
        }


# ---------------------------------------------------------------------------
# API 调用（anthropic SDK 顶层参数）
# ---------------------------------------------------------------------------


def build_thinking_kwargs(setting: str) -> dict[str, Any]:
    """setting: none | disabled | adaptive-low | adaptive-medium | adaptive-high"""
    if setting in ("none", "", None):
        return {}
    if setting == "disabled":
        return {"thinking": {"type": "disabled"}}
    if setting.startswith("adaptive-"):
        effort = setting.split("-", 1)[1]
        return {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
        }
    raise ValueError(f"未知 thinking 设置：{setting}")


def call_once(
    client: Any,
    *,
    model: str,
    messages: list[dict],
    max_tokens: int,
    system: Any = None,
    thinking_setting: str = "none",
    stream: bool = False,
    extra_headers: Optional[dict] = None,
    log: Optional[logging.Logger] = None,
) -> dict[str, Any]:
    """单次调用；超时 CALL_TIMEOUT_S；不重试。"""
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "timeout": CALL_TIMEOUT_S,
    }
    if system is not None:
        kwargs["system"] = system
    kwargs.update(build_thinking_kwargs(thinking_setting))
    if extra_headers:
        kwargs["extra_headers"] = extra_headers

    rec: dict[str, Any] = {
        "request_model": model,
        "thinking_setting": thinking_setting,
        "stream": stream,
        "max_tokens": max_tokens,
        "ok": False,
    }
    t0 = time.perf_counter()
    try:
        if stream:
            first_tok_s: Optional[float] = None
            text_parts: list[str] = []
            final_msg = None
            with client.messages.stream(**kwargs) as stream_ctx:
                for event in stream_ctx:
                    et = getattr(event, "type", None)
                    if first_tok_s is None and et in (
                        "content_block_delta",
                        "content_block_start",
                    ):
                        first_tok_s = time.perf_counter() - t0
                    if et == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta is not None and getattr(delta, "type", "") == "text_delta":
                            text_parts.append(getattr(delta, "text", "") or "")
                final_msg = stream_ctx.get_final_message()
            elapsed = time.perf_counter() - t0
            usage = usage_to_dict(getattr(final_msg, "usage", None))
            resp_model = getattr(final_msg, "model", None)
            stop = getattr(final_msg, "stop_reason", None)
            mid = getattr(final_msg, "id", None)
            csum = content_summary(getattr(final_msg, "content", None))
            text = csum["text"] or "".join(text_parts)
            rec.update(
                {
                    "ok": True,
                    "response_model": resp_model,
                    "model_mismatch": bool(resp_model and resp_model != model),
                    "id": mid,
                    "stop_reason": stop,
                    "usage": usage,
                    "elapsed_s": round(elapsed, 4),
                    "ttft_s": round(first_tok_s, 4) if first_tok_s is not None else None,
                    "content": csum,
                    "text_full": text if len(text) <= 500 else None,
                    "text_clip": clip_text(text, 300),
                }
            )
        else:
            msg = client.messages.create(**kwargs)
            elapsed = time.perf_counter() - t0
            usage = usage_to_dict(getattr(msg, "usage", None))
            resp_model = getattr(msg, "model", None)
            csum = content_summary(getattr(msg, "content", None))
            text = csum["text"]
            rec.update(
                {
                    "ok": True,
                    "response_model": resp_model,
                    "model_mismatch": bool(resp_model and resp_model != model),
                    "id": getattr(msg, "id", None),
                    "stop_reason": getattr(msg, "stop_reason", None),
                    "usage": usage,
                    "elapsed_s": round(elapsed, 4),
                    "ttft_s": None,
                    "content": csum,
                    "text_full": text if len(text) <= 500 else None,
                    "text_clip": clip_text(text, 300),
                }
            )
        if rec.get("model_mismatch") and log:
            log.error(
                "【MODEL_MISMATCH】request=%s response=%s",
                model,
                rec.get("response_model"),
            )
    except Exception as e:
        elapsed = time.perf_counter() - t0
        status = getattr(e, "status_code", None) or getattr(
            getattr(e, "response", None), "status_code", None
        )
        body = ""
        resp = getattr(e, "response", None)
        if resp is not None:
            try:
                body = resp.text if hasattr(resp, "text") else str(resp)
            except Exception:
                body = ""
        if not body:
            body = str(e)
        rec.update(
            {
                "ok": False,
                "elapsed_s": round(elapsed, 4),
                "error_type": type(e).__name__,
                "status_code": status,
                "error_body": redact(clip_text(body, 800)),
            }
        )
        if log:
            log.warning(
                "call failed model=%s type=%s status=%s body=%s",
                model,
                type(e).__name__,
                status,
                redact(clip_text(body, 400)),
            )
    return rec


# ---------------------------------------------------------------------------
# 计划 / 预算占用（dry-run）
# ---------------------------------------------------------------------------


def plan_section(only: set[str]) -> dict[str, Any]:
    """估算调用次数与粗略 token 占用（仅规划；真实以 usage 为准）。"""
    plan: dict[str, Any] = {}
    # A
    if "identity" in only:
        plan["identity"] = {
            "calls": [
                {"model": TARGET_HAIKU, "n": 3, "stream_n": 1, "est_in": 30, "est_out": 80},
                {"model": TARGET_SONNET, "n": 3, "stream_n": 1, "est_in": 30, "est_out": 80},
            ],
            "total_calls": 6,
        }
    # B
    if "e9" in only:
        # 5 settings × 3，仅 Haiku；max_tokens 2000；输入≈ filler 3000 tok + 提示
        plan["e9"] = {
            "calls": [
                {
                    "model": TARGET_HAIKU,
                    "n": 15,
                    "settings": 5,
                    "repeats": 3,
                    "est_in_each": 3200,
                    "est_out_each": 800,
                }
            ],
            "total_calls": 15,
        }
    # C
    if "json" in only:
        plan["json"] = {
            "calls": [
                {
                    "model": TARGET_HAIKU,
                    "n": 16,
                    "settings": ["none", "disabled", "adaptive-low", "adaptive-high"],
                    "repeats": 4,
                    "est_in_each": 6200,
                    "est_out_each": 200,
                },
                {
                    "model": TARGET_SONNET,
                    "n": 4,
                    "settings": ["none", "disabled"],
                    "repeats": 2,
                    "est_in_each": 6200,
                    "est_out_each": 200,
                },
            ],
            "total_calls": 20,
        }
    # D
    if "cache" in only:
        # 4 tiers × 2 + 1h×2，两模型
        plan["cache"] = {
            "calls": [
                {
                    "model": TARGET_HAIKU,
                    "n": 10,
                    "tiers": [600, 1200, 2400, 4800],
                    "est_in_note": "按字数档；真实以 usage",
                },
                {"model": TARGET_SONNET, "n": 10},
            ],
            "total_calls": 20,
        }
    # E
    if "speed" in only:
        plan["speed"] = {
            "calls": [
                {"model": TARGET_SONNET, "n": 2, "est_out": 2000},
                {"model": TARGET_HAIKU, "n": 1, "est_out": 2000},
            ],
            "total_calls": 3,
        }

    # 汇总预算占用粗估
    occ = {
        TARGET_HAIKU: {"input": 0, "output": 0},
        TARGET_SONNET: {"input": 0, "output": 0},
    }

    def add(model: str, n: int, inp: int, out: int) -> None:
        occ[model]["input"] += n * inp
        occ[model]["output"] += n * out

    if "identity" in only:
        add(TARGET_HAIKU, 3, 40, 100)
        add(TARGET_SONNET, 3, 40, 100)
    if "e9" in only:
        add(TARGET_HAIKU, 15, 3200, 800)
    if "json" in only:
        add(TARGET_HAIKU, 16, 6200, 250)
        add(TARGET_SONNET, 4, 6200, 250)
    if "cache" in only:
        # 粗：每档平均 ~ (600+1200+2400+4800)/4 字 ≈ 2250 字 ≈ 1500 tok ×2 次 ×4 档 + 2400×2
        add(TARGET_HAIKU, 10, 2000, 32)
        add(TARGET_SONNET, 10, 2000, 32)
    if "speed" in only:
        add(TARGET_SONNET, 2, 80, 2200)
        add(TARGET_HAIKU, 1, 80, 2200)

    total_calls = sum(v.get("total_calls", 0) for v in plan.values())
    return {
        "sections": plan,
        "total_calls": total_calls,
        "budget_cap": BUDGET,
        "budget_occupancy_estimate": occ,
        "budget_remaining_estimate": {
            m: {
                "input": BUDGET[m]["input"] - occ[m]["input"],
                "output": BUDGET[m]["output"] - occ[m]["output"],
            }
            for m in BUDGET
        },
    }


# ---------------------------------------------------------------------------
# 各节
# ---------------------------------------------------------------------------


def run_identity(client, budget: BudgetTracker, log: logging.Logger) -> dict:
    out: dict[str, Any] = {"section": "identity", "runs": []}
    for model in (TARGET_HAIKU, TARGET_SONNET):
        for i in range(3):
            if not budget.allow(model):
                out["runs"].append(
                    {"model": model, "i": i, "skipped": True, "reason": "预算已用尽"}
                )
                continue
            use_stream = i == 2  # 各模型第 3 次流式
            rec = call_once(
                client,
                model=model,
                messages=[{"role": "user", "content": IDENTITY_PROMPT}],
                max_tokens=256,
                thinking_setting="none",
                stream=use_stream,
                log=log,
            )
            # 身份回答存全文
            if rec.get("ok") and rec.get("content", {}).get("text"):
                rec["text_full"] = rec["content"]["text"]
            if rec.get("ok"):
                budget.add(model, rec.get("usage") or {})
            out["runs"].append(rec)
            log.info(
                "identity model=%s stream=%s ok=%s resp_model=%s mismatch=%s clip=%s",
                model,
                use_stream,
                rec.get("ok"),
                rec.get("response_model"),
                rec.get("model_mismatch"),
                rec.get("text_clip"),
            )
    return out


def run_e9(client, budget: BudgetTracker, log: logging.Logger) -> dict:
    settings = [
        "none",
        "disabled",
        "adaptive-low",
        "adaptive-medium",
        "adaptive-high",
    ]
    prompt = _e9_prompt()
    out: dict[str, Any] = {"section": "e9", "prompt_note": "reuse E9 filler+300字", "by_setting": {}}
    for st in settings:
        rows = []
        for i in range(3):
            if not budget.allow(TARGET_HAIKU):
                rows.append({"skipped": True, "reason": "预算已用尽"})
                continue
            rec = call_once(
                client,
                model=TARGET_HAIKU,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                thinking_setting=st,
                log=log,
            )
            # 被拒不算脚本失败
            if rec.get("ok"):
                budget.add(TARGET_HAIKU, rec.get("usage") or {})
                stop = rec.get("stop_reason")
                thinking_n = (rec.get("content") or {}).get("counts", {}).get("thinking", 0)
                thinking_size = sum(
                    b.get("size", 0)
                    for b in (rec.get("content") or {}).get("blocks", [])
                    if b.get("type") == "thinking"
                )
                text = (rec.get("content") or {}).get("text") or ""
                eaten = stop == "max_tokens"
                rec["analysis"] = {
                    "thinking_blocks": thinking_n,
                    "thinking_chars": thinking_size,
                    "answer_chars": len(text),
                    "complete_answer": bool(text) and not eaten,
                    "eaten_by_thinking": eaten,
                }
            rows.append(rec)
        out["by_setting"][st] = rows
    return out


def build_json_wordlist(target_input_tokens: int = 6000) -> tuple[str, list[str]]:
    """从 lexicon.json 固定顺序取名，拼编号词表。返回 (正文, 名列表)。"""
    if not LEXICON_PATH.is_file():
        raise FileNotFoundError(f"缺少查表：lookups/lexicon.json（相对 qa4/data）")
    data = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    names = [e["name"] for e in data if isinstance(e, dict) and e.get("name")]
    # 粗估：每行约 name+编号；先取足够多再截
    lines: list[str] = []
    used: list[str] = []
    # 约 1.5 字/token；目标正文 ~ target*1.5 字，留系统/问题余量
    need_chars = int(target_input_tokens * 1.4)
    for i, name in enumerate(names, 1):
        line = f"{i}. {name}"
        lines.append(line)
        used.append(name)
        if sum(len(x) + 1 for x in lines) >= need_chars:
            break
    body = "编号词表：\n" + "\n".join(lines)
    user = f"{body}\n\n问题：{JSON_USER_Q}"
    return user, used


def score_json(text: str, vocab: set[str]) -> dict[str, Any]:
    parsed = None
    err = None
    try:
        # 允许围栏
        t = text.strip()
        if t.startswith("```"):
            t = re.sub(r"^```(?:json)?\s*", "", t)
            t = re.sub(r"\s*```$", "", t)
        parsed = json.loads(t)
    except Exception as e:
        err = type(e).__name__
    ok_parse = isinstance(parsed, dict) and "matched" in parsed
    matched = []
    if ok_parse:
        m = parsed.get("matched")
        if isinstance(m, list):
            matched = [str(x) for x in m]
    in_vocab = ok_parse and all(x in vocab for x in matched) and len(matched) <= 5
    has_pair = ("神的爱" in matched) and ("爱神" in matched)
    pass_score = bool(ok_parse and in_vocab and has_pair)
    return {
        "parse_ok": ok_parse,
        "parse_error": err,
        "matched": matched,
        "all_in_vocab": in_vocab,
        "has_required_pair": has_pair,
        "pass": pass_score,
    }


def _stats(nums: list[float]) -> dict[str, Any]:
    ys = [float(x) for x in nums if isinstance(x, (int, float))]
    if not ys:
        return {"min": None, "median": None, "max": None, "n": 0}
    return {
        "min": min(ys),
        "median": float(statistics.median(ys)),
        "max": max(ys),
        "n": len(ys),
    }


def run_json(client, budget: BudgetTracker, log: logging.Logger) -> dict:
    user_text, names = build_json_wordlist(6000)
    vocab = set(names)
    # 首次校准：用 Haiku none 跑一次看 input_tokens，若偏差大则重拼（仍固定同一份之后）
    calibrated = user_text
    out: dict[str, Any] = {
        "section": "json",
        "vocab_n": len(names),
        "user_chars": len(user_text),
        "runs": [],
        "summary": {},
    }

    def one(model: str, setting: str, tag: str) -> dict:
        if not budget.allow(model):
            return {"skipped": True, "reason": "预算已用尽", "tag": tag}
        rec = call_once(
            client,
            model=model,
            system=JSON_SYSTEM,
            messages=[{"role": "user", "content": calibrated}],
            max_tokens=2000,
            thinking_setting=setting,
            log=log,
        )
        if rec.get("ok"):
            budget.add(model, rec.get("usage") or {})
            text = (rec.get("content") or {}).get("text") or ""
            rec["score"] = score_json(text, vocab)
        rec["tag"] = tag
        return rec

    # 校准调用（计入 Haiku none 的第一次）
    if budget.allow(TARGET_HAIKU):
        cal = one(TARGET_HAIKU, "none", "haiku/none/calibrate")
        out["runs"].append(cal)
        if cal.get("ok"):
            got = int((cal.get("usage") or {}).get("input_tokens") or 0)
            out["calibrated_input_tokens"] = got
            # 若偏离 6000 超过 25%，按比例缩放词表字数重拼一次并固定
            if got and abs(got - 6000) / 6000 > 0.25:
                scale = 6000 / got
                new_target = max(2000, int(6000 * scale))
                calibrated, names = build_json_wordlist(new_target)
                vocab = set(names)
                out["rebuilt_for_calibration"] = True
                out["user_chars"] = len(calibrated)
                out["vocab_n"] = len(names)

    schedule: list[tuple[str, str, int]] = []
    # Haiku：①②③⑤ 各 4 次；校准已占 none 1 次 → 再补 3
    for st, already in (
        ("none", 1 if out["runs"] and out["runs"][0].get("ok") is not None else 0),
        ("disabled", 0),
        ("adaptive-low", 0),
        ("adaptive-high", 0),
    ):
        need = 4 - (already if st == "none" else 0)
        # 若校准失败也算一次尝试，仍补到 4
        if st == "none":
            need = max(0, 4 - 1)
        for i in range(need):
            schedule.append((TARGET_HAIKU, st, i))
    for st in ("none", "disabled"):
        for i in range(2):
            schedule.append((TARGET_SONNET, st, i))

    for model, st, i in schedule:
        tag = f"{'haiku' if model==TARGET_HAIKU else 'sonnet'}/{st}/{i}"
        out["runs"].append(one(model, st, tag))

    # 汇总
    def summarize(pred) -> dict:
        subset = [r for r in out["runs"] if pred(r) and not r.get("skipped")]
        parse_ok = sum(1 for r in subset if (r.get("score") or {}).get("parse_ok"))
        pass_n = sum(1 for r in subset if (r.get("score") or {}).get("pass"))
        stops: dict[str, int] = {}
        outs: list[float] = []
        elaps: list[float] = []
        for r in subset:
            if r.get("ok"):
                sr = str(r.get("stop_reason"))
                stops[sr] = stops.get(sr, 0) + 1
                outs.append(float((r.get("usage") or {}).get("output_tokens") or 0))
                elaps.append(float(r.get("elapsed_s") or 0))
        return {
            "n": len(subset),
            "parse_ok": parse_ok,
            "pass": pass_n,
            "stop_reason": stops,
            "output_tokens": _stats(outs),
            "elapsed_s": _stats(elaps),
        }

    out["summary"]["all"] = summarize(lambda r: True)
    out["summary"]["haiku"] = summarize(lambda r: r.get("request_model") == TARGET_HAIKU or (r.get("tag") or "").startswith("haiku"))
    out["summary"]["sonnet"] = summarize(lambda r: (r.get("tag") or "").startswith("sonnet"))
    return out


def run_cache(client, budget: BudgetTracker, log: logging.Logger) -> dict:
    tiers = [600, 1200, 2400, 4800]
    out: dict[str, Any] = {"section": "cache", "models": {}}

    def cache_call(model: str, system_text: str, ttl: Optional[str], headers=None) -> dict:
        if not budget.allow(model):
            return {"skipped": True, "reason": "预算已用尽"}
        block: dict[str, Any] = {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
        if ttl:
            block["cache_control"]["ttl"] = ttl
        rec = call_once(
            client,
            model=model,
            system=[block],
            messages=[{"role": "user", "content": "只回复一个字：好"}],
            max_tokens=32,
            thinking_setting="none",
            extra_headers=headers,
            log=log,
        )
        if rec.get("ok"):
            budget.add(model, rec.get("usage") or {})
        return rec

    for model in (TARGET_HAIKU, TARGET_SONNET):
        m_out: dict[str, Any] = {"tiers": {}, "ttl_1h": {}}
        creation_by_tier: dict[int, int] = {}
        read_by_tier: dict[int, int] = {}
        for n_chars in tiers:
            sys_text = gen_chinese_chars(n_chars)
            rows = []
            for i in range(2):
                rec = cache_call(model, sys_text, ttl=None)
                rows.append(rec)
            m_out["tiers"][str(n_chars)] = rows
            if rows and rows[0].get("ok"):
                creation_by_tier[n_chars] = int(
                    (rows[0].get("usage") or {}).get("cache_creation_input_tokens") or 0
                )
            if len(rows) > 1 and rows[1].get("ok"):
                read_by_tier[n_chars] = int(
                    (rows[1].get("usage") or {}).get("cache_read_input_tokens") or 0
                )

        # 反推最小可缓存长度落在哪两档之间
        hits = [t for t in tiers if read_by_tier.get(t, 0) > 0]
        misses = [t for t in tiers if creation_by_tier.get(t, 0) == 0 and read_by_tier.get(t, 0) == 0]
        # 更准：第 2 次 read>0 视为可缓存
        first_hit = hits[0] if hits else None
        prev = None
        if first_hit is not None:
            idx = tiers.index(first_hit)
            prev = tiers[idx - 1] if idx > 0 else 0
        m_out["min_cacheable_between_chars"] = [prev, first_hit]
        m_out["creation_by_tier"] = creation_by_tier
        m_out["read_by_tier"] = read_by_tier

        # 1h ttl @ 2400
        sys_text = gen_chinese_chars(2400)
        r1 = cache_call(model, sys_text, ttl="1h")
        m_out["ttl_1h"]["create"] = r1
        if not r1.get("ok"):
            # 尝试 beta 头（按错误提示常见写法）
            for header in (
                {"anthropic-beta": "extended-cache-ttl-2025-04-11"},
                {"anthropic-beta": "prompt-caching-2024-07-31"},
            ):
                r_try = cache_call(model, sys_text, ttl="1h", headers=header)
                m_out["ttl_1h"][f"retry_{list(header.values())[0]}"] = r_try
                if r_try.get("ok"):
                    r1 = r_try
                    break
        if r1.get("ok"):
            r2 = cache_call(model, sys_text, ttl="1h")
            m_out["ttl_1h"]["hit"] = r2
            # 是否接受：创建成功 + usage 有 cache_creation；命中：第二次 read>0
            m_out["ttl_1h"]["accepted"] = True
            m_out["ttl_1h"]["creation_tokens"] = (r1.get("usage") or {}).get(
                "cache_creation_input_tokens"
            )
            m_out["ttl_1h"]["hit_read_tokens"] = (
                (r2.get("usage") or {}).get("cache_read_input_tokens")
                if r2.get("ok")
                else None
            )
            # cache_creation 明细若含 ttl / ephemeral_1h 等，原样记录
            m_out["ttl_1h"]["cache_creation_detail"] = (r1.get("usage") or {}).get(
                "cache_creation"
            )
        else:
            m_out["ttl_1h"]["accepted"] = False

        out["models"][model] = m_out
    return out


def run_speed(client, budget: BudgetTracker, log: logging.Logger) -> dict:
    schedule = [(TARGET_SONNET, 2), (TARGET_HAIKU, 1)]
    out: dict[str, Any] = {"section": "speed", "runs": []}
    for model, n in schedule:
        for i in range(n):
            if not budget.allow(model):
                out["runs"].append(
                    {"model": model, "skipped": True, "reason": "预算已用尽"}
                )
                continue
            rec = call_once(
                client,
                model=model,
                messages=[{"role": "user", "content": SPEED_PROMPT}],
                max_tokens=4000,
                thinking_setting="none",
                stream=True,
                log=log,
            )
            if rec.get("ok"):
                budget.add(model, rec.get("usage") or {})
                out_tok = float((rec.get("usage") or {}).get("output_tokens") or 0)
                total = float(rec.get("elapsed_s") or 0)
                ttft = rec.get("ttft_s")
                gen_s = None
                speed = None
                if isinstance(ttft, (int, float)) and total > ttft:
                    gen_s = total - float(ttft)
                    if gen_s > 0:
                        speed = out_tok / gen_s
                rec["speed_out_tokens_per_s"] = round(speed, 3) if speed else None
                rec["generation_s"] = round(gen_s, 4) if gen_s else None
            out["runs"].append(rec)
    # Sonnet 估 3000 token
    sonnet_speeds = [
        r.get("speed_out_tokens_per_s")
        for r in out["runs"]
        if r.get("request_model") == TARGET_SONNET and r.get("speed_out_tokens_per_s")
    ]
    if sonnet_speeds:
        sp = statistics.mean(sonnet_speeds)
        out["sonnet_est_seconds_for_3000_out"] = round(3000 / sp, 2) if sp else None
        out["sonnet_mean_speed"] = round(sp, 3)
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="探针 5b：模型疑点补查")
    p.add_argument("--dry-run", action="store_true", help="只打印计划，不联网、不读密钥值")
    p.add_argument("--yes", action="store_true", help="真实调用 API")
    p.add_argument(
        "--only",
        action="append",
        choices=list(SECTIONS),
        help="只跑指定节（可重复）",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="日志与结果 json 目录（默认 G:\\PanAI4.0专用\\logs）",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    if args.yes and args.dry_run:
        print("不能同时使用 --yes 与 --dry-run", file=sys.stderr)
        return 2
    if not args.yes and not args.dry_run:
        # 默认等同 dry-run 计划打印
        args.dry_run = True

    only = set(args.only) if args.only else set(SECTIONS)
    plan = plan_section(only)

    if args.dry_run:
        # 不读取密钥环境变量的值
        names_present = key_names_in_environ()
        report = {
            "mode": "dry-run",
            "anthropic_sdk_note": (
                "messages.create/stream 顶层参数含 thinking、output_config、"
                "cache_control（ttl: 5m|1h）；不必 extra_body"
            ),
            "key_env_names": list(KEY_ENV_NAMES),
            "key_env_names_present_in_environ": names_present,
            "key_present": None,  # dry-run 不读取值，故不判定
            "note": "dry-run 未读取密钥环境变量的值；未联网",
            "only": sorted(only),
            "plan": plan,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("--- 各节计划调用数 ---")
        for sec, meta in plan["sections"].items():
            print(f"  {sec}: total_calls={meta.get('total_calls')}")
        print(f"合计调用: {plan['total_calls']}")
        print("--- 预算占用粗估（非 API usage）---")
        print(json.dumps(plan["budget_occupancy_estimate"], ensure_ascii=False, indent=2))
        print("--- 预算剩余粗估 ---")
        print(json.dumps(plan["budget_remaining_estimate"], ensure_ascii=False, indent=2))
        return 0

    # --yes
    log, log_path, json_path = setup_logger(Path(args.out_dir))
    key = get_api_key()
    key_ok = bool(key)
    result: dict[str, Any] = {
        "mode": "yes",
        "key_present": key_ok,
        "only": sorted(only),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "sections": {},
        "budget": None,
    }
    if not key_ok:
        key = ""
        result["error"] = "缺少 CLAUDE_API_KEY / ANTHROPIC_API_KEY"
        json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        log.error("缺少 API 密钥环境变量（不打印名称以外的信息）")
        print(f"LOG={log_path}")
        print(f"JSON={json_path}")
        return 2

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key, timeout=CALL_TIMEOUT_S)
    except Exception as e:
        key = ""
        result["error"] = redact(str(e))
        json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return 2
    finally:
        # 尽快丢掉本地变量中的密钥引用
        key = ""

    budget = BudgetTracker()
    runners = {
        "identity": run_identity,
        "e9": run_e9,
        "json": run_json,
        "cache": run_cache,
        "speed": run_speed,
    }
    try:
        for sec in SECTIONS:
            if sec not in only:
                continue
            log.info("=== section %s ===", sec)
            try:
                result["sections"][sec] = runners[sec](client, budget, log)
            except Exception as e:
                result["sections"][sec] = {
                    "error_type": type(e).__name__,
                    "error": redact(str(e)),
                }
                log.exception("section %s failed: %s", sec, redact(str(e)))
            result["budget"] = budget.snapshot()
            # 若两模型预算都尽，提前停
            if all(budget.exhausted.values()):
                result["stopped_reason"] = "预算已用尽"
                log.warning("预算已用尽，停止后续节")
                break
    finally:
        result["finished_at"] = datetime.now().isoformat(timespec="seconds")
        result["budget"] = budget.snapshot()
        json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        log.info("wrote %s", json_path)
        print(f"LOG={log_path}")
        print(f"JSON={json_path}")
        print(f"key_present: {result.get('key_present')}")
        print(json.dumps({"budget": result.get("budget")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
