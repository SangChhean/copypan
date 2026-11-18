# -*- coding: utf-8 -*-
"""诗歌首数识别、取首与歌词查找。"""

from hymn.catalog import HymnCatalog, get_catalog, reset_catalog
from hymn.fetch import fetch_hymn_ref_list, fetch_hymns
from hymn.lyrics import find_lyrics, get_lyrics_index, lyric_intent, reset_lyrics_index
from hymn.parse import HymnRef, HymnRefList, format_hymn_refs, parse_hymn_refs

__all__ = [
    "HymnCatalog",
    "HymnRef",
    "HymnRefList",
    "fetch_hymn_ref_list",
    "fetch_hymns",
    "find_lyrics",
    "format_hymn_refs",
    "get_catalog",
    "get_lyrics_index",
    "lyric_intent",
    "parse_hymn_refs",
    "reset_catalog",
    "reset_lyrics_index",
]
