# -*- coding: utf-8 -*-
"""hymn_data 载荷：大本 / 补充本 / 说明附带。"""

from __future__ import annotations

import unittest

from hymn.payload import build_hymn_data


class TestHymnPayload(unittest.TestCase):
    def test_big_from_block(self):
        targeted = {
            "blocks": [
                {
                    "series": "诗歌",
                    "hymn_number": 15,
                    "name": "诗歌第15首　敬拜父─祂的公义",
                    "text": "一　若无流血就有赦罪",
                }
            ],
            "meta": {"notes": []},
        }
        data = build_hymn_data(targeted)
        self.assertIsNotNone(data)
        self.assertEqual(len(data["hymns"]), 1)
        h = data["hymns"][0]
        self.assertEqual(h["series_zh"], "大本")
        self.assertEqual(h["hymn_number"], 15)
        self.assertIn("流血", h["text"])

    def test_sup_series_zh(self):
        targeted = {
            "blocks": [
                {
                    "series": "补充本诗歌",
                    "hymn_number": 42,
                    "name": "补充本诗歌第42首",
                    "text": "一　测试补充本",
                }
            ],
            "meta": {},
        }
        data = build_hymn_data(targeted)
        self.assertEqual(data["hymns"][0]["series_zh"], "补充本")
        self.assertEqual(data["hymns"][0]["hymn_number"], 42)

    def test_notes_kept_with_hymns(self):
        targeted = {
            "blocks": [
                {"series": "big", "hymn_number": 801, "text": "一　补充本回退样例"}
            ],
            "meta": {"notes": ["大本没有第801首，显示的是补充本第801首。"]},
        }
        data = build_hymn_data(targeted)
        self.assertEqual(data["hymns"][0]["series_zh"], "大本")
        self.assertTrue(data["notes"])

    def test_empty_blocks_returns_none(self):
        self.assertIsNone(build_hymn_data({"blocks": [], "meta": {"notes": ["无此首"]}}))
        self.assertIsNone(build_hymn_data(None))


if __name__ == "__main__":
    unittest.main()
