# -*- coding: utf-8 -*-
"""qa4 / front_qa 文件清单与对照（SHA256）。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path
from typing import Iterable, Optional

_BACKEND = Path(__file__).resolve().parents[1]
_QA4 = _BACKEND.parent
_REPO = _QA4.parent

SKIP_DIR_NAMES = {".venv", "node_modules", "__pycache__", ".git", "dist"}

# 保护清单：相对仓库根的路径前缀或精确文件（POSIX 风格）
PROTECTED_PREFIXES = (
    "qa4/backend/scripture/",
    "qa4/backend/hymn/",
    "qa4/data/",
    "front_qa/",
)
PROTECTED_EXACT = {
    "qa4/backend/retrieval/targeted.py",
    "qa4/backend/pipeline/step03_rules.py",
    "qa4/backend/tests/_fast_hymn_env.py",
    "qa4/backend/tools/verify_stage2.py",
}


def _is_protected(rel: str) -> bool:
    r = rel.replace("\\", "/")
    if r in PROTECTED_EXACT:
        return True
    if any(r.startswith(p) for p in PROTECTED_PREFIXES):
        return True
    if r.startswith("qa4/backend/tests/") and r.endswith(".py"):
        # 已有测试文件视为保护；新增无法在清单规则里区分，对照时靠 before/after
        return True
    if r.startswith("qa4/backend/tools/probe_") and r.endswith(".py"):
        return True
    if "bible_data" in r.replace("\\", "/"):
        return True
    return False


def _should_skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parts = set(p.relative_to(root).parts)
        if parts & SKIP_DIR_NAMES:
            continue
        # 跳过路径中任一目录名
        if any(_should_skip_dir(x) for x in p.relative_to(root).parts[:-1]):
            continue
        yield p


def _sha256(path: Path, *, content: bool) -> str:
    if not content:
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_rows(repo: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    targets = [
        ("qa4", repo / "qa4"),
        ("front_qa", repo / "front_qa"),
    ]
    for label, root in targets:
        if not root.is_dir():
            continue
        for p in _iter_files(root):
            try:
                rel = p.relative_to(repo).as_posix()
            except ValueError:
                rel = f"{label}/{p.name}"
            size = p.stat().st_size
            # qa4/data 下只记路径与大小，不算内容哈希（体积大）
            hash_content = not rel.startswith("qa4/data/")
            digest = _sha256(p, content=hash_content) if hash_content else f"size-only:{size}"
            rows.append(
                {
                    "path": rel,
                    "size": str(size),
                    "sha256": digest,
                    "protected": "1" if _is_protected(rel) else "0",
                }
            )
    rows.sort(key=lambda r: r["path"])
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "size", "sha256", "protected"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def load_csv(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            out[row["path"]] = row
    return out


def compare(before: Path, after: Path, diff_out: Path) -> dict[str, int]:
    a = load_csv(before)
    b = load_csv(after)
    added = sorted(set(b) - set(a))
    deleted = sorted(set(a) - set(b))
    common = set(a) & set(b)
    modified = sorted(p for p in common if a[p]["sha256"] != b[p]["sha256"] or a[p]["size"] != b[p]["size"])
    diff_out.parent.mkdir(parents=True, exist_ok=True)
    stats = {"added": 0, "modified": 0, "deleted": 0, "protected_changed": 0}
    with diff_out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["change", "path", "size_before", "size_after", "sha_before", "sha_after", "flag"],
        )
        w.writeheader()
        for p in added:
            # 新增文件（含新增测试）不算破坏保护清单；仅 modified/deleted 标 PROTECTED_CHANGED
            w.writerow(
                {
                    "change": "added",
                    "path": p,
                    "size_before": "",
                    "size_after": b[p]["size"],
                    "sha_before": "",
                    "sha_after": b[p]["sha256"],
                    "flag": "",
                }
            )
            stats["added"] += 1
        for p in modified:
            flag = "PROTECTED_CHANGED" if _is_protected(p) else ""
            if flag:
                stats["protected_changed"] += 1
            w.writerow(
                {
                    "change": "modified",
                    "path": p,
                    "size_before": a[p]["size"],
                    "size_after": b[p]["size"],
                    "sha_before": a[p]["sha256"],
                    "sha_after": b[p]["sha256"],
                    "flag": flag,
                }
            )
            stats["modified"] += 1
        for p in deleted:
            flag = "PROTECTED_CHANGED" if _is_protected(p) else ""
            if flag:
                stats["protected_changed"] += 1
            w.writerow(
                {
                    "change": "deleted",
                    "path": p,
                    "size_before": a[p]["size"],
                    "size_after": "",
                    "sha_before": a[p]["sha256"],
                    "sha_after": "",
                    "flag": flag,
                }
            )
            stats["deleted"] += 1
    return stats


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="qa4/front_qa 文件清单")
    ap.add_argument("--out", type=Path, required=True, help="输出目录或 CSV 路径")
    ap.add_argument("--repo", type=Path, default=_REPO)
    ap.add_argument("--compare", type=Path, default=None, help="之前的清单 CSV，生成 diff")
    ap.add_argument("--name", type=str, default="manifest.csv")
    args = ap.parse_args(argv)

    out = args.out
    if out.suffix.lower() == ".csv":
        manifest_path = out
        out_dir = out.parent
    else:
        out_dir = out
        manifest_path = out_dir / args.name

    rows = build_rows(args.repo)
    write_csv(manifest_path, rows)
    print(f"MANIFEST={manifest_path} n={len(rows)}")

    if args.compare:
        diff_path = out_dir / "diff_before_after.csv"
        if args.compare.name.startswith("manifest_") and manifest_path.name.startswith("manifest_"):
            diff_path = out_dir / "diff_before_after.csv"
        stats = compare(args.compare, manifest_path, diff_path)
        print(f"DIFF={diff_path} {stats}")
        if stats["protected_changed"]:
            print(f"WARN PROTECTED_CHANGED={stats['protected_changed']}")
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
