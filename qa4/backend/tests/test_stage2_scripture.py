# -*- coding: utf-8 -*-
"""阶段 2：取经文、经节规范化、诗篇开关、3a 读经行现状（离线）。"""

from __future__ import annotations

import hashlib
import unittest

from _helpers import BIBLE_DIR, bible, fixture

from scripture.normalize import (
    KIND_CHAPTER,
    KIND_CROSS,
    KIND_VERSE,
    Ref,
    expand_verses,
    heuristic_miss,
    overlaps,
    parse_refs,
    reading_line_of,
    ref_in_bible,
)

HAS_BIBLE = BIBLE_DIR.is_dir()


@unittest.skipUnless(HAS_BIBLE, "qa4/data/bible_data 未就绪")
class TestBibleText(unittest.TestCase):
    def test_totals_1189_31103(self):
        t = bible().totals()
        self.assertEqual(t["books"], 66)
        self.assertEqual(t["chapters"], 1189)
        self.assertEqual(t["verses"], 31103)

    def test_known_verses_from_data(self):
        # (卷, 章, 节, 数据里的 ref_gb, text_gb_plain 的 sha256 前 8 位) — 取自本机 bible_data
        samples = [
            (1, 1, 1, "创一1", "de787b91"),
            (19, 3, 1, "诗三1", "683e4d3b"),
            (43, 3, 16, "约三16", "1544b45f"),
            (45, 8, 28, "罗八28", "61c9cc58"),
            (66, 22, 21, "启二二21", "3fd68d6d"),
        ]
        for bk, c, v, ref_gb, sha8 in samples:
            row = bible().get_verse(bk, c, v)
            self.assertIsNotNone(row, (bk, c, v))
            self.assertEqual(row["ref_gb"], ref_gb)
            self.assertEqual(hashlib.sha256(row["text_gb_plain"].encode("utf-8")).hexdigest()[:8], sha8)

    def test_range_chapter_cross_sorted(self):
        b = bible()
        rng = b.get_range(45, 8, 30, 28)
        self.assertEqual([r["verse"] for r in rng], [28, 29, 30])
        ch = b.get_chapter(19, 23)
        self.assertEqual([r["verse"] for r in ch], list(range(1, len(ch) + 1)))
        cross = b.get_cross(45, 1, 31, 2, 2)
        self.assertEqual([(r["chapter"], r["verse"]) for r in cross], [(1, 31), (1, 32), (2, 1), (2, 2)])
        self.assertIsNone(b.get_verse(64, 1, 99))

    def test_footnotes_present(self):
        self.assertGreater(len(bible().footnotes(43, 3, 16)), 0)


@unittest.skipUnless(HAS_BIBLE, "qa4/data/bible_data 未就绪")
class TestNormalize(unittest.TestCase):
    def test_basic_kinds_and_keys(self):
        refs = parse_refs("约三16，十4", bible=bible())
        self.assertEqual([r.label() for r in refs], ["约3:16", "约10:4"])
        self.assertTrue(all(r.kind == KIND_VERSE for r in refs))
        self.assertEqual(refs[0].key(), (43, 3, 16, 3, 16))
        whole = parse_refs("诗篇二十三篇", bible=bible())
        self.assertEqual(whole[0].kind, KIND_CHAPTER)
        self.assertEqual(whole[0].key(), (19, 23, 0, 23, 0))
        cross = parse_refs("罗一章三节至二章五节", bible=bible())
        self.assertEqual(cross[0].kind, KIND_CROSS)
        self.assertEqual(cross[0].key(), (45, 1, 3, 2, 5))

    def test_whole_line_inherits_book(self):
        # 整行解析：逗号后的「十4」继承「约」；先切开就丢书名
        line = "约三16，十4"
        whole = parse_refs(line, bible=bible())
        split = [r for part in line.split("，") for r in parse_refs(part, bible=bible())]
        self.assertEqual(len(whole), 2)
        self.assertLess(len(split), len(whole))

    def test_overlaps(self):
        a = Ref("罗", 45, 8, 28, 30, KIND_VERSE)
        b = Ref("罗", 45, 8, 30, 32, KIND_VERSE)
        c = Ref("罗", 45, 8, 31, 32, KIND_VERSE)
        whole = Ref("罗", 45, 8, 0, 0, KIND_CHAPTER)
        other = Ref("约", 43, 8, 28, 30, KIND_VERSE)
        cross = Ref("罗", 45, 7, 20, 1, KIND_CROSS, chapter_end=8)
        self.assertTrue(overlaps(a, b))
        self.assertFalse(overlaps(a, c))
        self.assertTrue(overlaps(whole, c))
        self.assertFalse(overlaps(a, other))
        self.assertTrue(overlaps(cross, Ref("罗", 45, 8, 1, 1, KIND_VERSE)))
        self.assertFalse(overlaps(cross, Ref("罗", 45, 8, 2, 2, KIND_VERSE)))

    def test_expand_only_when_asked(self):
        r = parse_refs("林前十三4~7", bible=bible())[0]
        self.assertEqual((r.v_start, r.v_end), (4, 7))
        self.assertEqual(expand_verses(r, 10), [(46, 13, v) for v in range(4, 8)])
        self.assertEqual(len(expand_verses(r, 2)), 2)
        whole = parse_refs("诗篇二十三篇", bible=bible())[0]
        self.assertEqual(len(expand_verses(whole, 100, bible=bible())), bible().verse_count(19, 23))

    def test_psalm_title_switch(self):
        for s in fixture("psalm_title_samples.json")["samples"]:
            on = parse_refs(s["raw"], bible=bible(), psalm_title=True)
            self.assertEqual(len(on), 1, s["raw"])
            self.assertEqual((on[0].book, on[0].chapter, on[0].v_start, on[0].v_end), ("诗", s["chapter"], 1, s["v_end"]))
            self.assertIn("含标题", on[0].flags)
            off = parse_refs(s["raw"], bible=bible(), psalm_title=False)
            self.assertEqual(off, [], s["raw"])

    def test_counts_whole_and_cross_separately(self):
        refs = parse_refs("诗篇二十三篇，罗一章三节至二章五节，约三16", bible=bible())
        kinds = [r.kind for r in refs]
        self.assertEqual(kinds.count(KIND_CHAPTER), 1)
        self.assertEqual(kinds.count(KIND_CROSS), 1)
        self.assertEqual(kinds.count(KIND_VERSE), 1)
        self.assertTrue(all(ref_in_bible(r, bible()) for r in refs))


@unittest.skipUnless(HAS_BIBLE, "qa4/data/bible_data 未就绪")
class TestReadingLineFixtures(unittest.TestCase):
    """断言现状：normalize v2 后零出处 1 行；疑似遗漏 22 行（见 scripture_normalize_v2_notes.md）。"""

    def test_zero_lines_current_state(self):
        rows = fixture("reading_lines_zero.json")
        self.assertEqual(len(rows), 1)
        for r in rows:
            self.assertEqual(parse_refs(r["line"], bible=bible()), [], r["title"])

    def test_miss_lines_current_state(self):
        rows = fixture("reading_lines_miss.json")
        self.assertEqual(len(rows), 22)
        for r in rows:
            refs = parse_refs(r["line"], bible=bible())
            self.assertEqual(len(refs), r["n_refs"], r["title"])
            self.assertTrue(heuristic_miss(r["line"], len(refs)), r["title"])

    def test_reading_line_prefix(self):
        self.assertEqual(reading_line_of("读经：约三16\n壹　…"), "约三16")
        self.assertIsNone(reading_line_of("壹　没有读经行"))


if __name__ == "__main__":
    unittest.main()
