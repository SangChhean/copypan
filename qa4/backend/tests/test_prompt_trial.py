# -*- coding: utf-8 -*-
"""prompt_trial 过滤 / 上文 / force-split / 价格表 / JSONL 结构（不读 holdout，不联网）。"""

from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

from tools import prompt_trial as pt

_DEV = Path(__file__).resolve().parents[2] / "notes" / "dev_questions_draft.csv"
_OUT = Path(r"G:\PanAI4.0专用\logs\prompt_trial")
_REAL_PRICES = Path(__file__).resolve().parents[1] / "config" / "prices.json"

_PRICE_KEYS = ("input", "output", "cache_write_5m", "cache_read")


def _write_prices(path: Path, *, status: str, fill: dict[str, dict] | None = None, null_all: bool = False) -> None:
    models = {
        "claude-haiku-5-5": {k: None for k in _PRICE_KEYS},
        "claude-sonnet-5-5": {k: None for k in _PRICE_KEYS},
    }
    if fill:
        for name, row in fill.items():
            models[name] = {k: row.get(k) for k in _PRICE_KEYS}
    elif not null_all and status == "已核实":
        models = {
            "claude-haiku-5-5": {
                "input": 1.0,
                "output": 2.0,
                "cache_write_5m": 4.0,
                "cache_read": 0.1,
            },
            "claude-sonnet-5-5": {
                "input": 3.0,
                "output": 6.0,
                "cache_write_5m": 8.0,
                "cache_read": 0.2,
            },
        }
    path.write_text(
        json.dumps({"status": status, "unit": "USD_per_million_tokens", "models": models}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class TestPromptTrialHelpers(unittest.TestCase):
    def setUp(self):
        # 测试不得被运行者窗口环境变量影响
        self._env_backup = {}
        for k in (
            "QA4_PROMPT_CHANNEL",
            "QA4_ANTHROPIC_API_KEY",
            "QA4_LLM_MODE",
            "QA4_PRICES_PATH",
            "QA4_ENV_FILE",
        ):
            self._env_backup[k] = os.environ[k] if k in os.environ else None
            os.environ.pop(k, None)
        # 真实检索相关：避免窗口残留影响「缺变量 / __FILL_ME__」判定
        self._retrieval_env_backup = {}
        for k in list(pt._REAL_RETRIEVAL_ENV) + list(pt._LIVE_SECRET_ENV):
            self._retrieval_env_backup[k] = os.environ[k] if k in os.environ else None
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for k, v in self._retrieval_env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_cited_numbers_in_order_first_occurrence(self):
        self.assertEqual(pt._cited_numbers_in_order("见[2]与[1]，再[2]"), [2, 1])
        self.assertEqual(pt._cited_numbers_in_order(""), [])

    def test_rewrite_info_no_history(self):
        info = pt._rewrite_info(None, [], None)
        self.assertTrue(info["rewrite_skipped"])
        self.assertFalse(info["rewrite_called"])
        self.assertEqual(info["history_turns_passed"], 0)
        self.assertIsNone(info["step2_input_chars"])

    def test_step_timings_ms_includes_first_token_key(self):
        class _Res:
            ttft_s = 0.0123

        class _Llm:
            last_stream_result = _Res()

        class _Deps:
            llm = _Llm()

        class _Ctx:
            timings_ms = {"step3": 10, "step7": 20}

        out = pt._step_timings_ms(_Ctx(), _Deps())
        self.assertEqual(out["step3"], 10)
        self.assertEqual(out["first_token_ms"], 12)

    def test_parse_history_standard_and_legacy(self):
        h1 = pt.parse_history("问：甲题\n答：甲答\n问：乙题\n答：乙答")
        self.assertEqual(len(h1), 2)
        self.assertEqual(h1[0]["question"], "甲题")
        self.assertEqual(h1[1]["answer"], "乙答")

        h2 = pt.parse_history("上一轮问：召会生活怎样？答：要牧养（摘要）。")
        self.assertEqual(len(h2), 1)
        self.assertIn("召会生活", h2[0]["question"])

        h3 = pt.parse_history("")
        self.assertEqual(h3, [])

    def test_filter_only_ids_then_truncate(self):
        rows = pt.load_questions(_DEV)
        kept, meta = pt.filter_questions(
            rows, priority=None, only_ids=["D01", "D02", "D03"], max_questions=2
        )
        self.assertEqual([r["id"] for r in kept], ["D01", "D02"])
        self.assertEqual(meta["after_filter"], 3)
        self.assertEqual(meta["kept"], 2)
        self.assertEqual(meta["truncated"], 1)

    def test_filter_priority_from_mini_csv(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "mini.csv"
            with p.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=["id", "问题", "优先级", "上文"],
                )
                w.writeheader()
                w.writerow({"id": "M1", "问题": "什么是国度？", "优先级": "P1", "上文": ""})
                w.writerow({"id": "M2", "问题": "什么是圣别？", "优先级": "P2", "上文": ""})
                w.writerow({"id": "M3", "问题": "什么是变化？", "优先级": "P1", "上文": ""})
            rows = pt.load_questions(p)
            kept, meta = pt.filter_questions(
                rows, priority="P1", only_ids=None, max_questions=10
            )
            self.assertEqual({r["id"] for r in kept}, {"M1", "M3"})
            self.assertEqual(meta["truncated"], 0)

    def test_force_split_hint_appended(self):
        calls = []

        class FakeLLM:
            async def complete_json(self, role, system, messages, *, step, max_tokens=None, cache=None):
                calls.append({"step": step, "messages": messages})
                return {}, type("R", (), {"usage": {}})()

        llm = FakeLLM()
        pt.install_force_split(llm, "split")

        async def _go():
            await llm.complete_json(
                "haiku",
                "",
                [{"role": "user", "content": "问题（改写后）：什么是国度？"}],
                step="step3",
            )
            await llm.complete_json(
                "haiku",
                "",
                [{"role": "user", "content": "其它"}],
                step="step4",
            )

        import asyncio

        asyncio.run(_go())
        self.assertIn("【试验】", calls[0]["messages"][0]["content"])
        self.assertIn("complex=true", calls[0]["messages"][0]["content"])
        self.assertNotIn("【试验】", calls[1]["messages"][0]["content"])

    def test_cli_dry_run_only_ids_no_network(self):
        _OUT.mkdir(parents=True, exist_ok=True)
        rc = pt.main(
            [
                "--questions-file",
                str(_DEV),
                "--only-ids",
                "D01,D02,D03",
                "--max-questions",
                "2",
                "--render-only",
                "--out",
                str(_OUT),
            ]
        )
        self.assertEqual(rc, 0)

    def test_prices_null_incomplete_live_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "prices_null.json"
            _write_prices(fake, status="已核实", null_all=True)
            prices = pt.load_prices(fake)
            self.assertTrue(pt.prices_incomplete(prices))
            os.environ["QA4_ANTHROPIC_API_KEY"] = "PLACEHOLDER_NOT_A_REAL_KEY"
            with tempfile.TemporaryDirectory() as out_td:
                rc = pt.main(
                    [
                        "--live",
                        "--only-ids",
                        "D01",
                        "--max-questions",
                        "1",
                        "--budget-usd",
                        "1",
                        "--prices-file",
                        str(fake),
                        "--out",
                        out_td,
                    ]
                )
            self.assertEqual(rc, 2)

    def test_prices_pending_status_live_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "prices_pending.json"
            # 数值齐全但 status=待核实 → 仍 incomplete
            _write_prices(fake, status="待核实")
            # 上面默认已核实才填数；待核实时手动写满数字
            data = json.loads(fake.read_text(encoding="utf-8"))
            data["status"] = "待核实"
            for row in data["models"].values():
                for k in _PRICE_KEYS:
                    row[k] = 1.0
            fake.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            prices = pt.load_prices(fake)
            self.assertTrue(pt.prices_incomplete(prices))
            os.environ["QA4_ANTHROPIC_API_KEY"] = "PLACEHOLDER_NOT_A_REAL_KEY"
            with tempfile.TemporaryDirectory() as out_td:
                rc = pt.main(
                    [
                        "--live",
                        "--only-ids",
                        "D01",
                        "--max-questions",
                        "1",
                        "--budget-usd",
                        "1",
                        "--prices-file",
                        str(fake),
                        "--out",
                        out_td,
                    ]
                )
            self.assertEqual(rc, 2)

    def test_prices_complete_allows_and_cache_priced_separately(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "prices_ok.json"
            _write_prices(fake, status="已核实")
            prices = pt.load_prices(fake)
            self.assertFalse(pt.prices_incomplete(prices))
            # 缓存写入与读取分项计价（同 token 数不同单价 → 费用不同）
            base = {"input": 0, "output": 0, "cache_creation": 1_000_000, "cache_read": 0}
            usd_write, miss_w, unp_w, m1h_w = pt._est_usd_for_usage(
                base, model="claude-haiku-5-5", prices=prices
            )
            usd_read, miss_r, unp_r, m1h_r = pt._est_usd_for_usage(
                {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 1_000_000},
                model="claude-haiku-5-5",
                prices=prices,
            )
            self.assertFalse(miss_w)
            self.assertFalse(miss_r)
            self.assertFalse(unp_w or m1h_w or unp_r or m1h_r)
            self.assertEqual(usd_write, 4.0)  # cache_write_5m
            self.assertEqual(usd_read, 0.1)  # cache_read
            self.assertNotEqual(usd_write, usd_read)
            # 价格关卡放行：齐全 + 已核实 → incomplete 为假（不跑真实 --live，避免联网）
            self.assertFalse(pt.prices_incomplete(pt.load_prices(fake)))

    def test_real_prices_json_structure(self):
        """真实 config/prices.json：四键齐全；已核实时四项为数字（不断言「不齐」）。"""
        self.assertTrue(_REAL_PRICES.is_file())
        prices = pt.load_prices(_REAL_PRICES)
        self.assertIn("status", prices)
        models = prices.get("models") or {}
        self.assertTrue(models)
        verified = str(prices.get("status") or "") == "已核实"
        for name, row in models.items():
            self.assertIsInstance(row, dict, msg=name)
            for k in _PRICE_KEYS:
                self.assertIn(k, row, msg=f"{name}.{k}")
                if verified:
                    self.assertIsInstance(row[k], (int, float), msg=f"{name}.{k} 应为数字")

    def test_dry_run_record_has_required_keys(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fake = td_path / "prices_ok.json"
            out_dir = td_path / "out"
            out_dir.mkdir()
            _write_prices(fake, status="已核实")
            rc = pt.main(
                [
                    "--dry-run",
                    "--only-ids",
                    "D01",
                    "--max-questions",
                    "1",
                    "--prices-file",
                    str(fake),
                    "--out",
                    str(out_dir),
                ]
            )
            self.assertEqual(rc, 0)
            path = next(out_dir.glob("dry_run_*.jsonl"))
            line = path.read_text(encoding="utf-8").strip().splitlines()[0]
            rec = json.loads(line)
        for k in (
            "id",
            "rewritten_question",
            "rewrite_skipped",
            "rewrite_info",
            "plan",
            "layers",
            "retrieval",
            "verdicts",
            "quote_checks_failed",
            "degraded_reasons",
            "cache_hit",
            "citations",
            "cited_numbers_in_order",
            "citations_count",
            "step_timings_ms",
            "tokens",
            "price_missing",
            "retrieval_mode",
            "cost_unknown",
        ):
            self.assertIn(k, rec)
        self.assertEqual(rec.get("retrieval_mode"), "fake")
        self.assertFalse(rec.get("price_missing"))
        self.assertFalse(rec.get("cost_unknown"))
        self.assertIn("by_subq", rec["layers"])
        self.assertIn("dropped", rec["layers"])
        self.assertIsInstance(rec["tokens"], dict)
        if rec["tokens"]:
            sample = next(iter(rec["tokens"].values()))
            for tk in ("model", "input", "output", "cache_creation", "cache_read"):
                self.assertIn(tk, sample)
        self.assertIn("understanding", rec["plan"])
        self.assertIn("subquestions", rec["plan"])
        if rec["plan"]["subquestions"]:
            sq = rec["plan"]["subquestions"][0]
            for sk in ("text", "qtype", "scope", "angle", "synthesis"):
                self.assertIn(sk, sq)
        self.assertIsInstance(rec["citations"], list)
        cite_keys = {
            "n",
            "index",
            "source",
            "title",
            "author",
            "year_or_volume",
            "chunk_id",
            "text_head",
        }
        for c in rec["citations"]:
            self.assertEqual(cite_keys, set(c.keys()))
            self.assertIsInstance(c.get("text_head"), str)
            self.assertLessEqual(len(c["text_head"]), 60)
        self.assertIsInstance(rec["cited_numbers_in_order"], list)
        self.assertIsInstance(rec["step_timings_ms"], dict)
        self.assertIn("first_token_ms", rec["step_timings_ms"])
        ri = rec["rewrite_info"]
        for rk in (
            "history_turns_passed",
            "rewrite_skipped",
            "rewrite_called",
            "step2_input_chars",
        ):
            self.assertIn(rk, ri)
        self.assertTrue(ri["rewrite_skipped"])
        self.assertFalse(ri["rewrite_called"])
        self.assertIsNone(ri["step2_input_chars"])
    def test_format_error_redacts_secrets(self):
        secret = "sk-ant-secrettoken12345678"
        os.environ["QA4_ANTHROPIC_API_KEY"] = secret

        def _boom():
            raise TypeError(f"LLM failed key={secret} also sk-othersecret99999999")

        try:
            _boom()
        except TypeError as e:
            err = pt.format_error(e)
        blob = json.dumps(err, ensure_ascii=False)
        self.assertNotIn(secret, blob)
        self.assertNotIn("sk-othersecret99999999", blob)
        self.assertIn("***", blob)
        self.assertEqual(err["type"], "TypeError")
        self.assertIn("message", err)
        self.assertIn("stack", err)
        self.assertIsInstance(err["stack"], list)
        self.assertGreaterEqual(len(err["stack"]), 1)

    def test_run_one_failure_writes_error_object(self):
        """故意失败（非缺密钥）：临时目录 JSONL error 含 type/message/stack，且脱敏。"""
        secret = "sk-live-injectfailABCDEFGH"
        os.environ["QA4_ANTHROPIC_API_KEY"] = secret

        async def _failing_run_one(*_a, **_k):
            raise TypeError(f"injected live-path failure with {secret}")

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fake = td_path / "prices_ok.json"
            out_dir = td_path / "out"
            out_dir.mkdir()
            _write_prices(fake, status="已核实")
            orig = pt._run_one
            pt._run_one = _failing_run_one  # type: ignore[assignment]
            try:
                rc = pt.main(
                    [
                        "--dry-run",
                        "--only-ids",
                        "D01,D02",
                        "--max-questions",
                        "2",
                        "--prices-file",
                        str(fake),
                        "--out",
                        str(out_dir),
                    ]
                )
            finally:
                pt._run_one = orig  # type: ignore[assignment]
            self.assertEqual(rc, 1)  # fail>0
            jsonls = list(out_dir.glob("dry_run_*.jsonl"))
            self.assertTrue(jsonls, msg="临时 out 目录应新增 JSONL")
            path = jsonls[0]
            lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
            self.assertEqual(len(lines), 2)  # dry-run 两题都记了，未中断
            for rec in lines:
                self.assertFalse(rec.get("ok", True))
                err = rec.get("error")
                self.assertIsInstance(err, dict)
                self.assertEqual(err.get("type"), "TypeError")
                self.assertIn("message", err)
                self.assertIn("stack", err)
                self.assertIsInstance(err["stack"], list)
                blob = json.dumps(err, ensure_ascii=False)
                self.assertNotIn(secret, blob)
                self.assertIn("***", err["message"])

    def test_cache_creation_structures(self):
        """纯数字 / None / 嵌套 dict（5m+1h）/ 未知结构 — 不抛异常。"""
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "prices_ok.json"
            _write_prices(fake, status="已核实")
            prices = pt.load_prices(fake)

        # 纯数字
        c1 = pt.parse_cache_creation({"cache_creation": 100})
        self.assertEqual(c1["tokens_5m"], 100)
        self.assertFalse(c1["usage_unparsed"])
        self.assertFalse(c1["price_missing_1h"])
        usd, miss, unp, m1h = pt._est_usd_for_usage(
            {"input": 0, "output": 0, "cache_creation": 1_000_000, "cache_read": 0},
            model="claude-haiku-5-5",
            prices=prices,
        )
        self.assertEqual(usd, 4.0)
        self.assertFalse(miss or unp or m1h)

        # None
        c0 = pt.parse_cache_creation({"cache_creation": None})
        self.assertEqual(c0["tokens_5m"], 0)
        self.assertFalse(c0["usage_unparsed"])

        # 嵌套 dict：5m + 1h
        nested = {
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 1000,
                "ephemeral_1h_input_tokens": 50,
            },
            "cache_read_input_tokens": 0,
        }
        cn = pt.parse_cache_creation(nested)
        self.assertEqual(cn["tokens_5m"], 1000)
        self.assertTrue(cn["usage_unparsed"])
        self.assertTrue(cn["price_missing_1h"])
        usd_n, miss_n, unp_n, m1h_n = pt._est_usd_for_usage(
            nested, model="claude-haiku-5-5", prices=prices
        )
        self.assertFalse(miss_n)
        self.assertTrue(unp_n and m1h_n)
        self.assertIsNotNone(usd_n)  # 已识别部分仍计价

        # 优先 cache_creation_input_tokens 总数
        prefer = {
            "cache_creation_input_tokens": 777,
            "cache_creation": {"ephemeral_5m_input_tokens": 1},
        }
        self.assertEqual(pt.parse_cache_creation(prefer)["tokens_5m"], 777)

        # 未知结构
        unk = pt.parse_cache_creation({"cache_creation": ["weird"]})
        self.assertEqual(unk["tokens_5m"], 0)
        self.assertTrue(unk["usage_unparsed"])
        usd_u, miss_u, unp_u, _ = pt._est_usd_for_usage(
            {"input": 0, "output": 0, "cache_creation": {"weird_key": 9}, "cache_read": 0},
            model="claude-haiku-5-5",
            prices=prices,
        )
        self.assertFalse(miss_u)
        self.assertTrue(unp_u)
        self.assertEqual(usd_u, 0.0)

        # _normalize_tokens 对嵌套 dict 不崩
        class _Ctx:
            tokens = {"step3": nested}
            models = {"step3": {"request_model": "claude-haiku-5-5"}}

        toks, any_unp, any_1h = pt._normalize_tokens(_Ctx())
        self.assertEqual(toks["step3"]["cache_creation"], 1000)
        self.assertTrue(any_unp and any_1h)

    def test_retrieval_real_refuses_when_env_missing(self):
        # setUp 已清相关键
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "prices_ok.json"
            _write_prices(fake, status="已核实")
            rc = pt.main(
                [
                    "--dry-run",
                    "--retrieval",
                    "real",
                    "--only-ids",
                    "D01",
                    "--max-questions",
                    "1",
                    "--prices-file",
                    str(fake),
                    "--out",
                    td,
                ]
            )
        self.assertEqual(rc, 2)

    def test_qa4_env_file_not_set_is_noop(self):
        os.environ.pop("QA4_ENV_FILE", None)
        marker = "QA4_ES_URL"
        self.assertIsNone(os.environ.get(marker))
        self.assertIsNone(pt.load_qa4_env_file_if_set())
        self.assertIsNone(os.environ.get(marker))

    def test_qa4_env_file_loads_when_set(self):
        with tempfile.TemporaryDirectory() as td:
            env_path = Path(td) / "trial.env"
            env_path.write_text(
                "QA4_ES_URL=http://envfile.example:9202\nQA4_ES_PASSWORD=not-a-secret-for-test\n",
                encoding="utf-8",
            )
            os.environ["QA4_ENV_FILE"] = str(env_path)
            loaded = pt.load_qa4_env_file_if_set()
            self.assertEqual(loaded, env_path)
            self.assertEqual(os.environ.get("QA4_ES_URL"), "http://envfile.example:9202")

    def test_qa4_env_file_fill_me_refuses_real(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            env_path = td_path / "trial.env"
            lines = []
            for k in pt._REAL_RETRIEVAL_ENV:
                if k.endswith("_URL") or k.endswith("_URI"):
                    lines.append(f"{k}=http://127.0.0.1:9")
                else:
                    lines.append(f"{k}=__FILL_ME__")
            # Neo4j URI 用 bolt
            lines = [
                "QA4_ES_URL=http://127.0.0.1:9202",
                "QA4_ES_PASSWORD=__FILL_ME__",
                "QA4_EMBED_BASE_URL=http://127.0.0.1:1",
                "QA4_EMBED_API_KEY=__FILL_ME__",
                "QA4_RERANK_BASE_URL=http://127.0.0.1:1",
                "QA4_RERANK_API_KEY=__FILL_ME__",
                "QA4_NEO4J_URI=bolt://127.0.0.1:7689",
                "QA4_NEO4J_PASSWORD=__FILL_ME__",
            ]
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.environ["QA4_ENV_FILE"] = str(env_path)
            fake = td_path / "prices_ok.json"
            _write_prices(fake, status="已核实")
            rc = pt.main(
                [
                    "--dry-run",
                    "--retrieval",
                    "real",
                    "--only-ids",
                    "D01",
                    "--max-questions",
                    "1",
                    "--prices-file",
                    str(fake),
                    "--out",
                    str(td_path / "out"),
                ]
            )
            self.assertEqual(rc, 2)
            # 载入后应能检出尚未填写（不断言具体密钥值）
            self.assertTrue(pt.unfilled_real_retrieval_env())

    def test_dry_run_records_retrieval_mode_fake(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fake = td_path / "prices_ok.json"
            out_dir = td_path / "out"
            out_dir.mkdir()
            _write_prices(fake, status="已核实")
            rc = pt.main(
                [
                    "--dry-run",
                    "--retrieval",
                    "fake",
                    "--only-ids",
                    "D01",
                    "--max-questions",
                    "1",
                    "--prices-file",
                    str(fake),
                    "--out",
                    str(out_dir),
                ]
            )
            self.assertEqual(rc, 0)
            path = next(out_dir.glob("dry_run_*.jsonl"))
            rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(rec.get("retrieval_mode"), "fake")
            summary = json.loads(next(out_dir.glob("summary_*.json")).read_text(encoding="utf-8"))
            self.assertEqual(summary.get("retrieval_mode"), "fake")


if __name__ == "__main__":
    unittest.main()
