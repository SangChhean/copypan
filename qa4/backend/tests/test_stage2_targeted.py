# -*- coding: utf-8 -*-
"""阶段 2：定向取篇（完整性数据驱动；节期按篇；诗歌 series；0/1 起始）。"""

from __future__ import annotations

import asyncio
import unittest

from _helpers import BIBLE_DIR, bible, quiet

from retrieval.fake import FakeRetrievalService, FakeSearchES, load_fixture
from retrieval.targeted import (
    INCOMPLETE,
    NOT_FOUND,
    NOT_SUPPORTED,
    OK,
    UNKNOWN_TOTAL,
    TargetedFetcher,
    analyze_orders,
)
from scripture.normalize import parse_refs

quiet("qa4.retrieval")


def _outline(indices, total, bt="甲书生命读经", mn=3):
    return [
        {
            "_id": f"ol-{i}",
            "book_title": bt,
            "message_number": mn,
            "chunk_index": i,
            "chunk_total": total,
            "text": f"纲目段{i}",
        }
        for i in indices
    ]


def _life(ns, bt="甲书生命读经", mn=3):
    return [
        {"_id": f"life_9-{mn}-{i}", "chunk_id": f"life_9-{mn}-{i}", "book_title": bt, "message_number": mn, "text": f"正文段{i}"}
        for i in ns
    ]


class TestAnalyzeOrders(unittest.TestCase):
    def test_base1_complete(self):
        info = analyze_orders([1, 2, 3], expected_total=3, orders_base=1, hits_total=3, fetched=3, has_total_field=True)
        self.assertEqual(info["status"], OK)
        self.assertTrue(info["orders_contiguous"])
        self.assertEqual(info["missing_orders"], [])

    def test_base0_complete(self):
        info = analyze_orders([0, 1, 2], expected_total=3, orders_base=0, hits_total=3, fetched=3, has_total_field=True)
        self.assertEqual(info["status"], OK)
        self.assertEqual(info["orders_base"], 0)

    def test_missing_one(self):
        info = analyze_orders([1, 3], expected_total=3, orders_base=1, hits_total=2, fetched=2, has_total_field=True)
        self.assertEqual(info["status"], INCOMPLETE)
        self.assertEqual(info["missing_orders"], [2])
        self.assertFalse(info["orders_contiguous"])

    def test_extra_and_dup(self):
        info = analyze_orders([1, 2, 2, 9], expected_total=3, orders_base=1, hits_total=4, fetched=4, has_total_field=True)
        self.assertEqual(info["status"], INCOMPLETE)
        self.assertIn(9, info["extra_orders"])
        self.assertIn(2, info["duplicate_orders"])

    def test_text_no_total_gaps_are_unknown(self):
        info = analyze_orders([1, 2, 10], expected_total=None, orders_base=0, hits_total=3, fetched=3, has_total_field=False)
        self.assertEqual(info["status"], UNKNOWN_TOTAL)
        self.assertEqual(info["missing_orders"], [])

    def test_text_truncated_incomplete(self):
        info = analyze_orders([1, 2], expected_total=None, orders_base=0, hits_total=7, fetched=2, has_total_field=False)
        self.assertEqual(info["status"], INCOMPLETE)


