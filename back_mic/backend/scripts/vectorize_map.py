# -*- coding: utf-8 -*-
"""
纲目型向量化：map_7feasts, map_note, map_pano, map_dictionary。
按 msg 中 ot1 切 chunk；每个 chunk 写入 {index}_chunks 索引为独立文档（chunk_id 为 _id）。
断点续传：先 scroll *_chunks 收集已处理过的 parent_id，scroll 父文档时若 parent 在集合内则跳过该父文档，否则处理其全部 chunk。
TEST_MODE=False 时用 scroll 遍历全量父文档，边 scroll 边处理边写入。
使用方式：在 back_mic/backend 下执行  python scripts/vectorize_map.py
"""
import sys
import os
import re

_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_script_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(_backend_dir, ".env"))

BATCH_SIZE = 100
MAX_CHARS = 2000  # 单条 chunk 截断长度，约 1000 汉字，远低于 8192 token
MAX_BATCH_CHARS = 200000  # 每批总字符数上限，避免 300000 tokens/request
TEST_MODE = False
SCROLL_SIZE = 1000
SCROLL_TTL = "5m"

INDICES = ["map_7feasts", "map_note", "map_pano", "map_dictionary", "filewall"]
SKIP_TYPES = {"bookname", "title", "b_read"}
OT1_TYPE = "ot1"
SUB_OT_PATTERN = re.compile(r"^ot[2-6n]$")
LIMIT_PER_INDEX = 100 if TEST_MODE else None

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 512


def build_chunks(doc):
    """
    从 doc["msg"] 按 ot1 切 chunk。
    返回 [(chunk_id, text), ...]，chunk_id = {doc_id}_chunk{序号}。
    """
    msg = doc.get("msg") or []
    doc_id = doc.get("id", "")
    chunks_out = []
    current_parts = []
    pending_ot1_text = []
    chunk_seq = 0

    def flush_chunk():
        nonlocal chunk_seq
        if not current_parts:
            return
        text = "".join(current_parts).strip()
        if len(text) >= 20:
            chunk_seq += 1
            cid = "{}_chunk{}".format(doc_id, chunk_seq)
            chunks_out.append((cid, text))
        current_parts.clear()

    for item in msg:
        if not isinstance(item, dict):
            continue
        t = (item.get("type") or "").strip()
        raw = (item.get("text") or "").strip()
        if not raw:
            continue
        if t in SKIP_TYPES:
            continue
        if t == OT1_TYPE:
            if current_parts:
                flush_chunk()
            if pending_ot1_text and not current_parts:
                pending_ot1_text.append(raw)
            else:
                pending_ot1_text = [raw]
            current_parts = []
            continue
        if SUB_OT_PATTERN.match(t):
            if pending_ot1_text:
                current_parts.extend(pending_ot1_text)
                pending_ot1_text = []
            current_parts.append(raw)
            continue
        current_parts.append(raw)

    if pending_ot1_text and current_parts:
        flush_chunk()
    elif pending_ot1_text and not current_parts:
        pass
    else:
        flush_chunk()

    return chunks_out


def collect_existing_parent_ids(es, chunks_index):
    """Scroll *_chunks 索引，返回已处理过的 parent_id 集合。"""
    existing = set()
    try:
        resp = es.search(
            index=chunks_index,
            body={"_source": ["parent_id"], "size": SCROLL_SIZE},
            scroll=SCROLL_TTL,
        )
        scroll_id = resp.get("_scroll_id")
        batch = resp["hits"]["hits"]
        while batch:
            for h in batch:
                existing.add(h["_source"]["parent_id"])
            if not scroll_id:
                break
            resp = es.scroll(scroll_id=scroll_id, scroll=SCROLL_TTL)
            scroll_id = resp.get("_scroll_id")
            batch = resp["hits"]["hits"]
        if scroll_id:
            try:
                es.clear_scroll(scroll_id=scroll_id)
            except Exception:
                pass
    except Exception:
        pass
    return existing


def get_embeddings(client, texts):
    if not texts:
        return []
    r = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=EMBEDDING_DIMS,
    )
    return [d.embedding for d in r.data]


