# -*- coding: utf-8 -*-
"""
QA 离线评测：调用 /api/qa/query（debug=true），多维度打分并汇总。

依赖：aiohttp、anthropic（异步客户端）。
环境：从 back_mic/backend/.env 读取 CLAUDE_API_KEY（评测脚本与 back_qa 目录相对位置固定）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import aiohttp
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_env_key(name: str) -> str:
    env_path = _repo_root() / "back_mic" / "backend" / ".env"
    if not env_path.is_file():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == name:
            return v.strip().strip('"').strip("'")
    return ""


def _dim1_pass(expected: str, found: bool) -> bool:
    if expected == "ANSWER":
        return found is True
    if expected == "NO_ANSWER":
        return found is False
    return False


def _forbidden_hits(answer: str, forbidden: list[str]) -> list[str]:
    if not answer or not forbidden:
        return []
    hits = []
    for w in forbidden:
        w = (w or "").strip()
        if w and w in answer:
            hits.append(w)
    return hits


def _chunks_hit(retrieved: list[str], gold: list[str]) -> bool:
    r = {x for x in (retrieved or []) if x}
    g = {x for x in (gold or []) if x}
    return bool(r & g)


def _failure_tags(
    expected: str,
    found: bool,
    dim1: bool,
    dim2: bool | None,
    dim3: bool | None,
    dim4: bool | None,
) -> list[str]:
    tags: list[str] = []
    if not dim1:
        if expected == "ANSWER" and not found:
            tags.append("误拒")
        elif expected == "NO_ANSWER" and found:
            tags.append("误放")
        else:
            tags.append("found不符")
        return tags
    if expected == "ANSWER":
        if dim2 is False:
            tags.append("chunks未命中")
        if dim3 is False:
            tags.append("forbidden")
        if dim4 is False:
            tags.append("LLM")
    return tags


@dataclass
class EvalRow:
    raw: dict[str, Any]
    api_json: dict[str, Any] | None = None
    error: str | None = None
    dim1_pass: bool = False
    dim2_pass: bool | None = None
    dim3_pass: bool | None = None
    dim4_pass: bool | None = None
    score: int = 0
    forbidden_hit: list[str] = field(default_factory=list)
    elapsed_ms: int = 0


JUDGE_MODEL = "claude-haiku-4-5-20251001"


async def _llm_judge(
    client: Any,
    query: str,
    gold_summary: str,
    answer: str,
) -> bool:
    prompt = f"""你是一个答案质量评审员。
