# -*- coding: utf-8 -*-
"""step3 草稿：后处理对抗用例（降级不崩溃）。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from core.llm_client import parse_json_loose
from pipeline.schemas import QType
from pipeline.step03_plan import fallback_plan, postprocess


class _Deps:
    def __init__(self):
        self.cfg = {"max_subquestions": 4}
        self.life_books = [{"book_title": "罗马书生命读经"}]
        self.feasts = [{"year": 2020, "month_code": "07", "name": "夏训"}]
        self.bible = None


class TestStep3Adversarial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parent / "fixtures" / "step3_adversarial.json"
        cls.cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        cls.deps = _Deps()

    def test_fence_json_loose(self):
        case = next(c for c in self.cases if c["id"] == "bad_json_fence")
        data = parse_json_loose(case["raw_text"])
        self.assertIsInstance(data, dict)
        plan = postprocess(data, "什么是爱", self.deps)
        self.assertEqual(plan.main_type, "定义")

    def test_unknown_type_coerced(self):
        case = next(c for c in self.cases if c["id"] == "unknown_type")
        plan = postprocess(case["raw"], "什么是爱", self.deps)
        self.assertEqual(plan.main_type, QType.默认.value)

    def test_five_subq_truncated(self):
        case = next(c for c in self.cases if c["id"] == "five_subq")
        plan = postprocess(case["raw"], "复杂题", self.deps)
        self.assertLessEqual(len(plan.subquestions), 4)

    def test_bad_life_book_degrades(self):
        case = next(c for c in self.cases if c["id"] == "bad_life_book")
        plan = postprocess(case["raw"], "取篇", self.deps)
        self.assertTrue(plan.degraded)
        self.assertEqual(plan.main_type, QType.默认.value)

    def test_missing_fields_fills_subq(self):
        case = next(c for c in self.cases if c["id"] == "missing_fields")
        plan = postprocess(case["raw"], "什么是爱", self.deps)
        self.assertEqual(len(plan.subquestions), 1)
        self.assertEqual(plan.subquestions[0].text, "什么是爱")

    def test_fallback_plan(self):
        plan = fallback_plan("q", "Boom")
        self.assertTrue(plan.degraded)
        self.assertEqual(plan.main_type, QType.默认.value)


if __name__ == "__main__":
    unittest.main()
