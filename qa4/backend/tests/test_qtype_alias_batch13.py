# -*- coding: utf-8 -*-
"""第13批：题型名接通——coerce 原样保留、话语检索≡核实说法、记录不改写成默认。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QA4_LLM_MODE", "fake")
os.environ.setdefault("QA4_RETRIEVAL_MODE", "fake")
os.environ.setdefault("QA4_JWT_SECRET", "dev-fake-jwt-not-a-real-secret")

from pipeline.caps import caps_for
from pipeline.context import RequestContext
from pipeline import step07_judge
from pipeline.schemas import (
    Plan,
    QType,
    SubQuestion,
    behavior_alias,
    coerce_qtype,
    is_layer1_only_type,
    is_verify_like,
)


_KEEP_AS_IS = [
    "真理",
    "定义",
    "比较",
    "汇集",
    "发展",
    "列举",
    "个人经历",
    "团体实行",
    "召会生活",
    "话语检索",
    "反找经文",
    "人物与历史",
    "预表与象征",
    "核实说法",
    "默认",
]


class TestCoerceAndAlias(unittest.TestCase):
    def test_coerce_keeps_known_names(self):
        for name in _KEEP_AS_IS:
            self.assertEqual(coerce_qtype(name), name, name)
            self.assertIn(name, {t.value for t in QType})

    def test_coerce_unknown_falls_back_default(self):
        self.assertEqual(coerce_qtype("乱写的题型"), "默认")
        self.assertEqual(coerce_qtype(""), "默认")
        self.assertEqual(coerce_qtype(None), "默认")

    def test_plan_preserves_new_names(self):
        for name in ("真理", "列举", "话语检索", "人物与历史", "预表与象征"):
            p = Plan(
                main_type=name,
                subquestions=[SubQuestion(text="问", qtype=name)],
            )
            self.assertEqual(p.main_type, name)
            self.assertEqual(p.subquestions[0].qtype, name)

    def test_behavior_alias(self):
        self.assertEqual(behavior_alias("话语检索"), "核实说法")
        self.assertEqual(behavior_alias("核实说法"), "核实说法")
        self.assertEqual(behavior_alias("真理"), "默认")
        self.assertEqual(behavior_alias("列举"), "默认")
        self.assertEqual(behavior_alias("人物与历史"), "默认")
        self.assertEqual(behavior_alias("预表与象征"), "默认")
        self.assertEqual(behavior_alias("定义"), "定义")
        self.assertTrue(is_verify_like("话语检索"))
        self.assertTrue(is_verify_like("核实说法"))
        self.assertTrue(is_layer1_only_type("话语检索"))
        self.assertTrue(is_layer1_only_type("核实说法"))
        self.assertTrue(is_layer1_only_type("反找经文"))
        self.assertFalse(is_layer1_only_type("真理"))

    def test_caps_alias_matches_default_or_verify(self):
        d = caps_for("默认")
        self.assertEqual(caps_for("真理"), d)
        self.assertEqual(caps_for("列举"), d)
        # 话语检索：配置无独立层 caps 时经 alias 回落默认；layer1_only 不走 caps 第 2–5 层
        v = caps_for("核实说法")
        # 核实说法未在 caps 表 → 回落默认；话语检索同
        self.assertEqual(caps_for("话语检索"), v)
        self.assertEqual(v, d)


class TestVerifyLikeJudge(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from core.es_client import FakeEsClient
        from core.neo4j_client import FakeNeo4jClient
        from core.redis_store import MemoryStore
        from config import get_settings, reset_settings_cache
        from pipeline.deps import build_deps
        from tests._fast_hymn_env import attach_stub_to_deps

        reset_settings_cache()
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        settings = get_settings(require_runtime=False)
        settings.data_dir = data
        settings.traces_db_path = data / "t.db"
        self.deps = build_deps(
            settings,
            store=MemoryStore(prefix="b13:"),
            es=FakeEsClient(reachable=True),
            neo4j=FakeNeo4jClient(reachable=True),
            traces_db=data / "traces.db",
        )
        attach_stub_to_deps(self.deps)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def _no_retry(self, main: str, qtype: str):
        ctx = RequestContext(request_id="r1", question_orig=f"{main}测试")
        ctx.plan = Plan(main_type=main, subquestions=[SubQuestion(text="测", qtype=qtype)])
        ctx.passages_by_subq = {0: []}
        ctx.passages = []
        n0 = len(self.deps.retrieval.calls)
        vs = await step07_judge.run(ctx, self.deps)
        self.assertFalse(ctx.retried, main)
        self.assertEqual(len(self.deps.retrieval.calls), n0, main)
        self.assertEqual(vs[0].overall, "不够", main)

    async def test_verify_and_discourse_no_retry(self):
        await self._no_retry("核实说法", "核实说法")
        await self._no_retry("话语检索", "话语检索")

    def test_apply_rules_verify_like(self):
        from pipeline.schemas import Passage

        p = Passage(number=1, id="a", index="text_cwwl", text="x", book_title="b", message_title="m")
        for qt in ("核实说法", "话语检索"):
            v = step07_judge.apply_rules(qt, {"keep": [1], "overall": "不够", "has_original": True}, [p])
            self.assertEqual(v.overall, "够", qt)
            v2 = step07_judge.apply_rules(
                qt, {"keep": [1], "overall": "不够", "has_approx": True}, [p]
            )
            self.assertEqual(v2.overall, "够", qt)
            self.assertIn("近似", v2.note)


class TestSkipStep5AndTrace(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from config import get_settings, reset_settings_cache
        from core.es_client import FakeEsClient
        from core.neo4j_client import FakeNeo4jClient
        from core.redis_store import MemoryStore
        from pipeline.deps import build_deps
        from tests._fast_hymn_env import attach_stub_to_deps
        from pipeline.orchestrator import collect_ask

        reset_settings_cache()
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        settings = get_settings(require_runtime=False)
        settings.data_dir = data
        settings.traces_db_path = data / "t.db"
        self.deps = build_deps(
            settings,
            store=MemoryStore(prefix="b13t:"),
            es=FakeEsClient(reachable=True),
            neo4j=FakeNeo4jClient(reachable=True),
            traces_db=data / "traces.db",
        )
        attach_stub_to_deps(self.deps)
        self.collect_ask = collect_ask

        import pipeline.step03_plan as s3

        self._orig = s3.run

        async def _force_plan(ctx, deps, qtype="话语检索"):
            ctx.plan = Plan(
                main_type=qtype,
                subquestions=[SubQuestion(text=ctx.question_orig or ctx.question, qtype=qtype)],
                source="test",
                understanding=f"forced {qtype}",
            )
            return ctx.plan

        self._force_plan = _force_plan

    async def asyncTearDown(self):
        import pipeline.step03_plan as s3

        s3.run = self._orig
        self.tmp.cleanup()

    async def test_discourse_skips_step5_and_keeps_name_in_trace(self):
        import pipeline.step03_plan as s3

        async def force(ctx, deps):
            return await self._force_plan(ctx, deps, "话语检索")

        s3.run = force  # type: ignore
        done = await self.collect_ask(self.deps, question="已过的信息里有否讲到过包罗万有的基督？")
        self.assertEqual(done.get("main_type"), "话语检索")
        rid = done["request_id"]
        rec = self.deps.traces.get(rid)
        self.assertEqual(rec.get("main_type"), "话语检索")
        steps = rec.get("steps") or {}
        self.assertTrue(isinstance(steps, dict), steps)
        self.assertTrue(steps.get("step5", {}).get("skipped"), steps)

    async def test_list_type_preserved_not_rewritten(self):
        import pipeline.step03_plan as s3

        async def force(ctx, deps):
            return await self._force_plan(ctx, deps, "列举")

        s3.run = force  # type: ignore
        done = await self.collect_ask(self.deps, question="神的名有哪些？")
        self.assertEqual(done.get("main_type"), "列举")
        rec = self.deps.traces.get(done["request_id"])
        self.assertEqual(rec.get("main_type"), "列举")


if __name__ == "__main__":
    unittest.main()
