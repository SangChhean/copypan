import re


def _get_highlight_text(item, preferred_field):
    """从 highlight 中取高亮片段，优先 preferred_field，否则用 zh/text/en/title 中第一个存在的"""
    hl = item.get("highlight") or {}
    for key in (preferred_field, "zh", "text", "en", "title"):
        if key in hl and hl[key]:
            return hl[key][0]
    return ""


def clear_bib(item, field):
    _id = item["_id"]
    zh = item["_source"]["zh"]
    en = item["_source"]["en"]
    tags = item["_source"]["tags"]
    source = item["_source"]["source"]
    highlight = _get_highlight_text(item, field)
    title = item["_source"]["title"]

    return {
        "id": _id,
        "up": highlight or (zh if field == "en" else en),
        "down": zh if field == "en" else en,
        "title": title,
        "tags": tags,
        "source": source,
    }
