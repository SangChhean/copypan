# -*- coding: utf-8 -*-
"""life_gen 结构解析与 Chunking：id 解析、段落合并、metadata 构建。"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

BOOK_TITLE = "创世记生命读经"
AUTHOR = "李常受"
YEAR = 1974
SHORT_THRESHOLD = 150
LONG_THRESHOLD = 800
TARGET_MIN, TARGET_MAX = 400, 800
OVERLAP_CHARS = 180
SENTENCE_SPLIT_RE = re.compile(r"[。；？！]")


def parse_life_id(id_str: str) -> dict[str, Any]:
    """从 life_1-{篇}-{段} 解析 book / message_number / sequence。"""
    parts = id_str.strip().split("-")
    if len(parts) != 3:
        return {"book": BOOK_TITLE, "message_number": 0, "sequence": 0}
    try:
        return {
            "book": BOOK_TITLE,
            "message_number": int(parts[1]),
            "sequence": int(parts[2]),
        }
    except ValueError:
        return {"book": BOOK_TITLE, "message_number": 0, "sequence": 0}


def extract_message_title(title_text: str) -> str:
    """从 title 的 text 中去掉「第X篇　」前缀，提取实际标题。匹配不到则原样返回。"""
    if not title_text or not title_text.strip():
        return title_text or ""
    m = re.match(r"^第.+?篇\s*", title_text.strip())
    if m:
        return title_text.strip()[m.end() :].strip()
    return title_text.strip()


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：按字符数 / 1.5，至少 1。"""
    if not text or not text.strip():
        return 0
    return max(1, int(len(text) / 1.5))


def _split_long_text(text: str, first_id: str) -> list[dict[str, Any]]:
    """单段 tokens > 800 时按句号等断句，贪心合并到 400-800，overlap 上一块最后 180 字。"""
    parts = SENTENCE_SPLIT_RE.split(text)
    sentences = []
    for i, s in enumerate(parts):
        s = s.strip()
        if not s:
            continue
        sep = "。" if i < len(parts) - 1 else ""
        sentences.append(s + sep)
    if not sentences:
        return [{"text": text, "chunk_id": first_id, "tokens": estimate_tokens(text)}]

    chunk_texts = []
    current = []
    current_tokens = 0
    overlap_buf = ""

    for sent in sentences:
        st = estimate_tokens(sent)
        if current_tokens + st <= TARGET_MAX and not overlap_buf:
            current.append(sent)
            current_tokens += st
        elif current_tokens + st <= TARGET_MAX and overlap_buf:
            current.append(overlap_buf + sent)
            current_tokens = estimate_tokens(current[-1])
            overlap_buf = ""
        else:
            if current:
                block_text = "".join(current)
                chunk_texts.append(block_text)
                overlap_buf = block_text[-OVERLAP_CHARS:] if len(block_text) >= OVERLAP_CHARS else block_text
            current = [sent]
            current_tokens = st
    if current:
        chunk_texts.append("".join(current))

    out = []
    for i, block in enumerate(chunk_texts):
        tid = f"{first_id}_part{i + 1}" if len(chunk_texts) > 1 else first_id
        out.append({"text": block, "chunk_id": tid, "tokens": estimate_tokens(block)})
    return out


