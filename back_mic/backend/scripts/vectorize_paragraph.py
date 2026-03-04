# -*- coding: utf-8 -*-
"""
段落型向量化：cwwl, cwwn, life, others。
只处理 type=="text" 的文档，向量化文本优先 zh，空则用 text。
读文本 → OpenAI embedding → 写回 ES embedding 字段。
断点续传：scroll 只扫 embedding 不存在的文档（query 加 must_not exists embedding）。
TEST_MODE=False 时用 scroll 遍历全量 type=text 且无 embedding 的文档，边 scroll 边处理边写入。
使用方式：在 back_mic/backend 下执行  python scripts/vectorize_paragraph.py
"""
import sys
import os

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

INDICES = ["cwwl", "cwwn", "life", "others"]
LIMIT_PER_INDEX = 100 if TEST_MODE else None

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 512

QUERY_TEXT = {"query": {"term": {"type": "text"}}}
# 断点续传：只处理尚未有 embedding 的文档
QUERY_TEXT_NO_EMBED = {
    "query": {
        "bool": {
            "must": [{"term": {"type": "text"}}],
            "must_not": [{"exists": {"field": "embedding"}}],
        }
    }
}


def get_text(doc):
    """优先 zh，空则 text。"""
    s = (doc.get("zh") or doc.get("text") or "").strip()
    return s


def get_embeddings(client, texts):
    if not texts:
        return []
    r = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=EMBEDDING_DIMS,
    )
    return [d.embedding for d in r.data]


def drain_pending(es, client, index_name, pending, total_ok, total_fail):
    """从 pending 中取最多 BATCH_SIZE 条，embedding 后写回 ES；返回 (new_total_ok, new_total_fail, num_drained)。"""
    drained = 0
    while len(pending) >= BATCH_SIZE:
        batch = pending[:BATCH_SIZE]
        del pending[:BATCH_SIZE]
        drained += len(batch)
        texts = [x[2] for x in batch]
        try:
            vectors = get_embeddings(client, texts)
        except Exception as e:
            print("[{}] Embedding 批量失败: {}".format(index_name, e))
            total_fail += len(batch)
            continue
        for i, (idx, eid, _) in enumerate(batch):
            if i >= len(vectors):
                total_fail += 1
                continue
            try:
                es.update(
                    index=idx,
                    id=eid,
                    body={"doc": {"embedding": vectors[i]}},
                    retry_on_conflict=3,
                    refresh=False,
                )
                total_ok += 1
            except Exception as e:
                print("[{}] 写回失败 id={}: {}".format(idx, eid, e))
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

    for index_name in INDICES:
        pending = []

        if TEST_MODE:
            r = es.search(
                index=index_name,
                body={**QUERY_TEXT_NO_EMBED, "size": LIMIT_PER_INDEX},
            )
            hits = r["hits"]["hits"]
            for h in hits:
                doc = h["_source"]
                es_id = h["_id"]
                text = get_text(doc)
                if not text:
                    continue
                pending.append((index_name, es_id, text))
            n_items = len(pending)
            total_ok, total_fail, _ = drain_pending(es, client, index_name, pending, total_ok, total_fail)
            if n_items > 0:
                print("[{}] 已完成 {}/{}".format(index_name, n_items, n_items))
        else:
            total_count = es.count(index=index_name, body=QUERY_TEXT_NO_EMBED).get("count", 0)
            resp = es.search(
                index=index_name,
                body={**QUERY_TEXT_NO_EMBED, "size": SCROLL_SIZE},
                scroll=SCROLL_TTL,
            )
            scroll_id = resp.get("_scroll_id")
            batch_hits = resp["hits"]["hits"]
            done = 0
            while batch_hits:
                for h in batch_hits:
                    doc = h["_source"]
                    es_id = h["_id"]
                    text = get_text(doc)
                    if not text:
                        continue
                    pending.append((index_name, es_id, text))
                    while len(pending) >= BATCH_SIZE:
                        total_ok, total_fail, d = drain_pending(es, client, index_name, pending, total_ok, total_fail)
                        done += d
                        print("[{}] 已完成 {}/{}".format(index_name, min(done, total_count), total_count))
                resp = es.scroll(scroll_id=scroll_id, scroll=SCROLL_TTL)
                scroll_id = resp.get("_scroll_id")
                batch_hits = resp["hits"]["hits"]
            if scroll_id:
                try:
                    es.clear_scroll(scroll_id=scroll_id)
                except Exception:
                    pass
            total_ok, total_fail, d = drain_pending(es, client, index_name, pending, total_ok, total_fail)
            done += d
            if done > 0:
                print("[{}] 已完成 {}/{}".format(index_name, done, total_count))

    print()
    print("汇总：成功写入 {} 条，失败 {} 条".format(total_ok, total_fail))


if __name__ == "__main__":
    main()
