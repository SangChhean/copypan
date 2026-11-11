# -*- coding: utf-8 -*-
"""验证 usage_logs 使用记录、BEGIN IMMEDIATE 原子扣费，以及 get_usage_stats 汇总。

全部在临时数据库上运行，不触碰 back_cn/cn_users.db，不调用任何 AI。
运行：python -m unittest back_cn.scripts.test_usage_logs -v
"""
from __future__ import annotations

import gc
import importlib.util
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CN_JWT_SECRET", "test-usage-logs-secret")

import back_cn.auth as auth  # noqa: E402

USER = "log_tester"


class _TempDbMixin:
    def _setup_db(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmpdir.name) / "cn_users.db"
        self._orig_db = auth.DB_PATH
        auth.DB_PATH = self.db_path
        auth.init_db()
        assert auth.create_user(USER, "pass123")
        assert auth.set_user_daily_limit(USER, "roundtable", 10)
        assert auth.set_user_daily_limit(USER, "qa", 3)

    def _teardown_db(self) -> None:
        auth.DB_PATH = self._orig_db
        gc.collect()
        self._tmpdir.cleanup()

    def _logs(self) -> list[tuple]:
        with sqlite3.connect(self.db_path) as c:
            return c.execute(
                "SELECT username, feature, amount, created_at FROM usage_logs ORDER BY id"
            ).fetchall()

    def _count(self, feature: str) -> int:
        with sqlite3.connect(self.db_path) as c:
            return c.execute(
                f"SELECT count_{feature} FROM users WHERE username = ?", (USER,)
            ).fetchone()[0]


