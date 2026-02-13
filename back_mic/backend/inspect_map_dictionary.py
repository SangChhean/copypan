"""查看 map_dictionary 文档结构"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_config import es

res = es.search(
    index="map_dictionary",
    body={"size": 3, "query": {"match_all": {}}}
)

print("\nmap_dictionary 样本文档字段:\n")
for i, hit in enumerate(res["hits"]["hits"]):
    src = hit.get("_source") or {}
    print(f"--- 文档 {i+1} ---")
    for k, v in src.items():
        if k == "msg" and isinstance(v, list):
            print(f"  {k}: [list, len={len(v)}] 首项keys={list(v[0].keys()) if v else 'empty'}")
        else:
            val = str(v)[:80] + "..." if len(str(v)) > 80 else v
            print(f"  {k}: {val}")
    print()