def drain_pending(es, client, index_name, chunks_index, pending, total_ok, total_fail):
    """从 pending 中取一批（最多 BATCH_SIZE 条且总字符数不超过 MAX_BATCH_CHARS），embedding 后写入；返回 (new_total_ok, new_total_fail, num_drained)。"""
    drained = 0
    while pending and (
        len(pending) >= BATCH_SIZE or sum(len(x[4]) for x in pending) > MAX_BATCH_CHARS
    ):
        batch = []
        batch_chars = 0
        while pending and len(batch) < BATCH_SIZE:
            if batch_chars + len(pending[0][4]) > MAX_BATCH_CHARS and len(batch) > 0:
                break
            item = pending.pop(0)
            batch.append(item)
            batch_chars += len(item[4])
        if not batch:
            break
        drained += len(batch)
        texts = [x[4] for x in batch]
        try:
            vectors = get_embeddings(client, texts)
        except Exception as e:
            print("[{}] Embedding 批量失败: {}".format(index_name, e))
            total_fail += len(batch)
            continue
        for i, (idx, parent_es_id, _doc_id, cid, text) in enumerate(batch):
            if i >= len(vectors):
                total_fail += 1
                continue
            try:
                es.index(
                    index=chunks_index,
                    id=cid,
                    body={
                        "chunk_id": cid,
                        "parent_id": parent_es_id,
                        "text": text,
                        "embedding": vectors[i],
                    },
                    refresh=False,
                )
                total_ok += 1
            except Exception as e:
                print("[{}] 写入失败 chunk_id={}: {}".format(chunks_index, cid, e))
                total_fail += 1
    return total_ok, total_fail, drained


def main():
    from es_config import es
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("错误：未设置 OPENAI_API_KEY（.env）")
        return
    client = OpenAI(api_key=api_key)

    total_ok = 0
    total_fail = 0
    chunks_index_base = "{}_chunks"

    for index_name in INDICES:
        chunks_index = chunks_index_base.format(index_name)
        pending = []
        existing_parent_ids = collect_existing_parent_ids(es, chunks_index)
        if existing_parent_ids:
            print("[{}] 已处理 {} 个父文档，将跳过".format(chunks_index, len(existing_parent_ids)))

        if TEST_MODE:
            r = es.search(index=index_name, size=LIMIT_PER_INDEX)
            hits = r["hits"]["hits"]
            for h in hits:
                if h["_id"] in existing_parent_ids:
                    continue
                doc = h["_source"]
                es_id = h["_id"]
                doc_id = doc.get("id", "")
                for cid, text in build_chunks(doc):
                    if len(text) > MAX_CHARS:
                        text = text[:MAX_CHARS]
                    pending.append((index_name, es_id, doc_id, cid, text))
            n_items = len(pending)
            total_ok, total_fail, _ = drain_pending(es, client, index_name, chunks_index, pending, total_ok, total_fail)
            if n_items > 0:
                print("[{}] 已完成 {}/{}".format(index_name, n_items, n_items))
        else:
            resp = es.search(index=index_name, body={"size": SCROLL_SIZE}, scroll=SCROLL_TTL)
            scroll_id = resp.get("_scroll_id")
            batch_hits = resp["hits"]["hits"]
            done = 0
            while batch_hits:
                for h in batch_hits:
                    if h["_id"] in existing_parent_ids:
                        continue
                    doc = h["_source"]
                    es_id = h["_id"]
                    doc_id = doc.get("id", "")
                    for cid, text in build_chunks(doc):
                        if len(text) > MAX_CHARS:
                            text = text[:MAX_CHARS]
                        pending.append((index_name, es_id, doc_id, cid, text))
                    while len(pending) >= BATCH_SIZE or (
                        pending and sum(len(x[4]) for x in pending) > MAX_BATCH_CHARS
                    ):
                        total_ok, total_fail, d = drain_pending(
                            es, client, index_name, chunks_index, pending, total_ok, total_fail
                        )
                        done += d
                        print("[{}] 已完成 {} 条".format(index_name, done))
                resp = es.scroll(scroll_id=scroll_id, scroll=SCROLL_TTL)
                scroll_id = resp.get("_scroll_id")
                batch_hits = resp["hits"]["hits"]
            if scroll_id:
                try:
                    es.clear_scroll(scroll_id=scroll_id)
                except Exception:
                    pass
            total_ok, total_fail, d = drain_pending(es, client, index_name, chunks_index, pending, total_ok, total_fail)
            done += d
            if d > 0:
                print("[{}] 已完成 {} 条".format(index_name, done))

    print()
    print("汇总：成功写入 {} 条，失败 {} 条".format(total_ok, total_fail))


if __name__ == "__main__":
    main()
