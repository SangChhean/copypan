# -*- coding: utf-8 -*-
"""「……」引文核对：同段顺序通过；跨段或颠倒不通过。"""

from __future__ import annotations

import unittest

from pipeline.citations import verify_quotes
from pipeline.schemas import Passage


class TestCitationsEllipsis(unittest.TestCase):
    def test_same_passage_order_ok(self):
        p = Passage(number=1, id="a", index="x", text="前半句内容在这里。后半句也在同段。")
        checks = verify_quotes("「前半句内容在这里……后半句也在同段」", [p])
        self.assertEqual(len(checks), 1)
        self.assertTrue(checks[0].ok)
        self.assertEqual(checks[0].passage_n, 1)
        self.assertEqual(checks[0].parts, 2)

    def test_different_passages_fail(self):
        p1 = Passage(number=1, id="a", index="x", text="前半句内容在这里。")
        p2 = Passage(number=2, id="b", index="x", text="无关另一段后半。")
        checks = verify_quotes("「前半句内容在这里……无关另一段后半」", [p1, p2])
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0].ok)

    def test_reversed_order_fail(self):
        p = Passage(number=1, id="a", index="x", text="前半句内容在这里。后半句也在同段。")
        checks = verify_quotes("「后半句也在同段……前半句内容在这里」", [p])
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0].ok)

    def test_heading_lines_skip_quote_verify(self):
        """以 ## / ### 开头的行上的「」不核对、不进 QuoteCheck。"""
        p = Passage(number=1, id="a", index="x", text="正文里的原话在这里。")
        text = (
            "## 总标题里有「假引文」\n"
            "正文「正文里的原话在这里」[1]\n"
            "### 小标题「也不核对」\n"
            "再一句「不存在的字」[1]\n"
        )
        checks = verify_quotes(text, [p])
        quotes = [c.quote for c in checks]
        self.assertNotIn("假引文", quotes)
        self.assertNotIn("也不核对", quotes)
        self.assertIn("正文里的原话在这里", quotes)
        self.assertIn("不存在的字", quotes)
        by_q = {c.quote: c for c in checks}
        self.assertTrue(by_q["正文里的原话在这里"].ok)
        self.assertFalse(by_q["不存在的字"].ok)


if __name__ == "__main__":
    unittest.main()
