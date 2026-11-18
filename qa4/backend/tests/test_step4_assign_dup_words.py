# -*- coding: utf-8 -*-
"""重复词：pipeline 在 assign 前经 postprocess_words 去重；sq2 不含「离婚」时不得拿到。"""

from __future__ import annotations

import unittest

from pipeline.caps import caps_cfg
from pipeline.schemas import Plan, SubQuestion
from pipeline.step04_layer1 import assign_to_subquestions, postprocess_words


class TestStep4AssignDupWords(unittest.TestCase):
    def test_dup_离婚_after_postprocess_skips_sq_without_word(self):
        # 与 run() 一致：扁平后先 postprocess_words（L52–53 去重），再 assign
        q = "弟兄姊妹离婚了还可以擘饼吗？"
        raw = ["离婚", "擘饼", "离婚"]
        kept, _ = postprocess_words(raw, q, lookups=None, plan=None)
        self.assertEqual(kept, ["离婚", "擘饼"])  # 第二次「离婚」已去掉

        plan = Plan(
            main_type="召会生活",
            complex=True,
            subquestions=[
                SubQuestion(text="离婚后经文根据是什么？", qtype="召会生活"),
                SubQuestion(text="离婚后真理原则是什么？", qtype="召会生活"),
                SubQuestion(text="召会如何处理与实行？", qtype="召会生活"),  # 不含「离婚」
            ],
        )
        per = assign_to_subquestions(kept, plan, caps_cfg=caps_cfg(), whole=8)
        self.assertIn("离婚", per[0])
        self.assertIn("离婚", per[1])
        self.assertNotIn("离婚", per[2])
        unique = {w for bucket in per for w in bucket}
        self.assertLessEqual(len(unique), 8)


if __name__ == "__main__":
    unittest.main()
