# 定向取篇：chunk 序号 / 完整性依据（只读核实）

日期：2026-11-16  
范围：为阶段 2 在线检查 4/5 的「完整性判断」与 map_note 解析差提供出处；不改数据、不放宽标准。

---

## 1. `chunk_index` 起始值与 `chunk_total`

### 1.1 outline_12490 / outline_feasts：**从 1 起，连续到 `chunk_total`**

- `docs/panai4_es/chunks_es_plan.md:198`：单位序号**从 1 起**，与 `chunk_index` 一致（`chunk_id` 后缀 `_c{单位序号}`）。
- 同文档 `:361`：验证清单要求每篇 `chunk_index` / `chunk_total` **从 1 连续到 `chunk_total`，无断号**。
- `qa4/data_prep/es_import.py:108–109,139–140`：mapping 声明 `chunk_index` / `chunk_total` 为 integer（**不规定起始值**；起始值依据在切块方案，不在 import 脚本）。
- `qa4/docs/es_import_scripts_report.md`：对照 import mapping，**未另写起始值口径**。

**结论**：纲目 / 节期纲目定向完整性应按 **`orders_base=1`，期望集合 `{1..chunk_total}`**。旧实现用 `range(expected)`（0..n-1）会把正常篇误判为不连续。

### 1.2 hymns：整首 `_c0` / `chunk_index=0`；节从 1 起

- `docs/panai4_es/hymns_index.md:86`：`chunk_id = gmhymns_{sha1…}_c{chunk_index}`，并写明 **`_c0`=整首**。
- `qa4/backend/config/retrieval.json`：`hymns.full_chunk_index = 0`（取全文时 term 该序号）。
- 假数据 `tests/fixtures/fake_passages.json`：大本第 1 首 `full` 为 `chunk_index=0`，`stanza` 为 `1`，`chunk_total=2`。

**「诗歌 `chunk_total` 可能与实际相差 1」**：在 `qa4/notes`、`qa4/docs`、`docs/panai4_es` 内**未找到**明确写成「相差 1」的段落。【待核实】可能来自「`chunk_total` 是否计入 full(0)」的口径歧义；定向通道只取 `full_chunk_index=0` 一块，**不依赖** `chunk_total` 做取全判断。

### 1.3 bible

- 有 `chunk_index` / `chunk_total`（`es_import.py:162–163`；probe_3 D.3）。定向经文走 `bible_data`，不经该索引的 chunk 序号。

---

## 2. text_* 的 `chunk_id` 构造

出处：`qa4/notes/qa4_backend_build_probe_3.md` D.1–D.2（`d_chunk.json` 抽样，【已确认】）。

| 索引 | 样例 | 规则摘要 |
|------|------|----------|
| text_life | `life_11-6-7` | `life_{卷}-{篇}-{段}`；末段数字为篇内段号 |
| text_cwwl | `cwwl_1998-1-3#1-1807` | `…#{篇}-{段}`；末段数字为段号 |
| text_cwwn | `cwwn_3-15#21-44` | 同上风格 |
| text_others | `others_2-4_30-31` | 末段数字为段号 |

- **无补零**：样例为裸数字（如 `7` 而非 `07`）。
- **常有缺号**：D.2「抽样中段号常有断档（切块跳段/合并），不是 1…N 密铺」→ **不能**把 min..max 空洞当 incomplete。
- **篇内重计**：`life_{卷}-{篇}-{段}` 中段号随篇走；跨篇不共用一段号序列（由格式推断；全量统计【待核实】）。
- **无 `chunk_total` 字段用于取全**：retrieval.json 的 text_* 未配置 `fields.total`；probe_3 D.3 写明继承索引探测样本无 `chunk_index`，`chunk_total` 是否可靠未全量扫。

**结论**：text_* 用 `chunk_id` 末尾数字排序；无总段数时 status=`unknown_total`；仅在「命中被 size 截断」或「同篇末尾数字重复」等可证问题上报 `incomplete`。

