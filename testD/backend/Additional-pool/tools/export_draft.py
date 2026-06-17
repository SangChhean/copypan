# -*- coding: utf-8 -*-
"""从翻译结果导出 draft.jsonl。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from testD.backend.additional_pool import normalize_zh


def from_response(data: dict, out_lines: list[str] | None = None) -> list[dict]:
    refs = data.get("refs") or []
    result = (data.get("result") or "").strip()
    if out_lines is None:
        out_lines = [ln for ln in result.splitlines() if ln.strip()]

    rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    if len(out_lines) != len(refs):
        print(
            f"warning: refs 行数 {len(refs)} 与译文行数 {len(out_lines)} 不一致",
            file=sys.stderr,
        )
    for i, group in enumerate(refs):
        st = group.get("stats") or {}
        if st.get("additional_pool_line"):
            continue
        zh = (group.get("original_line") or "").strip()
        en = (out_lines[i] if i < len(out_lines) else "").strip()
        if not en:
            continue
        if not zh:
            continue
        rows.append({
            "zh": zh,
            "en": en,
            "norm_zh": normalize_zh(zh),
            "saved_at": now,
            "source": "enhanced_translate",
        })
    return rows


def from_zh_en(zh_path: Path, en_path: Path) -> list[dict]:
    zh_lines = [ln.strip() for ln in zh_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    en_lines = [ln.strip() for ln in en_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(zh_lines) != len(en_lines):
        raise ValueError(f"中英文行数不一致: zh={len(zh_lines)} en={len(en_lines)}")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "zh": zh,
            "en": en,
            "norm_zh": normalize_zh(zh),
            "saved_at": now,
            "source": "enhanced_translate",
        }
        for zh, en in zip(zh_lines, en_lines)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 draft.jsonl")
    parser.add_argument("--response", type=Path, help="API 响应 JSON 文件")
    parser.add_argument("--zh", type=Path, help="中文纲目文本")
    parser.add_argument("--en", type=Path, help="英文纲目文本")
    parser.add_argument("-o", "--output", type=Path, required=True, help="输出 draft.jsonl")
    args = parser.parse_args()

    if args.response:
        data = json.loads(args.response.read_text(encoding="utf-8"))
        rows = from_response(data)
    elif args.zh and args.en:
        rows = from_zh_en(args.zh, args.en)
    else:
        parser.error("请指定 --response 或 --zh + --en")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"已导出 {len(rows)} 条 → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
