# -*- coding: utf-8 -*-
"""对外检索入口：retrieve(spec) -> RetrievalResult。

路：main（子问题文本）；每个推荐词各开一路（route=词名:<w>）；放宽模式再加 original（用户原话）。
每路在范围内各索引上跑 BM25 + knn；所有列表一起 RRF；融合后精排前 rerank_top；去重；截断。
软优先：先在优先范围取，不够上限再补其余范围，补的排在后面。
放宽模式：去掉软优先；追加原话一路；每个推荐词各自单独检索（不与主路混合精排）；合并去重；硬限定不放宽。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from retrieval.config import field_name, index_cfg, params, retrieval_cfg
from retrieval.dedupe import dedupe
from retrieval.es_search import build_bm25_body, build_knn_body, run_search
from retrieval.fusion import doc_key, rerank_docs, rrf
from retrieval.scope import ScopeDecision, decide_scope
from retrieval.types import Passage, RetrievalResult, SubQuestionSpec, stable_id

logger = logging.getLogger("qa4.retrieval")


def to_passage(d: dict[str, Any], cfg: Optional[dict] = None) -> Passage:
    lg = d.get("_logical") or ""

    def f(key: str) -> Any:
        name = field_name(lg, key, cfg)
        return d.get(name.split(".")[0]) if name else None

    loc: dict[str, Any] = {}
    for key in (
        "message_number",
        "section_title",
        "source_zh",
        "source_en",
        "verse_range",
        "hymn_number",
        "series",
        "order",
    ):
        v = f(key)
        if v not in (None, ""):
            loc[key] = v
    # source_en 在 mapping 中常为 index:false；若配置未声明字段名，仍从 _source 直取
    if "source_en" not in loc and d.get("source_en") not in (None, ""):
        loc["source_en"] = d.get("source_en")
    meta: dict[str, Any] = {}
    for key in ("author", "year", "year_end", "message_key", "conference", "month", "chunk_type", "unit_type", "total"):
        v = f(key)
        if v not in (None, ""):
            meta[key] = v
    meta["routes"] = list(d.get("_routes") or ([d.get("_route")] if d.get("_route") else []))
    title = f("book_title") or f("name") or ""
    tf = (index_cfg(lg, cfg).get("text_field") or "text")
    return Passage(
        id=stable_id(lg, str(d.get("_id") or ""), str(d.get(tf) or "")),
        index=lg,
        book_title=str(title or ""),
        message_title=str(f("message_title") or f("title") or ""),
        location=loc,
        text=str(d.get(tf) or ""),
        route=str(d.get("_route") or "main"),
        meta=meta,
        score=float(d.get("_rrf") or d.get("_score") or 0.0),
    )


class RetrievalService:
    def __init__(
        self,
        es: Any,
        embedder: Any,
        reranker: Any,
        *,
        year_table: Any = None,
        bible: Any = None,
        cfg: Optional[dict[str, Any]] = None,
    ) -> None:
        self.es = es
        self.embedder = embedder
        self.reranker = reranker
        self.year_table = year_table
        self.bible = bible
        self.cfg = cfg or retrieval_cfg()
        self.p = params(self.cfg)

    # ---------------- 底层：一路在若干索引上 ----------------
    async def _route_lists(
        self,
        route: str,
        query: str,
        indices: list[str],
        terms_by_index: dict[str, dict[str, list[Any]]],
        phrases: list[str],
        coverage: dict[str, Any],
    ) -> list[list[dict[str, Any]]]:
        vec: Optional[list[float]] = None
        try:
            vecs = await self.embedder.embed([query])
            vec = vecs[0] if vecs else None
        except Exception as e:
            logger.warning("嵌入失败 route=%s: %s", route, type(e).__name__)
            coverage.setdefault("degraded_reasons", []).append(f"embed:{type(e).__name__}")
        tasks = []
        labels = []
        fails = coverage.setdefault("es_failures", [])
        for lg in indices:
            terms = terms_by_index.get(lg) or {}
            tasks.append(
                run_search(
                    self.es,
                    lg,
                    build_bm25_body(
                        lg,
                        query,
                        size=self.p.get("bm25_size", 30),
                        terms=terms,
                        phrases=phrases,
                        phrase_boost=self.p.get("layer1_phrase_boost", 2.0),
                        cfg=self.cfg,
                    ),
                    failures_out=fails,
                )
            )
            labels.append((lg, "bm25"))
            if vec is not None:
                body = build_knn_body(
                    lg,
                    vec,
                    k=self.p.get("knn_k", 30),
                    num_candidates=self.p.get("knn_num_candidates", 200),
                    terms=terms,
                    cfg=self.cfg,
                )
                if body is not None:
                    tasks.append(run_search(self.es, lg, body, failures_out=fails))
                    labels.append((lg, "knn"))
        results = await asyncio.gather(*tasks)
        lists = []
        for (lg, kind), hits in zip(labels, results):
            for h in hits:
                h["_route"] = route
            c = coverage.setdefault("routes", {}).setdefault(route, {})
            c[f"{lg}.{kind}"] = len(hits)
            lists.append(hits)
        return lists

    async def _fused(
        self,
        routes: list[tuple[str, str]],
        indices: list[str],
        terms_by_index: dict[str, dict[str, list[Any]]],
        phrases: list[str],
        rerank_query: str,
        coverage: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], bool]:
        all_lists: list[list[dict[str, Any]]] = []
        per_route = await asyncio.gather(
            *[self._route_lists(r, q, indices, terms_by_index, phrases, coverage) for r, q in routes]
        )
        for lists in per_route:
            all_lists.extend(lists)
        fused = rrf(all_lists, k=int(self.p.get("rrf_k", 60)))
        coverage["fused"] = coverage.get("fused", 0) + len(fused)
        ranked, degraded = await rerank_docs(fused, rerank_query, self.reranker, int(self.p.get("rerank_top", 40)))
        coverage["reranked"] = coverage.get("reranked", 0) + len(ranked)
        return ranked, degraded

    # ---------------- 对外 ----------------
    async def retrieve(self, spec: SubQuestionSpec) -> RetrievalResult:
        res = RetrievalResult(coverage={"routes": {}})
        if spec.synthesis:
            res.synthesis = True
            return res
        dec: ScopeDecision = decide_scope(spec, year_table=self.year_table, cfg=self.cfg)
        res.scope = list(dec.indices)
        res.year_range_covered = dec.year_range_covered
        if dec.none_flag:
            res.none_flag = dec.none_flag
            return res
        cap = int(spec.cap or self.p.get("per_subquestion_cap", 20))
        phrases = [w for w in spec.layer1_words if w]
        routes: list[tuple[str, str]] = [("main", spec.query)]
        word_routes = [(f"词名:{w}", w) for w in spec.words if w]

        collected: list[dict[str, Any]] = []
        degraded_any = False

        if not spec.relaxed:
            routes += word_routes
            passes: list[tuple[list[str], dict[str, dict[str, list[Any]]]]] = []
            if dec.priority:
                pri_terms = {i: dict(dec.hard_terms.get(i) or {}) for i in dec.priority}
                for i, titles in dec.priority_terms.items():
                    if i in pri_terms:
                        from retrieval.config import filter_field

                        f = filter_field(i, "book_title", self.cfg)
                        if f and f not in pri_terms[i]:
                            pri_terms[i][f] = titles
                passes.append((dec.priority, pri_terms))
                passes.append((list(dec.indices), dict(dec.hard_terms)))
            else:
                passes.append((list(dec.indices), dict(dec.hard_terms)))
            for pi, (idxs, terms) in enumerate(passes):
                ranked, deg = await self._fused(routes, idxs, terms, phrases, spec.query, res.coverage)
                degraded_any = degraded_any or deg
                for d in ranked:
                    d["_pass"] = pi
                collected = _merge_unique(collected, ranked)
                kept, _ = dedupe(collected, per_message_cap=int(self.p.get("per_message_cap", 3)), bible=self.bible)
                if len(kept) >= cap:
                    break
        else:
            # 放宽：无软优先；main + original 一起；每个推荐词各自单独检索
            groups: list[list[tuple[str, str]]] = [routes + ([("original", spec.original_question)] if spec.original_question else [])]
            groups += [[wr] for wr in word_routes]
            for g in groups:
                ranked, deg = await self._fused(g, list(dec.indices), dict(dec.hard_terms), phrases, g[0][1], res.coverage)
                degraded_any = degraded_any or deg
                collected = _merge_unique(collected, ranked)

        kept, stats = dedupe(collected, per_message_cap=int(self.p.get("per_message_cap", 3)), bible=self.bible)
        kept = kept[:cap]
        res.coverage["dedupe"] = stats
        res.coverage["kept"] = len(kept)
        res.coverage["kept_by_route"] = _count_by(kept, "_route")
        res.coverage["kept_by_index"] = _count_by(kept, "_logical")
        res.degraded = degraded_any
        if degraded_any:
            res.degraded_reasons.append("rerank_degraded")
        res.passages = [to_passage(d, self.cfg) for d in kept]
        return res


def _merge_unique(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {doc_key(d) for d in a}
    out = list(a)
    for d in b:
        k = doc_key(d)
        if k not in seen:
            seen.add(k)
            out.append(d)
    return out


def _count_by(docs: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in docs:
        k = str(d.get(key) or "")
        out[k] = out.get(k, 0) + 1
    return out


def make_retrieval_service(settings: Any, es: Any, *, fake: Optional[bool] = None) -> Any:
    """live：真实 ES + 嵌入 + 重排；fake：FakeRetrievalService（tests/fixtures 段落集）。"""
    use_fake = fake if fake is not None else getattr(settings, "retrieval_mode", "live") == "fake"
    if use_fake:
        from retrieval.fake import FakeRetrievalService

        return FakeRetrievalService.from_default_fixture()
    from core.embedding_client import make_embedding_client
    from core.rerank_client import make_rerank_client
    from lookups.year_table import YearTable

    yt = None
    try:
        yt = YearTable.from_lookup_dir(settings.lookup_dir)
    except Exception as e:
        logger.warning("年代表加载失败: %s", type(e).__name__)
    return RetrievalService(
        es,
        make_embedding_client(settings, fake=False),
        make_rerank_client(settings, fake=False),
        year_table=yt,
    )
