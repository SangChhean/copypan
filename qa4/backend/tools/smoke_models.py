# -*- coding: utf-8 -*-
"""阶段 1b 冒烟：真实 API（需 --yes）。默认 / --dry-run 不联网、不读密钥值。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Optional

# BaseException 用于 apply_exc_meta 注解

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_OUT_DIR = Path(r"G:\PanAI4.0专用\logs")

BUDGET_DAY = {
    "haiku": {"input": 20_000, "output": 5_000},
    "sonnet": {"input": 30_000, "output": 6_000},
}

SECTIONS = (
    "haiku_json",
    "sonnet_json",
    "sonnet_between_tools",
    "sonnet_adaptive",
    "cache_ttl",
    "sonnet_disabled_error",
    "haiku_truncate",
    "sonnet_stream",
)


def _env_names_present() -> list[str]:
    import os

    env = getattr(os, "environ")
    names = ["QA4_ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "ANTHROPIC_API_KEY"]
    return [n for n in names if n in env]


def plan(only: set[str]) -> dict[str, Any]:
    calls = {
        "haiku_json": {"role": "haiku", "n": 1, "est_in": 200, "est_out": 80},
        "sonnet_json": {"role": "sonnet", "n": 1, "est_in": 200, "est_out": 80},
        "sonnet_between_tools": {"role": "sonnet", "n": 1, "est_in": 80, "est_out": 64},
        "sonnet_adaptive": {"role": "sonnet", "n": 2, "est_in": 80, "est_out": 128},
        "cache_ttl": {"role": "haiku", "n": 4, "est_in": 2000, "est_out": 16},
        "sonnet_disabled_error": {"role": "sonnet", "n": 1, "est_in": 40, "est_out": 0},
        "haiku_truncate": {"role": "haiku", "n": 1, "est_in": 40, "est_out": 5},
        "sonnet_stream": {"role": "sonnet", "n": 1, "est_in": 80, "est_out": 400},
    }
    sections = {k: v for k, v in calls.items() if k in only}
    occ = {"haiku": {"input": 0, "output": 0}, "sonnet": {"input": 0, "output": 0}}
    total = 0
    for meta in sections.values():
        total += meta["n"]
        r = meta["role"]
        occ[r]["input"] += meta["n"] * meta["est_in"]
        occ[r]["output"] += meta["n"] * meta["est_out"]
    return {
        "sections": sections,
        "total_calls": total,
        "budget_day_cap": BUDGET_DAY,
        "budget_occupancy_estimate": occ,
    }


def _budget_path(out_dir: Path) -> Path:
    return out_dir / f"smoke_models_budget_{date.today().isoformat()}.json"


def load_budget(out_dir: Path) -> dict[str, Any]:
    p = _budget_path(out_dir)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "date": date.today().isoformat(),
        "used": {
            "haiku": {"input": 0, "output": 0},
            "sonnet": {"input": 0, "output": 0},
        },
    }


def save_budget(out_dir: Path, data: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _budget_path(out_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def budget_allow(data: dict[str, Any], role: str) -> bool:
    used = data["used"][role]
    cap = BUDGET_DAY[role]
    return used["input"] < cap["input"] and used["output"] < cap["output"]


def budget_add(data: dict[str, Any], role: str, usage: dict[str, Any]) -> None:
    u = data["used"][role]
    u["input"] += int(usage.get("input_tokens") or 0)
    u["input"] += int(usage.get("cache_creation_input_tokens") or 0)
    u["input"] += int(usage.get("cache_read_input_tokens") or 0)
    u["output"] += int(usage.get("output_tokens") or 0)


def thinking_tokens_of(usage: Optional[dict[str, Any]]) -> Any:
    if not usage:
        return None
    details = usage.get("output_tokens_details")
    if isinstance(details, dict) and "thinking_tokens" in details:
        return details.get("thinking_tokens")
    return None


def usage_fields(usage: Optional[dict[str, Any]]) -> dict[str, Any]:
    return {
        "output_tokens": (usage or {}).get("output_tokens"),
        "thinking_tokens": thinking_tokens_of(usage),
    }


def apply_exc_meta(
    section: dict[str, Any],
    exc: BaseException,
    *,
    budget: Optional[dict[str, Any]] = None,
    role: Optional[str] = None,
) -> dict[str, Any]:
    """把带 meta 的异常写入节结果，并按 usage 计入预算。"""
    meta = getattr(exc, "meta", None)
    if isinstance(meta, dict) and meta:
        section["meta"] = meta
        usage = meta.get("usage") or {}
        section.update(usage_fields(usage if isinstance(usage, dict) else {}))
        if budget is not None and role and isinstance(usage, dict):
            budget_add(budget, role, usage)
    section.setdefault("error_type", type(exc).__name__)
    section.setdefault("error", str(exc)[:400])
    return section


def _filler(n_chars: int) -> str:
    unit = "甲乙丙丁戊己庚辛壬癸春夏秋冬东南西北一二三四五六七八九十"
    return (unit * (n_chars // len(unit) + 1))[:n_chars]


async def run_yes(out_dir: Path, only: set[str]) -> dict[str, Any]:
    import os

    from core.llm_client import (
        LLMBadRequestError,
        LLMClient,
        LLMStopReasonError,
        load_llm_policy,
        make_redis_usage_sink,
    )
    from core.redis_store import MemoryStore

    env = getattr(os, "environ")
    key = (
        (env.get("QA4_ANTHROPIC_API_KEY") or env.get("CLAUDE_API_KEY") or "")
        .strip()
    )
    key_present = bool(key)
    result: dict[str, Any] = {
        "mode": "yes",
        "key_present": key_present,
        "sections": {},
    }
    if not key_present:
        result["error"] = "缺少 QA4_ANTHROPIC_API_KEY"
        return result

    budget = load_budget(out_dir)
    policy = load_llm_policy()
    store = MemoryStore(prefix="qa4:")
    client = LLMClient(
        api_key=key,
        base_url=(env.get("QA4_ANTHROPIC_BASE_URL") or "").strip()
        or "https://api.anthropic.com",
        policy=policy,
        usage_sink=make_redis_usage_sink(store),
    )
    key = ""

    small_json_sys = '只输出 JSON：{"matched":["神的爱","爱神"]}，不要其它文字。'
    small_json_user = "词表含：神的爱、爱神、十字架。问题：神的爱与爱神有什么关系？"

    async def need(role: str) -> bool:
        if not budget_allow(budget, role):
            return False
        return True

    # 1 Haiku JSON disabled（策略默认）
    if "haiku_json" in only:
        if await need("haiku"):
            try:
                data, res = await client.complete_json(
                    "haiku",
                    small_json_sys,
                    [{"role": "user", "content": small_json_user}],
                    step="smoke_json",
                )
                budget_add(budget, "haiku", res.usage)
                row = {
                    "ok": True,
                    "parsed": data,
                    "response_model": res.response_model,
                    "model_mismatch": res.model_mismatch,
                    "thinking_blocks": res.thinking_blocks,
                    "usage": res.usage,
                }
                row.update(usage_fields(res.usage))
                result["sections"]["haiku_json"] = row
            except Exception as e:
                result["sections"]["haiku_json"] = apply_exc_meta(
                    {"ok": False}, e, budget=budget, role="haiku"
                )
        else:
            result["sections"]["haiku_json"] = {"skipped": True, "reason": "预算已用尽"}

    # 2 Sonnet JSON omit
    if "sonnet_json" in only:
        if await need("sonnet"):
            try:
                data, res = await client.complete_json(
                    "sonnet",
                    small_json_sys,
                    [{"role": "user", "content": small_json_user}],
                    step="smoke_json",
                )
                budget_add(budget, "sonnet", res.usage)
                row = {
                    "ok": True,
                    "thinking_blocks": res.thinking_blocks,
                    "usage": res.usage,
                }
                row.update(usage_fields(res.usage))
                result["sections"]["sonnet_json"] = row
            except Exception as e:
                result["sections"]["sonnet_json"] = apply_exc_meta(
                    {"ok": False}, e, budget=budget, role="sonnet"
                )
        else:
            result["sections"]["sonnet_json"] = {"skipped": True, "reason": "预算已用尽"}

    # 3 between_tools
    if "sonnet_between_tools" in only and await need("sonnet"):
        pol = json.loads(json.dumps(policy))
        pol["roles"]["sonnet"]["thinking"] = {"mode": "between_tools"}
        c2 = LLMClient(
            api_key=env.get("QA4_ANTHROPIC_API_KEY") or env.get("CLAUDE_API_KEY") or "",
            policy=pol,
            usage_sink=make_redis_usage_sink(store),
        )
        try:
            res = await c2.complete(
                "sonnet",
                "只回复一个字：好",
                [{"role": "user", "content": "好"}],
                step="smoke_json",
                max_tokens=32,
            )
            budget_add(budget, "sonnet", res.usage)
            row = {"ok": True, "accepted": True, "usage": res.usage}
            row.update(usage_fields(res.usage))
            result["sections"]["sonnet_between_tools"] = row
        except Exception as e:
            result["sections"]["sonnet_between_tools"] = apply_exc_meta(
                {"ok": False, "accepted": False}, e, budget=budget, role="sonnet"
            )

    # 4 adaptive low/medium
    if "sonnet_adaptive" in only:
        rows = []
        for effort in ("low", "medium"):
            if not await need("sonnet"):
                rows.append({"effort": effort, "skipped": True, "reason": "预算已用尽"})
                continue
            pol = json.loads(json.dumps(policy))
            pol["roles"]["sonnet"]["thinking"] = {"mode": "adaptive", "effort": effort}
            c3 = LLMClient(
                api_key=env.get("QA4_ANTHROPIC_API_KEY") or env.get("CLAUDE_API_KEY") or "",
                policy=pol,
                usage_sink=make_redis_usage_sink(store),
            )
            try:
                res = await c3.complete(
                    "sonnet",
                    "用一两句话说明 1+1。",
                    [{"role": "user", "content": "请回答"}],
                    step="smoke_json",
                    max_tokens=256,
                )
                budget_add(budget, "sonnet", res.usage)
                out_tok = int((res.usage or {}).get("output_tokens") or 0)
                row = {
                    "effort": effort,
                    "ok": True,
                    "accepted": True,
                    "text_len": len(res.text),
                    "ratio_out_tok_per_char": round(out_tok / max(1, len(res.text)), 3),
                    "usage": res.usage,
                }
                row.update(usage_fields(res.usage))
                rows.append(row)
            except Exception as e:
                rows.append(
                    apply_exc_meta(
                        {"effort": effort, "ok": False, "accepted": False},
                        e,
                        budget=budget,
                        role="sonnet",
                    )
                )
        result["sections"]["sonnet_adaptive"] = rows

    # 5 cache 1h + 5m with unique prefixes
    if "cache_ttl" in only:
        cache_out: dict[str, Any] = {}
        for ttl in ("1h", "5m"):
            if not await need("haiku"):
                cache_out[ttl] = {"skipped": True, "reason": "预算已用尽"}
                continue
            prefix = f"smoke-{ttl}-{uuid.uuid4().hex}"
            sys_blocks = [
                {
                    "type": "text",
                    "text": prefix + "\n" + _filler(2400),
                    "cacheable": True,
                }
            ]
            try:
                r1 = await client.complete(
                    "haiku",
                    sys_blocks,
                    [{"role": "user", "content": "只回复一个字：好"}],
                    step="smoke_json",
                    max_tokens=16,
                    cache={"ttl": ttl},
                )
                budget_add(budget, "haiku", r1.usage)
                r2 = await client.complete(
                    "haiku",
                    sys_blocks,
                    [{"role": "user", "content": "只回复一个字：好"}],
                    step="smoke_json",
                    max_tokens=16,
                    cache={"ttl": ttl},
                )
                budget_add(budget, "haiku", r2.usage)
                cc = (r1.usage or {}).get("cache_creation") or {}
                cache_out[ttl] = {
                    "ok": True,
                    "create_usage": r1.usage,
                    "hit_usage": r2.usage,
                    "ephemeral_1h_input_tokens": cc.get("ephemeral_1h_input_tokens")
                    if isinstance(cc, dict)
                    else None,
                    "cache_creation_input_tokens": (r1.usage or {}).get(
                        "cache_creation_input_tokens"
                    ),
                    "cache_read_input_tokens": (r2.usage or {}).get(
                        "cache_read_input_tokens"
                    ),
                }
            except Exception as e:
                cache_out[ttl] = apply_exc_meta(
                    {"ok": False}, e, budget=budget, role="haiku"
                )
        result["sections"]["cache_ttl"] = cache_out

    # 6 Sonnet disabled → 400（绕过策略，底层 create）
    if "sonnet_disabled_error" in only and await need("sonnet"):
        try:
            await client._client.messages.create(
                model=client.model_sonnet,
                max_tokens=32,
                thinking={"type": "disabled"},
                messages=[{"role": "user", "content": "只回复：好"}],
            )
            result["sections"]["sonnet_disabled_error"] = {
                "ok": False,
                "note": "unexpected success",
            }
        except Exception as e:
            from core.llm_client import _classify_http_error

            classified = _classify_http_error(e)
            result["sections"]["sonnet_disabled_error"] = {
                "ok": True,
                "raised": type(classified or e).__name__,
                "is_bad_request": isinstance(classified, LLMBadRequestError),
                "error": str(classified or e)[:400],
            }

    # 7 Haiku truncate
    if "haiku_truncate" in only and await need("haiku"):
        try:
            await client.complete(
                "haiku",
                "写一句完整的中文祝福。",
                [{"role": "user", "content": "请写一句完整的话。"}],
                step="smoke_truncate",
                max_tokens=5,
            )
            result["sections"]["haiku_truncate"] = {"ok": False, "note": "expected error"}
        except LLMStopReasonError as e:
            result["sections"]["haiku_truncate"] = apply_exc_meta(
                {
                    "ok": True,
                    "stop_reason": e.stop_reason,
                    "error_type": "LLMStopReasonError",
                },
                e,
                budget=budget,
                role="haiku",
            )
        except Exception as e:
            result["sections"]["haiku_truncate"] = apply_exc_meta(
                {"ok": False}, e, budget=budget, role="haiku"
            )

    # 8 Sonnet stream
    # 流式若中途/结束后抛错：已收到的文本增量视为无效；预算仍按 meta.usage 计入
    if "sonnet_stream" in only and await need("sonnet"):
        try:
            chunks: list[str] = []
            async for delta in client.stream(
                "sonnet",
                "只写正文，不要标题和前言，约两百字说明春天。",
                [{"role": "user", "content": "请开始。"}],
                step="smoke_stream",
                max_tokens=1000,
            ):
                chunks.append(delta)
            res = client.last_stream_result
            if res:
                budget_add(budget, "sonnet", res.usage)
            row = {
                "ok": True,
                "n_chunks": len(chunks),
                "text_len": sum(len(c) for c in chunks),
                "ttft_s": res.ttft_s if res else None,
                "usage": res.usage if res else None,
            }
            row.update(usage_fields(res.usage if res else None))
            result["sections"]["sonnet_stream"] = row
        except Exception as e:
            result["sections"]["sonnet_stream"] = apply_exc_meta(
                {"ok": False, "note": "partial_stream_invalid_if_error"},
                e,
                budget=budget,
                role="sonnet",
            )

    save_budget(out_dir, budget)
    result["budget"] = budget
    return result


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="qa4 阶段 1b 模型冒烟")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--only", action="append", choices=list(SECTIONS))
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = p.parse_args(argv)
    if args.yes and args.dry_run:
        print("不能同时 --yes 与 --dry-run", file=sys.stderr)
        return 2
    if not args.yes:
        args.dry_run = True

    only = set(args.only) if args.only else set(SECTIONS)
    pl = plan(only)

    if args.dry_run:
        report = {
            "mode": "dry-run",
            "key_env_names_present_in_environ": _env_names_present(),
            "key_present": None,
            "note": "dry-run 未读取密钥值；未联网",
            "plan": pl,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("--- 各节计划调用数 ---")
        for k, v in pl["sections"].items():
            print(f"  {k}: n={v['n']} role={v['role']}")
        print(f"合计: {pl['total_calls']}")
        print("--- 预算占用粗估 ---")
        print(json.dumps(pl["budget_occupancy_estimate"], ensure_ascii=False, indent=2))
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run_yes(out_dir, only))
    out = out_dir / f"smoke_models_{date.today().isoformat()}.json"
    # 确保无密钥字段
    assert "api_key" not in json.dumps(result)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"key_present": result.get("key_present"), "out": str(out)}, ensure_ascii=False))
    print(json.dumps(result.get("sections"), ensure_ascii=False, indent=2))
    return 0 if result.get("key_present") else 2


if __name__ == "__main__":
    raise SystemExit(main())
