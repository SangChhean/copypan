# -*- coding: utf-8 -*-
"""反找经文：词 → 经文清单（来源 graph / 3a / bible_vector）。

顺序：图谱 SUPPORTED_BY → 3a 读经行（整行解析）→ qa4_bible 向量检索后备。
合并去重用 Ref.key()，保留全部来源标签；排序按首个来源的先后，再按出现顺序。
后备触发【暂定】：图谱 + 3a 去重后少于 retrieval.json reverse.bible_vector_when_below 条才查 bible。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from scripture.normalize import Ref, parse_refs, reading_line_of

SOURCE_ORDER = {"graph": 0, "3a": 1, "bible_vector": 2}


@dataclass
class ScriptureHit:
    ref: Ref
    sources: list[str] = field(default_factory=list)
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.ref.label(),
            "key": list(self.ref.key()),
            "kind": self.ref.kind,
            "sources": list(self.sources),
            "rank": self.rank,
            "flags": list(self.ref.flags),
        }


class ReverseFinder:
    def __init__(
        self,
        *,
        graph: Any = None,
        definitions: Any = None,
        retrieval: Any = None,
        bible: Any = None,
        cfg: Optional[dict[str, Any]] = None,
    ) -> None:
        self.graph = graph
        self.definitions = definitions
        self.retrieval = retrieval
        self.bible = bible
        if cfg is None:
            from retrieval.config import retrieval_cfg

            cfg = retrieval_cfg()
        self.rcfg = dict(cfg.get("reverse") or {})

    def _parse(self, text: str) -> list[Ref]:
        return parse_refs(text, bible=self.bible, validate=self.bible is not None)

    async def find(self, term: str) -> dict[str, Any]:
        hits: dict[tuple, ScriptureHit] = {}
        order: list[tuple] = []
        counts = {"graph": 0, "3a": 0, "bible_vector": 0}

        def add(refs: list[Ref], source: str) -> None:
            for r in refs:
                k = r.key()
                if k not in hits:
                    hits[k] = ScriptureHit(ref=r, sources=[source])
                    order.append(k)
                elif source not in hits[k].sources:
                    hits[k].sources.append(source)
                counts[source] += 1

        if self.graph is not None:
            for raw in self.graph.supported_by(term) or []:
                add(self._parse(raw), "graph")
        if self.definitions is not None:
            line = reading_line_of(self.definitions.content_3a(term))
            if line:
                add(self._parse(line), "3a")
        used_vector = False
        if self.retrieval is not None and len(hits) < int(self.rcfg.get("bible_vector_when_below", 3)):
            from retrieval.types import SubQuestionSpec

            used_vector = True
            res = await self.retrieval.retrieve(
                SubQuestionSpec(query=term, scope_override=["bible"], cap=int(self.rcfg.get("bible_vector_top", 10)))
            )
            for p in res.passages:
                vr = str(p.location.get("verse_range") or "")
                add(self._parse(f"{p.book_title}{vr}"), "bible_vector")
        ranked = sorted(
            (hits[k] for k in order),
            key=lambda h: (SOURCE_ORDER.get(h.sources[0], 9), order.index(h.ref.key())),
        )
        for i, h in enumerate(ranked, 1):
            h.rank = i
        return {
            "term": term,
            "hits": [h.to_dict() for h in ranked],
            "counts": counts,
            "used_bible_vector": used_vector,
        }
