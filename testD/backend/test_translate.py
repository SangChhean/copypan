# -*- coding: utf-8 -*-
"""
增强式翻译单元测试（含 Additional Pool 短路验证）。

运行：在仓库根目录执行
  python -m pytest testD/backend/test_translate.py -v
或
  python testD/backend/test_translate.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from testD.backend import additional_pool
from testD.backend.additional_pool import append_records, normalize_zh, reload_pool
from testD.backend.enhanced_translate_service import (
    _detect_line_type,
    _split_body,
    _strip_scripture_suffix,
    _translate_prefix,
    enhanced_translate,
)


def test_parse_line():
    prefix, body, suffix = _strip_scripture_suffix("一\t神圣的生命—约一1：")
    assert prefix == "一\t"
    assert body == "神圣的生命"
    assert suffix == "—约一1："
    assert _translate_prefix(prefix) == "A.\t"
    assert _detect_line_type(body, prefix) == "outline"
    assert _detect_line_type("神乃是灵") == "reference"


def test_split_body():
    assert _split_body("神圣的生命；基督的经历") == ["神圣的生命", "基督的经历"]
    assert _split_body("职事的路") == ["职事的路"]
    assert _split_body("") == []


def test_normalize_zh():
    assert normalize_zh("一\t生命") == "一生命"
    assert normalize_zh("神圣的生命，") == "神圣的生命"


async def _run_pool_skip_gemini_test():
    """Section 13.1: Additional Pool 命中行不进检索与 batch。"""
    records = [
        {"zh": "一\t生命", "en": "A.\tLife", "norm_zh": "一生命", "source": "test"},
        {"zh": "二\t职事", "en": "B.\tMinistry", "norm_zh": "二职事", "source": "test"},
    ]
    append_records(records, force=True)
    reload_pool(force=True)

    retrieve_line_ids: list[int] = []
    batch_line_ids: list[list[int]] = []

    async def mock_retrieve_line(line_i, line, ctx):
        retrieve_line_ids.append(line_i)
        return {
            "line_i": line_i,
            "line": line,
            "body": "建造",
            "suffix": "",
            "en_prefix": "",
            "line_type": "outline",
            "line_refs": [],
            "deduped_refs": [],
            "needs_batch": True,
            "line_cached_en": "",
            "pool_line_en": "",
        }

    async def mock_translate_batch(items):
        batch_line_ids.append([line_i for line_i, _, _, _ in items])
        return (
            {line_i: f"GEMINI_{line_i}" for line_i, _, _, _ in items},
            {line_i: {"in_tok": 10, "out_tok": 5} for line_i, _, _, _ in items},
        )

    probe_mock = AsyncMock()

    with (
        patch(
            "testD.backend.enhanced_translate_service._retrieve_line",
            side_effect=mock_retrieve_line,
        ),
        patch(
            "testD.backend.enhanced_translate_service._translate_batch",
            side_effect=mock_translate_batch,
        ),
        patch(
            "testD.backend.enhanced_translate_service._probe_es",
            probe_mock,
        ),
        patch("testD.backend.enhanced_translate_service.gemini_client", object()),
        patch("testD.backend.enhanced_translate_service.auto_append_enabled", return_value=False),
    ):
        content = "一\t生命\n二\t职事\n三\t建造"
        r = await enhanced_translate(content)

    assert retrieve_line_ids == [2]
    assert probe_mock.await_count == 1
    assert batch_line_ids == [[2]]

    refs = r["refs"]
    out = (r["result"] or "").splitlines()
    summary = r["summary"] or {}

    assert summary.get("additional_pool_lines") == 2
    assert refs[0]["stats"]["retrieval_skipped"] is True
    assert refs[1]["stats"]["retrieval_skipped"] is True
    assert out[0] == "A.\tLife"
    assert out[1] == "B.\tMinistry"
    assert out[2].startswith("GEMINI_")

    additional_pool._cache_by_norm.clear()
    additional_pool._cache_mtime = 0.0


def test_pool_skip_gemini():
    asyncio.run(_run_pool_skip_gemini_test())


if __name__ == "__main__":
    test_parse_line()
    test_split_body()
    test_normalize_zh()
    test_pool_skip_gemini()
    print("全部测试通过")
