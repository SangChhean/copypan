# -*- coding: utf-8 -*-
"""SC 直写版（v3）默认模板验证。不调用真实 API。写入 logs/sc_v3_default.log。"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parents[1]
sys.path.insert(0, str(_BACKEND))

_LOG = _REPO / "logs" / "sc_v3_default.log"
_lines: list[str] = []


def log(msg: str = "") -> None:
    _lines.append(msg)
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                sys.stdout.encoding or "utf-8", errors="replace"
            ))
        except Exception:
            pass


def flush() -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    _LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")


def first_diff(a: str, b: str) -> str:
    if a == b:
        return ""
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return f"@{i}: a={a[max(0,i-30):i+30]!r} b={b[max(0,i-30):i+30]!r}"
    return f"len a={len(a)} b={len(b)}"


def strip_ref_block_and_defs(text: str) -> str:
    """去掉参考块（到【词条定义】段后分隔线）与词条定义，便于与普通版比。"""
    m = re.search(r"【词条定义】\n.*?\n━━━━━━━━━━━━━━━━━━━\n", text, re.S)
    if m:
        return text[m.end() :]
    # 无词条定义时：去掉参考块到第一条写作规则前？退化为去掉到 PLAIN 换句后的正文起点
    idx = text.find("你是一位精通倪柝声")
    if idx >= 0:
        return text[idx:]
    return text


def main() -> int:
    from panai4.prompts import load_template
    from panai4.sc.citation import compute_citation_stats
    from panai4.sc.data import (
        build_term_defs,
        fill_plain_prompt,
        fill_ref_prompt,
        load_sc_data,
        remaining_placeholders,
    )
    from panai4.sc.export_sc import extract_burden_export
    from panai4.sc.prompt_v3 import (
        ReplaceError,
        apply_plain_v3_transforms,
        build_plain_prompt_default_v3,
        build_ref_prompt_default_v3,
    )
    from panai4.sc.store import get_run

    log("=== SC v3 default verification ===")
    data = load_sc_data(force=True)
    if data.load_error:
        log(f"FAIL load: {data.load_error}")
        flush()
        return 1

    plain_v03 = load_template("burden")
    ref_block = data.ref_block_template
    v2_path = Path(__file__).resolve().parent / "prompts" / "ref_prompt_v2_outline.txt"
    if not v2_path.exists():
        log(f"FAIL: missing v2 archive {v2_path}")
        flush()
        return 1
    log(f"PASS: v2 archive exists chars={len(v2_path.read_text(encoding='utf-8'))}")

    # --- plain / ref defaults ---
    try:
        plain_v3, applied_p = apply_plain_v3_transforms(plain_v03)
    except ReplaceError as e:
        log(f"STOP plain transforms: {e}")
        flush()
        return 1
    log(f"P1–P12 applied: {', '.join(applied_p)}")
    log(f"plain v3 chars={len(plain_v3)}")

    if data.plain_prompt_default != plain_v3:
        log("FAIL: data.plain_prompt_default != build_plain_prompt_default_v3")
        flush()
        return 1
    if data.ref_prompt_default != build_ref_prompt_default_v3(plain_v03, ref_block):
        log("FAIL: data.ref_prompt_default != build_ref_prompt_default_v3")
        flush()
        return 1
    log("PASS: data defaults match v3 builders")

    # --- 1. fill ref vs prompt_C ---
    run19 = get_run(19)
    if not run19:
        log("FAIL: run #19 not found")
        flush()
        return 1
    topic = run19["topic"]
    final_terms = run19.get("final_terms") or []
    if isinstance(final_terms, str):
        final_terms = json.loads(final_terms or "[]")
    names = [t["name"] if isinstance(t, dict) else t for t in final_terms]
    term_defs, skipped, merged, *_ = build_term_defs(names, data)
    filled_ref = fill_ref_prompt(data.ref_prompt_default, topic, term_defs, data)
    prompt_c_path = _REPO / "docs" / "panai4_sc" / "exp_bc" / "prompt_C.txt"
    if not prompt_c_path.exists():
        log(f"FAIL: missing {prompt_c_path}")
        flush()
        return 1
    prompt_c = prompt_c_path.read_text(encoding="utf-8")
    if filled_ref == prompt_c:
        log("PASS: filled ref v3 == prompt_C.txt 逐字一致")
    else:
        log("FAIL: filled ref v3 != prompt_C.txt")
        log(f"  {first_diff(filled_ref, prompt_c)}")
        for line in difflib.unified_diff(
            prompt_c.splitlines(),
            filled_ref.splitlines(),
            fromfile="prompt_C",
            tofile="filled_ref_v3",
            lineterm="",
        ):
            log(line)
        flush()
        return 1

    # --- 2. plain diffs ---
    log("\n--- difflib: v0.3 → plain v3 ---")
    for line in difflib.unified_diff(
        plain_v03.splitlines(),
        plain_v3.splitlines(),
        fromfile="Prompt1_v0.3",
        tofile="plain_v3",
        lineterm="",
    ):
        log(line)

    ref_cmp = re.sub(
        r"【词条定义】\n\{TERM_DEFS\}\n━━━━━━━━━━━━━━━━━━━\n?",
        "",
        data.ref_prompt_default,
        count=1,
    )
    # 去掉参考块：从文首到正文「你是一位…」之前
    m_body = re.search(r"你是一位熟悉倪柝声", ref_cmp)
    if m_body:
        ref_cmp = ref_cmp[m_body.start() :]
    log("\n--- difflib: plain_v3 ↔ ref_v3(去参考块与词条定义) ---")
    for line in difflib.unified_diff(
        plain_v3.splitlines(),
        ref_cmp.splitlines(),
        fromfile="plain_v3",
        tofile="ref_v3_sans_refblock",
        lineterm="",
    ):
        log(line)

    # --- 3. placeholders ---
    plain_ph = remaining_placeholders(data.plain_prompt_default)
    ref_ph = remaining_placeholders(data.ref_prompt_default)
    ok_plain = "{query}" in data.plain_prompt_default and "{TERM_DEFS}" not in data.plain_prompt_default
    ok_ref = "{TERM_DEFS}" in data.ref_prompt_default and "{query}" in data.ref_prompt_default
    filled_plain = fill_plain_prompt(data.plain_prompt_default, topic)
    left_p = remaining_placeholders(filled_plain)
    left_r = remaining_placeholders(filled_ref)
    log(f"plain placeholders in default: {plain_ph} ok={ok_plain}")
    log(f"ref placeholders in default: {ref_ph} ok={ok_ref}")
    log(f"after fill plain leftover={left_p} ref leftover={left_r}")
    if not ok_plain or not ok_ref or left_p or left_r:
        log("FAIL: placeholder checks")
        flush()
        return 1
    log("PASS: placeholders")

    # --- 4. export cut ---
    sample_with = (
        "【负担说明】正文甲。\n\n"
        "【用到的参考材料】亚伯拉罕、以撒\n"
    )
    body1, w1 = extract_burden_export(sample_with)
    log(f"export with materials: warning={w1!r} body={body1!r}")
    if "用到的参考材料" in body1 or "亚伯拉罕" in body1:
        log("FAIL: materials leaked into burden export")
        flush()
        return 1
    if body1.strip() != "正文甲。":
        log(f"FAIL: unexpected body1={body1!r}")
        flush()
        return 1

    sample_only = "【负担说明】只有负担。\n"
    body2, w2 = extract_burden_export(sample_only)
    log(f"export only burden: warning={w2!r} body={body2!r}")
    if body2.strip() != "只有负担。" or w2:
        log("FAIL: only-burden export")
        flush()
        return 1

    body3, w3 = extract_burden_export("没有标题的全文")
    log(f"export missing title: warning={w3!r}")
    if not w3:
        log("FAIL: expected warning when missing title")
        flush()
        return 1
    log("PASS: export cut rules")

    # re-export C docx with new rule
    out_c_path = _REPO / "docs" / "panai4_sc" / "exp_bc" / "out_C.txt"
    out_c = out_c_path.read_text(encoding="utf-8") if out_c_path.exists() else ""
    if out_c:
        from panai4.sc.exp_bc import _export_burden_docx

        _export_burden_docx(
            topic,
            out_c,
            "【C直写版-负担说明】",
            _REPO / "docs" / "panai4_sc" / "exp_bc",
        )
        # verify exported body
        c_body, _ = extract_burden_export(out_c)
        if "用到的参考材料" in c_body:
            log("FAIL: C docx body still contains materials section")
            flush()
            return 1
        log(f"PASS: re-exported C docx; burden chars={len(c_body)}")
    else:
        log("WARN: out_C.txt missing, skip re-export")

    # --- 5. citation ---
    cite_src = out_c if out_c else (
        "【负担说明】认识亚伯拉罕、以撒、雅各，过祭坛与帐棚的生活，得着祝福。\n\n"
        "【用到的参考材料】亚伯拉罕、以撒、雅各、伯特利、对付天然、成熟、新造、经纶的三一、恩典\n"
    )
    cite_direct = compute_citation_stats(
        ref_output=cite_src,
        final_terms=final_terms,
        skipped=skipped,
        merged=merged,
        content_3a=data.content_3a,
        tier_of=data.tier_of,
    )
    log(f"\n--- direct citation format={cite_direct.get('format')} note={cite_direct.get('format_note')}")
    for tier in ("最内在", "内在", "外在"):
        b = cite_direct["by_tier"][tier]
        listed = b.get("listed", 0) + b.get("both", 0)
        log(
            f"  {tier}: 已列出 {listed} · 仅文中出现 {b.get('in_text', 0)} · 未使用 {b.get('unused', 0)} (total={b.get('total', 0)})"
        )
    in_text_names = [
        t["name"] for t in cite_direct["terms"] if t["status"] == "in_text"
    ]
    log(f"文中出现但自报漏掉: {in_text_names}")

    # old outline on run #19
    skipped19 = run19.get("skipped") or []
    merged19 = run19.get("merged") or []
    if isinstance(skipped19, str):
        skipped19 = json.loads(skipped19 or "[]")
    if isinstance(merged19, str):
        merged19 = json.loads(merged19 or "[]")
    cite19 = compute_citation_stats(
        ref_output=run19.get("ref_result") or "",
        final_terms=final_terms,
        skipped=skipped19,
        merged=merged19,
        content_3a=data.content_3a,
        tier_of=data.tier_of,
    )
    by = cite19["by_tier"]
    in_o = sum(by[t]["in_outline"] for t in by)
    defs_o = sum(by[t]["defs_only"] for t in by)
    cited = in_o + defs_o
    log(f"\n--- run#19 outline: format={cite19.get('format')} cited={cited} in_outline={in_o} defs_only={defs_o}")
    if cite19.get("format") != "outline" or cited != 14 or in_o != 13 or defs_o != 1:
        log(f"FAIL: expected 14 cited / 13 in_outline / 1 defs_only, got cited={cited} in_o={in_o} defs={defs_o}")
        flush()
        return 1
    log("PASS: run#19 old citation unchanged")

    log("\n=== DONE ===")
    flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
