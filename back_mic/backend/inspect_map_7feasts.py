"""查看 map_7feasts 索引内容构成"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from es_config import es

INDEX = "map_7feasts"

count = es.count(index=INDEX)["count"]
print(f"\nmap_7feasts 总文档数: {count:,}")

# 抽样：取 500 条，统计 id 前缀模式
sample = es.search(
    index=INDEX,
    body={
        "size": 500,
        "_source": ["id", "source", "sn"],
        "query": {"match_all": {}},
    }
)
ids = []
for hit in sample["hits"]["hits"]:
    s = hit.get("_source") or {}
    tid = s.get("id") or s.get("refid") or hit["_id"]
    ids.append(tid)

# 提取 id 前缀（如 map_7feasts_1997、map_7feasts_xxx 等）
prefixes = []
for i in ids:
    parts = str(i).split("_")
    if len(parts) >= 3:
        prefixes.append("_".join(parts[:3]))  # map_7feasts_1997
    else:
        prefixes.append(str(i)[:30])
cnt = Counter(prefixes)

print("\nid 前缀分布（抽样 500 条）:")
for pref, n in cnt.most_common(20):
    print(f"  {pref}: {n}")

print("\n样本文档（前 15 条）:")
for hit in sample["hits"]["hits"][:15]:
    s = hit.get("_source") or {}
    tid = s.get("id") or hit["_id"]
    src = (s.get("source") or "-")[:60]
    print(f"  id={tid[:70]}")
    print(f"    source={src}")
