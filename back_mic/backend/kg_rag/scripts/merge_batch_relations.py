# -*- coding: utf-8 -*-
"""Parse batch relation lines and merge into seed_concepts.json."""
import json
import sys
from pathlib import Path

TYPES_SORTED = sorted(
    ("LEADS_TO", "CONTAINS", "OPPOSES", "PRACTICED_AS", "EXPERIENCES", "LOCATED_IN"),
    key=len,
    reverse=True,
)


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


def main():
    root = Path(__file__).resolve().parents[2]
    seed_path = root / "seed_concepts.json"
    raw_name = sys.argv[1] if len(sys.argv) > 1 else "batch_relations_raw.txt"
    raw_path = Path(__file__).with_name(raw_name)

    data = json.loads(seed_path.read_text(encoding="utf-8"))
    names = {c["name"] for c in data["concepts"]}
    existing_keys = {(r["from"], r["to"], r["type"]) for r in data["relations"]}

    lines = raw_path.read_text(encoding="utf-8").splitlines()
    parsed = []
    bad_lines = []
    for ln, line in enumerate(lines, 1):
        p = parse_line(line)
        if p is None:
            if line.strip():
                bad_lines.append((ln, line))
            continue
        parsed.append(p)

    seen_batch = set()
    dup_in_batch = []
    for t in parsed:
        if t in seen_batch:
            dup_in_batch.append(t)
        seen_batch.add(t)

    missing = []
    new_objs = []
    skipped_existing = []
    for fr, typ, to in parsed:
        if fr not in names:
            missing.append(("from", fr, typ, to))
            continue
        if to not in names:
            missing.append(("to", fr, typ, to))
            continue
        key = (fr, to, typ)
        if key in existing_keys:
            skipped_existing.append(key)
            continue
        new_objs.append({"from": fr, "to": to, "type": typ})
        existing_keys.add(key)

    data["relations"].extend(new_objs)
    seed_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Parsed OK: {len(parsed)} lines")
    print(f"Bad lines (unparsed): {len(bad_lines)}")
    if bad_lines:
        for ln, t in bad_lines[:20]:
            print(f"  L{ln}: {t!r}")
    print(f"Duplicate within batch file: {len(dup_in_batch)}")
    print(f"Skipped (already in seed): {len(skipped_existing)}")
    print(f"Missing concept (skipped edge): {len(missing)}")
    for m in missing[:30]:
        print(f"  {m}")
    if len(missing) > 30:
        print(f"  ... and {len(missing) - 30} more")
    print(f"Appended new relations: {len(new_objs)}")


if __name__ == "__main__":
    main()
