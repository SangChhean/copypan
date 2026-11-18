# -*- coding: utf-8 -*-
"""阶段 2：RRF、查询体硬过滤、软优先、去重、放宽重试、冲突标志、精排降级（离线）。"""

from __future__ import annotations

import asyncio
import unittest

from _helpers import quiet

from core.embedding_client import FakeEmbeddingClient
from core.rerank_client import FakeRerankClient
from lookups.year_table import YearTable
from retrieval.dedupe import dedupe, map_note_key
from retrieval.es_search import build_bm25_body, build_knn_body
from retrieval.fake import FakeSearchES
from retrieval.fusion import rrf
from retrieval.scope import NONE_FLAG, decide_scope
from retrieval.service import RetrievalService
from retrieval.types import SubQuestionSpec

quiet("qa4.retrieval", "qa4.rerank", "qa4.embed")


def _doc(lg, i, **kw):
    d = {"_id": f"{lg}-{i}", "chunk_id": f"{lg}-{i}", "text": f"占位文字 {lg} {i}", "book_title": f"书{lg}", "message_number": i}
    d.update(kw)
    return d


def _yt():
    return YearTable(
        [
            {"year_mark": "1985", "text_cwwl_book_titles": ["文集一九八五年第一册"]},
            {"year_mark": "1991–92", "text_cwwl_book_titles": ["文集一九九一至一九九二年第一册"]},
            {"year_mark": "1994–97", "text_cwwl_book_titles": ["文集一九九四至一九九七年第一册"]},
        ],
        no_year_titles={"文集信函与拾遗第一册"},
    )


class TestRRF(unittest.TestCase):
    def test_hand_computed(self):
        A, B, C = ({"_logical": "x", "_id": n} for n in "ABC")
        out = rrf([[A, B, C], [C, A]], k=60)
        self.assertEqual([d["_id"] for d in out], ["A", "C", "B"])
        self.assertAlmostEqual(out[0]["_rrf"], 1 / 61 + 1 / 62, places=12)
        self.assertAlmostEqual(out[1]["_rrf"], 1 / 63 + 1 / 61, places=12)
        self.assertAlmostEqual(out[2]["_rrf"], 1 / 62, places=12)

    def test_k_from_config_changes_scores(self):
        A = {"_logical": "x", "_id": "A"}
        self.assertAlmostEqual(rrf([[A]], k=10)[0]["_rrf"], 1 / 11)


class TestQueryBodies(unittest.TestCase):
    def test_bm25_terms_and_phrase_boost(self):
        body = build_bm25_body(
            "text_cwwl", "问题", size=30, terms={"author": ["李常受"], "book_title.keyword": ["甲", "乙"]}, phrases=["神的爱"], phrase_boost=2.5
        )
        b = body["query"]["bool"]
        self.assertIn({"terms": {"author": ["李常受"]}}, b["filter"])
        self.assertIn({"terms": {"book_title.keyword": ["甲", "乙"]}}, b["filter"])
        self.assertEqual(b["should"][0]["match_phrase"]["text"]["boost"], 2.5)
        self.assertNotIn("analyzer", b["must"][0]["match"]["text"])

    def test_knn_uses_configured_vector_field_and_filter(self):
        body = build_knn_body("text_life", [0.0] * 4, k=30, num_candidates=200, terms={"author": ["李常受"]})
        self.assertEqual(body["knn"]["field"], "text_vector")
        self.assertEqual(body["knn"]["num_candidates"], 200)
        self.assertEqual(body["knn"]["filter"], [{"terms": {"author": ["李常受"]}}])
        self.assertEqual(build_knn_body("outline_12490", [0.0], k=1, num_candidates=1)["knn"]["field"], "embedding")
        self.assertIsNone(build_knn_body("pano_catalog", [0.0], k=1, num_candidates=1))


