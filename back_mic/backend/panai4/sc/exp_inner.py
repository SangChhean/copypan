# -*- coding: utf-8 -*-
"""对照实验：只送内在+最内在定义 vs run #23（全定义）。

用法（在 back_mic/backend）:
    python -m panai4.sc.exp_inner            # dry-run（FAKE_LLM）
    python -m panai4.sc.exp_inner --run      # 真实 API；需环境变量 CLAUDE_API_KEY
    python -m panai4.sc.exp_inner --run2     # 第2次真跑（对照 #23/#26）；日志 sc_exp_inner_run2.log
    python -m panai4.sc.exp_inner --run-id 23
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parents[1]
_OUT_DIR = _REPO / "docs" / "panai4_sc" / "exp_inner"
_LOG = _REPO / "logs" / "sc_exp_inner.log"

_SOURCE_RUN_ID = 23
_COMPARE_RUN_ID = 26
_PHRASES = [
    "族类转换",
    "巴别",
    "神的朋友",
    "十字架",
    "停下天然的努力",
    "构成神圣的元素",
    "把祂自己作到他里面",
    "徒七2",
    "罗四17",
    "来十一10",
]
_PHRASES_RUN2 = [
    "把祂自己作到他里面",
    "构成神圣的元素",
    "停下天然的努力",
    "十字架",
    "族类转换",
    "巴别",
    "割礼",
    "伯特利",
    "神的家",
    "父神",
    "神的朋友",
    "徒七2",
    "罗四17",
    "来十一10",
]

_lines: list[str] = []


def log(msg: str = "") -> None:
    _lines.append(msg)
    try:
        print(msg)
    except Exception:
        try:
            sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
        except Exception:
            pass


def flush_log() -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    _LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")


def _burden_body(text: str) -> str:
    from panai4.sc.export_sc import extract_burden_export

    body, _ = extract_burden_export(text or "")
    return body


def _burden_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", _burden_body(text)))


def _phrase_hit(text: str, phrase: str) -> tuple[bool, str]:
    """返回 (有/无, 位置说明)。含「把自己作到…里面」宽松匹配。"""
    body = _burden_body(text)
    idx = body.find(phrase)
    matched = phrase
    if idx < 0:
        alts = {
            "徒七2": ["徒七２", "徒7:2", "徒七章二", "徒七2节"],
            "罗四17": ["罗四１７", "罗4:17", "罗四章十七"],
            "来十一10": ["来十一１０", "来11:10", "来十一章十"],
            "停下天然的努力": ["停下天然努力", "天然的努力停"],
            "构成神圣的元素": ["神圣的元素构成", "构成神的元素"],
            "把祂自己作到他里面": [
                "把祂自己作到人里面",
                "把神自己作到他里面",
                "把自己作到这人里面",
                "把自己作到他里面",
                "把自己作到人里面",
            ],
        }
        for alt in alts.get(phrase, []):
            idx = body.find(alt)
            if idx >= 0:
                matched = alt
                break
    if idx < 0 and phrase == "把祂自己作到他里面":
        m = re.search(r"把[祂神]?自己作到.{0,8}里面", body)
        if m:
            idx = m.start()
            matched = m.group(0)
    if idx < 0:
        return False, "无"
    start = max(0, idx - 12)
    end = min(len(body), idx + len(matched) + 12)
    snippet = body[start:end].replace("\n", " ")
    return True, f"有 @负担说明[{idx}] …{snippet}…"


def _phrase_yn(text: str, phrase: str) -> str:
    ok, _ = _phrase_hit(text, phrase)
    return "有" if ok else "无"


def _unique_ministry_bits(a: str, b: str, term_names: list[str]) -> list[str]:
    """a 有而 b 无的具体用语：词条名命中 + 较长独有片段。"""
    body_a = _burden_body(a)
    body_b = _burden_body(b)
    hits: list[str] = []
    for name in term_names:
        if name and name in body_a and name not in body_b:
            hits.append(name)
    # 句子级：a 的句子在 b 中找不到足够重叠
    for sent in re.split(r"[。；;]", body_a):
        s = sent.strip()
        if len(s) < 8:
            continue
        # 取中间一段做指纹
        key = re.sub(r"\s+", "", s)
        if len(key) < 10:
            continue
        if key not in re.sub(r"\s+", "", body_b):
            # 再缩短：取 12–20 字窗口，若窗口也不在 b，记一条
            win = key[2:18] if len(key) > 18 else key
            if win and win not in re.sub(r"\s+", "", body_b):
                hits.append(s[:40] + ("…" if len(s) > 40 else ""))
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:40]


def _cite_direct_lines(stats: dict) -> list[str]:
    lines = []
    by = stats.get("by_tier") or {}
    for tier in ("最内在", "内在", "外在"):
        b = by.get(tier) or {}
        listed = (b.get("listed") or 0) + (b.get("both") or 0)
        lines.append(
            f"- {tier}：已列出 {listed} · 仅文中出现 {b.get('in_text', 0)} · 未使用 {b.get('unused', 0)}"
            f"（共 {b.get('total', 0)}）"
        )
    return lines


def _snapshot_plain_cache(topic: str, cache_id: int | None) -> dict:
    import panai4.db as panai4_db

    conn = panai4_db.connect()
    if cache_id is None:
        return {}
    row = conn.execute("SELECT * FROM sc_plain_cache WHERE id = ?", (cache_id,)).fetchone()
    if not row:
        return {}
    d = dict(row)
    return {
        "id": d["id"],
        "prompt_hash": d["prompt_hash"],
        "result_sha1": hashlib.sha1((d.get("result_text") or "").encode("utf-8")).hexdigest(),
        "cost_usd": d.get("cost_usd"),
        "len": len(d.get("result_text") or ""),
    }


def _snapshot_run(run_id: int) -> dict:
    from panai4.sc.store import get_run

    r = get_run(run_id)
    if not r:
        return {}
    return {
        "id": r["id"],
        "ref_sha1": hashlib.sha1((r.get("ref_result") or "").encode("utf-8")).hexdigest(),
        "plain_sha1": hashlib.sha1((r.get("plain_result") or "").encode("utf-8")).hexdigest(),
        "cost_ref_usd": r.get("cost_ref_usd"),
        "defs_chars": r.get("defs_chars"),
        "skipped": list(r.get("skipped") or []),
    }


def prepare(source_run_id: int = _SOURCE_RUN_ID):
    from panai4.sc.config import MODEL
    from panai4.sc.data import build_term_defs, fill_ref_prompt, load_sc_data
    from panai4.sc.store import get_plain_cache, get_run, prompt_hash

    data = load_sc_data(force=True)
    if data.load_error:
        raise RuntimeError(data.load_error)
    run = get_run(source_run_id)
    if not run:
        raise RuntimeError(f"run #{source_run_id} not found")
    topic = run.get("topic") or ""
    terms = run.get("final_terms") or []
    names = [t["name"] if isinstance(t, dict) else t for t in terms]
    if len(names) != 35:
        raise RuntimeError(f"expected 35 terms, got {len(names)}")

    term_defs, skipped, merged, defs_chars, defs_sent = build_term_defs(names, data)
    ref_full = fill_ref_prompt(data.ref_prompt_default, topic, term_defs, data)
    p_hash = prompt_hash(data.plain_prompt_default)
    cached = get_plain_cache(topic, p_hash, MODEL)
    return {
        "data": data,
        "run": run,
        "topic": topic,
        "names": names,
        "terms": terms,
        "term_defs": term_defs,
        "skipped": skipped,
        "merged": merged,
        "defs_chars": defs_chars,
        "defs_sent": defs_sent,
        "ref_full": ref_full,
        "plain_prompt": data.plain_prompt_default,
        "cached": cached,
        "model": MODEL,
    }


def extract_ref_block(filled: str) -> str:
    m = re.search(r"你是一位熟悉倪柝声", filled)
    if not m:
        return filled
    return filled[: m.start()]


def dry_run(source_run_id: int = _SOURCE_RUN_ID) -> int:
    # FAKE for dry-run safety
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_FAKE_DELAY"] = "0"

    log(f"=== SC EXP INNER dry-run (source=#{source_run_id}) ===")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    prep = prepare(source_run_id)
    topic = prep["topic"]
    term_defs = prep["term_defs"]
    skipped = prep["skipped"]
    defs_sent = prep["defs_sent"]
    ref_full = prep["ref_full"]

    log(f"topic={topic}")
    log(f"terms={len(prep['names'])}")
    log(f"defs_sent_count={defs_sent} defs_chars={prep['defs_chars']}")
    log(f"skipped={skipped}")
    log(f"merged={prep['merged']}")
    log(f"plain_cache={'hit id='+str(prep['cached']['id']) if prep['cached'] else 'MISS'}")

    n_blocks = len(re.findall(r"〔(?:最内在|内在)〕", term_defs))
    has_outer_block = "〔外在〕" in term_defs
    outer_line = "另选的外在词条（仅名，无定义）："
    outer_names = [n for n in prep["names"] if prep["data"].tier_of.get(n) == "外在"]
    log(f"definition blocks={n_blocks} has_外在_block={has_outer_block}")
    log(f"outer_names={len(outer_names)} line_present={outer_line in term_defs}")

    ok = True
    if n_blocks != 17 or defs_sent != 17:
        log(f"FAIL: expected 17 defs, got blocks={n_blocks} sent={defs_sent}")
        ok = False
    else:
        log("PASS: 17 definition blocks")
    if has_outer_block:
        log("FAIL: outer definition blocks present")
        ok = False
    if len(outer_names) != 14 or outer_line not in term_defs:
        log("FAIL: outer names line")
        ok = False
    else:
        log("PASS: 14 outer names-only")
    expect_skip = {"永远的神", "荣耀的神", "全能者", "耶和华"}
    if set(skipped) != expect_skip:
        log(f"FAIL: skipped expected {expect_skip}, got {skipped}")
        ok = False
    else:
        log("PASS: 4 inner/innermost null-3a skipped")

    block = extract_ref_block(ref_full)
    (_OUT_DIR / "term_defs.txt").write_text(term_defs, encoding="utf-8")
    (_OUT_DIR / "prompt_ref.txt").write_text(ref_full, encoding="utf-8")
    (_OUT_DIR / "ref_block_filled.txt").write_text(block, encoding="utf-8")
    log(f"\n--- reference block (chars={len(block)}) ---")
    log(block)
    log(f"\nwrote {_OUT_DIR / 'term_defs.txt'}")
    log(f"wrote {_OUT_DIR / 'prompt_ref.txt'}")
    log("=== dry-run done ===")
    flush_log()
    return 0 if ok else 1


def _export_docx(
    topic: str,
    raw: str,
    *,
    prefix: str = "【加词条定义版-负担说明（仅内在定义）】",
) -> Path:
    from docx import Document
    from panai4.export_docx import safe_filename_part
    from panai4.sc.export_sc import _add, _set_title_paragraph, extract_burden_export

    body, warning = extract_burden_export(raw)
    if warning:
        log(f"export warning: {warning}")
    doc = Document()
    title = f"{prefix}{topic}"
    if doc.paragraphs:
        _set_title_paragraph(doc.paragraphs[0], title)
    else:
        p = doc.add_paragraph()
        _set_title_paragraph(p, title)
    for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        _add(doc, line)
    max_topic = max(1, 120 - len(prefix) - len(".docx"))
    fname = f"{prefix}{safe_filename_part(topic, max_topic)}.docx"
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUT_DIR / fname
    doc.save(str(path))
    log(f"wrote {path}")
    return path


def _write_report(
    *,
    old_run: dict,
    new_run_id: int,
    new_ref: str,
    new_usage: dict,
    new_cost: float,
    defs_sent: int,
    defs_chars: int,
    skipped: list[str],
    merged: list[str],
    names: list[str],
    terms: list,
    data,
) -> Path:
    from panai4.sc.citation import compute_citation_stats
    from panai4.sc.cost import format_usd, input_output_prices

    old_ref = old_run.get("ref_result") or ""
    old_usage = old_run.get("ref_usage") or {}
    old_cost = old_run.get("cost_ref_usd")
    old_chars = _burden_char_count(old_ref)
    new_chars = _burden_char_count(new_ref)

    # citation for both with appropriate skipped
    old_skipped = old_run.get("skipped") or []
    old_merged = old_run.get("merged") or []
    cite_new = compute_citation_stats(
        ref_output=new_ref,
        final_terms=terms,
        skipped=skipped,
        merged=merged,
        content_3a=data.content_3a,
        tier_of=data.tier_of,
    )
    cite_old = compute_citation_stats(
        ref_output=old_ref,
        final_terms=terms,
        skipped=old_skipped,
        merged=old_merged,
        content_3a=data.content_3a,
        tier_of=data.tier_of,
    )

    lines = [
        "# SC 对照：全定义（#23）vs 仅内在+最内在定义",
        "",
        f"篇题：{old_run.get('topic')}",
        f"旧记录：sc_runs #{old_run.get('id')}（全定义，defs_chars={old_run.get('defs_chars')}）",
        f"新记录：sc_runs #{new_run_id}（仅内在定义，defs_sent={defs_sent}，defs_chars={defs_chars}）",
        f"跳过（新）：{skipped}",
        "",
        "## a. 负担说明字数",
        f"- #23 全定义版：{old_chars}",
        f"- 本次仅内在定义：{new_chars}",
        "",
        "## b. 指定词句（有/无 + 位置）",
        "",
        "| 词句 | #23 全定义 | 本次仅内在 |",
        "|---|---|---|",
    ]
    for ph in _PHRASES:
        ok_old, loc_old = _phrase_hit(old_ref, ph)
        ok_new, loc_new = _phrase_hit(new_ref, ph)
        # 十字架（停下天然的努力）作为组合说明：十字架单独查；停下天然的努力单独查
        label = ph
        if ph == "十字架":
            label = "十字架（停下天然的努力）—「十字架」"
        lines.append(
            f"| {label} | {'有' if ok_old else '无'}；{loc_old} | {'有' if ok_new else '无'}；{loc_new} |"
        )
    # 额外一行：停下天然的努力 已在列表中

    only_new = _unique_ministry_bits(new_ref, old_ref, names)
    only_old = _unique_ministry_bits(old_ref, new_ref, names)
    lines += [
        "",
        "## c. 职事用语差异（只列，不评价）",
        "",
        "### 新版有、旧版无",
    ]
    if only_new:
        for x in only_new:
            lines.append(f"- {x}")
    else:
        lines.append("- （未检出）")
    lines += ["", "### 旧版有、新版无"]
    if only_old:
        for x in only_old:
            lines.append(f"- {x}")
    else:
        lines.append("- （未检出）")

    old_full = old_run.get("ref_prompt_full") or ""
    old_def_n = len(re.findall(r"〔(?:最内在|内在|外在)〕", old_full))
    if old_def_n == 0:
        old_def_n = 30
    prices = input_output_prices((new_usage or {}).get("model") or (old_usage or {}).get("model"))
    old_cin = int((old_usage or {}).get("input_tokens") or 0) * prices["input"] / 1_000_000
    old_cout = int((old_usage or {}).get("output_tokens") or 0) * prices["output"] / 1_000_000
    new_cin = int((new_usage or {}).get("input_tokens") or 0) * prices["input"] / 1_000_000
    new_cout = int((new_usage or {}).get("output_tokens") or 0) * prices["output"] / 1_000_000

    old_cite_lines = (
        _cite_direct_lines(cite_old)
        if cite_old.get("format") == "direct"
        else [f"- （outline 格式）note={cite_old.get('note')}"]
    )
    lines += [
        "",
        "## d. 引用统计（直写版：已列出 / 仅文中出现 / 未使用）",
        "",
        "### 本次（仅内在定义）",
        f"format={cite_new.get('format')}；{cite_new.get('format_note') or ''}",
        f"sent_total={cite_new.get('sent_total')}",
        *_cite_direct_lines(cite_new),
        "",
        "### #23（全定义）",
        f"format={cite_old.get('format')}；{cite_old.get('format_note') or cite_old.get('note') or ''}",
        f"sent_total={cite_old.get('sent_total')}",
        *old_cite_lines,
        "",
        "## e. 送入定义数与花费",
        "",
        "| 项目 | #23 全定义 | 本次仅内在 |",
        "|---|---|---|",
        f"| 送入定义词条数 | {old_def_n} | {defs_sent} |",
        f"| defs_chars | {old_run.get('defs_chars')} | {defs_chars} |",
        f"| 输入 token | {old_usage.get('input_tokens', '—')} | {new_usage.get('input_tokens', '—')} |",
        f"| 输出 token | {old_usage.get('output_tokens', '—')} | {new_usage.get('output_tokens', '—')} |",
        f"| 费用（输入） | {format_usd(old_cin)} | {format_usd(new_cin)} |",
        f"| 费用（输出） | {format_usd(old_cout)} | {format_usd(new_cout)} |",
        f"| 费用（合计） | {format_usd(float(old_cost) if old_cost is not None else None)} | {format_usd(new_cost)} |",
        "",
    ]
    lines += [
        "## 负担说明正文",
        "",
        "### #23 全定义版",
        _burden_body(old_ref),
        "",
        "### 本次仅内在定义",
        _burden_body(new_ref),
        "",
    ]
    path = _OUT_DIR / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    log(f"wrote {path}")
    return path


async def _call_ref(prompt: str, topic: str):
    from panai4.sc.cost import calc_cost_usd, format_usd
    from panai4.sc.llm_call import sc_complete, usage_dict

    result = await sc_complete(prompt, topic=topic)
    usage = usage_dict(result)
    cost = calc_cost_usd(usage)
    usage["cost_usd"] = cost
    usage["cost_display"] = format_usd(cost)
    return result, usage, cost


def run_api(source_run_id: int = _SOURCE_RUN_ID) -> int:
    # Real API: ensure FAKE is off; load .env without printing secrets
    if os.environ.get("PANAI4_FAKE_LLM") == "1":
        del os.environ["PANAI4_FAKE_LLM"]
    try:
        from dotenv import load_dotenv

        load_dotenv(_BACKEND / ".env")
    except Exception:
        pass
    if not (os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        log("FAIL: CLAUDE_API_KEY not set in environment")
        flush_log()
        return 1

    log(f"=== SC EXP INNER --run (source=#{source_run_id}) ===")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    prep = prepare(source_run_id)
    old_run = prep["run"]
    topic = prep["topic"]
    names = prep["names"]
    cached = prep["cached"]
    if cached is None:
        log("FAIL: 普通版存档不存在，拒绝重跑普通版；请先确认 plain cache")
        flush_log()
        return 1

    snap23_before = _snapshot_run(source_run_id)
    snap_plain_before = _snapshot_plain_cache(topic, cached["id"])
    log(f"snapshot #23 before={snap23_before}")
    log(f"snapshot plain_cache before={snap_plain_before}")
    log(f"defs_sent={prep['defs_sent']} skipped={prep['skipped']}")
    log(f"ref_full chars={len(prep['ref_full'])}")

    (_OUT_DIR / "prompt_ref.txt").write_text(prep["ref_full"], encoding="utf-8")
    (_OUT_DIR / "term_defs.txt").write_text(prep["term_defs"], encoding="utf-8")

    log("calling claude-opus-5-5 (ref only)...")
    result, usage, cost = asyncio.run(_call_ref(prep["ref_full"], topic))
    new_text = result.text or ""
    (_OUT_DIR / "out_ref.txt").write_text(new_text, encoding="utf-8")
    (_OUT_DIR / "usage_ref.json").write_text(
        json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"ref done: in={usage.get('input_tokens')} out={usage.get('output_tokens')} cost={usage.get('cost_display')}")

    from panai4.sc import store
    from panai4.sc.cost import sum_costs

    final_terms_payload = [
        {
            "name": n,
            "tier": prep["data"].tier_of[n],
            "has_3a": bool(prep["data"].content_3a.get(n)),
        }
        for n in names
    ]
    plain_usage = json.loads(cached.get("usage_json") or "{}")
    # 普通版用存档：本次 plain 费用记 0；不写入/更新 cache
    cost_plain = 0.0
    cost_select = None  # 不重复计入选词
    cost_total = sum_costs(cost_select, cost, cost_plain)

    new_id = store.create_run(
        topic=topic,
        final_terms_json=final_terms_payload,
        skipped_json=prep["skipped"],
        merged_json=prep["merged"],
        defs_chars=prep["defs_chars"],
        ref_prompt_full=prep["ref_full"],
        ref_result=new_text,
        ref_usage_json=usage,
        plain_cache_id=cached["id"],
        plain_result=cached.get("result_text"),
        plain_usage_json=plain_usage,
        plain_from_cache=1,
        cost_select_usd=cost_select,
        cost_ref_usd=cost,
        cost_plain_usd=cost_plain,
        cost_total_usd=cost_total,
        status="done",
    )
    log(f"created sc_runs #{new_id}")

    snap23_after = _snapshot_run(source_run_id)
    snap_plain_after = _snapshot_plain_cache(topic, cached["id"])
    if snap23_before != snap23_after:
        log(f"FAIL: #23 changed! before={snap23_before} after={snap23_after}")
        flush_log()
        return 1
    if snap_plain_before != snap_plain_after:
        log(f"FAIL: plain cache changed! before={snap_plain_before} after={snap_plain_after}")
        flush_log()
        return 1
    log("PASS: #23 and plain cache unchanged")

    _export_docx(topic, new_text)
    _write_report(
        old_run=old_run,
        new_run_id=new_id,
        new_ref=new_text,
        new_usage=usage,
        new_cost=cost,
        defs_sent=prep["defs_sent"],
        defs_chars=prep["defs_chars"],
        skipped=prep["skipped"],
        merged=prep["merged"],
        names=names,
        terms=final_terms_payload,
        data=prep["data"],
    )

    log("=== --run done ===")
    flush_log()
    return 0


def _unique_in_one_of_three(
    texts: dict[str, str], term_names: list[str]
) -> dict[str, list[str]]:
    """返回 label -> 仅该份有的用语列表。"""
    bodies = {k: _burden_body(v) for k, v in texts.items()}
    norms = {k: re.sub(r"\s+", "", b) for k, b in bodies.items()}
    labels = list(texts.keys())
    out: dict[str, list[str]] = {k: [] for k in labels}

    # 词条名
    for name in term_names:
        if not name:
            continue
        present = [lab for lab in labels if name in bodies[lab]]
        if len(present) == 1:
            out[present[0]].append(name)

    # 句子指纹
    for lab in labels:
        others = [norms[x] for x in labels if x != lab]
        for sent in re.split(r"[。；;]", bodies[lab]):
            s = sent.strip()
            key = re.sub(r"\s+", "", s)
            if len(key) < 10:
                continue
            win = key[2:18] if len(key) > 18 else key
            if not win:
                continue
            if all(win not in o for o in others):
                item = s[:40] + ("…" if len(s) > 40 else "")
                if item not in out[lab]:
                    out[lab].append(item)
    # 截断
    for lab in labels:
        out[lab] = out[lab][:30]
    return out


def _write_report_run2(
    *,
    run23: dict,
    run26: dict,
    new_run_id: int,
    new_ref: str,
    new_usage: dict,
    new_cost: float,
    defs_sent: int,
    defs_chars: int,
    names: list[str],
) -> Path:
    from panai4.sc.cost import format_usd, input_output_prices

    t23 = run23.get("ref_result") or ""
    t26 = run26.get("ref_result") or ""
    u23 = run23.get("ref_usage") or {}
    u26 = run26.get("ref_usage") or {}
    c23 = run23.get("cost_ref_usd")
    c26 = run26.get("cost_ref_usd")

    prices = input_output_prices(
        (new_usage or {}).get("model")
        or (u26 or {}).get("model")
        or (u23 or {}).get("model")
    )

    def cost_parts(usage, total):
        inp = int((usage or {}).get("input_tokens") or 0)
        out = int((usage or {}).get("output_tokens") or 0)
        return (
            inp,
            out,
            inp * prices["input"] / 1_000_000,
            out * prices["output"] / 1_000_000,
            float(total) if total is not None else None,
        )

    p23 = cost_parts(u23, c23)
    p26 = cost_parts(u26, c26)
    pnew = cost_parts(new_usage, new_cost)

    lines = [
        "# SC 对照：仅内在定义 第1次（#26）vs 第2次",
        "",
        f"篇题：{run23.get('topic')}",
        f"全定义对照：sc_runs #{run23.get('id')}",
        f"仅内在第1次：sc_runs #{run26.get('id')}（defs 约以存档为准）",
        f"仅内在第2次：sc_runs #{new_run_id}（defs_sent={defs_sent}，defs_chars={defs_chars}）",
        "",
        "## a. 字数与花费（#26 vs 本次）",
        "",
        "| 项目 | #26 第1次 | 本次第2次 |",
        "|---|---|---|",
        f"| 负担说明字数 | {_burden_char_count(t26)} | {_burden_char_count(new_ref)} |",
        f"| 输入 token | {p26[0]} | {pnew[0]} |",
        f"| 输出 token | {p26[1]} | {pnew[1]} |",
        f"| 费用（输入） | {format_usd(p26[2])} | {format_usd(pnew[2])} |",
        f"| 费用（输出） | {format_usd(p26[3])} | {format_usd(pnew[3])} |",
        f"| 费用（合计） | {format_usd(p26[4])} | {format_usd(pnew[4])} |",
        "",
        f"（参考）#23 全定义：字数 {_burden_char_count(t23)}；费用 {format_usd(p23[4])}（入 {format_usd(p23[2])} / 出 {format_usd(p23[3])}）",
        "",
        "## b. 指定词句（#23 / #26 / 本次）",
        "",
        "| 词句 | #23 全定义 | #26 仅内在① | 本次仅内在② |",
        "|---|---|---|---|",
    ]
    for ph in _PHRASES_RUN2:
        label = ph
        if ph == "把祂自己作到他里面":
            label = "把祂自己作到他里面（含「把自己作到…里面」）"
        lines.append(
            f"| {label} | {_phrase_yn(t23, ph)} | {_phrase_yn(t26, ph)} | {_phrase_yn(new_ref, ph)} |"
        )

    uniq = _unique_in_one_of_three(
        {"#23": t23, "#26": t26, "本次": new_ref},
        names,
    )
    lines += [
        "",
        "## c. 仅出现在其中一份的职事用语（不评价）",
        "",
        "### 仅 #23 有",
    ]
    if uniq["#23"]:
        lines.extend(f"- {x}" for x in uniq["#23"])
    else:
        lines.append("- （未检出）")
    lines += ["", "### 仅 #26 有"]
    if uniq["#26"]:
        lines.extend(f"- {x}" for x in uniq["#26"])
    else:
        lines.append("- （未检出）")
    lines += ["", "### 仅本次有"]
    if uniq["本次"]:
        lines.extend(f"- {x}" for x in uniq["本次"])
    else:
        lines.append("- （未检出）")

    lines += [
        "",
        "## 负担说明正文",
        "",
        "### #23 全定义",
        _burden_body(t23),
        "",
        "### #26 仅内在①",
        _burden_body(t26),
        "",
        "### 本次仅内在②",
        _burden_body(new_ref),
        "",
    ]
    path = _OUT_DIR / "report_run2.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    log(f"wrote {path}")
    return path


def dry_run2(source_run_id: int = _SOURCE_RUN_ID) -> int:
    global _LOG, _lines
    _LOG = _REPO / "logs" / "sc_exp_inner_run2.log"
    _lines = []
    log("=== SC EXP INNER run2 dry-run ===")
    # reuse dry_run checks but keep run2 log
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_FAKE_DELAY"] = "0"
    prep = prepare(source_run_id)
    term_defs = prep["term_defs"]
    n_blocks = len(re.findall(r"〔(?:最内在|内在)〕", term_defs))
    outer_names = [n for n in prep["names"] if prep["data"].tier_of.get(n) == "外在"]
    log(f"defs_sent_count={prep['defs_sent']} blocks={n_blocks}")
    log(f"skipped={prep['skipped']}")
    log(f"outer_names={len(outer_names)} line={'另选的外在词条（仅名，无定义）：' in term_defs}")
    ok = (
        n_blocks == 17
        and prep["defs_sent"] == 17
        and "〔外在〕" not in term_defs
        and len(outer_names) == 14
        and set(prep["skipped"]) == {"永远的神", "荣耀的神", "全能者", "耶和华"}
    )
    if ok:
        log("PASS: 17 defs; 14 outer names-only; 4 null skipped")
    else:
        log("FAIL: dry-run2 checks")
    block = extract_ref_block(prep["ref_full"])
    (_OUT_DIR / "ref_block_filled_run2.txt").write_text(block, encoding="utf-8")
    log(f"\n--- reference block (chars={len(block)}) ---")
    log(block)
    log("=== run2 dry-run done ===")
    flush_log()
    return 0 if ok else 1


def run_api2(
    source_run_id: int = _SOURCE_RUN_ID,
    compare_run_id: int = _COMPARE_RUN_ID,
) -> int:
    global _LOG, _lines
    _LOG = _REPO / "logs" / "sc_exp_inner_run2.log"
    _lines = []

    if os.environ.get("PANAI4_FAKE_LLM") == "1":
        del os.environ["PANAI4_FAKE_LLM"]
    try:
        from dotenv import load_dotenv

        load_dotenv(_BACKEND / ".env")
    except Exception:
        pass
    if not (os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        log("FAIL: CLAUDE_API_KEY not set")
        flush_log()
        return 1

    from panai4.sc.store import get_run

    log(f"=== SC EXP INNER --run2 (source=#{source_run_id}, compare=#{compare_run_id}) ===")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    prep = prepare(source_run_id)
    run23 = prep["run"]
    run26 = get_run(compare_run_id)
    if not run26:
        log(f"FAIL: compare run #{compare_run_id} not found")
        flush_log()
        return 1
    topic = prep["topic"]
    names = prep["names"]
    cached = prep["cached"]
    if cached is None:
        log("FAIL: plain cache miss")
        flush_log()
        return 1

    # verify same final_terms as #26
    names26 = [
        t["name"] if isinstance(t, dict) else t for t in (run26.get("final_terms") or [])
    ]
    if set(names) != set(names26) or len(names) != len(names26):
        log("FAIL: final_terms differ from #26")
        flush_log()
        return 1
    log("PASS: final_terms same set as #26")

    snap23_b = _snapshot_run(source_run_id)
    snap26_b = _snapshot_run(compare_run_id)
    snap_plain_b = _snapshot_plain_cache(topic, cached["id"])
    log(f"snapshot #23={snap23_b}")
    log(f"snapshot #26={snap26_b}")
    log(f"snapshot plain={snap_plain_b}")
    log(f"defs_sent={prep['defs_sent']} skipped={prep['skipped']}")

    (_OUT_DIR / "prompt_ref_run2.txt").write_text(prep["ref_full"], encoding="utf-8")
    log("calling claude-opus-5-5 (ref only, run2)...")
    result, usage, cost = asyncio.run(_call_ref(prep["ref_full"], topic))
    new_text = result.text or ""
    (_OUT_DIR / "out_ref_run2.txt").write_text(new_text, encoding="utf-8")
    (_OUT_DIR / "usage_ref_run2.json").write_text(
        json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(
        f"ref done: in={usage.get('input_tokens')} out={usage.get('output_tokens')} "
        f"cost={usage.get('cost_display')}"
    )

    from panai4.sc import store
    from panai4.sc.cost import sum_costs

    final_terms_payload = [
        {
            "name": n,
            "tier": prep["data"].tier_of[n],
            "has_3a": bool(prep["data"].content_3a.get(n)),
        }
        for n in names
    ]
    plain_usage = json.loads(cached.get("usage_json") or "{}")
    cost_plain = 0.0
    new_id = store.create_run(
        topic=topic,
        final_terms_json=final_terms_payload,
        skipped_json=prep["skipped"],
        merged_json=prep["merged"],
        defs_chars=prep["defs_chars"],
        ref_prompt_full=prep["ref_full"],
        ref_result=new_text,
        ref_usage_json=usage,
        plain_cache_id=cached["id"],
        plain_result=cached.get("result_text"),
        plain_usage_json=plain_usage,
        plain_from_cache=1,
        cost_select_usd=None,
        cost_ref_usd=cost,
        cost_plain_usd=cost_plain,
        cost_total_usd=sum_costs(None, cost, cost_plain),
        status="done",
    )
    log(f"created sc_runs #{new_id}")

    if _snapshot_run(source_run_id) != snap23_b:
        log("FAIL: #23 changed")
        flush_log()
        return 1
    if _snapshot_run(compare_run_id) != snap26_b:
        log("FAIL: #26 changed")
        flush_log()
        return 1
    if _snapshot_plain_cache(topic, cached["id"]) != snap_plain_b:
        log("FAIL: plain cache changed")
        flush_log()
        return 1
    log("PASS: #23, #26, plain cache unchanged")

    _export_docx(
        topic,
        new_text,
        prefix="【加词条定义版-负担说明（仅内在定义-第2次）】",
    )
    _write_report_run2(
        run23=run23,
        run26=run26,
        new_run_id=new_id,
        new_ref=new_text,
        new_usage=usage,
        new_cost=cost,
        defs_sent=prep["defs_sent"],
        defs_chars=prep["defs_chars"],
        names=names,
    )
    log("=== --run2 done ===")
    flush_log()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SC 仅内在定义对照实验")
    parser.add_argument("--run", action="store_true", help="真实调用 API")
    parser.add_argument(
        "--run2",
        action="store_true",
        help="第2次模式：无 --run 时 dry-run；配合 --run 真跑",
    )
    parser.add_argument("--run-id", type=int, default=_SOURCE_RUN_ID, help="对照源 run（默认 23）")
    parser.add_argument(
        "--compare-id", type=int, default=_COMPARE_RUN_ID, help="第1次仅内在 run（默认 26）"
    )
    args = parser.parse_args(argv)
    try:
        if args.run2 and args.run:
            return run_api2(args.run_id, args.compare_id)
        if args.run2:
            return dry_run2(args.run_id)
        if args.run:
            return run_api(args.run_id)
        return dry_run(args.run_id)
    except Exception as e:
        log(f"ERROR: {e}")
        flush_log()
        raise


if __name__ == "__main__":
    sys.exit(main())
