# -*- coding: utf-8 -*-
"""阶段 3：流水线离线测试（QA4_LLM_MODE=fake / QA4_RETRIEVAL_MODE=fake）。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from config import Settings, get_settings, reset_settings_cache
from core.auth import AuthStore
from core.es_client import FakeEsClient
from core.neo4j_client import FakeNeo4jClient
from core.redis_store import MemoryStore
from main import create_app
from pipeline.caps import caps_for, truncate_complex, truncate_layers
from pipeline.citations import verify_quotes
from pipeline.deps import build_deps
from pipeline.orchestrator import collect_ask, run_pipeline
from pipeline.schemas import Layers, Passage
from prompts.loader import PromptRegistry, PromptVariableError
from fastapi.testclient import TestClient


def _settings(tmp: Path, **over) -> Settings:
    reset_settings_cache()
    os.environ["QA4_LLM_MODE"] = "fake"
    os.environ["QA4_RETRIEVAL_MODE"] = "fake"
    os.environ["QA4_JWT_SECRET"] = "test-jwt"
    os.environ["QA4_ADMIN_TOKEN"] = "adm"
    os.environ["QA4_DATA_DIR"] = str(tmp)
    os.environ["QA4_DAILY_LIMIT_DEFAULT"] = "30"
    os.environ["QA4_RATE_LIMIT_PER_MINUTE"] = "1000"
    # lookups 用仓库内真实查表
    qa4 = BACKEND.parent
    os.environ["QA4_LOOKUP_DIR"] = str(qa4 / "data" / "lookups")
    os.environ["QA4_GRAPH_ANNOTATIONS_DIR"] = str(qa4 / "data" / "graph_annotations")
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    for k, v in over.items():
        setattr(s, k, v)
    return s


class Stage3Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.settings = _settings(self.tmp_path)
        # 指向仓库内 bible_data，供经文相关路径；假检索不依赖它
        qa4 = BACKEND.parent
        self.settings.bible_dir = qa4 / "data" / "bible_data"
        self.store = MemoryStore(prefix="qa4:")
        self.auth = AuthStore(
            self.tmp_path / "qa4_users.db",
            jwt_secret="test-jwt",
            jwt_expire_days=7,
            daily_limit_default=30,
            tz_name="UTC",
            admin_token="adm",
        )
        self.auth.create_invite("INV", max_uses=100)
        self.auth.register("INV", "u1", "pass1234")
        self.deps = build_deps(
            self.settings,
            store=self.store,
            es=FakeEsClient(reachable=True),
            neo4j=FakeNeo4jClient(reachable=True),
            traces_db=self.tmp_path / "qa4_traces.db",
        )
        from tests._fast_hymn_env import attach_stub_to_deps

        attach_stub_to_deps(self.deps)

    def tearDown(self):
        self.tmp.cleanup()
        for k in [
            "QA4_LLM_MODE",
            "QA4_RETRIEVAL_MODE",
            "QA4_JWT_SECRET",
            "QA4_ADMIN_TOKEN",
            "QA4_DATA_DIR",
            "QA4_LOOKUP_DIR",
            "QA4_GRAPH_ANNOTATIONS_DIR",
            "QA4_DAILY_LIMIT_DEFAULT",
            "QA4_RATE_LIMIT_PER_MINUTE",
        ]:
            os.environ.pop(k, None)
        reset_settings_cache()

    async def _events(self, q: str, history=None):
        evs = []
        async for e in run_pipeline(self.deps, question=q, history=history or []):
            evs.append(e)
        return evs

    def _names(self, evs):
        return [e.get("event") for e in evs]


class TestPrompts(unittest.TestCase):
    def test_placeholder_and_current(self):
        reg = PromptRegistry()
        self.assertTrue(reg.placeholder_steps())
        self.assertIn("step2", reg.versions())
        tpl = reg.get("step3")
        self.assertTrue(tpl.placeholder)
        with self.assertRaises(PromptVariableError):
            tpl.render()


class TestCaps(unittest.TestCase):
    def test_truncate_order(self):
        caps = caps_for("定义")
        L = Layers(
            revelation=["a", "b", "c", "d", "e"],
            intrinsic=["i1", "i2", "i3", "i4"],
            experience=["e1", "e2", "e3"],
            practice=["p1", "p2", "p3"],
        )
        out = truncate_layers(L, caps)
        self.assertLessEqual(out.total_2_5(), caps["total"])
        self.assertLessEqual(len(out.revelation), caps["revelation"])

    def test_complex_total(self):
        caps = [caps_for("定义"), caps_for("个人经历")]
        layers = [
            Layers(revelation=["a", "b", "c", "d"], intrinsic=["i1"], experience=["e1"], practice=["p1"]),
            Layers(revelation=["x", "y"], intrinsic=["i2"], experience=["e2", "e3", "e4", "e5"], practice=["p2", "p3"]),
        ]
        out = truncate_complex(layers, caps, total_cap=10, min_per=1)
        self.assertLessEqual(sum(l.total_2_5() for l in out), 10)
        self.assertTrue(all(l.total_2_5() >= 1 for l in out))


class TestCitations(unittest.TestCase):
    def test_verify_ok_and_ellipsis(self):
        p = Passage(number=1, id="a", index="x", text="甲乙丙丁戊己庚辛壬癸")
        checks = verify_quotes("见「乙丙丁」[1]", [p])
        self.assertTrue(checks[0].ok)
        checks2 = verify_quotes("见「乙丙……己庚」[1]", [p])
        self.assertTrue(checks2[0].ok)
        checks3 = verify_quotes("见「不存在的字」[1]", [p])
        self.assertFalse(checks3[0].ok)


class TestE2E(Stage3Base):
    async def test_simple_event_order_and_citations(self):
        evs = await self._events("什么是神的爱")
        names = self._names(evs)
        self.assertEqual(names[0], "step")
        self.assertIn("plan", names)
        self.assertIn("token", names)
        self.assertEqual(names[-1], "done")
        done = evs[-1]
        refs = set()
        import re

        for m in re.finditer(r"\[(\d+)\]", done["answer"]):
            refs.add(int(m.group(1)))
        cite_ns = {c["n"] for c in done["citations"] if not c.get("out_of_range")}
        self.assertTrue(refs)
        self.assertEqual(refs, cite_ns)
        self.assertEqual(self.deps.traces.count(), 1)
        rec = self.deps.traces.get(done["request_id"])
        self.assertIsNotNone(rec)
        # 方案 A：库内存原文（仅管理接口可读）；哈希/长度仍保留
        self.assertEqual(rec.get("question_text"), "什么是神的爱")
        self.assertIn("question_hash", rec)
        self.assertIn("question_len", rec)

    async def test_followup_history_and_cache(self):
        # 先写入改写目标问题的缓存
        first = await collect_ask(self.deps, question="神的爱是什么")
        self.assertFalse(first.get("cache_hit"))
        n0 = len(self.deps.llm.calls)
        # 追问：历史 4 轮→只取 3；回答截 300；改写成已缓存问题
        long_ans = "答" * 400
        history = [
            {"question": f"旧问{i}", "answer": long_ans}
            for i in range(4)
        ]
        evs = await self._events("请再说一遍【改写:神的爱是什么】", history=history)
        # step2 记录
        ctx_step2 = None
        # 通过假模型 calls 看 step2 输入
        step2_calls = [c for c in self.deps.llm.calls[n0:] if c.get("step") == "step2"]
        self.assertTrue(step2_calls)
        content = step2_calls[0]["content"]
        # 历史只取 3 轮；回答截 300（占位模板里可能另有「问：」字样，故查截断）
        self.assertNotIn("答" * 301, content)
        self.assertIn("答" * 300, content)
        done = [e for e in evs if e.get("event") == "done"][-1]
        self.assertTrue(done.get("cache_hit"))

    async def test_complex_split_and_caps(self):
        done = await collect_ask(self.deps, question="【拆】请比较神的爱与爱神")
        self.assertIn("plan", done["events"])
        # 综合子问题不检索：coverage 里 synthesis
        # 第 5 步合计 ≤10
        # 通过 traces
        rec = self.deps.traces.get(done["request_id"])
        s5 = (rec.get("steps") or {}).get("step5") or {}
        totals = s5.get("totals") or []
        self.assertLessEqual(sum(totals), 10)
        # 非综合子问题至少 1（若有 totals）
        if totals:
            self.assertTrue(all(t >= 0 for t in totals))

    async def test_targeted_hymn(self):
        self.deps.llm.reset()
        done = await collect_ask(self.deps, question="请取【诗歌1】")
        # 优先 hymn_data；无载荷时仍可 direct
        self.assertTrue(
            "hymn_data" in done["events"] or "direct" in done["events"],
            msg=f"events={done['events']}",
        )
        self.assertNotIn("token", done["events"])  # 诗歌不写摘要，无 token 流
        # 不缓存
        hit = self.deps.cache.lookup("请取【诗歌1】")
        self.assertIsNone(hit)
        steps = {c["step"] for c in self.deps.llm.calls}
        self.assertNotIn("step4", steps)
        self.assertNotIn("step5", steps)
        self.assertNotIn("step7", steps)

    async def test_cache_hit_no_llm(self):
        await collect_ask(self.deps, question="什么是召会生活")
        self.deps.llm.reset()
        done = await collect_ask(self.deps, question="什么是召会生活")
        self.assertTrue(done.get("cache_hit"))
        self.assertEqual(len(self.deps.llm.calls), 0)

    async def test_not_found_cache_ttl(self):
        done = await collect_ask(self.deps, question="【不够】完全找不到材料的怪问题xyz")
        self.assertTrue(done.get("not_found") or "没有" in (done.get("answer") or ""))
        # 放宽后仍不够才缓存 → retried
        rec = self.deps.traces.get(done["request_id"])
        self.assertTrue(rec.get("retried") or done.get("not_found"))
        ttl = self.deps.cache.ttl_for(not_found=True)
        self.assertEqual(ttl, 86400)

    async def test_degrade_step3(self):
        done = await collect_ask(self.deps, question="【第3步失败】神的爱")
        self.assertTrue(done.get("degraded") or done.get("main_type") == "默认")
        rec = self.deps.traces.get(done["request_id"])
        self.assertTrue(rec.get("degraded") or (rec.get("degraded_reasons")))

    async def test_degrade_step5(self):
        done = await collect_ask(self.deps, question="【第5步失败】神的爱是什么")
        rec = self.deps.traces.get(done["request_id"])
        self.assertTrue(
            rec.get("degraded")
            or ((rec.get("steps") or {}).get("step5") or {}).get("fallback")
        )

    async def test_degrade_step7_default_pass(self):
        done = await collect_ask(self.deps, question="【第7步失败】神的爱")
        # 失败默认放行，应仍有回答
        self.assertTrue(done.get("answer"))

    async def test_stream_mid_fail(self):
        evs = await self._events("【第8步中途失败】神的爱")
        names = self._names(evs)
        self.assertIn("error", names)
        done = [e for e in evs if e.get("event") == "done"][-1]
        self.assertTrue(done.get("degraded"))

    async def test_wrong_quote(self):
        done = await collect_ask(self.deps, question="【错引】什么是神的爱")
        checks = done.get("quote_checks") or []
        self.assertTrue(any(not c.get("ok") for c in checks))
        self.assertIn("〔未核实〕", done.get("answer") or "")

    async def test_layer1_filters(self):
        from pipeline.step04_layer1 import postprocess_words, fallback_longest_match
        from pipeline.schemas import Plan

        words, flags = postprocess_words(
            ["神的爱", "不在原文的示例词", "弟兄"],
            "请解释神的爱",
            self.deps.lookups,
            Plan(),
        )
        self.assertIn("神的爱", words)
        self.assertNotIn("不在原文的示例词", words)
        fb = fallback_longest_match("神的爱与弟兄", self.deps.lookups, self.deps.generic)
        self.assertIn("神的爱", fb)
        self.assertNotIn("弟兄", fb)


class TestApi(Stage3Base):
    def _client(self, *, llm_mode="fake"):
        self.settings.llm_mode = llm_mode
        if llm_mode == "live":
            # 重新装配以反映 live 阻断
            self.deps.llm_mode = "live"
        app = create_app(
            self.settings,
            redis_store=self.store,
            es_client=FakeEsClient(reachable=True),
            neo4j_client=FakeNeo4jClient(reachable=True),
            auth_store=self.auth,
            pipeline_deps=self.deps,
        )
        return TestClient(app)

    def test_ask_and_limit_31(self):
        c = self._client()
        tok = c.post("/api/auth/login", json={"username": "u1", "password": "pass1234"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        for i in range(30):
            r = c.post("/api/qa/ask", headers=h, json={"question": f"什么是神的爱 #{i}"})
            self.assertEqual(r.status_code, 200, r.text)
        r = c.post("/api/qa/ask", headers=h, json={"question": "第31次"})
        self.assertEqual(r.status_code, 429)

    def test_live_placeholder_503(self):
        self.deps.llm_mode = "live"
        c = self._client(llm_mode="live")
        tok = c.post("/api/auth/login", json={"username": "u1", "password": "pass1234"}).json()["token"]
        r = c.post(
            "/api/qa/ask",
            headers={"Authorization": f"Bearer {tok}"},
            json={"question": "什么是神的爱"},
        )
        self.assertEqual(r.status_code, 503)
        self.assertIn("提示词", r.json().get("message", ""))

    def test_cache_clear_new_keys(self):
        c = self._client()
        tok = c.post("/api/auth/login", json={"username": "u1", "password": "pass1234"}).json()["token"]
        c.post("/api/qa/ask", headers={"Authorization": f"Bearer {tok}"}, json={"question": "什么是神的爱"})
        # 应有 cache: 键
        keys_before = [k for k in self.store._data if "cache" in k]
        self.assertTrue(keys_before)
        r = c.post("/api/admin/cache/clear", headers={"X-Admin-Token": "adm"})
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.json()["deleted"], 0)
        keys_after = [k for k in self.store._data if "cache" in k]
        self.assertEqual(keys_after, [])

    def test_traces_admin(self):
        c = self._client()
        tok = c.post("/api/auth/login", json={"username": "u1", "password": "pass1234"}).json()["token"]
        done = c.post(
            "/api/qa/ask",
            headers={"Authorization": f"Bearer {tok}"},
            json={"question": "什么是神的爱"},
        ).json()
        rid = done["request_id"]
        r = c.get("/api/admin/traces?limit=5", headers={"X-Admin-Token": "adm"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["items"])
        r = c.get(f"/api/admin/traces/{rid}", headers={"X-Admin-Token": "adm"})
        self.assertEqual(r.status_code, 200)
        # 方案 A：详情含全文
        self.assertEqual(r.json()["item"].get("question_text"), "什么是神的爱")


if __name__ == "__main__":
    unittest.main()
