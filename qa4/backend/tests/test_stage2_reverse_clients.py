# -*- coding: utf-8 -*-
"""阶段 2：反找经文（假 Neo4j / 假 3a / 假检索）与嵌入、重排客户端（不联网）。"""

from __future__ import annotations

import asyncio
import math
import unittest

from _helpers import BIBLE_DIR, bible, quiet

from core.embedding_client import EmbeddingClient, EmbeddingError, FakeEmbeddingClient, cosine
from core.neo4j_client import FakeNeo4jClient
from core.rerank_client import FakeRerankClient, RerankClient
from retrieval.fake import FakeRetrievalService
from scripture.reverse import ReverseFinder

quiet("qa4.rerank", "qa4.embed", "qa4.retrieval")


class _Defs:
    def __init__(self, rows):
        self.rows = rows

    def content_3a(self, name):
        return self.rows.get(name, "")


@unittest.skipUnless(BIBLE_DIR.is_dir(), "bible_data 未就绪")
class TestReverse(unittest.TestCase):
    def test_merge_order_and_source_tags(self):
        graph = FakeNeo4jClient(scripture_links={"神的爱": ["约三16", "罗五5"]})
        defs = _Defs({"神的爱": "读经：罗五5，约壹四8\n壹　占位"})
        rf = ReverseFinder(graph=graph, definitions=defs, retrieval=FakeRetrievalService.from_default_fixture(), bible=bible())
        out = asyncio.run(rf.find("神的爱"))
        labels = [h["label"] for h in out["hits"]]
        self.assertEqual(labels[:3], ["约3:16", "罗5:5", "约壹4:8"])
        by = {h["label"]: h["sources"] for h in out["hits"]}
        self.assertEqual(by["罗5:5"], ["graph", "3a"])
        self.assertEqual(by["约壹4:8"], ["3a"])
        self.assertFalse(out["used_bible_vector"])
        self.assertEqual([h["rank"] for h in out["hits"]], list(range(1, len(labels) + 1)))

    def test_bible_vector_fallback_when_few(self):
        rf = ReverseFinder(graph=FakeNeo4jClient(), definitions=_Defs({}), retrieval=FakeRetrievalService.from_default_fixture(), bible=bible())
        out = asyncio.run(rf.find("神的爱"))
        self.assertTrue(out["used_bible_vector"])
        self.assertEqual(out["hits"][0]["sources"], ["bible_vector"])
        self.assertEqual(out["hits"][0]["label"], "约3:16")


class _Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data


class _Http:
    def __init__(self, resp):
        self.resp = resp
        self.posts = []

    async def post(self, url, json=None, headers=None):
        self.posts.append((url, json, headers))
        return self.resp


class TestClients(unittest.TestCase):
    def test_fake_embedding_deterministic_unit_1024(self):
        f = FakeEmbeddingClient()
        a, b = asyncio.run(f.embed(["甲", "甲"]))
        c = asyncio.run(f.embed(["乙"]))[0]
        self.assertEqual(len(a), 1024)
        self.assertEqual(a, b)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in a)), 1.0, places=6)
        self.assertLess(cosine(a, c), 0.99)

    def test_embedding_client_protocol_without_network(self):
        http = _Http(_Resp(200, {"data": [{"index": 1, "embedding": [0.0] * 1024}, {"index": 0, "embedding": [1.0] * 1024}]}))
        cli = EmbeddingClient("https://example.invalid/v1", "k", "m", http_client=http)
        out = asyncio.run(cli.embed(["a", "b"]))
        self.assertEqual(out[0][0], 1.0)
        url, payload, _ = http.posts[0]
        self.assertTrue(url.endswith("/embeddings"))
        self.assertEqual(payload["dimensions"], 1024)
        self.assertEqual(payload["input"], ["a", "b"])
        with self.assertRaises(EmbeddingError):
            asyncio.run(EmbeddingClient("", "", "m").embed(["a"]))

    def test_rerank_client_protocol_and_degrade(self):
        http = _Http(_Resp(200, {"results": [{"index": 2}, {"index": 0}]}))
        cli = RerankClient("https://example.invalid/v1", "k", "jina-reranker-v3", http_client=http)
        idx, deg = asyncio.run(cli.rerank("q", ["a", "b", "c"], 3))
        self.assertEqual((idx, deg), ([2, 0, 1], False))
        self.assertTrue(http.posts[0][0].endswith("/rerank"))
        self.assertEqual(http.posts[0][1]["top_n"], 3)
        bad = RerankClient("https://example.invalid/v1", "k", "m", http_client=_Http(_Resp(500, {})))
        self.assertEqual(asyncio.run(bad.rerank("q", ["a", "b"], 2)), ([0, 1], True))
        self.assertEqual(asyncio.run(RerankClient("", "", "m").rerank("q", ["a"], 1)), ([0], True))

    def test_fake_rerank_deterministic(self):
        r = FakeRerankClient()
        a = asyncio.run(r.rerank("神的爱", ["别的", "神的爱在此", "爱"], 3))
        self.assertEqual(a, asyncio.run(r.rerank("神的爱", ["别的", "神的爱在此", "爱"], 3)))
        self.assertEqual(a[0][0], 1)


if __name__ == "__main__":
    unittest.main()
