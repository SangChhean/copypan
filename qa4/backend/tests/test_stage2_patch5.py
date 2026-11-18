# -*- coding: utf-8 -*-
"""补丁五：iter_json_rows 健壮性；检查 8 ids 精确取数。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.check_source_vs_es import iter_json_rows
from tools.stage2_live_patch3 import check_text_source_vs_es, es_existing_chunk_ids


class TestIterJsonRows(unittest.TestCase):
    def test_json_array(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.json"
            p.write_text(json.dumps([{"chunk_id": "1"}, {"chunk_id": "2"}]), encoding="utf-8")
            rows = list(iter_json_rows([p]))
        self.assertEqual([r["chunk_id"] for r in rows], ["1", "2"])

    def test_json_lines_with_blank(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.jsonl"
            p.write_text('{"chunk_id":"a"}\n\n{"chunk_id":"b"}\n', encoding="utf-8")
            rows = list(iter_json_rows([p]))
        self.assertEqual([r["chunk_id"] for r in rows], ["a", "b"])

    def test_bom_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bom.jsonl"
            p.write_bytes(b"\xef\xbb\xbf" + b'{"chunk_id":"x"}\n')
            rows = list(iter_json_rows([p]))
        self.assertEqual(rows[0]["chunk_id"], "x")

    def test_json_extra_data_fallback_to_lines(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "chunks_vec.json"
            # 形如整文件 json.loads 会 Extra data
            p.write_text('{"chunk_id":"1"}\n{"chunk_id":"2"}\n', encoding="utf-8")
            rows = list(iter_json_rows([p]))
        self.assertEqual([r["chunk_id"] for r in rows], ["1", "2"])

    def test_bad_line_recorded_and_continues(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.jsonl"
            p.write_text('{"chunk_id":"ok1"}\nNOT_JSON\n{"chunk_id":"ok2"}\n', encoding="utf-8")
            bad: list = []
            rows = list(iter_json_rows([p], bad_lines=bad))
        self.assertEqual([r["chunk_id"] for r in rows], ["ok1", "ok2"])
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)


class _FakeEs:
    """假 ES：仅支持 ids 查询；docs 用 _id=chunk_id。"""

    def __init__(self, docs: dict[str, dict]):
        self.docs = docs

    def search(self, index: str, body: dict, *, scroll=None):
        q = body.get("query") or {}
        ids = (q.get("ids") or {}).get("values") or []
        hits = []
        for i in ids:
            if i in self.docs:
                hits.append({"_id": i, "_source": {"chunk_id": i, **self.docs[i]}})
        return {"hits": {"hits": hits}}


class TestCheck8IdsExact(unittest.TestCase):
    def test_es_existing_across_book_titles(self):
        # 同一 message_key 跨多 book_title；旧逻辑按单 book_title 会漏
        docs = {
            "cwwl_1994-1997-2-1#1-1": {"book_title": "书A", "message_number": 1},
            "cwwl_1994-1997-2-2#1-1": {"book_title": "书B", "message_number": 1},
            "cwwl_1994-1997-2-3#1-1": {"book_title": "书C", "message_number": 1},
        }
        es = _FakeEs(docs)
        want = list(docs.keys())
        got = es_existing_chunk_ids(es, "qa4_text_cwwl", want, batch_size=2)
        self.assertEqual(got, set(want))

    def test_check8_from_source_reports_missing(self):
        rows = [
            {
                "chunk_id": "life_49-1-1",
                "message_key": "life_49-1",
                "book_title": "以弗所书生命读经",
                "message_number": 1,
                "text": "a",
            },
            {
                "chunk_id": "life_49-1-2",
                "message_key": "life_49-1",
                "book_title": "以弗所书生命读经",
                "message_number": 1,
                "text": "b",
            },
            {
                "chunk_id": "life_49-1-3",
                "message_key": "life_49-1",
                "book_title": "以弗所书生命读经",
                "message_number": 1,
                "text": "c",
            },
            {
                "chunk_id": "life_17-1-1",
                "message_key": "life_17-1",
                "book_title": "以斯帖记生命读经",
                "message_number": 1,
                "text": "d",
            },
            {
                "chunk_id": "life_45-1-1",
                "message_key": "life_45-1",
                "book_title": "罗马书生命读经",
                "message_number": 1,
                "text": "e",
            },
            {
                "chunk_id": "life_43-1-1",
                "message_key": "life_43-1",
                "book_title": "约翰福音生命读经",
                "message_number": 1,
                "text": "f",
            },
        ]
        # ES 缺 life_49-1 的 3 个 id 中的全部 → 对该样例 FAIL；其它样例在
        present = {
            "life_17-1-1": {},
            "life_45-1-1": {},
            "life_43-1-1": {},
        }
        es = _FakeEs(present)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            life = root / "panai4_text_life" / "shards"
            life.mkdir(parents=True)
            (life / "a.jsonl").write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                encoding="utf-8",
            )
            args = SimpleNamespace(
                source_text_life=life.parent,
                source_text_cwwl=None,
                source_text_cwwn=None,
                source_text_others=None,
                source_vs_es_json=None,
            )
            # monkeypatch env defaults by passing paths
            import tools.stage2_live_patch3 as p3

            # actual_index via settings not needed — patch retrieval.config.actual_index
            import retrieval.config as rc

            old = rc.actual_index
            rc.actual_index = lambda logical: f"qa4_{logical}"
            try:
                out = check_text_source_vs_es(es, settings=None, args=args)
            finally:
                rc.actual_index = old
        self.assertFalse(out["pass"])
        sample = out["samples"]["life:以弗所书生命读经"]
        self.assertEqual(sample["source_n"], 3)
        self.assertEqual(sorted(sample["missing_chunk_ids"]), ["life_49-1-1", "life_49-1-2", "life_49-1-3"])

    def test_check8_from_report_without_rereading(self):
        # 四索引齐全；cwwl 真缺 3 → FAIL（补丁六起须齐全才进入判定）
        report = {
            "indices": {
                "text_life": {
                    "source_n": 10,
                    "es_n": 10,
                    "missing_n": 0,
                    "extra_n": 0,
                    "volumes_top_missing": [],
                },
                "text_cwwl": {
                    "source_n": 100,
                    "es_n": 97,
                    "missing_n": 3,
                    "extra_n": 0,
                    "volumes_top_missing": [
                        {
                            "volume": "cwwl_x",
                            "source_n": 10,
                            "es_n": 7,
                            "missing_n": 3,
                            "missing_rate": 0.3,
                            "missing_chunk_ids": ["a", "b", "c"],
                        }
                    ],
                },
                "text_cwwn": {
                    "source_n": 5,
                    "es_n": 5,
                    "missing_n": 0,
                    "extra_n": 0,
                    "volumes_top_missing": [],
                },
                "text_others": {
                    "source_n": 5,
                    "es_n": 5,
                    "missing_n": 0,
                    "extra_n": 0,
                    "volumes_top_missing": [],
                },
            },
            "top3_missing_volumes": [
                {
                    "logical": "text_cwwl",
                    "volume": "cwwl_x",
                    "source_n": 10,
                    "es_n": 7,
                    "missing_n": 3,
                    "missing_rate": 0.3,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            jp = Path(td) / "rep.json"
            jp.write_text(json.dumps(report), encoding="utf-8")
            args = SimpleNamespace(source_vs_es_json=jp)
            out = check_text_source_vs_es(_FakeEs({}), settings=None, args=args)
        self.assertEqual(out["mode"], "from_report")
        self.assertNotIn("skipped", out)
        self.assertFalse(out["pass"])
        self.assertTrue(out["samples"]["report:text_life"]["equal"])
        self.assertFalse(out["samples"]["report:text_cwwl"]["equal"])
        self.assertEqual(out["samples"]["topmiss:text_cwwl:cwwl_x"]["missing_chunk_ids"], ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
