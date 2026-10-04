# -*- coding: utf-8 -*-
"""对导出的五个 jsonl 做字段勘探，写出 docs/panai4_es/inherit_probe.md。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_IN = r"G:\PanAI4.0专用\12490原文JSONL"
REPORT_DEFAULT = None  # filled relative to repo


def _repo_report() -> Path:
    # panai4/inherit → backend → back_mic → copypan
    here = Path(__file__).resolve()
    root = here.parents[4]
    return root / "docs" / "panai4_es" / "inherit_probe.md"


INDICES = [
    "kg-rag_life",
    "kg-rag_cwwl",
    "kg-rag_cwwn",
    "kg-rag_others",
    "kg-rag_map_note",
]

TEXT_FOUR = ["kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn", "kg-rag_others"]


def _type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int) and not isinstance(v, bool):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        if not v:
            return "list(empty)"
        inner = Counter(_type_name(x) for x in v[:20])
        top = inner.most_common(1)[0][0]
        return f"list[{top}]"
    if isinstance(v, dict):
        return "dict"
    return type(v).__name__


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, (list, dict)) and len(v) == 0:
        return True
    return False


def probe_file(path: Path) -> dict:
    field_present = Counter()
    field_types: dict[str, Counter] = {}
    n = 0
    empty_book = empty_msg = empty_sec = 0
    title_in_text = 0
    chunk_ids: list[str] = []
    samples: list[dict] = []

    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            n += 1
            for k, v in obj.items():
                field_present[k] += 1
                field_types.setdefault(k, Counter())[_type_name(v)] += 1

            if _is_empty(obj.get("book_title")):
                empty_book += 1
            if _is_empty(obj.get("message_title")):
                empty_msg += 1
            if _is_empty(obj.get("section_title")):
                empty_sec += 1

            book = (obj.get("book_title") or "").strip()
            text = obj.get("text") or ""
            if book and text.startswith(book):
                title_in_text += 1

            cid = obj.get("chunk_id")
            if cid is not None:
                chunk_ids.append(str(cid))

            if len(samples) < 3:
                samples.append(obj)

    unique_ids = len(set(chunk_ids))
    fields = {}
    for k, present in sorted(field_present.items()):
        types = field_types[k]
        type_str = ", ".join(f"{t}:{c}" for t, c in types.most_common())
        fields[k] = {
            "present": present,
            "rate": present / n if n else 0.0,
            "types": type_str,
        }

    return {
        "n": n,
        "fields": fields,
        "field_set": set(fields.keys()),
        "empty_book": empty_book,
        "empty_msg": empty_msg,
        "empty_sec": empty_sec,
        "title_in_text": title_in_text,
        "chunk_id_total": len(chunk_ids),
        "chunk_id_unique": unique_ids,
        "samples": samples,
    }


def _sample_block(obj: dict) -> list[str]:
    lines = ["```json"]
    shown = {}
    for k, v in obj.items():
        if k == "text" and isinstance(v, str):
            shown[k] = v[:120] + ("…" if len(v) > 120 else "")
        else:
            shown[k] = v
    lines.append(json.dumps(shown, ensure_ascii=False, indent=2))
    lines.append("```")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_dir", default=DEFAULT_IN)
    parser.add_argument("--report", default=str(_repo_report()))
    args = parser.parse_args(argv)

    in_dir = Path(args.in_dir)
    report_path = Path(args.report)
    results = {}

    for name in INDICES:
        path = in_dir / f"{name}.jsonl"
        if not path.is_file():
            print(f"MISSING {path}", flush=True)
            return 2
        print(f"PROBE {name}", flush=True)
        results[name] = probe_file(path)
        print(f"PROBE_DONE {name} n={results[name]['n']}", flush=True)

    life_set = results["kg-rag_life"]["field_set"]
    lines: list[str] = []
    w = lines.append

    w("# 3.5 → 4.0 继承：字段勘探报告")
    w("")
    w(f"数据目录：`{in_dir}`")
    w("")
    w("源索引只读导出（已排除 dense_vector）。本报告不涉及切块与写入 ES。")
    w("")

    for name in INDICES:
        r = results[name]
        w(f"## `{name}`")
        w("")
        w(f"- 条数：{r['n']:,}")
        w(
            f"- chunk_id 总数 / 去重：{r['chunk_id_total']:,} / {r['chunk_id_unique']:,}"
            f"（{'等于总条数' if r['chunk_id_unique'] == r['n'] else '**不等于总条数**'}）"
        )
        w("")
        w("### 字段清单")
        w("")
        w("| 字段 | 出现条数 | 出现率 | 类型分布 |")
        w("|---|---:|---:|---|")
        for k, meta in r["fields"].items():
            w(
                f"| `{k}` | {meta['present']:,} | {meta['rate']*100:.1f}% | {meta['types']} |"
            )
        w("")
        w("### 标题空值率")
        w("")
        n = r["n"] or 1
        w(
            f"- `book_title` 空：{r['empty_book']:,}（{r['empty_book']/n*100:.2f}%）"
        )
        w(
            f"- `message_title` 空：{r['empty_msg']:,}（{r['empty_msg']/n*100:.2f}%）"
        )
        w(
            f"- `section_title` 空：{r['empty_sec']:,}（{r['empty_sec']/n*100:.2f}%）"
        )
        w("")
        w(
            f"- `text` 以 `book_title` 开头：{r['title_in_text']:,} / {r['n']:,}"
            f"（{r['title_in_text']/n*100:.2f}%）"
        )
        w("")
        w("### 样本 3 条（text 截前 120 字）")
        w("")
        for i, sample in enumerate(r["samples"], 1):
            w(f"#### 样本 {i}")
            w("")
            lines.extend(_sample_block(sample))
            w("")

    w("## 与 `kg-rag_life` 字段集对照")
    w("")
    w(f"`kg-rag_life` 字段集（{len(life_set)}）：`{'`, `'.join(sorted(life_set))}`")
    w("")
    gate_text_ok = True
    map_note_differs = False
    for name in INDICES:
        if name == "kg-rag_life":
            continue
        s = results[name]["field_set"]
        only_life = sorted(life_set - s)
        only_other = sorted(s - life_set)
        same = s == life_set
        w(f"### `{name}`")
        w("")
        if same:
            w("- 与 life **一致**")
        else:
            w("- 与 life **不一致**")
            w(f"- 仅 life 有：{only_life if only_life else '（无）'}")
            w(f"- 仅本索引有：{only_other if only_other else '（无）'}")
        w("")
        if name in TEXT_FOUR and not same:
            gate_text_ok = False
        if name == "kg-rag_map_note" and not same:
            map_note_differs = True

    w("## A4 硬闸门判定")
    w("")
    if gate_text_ok:
        w(
            "- `life` / `cwwl` / `cwwn` / `others` 字段集与 `kg-rag_life` **一致** → "
            "**四个职事正文索引可进入阶段 B**。"
        )
    else:
        w(
            "- 四个职事正文索引字段集存在不一致 → **阶段 B 全部停下，等确认**。"
        )
    if map_note_differs:
        w(
            "- `kg-rag_map_note` 字段集与 life **不同**（预期）→ "
            "**map_note 本项停下，只记入本报告，等确认后再做**。"
        )
    else:
        w(
            "- `kg-rag_map_note` 字段集与 life **意外一致** → 仍建议人工确认后再进 B。"
        )
    w("")
    w("proceed_text_four: {0}".format("yes" if gate_text_ok else "no"))
    w("proceed_map_note: no")
    w("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {report_path}", flush=True)
    print(
        f"GATE text_four={'yes' if gate_text_ok else 'no'} "
        f"map_note={'no' if map_note_differs or True else 'yes'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
