# -*- coding: utf-8 -*-
"""检查 life.json 前 300 条的 type 分布和 id 格式"""
import ijson, collections

types = collections.Counter()
sample_by_type = {}
with open(r"E:\12490_with_bib\life.json", "rb") as fp:
    for i, doc in enumerate(ijson.items(fp, "item")):
        if i >= 300:
            break
        t = doc.get("type", "NO_TYPE").strip()
        types[t] += 1
        if t not in sample_by_type:
            sample_by_type[t] = doc

print("=== type 分布（前300条）===")
for t, c in types.most_common():
    print(f"  {t!r}: {c}")

print("\n=== 各 type 样本 ===")
for t, doc in sample_by_type.items():
    print(f"\n[{t}]")
    print(f"  id    : {doc.get('id')}")
    print(f"  title : {str(doc.get('title', ''))[:80]}")
    print(f"  text  : {str(doc.get('text', ''))[:60]}")
    print(f"  source: {doc.get('source', [])[:1]}")
