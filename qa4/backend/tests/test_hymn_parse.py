# -*- coding: utf-8 -*-
"""诗歌首数识别：规则 (c)(d)(e)(f)(g) 单元测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from hymn.catalog import HymnCatalog
from hymn.parse import format_hymn_refs, parse_hymn_refs

JSON = Path(r"G:\PanAI4.0专用\索引数据\panai4_hymns\02_清洗JSON\chunks_hymns.json")


@unittest.skipUnless(JSON.is_file(), "hymns 清洗 JSON 未就绪")
class TestHymnParseRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = HymnCatalog()
        cls.cat.ensure_loaded(json_path=JSON)

    def _fmt(self, text: str) -> str:
        return format_hymn_refs(parse_hymn_refs(text, catalog=self.cat))

    # ---- (c) 句式 ----
    def test_c_di_before_number_required_for_trailing(self):
        self.assertEqual(self._fmt("第15首诗歌"), "大本 15")
        self.assertEqual(self._fmt("15首诗歌"), "无首数")

    def test_c_quantity_and_chapter_not_hymn(self):
        self.assertEqual(self._fmt("三首诗歌"), "无首数")
        self.assertEqual(self._fmt("诗歌有780首"), "无首数")
        self.assertEqual(self._fmt("诗歌第三章"), "无首数")

    # ---- (d) 无系列词 ----
    def test_d_bare_number_forms_empty(self):
        self.assertEqual(self._fmt("第15首"), "无首数")
        self.assertEqual(self._fmt("15首"), "无首数")
        self.assertEqual(self._fmt("No.15"), "无首数")
        self.assertEqual(self._fmt("#15"), "无首数")
        self.assertEqual(self._fmt("补5"), "无首数")
        self.assertEqual(self._fmt("补充5"), "无首数")
        self.assertEqual(self._fmt("小本5"), "无首数")
        self.assertEqual(self._fmt("附1"), "无首数")

    # ---- (e) 与诗篇区分 ----
    def test_e_psalm_not_hymn(self):
        self.assertEqual(self._fmt("诗15"), "无首数")
        self.assertEqual(self._fmt("诗篇15篇"), "无首数")
        self.assertEqual(self._fmt("诗23"), "无首数")

    def test_e_shi_with_shou_is_hymn(self):
        self.assertEqual(self._fmt("诗15首"), "大本 15")
        self.assertEqual(self._fmt("诗第15首"), "大本 15")

    # ---- (f) 多首与截断 ----
    def test_f_list_and_range(self):
        self.assertEqual(self._fmt("诗歌1、2、3"), "大本 1 ; 大本 2 ; 大本 3")
        self.assertEqual(self._fmt("诗歌1到3首"), "大本 1 ; 大本 2 ; 大本 3")

    def test_f_truncate_max_10(self):
        out = self._fmt("诗歌1至12")
        self.assertTrue(out.endswith("+截断"))
        self.assertEqual(out.count("大本"), 10)

    def test_f_missing_in_range(self):
        self.assertEqual(
            self._fmt("补充本36-40"),
            "补充本 36 ; 补充本 37 ; 无此首 补充本 38 ; 无此首 补充本 39 ; 无此首 补充本 40",
        )

    # ---- (g) 存在性与回退 ----
    def test_g_fallback_sup(self):
        self.assertEqual(self._fmt("诗歌801"), "补充本 801 *")
        r = parse_hymn_refs("诗歌801", catalog=self.cat)[0]
        self.assertEqual(r.series, "sup")
        self.assertTrue(r.fallback)
        self.assertTrue(r.exists)

    def test_g_explicit_big_no_fallback(self):
        self.assertEqual(self._fmt("大本781"), "无此首 大本 781")
        r = parse_hymn_refs("大本781", catalog=self.cat)[0]
        self.assertEqual(r.series, "big")
        self.assertTrue(r.explicit_series)
        self.assertFalse(r.fallback)

    def test_g_zero_and_missing_sup(self):
        self.assertEqual(self._fmt("诗歌0"), "无此首 大本 0")
        self.assertEqual(self._fmt("补充本50"), "无此首 补充本 50")


if __name__ == "__main__":
    unittest.main()
