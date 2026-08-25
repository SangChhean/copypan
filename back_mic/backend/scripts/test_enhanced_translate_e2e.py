# -*- coding: utf-8 -*-
"""
增强式翻译 Pool 读写全链路集成测试。

覆盖范围（串联真实调用路径，而不是孤立测试单个函数）：
  1. human_verified 加载迁移（Additional Pool + Source Pool）
  2. 单行编辑保存完整链路：router.api_update_translation（内容变化）
  3. force_confirm 强制确认（内容不变）+ 幂等性
  4. 单行删除完整链路：router.api_delete_translation
  5. source_pool 联动：保存/删除带出处的正文行时，source_pool 记录同步更新/删除
  6. API 响应透传完整链路：router.retrieve_test / service._build_line_ref_group /
     source_translator.translate_source_zh_batch
  7. 边界情况：force_confirm + 记录不存在；.bak 备份机制仍然生效

使用方式：在任意工作目录下运行 `python scripts/test_enhanced_translate_e2e.py`
或 `python back_mic/backend/scripts/test_enhanced_translate_e2e.py`（脚本会
根据自身文件位置定位 back_mic/backend 目录并加入 sys.path，不依赖当前工作目录）。
本脚本只读取/调用现有业务代码，不修改任何 pool.py / router.py / service.py /
source_translator.py / EnhancedTranslate.vue 文件。

关于外部依赖（不依赖真实 ES / Gemini，可安全重复运行，无额外成本）：
  - 场景 6 涉及的检索、出处翻译流程本来会调用真实 Elasticsearch 和 Gemini API。
    为了让这份测试可以在没有 ES/网络、或不想产生 token 开销的环境下稳定重复
    运行，这里只在**本进程内**、**仅测试脚本自己的作用域**里，对
    service.es_client 替换成一个返回"空命中"的假对象，对
    source_translator._gemini_sources_once 替换成一个直接返回空结果的假函数
    ——这两处都是运行期 monkeypatch，完全没有修改任何 .py 源文件本身。
    被替换的函数覆盖的是"外部服务调用"这一层，_probe_es / _retrieve_line /
    translate_source_zh_batch 内部的真实业务分支逻辑（路1/路2选择、
    human_verified 逐条透传等）都还是原样执行、原样被测试到。
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

# 定位到 back_mic/backend（本文件位于 back_mic/backend/scripts/ 下），
# 不依赖运行脚本时的当前工作目录，与 scripts/ 目录下其他脚本
# （如 list_indices.py）的写法保持一致。
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import features.enhanced_translate.pool as pool  # noqa: E402

# ── 0. 隔离的临时 pool 目录，先于 router/service 导入完成路径替换 ──────────────
tmpdir = Path(tempfile.mkdtemp(prefix="enhanced_translate_e2e_"))
pool._POOL_DIR = tmpdir
pool._POOL_FILE = tmpdir / "pool.jsonl"
pool._SOURCE_POOL_PATH = tmpdir / "source_pool.jsonl"
pool._cache_by_norm.clear()
pool._cache_mtime = 0.0
pool._source_pool_loaded = False

print(f"[setup] 临时目录: {tmpdir}")

# ── 构造初始数据 ──────────────────────────────────────────────────────────────
# Additional Pool：3 条"存量"（无 human_verified，模拟迁移前真实数据）+ 1 条已确认
legacy_pool_rows = [
    {
        "zh": "基督是我们的生命",
        "en": "Christ is our life",
        "norm_zh": pool.normalize_zh("基督是我们的生命"),
        "source": "enhanced_translate",
    },
    {
        "zh": "神是爱",
        "en": "God is love",
        "norm_zh": pool.normalize_zh("神是爱"),
        "source": "enhanced_translate",
    },
    {
        "zh": "英译中示例行",
        "en": "english to chinese example line",
        "norm_zh": pool.normalize_zh("英译中示例行"),
        "norm_en": pool.normalize_en("english to chinese example line"),
        "source": "enhanced_translate_en2zh",
    },
]
confirmed_pool_row = {
    "zh": "已确认的行",
    "en": "already confirmed line",
    "norm_zh": pool.normalize_zh("已确认的行"),
    "human_verified": True,
    "source": "enhanced_translate",
}

with pool._POOL_FILE.open("w", encoding="utf-8") as f:
    for row in legacy_pool_rows + [confirmed_pool_row]:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

# Source Pool：2 条"存量"（无 human_verified）+ 1 条已确认
# - "腓立比书生命读经，第三篇" / "希伯来书结晶读经，第七篇" 用于迁移检查 + 多出处场景
# - "创世记生命读经，第一篇" 专门留给场景 5（正文行出处联动）
legacy_source_rows = [
    {
        "zh": "腓立比书生命读经，第三篇",
        "en": "Life-study of Philippians, Message Three",
        "norm_zh": pool.normalize_zh("腓立比书生命读经，第三篇"),
        "norm_en": pool.normalize_en("Life-study of Philippians, Message Three"),
    },
    {
        "zh": "创世记生命读经，第一篇",
        "en": "Life-study of Genesis, Message 1 (old rendering)",
        "norm_zh": pool.normalize_zh("创世记生命读经，第一篇"),
        "norm_en": pool.normalize_en("Life-study of Genesis, Message 1 (old rendering)"),
    },
]
confirmed_source_row = {
    "zh": "希伯来书结晶读经，第七篇",
    "en": "Crystallization-study of Hebrews, Message Seven",
    "norm_zh": pool.normalize_zh("希伯来书结晶读经，第七篇"),
    "norm_en": pool.normalize_en("Crystallization-study of Hebrews, Message Seven"),
    "human_verified": True,
}

with pool._SOURCE_POOL_PATH.open("w", encoding="utf-8") as f:
    for row in legacy_source_rows + [confirmed_source_row]:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

# ── 结果收集 ──────────────────────────────────────────────────────────────────
results: list[tuple[str, bool, str]] = []


def check(scenario: str, cond: bool, detail: str = "") -> None:
    passed = bool(cond)
    results.append((scenario, passed, detail))
    status = "PASS" if passed else "FAIL"
    line = f"[{status}] {scenario}"
    if detail:
        line += f"  ({detail})"
    print(line)


# ═══════════════════════════════════════════════════════════════════════════
# 场景 1：加载迁移
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 78)
print("场景 1：加载迁移（缺 human_verified 字段自动补 false，已有字段不受影响）")
print("=" * 78)

pool.reload_pool(force=True)
for row in legacy_pool_rows:
    rec = pool._cache_by_norm.get(row["norm_zh"])
    check(
        f"1a. Additional Pool 存量记录迁移: 「{row['zh']}」 human_verified=False",
        rec is not None and rec.get("human_verified") is False,
        f"rec={rec}",
    )
rec_confirmed = pool._cache_by_norm.get(confirmed_pool_row["norm_zh"])
check(
    "1b. Additional Pool 已确认记录不受迁移影响（仍为 True）",
    rec_confirmed is not None and rec_confirmed.get("human_verified") is True,
    f"rec={rec_confirmed}",
)

pool._source_pool_loaded = False
pool._load_source_pool()
for row in legacy_source_rows:
    rec = pool._source_pool_by_norm_zh.get(row["norm_zh"])
    check(
        f"1c. Source Pool 存量记录迁移: 「{row['zh']}」 human_verified=False",
        rec is not None and rec.get("human_verified") is False,
        f"rec={rec}",
    )
rec_confirmed_src = pool._source_pool_by_norm_zh.get(confirmed_source_row["norm_zh"])
check(
    "1d. Source Pool 已确认记录不受迁移影响（仍为 True）",
    rec_confirmed_src is not None and rec_confirmed_src.get("human_verified") is True,
    f"rec={rec_confirmed_src}",
)

# ── 导入 router（连带触发 service.py / source_translator.py 真实初始化） ──────
print("\n[setup] 正在导入 features.enhanced_translate.router（会触发 Gemini/Claude 客户端等模块级初始化，可能需要 1 分钟左右）……")
import features.enhanced_translate.router as router  # noqa: E402
import features.enhanced_translate.service as service  # noqa: E402
import features.enhanced_translate.source_translator as source_translator  # noqa: E402
print("[setup] 导入完成")

# ── 仅在本进程内替换外部服务调用，避免依赖真实 ES 连通性 / 消耗真实 Gemini token ──
_original_es_client = service.es_client
_original_gemini_sources_once = source_translator._gemini_sources_once


class _FakeEsClient:
    """替身 ES 客户端：ping 恒为可用，search 恒为空命中，get 恒抛异常（模拟未找到）。
    只影响本进程内 service.es_client 这个名字的指向，不修改任何源文件。"""

    def ping(self, *args, **kwargs):
        return True

    def search(self, *args, **kwargs):
        return {"hits": {"hits": []}, "took": 0}

    def get(self, *args, **kwargs):
        raise Exception("not found (mocked es client, for offline test only)")


async def _fake_gemini_sources_once(infer_tasks, road2_tasks):
    """直接返回空结果，等价于"这次 Gemini 调用什么都没翻出来"——
    调用方（translate_source_zh_batch/en_batch）遇到这种情况本来就有
    "回退到原文、路径标为空"的兜底分支，不会因此崩溃。"""
    return {}, 0.0


service.es_client = _FakeEsClient()
source_translator._gemini_sources_once = _fake_gemini_sources_once
print("[setup] 已将 service.es_client 替换为离线假客户端，source_translator._gemini_sources_once 替换为空结果假函数（仅本进程内生效）\n")


async def scenario_2() -> None:
    print("=" * 78)
    print("场景 2：单行编辑保存完整链路（router.api_update_translation，内容变化）")
    print("=" * 78)
    zh = "基督是我们的生命"
    norm = pool.normalize_zh(zh)
    mtime_before = pool._POOL_FILE.stat().st_mtime

    req = router.UpdateTranslationRequest(
        original_line=zh,
        new_translation="Christ is our life indeed",
        direction="zh2en",
        line_type="reference",
    )
    resp = await router.api_update_translation(req)

    rec_mem = pool._cache_by_norm.get(norm)
    check(
        "2a. 记录内容被更新（内存态）",
        rec_mem is not None and rec_mem.get("en") == "Christ is our life indeed",
        f"rec={rec_mem}",
    )
    check(
        "2b. human_verified 变为 True（内存态）",
        rec_mem is not None and rec_mem.get("human_verified") is True,
        f"rec={rec_mem}",
    )
    check(
        "2c. 响应体带有 human_verified: true",
        resp == {"success": True, "human_verified": True},
        f"resp={resp}",
    )
    mtime_after = pool._POOL_FILE.stat().st_mtime
    check(
        "2d-i. 文件被真实写入（mtime 发生变化）",
        mtime_after != mtime_before,
        f"before={mtime_before} after={mtime_after}",
    )
    # 不能只看内存缓存：用独立的 _load_pool_file() 重新解析磁盘文件
    fresh = pool._load_pool_file()
    rec_disk = fresh.get(norm)
    check(
        "2d-ii. 重新从磁盘加载文件后内容与写入一致（不是只看内存状态）",
        rec_disk is not None
        and rec_disk.get("en") == "Christ is our life indeed"
        and rec_disk.get("human_verified") is True,
        f"rec_disk={rec_disk}",
    )


async def scenario_3() -> None:
    print("\n" + "=" * 78)
    print("场景 3：force_confirm 强制确认（内容不变）+ 幂等性")
    print("=" * 78)
    zh = "神是爱"
    norm = pool.normalize_zh(zh)
    old_rec = pool._cache_by_norm.get(norm)
    old_en = old_rec.get("en") if old_rec else None
    check(
        "3-pre. 起始状态: 该记录 human_verified 为 False",
        old_rec is not None and old_rec.get("human_verified") is False,
        f"old_rec={old_rec}",
    )

    req = router.UpdateTranslationRequest(
        original_line=zh,
        new_translation=old_en,  # 与当前内容完全相同
        direction="zh2en",
        line_type="reference",
        force_confirm=True,
    )
    resp = await router.api_update_translation(req)
    rec = pool._cache_by_norm.get(norm)
    check(
        "3a. force_confirm 后 human_verified 变为 True",
        rec is not None and rec.get("human_verified") is True,
        f"rec={rec}",
    )
    check(
        "3b. force_confirm 没有意外修改内容本身",
        rec is not None and rec.get("en") == old_en,
        f"rec={rec}",
    )
    check(
        "3c. 响应体正确反映 human_verified: true",
        resp == {"success": True, "human_verified": True},
        f"resp={resp}",
    )

    # 幂等性：对已经是 True 的记录重复同样操作
    mtime_before_idem = pool._POOL_FILE.stat().st_mtime
    req2 = router.UpdateTranslationRequest(
        original_line=zh,
        new_translation=old_en,
        direction="zh2en",
        line_type="reference",
        force_confirm=True,
    )
    resp2 = await router.api_update_translation(req2)
    check(
        "3d. 对已确认记录重复 force_confirm 是幂等的（不报错，结果仍是 True）",
        resp2 == {"success": True, "human_verified": True},
        f"resp2={resp2}",
    )
    mtime_after_idem = pool._POOL_FILE.stat().st_mtime
    check(
        "3e. 幂等分支未触发多余的文件写入（mtime 不变）",
        mtime_before_idem == mtime_after_idem,
        f"before={mtime_before_idem} after={mtime_after_idem}",
    )


async def scenario_4() -> None:
    print("\n" + "=" * 78)
    print("场景 4：单行删除完整链路（router.api_delete_translation）")
    print("=" * 78)
    zh = "神是爱"  # 场景 3 里已确认过，此处验证删除
    norm = pool.normalize_zh(zh)

    req = router.DeleteTranslationRequest(
        original_line=zh, direction="zh2en", line_type="reference"
    )
    resp = await router.api_delete_translation(req)
    check("4a-i. 删除请求返回 success=True", resp.get("success") is True, f"resp={resp}")

    fresh = pool._load_pool_file()
    check(
        "4a-ii. 重新加载磁盘文件后记录真实消失",
        norm not in fresh,
        f"norm={norm} 仍在文件里={norm in fresh}",
    )

    resp2 = await router.api_delete_translation(req)
    check(
        "4b. 再次删除同一条记录返回「未找到」而不是崩溃",
        resp2 == {"success": False, "error": "Additional Pool 中未找到对应条目"},
        f"resp2={resp2}",
    )


async def scenario_5() -> None:
    print("\n" + "=" * 78)
    print("场景 5：source_pool 联动（带出处的正文行，保存/删除时同步处理）")
    print("=" * 78)
    zh_source_key = "创世记生命读经，第一篇"
    original_line = f"神创造万有（{zh_source_key}）"
    new_translation = "God created all things (Life-study of Genesis, Message One)"

    # 主行先放进 Additional Pool，作为一条可编辑保存的记录（初始英文不含出处）
    added, _ = pool.append_records(
        [{"zh": original_line, "en": "God created all things", "source": "enhanced_translate"}]
    )
    check("5-pre. 主行已放入 Additional Pool", added == 1, f"added={added}")

    old_src_rec = pool.get_source_pool_record_by_zh(zh_source_key)
    check(
        "5-pre2. 关联 source_pool 记录预先存在（迁移后 human_verified=False）",
        old_src_rec is not None and old_src_rec.get("human_verified") is False,
        f"old_src_rec={old_src_rec}",
    )

    req = router.UpdateTranslationRequest(
        original_line=original_line,
        new_translation=new_translation,
        direction="zh2en",
        line_type="reference",
    )
    resp = await router.api_update_translation(req)
    check("5a-i. 主行（含出处）保存成功", resp.get("success") is True, f"resp={resp}")

    src_rec = pool.get_source_pool_record_by_zh(zh_source_key)
    check(
        "5a-ii. 联动: source_pool 记录内容随之更新为新出处译文",
        src_rec is not None and src_rec.get("en") == "Life-study of Genesis, Message One",
        f"src_rec={src_rec}",
    )
    check(
        "5a-iii. 联动: source_pool 记录 human_verified 因内容变化被置 True",
        src_rec is not None and src_rec.get("human_verified") is True,
        f"src_rec={src_rec}",
    )
    # 独立复查磁盘，确认不是只在内存里更新了
    pool._source_pool_loaded = False
    pool._load_source_pool()
    src_rec_disk = pool._source_pool_by_norm_zh.get(pool.normalize_zh(zh_source_key))
    check(
        "5a-iv. source_pool 联动更新也被真实写入磁盘",
        src_rec_disk is not None and src_rec_disk.get("en") == "Life-study of Genesis, Message One",
        f"src_rec_disk={src_rec_disk}",
    )

    del_req = router.DeleteTranslationRequest(
        original_line=original_line, direction="zh2en", line_type="reference"
    )
    del_resp = await router.api_delete_translation(del_req)
    check("5b-i. 主行删除成功", del_resp.get("success") is True, f"del_resp={del_resp}")

    src_rec_after = pool.get_source_pool_record_by_zh(zh_source_key)
    check(
        "5b-ii. 联动: 删除主行时，关联的 source_pool 记录也被同步删除",
        src_rec_after is None,
        f"src_rec_after={src_rec_after}",
    )


async def scenario_6() -> None:
    print("\n" + "=" * 78)
    print("场景 6：API 响应透传完整链路（ES/Gemini 均为本进程内假实现，见文件头说明）")
    print("=" * 78)

    # 准备两条 Additional Pool 记录：一条未确认，一条已确认
    pool.append_records(
        [{"zh": "神是爱的源头", "en": "God is the source of love", "source": "enhanced_translate"}]
    )
    pool.reload_pool(force=True)
    existing = dict(pool._cache_by_norm)
    norm_confirmed = pool.normalize_zh("神是灵")
    existing[norm_confirmed] = {
        "zh": "神是灵",
        "en": "God is Spirit",
        "norm_zh": norm_confirmed,
        "source": "enhanced_translate",
        "human_verified": True,
    }
    pool._write_pool(existing)

    content = (
        "神是爱的源头\n"
        "神是灵\n"
        "这是一句完全没有命中任何语料的从未出现过的句子测试标记ZZZ不应该匹配任何东西"
    )
    req = router.RetrieveTestRequest(content=content)
    result = await router.retrieve_test(req)
    refs = result["refs"]
    check("6-0. retrieve_test 正常返回 3 行", len(refs) == 3, f"len(refs)={len(refs)}")

    if len(refs) == 3:
        g0, g1, g2 = refs[0], refs[1], refs[2]
        check(
            "6a. Pool 命中但未确认的行: human_verified == False",
            g0.get("human_verified") is False,
            f"line={g0.get('original_line')} human_verified={g0.get('human_verified')} stats={g0.get('stats')}",
        )
        check(
            "6b. Pool 命中且已确认的行: human_verified == True",
            g1.get("human_verified") is True,
            f"line={g1.get('original_line')} human_verified={g1.get('human_verified')} stats={g1.get('stats')}",
        )
        check(
            "6c-i. 完全无匹配的行: human_verified 这个 key 不存在（不是 null）",
            "human_verified" not in g2,
            f"line={g2.get('original_line')} keys={sorted(g2.keys())} stats={g2.get('stats')}",
        )
    else:
        check("6a. (跳过，因为返回行数不为 3)", False, f"refs={refs}")
        check("6b. (跳过，因为返回行数不为 3)", False, f"refs={refs}")
        check("6c-i. (跳过，因为返回行数不为 3)", False, f"refs={refs}")

    # ES Pool 命中（pool_line=True）分支：直接构造，不依赖真实/假 ES 语料内容是否
    # 恰好命中——目的是验证 _build_line_ref_group 本身的"非 Additional Pool
    # 命中不编造 human_verified"规则。
    g_es = service._build_line_ref_group(
        99,
        "某句 ES Pool 命中示例",
        [],
        line_type="reference",
        gemini_translate="x",
        pool_line=True,
    )
    check(
        "6c-ii. ES Pool 命中（pool_line=True）的行: human_verified 这个 key 也不存在",
        "human_verified" not in g_es,
        f"keys={sorted(g_es.keys())}",
    )

    # 多出处场景：走真实的 translate_source_zh_batch（Gemini 调用已替换为空结果假函数）
    items = [
        (
            0,
            [
                "腓立比书生命读经，第三篇",  # source_pool 命中，human_verified=False
                "希伯来书结晶读经，第七篇",  # source_pool 命中，human_verified=True
                "从未收录过的完全虚构出处示例文本ZZZ999",  # 非 source_pool 命中
            ],
            [],
            False,
        )
    ]
    _results_map, _paths_map, verified_map, _cost = await source_translator.translate_source_zh_batch(items)
    v = verified_map.get(0, [])
    check(
        "6d-i. 多出处 reference_source_human_verified[0] == False（Source Pool 命中未确认）",
        len(v) == 3 and v[0] is False,
        f"verified={v}",
    )
    check(
        "6d-ii. 多出处 reference_source_human_verified[1] == True（Source Pool 命中已确认）",
        len(v) == 3 and v[1] is True,
        f"verified={v}",
    )
    check(
        "6d-iii. 多出处 reference_source_human_verified[2] is None（非 Source Pool 命中）",
        len(v) == 3 and v[2] is None,
        f"verified={v}",
    )


async def scenario_7() -> None:
    print("\n" + "=" * 78)
    print("场景 7：边界情况")
    print("=" * 78)

    # 7a: force_confirm=True 但记录不存在
    before_count = len(pool._cache_by_norm)
    req = router.UpdateTranslationRequest(
        original_line="这条记录压根不存在于任何地方xyz",
        new_translation="this record does not exist anywhere xyz",
        direction="zh2en",
        line_type="reference",
        force_confirm=True,
    )
    resp = await router.api_update_translation(req)
    check(
        "7a-i. force_confirm=True + 记录不存在: 返回失败而不是新建",
        resp == {
            "success": False,
            "error": "Additional Pool 中未找到对应条目，或译文为空",
        },
        f"resp={resp}",
    )
    after_count = len(pool._cache_by_norm)
    check(
        "7a-ii. force_confirm=True + 记录不存在: 确实没有新建任何记录",
        after_count == before_count,
        f"before={before_count} after={after_count}",
    )

    # 7b: .bak 备份机制（pool.jsonl）
    before_content = pool._POOL_FILE.read_text(encoding="utf-8")
    req2 = router.UpdateTranslationRequest(
        original_line="已确认的行",
        new_translation="already confirmed line UPDATED",
        direction="zh2en",
        line_type="reference",
    )
    resp2 = await router.api_update_translation(req2)
    check("7b-i. 触发一次真实写入的保存操作成功", resp2.get("success") is True, f"resp2={resp2}")
    bak_path = pool._POOL_FILE.with_suffix(".jsonl.bak")
    check("7b-ii. pool.jsonl.bak 备份文件存在", bak_path.is_file(), f"bak_path={bak_path}")
    bak_content = bak_path.read_text(encoding="utf-8") if bak_path.is_file() else ""
    check(
        "7b-iii. .bak 内容等于写入前的文件状态",
        bak_content == before_content,
        f"bak_len={len(bak_content)} before_len={len(before_content)}",
    )

    # 7c: .bak 备份机制（source_pool.jsonl）
    before_src_content = pool._SOURCE_POOL_PATH.read_text(encoding="utf-8")
    ok = pool.update_source_pool_record(
        "腓立比书生命读经，第三篇", "Life-study of Philippians, Message Three UPDATED"
    )
    check("7c-i. 触发一次 source_pool 真实写入成功", ok is True, f"ok={ok}")
    src_bak_path = pool._SOURCE_POOL_PATH.with_suffix(".jsonl.bak")
    check("7c-ii. source_pool.jsonl.bak 备份文件存在", src_bak_path.is_file(), f"src_bak_path={src_bak_path}")
    src_bak_content = src_bak_path.read_text(encoding="utf-8") if src_bak_path.is_file() else ""
    check(
        "7c-iii. source_pool .bak 内容等于写入前的文件状态",
        src_bak_content == before_src_content,
        f"bak_len={len(src_bak_content)} before_len={len(before_src_content)}",
    )


async def main() -> None:
    try:
        await scenario_2()
        await scenario_3()
        await scenario_4()
        await scenario_5()
        await scenario_6()
        await scenario_7()
    finally:
        # 恢复被替换的外部依赖，避免影响同一进程里后续可能存在的其他代码
        service.es_client = _original_es_client
        source_translator._gemini_sources_once = _original_gemini_sources_once

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
    print(f"\n临时数据目录（可自行查看写入的 pool.jsonl / .bak 等文件）: {tmpdir}")


if __name__ == "__main__":
    asyncio.run(main())
