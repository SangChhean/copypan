# -*- coding: utf-8 -*-
"""临时脚本：用写死的路径运行 life_gen chunking，避免 shell 编码问题。"""
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from kg_rag.scripts.chunking import chunk_document

def main():
    path = Path(r"e:\PanAI用\【PanAI3.0】KG-RAG升级\life_gen.json")
    if not path.exists():
        print(f"文件不存在: {path}")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    chunks, stats = chunk_document(data)
    out = _BACKEND_ROOT / "life_chunks_output.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print("统计信息：")
    print(f"  原始条目数: {stats['original_count']}")
    print(f"  type 分布: {stats['type_distribution']}")
    print(f"  生成 chunk 数: {stats['chunk_count']}")
    print(f"  短段落合并次数: {stats['merge_count']}")
    print(f"  长段落拆分次数: {stats['split_count']}")
    print(f"  chunk token 范围: min={stats['chunk_tokens_min']} max={stats['chunk_tokens_max']} avg={stats['chunk_tokens_avg']} median={stats['chunk_tokens_median']}")
    print(f"  每篇 chunk 数范围: min={stats['per_message_chunks_min']} max={stats['per_message_chunks_max']} avg={stats['per_message_chunks_avg']}")

if __name__ == "__main__":
    main()
