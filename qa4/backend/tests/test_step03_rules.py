# -*- coding: utf-8 -*-
"""规则前置与冲突小表；歌词用合成语料。"""

from __future__ import annotations

import unittest

from pipeline.step03_rules import apply_rule_plan
from tests._fast_hymn_env import attach_synth_to_deps, ensure_synth_lyrics_index


def _deps():
    from config import load_config_json

    class D:
        pass

    d = D()
    d.cfg = load_config_json("pipeline.json")
    d.bible = None
    attach_synth_to_deps(d)
    return d


class TestStep03Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.synth_index = ensure_synth_lyrics_index()

    def setUp(self):
        self.deps = _deps()

    def test_pure_scripture_skips_llm(self):
        o = apply_rule_plan("约3:16", "约3:16", self.deps, bible=None)
        self.assertTrue(o.skip_llm)
        self.assertEqual(o.plan.source, "scripture_rule")
        self.assertEqual(o.plan.main_type, "经文")

    def test_pure_hymn_skips_llm(self):
        o = apply_rule_plan("诗歌第15首", "诗歌第15首", self.deps, bible=None)
        self.assertTrue(o.skip_llm)
        self.assertEqual(o.plan.source, "hymn_rule")
        self.assertEqual(o.plan.locator.hymn_series, "big")
        self.assertEqual(o.plan.locator.hymn_number, 15)

    def test_substantive_scripture_no_short_circuit(self):
        o = apply_rule_plan("约3:16是什么意思", "约3:16是什么意思", self.deps, bible=None)
        self.assertFalse(o.skip_llm)
        self.assertTrue(any(h.get("kind") == "scripture" for h in o.rule_hits))

    def test_lyrics_single(self):
        q = "哪首诗歌有这句：合成朝阳升起照亮测试山谷溪流"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertTrue(o.skip_llm)
        self.assertEqual(o.plan.source, "lyrics_rule")
        self.assertEqual(o.plan.main_type, "诗歌")
        self.assertEqual(o.plan.locator.hymn_number, 1)

    def test_lyrics_multi_choose(self):
        q = "哪首诗歌有这句：合成双命中专有短句金银铜铁"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertTrue(o.early_done)
        self.assertTrue(o.awaiting_choice)
        self.assertGreaterEqual(len(o.choose_candidates), 2)
        self.assertIn("合成双命中", o.answer_text)

    def test_lyrics_too_short(self):
        q = "哪首诗歌有这句：啊"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertTrue(o.early_done)
        self.assertEqual(o.lyrics_status, "too_short")

    def test_lyrics_too_short_bare_no_hint(self):
        # 与 find_lyrics 一致：无提示的过短输入也 too_short，不交模型
        o = apply_rule_plan("主啊", "主啊", self.deps, bible=None)
        self.assertTrue(o.early_done)
        self.assertTrue(o.skip_llm)
        self.assertEqual(o.lyrics_status, "too_short")
        self.assertFalse(any(h.get("kind") == "lyrics" and h.get("status") == "found" for h in o.rule_hits))

    def test_lyrics_too_common(self):
        q = "哪首诗歌有这句：合成共用短句重复出现在多样例中"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertTrue(o.early_done)
        self.assertEqual(o.lyrics_status, "too_common")

    def test_lyrics_not_found_falls_through(self):
        q = "哪首诗歌有这句：完全虚构绝无命中的合成长句甲乙丙丁"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertFalse(o.skip_llm)
        self.assertEqual(o.lyrics_status, "not_found")
        self.assertIsNone(o.plan)

    def test_rule_disabled(self):
        self.deps.cfg = dict(self.deps.cfg)
        self.deps.cfg["rule_preplan_enabled"] = False
        o = apply_rule_plan("约3:16", "约3:16", self.deps, bible=None)
        self.assertFalse(o.skip_llm)
        self.assertIsNone(o.plan)

    def test_scripture_false_positive_with_strong_hint_goes_lyrics(self):
        # 经文解析误读「约三16…」但带强提示且歌词 found → 走歌词
        q = "哪首诗歌有这句：约三16恩典临到测试山谷溪流长"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertTrue(o.skip_llm)
        self.assertEqual(o.plan.source, "lyrics_rule")
        self.assertEqual(o.plan.locator.hymn_number, 5)
        self.assertTrue(any(h.get("kind") == "scripture" for h in o.rule_hits))

    def test_scripture_and_strong_hint_but_lyrics_not_found_to_model(self):
        q = "哪首诗歌有这句约3:16"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertFalse(o.skip_llm)
        self.assertIsNone(o.plan)
        self.assertTrue(any(h.get("kind") == "scripture" for h in o.rule_hits))

    def test_scripture_false_positive_without_strong_hint_stays_model(self):
        # 无强档提示：即使正文含可被 parse_refs 的片段，也不走歌词
        q = "约三16恩典临到测试山谷溪流长是什么意思"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertFalse(o.skip_llm)
        self.assertNotEqual(getattr(o.plan, "source", None), "lyrics_rule")
        self.assertTrue(any(h.get("kind") == "scripture" for h in o.rule_hits))

    def test_title_equals_lexicon_without_strong_goes_model(self):
        from pipeline.step03_rules import _norm_name

        self.deps.lexicon_norm_names = {_norm_name("爱里建造")}
        q = "爱里建造"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertFalse(o.skip_llm)
        self.assertNotEqual(getattr(o.plan, "source", None), "lyrics_rule")

    def test_title_equals_lexicon_with_strong_goes_lyrics(self):
        from pipeline.step03_rules import _norm_name

        self.deps.lexicon_norm_names = {_norm_name("爱里建造")}
        q = "哪首诗歌的歌词是爱里建造"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertTrue(o.skip_llm)
        self.assertEqual(o.plan.source, "lyrics_rule")
        self.assertEqual(o.plan.locator.hymn_number, 6)

    def test_title_not_lexicon_without_strong_goes_lyrics(self):
        from pipeline.step03_rules import _norm_name

        self.deps.lexicon_norm_names = {_norm_name("爱里建造")}
        q = "合成独特诗名无词条冲突专用"
        o = apply_rule_plan(q, q, self.deps, bible=None)
        self.assertTrue(o.skip_llm)
        self.assertEqual(o.plan.source, "lyrics_rule")
        self.assertEqual(o.plan.locator.hymn_number, 7)


