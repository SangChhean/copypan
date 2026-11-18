# -*- coding: utf-8 -*-
"""阶段 1b：Anthropic 模型封装（AsyncAnthropic）。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, Union

from core.ready import redact_secrets

logger = logging.getLogger("qa4.llm")

OFFICIAL_BASE = "https://api.anthropic.com"
VALID_MODES = frozenset({"disabled", "omit", "between_tools", "adaptive"})
VALID_EFFORT = frozenset({"low", "medium", "high", "xhigh", "max"})
VALID_TTL = frozenset({"5m", "1h"})

SystemInput = Union[str, list[dict[str, Any]]]
UsageSink = Callable[[dict[str, Any]], Any]


class LLMError(RuntimeError):
    """模型调用错误基类（消息已脱敏）。"""


class LLMConfigError(LLMError):
    pass


class LLMJsonError(LLMError):
    pass


class LLMModelMismatchError(LLMError):
    """响应 model 与请求不一致。可带 meta（含 usage，无文本原文）。"""

    def __init__(self, message: str = "", *, meta: Optional[dict[str, Any]] = None):
        self.meta: dict[str, Any] = dict(meta or {})
        super().__init__(message or "model mismatch")


class LLMStopReasonError(LLMError):
    """stop_reason 非 end_turn。可带 meta（含 usage，无文本原文）。"""

    def __init__(
        self, stop_reason: str, message: str = "", *, meta: Optional[dict[str, Any]] = None
    ):
        self.stop_reason = stop_reason
        self.meta: dict[str, Any] = dict(meta or {})
        super().__init__(message or f"stop_reason={stop_reason}")


class LLMEmptyOutputError(LLMError):
    """无文本块或文本为空。可带 meta（含 usage，无文本原文）。"""

    def __init__(self, message: str = "", *, meta: Optional[dict[str, Any]] = None):
        self.meta: dict[str, Any] = dict(meta or {})
        super().__init__(message or "empty text")


class LLMBadRequestError(LLMError):
    def __init__(self, message: str, *, status_code: int = 400):
        self.status_code = status_code
        super().__init__(message)


class LLMAuthError(LLMError):
    def __init__(self, message: str, *, status_code: int = 401):
        self.status_code = status_code
        super().__init__(message)


class LLMRetryExhaustedError(LLMError):
    pass


@dataclass
class LLMResult:
    text: str
    request_model: str
    response_model: Optional[str]
    id: Optional[str]
    stop_reason: Optional[str]
    usage: dict[str, Any]
    thinking_blocks: int
    elapsed_s: float
    attempts: int
    ttft_s: Optional[float] = None
    model_mismatch: bool = False
    step: str = ""
    role: str = ""


def _hash8(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:8]


def _content_meta(text: str) -> dict[str, Any]:
    return {"len": len(text or ""), "sha8": _hash8(text or "")}


def load_llm_policy(path: Optional[Path] = None) -> dict[str, Any]:
    cfg_dir = Path(__file__).resolve().parents[1] / "config"
    path = path or (cfg_dir / "llm_policy.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_llm_policy(raw)
    return raw


def validate_llm_policy(policy: dict[str, Any]) -> None:
    roles = policy.get("roles") or {}
    for role in ("haiku", "sonnet"):
        if role not in roles:
            raise LLMConfigError(f"llm_policy 缺少 roles.{role}")
        th = (roles[role].get("thinking") or {})
        mode = th.get("mode")
        if mode not in VALID_MODES:
            raise LLMConfigError(f"roles.{role}.thinking.mode 非法：{mode!r}")
        allow_default = bool(roles[role].get("allow_default_thinking"))
        if role == "haiku" and mode == "omit" and not allow_default:
            raise LLMConfigError(
                "haiku 不得使用 thinking.mode=omit（默认会思考）；"
                "请用 disabled，或显式 allow_default_thinking=true"
            )
        if role == "sonnet" and mode == "disabled":
            raise LLMConfigError(
                "sonnet 不得使用 thinking.mode=disabled（API 返回 400）；"
                "请改用 between_tools 或 omit"
            )
        if mode == "adaptive":
            effort = th.get("effort") or "low"
            if effort not in VALID_EFFORT:
                raise LLMConfigError(f"roles.{role}.thinking.effort 非法：{effort!r}")
    cache = policy.get("cache") or {}
    ttl = cache.get("default_ttl", "5m")
    if ttl not in VALID_TTL:
        raise LLMConfigError(f"cache.default_ttl 非法：{ttl!r}")


def build_thinking_params(role: str, policy: dict[str, Any]) -> dict[str, Any]:
    """按策略构造顶层 thinking / output_config；绝不含 temperature。"""
    role_cfg = (policy.get("roles") or {}).get(role) or {}
    th = role_cfg.get("thinking") or {}
    mode = th.get("mode") or "omit"
    if mode == "omit":
        return {}
    if mode == "disabled":
        return {"thinking": {"type": "disabled"}}
    if mode == "between_tools":
        return {"thinking": {"type": "between_tools"}}
    if mode == "adaptive":
        effort = th.get("effort") or "low"
        return {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
        }
    raise LLMConfigError(f"未知 thinking mode：{mode}")


def normalize_system(
    system: SystemInput,
    *,
    default_ttl: str = "5m",
    cache_override: Optional[dict[str, Any]] = None,
) -> Any:
    """字符串原样；块列表可为 cacheable 加 cache_control。"""
    if isinstance(system, str):
        return system
    ttl = (cache_override or {}).get("ttl") or default_ttl
    if ttl not in VALID_TTL:
        ttl = default_ttl
    out: list[dict[str, Any]] = []
    for block in system:
        b = dict(block)
        if b.get("cacheable"):
            b = {k: v for k, v in b.items() if k != "cacheable"}
            if b.get("type") is None:
                b["type"] = "text"
            b["cache_control"] = {"type": "ephemeral", "ttl": ttl}
        else:
            b.pop("cacheable", None)
            # 非 cacheable 不得带 cache_control
            b.pop("cache_control", None)
        out.append(b)
    return out


def extract_text_blocks(content: Any) -> tuple[str, int]:
    """只拼接 type==text；返回 (text, thinking_blocks_count)。"""
    texts: list[str] = []
    thinking_n = 0
    if not content:
        return "", 0
    for b in content:
        if isinstance(b, dict):
            typ = b.get("type")
            if typ == "text":
                texts.append(b.get("text") or "")
            elif typ == "thinking":
                thinking_n += 1
        else:
            typ = getattr(b, "type", None)
            if typ == "text":
                texts.append(getattr(b, "text", None) or "")
            elif typ == "thinking":
                thinking_n += 1
    return "".join(texts), thinking_n


def usage_to_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return dict(usage)
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    d: dict[str, Any] = {}
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
            d[k] = v
    return d


_JSON_FENCE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```$", re.IGNORECASE)


def parse_json_loose(text: str) -> Any:
    t = (text or "").strip()
    m = _JSON_FENCE.match(t)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # 取第一个顶层对象或数组
    for opener, closer in (("{", "}"), ("[", "]")):
        start = t.find(opener)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise LLMJsonError("无法解析 JSON")


def _status_of(exc: BaseException) -> Optional[int]:
    for attr in ("status_code", "status"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    resp = getattr(exc, "response", None)
    if resp is not None:
        st = getattr(resp, "status_code", None)
        if isinstance(st, int):
            return st
    return None


def _is_retryable(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    if any(x in name for x in ("timeout", "connect", "connection", "ratelimit")):
        return True
    st = _status_of(exc)
    if st == 429:
        return True
    if st is not None and 500 <= st <= 599:
        return True
    return False


def _classify_http_error(exc: BaseException) -> Optional[LLMError]:
    st = _status_of(exc)
    msg = redact_secrets(str(exc))
    if st in (401, 403):
        return LLMAuthError(msg, status_code=st)
    if st in (400, 404):
        return LLMBadRequestError(msg, status_code=st or 400)
    return None


@dataclass
class LLMClient:
    """异步模型客户端。"""

    api_key: str
    base_url: str = OFFICIAL_BASE
    model_haiku: str = "claude-haiku-5-5"
    model_sonnet: str = "claude-sonnet-5-5"
    policy: dict[str, Any] = field(default_factory=dict)
    max_concurrency_haiku: int = 16
    max_concurrency_sonnet: int = 6
    timeout_haiku_s: float = 30.0
    timeout_sonnet_s: float = 120.0
    max_retries: int = 2
    strict_model: bool = False
    usage_sink: Optional[UsageSink] = None
    sleep_fn: Callable[[float], Awaitable[None]] = field(
        default=None  # type: ignore[assignment]
    )
    _client: Any = field(default=None, repr=False)
    _sem_haiku: asyncio.Semaphore = field(init=False, repr=False)
    _sem_sonnet: asyncio.Semaphore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.policy:
            self.policy = load_llm_policy()
        else:
            validate_llm_policy(self.policy)
        self._sem_haiku = asyncio.Semaphore(self.max_concurrency_haiku)
        self._sem_sonnet = asyncio.Semaphore(self.max_concurrency_sonnet)
        if self.sleep_fn is None:
            self.sleep_fn = asyncio.sleep
        self._warn_base_url_conflict()
        self._init_sdk()
        # 不在实例上保留明文 key 供日志使用；SDK 已持有
        self._key_present = bool(self.api_key and self.api_key.strip())
        self.api_key = ""

    def _warn_base_url_conflict(self) -> None:
        import os

        env = getattr(os, "environ")
        env_base = (env.get("ANTHROPIC_BASE_URL") or "").strip().rstrip("/")
        cfg = (self.base_url or OFFICIAL_BASE).rstrip("/")
        if env_base and env_base != cfg:
            print(
                "\n"
                "============================================================\n"
                "警告：环境变量 ANTHROPIC_BASE_URL 与 QA4 配置不一致！\n"
                f"  env ANTHROPIC_BASE_URL 已设置（值已脱敏不打印）\n"
                f"  配置 base_url={cfg}\n"
                "  将显式使用配置 base_url 传给 SDK，避免静默改路由。\n"
                "============================================================\n"
            )
            logger.warning(
                "ANTHROPIC_BASE_URL env conflicts with config base_url=%s", cfg
            )

    def _init_sdk(self) -> None:
        if self._client is not None:
            return
        try:
            from anthropic import AsyncAnthropic

            kwargs: dict[str, Any] = {
                "api_key": self.api_key,
                "base_url": self.base_url or OFFICIAL_BASE,
            }
            self._client = AsyncAnthropic(**kwargs)
        except Exception as e:
            raise LLMConfigError(redact_secrets(f"AsyncAnthropic 初始化失败：{e}")) from e

    def model_for(self, role: str) -> str:
        if role == "haiku":
            return self.model_haiku
        if role == "sonnet":
            return self.model_sonnet
        raise LLMConfigError(f"未知 role：{role}")

    def _timeout_for(self, role: str) -> float:
        return self.timeout_haiku_s if role == "haiku" else self.timeout_sonnet_s

    def _sem_for(self, role: str) -> asyncio.Semaphore:
        return self._sem_haiku if role == "haiku" else self._sem_sonnet

    def _max_tokens(self, step: str, override: Optional[int]) -> int:
        if override is not None:
            return int(override)
        steps = self.policy.get("steps") or {}
        meta = steps.get(step) or steps.get("default") or {}
        return int(meta.get("max_tokens") or 2048)

    def _emit_usage(self, record: dict[str, Any]) -> None:
        if self.usage_sink is None:
            logger.info("llm usage sink missing; record step=%s role=%s", record.get("step"), record.get("role"))
            return
        try:
            self.usage_sink(record)
        except Exception as e:
            logger.warning("usage_sink failed: %s", type(e).__name__)

    def _build_call_meta(
        self,
        *,
        role: str,
        step: str,
        request_model: str,
        response_model: Optional[str],
        msg_id: Optional[str],
        stop_reason: Optional[str],
        usage: dict[str, Any],
        thinking_blocks: int,
        text_len: int,
        elapsed_s: float,
        attempts: int,
        ttft_s: Optional[float] = None,
    ) -> dict[str, Any]:
        """失败/成功共用元数据：无用户输入、提示词或生成文本原文。"""
        return {
            "role": role,
            "step": step,
            "request_model": request_model,
            "response_model": response_model,
            "id": msg_id,
            "stop_reason": stop_reason,
            "usage": usage,
            "thinking_blocks": thinking_blocks,
            "text_len": int(text_len),
            "elapsed_s": round(elapsed_s, 4),
            "attempts": attempts,
            "ttft_s": ttft_s,
        }

    def _emit_failure_usage(
        self, meta: dict[str, Any], *, error_type: str
    ) -> None:
        rec = {
            "ts": time.time(),
            "ok": False,
            "error_type": error_type,
            "step": meta.get("step"),
            "role": meta.get("role"),
            "request_model": meta.get("request_model"),
            "response_model": meta.get("response_model"),
            "stop_reason": meta.get("stop_reason"),
            "usage": meta.get("usage") or {},
            "elapsed_s": meta.get("elapsed_s"),
            "attempts": meta.get("attempts"),
            "model_mismatch": bool((meta.get("usage") or {}).get("model_mismatch")),
            "ttft_s": meta.get("ttft_s"),
            "thinking_blocks": meta.get("thinking_blocks"),
            "text_len": meta.get("text_len"),
        }
        self._emit_usage(rec)

    def _build_kwargs(
        self,
        *,
        role: str,
        system: SystemInput,
        messages: list[dict[str, Any]],
        step: str,
        max_tokens: Optional[int],
        cache: Optional[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]]:
        model = self.model_for(role)
        default_ttl = (self.policy.get("cache") or {}).get("default_ttl") or "5m"
        sys_norm = normalize_system(
            system, default_ttl=default_ttl, cache_override=cache
        )
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": self._max_tokens(step, max_tokens),
            "messages": messages,
            "system": sys_norm,
            "timeout": self._timeout_for(role),
        }
        kwargs.update(build_thinking_params(role, self.policy))
        # 硬规则：不得出现 temperature / 预填由调用方保证；此处再剥一次
        kwargs.pop("temperature", None)
        return model, kwargs

    async def _create_with_retry(
        self, role: str, kwargs: dict[str, Any]
    ) -> tuple[Any, int]:
        attempts = 0
        last_exc: Optional[BaseException] = None
        while attempts <= self.max_retries:
            attempts += 1
            try:
                async with self._sem_for(role):
                    msg = await self._client.messages.create(**kwargs)
                return msg, attempts
            except Exception as e:
                last_exc = e
                classified = _classify_http_error(e)
                if classified is not None:
                    raise classified from e
                if attempts <= self.max_retries and _is_retryable(e):
                    delay = (2 ** (attempts - 1)) + random.random() * 0.1
                    logger.warning(
                        "llm retryable error attempt=%s type=%s",
                        attempts,
                        type(e).__name__,
                    )
                    await self.sleep_fn(delay)
                    continue
                raise LLMRetryExhaustedError(
                    redact_secrets(f"{type(e).__name__}: {e}")
                ) from e
        raise LLMRetryExhaustedError(
            redact_secrets(str(last_exc) if last_exc else "retry exhausted")
        )

    def _finalize_result(
        self,
        *,
        role: str,
        step: str,
        request_model: str,
        msg: Any,
        elapsed_s: float,
        attempts: int,
        ttft_s: Optional[float] = None,
    ) -> LLMResult:
        """校验响应；失败时仍写入 usage_sink（ok=false）并在异常上挂 meta。

        流式：若在已产出文本增量后因 stop_reason/空文本等抛错，调用方必须把
        已收到的增量视为无效。
        """
        resp_model = getattr(msg, "model", None)
        mismatch = bool(resp_model and resp_model != request_model)
        if mismatch:
            logger.warning(
                "model_mismatch request=%s response=%s step=%s",
                request_model,
                resp_model,
                step,
            )
        text, thinking_n = extract_text_blocks(getattr(msg, "content", None))
        stop = getattr(msg, "stop_reason", None)
        usage = usage_to_dict(getattr(msg, "usage", None))
        usage["model_mismatch"] = mismatch
        meta = self._build_call_meta(
            role=role,
            step=step,
            request_model=request_model,
            response_model=resp_model,
            msg_id=getattr(msg, "id", None),
            stop_reason=stop,
            usage=usage,
            thinking_blocks=thinking_n,
            text_len=len(text or ""),
            elapsed_s=elapsed_s,
            attempts=attempts,
            ttft_s=ttft_s,
        )
        if mismatch and self.strict_model:
            self._emit_failure_usage(meta, error_type="LLMModelMismatchError")
            raise LLMModelMismatchError(
                f"response_model={resp_model} != request_model={request_model}",
                meta=meta,
            )
        if stop != "end_turn":
            self._emit_failure_usage(meta, error_type="LLMStopReasonError")
            raise LLMStopReasonError(
                str(stop),
                message=f"stop_reason={stop} step={step} role={role}",
                meta=meta,
            )
        if not (text or "").strip():
            self._emit_failure_usage(meta, error_type="LLMEmptyOutputError")
            raise LLMEmptyOutputError(
                f"empty text step={step} role={role}", meta=meta
            )
        result = LLMResult(
            text=text,
            request_model=request_model,
            response_model=resp_model,
            id=getattr(msg, "id", None),
            stop_reason=stop,
            usage=usage,
            thinking_blocks=thinking_n,
            elapsed_s=round(elapsed_s, 4),
            attempts=attempts,
            ttft_s=ttft_s,
            model_mismatch=mismatch,
            step=step,
            role=role,
        )
        self._emit_usage(
            {
                "ts": time.time(),
                "ok": True,
                "error_type": None,
                "step": step,
                "role": role,
                "request_model": request_model,
                "response_model": resp_model,
                "stop_reason": stop,
                "usage": usage,
                "elapsed_s": result.elapsed_s,
                "attempts": attempts,
                "model_mismatch": mismatch,
                "ttft_s": ttft_s,
                "text_meta": _content_meta(text),
            }
        )
        return result

    async def complete(
        self,
        role: str,
        system: SystemInput,
        messages: list[dict[str, Any]],
        *,
        step: str,
        max_tokens: Optional[int] = None,
        cache: Optional[dict[str, Any]] = None,
    ) -> LLMResult:
        logger.info(
            "llm complete role=%s step=%s sys=%s msgs=%s key_present=%s",
            role,
            step,
            _content_meta(system if isinstance(system, str) else json.dumps(system, ensure_ascii=False)),
            len(messages),
            getattr(self, "_key_present", False),
        )
        request_model, kwargs = self._build_kwargs(
            role=role,
            system=system,
            messages=messages,
            step=step,
            max_tokens=max_tokens,
            cache=cache,
        )
        t0 = time.perf_counter()
        msg, attempts = await self._create_with_retry(role, kwargs)
        return self._finalize_result(
            role=role,
            step=step,
            request_model=request_model,
            msg=msg,
            elapsed_s=time.perf_counter() - t0,
            attempts=attempts,
        )

    async def complete_json(
        self,
        role: str,
        system: SystemInput,
        messages: list[dict[str, Any]],
        *,
        step: str,
        max_tokens: Optional[int] = None,
        cache: Optional[dict[str, Any]] = None,
    ) -> tuple[Any, LLMResult]:
        retries = int(self.policy.get("json_retry") or 1)
        last_err: Optional[Exception] = None
        msgs = list(messages)
        for attempt in range(retries + 1):
            result = await self.complete(
                role,
                system,
                msgs,
                step=step,
                max_tokens=max_tokens,
                cache=cache,
            )
            try:
                return parse_json_loose(result.text), result
            except LLMJsonError as e:
                last_err = e
                if attempt >= retries:
                    break
                msgs = list(msgs) + [
                    {"role": "assistant", "content": result.text},
                    {
                        "role": "user",
                        "content": "上一次输出不是合法 JSON。请只输出一个 JSON 对象或数组，不要其它文字。",
                    },
                ]
                logger.warning("json parse failed; reask attempt=%s step=%s", attempt + 1, step)
        raise LLMJsonError(redact_secrets(str(last_err) if last_err else "json failed"))

    async def stream(
        self,
        role: str,
        system: SystemInput,
        messages: list[dict[str, Any]],
        *,
        step: str,
        max_tokens: Optional[int] = None,
        cache: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """异步迭代文本增量；结束后 self.last_stream_result 可用。

        若流结束后校验失败（如 stop_reason=max_tokens），会抛带 meta 的异常，
        并已写入 usage_sink。抛错前可能已 yield 部分文本增量——调用方必须
        将已收到的增量视为无效，不得当作成品。
        """
        request_model, kwargs = self._build_kwargs(
            role=role,
            system=system,
            messages=messages,
            step=step,
            max_tokens=max_tokens,
            cache=cache,
        )
        t0 = time.perf_counter()
        ttft_s: Optional[float] = None
        attempts = 0
        last_exc: Optional[BaseException] = None
        while attempts <= self.max_retries:
            attempts += 1
            try:
                async with self._sem_for(role):
                    stream_cm = self._client.messages.stream(**kwargs)
                    async with stream_cm as stream_ctx:
                        async for event in stream_ctx:
                            et = getattr(event, "type", None)
                            if et == "content_block_delta":
                                delta = getattr(event, "delta", None)
                                if (
                                    delta is not None
                                    and getattr(delta, "type", "") == "text_delta"
                                ):
                                    if ttft_s is None:
                                        ttft_s = time.perf_counter() - t0
                                    text = getattr(delta, "text", "") or ""
                                    if text:
                                        yield text
                        final_msg = await stream_ctx.get_final_message()
                self.last_stream_result = self._finalize_result(
                    role=role,
                    step=step,
                    request_model=request_model,
                    msg=final_msg,
                    elapsed_s=time.perf_counter() - t0,
                    attempts=attempts,
                    ttft_s=round(ttft_s, 4) if ttft_s is not None else None,
                )
                return
            except (LLMStopReasonError, LLMEmptyOutputError, LLMModelMismatchError):
                raise
            except Exception as e:
                last_exc = e
                classified = _classify_http_error(e)
                if classified is not None:
                    raise classified from e
                if attempts <= self.max_retries and _is_retryable(e):
                    delay = (2 ** (attempts - 1)) + random.random() * 0.1
                    await self.sleep_fn(delay)
                    continue
                raise LLMRetryExhaustedError(
                    redact_secrets(f"{type(e).__name__}: {e}")
                ) from e
        raise LLMRetryExhaustedError(
            redact_secrets(str(last_exc) if last_exc else "stream retry exhausted")
        )


def make_redis_usage_sink(redis_store: Any, *, key: str = "llm:usage", cap: int = 500):
    def _sink(record: dict[str, Any]) -> None:
        try:
            redis_store.push_capped(key, json.dumps(record, ensure_ascii=False), cap)
        except Exception as e:
            logger.warning(
                "redis usage sink failed type=%s record_step=%s",
                type(e).__name__,
                record.get("step"),
            )

    return _sink


def check_llm_ready(
    *,
    key_present: bool,
    model_haiku: str,
    model_sonnet: str,
    policy: Optional[dict[str, Any]] = None,
    policy_path: Optional[Path] = None,
) -> dict[str, Any]:
    """只检查配置，不联网。"""
    try:
        if policy is None:
            policy = load_llm_policy(policy_path)
        else:
            validate_llm_policy(policy)
    except Exception as e:
        return {
            "status": "not_ready",
            "message": f"{type(e).__name__}: {redact_secrets(str(e))}",
            "key_present": key_present,
        }
    if not (model_haiku and model_sonnet):
        return {
            "status": "not_ready",
            "message": "模型名未配置",
            "key_present": key_present,
        }
    if not key_present:
        return {
            "status": "degraded",
            "message": "QA4_ANTHROPIC_API_KEY 未配置",
            "key_present": False,
            "models": {"haiku": model_haiku, "sonnet": model_sonnet},
        }
    return {
        "status": "ok",
        "key_present": True,
        "models": {"haiku": model_haiku, "sonnet": model_sonnet},
    }
