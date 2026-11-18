# -*- coding: utf-8 -*-
"""生成 qa4/data/bible_data.manifest.json（每个文件的相对路径、SHA256、章数、节数）。

离线、只读 bible_data；只写 manifest 一个文件。
用法：python qa4/backend/tools/build_bible_manifest.py [--check]
  --check：不写文件，只核对现有 manifest 与目录是否一致（退出码 0/1）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripture.bible_text import file_stats  # noqa: E402

QA4_ROOT = _BACKEND.parent


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build(bible_dir: Path) -> dict:
    files = []
    for p in sorted(bible_dir.glob("*.json")):
        st = file_stats(p)
        files.append(
            {
                "path": f"bible_data/{p.name}",
                "sha256": _sha256(p),
                "bytes": p.stat().st_size,
                "chapters": st["chapters"],
                "verses": st["verses"],
            }
        )
    return {
        "files": files,
        "totals": {
            "files": len(files),
            "chapters": sum(f["chapters"] for f in files),
            "verses": sum(f["verses"] for f in files),
        },
    }


def check(bible_dir: Path, manifest_path: Path) -> list[str]:
    fails: list[str] = []
    if not manifest_path.is_file():
        return ["缺少 data/bible_data.manifest.json"]
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_name = {f["path"].split("/", 1)[1]: f for f in man.get("files") or []}
    disk = {p.name: p for p in bible_dir.glob("*.json")}
    if set(by_name) != set(disk):
        fails.append(
            f"文件集合不一致：仅 manifest={sorted(set(by_name) - set(disk))[:5]} "
            f"仅目录={sorted(set(disk) - set(by_name))[:5]}"
        )
    for name, meta in by_name.items():
        p = disk.get(name)
        if p is None:
            continue
        if _sha256(p) != meta.get("sha256"):
            fails.append(f"SHA256 不符：bible_data/{name}")
    return fails


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bible-dir", type=Path, default=QA4_ROOT / "data" / "bible_data")
    ap.add_argument("--out", type=Path, default=QA4_ROOT / "data" / "bible_data.manifest.json")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        fails = check(args.bible_dir, args.out)
        for f in fails:
            print("FAIL", f)
        print("OK" if not fails else f"FAIL n={len(fails)}")
        return 0 if not fails else 1
    man = build(args.bible_dir)
    args.out.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(man["totals"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
