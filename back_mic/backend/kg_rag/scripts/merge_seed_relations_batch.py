# -*- coding: utf-8 -*-
"""将一批「from TYPE to」行合并进 seed_concepts_test1.json 的 relations，去重并报告统计。"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seed_concepts_test1.json"
_SCRIPT_DIR = Path(__file__).resolve().parent
# 支持 relations_batch.txt 或 relations_batch_1.txt … 多段合并
def _load_batch_text() -> str:
    single = _SCRIPT_DIR / "relations_batch.txt"
    if single.exists():
        return single.read_text(encoding="utf-8")
    parts = sorted(_SCRIPT_DIR.glob("relations_batch_*.txt"))
    if not parts:
        raise FileNotFoundError(
            f"未找到 {single} 或 relations_batch_*.txt，请放入关系文本后再运行。"
        )
    return "\n".join(p.read_text(encoding="utf-8") for p in parts)

# 用户笔误或与概念表不一致时的规范化（两端都应用）
CANONICAL = {
    "晨兴复兴": "晨晨复兴",
    "信": "信徒的信",
}

REL_PATTERN = re.compile(
    r"^(.+?)\s+(LEADS_TO|OPPOSES|PRACTICED_AS|CONTAINS|EXPERIENCES|LOCATED_IN)\s+(.+)$"
)


def norm(s: str) -> str:
    s = (s or "").strip()
    return CANONICAL.get(s, s)


def parse_lines(text: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if " CONTAINS / LOCATED_IN " in line:
            left, right = line.split(" CONTAINS / LOCATED_IN ", 1)
            lf = norm(left.strip())
            rt = norm(right.strip())
            out.append((lf, "CONTAINS", rt))
            out.append((lf, "LOCATED_IN", rt))
            continue
        m = REL_PATTERN.match(line)
        if not m:
            raise ValueError(f"无法解析行: {raw!r}")
        a, typ, b = m.group(1), m.group(2), m.group(3)
        out.append((norm(a), typ, norm(b.strip())))
    return out


def main() -> None:
    text = _load_batch_text()
    parsed = parse_lines(text)
    data = json.loads(SEED.read_text(encoding="utf-8"))
    names = {c["name"] for c in data.get("concepts", []) if isinstance(c, dict) and c.get("name")}

    existing: list[dict] = list(data.get("relations", []))
    key = lambda r: (r.get("from"), r.get("type"), r.get("to"))
    seen_existing = {key(r) for r in existing if isinstance(r, dict)}

    from collections import Counter

    cnt = Counter(parsed)
    dup_in_batch = [k for k, v in cnt.items() if v > 1]

    dup_vs_seed = [t for t in set(parsed) if t in seen_existing]

    missing_from: set[str] = set()
    missing_to: set[str] = set()
    for f, _, t in parsed:
        if f not in names:
            missing_from.add(f)
        if t not in names:
            missing_to.add(t)

    added = 0
    for f, typ, t in parsed:
        if (f, typ, t) in seen_existing:
            continue
        existing.append({"from": f, "to": t, "type": typ})
        seen_existing.add((f, typ, t))
        added += 1

    data["relations"] = existing
    SEED.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=== 合并结果 ===")
    print(f"批次解析边数: {len(parsed)}")
    dup_extra = sum(cnt[k] - 1 for k in dup_in_batch)
    print(f"批次内完全重复的三元组种类: {len(dup_in_batch)}，多出的条数: {dup_extra}")
    print(f"与 seed 已有关系重复: {len(dup_vs_seed)} 条")
    print(f"新写入: {added} 条")
    print(f"合并后 relations 总数: {len(existing)}")
    if missing_from or missing_to:
        print("\n=== 不在 concepts.name 中的端点 ===")
        if missing_from:
            print("from 缺失:", sorted(missing_from))
        if missing_to:
            print("to 缺失:", sorted(missing_to))
    else:
        print("\n所有边的 from / to 均在 concepts.name 中（规范化后）。")


if __name__ == "__main__":
    main()
