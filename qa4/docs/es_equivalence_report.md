# qa4-es ↔ panai4_* 内容等价报告（C-4 / C-4b / C-4c）

> 依据真实只读运行产物固化结论；**未**在撰写本报告时连接任何 ES、未改容器。  
> **最终全量证据：** `G:\PanAI4.0专用\logs\qa4_verify_20261109_154127.json`（及同名 `.log`/`.md`）  
> **hymns kNN 收尾（判据修改后）：** `G:\PanAI4.0专用\logs\qa4_verify_20261109_161710.json`（仅 hymns，总结果 PASS）  
> 诊断证据：`G:\PanAI4.0专用\logs\qa4_verify_diag_20261109_151150.json`（及同名 `.log`/`.md`）  
> hymns 单独（判据修改前，历史）：`G:\PanAI4.0专用\logs\qa4_verify_20261109_160520.json`  
> 脚本：`qa4/data_prep/es_verify.py`（content 规范化；analyze 探针；kNN 重复向量并列无害）；`es_verify_diag.py`。  
> **收尾结论：** 全部十个索引除 knn「重复向量并列（无害）」判据修改外，无其他放宽。

---

## a. 对照范围与方法

| 项 | 值（来自最终 verify JSON `20261109_154127`） |
|----|------------------------|
| 时间戳 | `20261109_154127` |
| 对照 ES（旧） | `http://127.0.0.1:9200`，`cluster_name=docker-cluster`（容器名惯例为 `elasticsearch8`） |
| qa4 ES（新） | `http://127.0.0.1:9202`，`cluster_name=qa4`（镜像/部署约定为 `qa4-es:8.19.0-ik`，见 `es_infra_report.md`） |
| 索引对数 | 10：`outline_12490` / `outline_feasts` / `bible` / `hymns` / `text_life` / `text_cwwl` / `text_cwwn` / `text_others` / `map_note` / `pano_catalog`（`panai4_*` ↔ `qa4_*`） |
| 总文档数 | `total_count_old=414082`，`total_count_new=414082`，`total_count_ok=true` |
| 总结果（154127） | `ok=false`（当时唯一 FAIL：`hymns.knn`；已由 161710 在新判据下取代，见 §c.3） |

检查项（a–i，与 `es_verify.py` 一致）：

| 代号 | 检查 | 说明 |
|------|------|------|
| a | count | 文档数与期望 |
| b | mapping | mapping 等价（含向量字段） |
| c | settings | analysis / shards / replicas |
| d | ids | `_id` 集合指纹 |
| e | content | `_source`（排除向量；结论以 `normalized_equal` 为准） |
| f | vectors | 向量逐位（大索引抽样） |
| g | knn | 随机样本自检索；重复向量并列可判无害（C-4b） |
| h | bm25 | 固定查询 top-10（含并列无害、相对分数差） |
| i | analyze | `field=text` 与 `analyzer=ik_smart` |

诊断 run `20261109_151150` 对当时 content 指纹差异五索引做全量 diff 分类，并对 hymns knn 失败样本、`outline_12490`/`text_life` 做 stats 探针。

---

## b. 结果表（最终运行 `20261109_154127`）

状态字面量直接取自 `qa4_verify_20261109_154127.json` → `indices.<suffix>.<check>.status`。  
附加数字取自同文件 `detail`（diag / 手工查询已另行标明）。

### b.1 总览矩阵

| suffix | count | mapping | settings | ids | content | vectors | knn | bm25 | analyze |
|--------|-------|---------|----------|-----|---------|---------|-----|------|---------|
| outline_12490 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| outline_feasts | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| bible | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| hymns | PASS | PASS | PASS | PASS | PASS | PASS | FAIL | PASS | PASS |
| text_life | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| text_cwwl | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| text_cwwn | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| text_others | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| map_note | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| pano_catalog | PASS | PASS | PASS | PASS | PASS | SKIP | SKIP | PASS | PASS |

### b.2 count（a）

| suffix | old | new | expect |
|--------|-----|-----|--------|
| outline_12490 | 55841 | 55841 | 55841 |
| outline_feasts | 11110 | 11110 | 11110 |
| bible | 3691 | 3691 | 3691 |
| hymns | 9154 | 9154 | 9154 |
| text_life | 39463 | 39463 | 39463 |
| text_cwwl | 178107 | 178107 | 178107 |
| text_cwwn | 32032 | 32032 | 32032 |
| text_others | 15481 | 15481 | 15481 |
| map_note | 16052 | 16052 | 16052 |
| pano_catalog | 53151 | 53151 | 53151 |

### b.3 settings（c）摘要

十个索引均为 `analysis_equal=true`，`old_shards=new_shards=1`，`old_replicas=new_replicas=0`。

