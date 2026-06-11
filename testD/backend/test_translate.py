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
from testD.backend.additional_pool import append_records, normalize_zh, reload_pool, zh_contains, zh_eq
from testD.backend.enhanced_translate_service import (
    _RetrievalCtx,
    _detect_line_type,
    _pool_hit_matches_outline_body,
    _retrieve_line,
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

    # Pool 语料常见「：─引用经文」占位后缀；用户输入无此后缀时 body 须能与之对齐
    pool_line = (
        "2　在马太二十四章三十七至三十九节和路加十七章二十六至二十七节，"
        "主耶稣把我们这世代比作挪亚的日子：─引用经文"
    )
    _, pool_body, pool_suffix = _strip_scripture_suffix(pool_line)
    assert "引用经文" in pool_suffix
    assert pool_body == (
        "在马太二十四章三十七至三十九节和路加十七章二十六至二十七节，"
        "主耶稣把我们这世代比作挪亚的日子"
    )
    user_line = (
        "２ 在马太二十四章三十七至三十九节和路加十七章二十六至二十七节，"
        "主耶稣把我们这世代比作挪亚的日子。"
    )
    _, user_body, user_suffix = _strip_scripture_suffix(user_line)
    assert user_suffix == ""
    assert normalize_zh(user_body) == normalize_zh(pool_body)


def test_zh_eq_and_contains():
    assert zh_eq("神圣的生命", "神聖的生命")
    assert zh_eq("豫表", "预表")
    assert zh_contains("巴路西亚要在那时开始", "但祂的巴路西亚要在那时开始。")
    assert not zh_contains("abc", "")


def test_split_body():
    assert _split_body("神圣的生命；基督的经历") == ["神圣的生命", "基督的经历"]
    assert _split_body("职事的路") == ["职事的路"]
    assert _split_body("") == []


def test_normalize_zh():
    assert normalize_zh("一\t生命") == "一生命"
    assert normalize_zh("神圣的生命，") == "神圣的生命"


def test_pool_hit_matches_outline_body():
    body = "要开始于初熟果子被带到三层天上的时候；那时，就一面说，主不会离开三层天，但祂的巴路西亚要在那时开始"
    long_cwwl = (
        "多年前，因着倪柝声弟兄的帮助，我们出版了一些论到被提的文章。按照我们的研读，我们看见主的同在，"
        "就是祂的巴路西亚，要开始于初熟果子被带到三层天上的时候。那时，就一面说，主不会离开三层天，"
        "但祂的巴路西亚要在那时开始。主的巴路西亚至少要持续三年半之久。"
    )
    assert _pool_hit_matches_outline_body(
        body,
        {"_index": "cwwl", "zh": long_cwwl, "en": "Many years ago..."},
    )
    assert not _pool_hit_matches_outline_body(
        body,
        {"_index": "feasts", "zh": long_cwwl, "en": "Feasts..."},
    )
    assert _pool_hit_matches_outline_body(
        body,
        {
            "_index": "feasts",
            "zh": f"2\u3000{body}：─引用经文",
            "en": "2. To begin...",
        },
    )


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


async def _run_reference_retrieval_path_test():
    """reference：Pool 300 子串未中 → BM25 top1 + 分句 BM25，无 dense/rerank/feasts。"""
    line = "神乃是灵"
    dense_called = False
    rerank_called = False

    async def mock_pool_lookup(_clause):
        return None

    async def mock_pool_recall_hits(_query, top_k=300):
        return []

    async def mock_bm25_hits(query, index, top_k=40):
        if top_k == 1 and query == line:
            return [{"chunk_id": "c1", "text": "神乃是灵", "en": "God is Spirit"}]
        return []

    async def mock_dense_hits(query, ctx, top_k=40):
        nonlocal dense_called
        dense_called = True
        return []

    async def mock_enrich(hit, ctx):
        return hit

    async def mock_rerank(*_args, **_kwargs):
        nonlocal rerank_called
        rerank_called = True
        return []

    with (
        patch(
            "testD.backend.enhanced_translate_service._pool_lookup",
            side_effect=mock_pool_lookup,
        ),
        patch(
            "testD.backend.enhanced_translate_service._pool_recall_hits",
            side_effect=mock_pool_recall_hits,
        ),
        patch(
            "testD.backend.enhanced_translate_service._bm25_hits",
            side_effect=mock_bm25_hits,
        ),
        patch(
            "testD.backend.enhanced_translate_service._dense_hits",
            side_effect=mock_dense_hits,
        ),
        patch(
            "testD.backend.enhanced_translate_service._enrich_hit_en",
            side_effect=mock_enrich,
        ),
        patch(
            "testD.backend.enhanced_translate_service.rerank",
            side_effect=mock_rerank,
        ),
    ):
        ctx = _RetrievalCtx.create()
        result = await _retrieve_line(0, line, ctx)

    assert result["line_type"] == "reference"
    assert not dense_called
    assert not rerank_called
    assert len(result["line_refs"]) == 1
    assert len(result["deduped_refs"]) == 1
    assert result["needs_batch"] is True
    assert result["line_refs"][0]["match_kind"] == "retrieved"
    assert result["retrieval_failed"] is False


def test_reference_retrieval_path():
    asyncio.run(_run_reference_retrieval_path_test())


async def _run_outline_two_phase_retrieval_test():
    """outline 行：主参考 + 子句参考，source_type / clauses 字段正确。"""
    line = "一　神是灵；神是爱"
    rrf_bm25_weight: float | None = None
    main_rerank_top_k: int | None = None

    async def mock_pool_lookup(_clause):
        return None

    async def mock_outline_body_pool_exact(_body):
        return [], []

    async def mock_bm25_hits(query, index, top_k=40):
        if query == "神是灵；神是爱":
            return [{"chunk_id": "main-bm25", "text": "纲目总述", "en": "Main BM25"}]
        if query == "神是灵":
            return [{"chunk_id": "clause-1", "text": "神是灵子句", "en": "Clause1 EN"}]
        if query == "神是爱":
            return [{"chunk_id": "clause-2", "text": "神是爱子句", "en": "Clause2 EN"}]
        return []

    async def mock_dense_hits(query, ctx, top_k=40):
        return [{"chunk_id": "main-dense", "text": "dense main", "en": "Main Dense"}]

    async def mock_enrich(hit, ctx):
        return hit

    async def mock_rrf_merge(bm25_bucket, dense_bucket, **kwargs):
        nonlocal rrf_bm25_weight
        rrf_bm25_weight = kwargs.get("bm25_weight")
        return bm25_bucket + dense_bucket

    async def mock_rerank(merged, query, top_k):
        nonlocal main_rerank_top_k
        if query == "神是灵；神是爱":
            main_rerank_top_k = top_k
            return [merged[0]] if merged else []
        return []

    with (
        patch(
            "testD.backend.enhanced_translate_service._pool_lookup",
            side_effect=mock_pool_lookup,
        ),
        patch(
            "testD.backend.enhanced_translate_service._outline_body_pool_exact",
            side_effect=mock_outline_body_pool_exact,
        ),
        patch(
            "testD.backend.enhanced_translate_service._bm25_hits",
            side_effect=mock_bm25_hits,
        ),
        patch(
            "testD.backend.enhanced_translate_service._dense_hits",
            side_effect=mock_dense_hits,
        ),
        patch(
            "testD.backend.enhanced_translate_service.bm25_search",
            new_callable=AsyncMock,
        ),
        patch(
            "testD.backend.enhanced_translate_service._enrich_hit_en",
            side_effect=mock_enrich,
        ),
        patch(
            "testD.backend.enhanced_translate_service.rrf_merge",
            side_effect=mock_rrf_merge,
        ),
        patch(
            "testD.backend.enhanced_translate_service.rerank",
            side_effect=mock_rerank,
        ),
    ):
        ctx = _RetrievalCtx.create()
        result = await _retrieve_line(0, line, ctx)

    assert result["line_type"] == "outline"
    assert rrf_bm25_weight == 1.5
    assert main_rerank_top_k == 1
    assert len(result["line_refs"]) >= 2
    assert result["line_refs"][0]["source_type"] == "main"
    assert result["line_refs"][0]["clauses"] == []

    clause_refs = [r for r in result["line_refs"] if r.get("source_type") == "clause"]
    assert len(clause_refs) >= 1
    assert clause_refs[0]["clauses"]
    assert result["line_refs"][0]["chunk_id"] != clause_refs[0]["chunk_id"]


def test_outline_two_phase_retrieval():
    asyncio.run(_run_outline_two_phase_retrieval_test())


if __name__ == "__main__":
    test_parse_line()
    test_split_body()
    test_normalize_zh()
    test_zh_eq_and_contains()
    test_pool_hit_matches_outline_body()
    test_pool_skip_gemini()
    test_reference_retrieval_path()
    test_outline_two_phase_retrieval()
    print("全部测试通过")
