# -*- coding: utf-8 -*-
"""解析经文 TXT 文件，输出 seed_scriptures.json。

行格式：
  - 序号+概念名：支持 16背、16、背、16.背、16 背、（16）背、(16)背 等变体
  - 希腊文： / 希伯来文：xxx（仅按顿号分割；中英文逗号视为词内字符）
  - 书卷章节与经文：全角空格、半角空白、或中英文冒号分隔（优先全角空格，再空白，再冒号）
  - 空行忽略

未匹配的非空行可写入 ``unparsed_out``（用于自检，避免静默丢失）。
每项为 dict：``file_line``（源文件物理行号，从 1 起）、``text``、``concept``（当前概念块，可能为 None）、``reason``（简要说明）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


def _strip_lang_outer_wrappers(s: str) -> str:
    """去掉整段或单项最外层的一对（）或 ()。

    仅当「首字符的开括号」与「末字符的闭括号」配对且包住**整段**时才剥除，
    避免把 ``（zoē），（bios）`` 误剥成 ``zoē），（bios``。
    """
    s = s.strip()
    for open_ch, close_ch in (("（", "）"), ("(", ")")):
        if len(s) < 2 or s[0] != open_ch or s[-1] != close_ch:
            continue
        depth = 0
        for i, ch in enumerate(s):
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    if i == len(s) - 1:
                        return s[1:-1].strip()
                    return s
        return s
    return s


def _split_lang_terms(body: str) -> list[str]:
    body = _strip_lang_outer_wrappers(body)
    if not body:
        return []
    # 注意：中英文逗号都可能是词形一部分（例如 "ho, (G3588)"），不能作为分隔符。
    raw_parts = re.split(r"[、]", body)
    out: list[str] = []
    for p in raw_parts:
        t = _strip_lang_outer_wrappers(p.strip())
        if t:
            out.append(t)
    return out


def _parse_scripture_line(line: str) -> tuple[str, str] | None:
    """经文行：优先全角空格，再首段空白，再首个中/英冒号。"""
    if "\u3000" in line:
        i = line.index("\u3000")
        sid, txt = line[:i].strip(), line[i + 1 :].strip()
        if sid and txt:
            return sid, txt
    m = re.match(r"^(.+?)(\s+)(.+)$", line)
    if m:
        sid, txt = m.group(1).strip(), m.group(3).strip()
        if sid and txt:
            return sid, txt
    m = re.match(r"^(.+?)([：:])(.+)$", line)
    if m:
        sid, txt = m.group(1).strip(), m.group(3).strip()
        if sid and txt:
            return sid, txt
    return None


def _unparsed_reason(line: str, *, current: dict | None, lang_before_concept: bool) -> str:
    """人类可读的未解析原因（启发式）。"""
    if lang_before_concept:
        return "希腊/希伯来行出现在第一个「序号+概念」行之前"
    if re.match(r"^(?:希腊文|希伯来文)[：:]\s*$", line):
        return (
            "希腊/希伯来行仅有前缀、冒号后无任何字符；"
            "当前语言行正则为 (.+) 要求冒号后至少一个字符，故整行未识别为语言行"
        )
    if current is None:
        return "非空行，且尚未进入任一概念块，也不匹配概念行格式"
    return "在当前概念块内：非希腊/希伯来行，且经文行未匹配（需出处与正文之间为全角空格、空白或冒号）"


def _append_unparsed(
    unparsed_out: list[dict],
    *,
    file_line: int,
    text: str,
    current: dict | None,
    reason: str,
) -> None:
    unparsed_out.append(
        {
            "file_line": file_line,
            "text": text,
            "concept": current["concept"] if current else None,
            "reason": reason,
        }
    )


def parse_txt(
    text: str,
    *,
    unparsed_out: list[dict] | None = None,
) -> list[dict]:
    lines = text.splitlines()
    results: list[dict] = []
    current: dict | None = None

    # 序号：(16) / （16） / 16；后可接顿号、句号、全角句点、空白等再概念名
    concept_re = re.compile(
        r"^(?:[（(]\s*(\d+)\s*[）)]|(\d+))"
        r"\s*[、。.,；;\s　．]*"
        r"(.+)$"
    )
    greek_or_hebrew_re = re.compile(r"^(?:希腊文|希伯来文)[：:](.+)$")

    for file_line, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        m_concept = concept_re.match(line)
        if m_concept:
            concept = (m_concept.group(3) or "").strip()
            if concept:
                current = {
                    "concept": concept,
                    "greek_terms": [],
                    "scriptures": [],
                }
                results.append(current)
            continue

        m_lang = greek_or_hebrew_re.match(line)
        if m_lang:
            if current is None:
                if unparsed_out is not None:
                    _append_unparsed(
                        unparsed_out,
                        file_line=file_line,
                        text=line,
                        current=None,
                        reason=_unparsed_reason(
                            line, current=None, lang_before_concept=True
                        ),
                    )
                continue
            current["greek_terms"].extend(_split_lang_terms(m_lang.group(1)))
            continue

        sc = _parse_scripture_line(line)
        if sc is not None and current is not None:
            sid, txt = sc
            current["scriptures"].append({"id": sid, "text": txt})
            continue

        if unparsed_out is not None:
            _append_unparsed(
                unparsed_out,
                file_line=file_line,
                text=line,
                current=current,
                reason=_unparsed_reason(
                    line, current=current, lang_before_concept=False
                ),
            )

    return results


_SELF_TEST_TEXT = """1概念全角顿号序号
希腊文：zoē、bios
约一4　全角空格经文A

