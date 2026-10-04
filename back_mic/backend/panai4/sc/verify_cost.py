# -*- coding: utf-8 -*-
"""SC 花费统计 mock 验证。不调用真实 API。结果写入 logs/sc_cost.log。

用法（在 back_mic/backend）:
    python -m panai4.sc.verify_cost
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["PANAI4_FAKE_LLM"] = "1"
os.environ["PANAI4_FAKE_DELAY"] = "0"

from panai4.sc.cost import (
    CACHE_USAGE_FIELDS,
    calc_cost_usd,
    format_usd,
    sum_costs,
)
from panai4.sc import store
from panai4.sc.export_sc import build_sc_docx, _cost_line
from panai4.sc.llm_call import usage_dict
from panai4.llm import LLMResult

_REPO = Path(__file__).resolve().parents[4]
_LOG = _REPO / "logs" / "sc_cost.log"
_lines: list[str] = []

VERIFY_PRICES = {"input": 15.0, "output": 75.0}


def log(msg: str = "") -> None:
    _lines.append(msg)
    print(msg)


def check(cond: bool, ok: str, fail: str) -> int:
    if cond:
        log(f"PASS: {ok}")
        return 0
    log(f"FAIL: {fail}")
    return 1


def main() -> int:
    fails = 0
    log("=== SC COST VERIFY ===")
    log("--- 0 单价来源与缓存字段 ---")
    log("复用 panai4.config.PRICES_USD_PER_MILLION / price_for_model（未新增 SC_PRICE 默认值）")
    log(f"usage 缓存相关字段名（来自 llm_call.usage_dict / LLMResult）: {list(CACHE_USAGE_FIELDS)}")
    sample = usage_dict(
        LLMResult(
            text="",
            model="fake",
            stop_reason="end_turn",
            input_tokens=1,
            output_tokens=1,
            cache_creation_input_tokens=10,
            cache_read_input_tokens=20,
            cache_creation_5m_tokens=5,
            cost_usd=0.0,
            cost_note=None,
            duration_ms=0,
            content_blocks={},
            thinking_text="",
        )
    )
    log(f"usage_dict 实际键: {sorted(sample.keys())}")
    log(
        "缓存字段值示例: "
        f"cache_creation_input_tokens={sample.get('cache_creation_input_tokens')}, "
        f"cache_read_input_tokens={sample.get('cache_read_input_tokens')}, "
        f"cache_creation_5m_tokens={sample.get('cache_creation_5m_tokens')}"
    )
    log("本任务不计缓存价格，页面可单独显示上述 token 数。")

    log("--- 1 单价 15/75，usage 100000/4000 → $1.800 ---")
    u1 = {"input_tokens": 100000, "output_tokens": 4000}
    c1 = calc_cost_usd(u1, prices=VERIFY_PRICES)
    fails += check(
        abs(c1 - 1.8) < 1e-12 and format_usd(c1) == "$1.800",
        f"raw={c1!r} display={format_usd(c1)}",
        f"got raw={c1!r} display={format_usd(c1)} expected 1.8 / $1.800",
    )

    log("--- 2 单价 15/75，usage 12345/678 → 存 0.236025，显 $0.236 ---")
    u2 = {"input_tokens": 12345, "output_tokens": 678}
    c2 = calc_cost_usd(u2, prices=VERIFY_PRICES)
    expected2 = 12345 * 15 / 1_000_000 + 678 * 75 / 1_000_000
    fails += check(
        abs(c2 - expected2) < 1e-15 and abs(c2 - 0.236025) < 1e-12 and format_usd(c2) == "$0.236",
        f"raw={c2!r} display={format_usd(c2)} (expected raw 0.236025)",
        f"got raw={c2!r} display={format_usd(c2)} expected 0.236025 / $0.236",
    )
    fails += check(
        c2 != 0.236,
        "内部未先舍入成 0.236",
        f"内部被舍入成了 {c2!r}",
    )

    log("--- 3 普通版存档命中：plain=$0.000，合计=选词+加词条定义版 ---")
    store.ensure_tables()
    sel = 0.10
    ref = 0.20
    plain_cached = 0.0
    total = sum_costs(sel, ref, plain_cached)
    fails += check(
        plain_cached == 0.0 and abs(total - 0.30) < 1e-12,
        f"plain={plain_cached} total={total} (select+ref only)",
        f"plain={plain_cached} total={total}",
    )
    run_id_cache = store.create_run(
        topic="__cost_verify_cache__",
        cost_select_usd=sel,
        cost_ref_usd=ref,
        cost_plain_usd=0.0,
        cost_total_usd=total,
        plain_from_cache=1,
        status="done",
    )
    row = store.get_run(run_id_cache)
    fails += check(
        row is not None
        and float(row["cost_plain_usd"]) == 0.0
        and abs(float(row["cost_total_usd"]) - 0.30) < 1e-12,
        f"DB run#{run_id_cache} plain=0 total={row and row.get('cost_total_usd')}",
        f"DB mismatch {row}",
    )
    line = _cost_line(row or {})
    fails += check(
        "普通版 存档" in line and "合计 $0.300" in line,
        f"docx 费用行: {line}",
        f"docx 费用行不符: {line}",
    )
    # 冒烟：能生成 docx
    blob = build_sc_docx(row or {})
    fails += check(len(blob) > 100, f"docx bytes={len(blob)}", "docx 生成失败")

    log("--- 4 累计：未舍入之和再舍入 ≠ 各次舍入后再加 ---")
    a = 0.1234
    b = 0.1234
    raw_sum = a + b  # 0.2468 → $0.247
    rounded_then_sum = round(a, 3) + round(b, 3)  # 0.123+0.123=0.246 → $0.246
    fails += check(
        format_usd(raw_sum) == "$0.247" and format_usd(rounded_then_sum) == "$0.246",
        f"raw_sum={raw_sum}→{format_usd(raw_sum)}; rounded_then={rounded_then_sum}→{format_usd(rounded_then_sum)}",
        "两种算法应不同",
    )
    # 写入两条，走 list_runs 累计
    store.create_run(topic="__cost_verify_sum_a__", cost_total_usd=a, status="done")
    store.create_run(topic="__cost_verify_sum_b__", cost_total_usd=b, status="done")
    listed = store.list_runs(limit=500)
    # 从全库 SUM 已在 list_runs；用专门查询验证本批
    from panai4 import db as panai4_db

    conn = panai4_db.connect()
    sum_ab = conn.execute(
        "SELECT SUM(cost_total_usd) FROM sc_runs WHERE topic IN (?, ?)",
        ("__cost_verify_sum_a__", "__cost_verify_sum_b__"),
    ).fetchone()[0]
    fails += check(
        abs(float(sum_ab) - raw_sum) < 1e-12 and format_usd(float(sum_ab)) == "$0.247",
        f"DB SUM(a,b)={sum_ab} display={format_usd(float(sum_ab))}（取未舍入之和）",
        f"DB SUM 错误 {sum_ab}",
    )
    fails += check(
        listed["cost_counted_runs"] is not None and listed["cost_sum_display"] is not None,
        f"list_runs cost_sum_display={listed['cost_sum_display']} counted={listed['cost_counted_runs']}",
        "list_runs 无累计字段",
    )

    log("--- 5 旧记录无 cost 字段 → 显示 —，不计入累计 ---")
    old_id = store.create_run(topic="__cost_verify_old__", status="done")
    # 确保 cost_total_usd 为 NULL（create_run 不传则不写列，默认 NULL）
    old = store.get_run(old_id)
    fails += check(
        old is not None and old.get("cost_total_usd") is None,
        f"old run#{old_id} cost_total_usd is NULL",
        f"old run cost={old and old.get('cost_total_usd')}",
    )
    listed2 = store.list_runs(limit=500)
    old_item = next((r for r in listed2["runs"] if r["id"] == old_id), None)
    fails += check(
        old_item is not None and old_item.get("cost_total_display") is None,
        f"旧记录展示: {old_item and old_item.get('cost_total_display')!r} → 页面用 —",
        f"旧记录展示异常: {old_item}",
    )
    # 旧记录不应在 COUNT(cost_total_usd) 中
    counted_old = conn.execute(
        "SELECT COUNT(*) FROM sc_runs WHERE id = ? AND cost_total_usd IS NOT NULL",
        (old_id,),
    ).fetchone()[0]
    fails += check(counted_old == 0, "旧记录不计入累计 COUNT", f"counted_old={counted_old}")

    log("--- 6 前端构建（仅检查，本脚本不跑 npm；见下方 shell）---")
    log("(npm build 由 verify 流程外层执行)")

    log("")
    log(f"=== RESULT fails={fails} ===")
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    _LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    log(f"wrote {_LOG}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