class TestGroupDeterminism(unittest.TestCase):
    """格式集分组与种子/调用次序无关。"""

    def test_scripture_v2_group_stable_across_two_calls(self):
        import csv
        from pathlib import Path
        from tools.probe_pipeline_rules import _deps, _group_reason

        path = Path(__file__).resolve().parents[2] / "notes" / "scripture_format_cases_v2.csv"
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
        deps_a = _deps()
        deps_b = _deps()
        g1 = [
            (r.get("id"), _group_reason((r.get("input") or "").strip(), "scripture", deps_a, has_refs=False))
            for r in rows
        ]
        # 中间跑一遍规则，模拟探针干扰
        for r in rows[:40]:
            inp = (r.get("input") or "").strip()
            apply_rule_plan(inp, inp, deps_a, bible=deps_a.bible)
        g2 = [
            (r.get("id"), _group_reason((r.get("input") or "").strip(), "scripture", deps_b, has_refs=False))
            for r in rows
        ]
        self.assertEqual(g1, g2)


class TestConflictTable(unittest.TestCase):
    """冲突小表：期望路径。"""

    def setUp(self):
        self.deps = _deps()

    def _path(self, q: str) -> str:
        o = apply_rule_plan(q, q, self.deps, bible=None)
        if o.skip_llm and o.plan and o.plan.source == "scripture_rule":
            return "scripture_rule"
        if o.skip_llm and o.plan and o.plan.source == "hymn_rule":
            return "hymn_rule"
        if o.early_done or (o.plan and o.plan.source == "lyrics_rule"):
            return "lyrics_rule"
        if o.rule_hits and not o.skip_llm:
            kinds = [h.get("kind") for h in o.rule_hits if h.get("kind") in {"scripture", "hymn"}]
            return "model_with_hits:" + ",".join(kinds) if kinds else "model"
        return "model"

    def test_conflict_cases(self):
        expected = {
            "诗15": "scripture_rule",  # 诗篇第15章
            "诗歌15": "hymn_rule",
            "诗篇23": "scripture_rule",
            # 含出处+歌词强提示：记经文 hits，不短路，不进歌词
            "哪首诗歌有这句约3:16": "model_with_hits:scripture",
            "约3:16是什么意思": "model_with_hits:scripture",
            "约3:16的注解": "model_with_hits:scripture",
            "倪柝声怎样讲罗8:2": "model_with_hits:scripture",
            "诗歌15首讲什么": "model_with_hits:hymn",
        }
        for q, want in expected.items():
            self.assertEqual(self._path(q), want, msg=q)


if __name__ == "__main__":
    unittest.main()