### b.4 ids（d）

十个索引均为 `only_old=0`、`only_new=0`，且 `old_n=new_n`（与 count 一致）。

### b.5 vectors（f）

| suffix | compared | mismatch | full |
|--------|----------|----------|------|
| outline_12490 | 500 | 0 | false |
| outline_feasts | 500 | 0 | false |
| bible | 3691 | 0 | true |
| hymns | 9154 | 0 | true |
| text_life | 500 | 0 | false |
| text_cwwl | 500 | 0 | false |
| text_cwwn | 500 | 0 | false |
| text_others | 500 | 0 | false |
| map_note | 500 | 0 | false |
| pano_catalog | SKIP（无向量字段） | — | — |

### b.6 knn（g）

| suffix | samples | self_top1 | overlap_mean | overlap_min | status |
|--------|---------|-----------|--------------|-------------|--------|
| outline_12490 | 30 | 30 | 9.867 | 9 | PASS |
| outline_feasts | 30 | 30 | 9.933 | 9 | PASS |
| bible | 30 | 30 | 9.9 | 9 | PASS |
| hymns | 30 | 28 | 9.867 | 9 | FAIL† |
| text_life | 30 | 30 | 9.8 | 9 | PASS |
| text_cwwl | 30 | 30 | 9.767 | 8 | PASS |
| text_cwwn | 30 | 30 | 9.867 | 9 | PASS |
| text_others | 30 | 30 | 10.0 | 10 | PASS |
| map_note | 30 | 30 | 9.967 | 9 | PASS |
| pano_catalog | SKIP | — | — | — | SKIP |

> † `hymns` 行数字取自全量 `20261109_154127`（判据修改前 status=FAIL）。同一样本在判据修改后的 `20261109_161710` 为 PASS（`harmless_dup=2`，详见 §c.3）。其余九个索引结论仍以 `20261109_154127` 为准。

### b.7 bm25（h）：每索引 `max(max_rel_score_diff)`

| suffix | status | max_rel_score_diff | tie_harmless_count |
|--------|--------|--------------------|--------------------|
| outline_12490 | PASS | 0.001917 | 0 |
| outline_feasts | PASS | 0.0 | 0 |
| bible | PASS | 0.0 | 0 |
| hymns | PASS | 0.0 | 0 |
| text_life | PASS | 0.034274 | 2 |
| text_cwwl | PASS | 0.0 | 1 |
| text_cwwn | PASS | 0.0 | 0 |
| text_others | PASS | 0.0 | 0 |
| map_note | PASS | 0.0 | 0 |
| pano_catalog | PASS | 0.0 | 0 |

`text_life` 各查询 `max_rel_score_diff`：

| q | max_rel_score_diff |
|---|--------------------|
| 三一神 | 0.006176 |
| 神圣的生命 | 0.004659 |
| 变化与成熟 | 0.00542 |
| 经历基督 | 0.030626 |
| 住在主里面 | 0.018514 |
| 十字架的道路 | 0.002222 |
| 内里的人 | 0.004448 |
| 属灵的争战 | 0.001222 |
| 供应生命 | 0.023874 |
| 与主成为一灵 | 0.034274 |

### b.8 analyze（i）

十个索引均为 PASS。探针句 `神的经纶与基督的身体`（以 hymns 为例）：

- `field:text`：`equal=true`，`old_ik_ok=new_ik_ok=true`；tokens 含 `经纶`/`基督`/`身体`
- `analyzer:ik_smart`：`equal=true`，`old_ik_ok=new_ik_ok=true`；tokens=`['神的经纶', '与', '基督的身体']`

### b.9 content（e）

结论以 `normalized_equal` 为准（该次运行十索引均为 `true` → status PASS）。`raw_*` 为附带记录。

| suffix | status | raw_equal | normalized_equal | raw_mismatch | norm_mismatch |
|--------|--------|-----------|------------------|--------------|---------------|
| outline_12490 | PASS | false | true | 55841 | 0 |
| outline_feasts | PASS | false | true | 11110 | 0 |
| bible | PASS | false | true | 66 | 0 |
| hymns | PASS | false | true | 4690 | 0 |
| text_life | PASS | false | true | 29 | 0 |
| text_cwwl | PASS | true | true | 0 | 0 |
| text_cwwn | PASS | true | true | 0 | 0 |
| text_others | PASS | true | true | 0 | 0 |
| map_note | PASS | true | true | 0 | 0 |
| pano_catalog | PASS | true | true | 0 | 0 |

`raw_equal=false` 的五索引差异种类见 diag（§c.1）：均为顶层 `null_vs_missing`；`still_diff_after_semantic_normalize=0`。