class TestLifeStudy(unittest.TestCase):
    def test_shuffled_input_sorted_output_base1(self):
        # 纲目 1..5；正文有洞但不报 incomplete
        es = FakeSearchES(
            {"outline_12490": _outline([5, 1, 3, 2, 4], 5), "text_life": _life([1, 2, 3, 10, 11])},
            shuffle_seed=7,
        )
        r = asyncio.run(TargetedFetcher(es).life_study("甲书生命读经", 3))
        self.assertEqual(r.status, UNKNOWN_TOTAL)  # text 无 total → 整体取最差
        ol = [b["order"] for b in r.blocks if b["index"] == "outline_12490"]
        lf = [b["order"] for b in r.blocks if b["index"] == "text_life"]
        self.assertEqual(ol, [1, 2, 3, 4, 5])
        self.assertEqual(lf, [1, 2, 3, 10, 11])
        p_ol = r.meta["parts"]["outline_12490"]
        self.assertEqual(p_ol["status"], OK)
        self.assertEqual(p_ol["orders_base"], 1)
        self.assertEqual(p_ol["expected_total"], 5)
        self.assertTrue(p_ol["orders_contiguous"])
        p_lf = r.meta["parts"]["text_life"]
        self.assertEqual(p_lf["status"], UNKNOWN_TOTAL)
        self.assertIsNone(p_lf["expected_total"])

    def test_missing_one_outline_chunk_incomplete(self):
        docs = _outline([1, 2, 4, 5], 5)  # 缺 3
        es = FakeSearchES({"outline_12490": docs, "text_life": _life([1])})
        r = asyncio.run(TargetedFetcher(es).life_study("甲书生命读经", 3))
        self.assertEqual(r.status, INCOMPLETE)
        self.assertEqual(r.meta["parts"]["outline_12490"]["missing_orders"], [3])
        self.assertFalse(r.meta["parts"]["outline_12490"]["orders_contiguous"])

    def test_base0_outline_via_cfg(self):
        cfg = {
            "indices": {
                "outline_12490": {
                    "text_field": "text",
                    "order_base": 0,
                    "fields": {
                        "order": {"name": "chunk_index"},
                        "total": {"name": "chunk_total"},
                        "message_number": {"name": "message_number"},
                    },
                    "filters": {"book_title": {"name": "book_title"}},
                },
                "text_life": {
                    "text_field": "text",
                    "fields": {
                        "order": {"name": "chunk_id", "derive": "trailing_int"},
                        "message_number": {"name": "message_number"},
                    },
                    "filters": {"book_title": {"name": "book_title"}},
                },
            },
            "params": {"targeted_max_size": 2000},
        }
        es = FakeSearchES({"outline_12490": _outline([0, 1, 2], 3), "text_life": _life([1])})
        r = asyncio.run(TargetedFetcher(es, cfg=cfg).life_study("甲书生命读经", 3))
        self.assertEqual(r.meta["parts"]["outline_12490"]["status"], OK)
        self.assertEqual(r.meta["parts"]["outline_12490"]["orders_base"], 0)

    def test_truncated_by_size_incomplete(self):
        es = FakeSearchES({"text_life": _life(range(1, 8))})
        f = TargetedFetcher(es)
        f.max_size = 3
        r = asyncio.run(f.life_study("甲书生命读经", 3))
        self.assertEqual(r.status, INCOMPLETE)
        self.assertEqual(r.meta["parts"]["text_life"]["hits_total"], 7)

    def test_duplicate_text_orders_incomplete(self):
        docs = _life([1, 2, 2, 3])
        es = FakeSearchES({"text_life": docs})
        r = asyncio.run(TargetedFetcher(es).life_study("甲书生命读经", 3))
        self.assertEqual(r.status, INCOMPLETE)
        self.assertIn(2, r.meta["parts"]["text_life"]["duplicate_orders"])

    def test_not_found(self):
        r = asyncio.run(TargetedFetcher(FakeSearchES({})).life_study("无此书", 1))
        self.assertEqual(r.status, NOT_FOUND)
        self.assertIn("无此书", r.meta["missing"])