---

## 3. 节期组织与 lookups

### 3.1 索引侧

- `outline_feasts` 与 12490 同批切块规则：每篇（`message_number`）独立 `chunk_index` 1..`chunk_total`（chunks_es_plan §5 / §9.1）。
- 一场特会对应一个 `book_title`（特会名）；其下多篇靠 `message_number` 区分（retrieval.json `outline_feasts.fields.message_number`）。

### 3.2 lookups/feasts.json

- 本机 `qa4/data/lookups/feasts.json`：259 条；字段仅 **`year` / `month_code` / `name`**。
- **没有**「每场篇数 / message_count」字段 → 无法从特会表核对「该场应有几篇」。
- 例：1997 年同表有「春季长老训练」「国殇节特会」「安那翰全时间训练」等多场（同年多场 + 全时间均有）。

**结论**：输入仅「年+月码」时必须按 `message_number` **分组**做完整性；把整场所有块混成一条 1..N 序列会误报 incomplete。篇数是否取全：lookups **不能**提供期望篇数；只能按 ES `hits_total==fetched` 确认「索引里该特会名下的块都取到了」。

---

## 4. 诗歌大本 / 补充本号码重叠

- `qa4/notes/qa4_backend_build_probe_4.md:195`：大本与补充本号码重叠 **398**。
- `qa4/data/lookups/hymn_series.json`：`daben_buchong_number_overlap=398`；`default_series=诗歌`；note 写明默认大本靠 **series 字段**。
- 代码：`TargetedFetcher.hymn` 默认 `series = icfg.default_series or "诗歌"`，并 term `series` + `hymn_number` + `full_chunk_index`。

---

## 5. map_note：探测 5 vs 在线检查 4（差异拆开）

| 项 | 探测 5（`probe5/c_verse_norm.py`） | 原 `verify_stage2_live` 检查 4 |
|----|-----------------------------------|--------------------------------|
| 母体 | jsonl 全量可抽取 mid 的列表 | ES `random_score` 直接抽 2000 条 `source_zh` |
| 抽样 | `Random(20261116).sample(map_refs, 2000)` | ES seed 20261116，**未**先滤可抽取 |
| 成功口径 | 对 **mid 经节串** 跑原始 v2.1 | `map_note_key(source_zh)`（包装层） |
| 抽取 | `extract_map_note_ref`：去括号→逗号切→丢「恢复本/圣经」首段与「注N」→取 mid | `map_note_key`：只剥「注N」，整段 body 交给 `parse_refs` |

出处：`c_verse_norm.py:250–273,594–614`；`retrieval/dedupe.py:12–24`；原 live 脚本 `check_map_note`。

**代码上可判断的差因（不必等在线）**：

1. **母体不同**：探测 5 只在「能抽出 mid」的集合上抽；原检查 4 含抽不出 mid / 怪异 `source_zh` 的文档。  
2. **成功定义不同**：探测 5 = v2.1(mid)；检查 4 = 包装层键（须 `parse_refs(body)` 成功；注号可缺省为 0）。  
3. **输入串不同**：mid 已去掉「恢复本圣经」；包装层 body 往往仍含该前缀，可能多失败。

在线需再确认：同一批「可抽取 mid」样本上，v2.1 成功数 vs 包装层成功数各多少、失败样例原因分布。

---

## 6. 旧完整性实现的问题（对照）

- `retrieval/targeted.py` 原 `_check_complete`：注释写「段序须恰为 0..total-1」→ 与纲目 **从 1 起** 冲突。  
- 节期：虽有按 `message_number` 分组调用 `_check_complete`，但各组仍按 0-based；且 live 只看整体 status，未输出 per-message 缺口。  
- text_life：无 total 时仅按 hits 核对；旧测试在「乱序有洞」时仍标 OK——与「常有断档」一致；但截断时标 incomplete 合理。