问题：{query}
参考要点：{gold_summary}
系统答案：{answer}
系统答案是否覆盖了参考要点的核心内容？只回答 yes 或 no，不要任何解释。"""
    msg = await client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=16,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    block = msg.content[0]
    text = getattr(block, "text", "") or ""
    text = text.strip().lower()
    return text.startswith("yes")


async def _call_qa(
    session: aiohttp.ClientSession,
    api_url: str,
    token: str,
    question: str,
) -> tuple[dict[str, Any] | None, str | None, int]:
    url = api_url.rstrip("/") + "/api/qa/query"
    payload = {
        "question": question,
        "skip_cache": True,
        "debug": True,
        "history": [],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    t0 = time.monotonic()
    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=600)) as resp:
            raw = await resp.text()
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if resp.status != 200:
                return None, f"HTTP {resp.status}: {raw[:500]}", elapsed_ms
            data = json.loads(raw)
            return data, None, elapsed_ms
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return None, str(e), elapsed_ms


async def _evaluate_one(
    item: dict[str, Any],
    session: aiohttp.ClientSession,
    api_url: str,
    token: str,
    judge_client: Any,
    sem: asyncio.Semaphore,
    total: int,
    print_lock: asyncio.Lock,
    counter: list[int],
) -> dict[str, Any]:
    qid = item.get("query_id", "")
    query = (item.get("query") or "").strip()
    expected = (item.get("expected_answer_state") or "").strip()
    gold_chunks = item.get("gold_chunks") or []
    if not isinstance(gold_chunks, list):
        gold_chunks = []
    gold_summary = item.get("gold_answer_summary") or ""
    forbidden = item.get("forbidden_concepts") or []
    if not isinstance(forbidden, list):
        forbidden = []

    async with sem:
        data, err, elapsed_ms = await _call_qa(session, api_url, token, query)

    row = EvalRow(raw=item)
    row.elapsed_ms = elapsed_ms

    if err or not data:
        row.error = err or "empty response"
        row.dim1_pass = False
        row.dim2_pass = None
        row.dim3_pass = None
        row.dim4_pass = None
        row.score = 0
        out = _row_to_dict(
            row,
            gold_chunks,
            forbidden,
            answer="",
            found=False,
            retrieved=[],
            api_error=True,
        )
        async with print_lock:
            counter[0] += 1
            print(f"[{counter[0]}/{total}] {qid} ❌ error: {row.error}", flush=True)
        return out

    row.api_json = data
    found = bool(data.get("found"))
    answer = data.get("answer") or ""
    debug = data.get("debug") or {}
    retrieved = debug.get("retrieved_chunks")
    if not isinstance(retrieved, list):
        retrieved = []

    row.dim1_pass = _dim1_pass(expected, found)

    if not row.dim1_pass:
        row.score = 0
        row.dim2_pass = None
        row.dim3_pass = None
        row.dim4_pass = None
    elif expected == "NO_ANSWER":
        row.dim2_pass = None
        row.dim4_pass = None
        row.forbidden_hit = _forbidden_hits(answer, forbidden)
        row.dim3_pass = len(row.forbidden_hit) == 0
        row.score = 1 if row.dim3_pass else 0
    else:
        row.dim2_pass = _chunks_hit(retrieved, gold_chunks)
        row.forbidden_hit = _forbidden_hits(answer, forbidden)
        row.dim3_pass = len(row.forbidden_hit) == 0
        try:
            row.dim4_pass = await _llm_judge(judge_client, query, gold_summary, answer)
        except Exception as e:
            row.dim4_pass = False
            row.error = (row.error or "") + f"; judge_error={e}"
        row.score = sum(
            [
                1 if row.dim2_pass else 0,
                1 if row.dim3_pass else 0,
                1 if row.dim4_pass else 0,
            ]
        )

    out = _row_to_dict(row, gold_chunks, forbidden, answer=answer, found=found, retrieved=retrieved)
    max_pts = 0
    if row.dim1_pass:
        if expected == "NO_ANSWER":
            max_pts = 1
        else:
            max_pts = 3

    async with print_lock:
        counter[0] += 1
        if row.dim1_pass and max_pts and row.score == max_pts:
            ok = "✅"
        elif not row.dim1_pass:
            ok = "❌"
        else:
            ok = "⚠️"
        pts = f"{row.score}/{max_pts}" if max_pts else "0/0"
        print(f"[{counter[0]}/{total}] {qid} {ok} {pts}", flush=True)

    return out


def _row_to_dict(
    row: EvalRow,
    gold_chunks: list[str],
    forbidden: list[str],
    *,
    answer: str = "",
    found: bool = False,
    retrieved: list[str] | None = None,
    api_error: bool = False,
) -> dict[str, Any]:
    item = row.raw
    retrieved = retrieved if retrieved is not None else []
    if row.api_json:
        answer = row.api_json.get("answer") or answer
        found = bool(row.api_json.get("found"))
        dbg = row.api_json.get("debug") or {}
        rc = dbg.get("retrieved_chunks")
        if isinstance(rc, list):
            retrieved = rc
    dim1 = row.dim1_pass if not api_error else None
    return {
        "query_id": item.get("query_id"),
        "query": item.get("query"),
        "expected_answer_state": item.get("expected_answer_state"),
        "found": found,
        "dim1_pass": dim1,
        "dim2_pass": row.dim2_pass,
        "dim3_pass": row.dim3_pass,
        "dim4_pass": row.dim4_pass,
        "score": row.score,
        "retrieved_chunks": retrieved,
        "gold_chunks": gold_chunks,
        "forbidden_hit": row.forbidden_hit,
        "answer": answer,
        "elapsed_ms": row.elapsed_ms,
        "error": row.error,
    }


def _aggregate(rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    n = len(rows)
    api_err_n = sum(1 for r in rows if r.get("error"))
    dim1_ok = sum(1 for r in rows if r.get("dim1_pass") is True)
    false_reject = 0
    false_accept = 0
    for r in rows:
        if r.get("error"):
            continue
        exp = r.get("expected_answer_state")
        found = r.get("found")
        if exp == "ANSWER" and r.get("dim1_pass") is False and not found:
            false_reject += 1
        if exp == "NO_ANSWER" and r.get("dim1_pass") is False and found:
            false_accept += 1

    eligible = [
        r
        for r in rows
        if r.get("expected_answer_state") == "ANSWER" and r.get("dim1_pass") is True and not r.get("error")
    ]
    ne = len(eligible)
    d2_ok = sum(1 for r in eligible if r.get("dim2_pass") is True)
    d3_ok = sum(1 for r in eligible if r.get("dim3_pass") is True)
    d4_ok = sum(1 for r in eligible if r.get("dim4_pass") is True)
    sum_pts = sum(r.get("score", 0) for r in rows)
    max_pts = ne * 3 + sum(
        1
        for r in rows
        if r.get("expected_answer_state") == "NO_ANSWER"
        and r.get("dim1_pass") is True
        and not r.get("error")
    )

    lines = []
    lines.append("============ 评测报告 ============")
    lines.append(f"总题数:         {n}")
    if api_err_n:
        lines.append(f"API/网络错误:   {api_err_n}题（不计入维度1 误拒/误放）")
    n_dim1 = n - api_err_n
    if n_dim1:
        p1 = 100.0 * dim1_ok / n_dim1
        lines.append(f"维度1 found符合预期:   {dim1_ok}/{n_dim1}  ({p1:.1f}%)")
    else:
        lines.append("维度1 found符合预期:   N/A（全部为 API/网络错误）")
    lines.append(f"  - 误拒 (ANSWER→not found):  {false_reject}题")
    lines.append(f"  - 误放 (NO_ANSWER→found):    {false_accept}题")
    if ne:
        lines.append(f"维度2 chunks命中:      {d2_ok}/{ne}   ({100.0 * d2_ok / ne:.1f}%)")
        lines.append(f"维度3 forbidden未出现: {d3_ok}/{ne}   ({100.0 * d3_ok / ne:.1f}%)")
        lines.append(f"维度4 LLM评审通过:     {d4_ok}/{ne}   ({100.0 * d4_ok / ne:.1f}%)")
    else:
        lines.append("维度2 chunks命中:      N/A（无 ANSWER 且维度1 通过题）")
        lines.append("维度3 forbidden未出现: N/A")
        lines.append("维度4 LLM评审通过:     N/A")
    if max_pts:
        lines.append(f"综合得分:       {sum_pts}/{max_pts}  ({100.0 * sum_pts / max_pts:.1f}%)")
    else:
        lines.append("综合得分:       N/A")

    lines.append("")
    lines.append("---- 失败题目 ----")
    fail_lines = []
    for r in rows:
        if r.get("error"):
            fail_lines.append(f"{r.get('query_id')} [API错误] {r.get('error', '')[:120]}")
            continue
        d1 = r.get("dim1_pass")
        if d1 is None:
            continue
        tags = _failure_tags(
            str(r.get("expected_answer_state") or ""),
            bool(r.get("found")),
            bool(d1),
            r.get("dim2_pass"),
            r.get("dim3_pass"),
            r.get("dim4_pass"),
        )
        if tags:
            tag_str = " ".join(f"[{t}]" for t in tags)
            fail_lines.append(f"{r.get('query_id')} {tag_str} {r.get('query', '')[:80]}")
    if not fail_lines:
        fail_lines.append("(无)")
    lines.extend(fail_lines)
    lines.append("=================================")

    report = "\n".join(lines)
    stats = {
        "n": n,
        "dim1_ok": dim1_ok,
        "false_reject": false_reject,
        "false_accept": false_accept,
        "api_errors": api_err_n,
        "eligible_answer_dim1": ne,
        "dim2_ok": d2_ok,
        "dim3_ok": d3_ok,
        "dim4_ok": d4_ok,
        "sum_pts": sum_pts,
        "max_pts": max_pts,
    }
    return report, stats


async def _amain(args: argparse.Namespace) -> None:
    from anthropic import AsyncAnthropic

    api_key = _load_env_key("CLAUDE_API_KEY")
    if not api_key:
        print("错误: 未在 back_mic/backend/.env 中找到 CLAUDE_API_KEY", file=sys.stderr)
        sys.exit(1)

    eval_path = Path(args.eval_set)
    if not eval_path.is_file():
        alt = Path(__file__).resolve().parent / args.eval_set
        if alt.is_file():
            eval_path = alt
        else:
            print(f"错误: 评测集不存在: {args.eval_set}", file=sys.stderr)
            sys.exit(1)

    items = json.loads(eval_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        print("错误: 评测集应为 JSON 数组", file=sys.stderr)
        sys.exit(1)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_name = args.output.replace("{timestamp}", ts)
    out_path = Path(out_name)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = out_path.with_name(out_path.stem + "_summary.txt")

    sem = asyncio.Semaphore(max(1, int(args.concurrency)))
    judge_client = AsyncAnthropic(api_key=api_key)
    print_lock = asyncio.Lock()
    counter = [0]
    total = len(items)

    async with aiohttp.ClientSession() as session:
        tasks = [
            _evaluate_one(
                item,
                session,
                args.api_url,
                args.token,
                judge_client,
                sem,
                total,
                print_lock,
                counter,
            )
            for item in items
        ]
        rows = await asyncio.gather(*tasks)

    rows_sorted = sorted(rows, key=lambda r: str(r.get("query_id", "")))
    report, stats = _aggregate(rows_sorted)

    payload = {
        "meta": {
            "eval_set": str(eval_path),
            "api_url": args.api_url,
            "timestamp_utc": ts,
            "stats": stats,
        },
        "results": rows_sorted,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(report + "\n", encoding="utf-8")
    print(report, flush=True)
    print(f"\n已写入: {out_path.resolve()}", flush=True)
    print(f"已写入: {summary_path.resolve()}", flush=True)


def main() -> None:
    # 延迟 import，便于 --help 在未安装依赖时仍可用
    parser = argparse.ArgumentParser(description="QA /api/qa/query 离线评测")
    parser.add_argument(
        "--eval-set",
        default="eval_set_v3.json",
        help="评测集 JSON 路径（默认 scripts/eval_set_v3.json 或 cwd 相对路径）",
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8001", help="back_qa 根地址")
    parser.add_argument("--token", required=True, help="JWT（qa_token）")
    parser.add_argument("--concurrency", type=int, default=3, help="并发数")
    parser.add_argument(
        "--output",
        default="eval_result_{timestamp}.json",
        help="结果 JSON（支持 {timestamp} 占位）",
    )
    args = parser.parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
