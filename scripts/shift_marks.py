#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch shift [FnN]/[Crx] marks one character left in bible_data JSON files."""

from __future__ import annotations

import json
import re
from pathlib import Path


MARK_GROUP = re.compile(r"((?:\[Fn\d+\]|\[Cr[a-z]\])+)")


def shift_marks_left(text: str) -> str:
    """
    把 [FnN] 和 [Crx] 往前移一个字符。
    例：「奴[Cra]仆」→「[Cra]奴仆」
    连续多个锚点（如[Fn1][Crb]）整体往前移一个字符。
    """
    if not text:
        return text

    result: list[str] = []
    i = 0
    while i < len(text):
        m = MARK_GROUP.search(text, i)
        if m is None:
            result.append(text[i:])
            break

        start = m.start()
        end = m.end()
        marks = m.group(1)

        # 普通文本先入 result
        result.append(text[i:start])

        # 将锚点组整体左移一个字符：取 result 最后片段尾字
        if start > 0 and result and result[-1]:
            prev_char = result[-1][-1]
            result[-1] = result[-1][:-1]
            result.append(marks + prev_char)
        else:
            # 开头无前置字符，保持不变
            result.append(marks)

        i = end

    return "".join(result)


def _run_unit_tests() -> None:
    cases = [
        ("奴[Cra]仆", "[Cra]奴仆"),
        ("腓[Fn1][Crb]立", "[Fn1][Crb]腓立"),
        ("[Cra]起初", "[Cra]起初"),
    ]
    for src, expected in cases:
        got = shift_marks_left(src)
        ok = got == expected
        print(f"{src} -> {got}  {'OK' if ok else 'FAIL'}")
        if not ok:
            raise AssertionError(f"case failed: {src} -> {got}, expect {expected}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    bible_dir = root / "back_qa" / "bible_data"
    files = sorted(p for p in bible_dir.glob("*.json") if p.name.lower() != "index.json")

    _run_unit_tests()

    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        chapters = data.get("chapters") or []
        for ch in chapters:
            verses = ch.get("verses") or []
            for v in verses:
                for key in ("text_gb", "text_big5"):
                    val = v.get(key)
                    if isinstance(val, str) and val:
                        v[key] = shift_marks_left(val)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{path.name} done")


if __name__ == "__main__":
    main()
