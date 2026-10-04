# -*- coding: utf-8 -*-
"""SC 加词条定义版默认模板 → 参考优先版（v2）验证。不调用真实 API。

用法（在 back_mic/backend）:
    python -m panai4.sc.verify_ref_v2
结果写入 logs/sc_ref_v2.log
"""
from __future__ import annotations

import os
import difflib
import re
import sys
from pathlib import Path

os.environ["PANAI4_FAKE_LLM"] = "1"
os.environ["PANAI4_FAKE_DELAY"] = "0"

from panai4.prompts import load_template
from panai4.sc.config import prompts_dir
from panai4.sc.data import (
    build_ref_prompt_default,
    build_ref_prompt_v1_block_only,
    check_sc_placeholders,
    ensure_ref_prompt_v1_archive,
    fill_ref_prompt,
    load_sc_data,
    remaining_placeholders,
)
from panai4.sc import store
from panai4 import db as panai4_db

_REPO = Path(__file__).resolve().parents[4]
_LOG = _REPO / "logs" / "sc_ref_v2.log"
_lines: list[str] = []


def log(msg: str = "") -> None:
    _lines.append(msg)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


def _clip(s: str, n: int = 120) -> str:
    s = s.replace("\r", "\\r").replace("\n", "\\n")
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n})"


def check(cond: bool, ok: str, fail: str) -> int:
    if cond:
        log(f"PASS: {ok}")
        return 0
    log(f"FAIL: {fail}")
    return 1


