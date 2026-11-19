# -*- coding: utf-8 -*-
"""假模型：与 LLMClient 同接口，供测试与阶段 3 骨架。"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from core.llm_client import (
    LLMAuthError,
    LLMBadRequestError,
    LLMEmptyOutputError,
    LLMJsonError,
    LLMModelMismatchError,
    LLMResult,
    LLMRetryExhaustedError,
    LLMStopReasonError,
    SystemInput,
    parse_json_loose,
)


@dataclass
class FakeScript:
    """单步脚本。"""

    text: str = '{"ok":true}'
    stop_reason: str = "end_turn"
    response_model: Optional[str] = None  # None → 与请求一致
    thinking_blocks: int = 0
    thinking_only: bool = False
    empty_text: bool = False
    status_code: Optional[int] = None  # 429/400/401/...
    timeout: bool = False
    stream_chunks: Optional[list[str]] = None
    usage: Optional[dict[str, Any]] = None
    delay_s: float = 0.0


@dataclass
class FakeLLM:
    """可按 step 注入行为。"""

    scripts: dict[str, FakeScript] = field(default_factory=dict)
    default_script: FakeScript = field(default_factory=FakeScript)
    model_haiku: str = "claude-haiku-5-5"
    model_sonnet: str = "claude-sonnet-5-5"
    strict_model: bool = False
    usage_sink: Any = None
    last_stream_result: Optional[LLMResult] = None
    call_log: list[dict[str, Any]] = field(default_factory=list)
    json_retry: int = 1
    # 可切换的二次返回（JSON 重问）
    reask_scripts: dict[str, FakeScript] = field(default_factory=dict)
    _reask_count: dict[str, int] = field(default_factory=dict)

    def model_for(self, role: str) -> str:
        return self.model_haiku if role == "haiku" else self.model_sonnet

    def _script(self, step: str) -> FakeScript:
        n = self._reask_count.get(step, 0)
        if n > 0 and step in self.reask_scripts:
            return self.reask_scripts[step]
        return self.scripts.get(step) or self.default_script

    def _emit(self, record: dict[str, Any]) -> None:
        if self.usage_sink:
            self.usage_sink(record)

    async def _maybe_fail(self, script: FakeScript, request_model: str) -> None:
        if script.timeout:
            raise LLMRetryExhaustedError("FakeTimeout")
        if script.status_code == 429:
            raise LLMRetryExhaustedError("Fake429")
        if script.status_code in (401, 403):
            raise LLMAuthError("FakeAuth", status_code=script.status_code)
        if script.status_code in (400, 404):
            raise LLMBadRequestError("FakeBadRequest", status_code=script.status_code or 400)

    def _meta_for(
        self,
        *,
        role: str,
        step: str,
        script: FakeScript,
        request_model: str,
        resp_model: str,
        mismatch: bool,
        elapsed_s: float,
        attempts: int = 1,
        ttft_s: Optional[float] = None,
        text_len: int = 0,
        stop_reason: Optional[str] = None,
    ) -> dict[str, Any]:
        usage = dict(
            script.usage
            or {
                "input_tokens": 10,
                "output_tokens": 5,
                "output_tokens_details": {"thinking_tokens": 0},
            }
        )
        usage["model_mismatch"] = mismatch
        return {
            "role": role,
            "step": step,
            "request_model": request_model,
            "response_model": resp_model,
            "id": "fake-id",
            "stop_reason": stop_reason if stop_reason is not None else script.stop_reason,
            "usage": usage,
            "thinking_blocks": script.thinking_blocks,
            "text_len": text_len,
            "elapsed_s": round(elapsed_s, 4),
            "attempts": attempts,
            "ttft_s": ttft_s,
        }

    def _raise_with_meta(
        self,
        exc: Exception,
        meta: dict[str, Any],
        *,
        error_type: str,
    ) -> None:
        self._emit(
            {
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
        )
        raise exc

    def _build_result(
        self,
        *,
        role: str,
        step: str,
        script: FakeScript,
        elapsed_s: float,
        ttft_s: Optional[float] = None,
        attempts: int = 1,
    ) -> LLMResult:
        request_model = self.model_for(role)
        resp_model = (
            script.response_model if script.response_model is not None else request_model
        )
        mismatch = resp_model != request_model
        text = "" if (script.thinking_only or script.empty_text) else script.text
        meta = self._meta_for(
            role=role,
            step=step,
            script=script,
            request_model=request_model,
            resp_model=resp_model,
            mismatch=mismatch,
            elapsed_s=elapsed_s,
            attempts=attempts,
            ttft_s=ttft_s,
            text_len=len(text),
        )
        if mismatch and self.strict_model:
            self._raise_with_meta(
                LLMModelMismatchError(
                    f"response_model={resp_model} != request_model={request_model}",
                    meta=meta,
                ),
                meta,
                error_type="LLMModelMismatchError",
            )
        if script.stop_reason != "end_turn":
            self._raise_with_meta(
                LLMStopReasonError(script.stop_reason, meta=meta),
                meta,
                error_type="LLMStopReasonError",
            )
        if script.thinking_only or script.empty_text:
            self._raise_with_meta(
                LLMEmptyOutputError("fake empty/thinking-only", meta=meta),
                meta,
                error_type="LLMEmptyOutputError",
            )
        usage = dict(meta["usage"])
        result = LLMResult(
            text=script.text,
            request_model=request_model,
            response_model=resp_model,
            id="fake-id",
            stop_reason=script.stop_reason,
            usage=usage,
            thinking_blocks=script.thinking_blocks,
            elapsed_s=elapsed_s,
            attempts=attempts,
            ttft_s=ttft_s,
            model_mismatch=mismatch,
            step=step,
            role=role,
        )
        self._emit(
            {
                "ts": time.time(),
                "ok": True,
                "error_type": None,
                "step": step,
                "role": role,
                "request_model": request_model,
                "response_model": resp_model,
                "stop_reason": script.stop_reason,
                "usage": usage,
                "elapsed_s": elapsed_s,
                "attempts": attempts,
                "model_mismatch": mismatch,
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
        self.call_log.append(
            {
                "op": "complete",
                "role": role,
                "step": step,
                "max_tokens": max_tokens,
                "cache": cache,
                "n_messages": len(messages),
            }
        )
        script = self._script(step)
        t0 = time.perf_counter()
        if script.delay_s:
            await asyncio.sleep(script.delay_s)
        await self._maybe_fail(script, self.model_for(role))
        return self._build_result(
            role=role,
            step=step,
            script=script,
            elapsed_s=time.perf_counter() - t0,
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
        retries = self.json_retry
        last_err: Optional[Exception] = None
        for attempt in range(retries + 1):
            self._reask_count[step] = attempt
            result = await self.complete(
                role, system, messages, step=step, max_tokens=max_tokens, cache=cache
            )
            try:
                return parse_json_loose(result.text), result
            except LLMJsonError as e:
                last_err = e
                if attempt >= retries:
                    break
        raise LLMJsonError(str(last_err) if last_err else "json failed")

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
        """流式假模型。若最终校验失败，已 yield 的增量应视为无效。"""
        self.call_log.append({"op": "stream", "role": role, "step": step})
        script = self._script(step)
        t0 = time.perf_counter()
        await self._maybe_fail(script, self.model_for(role))
        chunks = script.stream_chunks
        if chunks is None:
            base = script.text if not (script.thinking_only or script.empty_text) else "partial"
            if script.stop_reason != "end_turn":
                base = script.text or "partial"
            chunks = [base[i : i + 8] for i in range(0, len(base), 8)] or [""]
        ttft: Optional[float] = None
        for ch in chunks:
            if ttft is None:
                ttft = time.perf_counter() - t0
            if ch:
                yield ch
        self.last_stream_result = self._build_result(
            role=role,
            step=step,
            script=script,
            elapsed_s=time.perf_counter() - t0,
            ttft_s=round(ttft, 4) if ttft is not None else None,
        )


# ---------------------------------------------------------------------------
# 阶段 3：流水线用的确定性假模型（按步骤名返回合法 JSON）
# 标记词只在 fake 模式生效，不进任何真实提示词：
#   【拆】 第 3 步返回复杂 + 2 个子问题（另附 1 个依赖二者的综合子问题，见报告）
#   【诗歌N】 诗歌定向；【敏感】 敏感标记；【错引】 第 8 步引一处不在段落里的话
#   【团体】 第 3 步返回团体实行题型
#   【第3步失败】【第5步失败】【第7步失败】【第8步中途失败】 对应步骤抛错
#   【不够】 第 7 步判不够，放宽重试后仍不够
#   【改写:XXX】 第 2 步把追问改写成 XXX
# ---------------------------------------------------------------------------
import json as _json
import re as _re

_FAKE_VOCAB = ["神的爱", "爱神", "十字架", "召会生活", "生命", "李常受", "倪柝声"]
_HYMN_RE = _re.compile(r"【诗歌(\d+)】")
_REWRITE_RE = _re.compile(r"【改写:([^】]+)】")
_PASSAGE_RE = _re.compile(r"^\[(\d+)\][^\n]*\n([^\n]+)", _re.M)


def _content_of(system: Any, messages: list[dict[str, Any]]) -> str:
    parts = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            parts.extend(str(b.get("text") or "") for b in c if isinstance(b, dict))
    return "\n".join(parts)


def _system_text(system: Any) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n".join(str(b.get("text") or "") for b in system if isinstance(b, dict))
    return ""


def _line_after(content: str, label: str) -> str:
    m = _re.search(_re.escape(label) + r"(.*)", content)
    return (m.group(1).strip() if m else "").strip()


@dataclass
class PipelineFakeLLM:
    model_haiku: str = "claude-haiku-5-5"
    model_sonnet: str = "claude-sonnet-5-5"
    calls: list[dict[str, Any]] = field(default_factory=list)
    last_stream_result: Optional[LLMResult] = None
    usage_sink: Any = None

    def model_for(self, role: str) -> str:
        return self.model_haiku if role == "haiku" else self.model_sonnet

    def reset(self) -> None:
        self.calls.clear()

    def _result(self, role: str, step: str, text: str, t0: float, ttft: Optional[float] = None) -> LLMResult:
        return LLMResult(
            text=text,
            request_model=self.model_for(role),
            response_model=self.model_for(role),
            id="fake-pipeline",
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": max(1, len(text) // 2), "model_mismatch": False},
            thinking_blocks=0,
            elapsed_s=round(time.perf_counter() - t0, 4),
            attempts=1,
            ttft_s=ttft,
            step=step,
            role=role,
        )

    # ---------------- 各步规则 ----------------
    def _step2(self, content: str) -> str:
        m = _REWRITE_RE.search(content)
        if m:
            return m.group(1)
        return _line_after(content, "当前追问：")

    def _step3(self, content: str) -> dict[str, Any]:
        q = _line_after(content, "问题（改写后）：")
        if "【第3步失败】" in content:
            raise LLMBadRequestError("fake step3 failure", status_code=400)
        hm = _HYMN_RE.search(q)
        if hm:
            return {
                "main_type": "诗歌",
                "complex": False,
                "subquestions": [{"text": q, "qtype": "诗歌"}],
                "understanding": f"取诗歌第{hm.group(1)}首",
                "locator": {"hymn_number": int(hm.group(1))},
            }
        if "【拆】" in q:
            return {
                "main_type": "默认",
                "complex": True,
                "subquestions": [
                    {"text": q + "（一）神的爱", "qtype": "定义"},
                    {"text": q + "（二）爱神", "qtype": "个人经历"},
                    {"text": "综合以上两点", "qtype": "默认", "synthesis": True, "depends_on": [0, 1]},
                ],
                "sensitive": "【敏感】" in q,
                "understanding": "占位理解说明",
                "restrictions": [],
            }
        if "【团体】" in q or "团体实行" in q:
            return {
                "main_type": "团体实行",
                "complex": False,
                "subquestions": [{"text": q, "qtype": "团体实行"}],
                "sensitive": "【敏感】" in q,
                "understanding": "团体实行类",
                "restrictions": [],
            }
        if "【比较】" in q or ( "比较" in q and "【拆】" not in q):
            objs = []
            m = _re.search(r"比较(.{1,12})(?:与|和|跟)(.{1,12})", q)
            if m:
                objs = [m.group(1).strip(" ：:的"), m.group(2).strip(" ：:的？?")]
            if len(objs) < 2:
                objs = ["神的爱", "爱神"]
            return {
                "main_type": "比较",
                "complex": False,
                "subquestions": [{"text": q, "qtype": "比较", "compare_objects": objs[:2]}],
                "sensitive": "【敏感】" in q,
                "understanding": "比较两类对象",
                "restrictions": [],
            }
        main = "定义" if "什么是" in q else "默认"
        return {
            "main_type": main,
            "complex": False,
            "subquestions": [{"text": q, "qtype": main}],
            "sensitive": "【敏感】" in q,
            "understanding": "占位理解说明",
            "restrictions": [],
        }

    def _step4(self, content: str) -> dict[str, Any]:
        q = _line_after(content, "问题（改写后）：")
        words = [w for w in _FAKE_VOCAB if w in q]
        words.append("不在原文的示例词")
        return {"words": words}

    def _step5(self, content: str, system: Any) -> dict[str, Any]:
        if "【第5步失败】" in content:
            raise LLMBadRequestError("fake step5 failure", status_code=400)
        sys_text = _system_text(system)
        intr = [x for x in _line_after(sys_text, "内在素质候选：").split("、") if x]
        others: list[str] = []
        for line in sys_text.splitlines():
            if line.startswith("·"):
                others.extend(x for x in line.split("：", 1)[-1].split("、") if x)
        n = max(1, content.count("子问题#"))
        subs: list[dict[str, Any]] = []
        for i in range(n):
            m = _re.search(rf"子问题#{i}[^；\n]*比较对象：([^；\n]+)", content)
            objs = [x.strip() for x in m.group(1).split("、") if x.strip()] if m else []
            rev = others[i * 3 : i * 3 + 3]
            of: dict[str, str] = {}
            if len(objs) >= 2 and rev:
                of[rev[0]] = objs[0]
                if len(rev) > 1:
                    of[rev[1]] = objs[1]
            subs.append(
                {
                    "index": i,
                    "revelation": rev + ["名单外的词"],
                    "intrinsic": intr[i : i + 2],
                    "experience": others[10 + i : 12 + i],
                    "practice": others[20 + i : 22 + i],
                    "object_of": of,
                }
            )
        return {"subquestions": subs}

    def _step7(self, content: str) -> dict[str, Any]:
        if "【第7步失败】" in content:
            raise LLMBadRequestError("fake step7 failure", status_code=400)
        nums = [int(n) for n, _ in _PASSAGE_RE.findall(content)]
        overall = "不够" if "【不够】" in content else "够"
        return {"keep": nums, "drop": [], "overall": overall}

    def _step8_text(self, content: str) -> str:
        found = _PASSAGE_RE.findall(content)
        if "【错引】" in content:
            quote = "这句话不在任何段落里"
            n1 = int(found[0][0]) if found else 1
        elif found:
            first = found[0][1].strip()
            quote = first[2:14] if len(first) > 14 else first
            n1 = int(found[0][0])
        else:
            quote = ""
            n1 = 1
        n2 = f"另一段也提到相关内容「{found[1][1].strip()[:12]}」[{found[1][0]}]。" if len(found) >= 2 else "以上为占位回答。"
        q = f"「{quote}」" if quote else "〔归纳〕材料要点如下。"
        # 与 step8_v0.1 版式一致；正文加长约 300 字，便于开发服观察打字机（约 60 块 × 5 字）
        pad = (
            "召会是基督的身体，是那在万有中充满万有者的丰满。"
            "我们需要在灵里被充满，在召会生活中经历基督作生命，"
            "并在真理上得着供应，好叫众肢体彼此相顾、互相成全。"
            "主的恢复重在基督与召会；我们每天借着祷读主话、呼求主名，"
            "就能被更新而变化，模成神儿子的形像，团体地彰显三一神。"
            "这不是仅仅道理的认识，乃是生命的经历与实行；"
            "当我们照着灵而行，就能实际地活出神人调和的生活。"
        )
        body = f"## 占位总标题\n{q}[{n1}]。\n### 材料要点\n{n2}\n### 补充说明\n{pad}"
        # 约 300 字（不足则再填，过长则截断）
        while len(body) < 300:
            body += "我们继续在召会中追求主。"
        return body[:320]

    # ---------------- 接口 ----------------
    async def complete(self, role, system, messages, *, step, max_tokens=None, cache=None) -> LLMResult:
        t0 = time.perf_counter()
        content = _content_of(system, messages)
        self.calls.append({"op": "complete", "role": role, "step": step, "content": content, "system": system, "cache": cache})
        if step == "step2":
            text = self._step2(content)
        elif step == "step8_summary":
            text = "（归纳）占位摘要。"
        else:
            data = await self._json_for(step, content, system)
            text = _json.dumps(data, ensure_ascii=False)
        return self._result(role, step, text, t0)

    async def _json_for(self, step: str, content: str, system: Any) -> dict[str, Any]:
        if step == "step3":
            return self._step3(content)
        if step == "step4":
            return self._step4(content)
        if step == "step5":
            return self._step5(content, system)
        if step == "step7":
            return self._step7(content)
        return {}

    async def complete_json(self, role, system, messages, *, step, max_tokens=None, cache=None):
        res = await self.complete(role, system, messages, step=step, max_tokens=max_tokens, cache=cache)
        return parse_json_loose(res.text), res

    async def stream(self, role, system, messages, *, step, max_tokens=None, cache=None):
        t0 = time.perf_counter()
        content = _content_of(system, messages)
        self.calls.append({"op": "stream", "role": role, "step": step, "content": content})
        text = self._step8_text(content)
        # 约 60 块：按 5 字切（300 字 → 60 块）
        chunk_size = 5
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)] or [""]
        ttft = None
        # 默认 0（单测快）。开发服 / restart_qa4.bat fake 设 QA4_FAKE_STREAM_DELAY_MS=25。
        try:
            delay_ms = float(os.environ.get("QA4_FAKE_STREAM_DELAY_MS", "0") or "0")
        except ValueError:
            delay_ms = 0.0
        for i, ch in enumerate(chunks):
            if ttft is None:
                ttft = round(time.perf_counter() - t0, 4)
            if "【第8步中途失败】" in content and i == 2:
                raise LLMStopReasonError(
                    "max_tokens",
                    message="fake step8 mid-stream failure",
                    meta={"role": role, "step": step, "usage": {"output_tokens": 3}},
                )
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)
            else:
                await asyncio.sleep(0)
            yield ch
        self.last_stream_result = self._result(role, step, text, t0, ttft)