class TestFeastAndHymn(unittest.TestCase):
    feasts = [
        {"year": 1997, "month_code": "06", "name": "1997年示例特会"},
        {"year": 1997, "month_code": "08", "name": "1997年示例全时间"},
    ]

    def test_feast_multi_message_grouped_base1(self):
        # 两篇各 1..2；混排输入；不得把两篇序号拼成一条序列
        docs = []
        for m in (2, 1):
            for i in (2, 1):
                docs.append(
                    {
                        "_id": f"f{m}-{i}",
                        "book_title": "1997年示例特会",
                        "message_number": m,
                        "chunk_index": i,
                        "chunk_total": 2,
                        "text": "x",
                    }
                )
        es = FakeSearchES({"outline_feasts": docs}, shuffle_seed=5)
        r = asyncio.run(TargetedFetcher(es, feasts=self.feasts).feast(1997, "6"))
        self.assertEqual(r.status, OK)
        self.assertEqual([(b["message_number"], b["order"]) for b in r.blocks], [(1, 1), (1, 2), (2, 1), (2, 2)])
        self.assertEqual(r.meta["messages"]["1"]["missing_orders"], [])
        self.assertEqual(r.meta["messages"]["2"]["status"], OK)
        self.assertTrue(r.meta["messages"]["1"]["orders_contiguous"])

    def test_feast_one_message_missing_chunk(self):
        docs = [
            {"_id": "a", "book_title": "1997年示例特会", "message_number": 1, "chunk_index": 1, "chunk_total": 3, "text": "x"},
            {"_id": "b", "book_title": "1997年示例特会", "message_number": 1, "chunk_index": 3, "chunk_total": 3, "text": "x"},
            {"_id": "c", "book_title": "1997年示例特会", "message_number": 2, "chunk_index": 1, "chunk_total": 1, "text": "x"},
        ]
        es = FakeSearchES({"outline_feasts": docs})
        r = asyncio.run(TargetedFetcher(es, feasts=self.feasts).feast(1997, "06"))
        self.assertEqual(r.status, INCOMPLETE)
        self.assertEqual(r.meta["messages"]["1"]["missing_orders"], [2])
        self.assertEqual(r.meta["messages"]["2"]["status"], OK)

    def test_feast_with_message_number_only_that_msg(self):
        docs = [
            {"_id": f"f{m}-{i}", "book_title": "1997年示例特会", "message_number": m, "chunk_index": i, "chunk_total": 1, "text": "x"}
            for m in (1, 2)
            for i in (1,)
        ]
        es = FakeSearchES({"outline_feasts": docs})
        r = asyncio.run(TargetedFetcher(es, feasts=self.feasts).feast(1997, "06", message_number=2))
        self.assertEqual(r.status, OK)
        self.assertEqual([b["message_number"] for b in r.blocks], [2])

    def test_feast_not_in_table_or_index(self):
        f = TargetedFetcher(FakeSearchES({}), feasts=self.feasts)
        r1 = asyncio.run(f.feast(1998, "01"))
        self.assertEqual(r1.status, NOT_FOUND)
        self.assertIn("1998", r1.meta["missing"])
        r2 = asyncio.run(f.feast(1997, "06", message_number=9))
        self.assertEqual(r2.status, NOT_FOUND)
        self.assertIn("第9篇", r2.meta["missing"])

    def test_hymn_full_default_series(self):
        hymns = [p for p in load_fixture() if p["_logical"] == "hymns"]
        es = FakeSearchES({"hymns": hymns}, shuffle_seed=3)
        r = asyncio.run(TargetedFetcher(es).hymn(1))
        self.assertEqual(r.status, OK)
        self.assertEqual(len(r.blocks), 1)
        self.assertEqual(r.meta["series"], "诗歌")
        self.assertIn("第一首全文", r.blocks[0]["text"])
        rb = asyncio.run(TargetedFetcher(es).hymn(1, series="补充本诗歌"))
        self.assertIn("补充本", rb.blocks[0]["text"])
        self.assertEqual(asyncio.run(TargetedFetcher(es).hymn(999)).status, NOT_FOUND)

    def test_hymn_overlap_number_series_disambiguates(self):
        """同一号码两 series：默认大本；显式补充本。"""
        docs = [
            {
                "_id": "h-daben",
                "series": "诗歌",
                "hymn_number": 42,
                "chunk_index": 0,
                "chunk_total": 1,
                "unit_type": "full",
                "text": "大本42全文占位",
            },
            {
                "_id": "h-buchong",
                "series": "补充本诗歌",
                "hymn_number": 42,
                "chunk_index": 0,
                "chunk_total": 1,
                "unit_type": "full",
                "text": "补充本42全文占位",
            },
        ]
        es = FakeSearchES({"hymns": docs})
        rd = asyncio.run(TargetedFetcher(es).hymn(42))
        self.assertEqual(rd.status, OK)
        self.assertEqual(rd.meta["series"], "诗歌")
        self.assertIn("大本42", rd.blocks[0]["text"])
        rb = asyncio.run(TargetedFetcher(es).hymn(42, series="补充本诗歌"))
        self.assertIn("补充本42", rb.blocks[0]["text"])


@unittest.skipUnless(BIBLE_DIR.is_dir(), "bible_data 未就绪")
class TestScriptureAndNotes(unittest.TestCase):
    def test_scripture_ranges_and_whole_chapter(self):
        f = TargetedFetcher(None, bible=bible())
        r = asyncio.run(f.scripture(parse_refs("诗篇二十三篇，罗八30～28", bible=bible())))
        self.assertEqual(r.status, OK)
        orders = [b["order"] for b in r.blocks]
        self.assertEqual(len(r.blocks), bible().verse_count(19, 23) + 3)
        self.assertEqual(orders[: bible().verse_count(19, 23)], sorted(orders[: bible().verse_count(19, 23)]))

    def test_footnotes_by_verse(self):
        f = TargetedFetcher(None, bible=bible())
        r = f.footnotes_for(parse_refs("约三16", bible=bible())[0])
        self.assertEqual(r.status, OK)
        self.assertEqual([b["order"] for b in r.blocks], sorted(b["order"] for b in r.blocks))
        self.assertEqual(f.footnotes_for(parse_refs("诗篇二十三篇", bible=bible())[0]).status, NOT_SUPPORTED)

    def test_notes_by_topic_coverage_note(self):
        f = TargetedFetcher(None, retrieval=FakeRetrievalService.from_default_fixture())
        r = asyncio.run(f.notes_by_topic("神的爱"))
        self.assertEqual(r.status, OK)
        self.assertIn("48%", r.meta["coverage_note"])
        self.assertTrue(all(b["index"] == "map_note" for b in r.blocks))


if __name__ == "__main__":
    unittest.main()