def main() -> int:
    fails = 0
    log("=== SC REF PROMPT V2 VERIFY ===")

    plain = load_template("burden")
    ref_block = (prompts_dir() / "ref_block.txt").read_text(encoding="utf-8")
    v1_path = ensure_ref_prompt_v1_archive(plain, ref_block)
    v1 = build_ref_prompt_v1_block_only(plain, ref_block)
    v2 = build_ref_prompt_default(plain, ref_block)
    data = load_sc_data(force=True)

    fails += check(
        v1_path.exists() and v1_path.read_text(encoding="utf-8") == v1,
        f"v1 留档存在且内容正确: {v1_path.name}",
        f"v1 留档异常: {v1_path}",
    )
    fails += check(
        data.ref_prompt_default == v2,
        "meta 默认模板 == v2",
        "meta 默认模板与 v2 不一致",
    )

    log("--- 1 第二步附近 / 依据类型上下文 ---")
    lines = v2.splitlines()
    idx = next(i for i, ln in enumerate(lines) if ln.startswith("第二步：列出职事界定"))
    nearby = lines[idx : idx + 6]
    for ln in nearby:
        log(f"  | {ln}")
    fails += check(
        "分四轮进行" in nearby[0],
        "第二步已改为四轮",
        f"第二步行={nearby[0]!r}",
    )
    fails += check(
        any(ln.startswith("(0) 参考材料：") for ln in nearby),
        "(0) 参考材料 在第二步附近",
        "缺少 (0) 参考材料",
    )
    i0 = next(i for i, ln in enumerate(lines) if ln.startswith("(0) 参考材料："))
    i1 = next(i for i, ln in enumerate(lines) if ln.startswith("(1) 经文回想："))
    fails += check(i0 < i1, f"(0) 在 (1) 之前 (lines {i0}<{i1})", f"(0)@{i0} (1)@{i1}")

    basis_idx = next(i for i, ln in enumerate(lines) if "依据类型分" in ln)
    for ln in lines[basis_idx - 1 : basis_idx + 2]:
        log(f"  | {ln}")
    fails += check(
        "依据类型分四种：经文明文、职事明言、参考材料、自行推论。" in lines[basis_idx],
        "依据类型已改为四种（含参考材料）",
        f"依据类型行={lines[basis_idx]!r}",
    )
    fails += check(
        "主干环必须是经文明文或职事明言" in lines[basis_idx],
        "依据类型行后半（主干环…）仍保留",
        "主干环原文被改动",
    )

    log("--- 2 字数差与 difflib ---")
    log(f"v1 chars={len(v1)}  v2 chars={len(v2)}  diff={len(v2) - len(v1)}")
    diff = list(
        difflib.unified_diff(
            v1.splitlines(),
            v2.splitlines(),
            fromfile="v1_block_only",
            tofile="v2_ref_priority",
            lineterm="",
        )
    )
    for row in diff:
        log(row)
    # 允许的改动：第二步行、插入 (0)、空行、依据类型句
    changed_msgs = [r for r in diff if r.startswith("+") or r.startswith("-")]
    changed_msgs = [r for r in changed_msgs if not r.startswith("+++") and not r.startswith("---")]
    unexpected = []
    for r in changed_msgs:
        body = r[1:]
        if body.startswith("第二步：") or body.startswith("(0) 参考材料：") or body == "":
            continue
        if "依据类型分" in body:
            continue
        unexpected.append(r)
    fails += check(
        not unexpected,
        f"diff 仅含预期改动（{len(changed_msgs)} 行 +/-）",
        f"意外 diff 行: {unexpected}",
    )

    log("--- 3 与存档 ref_prompt_full 比较 ---")
    store.ensure_tables()
    conn = panai4_db.connect()
    row = conn.execute(
        """
        SELECT id, topic, cost_ref_usd, ref_prompt_full, final_terms_json
        FROM sc_runs
        WHERE cost_ref_usd IS NOT NULL
          AND ABS(cost_ref_usd - 0.762) < 0.005
          AND ref_prompt_full IS NOT NULL AND ref_prompt_full != ''
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    note = "cost_ref_usd≈0.762"
    if row is None:
        row = conn.execute(
            """
            SELECT id, topic, cost_ref_usd, ref_prompt_full, final_terms_json
            FROM sc_runs
            WHERE ref_prompt_full IS NOT NULL AND ref_prompt_full != ''
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        note = "fallback: 最近一次有 ref_prompt_full"
    if row is None:
        log("WARN: sc_runs 中无 ref_prompt_full，跳过存档比对")
        fails += check(False, "", "无存档可比对")
    else:
        run = dict(row)
        log(
            f"选用运行 #{run['id']} topic={run['topic']!r} "
            f"cost_ref_usd={run['cost_ref_usd']} ({note})"
        )
        archived = run["ref_prompt_full"] or ""
        # 从存档反推：用同一 topic，以存档全文与新模板填充结果比较
        # 尝试从存档提取 {TERM_DEFS} 区域：【词条定义】与 ━━━ 之间
        m = re.search(
            r"【词条定义】\n(.*?)\n━━━━━━━━━━━━━━━━━━━",
            archived,
            re.S,
        )
        if not m:
            log("WARN: 无法从存档解析 TERM_DEFS，改用 final_terms 重建")
            from panai4.sc.data import build_term_defs
            import json

            terms = json.loads(run["final_terms_json"] or "[]")
            names = [t["name"] if isinstance(t, dict) else t for t in terms]
            term_defs, *_ = build_term_defs(names, data)
        else:
            term_defs = m.group(1)
        filled_new = fill_ref_prompt(v2, run["topic"], term_defs, data)
        if filled_new == archived:
            fails += check(True, "新默认填充后与存档 ref_prompt_full 完全一致", "")
        else:
            log("新默认填充后与存档不完全一致（预期：v2 改动会与旧存档不同）")
            sm = difflib.SequenceMatcher(None, archived, filled_new)
            shown = 0
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                shown += 1
                if shown > 20:
                    log(f"  … 其余差异省略（已显示 20 处）")
                    break
                a = archived[i1:i2]
                b = filled_new[j1:j2]
                log(f"  [{tag}] archive[{i1}:{i2}]={_clip(a)!r}  vs  new[{j1}:{j2}]={_clip(b)!r}")
            log(f"结论: 完全一致={filled_new == archived}；差异块数≈{shown}+")
            # 报告项，不一致不记失败
            fails += check(True, "已完成存档比对报告（不修正存档）", "")

    log("--- 4 占位符校验 ---")
    ph = check_sc_placeholders("ref", v2)
    fails += check(ph["ok"], f"占位符校验通过 {ph}", f"占位符失败 {ph}")
    filled = fill_ref_prompt(v2, "测试篇题", "词条甲：定义", data)
    leftover = remaining_placeholders(filled)
    # DEF_* TERM_DEFS query 应已替换；不应残留这些
    bad = [p for p in leftover if p in {"DEF_WAI", "DEF_NEI", "DEF_ZUINEI", "TERM_DEFS", "query"}]
    fails += check(
        not bad,
        f"填充后无关键残留占位符 leftover={leftover}",
        f"仍有残留 {bad} full_leftover={leftover}",
    )

    log("--- 5 前端文案 ---")
    vue = (
        _REPO
        / "front_mic"
        / "frontend"
        / "src"
        / "components"
        / "toolbox"
        / "PanAI4SC.vue"
    ).read_text(encoding="utf-8")
    fails += check(
        "默认：参考优先版（v2）" in vue,
        "页面有「默认：参考优先版（v2）」",
        "页面缺少版本标注",
    )
    log("(npm run build 由外层执行)")

    log("")
    log(f"=== RESULT fails={fails} ===")
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    _LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    log(f"wrote {_LOG}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
