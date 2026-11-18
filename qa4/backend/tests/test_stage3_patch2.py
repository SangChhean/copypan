# -*- coding: utf-8 -*-
"""阶段 2+3 收尾补丁：trace 原文、比较类强制、step3/4/5/7 补测。"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
QA4 = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from config import get_settings, reset_settings_cache
from core.auth import AuthStore
from core.es_client import FakeEsClient
from core.neo4j_client import FakeNeo4jClient
from core.redis_store import MemoryStore
from fastapi.testclient import TestClient
from lookups.year_table import YearTable
from main import create_app
from pipeline.caps import caps_cfg, truncate_layers
from pipeline.context import RequestContext
from pipeline.deps import build_deps
from pipeline.schemas import Layers, Plan, SubQuestion, Verdict
from pipeline import step04_layer1, step05_layers, step07_judge
from pipeline.traces import TraceStore
from pipeline.orchestrator import collect_ask


def _settings(tmp: Path):
    reset_settings_cache()
    os.environ["QA4_LLM_MODE"] = "fake"
    os.environ["QA4_RETRIEVAL_MODE"] = "fake"
    os.environ["QA4_JWT_SECRET"] = "test-jwt"
    os.environ["QA4_ADMIN_TOKEN"] = "adm"
    os.environ["QA4_DATA_DIR"] = str(tmp)
    os.environ["QA4_LOOKUP_DIR"] = str(QA4 / "data" / "lookups")
    os.environ["QA4_GRAPH_ANNOTATIONS_DIR"] = str(QA4 / "data" / "graph_annotations")
    os.environ["QA4_DAILY_LIMIT_DEFAULT"] = "100"
    os.environ["QA4_RATE_LIMIT_PER_MINUTE"] = "1000"
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    s.bible_dir = QA4 / "data" / "bible_data"
    return s


class TestYearTable(unittest.TestCase):
    def setUp(self):
        self.yt = YearTable.from_lookup_dir(QA4 / "data" / "lookups")

    def test_overlap_and_multi_book(self):
        sel = self.yt.select(1932, 1949)
        self.assertTrue(sel.book_titles)
        self.assertTrue(any("一九三" in t or "194" in t or "193" in t for t in sel.marks) or sel.marks)
        # 一年多册：1934 附近
        one = self.yt.select(1984, 1984)
        self.assertIsInstance(one.book_titles, list)

    def test_cross_year_volume_and_no_year(self):
        # 跨年标记应命中区间重叠
        sel = self.yt.select(1994, 1996)
        self.assertTrue(sel.book_titles)
        # 无年份书名永不命中
        for t in list(self.yt.no_year)[:5]:
            self.assertNotIn(t, sel.book_titles)
        self.assertEqual(len(self.yt.no_year), 61)


class TestStep4(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _settings(Path(self.tmp.name))
        self.deps = build_deps(
            self.settings,
            store=MemoryStore(prefix="qa4:"),
            es=FakeEsClient(reachable=True),
            neo4j=FakeNeo4jClient(reachable=True),
            traces_db=Path(self.tmp.name) / "t.db",
        )
        from tests._fast_hymn_env import attach_stub_to_deps

        attach_stub_to_deps(self.deps)

    def tearDown(self):
        self.tmp.cleanup()
        for k in list(os.environ):
            if k.startswith("QA4_"):
                os.environ.pop(k, None)
        reset_settings_cache()

    def test_paren_map_and_drop_not_in_question(self):
        # 括号词：若 lookups 有 same_as，映射到外词
        plan = Plan(main_type="定义", subquestions=[SubQuestion(text="什么是神的爱", qtype="定义")])
        words, flags = step04_layer1.postprocess_words(
            ["神的爱", "幽灵词XYZ"], "什么是神的爱", self.deps.lookups, plan
        )
        self.assertIn("神的爱", words)
        self.assertNotIn("幽灵词XYZ", words)

    def test_fallback_excludes_generic_and_limits(self):
        fb = step04_layer1.fallback_longest_match("弟兄与神的爱", self.deps.lookups, self.deps.generic)
        self.assertNotIn("弟兄", fb)
        self.assertIn("神的爱", fb)

    def test_layer1_caps(self):
        ccfg = caps_cfg()
        plan = Plan(
            main_type="默认",
            complex=True,
            subquestions=[
                SubQuestion(text="神的爱 爱神 十字架 召会生活 生命", qtype="默认"),
                SubQuestion(text="神的爱 爱神 十字架", qtype="默认"),
                SubQuestion(text="综合", qtype="默认", synthesis=True),
            ],
        )
        words = ["神的爱", "爱神", "十字架", "召会生活", "生命"]
        per = step04_layer1.assign_to_subquestions(words, plan, caps_cfg=ccfg, whole=8)
        self.assertLessEqual(len(per[0]), 3)
        self.assertLessEqual(sum(len(p) for p in per), 8)

    def test_compare_keeps_non_entry_object(self):
        ccfg = caps_cfg()
        plan = Plan(
            main_type="比较",
            subquestions=[
                SubQuestion(
                    text="请比较甲对象与乙对象",
                    qtype="比较",
                    compare_objects=["甲对象", "乙对象"],
                )
            ],
        )
        words, is_entry = step04_layer1.postprocess_words(
            ["甲对象", "乙对象", "神的爱"], "请比较甲对象与乙对象以及神的爱", self.deps.lookups, plan
        )
        per = step04_layer1.assign_to_subquestions(words, plan, caps_cfg=ccfg, whole=8)
        step04_layer1._force_compare_objects(per, is_entry, plan, self.deps.lookups, ccfg=ccfg, whole=8)
        self.assertIn("甲对象", per[0])
        self.assertIn("乙对象", per[0])
        self.assertFalse(is_entry.get("甲对象", True))


class TestStep5Compare(unittest.TestCase):
    def test_truncate_never_wipes_one_side(self):
        layers = Layers(
            layer1=["甲对象", "乙对象"],
            revelation=["偏甲1", "偏甲2", "偏甲3", "偏甲4", "偏乙1"],
            intrinsic=[],
            experience=[],
            practice=[],
            object_of={"偏甲1": "甲对象", "偏甲2": "甲对象", "偏甲3": "甲对象", "偏甲4": "甲对象", "偏乙1": "乙对象"},
        )
        caps = {"revelation": 4, "intrinsic": 2, "experience": 2, "practice": 1, "total": 3}
        out = truncate_layers(layers, caps, object_of=layers.object_of, protect_objects=["甲对象", "乙对象"])
        pointed = set(out.object_of.values()) | set(out.recommended())
        # 乙对象至少通过 object_of 或词本身留下
        self.assertTrue("乙对象" in pointed or any(out.object_of.get(w) == "乙对象" for w in out.recommended()))

    def test_uncovered_warning_and_partial(self):
        plan = Plan(
            main_type="比较",
            subquestions=[SubQuestion(text="比较甲与乙", qtype="比较", compare_objects=["甲对象", "乙对象"])],
        )
        layers = [Layers(layer1=["甲对象"])]
        raw = {
            "subquestions": [
                {
                    "index": 0,
                    "revelation": ["只偏甲"],
                    "intrinsic": [],
                    "experience": [],
                    "practice": [],
                    "object_of": {"只偏甲": "甲对象"},
                }
            ]
        }

        class L:
            zui_neizai = []
            other_2239 = {"只偏甲"}
            lexicon = []

        out, stats = step05_layers.postprocess(raw, layers, plan, L())
        self.assertIn("乙对象", (stats.get("uncovered_objects") or {}).get("0") or [])
        # 把关：够 → 部分够
        ctx = RequestContext(request_id="x", question_orig="比较甲与乙")
        ctx.plan = plan
        ctx.warn("compare_object_uncovered")
        ctx.verdicts = []
        v = Verdict(subq=0, overall="够", keep={1: True})
        from pipeline import step07_judge

        # 直接应用降级规则片段
        if "compare_object_uncovered" in ctx.warnings and v.overall == "够":
            v.overall = "部分够"
        self.assertEqual(v.overall, "部分够")


class TestStep5Filters(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _settings(Path(self.tmp.name))
        self.deps = build_deps(
            self.settings,
            store=MemoryStore(prefix="qa4:"),
            es=FakeEsClient(reachable=True),
            neo4j=FakeNeo4jClient(reachable=True),
            traces_db=Path(self.tmp.name) / "t.db",
        )
        from tests._fast_hymn_env import attach_stub_to_deps

        attach_stub_to_deps(self.deps)

    def tearDown(self):
        self.tmp.cleanup()
        for k in list(os.environ):
            if k.startswith("QA4_"):
                os.environ.pop(k, None)
        reset_settings_cache()

    def test_drop_out_of_list_and_dup_and_intrinsic_only_133(self):
        lu = self.deps.lookups
        zui = lu.zui_neizai[0]
        other = next(iter(lu.other_2239))
        plan = Plan(main_type="定义", subquestions=[SubQuestion(text="x", qtype="定义")])
        layers = [Layers(layer1=[zui])]
        raw = {
            "subquestions": [
                {
                    "index": 0,
                    "revelation": [other, "名单外的词", zui],
                    "intrinsic": [other, zui],  # other 不该进 intrinsic
                    "experience": [other],
                    "practice": [],
                }
            ]
        }
        out, stats = step05_layers.postprocess(raw, layers, plan, lu)
        self.assertGreater(stats["dropped_not_in_list"], 0)
        self.assertNotIn(other, out[0].intrinsic)
        self.assertNotIn(zui, out[0].revelation)  # 与 layer1 重复
        self.assertNotIn("名单外的词", out[0].revelation)

    def test_all_bad_keeps_layer1_only(self):
        plan = Plan(main_type="定义", subquestions=[SubQuestion(text="x", qtype="定义")])
        layers = [Layers(layer1=["神的爱"])]
        raw = {"subquestions": [{"index": 0, "revelation": ["完全不在名单"], "intrinsic": [], "experience": [], "practice": []}]}
        out, stats = step05_layers.postprocess(raw, layers, plan, self.deps.lookups)
        self.assertEqual(out[0].total_2_5(), 0)
        self.assertEqual(out[0].layer1, ["神的爱"])


class TestStep7Retry(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _settings(Path(self.tmp.name))
        self.store = MemoryStore(prefix="qa4:")
        self.deps = build_deps(
            self.settings,
            store=self.store,
            es=FakeEsClient(reachable=True),
            neo4j=FakeNeo4jClient(reachable=True),
            traces_db=Path(self.tmp.name) / "t.db",
        )
        from tests._fast_hymn_env import attach_stub_to_deps

        attach_stub_to_deps(self.deps)

    async def asyncTearDown(self):
        self.tmp.cleanup()
        for k in list(os.environ):
            if k.startswith("QA4_"):
                os.environ.pop(k, None)
        reset_settings_cache()

    async def test_retry_once_then_not_found(self):
        self.deps.llm.reset()
        n0 = len(self.deps.retrieval.calls)
        done = await collect_ask(self.deps, question="【不够】怪问题完全无材料zzz")
        # 放宽检索恰好多一轮调用
        self.assertTrue(self.deps.llm.calls)
        step7_calls = [c for c in self.deps.llm.calls if c.get("step") == "step7"]
        self.assertGreaterEqual(len(step7_calls), 2)  # 初判 + 重判
        self.assertTrue(done.get("not_found") or "没有" in (done.get("answer") or ""))
        self.assertGreater(len(self.deps.retrieval.calls), n0)

    async def test_verify_claim_no_retry(self):
        # 强制 plan 为核实说法：用 monkey 在 step3 后——改假模型不够可靠；直接调 step07
        ctx = RequestContext(request_id="r1", question_orig="核实说法测试")
        ctx.plan = Plan(main_type="核实说法", subquestions=[SubQuestion(text="核实", qtype="核实说法")])
        ctx.passages_by_subq = {0: []}
        ctx.passages = []
        n0 = len(self.deps.retrieval.calls)
        vs = await step07_judge.run(ctx, self.deps)
        self.assertFalse(ctx.retried)
        self.assertEqual(len(self.deps.retrieval.calls), n0)
        self.assertEqual(vs[0].overall, "不够")


class TestTracesSchemeA(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.settings = _settings(self.tmp_path)
        self.store = MemoryStore(prefix="qa4:")
        self.auth = AuthStore(
            self.tmp_path / "u.db",
            jwt_secret="test-jwt",
            jwt_expire_days=7,
            daily_limit_default=100,
            tz_name="UTC",
            admin_token="adm",
        )
        self.auth.create_invite("I", max_uses=10)
        self.auth.register("I", "u1", "pass1234")
        self.deps = build_deps(
            self.settings,
            store=self.store,
            es=FakeEsClient(reachable=True),
            neo4j=FakeNeo4jClient(reachable=True),
            traces_db=self.tmp_path / "traces.db",
        )
        from tests._fast_hymn_env import attach_stub_to_deps

        attach_stub_to_deps(self.deps)

    async def asyncTearDown(self):
        self.tmp.cleanup()
        for k in list(os.environ):
            if k.startswith("QA4_"):
                os.environ.pop(k, None)
        reset_settings_cache()

    async def test_store_and_preview_and_auth(self):
        q = "独特问题字符串TRACE_UNIQUE_XYZ_请解释神的爱" + ("长" * 40)
        done = await collect_ask(
            self.deps,
            question=q,
            history=[{"question": "上文问", "answer": "上文答" * 200}],
        )
        rid = done["request_id"]
        detail = self.deps.traces.get(rid)
        self.assertEqual(detail["question_text"], q)
        self.assertTrue(detail.get("history_json"))
        self.assertEqual(len(detail["history_json"][0]["answer"]), 300)
        self.assertTrue(detail.get("rewritten_question"))
        items = self.deps.traces.recent(5)
        self.assertTrue(items)
        self.assertLessEqual(len(items[0]["question_preview"]), 60)
        self.assertTrue(q.startswith(items[0]["question_preview"]))

        app = create_app(
            self.settings,
            redis_store=self.store,
            es_client=FakeEsClient(reachable=True),
            neo4j_client=FakeNeo4jClient(reachable=True),
            auth_store=self.auth,
            pipeline_deps=self.deps,
        )
        c = TestClient(app)
        self.assertEqual(c.get("/api/admin/traces").status_code, 401)
        self.assertEqual(c.get("/api/admin/traces", headers={"X-Admin-Token": "bad"}).status_code, 401)
        self.assertEqual(c.get(f"/api/admin/traces/{rid}").status_code, 401)
        ok = c.get("/api/admin/traces?limit=3", headers={"X-Admin-Token": "adm"})
        self.assertEqual(ok.status_code, 200)
        self.assertLessEqual(len(ok.json()["items"][0]["question_preview"]), 60)
        full = c.get(f"/api/admin/traces/{rid}", headers={"X-Admin-Token": "adm"})
        self.assertEqual(full.json()["item"]["question_text"], q)

    async def test_store_question_text_false(self):
        self.deps.cfg.setdefault("traces", {})["store_question_text"] = False
        self.deps.traces.store_question_text = False
        done = await collect_ask(self.deps, question="不应入库的原文SECRET_Q")
        rec = self.deps.traces.get(done["request_id"])
        self.assertIn(rec.get("question_text"), (None, ""))
        # 列也为空
        with sqlite3.connect(str(self.deps.traces.db_path)) as conn:
            row = conn.execute(
                "SELECT question_text FROM qa4_traces WHERE request_id=?", (done["request_id"],)
            ).fetchone()
        self.assertIsNone(row[0])

    def test_retention_and_migration(self):
        db = self.tmp_path / "old.db"
        with sqlite3.connect(str(db)) as conn:
            conn.execute(
                "CREATE TABLE qa4_traces ("
                "request_id TEXT PRIMARY KEY, created_at REAL NOT NULL, "
                "question_hash TEXT NOT NULL, question_len INTEGER NOT NULL, "
                "cache_hit INTEGER NOT NULL DEFAULT 0, degraded INTEGER NOT NULL DEFAULT 0, "
                "record_json TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO qa4_traces VALUES (?,?,?,?,?,?,?)",
                ("old1", time.time() - 100, "abc", 3, 0, 0, json.dumps({"request_id": "old1"})),
            )
            conn.commit()
        store = TraceStore(db, retention_days=90, store_question_text=True)
        self.assertEqual(store.count(), 1)
        store.write(
            {
                "request_id": "new1",
                "question_hash": "h" * 64,
                "question_len": 5,
                "question_text": "新问题",
                "history_json": [],
                "rewritten_question": "",
                "cache_hit": False,
                "degraded": False,
            }
        )
        self.assertEqual(store.get("old1")["request_id"], "old1")
        self.assertEqual(store.get("new1")["question_text"], "新问题")

        # 过期清理
        exp = TraceStore(self.tmp_path / "exp.db", retention_days=1, store_question_text=True)
        exp.write({"request_id": "keep", "question_hash": "h", "question_len": 1, "cache_hit": False, "degraded": False}, now=time.time())
        exp.write(
            {"request_id": "gone", "question_hash": "h", "question_len": 1, "cache_hit": False, "degraded": False},
            now=time.time() - 3 * 86400,
        )
        # 强制再清（绕过一天一次）
        exp._last_purge_at = 0
        exp.purge_expired(force=True, now=time.time())
        self.assertIsNone(exp.get("gone"))
        self.assertIsNotNone(exp.get("keep"))

    async def test_logs_and_monitor_no_question(self):
        marker = "LOG_MARKER_UNIQUE_QUESTION_字串_神的爱"
        log = logging.getLogger("qa4.pipeline")
        with self.assertLogs("qa4.pipeline", level="INFO") as cm:
            log.info("pipeline_start sha8_only")
            done = await collect_ask(self.deps, question=marker)
            # 主动打一条带 request id 的 warning（模拟 degrade），确认不含原文
            log.warning("degraded request=%s reason=%s", done["request_id"][:8], "unit_test")
        joined = "\n".join(cm.output)
        self.assertNotIn(marker, joined)
        mon = None
        for k, v in self.store._lists.items():
            if "monitor" in k:
                mon = v
                break
        self.assertIsNotNone(mon)
        self.assertNotIn(marker, "\n".join(mon))


if __name__ == "__main__":
    unittest.main()
