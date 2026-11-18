# -*- coding: utf-8 -*-
"""阶段 1b LLM 封装单元测试（假 SDK，不联网）。"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.llm_client import (
    LLMBadRequestError,
    LLMClient,
    LLMConfigError,
    LLMEmptyOutputError,
    LLMJsonError,
    LLMModelMismatchError,
    LLMRetryExhaustedError,
    LLMStopReasonError,
    build_thinking_params,
    check_llm_ready,
    load_llm_policy,
    make_redis_usage_sink,
    normalize_system,
    parse_json_loose,
    validate_llm_policy,
)
from core.llm_fake import FakeLLM, FakeScript
from core.ready import build_ready_report
from core.redis_store import MemoryStore


def _policy(**role_overrides) -> dict:
    p = load_llm_policy()
    for role, th in role_overrides.items():
        p["roles"][role]["thinking"] = th
    return p


class FakeMessage:
    def __init__(
        self,
        *,
        text: str = "hello",
        model: str = "claude-haiku-5-5",
        stop_reason: str = "end_turn",
        thinking: bool = False,
        thinking_only: bool = False,
        usage: Optional[dict] = None,
        mid: str = "msg_1",
    ):
        content = []
        if thinking or thinking_only:
            content.append(SimpleNamespace(type="thinking", thinking=""))
        if not thinking_only:
            content.append(SimpleNamespace(type="text", text=text))
        self.content = content
        self.model = model
        self.stop_reason = stop_reason
        self.usage = SimpleNamespace(
            **(
                usage
                or {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "cache_creation": None,
                }
            )
        )
        self.id = mid

    def model_dump(self):
        return {}


class FakeRateLimitError(Exception):
    status_code = 429


class FakeBadRequest(Exception):
    status_code = 400

    def __str__(self):
        return "bad request body"


class FakeTimeout(Exception):
    pass


class FakeStreamCtx:
    def __init__(self, final: FakeMessage, deltas: list[str]):
        self._final = final
        self._deltas = deltas

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for t in self._deltas:
            yield SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(type="text_delta", text=t),
            )

    async def get_final_message(self):
        return self._final


class FakeMessagesAPI:
    def __init__(self):
        self.calls: list[dict] = []
        self.queue: list[Any] = []
        self.create_impl = None

    def enqueue(self, *items):
        self.queue.extend(items)

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.create_impl:
            return await self.create_impl(**kwargs)
        if not self.queue:
            return FakeMessage(model=kwargs.get("model"))
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(kwargs)
        return item

    def stream(self, **kwargs):
        self.calls.append({**kwargs, "_stream": True})
        if self.queue:
            item = self.queue.pop(0)
            if isinstance(item, Exception):
                raise item
            final = item if isinstance(item, FakeMessage) else FakeMessage(model=kwargs.get("model"))
        else:
            final = FakeMessage(model=kwargs.get("model"), text="streamed")
        text = ""
        for b in final.content:
            if getattr(b, "type", None) == "text":
                text += getattr(b, "text", "") or ""
        deltas = [text[i : i + 4] for i in range(0, max(1, len(text)), 4)] if text else ["x"]
        return FakeStreamCtx(final, deltas)


class FakeAsyncClient:
    def __init__(self, messages: FakeMessagesAPI):
        self.messages = messages


def _client(policy=None, **kw) -> LLMClient:
    api = FakeMessagesAPI()
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    c = LLMClient(
        "x",
        policy=policy or load_llm_policy(),
        _client=FakeAsyncClient(api),
        sleep_fn=fake_sleep,
        **kw,
    )
    c._fake_api = api  # type: ignore[attr-defined]
    c._sleeps = sleeps  # type: ignore[attr-defined]
    return c


class TestPolicy(unittest.TestCase):
    def test_default_thinking_params(self):
        p = load_llm_policy()
        self.assertEqual(build_thinking_params("haiku", p), {"thinking": {"type": "disabled"}})
        self.assertEqual(build_thinking_params("sonnet", p), {})

    def test_between_tools_and_adaptive(self):
        p = _policy(sonnet={"mode": "between_tools"})
        self.assertEqual(
            build_thinking_params("sonnet", p), {"thinking": {"type": "between_tools"}}
        )
        p2 = _policy(sonnet={"mode": "adaptive", "effort": "medium"})
        self.assertEqual(
            build_thinking_params("sonnet", p2),
            {"thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}},
        )

    def test_reject_haiku_omit(self):
        p = load_llm_policy()
        p["roles"]["haiku"]["thinking"] = {"mode": "omit"}
        p["roles"]["haiku"]["allow_default_thinking"] = False
        with self.assertRaises(LLMConfigError):
            validate_llm_policy(p)

    def test_reject_sonnet_disabled(self):
        p = load_llm_policy()
        p["roles"]["sonnet"]["thinking"] = {"mode": "disabled"}
        with self.assertRaises(LLMConfigError):
            validate_llm_policy(p)

    def test_reject_unknown_mode(self):
        p = load_llm_policy()
        p["roles"]["haiku"]["thinking"] = {"mode": "weird"}
        with self.assertRaises(LLMConfigError):
            validate_llm_policy(p)


class TestComplete(unittest.IsolatedAsyncioTestCase):
    async def test_no_temperature_no_prefill_haiku_disabled(self):
        c = _client()
        await c.complete(
            "haiku",
            "sys",
            [{"role": "user", "content": "hi"}],
            step="default",
        )
        kw = c._fake_api.calls[0]
        self.assertNotIn("temperature", kw)
        self.assertEqual(kw["thinking"], {"type": "disabled"})
        self.assertTrue(all(m.get("role") != "assistant" for m in kw["messages"]))

    async def test_sonnet_omits_thinking(self):
        c = _client()
        await c.complete(
            "sonnet", "s", [{"role": "user", "content": "x"}], step="default"
        )
        kw = c._fake_api.calls[0]
        self.assertNotIn("thinking", kw)

    async def test_ignore_empty_thinking_take_text(self):
        c = _client()
        c._fake_api.enqueue(
            FakeMessage(text="答案", thinking=True, model="claude-haiku-5-5")
        )
        r = await c.complete(
            "haiku", "s", [{"role": "user", "content": "q"}], step="default"
        )
        self.assertEqual(r.text, "答案")
        self.assertEqual(r.thinking_blocks, 1)

    async def test_thinking_only_empty_error(self):
        records = []
        c = _client(usage_sink=lambda r: records.append(r))
        c._fake_api.enqueue(
            FakeMessage(thinking_only=True, model="claude-haiku-5-5")
        )
        with self.assertRaises(LLMEmptyOutputError) as cm:
            await c.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="default"
            )
        self.assertTrue(cm.exception.meta.get("usage"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].get("ok"), False)
        self.assertEqual(records[0].get("error_type"), "LLMEmptyOutputError")

    async def test_max_tokens_stop_reason(self):
        sentinel = "SENTINEL_SHOULD_NOT_LEAK_IN_META"
        records = []
        c = _client(usage_sink=lambda r: records.append(r))
        c._fake_api.enqueue(
            FakeMessage(
                text=sentinel,
                stop_reason="max_tokens",
                model="claude-haiku-5-5",
                usage={
                    "input_tokens": 11,
                    "output_tokens": 22,
                    "output_tokens_details": {"thinking_tokens": 7},
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "cache_creation": None,
                },
            )
        )
        with self.assertRaises(LLMStopReasonError) as cm:
            await c.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="json"
            )
        self.assertEqual(cm.exception.stop_reason, "max_tokens")
        meta = cm.exception.meta
        self.assertEqual(meta["usage"]["output_tokens"], 22)
        self.assertEqual(meta["text_len"], len(sentinel))
        blob = json.dumps(meta, ensure_ascii=False)
        self.assertNotIn(sentinel, blob)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["ok"], False)
        self.assertEqual(records[0]["error_type"], "LLMStopReasonError")

    async def test_model_mismatch_warn_and_strict(self):
        c = _client()
        c._fake_api.enqueue(FakeMessage(text="ok", model="other-model"))
        with self.assertLogs("qa4.llm", level="WARNING") as cm:
            r = await c.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="default"
            )
        self.assertTrue(any("model_mismatch" in x for x in cm.output))
        self.assertTrue(r.model_mismatch)
        self.assertTrue(r.usage.get("model_mismatch"))

        records = []
        c2 = _client(strict_model=True, usage_sink=lambda r: records.append(r))
        c2._fake_api.enqueue(FakeMessage(text="ok", model="other-model"))
        with self.assertLogs("qa4.llm", level="WARNING"), self.assertRaises(
            LLMModelMismatchError
        ) as cm2:
            await c2.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="default"
            )
        self.assertTrue(cm2.exception.meta.get("usage"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["error_type"], "LLMModelMismatchError")


class TestRetry(unittest.IsolatedAsyncioTestCase):
    async def test_429_retries_then_raises(self):
        c = _client(max_retries=2)
        c._fake_api.enqueue(FakeRateLimitError(), FakeRateLimitError(), FakeRateLimitError())
        with self.assertLogs("qa4.llm", level="WARNING"), self.assertRaises(LLMRetryExhaustedError):
            await c.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="default"
            )
        self.assertEqual(len(c._fake_api.calls), 3)
        self.assertEqual(len(c._sleeps), 2)

    async def test_400_no_retry(self):
        records = []
        c = _client(max_retries=2, usage_sink=lambda r: records.append(r))
        c._fake_api.enqueue(FakeBadRequest())
        with self.assertRaises(LLMBadRequestError):
            await c.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="default"
            )
        self.assertEqual(len(c._fake_api.calls), 1)
        self.assertEqual(c._sleeps, [])
        self.assertEqual(records, [])

    async def test_timeout_retries(self):
        c = _client(max_retries=1)
        c._fake_api.enqueue(FakeTimeout(), FakeMessage(text="ok"))
        with self.assertLogs("qa4.llm", level="WARNING"):
            r = await c.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="default"
            )
        self.assertEqual(r.text, "ok")
        self.assertEqual(r.attempts, 2)
        self.assertEqual(len(c._sleeps), 1)


class TestJson(unittest.IsolatedAsyncioTestCase):
    async def test_fence_and_noise(self):
        self.assertEqual(parse_json_loose('```json\n{"a":1}\n```'), {"a": 1})
        self.assertEqual(parse_json_loose('前缀 {"a":1} 后缀'), {"a": 1})

    async def test_reask_success(self):
        c = _client()
        c._fake_api.enqueue(
            FakeMessage(text="not json", model="claude-haiku-5-5"),
            FakeMessage(text='{"ok":true}', model="claude-haiku-5-5"),
        )
        with self.assertLogs("qa4.llm", level="WARNING"):
            data, res = await c.complete_json(
                "haiku", "s", [{"role": "user", "content": "q"}], step="json"
            )
        self.assertEqual(data, {"ok": True})
        self.assertEqual(len(c._fake_api.calls), 2)

    async def test_reask_fail(self):
        c = _client()
        c._fake_api.enqueue(
            FakeMessage(text="nope", model="claude-haiku-5-5"),
            FakeMessage(text="still", model="claude-haiku-5-5"),
        )
        with self.assertLogs("qa4.llm", level="WARNING"), self.assertRaises(LLMJsonError):
            await c.complete_json(
                "haiku", "s", [{"role": "user", "content": "q"}], step="json"
            )


class TestCacheAndSink(unittest.IsolatedAsyncioTestCase):
    async def test_cache_control_on_cacheable_only(self):
        blocks = normalize_system(
            [
                {"type": "text", "text": "cache me", "cacheable": True},
                {"type": "text", "text": "no", "cacheable": False},
            ],
            default_ttl="1h",
        )
        self.assertEqual(blocks[0]["cache_control"], {"type": "ephemeral", "ttl": "1h"})
        self.assertNotIn("cache_control", blocks[1])

        c = _client()
        await c.complete(
            "haiku",
            [{"type": "text", "text": "x", "cacheable": True}],
            [{"role": "user", "content": "q"}],
            step="default",
            cache={"ttl": "5m"},
        )
        sys_arg = c._fake_api.calls[0]["system"]
        self.assertEqual(sys_arg[0]["cache_control"]["ttl"], "5m")

    async def test_usage_sink_and_redis_fallback(self):
        records = []
        c = _client(usage_sink=lambda r: records.append(r))
        await c.complete(
            "haiku", "s", [{"role": "user", "content": "q"}], step="default"
        )
        self.assertEqual(len(records), 1)
        self.assertIn("usage", records[0])
        self.assertIn("request_model", records[0])

        store = MemoryStore(prefix="qa4:")
        sink = make_redis_usage_sink(store)
        sink({"step": "t", "usage": {}})
        # broken store
        broken = MagicMock()
        broken.push_capped.side_effect = RuntimeError("down")
        sink2 = make_redis_usage_sink(broken)
        with self.assertLogs("qa4.llm", level="WARNING"):
            sink2({"step": "t"})


class TestConcurrencyAndReady(unittest.IsolatedAsyncioTestCase):
    async def test_semaphore_limit(self):
        c = _client(max_concurrency_haiku=1)
        active = 0
        max_active = 0

        async def slow_create(**kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            active -= 1
            return FakeMessage(model=kwargs.get("model"))

        c._fake_api.create_impl = slow_create
        await asyncio.gather(
            c.complete("haiku", "s", [{"role": "user", "content": "1"}], step="default"),
            c.complete("haiku", "s", [{"role": "user", "content": "2"}], step="default"),
        )
        self.assertEqual(max_active, 1)

    def test_readyz_llm_degraded_and_not_ready(self):
        llm_ok = check_llm_ready(
            key_present=False,
            model_haiku="claude-haiku-5-5",
            model_sonnet="claude-sonnet-5-5",
            policy=load_llm_policy(),
        )
        self.assertEqual(llm_ok["status"], "degraded")

        bad = dict(load_llm_policy())
        bad["roles"]["haiku"]["thinking"] = {"mode": "omit"}
        bad["roles"]["haiku"]["allow_default_thinking"] = False
        with self.assertRaises(LLMConfigError):
            validate_llm_policy(bad)

        # via check_llm_ready catching
        # pass invalid by monkey: load fails
        r = check_llm_ready(
            key_present=True,
            model_haiku="h",
            model_sonnet="s",
            policy=bad,
        )
        # validate raises before return — check_llm_ready catches
        self.assertEqual(r["status"], "not_ready")

        report = build_ready_report(
            redis_store=MemoryStore(),
            es_client=type("E", (), {"ping": lambda self: True, "stats_by_logical": lambda self, e: {k: {"status": "ok"} for k in e}})(),
            neo4j_client=type(
                "N",
                (),
                {
                    "ping": lambda self: True,
                    "label_counts": lambda self, lbs: {lb: 1 for lb in lbs},
                },
            )(),
            lookup_dir=Path(__file__).resolve().parents[2] / "data" / "lookups",
            expected={"es": {}, "neo4j": {}},
            llm_settings={
                "key_present": False,
                "model_haiku": "claude-haiku-5-5",
                "model_sonnet": "claude-sonnet-5-5",
                "policy": load_llm_policy(),
            },
        )
        self.assertIn(report["checks"]["llm"]["status"], {"degraded", "ok", "not_ready"})
        if report["checks"]["lookups"]["status"] == "ok":
            self.assertIn(report["status"], {"ok", "degraded"})


class TestFailureMetaAndStream(unittest.IsolatedAsyncioTestCase):
    async def test_stream_truncate_has_meta_and_sink(self):
        records = []
        c = _client(usage_sink=lambda r: records.append(r))
        c._fake_api.enqueue(
            FakeMessage(
                text="partial-out",
                stop_reason="max_tokens",
                model="claude-sonnet-5-5",
                usage={
                    "input_tokens": 5,
                    "output_tokens": 40,
                    "output_tokens_details": {"thinking_tokens": 12},
                },
            )
        )
        got = []
        with self.assertRaises(LLMStopReasonError) as cm:
            async for d in c.stream(
                "sonnet", "s", [{"role": "user", "content": "q"}], step="smoke_stream"
            ):
                got.append(d)
        self.assertTrue(got)  # 抛错前已有增量；调用方须视为无效
        self.assertEqual(cm.exception.meta["usage"]["output_tokens"], 40)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["ok"], False)

    async def test_401_no_usage_record(self):
        class FakeAuth(Exception):
            status_code = 401

        records = []
        c = _client(usage_sink=lambda r: records.append(r))
        c._fake_api.enqueue(FakeAuth())
        with self.assertRaises(Exception):
            await c.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="default"
            )
        self.assertEqual(records, [])


class TestFakeLLM(unittest.IsolatedAsyncioTestCase):
    async def test_injections(self):
        records = []
        fake = FakeLLM(
            scripts={
                "ok": FakeScript(text='{"a":1}'),
                "trunc": FakeScript(
                    stop_reason="max_tokens",
                    text="TRUNC_TEXT",
                    usage={"input_tokens": 1, "output_tokens": 9},
                ),
                "empty": FakeScript(empty_text=True),
                "think": FakeScript(thinking_only=True, thinking_blocks=1),
                "mm": FakeScript(text="x", response_model="other"),
                "badjson": FakeScript(text="not-json"),
                "fence": FakeScript(text='```json\n{"a":1}\n```'),
                "429": FakeScript(status_code=429),
                "400": FakeScript(status_code=400),
            },
            reask_scripts={"badjson": FakeScript(text='{"a":1}')},
            strict_model=True,
            usage_sink=lambda r: records.append(r),
        )
        data, _ = await fake.complete_json(
            "haiku", "s", [{"role": "user", "content": "q"}], step="fence"
        )
        self.assertEqual(data, {"a": 1})

        with self.assertRaises(LLMStopReasonError) as cm:
            await fake.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="trunc"
            )
        self.assertEqual(cm.exception.meta["usage"]["output_tokens"], 9)
        self.assertNotIn("TRUNC_TEXT", json.dumps(cm.exception.meta))
        with self.assertRaises(LLMEmptyOutputError) as cm2:
            await fake.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="empty"
            )
        self.assertTrue(cm2.exception.meta)
        with self.assertRaises(LLMEmptyOutputError) as cm3:
            await fake.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="think"
            )
        self.assertTrue(cm3.exception.meta)
        with self.assertRaises(LLMModelMismatchError) as cm4:
            await fake.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="mm"
            )
        self.assertTrue(cm4.exception.meta)
        with self.assertRaises(LLMRetryExhaustedError):
            await fake.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="429"
            )
        with self.assertRaises(LLMBadRequestError):
            await fake.complete(
                "haiku", "s", [{"role": "user", "content": "q"}], step="400"
            )
        data2, _ = await fake.complete_json(
            "haiku", "s", [{"role": "user", "content": "q"}], step="badjson"
        )
        self.assertEqual(data2, {"a": 1})

        fail_recs = [r for r in records if r.get("ok") is False]
        self.assertGreaterEqual(len(fail_recs), 4)

        chunks = []
        async for d in fake.stream(
            "sonnet", "s", [{"role": "user", "content": "q"}], step="ok"
        ):
            chunks.append(d)
        self.assertTrue(chunks)
        self.assertIsNotNone(fake.last_stream_result)


class TestBaseUrlWarn(unittest.TestCase):
    def test_base_url_conflict_warns(self):
        import os

        env = getattr(os, "environ")
        old = env.get("ANTHROPIC_BASE_URL")
        env["ANTHROPIC_BASE_URL"] = "https://example.invalid/v1"
        try:
            buf = io.StringIO()
            with redirect_stdout(buf), self.assertLogs("qa4.llm", level="WARNING"):
                _client()
            self.assertIn("ANTHROPIC_BASE_URL", buf.getvalue())
        finally:
            if old is None:
                env.pop("ANTHROPIC_BASE_URL", None)
            else:
                env["ANTHROPIC_BASE_URL"] = old


if __name__ == "__main__":
    unittest.main()
