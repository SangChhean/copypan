# -*- coding: utf-8 -*-
import json, statistics

data = json.load(open(r"E:\12490_with_bib\kg-rag_life_chunks.json", encoding="utf-8"))
print("chunk总数:", len(data))
print("字段数:", len(data[0]))
print("有book_title的比例:", f"{sum(1 for d in data if d['book_title']) / len(data):.4f}")
print("section_title非空数:", sum(1 for d in data if d["section_title"]))

tokens = [d["tokens"] for d in data]
print(f"token分布: min={min(tokens)}, max={max(tokens)}, avg={sum(tokens)/len(tokens):.1f}, median={statistics.median(tokens):.1f}")

print("original_ids样本:", data[0]["original_ids"])

# 检查有无超过800的token
over800 = [d for d in data if d["tokens"] > 800]
print(f"tokens>800的chunk数: {len(over800)}")

# 检查_p后缀chunk
split_chunks = [d for d in data if "_p" in d["chunk_id"]]
print(f"拆分chunk数: {len(split_chunks)}")
if split_chunks:
    print("拆分样本:", split_chunks[0]["chunk_id"], "tokens:", split_chunks[0]["tokens"])

# scripture_refs 非空
with_refs = sum(1 for d in data if d["scripture_refs"])
print(f"有scripture_refs的chunk数: {with_refs}")

# en字段非空比例
with_en = sum(1 for d in data if d["en"])
print(f"有en字段的chunk数: {with_en} ({with_en/len(data):.2%})")

print("\n--- 样本 chunk [100] ---")
print(json.dumps(data[100], ensure_ascii=False, indent=2))