class TestScope(unittest.TestCase):
    def test_default_excludes_bible_hymns_pano(self):
        dec = decide_scope(SubQuestionSpec(query="q"))
        self.assertNotIn("bible", dec.indices)
        self.assertNotIn("hymns", dec.indices)
        self.assertNotIn("pano_catalog", dec.indices)
        self.assertIn("map_note", dec.indices)

    def test_author_hard_filter(self):
        dec = decide_scope(SubQuestionSpec(query="q", author="倪柝声"))
        self.assertEqual(dec.indices, ["text_cwwn"])
        self.assertEqual(dec.hard_terms["text_cwwn"], {"author": ["倪柝声"]})
        dec2 = decide_scope(SubQuestionSpec(query="q", author="李常受"))
        self.assertEqual(sorted(dec2.indices), ["text_cwwl", "text_life", "text_others"])
        self.assertNotIn("map_note", dec2.indices)

    def test_year_hard_filter_overlap_and_range(self):
        dec = decide_scope(SubQuestionSpec(query="q", year_range=(1990, 1992)), year_table=_yt())
        self.assertEqual(dec.indices, ["text_cwwl"])
        self.assertEqual(dec.hard_terms["text_cwwl"]["book_title.keyword"], ["文集一九九一至一九九二年第一册"])
        self.assertEqual(dec.year_range_covered, (1991, 1992))
        self.assertNotIn("文集信函与拾遗第一册", dec.hard_terms["text_cwwl"]["book_title.keyword"])

    def test_conflicts_return_none_flag(self):
        self.assertEqual(decide_scope(SubQuestionSpec(query="q", author="倪柝声", year_range=(1950, 1960)), year_table=_yt()).none_flag, NONE_FLAG)
        self.assertEqual(
            decide_scope(SubQuestionSpec(query="q", author="李常受", scope_override=["outline_feasts"])).none_flag, NONE_FLAG
        )
        self.assertEqual(decide_scope(SubQuestionSpec(query="q", year_range=(2010, 2011)), year_table=_yt()).none_flag, NONE_FLAG)


def _service(docs_by_lg, *, rerank_fail=False):
    es = FakeSearchES(docs_by_lg)
    rr = FakeRerankClient(fail=rerank_fail)
    svc = RetrievalService(es, FakeEmbeddingClient(), rr, year_table=_yt())
    return svc, es, rr


