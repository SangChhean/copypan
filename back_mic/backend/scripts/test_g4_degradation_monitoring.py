# -*- coding: utf-8 -*-
"""
G4（发现信号未落盘）降级监控端到端集成测试。

覆盖范围（串联真实调用路径，而不是孤立测试单个函数）：
  1. Rerank 服务失败场景：真实调用 features.enhanced_translate.rerank.rerank()，
     只 mock 掉最外层的网络依赖 ai_search.reranker_service.rerank（Jina API），
     内部 _degrade_results() / _record_rerank_degradation() 均按真实代码路径执行，
     最终落到真实的 AIMonitoring.record_degradation()（写入假 Redis）。
  2. 检索未命中降级场景：真实调用
     features.enhanced_translate.service._record_translate_monitoring()
     （enhanced_translate / enhanced_translate_en2zh 内部实际调用的同一个函数对象，
     不是重新实现的等价逻辑），验证每个 degraded_no_refs=True 的行都触发
     record_degradation，字段正确。
  3. rerank_score 平均值场景：验证 avg_rerank_score 正确过滤 None 后求平均。
  4. 全降级场景：验证 avg_rerank_score 为 None 而不是 0。
  5. 容错场景：AIMonitoring.redis 为 None（模拟 Redis 不可用）时，场景 1、2
     的真实调用链路仍能正常跑完、不抛异常、返回值不受影响。
  6. 读取验证：调用真实的 AIMonitoring.get_recent_degradations() /
     get_recent_retrieval_log()，确认场景 1-4 写入的记录能被读回、字段完整。

使用方式：在任意工作目录下运行 `python scripts/test_g4_degradation_monitoring.py`
或 `python back_mic/backend/scripts/test_g4_degradation_monitoring.py`（脚本会
根据自身文件位置定位 back_mic/backend 目录并加入 sys.path，不依赖当前工作目录）。
本脚本只调用现有业务代码，不修改 monitoring.py / rerank.py / service.py 任何一行。

关于外部依赖（不依赖真实 Redis / Jina API / ES / Gemini，可安全重复运行）：
  - Redis：不 mock AIMonitoring 本身的任何方法，而是把它依赖的 self.redis
    换成本脚本内定义的 FakeRedis（一个进程内内存字典实现的最小 redis-py 兼容
    替身，支持 pipeline/lpush/ltrim/lrange/hgetall/delete），这样
    record_degradation / record_retrieval_stats / get_recent_* 的真实业务逻辑
    （key 命名、JSON 序列化、capped list 裁剪等）全部按真实代码执行，只是最终
    的网络 I/O 层被替换。
  - Jina Rerank API：只替换 ai_search.reranker_service.rerank 这一个函数
    （对应 rerank.py 里 `from ai_search.reranker_service import rerank as
    _jina_rerank` 这一层依赖注入点），rerank.py 自身的降级判断、
    _record_rerank_degradation 调用均为真实代码。
  - ES / Gemini：场景 2-4 直接调用 service._record_translate_monitoring()
    （而非完整的 enhanced_translate()/enhanced_translate_en2zh()），因为这两个
    函数内部的检索阶段依赖真实 Elasticsearch 索引和真实 Gemini API Key，在无
    网络/无 ES 环境下无法稳定复现"检索未命中"这种特定分支；而
    _record_translate_monitoring 正是这两个函数在生成 degraded_warnings 之后
    实际调用的同一个监控落盘函数（本次改动的接入点本身），构造 preps 来驱动它
    仍然是对真实接入代码的端到端调用，只是没有从真实检索结果生成 preps。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import ai_search.monitoring as monitoring_mod  # noqa: E402
import ai_search.reranker_service as reranker_service_mod  # noqa: E402
from features.enhanced_translate import rerank as rerank_mod  # noqa: E402
from features.enhanced_translate import service as service_mod  # noqa: E402

_ORIGINAL_JINA_RERANK = reranker_service_mod.rerank


# ── FakeRedis：最小内存实现，只覆盖 AIMonitoring 用到的接口 ──────────────────
class FakeRedis:
    class _Pipe:
        def __init__(self):
            self.ops = []

        def hincrby(self, *a, **k):
            self.ops.append(("hincrby", a, k))
            return self

        def hincrbyfloat(self, *a, **k):
            self.ops.append(("hincrbyfloat", a, k))
            return self

        def expire(self, *a, **k):
            self.ops.append(("expire", a, k))
            return self

        def execute(self):
            return []

    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.hashes: dict[str, dict] = {}

    def ping(self):
        return True

    def pipeline(self):
        return FakeRedis._Pipe()

    def lpush(self, key, value):
        self.lists.setdefault(key, [])
        self.lists[key].insert(0, value)

    def ltrim(self, key, start, end):
        lst = self.lists.get(key, [])
        self.lists[key] = lst[start:end + 1] if end != -1 else lst[start:]

    def lrange(self, key, start, end):
        lst = self.lists.get(key, [])
        return lst[start:] if end == -1 else lst[start:end + 1]

    def hgetall(self, key):
        return self.hashes.get(key, {})

    def delete(self, *keys):
        for k in keys:
            self.lists.pop(k, None)
            self.hashes.pop(k, None)


# ── 结果收集（风格参照 scripts/test_enhanced_translate_e2e.py）───────────────
results: list[tuple[str, bool, str]] = []


def check(scenario: str, cond: bool, detail: str = "") -> None:
    passed = bool(cond)
    results.append((scenario, passed, detail))
    status = "PASS" if passed else "FAIL"
    line = f"[{status}] {scenario}"
    if detail:
        line += f"  ({detail})"
    print(line)


# ── 真实 AIMonitoring 单例，注入 FakeRedis，供 rerank.py / service.py 的
#    真实代码路径通过 get_monitoring() 拿到并写入/读取 ─────────────────────
fake_redis = FakeRedis()
real_monitoring = monitoring_mod.AIMonitoring(redis_client=fake_redis)
monitoring_mod._monitoring_instance = real_monitoring


def _degradation_count() -> int:
    return len(fake_redis.lists.get(monitoring_mod.KEY_DEGRADATION_LOG, []))


def _retrieval_log_count() -> int:
    return len(fake_redis.lists.get(monitoring_mod.KEY_RETRIEVAL_LOG, []))


async def scenario_1_rerank_failure() -> None:
    print("\n" + "=" * 78)
    print("场景 1：Rerank 服务失败 -> rerank.py 真实降级路径 -> record_degradation 落盘")
    print("=" * 78)

    sample_results = [
        {"text": "第一条候选文本", "chunk_id": "c1"},
        {"text": "第二条候选文本", "chunk_id": "c2"},
        {"text": "第三条候选文本", "chunk_id": "c3"},
    ]
    long_query = "这是一个用于测试 query_preview 截断逻辑的很长查询文本" * 3

    # 1a: degraded=True（模拟 JINA_API_KEY 未配置或 API 调用失败）
    async def _fake_degraded(query, texts, top_n=20):
        return list(range(len(texts))), [], True

    reranker_service_mod.rerank = _fake_degraded
    before = _degradation_count()
    out, msg = await rerank_mod.rerank(sample_results, long_query, top_n=3)
    check(
        "1a-i. degraded=True 时返回结果保持原序、数量正确、标记 rerank_degraded=True",
        len(out) == 3
        and [d["chunk_id"] for d in out] == ["c1", "c2", "c3"]
        and all(d.get("rerank_degraded") is True for d in out),
        f"out={out}",
    )
    check("1a-ii. rerank() 返回了非 None 的降级提示 msg", msg is not None, f"msg={msg}")
    after = _degradation_count()
    check("1a-iii. record_degradation 被真实调用一次（degradation_log 计数 +1）", after - before == 1, f"before={before} after={after}")
    latest = json.loads(fake_redis.lists[monitoring_mod.KEY_DEGRADATION_LOG][0])
    check(
        "1a-iv. 落盘记录 source=rerank_service，reason 与实际失败原因一致",
        latest.get("source") == "rerank_service" and latest.get("reason") == "JINA_API_KEY 未配置或 API 失败",
        f"latest={latest}",
    )
    check(
        "1a-v. 落盘记录 query_preview 已截断到 <=30 字（不记录完整 query）",
        "query_preview" in latest and len(latest["query_preview"]) <= 30,
        f"query_preview_len={len(latest.get('query_preview', ''))}",
    )

    # 1b: 真实异常（模拟 Jina 调用抛出网络异常）
    async def _fake_exception(query, texts, top_n=20):
        raise ConnectionError("模拟 Jina API 网络超时")

    reranker_service_mod.rerank = _fake_exception
    before = _degradation_count()
    out2, msg2 = await rerank_mod.rerank(sample_results, long_query, top_n=3)
    after = _degradation_count()
    check(
        "1b-i. 异常场景返回结果仍正确降级（保持原序、数量正确）",
        len(out2) == 3 and [d["chunk_id"] for d in out2] == ["c1", "c2", "c3"],
        f"out2={out2}",
    )
    check("1b-ii. 异常场景 record_degradation 被调用一次", after - before == 1, f"before={before} after={after}")
    latest2 = json.loads(fake_redis.lists[monitoring_mod.KEY_DEGRADATION_LOG][0])
    check(
        "1b-iii. 落盘 reason 与实际异常信息一致（str(e)）",
        latest2.get("source") == "rerank_service" and latest2.get("reason") == "模拟 Jina API 网络超时",
        f"latest2={latest2}",
    )

    # 1c: indices 为空（degraded=False 但没有任何候选下标）
    async def _fake_empty_indices(query, texts, top_n=20):
        return [], [], False

    reranker_service_mod.rerank = _fake_empty_indices
    before = _degradation_count()
    out3, msg3 = await rerank_mod.rerank(sample_results, long_query, top_n=3)
    after = _degradation_count()
    check("1c-i. indices 为空场景 record_degradation 被调用一次", after - before == 1, f"before={before} after={after}")
    latest3 = json.loads(fake_redis.lists[monitoring_mod.KEY_DEGRADATION_LOG][0])
    check("1c-ii. 落盘 reason='indices 为空'", latest3.get("reason") == "indices 为空", f"latest3={latest3}")

    # 1d: indices 全部越界，解析后 out 为空
    async def _fake_out_of_range(query, texts, top_n=20):
        return [999, 998], [0.5, 0.4], False

    reranker_service_mod.rerank = _fake_out_of_range
    before = _degradation_count()
    out4, msg4 = await rerank_mod.rerank(sample_results, long_query, top_n=3)
    after = _degradation_count()
    check("1d-i. out 为空场景 record_degradation 被调用一次", after - before == 1, f"before={before} after={after}")
    latest4 = json.loads(fake_redis.lists[monitoring_mod.KEY_DEGRADATION_LOG][0])
    check("1d-ii. 落盘 reason='indices 解析后 out 为空'", latest4.get("reason") == "indices 解析后 out 为空", f"latest4={latest4}")

    # 1e: 对照组——正常成功路径不应触发任何 record_degradation
    async def _fake_success(query, texts, top_n=20):
        return list(range(len(texts))), [0.9, 0.8, 0.7][: len(texts)], False

    reranker_service_mod.rerank = _fake_success
    before = _degradation_count()
    out5, msg5 = await rerank_mod.rerank(sample_results, long_query, top_n=3)
    after = _degradation_count()
    check(
        "1e-i. 对照组：成功路径 rerank_degraded=False 且带有 rerank_score",
        all(d.get("rerank_degraded") is False and "rerank_score" in d for d in out5),
        f"out5={out5}",
    )
    check("1e-ii. 对照组：成功路径不触发 record_degradation（计数不变）", after == before, f"before={before} after={after}")


async def scenario_2_3_4_translate_degradation() -> None:
    print("\n" + "=" * 78)
    print("场景 2/3/4：检索未命中降级 + rerank_score 平均值 + 全降级场景")
    print("（真实调用 service._record_translate_monitoring，即 enhanced_translate")
    print(" / enhanced_translate_en2zh 内部实际调用的同一函数对象）")
    print("=" * 78)

    check(
        "0. 前置确认：_record_translate_monitoring 确为 enhanced_translate 系列函数内部真实引用的对象",
        service_mod._record_translate_monitoring.__module__ == service_mod.__name__,
        f"module={service_mod._record_translate_monitoring.__module__}",
    )

    # 场景 2：混合场景（1 行降级 + 2 行有 refs），同时兼顾场景 3 的 rerank_score 平均值
    preps_mixed = [
        {
            "line_i": 0,
            "line_type": "reference",
            "deduped_refs": [{"rerank_score": 0.7}, {"rerank_score": None}],
        },
        {
            "line_i": 1,
            "line_type": "outline",
            "deduped_refs": [{"rerank_score": 0.9}],
        },
        {
            "line_i": 2,
            "line_type": "reference",
            "deduped_refs": [],
            "degraded_no_refs": True,
        },
    ]

    before_deg = _degradation_count()
    before_ret = _retrieval_log_count()
    service_mod._record_translate_monitoring(preps_mixed, "混合场景测试纲目内容" * 3, direction="zh2en")
    after_deg = _degradation_count()
    after_ret = _retrieval_log_count()

    check("2a-i. 混合场景：只有 1 行 degraded_no_refs=True，record_degradation 恰好触发 1 次", after_deg - before_deg == 1, f"before={before_deg} after={after_deg}")
    deg_item = json.loads(fake_redis.lists[monitoring_mod.KEY_DEGRADATION_LOG][0])
    check(
        "2a-ii. 落盘字段 source=translate_line，line_i/line_type/direction 正确",
        deg_item.get("source") == "translate_line"
        and deg_item.get("line_i") == 2
        and deg_item.get("line_type") == "reference"
        and deg_item.get("direction") == "zh2en",
        f"deg_item={deg_item}",
    )

    check("2b-i. record_retrieval_stats 被调用一次（retrieval_log 计数 +1）", after_ret - before_ret == 1, f"before={before_ret} after={after_ret}")
    ret_item = json.loads(fake_redis.lists[monitoring_mod.KEY_RETRIEVAL_LOG][0])
    check(
        "2b-ii. total=3（总行数）、used=2（有 deduped_refs 的行数）",
        ret_item.get("total") == 3 and ret_item.get("used") == 2,
        f"ret_item={ret_item}",
    )
    expected_waste = round(1 / 3 * 100, 1)
    check(
        f"2b-iii. waste_rate=degraded_count/total*100={expected_waste}",
        abs(ret_item.get("waste_rate", -1) - expected_waste) < 1e-6,
        f"waste_rate={ret_item.get('waste_rate')}",
    )
    check("2b-iv. mode='增强式翻译'（区别于 kg_rag_service 的 'KG-RAG'）", ret_item.get("mode") == "增强式翻译", f"mode={ret_item.get('mode')}")

    # 场景 3：avg_rerank_score 正确过滤 None 后求平均 = (0.7+0.9)/2 = 0.8
    check(
        "3a. avg_rerank_score 正确排除 None 值后求平均（(0.7+0.9)/2=0.8）",
        abs(ret_item.get("avg_rerank_score", -1) - 0.8) < 1e-9,
        f"avg_rerank_score={ret_item.get('avg_rerank_score')}",
    )

    # 场景 4：全降级、没有任何 rerank_score -> avg_rerank_score 必须是 None，不是 0
    preps_all_degraded = [
        {"line_i": 0, "line_type": "reference", "deduped_refs": [], "degraded_no_refs": True},
        {"line_i": 1, "line_type": "reference", "deduped_refs": [], "degraded_no_refs": True},
        {"line_i": 2, "line_type": "outline", "deduped_refs": [], "degraded_no_refs": True},
    ]
    before_deg = _degradation_count()
    service_mod._record_translate_monitoring(preps_all_degraded, "全降级场景测试", direction="en2zh")
    after_deg = _degradation_count()
    check("4a. 全降级场景：3 行全部触发 record_degradation", after_deg - before_deg == 3, f"before={before_deg} after={after_deg}")
    deg_items = [json.loads(s) for s in fake_redis.lists[monitoring_mod.KEY_DEGRADATION_LOG][:3]]
    check(
        "4b. 全降级场景：3 条记录 direction 均为 en2zh",
        all(d.get("direction") == "en2zh" for d in deg_items),
        f"deg_items={deg_items}",
    )
    ret_item_all = json.loads(fake_redis.lists[monitoring_mod.KEY_RETRIEVAL_LOG][0])
    check(
        "4c. avg_rerank_score 为 None（键不存在），而不是被写成 0",
        "avg_rerank_score" not in ret_item_all,
        f"ret_item_all={ret_item_all}",
    )
    check("4d. used=0（没有任何行拿到 deduped_refs）", ret_item_all.get("used") == 0, f"used={ret_item_all.get('used')}")


async def scenario_5_fault_tolerance() -> None:
    print("\n" + "=" * 78)
    print("场景 5：Redis 不可用时的容错（AIMonitoring.redis=None）")
    print("=" * 78)

    broken_monitoring = monitoring_mod.AIMonitoring(redis_client=None)
    check("5-0. 构造的容错实例 self.redis 确实为 None", broken_monitoring.redis is None)
    monitoring_mod._monitoring_instance = broken_monitoring

    # 5a: rerank.py 真实降级路径在 Redis 不可用时仍要正常返回
    async def _fake_degraded(query, texts, top_n=20):
        return list(range(len(texts))), [], True

    reranker_service_mod.rerank = _fake_degraded
    sample_results = [{"text": "x1", "chunk_id": "a"}, {"text": "x2", "chunk_id": "b"}]
    exc = None
    out = msg = None
    try:
        out, msg = await rerank_mod.rerank(sample_results, "容错测试查询", top_n=2)
    except Exception as e:  # noqa: BLE001
        exc = e
    check("5a-i. Redis 不可用时 rerank() 调用不抛异常", exc is None, f"exc={exc}")
    check(
        "5a-ii. Redis 不可用时降级返回结果仍正确（保持原序、数量正确）",
        out is not None and len(out) == 2 and [d["chunk_id"] for d in out] == ["a", "b"],
        f"out={out}",
    )

    # 5b: service._record_translate_monitoring 在 Redis 不可用时仍要正常跑完
    preps = [
        {"line_i": 0, "line_type": "reference", "deduped_refs": [], "degraded_no_refs": True},
        {"line_i": 1, "line_type": "reference", "deduped_refs": [{"rerank_score": 0.5}]},
    ]
    exc2 = None
    try:
        service_mod._record_translate_monitoring(preps, "容错测试纲目", direction="zh2en")
    except Exception as e:  # noqa: BLE001
        exc2 = e
    check("5b-i. Redis 不可用时 _record_translate_monitoring 不抛异常", exc2 is None, f"exc2={exc2}")

    # 恢复为 FakeRedis 支撑的真实实例，供场景 6 读取校验
    monitoring_mod._monitoring_instance = real_monitoring


def scenario_6_read_back() -> None:
    print("\n" + "=" * 78)
    print("场景 6：读取验证（get_recent_degradations / get_recent_retrieval_log）")
    print("=" * 78)

    check(
        "6-0. 单例已恢复为 FakeRedis 支撑的真实 AIMonitoring 实例",
        monitoring_mod.get_monitoring() is real_monitoring,
    )

    degradations = real_monitoring.get_recent_degradations(limit=50)
    check(
        "6a. get_recent_degradations 能读到场景 1/2/4 写入的记录（数量 >= 1a+1b+1c+1d(4) + 2a(1) + 4a(3) = 8）",
        len(degradations) >= 8,
        f"len={len(degradations)}",
    )
    sources = {d.get("source") for d in degradations}
    check(
        "6b. 读回记录同时包含 rerank_service 与 translate_line 两种 source，字段完整（ts/source/reason 齐全）",
        sources == {"rerank_service", "translate_line"}
        and all({"ts", "source", "reason"} <= set(d.keys()) for d in degradations),
        f"sources={sources}",
    )

    retrieval_log = real_monitoring.get_recent_retrieval_log(limit=50)
    check(
        "6c. get_recent_retrieval_log 能读到场景 2/4 写入的记录（数量 >= 2）",
        len(retrieval_log) >= 2,
        f"len={len(retrieval_log)}",
    )
    check(
        "6d. 读回的检索日志字段完整，且 mode 均为增强式翻译",
        all(
            {"ts", "question", "total", "used", "waste_rate", "mode"} <= set(r.keys()) and r.get("mode") == "增强式翻译"
            for r in retrieval_log
        ),
        f"retrieval_log={retrieval_log}",
    )
    has_avg = [r for r in retrieval_log if "avg_rerank_score" in r]
    no_avg = [r for r in retrieval_log if "avg_rerank_score" not in r]
    check(
        "6e. 读回记录里既有带 avg_rerank_score 字段的（混合场景），也有不带该字段的（全降级场景）",
        len(has_avg) >= 1 and len(no_avg) >= 1,
        f"has_avg_count={len(has_avg)} no_avg_count={len(no_avg)}",
    )


async def main() -> None:
    try:
        await scenario_1_rerank_failure()
        await scenario_2_3_4_translate_degradation()
        await scenario_5_fault_tolerance()
        scenario_6_read_back()
    finally:
        reranker_service_mod.rerank = _ORIGINAL_JINA_RERANK

    print("\n" + "=" * 78)
    print("测试报告汇总")
    print("=" * 78)
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}")
        if not ok and detail:
            print(f"         详情: {detail}")
    print("-" * 78)
    print(f"总计 {total} 项断言，通过 {passed} 项，失败 {failed} 项")
    if failed:
        print("存在失败项，请查看上方标记 FAIL 的条目及其详情。")
    else:
        print("全部通过。")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
