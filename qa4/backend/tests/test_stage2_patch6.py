# -*- coding: utf-8 -*-
"""补丁六：resume 不复用 failed/skipped；检查 8 报告模式不假 PASS。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.check_source_vs_es import _index_done, collect_resume_indices
from tools.stage2_live_patch3 import CHECK8_REQUIRED_INDICES, check_text_source_vs_es
from tools.verify_stage2_live import _item_state


def _ok(n: int = 10) -> dict:
    return {
        "source_n": n,
        "es_n": n,
        "missing_n": 0,
        "extra_n": 0,
        "volumes_top_missing": [],
        "pass": True,
    }


class TestResumeIndexDone(unittest.TestCase):
    def test_resume_reuses_only_success(self):
        prev = {
            "text_life": {
                "source_n": 39463,
                "es_n": 39463,
                "missing_n": 0,
                "extra_n": 0,
                "pass": True,
            },
            "text_cwwl": {"failed": True, "error_type": "JSONDecodeError", "error": "Extra data"},
            "text_cwwn": {"skipped": True, "reason": "缺源"},
        }
        self.assertTrue(_index_done(prev["text_life"]))
        self.assertFalse(_index_done(prev["text_cwwl"]))
        self.assertFalse(_index_done(prev["text_cwwn"]))
        reused = collect_resume_indices(prev)
        self.assertEqual(set(reused.keys()), {"text_life"})
        # 另两个视为未完成 → 续跑时会重新比对
        need_rerun = [k for k in ("text_life", "text_cwwl", "text_cwwn") if k not in reused]
        self.assertEqual(set(need_rerun), {"text_cwwl", "text_cwwn"})


class TestCheck8ReportNoFalsePass(unittest.TestCase):
    def _run(self, indices: dict, *, top3=None) -> dict:
        report = {"indices": indices, "top3_missing_volumes": top3 or []}
        with tempfile.TemporaryDirectory() as td:
            jp = Path(td) / "rep.json"
            jp.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            args = SimpleNamespace(source_vs_es_json=jp)
            return check_text_source_vs_es(es=None, settings=None, args=args)

    def test_required_set(self):
        self.assertEqual(
            CHECK8_REQUIRED_INDICES,
            ("text_life", "text_cwwl", "text_cwwn", "text_others"),
        )

    def test_missing_text_cwwl_is_skip_not_pass(self):
        indices = {lg: _ok() for lg in CHECK8_REQUIRED_INDICES if lg != "text_cwwl"}
        out = self._run(indices)
        self.assertIn("skipped", out)
        self.assertTrue(any("text_cwwl" in s for s in out["skipped"]))
        self.assertNotEqual(_item_state(out), "PASS")
        self.assertEqual(_item_state(out), "跳过")

    def test_failed_text_cwwl_is_skip_not_pass(self):
        indices = {lg: _ok() for lg in CHECK8_REQUIRED_INDICES}
        indices["text_cwwl"] = {"failed": True, "error_type": "RuntimeError", "error": "boom"}
        out = self._run(indices)
        self.assertIn("skipped", out)
        self.assertTrue(any("text_cwwl" in s and "失败" in s for s in out["skipped"]))
        self.assertEqual(_item_state(out), "跳过")

    def test_skipped_text_cwwl_is_skip_not_pass(self):
        indices = {lg: _ok() for lg in CHECK8_REQUIRED_INDICES}
        indices["text_cwwl"] = {"skipped": True, "reason": "缺源"}
        out = self._run(indices)
        self.assertIn("skipped", out)
        self.assertTrue(any("text_cwwl" in s and "跳过" in s for s in out["skipped"]))
        self.assertEqual(_item_state(out), "跳过")

    def test_all_ok_equal_is_pass(self):
        indices = {lg: _ok() for lg in CHECK8_REQUIRED_INDICES}
        out = self._run(indices)
        self.assertNotIn("skipped", out)
        self.assertTrue(out.get("pass"))
        self.assertEqual(_item_state(out), "PASS")
        for lg in CHECK8_REQUIRED_INDICES:
            self.assertTrue(out["samples"][f"report:{lg}"]["equal"])

    def test_true_missing_ids_is_fail(self):
        indices = {lg: _ok() for lg in CHECK8_REQUIRED_INDICES}
        indices["text_cwwl"] = {
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
                    "missing_chunk_ids": ["m1", "m2", "m3"],
                }
            ],
            "pass": False,
        }
        out = self._run(
            indices,
            top3=[
                {
                    "logical": "text_cwwl",
                    "volume": "cwwl_x",
                    "source_n": 10,
                    "es_n": 7,
                    "missing_n": 3,
                    "missing_rate": 0.3,
                }
            ],
        )
        self.assertNotIn("skipped", out)
        self.assertFalse(out.get("pass"))
        self.assertEqual(_item_state(out), "FAIL")
        self.assertEqual(
            out["samples"]["report:text_cwwl"]["missing_chunk_ids"][:3],
            ["m1", "m2", "m3"],
        )


if __name__ == "__main__":
    unittest.main()
