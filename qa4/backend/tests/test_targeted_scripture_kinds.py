# -*- coding: utf-8 -*-
"""targeted.scripture：whole_book / chapter_range / 截断 / not_found（离线 bible_data）。"""

from __future__ import annotations

import asyncio
import unittest

from _helpers import BIBLE_DIR, bible, quiet

from retrieval.dedupe import map_note_key
from retrieval.targeted import NOT_FOUND, OK, TargetedFetcher, book_verse_total
from scripture.normalize import (
    KIND_BOOK,
    KIND_CHAPTER,
    KIND_CHAPTER_RANGE,
    KIND_CROSS,
    KIND_VERSE,
    Ref,
    parse_refs,
)

quiet("qa4.retrieval")


def _run(refs):
    return asyncio.run(TargetedFetcher(None, bible=bible()).scripture(refs))


@unittest.skipUnless(BIBLE_DIR.is_dir(), "bible_data 未就绪")
class TestTargetedScriptureKinds(unittest.TestCase):
    def test_verse_range_positive(self):
        refs = parse_refs("约3:16", bible=bible())
        self.assertEqual(refs[0].kind, KIND_VERSE)
        r = _run(refs)
        self.assertEqual(r.status, OK)
        self.assertEqual(len(r.blocks), 1)
        self.assertEqual(set(r.blocks[0]), {"index", "order", "ref", "book_title", "text", "flags"})

    def test_whole_chapter_positive(self):
        refs = parse_refs("诗篇二十三篇", bible=bible())
        self.assertEqual(refs[0].kind, KIND_CHAPTER)
        r = _run(refs)
        self.assertEqual(r.status, OK)
        self.assertEqual(len(r.blocks), bible().verse_count(19, 23))

    def test_cross_chapter_positive_short(self):
        refs = parse_refs("创1:1-2:3", bible=bible())
        self.assertEqual(refs[0].kind, KIND_CROSS)
        r = _run(refs)
        self.assertEqual(r.status, OK)
        self.assertGreater(len(r.blocks), 1)
        self.assertNotIn("truncated", r.meta)

    def test_chapter_range_gen_1_3_order(self):
        refs = parse_refs("创一至三章", bible=bible())
        self.assertEqual(refs[0].kind, KIND_CHAPTER_RANGE)
        r = _run(refs)
        self.assertEqual(r.status, OK)
        self.assertEqual(r.meta.get("kind"), KIND_CHAPTER_RANGE)
        self.assertEqual(r.meta.get("requested_chapters"), 3)
        self.assertEqual(r.meta.get("returned_chapters"), 3)
        self.assertNotIn("truncated", r.meta)
        chapters = [b["order"] // 1000 for b in r.blocks]
        self.assertEqual(sorted(set(chapters)), [1, 2, 3])
        self.assertEqual(chapters, sorted(chapters))
        want = sum(bible().verse_count(1, c) for c in (1, 2, 3))
        self.assertEqual(len(r.blocks), want)

    def test_chapter_range_psalm_1_10_no_truncate(self):
        refs = parse_refs("诗1至10章", bible=bible())
        r = _run(refs)
        self.assertEqual(r.status, OK)
        self.assertEqual(r.meta.get("requested_chapters"), 10)
        self.assertEqual(r.meta.get("returned_chapters"), 10)
        self.assertNotIn("truncated", r.meta)
        self.assertEqual(sorted({b["order"] // 1000 for b in r.blocks}), list(range(1, 11)))

    def test_chapter_range_psalm_1_12_truncated(self):
        refs = parse_refs("诗1至12章", bible=bible())
        r = _run(refs)
        self.assertEqual(r.status, OK)
        self.assertTrue(r.meta.get("truncated"))
        self.assertEqual(r.meta.get("requested_chapters"), 12)
        self.assertEqual(r.meta.get("returned_chapters"), 10)
        self.assertEqual(sorted({b["order"] // 1000 for b in r.blocks}), list(range(1, 11)))

    def test_cross_acts_truncated_200(self):
        refs = parse_refs("徒2:1-12:25", bible=bible())
        self.assertEqual(refs[0].kind, KIND_CROSS)
        full = len(bible().get_cross(44, 2, 1, 12, 25))
        self.assertGreater(full, 200)
        r = _run(refs)
        self.assertEqual(r.status, OK)
        self.assertTrue(r.meta.get("truncated"))
        self.assertEqual(r.meta.get("returned_verses"), 200)
        self.assertEqual(r.meta.get("requested_verses"), full)
        self.assertEqual(len(r.blocks), 200)

    def test_whole_book_romans(self):
        refs = parse_refs("罗马书", bible=bible())
        self.assertEqual(refs[0].kind, KIND_BOOK)
        r = _run(refs)
        self.assertEqual(r.status, OK)
        self.assertEqual(r.meta.get("kind"), KIND_BOOK)
        self.assertEqual(r.meta.get("chapter_count"), 16)
        self.assertEqual(r.meta.get("verse_count"), book_verse_total(bible(), 45))
        self.assertEqual(r.meta.get("verse_count"), 433)
        overview = [b for b in r.blocks if b.get("unit") == "book_overview"]
        self.assertEqual(len(overview), 1)
        self.assertEqual(overview[0]["chapter_count"], 16)
        self.assertEqual(overview[0]["verse_count"], 433)
        self.assertEqual(overview[0]["text"], "")
        # 无 ES 时不带 outline
        self.assertFalse(r.meta.get("has_outline"))
        self.assertTrue(all(b.get("chunk_type") != "book_outline" for b in r.blocks))

    def test_not_found_gen_51(self):
        ref = Ref(book="创", book_no=1, chapter=51, v_start=0, v_end=0, kind=KIND_CHAPTER, raw="创51")
        r = _run([ref])
        self.assertEqual(r.status, NOT_FOUND)
        self.assertFalse(r.blocks)
        self.assertIn("reason", r.meta)

    def test_not_found_gen_3_to_1(self):
        ref = Ref(
            book="创",
            book_no=1,
            chapter=3,
            v_start=0,
            v_end=0,
            kind=KIND_CHAPTER_RANGE,
            chapter_end=1,
            raw="创3-1",
        )
        r = _run([ref])
        self.assertEqual(r.status, NOT_FOUND)
        self.assertFalse(r.blocks)
        self.assertIn("止章小于起章", r.meta.get("reason", ""))

    def test_map_note_key_rejects_new_kinds(self):
        self.assertIsNone(map_note_key("（恢复本圣经，罗马书，注1）", bible=bible()))
        self.assertIsNone(map_note_key("（恢复本圣经，创一至三章，注1）", bible=bible()))
        # 既有节引用仍可用
        self.assertEqual(map_note_key("（恢复本圣经，可十四24，注1）"), (41, 14, 24, 14, 24, 1))


if __name__ == "__main__":
    unittest.main()
