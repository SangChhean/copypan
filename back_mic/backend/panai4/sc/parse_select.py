# -*- coding: utf-8 -*-
"""解析选词模型输出。"""
from __future__ import annotations

import re

_SECTION_MARKS = (
    ("最内在", "【最内在】"),
    ("内在", "【内在】"),
    ("外在", "【外在】"),
)
_LINE_RE = re.compile(r"^\s*(.+?)｜依据[：:]\s*(.*?)\s*$")


def parse_select_output(raw: str, tier_of: dict[str, str], has_3a: dict[str, bool]) -> list[dict]:
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    # split by section headers
    positions: list[tuple[int, str]] = []
    for tier, mark in _SECTION_MARKS:
        idx = text.find(mark)
        if idx >= 0:
            positions.append((idx, tier))
    positions.sort()
    sections: dict[str, str] = {t: "" for t, _ in _SECTION_MARKS}
    for i, (pos, tier) in enumerate(positions):
        start = pos + len(f"【{tier}】")
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        sections[tier] = text[start:end]

    items: list[dict] = []
    for tier_by_model, _mark in _SECTION_MARKS:
        body = sections.get(tier_by_model, "")
        for line in body.split("\n"):
            line = line.strip()
            if not line or line == "无":
                continue
            m = _LINE_RE.match(line)
            if not m:
                # tolerate lines without 依据
                if "｜" in line:
                    name, _, rest = line.partition("｜")
                    name = name.strip()
                    reason = rest.replace("依据：", "").replace("依据:", "").strip()
                else:
                    name, reason = line, ""
            else:
                name, reason = m.group(1).strip(), m.group(2).strip()
            if not name:
                continue
            actual = tier_of.get(name)
            in_list = actual is not None
            items.append(
                {
                    "name": name,
                    "tier_by_model": tier_by_model,
                    "tier_actual": actual or tier_by_model,
                    "reason": reason,
                    "in_list": in_list,
                    "has_3a": bool(has_3a.get(name)) if in_list else False,
                    "tier_mismatch": bool(in_list and actual != tier_by_model),
                }
            )
    return items
