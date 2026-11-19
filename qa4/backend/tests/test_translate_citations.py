# -*- coding: utf-8 -*-
"""英译引用编号掩码：重编号后的 [n] 译完应原样保留；answer 不含书目块。"""

from __future__ import annotations

import unittest
from unittest import mock

from core import translate as tr


class TestMaskBracketCitations(unittest.TestCase):
    def test_mask_and_unmask_bracket_n(self):
        body = "先引「乙」[1] 再引「甲」[2] 又引[1]"
        masked, ph = tr.mask_en_citations(body)
        self.assertNotIn("[1]", masked)
        self.assertNotIn("[2]", masked)
        self.assertIn("[REF:0]", masked)
        restored = tr.unmask_en_citations(masked, ph)
        self.assertEqual(restored, body)

    def test_translate_en_keeps_renumbered_brackets(self):
        """模拟 Gemini 原样回传占位符：重编号正文译完编号不变，且不拼 References。"""
        body = "先引「乙」[1] 再引「甲」[2] 又引[1]"
        sources = ["[1] 乙书 篇三", "[2] 甲书"]

        def fake_gemini(text: str) -> str:
            # 占位符必须保留；其余可改成英文
            return text.replace("先引「乙」", "First cite B").replace("再引「甲」", "then A").replace(
                "又引", "again"
            )

        with mock.patch.object(tr, "gemini_translate_en", side_effect=fake_gemini):
            out = tr.translate_answer(text=body, sources=sources, target_lang="en")
        self.assertEqual(out["answer"], "First cite B[1] then A[2] again[1]")
        self.assertNotIn("[References]", out["answer"])
        self.assertNotIn("乙书", out["answer"])
        self.assertEqual(out["sources"], sources)

    def test_unmask_mismatch_logs(self):
        body = "见[1]与[2]"
        masked, ph = tr.mask_en_citations(body)
        broken = masked.replace("[REF:0]", "")  # 丢掉一个占位
        with self.assertLogs("qa4.translate", level="WARNING") as cm:
            tr.unmask_en_citations(broken, ph)
        self.assertTrue(any("citation unmask mismatch" in r for r in cm.output))


if __name__ == "__main__":
    unittest.main()
