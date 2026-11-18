# -*- coding: utf-8 -*-
"""check_services 纯逻辑测试（假数据，不连外部服务）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_TOOLS = _BACKEND / "tools"
for p in (_BACKEND, _TOOLS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from check_services import (  # noqa: E402
    EXPECT_VECTOR_DIMS,
    evaluate_es,
    evaluate_neo4j,
    exit_code_for_status,
    main,
    redact_secrets,
    summarize_report,
)


INDEX_MAP = {
    "bible": {"index": "qa4_bible", "vector_field": "embedding"},
    "pano_catalog": {"index": "qa4_pano_catalog", "vector_field": None},
}


def _ok_stats(expected: dict[str, int]) -> dict[str, dict]:
    return {
        k: {
            "index": INDEX_MAP.get(k, {}).get("index", f"qa4_{k}"),
            "exists": True,
            "count": v,
            "expected": v,
            "status": "ok",
        }
        for k, v in expected.items()
    }


def _good_mappings() -> dict:
    return {
        "qa4_bible": {
            "qa4_bible": {
                "mappings": {
                    "properties": {
                        "embedding": {
                            "type": "dense_vector",
                            "dims": EXPECT_VECTOR_DIMS,
                        }
                    }
                }
            }
        },
        "qa4_pano_catalog": {
            "qa4_pano_catalog": {"mappings": {"properties": {"title": {"type": "text"}}}}
        },
    }


class TestCheckServicesEval(unittest.TestCase):
    def test_mapping_dims_mismatch_not_ready(self):
        expected = {"bible": 10, "pano_catalog": 5}
        mappings = _good_mappings()
        mappings["qa4_bible"]["qa4_bible"]["mappings"]["properties"]["embedding"][
            "dims"
        ] = 768
        rep = evaluate_es(
            index_map=INDEX_MAP,
            expected=expected,
            stats=_ok_stats(expected),
            mappings=mappings,
        )
        self.assertEqual(rep["status"], "not_ready")
        bible = rep["indices"]["bible"]
        self.assertEqual(bible["status"], "not_ready")
        self.assertIn("向量维度不符", bible["message"])
        self.assertIn("qa4_bible", bible["message"])
        self.assertIn("embedding", bible["message"])
        self.assertIn("768", bible["message"])
        # pano 无向量要求，仍 ok
        self.assertEqual(rep["indices"]["pano_catalog"]["status"], "ok")
        self.assertEqual(exit_code_for_status(rep["status"]), 1)

    def test_neo4j_count_mismatch_degraded(self):
        expected = {
            "Truth_Point": 2380,
            "Branch": 91,
            "Trunk": 12,
            "Scripture": 4848,
        }
        counts = {
            "Truth_Point": 2380,
            "Branch": 91,
            "Trunk": 12,
            "Scripture": 4851,
        }
        rep = evaluate_neo4j(counts, expected, ping_ok=True)
        self.assertEqual(rep["status"], "degraded")
        sc = rep["labels"]["Scripture"]
        self.assertEqual(sc["status"], "degraded")
        self.assertEqual(sc["actual"], 4851)
        self.assertEqual(sc["expected"], 4848)
        self.assertIn("4851", sc["message"])
        self.assertIn("4848", sc["message"])
        self.assertEqual(exit_code_for_status(rep["status"]), 0)

    def test_all_consistent_ok(self):
        expected_es = {"bible": 10, "pano_catalog": 5}
        es_rep = evaluate_es(
            index_map=INDEX_MAP,
            expected=expected_es,
            stats=_ok_stats(expected_es),
            mappings=_good_mappings(),
        )
        self.assertEqual(es_rep["status"], "ok")

        expected_neo = {
            "Truth_Point": 2380,
            "Branch": 91,
            "Trunk": 12,
            "Scripture": 4848,
        }
        neo_rep = evaluate_neo4j(expected_neo, expected_neo, ping_ok=True)
        self.assertEqual(neo_rep["status"], "ok")

        report = summarize_report(
            redis={"status": "ok", "ping": True},
            elasticsearch=es_rep,
            neo4j=neo_rep,
        )
        self.assertEqual(report["status"], "ok")
        self.assertEqual(exit_code_for_status(report["status"]), 0)

    def test_exception_message_redacted(self):
        secret = "Hunter2Secret"
        ping_err = f"Failed bolt://neo4j:{secret}@localhost:7687 password={secret}"
        rep = evaluate_neo4j(
            {},
            {"Scripture": 4848},
            ping_ok=False,
            ping_error=ping_err,
        )
        blob = str(rep)
        self.assertNotIn(secret, blob)
        self.assertEqual(rep["status"], "not_ready")
        self.assertEqual(rep["message"], redact_secrets(ping_err))

        es_rep = evaluate_es(
            index_map=INDEX_MAP,
            expected={"bible": 1},
            stats={},
            mappings={},
            ping_ok=False,
            ping_error=f"https://elastic:{secret}@localhost:9200 token={secret}",
        )
        self.assertNotIn(secret, str(es_rep))

    def test_vector_field_missing_not_ready(self):
        expected = {"bible": 10}
        mappings = {
            "qa4_bible": {
                "qa4_bible": {"mappings": {"properties": {"text": {"type": "text"}}}}
            }
        }
        rep = evaluate_es(
            index_map=INDEX_MAP,
            expected=expected,
            stats=_ok_stats(expected),
            mappings=mappings,
        )
        self.assertEqual(rep["status"], "not_ready")
        self.assertIn("向量字段缺失", rep["indices"]["bible"]["message"])

    def test_es_count_mismatch_degraded_when_mapping_ok(self):
        expected = {"bible": 10, "pano_catalog": 5}
        stats = _ok_stats(expected)
        stats["bible"]["count"] = 9
        rep = evaluate_es(
            index_map=INDEX_MAP,
            expected=expected,
            stats=stats,
            mappings=_good_mappings(),
        )
        self.assertEqual(rep["status"], "degraded")
        self.assertEqual(rep["indices"]["bible"]["status"], "degraded")
        self.assertEqual(exit_code_for_status("degraded"), 0)


class TestCheckServicesCli(unittest.TestCase):
    def test_dry_run(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("dry-run", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