### b.10 历史记录：`20261109_151505`

当时脚本仍用 raw 指纹判 content、且 ik_smart 误要求独立 token `经纶`，故矩阵不同：

| suffix | content | knn | analyze | 其余（count/mapping/settings/ids/vectors/bm25） |
|--------|---------|-----|---------|-----------------------------------------------|
| outline_12490 | FAIL | PASS | FAIL | PASS |
| outline_feasts | FAIL | PASS | FAIL | PASS |
| bible | FAIL | PASS | FAIL | PASS |
| hymns | FAIL | FAIL | FAIL | PASS |
| text_life | FAIL | PASS | FAIL | PASS |
| text_cwwl | PASS | PASS | FAIL | PASS |
| text_cwwn | PASS | PASS | FAIL | PASS |
| text_others | PASS | PASS | FAIL | PASS |
| map_note | PASS | PASS | FAIL | PASS |
| pano_catalog | PASS | SKIP | FAIL | PASS（vectors/knn=SKIP） |

原始文件：`G:\PanAI4.0专用\logs\qa4_verify_20261109_151505.json`。

---

## c. 三条已确认差异及原因

### c.1 顶层 null 键 ↔ 缺键（content 原始指纹）

**现象：** 最终运行 content 以规范化判据为 PASS，但五索引 `raw_equal=false`（`raw_mismatch` 见 b.9）。diag 样本 `field_diffs.kind` 均为 `null_vs_missing`（旧侧显式 `null`，新侧缺键）。

**全量统计（diag `content.*.field_kind_table` / `mismatch_docs`）：**

| suffix | total_docs | mismatch_docs | mismatch_ratio_pct | still_diff_after_semantic_normalize | 字段（kind=null_vs_missing）与 count |
|--------|------------|---------------|--------------------|--------------------------------------|--------------------------------------|
| outline_12490 | 55841 | 55841 | 100.00% | 0 | conference 55841；month 55841；part_name 54255；part_no 54255；year 17874；year_end 17874；message_number 625 |
| outline_feasts | 11110 | 11110 | 100.00% | 0 | author 11110；part_name 11110；part_no 11110 |
| bible | 3691 | 66 | 1.79% | 0 | message_number 66；outline_level 66；verse_range 66 |
| hymns | 9154 | 4690 | 51.23% | 0 | category 3006；reference 2576；unit_label 1299 |
| text_life | 39463 | 29 | 0.07% | 0 | section_title 29 |

**已确认事实与原因：**

1. **数据包里是显式 null（非缺键）。**  
   文件 `qa4_import_src\es\data\panai4_outline_feasts\chunks_feasts_vec.json` 为 JSON Lines（扩展名 `.json`）。Srey 于 2026-11-09 用 `Select-String` 核对：**第 1 行**含 `"author": null`。

2. **qa4 索引里无该键。**  
   verify/diag 对 `qa4_outline_feasts` 的差异种类为 `null_vs_missing`（旧有 `author: null`，新侧 `<missing>`）；diag 计 `author` count=11110（全索引）。

3. **丢弃环节：官方导入脚本 `row_to_action`（非 ES 自行抹键）。**  
   `panai4_outline_feasts` 的 `kind` 为 `embedding_jsonl`。构造 `_source` 时过滤掉值为 `None` 的字段：

   | 脚本 | 路径 | 行号 | 代码 |
   |------|------|------|------|
   | qa4 副本 | `qa4/data_prep/es_import.py` | **411** | `src = {k: v for k, v in row.items() if v is not None}` |
   | 数据包官方原脚本 | `G:\PanAI4.0专用\qa4_import_src\es\import_to_local_es.py` | **379** | `src = {k: v for k, v in row.items() if v is not None}` |

   同函数内 `pano_jsonl` 分支亦有同类过滤（qa4 **435** / 原包 **403**）。  
   `inherit_jsonl` 对 `section_title` 另有显式跳过 null/空串（qa4 **428–429** / 原包 **396–397**），与 `text_life.section_title` 的 29 条一致。

**结论：** 用数据包**官方导入脚本**导入的结果即为「无 null 键」形式；旧 ES（`panai4_*`）是**另一写入路径**保留了显式 null。两边语义内容相同（diag：`still_diff_after_semantic_normalize=0`；最终运行 `norm_mismatch=0`）。

### c.2 BM25 分数相对偏差

**现象（最终 verify `20261109_154127`）：**

- 仅 `text_life`（最大 `max_rel_score_diff=0.034274` ≈ 3.4274%）与 `outline_12490`（最大 `0.001917` ≈ 0.1917%）出现非零相对分数差；
- 其余 8 个索引所有查询 `max_rel_score_diff=0.0`（分数逐位相同）；
- 上述偏差未导致 bm25 FAIL（`exact` 或 `并列排序差异（无害）`，`fail=false`）。