2概念英文逗号不切分
希腊文：zoē, bios
约一4 半角空格经文B

3概念带编号英文逗号不切分
希腊文：zoē (G2222), bios (G979)
约一4：冒号分隔经文C

4概念外层中文括号整段英文逗号不切分
希腊文：（zoē, bios）
约一4　外层括号拆两项

5概念外层英文括号整段英文逗号不切分
希腊文:(zoē, bios)
约一5　英文括号整段

6概念每项带括号
希腊文：（zoē）、（bios）
约一6　每项括号

16、背十字架顿号
希伯来文：tsaba
约二1　经文D

16.背十字架句点
希腊文：stauros
约二2　经文E

16 背十字架空格
希腊文：xylon
约二3　经文F

（16）背十字架全角括号
希腊文：airó
约二4　经文G

(16)背十字架半角括号
希腊文：stauros2
约二5　经文H

9概念混合冒号与空白
希腊文：alpha, beta
约三1 经文里：可含冒号
约三2：仅冒号分隔

10概念ho逗号词内字符
希腊文：euaggelion (G2098) ho, (G3588) charis (G5485)
约四1　经文I
"""


def _run_self_test() -> None:
    unparsed: list[dict] = []
    rows = parse_txt(_SELF_TEST_TEXT, unparsed_out=unparsed)
    if unparsed:
        raise SystemExit(f"自检失败：存在未解析行: {unparsed!r}")

    by = {r["concept"]: r for r in rows}

    assert by["概念全角顿号序号"]["greek_terms"] == ["zoē", "bios"]
    assert by["概念全角顿号序号"]["scriptures"][0] == {
        "id": "约一4",
        "text": "全角空格经文A",
    }

    assert by["概念英文逗号不切分"]["greek_terms"] == ["zoē, bios"]
    assert by["概念英文逗号不切分"]["scriptures"][0]["text"] == "半角空格经文B"

    assert by["概念带编号英文逗号不切分"]["greek_terms"] == [
        "zoē (G2222), bios (G979)",
    ]
    assert by["概念带编号英文逗号不切分"]["scriptures"][0] == {
        "id": "约一4",
        "text": "冒号分隔经文C",
    }

    assert by["概念外层中文括号整段英文逗号不切分"]["greek_terms"] == ["zoē, bios"]

    assert by["概念外层英文括号整段英文逗号不切分"]["greek_terms"] == ["zoē, bios"]

    assert by["概念每项带括号"]["greek_terms"] == ["zoē", "bios"]

    assert by["背十字架顿号"]["greek_terms"] == ["tsaba"]
    assert by["背十字架句点"]["greek_terms"] == ["stauros"]
    assert by["背十字架空格"]["greek_terms"] == ["xylon"]
    assert by["背十字架全角括号"]["greek_terms"] == ["airó"]
    assert by["背十字架半角括号"]["greek_terms"] == ["stauros2"]

    assert by["概念混合冒号与空白"]["greek_terms"] == ["alpha, beta"]
    assert len(by["概念混合冒号与空白"]["scriptures"]) == 2
    assert by["概念混合冒号与空白"]["scriptures"][0] == {
        "id": "约三1",
        "text": "经文里：可含冒号",
    }
    assert by["概念混合冒号与空白"]["scriptures"][1] == {
        "id": "约三2",
        "text": "仅冒号分隔",
    }

    assert by["概念ho逗号词内字符"]["greek_terms"] == [
        "euaggelion (G2098) ho, (G3588) charis (G5485)"
    ]

    print("parse_scripture_input 自检通过。", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="解析经文 TXT → seed_scriptures.json")
    parser.add_argument("--input", type=str, default="", help="输入 TXT 文件路径")
    parser.add_argument("--output", type=str, default="seed_scriptures.json", help="输出 JSON 路径")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="运行内置格式变体自检（可不提供 --input）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="未解析行较多时，在 stderr 末尾打印按原因汇总的条数",
    )
    args = parser.parse_args()

    if args.self_test:
        _run_self_test()
        return

    if not args.input:
        parser.error("请提供 --input，或使用 --self-test")

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在: {input_path}")

    text = input_path.read_text(encoding="utf-8")
    unparsed: list[dict] = []
    results = parse_txt(text, unparsed_out=unparsed)

    if unparsed:
        for rec in unparsed:
            block = (
                rec["concept"]
                if rec["concept"] is not None
                else "（尚未进入任一概念块）"
            )
            print(
                f"警告：未解析行（已跳过） 源文件第 {rec['file_line']} 行  "
                f"当前概念块={block!r}\n"
                f"       原因: {rec['reason']}\n"
                f"       原文: {rec['text']!r}",
                file=sys.stderr,
            )
        if args.debug:
            by_reason = Counter(r["reason"] for r in unparsed)
            print(
                f"[DEBUG] 未解析共 {len(unparsed)} 条，按原因统计:\n"
                + "\n".join(f"  {n}× {reason}" for reason, n in by_reason.most_common()),
                file=sys.stderr,
            )

    if not results:
        print("警告：未解析到任何概念条目")

    output_path = Path(args.output)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n已输出 {len(results)} 个概念到 {output_path}\n")
    for item in results:
        print(
            f"  {item['concept']}  "
            f"greek_terms={len(item['greek_terms'])}  "
            f"scriptures={len(item['scriptures'])}"
        )
    print()


if __name__ == "__main__":
    main()