class UsageLogTests(_TempDbMixin, unittest.TestCase):
    def setUp(self) -> None:
        self._setup_db()

    def tearDown(self) -> None:
        self._teardown_db()

    def test_schema_and_indexes(self) -> None:
        with sqlite3.connect(self.db_path) as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(usage_logs)")]
            idx = {r[1] for r in c.execute("PRAGMA index_list(usage_logs)")}
        self.assertEqual(cols, ["id", "username", "feature", "amount", "created_at"])
        self.assertIn("idx_usage_logs_feature_time", idx)
        self.assertIn("idx_usage_logs_user_time", idx)
        auth.init_db()  # 重复启动不报错

    def test_scenario_charge_refund_deny(self) -> None:
        # 扣 1 次
        r = auth.check_and_increment_daily_usage(USER, "qa")
        self.assertTrue(r["allowed"])
        # 小排按版本数扣 4 次
        r = auth.check_and_increment_daily_usage(USER, "roundtable", amount=4)
        self.assertTrue(r["allowed"])
        self.assertEqual(r["used"], 4)
        # 退还 2 次
        auth.refund_daily_usage(USER, "roundtable", amount=2)
        self.assertEqual(self._count("roundtable"), 2)
        # 额度不足被拒（roundtable 上限 10，已用 2，再扣 9）
        r = auth.check_and_increment_daily_usage(USER, "roundtable", amount=9)
        self.assertFalse(r["allowed"])
        self.assertEqual(self._count("roundtable"), 2)

        logs = [(u, f, a) for u, f, a, _ in self._logs()]
        self.assertEqual(
            logs,
            [(USER, "qa", 1), (USER, "roundtable", 4), (USER, "roundtable", -2)],
        )

    def test_created_at_beijing_format(self) -> None:
        auth.check_and_increment_daily_usage(USER, "qa")
        created_at = self._logs()[0][3]
        self.assertRegex(created_at, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertEqual(created_at[:10], auth._today())
        bj = datetime.utcnow() + timedelta(hours=8)
        diff = abs((datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S") - bj).total_seconds())
        self.assertLess(diff, 60)

    def test_refund_truncated_records_actual(self) -> None:
        auth.check_and_increment_daily_usage(USER, "roundtable", amount=2)
        auth.refund_daily_usage(USER, "roundtable", amount=5)  # 实际只能退 2
        self.assertEqual(self._count("roundtable"), 0)
        self.assertEqual([a for _, f, a, _ in self._logs() if f == "roundtable"], [2, -2])

    def test_refund_zero_actual_writes_nothing(self) -> None:
        auth.refund_daily_usage(USER, "qa", amount=1)  # 计数本来是 0
        auth.refund_daily_usage(USER, "qa", amount=0)  # amount=0 原样直接返回
        auth.refund_daily_usage("no_such_user", "qa", amount=1)
        self.assertEqual(self._logs(), [])

    def test_refund_after_day_change_writes_nothing(self) -> None:
        auth.check_and_increment_daily_usage(USER, "qa")
        with sqlite3.connect(self.db_path) as c:
            c.execute("UPDATE users SET daily_date = '2000-01-01' WHERE username = ?", (USER,))
        auth.refund_daily_usage(USER, "qa", amount=1)  # 跨天：计数已清零，实际退 0
        self.assertEqual([a for _, _, a, _ in self._logs()], [1])
        self.assertEqual(self._count("qa"), 0)

    def test_denied_and_unknown_user_write_nothing(self) -> None:
        for _ in range(3):
            self.assertTrue(auth.check_and_increment_daily_usage(USER, "qa")["allowed"])
        self.assertFalse(auth.check_and_increment_daily_usage(USER, "qa")["allowed"])
        self.assertFalse(auth.check_and_increment_daily_usage("no_such_user", "qa")["allowed"])
        self.assertEqual([a for _, _, a, _ in self._logs()], [1, 1, 1])

    def test_log_failure_rolls_back_charge(self) -> None:
        with sqlite3.connect(self.db_path) as c:
            c.execute("DROP TABLE usage_logs")
        with self.assertRaises(sqlite3.OperationalError):
            auth.check_and_increment_daily_usage(USER, "qa")
        self.assertEqual(self._count("qa"), 0)  # 扣费已回滚
        # 退还同理
        auth.init_db()
        auth.check_and_increment_daily_usage(USER, "qa")
        with sqlite3.connect(self.db_path) as c:
            c.execute("DROP TABLE usage_logs")
        with self.assertRaises(sqlite3.OperationalError):
            auth.refund_daily_usage(USER, "qa")
        self.assertEqual(self._count("qa"), 1)  # 退还已回滚

    def test_concurrent_charges_respect_limit(self) -> None:
        """20 个线程同时扣 qa（上限 3）：恰好 3 个成功，计数 3，记录 3 条。"""
        results: list[bool] = []
        lock = threading.Lock()
        barrier = threading.Barrier(20)

        def worker() -> None:
            barrier.wait()
            r = auth.check_and_increment_daily_usage(USER, "qa")
            with lock:
                results.append(r["allowed"])

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(True), 3)
        self.assertEqual(self._count("qa"), 3)
        self.assertEqual(len(self._logs()), 3)


class UsageStatsTests(_TempDbMixin, unittest.TestCase):
    def setUp(self) -> None:
        self._setup_db()
        rows = [
            ("alice", "qa", 1, "2026-09-05 10:00:00"),
            ("alice", "qa", 1, "2026-10-01 00:00:00"),
            ("alice", "roundtable", 4, "2026-10-02 12:00:00"),
            ("alice", "roundtable", -1, "2026-10-02 12:05:00"),
            ("bob", "outline", 1, "2026-10-31 23:59:59"),
            ("bob", "qa", 1, "2026-11-01 08:00:00"),
            ("carol_x", "es_search", 1, "2026-11-02 09:00:00"),
            ("carol_x", "es_search", -1, "2026-11-02 09:00:01"),  # 净 0，不列出
            ("ghost", "removed_feature", 5, "2026-11-03 00:00:00"),  # 非 FEATURES，忽略
        ]
        with sqlite3.connect(self.db_path) as c:
            c.executemany(
                "INSERT INTO usage_logs (username, feature, amount, created_at) VALUES (?,?,?,?)",
                rows,
            )

    def tearDown(self) -> None:
        self._teardown_db()

    def test_all(self) -> None:
        s = auth.get_usage_stats()
        self.assertEqual(s["since"], "2026-09-05")
        self.assertEqual(s["totals"]["qa"], 3)
        self.assertEqual(s["totals"]["roundtable"], 3)
        self.assertEqual(s["totals"]["outline"], 1)
        self.assertEqual(s["totals"]["es_search"], 0)
        self.assertEqual(s["grand_total"], 7)
        self.assertEqual([u["username"] for u in s["by_user"]], ["alice", "bob"])
        self.assertEqual(s["by_user"][0]["total"], 5)
        self.assertEqual(s["by_user"][1]["counts"]["outline"], 1)
        self.assertEqual([m["month"] for m in s["by_month"]], ["2026-09", "2026-10", "2026-11"])
        self.assertEqual(s["by_month"][1]["total"], 5)  # 10 月：qa1 + rt3 + outline1
        labels = {f["key"]: f["label"] for f in s["features"]}
        self.assertEqual(labels["translate"], "纲目翻译")
        self.assertEqual(labels["asr"], "语音转写")
        self.assertEqual(labels["outline"], "纲目制作")
        self.assertEqual([f["key"] for f in s["features"]], list(auth.FEATURES))

    def test_date_range_inclusive(self) -> None:
        s = auth.get_usage_stats("2026-10-01", "2026-10-31")
        self.assertEqual(s["grand_total"], 5)  # 含 10-01 00:00:00 与 10-31 23:59:59
        self.assertEqual(s["since"], "2026-09-05")  # since 不受筛选影响

    def test_feature_and_username_filters(self) -> None:
        s = auth.get_usage_stats(feature="qa")
        self.assertEqual(s["grand_total"], 3)
        self.assertEqual(s["totals"]["roundtable"], 0)
        s = auth.get_usage_stats(username="LIC")  # SQLite LIKE 对 ASCII 不区分大小写
        self.assertEqual([u["username"] for u in s["by_user"]], ["alice"])
        s = auth.get_usage_stats(username="_")  # _ 按字面匹配，不当通配符
        self.assertEqual(s["by_user"], [])
        self.assertEqual(s["totals"]["es_search"], 0)
        s = auth.get_usage_stats(username="%")
        self.assertEqual(s["grand_total"], 0)

    def test_invalid_params(self) -> None:
        with self.assertRaises(ValueError):
            auth.get_usage_stats(feature="nope")
        with self.assertRaises(ValueError):
            auth.get_usage_stats(start_date="2026/10/01")
        with self.assertRaises(ValueError):
            auth.get_usage_stats("2026-11-01", "2026-10-01")

    def test_empty_table(self) -> None:
        with sqlite3.connect(self.db_path) as c:
            c.execute("DELETE FROM usage_logs")
        s = auth.get_usage_stats()
        self.assertIsNone(s["since"])
        self.assertEqual(s["grand_total"], 0)
        self.assertEqual(s["by_user"], [])


class DailyCountBehaviourUnchangedTests(unittest.TestCase):
    """同一组操作分别跑「改动前 auth.py」与「当前 auth.py」，users 表每一步结果必须一致。

    改动前版本取自引入 usage_logs 之前的提交（默认 9136d116，可用环境变量 USAGE_LOGS_BASELINE_REV 覆盖）；
    没有 git 或找不到该提交时跳过。
    """

    BASELINE_REV = os.environ.get("USAGE_LOGS_BASELINE_REV", "9136d116")

    def _load_head_auth(self, tmp: Path):
        try:
            src = subprocess.run(
                ["git", "show", f"{self.BASELINE_REV}:back_cn/auth.py"],
                cwd=ROOT, capture_output=True, check=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            self.skipTest(f"无法读取基线版本 {self.BASELINE_REV}:back_cn/auth.py")
        if b"usage_logs" in src:
            self.fail(f"基线版本 {self.BASELINE_REV} 已包含 usage_logs，不是改动前的版本")
        path = tmp / "auth_head.py"
        path.write_bytes(src)
        spec = importlib.util.spec_from_file_location("auth_head", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_same_daily_counts(self) -> None:
        steps = [
            ("inc", "qa", 1), ("inc", "qa", 1), ("inc", "qa", 1), ("inc", "qa", 1),
            ("inc", "roundtable", 4), ("refund", "roundtable", 2), ("inc", "roundtable", 9),
            ("refund", "roundtable", 5), ("refund", "qa", 0), ("refund", "es_search", 1),
            ("newday", None, None), ("refund", "qa", 1), ("inc", "outline", 1),
        ]
        # 改动前的 auth.py 用 `with _connect()` 不关连接，Windows 上临时文件可能被占用：清理时忽略
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            tmp = Path(d)
            head = self._load_head_auth(tmp)
            traces = []
            for mod, name in ((head, "head.db"), (auth, "new.db")):
                orig = mod.DB_PATH
                mod.DB_PATH = tmp / name
                try:
                    mod.init_db()
                    mod.create_user(USER, "pass123")
                    mod.set_user_daily_limit(USER, "roundtable", 10)
                    mod.set_user_daily_limit(USER, "qa", 3)
                    trace = []
                    for op, feat, amt in steps:
                        if op == "inc":
                            r = mod.check_and_increment_daily_usage(USER, feat, amount=amt)
                            trace.append(("inc", feat, r["allowed"], r["used"], r["limit"]))
                        elif op == "refund":
                            mod.refund_daily_usage(USER, feat, amount=amt)
                        else:
                            with sqlite3.connect(mod.DB_PATH) as c:
                                c.execute("UPDATE users SET daily_date='2000-01-01'")
                        trace.append(mod.get_daily_usage(USER))
                        with sqlite3.connect(mod.DB_PATH) as c:
                            trace.append(c.execute("SELECT daily_date FROM users").fetchone())
                    traces.append(trace)
                finally:
                    mod.DB_PATH = orig
            gc.collect()
            self.assertEqual(traces[0], traces[1])
            self.assertGreater(len(traces[0]), 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
