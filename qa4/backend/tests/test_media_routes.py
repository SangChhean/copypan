# -*- coding: utf-8 -*-
"""三语 / TTS / ASR 路由契约（不调外部服务；缺 key 返回 503）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QA4_LLM_MODE", "fake")
os.environ.setdefault("QA4_RETRIEVAL_MODE", "fake")
os.environ.setdefault("QA4_JWT_SECRET", "dev-fake-jwt-not-a-real-secret")
os.environ.pop("QA4_ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient

from config import get_settings, reset_settings_cache
from core.auth import AuthStore
from core.neo4j_client import FakeNeo4jClient
from core.redis_store import MemoryStore
from core.es_client import FakeEsClient
from main import create_app


class TestMediaRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset_settings_cache()
        cls.tmp = tempfile.TemporaryDirectory()
        data = Path(cls.tmp.name)
        settings = get_settings(require_runtime=False)
        settings.data_dir = data
        settings.traces_db_path = data / "t.db"
        cls.auth = AuthStore(
            data / "users.db",
            jwt_secret=settings.jwt_secret,
            daily_limit_default=30,
            admin_token="adm",
        )
        cls.auth.create_invite("M1", max_uses=5)
        cls.auth.register("M1", "media_u", "pass1234")
        cls.app = create_app(
            settings,
            redis_store=MemoryStore(prefix="m:"),
            es_client=FakeEsClient(reachable=True),
            neo4j_client=FakeNeo4jClient(reachable=True),
            auth_store=cls.auth,
        )
        cls.client = TestClient(cls.app)
        tok = cls.client.post(
            "/api/auth/login", json={"username": "media_u", "password": "pass1234"}
        ).json()["token"]
        cls.headers = {"Authorization": f"Bearer {tok}"}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_translate_requires_auth(self):
        r = self.client.post("/api/translate", json={"text": "神的爱", "target_lang": "zh_tw"})
        self.assertEqual(r.status_code, 401)

    def test_translate_zh_tw(self):
        r = self.client.post(
            "/api/translate",
            headers=self.headers,
            json={"text": "神的爱", "sources": ["罗马书生命读经"], "target_lang": "zh_tw"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("answer", data)
        self.assertTrue(data["answer"])
        # 繁体「愛」或至少不同于空
        self.assertNotEqual(data["answer"].strip(), "")

    def test_tts_minimax_missing_key(self):
        with mock.patch.dict(
            os.environ,
            {
                "MINIMAX_API_KEY": "",
                "MINIMAX_GROUP_ID": "",
                "QA4_MINIMAX_API_KEY": "",
                "QA4_MINIMAX_GROUP_ID": "",
            },
            clear=False,
        ):
            r = self.client.post(
                "/api/tts/minimax",
                headers=self.headers,
                json={"text": "主啊我爱你", "lang": "zh"},
            )
        self.assertEqual(r.status_code, 503, r.text)

    def test_asr_missing_key(self):
        with mock.patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "", "QA4_OPENAI_API_KEY": ""},
            clear=False,
        ):
            r = self.client.post(
                "/api/asr",
                headers=self.headers,
                files={"file": ("a.webm", b"\x00\x01\x02", "audio/webm")},
            )
        self.assertEqual(r.status_code, 503, r.text)


if __name__ == "__main__":
    unittest.main()
