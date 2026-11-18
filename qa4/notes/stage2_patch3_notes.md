# 阶段 2/3 补丁三笔记

日期：2026-11-16  
约束：只改 `qa4/`；未提交；未联网；未读写密钥；未改 `back_*`；未改 `vendor_get_vers_v21.py`。

---

## 一、text_* 段号断档

### 源数据位置（已找到）

| 用途 | 路径 |
|------|------|
| ES 导入源（与线上一致） | `…/es/data/panai4_text_life/shards/*.jsonl`（`es_import.py` `files_glob=shards/*.jsonl`，expect 39463） |
| 同源整文件 | `G:\PanAI4.0专用\12490原文JSONL\kg-rag_life.jsonl`（39463 条，字段同 inherit） |
| 约定默认（脚本） | `QA4_SOURCE_TEXT_*` 或 `qa4/data/es_src/panai4_text_*`（仓库内可空，缺则跳过） |

工具：`qa4/backend/tools/check_text_life_gaps.py`（本机已跑通，OUT 在 logs/stage2）。

### 本机汇总（源 jsonl，非猜）

- **text_life**：1984 篇，**全部有断档**；分布 1–5:30 / 6–20:1346 / 21–50:600 / 51+:8。  
  - 以弗所 life_49-1：35 段，gaps=34（in_original_ids=5，absent=29，merges=3）  
  - 以斯帖 life_17-1：13；罗马 life_45-1：42；约翰 life_43-1：36（同口径）
- **text_cwwl / cwwn / others**：抽样 5 篇均见断档；部分缺口落在 `original_ids`（合并），部分在源中完全不存在。

### 原因与证据（不猜）

1. **切块只保留 `type=="text"`**；heading 只作 `section_title` 查找表，**不产出 chunk**。  
   出处：`back_mic/backend/kg_rag/scripts/chunking_full.py` Pass1 `:441–458`、Pass2 `:570–571`（只读引用，未改该文件）。
2. **空文本跳过**（`:516–517`）→ 原 id 不进入输出，也不进 `original_ids`。
3. **短段合并**：`tokens<150` 并入 buffer，`chunk_id=first.id`，`original_ids` 含被吞 id（`:524–508`）。  
   实证：`life_17-1-3` 的 `original_ids` = `[…-3,-4,-5,-6]`；`life_49-1-7` 吞 `-8`。
4. **源 jsonl 里只有 `paragraph_type=text`**，断档号在源中「无处可寻」的占多数 → **不是导入时丢段，而是源编号本身不连续**（原书/上游 id 含 heading 等）。
5. `source_zh`「第 N 段」与 `chunk_id` 末位数字常差 1（inherit_probe 样例 life_9-34-18 ↔ 第十七段）——末位数字是上游 id，不是密 1…N 顺序号。

**结论**：断档 = **源编号特性**（heading/空段未入库 + 短段合并），**不代表正文在 ES 相对源缺失**。ES 是否与源一致 → 在线检查 8（chunk_id 集合相等）。若检查 8 发现 ES 少段，再标 `possibly_incomplete`；定向取篇 text_* 在无 total 时保持 `unknown_total`，截断/重复时 `possibly_incomplete=true`。

`retrieval.json`：text_life / text_cwwl 的 order 已改为 verified=true，并写明上述依据。

---

## 二、map_note「〇」写法

- 已知失败例：「诗十〇二14」（102 写成「十〇二」）。  
- **规律明确**：`十〇` + 个位汉字 → 应为 `一〇` + 同个位（`十〇二`→`一〇二`）。  
- 已在包装层 `normalize.preprocess_ref_text` 处理（**未改 vendor**）；单元测试覆盖：十〇二 / 一〇二 / 二十三 / 一百〇二。  
- 检查 2/3：图谱与 bible verse_range 此前无此类失败（Srey 在线已过）；全量失败分布见检查 4b（须在线跑）。

---

## 三、辩理 live 源

- 图谱：`Truth_Point.devine_argument`（导入约 187；桌面 JSON 189，丢弃括号词 2 个）。  
- 形态：多为 **JSON 字符串**，对象含 `title` / `description` / `outline`（probe_4/5）。  
- `DevineProvider` live：Neo4j 按名取 → strip 后内容去重 → 上限 `pipeline.json devine_max_items`（默认 2）；括号词经 `same_as` 映到外词。  
- 72 vs 73：以检查 11 的「原样去重 / strip 去重」实数为准，不凑。

---

## 四、在线新检查

| 编号 | 内容 | 汇总标注 |
|------|------|----------|
| 4b | map_note 全量可抽取：v2.1 vs 包装层 | 诊断 |
| 6b | 其余 5 索引向量余弦 | 诊断 |
| 8 | ES vs 源 chunk_id | PASS/FAIL |
| 9 | 作者/年代/冲突/软优先/放宽 | PASS/FAIL（软优先/放宽子项诊断） |
| 10 | fake LLM + live 检索 e2e | PASS/FAIL |
| 11 | 辩理统计 + reverse | 诊断 |

---

## 五、指令外决定

1. 检查 10 用 `/api/qa/ask`（非 SSE）统计结构字段，避免流式解析脆弱；问题只存 sha12+长度。  
2. text_cwwn / text_others 未单独加 order 配置项（定向主路径是 life）；同类断档结论已写入本笔记。  
3. `possibly_incomplete` 仅在 text_* 截断/重复时为 true；源编号断档本身为 false。