def _chunk_paragraphs(
    paras: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """
    对一篇内的 text 段落列表做合并与拆分。
    返回 (chunk 列表, 短段落合并次数, 长段落拆分次数)。
    """
    if not paras:
        return [], 0, 0
    merge_count = 0
    split_count = 0

    # 1) 合并连续短段落（同 section_title，不跨 heading）
    segments = []
    i = 0
    while i < len(paras):
        p = paras[i]
        text = (p.get("text") or "").strip()
        if not text:
            i += 1
            continue
        t = estimate_tokens(text)
        first_id = p["id"]
        meta = {
            "message_number": p["message_number"],
            "message_title": p["message_title"],
            "section_title": p.get("section_title") or "",
        }
        if t >= SHORT_THRESHOLD:
            segments.append({"chunk_id": first_id, "text": text, "tokens": t, **meta})
            i += 1
            continue
        merged_text = text
        merged_tokens = t
        j = i + 1
        while j < len(paras):
            q = paras[j]
            qtext = (q.get("text") or "").strip()
            if not qtext:
                j += 1
                continue
            qt = estimate_tokens(qtext)
            if q.get("section_title") != meta["section_title"]:
                break
            if merged_tokens + qt > LONG_THRESHOLD:
                break
            merged_text += "\n\n" + qtext
            merged_tokens += qt
            j += 1
            if qt >= SHORT_THRESHOLD:
                break
        if j > i + 1:
            merge_count += 1
        segments.append({"chunk_id": first_id, "text": merged_text, "tokens": merged_tokens, **meta})
        i = j

    # 2) 长段拆分 + 输出格式
    result = []
    for seg in segments:
        if seg["tokens"] > LONG_THRESHOLD:
            sub = _split_long_text(seg["text"], seg["chunk_id"])
            if len(sub) > 1:
                split_count += 1
            for s in sub:
                result.append({
                    "chunk_id": s["chunk_id"],
                    "text": s["text"],
                    "book_title": BOOK_TITLE,
                    "author": AUTHOR,
                    "year": YEAR,
                    "message_number": seg["message_number"],
                    "message_title": seg["message_title"],
                    "section_title": seg["section_title"],
                    "paragraph_type": "text",
                    "tokens": s["tokens"],
                })
        else:
            result.append({
                "chunk_id": seg["chunk_id"],
                "text": seg["text"],
                "book_title": BOOK_TITLE,
                "author": AUTHOR,
                "year": YEAR,
                "message_number": seg["message_number"],
                "message_title": seg["message_title"],
                "section_title": seg["section_title"],
                "paragraph_type": "text",
                "tokens": seg["tokens"],
            })
    return result, merge_count, split_count


def chunk_document(
    items: list[dict[str, Any]],
    target_tokens: tuple[int, int] = (400, 800),
    overlap_tokens: int = 120,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    将 life_gen 条目（含 id/text/type）切分为 chunk，携带 chunk_id 与 metadata。
    返回 (chunks 列表, 统计信息)。
    """
    type_counts = {"title": 0, "heading": 0, "text": 0}
    # 按 message_number、sequence 排序，保证每篇内顺序正确
    def sort_key(raw: dict) -> tuple[int, int]:
        p = parse_life_id((raw.get("id") or "").strip())
        return (p["message_number"], p["sequence"])

    sorted_items = sorted([r for r in items if (r.get("type") or "").strip() in type_counts], key=sort_key)
    by_message: dict[int, list[dict[str, Any]]] = {}

    current_message_title = ""
    current_section_title = ""

    for raw in sorted_items:
        typ = (raw.get("type") or "").strip()
        if typ not in type_counts:
            continue
        type_counts[typ] += 1
        id_str = (raw.get("id") or "").strip()
        text = (raw.get("text") or "").strip()
        parsed = parse_life_id(id_str)
        msg_num = parsed["message_number"]

        if typ == "title":
            current_message_title = extract_message_title(text)
            current_section_title = ""
            continue
        if typ == "heading":
            current_section_title = text
            continue
        if typ == "text":
            if not text:
                continue
            if msg_num not in by_message:
                by_message[msg_num] = []
            by_message[msg_num].append({
                "id": id_str,
                "text": text,
                "message_number": msg_num,
                "message_title": current_message_title,
                "section_title": current_section_title,
            })

    all_chunks = []
    total_merge = 0
    total_split = 0
    chunks_per_message = []

    for msg_num in sorted(by_message.keys()):
        paras = by_message[msg_num]
        chunks, merge_n, split_n = _chunk_paragraphs(paras)
        all_chunks.extend(chunks)
        total_merge += merge_n
        total_split += split_n
        chunks_per_message.append(len(chunks))

    stats = {
        "original_count": len(items),
        "type_distribution": type_counts,
        "chunk_count": len(all_chunks),
        "merge_count": total_merge,
        "split_count": total_split,
    }
    if all_chunks:
        tokens_list = [c["tokens"] for c in all_chunks]
        stats["chunk_tokens_min"] = min(tokens_list)
        stats["chunk_tokens_max"] = max(tokens_list)
        stats["chunk_tokens_avg"] = round(statistics.mean(tokens_list), 1)
        stats["chunk_tokens_median"] = statistics.median(tokens_list)
    else:
        stats["chunk_tokens_min"] = stats["chunk_tokens_max"] = 0
        stats["chunk_tokens_avg"] = stats["chunk_tokens_median"] = 0
    if chunks_per_message:
        stats["per_message_chunks_min"] = min(chunks_per_message)
        stats["per_message_chunks_max"] = max(chunks_per_message)
        stats["per_message_chunks_avg"] = round(statistics.mean(chunks_per_message), 1)
    else:
        stats["per_message_chunks_min"] = stats["per_message_chunks_max"] = 0
        stats["per_message_chunks_avg"] = 0

    return all_chunks, stats


def main() -> None:
    """入口：读取 JSON、解析、chunk、写输出并打印统计。"""
    if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding and "utf-8" not in (sys.stdout.encoding or "").lower():
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="life_gen chunking")
    parser.add_argument("--input", type=str, required=True, help="输入 life_gen.json 路径")
    parser.add_argument("--output", type=str, default="chunks_output.json", help="输出 chunk JSON 路径")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit("输入 JSON 应为数组")

    chunks, stats = chunk_document(data)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
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
