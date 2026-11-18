# -*- coding: utf-8 -*-
"""检查提示词：大小、变量一致性、残留占位、禁止写法、固定段提示。"""

from __future__ import annotations

import argparse
import json
import re
import string
import sys
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_FORBIDDEN = [
    (re.compile(r"预填|事先写好回复|先写好答案"), "要求模型预填回复"),
    (re.compile(r"```\s*json|用 markdown 围栏|用围栏包住 JSON", re.I), "要求输出 markdown 围栏 JSON"),
    (re.compile(r"temperature\s*=|温度\s*[=：:]"), "写死温度"),
]


def estimate_tokens(text: str) -> float:
    return round(len(text) * 1.2, 1)


def analyze_one(step: str, channel: str) -> dict[str, Any]:
    from prompts.loader import PromptRegistry

    reg = PromptRegistry(channel=channel)
    tpl = reg.get(step)
    fields = sorted({f for _, f, _, _ in string.Formatter().parse(tpl.text) if f})
    declared = list(tpl.variables)
    missing_in_text = [v for v in declared if v not in fields]
    extra_in_text = [v for v in fields if v not in declared]
    sample = {v: f"<{v}>" for v in declared}
    rendered = tpl.render(**sample)
    leftover = re.findall(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", rendered)
    forbid_hits = []
    for pat, label in _FORBIDDEN:
        if pat.search(tpl.text):
            forbid_hits.append(label)
    # 固定大块是否靠前：看「可变」关键词首次出现位置
    var_markers = ("问题（改写后）", "子问题", "可变部分", "本问线索", "当前追问")
    first_var = min((tpl.text.find(m) for m in var_markers if m in tpl.text), default=-1)
    fixed_front = first_var > 200 or step == "step5"  # step5 词表在 system，正文规则在前亦可
    return {
        "step": step,
        "channel": channel,
        "version": tpl.version,
        "draft": tpl.draft,
        "placeholder": tpl.placeholder,
        "chars": len(tpl.text),
        "est_tokens": estimate_tokens(tpl.text),
        "variables_declared": declared,
        "variables_in_text": fields,
        "missing_in_text": missing_in_text,
        "extra_in_text": extra_in_text,
        "leftover_placeholders": leftover,
        "forbidden": forbid_hits,
        "first_variable_marker_at": first_var,
        "fixed_block_likely_front": bool(fixed_front),
        "ok": not missing_in_text and not extra_in_text and not leftover and not forbid_hits,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", choices=["stable", "draft", "both"], default="both")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(r"G:\PanAI4.0专用\logs\stage45\check_prompts_draft.json"),
        help="结果 JSON（默认仓库外 logs/stage45）",
    )
    args = ap.parse_args(argv)
    channels = ["stable", "draft"] if args.channel == "both" else [args.channel]
    from prompts.loader import PromptRegistry

    rows = []
    for ch in channels:
        reg = PromptRegistry(channel=ch)
        for step in reg.steps():
            rows.append(analyze_one(step, ch))
    text = json.dumps(rows, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"OUT={args.out}")
    print(text)
    bad = [r for r in rows if not r["ok"]]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
