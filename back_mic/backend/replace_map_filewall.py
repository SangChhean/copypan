"""
替换 filewall 索引：删除现有 filewall，从指定 JSON 文件导入新数据

用法：
  cd back_mic/backend
  python replace_map_filewall.py

数据源：见 SOURCE_FILE 变量
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from es_config import es

SOURCE_FILE = os.path.join(os.path.dirname(__file__), "filewall.json")
INDEX_NAME = "filewall"

FILEWALL_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "text": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "msg": {
                "type": "nested",
                "properties": {
                    "text": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart",
                    }
                },
            },
            "sn": {"type": "keyword"},
            "source": {"type": "keyword"},
        }
    }
}


def main():
    print("=" * 60)
    print("  替换 filewall 索引")
    print("=" * 60)

    source = Path(SOURCE_FILE)
    if not source.exists():
        print(f"❌ 文件不存在: {SOURCE_FILE}")
        return

    print("\n[1/3] 删除现有 filewall 索引...")
    if es.indices.exists(index=INDEX_NAME):
        es.indices.delete(index=INDEX_NAME)
        print("  ✓ 已删除")
    else:
        print("  (索引不存在，跳过)")

    print("\n[2/3] 创建新 filewall 索引...")
    es.indices.create(index=INDEX_NAME, body=FILEWALL_MAPPING)
    print("  ✓ 已创建")

    print("\n[3/3] 导入数据...")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return

    if not isinstance(data, list):
        data = [data]

    total = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        idx = item.get("id") or item.get("refid")
        if not idx:
            continue
        body = {k: v for k, v in item.items() if k != "index"}
        try:
            es.index(index=INDEX_NAME, id=idx, body=body)
            total += 1
        except Exception as e:
            print(f"  ⚠ 写入失败 {idx}: {e}")

    print(f"\n  ✓ 共导入 {total} 条文档")
    print("\n" + "=" * 60)
    print("  替换完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
