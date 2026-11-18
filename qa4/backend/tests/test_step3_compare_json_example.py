# -*- coding: utf-8 -*-
"""step3 草稿 JSON 须含比较示例，且 compare_objects 合格。"""

from __future__ import annotations

import json
import re
import unittest
from types import SimpleNamespace

from prompts.loader import PromptRegistry
from pipeline.step03_plan import postprocess


_JSON_OBJ_RE = re.compile(r"\{\{[^{}]*(?:\{\{[^{}]*\}\}[^{}]*)*\}\}", re.DOTALL)


def _extract_plans(text: str) -> list[dict]:
    out: list[dict] = []
    for m in _JSON_OBJ_RE.finditer(text):
        raw = m.group(0)
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


class TestStep3CompareJsonExample(unittest.TestCase):
    def test_compare_example_present_and_ok(self):
        tpl = PromptRegistry(channel="draft").get("step3")
        plans = _extract_plans(tpl.text)
        compares = [p for p in plans if p.get("main_type") == "比较"]
        self.assertGreaterEqual(len(compares), 1, msg="缺少比较 JSON 示例")
        deps = SimpleNamespace(
            cfg={"max_subquestions": 4},
            life_books=[],
            feasts=[],
            bible=None,
        )
        for raw in compares:
            sq0 = (raw.get("subquestions") or [{}])[0]
            objs = sq0.get("compare_objects") or []
            self.assertEqual(len(objs), 2, msg=f"compare_objects 须两个：{objs}")
            plan = postprocess(raw, str(sq0.get("text") or "比较"), deps)
            self.assertFalse(plan.degraded)
            self.assertEqual(plan.main_type, "比较")
            self.assertEqual(len(plan.subquestions[0].compare_objects), 2)


if __name__ == "__main__":
    unittest.main()
