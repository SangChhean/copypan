# -*- coding: utf-8 -*-
"""
经文型向量化：bib。
从 id 解析 bib_{book}-{chapter}-{verse}，按 book+chapter 分组合并 zh，每章一个向量；
向量写回该章第一条文档（verse=1 优先，否则该章首条）的 embedding 字段。
断点续传：构建章节列表后，用 mget 检查首条文档是否已有 embedding，只处理尚无向量的章。
TEST_MODE=False 时用 scroll 遍历全量 bib 文档，边 scroll 边按章聚合，再批量 embed+写回。
使用方式：在 back_mic/backend 下执行  python scripts/vectorize_bib.py
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
TEST_MODE = False
SCROLL_SIZE = 1000
SCROLL_TTL = "5m"

INDEX_BIB = "bib"
ID_PATTERN = re.compile(r"^bib_(\d+)-(\d+)-(\d+)$")
DOCS_LIMIT = 100 if TEST_MODE else None

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 512


def parse_bib_id(doc_id):
    """解析 bib_{book}-{chapter}-{verse}，返回 (book, chapter, verse) 或 None。"""
    if not doc_id or not isinstance(doc_id, str):
        return None
    m = ID_PATTERN.match(doc_id.strip())
    if not m:
        return None
    return (m.group(1), m.group(2), m.group(3))


def get_embeddings(client, texts):
    if not texts:
        return []
    r = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=EMBEDDING_DIMS,
    )
    return [d.embedding for d in r.data]


def main():
    from es_config import es
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("错误：未设置 OPENAI_API_KEY（.env）")
        return
    client = OpenAI(api_key=api_key)

    by_key = {}

    if TEST_MODE:
        r = es.search(index=INDEX_BIB, size=DOCS_LIMIT)
        hits = r["hits"]["hits"]
        for h in hits:
            doc = h["_source"]
            doc_id = doc.get("id", "")
            parsed = parse_bib_id(doc_id)
            if not parsed:
                continue
            book, chapter, verse = parsed
            key = (book, chapter)
            if key not in by_key:
                by_key[key] = {"texts": [], "candidates": []}
            zh = (doc.get("zh") or doc.get("text") or "").strip()
            if zh:
                by_key[key]["texts"].append(zh)
            by_key[key]["candidates"].append((h["_id"], int(verse)))
    else:
        resp = es.search(index=INDEX_BIB, body={"size": SCROLL_SIZE}, scroll=SCROLL_TTL)
        scroll_id = resp.get("_scroll_id")
        batch_hits = resp["hits"]["hits"]
        while batch_hits:
            for h in batch_hits:
                doc = h["_source"]
                doc_id = doc.get("id", "")
                parsed = parse_bib_id(doc_id)
                if not parsed:
                    continue
                book, chapter, verse = parsed
                key = (book, chapter)
                if key not in by_key:
                    by_key[key] = {"texts": [], "candidates": []}
                zh = (doc.get("zh") or doc.get("text") or "").strip()
                if zh:
                    by_key[key]["texts"].append(zh)
                by_key[key]["candidates"].append((h["_id"], int(verse)))
            resp = es.scroll(scroll_id=scroll_id, scroll=SCROLL_TTL)
            scroll_id = resp.get("_scroll_id")
            batch_hits = resp["hits"]["hits"]
        if scroll_id:
            try:
                es.clear_scroll(scroll_id=scroll_id)
            except Exception:
                pass

    chapters = []
    for (book, chapter), data in sorted(by_key.items(), key=lambda x: (x[0][0], x[0][1])):
        merged = "".join(data["texts"])
        if not merged:
            continue
        cands = data["candidates"]
        verse1 = [c for c in cands if c[1] == 1]
        first_es_id = verse1[0][0] if verse1 else cands[0][0]
        chapters.append((INDEX_BIB, first_es_id, merged))

    # 断点续传：只处理首条文档尚无 embedding 的章
    if chapters:
        all_first_ids = [c[1] for c in chapters]
        has_embedding = set()
        for start in range(0, len(all_first_ids), 1000):
            batch_ids = all_first_ids[start : start + 1000]
            try:
                r = es.mget(index=INDEX_BIB, body={"ids": batch_ids}, _source=["embedding"])
                for doc in r.get("docs", []):
                    if doc.get("found") and doc.get("_source") and doc["_source"].get("embedding"):
                        has_embedding.add(doc["_id"])
            except Exception:
                pass
        chapters = [c for c in chapters if c[1] not in has_embedding]
        if has_embedding:
            print("[bib] 已有 {} 章存在 embedding，将跳过".format(len(has_embedding)))

    total_ok = 0
    total_fail = 0
    total = len(chapters)
    for start in range(0, total, BATCH_SIZE):
        batch = chapters[start : start + BATCH_SIZE]
        texts = [x[2] for x in batch]
        try:
            vectors = get_embeddings(client, texts)
        except Exception as e:
            print("[bib] Embedding 批量失败: {}".format(e))
            total_fail += len(batch)
            continue
        for i, (idx, es_id, _text) in enumerate(batch):
            if i >= len(vectors):
                total_fail += 1
                continue
            try:
                es.update(
                    index=idx,
                    id=es_id,
                    body={"doc": {"embedding": vectors[i]}},
                    refresh=False,
                )
                total_ok += 1
            except Exception as e:
                print("[bib] 写回失败 id={}: {}".format(es_id, e))
                total_fail += 1
        print("[bib] 已完成 {}/{}".format(min(start + len(batch), total), total))

    print()
    print("汇总：成功写入 {} 条，失败 {} 条".format(total_ok, total_fail))


if __name__ == "__main__":
    main()
