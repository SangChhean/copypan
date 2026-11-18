# -*- coding: utf-8 -*-
"""检查开发题集是否与草稿提示词例子逐字重合（去标点后）。"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

_BACKEND = Path(__file__).resolve().parents[1]
_QA4 = _BACKEND.parent
_NOTES = _QA4 / "notes"
_TEXTS = _BACKEND / "prompts" / "texts"

_PUNCT_RE = re.compile(
    r"[\s"
    r"\u3000"
    r"，。？！、：；“”‘’（）【】\[\]《》〈〉·…—\-_,\.;:\!\?\(\)\{\}\"\'/\\|@#$%^&*+=~`]"
    r"+"
)


def normalize(text: str) -> str:
    return _PUNCT_RE.sub("", (text or "").strip()).lower()


def load_prompt_corpus(texts_dir: Path | None = None) -> str:
    root = texts_dir or _TEXTS
    parts: list[str] = []
    for p in sorted(root.glob("*_v0.1.txt")):
        parts.append(p.read_text(encoding="utf-8"))
    return normalize("\n".join(parts))


def load_dev_questions(csv_path: Path | None = None) -> list[dict[str, str]]:
    path = csv_path or (_NOTES / "dev_questions_draft.csv")
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = (row.get("id") or "").strip()
            if not qid or qid.startswith("_"):
                continue
            q = (row.get("问题") or "").strip()
            if not q:
                continue
            rows.append({"id": qid, "question": q})
    return rows


def find_overlaps(
    questions: Iterable[dict[str, str]],
    corpus_norm: str,
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for row in questions:
        nq = normalize(row["question"])
        if len(nq) < 4:
            # 过短单词题：整词命中才算
            if nq and nq in corpus_norm:
                hits.append({**row, "norm": nq})
            continue
        if nq and nq in corpus_norm:
            hits.append({**row, "norm": nq})
    return hits


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=_NOTES / "dev_questions_draft.csv")
    ap.add_argument("--texts", type=Path, default=_TEXTS)
    args = ap.parse_args(argv)
    corpus = load_prompt_corpus(args.texts)
    qs = load_dev_questions(args.csv)
    hits = find_overlaps(qs, corpus)
    print(f"QUESTIONS={len(qs)} OVERLAP={len(hits)}")
    for h in hits:
        print(f"HIT\t{h['id']}\t{h['question']}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
