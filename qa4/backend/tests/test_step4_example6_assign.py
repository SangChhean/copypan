# -*- coding: utf-8 -*-
"""step4 共用词回填：示例 6、离婚擘饼拆分、每子问题/整题去重上限。"""

from __future__ import annotations

import json
import re
import unittest

from pipeline.caps import caps_cfg
from pipeline.schemas import Plan, SubQuestion
from pipeline.step04_layer1 import assign_to_subquestions, postprocess_words
from prompts.loader import PromptRegistry

_JSON_OBJ_RE = re.compile(r"\{\{[^{}]*(?:\{\{[^{}]*\}\}[^{}]*)*\}\}", re.DOTALL)


def _example6_obj(text: str) -> dict:
    for m in _JSON_OBJ_RE.finditer(text):
        fixed = m.group(0).replace("{{", "{").replace("}}", "}")
        try:
            obj = json.loads(fixed)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        subs = obj.get("subquestions")
        if isinstance(subs, list) and len(subs) >= 2 and all(
            isinstance(s, dict) and "words" in s for s in subs
        ):
            flat = []
            for s in subs:
                flat.extend(s.get("words") or [])
            if "生机的救恩" in flat and "素质" in flat and "经历" in flat:
                return obj
    raise AssertionError("step4 示例 6 JSON 未找到")


class TestStep4Example6Assign(unittest.TestCase):
    def test_example6_assign_matches_program(self):
        tpl = PromptRegistry(channel="draft").get("step4")
        obj = _example6_obj(tpl.text)
        flat: list[str] = []
        for s in obj["subquestions"]:
            flat.extend(str(w) for w in s["words"])
        q = "生机的救恩：素质一面是什么？生机的救恩：经历一面是什么？"
        kept, _ = postprocess_words(flat, q, lookups=None, plan=None)
        self.assertEqual(kept, ["生机的救恩", "素质", "经历"])
        plan = Plan(
            main_type="默认",
            complex=True,
            subquestions=[
                SubQuestion(text="生机的救恩：素质一面是什么？", qtype="定义"),
                SubQuestion(text="生机的救恩：经历一面是什么？", qtype="个人经历"),
            ],
        )
        per = assign_to_subquestions(kept, plan, caps_cfg=caps_cfg(), whole=8)
        self.assertEqual(per, [["生机的救恩", "素质"], ["生机的救恩", "经历"]])


class TestStep4SharedWordBackfill(unittest.TestCase):
    def test_divorce_bread_shared_to_all_nonsynth(self):
        q = "弟兄姊妹离婚了还可以擘饼吗？"
        words = ["离婚", "擘饼"]
        kept, _ = postprocess_words(words, q, lookups=None, plan=None)
        plan = Plan(
            main_type="召会生活",
            complex=True,
            subquestions=[
                SubQuestion(text="弟兄姊妹离婚后可否擘饼：经文根据是什么？", qtype="召会生活"),
                SubQuestion(text="弟兄姊妹离婚后可否擘饼：真理原则是什么？", qtype="召会生活"),
                SubQuestion(text="弟兄姊妹离婚后可否擘饼：召会如何处理与实行？", qtype="召会生活"),
                SubQuestion(text="弟兄姊妹离婚后可否擘饼：综合以上各点", qtype="召会生活", synthesis=True),
            ],
        )
        per = assign_to_subquestions(kept, plan, caps_cfg=caps_cfg(), whole=8)
        self.assertEqual(per[0], ["离婚", "擘饼"])
        self.assertEqual(per[1], ["离婚", "擘饼"])
        self.assertEqual(per[2], ["离婚", "擘饼"])
        self.assertEqual(per[3], [])

    def test_per_subq_and_unique_whole_caps(self):
        # 自造：每子问题 cap=3；整题 unique=8；共用回填不把 unique 计重
        plan = Plan(
            main_type="默认",
            complex=True,
            subquestions=[
                SubQuestion(text="甲词 乙词 丙词 丁词 戊词 己词 庚词 辛词 壬词", qtype="默认"),
                SubQuestion(text="甲词 乙词 丙词 丁词 戊词 己词 庚词 辛词", qtype="默认"),
                SubQuestion(text="综合跳过", qtype="默认", synthesis=True),
            ],
        )
        words = ["甲词", "乙词", "丙词", "丁词", "戊词", "己词", "庚词", "辛词", "壬词"]
        per = assign_to_subquestions(words, plan, caps_cfg=caps_cfg(), whole=8)
        self.assertLessEqual(len(per[0]), 3)
        self.assertLessEqual(len(per[1]), 3)
        self.assertEqual(per[2], [])
        # 前 3 个共用进两边；丁…辛 因两侧已满且 unique 未满也无法再进匹配槽 → 壬词 unique 第 9 被整题掐掉
        unique = {w for bucket in per for w in bucket}
        self.assertLessEqual(len(unique), 8)
        self.assertEqual(per[0], ["甲词", "乙词", "丙词"])
        self.assertEqual(per[1], ["甲词", "乙词", "丙词"])
        self.assertNotIn("壬词", unique)


if __name__ == "__main__":
    unittest.main()
