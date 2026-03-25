# -*- coding: utf-8 -*-
"""检查同一 group 的 text/heading/title 文档是否连续出现"""
import ijson

# 收集每个 doc 的 (index, type, group_key)
entries = []
with open(r"E:\12490_with_bib\life.json", "rb") as fp:
    for i, doc in enumerate(ijson.items(fp, "item")):
        doc_id = doc.get("id", "")
        if not doc_id.startswith("life_"):
            continue
        rest = doc_id[5:]
        parts = rest.split("-")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            continue
        while len(nums) < 3:
            nums.append(0)
        group_key = f"life_{nums[0]}-{nums[1]}"
        entries.append((i, doc.get("type","").strip(), group_key, tuple(nums)))

# 找第一个出现 heading/title 文档的索引
heading_positions = [(i, t, g) for (i, t, g, _) in entries if t != "text"]
print(f"非 text 文档共 {len(heading_positions)} 条")
print(f"前10条非text文档的文件位置：")
for i, t, g in heading_positions[:10]:
    print(f"  file_index={i}, type={t!r}, group={g}")

# 检查 life_60-12 组的所有文档的文件位置和类型
group_60_12 = [(i, t, s) for (i, t, g, s) in entries if g == "life_60-12"]
print(f"\nlife_60-12 组的所有文档（共{len(group_60_12)}条）：")
for i, t, s in group_60_12[:20]:
    print(f"  file_index={i}, type={t!r}, sort={s}")
