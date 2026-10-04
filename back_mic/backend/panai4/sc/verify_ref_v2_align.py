# -*- coding: utf-8 -*-
"""追加验证：v2 (0) 空行对齐 run #19。写入 logs/sc_ref_v2.log（追加）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["PANAI4_FAKE_LLM"] = "1"
os.environ["PANAI4_FAKE_DELAY"] = "0"

from panai4 import db as panai4_db
from panai4.prompts import load_template
from panai4.sc import store
from panai4.sc.config import prompts_dir
from panai4.sc.data import (
    build_ref_prompt_default,
    build_term_defs,
    check_sc_placeholders,
    fill_ref_prompt,
    load_sc_data,
    remaining_placeholders,
)

_REPO = Path(__file__).resolve().parents[4]
_LOG = _REPO / "logs" / "sc_ref_v2.log"
_lines: list[str] = []


def log(msg: str = "") -> None:
    _lines.append(msg)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("ascii", errors="replace"))


def check(cond: bool, ok: str, fail: str) -> int:
    if cond:
        log(f"PASS: {ok}")
        return 0
    log(f"FAIL: {fail}")
    return 1


def main() -> int:
    fails = 0
    log("")
    log("=== SC REF V2 BLANK-LINE ALIGN (append) ===")

    plain = load_template("burden")
    ref_block = (prompts_dir() / "ref_block.txt").read_text(encoding="utf-8")
    v2 = build_ref_prompt_default(plain, ref_block)
    data = load_sc_data(force=True)

    # 结构抽查：分四轮 → (0) → (1) 之间无空行
    i = v2.find("分四轮进行：")
    j = v2.find("(1) 经文回想：", i)
    chunk = v2[i:j]
    log(f"结构 repr: {chunk[:80]!r}… → 到(1)前共 {len(chunk)} 字符")
    fails += check(
        "\n\n" not in v2[v2.find("第二步：列出职事界定"): j + 10],
        "第二步到(1)之间无空行",
        f"仍有空行: {v2[v2.find('第二步：列出职事界定'): j + 10]!r}",
    )

    store.ensure_tables()
    row = panai4_db.connect().execute(
        "SELECT id, topic, ref_prompt_full, final_terms_json FROM sc_runs WHERE id = 19"
    ).fetchone()
    if not row:
        log("FAIL: 找不到 run #19")
        return 1
    run = dict(row)
    archived = run["ref_prompt_full"] or ""
    terms = json.loads(run["final_terms_json"] or "[]")
    names = [t["name"] if isinstance(t, dict) else t for t in terms]
    term_defs, *_ = build_term_defs(names, data)
    filled = fill_ref_prompt(v2, run["topic"], term_defs, data)

    log(f"run#19 topic={run['topic']!r} terms={len(names)}")
    log(f"len archive={len(archived)} filled={len(filled)} equal={filled == archived}")
    if filled == archived:
        fails += check(True, "填充后与 run#19 ref_prompt_full 逐字一致", "")
    else:
        import difflib

        sm = difflib.SequenceMatcher(None, archived, filled)
        shown = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            shown += 1
            if shown > 15:
                log("  … 其余省略")
                break
            a = archived[i1:i2].replace("\n", "\\n")
            b = filled[j1:j2].replace("\n", "\\n")
            if len(a) > 100:
                a = a[:100] + "…"
            if len(b) > 100:
                b = b[:100] + "…"
            log(f"  [{tag}] archive[{i1}:{i2}]={a!r} vs new[{j1}:{j2}]={b!r}")
        fails += check(False, "", f"仍不一致，差异块≈{shown}")

    ph = check_sc_placeholders("ref", v2)
    fails += check(ph["ok"], f"占位符校验 {ph}", f"占位符失败 {ph}")
    sample = fill_ref_prompt(v2, "测试篇题", "词条甲：定义", data)
    bad = [
        p
        for p in remaining_placeholders(sample)
        if p in {"DEF_WAI", "DEF_NEI", "DEF_ZUINEI", "TERM_DEFS", "query"}
    ]
    fails += check(not bad, f"填充后无残留 leftover={remaining_placeholders(sample)}", f"残留 {bad}")

    log("(npm run build 由外层执行)")
    log(f"=== RESULT fails={fails} ===")
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOG.open("a", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")
    log(f"appended {_LOG}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
