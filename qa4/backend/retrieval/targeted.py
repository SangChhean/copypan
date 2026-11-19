# -*- coding: utf-8 -*-
"""定向取篇：生命读经篇、节期纲目篇、诗歌、经文、注解。

不经检索直接取；程序内显式排序（不依赖 ES 默认顺序）；核对取全。
统一返回 TargetedResult(status ∈ ok / not_found / incomplete / unknown_total / not_supported,
blocks 有序, meta)。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any, Optional

from retrieval.config import field_name, filter_field, index_cfg, params, retrieval_cfg

OK = "ok"
NOT_FOUND = "not_found"
INCOMPLETE = "incomplete"
UNKNOWN_TOTAL = "unknown_total"
NOT_SUPPORTED = "not_supported"

_STATUS_RANK = {OK: 0, UNKNOWN_TOTAL: 1, INCOMPLETE: 2, NOT_FOUND: 3, NOT_SUPPORTED: 3}

_TRAIL_INT = re.compile(r"(\d+)(?!.*\d)")

KIND_VERSE = "verse_range"
KIND_CHAPTER = "whole_chapter"
KIND_CROSS = "cross_chapter"
KIND_BOOK = "whole_book"
KIND_CHAPTER_RANGE = "chapter_range"


@lru_cache(maxsize=1)
def _scripture_cfg() -> dict[str, Any]:
    from config import load_config_json

    return load_config_json("scripture.json")


def scripture_caps() -> tuple[int, int]:
    """(max_chapters, max_verses)，默认来自 config/scripture.json。"""
    cfg = _scripture_cfg()
    return int(cfg.get("max_chapters", 10)), int(cfg.get("max_verses", 200))


def book_verse_total(bible: Any, book_no: int) -> int:
    n = 0
    for ch in range(1, int(bible.chapter_count(book_no)) + 1):
        n += int(bible.verse_count(book_no, ch))
    return n


def _verse_block(row: dict[str, Any], flags: list[Any]) -> dict[str, Any]:
    return {
        "index": "bible_data",
        "order": (int(row["chapter"]) * 1000 + int(row["verse"])),
        "ref": row.get("ref_gb"),
        "book_title": row.get("book_name"),
        "text": row.get("text_gb_plain") or row.get("text_gb") or "",
        "flags": list(flags),
    }


@dataclass
class TargetedResult:
    status: str
    blocks: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def order_value(doc: dict[str, Any], logical: str, cfg: Optional[dict] = None) -> int:
    """段序：配置里 order 字段；derive=trailing_int 时取 chunk_id 末尾数字。"""
    fmeta = ((index_cfg(logical, cfg).get("fields") or {}).get("order")) or {}
    name = fmeta.get("name") or "chunk_index"
    raw = doc.get(name)
    if fmeta.get("derive") == "trailing_int":
        m = _TRAIL_INT.search(str(raw or doc.get("_id") or ""))
        return int(m.group(1)) if m else 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def order_base_for(logical: str, cfg: Optional[dict] = None) -> int:
    """序号起点：纲目/节期为 1；诗歌 full 为 0；可由 retrieval.json order_base 覆盖。"""
    icfg = index_cfg(logical, cfg)
    if "order_base" in icfg:
        return int(icfg["order_base"])
    fmeta = ((icfg.get("fields") or {}).get("order")) or {}
    if "order_base" in fmeta:
        return int(fmeta["order_base"])
    if fmeta.get("derive") == "trailing_int":
        return 0  # text_*：无固定期望序列，base 仅作诊断
    return 1


def _worst_status(*statuses: str) -> str:
    worst = OK
    for s in statuses:
        if _STATUS_RANK.get(s, 0) > _STATUS_RANK.get(worst, 0):
            worst = s
    return worst


def analyze_orders(
    orders: list[int],
    *,
    expected_total: Optional[int],
    orders_base: int,
    hits_total: Optional[int],
    fetched: int,
    has_total_field: bool,
) -> dict[str, Any]:
    """数据驱动完整性：返回 orders_base / missing_orders / extra_orders / status 等。"""
    sorted_orders = sorted(orders)
    info: dict[str, Any] = {
        "fetched": fetched,
        "hits_total": hits_total,
        "expected_total": expected_total,
        "orders_base": orders_base,
        "orders": sorted_orders,
        "missing_orders": [],
        "extra_orders": [],
        "orders_contiguous": False,
        "duplicate_orders": [],
        "chunk_totals": [],
        "status": OK,
    }

    # 重复序号
    seen: set[int] = set()
    dups: list[int] = []
    for o in sorted_orders:
        if o in seen and o not in dups:
            dups.append(o)
        seen.add(o)
    info["duplicate_orders"] = dups

    truncated = hits_total is not None and hits_total > fetched

    if has_total_field and expected_total is not None and expected_total > 0:
        expect = set(range(orders_base, orders_base + expected_total))
        actual = set(sorted_orders)
        missing = sorted(expect - actual)
        extra = sorted(actual - expect)
        info["missing_orders"] = missing
        info["extra_orders"] = extra
        info["orders_contiguous"] = not missing and not extra and not dups
        if truncated or missing or extra or dups or fetched != expected_total:
            info["status"] = INCOMPLETE
        else:
            info["status"] = OK
        return info

    # 无总段数字段（text_* 等）：不能把断档当缺口
    if truncated or dups:
        info["status"] = INCOMPLETE
        info["possibly_incomplete"] = True
        if truncated:
            info["total_note"] = "命中数大于取回数（可能被 targeted_max_size 截断）"
        if dups:
            info["total_note"] = (info.get("total_note") or "") + "；同篇序号重复"
        return info

    info["status"] = UNKNOWN_TOTAL
    info["possibly_incomplete"] = False
    info["total_note"] = (
        "该索引无总段数字段；chunk_id 末尾数字作序；断档为源编号特性（heading/空段跳过、短段合并），"
        "不代表正文缺失；仅按 ES 命中总数核对"
    )
    info["orders_contiguous"] = False
    return info


def _block(doc: dict[str, Any], logical: str, cfg: Optional[dict] = None) -> dict[str, Any]:
    tf = index_cfg(logical, cfg).get("text_field") or "text"
    out = {
        "index": logical,
        "id": doc.get("_id") or doc.get("chunk_id"),
        "order": order_value(doc, logical, cfg),
        "book_title": doc.get("book_title") or doc.get("name"),
        "message_title": doc.get("message_title") or doc.get("title"),
        "message_number": doc.get("message_number"),
        "text": doc.get(tf) or "",
    }
    # source_en / source_zh 从 _source 直取（常为 index:false）
    for k in ("source_zh", "source_en"):
        v = doc.get(k)
        if v not in (None, ""):
            out[k] = v
    return out


class TargetedFetcher:
    def __init__(
        self,
        es: Any,
        *,
        bible: Any = None,
        feasts: Optional[list[dict[str, Any]]] = None,
        retrieval: Any = None,
        cfg: Optional[dict[str, Any]] = None,
    ) -> None:
        self.es = es
        self.bible = bible
        self.feasts = feasts or []
        self.retrieval = retrieval
        self.cfg = cfg or retrieval_cfg()
        self.max_size = int(params(self.cfg).get("targeted_max_size", 2000))

    async def _fetch(self, logical: str, terms: dict[str, Any]) -> tuple[list[dict[str, Any]], Optional[int]]:
        from retrieval.es_search import hits_total, normalize_hits, run_search_raw

        flt = [{"term": {k: v}} for k, v in terms.items() if v is not None]
        body: dict[str, Any] = {"size": self.max_size, "query": {"bool": {"filter": flt}}}
        ofield = ((index_cfg(logical, self.cfg).get("fields") or {}).get("order")) or {}
        if ofield.get("name") and not ofield.get("derive"):
            body["sort"] = [{ofield["name"]: "asc"}]
        resp = await run_search_raw(self.es, logical, body)
        return normalize_hits(logical, resp), hits_total(resp)

    def _part_info(
        self, docs: list[dict[str, Any]], total_hits: Optional[int], logical: str
    ) -> dict[str, Any]:
        tname = field_name(logical, "total", self.cfg)
        has_total = bool(tname)
        totals: list[int] = []
        expected: Optional[int] = None
        if has_total and docs:
            raw_totals = [d.get(tname) for d in docs if d.get(tname) is not None]
            totals = sorted({int(x) for x in raw_totals})
            if totals:
                expected = max(totals)
        base = order_base_for(logical, self.cfg)
        orders = [order_value(d, logical, self.cfg) for d in docs]
        info = analyze_orders(
            orders,
            expected_total=expected,
            orders_base=base,
            hits_total=total_hits,
            fetched=len(docs),
            has_total_field=has_total,
        )
        info["chunk_totals"] = totals
        return info

    # ---------------- 生命读经 ----------------
    async def life_study(self, book_title: str, message_number: int) -> TargetedResult:
        out = TargetedResult(
            status=OK, kind="生命读经", meta={"book_title": book_title, "message_number": message_number}
        )
        parts: dict[str, Any] = {}
        any_found = False
        statuses: list[str] = []
        for logical in ("outline_12490", "text_life"):
            bt = filter_field(logical, "book_title", self.cfg) or "book_title"
            mn = field_name(logical, "message_number", self.cfg) or "message_number"
            docs, tot = await self._fetch(logical, {bt: book_title, mn: int(message_number)})
            docs.sort(key=lambda d: order_value(d, logical, self.cfg))
            info = self._part_info(docs, tot, logical)
            parts[logical] = info
            if docs:
                any_found = True
                statuses.append(info["status"])
            out.blocks.extend(_block(d, logical, self.cfg) for d in docs)
        out.meta["parts"] = parts
        if not any_found:
            out.status = NOT_FOUND
            out.meta["missing"] = f"{book_title} 第{message_number}篇"
        else:
            out.status = _worst_status(*statuses) if statuses else NOT_FOUND
        return out

    # ---------------- 节期纲目 ----------------
    def feast_name(self, year: int, month_code: str) -> Optional[str]:
        mc = str(month_code).zfill(2)
        for f in self.feasts:
            if int(f.get("year") or 0) == int(year) and str(f.get("month_code")).zfill(2) == mc:
                return str(f.get("name"))
        return None

    async def feast(self, year: int, month_code: str, message_number: Optional[int] = None) -> TargetedResult:
        out = TargetedResult(status=OK, kind="节期纲目", meta={"year": year, "month_code": str(month_code).zfill(2)})
        name = self.feast_name(year, month_code)
        if not name:
            out.status = NOT_FOUND
            out.meta["missing"] = f"{year} 年 {str(month_code).zfill(2)} 特会不在特会表"
            return out
        out.meta["feast_name"] = name
        logical = "outline_feasts"
        terms: dict[str, Any] = {(filter_field(logical, "book_title", self.cfg) or "book_title"): name}
        if message_number is not None:
            terms[field_name(logical, "message_number", self.cfg) or "message_number"] = int(message_number)
        docs, tot = await self._fetch(logical, terms)
        if not docs:
            out.status = NOT_FOUND
            out.meta["missing"] = f"{name}" + (f" 第{message_number}篇" if message_number is not None else "")
            return out
        mn_field = field_name(logical, "message_number", self.cfg) or "message_number"
        docs.sort(key=lambda d: (int(d.get(mn_field) or 0), order_value(d, logical, self.cfg)))

        per_msg: dict[int, list[dict[str, Any]]] = {}
        for d in docs:
            per_msg.setdefault(int(d.get(mn_field) or 0), []).append(d)

        msg_info: dict[str, Any] = {}
        statuses: list[str] = []
        for k in sorted(per_msg):
            group = per_msg[k]
            # 单篇 hits 未知时用本组长度；整场 hits 只挂在顶层
            info = self._part_info(group, len(group), logical)
            # 修正：单篇无法从整场 tot 得 hits；用组内一致的 chunk_total 已够
            msg_info[str(k)] = {
                "fetched": info["fetched"],
                "expected_total": info["expected_total"],
                "orders_contiguous": info["orders_contiguous"],
                "orders_base": info["orders_base"],
                "missing_orders": info["missing_orders"],
                "extra_orders": info["extra_orders"],
                "duplicate_orders": info["duplicate_orders"],
                "chunk_totals": info["chunk_totals"],
                "orders": info["orders"],
                "status": info["status"],
            }
            statuses.append(info["status"])

        out.meta["messages"] = msg_info
        out.meta["messages_fetched"] = len(per_msg)
        out.meta["hits_total"] = tot
        out.meta["expected_message_count"] = None  # feasts.json 无篇数字段
        out.meta["message_count_note"] = "特会表无每场篇数；仅按索引命中核对是否取全场块"
        if tot is not None and tot > len(docs):
            statuses.append(INCOMPLETE)
            out.meta["truncated"] = True
        out.blocks = [_block(d, logical, self.cfg) for d in docs]
        out.status = _worst_status(*statuses) if statuses else OK
        return out

    # ---------------- 诗歌 ----------------
    async def hymn(self, number: int, series: Optional[str] = None) -> TargetedResult:
        logical = "hymns"
        icfg = index_cfg(logical, self.cfg)
        series = series or icfg.get("default_series") or "诗歌"
        out = TargetedResult(status=OK, kind="诗歌", meta={"series": series, "hymn_number": int(number)})
        terms = {
            (filter_field(logical, "series", self.cfg) or "series"): series,
            (filter_field(logical, "hymn_number", self.cfg) or "hymn_number"): int(number),
            (field_name(logical, "order", self.cfg) or "chunk_index"): int(icfg.get("full_chunk_index", 0)),
        }
        docs, _ = await self._fetch(logical, terms)
        docs.sort(key=lambda d: order_value(d, logical, self.cfg))
        if not docs:
            out.status = NOT_FOUND
            out.meta["missing"] = f"{series}第{number}首"
            return out
        blk = _block(docs[0], logical, self.cfg)
        # 供前端 hymn_data / 标题：系列与首数
        blk["series"] = series
        blk["hymn_number"] = int(number)
        blk["name"] = docs[0].get("name") or blk.get("book_title")
        blk["title"] = docs[0].get("title") or blk.get("message_title")
        out.blocks = [blk]
        return out

    async def _book_outline(self, book_no: int) -> Optional[dict[str, Any]]:
        """从 qa4_bible 取该卷 book_outline；无 ES / 未命中则 None。"""
        if self.es is None:
            return None
        try:
            terms = {
                (filter_field("bible", "chunk_type", self.cfg) or "chunk_type"): "book_outline",
                (field_name("bible", "book_no", self.cfg) or "book_no"): int(book_no),
            }
            docs, _ = await self._fetch("bible", terms)
        except Exception:
            return None
        return docs[0] if docs else None

    # ---------------- 经文 ----------------
    async def scripture(self, refs: list[Any]) -> TargetedResult:
        out = TargetedResult(status=OK, kind="经文", meta={"refs": [r.label() for r in refs]})
        if self.bible is None:
            out.status = NOT_SUPPORTED
            out.meta["reason"] = "未加载 bible_data"
            return out
        max_chapters, max_verses = scripture_caps()
        missing: list[str] = []
        reasons: list[str] = []
        for r in refs:
            flags = list(r.flags)
            if r.kind == KIND_BOOK:
                out.meta["kind"] = KIND_BOOK
                n_ch = int(self.bible.chapter_count(r.book_no))
                if n_ch <= 0:
                    missing.append(r.label())
                    reasons.append(f"{r.label()}：书卷不存在")
                    continue
                n_vs = book_verse_total(self.bible, r.book_no)
                name = self.bible.book_name(r.book_no) or r.book
                out.meta["book_title"] = name
                out.meta["chapter_count"] = n_ch
                out.meta["verse_count"] = n_vs
                out.blocks.append(
                    {
                        "index": "bible_data",
                        "order": 0,
                        "ref": r.label(),
                        "book_title": name,
                        "book_no": int(r.book_no),
                        "chapter_count": n_ch,
                        "verse_count": n_vs,
                        "unit": "book_overview",
                        "text": "",
                        "flags": flags,
                    }
                )
                outline = await self._book_outline(r.book_no)
                out.meta["has_outline"] = outline is not None
                if outline is not None:
                    out.blocks.append(
                        {
                            "index": "bible",
                            "id": outline.get("_id") or outline.get("chunk_id"),
                            "order": 1,
                            "ref": r.label(),
                            "book_title": outline.get("book_title") or name,
                            "book_no": int(r.book_no),
                            "chunk_type": "book_outline",
                            "text": outline.get("text") or "",
                            "flags": flags,
                        }
                    )
                continue

            if r.kind == KIND_CHAPTER_RANGE:
                out.meta["kind"] = KIND_CHAPTER_RANGE
                c1, c2 = int(r.chapter), int(r.end_chapter)
                if c2 < c1:
                    missing.append(r.label())
                    reasons.append(f"{r.label()}：止章小于起章")
                    continue
                if not self.bible.chapter_exists(r.book_no, c1):
                    missing.append(r.label())
                    reasons.append(f"{r.label()}：起章不存在")
                    continue
                if not self.bible.chapter_exists(r.book_no, c2):
                    missing.append(r.label())
                    reasons.append(f"{r.label()}：止章不存在")
                    continue
                requested = c2 - c1 + 1
                returned = min(requested, max_chapters)
                out.meta["requested_chapters"] = requested
                out.meta["returned_chapters"] = returned
                if returned < requested:
                    out.meta["truncated"] = True
                for ch in range(c1, c1 + returned):
                    for row in self.bible.get_chapter(r.book_no, ch):
                        out.blocks.append(_verse_block(row, flags))
                continue

            if r.kind == KIND_CHAPTER:
                if not self.bible.chapter_exists(r.book_no, r.chapter):
                    missing.append(r.label())
                    reasons.append(f"{r.label()}：章不存在")
                    continue
                rows = self.bible.get_chapter(r.book_no, r.chapter)
                if not rows:
                    missing.append(r.label())
                    continue
                for row in rows:
                    out.blocks.append(_verse_block(row, flags))
                continue

            if r.kind == KIND_CROSS:
                if r.end_chapter < r.chapter or (
                    r.end_chapter == r.chapter and r.v_end < r.v_start
                ):
                    missing.append(r.label())
                    reasons.append(f"{r.label()}：止点小于起点")
                    continue
                if not self.bible.verse_exists(r.book_no, r.chapter, r.v_start):
                    missing.append(r.label())
                    reasons.append(f"{r.label()}：起点不存在")
                    continue
                if not self.bible.verse_exists(r.book_no, r.end_chapter, r.v_end):
                    missing.append(r.label())
                    reasons.append(f"{r.label()}：止点不存在")
                    continue
                rows = self.bible.get_cross(r.book_no, r.chapter, r.v_start, r.end_chapter, r.v_end)
                requested = len(rows)
                if requested > max_verses:
                    rows = rows[:max_verses]
                    out.meta["truncated"] = True
                    out.meta["requested_verses"] = requested
                    out.meta["returned_verses"] = len(rows)
                if not rows:
                    missing.append(r.label())
                    continue
                for row in rows:
                    out.blocks.append(_verse_block(row, flags))
                continue

            # verse_range（及其它按节范围）
            if not self.bible.chapter_exists(r.book_no, r.chapter):
                missing.append(r.label())
                reasons.append(f"{r.label()}：章不存在")
                continue
            rows = self.bible.get_range(r.book_no, r.chapter, r.v_start, r.v_end)
            want = abs(int(r.v_end) - int(r.v_start)) + 1
            if len(rows) != want:
                missing.append(r.label())
            requested = len(rows)
            if requested > max_verses:
                rows = rows[:max_verses]
                out.meta["truncated"] = True
                out.meta["requested_verses"] = requested
                out.meta["returned_verses"] = len(rows)
            if not rows:
                if r.label() not in missing:
                    missing.append(r.label())
                continue
            for row in rows:
                out.blocks.append(_verse_block(row, flags))

        if missing:
            out.meta["missing"] = sorted(set(missing))
            if reasons:
                out.meta["reason"] = "；".join(reasons)
            out.status = NOT_FOUND if not out.blocks else INCOMPLETE
        return out

    # ---------------- 注解 ----------------
    def footnotes_for(self, ref: Any) -> TargetedResult:
        out = TargetedResult(status=OK, kind="注解", meta={"ref": ref.label(), "mode": "by_verse"})
        if self.bible is None:
            out.status = NOT_SUPPORTED
            out.meta["reason"] = "未加载 bible_data"
            return out
        if ref.kind != "verse_range":
            out.status = NOT_SUPPORTED
            out.meta["reason"] = "按经节取注解只支持节或节范围"
            return out
        for v in range(ref.v_start, ref.v_end + 1):
            for i, fn in enumerate(self.bible.footnotes(ref.book_no, ref.chapter, v)):
                out.blocks.append(
                    {
                        "index": "bible_data",
                        "order": v * 1000 + int(fn.get("num") or i),
                        "verse": v,
                        "note_no": fn.get("num"),
                        "text": fn.get("zh") or "",
                    }
                )
        out.blocks.sort(key=lambda b: b["order"])
        if not out.blocks:
            out.status = NOT_FOUND
            out.meta["missing"] = f"{ref.label()} 无脚注"
        return out

    async def notes_by_topic(self, query: str) -> TargetedResult:
        out = TargetedResult(
            status=OK,
            kind="注解",
            meta={"mode": "by_topic", "coverage_note": "map_note 只覆盖约 48% 的主题，未找到不代表没有注解"},
        )
        if self.retrieval is None:
            out.status = NOT_SUPPORTED
            out.meta["reason"] = "未配置检索服务"
            return out
        from retrieval.types import SubQuestionSpec

        res = await self.retrieval.retrieve(SubQuestionSpec(query=query, scope_override=["map_note"]))
        for i, p in enumerate(res.passages):
            out.blocks.append(
                {
                    "index": "map_note",
                    "order": i,
                    "book_title": p.book_title,
                    "message_title": p.message_title,
                    "source_zh": p.location.get("source_zh"),
                    "source_en": p.location.get("source_en"),
                    "text": p.text,
                }
            )
        if not out.blocks:
            out.status = NOT_FOUND
        return out
