# -*- coding: utf-8 -*-
"""验证 roundtable 按版本数扣费/退还，以及其它 feature 默认 amount=1 兼容。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# 保证仓库根在 path 上
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# auth 初始化需要 JWT secret
os.environ.setdefault("CN_JWT_SECRET", "test-roundtable-quota-secret")


class AuthAmountTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "cn_users.db"
        import back_cn.auth as auth

        self.auth = auth
        self._orig_db = auth.DB_PATH
        auth.DB_PATH = self.db_path
        auth.init_db()
        ok = auth.create_user("quota_tester", "pass123")
        self.assertTrue(ok)
        # 给 roundtable 较高上限，方便测扣 4
        self.assertTrue(auth.set_user_daily_limit("quota_tester", "roundtable", 10))
        self.assertTrue(auth.set_user_daily_limit("quota_tester", "qa", 3))
        self.assertTrue(auth.set_user_daily_limit("quota_tester", "outline", 3))

    def tearDown(self) -> None:
        self.auth.DB_PATH = self._orig_db
        self._tmpdir.cleanup()

    def _rt(self) -> dict:
        return self.auth.get_daily_usage("quota_tester")["roundtable"]

    def test_default_amount_one_compat(self) -> None:
        """其它功能仍用默认 amount=1，行为不变。"""
        u1 = self.auth.check_and_increment_daily_usage("quota_tester", "qa")
        self.assertTrue(u1["allowed"])
        self.assertEqual(u1["used"], 1)
        u2 = self.auth.check_and_increment_daily_usage("quota_tester", "outline")
        self.assertTrue(u2["allowed"])
        self.assertEqual(u2["used"], 1)
        self.auth.refund_daily_usage("quota_tester", "qa")
        self.assertEqual(self.auth.get_daily_usage("quota_tester")["qa"]["used"], 0)
        self.assertEqual(self.auth.get_daily_usage("quota_tester")["outline"]["used"], 1)

    def test_atomic_insufficient_does_not_partial_charge(self) -> None:
        """剩余 2 次却扣 4：拒绝且 used 不变。"""
        # 先用掉 8，剩 2
        charged = self.auth.check_and_increment_daily_usage(
            "quota_tester", "roundtable", amount=8
        )
        self.assertTrue(charged["allowed"])
        self.assertEqual(self._rt()["used"], 8)

        denied = self.auth.check_and_increment_daily_usage(
            "quota_tester", "roundtable", amount=4
        )
        self.assertFalse(denied["allowed"])
        self.assertEqual(denied["used"], 8)
        self.assertEqual(self._rt()["used"], 8)

    def test_charge_four_success_net_four(self) -> None:
        charged = self.auth.check_and_increment_daily_usage(
            "quota_tester", "roundtable", amount=4
        )
        self.assertTrue(charged["allowed"])
        self.assertEqual(charged["used"], 4)
        self.assertEqual(self._rt()["used"], 4)

    def test_charge_four_refund_two_net_two(self) -> None:
        self.auth.check_and_increment_daily_usage(
            "quota_tester", "roundtable", amount=4
        )
        self.auth.refund_daily_usage("quota_tester", "roundtable", amount=2)
        self.assertEqual(self._rt()["used"], 2)

    def test_charge_four_refund_four_net_zero(self) -> None:
        self.auth.check_and_increment_daily_usage(
            "quota_tester", "roundtable", amount=4
        )
        self.auth.refund_daily_usage("quota_tester", "roundtable", amount=4)
        self.assertEqual(self._rt()["used"], 0)

    def test_single_version_charge_and_refund(self) -> None:
        self.auth.check_and_increment_daily_usage(
            "quota_tester", "roundtable", amount=1
        )
        self.assertEqual(self._rt()["used"], 1)
        self.auth.refund_daily_usage("quota_tester", "roundtable", amount=1)
        self.assertEqual(self._rt()["used"], 0)

    def test_refund_amount_zero_noop(self) -> None:
        self.auth.check_and_increment_daily_usage(
            "quota_tester", "roundtable", amount=2
        )
        self.auth.refund_daily_usage("quota_tester", "roundtable", amount=0)
        self.assertEqual(self._rt()["used"], 2)

    def test_unlimited_allows_any_amount(self) -> None:
        self.assertTrue(
            self.auth.set_user_daily_limit("quota_tester", "roundtable", -1)
        )
        charged = self.auth.check_and_increment_daily_usage(
            "quota_tester", "roundtable", amount=4
        )
        self.assertTrue(charged["allowed"])
        self.assertEqual(charged["limit"], -1)


class RoundtableRouterRefundFlowTests(unittest.IsolatedAsyncioTestCase):
    """用 mock 跑 generate 后台逻辑，验证退还次数。"""

    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "cn_users.db"
        import back_cn.auth as auth

        self.auth = auth
        self._orig_db = auth.DB_PATH
        auth.DB_PATH = self.db_path
        auth.init_db()
        auth.create_user("rt_flow", "pass123")
        auth.set_user_daily_limit("rt_flow", "roundtable", 10)

    async def asyncTearDown(self) -> None:
        self.auth.DB_PATH = self._orig_db
        self._tmpdir.cleanup()

    def _used(self) -> int:
        return self.auth.get_daily_usage("rt_flow")["roundtable"]["used"]

    async def _run_generate(
        self,
        *,
        versions: list[str],
        step1_ok: bool = True,
        fail_versions: set[str] | None = None,
    ) -> None:
        fail_versions = fail_versions or set()
        from back_cn.routers import roundtable_router as rr

        body = SimpleNamespace(
            book=45,
            start_issue=1,
            count=1,
            versions=versions,
            week_number=None,
        )
        request = MagicMock()

        bg_task_holder: list = []

        def capture_create_task(coro):
            # 同步跑完后台协程，便于断言配额
            t = asyncio.get_event_loop().create_task(coro)
            bg_task_holder.append(t)
            return t

        async def fake_step1(*_a, **_k):
            if not step1_ok:
                raise RuntimeError("step1 boom")
            return {"title": "t", "source_line": "s"}

        async def fake_version(version_key, *_a, **_k):
            if version_key in fail_versions:
                raise RuntimeError(f"{version_key} fail")
            return {
                "label": version_key,
                "word_count": 10,
                "data": {"ok": True},
            }

        with (
            patch.object(rr, "get_current_user", return_value={"username": "rt_flow"}),
            patch.object(
                rr,
                "resolve_cross_book_selection",
                return_value=[(45, 1)],
            ),
            patch.object(
                rr,
                "get_messages_by_selection",
                return_value=[{"text": "x"}],
            ),
            patch.object(rr, "_cleanup_expired_tasks"),
            patch.object(rr, "generate_unified_fields", side_effect=fake_step1),
            patch.object(rr, "generate_version", side_effect=fake_version),
            patch.object(
                rr,
                "format_version_preview",
                return_value="preview",
            ),
            patch.object(
                rr,
                "format_version_preview_html",
                return_value="<p>preview</p>",
            ),
            patch.object(rr, "init_task_usage"),
            patch.object(rr, "log_task_usage"),
            patch.object(rr, "discard_task_usage"),
            patch.object(rr.asyncio, "create_task", side_effect=capture_create_task),
        ):
            result = await rr.generate_roundtable(request, body)
            self.assertIn("task_id", result)
            await bg_task_holder[0]

    async def test_all_success_net_charge_4(self) -> None:
        versions = ["truth", "gospel", "life", "elderly"]
        await self._run_generate(versions=versions)
        self.assertEqual(self._used(), 4)

    async def test_partial_fail_net_charge_2(self) -> None:
        versions = ["truth", "gospel", "life", "elderly"]
        await self._run_generate(
            versions=versions, fail_versions={"gospel", "elderly"}
        )
        self.assertEqual(self._used(), 2)

    async def test_step1_fail_net_charge_0(self) -> None:
        versions = ["truth", "gospel", "life", "elderly"]
        await self._run_generate(versions=versions, step1_ok=False)
        self.assertEqual(self._used(), 0)

    async def test_backend_rejects_when_remaining_lt_versions(self) -> None:
        # 先扣到只剩 2
        self.auth.check_and_increment_daily_usage(
            "rt_flow", "roundtable", amount=8
        )
        self.assertEqual(self._used(), 8)

        from back_cn.routers import roundtable_router as rr
        from fastapi import HTTPException

        body = SimpleNamespace(
            book=45,
            start_issue=1,
            count=1,
            versions=["truth", "gospel", "life", "elderly"],
            week_number=None,
        )
        with (
            patch.object(rr, "get_current_user", return_value={"username": "rt_flow"}),
            patch.object(
                rr, "resolve_cross_book_selection", return_value=[(45, 1)]
            ),
            patch.object(
                rr, "get_messages_by_selection", return_value=[{"text": "x"}]
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await rr.generate_roundtable(MagicMock(), body)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("额度不足", ctx.exception.detail)
        self.assertEqual(self._used(), 8)  # 未扣减

    async def test_single_version_success_and_fail(self) -> None:
        await self._run_generate(versions=["truth"])
        self.assertEqual(self._used(), 1)
        await self._run_generate(versions=["gospel"], fail_versions={"gospel"})
        # 扣1再退1，净仍为1
        self.assertEqual(self._used(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
