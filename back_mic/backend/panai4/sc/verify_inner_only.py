# -*- coding: utf-8 -*-
"""验证：加词条定义版只送内在+最内在 3a；外在仅名。写入 logs/sc_inner_only.log。"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path

os.environ["PANAI4_FAKE_LLM"] = "1"
os.environ["PANAI4_FAKE_DELAY"] = "0"

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parents[1]
sys.path.insert(0, str(_BACKEND))

_LOG = _REPO / "logs" / "sc_inner_only.log"
_lines: list[str] = []


def log(msg: str = "") -> None:
    _lines.append(msg)
    try:
        print(msg)
    except Exception:
        pass


def flush() -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    _LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")


def build_term_defs_old(final_terms: list[str], data) -> tuple[str, list[str], list[str], int]:
    """改前逻辑：三档均送 3a。"""
    from panai4.sc.config import TIER_ORDER

    skipped: list[str] = []
    merged: list[str] = []
    by_tier: dict[str, list[str]] = {t: [] for t in TIER_ORDER}
    for name in final_terms:
        tier = data.tier_of.get(name)
        if tier in by_tier:
            by_tier[tier].append(name)
        else:
            skipped.append(name)
    blocks: list[str] = []
    seen: dict[str, str] = {}
    for tier in TIER_ORDER:
        for name in by_tier[tier]:
            content = data.content_3a.get(name)
            if content is None or not str(content).strip():
                skipped.append(name)
                continue
            if content in seen:
                merged.append(name)
                continue
            seen[content] = name
            blocks.append(f"〔{tier}〕{name}\n{content}")
    text = "\n\n".join(blocks)
    if text:
        text += "\n"
    return text, skipped, merged, len(text)


def extract_ref_material_block(filled: str) -> str:
    """从填好的加词条定义版提示词截取参考块（文首到正文「你是一位」之前）。"""
    m = re.search(r"你是一位熟悉倪柝声", filled)
    if not m:
        return filled
    return filled[: m.start()]


def main() -> int:
    from panai4.sc.citation import compute_citation_stats
    from panai4.sc.data import build_term_defs, fill_ref_prompt, load_sc_data
    from panai4.sc.store import get_run

    log("=== SC inner-only TERM_DEFS verification ===")
    data = load_sc_data(force=True)
    if data.load_error:
        log(f"FAIL load: {data.load_error}")
        flush()
        return 1

    # 第二篇：run #23（35 词：8/13/14）
    run = get_run(23)
    if not run:
        log("FAIL: run #23 not found")
        flush()
        return 1
    topic = run["topic"]
    final_terms = run.get("final_terms") or []
    names = [t["name"] if isinstance(t, dict) else t for t in final_terms]
    tier_counts = Counter(data.tier_of.get(n, "?") for n in names)
    log(f"run#23 topic={topic}")
    log(f"final_terms={len(names)} tiers={dict(tier_counts)}")
    if len(names) != 35 or tier_counts.get("最内在") != 8 or tier_counts.get("内在") != 13 or tier_counts.get("外在") != 14:
        log("FAIL: expected 35 = 8/13/14")
        flush()
        return 1
    log("PASS: second topic selection counts")

    old_text, old_sk, old_mg, old_chars = build_term_defs_old(names, data)
    old_n = old_text.count("〔")
    new_text, new_sk, new_mg, new_chars, new_sent = build_term_defs(names, data)
    new_n = len(re.findall(r"〔(?:最内在|内在)〕", new_text))
    outer_names = [n for n in names if data.tier_of.get(n) == "外在"]

    log(f"\n--- before (all tiers with 3a) ---")
    log(f"defs_sent≈{old_n} defs_chars={old_chars} skipped={len(old_sk)} merged={len(old_mg)}")
    log(f"\n--- after (inner+innermost defs; outer names) ---")
    log(f"defs_sent_count={new_sent} defs_chars={new_chars} skipped={new_sk} merged={new_mg}")
    log(f"TERM_DEFS total chars (incl. outer names line)={len(new_text)}")

    expect_max = 8 + 13  # 21
    if new_sent > expect_max:
        log(f"FAIL: defs_sent_count {new_sent} > {expect_max}")
        flush()
        return 1
    if "〔外在〕" in new_text:
        log("FAIL: TERM_DEFS still has 〔外在〕 definition blocks")
        flush()
        return 1
    if "另选的外在词条（仅名，无定义）：" not in new_text:
        log("FAIL: missing outer names line")
        flush()
        return 1
    for n in outer_names:
        if n not in new_text:
            log(f"FAIL: outer name missing from TERM_DEFS: {n}")
            flush()
            return 1
        # 3a 正文不得作为定义块出现（允许名字出现在清单里）
        content = data.content_3a.get(n)
        if content and str(content).strip():
            snippet = str(content).strip()[:40]
            # 定义块形态：〔外在〕名\\ncontent — 已禁；再查 content 长片段是否游离出现
            if snippet and snippet in new_text:
                # 若名字行之后误附了全文会命中；允许极短偶然子串时再严查
                if f"〔外在〕{n}\n" in new_text or (n + "\n" + snippet) in new_text:
                    log(f"FAIL: outer 3a body found for {n}")
                    flush()
                    return 1
                # 更严：content 前 80 字若出现在 TERM_DEFS 且不在「仅名」行
                long = str(content).strip()[:80]
                if long in new_text:
                    log(f"FAIL: outer 3a text leaked for {n}: {long[:30]!r}...")
                    flush()
                    return 1
    log(f"PASS: {new_sent} definition blocks (≤21); 14 outer names-only; no outer 3a body")

    filled = fill_ref_prompt(data.ref_prompt_default, topic, new_text, data)
    block = extract_ref_material_block(filled)
    log(f"\n--- filled reference block (chars={len(block)}) ---")
    # 打印参考块（可能较长，整段写入 log）
    log(block)
    if "{TERM_DEFS}" in filled or "{query}" in filled:
        log("FAIL: leftover placeholders")
        flush()
        return 1
    if "内在与最内在附定义并标明档次；外在仅列名字" not in block:
        log("FAIL: ref_block wording not updated in filled prompt")
        flush()
        return 1
    log("PASS: filled ref block OK")

    # 引用统计：外在无 3a 也要进基数
    null_outer = next(n for n in outer_names if not (data.content_3a.get(n) or "").strip())
    sample_out = (
        "【负担说明】认识并经历，过祭坛与帐棚的生活。\n\n"
        f"【用到的参考材料】{null_outer}、不存在的假词\n"
    )
    payload = [{"name": n, "tier": data.tier_of[n], "has_3a": bool(data.content_3a.get(n))} for n in names]
    stats = compute_citation_stats(
        ref_output=sample_out,
        final_terms=payload,
        skipped=new_sk,
        merged=new_mg,
        content_3a=data.content_3a,
        tier_of=data.tier_of,
    )
    outer_rows = [t for t in stats["terms"] if t["tier"] == "外在"]
    log(f"\n--- citation direct: format={stats.get('format')} sent_total={stats.get('sent_total')}")
    log(f"outer term rows={len(outer_rows)} (expect 14)")
    if stats.get("format") != "direct" or len(outer_rows) != 14:
        log("FAIL: outer citation rows")
        flush()
        return 1
    hit = next((t for t in outer_rows if t["name"] == null_outer), None)
    if not hit or hit["status"] not in {"listed", "both"}:
        log(f"FAIL: null-outer not listed in citation: {hit}")
        flush()
        return 1
    log(f"PASS: outer without 3a cited as {hit['status_label']}")

    log(f"\n--- comparison ---")
    log(f"改前：送入定义 {old_n} 个，字数 {old_chars}")
    log(f"改后：送入定义 {new_sent} 个，字数 {new_chars}（前端「送入 N 个 3a 鸟瞰」= {new_sent}）")
    log(f"字数减少 {old_chars - new_chars}（{100.0 * (old_chars - new_chars) / old_chars:.1f}%）")

    # FAKE_LLM smoke：组装 generate 路径不调真 API
    from panai4.sc import llm_call
    from panai4.sc.verify_stage2 import fake_result

    async def _fake(prompt, **kwargs):
        return fake_result("【负担说明】假。\n\n【用到的参考材料】\n")

    llm_call.set_mock(_fake)
    import asyncio
    from panai4.sc.router import GenerateIn, generate

    body = GenerateIn(
        topic=topic,
        final_terms=names,
        ref_prompt=data.ref_prompt_default,
        plain_prompt=data.plain_prompt_default,
        mode="ref",
        force_plain=False,
        select_run_id=None,
    )

    async def _run():
        return await generate(body)

    out = asyncio.run(_run())
    log(f"\n--- FAKE generate ---")
    log(f"defs_sent_count={out.get('defs_sent_count')} defs_chars={out.get('defs_chars')}")
    if out.get("defs_sent_count") != new_sent:
        log("FAIL: API defs_sent_count mismatch")
        flush()
        return 1
    log("PASS: FAKE generate returns defs_sent_count")
    llm_call.set_mock(None)

    log("\n=== DONE ===")
    flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
