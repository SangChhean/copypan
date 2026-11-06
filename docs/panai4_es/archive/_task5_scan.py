# -*- coding: utf-8 -*-
"""Task5 read-only scanner. Do not commit."""
from __future__ import annotations

import os
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"G:\copypan")
os.chdir(ROOT)

status = subprocess.check_output(
    ["git", "status", "--short"], text=True, encoding="utf-8", errors="replace"
).splitlines()
mod = []
unt = []
for ln in status:
    if not ln.strip():
        continue
    code = ln[:2]
    path = ln[3:].strip().strip('"')
    if " -> " in path:
        path = path.split(" -> ")[-1]
    if code.strip() == "??":
        unt.append(path)
    else:
        mod.append((code, path))

print("modified", len(mod), "untracked", len(unt))


def group(path: str) -> str:
    p = path.replace("\\", "/")
    if "kg_rag/" in p:
        return "B_kg_rag"
    if "/graph/" in p or "panai4_graph" in p:
        return "C_graph"
    if "docs/panai4_es" in p:
        return "E_docs_es"
    if any(
        x in p
        for x in (
            "panai4/outline",
            "panai4/bible",
            "panai4/inherit",
            "panai4/pano",
            "probe_",
            "apply_life_fix",
            "index_to_es",
            "gen_embeddings",
            "build_chunks",
            "convert_outline",
            "push_remote",
        )
    ):
        return "D_es_scripts"
    if any(
        x in p
        for x in (
            "PanAI4Test",
            "PanAI4Prompts",
            "panai4_ui",
            "panai4_prompts",
            "panai4_sc",
            "panai4_fullflow",
            "export_docx",
            "features/progress",
            "pipeline",
            "runner",
        )
    ):
        return "A_fullflow"
    if p.endswith((".pyc", ".bak", ".log")) or "__pycache__" in p or p.startswith("logs/"):
        return "F_nocommit"
    if p.endswith((".json", ".jsonl", ".csv")) and "docs/" in p and "archive" in p:
        return "E_docs_es"
    return "G_other"


gm = Counter()
gu = Counter()
gm_files = defaultdict(list)
gu_files = defaultdict(list)
for code, p in mod:
    g = group(p)
    gm[g] += 1
    gm_files[g].append((code, p))
for p in unt:
    g = group(p)
    gu[g] += 1
    gu_files[g].append(p)

print("MOD groups", dict(gm))
print("UNT groups", dict(gu))
for g in sorted(set(list(gm) + list(gu))):
    print("===", g, "M", gm[g], "U", gu[g])
    for x in gm_files[g]:
        print(" M", x)
    for x in gu_files[g]:
        print(" U", x)

print("=== LARGE UNT >5MB")
for p in unt:
    fp = ROOT / p
    try:
        sz = fp.stat().st_size
    except OSError:
        continue
    if sz > 5 * 1024 * 1024:
        print(f"{sz / 1024 / 1024:.1f}MB\t{p}")

secret_re = re.compile(
    r"(api[_-]?key|password|secret|token)\s*[=:]\s*['\"][^'\"]{8,}",
    re.I,
)
print("=== SECRET-ISH")
for p in [x for _, x in mod] + unt:
    if "panai4" not in p and "kg_rag" not in p:
        continue
    fp = ROOT / p
    if not fp.is_file() or fp.suffix.lower() not in {".py", ".vue", ".ts", ".js", ".md"}:
        continue
    if fp.stat().st_size > 2_000_000:
        continue
    try:
        text = fp.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    for i, line in enumerate(text.splitlines(), 1):
        if not secret_re.search(line):
            continue
        low = line.lower()
        if any(x in low for x in ("getenv", "environ", "example", "your_", "xxx", "***", "placeholder")):
            continue
        print(f"{p}:{i}:疑似密钥赋值")

path_re = re.compile(r"[GC]:\\[^\s'\"]+|G:/[^\s'\"]+")
print("=== PATH HARDCODE")
for p in [x for _, x in mod] + unt:
    if not p.endswith(".py"):
        continue
    fp = ROOT / p
    if not fp.is_file() or fp.stat().st_size > 1_000_000:
        continue
    try:
        text = fp.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    n = len(path_re.findall(text))
    if n:
        print(f"{p}: {n} hits")

# ignored sample via check-ignore on common junk
print("=== check-ignore samples")
for cand in [
    "back_mic/backend/.env",
    "back_mic/backend/panai4/outline/config.py.bak_20261106",
    "logs/life_fix_apply_20261106_150321.log",
    "back_mic/backend/panai4/outline/__pycache__/apply_life_fix.cpython-310.pyc",
]:
    r = subprocess.run(
        ["git", "check-ignore", "-v", cand],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(cand, "->", (r.stdout or r.stderr or "").strip() or "(not ignored)")
