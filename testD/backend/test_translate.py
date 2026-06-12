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
from testD.backend.additional_pool import (
    append_records,
    normalize_zh,
    reload_pool,
    zh_contains,
    zh_eq,
    zh_fuzzy_eq,
)
from testD.backend.source_translator import (
    _split_sources,
    format_source_zh,
    parse_source_from_line,
)
from testD.backend.enhanced_translate_service import (
    _RetrievalCtx,
    _detect_line_type,
    _pool_hit_matches_outline_body,
    _precompute_line_types,
    _retrieve_line,
    _split_body,
    _strip_scripture_suffix,
    _strip_title_prefix,
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
    assert _detect_line_type("第二篇　亚当") == "title"
    assert _detect_line_type("读经：罗五14") == "bible-reading"
    assert _detect_line_type("读经罗五14", prev_line_type="title") == "bible-reading"
    assert _detect_line_type("读经罗五14", prev_line_type="outline") == "reference"
    assert _strip_title_prefix("第二篇　亚当") == "亚当"
    types = _precompute_line_types(["第二篇　亚当", "读经罗五14"])
    assert types == ["title", "bible-reading"]

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


def test_zh_fuzzy_eq():
    short = "神乃是灵住在人的灵里作人的生命"
  # 1 字差异（灵→靈 normalize 后相同；用未入表的异体字模拟）
    assert zh_fuzzy_eq(short, short.replace("灵", "靈", 1))
    assert zh_eq(short, short.replace("灵", "靈", 1))
    typo = short[:10] + "X" + short[11:]
    assert zh_fuzzy_eq(short, typo)
    assert not zh_eq(short, typo)
    # 短句：6 字差异不命中（阈值 5）
    assert not zh_fuzzy_eq("一二三四五六七八九十", "一二三四五六九八七六五四三二")
    block24 = "一" * 10 + "二" * 4 + "三" * 10
    assert not zh_fuzzy_eq(block24, "一" * 10 + "四" * 4 + "三" * 10)
    # 长句 >30：≤8 连续块仍允许
    long_a = "一" * 35
    long_b = "一" * 27 + "二" * 8
    assert zh_fuzzy_eq(long_a, long_b)
    assert not zh_fuzzy_eq(long_a, "二" * 35)


def test_split_sources():
    single = _split_sources("2000年安那翰秋季全时间训练，第二篇")
    assert single == ["2000年安那翰秋季全时间训练，第二篇"]

    two_semi = _split_sources(
        "2000年安那翰秋季全时间训练，第二篇；新约总论，第四十一篇，第十五段*"
    )
    assert len(two_semi) == 2
    assert two_semi[0].startswith("2000年")
    assert two_semi[1].startswith("新约总论")

    # 分隔符不规范：用逗号连接第二条
    two_comma = _split_sources(
        "2000年安那翰秋季全时间训练，第二篇，新约总论，第四十一篇"
    )
    assert len(two_comma) == 2
    assert two_comma[1].startswith("新约总论")

    three = _split_sources("2000年第一篇；新约总论，第四十一篇；腓立比书生命读经，第一篇")
    assert len(three) == 3

    nested = _split_sources(
        "倪柝声文集第一辑第五册，基督徒报（卷三）（六）非拉铁非（忠心小群）"
    )
    assert len(nested) == 1
    assert "非拉铁非" in nested[0]

    assert _split_sources("创二8～9。") == []


def test_parse_source_from_line():
    nested1 = "纲要正文。（倪柝声文集第一辑第五册，基督徒报（卷三）（六）非拉铁非（忠心小群））"
    stripped1, src1 = parse_source_from_line(nested1)
    assert stripped1 == "纲要正文。"
    assert src1 == [
        "倪柝声文集第一辑第五册，基督徒报（卷三）（六）非拉铁非（忠心小群）"
    ]
    assert format_source_zh(src1).startswith("（倪柝声文集")

    nested2 = "二　要点。（倪柝声文集第二辑第十二册，敞开的门（卷二），敞开的门（卷二）第十六期）"
    stripped2, src2 = parse_source_from_line(nested2)
    assert stripped2 == "二　要点。"
    assert len(src2) == 1
    assert src2[0].startswith("倪柝声文集")

    plain = "（李常受文集一九七二年第二册，国度，第四十章）"
    line_plain = f"正文{plain}"
    stripped_plain, src_plain = parse_source_from_line(line_plain)
    assert stripped_plain == "正文"
    assert src_plain == ["李常受文集一九七二年第二册，国度，第四十章"]

    multi = (
        "要点。（2000年安那翰秋季全时间训练，第二篇；新约总论，第四十一篇，第十五段*）"
    )
    stripped_multi, src_multi = parse_source_from_line(multi)
    assert stripped_multi == "要点。"
    assert len(src_multi) == 2

    no_source = "神乃是灵，住在人的里面。"
    assert parse_source_from_line(no_source) == (no_source, [])

    fake_paren = "说明（不是出处格式）继续"
    assert parse_source_from_line(fake_paren) == (fake_paren, [])

    scripture_paren = "经文说明。（创二8～9。）"
    assert parse_source_from_line(scripture_paren) == (scripture_paren, [])

    # 正文含（犹3）等括号，出处应在行末被剥离
    mid_paren = (
        "二 神不是呼召我们去发明更好于祂在圣经里所启示的教会组织，"
        "祂的命令乃是要我们按着一次交给圣徒的真道而行（犹3）。"
        "（倪柝声文集第一辑第五册，基督徒报（卷三），（五）撒狄（更正的教会））"
    )
    stripped_mid, src_mid = parse_source_from_line(mid_paren)
    assert "（倪柝声文集" not in stripped_mid
    assert "（犹3）" in stripped_mid
    assert src_mid[0].startswith("倪柝声文集")

    after_verse = (
        "一 圣经自己的见证是说，“圣经都是神所默示的”（提后三16～17）。"
        "（倪柝声文集第一辑第五册，基督徒报（卷三），默想启示录（中卷），（四）推雅推喇（罗马的教会））"
    )
    stripped_av, src_av = parse_source_from_line(after_verse)
    assert "（倪柝声文集" not in stripped_av
    assert "（提后三16～17）" in stripped_av
    assert "推雅推喇" in src_av[0]


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

    async def mock_retrieve_line(line_i, line, ctx, **kwargs):
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

    async def mock_pool_lookup(_clause, *, fuzzy=False):
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
        result = await _retrieve_line(0, line, ctx, line_type="reference")

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

    async def mock_pool_lookup(_clause, *, fuzzy=False):
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
        result = await _retrieve_line(0, line, ctx, line_type="outline")

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


async def _run_title_and_bible_reading_retrieval_test():
    title_line = "第二篇　亚当"
    bible_line = "读经：罗五14，林前十五45"

    async def mock_pool_lookup_hit(_clause, *, fuzzy=False):
        return None

    async def mock_pool_recall(_query, top_k=300):
        return []

    async def mock_enrich(hit, ctx):
        return hit

    with (
        patch(
            "testD.backend.enhanced_translate_service._pool_lookup_hit",
            side_effect=mock_pool_lookup_hit,
        ),
        patch(
            "testD.backend.enhanced_translate_service._pool_recall_hits",
            side_effect=mock_pool_recall,
        ),
        patch(
            "testD.backend.enhanced_translate_service.recall_local_pool_hits",
            return_value=[{
                "zh": "第二篇　亚当的堕落与神的和好",
                "text": "第二篇　亚当的堕落与神的和好",
                "en": "Outlines (2) The Fall of Adam and Reconciliation with God",
            }],
        ),
        patch(
            "testD.backend.enhanced_translate_service._enrich_hit_en",
            side_effect=mock_enrich,
        ),
    ):
        ctx = _RetrievalCtx.create()
        title_result = await _retrieve_line(0, title_line, ctx, line_type="title")
        bible_result = await _retrieve_line(1, bible_line, ctx, line_type="bible-reading")

    assert title_result["retrieval_failed"] is False
    assert title_result["needs_batch"] is True
    assert len(title_result["deduped_refs"]) >= 1
    assert bible_result["retrieval_failed"] is False
    assert bible_result["needs_batch"] is True
    assert bible_result["deduped_refs"] == []


def test_title_and_bible_reading_retrieval():
    asyncio.run(_run_title_and_bible_reading_retrieval_test())


if __name__ == "__main__":
    test_parse_line()
    test_split_body()
    test_normalize_zh()
    test_zh_eq_and_contains()
    test_zh_fuzzy_eq()
    test_split_sources()
    test_parse_source_from_line()
    test_pool_hit_matches_outline_body()
    test_pool_skip_gemini()
    test_reference_retrieval_path()
    test_outline_two_phase_retrieval()
    test_title_and_bible_reading_retrieval()
    print("全部测试通过")
