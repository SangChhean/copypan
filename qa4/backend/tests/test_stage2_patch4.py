# -*- coding: utf-8 -*-
"""补丁四：preprocess 制表符/全角冒号；源比对工具离线单元。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripture.normalize import parse_refs, preprocess_ref_text
from tests._helpers import bible


class TestPreprocessTabColon(unittest.TestCase):
    def test_tab_fullwidth_colon_to_vendor_form(self):
        raw = "腓\t1：5"
        self.assertEqual(preprocess_ref_text(raw), "腓一5")
        refs = parse_refs(raw, bible=bible(), validate=True)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].book, "腓")
        self.assertEqual(refs[0].chapter, 1)
        self.assertEqual(refs[0].v_start, 5)

    def test_arabic_colon_without_tab(self):
        self.assertEqual(preprocess_ref_text("太3：16"), "太三16")
        refs = parse_refs("太3：16", bible=bible(), validate=True)
        self.assertEqual(len(refs), 1)
        self.assertEqual((refs[0].book, refs[0].chapter, refs[0].v_start), ("太", 3, 16))

    def test_normal_forms_unchanged(self):
        self.assertEqual(preprocess_ref_text("腓一5"), "腓一5")
        self.assertEqual(preprocess_ref_text("诗十〇二14"), "诗一〇二14")
        self.assertEqual(preprocess_ref_text("诗二十三"), "诗二十三")
        self.assertEqual(preprocess_ref_text("林前三10"), "林前三10")
        refs = parse_refs("腓一5", bible=bible(), validate=True)
        self.assertEqual(len(refs), 1)


class TestAnalyzeSourceDupesOffline(unittest.TestCase):
    def test_volume_key_and_focus_cross(self):
        from tools.analyze_source_dupes import analyze_index, text_hash, volume_key

        rows = [
            {
                "chunk_id": "cwwl_1994-1997-2-1#1-1",
                "text": "AAA same",
                "book_title": "x",
            },
            {
                "chunk_id": "cwwl_1994-1997-2-1#1-2",
                "text": "unique-in-focus",
                "book_title": "x",
            },
            {
                "chunk_id": "cwwl_1998-1-1#1-1",
                "text": "AAA same",
                "book_title": "y",
            },
            {
                "chunk_id": "cwwl_1998-1-1#1-2",
                "text": "other-only",
                "book_title": "y",
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.jsonl"
            p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            info = analyze_index([p], "text_cwwl")
        self.assertEqual(info["source_rows"], 4)
        self.assertEqual(info["unique_chunk_ids"], 4)
        self.assertEqual(info["chunk_id_duplicate_extra_rows"], 0)
        self.assertGreaterEqual(info["same_text_rows"], 2)
        focus = info["focus_cwwl_1994_1997_2"]
        self.assertEqual(focus["n"], 2)
        self.assertEqual(focus["cross_volume_same_text_n"], 1)
        self.assertIn("cwwl_1994-1997-2-1#1-1", focus["cross_volume_same_text_ids"])
        self.assertEqual(volume_key("text_cwwl", rows[0]), "cwwl_1994-1997-2")
        self.assertEqual(text_hash("A A"), text_hash("AA"))


class TestCheckSourceVsEsOffline(unittest.TestCase):
    def test_volume_of_and_dup_attribution(self):
        from tools.check_source_vs_es import text_hash, volume_of

        self.assertEqual(volume_of("text_cwwl", "cwwl_1994-1997-2-1#1-10"), "cwwl_1994-1997-2")
        self.assertEqual(volume_of("text_cwwl", "cwwl_1998-1-3#1-2"), "cwwl_1998-1")
        self.assertEqual(volume_of("text_life", "life_49-1-3"), "life_49-1")
        h = text_hash("hello")
        es_ids = {"a", "b"}
        id_hash = {"a": h, "b": "other", "c": h, "d": "solo"}
        # c 缺失但哈希已在 ES 已有 id 的源哈希中 → 重复型；d 独有型
        missing = {"c", "d"}
        present_hashes = {id_hash[i] for i in es_ids if i in id_hash}
        dup = sum(1 for i in missing if id_hash[i] in present_hashes)
        uniq = sum(1 for i in missing if id_hash[i] not in present_hashes)
        self.assertEqual(dup, 1)
        self.assertEqual(uniq, 1)


if __name__ == "__main__":
    unittest.main()
