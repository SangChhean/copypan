# -*- coding: utf-8 -*-
"""step3 取经文 JSON 示例经真实 postprocess，locator.scripture 合规。"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from pipeline.step03_plan import postprocess
from prompts.loader import PromptRegistry
from scripture.bible_text import BibleText
from scripture.normalize import parse_refs

_JSON_OBJ_RE = re.compile(r"\{\{[^{}]*(?:\{\{[^{}]*\}\}[^{}]*)*\}\}", re.DOTALL)
_BIBLE = Path(__file__).resolve().parents[2] / "data" / "bible_data"


class _Deps:
    def __init__(self, bible):
        self.cfg = {"max_subquestions": 4}
        self.life_books = []
        self.feasts = []
        self.bible = bible


class TestStep3ScriptureJsonExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bible = BibleText(_BIBLE) if _BIBLE.is_dir() else None
        cls.deps = _Deps(cls.bible)
        text = PromptRegistry(channel="draft").get("step3").text
        cls.examples = []
        for m in _JSON_OBJ_RE.finditer(text):
            raw = m.group(0)
            if '"经文"' not in raw and "'经文'" not in raw:
                continue
            if "main_type" not in raw:
                continue
            fixed = raw.replace("{{", "{").replace("}}", "}")
            try:
                obj = json.loads(fixed)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("main_type") == "经文":
                cls.examples.append(obj)

    def test_found_scripture_example(self):
        self.assertGreaterEqual(len(self.examples), 1)

    def test_postprocess_scripture_locator(self):
        for i, raw in enumerate(self.examples):
            with self.subTest(i=i):
                q = (raw.get("subquestions") or [{}])[0].get("text") or "请给我经文"
                plan = postprocess(raw, q, self.deps)
                self.assertFalse(plan.degraded, msg=plan.understanding)
                self.assertEqual(plan.main_type, "经文")
                self.assertIsNotNone(plan.locator)
                sc = plan.locator.scripture
                self.assertTrue(sc)
                refs = parse_refs(sc, bible=self.bible, validate=self.bible is not None)
                self.assertTrue(refs, msg=f"scripture={sc!r}")
                # 规范化短标签形如 林前15:45
                self.assertRegex(sc, r"^[\u4e00-\u9fff]{1,4}\d+:\d+")


if __name__ == "__main__":
    unittest.main()
