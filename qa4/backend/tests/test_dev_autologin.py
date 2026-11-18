# -*- coding: utf-8 -*-
"""QA4_DEV_AUTOLOGIN：仅本机回环免登录。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from config import ConfigError, reset_settings_cache
from config.settings import Settings, assert_dev_autologin_safe, load_expected_counts, load_index_map
from core.auth import AuthStore
from core.es_client import FakeEsClient
from core.neo4j_client import FakeNeo4jClient
from core.redis_store import MemoryStore
from main import create_app


def _settings(
    data: Path,
    *,
    dev_autologin: bool,
    bind_host: str,
) -> Settings:
    lookup = Path(__file__).resolve().parents[2] / "data" / "lookups"
    return Settings(
        port=8030,
        data_dir=data,
        lookup_dir=lookup if lookup.is_dir() else data / "lookups",
        redis_url="",
        redis_prefix="qa4:",
        es_url="",
        es_user="",
        es_secret="",
        es_verify=False,
        neo4j_uri="",
        neo4j_user="",
        neo4j_secret="",
        claude_api_key="",
        openrouter_api_key="",
        model_fast="x",
        model_main="y",
        daily_limit_default=30,
        fake_llm=True,
        jwt_secret="test-secret",
        jwt_expire_days=7,
        admin_token="adm",
        tz_name="UTC",
        rate_limit_per_minute=15,
        index_map=load_index_map(),
        expected_counts=load_expected_counts(),
        dev_autologin=dev_autologin,
        bind_host=bind_host,
    )


class TestDevAutologin(unittest.TestCase):
    def setUp(self):
        reset_settings_cache()
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        (self.data / "lookups").mkdir(parents=True, exist_ok=True)
        self.auth = AuthStore(
            self.data / "qa4_users.db",
            jwt_secret="test-secret",
            daily_limit_default=30,
            admin_token="adm",
        )
        self.store = MemoryStore(prefix="qa4:")

    def tearDown(self):
        self.tmp.cleanup()
        reset_settings_cache()

    def _app(self, *, dev_autologin: bool, bind_host: str):
        s = _settings(self.data, dev_autologin=dev_autologin, bind_host=bind_host)
        return create_app(
            s,
            redis_store=self.store,
            es_client=FakeEsClient(reachable=True),
            neo4j_client=FakeNeo4jClient(reachable=True),
            auth_store=self.auth,
        )

    def _loopback_client(self, app, **kwargs):
        # base_url 决定 Host 头；须为本机名/地址才通过免登录
        return TestClient(
            app,
            base_url="http://127.0.0.1:8030",
            client=("127.0.0.1", 50000),
            **kwargs,
        )

    def test_off_dev_login_401(self):
        app = self._app(dev_autologin=False, bind_host="127.0.0.1")
        c = self._loopback_client(app)
        r = c.post("/api/auth/login", json={"username": "dev", "password": "any-pass"})
        self.assertEqual(r.status_code, 401, r.text)

    def test_on_non_loopback_client_401(self):
        app = self._app(dev_autologin=True, bind_host="127.0.0.1")
        c = TestClient(app, base_url="http://127.0.0.1:8030", client=("8.8.8.8", 50000))
        r = c.post("/api/auth/login", json={"username": "dev", "password": "any-pass"})
        self.assertEqual(r.status_code, 401, r.text)
        self.assertIsNone(self.auth.get_user("dev"))

    def test_on_loopback_with_forwarded_for_401(self):
        app = self._app(dev_autologin=True, bind_host="127.0.0.1")
        c = self._loopback_client(app)
        r = c.post(
            "/api/auth/login",
            json={"username": "dev", "password": "any-pass"},
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        self.assertEqual(r.status_code, 401, r.text)
        self.assertIsNone(self.auth.get_user("dev"))

    def test_on_loopback_host_example_com_401(self):
        app = self._app(dev_autologin=True, bind_host="127.0.0.1")
        c = TestClient(app, base_url="http://example.com", client=("127.0.0.1", 50000))
        r = c.post("/api/auth/login", json={"username": "dev", "password": "any-pass"})
        self.assertEqual(r.status_code, 401, r.text)
        self.assertIsNone(self.auth.get_user("dev"))

    def test_on_loopback_200_and_creates_user(self):
        app = self._app(dev_autologin=True, bind_host="127.0.0.1")
        c = self._loopback_client(app)
        r = c.post("/api/auth/login", json={"username": "dev", "password": "whatever"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body.get("username"), "dev")
        self.assertTrue(body.get("token"))
        self.assertIsNotNone(self.auth.get_user("dev"))
        # 再次任意密码仍可登录
        r2 = c.post("/api/auth/login", json={"username": "dev", "password": "other"})
        self.assertEqual(r2.status_code, 200, r2.text)

    def test_on_non_loopback_bind_refuses_start(self):
        s = _settings(self.data, dev_autologin=True, bind_host="0.0.0.0")
        with self.assertRaises(ConfigError) as ctx:
            assert_dev_autologin_safe(s)
        self.assertIn("QA4_DEV_AUTOLOGIN", str(ctx.exception))
        with self.assertRaises(ConfigError):
            create_app(
                s,
                redis_store=self.store,
                es_client=FakeEsClient(reachable=True),
                neo4j_client=FakeNeo4jClient(reachable=True),
                auth_store=self.auth,
            )

    def test_startup_warning_when_enabled(self):
        with self.assertLogs("qa4.main", level="WARNING") as cm:
            self._app(dev_autologin=True, bind_host="127.0.0.1")
        blob = "\n".join(cm.output)
        self.assertIn("本机免登录已开启", blob)


if __name__ == "__main__":
    unittest.main()
