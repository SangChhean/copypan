# -*- coding: utf-8 -*-
"""索引检索失败应写入问答记录 es_failures。"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from pipeline.context import RequestContext
from pipeline.schemas import Answer, Plan, SubQuestion
from pipeline.step09_record import build_trace, collect_es_failures
from retrieval.es_search import record_es_failure, run_search


class _BoomEs:
    def search(self, index: str, body: dict):
        class Meta:
            status = 400

        exc = Exception("boom")
        exc.meta = Meta()  # type: ignore[attr-defined]
        exc.body = {  # type: ignore[attr-defined]
            "error": {
                "type": "search_phase_execution_exception",
                "reason": "all shards failed",
                "root_cause": [
                    {
                        "type": "illegal_argument_exception",
                        "reason": "simulated field error",
                    }
                ],
            }
        }
        raise exc


class TestEsFailureRecord(unittest.TestCase):
    def test_run_search_records_failure(self):
        fails: list[dict] = []

        async def _go():
            hits = await run_search(_BoomEs(), "text_cwwl", {"size": 1, "query": {"match_all": {}}}, failures_out=fails)
            return hits

        hits = asyncio.run(_go())
        self.assertEqual(hits, [])
        self.assertEqual(len(fails), 1)
        self.assertEqual(fails[0]["logical"], "text_cwwl")
        self.assertEqual(fails[0]["status"], 400)
        self.assertEqual(fails[0]["type"], "illegal_argument_exception")

    def test_build_trace_includes_es_failures(self):
        ctx = RequestContext(request_id="rid-es-fail", question_orig="测试检索失败记录")
        ctx.plan = Plan(
            main_type="真理",
            subquestions=[SubQuestion(text="测试检索失败记录", qtype="真理")],
        )
        ctx.answer = Answer(text="占位")
        ctx.retrieval_cov = {
            "0": {
                "coverage": {
                    "es_failures": [
                        {
                            "logical": "outline_12490",
                            "index": "qa4_outline_12490",
                            "status": 400,
                            "type": "illegal_argument_exception",
                        }
                    ]
                }
            }
        }
        deps = SimpleNamespace(
            cfg={"traces": {"store_question_text": True}},
            prompts=SimpleNamespace(versions=lambda: {}),
        )
        rec = build_trace(ctx, deps)
        self.assertEqual(len(rec["es_failures"]), 1)
        self.assertEqual(rec["es_failures"][0]["logical"], "outline_12490")
        self.assertEqual(rec["es_failures"][0]["status"], 400)
        self.assertEqual(rec["es_failures"][0]["type"], "illegal_argument_exception")

    def test_collect_dedupes(self):
        cov = {
            "0": {
                "coverage": {
                    "es_failures": [
                        {"logical": "text_cwwl", "status": 400, "type": "x"},
                        {"logical": "text_cwwl", "status": 400, "type": "x"},
                    ]
                }
            },
            "1": {
                "coverage": {
                    "es_failures": [
                        {"logical": "text_cwwl", "status": 400, "type": "x"},
                        {"logical": "outline_12490", "status": 500, "type": "y"},
                    ]
                }
            },
        }
        got = collect_es_failures(cov)
        self.assertEqual(len(got), 2)
        logicals = {g["logical"] for g in got}
        self.assertEqual(logicals, {"text_cwwl", "outline_12490"})

    def test_record_es_failure_helper(self):
        out: list[dict] = []
        record_es_failure(out, logical="text_life", index="qa4_text_life", status=404, etype="index_not_found_exception")
        record_es_failure(out, logical="text_life", index="qa4_text_life", status=404, etype="index_not_found_exception")
        self.assertEqual(len(out), 1)


class TestTranslateMissingOpencc(unittest.TestCase):
    def test_to_traditional_raises_when_missing(self):
        from core import translate as tr

        saved = {k: sys.modules[k] for k in list(sys.modules) if k == "opencc" or k.startswith("opencc.") or k == "zhconv"}
        for k in saved:
            sys.modules.pop(k, None)
        try:
            with mock.patch.dict(sys.modules, {"opencc": None, "zhconv": None}):
                with self.assertRaises(RuntimeError) as cm:
                    tr.to_traditional("神的爱")
            self.assertIn("未安装", str(cm.exception))
        finally:
            sys.modules.update(saved)


if __name__ == "__main__":
    unittest.main()
