"""列出本地 ES 所有索引"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_config import es

indices = es.cat.indices(format="json")
print("\n本地 ES 索引列表:\n")
print(f"{'索引名':<40} {'文档数':>12} {'大小':>12}")
print("-" * 66)
for idx in sorted(indices, key=lambda x: x.get("index", "")):
    name = idx.get("index", "")
    if not name.startswith("."):
        docs = idx.get("docs.count", "0")
        store = idx.get("store.size", "0b")
        print(f"{name:<40} {docs:>12} {store:>12}")
print("-" * 66)
print(f"共 {len([i for i in indices if not i.get('index','').startswith('.')])} 个用户索引\n")
