# -*- coding: utf-8 -*-
"""
从本地 ES 7.x 将索引 reindex 到本地 ES 8.x。

前提条件（ES 8.x 服务端）：
  - 在 ES 8.x 的 elasticsearch.yml 中配置：
      reindex.remote.whitelist: [host.docker.internal:9201]
  - 配置后需重启 ES 8.x 才能生效。

连接配置：
  - ES 7.x source：http://localhost:9201，无认证
  - ES 8.x dest：http://localhost:9200，认证 elastic / qwSD4AF2Dcv
"""
import sys
import time

# 连接配置
# 脚本在宿主机运行，拉取索引列表和 mapping 时连 ES 7.x 用 localhost
ES7_HOST = "http://localhost:9201"
# reindex 由 ES 8.x 容器内发起，需用 host.docker.internal 才能连到宿主机 7.x
ES7_REINDEX_REMOTE_HOST = "http://host.docker.internal:9201"
ES8_HOST = "http://localhost:9200"
ES8_USER = "elastic"
ES8_PASSWORD = "qwSD4AF2Dcv"

# 仅复制这些索引；空列表 [] 表示全部，非空则只跑指定索引
ONLY_INDICES = []

# 轮询间隔（秒）
POLL_INTERVAL = 15

# 过滤：排除系统索引（. 开头）和空索引（docs.count = 0）
def should_include(index_name: str, docs_count: str) -> bool:
    if not index_name or index_name.startswith("."):
        return False
    try:
        return int(docs_count or "0") > 0
    except (ValueError, TypeError):
        return False


def main():
    from elasticsearch import Elasticsearch

    es7 = Elasticsearch(hosts=[ES7_HOST], request_timeout=60)
    es8 = Elasticsearch(
        hosts=[ES8_HOST],
        basic_auth=(ES8_USER, ES8_PASSWORD),
        request_timeout=120,
    )

    # 从 7.x 获取所有索引（cat.indices 返回 JSON 便于解析）
    raw = es7.cat.indices(format="json", h="index,docs.count,store.size")
    if not raw:
        print("7.x 未返回任何索引")
        return

    candidates = [
        (item["index"], item.get("docs.count", "0"), item.get("store.size", ""))
        for item in raw
        if should_include(item.get("index", ""), item.get("docs.count", "0"))
    ]
    candidates.sort(key=lambda x: x[0])

    if ONLY_INDICES:
        only_set = set(ONLY_INDICES)
        candidates = [c for c in candidates if c[0] in only_set]
        if not candidates:
            print("ONLY_INDICES 指定了 {}，但 7.x 中无匹配索引".format(ONLY_INDICES))
            return
        print("仅复制指定索引: {}".format(ONLY_INDICES))

    if not candidates:
        print("过滤后没有需要复制的索引（已排除系统索引和空索引）")
        return

    print("将要复制的索引列表（共 {} 个）：".format(len(candidates)))
    for idx, (name, docs, size) in enumerate(candidates, 1):
        print("  {:3d}. {}  (docs={}, size={})".format(idx, name, docs, size))
    print()
    try:
        input("按回车确认后开始执行，Ctrl+C 取消...")
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(0)

    success_count = 0
    fail_count = 0

    for index_name, src_docs_str, _ in candidates:
        try:
            src_docs = int(src_docs_str or "0")

            # 1) 若 8.x 已存在该索引则先删除再重建，避免重复数据
            if es8.indices.exists(index=index_name):
                es8.indices.delete(index=index_name)
                print("[{}] 已删除 8.x 原有索引".format(index_name))

            # 2) 从 7.x 读取 mapping，在 8.x 创建索引
            m = es7.indices.get_mapping(index=index_name)
            mapping = m[index_name].get("mappings", {})
            es8.indices.create(index=index_name, body={"mappings": mapping})
            print("[{}] 已在 8.x 创建索引".format(index_name))

            # 3) 异步 reindex：wait_for_completion=False，拿到 task_id
            body = {
                "source": {
                    "remote": {"host": ES7_REINDEX_REMOTE_HOST},
                    "index": index_name,
                },
                "dest": {"index": index_name},
            }
            result = es8.reindex(body=body, wait_for_completion=False, request_timeout=30)
            task_id = result.get("task")
            if not task_id:
                raise RuntimeError("reindex 未返回 task_id: {}".format(result))

            # 4) 轮询任务直到完成，每 15 秒打印进度
            while True:
                time.sleep(POLL_INTERVAL)
                task_info = es8.tasks.get(task_id=task_id, request_timeout=30)
                completed = task_info.get("completed", False)
                status = task_info.get("task", {}).get("status", {})
                total = status.get("total", 0)
                created = status.get("created", 0)
                updated = status.get("updated", 0)
                done = created + updated
                print("    {}  进度: {} / {} (created={}, updated={})".format(
                    index_name, done, total, created, updated
                ))
                if completed:
                    break

            # 5) 验证：源文档数 vs 8.x 实际文档数
            dest_count = es8.count(index=index_name).get("count", 0)
            if dest_count != src_docs:
                print("  {}  源文档数={}  复制后 8.x 文档数={}  [警告: 数量不一致]".format(
                    index_name, src_docs, dest_count
                ))
            else:
                print("  {}  源文档数={}  复制后 8.x 文档数={}  OK".format(
                    index_name, src_docs, dest_count
                ))
            success_count += 1
        except Exception as e:
            print("  {}  失败: {}".format(index_name, e))
            fail_count += 1

    print()
    print("汇总：成功 {} 个，失败 {} 个".format(success_count, fail_count))


if __name__ == "__main__":
    main()
