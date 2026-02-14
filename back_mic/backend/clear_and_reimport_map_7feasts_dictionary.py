"""
清空 map_7feasts、map_dictionary 的文档内容（保留索引和 mapping），然后重新导入。

用法：
  cd back_mic/backend
  python clear_and_reimport_map_7feasts_dictionary.py

注意：不删除索引定义，不修改 ai_service.py 中的搜索配置。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_config import es

SOURCE_DIRS = [
    (r"C:\Users\Administrator\Desktop\note、7feasts、dictionary、pano\map_7feasts", "map_7feasts"),
    (r"C:\Users\Administrator\Desktop\note、7feasts、dictionary、pano\map_dictionary", "map_dictionary"),
]


def clear_index(index_name: str) -> int:
    """清空索引内所有文档，保留索引和 mapping，返回删除的文档数"""
    if not es.indices.exists(index=index_name):
        print(f"  索引不存在，跳过清空: {index_name}")
        return 0
    res = es.delete_by_query(index=index_name, body={"query": {"match_all": {}}})
    deleted = res.get("deleted", 0)
    print(f"  已清空 {index_name}，删除 {deleted} 条文档")
    return deleted


def import_json_dir(dir_path: str, index_name: str) -> int:
    """导入目录下所有 JSON 到指定索引"""
    root = Path(dir_path)
    if not root.exists():
        print(f"  ⚠ 目录不存在: {dir_path}")
        return 0
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
                es.index(index=index_name, id=idx, body=body)
                total += 1
            except Exception as e:
                print(f"  ⚠ 写入失败 {idx}: {e}")
        print(f"    已处理: {jf.name}")
    return total


def main():
    print("=" * 60)
    print("  清空并重新导入 map_7feasts / map_dictionary")
    print("=" * 60)

    for dir_path, index_name in SOURCE_DIRS:
        print(f"\n[{index_name}]")
        print("  [1/2] 清空文档...")
        clear_index(index_name)
        print("  [2/2] 重新导入...")
        n = import_json_dir(dir_path, index_name)
        print(f"  ✓ 共导入 {n} 条文档")

    print("\n" + "=" * 60)
    print("  完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
