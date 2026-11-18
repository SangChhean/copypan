# -*- coding: utf-8 -*-
"""从 step3_v0.1 提取 JSON 示例，走真实 postprocess。"""

from __future__ import annotations

import json
import re
import unittest
from types import SimpleNamespace

from prompts.loader import PromptRegistry
from pipeline.step03_plan import postprocess


_JSON_OBJ_RE = re.compile(r"\{\{[^{}]*(?:\{\{[^{}]*\}\}[^{}]*)*\}\}", re.DOTALL)


def _extract_json_examples(text: str) -> list[dict]:
    """把 {{ / }} 还原后解析对象；跳过过小的片段（如单字段示意）。"""
    out: list[dict] = []
    for m in _JSON_OBJ_RE.finditer(text):
        raw = m.group(0)
        # 只取含 main_type 的完整 Plan 示例
        if "main_type" not in raw:
            continue
        fixed = raw.replace("{{", "{").replace("}}", "}")
        try:
            obj = json.loads(fixed)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "main_type" in obj:
            out.append(obj)
    return out


class _Deps:
    def __init__(self):
        self.cfg = {"max_subquestions": 4}
        self.life_books = [
            {"book_title": "罗马书生命读经"},
            {"book_title": "约翰福音生命读经"},
            {"book_title": "加拉太书生命读经"},
            {"book_title": "创世记生命读经"},
        ]
        self.feasts = [
            {"year": 2019, "month_code": "07", "name": "2019年秋季长老训练"},
            {"year": 2020, "month_code": "04", "name": "2020年夏季训练"},
            {"year": 2021, "month_code": "02", "name": "2021年春季长老训练"},
        ]
        self.bible = None


class TestStep3PromptJsonExamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tpl = PromptRegistry(channel="draft").get("step3")
        cls.examples = _extract_json_examples(tpl.text)
        cls.deps = _Deps()

    def test_found_at_least_five(self):
        self.assertGreaterEqual(len(self.examples), 5, msg=f"got {len(self.examples)}")

    def test_each_postprocess_ok(self):
        for i, raw in enumerate(self.examples):
            with self.subTest(i=i, main_type=raw.get("main_type")):
                q = ""
                subs = raw.get("subquestions") or []
                if subs and isinstance(subs[0], dict):
                    q = str(subs[0].get("text") or "")
                plan = postprocess(raw, q or "示例题", self.deps)
                self.assertFalse(plan.degraded, msg=plan.understanding)
                self.assertNotIn("核对不过", plan.understanding or "")
                loc = plan.locator
                if loc and loc.book_title:
                    titles = {b["book_title"] for b in self.deps.life_books}
                    self.assertIn(loc.book_title, titles)
                if loc and loc.feast_month:
                    self.assertRegex(str(loc.feast_month), r"^\d{2}$")
                    ok = any(
                        int(f["year"]) == int(loc.feast_year)
                        and str(f["month_code"]).zfill(2) == str(loc.feast_month).zfill(2)
                        for f in self.deps.feasts
                    )
                    self.assertTrue(ok)
                if loc and loc.hymn_series:
                    self.assertIn(loc.hymn_series, {"big", "sup", "fu", "child"})


if __name__ == "__main__":
    unittest.main()
