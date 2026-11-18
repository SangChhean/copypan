# -*- coding: utf-8 -*-
"""假检索 / 假 ES（离线）。

FakeRetrievalService：按关键词在 tests/fixtures/fake_passages.json 里返回段落，接口同 RetrievalService。
FakeSearchES：最小 ES 替身，支持 search(index, body) 的 bool.filter.term/terms 与 size，
           可注入乱序、缺段，供定向取篇与查询体测试。
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Optional

from retrieval.config import actual_index, index_map
from retrieval.dedupe import dedupe
from retrieval.scope import decide_scope
from retrieval.service import to_passage
from retrieval.types import RetrievalResult, SubQuestionSpec

_BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = _BACKEND / "tests" / "fixtures" / "fake_passages.json"


def load_fixture(path: Optional[Path] = None) -> list[dict[str, Any]]:
    data = json.loads(Path(path or DEFAULT_FIXTURE).read_text(encoding="utf-8"))
    return list(data.get("passages") or [])


class FakeRetrievalService:
    def __init__(self, passages: list[dict[str, Any]]) -> None:
        self.passages = passages
        self.calls: list[SubQuestionSpec] = []

    @classmethod
    def from_default_fixture(cls) -> "FakeRetrievalService":
        return cls(load_fixture())

    def _match(self, terms: list[str], indices: list[str], author: Optional[str]) -> list[dict[str, Any]]:
        out = []
        for p in self.passages:
            if p["_logical"] not in indices:
                continue
            if author and p.get("author") and p.get("author") != author:
                continue
            kws = set(p.get("keywords") or [])
            text = p.get("text") or ""
            # 词在 keywords / 正文里，或 keywords 是查询串的子串（假检索按关键词驱动）
            if any(
                t
                and (
                    t in kws
                    or t in text
                    or any(kw and kw in t for kw in kws)
                )
                for t in terms
            ):
                out.append(dict(p))
        return out

    async def retrieve(self, spec: SubQuestionSpec) -> RetrievalResult:
        self.calls.append(spec)
        res = RetrievalResult(coverage={"routes": {}})
        if spec.synthesis:
            res.synthesis = True
            return res
        dec = decide_scope(spec, year_table=None)
        if dec.none_flag:
            res.none_flag = dec.none_flag
            return res
        indices = dec.indices
        res.scope = list(indices)
        routes = [("main", [spec.query] + list(spec.layer1_words))]
        routes += [(f"词名:{w}", [w]) for w in spec.words]
        if spec.relaxed and spec.original_question:
            routes.append(("original", [spec.original_question]))
        collected: list[dict[str, Any]] = []
        seen: set = set()
        for route, terms in routes:
            hits = self._match(terms, indices, spec.author)
            res.coverage["routes"][route] = {"fake": len(hits)}
            for h in hits:
                if h["_id"] in seen:
                    continue
                seen.add(h["_id"])
                h["_route"] = route
                collected.append(h)
        kept, stats = dedupe(collected, per_message_cap=3, bible=None)
        cap = int(spec.cap or 20)
        kept = kept[:cap]
        res.coverage["kept"] = len(kept)
        res.coverage["dedupe"] = stats
        res.passages = [to_passage(d) for d in kept]
        return res


class FakeSearchES:
    """最小 ES 替身：docs 按 actual index 存放；忽略打分，按插入顺序（可打乱）。"""

    def __init__(self, docs_by_logical: dict[str, list[dict[str, Any]]], *, shuffle_seed: Optional[int] = None) -> None:
        self.docs: dict[str, list[dict[str, Any]]] = {}
        for lg, docs in docs_by_logical.items():
            arr = [dict(d) for d in docs]
            if shuffle_seed is not None:
                random.Random(shuffle_seed).shuffle(arr)
            self.docs[actual_index(lg)] = arr
        self.bodies: list[tuple[str, dict[str, Any]]] = []

    @staticmethod
    def _get(doc: dict[str, Any], field: str) -> Any:
        return doc.get(field.split(".")[0])

    def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        self.bodies.append((index, body))
        docs = self.docs.get(index, [])
        flt = (((body.get("query") or {}).get("bool") or {}).get("filter")) or []
        if "knn" in body:
            flt = (body["knn"].get("filter")) or []
        matched = []
        for d in docs:
            ok = True
            for clause in flt:
                if "term" in clause:
                    (f, v), = clause["term"].items()
                    ok = ok and self._get(d, f) == v
                elif "terms" in clause:
                    (f, vs), = clause["terms"].items()
                    ok = ok and self._get(d, f) in vs
            if ok:
                matched.append(d)
        size = int(body.get("size") or 10)
        hits = [
            {"_id": d.get("_id") or d.get("chunk_id"), "_score": 1.0, "_source": {k: v for k, v in d.items() if k != "_id"}}
            for d in matched[:size]
        ]
        return {"hits": {"total": {"value": len(matched)}, "hits": hits}}


def known_logical_indices() -> list[str]:
    return list(index_map().keys())
