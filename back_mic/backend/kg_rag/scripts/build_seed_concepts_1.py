# -*- coding: utf-8 -*-
"""一次性脚本：从 new_name.txt + merged_output1.txt 生成 seed_concepts_1.json 与校验报告。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # back_mic/backend
SCRIPTS = Path(__file__).resolve().parent

TYPES_SORTED = sorted(
    (
        "LEADS_TO",
        "CONTAINS",
        "OPPOSES",
        "PRACTICED_AS",
        "EXPERIENCES",
        "LOCATED_IN",
        "SUPPORTED_BY",
    ),
    key=len,
    reverse=True,
)


def filter_relations(
    relations: list[dict[str, str]],
    allowed_union: set[str],
) -> tuple[list[dict[str, str]], int]:
    """仅保留两端均在 allowed_union 内的边。

    说明：源文件中「渐进 LEADS_TO 」缺目标行无法被 parse_line 解析，不会进入 relations，
    因此不存在「只删那一条」的 JSON 操作；其余 渐进-[LEADS_TO]->* 正常保留。
    """
    out: list[dict[str, str]] = []
    drop_orphan = 0
    for r in relations:
        if r["from"] not in allowed_union or r["to"] not in allowed_union:
            drop_orphan += 1
            continue
        out.append(r)
    return out, drop_orphan


def parse_line(line: str):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    for t in TYPES_SORTED:
        i = line.find(t)
        if i < 0:
            continue
        before = line[:i].strip()
        after = line[i + len(t) :].strip()
        if not before or not after:
            continue
        return before, t, after
    return None


def main() -> None:
    seed_path = ROOT / "seed_concepts.json"
    new_names_path = SCRIPTS / "new_name.txt"
    merged_path = SCRIPTS / "merged_output1.txt"
    out_json = ROOT / "seed_concepts_1.json"
    out_report = ROOT / "seed_concepts_1_orphan_relations.txt"

    old_names = {c["name"] for c in json.loads(seed_path.read_text(encoding="utf-8"))["concepts"]}

    new_order: list[str] = []
    seen_new: set[str] = set()
    for raw in new_names_path.read_text(encoding="utf-8").splitlines():
        name = raw.strip()
        if not name:
            continue
        if name in seen_new:
            continue
        seen_new.add(name)
        new_order.append(name)

    allowed_union = old_names | set(new_order)

    lines = merged_path.read_text(encoding="utf-8").splitlines()
    relations: list[dict[str, str]] = []
    keys_seen: set[tuple[str, str, str]] = set()
    bad_lines: list[tuple[int, str]] = []
    dup_in_file: list[tuple[str, str, str]] = []

    for ln, line in enumerate(lines, start=1):
        p = parse_line(line)
        if p is None:
            if line.strip():
                bad_lines.append((ln, line))
            continue
        fr, typ, to = p
        key = (fr, typ, to)
        if key in keys_seen:
            dup_in_file.append(key)
            continue
        keys_seen.add(key)
        relations.append({"from": fr, "to": to, "type": typ})

    relations_before_filter = len(relations)
    relations, drop_orphan = filter_relations(
        relations, allowed_union
    )

    payload = {
        "concepts": [{"name": n} for n in new_order],
        "relations": relations,
    }
    out_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report_lines = [
        f"旧词数量（seed_concepts.json concepts）: {len(old_names)}",
        f"新词数量（new_name.txt 去重后顺序保留）: {len(new_order)}",
        f"合并关系条数（merged 去重后，过滤前）: {relations_before_filter}",
        f"写入 seed_concepts_1.json 的关系条数（过滤后）: {len(relations)}",
        f"已删除：端点不在(旧∪新) 的条数: {drop_orphan}",
        f"无法解析的行数: {len(bad_lines)}",
        f"文件内重复（第二次及以后出现，已跳过）: {len(dup_in_file)}",
        "",
        "说明：JSON 中仅保留「from、to 均在 旧词∪新460」内的关系。",
        "源文件中无法解析的行（如「渐进 LEADS_TO 」缺目标）从不进入 relations，无需在 JSON 里删除。",
    ]
    if bad_lines:
        report_lines.extend(["", "--- 无法解析的行（前 50 条）---"])
        for ln, t in bad_lines[:50]:
            report_lines.append(f"  L{ln}: {t!r}")

    out_report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"Wrote {out_json}")
    print(f"Wrote {out_report}")
    print(
        f"relations_after_filter={len(relations)} dropped_orphan={drop_orphan}"
    )


if __name__ == "__main__":
    main()
