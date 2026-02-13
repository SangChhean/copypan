"""
替换 map_note 索引：删除现有 map_note，从指定目录导入新数据

用法：
  cd back_mic/backend
  python replace_map_note.py

数据源：见 SOURCE_DIR 变量
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from es_config import es

SOURCE_DIR = r"C:\Users\Administrator\Desktop\note、7feasts、dictionary、pano\map_note"
INDEX_NAME = "map_note"

MAP_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "text": {"type": "text"},
            "msg": {"type": "nested"},
            "sn": {"type": "keyword"},
            "source": {"type": "keyword"},
        }
    }
}


def main():
    print("=" * 60)
    print("  替换 map_note 索引")
    print("=" * 60)

    root = Path(SOURCE_DIR)
    if not root.exists():
        print(f"❌ 目录不存在: {SOURCE_DIR}")
        return

    # 1. 删除现有 map_note
    print("\n[1/3] 删除现有 map_note 索引...")
    if es.indices.exists(index=INDEX_NAME):
        es.indices.delete(index=INDEX_NAME)
        print("  ✓ 已删除")
    else:
        print("  (索引不存在，跳过)")

    # 2. 创建新索引
    print("\n[2/3] 创建新 map_note 索引...")
    es.indices.create(index=INDEX_NAME, body=MAP_MAPPING)
    print("  ✓ 已创建")

    # 3. 导入所有 JSON
    print("\n[3/3] 导入数据...")
    total = 0
    for jf in sorted(root.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠ 读取失败 {jf.name}: {e}")
            continue

        if not isinstance(data, list):
            data = [data]

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

        print(f"    已处理: {jf.name}")

    print(f"\n  ✓ 共导入 {total} 条文档")
    print("\n" + "=" * 60)
    print("  替换完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
