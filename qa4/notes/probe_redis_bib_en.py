# -*- coding: utf-8 -*-
"""从 Redis 答案缓存取出最近带 citations 的回答，跑书目英译。"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

backend = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend))
os.environ.setdefault("QA4_ENV_FILE", str(backend / ".env"))

from config import get_settings, reset_settings_cache  # noqa: E402
from core.translate import resolve_source_en_line  # noqa: E402

_CJK = re.compile(r"[\u4e00-\u9fff]")


def main() -> None:
    reset_settings_cache()
    s = get_settings(require_runtime=False)
    import redis

    r = redis.Redis.from_url(s.redis_url, decode_responses=True)
    prefix = s.redis_prefix or "qa4:"
    # 扫 cache 键
    keys = []
    for pat in (f"{prefix}cache:*", f"{prefix}*answer*", f"{prefix}*"):
        found = list(r.scan_iter(match=pat, count=500))
        keys.extend(found)
        if len(keys) > 200:
            break
    keys = sorted(set(keys))
    print("keys_sampled", len(keys))
    print("sample keys", keys[:20])

    candidates = []
    for k in keys:
        try:
            raw = r.get(k)
        except Exception:
            continue
        if not raw or not isinstance(raw, str) or raw[0] not in "{[":
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        cites = None
        if isinstance(data, dict):
            cites = data.get("citations")
            if not cites and isinstance(data.get("answer"), dict):
                cites = data["answer"].get("citations")
            if not cites and isinstance(data.get("payload"), dict):
                cites = data["payload"].get("citations")
        if cites:
            candidates.append((k, data, cites))

    print("cache_with_citations", len(candidates))
    if not candidates:
        # 也扫 list/monitor
        mon = r.lrange(f"{prefix}monitor:traces", 0, 20)
        print("monitor sample", mon[:2])
        return

    # 优先含用户那三本书目关键字的
    prefer = ["福音题纲", "极大的奥秘", "钉十字架", "问中之问", "基督是谁"]
    picked = None
    for k, data, cites in candidates:
        blob = json.dumps(cites, ensure_ascii=False)
        if any(p in blob for p in prefer):
            picked = (k, data, cites)
            break
    if picked is None:
        picked = candidates[0]
    k, data, cites = picked
    print("picked_key", k)
    print("n_citations", len(cites))

    items = []
    still_zh = []
    for i, c in enumerate(cites):
        loc = (c or {}).get("location") or {}
        n = (c or {}).get("n") or i + 1
        item = {
            "n": n,
            "zh": f"[{n}] {(c or {}).get('book_title') or ''} {(c or {}).get('message_title') or ''}".strip(),
            "en": ((c or {}).get("source_en") or loc.get("source_en") or "").strip(),
            "source_zh": (loc.get("source_zh") or "").strip(),
            "book_title": (c or {}).get("book_title") or "",
            "message_title": (c or {}).get("message_title") or "",
            "message_number": loc.get("message_number"),
            "index": (c or {}).get("index") or "",
        }
        line, path = resolve_source_en_line(item, i)
        row = {**item, "resolved": line, "path": path}
        items.append(row)
        if path == "zh" or (_CJK.search(line) and path != "source_en"):
            reasons = []
            if not item["en"]:
                reasons.append("citation 无 source_en")
            if item["index"] in ("outline_12490", "outline_feasts") or str(item["index"]).startswith("outline"):
                reasons.append(f"索引 {item['index']} 无 source_en 字段")
            if path == "zh":
                reasons.append("规则无法识别")
            still_zh.append({**row, "reason": "；".join(reasons) or path})

    print("--- resolved ---")
    for it in items:
        print(f"[{it['path']}] idx={it['index']} en_in_cite={bool(it['en'])} -> {it['resolved'][:140]}")
    print("--- still Chinese ---")
    for it in still_zh:
        print(it["resolved"])
        print(" ", it["reason"])

    out = Path(__file__).with_name("probe_redis_bib_en_out.json")
    out.write_text(
        json.dumps({"key": k, "items": items, "still_zh": still_zh}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("wrote", out)


if __name__ == "__main__":
    main()
