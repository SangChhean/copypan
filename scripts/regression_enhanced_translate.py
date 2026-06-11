# -*- coding: utf-8 -*-
"""Six-step regression runner for main-site enhanced translate."""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

API_BASE = "http://127.0.0.1:8765"
USERNAME = "admin"
PASSWORD = "Pass2Pansearch"

LINE_POOL = "一\t生命"
LINE_REF = (
    "基督是我们的生命，我们借着祂活着，"
    "都是得胜者。（路加福音生命读经，第四十八篇）"
)
LINE_DEGRADED = "E2E回归探测20260611完全编造的句子不应整单报错"


def _req(method: str, path: str, token: str | None = None, data: dict | None = None) -> tuple[int, dict]:
    url = f"{API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def get_token() -> str:
    form = urllib.parse.urlencode(
        {"username": USERNAME, "password": PASSWORD, "remember": "false"}
    ).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["access_token"]


def main() -> int:
    token = get_token()
    print("TOKEN_OK")

    # 3-line translate test
    content = "\n".join([LINE_POOL, LINE_REF, LINE_DEGRADED])
    status, data = _req(
        "POST",
        "/api/ai_search/enhanced_translate/translate",
        token,
        {"content": content},
    )
    print(f"TRANSLATE_STATUS={status}")
    if status != 200:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 1
    if data.get("error") and not data.get("result"):
        print("WHOLE_REQUEST_ERROR:", data.get("error"))
        return 1

    refs = data.get("refs") or []
    summary = data.get("summary") or {}
    warnings = data.get("warnings") or []
    print("SUMMARY:", json.dumps(summary, ensure_ascii=False))
    print("WARNINGS:", warnings)

    for g in refs:
        idx = g.get("line_index")
        st = g.get("stats") or {}
        deduped = g.get("deduped_refs") or []
        src_types = [r.get("source_type") for r in deduped]
        kinds = [r.get("match_kind") or r.get("match_type") for r in deduped]
        print(
            f"LINE_{idx}: stats={st} deduped={len(deduped)} kinds={kinds} source_types={src_types} "
            f"ref_src_zh={g.get('reference_source_zh')!r} ref_src_en={g.get('reference_source_en')!r}"
        )
        for r in deduped[:2]:
            print(
                f"  ref p{r.get('paragraph')}: match={r.get('match_kind')} "
                f"source_type={r.get('source_type')} rerank_score={r.get('rerank_score')}"
            )

    # retrieve_test (no Gemini)
    status2, data2 = _req(
        "POST",
        "/api/ai_search/enhanced_translate/retrieve_test",
        token,
        {"content": content},
    )
    print(f"RETRIEVE_TEST_STATUS={status2}")
    if status2 == 200:
        rrefs = data2.get("refs") or []
        scores = []
        for g in rrefs:
            for r in g.get("deduped_refs") or []:
                if r.get("rerank_score") is not None:
                    scores.append(r["rerank_score"])
        print(f"RETRIEVE_TEST_LINES={len(rrefs)} RERANK_SCORES_SAMPLE={scores[:3]}")
        print("RETRIEVE_SUMMARY:", json.dumps(data2.get("summary") or {}, ensure_ascii=False))
    else:
        print(json.dumps(data2, ensure_ascii=False, indent=2))
        return 1

    # Traditional variant pool hit
    trad_line = "一\t生命"  # same simplified; try lookup with traditional from pool
    status3, data3 = _req(
        "POST",
        "/api/ai_search/enhanced_translate/translate",
        token,
        {"content": "藉著神的話，我們得著生命"},
    )
    g0 = (data3.get("refs") or [{}])[0]
    print(
        "TRAD_VARIANT:",
        "stats=",
        g0.get("stats"),
        "deduped=",
        len(g0.get("deduped_refs") or []),
        "cost=",
        (data3.get("summary") or {}).get("total_cost_usd"),
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL:", e)
        raise
