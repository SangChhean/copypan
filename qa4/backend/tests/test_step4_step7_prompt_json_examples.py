# -*- coding: utf-8 -*-
"""从 step4/step7 草稿提示词提取 JSON 示例，送进真实解析。"""

from __future__ import annotations

import json
import re
import unittest
from types import SimpleNamespace

from prompts.loader import PromptRegistry
from pipeline.schemas import Passage
from pipeline.step04_layer1 import postprocess_words
from pipeline.step07_judge import apply_rules


_JSON_OBJ_RE = re.compile(r"\{\{[^{}]*(?:\{\{[^{}]*\}\}[^{}]*)*\}\}", re.DOTALL)


def _extract_objs(text: str) -> list[dict]:
    out: list[dict] = []
    for m in _JSON_OBJ_RE.finditer(text):
        fixed = m.group(0).replace("{{", "{").replace("}}", "}")
        try:
            obj = json.loads(fixed)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _flatten_step4_words(obj: dict) -> list[str]:
    if isinstance(obj.get("words"), list):
        return [str(x) for x in obj["words"]]
    flat: list[str] = []
    for s in obj.get("subquestions") or []:
        if isinstance(s, dict) and isinstance(s.get("words"), list):
            flat.extend(str(x) for x in s["words"])
    return flat


class TestStep4PromptJsonExamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.objs = [
            o
            for o in _extract_objs(PromptRegistry(channel="draft").get("step4").text)
            if "words" in o or "subquestions" in o
        ]

    def test_at_least_six(self):
        self.assertGreaterEqual(len(self.objs), 6)

    def test_parse_and_fields(self):
        for i, obj in enumerate(self.objs):
            with self.subTest(i=i):
                if "words" in obj:
                    self.assertIsInstance(obj["words"], list)
                    self.assertTrue(all(isinstance(w, str) and w for w in obj["words"]))
                if "subquestions" in obj:
                    self.assertIsInstance(obj["subquestions"], list)
                    for s in obj["subquestions"]:
                        self.assertIn("index", s)
                        self.assertIsInstance(s.get("words"), list)
                words = _flatten_step4_words(obj)
                self.assertTrue(words)
                # 用拼接假问题，使 postprocess 的「须在原文出现」能通过
                q = " ".join(words) + " 示例问句"
                kept, _ = postprocess_words(words, q, lookups=None, plan=None)
                uniq: list[str] = []
                for w in words:
                    if w not in uniq:
                        uniq.append(w)
                self.assertEqual(kept, uniq)


class TestStep7PromptJsonExamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.objs = [
            o
            for o in _extract_objs(PromptRegistry(channel="draft").get("step7").text)
            if "overall" in o and ("keep" in o or "drop" in o)
        ]

    def test_at_least_three(self):
        # 第4批起至少 4 个（含 has_original + has_approx）
        self.assertGreaterEqual(len(self.objs), 4)

    def test_verify_flags_present(self):
        has_orig = [o for o in self.objs if o.get("has_original") is True]
        has_approx = [o for o in self.objs if o.get("has_approx") is True]
        self.assertGreaterEqual(len(has_orig), 1)
        self.assertGreaterEqual(len(has_approx), 1)

    def test_apply_rules_ok(self):
        for i, obj in enumerate(self.objs):
            with self.subTest(i=i, overall=obj.get("overall")):
                self.assertIn(obj["overall"], {"够", "部分够", "不够"})
                keep = obj.get("keep") or []
                drop = obj.get("drop") or []
                self.assertIsInstance(keep, list)
                self.assertIsInstance(drop, list)
                nums = sorted({int(n) for n in list(keep) + list(drop)})
                passages = [
                    Passage(
                        number=n,
                        id=f"p{n}",
                        index="outline_12490",
                        text=f"段{n}",
                        book_title="自造",
                        message_title="",
                    )
                    for n in nums
                ]
                qtype = "核实说法" if obj.get("has_original") is not None else (
                    "比较" if obj.get("sides_missing") is not None else "默认"
                )
                v = apply_rules(qtype, obj, passages)
                self.assertIn(v.overall, {"够", "部分够", "不够"})
                self.assertTrue(v.keep)


if __name__ == "__main__":
    unittest.main()