class TestService(unittest.TestCase):
    def test_soft_priority_first_then_fill(self):
        docs = {"outline_12490": [_doc("ol", i) for i in range(3)], "text_cwwl": [_doc("cw", i) for i in range(2)]}
        svc, es, _ = _service(docs)
        res = asyncio.run(svc.retrieve(SubQuestionSpec(query="个人", qtype="个人经历", cap=20)))
        idx = [p.index for p in res.passages]
        self.assertEqual(idx[:2], ["text_cwwl", "text_cwwl"])
        self.assertIn("outline_12490", idx[2:])
        self.assertEqual(set(idx[2:]), {"outline_12490"})

    def test_priority_enough_skips_fill(self):
        docs = {"outline_12490": [_doc("ol", i) for i in range(3)], "text_cwwl": [_doc("cw", i) for i in range(5)]}
        svc, _, _ = _service(docs)
        res = asyncio.run(svc.retrieve(SubQuestionSpec(query="个人", qtype="个人经历", cap=3)))
        self.assertEqual([p.index for p in res.passages], ["text_cwwl"] * 3)

    def test_hard_filter_present_in_es_bodies(self):
        docs = {"text_cwwl": [_doc("cw", 1, author="李常受", book_title="文集一九八五年第一册")]}
        svc, es, _ = _service(docs)
        asyncio.run(svc.retrieve(SubQuestionSpec(query="q", author="李常受", year_range=(1985, 1985))))
        cw = [b for (ix, b) in es.bodies if ix == "qa4_text_cwwl"]
        self.assertTrue(cw)
        for b in cw:
            flt = b["query"]["bool"]["filter"] if "query" in b else b["knn"]["filter"]
            self.assertIn({"terms": {"author": ["李常受"]}}, flt)
            self.assertIn({"terms": {"book_title.keyword": ["文集一九八五年第一册"]}}, flt)
        self.assertFalse([ix for (ix, _) in es.bodies if ix != "qa4_text_cwwl"])

    def test_synthesis_no_search(self):
        svc, es, _ = _service({})
        res = asyncio.run(svc.retrieve(SubQuestionSpec(query="q", synthesis=True)))
        self.assertTrue(res.synthesis)
        self.assertEqual(res.passages, [])
        self.assertEqual(es.bodies, [])

    def test_word_routes_and_relaxed_mode(self):
        docs = {"text_cwwl": [_doc("cw", i) for i in range(2)], "outline_12490": [_doc("ol", i) for i in range(2)]}
        svc, _, rr = _service(docs)
        spec = SubQuestionSpec(query="q", qtype="个人经历", words=["甲", "乙"], original_question="原话")
        normal = asyncio.run(svc.retrieve(spec))
        self.assertIn("词名:甲", normal.coverage["routes"])
        self.assertNotIn("original", normal.coverage["routes"])
        calls_normal = rr.calls
        spec.relaxed = True
        relaxed = asyncio.run(svc.retrieve(spec))
        self.assertIn("original", relaxed.coverage["routes"])
        # 放宽：主路+原话 1 组 + 每个推荐词各 1 组 → 3 次精排；无软优先分两遍
        self.assertEqual(rr.calls - calls_normal, 3)
        self.assertNotEqual([p.index for p in relaxed.passages][:2], ["text_cwwl", "text_cwwl"])

    def test_rerank_failure_degraded_keeps_fusion_order(self):
        docs = {"outline_12490": [_doc("ol", i) for i in range(3)]}
        svc, _, _ = _service(docs, rerank_fail=True)
        res = asyncio.run(svc.retrieve(SubQuestionSpec(query="q", scope_override=["outline_12490"])))
        self.assertTrue(res.degraded)
        self.assertEqual([p.id for p in res.passages], [f"outline_12490:ol-{i}" for i in range(3)])

    def test_coverage_counts(self):
        docs = {"outline_12490": [_doc("ol", i) for i in range(3)]}
        svc, _, _ = _service(docs)
        res = asyncio.run(svc.retrieve(SubQuestionSpec(query="q", scope_override=["outline_12490"])))
        self.assertEqual(res.coverage["routes"]["main"]["outline_12490.bm25"], 3)
        self.assertEqual(res.coverage["kept"], 3)


class TestDedupe(unittest.TestCase):
    def test_map_note_key(self):
        self.assertEqual(map_note_key("（恢复本圣经，可十四24，注1）"), (41, 14, 24, 14, 24, 1))
        self.assertIsNone(map_note_key("（没有出处）"))

    def test_three_kinds(self):
        docs = [
            {"_logical": "map_note", "_id": "m1", "source_zh": "（恢复本圣经，可十四24，注1）"},
            {"_logical": "map_note", "_id": "m2", "source_zh": "（恢复本圣经，可十四24，注1）"},
            {"_logical": "map_note", "_id": "m3", "source_zh": "（恢复本圣经，可十四24，注2）"},
            {"_logical": "hymns", "_id": "h1", "series": "诗歌", "hymn_number": 1},
            {"_logical": "hymns", "_id": "h2", "series": "诗歌", "hymn_number": 1},
            {"_logical": "hymns", "_id": "h3", "series": "补充本诗歌", "hymn_number": 1},
        ] + [{"_logical": "text_life", "_id": f"l{i}", "book_title": "甲生命读经", "message_number": 2} for i in range(5)]
        kept, st = dedupe(docs, per_message_cap=3)
        ids = [d["_id"] for d in kept]
        self.assertEqual(ids, ["m1", "m3", "h1", "h3", "l0", "l1", "l2"])
        self.assertEqual(st, {"map_note_dup": 1, "hymn_dup": 1, "message_cap": 2})


if __name__ == "__main__":
    unittest.main()
