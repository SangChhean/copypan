# -*- coding: utf-8 -*-
"""
将评测集中 gold_chunks 的 ls_1-XX_YY 格式转为 life_1-X-YY（不修改源文件），
并可选对 kg-rag_life 索引做 chunk_id term 校验。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

LS_CHUNK_RE = re.compile(r"^ls_1-(\d+)_(\d+)$")


def convert_chunk_id(chunk_id: str) -> str:
    """ls_1-XX_YY → life_1-X-YY（篇号去前导零，段号保持原样）。"""
    m = LS_CHUNK_RE.match(chunk_id.strip())
    if not m:
        return chunk_id
    chapter = str(int(m.group(1)))
    segment = m.group(2)
    return f"life_1-{chapter}-{segment}"


def convert_eval_items(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in items:
        new_row = dict(row)
        gcs = row.get("gold_chunks") or []
        if isinstance(gcs, list):
            new_row["gold_chunks"] = [convert_chunk_id(c) for c in gcs]
        out.append(new_row)
    return out


def load_es():
    from elasticsearch import Elasticsearch

    host = (os.environ.get("ES_HOST") or "localhost").strip()
    port = (os.environ.get("ES_PORT") or "9200").strip()
    user = os.environ.get("ES_USERNAME", "elastic")
    password = os.environ.get("ES_PASSWORD", "")
    url = host if host.startswith("http://") or host.startswith("https://") else f"http://{host}:{port}"
    return Elasticsearch(url, basic_auth=(user, password), request_timeout=60)


def _hit_total(r: dict) -> int:
    t = r.get("hits", {}).get("total", 0)
    if isinstance(t, dict):
        return int(t.get("value", 0))
    return int(t or 0)


def term_exists(es, index: str, chunk_id: str) -> bool:
    body = {"query": {"term": {"chunk_id": chunk_id}}, "size": 0, "track_total_hits": True}
    r = es.search(index=index, body=body)
    return _hit_total(r) > 0


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    default_input = Path(r"e:\PanAI用\问答系统\2评测集\评测集数据（1~120）.json")

    p = argparse.ArgumentParser(description="转换评测集 gold_chunks ID 并校验 ES")
    p.add_argument(
        "--input",
        type=Path,
        default=default_input,
        help="源评测集 JSON 路径",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出路径，默认与输入同目录下的 eval_set_v2.json",
    )
    p.add_argument("--seed", type=int, default=None, help="随机抽样种子（可选）")
    p.add_argument("--skip-es", action="store_true", help="跳过 ES 校验")
    args = p.parse_args()

    inp = args.input.expanduser().resolve()
    if not inp.is_file():
        print(f"输入文件不存在: {inp}", file=sys.stderr)
        return 1

    out = args.output
    if out is None:
        out = inp.parent / "eval_set_v2.json"
    else:
        out = out.expanduser().resolve()

    try:
        from dotenv import load_dotenv

        load_dotenv(repo / "back_mic" / "backend" / ".env")
    except ImportError:
        pass

    with inp.open(encoding="utf-8") as f:
        items = json.load(f)

    converted = convert_eval_items(items)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=4)
    print(f"已写入: {out}（共 {len(converted)} 条）")

    with_chunks = [r for r in converted if r.get("gold_chunks")]
    if args.seed is not None:
        random.seed(args.seed)
    k = min(5, len(with_chunks))
    if k == 0:
        print("没有含 gold_chunks 的题目，跳过 ES 抽样")
        return 0

    sample = random.sample(with_chunks, k=k)
    if args.skip_es:
        print("--skip-es：不查询 Elasticsearch")
        return 0

    try:
        es = load_es()
    except Exception as e:
        print(f"ES 客户端初始化失败: {e}", file=sys.stderr)
        return 2

    if not es.ping():
        print("ES ping 失败", file=sys.stderr)
        return 2

    index = "kg-rag_life"
    rows_ok = 0
    print(f"\n随机抽样 {k} 条（索引 {index}，term chunk_id）:\n")
    for row in sample:
        qid = row.get("query_id", "?")
        chunks = row["gold_chunks"]
        all_exist = True
        details = []
        for cid in chunks:
            ok = term_exists(es, index, cid)
            details.append(f"  {cid}: {'存在' if ok else '不存在'}")
            if not ok:
                all_exist = False
        if all_exist:
            rows_ok += 1
        print(f"[{qid}] gold_chunks ({len(chunks)}):")
        print("\n".join(details))
        print()

    print(f"抽样中 chunk 全部存在的题目数: {rows_ok}/{k}")
    if rows_ok >= 4:
        print("验证：≥4/5 题目全部命中，转换规则与索引一致的可能性高。")
    else:
        print("验证：命中不足 4/5，请检查转换规则或索引数据。", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
