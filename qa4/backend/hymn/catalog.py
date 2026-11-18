# -*- coding: utf-8 -*-
"""诗歌号码存在性目录：运行时 ES，离线本地清洗 JSON；号码不硬编码。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("qa4.hymn")

# 逻辑系列 → ES / JSON 的 series 字段
SERIES_TO_ES = {
    "big": "诗歌",
    "sup": "补充本诗歌",
    "fu": "诗歌附",
}
ES_TO_SERIES = {v: k for k, v in SERIES_TO_ES.items()}

DEFAULT_JSON = Path(r"G:\PanAI4.0专用\索引数据\panai4_hymns\02_清洗JSON\chunks_hymns.json")
DEFAULT_INDEX = "panai4_hymns"


class HymnCatalog:
    """series(big/sup/fu) → 存在号码集合；并缓存整首块（chunk_index=0）。"""

    def __init__(self) -> None:
        self._nums: Optional[dict[str, set[int]]] = None
        self._rows: Optional[list[dict[str, Any]]] = None
        self._source: str = ""

    @property
    def loaded(self) -> bool:
        return self._nums is not None

    @property
    def source(self) -> str:
        return self._source

    def numbers(self, series: str) -> set[int]:
        self.ensure_loaded()
        assert self._nums is not None
        return set(self._nums.get(series) or ())

    def full_rows(self) -> list[dict[str, Any]]:
        """整首块列表：series(逻辑码)、hymn_number、name、title、text、series_zh。"""
        self.ensure_loaded()
        return list(self._rows or [])

    def exists(self, series: str, number: int) -> bool:
        if series == "child":
            return False
        self.ensure_loaded()
        assert self._nums is not None
        return int(number) in (self._nums.get(series) or ())

    def ensure_loaded(
        self,
        *,
        es: Any = None,
        json_path: Optional[Path] = None,
        force: bool = False,
    ) -> None:
        if self._nums is not None and not force:
            return
        if es is not None:
            try:
                self._nums, self._rows = _load_from_es(es)
                self._source = "es"
                return
            except Exception as e:
                logger.warning("ES 加载诗歌目录失败，回退本地：%s", type(e).__name__)
        path = Path(json_path) if json_path else DEFAULT_JSON
        self._nums, self._rows = _load_from_jsonl(path)
        self._source = str(path)

    def reset(self) -> None:
        self._nums = None
        self._rows = None
        self._source = ""


def _empty() -> dict[str, set[int]]:
    return {"big": set(), "sup": set(), "fu": set()}


def _row_from_obj(obj: dict[str, Any]) -> Optional[dict[str, Any]]:
    series_zh = str(obj.get("series") or "")
    key = ES_TO_SERIES.get(series_zh)
    num = obj.get("hymn_number")
    if not key or num is None:
        return None
    return {
        "series": key,
        "series_zh": series_zh,
        "hymn_number": int(num),
        "name": str(obj.get("name") or ""),
        "title": str(obj.get("title") or ""),
        "text": str(obj.get("text") or ""),
    }


def _add_hit(
    out: dict[str, set[int]],
    rows: list[dict[str, Any]],
    obj: dict[str, Any],
) -> None:
    row = _row_from_obj(obj)
    if not row:
        return
    out[row["series"]].add(int(row["hymn_number"]))
    rows.append(row)


def _load_from_jsonl(path: Path) -> tuple[dict[str, set[int]], list[dict[str, Any]]]:
    out = _empty()
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        raise FileNotFoundError(f"诗歌清洗 JSON 不存在：{path}")
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if int(obj.get("chunk_index", -1)) != 0:
                continue
            _add_hit(out, rows, obj)
    return out, rows


def _load_from_es(es: Any, index: str = DEFAULT_INDEX) -> tuple[dict[str, set[int]], list[dict[str, Any]]]:
    """扫描 chunk_index=0 的整首块。"""
    out = _empty()
    rows: list[dict[str, Any]] = []
    src_fields = ["series", "hymn_number", "name", "title", "text"]
    try:
        from elasticsearch.helpers import scan

        for src in scan(
            es,
            index=index,
            query={"query": {"term": {"chunk_index": 0}}},
            _source=src_fields,
            size=500,
        ):
            body = src.get("_source") or src
            _add_hit(out, rows, body)
    except Exception:
        resp = es.search(
            index=index,
            body={
                "size": 5000,
                "query": {"term": {"chunk_index": 0}},
                "_source": src_fields,
            },
        )
        for h in ((resp or {}).get("hits") or {}).get("hits") or []:
            body = h.get("_source") or h
            _add_hit(out, rows, body)
    if not any(out.values()):
        raise RuntimeError("ES panai4_hymns 未读到整首块")
    return out, rows


_CATALOG = HymnCatalog()


def get_catalog() -> HymnCatalog:
    return _CATALOG


def reset_catalog() -> None:
    _CATALOG.reset()
