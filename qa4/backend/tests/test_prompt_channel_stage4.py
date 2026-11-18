# -*- coding: utf-8 -*-
"""阶段4：提示词通道与变量（新增文件，不改已有测试）。"""

from __future__ import annotations

import os
import unittest

from prompts.loader import PromptRegistry, PromptVariableError, prompt_channel


class TestPromptChannel(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("QA4_PROMPT_CHANNEL", None)

    def test_default_stable_still_placeholder(self):
        os.environ.pop("QA4_PROMPT_CHANNEL", None)
        reg = PromptRegistry()
        self.assertEqual(reg.channel, "stable")
        self.assertTrue(reg.get("step3").placeholder)
        self.assertEqual(reg.get("step3").version, "v1.0")
        self.assertIn("channel=stable", reg.version_key())

    def test_draft_loads_v01_not_placeholder(self):
        os.environ["QA4_PROMPT_CHANNEL"] = "draft"
        reg = PromptRegistry()
        self.assertEqual(reg.channel, "draft")
        tpl = reg.get("step3")
        self.assertEqual(tpl.version, "v0.1")
        self.assertFalse(tpl.placeholder)
        self.assertTrue(tpl.draft)
        self.assertIn("channel=draft", reg.version_key())
        self.assertNotEqual(
            PromptRegistry(channel="stable").version_key(),
            reg.version_key(),
        )

    def test_draft_render_no_leftover(self):
        reg = PromptRegistry(channel="draft")
        for step in reg.steps():
            tpl = reg.get(step)
            vals = {v: f"X{v}X" for v in tpl.variables}
            out = tpl.render(**vals)
            self.assertNotIn("{question}", out)
            for v in tpl.variables:
                self.assertIn(f"X{v}X", out)

    def test_variable_mismatch_raises(self):
        reg = PromptRegistry(channel="draft")
        tpl = reg.get("step2")
        with self.assertRaises(PromptVariableError):
            tpl.render(history="h")  # missing question

    def test_prompt_channel_helper(self):
        os.environ["QA4_PROMPT_CHANNEL"] = "draft"
        self.assertEqual(prompt_channel(), "draft")
        os.environ["QA4_PROMPT_CHANNEL"] = "stable"
        self.assertEqual(prompt_channel(), "stable")


if __name__ == "__main__":
    unittest.main()
