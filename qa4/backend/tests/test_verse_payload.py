# -*- coding: utf-8 -*-
"""verse_data 载荷：约三16 / 范围 / 整章。"""

from __future__ import annotations

import unittest
from pathlib import Path

from scripture.bible_text import BibleText
from scripture.normalize import KIND_CHAPTER, KIND_VERSE, Ref, parse_refs
from scripture.verse_payload import build_verse_data

_BIBLE = Path(__file__).resolve().parents[2] / "data" / "bible_data"


@unittest.skipUnless(_BIBLE.is_dir() and (_BIBLE / "43_john.json").is_file(), "需要 qa4/data/bible_data")
class TestVersePayload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bible = BibleText(_BIBLE)

    def test_single_verse_john_316(self):
        refs = parse_refs("约三16", bible=self.bible, validate=True)
        self.assertTrue(refs)
        data = build_verse_data(bible=self.bible, refs=refs)
        self.assertIsInstance(data, dict)
        self.assertNotIn("verses", data)
        self.assertEqual(int(data.get("book") or 0), 43)
        self.assertEqual(int(data.get("chapter") or 0), 3)
        self.assertEqual(int(data.get("verse") or 0), 16)
        self.assertTrue(data.get("text_gb") or data.get("text_gb_plain"))
        self.assertIsInstance(data.get("footnotes"), list)
        self.assertIsInstance(data.get("crossrefs"), list)

    def test_range_payload(self):
        refs = [
            Ref(
                book="约",
                book_no=43,
                chapter=3,
                v_start=16,
                v_end=17,
                kind=KIND_VERSE,
            )
        ]
        data = build_verse_data(bible=self.bible, refs=refs)
        self.assertIn("verses", data)
        self.assertEqual(data.get("query_type"), "range")
        self.assertEqual(len(data["verses"]), 2)

    def test_chapter_payload(self):
        refs = [
            Ref(
                book="约",
                book_no=43,
                chapter=3,
                v_start=0,
                v_end=0,
                kind=KIND_CHAPTER,
            )
        ]
        data = build_verse_data(bible=self.bible, refs=refs)
        self.assertIn("verses", data)
        self.assertEqual(data.get("query_type"), "chapter")
        self.assertGreater(len(data["verses"]), 10)
        self.assertTrue(all(v.get("book") == 43 for v in data["verses"]))


if __name__ == "__main__":
    unittest.main()
