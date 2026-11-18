# -*- coding: utf-8 -*-
"""假后端 / 流水线事件契约（新增）：【错引】标记、【拆】【敏感】plan、direct meta。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QA4_LLM_MODE", "fake")
os.environ.setdefault("QA4_RETRIEVAL_MODE", "fake")
os.environ.setdefault("QA4_PROMPT_CHANNEL", "draft")
os.environ.setdefault("QA4_JWT_SECRET", "dev-fake-jwt-not-a-real-secret")
os.environ.pop("QA4_ANTHROPIC_API_KEY", None)

from config import get_settings, reset_settings_cache
from core.neo4j_client import FakeNeo4jClient
from core.redis_store import MemoryStore
from pipeline.deps import build_deps
from pipeline.orchestrator import run_pipeline
from tools.dev_server_fake import SeededFakeEs, _targeted_with_seeds


class TestDevFakeStreamContract(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        reset_settings_cache()
        cls.settings = get_settings(require_runtime=False)
        tmp = Path(tempfile.mkdtemp(prefix="qa4_fake_contract_"))
        cls.settings.traces_db_path = tmp / "t.db"
        es = SeededFakeEs(reachable=True)
        cls.deps = build_deps(
            cls.settings,
            store=MemoryStore(prefix="c:"),
            es=es,
            neo4j=FakeNeo4jClient(reachable=True),
            traces_db=tmp / "t.db",
        )
        cls.deps.targeted = _targeted_with_seeds(cls.deps)

    async def _collect(self, q: str) -> list[dict]:
        out = []
        async for ev in run_pipeline(self.deps, question=q, history=[]):
            out.append(ev)
        return out

    async def test_wrong_quote_marked_in_done_answer(self):
        evs = await self._collect("【错引】什么是神的经纶？")
        done = next(e for e in evs if e.get("event") == "done")
        # 契约：字段名是 answer（不是 answer_text）；含核对结果与标记
        self.assertIn("answer", done)
        self.assertNotIn("answer_text", done)
        self.assertIn("〔未核实〕", done.get("answer") or "")
        checks = done.get("quote_checks") or []
        self.assertTrue(any(not c.get("ok") for c in checks))

    async def test_split_and_sensitive_plan_fields(self):
        evs = await self._collect("【拆】什么是神的爱？")
        plan = next(e for e in evs if e.get("event") == "plan")
        self.assertTrue(plan.get("complex"))
        self.assertGreaterEqual(len(plan.get("subquestions") or []), 2)

        evs2 = await self._collect("【敏感】怎样看宗派？")
        plan2 = next(e for e in evs2 if e.get("event") == "plan")
        self.assertTrue(plan2.get("sensitive"))

    async def test_scripture_verse_data_or_direct_title(self):
        """经文优先 verse_data（3.0 同形）；无 bible_data 时仍可回退 direct。"""
        evs = await self._collect("约3:16")
        vds = [e for e in evs if e.get("event") == "verse_data"]
        directs = [e for e in evs if e.get("event") == "direct"]
        if vds:
            data = vds[0].get("data") or {}
            if "verses" in data:
                self.assertTrue(data["verses"])
                row = data["verses"][0]
            else:
                row = data
            self.assertTrue(row.get("book") or row.get("ref_gb") or row.get("text_gb") or row.get("text_gb_plain"))
        else:
            self.assertTrue(directs)
            meta = directs[0].get("meta") or {}
            self.assertTrue(meta.get("ref") or meta.get("book_title"))

    async def test_hymn_seeded_hymn_data_or_direct(self):
        """诗歌优先 hymn_data；无载荷时仍可回退 direct。"""
        evs = await self._collect("诗歌第15首")
        hymns = [e for e in evs if e.get("event") == "hymn_data"]
        directs = [e for e in evs if e.get("event") == "direct"]
        if hymns:
            data = hymns[0].get("data") or {}
            rows = data.get("hymns") or []
            self.assertTrue(rows, msg="hymn_data 应含 hymns")
            row = rows[0]
            self.assertTrue(
                row.get("text") or row.get("hymn_number") is not None or row.get("series_zh")
            )
        else:
            self.assertTrue(directs, msg="种子诗歌应产出 hymn_data 或 direct")
            meta = directs[0].get("meta") or {}
            self.assertTrue(
                meta.get("book_title")
                or meta.get("series")
                or meta.get("name")
                or meta.get("hymn_number") is not None
            )


if __name__ == "__main__":
    unittest.main()
