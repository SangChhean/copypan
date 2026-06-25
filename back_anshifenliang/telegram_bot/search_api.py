"""调用 back_anshifenliang API：搜索 + 查看全文。"""
import os
import re
import logging

import requests

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("ANSHIFENLIANG_API", "http://127.0.0.1:8020")
SEARCH_TIMEOUT = int(os.environ.get("SEARCH_TIMEOUT", "60"))
DETAIL_TIMEOUT = int(os.environ.get("DETAIL_TIMEOUT", "60"))


def _parse_items_from_html(html_message: str, max_results: int = 20) -> list[dict]:
    """Fallback：从 HTML message 解析条目（与 lib/search_parse.js 对齐）。"""
    if not html_message:
        return []

    block_re = re.compile(
        r'<p[^>]*>\s*<span class="(?:data-title(?:_\d+)?|hymn-title)"[^>]*>([^<]+)</span>\s*'
        r'<button class="view-original"([^>]*)>[\s\S]*?</button>\s*</p>([\s\S]*?)'
        r'(?=<p[^>]*>\s*<span class="(?:data-title(?:_\d+)?|hymn-title)"|<p style|$)',
        re.IGNORECASE,
    )

    items = []
    for m in block_re.finditer(html_message):
        if len(items) >= max_results:
            break

        title = m.group(1).strip()
        btn_attrs = m.group(2)
        preview_html = (m.group(3) or "").strip()

        source_m = re.search(r'data-source="([^"]+)"', btn_attrs)
        if not source_m:
            continue

        title_key_m = re.search(r'data-(?:title|title_3|book-key)="([^"]+)"', btn_attrs)
        title_key = title_key_m.group(1).strip() if title_key_m else title

        items.append({
            "title": title,
            "source": source_m.group(1).strip(),
            "titleKey": title_key,
            "previewHtml": preview_html,
        })

    if len(items) >= max_results:
        return items

    for seg in re.split(r"<br\s*/?>", html_message, flags=re.I):
        if len(items) >= max_results:
            break
        seg = seg.strip()
        m = re.match(r"^(.+?)　查看全文\s*$", seg)
        if not m:
            continue
        display_title = m.group(1).strip()
        if not display_title or "<" in display_title:
            continue
        if any(it["titleKey"] == display_title and it["source"] == "hymns" for it in items):
            continue
        items.append({
            "title": display_title,
            "source": "hymns",
            "titleKey": display_title,
            "previewHtml": "",
        })

    if len(items) >= max_results:
        return items

    if not items:
        hymn_direct = re.match(
            r"^<strong>([\s\S]*?)</strong>\s*([\s\S]*)$",
            html_message,
            re.IGNORECASE,
        )
        if hymn_direct:
            title = re.sub(r"<[^>]+>", "", hymn_direct.group(1))
            title = re.sub(r"\s+", " ", title).strip()
            preview = (hymn_direct.group(2) or "").strip()
            if title:
                source = None
                if "节注" in title:
                    source = "zhu_jie_html"
                elif re.search(r"第.+章$", title):
                    source = "jing_wen_with_index"
                elif re.search(r"诗歌第|补充本诗歌第|儿童诗歌第", title):
                    source = "hymns"
                if source:
                    items.append({
                        "title": title,
                        "source": source,
                        "titleKey": title,
                        "previewHtml": preview,
                    })

    if len(items) >= max_results:
        return items

    verse_re = re.compile(
        r'<div[^>]*border-left:\s*4px\s+solid\s+#4CAF50[^>]*>[\s\S]*?'
        r'<p[^>]*>([^<]+)</p>[\s\S]*?<p[^>]*>([\s\S]*?)</p>[\s\S]*?</div>|'
        r'<p[^>]*font-weight:\s*bold[^>]*>([^<]+)</p>\s*'
        r'<p[^>]*line-height:\s*1\.5[^>]*>([\s\S]*?)</p>',
        re.IGNORECASE,
    )
    for m in verse_re.finditer(html_message):
        if len(items) >= max_results:
            break
        title = (m.group(1) or m.group(3) or "").strip()
        content = (m.group(2) or m.group(4) or "").strip()
        if not title:
            continue
        if any(it["title"] == title and it["source"] == "bible_verse" for it in items):
            continue
        items.append({
            "title": title,
            "source": "bible_verse",
            "titleKey": title,
            "previewHtml": content,
        })

    return items


def detect_query_lang(query: str) -> str:
    """与主站一致：检测用户输入是否为繁体。"""
    try:
        resp = requests.post(
            f"{API_BASE}/api/is-traditional",
            json={"text": query},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("lang") or "zh-CN"
    except Exception as exc:
        logger.warning("繁简检测失败，默认简体: %s", exc)
        return "zh-CN"


def search_in_api(
    query: str,
    category: str | None = None,
    max_results: int = 20,
    lang: str | None = None,
) -> dict:
    """搜索，返回 { found, query, items, lang }。"""
    if not lang:
        lang = detect_query_lang(query)
    payload = {"query": query, "lang": lang}
    if category:
        payload["category"] = category

    url = f"{API_BASE}/api/search"
    logger.info("API POST %s payload=%r", url, payload)
    resp = requests.post(url, json=payload, timeout=SEARCH_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    found = bool(data.get("found"))
    message = data.get("message") or ""
    items = data.get("items")
    if items is None and found:
        items = _parse_items_from_html(message, max_results=max_results)
    else:
        items = (items or [])[:max_results]

    logger.info(
        "API 响应 status=%s found=%s message_len=%d items=%d",
        resp.status_code,
        found,
        len(message),
        len(items),
    )
    return {
        "found": found,
        "query": data.get("query") or query,
        "items": items,
        "lang": data.get("lang") or lang,
    }


def fetch_detail(source: str, title: str, lang: str = "zh-CN") -> dict | None:
    """调用 /api/detail 获取完整正文。"""
    url = f"{API_BASE}/api/detail"
    payload = {"source": source, "title": title, "lang": lang}
    logger.info("API POST %s source=%r title=%r", url, source, title)
    resp = requests.post(url, json=payload, timeout=DETAIL_TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def check_api_ready() -> bool:
    try:
        resp = requests.get(f"{API_BASE}/api/health", timeout=5)
        resp.raise_for_status()
        return resp.json().get("status") == "ok"
    except Exception as exc:
        logger.warning("搜索 API 不可用: %s", exc)
        return False
