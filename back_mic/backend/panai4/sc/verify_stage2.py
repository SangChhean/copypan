# -*- coding: utf-8 -*-
"""SC stage2 mock verification. Does not call real Anthropic API.

用法（在 back_mic/backend）:
    python -m panai4.sc.verify_stage2
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

# Ensure fake LLM before any LLM import path uses it for leftovers
os.environ["PANAI4_FAKE_LLM"] = "1"
os.environ["PANAI4_FAKE_DELAY"] = "0"

from panai4.llm import LLMResult
from panai4.prompts import load_template
from panai4.sc import llm_call, store
from panai4.sc.config import MODEL, PLAIN_NEW, PLAIN_OLD
from panai4.sc.data import (
    build_ref_prompt_default,
    build_term_defs,
    check_sc_placeholders,
    fill_ref_prompt,
    load_sc_data,
    remaining_placeholders,
)
from panai4.sc.parse_select import parse_select_output

_REPO = Path(__file__).resolve().parents[4]
_LOG = _REPO / "logs" / "sc_stage2.log"
_lines: list[str] = []


def log(msg: str = "") -> None:
    _lines.append(msg)
    print(msg)


def fake_result(text: str) -> LLMResult:
    return LLMResult(
        text=text,
        model="fake",
        stop_reason="end_turn",
        input_tokens=1,
        output_tokens=2,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_5m_tokens=0,
        cost_usd=0.0,
        cost_note=None,
        duration_ms=0,
        content_blocks={"text": 1},
        thinking_text="",
    )


def main() -> int:
    log("=== SC STAGE2 VERIFY ===")
    fails = 0

    # 1. ref extract already done; re-print
    ref = _REPO / "docs" / "panai4_sc" / "ref"
    log("--- 1 REF ---")
    for name in ("ch1.txt", "def_外在.txt", "def_内在.txt", "def_最内在.txt"):
        p = ref / name
        body = p.read_text(encoding="utf-8").rstrip("\n")
        bom = p.read_bytes()[:3] == b"\xef\xbb\xbf"
        log(f"{name}: chars={len(body)} bom={bom} head={body[:30]!r} tail={body[-30:]!r}")
        if bom:
            fails += 1
            log("FAIL bom")

    # 2. data
    log("--- 2 DATA ---")
    data = load_sc_data(force=True)
    if data.load_error:
        log(f"FAIL load: {data.load_error}")
        fails += 1
    else:
        counts = {t: len(data.tiers[t]) for t in ("外在", "内在", "最内在")}
        log(f"counts={counts} total={sum(counts.values())} equal_3a={data.mismatch.get('equal')}")
        expect = {"外在": 1760, "内在": 488, "最内在": 133}
        if counts != expect or sum(counts.values()) != 2381 or not data.mismatch.get("equal"):
            log(f"FAIL counts expect {expect}")
            fails += 1
        else:
            log("PASS counts/equal")
        for tier, exp_has, exp_null in (("外在", 1493, 267), ("内在", 388, 100), ("最内在", 107, 26)):
            has = sum(1 for n in data.tiers[tier] if data.content_3a.get(n))
            null = len(data.tiers[tier]) - has
            log(f"{tier}: has_3a={has} null={null}")
            if has != exp_has or null != exp_null:
                log(f"FAIL {tier} 3a stats")
                fails += 1

    # 3. templates（与现状对齐：plain/ref 默认出自 v3 构建；CURRENT burden 已是 v1.0）
    log("--- 3 TEMPLATES ---")
    plain_v03 = load_template("burden", "v0.3")
    plain_cur = load_template("burden")
    from panai4.prompts import REGISTRY as _REG
    from panai4.sc.prompt_v3 import build_plain_prompt_default_v3

    log(f"burden CURRENT={_REG['burden'].CURRENT} chars={len(plain_cur)}")
    log(f"plain_v03_chars={len(plain_v03)} placeholders={check_sc_placeholders('plain', plain_v03)}")
    log(f"select_chars={len(data.select_prompt_default)} check={check_sc_placeholders('select', data.select_prompt_default)}")
    log(f"ref_chars={len(data.ref_prompt_default)} check={check_sc_placeholders('ref', data.ref_prompt_default)}")
    if plain_v03.count(PLAIN_OLD) != 1:
        log(f"FAIL PLAIN_OLD in v0.3 count={plain_v03.count(PLAIN_OLD)}")
        fails += 1
    else:
        log("PASS v0.3 has PLAIN_OLD once")
    # 过时断言原为：plain_prompt_default == load_template('burden')（当时 CURRENT=v0.3）
    # 现况：plain 默认 = build_plain_prompt_default_v3(v0.3)，与 CURRENT v1.0 正文不同。
    plain_built = build_plain_prompt_default_v3(plain_v03)
    if data.plain_prompt_default != plain_built:
        log("FAIL plain default != build_plain_prompt_default_v3(v0.3)")
        fails += 1
    else:
        log("PASS plain default == v3(build from v0.3)")
    if data.ref_prompt_default.count(PLAIN_OLD) != 0:
        log("FAIL ref still has old sentence")
        fails += 1
    # 过时断言原为：ref 中 PLAIN_NEW 恰好 1 次；直写 v3 现行正文已不含该替换句，计数为 0。
    new_n = data.ref_prompt_default.count(PLAIN_NEW)
    if new_n != 0:
        log(f"FAIL ref PLAIN_NEW count={new_n} (expect 0 for current v3)")
        fails += 1
    else:
        log("PASS ref PLAIN_NEW count=0（现行直写 v3，不再要求旧替换句）")
    rebuilt = build_ref_prompt_default(plain_v03, data.ref_block_template)
    if rebuilt != data.ref_prompt_default:
        log("FAIL rebuilt ref != default")
        fails += 1
    else:
        log("PASS rebuilt ref == default")

    # 4. parse select
    log("--- 4 PARSE SELECT ---")
    # pick known names
    zui = data.tiers["最内在"][0]
    nei = data.tiers["内在"][0]
    wai = data.tiers["外在"][0]
    # paren pair if present
    twin_a, twin_b = "产生男孩子", "产生得胜者"
    fake_out = f"""【最内在】
{zui}｜依据：素质一句
【内在】
{wai}｜依据：档次写错应属外在
不存在的词XYZ｜依据：应标红
【外在】
{twin_a}｜依据：括号外
{twin_b}｜依据：括号内
"""
    has_3a = {n: bool(data.content_3a.get(n)) for n in data.tier_of}
    items = parse_select_output(fake_out, data.tier_of, has_3a)
    by_name = {i["name"]: i for i in items}
    ok4 = True
    if not by_name[zui]["in_list"] or by_name[zui]["tier_mismatch"]:
        ok4 = False
        log(f"FAIL normal {by_name.get(zui)}")
    if by_name["不存在的词XYZ"]["in_list"]:
        ok4 = False
        log("FAIL fake name in_list")
    if not by_name[wai]["tier_mismatch"] or by_name[wai]["tier_actual"] != "外在":
        ok4 = False
        log(f"FAIL tier mismatch {by_name.get(wai)}")
    if twin_a not in by_name or twin_b not in by_name:
        ok4 = False
        log("FAIL paren twins missing")
    log(f"parse_items={json.dumps(items, ensure_ascii=False)}")
    if ok4:
        log("PASS parse select")
    else:
        fails += 1

    # 5. TERM_DEFS（内在+最内在送定义；外在仅名）
    log("--- 5 TERM_DEFS ---")
    pick_z = next(n for n in data.tiers["最内在"] if data.content_3a.get(n))
    pick_n = next(n for n in data.tiers["内在"] if data.content_3a.get(n))
    pick_w = next(n for n in data.tiers["外在"] if data.content_3a.get(n))
    null_outer = next(n for n in data.tiers["外在"] if not data.content_3a.get(n))
    null_inner = next((n for n in data.tiers["内在"] if not data.content_3a.get(n)), None)
    if data.content_3a.get(twin_a) and data.content_3a.get(twin_a) == data.content_3a.get(twin_b):
        finals = [pick_z, pick_n, twin_a, twin_b, pick_w, null_outer]
    else:
        finals = [pick_z, pick_n, pick_w, null_outer]
        twin_a = twin_b = None
    if null_inner:
        finals.append(null_inner)
    defs, skipped, merged, chars, sent_n = build_term_defs(finals, data)
    log(f"defs_chars={chars} defs_sent={sent_n} skipped={skipped} merged={merged}")
    pos_z = defs.find("〔最内在〕")
    pos_n = defs.find("〔内在〕")
    pos_w_block = defs.find("〔外在〕")
    outer_line = "另选的外在词条（仅名，无定义）："
    if pos_z < 0 or pos_n < 0 or not (pos_z < pos_n) or pos_w_block >= 0:
        log(f"FAIL order/outer-block z={pos_z} n={pos_n} w_block={pos_w_block}")
        fails += 1
    elif outer_line not in defs or pick_w not in defs or null_outer not in defs:
        log("FAIL outer names line missing")
        fails += 1
    else:
        log("PASS TERM_DEFS inner defs + outer names-only")
    if null_outer in skipped:
        log("FAIL outer null should not be skipped")
        fails += 1
    if null_inner and null_inner not in skipped:
        log("FAIL inner null not skipped")
        fails += 1
    if twin_a and twin_b and twin_b not in merged:
        log(f"FAIL twin not merged {merged}")
        fails += 1
    ref_full = fill_ref_prompt(data.ref_prompt_default, "测试篇题", defs, data)
    left = [p for p in remaining_placeholders(ref_full) if p in {"DEF_WAI", "DEF_NEI", "DEF_ZUINEI", "TERM_DEFS", "query"}]
    if left:
        log(f"FAIL leftover placeholders {left}")
        fails += 1
    else:
        log("PASS no leftover placeholders in filled ref")
    # 6-7 cache + concurrency via mock
    log("--- 6/7 CACHE & CONCURRENCY ---")

    async def run_cache_tests():
        nonlocal fails
        store.ensure_tables()
        llm_call.call_count = 0
        llm_call.reset_semaphore()
        topic = "__sc_verify_topic__"
        plain_a = data.plain_prompt_default
        plain_b = data.plain_prompt_default + " "
        # unique topic to avoid colliding production cache
        topic = topic + hashlib.sha1(os.urandom(4)).hexdigest()[:8]

        concurrent = {"n": 0, "max": 0}

        async def mock_fn(prompt: str, topic: str = ""):
            concurrent["n"] += 1
            concurrent["max"] = max(concurrent["max"], concurrent["n"])
            await asyncio.sleep(0.05)
            concurrent["n"] -= 1
            return fake_result(f"MOCK_RESULT:{topic}:{len(prompt)}")

        llm_call.set_mock(mock_fn)

        from panai4.sc.router import generate
        from panai4.sc.router import GenerateIn

        # first parallel
        body = GenerateIn(
            topic=topic,
            final_terms=[pick_z, pick_n, pick_w],
            ref_prompt=data.ref_prompt_default,
            plain_prompt=plain_a,
            mode="ref_and_plain_parallel",
            force_plain=False,
        )
        r1 = await generate(body)
        c1 = llm_call.call_count
        log(f"first parallel calls={c1} plain_from_cache={r1['plain']['from_cache']} max_conc={concurrent['max']}")
        if c1 != 2:
            log(f"FAIL expected 2 calls got {c1}")
            fails += 1
        if concurrent["max"] < 2:
            log(f"FAIL expected concurrent>=2 got {concurrent['max']}")
            fails += 1
        else:
            log("PASS parallel concurrency observed")

        # second parallel same prompts — plain from cache, only ref calls
        before = llm_call.call_count
        r2 = await generate(body)
        delta = llm_call.call_count - before
        log(f"second parallel delta_calls={delta} from_cache={r2['plain']['from_cache']}")
        if delta != 1 or not r2["plain"]["from_cache"]:
            log("FAIL cache not used on second parallel")
            fails += 1
        else:
            log("PASS plain cache hit (no extra plain call)")

        # change plain one char
        before = llm_call.call_count
        body2 = body.model_copy(update={"plain_prompt": plain_b})
        r3 = await generate(body2)
        delta = llm_call.call_count - before
        log(f"changed plain delta_calls={delta} from_cache={r3['plain']['from_cache']}")
        if delta != 2 or r3["plain"]["from_cache"]:
            log("FAIL changed plain should call both")
            fails += 1
        else:
            log("PASS changed plain re-calls")

        # force_plain
        before = llm_call.call_count
        body3 = body.model_copy(update={"force_plain": True})
        r4 = await generate(body3)
        delta = llm_call.call_count - before
        log(f"force_plain delta_calls={delta} from_cache={r4['plain']['from_cache']}")
        if delta != 2 or r4["plain"]["from_cache"]:
            log("FAIL force_plain should re-call plain+ref")
            fails += 1
        else:
            log("PASS force_plain re-calls")

        # concurrency limit 3
        llm_call.reset_semaphore()
        concurrent["max"] = 0

        async def many():
            await asyncio.gather(*[llm_call.sc_complete("p", topic=f"t{i}") for i in range(5)])

        await many()
        log(f"five calls max_conc={concurrent['max']}")
        if concurrent["max"] > 3:
            log("FAIL exceeded max concurrent 3")
            fails += 1
        elif concurrent["max"] < 1:
            log("FAIL no concurrency recorded")
            fails += 1
        else:
            log("PASS max concurrent <= 3")

        llm_call.set_mock(None)

    asyncio.run(run_cache_tests())

    # 8. frontend（步骤 F：SC 入口隐藏，组件与数据保留）
    log("--- 8 FRONTEND STATIC ---")
    test_vue = _REPO / "front_mic" / "frontend" / "src" / "components" / "toolbox" / "PanAI4Test.vue"
    sc_vue = _REPO / "front_mic" / "frontend" / "src" / "components" / "toolbox" / "PanAI4SC.vue"
    text = test_vue.read_text(encoding="utf-8")
    if "全流程测试" not in text:
        log("FAIL missing 全流程测试 tab")
        fails += 1
    else:
        log("PASS 全流程测试 tab present")
    if 'tab === \'sc\'' in text or 'tab === "sc"' in text:
        # 不应再有可点的 sc 页签绑定
        if "词条定义生成负担说明测试（SC）" in text and "v-show=\"tab === 'sc'\"" in text:
            log("FAIL SC tab still visible")
            fails += 1
        else:
            log("PASS SC tab label not shown as active tab")
    if "PanAI4SC" not in text:
        log("FAIL PanAI4SC import/component removed (should keep code)")
        fails += 1
    else:
        log("PASS PanAI4SC retained in codebase wiring")
    if "SC 页签已退役" not in text and "aria-hidden" not in text:
        log("WARN SC hide marker missing")
    if not sc_vue.is_file():
        log("FAIL PanAI4SC.vue missing")
        fails += 1
    sc_text = sc_vue.read_text(encoding="utf-8")
    if "localStorage" in sc_text:
        log("FAIL PanAI4SC uses localStorage")
        fails += 1
    else:
        log("PASS PanAI4SC has no localStorage")

    log(f"=== DONE fails={fails} ===")
    prev = _LOG.read_text(encoding="utf-8") if _LOG.exists() else ""
    _LOG.write_text(prev.rstrip() + "\n\n" + "\n".join(_lines) + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
