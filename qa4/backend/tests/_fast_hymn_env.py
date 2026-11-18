# -*- coding: utf-8 -*-
"""单测加速：进程内只建一次轻量歌词索引，避免反复从真实诗歌库建索引。

不重置 HymnCatalog（诗歌解析单测需要完整/自备目录）。
不访问真实 ES。
"""

from __future__ import annotations

import os
from pathlib import Path

_READY = False
_SYNTH_READY = False


def ensure_stub_lyrics_index() -> None:
    """流水线单测用：空歌词索引（find 恒 not_found，建索引可忽略）。"""
    global _READY
    os.environ.setdefault("QA4_RETRIEVAL_MODE", "fake")
    if _READY:
        return
    from hymn.lyrics import LyricsIndex
    import hymn.lyrics as L

    if getattr(L, "_INDEX", None) is not None and getattr(L._INDEX, "_qa4_stub", False):
        _READY = True
        return
    # 若已有合成索引（step03/lyrics 单测），勿覆盖
    if getattr(L, "_INDEX", None) is not None and getattr(L._INDEX, "_qa4_synth", False):
        _READY = True
        return
    idx = LyricsIndex.from_rows([])
    idx._qa4_stub = True  # type: ignore[attr-defined]
    L._INDEX = idx
    _READY = True


def ensure_synth_lyrics_index() -> object:
    """规则/歌词单测用：合成语料，只建一次（fixture 变更则重建）。"""
    global _SYNTH_READY
    import json
    from hymn.lyrics import LyricsIndex
    import hymn.lyrics as L

    fixture = Path(__file__).parent / "fixtures" / "synth_lyrics_rows.json"
    rows = json.loads(fixture.read_text(encoding="utf-8"))
    sig = (len(rows), fixture.stat().st_mtime_ns)
    if (
        getattr(L, "_INDEX", None) is not None
        and getattr(L._INDEX, "_qa4_synth", False)
        and getattr(L._INDEX, "_qa4_synth_sig", None) == sig
    ):
        _SYNTH_READY = True
        return L._INDEX
    idx = LyricsIndex.from_rows(rows)
    idx._qa4_synth = True  # type: ignore[attr-defined]
    idx._qa4_synth_sig = sig  # type: ignore[attr-defined]
    L._INDEX = idx
    _SYNTH_READY = True
    _READY = True
    return idx


def attach_stub_to_deps(deps) -> None:
    ensure_stub_lyrics_index()
    import hymn.lyrics as L

    deps.lyrics_index = L._INDEX


def attach_synth_to_deps(deps) -> None:
    idx = ensure_synth_lyrics_index()
    deps.lyrics_index = idx
