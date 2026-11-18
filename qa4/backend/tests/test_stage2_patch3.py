# -*- coding: utf-8 -*-
"""阶段 2/3 补丁三：断档工具、〇 预处理、辩理 live、过滤与软优先（假 ES/Neo4j）。"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from _helpers import BIBLE_DIR, bible, quiet

from core.embedding_client import FakeEmbeddingClient
from core.neo4j_client import FakeNeo4jClient
from core.rerank_client import FakeRerankClient
from lookups.year_table import YearTable
from pipeline.deps import DevineProvider, _devine_content_key
from retrieval.fake import FakeSearchES
from retrieval.service import RetrievalService
from retrieval.targeted import UNKNOWN_TOTAL, TargetedFetcher, analyze_orders
from retrieval.text_source import chunk_ids_for_message, resolve_jsonl_paths
from retrieval.types import SubQuestionSpec
from scripture.normalize import parse_refs, preprocess_ref_text
from tools.check_text_life_gaps import analyze_index

quiet("qa4")


class TestGapTool(unittest.TestCase):
    def test_analyze_gaps_merge_and_absent(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.jsonl"
            rows = [
                {"chunk_id": "life_1-1-2", "message_key": "life_1-1", "text": "a", "original_ids": ["life_1-1-2"]},
                {"chunk_id": "life_1-1-5", "message_key": "life_1-1", "text": "b", "original_ids": ["life_1-1-5", "life_1-1-6"]},
                {"chunk_id": "life_1-1-8", "message_key": "life_1-1", "text": "c", "original_ids": ["life_1-1-8"]},
            ]
            p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            rep = analyze_index([p], "text_life", ("life_1-1",))
            s = rep["samples"]["life_1-1"]
            self.assertEqual(s["fetched"], 3)
            self.assertIn(6, s["gaps_in_original_ids"])
            self.assertIn(3, s["gaps_absent_from_source"])
            self.assertIn(4, s["gaps_absent_from_source"])
            self.assertIn(7, s["gaps_absent_from_source"])

    def test_chunk_ids_for_message(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "shards"
            root.mkdir()
            (root / "x.jsonl").write_text(
                json.dumps({"chunk_id": "life_49-1-2", "message_key": "life_49-1", "book_title": "以弗所书生命读经", "message_number": 1})
                + "\n"
                + json.dumps({"chunk_id": "life_49-1-5", "message_key": "life_49-1", "book_title": "以弗所书生命读经", "message_number": 1})
                + "\n",
                encoding="utf-8",
            )
            paths = resolve_jsonl_paths(Path(td))
            ids = chunk_ids_for_message(paths, message_key="life_49-1")
            self.assertEqual(ids, {"life_49-1-2", "life_49-1-5"})


class TestShiLingPreprocess(unittest.TestCase):
    def test_preprocess_only_shi_ling_digit(self):
        self.assertEqual(preprocess_ref_text("诗十〇二14"), "诗一〇二14")
        self.assertEqual(preprocess_ref_text("诗一〇二14"), "诗一〇二14")
        self.assertEqual(preprocess_ref_text("诗二十三"), "诗二十三")
        self.assertEqual(preprocess_ref_text("诗一百〇二"), "诗一百〇二")

    @unittest.skipUnless(BIBLE_DIR.is_dir(), "bible_data 未就绪")
    def test_parse_shi_ling_via_wrapper(self):
        refs = parse_refs("诗十〇二14", bible=bible())
        self.assertTrue(refs)
        self.assertEqual(refs[0].book_no, 19)
        self.assertEqual(refs[0].chapter, 102)
        self.assertEqual(refs[0].v_start, 14)
        # 正常写法不受影响
        self.assertTrue(parse_refs("诗一〇二14", bible=bible()))
        self.assertTrue(parse_refs("诗二十三1", bible=bible()))


class TestTextLifeUnknownTotal(unittest.TestCase):
    def test_gaps_unknown_not_incomplete(self):
        info = analyze_orders([2, 5, 6, 7], expected_total=None, orders_base=0, hits_total=4, fetched=4, has_total_field=False)
        self.assertEqual(info["status"], UNKNOWN_TOTAL)
        self.assertFalse(info["possibly_incomplete"])


class TestDevineProvider(unittest.TestCase):
    def test_dedupe_and_cap_fake_items(self):
        items = [
            {"term": "甲", "content": "同一份辩理"},
            {"term": "乙", "content": "同一份辩理"},
            {"term": "丙", "content": "另一份"},
        ]
        p = DevineProvider(items, max_items=2)
        out = p.fetch(["甲", "乙", "丙"])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["content"], "同一份辩理")
        self.assertIn("甲", out[0]["terms"])
        self.assertIn("乙", out[0]["terms"])

    def test_live_neo4j_json_string_and_same_as(self):
        blob = json.dumps({"title": "题", "description": "说", "outline": "纲"}, ensure_ascii=False)
        neo = FakeNeo4jClient(devine_by_name={"外词": blob, "独词": json.dumps({"title": "别", "description": "", "outline": "x"}, ensure_ascii=False)})
        p = DevineProvider(None, neo4j=neo, same_as={"括号词": "外词"}, max_items=2)
        out = p.fetch(["括号词", "独词", "无"])
        self.assertEqual(len(out), 2)
        self.assertIn("括号词", out[0]["terms"])
        empty = p.fetch(["无"])
        self.assertEqual(empty, [])

    def test_content_key_strip(self):
        k1, _ = _devine_content_key('{"title":"A","description":"","outline":"x"}')
        k2, _ = _devine_content_key('  {"title":"A","description":"","outline":"x"}  ')
        self.assertEqual(k1, k2)


class TestAuthorYearSoft(unittest.TestCase):
    def _svc(self, docs):
        es = FakeSearchES(docs)
        yt = YearTable(
            [
                {"year_mark": "1985", "text_cwwl_book_titles": ["文集一九八五年第一册"]},
                {"year_mark": "1990", "text_cwwl_book_titles": ["文集一九九〇年第一册"]},
            ]
        )
        return RetrievalService(es, FakeEmbeddingClient(), FakeRerankClient(), year_table=yt), es

    def test_ni_author_filter_in_bodies(self):
        docs = {
            "text_cwwn": [{"_id": "1", "author": "倪柝声", "book_title": "倪册", "text": "爱"}],
            "text_cwwl": [{"_id": "2", "author": "李常受", "book_title": "李册", "text": "爱"}],
        }
        svc, es = self._svc(docs)
        asyncio.run(svc.retrieve(SubQuestionSpec(query="爱", author="倪柝声")))
        searched = {ix for ix, _ in es.bodies}
        self.assertIn("qa4_text_cwwn", searched)
        self.assertNotIn("qa4_text_cwwl", searched)

    def test_conflict_none_flag(self):
        svc, es = self._svc({})
        r = asyncio.run(svc.retrieve(SubQuestionSpec(query="q", author="倪柝声", year_range=(1985, 1990))))
        self.assertEqual(r.none_flag, "职事信息里没有")
        self.assertEqual(es.bodies, [])


if __name__ == "__main__":
    unittest.main()
