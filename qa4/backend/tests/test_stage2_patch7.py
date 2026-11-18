# -*- coding: utf-8 -*-
"""补丁七：JSONL 不按 Unicode 行边界切开；--rerun 强制重算。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.check_source_vs_es import collect_resume_indices, iter_json_rows


class TestJsonlUnicodeLineSep(unittest.TestCase):
    def test_keeps_record_with_unicode_separators(self):
        # 文本中嵌入多种「类换行」码点，仍应作为一行 JSON
        specials = "\u2028\u2029\x0b\x0c\x1c\x85"
        row = {
            "chunk_id": "cwwl_keep_me",
            "text": f"hello{specials}world",
        }
        line = json.dumps(row, ensure_ascii=False)
        # 确认 splitlines 会切开，而我们的读取不应
        self.assertGreater(len(line.splitlines()), 1)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.jsonl"
            p.write_bytes((line + "\n").encode("utf-8"))
            bad: list = []
            rows = list(iter_json_rows([p], bad_lines=bad))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["chunk_id"], "cwwl_keep_me")
        self.assertEqual(rows[0]["text"], f"hello{specials}world")
        self.assertEqual(bad, [])

    def test_true_bad_line_still_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.jsonl"
            p.write_text(
                '{"chunk_id":"ok1"}\n{"chunk_id":"trunc\n{"chunk_id":"ok2"}\n',
                encoding="utf-8",
            )
            bad: list = []
            rows = list(iter_json_rows([p], bad_lines=bad))
        self.assertEqual([r["chunk_id"] for r in rows], ["ok1", "ok2"])
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)
        self.assertTrue(str(p) == bad[0]["file"] or bad[0]["file"].endswith("a.jsonl"))


class TestRerunFlag(unittest.TestCase):
    def test_rerun_excludes_from_resume(self):
        prev = {
            "text_life": {
                "source_n": 10,
                "es_n": 10,
                "missing_n": 0,
                "extra_n": 0,
                "pass": True,
            },
            "text_cwwl": {
                "source_n": 178106,
                "es_n": 178107,
                "missing_n": 0,
                "extra_n": 1,
                "pass": False,
            },
        }
        reused = collect_resume_indices(prev, rerun={"text_cwwl"})
        self.assertEqual(set(reused.keys()), {"text_life"})
        self.assertNotIn("text_cwwl", reused)
        # 合并语义：复用 life，重算 cwwl 后写入
        merged = dict(reused)
        merged["text_cwwl"] = {
            "source_n": 178107,
            "es_n": 178107,
            "missing_n": 0,
            "extra_n": 0,
            "pass": True,
        }
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            out.write_text(
                json.dumps({"indices": merged}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            loaded = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(loaded["indices"]["text_life"]["source_n"], 10)
        self.assertEqual(loaded["indices"]["text_cwwl"]["source_n"], 178107)


class TestRealCwwlExtraIdOffline(unittest.TestCase):
    """若本机有 import_src，确认修复后能读到 cwwl_1972-1-4#1-20。"""

    def test_read_known_ls_record_if_present(self):
        shard = Path(
            r"G:/PanAI4.0专用/qa4_import_src/es/data/panai4_text_cwwl/shards/kg-rag_cwwl_shard_00013.jsonl"
        )
        if not shard.is_file():
            self.skipTest("无本机 cwwl shard")
        bad: list = []
        found = None
        for row in iter_json_rows([shard], bad_lines=bad):
            if row.get("chunk_id") == "cwwl_1972-1-4#1-20":
                found = row
                break
        self.assertIsNotNone(found)
        # U+2028 在 en 字段（非 text）；读整行后仍应保留
        self.assertIn("\u2028", found.get("en") or "")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
