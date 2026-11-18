# -*- coding: utf-8 -*-
"""第五组：管理后台 stats / feedback/stats / delete user / stats clear。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("QA4_LLM_MODE", "fake")
os.environ.setdefault("QA4_RETRIEVAL_MODE", "fake")
os.environ.setdefault("QA4_JWT_SECRET", "dev-fake-jwt-not-a-real-secret")
os.environ.pop("QA4_ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient

from config import get_settings, reset_settings_cache
from core.auth import AuthStore
from core.es_client import FakeEsClient
from core.neo4j_client import FakeNeo4jClient
from core.redis_store import MemoryStore
from main import create_app
from pipeline.traces import TraceStore


class TestAdminGroup5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset_settings_cache()
        cls.tmp = tempfile.TemporaryDirectory()
        data = Path(cls.tmp.name)
        settings = get_settings(require_runtime=False)
        settings.data_dir = data
        settings.traces_db_path = data / "t.db"
        cls.store = MemoryStore(prefix="g5:")
        cls.auth = AuthStore(
            data / "users.db",
            jwt_secret=settings.jwt_secret,
            daily_limit_default=30,
            admin_token="adm5",
        )
        cls.auth.create_invite("G5", max_uses=5)
        cls.auth.register("G5", "g5_u", "pass1234")
        cls.auth.register("G5", "g5_del", "pass1234")
        cls.traces = TraceStore(
            data / "traces.db",
            store=cls.store,
            monitor_key="monitor:traces",
            store_question_text=True,
        )
        cls.traces.write(
            {
                "request_id": "r1",
                "question_hash": "abc",
                "question_len": 4,
                "question_text": "什么是召会",
                "cache_hit": False,
                "degraded": False,
                "not_found": True,
                "elapsed_ms": 120,
            }
        )
        cls.traces.write(
            {
                "request_id": "r2",
                "question_hash": "def",
                "question_len": 3,
                "question_text": "神的爱",
                "cache_hit": True,
                "degraded": False,
                "not_found": False,
                "elapsed_ms": 10,
            }
        )
        cls.app = create_app(
            settings,
            redis_store=cls.store,
            es_client=FakeEsClient(reachable=True),
            neo4j_client=FakeNeo4jClient(reachable=True),
            auth_store=cls.auth,
        )
        # 注入 traces 到 pipeline_deps（若 create_app 已建则覆盖）
        deps = getattr(cls.app.state, "pipeline_deps", None)
        if deps is not None:
            deps.traces = cls.traces
        else:
            class _D:
                traces = cls.traces

            cls.app.state.pipeline_deps = _D()
        cls.client = TestClient(cls.app)
        cls.headers = {"X-Admin-Token": "adm5"}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_stats_requires_admin(self):
        self.assertEqual(self.client.get("/api/admin/stats").status_code, 401)

    def test_stats_aggregate(self):
        r = self.client.get("/api/admin/stats", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertGreaterEqual(body.get("total_requests"), 2)
        self.assertIn("cache_hit_rate", body)
        self.assertIn("step_fail_records", body)
        self.assertTrue(any("召会" in (x.get("question") or "") for x in body["step_fail_records"]))

    def test_feedback_stats(self):
        uid = self.auth.get_user("g5_u")["id"]
        self.auth.add_feedback(user_id=uid, request_id="r1", rating=1)
        self.auth.add_feedback(user_id=uid, request_id="r2", rating=-1, comment="")
        r = self.client.get("/api/admin/feedback/stats", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertGreaterEqual(body.get("thumbs_up"), 1)
        self.assertGreaterEqual(body.get("thumbs_down"), 1)
        self.assertIn("rate", body)
        self.assertTrue(body.get("recent_down"))

    def test_delete_user(self):
        r = self.client.delete("/api/admin/users/g5_del", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(self.auth.get_user("g5_del"))
        r2 = self.client.delete("/api/admin/users/nope", headers=self.headers)
        self.assertEqual(r2.status_code, 404)

    def test_stats_clear_and_cache_clear(self):
        r = self.client.post("/api/admin/stats/clear", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        r2 = self.client.post("/api/admin/cache/clear", headers=self.headers)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertIn("deleted", r2.json())


if __name__ == "__main__":
    unittest.main()
