# -*- coding: utf-8 -*-
"""计价公共模块 + traces.stats 费用求和。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.pricing import (  # noqa: E402
    clear_prices_cache,
    cost_usd_from_record,
    estimate_total_cost_usd,
    est_usd_for_usage,
    load_prices,
)
from pipeline.traces import TraceStore


def _write_prices(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "已核实",
                "unit": "USD_per_million_tokens",
                "models": {
                    "claude-haiku-5-5": {
                        "input": 1.0,
                        "output": 2.0,
                        "cache_write_5m": 4.0,
                        "cache_read": 0.1,
                    },
                    "claude-sonnet-5-5": {
                        "input": 3.0,
                        "output": 6.0,
                        "cache_write_5m": 8.0,
                        "cache_read": 0.2,
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class TestPricing(unittest.TestCase):
    def setUp(self):
        clear_prices_cache()
        self._td = tempfile.TemporaryDirectory()
        self.prices_path = Path(self._td.name) / "prices.json"
        _write_prices(self.prices_path)
        self.prices = load_prices(self.prices_path, use_cache=False)

    def tearDown(self):
        clear_prices_cache()
        self._td.cleanup()

    def test_est_usd_from_tokens_with_cache(self):
        # 1M input + 1M output + 1M cache_write + 1M cache_read @ haiku
        usage = {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cache_creation_input_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000,
        }
        usd, miss, unp, m1h = est_usd_for_usage(
            usage, model="claude-haiku-5-5", prices=self.prices
        )
        self.assertFalse(miss or unp or m1h)
        self.assertEqual(usd, 1.0 + 2.0 + 4.0 + 0.1)

    def test_estimate_total_sums_steps(self):
        tokens = {
            "step2": {"input_tokens": 1_000_000, "output_tokens": 0},
            "step8": {"input_tokens": 0, "output_tokens": 1_000_000},
        }
        models = {
            "step2": {"request_model": "claude-haiku-5-5"},
            "step8": {"request_model": "claude-sonnet-5-5"},
        }
        # haiku 1M input = 1.0; sonnet 1M output = 6.0
        self.assertEqual(
            estimate_total_cost_usd(tokens, models, prices=self.prices),
            7.0,
        )

    def test_cost_from_record_prefers_stored_then_tokens(self):
        self.assertEqual(
            cost_usd_from_record({"total_cost_usd": 0.0123}, prices=self.prices),
            0.0123,
        )
        # 旧记录无 total_cost_usd：按 tokens 现算
        rec = {
            "tokens": {"step4": {"input_tokens": 1_000_000, "output_tokens": 0}},
            "models": {"step4": {"request_model": "claude-haiku-5-5"}},
        }
        self.assertEqual(cost_usd_from_record(rec, prices=self.prices), 1.0)
        # 无 tokens → 0
        self.assertEqual(cost_usd_from_record({}, prices=self.prices), 0.0)


class TestTraceStatsCost(unittest.TestCase):
    def setUp(self):
        clear_prices_cache()
        self._td = tempfile.TemporaryDirectory()
        self.prices_path = Path(self._td.name) / "prices.json"
        _write_prices(self.prices_path)
        self.prices = load_prices(self.prices_path, use_cache=False)
        # 让 stats 回退计价用这张表
        import os

        self._old = os.environ.get("QA4_PRICES_PATH")
        os.environ["QA4_PRICES_PATH"] = str(self.prices_path)
        clear_prices_cache()
        self.store = TraceStore(Path(self._td.name) / "t.db", store_question_text=True)

    def tearDown(self):
        import os

        if self._old is None:
            os.environ.pop("QA4_PRICES_PATH", None)
        else:
            os.environ["QA4_PRICES_PATH"] = self._old
        clear_prices_cache()
        self._td.cleanup()

    def test_stats_sums_stored_and_legacy_tokens(self):
        # 新记录：已有 total_cost_usd
        self.store.write(
            {
                "request_id": "a1",
                "question_hash": "h1",
                "question_len": 3,
                "question_text": "问甲",
                "cache_hit": False,
                "not_found": False,
                "elapsed_ms": 1000,
                "total_cost_usd": 0.01,
                "tokens": {},
                "models": {},
            }
        )
        # 旧记录：无 total_cost_usd，有 tokens
        self.store.write(
            {
                "request_id": "a2",
                "question_hash": "h2",
                "question_len": 3,
                "question_text": "问乙",
                "cache_hit": False,
                "not_found": False,
                "elapsed_ms": 2000,
                "tokens": {
                    "step8": {
                        "input_tokens": 1_000_000,
                        "output_tokens": 0,
                    }
                },
                "models": {"step8": {"request_model": "claude-sonnet-5-5"}},
            }
        )
        # 缓存命中不计入费用合计（与 3.0 found_non_cache 口径一致）
        self.store.write(
            {
                "request_id": "a3",
                "question_hash": "h3",
                "question_len": 2,
                "question_text": "缓存",
                "cache_hit": True,
                "not_found": False,
                "elapsed_ms": 10,
                "total_cost_usd": 9.99,
            }
        )
        stats = self.store.stats()
        # 0.01 + sonnet 1M input(3.0) = 3.01
        self.assertEqual(stats["total_cost_usd"], 3.01)
        self.assertEqual(stats["total_requests"], 3)


if __name__ == "__main__":
    unittest.main()
