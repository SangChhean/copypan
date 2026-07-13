#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性迁移：把 back_anshifenliang/data/hymns.js 转为 back_cn/data/hymns.json。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = REPO_ROOT / "back_anshifenliang" / "data" / "hymns.js"
OUTPUT_PATH = REPO_ROOT / "back_cn" / "data" / "hymns.json"

# 大本 / 补充本 / 儿童 / 附
KEY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^诗歌第(\d+)首[　\s]*(.*)$"), "大本"),
    (re.compile(r"^补充本诗歌第(\d+)首[　\s]*(.*)$"), "补充"),
    (re.compile(r"^儿童诗歌第(\d+)首[　\s]*(.*)$"), "儿童"),
    (re.compile(r"^诗歌附(\d+)[　\s]*(.*)$"), "附"),
]

SKIP_KEYS = {"诗歌目录", "补充本诗歌目录", "儿童诗歌目录"}


def load_hymns_js(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").strip()
    m = re.match(r"^window\.hymns\s*=\s*", text)
    if not m:
        raise ValueError("文件开头不是 window.hymns = ...")
    body = text[m.end() :].rstrip()
    if body.endswith(";"):
        body = body[:-1]
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        print("JSON 解析失败:", e, file=sys.stderr)
        print("文件开头:", text[:500], file=sys.stderr)
        raise
    if not isinstance(data, dict):
        raise ValueError(f"解析结果不是对象: {type(data)}")
    return data


def split_title_note(rest: str) -> tuple[str, str]:
    """从 key 剩余部分拆出曲名与 note（英/西对照）。"""
    title = rest.split("<", 1)[0].strip()
    note = ""
    nm = re.search(r"（([^）]*)）", rest)
    if nm:
        note = nm.group(1).strip()
    return title, note


def parse_entry(key: str, content: str) -> dict | None:
    """成功返回 hymn dict；无法识别格式返回 None（由调用方记失败）。"""
    if key in SKIP_KEYS:
        return None

    for pat, source in KEY_PATTERNS:
        m = pat.match(key)
        if not m:
            continue
        no = int(m.group(1))
        rest = m.group(2) or ""
        title, note = split_title_note(rest)
        if not title:
            raise ValueError(f"曲名为空: {key!r}")
        if "<" in title or ">" in title:
            raise ValueError(f"曲名仍含 HTML: {title!r}")
        text = (content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            raise ValueError(f"歌词内容为空: {key!r}")
        return {
            "no": no,
            "source": source,
            "title": title,
            "note": note,
            "content": text,
        }
    return None


def main() -> int:
    if not SOURCE_PATH.is_file():
        print(f"ERROR: 找不到源文件 {SOURCE_PATH}", file=sys.stderr)
        return 1

    raw = load_hymns_js(SOURCE_PATH)
    hymns: list[dict] = []
    failures: list[str] = []
    skipped_dirs: list[str] = []

    for key, content in raw.items():
        if key in SKIP_KEYS:
            skipped_dirs.append(key)
            continue
        try:
            item = parse_entry(key, content if isinstance(content, str) else str(content))
        except Exception as e:
            failures.append(f"{key!r}: {e}")
            continue
        if item is None:
            failures.append(f"{key!r}: 键名格式不符合诗歌第N首/补充本/儿童/附 预期")
            continue
        hymns.append(item)

    # 稳定排序：按 source 再按 no
    source_order = {"大本": 0, "补充": 1, "儿童": 2, "附": 3}
    hymns.sort(key=lambda h: (source_order.get(h["source"], 9), h["no"]))

    # 检查同 source 内编号重复
    seen: dict[tuple[str, int], int] = {}
    for h in hymns:
        k = (h["source"], h["no"])
        seen[k] = seen.get(k, 0) + 1
    for k, n in sorted(seen.items()):
        if n > 1:
            failures.append(f"重复条目: source={k[0]} no={k[1]} 出现 {n} 次")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps({"hymns": hymns}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    by_source: dict[str, int] = {}
    for h in hymns:
        by_source[h["source"]] = by_source.get(h["source"], 0) + 1

    print("=== 诗歌迁移汇总 ===")
    print(f"源文件: {SOURCE_PATH}")
    print(f"输出: {OUTPUT_PATH}")
    print(f"源对象键数: {len(raw)}")
    print(f"成功转换: {len(hymns)}")
    print(f"按来源: {by_source}")
    print(f"跳过目录键: {skipped_dirs}")
    print(f"失败/异常: {len(failures)}")
    if failures:
        print("--- 失败明细 ---")
        for line in failures:
            print(line)
    else:
        print("失败明细: （无）")

    # 编号重叠提示（大本 vs 补充）
    main_nos = {h["no"] for h in hymns if h["source"] == "大本"}
    supp_nos = {h["no"] for h in hymns if h["source"] == "补充"}
    overlap = sorted(main_nos & supp_nos)
    print(
        f"编号体系: 大本与补充本为两套独立编号；"
        f"编号重叠 {len(overlap)} 个（例: {overlap[:10]}）"
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
