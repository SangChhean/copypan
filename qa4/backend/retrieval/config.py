# -*- coding: utf-8 -*-
"""retrieval.json / index_map.json 访问。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional


@lru_cache(maxsize=1)
def retrieval_cfg() -> dict[str, Any]:
    from config import load_config_json

    return load_config_json("retrieval.json")


@lru_cache(maxsize=1)
def index_map() -> dict[str, Any]:
    from config import load_index_map

    return (load_index_map().get("indices") or {})


def reset_cache() -> None:
    retrieval_cfg.cache_clear()
    index_map.cache_clear()


def params(cfg: Optional[dict] = None) -> dict[str, Any]:
    return dict((cfg or retrieval_cfg()).get("params") or {})


def index_cfg(logical: str, cfg: Optional[dict] = None) -> dict[str, Any]:
    return dict(((cfg or retrieval_cfg()).get("indices") or {}).get(logical) or {})


def actual_index(logical: str) -> str:
    meta = index_map().get(logical) or {}
    return str(meta.get("index") or f"qa4_{logical}")


def field_name(logical: str, key: str, cfg: Optional[dict] = None) -> Optional[str]:
    f = (index_cfg(logical, cfg).get("fields") or {}).get(key) or {}
    return f.get("name")


def filter_field(logical: str, key: str, cfg: Optional[dict] = None) -> Optional[str]:
    f = (index_cfg(logical, cfg).get("filters") or {}).get(key) or {}
    return f.get("name")


def unverified_fields(cfg: Optional[dict] = None) -> list[str]:
    """列出所有 verified=false 的配置项（索引.分组.键）。"""
    out: list[str] = []
    for logical, icfg in ((cfg or retrieval_cfg()).get("indices") or {}).items():
        for group in ("fields", "filters"):
            for key, meta in (icfg.get(group) or {}).items():
                if isinstance(meta, dict) and meta.get("verified") is False:
                    out.append(f"{logical}.{group}.{key}={meta.get('name')}")
        for key, meta in icfg.items():
            if key in ("fields", "filters"):
                continue
            if isinstance(meta, dict):
                if meta.get("verified") is False:
                    out.append(f"{logical}.{key}")
                for sub, smeta in meta.items():
                    if isinstance(smeta, dict) and smeta.get("verified") is False:
                        out.append(f"{logical}.{key}.{sub}")
    return out


def source_fields(logical: str, cfg: Optional[dict] = None) -> list[str]:
    icfg = index_cfg(logical, cfg)
    names = {icfg.get("text_field") or "text"}
    for meta in (icfg.get("fields") or {}).values():
        if isinstance(meta, dict) and meta.get("name"):
            names.add(str(meta["name"]).split(".")[0])
    return sorted(names)
