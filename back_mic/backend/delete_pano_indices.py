"""
删除 ES 中所有 pano 相关索引。
用法：在 back_mic/backend 目录下执行  python delete_pano_indices.py
"""
from es_config import es

PANO_INDICES = [
    "pano",
    "pano_booknames",
    "pano_headings",
    "pano_msg",
    "pano_ot1",
    "pano_outlines",
    "pano_titles",
    "map_pano_bookname",
    "map_pano_title",
]

if __name__ == "__main__":
    print("正在删除 pano 相关索引...")
    for name in PANO_INDICES:
        try:
            if es.indices.exists(index=name):
                es.indices.delete(index=name)
                print(f"  已删除: {name}")
            else:
                print(f"  不存在，跳过: {name}")
        except Exception as e:
            print(f"  失败 {name}: {e}")
    print("完成。")
