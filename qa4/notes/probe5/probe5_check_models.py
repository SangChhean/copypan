# -*- coding: utf-8 -*-
"""
E. 新模型参数核实（供 Srey 运行）

默认：只估算请求次数与最高费用（不调 API）。
--dry-run：只检查参数与本地依赖，不联网。
--yes：真实调用 Anthropic Messages API。

密钥：CLAUDE_API_KEY，缺失则回退 ANTHROPIC_API_KEY。不读 .env。
费用上限：预计最高费用 > 1 USD 则拒绝运行。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path(r"G:\PanAI4.0专用\logs")
API_BASE = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
TARGET_HAIKU = "claude-haiku-5-5"
TARGET_SONNET = "claude-sonnet-5-5"
COST_CAP_USD = 1.0

# 保守单价估算（USD / 1M tokens）——仅用于上限闸门；真实价格需人工填
EST_IN_HAIKU = 1.0
EST_OUT_HAIKU = 5.0
EST_IN_SONNET = 3.0
EST_OUT_SONNET = 15.0

SECRET_RE = re.compile(r"(?i)(api[_-]?key|authorization|bearer|x-api-key)\s*[:=]\s*\S+")
# 避免源码出现连续的 s k - 字面量（便于 Select-String 扫密钥）
_SK_PREFIX = "sk" + "-"
SK_RE = re.compile(re.escape(_SK_PREFIX) + r"[A-Za-z0-9_\-]{10,}")


def redact(s: str) -> str:
    s = SECRET_RE.sub(r"\1=***", s)
    s = SK_RE.sub(_SK_PREFIX + "***", s)
    return s


def get_api_key() -> str:
    return (os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def setup_logger(name: str) -> tuple[logging.Logger, Path, Path]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"probe5_{name}_{ts}.log"
    json_path = LOG_DIR / f"probe5_{name}_{ts}.json"
    logger = logging.getLogger(f"probe5_{name}_{ts}")
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
            return True

    logger.addFilter(RedactFilter())
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger, log_path, json_path


def pip_show_anthropic() -> dict:
    try:
        p = subprocess.run(
            [sys.executable, "-m", "pip", "show", "anthropic"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        info = {"returncode": p.returncode, "raw": (p.stdout or "")[:2000]}
        ver = None
        for line in (p.stdout or "").splitlines():
            if line.lower().startswith("version:"):
                ver = line.split(":", 1)[1].strip()
        info["version"] = ver
        return info
    except Exception as e:
        return {"error": redact(str(e)), "version": None}


def gen_chinese_filler(approx_tokens: int) -> str:
    """生成与项目数据无关的固定中文测试文本（约 approx_tokens）。"""
    unit = (
        "甲乙丙丁戊己庚辛壬癸，子丑寅卯辰巳午未申酉戌亥。"
        "春夏秋冬循环往复，东南西北上下左右。"
        "一二三四五六七八九十百千万，测试缓存与延迟所用无意义文本。"
    )
    # 约 1.5 字/token
    need_chars = int(approx_tokens * 1.5)
    reps = max(1, (need_chars // len(unit)) + 1)
    text = (unit * reps)[:need_chars]
    return text


def estimate_tokens(text: str) -> int:
    return max(1, int(round(len(text) / 1.5)))


def plan_requests() -> dict:
    """统计 --yes 将发出的请求结构（两模型各跑一遍）。"""
    # 每模型：
    # E1:1  E2:3  E3:2  E4:2(+可选2)  E5:1  E6:5+1  E7:4  E8:2  E9:3
    per_model_min = 1 + 3 + 2 + 2 + 1 + 5 + 1 + 4 + 2 + 3  # 24
    per_model_max = per_model_min + 2  # E4 升级到 12k 再试
    n_models = 2
    # token 粗估
    sys5k = gen_chinese_filler(5000)
    sys12k = gen_chinese_filler(12000)
    delay_in = gen_chinese_filler(3000)

    # 输入 token 粗算（两模型）
    tok_in = 0
    tok_out = 0
    # E1
    tok_in += 2 * estimate_tokens("只回复一个字：好")
    tok_out += 2 * 16
    # E2 ×3
    tok_in += 2 * 3 * estimate_tokens("只回复一个字：好")
    tok_out += 2 * 3 * 16
    # E3 ×2
    tok_in += 2 * 2 * (estimate_tokens("你是助手。") + estimate_tokens("只回复一个字：好"))
    tok_out += 2 * 2 * 16
    # E4 ×2（5k）+ 可能 ×2（12k）
    tok_in += 2 * 2 * estimate_tokens(sys5k)
    tok_out += 2 * 2 * 32
    tok_in_max = tok_in + 2 * 2 * estimate_tokens(sys12k)
    tok_out_max = tok_out + 2 * 2 * 32
    # E5
    tok_in += 2 * estimate_tokens("用一句话介绍自己。")
    tok_out += 2 * 64
    # E6 ×5 + prefill
    json_task = "只输出 JSON，含字段 a,b,c，值分别为 1,2,3。不要其它文字。"
    tok_in += 2 * 6 * estimate_tokens(json_task)
    tok_out += 2 * 6 * 64
    # E7 ×4 short
    tok_in += 2 * 4 * estimate_tokens("只回复一个字：好")
    tok_out += 2 * 4 * 8  # 实际不会用满 max_tokens
    # E8 ×2
    tok_in += 2 * 2 * estimate_tokens("简要说明 1+1 等于几。")
    tok_out += 2 * 2 * 256
    # E9 ×3
    tok_in += 2 * 3 * estimate_tokens(delay_in + "\n请写约三百字的说明。")
    tok_out += 2 * 3 * 400

    # 费用：按 Sonnet 单价估最高（保守）
    usd_haiku = tok_in / 1e6 * EST_IN_HAIKU + tok_out / 1e6 * EST_OUT_HAIKU
    usd_sonnet = tok_in / 1e6 * EST_IN_SONNET + tok_out / 1e6 * EST_OUT_SONNET
    usd_max = (tok_in_max / 1e6 * EST_IN_SONNET + tok_out_max / 1e6 * EST_OUT_SONNET) + (
        tok_in_max / 1e6 * EST_IN_HAIKU + tok_out_max / 1e6 * EST_OUT_HAIKU
    )
    # 上面 tok_in 已含两模型；再加 12k 增量时需注意重复。简化：用两模型×sonnet单价×max token
    usd_cap_check = (
        (tok_in_max * 2) / 1e6 * EST_IN_SONNET + (tok_out_max * 2) / 1e6 * EST_OUT_SONNET
    ) * 0.5 + (
        (tok_in_max) / 1e6 * EST_IN_HAIKU + (tok_out_max) / 1e6 * EST_OUT_HAIKU
    ) * 0.5
    # 更直白：假设全部按 Sonnet 价（偏高）
    usd_worst = tok_in_max / 1e6 * EST_IN_SONNET + tok_out_max / 1e6 * EST_OUT_SONNET
    # tok_* 已按两模型合计；上面 usd_haiku/sonnet 分计有误。重算：
    # plan 里 tok_in/out 是两模型合计
    usd_worst = tok_in_max / 1e6 * EST_IN_SONNET + tok_out_max / 1e6 * EST_OUT_SONNET

    return {
        "n_models": n_models,
        "requests_per_model_min": per_model_min,
        "requests_per_model_max": per_model_max,
        "requests_total_min": per_model_min * n_models,
        "requests_total_max": per_model_max * n_models,
        "est_input_tokens_min": tok_in,
        "est_output_tokens_min": tok_out,
        "est_input_tokens_max": tok_in_max,
        "est_output_tokens_max": tok_out_max,
        "est_usd_worst_using_sonnet_rates": round(usd_worst, 4),
        "cost_cap_usd": COST_CAP_USD,
        "price_note": "价格需按官方价格页人工填写；此处仅为上限闸门粗估",
        "assumed_rates": {
            "haiku_in": EST_IN_HAIKU,
            "haiku_out": EST_OUT_HAIKU,
            "sonnet_in": EST_IN_SONNET,
            "sonnet_out": EST_OUT_SONNET,
        },
    }


def clip_err(obj: Any, limit: int = 200) -> str:
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    s = redact(s)
    return s[:limit]


def http_json(
    method: str,
    path: str,
    key: str,
    body: dict | None = None,
    stream: bool = False,
    timeout: float = 120.0,
) -> dict:
    """用 httpx（优先）或 requests 调用；不经 anthropic SDK。"""
    url = API_BASE + path
    headers = {
        "x-api-key": key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    t0 = time.perf_counter()
    try:
        import httpx

        if stream:
            # 手动读 SSE
            with httpx.Client(timeout=timeout) as client:
                with client.stream(method, url, headers=headers, json=body) as resp:
                    status = resp.status_code
                    events = []
                    first_text_latency = None
                    text_parts = []
                    usage = None
                    err_body = None
                    if status >= 400:
                        err_body = resp.read().decode("utf-8", errors="replace")
                    else:
                        for line in resp.iter_lines():
                            if not line:
                                continue
                            if line.startswith("data: "):
                                payload = line[6:]
                                events.append(payload[:200])
                                try:
                                    data = json.loads(payload)
                                except Exception:
                                    continue
                                et = data.get("type")
                                if et == "content_block_delta":
                                    delta = (data.get("delta") or {}).get("text") or ""
                                    if delta and first_text_latency is None:
                                        first_text_latency = time.perf_counter() - t0
                                    text_parts.append(delta)
                                if et == "message_delta":
                                    usage = (data.get("usage") or usage)
                                if et == "message_start":
                                    msg = data.get("message") or {}
                                    if msg.get("usage"):
                                        usage = msg.get("usage")
                    return {
                        "ok": status < 400,
                        "status": status,
                        "stream": True,
                        "event_count": len(events),
                        "first_text_latency_s": first_text_latency,
                        "text": "".join(text_parts),
                        "usage": usage,
                        "error": clip_err(err_body) if err_body else None,
                        "elapsed_s": time.perf_counter() - t0,
                    }
        else:
            with httpx.Client(timeout=timeout) as client:
                resp = client.request(method, url, headers=headers, json=body)
                elapsed = time.perf_counter() - t0
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text[:500]}
                err = None
                if resp.status_code >= 400:
                    err_type = None
                    if isinstance(data, dict):
                        err_type = (data.get("error") or {}).get("type")
                        err = {
                            "type": err_type,
                            "message": clip_err((data.get("error") or {}).get("message") or data),
                        }
                    else:
                        err = {"type": None, "message": clip_err(data)}
                return {
                    "ok": resp.status_code < 400,
                    "status": resp.status_code,
                    "data": data if resp.status_code < 400 else None,
                    "error": err,
                    "usage": (data.get("usage") if isinstance(data, dict) else None),
                    "elapsed_s": elapsed,
                }
    except ImportError:
        import requests

        if stream:
            resp = requests.request(
                method, url, headers=headers, json=body, stream=True, timeout=timeout
            )
            status = resp.status_code
            events = []
            first_text_latency = None
            text_parts = []
            usage = None
            if status >= 400:
                return {
                    "ok": False,
                    "status": status,
                    "stream": True,
                    "error": clip_err(resp.text),
                    "elapsed_s": time.perf_counter() - t0,
                }
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: "):
                    payload = line[6:]
                    events.append(payload[:200])
                    try:
                        data = json.loads(payload)
                    except Exception:
                        continue
                    et = data.get("type")
                    if et == "content_block_delta":
                        delta = (data.get("delta") or {}).get("text") or ""
                        if delta and first_text_latency is None:
                            first_text_latency = time.perf_counter() - t0
                        text_parts.append(delta)
                    if et == "message_delta":
                        usage = data.get("usage") or usage
            return {
                "ok": True,
                "status": status,
                "stream": True,
                "event_count": len(events),
                "first_text_latency_s": first_text_latency,
                "text": "".join(text_parts),
                "usage": usage,
                "elapsed_s": time.perf_counter() - t0,
            }
        resp = requests.request(method, url, headers=headers, json=body, timeout=timeout)
        elapsed = time.perf_counter() - t0
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text[:500]}
        err = None
        if resp.status_code >= 400:
            if isinstance(data, dict):
                err = {
                    "type": (data.get("error") or {}).get("type"),
                    "message": clip_err((data.get("error") or {}).get("message") or data),
                }
            else:
                err = {"type": None, "message": clip_err(data)}
        return {
            "ok": resp.status_code < 400,
            "status": resp.status_code,
            "data": data if resp.status_code < 400 else None,
            "error": err,
            "usage": (data.get("usage") if isinstance(data, dict) else None),
            "elapsed_s": elapsed,
        }


def pick_models(model_ids: list[str]) -> dict:
    """从列表中选 haiku/sonnet；优先精确 id。"""
    haiku = TARGET_HAIKU if TARGET_HAIKU in model_ids else None
    sonnet = TARGET_SONNET if TARGET_SONNET in model_ids else None
    haiku_cands = [m for m in model_ids if "haiku" in m.lower()]
    sonnet_cands = [m for m in model_ids if "sonnet" in m.lower()]

    def nearest(cands: list[str], want: str) -> str | None:
        if not cands:
            return None
        # 优先含 5-5 / 5.5 / 4-5 等
        for key in ("5-5", "5.5", "4-5", "4.5", "3-5", "3.5"):
            for m in cands:
                if key in m:
                    return m
        return sorted(cands)[-1]

    if haiku is None:
        haiku = nearest(haiku_cands, TARGET_HAIKU)
    if sonnet is None:
        sonnet = nearest(sonnet_cands, TARGET_SONNET)
    return {
        "target_haiku": TARGET_HAIKU,
        "target_sonnet": TARGET_SONNET,
        "chosen_haiku": haiku,
        "chosen_sonnet": sonnet,
        "haiku_exact": TARGET_HAIKU in model_ids,
        "sonnet_exact": TARGET_SONNET in model_ids,
        "all_haiku": haiku_cands,
        "all_sonnet": sonnet_cands,
    }


def extract_text(data: dict | None) -> str:
    if not data:
        return ""
    parts = []
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts)


def run_suite_for_model(model: str, key: str, log: logging.Logger) -> dict:
    out: dict[str, Any] = {"model": model, "tests": {}}

    def rec(name: str, resp: dict, extra: dict | None = None):
        item = {
            "status": resp.get("status"),
            "ok": resp.get("ok"),
            "error_type": (resp.get("error") or {}).get("type") if isinstance(resp.get("error"), dict) else None,
            "error_message": (
                (resp.get("error") or {}).get("message")
                if isinstance(resp.get("error"), dict)
                else resp.get("error")
            ),
            "usage": resp.get("usage"),
            "elapsed_s": resp.get("elapsed_s"),
        }
        if extra:
            item.update(extra)
        out["tests"][name] = item
        log.info(
            "%s %s status=%s ok=%s err=%s",
            model,
            name,
            item["status"],
            item["ok"],
            item.get("error_message"),
        )

    # E1
    body = {
        "model": model,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "只回复一个字：好"}],
    }
    rec("E1_basic", http_json("POST", "/v1/messages", key, body))

    # E2 temperature
    for t in (0, 0.3, 1.0):
        body = {
            "model": model,
            "max_tokens": 16,
            "temperature": t,
            "messages": [{"role": "user", "content": "只回复一个字：好"}],
        }
        rec(f"E2_temperature_{t}", http_json("POST", "/v1/messages", key, body))

    # E3 system string / cache_control blocks
    body = {
        "model": model,
        "max_tokens": 16,
        "system": "你是助手。",
        "messages": [{"role": "user", "content": "只回复一个字：好"}],
    }
    rec("E3_system_string", http_json("POST", "/v1/messages", key, body))
    body = {
        "model": model,
        "max_tokens": 16,
        "system": [
            {
                "type": "text",
                "text": "你是助手。",
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": "只回复一个字：好"}],
    }
    rec("E3_system_blocks_cache_control", http_json("POST", "/v1/messages", key, body))

    # E4 prompt cache
    def cache_trial(n_tok: int, tag: str):
        sys_text = gen_chinese_filler(n_tok)
        body = {
            "model": model,
            "max_tokens": 32,
            "system": [
                {
                    "type": "text",
                    "text": sys_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": "只回复一个字：好"}],
        }
        r1 = http_json("POST", "/v1/messages", key, body)
        r2 = http_json("POST", "/v1/messages", key, body)
        u1 = r1.get("usage") or {}
        u2 = r2.get("usage") or {}
        # usage 可能在 data 里
        if not u1 and r1.get("data"):
            u1 = (r1["data"] or {}).get("usage") or {}
        if not u2 and r2.get("data"):
            u2 = (r2["data"] or {}).get("usage") or {}
        rec(
            f"E4_cache_{tag}_first",
            r1,
            {
                "cache_creation_input_tokens": u1.get("cache_creation_input_tokens"),
                "cache_read_input_tokens": u1.get("cache_read_input_tokens"),
                "usage": u1,
            },
        )
        rec(
            f"E4_cache_{tag}_second",
            r2,
            {
                "cache_creation_input_tokens": u2.get("cache_creation_input_tokens"),
                "cache_read_input_tokens": u2.get("cache_read_input_tokens"),
                "usage": u2,
            },
        )
        created = u1.get("cache_creation_input_tokens") or 0
        return bool(created)

    ok5k = cache_trial(5000, "5k")
    if not ok5k:
        log.info("%s E4 5k 未缓存成功，改试 12k", model)
        cache_trial(12000, "12k")

    # E5 stream
    body = {
        "model": model,
        "max_tokens": 64,
        "stream": True,
        "messages": [{"role": "user", "content": "用一句话介绍自己。"}],
    }
    r = http_json("POST", "/v1/messages", key, body, stream=True)
    rec(
        "E5_stream",
        r,
        {
            "first_text_latency_s": r.get("first_text_latency_s"),
            "event_count": r.get("event_count"),
            "usage_present": bool(r.get("usage")),
            "text_preview": (r.get("text") or "")[:40],
        },
    )

    # E6 JSON format ×5 + prefill
    json_task = "只输出 JSON，含字段 a,b,c，值分别为 1,2,3。不要其它文字。"
    ok_n = 0
    for i in range(5):
        body = {
            "model": model,
            "max_tokens": 64,
            "messages": [{"role": "user", "content": json_task}],
        }
        r = http_json("POST", "/v1/messages", key, body)
        text = extract_text(r.get("data"))
        parsed_ok = False
        try:
            # 截取首个 {...}
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                json.loads(m.group(0))
                parsed_ok = True
                ok_n += 1
        except Exception:
            parsed_ok = False
        rec(f"E6_json_trial_{i+1}", r, {"text_preview": text[:60], "json_ok": parsed_ok})
    out["tests"]["E6_json_success_count"] = {"ok_n": ok_n, "total": 5}

    # assistant 预填 "{"
    body = {
        "model": model,
        "max_tokens": 64,
        "messages": [
            {"role": "user", "content": json_task},
            {"role": "assistant", "content": "{"},
        ],
    }
    rec("E6_assistant_prefill_brace", http_json("POST", "/v1/messages", key, body))

    # E7 max_tokens ceilings
    for mt in (8192, 16000, 32000, 64000):
        body = {
            "model": model,
            "max_tokens": mt,
            "messages": [{"role": "user", "content": "只回复一个字：好"}],
        }
        rec(f"E7_max_tokens_{mt}", http_json("POST", "/v1/messages", key, body))

    # E8 thinking
    body = {
        "model": model,
        "max_tokens": 4096,
        "thinking": {"type": "enabled", "budget_tokens": 1024},
        "messages": [{"role": "user", "content": "简要说明 1+1 等于几。"}],
    }
    rec("E8_thinking_enabled", http_json("POST", "/v1/messages", key, body))
    body = {
        "model": model,
        "max_tokens": 4096,
        "thinking": {"type": "adaptive"},
        "messages": [{"role": "user", "content": "简要说明 1+1 等于几。"}],
    }
    rec("E8_thinking_adaptive", http_json("POST", "/v1/messages", key, body))

    # E9 latency baseline
    delay_prompt = gen_chinese_filler(3000) + "\n请根据上文风格，写大约三百字的说明性文字。"
    latencies = []
    for i in range(3):
        body = {
            "model": model,
            "max_tokens": 512,
            "messages": [{"role": "user", "content": delay_prompt}],
        }
        r = http_json("POST", "/v1/messages", key, body, timeout=180.0)
        latencies.append(r.get("elapsed_s"))
        rec(f"E9_latency_{i+1}", r)
    xs = sorted(x for x in latencies if isinstance(x, (int, float)))
    med = xs[len(xs) // 2] if xs else None
    out["tests"]["E9_latency_median_s"] = {"median_s": med, "samples": latencies}

    return out


def dry_run(log: logging.Logger) -> dict:
    plan = plan_requests()
    anth = pip_show_anthropic()
    # 检查 httpx/requests 可导入（不发起请求）
    http_lib = None
    try:
        import httpx  # noqa: F401

        http_lib = "httpx"
    except ImportError:
        try:
            import requests  # noqa: F401

            http_lib = "requests"
        except ImportError:
            http_lib = None
    filler5k = gen_chinese_filler(5000)
    report = {
        "mode": "dry-run",
        "api_base": API_BASE,
        "anthropic_version_header": ANTHROPIC_VERSION,
        "targets": [TARGET_HAIKU, TARGET_SONNET],
        "key_env_checked": ["CLAUDE_API_KEY", "ANTHROPIC_API_KEY"],
        "key_present": bool(get_api_key()),
        "http_lib": http_lib,
        "pip_anthropic": anth,
        "plan": plan,
        "cache_filler_5k_chars": len(filler5k),
        "cache_filler_5k_est_tokens": estimate_tokens(filler5k),
        "price_note": "价格需按官方价格页人工填写",
        "note": "dry-run 不联网；未读取密钥值",
    }
    if http_lib is None:
        raise SystemExit("dry-run 失败：未安装 httpx 或 requests")
    log.info(
        "dry-run OK http_lib=%s anthropic_pkg=%s req_max=%s est_usd_worst=%s",
        http_lib,
        anth.get("version"),
        plan["requests_total_max"],
        plan["est_usd_worst_using_sonnet_rates"],
    )
    return report


def run_yes(log: logging.Logger) -> dict:
    key = get_api_key()
    if not key:
        raise SystemExit("缺少 CLAUDE_API_KEY / ANTHROPIC_API_KEY")

    plan = plan_requests()
    log.info(
        "预计请求 %s–%s 次；粗估最高费用 $%s（闸门 $%s）",
        plan["requests_total_min"],
        plan["requests_total_max"],
        plan["est_usd_worst_using_sonnet_rates"],
        COST_CAP_USD,
    )
    if plan["est_usd_worst_using_sonnet_rates"] > COST_CAP_USD:
        raise SystemExit(
            f"预计最高费用 ${plan['est_usd_worst_using_sonnet_rates']} 超过上限 ${COST_CAP_USD}，拒绝运行"
        )

    # GET /v1/models
    models_resp = http_json("GET", "/v1/models", key)
    model_ids = []
    if models_resp.get("ok") and isinstance(models_resp.get("data"), dict):
        data = models_resp["data"]
        # Anthropic 返回 {"data":[{"id":...},...]} 或直接 list
        items = data.get("data") if isinstance(data.get("data"), list) else data.get("models")
        if items is None and isinstance(data, list):
            items = data
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get("id"):
                    model_ids.append(it["id"])
                elif isinstance(it, str):
                    model_ids.append(it)
    # 有些账号 /v1/models 不可用：允许用目标 id 直接试
    picked = pick_models(model_ids)
    if not picked["chosen_haiku"]:
        picked["chosen_haiku"] = TARGET_HAIKU
        picked["haiku_fallback_assumed"] = True
    if not picked["chosen_sonnet"]:
        picked["chosen_sonnet"] = TARGET_SONNET
        picked["sonnet_fallback_assumed"] = True

    log.info(
        "models listed=%s haiku=%s(exact=%s) sonnet=%s(exact=%s)",
        len(model_ids),
        picked["chosen_haiku"],
        picked["haiku_exact"],
        picked["chosen_sonnet"],
        picked["sonnet_exact"],
    )

    results = []
    for mid in (picked["chosen_haiku"], picked["chosen_sonnet"]):
        results.append(run_suite_for_model(mid, key, log))

    return {
        "mode": "yes",
        "models_http": {
            "status": models_resp.get("status"),
            "ok": models_resp.get("ok"),
            "error": models_resp.get("error"),
            "n_ids": len(model_ids),
            "haiku_sonnet_ids": [m for m in model_ids if "haiku" in m.lower() or "sonnet" in m.lower()],
        },
        "picked": picked,
        "suites": results,
        "pip_anthropic": pip_show_anthropic(),
        "price_note": "价格需按官方价格页人工填写",
        "plan": plan,
    }


def parse_args():
    p = argparse.ArgumentParser(description="probe5 新模型参数核实")
    p.add_argument("--dry-run", action="store_true", help="只检查参数，不联网")
    p.add_argument("--yes", action="store_true", help="真实调用 Anthropic API")
    return p.parse_args()


def main():
    args = parse_args()
    if args.yes and args.dry_run:
        raise SystemExit("不能同时使用 --yes 与 --dry-run")

    log, log_path, json_path = setup_logger("check_models")
    log.info("log=%s", log_path)

    result: dict[str, Any] = {
        "script": "qa4/notes/probe5/probe5_check_models.py",
        "log": str(log_path),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }

    try:
        if args.dry_run:
            result["report"] = dry_run(log)
        elif args.yes:
            # 启动时打印预计最高费用
            plan = plan_requests()
            print(
                f"ESTIMATED_MAX_USD={plan['est_usd_worst_using_sonnet_rates']} "
                f"CAP={COST_CAP_USD} REQUESTS_MAX={plan['requests_total_max']}"
            )
            if plan["est_usd_worst_using_sonnet_rates"] > COST_CAP_USD:
                raise SystemExit("预计最高费用超过 1 USD，拒绝运行")
            result["report"] = run_yes(log)
        else:
            plan = plan_requests()
            result["report"] = {
                "mode": "estimate",
                "plan": plan,
                "pip_anthropic": pip_show_anthropic(),
                "key_present": bool(get_api_key()),
                "message": "未加 --yes，未调用 API。加 --yes 才会真实核实。",
                "price_note": "价格需按官方价格页人工填写",
            }
            print(
                f"ESTIMATED_MAX_USD={plan['est_usd_worst_using_sonnet_rates']} "
                f"CAP={COST_CAP_USD} REQUESTS_MAX={plan['requests_total_max']}"
            )
            log.info(
                "仅估算：请求 %s–%s，粗估最高 $%s",
                plan["requests_total_min"],
                plan["requests_total_max"],
                plan["est_usd_worst_using_sonnet_rates"],
            )
    except Exception as e:
        log.exception("失败: %s", redact(str(e)))
        result["error"] = redact(str(e))
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(1) from e

    result["finished_at"] = datetime.now().isoformat(timespec="seconds")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("结果 JSON: %s", json_path)
    print(f"RESULT_JSON={json_path}")
    print(f"LOG={log_path}")


if __name__ == "__main__":
    main()
