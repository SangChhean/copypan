# -*- coding: utf-8 -*-
"""解析经文 TXT 文件，输出 seed_scriptures.json。

行格式：
  - 序号+概念名（如 1变化、2神的经纶）
  - 希腊文：xxx，xxx（顿号或逗号分割）
  - 书卷章节　经文内容（全角空格分隔）
  - 空行忽略
"""
import argparse
import json
import re
from pathlib import Path


def parse_txt(text: str) -> list[dict]:
    lines = text.splitlines()
    results: list[dict] = []
    current: dict | None = None

    concept_re = re.compile(r"^(\d+)\s*(.+)$")
    greek_re = re.compile(r"^希腊文[：:](.+)$")
    # 书卷章节：中文 + 可选罗马/阿拉伯数字 + 全角空格 + 经文
    scripture_re = re.compile(r"^(.+?)\u3000(.+)$")

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        m_concept = concept_re.match(line)
        if m_concept:
            current = {
                "concept": m_concept.group(2).strip(),
                "greek_terms": [],
                "scriptures": [],
            }
            results.append(current)
            continue

        m_greek = greek_re.match(line)
        if m_greek:
            if current is None:
                continue
            raw_terms = re.split(r"[、,，]", m_greek.group(1))
            current["greek_terms"] = [t.strip() for t in raw_terms if t.strip()]
            continue

        m_scripture = scripture_re.match(line)
        if m_scripture and current is not None:
            current["scriptures"].append({
                "id": m_scripture.group(1).strip(),
                "text": m_scripture.group(2).strip(),
            })
            continue

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="解析经文 TXT → seed_scriptures.json")
    parser.add_argument("--input", type=str, required=True, help="输入 TXT 文件路径")
    parser.add_argument("--output", type=str, default="seed_scriptures.json", help="输出 JSON 路径")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在: {input_path}")

    text = input_path.read_text(encoding="utf-8")
    results = parse_txt(text)

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
