"""Build seed_concepts.json from 600.txt (one name per line) and merged_output.txt (from TYPE to)."""
import argparse
import json
import re
from pathlib import Path

REL_TYPES = (
    "CONTAINS",
    "EXPERIENCES",
    "LEADS_TO",
    "LOCATED_IN",
    "OPPOSES",
    "PRACTICED_AS",
)
LINE_RE = re.compile(
    rf"^(.+?)\s+({'|'.join(REL_TYPES)})\s+(.+)$"
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("concepts_txt", type=Path, help="e.g. 600.txt")
    ap.add_argument("merged_txt", type=Path, help="e.g. merged_output.txt")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "seed_concepts.json",
    )
    args = ap.parse_args()

    names = [
        line.strip()
        for line in args.concepts_txt.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rel_lines = [
        line.strip()
        for line in args.merged_txt.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    relations = []
    bad = []
    for i, line in enumerate(rel_lines, 1):
        m = LINE_RE.match(line)
        if not m:
            bad.append((i, line))
            continue
        frm, typ, to = m.group(1).strip(), m.group(2), m.group(3).strip()
        relations.append({"from": frm, "to": to, "type": typ})

    if bad:
        raise SystemExit(f"Unparseable lines: {bad[:5]} ... total {len(bad)}")

    data = {"concepts": [{"name": n} for n in names], "relations": relations}
    args.output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output}")
    print(f"concepts: {len(names)}, relations: {len(relations)}")


if __name__ == "__main__":
    main()
