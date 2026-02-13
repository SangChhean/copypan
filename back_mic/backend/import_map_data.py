"""
将 map_pano 数据导入本地 ES（新增，不覆盖现有索引其他数据）

用法：
  cd back_mic/backend
  python import_map_data.py
"""
import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from es_config import es

# 数据源目录（按需修改）
SOURCE_DIRS = [
    (r"C:\Users\Administrator\Desktop\note、7feasts、dictionary、pano\map_pano", "map_pano"),
]

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


def ensure_index(index_name: str):
    """若索引不存在则创建（使用 map 类型 mapping）"""
    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name, body=MAP_MAPPING)
        print(f"  已创建索引: {index_name}")
    else:
        print(f"  索引已存在，将新增文档: {index_name}")


def import_json_dir(dir_path: str, index_name: str) -> int:
    """导入目录下所有 JSON 文件到指定索引，返回导入文档数"""
    root = Path(dir_path)
    if not root.exists():
        print(f"  ⚠ 目录不存在: {dir_path}")
        return 0

    total = 0
    json_files = sorted(root.glob("*.json"))

    for jf in json_files:
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
            # 移除 index 字段，避免写入 ES
            body = {k: v for k, v in item.items() if k != "index"}
            try:
                es.index(index=index_name, id=idx, body=body)
                total += 1
            except Exception as e:
                print(f"  ⚠ 写入失败 {idx}: {e}")

        print(f"    已处理: {jf.name}")

    return total


def main():
    print("=" * 60)
    print("  map_pano 导入本地 ES")
    print("=" * 60)

    for dir_path, index_name in SOURCE_DIRS:
        print(f"\n[{index_name}]")
        ensure_index(index_name)
        n = import_json_dir(dir_path, index_name)
        print(f"  ✓ 共导入 {n} 条文档")

    print("\n" + "=" * 60)
    print("  导入完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