**diag 附加（脚本）：**

- `term_神_match_docs`：`outline_12490` old/new=`34796/34796`；`text_life`=`22808/22808`；
- 脚本内 `_cat` 解析失败，日志为 `deleted=None/None`（不能作为 deleted 计数来源）。

#### 手工只读查询（Srey，2026-11-09 约 15:17）

来源：**手工**对旧 ES / qa4-es 执行 `_cat/indices`（**不是**脚本日志 / diag JSON）。

| 集群 | 索引 | docs.deleted |
|------|------|--------------|
| 旧 ES | `panai4_text_life` | 4976 |
| 旧 ES | `panai4_outline_12490` | 348 |
| 旧 ES | 其余八个 `panai4_*` | 0 |
| qa4-es | 十个 `qa4_*` | 全为 0 |

与分数偏差一致：只有这两个索引有已删除文档，也只有这两个索引有分数偏差。  
（未取得 `_explain` 输出；不声称已被 explain 证实。）

### c.3 hymns kNN：重复向量并列（无害）

**最终状态（`20261109_161710.json`，仅 hymns，总结果 PASS）：**

| 项 | 值 |
|----|-----|
| status | PASS |
| samples | 30 |
| self_top1 | 28 |
| harmless_dup | 2 |
| overlap_mean | 9.867 |
| overlap_min | 9 |
| fail_samples | `[]`（空） |

**无害的 2 个样本（`harmless_samples`）：**

| query_id | 两侧 top1 | both_sides_harmless_dup | 说明 |
|----------|-----------|-------------------------|------|
| gmhymns_6fd3ef75791a_c8 | 旧/新均为 `gmhymns_6fd3ef75791a_c2` | true | 同一首诗歌的 c2；top1 向量与查询向量完全相同 |
| gmhymns_f4e96c267e3d_c8 | 旧/新均为 `gmhymns_f4e96c267e3d_c2` | true | 同一首诗歌的 c2；top1 向量与查询向量完全相同 |

旧 ES 与 qa4 均出现（`both_sides_harmless_dup=true`），故为**数据本身的重复向量**，非导入问题。

**覆盖范围：** 该重跑仅覆盖 `hymns`；其余九个索引的结论仍以 `20261109_154127` 为准。全量 `154127` 中的 `hymns.knn` FAIL 就是本项，已由判据修改后的 `161710` 取代。

**判据修改前对照（历史）：** `154127` / `160520` 均为 `self_top1=28`/`samples=30` → FAIL；diag `20261109_151150` 已确认这两条 `old_top1_vec_equals_query=true` 且旧侧同样非 self-top1。

---

## d. 判定标准与适用范围

**content 相等（以 `normalized_equal` 为准）：**

1. 去掉向量字段（`embedding` / `text_vector`）；
2. 只去掉**顶层**值为 `null` 的键（不递归改嵌套）；
3. 再 `canonical_json` 比较；全部 `_id` 均相等 → PASS；
4. 同时记录 `raw_equal`；**结论只看 `normalized_equal`**。

**knn（C-4b）：**

- top1 为自身 → 通过；
- top1 非自身但 top1 文档向量与查询向量完全相同 →「重复向量并列（无害）」，不计 FAIL；并记录旧 ES / qa4 是否都出现；
- top1 非自身且向量不同 → FAIL；
- 不放宽 overlap 等其他记录项。

**其他：**

- analyze：`field:text` 预期含 `经纶`/`基督`/`身体`；`ik_smart` 预期含 `神的经纶`；
- bm25：同分并列顺序差不计 FAIL。

---

## e. 对后续的影响

1. **读 `_source` 的代码**须容忍缺键：官方导入脚本会丢掉 JSON 中的显式 null；旧 ES 另一路径仍可能保留 null。
2. **将来同步/校验**须沿用同一顶层 null 规范化。
3. **覆盖更新**会产生已删除文档，可能拉偏 BM25；qa4 fresh 导入侧 `docs.deleted=0`（手工核对）。
4. **hymns kNN** 须排除重复向量并列（旧集群同样存在）。
5. **analyze 探针**勿对 ik_smart 要求细粒度子词。

---

## 附录：脚本自测

```text
python qa4/data_prep/es_verify.py --self-test      → exit=0
python qa4/data_prep/es_verify_diag.py --self-test → exit=0
```

hymns kNN 收尾运行：`.\es_verify_run.ps1 -OldUser elastic -Only hymns` → `qa4_verify_20261109_161710.json`（PASS）。
