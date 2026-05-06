# -*- coding: utf-8 -*-
"""将 merged_output2.txt 合并进 seed_concepts_1.json，并输出越界关系清单。

规则：
1) 复用现有关系解析规则（按关系类型关键字切分，支持无空格写法）。
2) 与 seed_concepts_1.json 现有关系按 (from, type, to) 去重。
3) 即使 from/to 不在 旧词∪新词 中，也照样添加到 relations。
4) 将上述“越界关系”单独写到报告文件，供人工删除判断。
"""
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


def parse_line(line: str):
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    for t in TYPES_SORTED:
        i = s.find(t)
        if i < 0:
            continue
        before = s[:i].strip()
        after = s[i + len(t) :].strip()
        if not before or not after:
            continue
        return before, t, after
    return None


def main() -> None:
    seed_old = ROOT / "seed_concepts.json"
    seed_new = ROOT / "seed_concepts_1.json"
    merged2 = SCRIPTS / "merged_output2.txt"
    report = ROOT / "seed_concepts_1_merged_output2_out_of_vocab.txt"

    old_names = {c["name"] for c in json.loads(seed_old.read_text(encoding="utf-8"))["concepts"]}

    data = json.loads(seed_new.read_text(encoding="utf-8"))
    new_names = {c["name"] for c in data.get("concepts", [])}
    allowed = old_names | new_names

    existing = {
        (str(r.get("from", "")).strip(), str(r.get("type", "")).strip(), str(r.get("to", "")).strip())
        for r in data.get("relations", [])
    }
    relations = list(data.get("relations", []))

    lines = merged2.read_text(encoding="utf-8").splitlines()
    parsed = []
    bad_lines: list[tuple[int, str]] = []
    for ln, line in enumerate(lines, start=1):
        p = parse_line(line)
        if p is None:
            if line.strip():
                bad_lines.append((ln, line))
            continue
        parsed.append((ln, p[0], p[1], p[2]))

    added: list[tuple[int, dict[str, str]]] = []
    dup_count = 0
    for ln, fr, typ, to in parsed:
        k = (fr, typ, to)
        if k in existing:
            dup_count += 1
            continue
        existing.add(k)
        obj = {"from": fr, "to": to, "type": typ}
        relations.append(obj)
        added.append((ln, obj))

    out_of_vocab: list[tuple[int, dict[str, str], str]] = []
    for ln, obj in added:
        fr = obj["from"]
        to = obj["to"]
        reasons: list[str] = []
        if fr not in allowed:
            reasons.append(f"from不在旧∪新: {fr}")
        if to not in allowed:
            reasons.append(f"to不在旧∪新: {to}")
        if reasons:
            out_of_vocab.append((ln, obj, "；".join(reasons)))

    data["relations"] = relations
    seed_new.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_lines = [
        f"merged_output2 原始行数: {len(lines)}",
        f"可解析关系行: {len(parsed)}",
        f"无法解析非空行: {len(bad_lines)}",
        f"与 seed_concepts_1 已有关系重复(跳过): {dup_count}",
        f"本次新增关系: {len(added)}",
        f"本次新增中 from/to 不在旧∪新 的关系: {len(out_of_vocab)}",
        "",
        "--- 本次新增的越界关系（请人工判定是否删除）---",
    ]
    if out_of_vocab:
        for ln, obj, why in out_of_vocab:
            report_lines.append(
                f"L{ln}: {obj['from']} -[{obj['type']}]-> {obj['to']} | {why}"
            )
    else:
        report_lines.append("（无）")

    if bad_lines:
        report_lines.extend(["", "--- 无法解析的非空行（前50）---"])
        for ln, t in bad_lines[:50]:
            report_lines.append(f"L{ln}: {t}")

    report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"updated={seed_new}")
    print(f"report={report}")
    print(
        f"parsed={len(parsed)} added={len(added)} dup={dup_count} "
        f"out_of_vocab_added={len(out_of_vocab)} bad={len(bad_lines)}"
    )


if __name__ == "__main__":
    main()
