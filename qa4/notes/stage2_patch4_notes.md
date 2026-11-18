# 阶段 2 补丁四：源 vs ES 全量核对

日期：2026-11-16  
约束：只改 `qa4/`；ES 只读；未改 vendor / back_*；未提交；未联网。

---

## 一、导入脚本会不会跳过/丢弃段落

出处：`qa4/data_prep/es_import.py`。

### 会跳过（`row_to_action` 返回 `None`，不进 bulk）

1. **缺 `_id` 字段**：`id_field`（text_* / map_note 为 `chunk_id`）为空 → `:415–417`。  
2. **inherit_jsonl（text_* / map_note）缺合法向量**：`embedding` 或 `text_vector` 不是长度为 1024 的 list → `:428–430`。  
3. **embedding_jsonl（纲目/bible/hymns）同理**：无合法 `embedding` → `:421–423`。  
4. **无**按正文长度过滤；**无**按文本哈希去重；**无**「内容重复则丢」逻辑（全文件检索无 hash(text) / dedup 类分支）。

### `_id` 与重复

- 写入 `_id = chunk_id`（`:424,441`）。同源多行同 `chunk_id` 时 ES **后者覆盖前者**，最终索引文档数 = **唯一 id 数**，不是行数。  
- 导入前用 `count_jsonl` 数**行**与 MANIFEST 比对（`:561–565`）；若行数=期望但唯一 id 更少，导入后 `count` 会对不上并 FAIL（`:614–616`）。

### bulk 失败

- `bulk(..., raise_on_error=False, raise_on_exception=False)`（`:595–601`）。  
- 日志：`bulk_ok` / `bulk_err` / `count` / `expect`；有错时打一条 `sample_error`（`:608–613`）。  
- **无**按条无限重试；失败记入 `errors`，最终 `err_n!=0` 或 `count!=expect` 则该索引 FAIL。

### 是否记录源条数/成功/失败

- **有**：每个索引 `DONE … bulk_ok=… bulk_err=… count=… expect=…`；结束「文档数对照」表（pack vs es）。  
- 本机日志：`G:\PanAI4.0专用\logs\qa4_import_20261109_114630.log`：`qa4_text_cwwl` **bulk_ok=178107 bulk_err=0 count=178107 expect=178107**（与 MANIFEST 一致）。  
- **无**「按册缺失清单」；期望值来自 MANIFEST/包内行数，不是事后对源 id 集合 diff。

### 对「cwwl 某册源 452 / ES 85」的含义（依据层）

导入日志显示当时 **整索引** 行数=ES 数且 bulk_err=0 → 缺口更可能是：  
(A) 当前比对的源与导入时包内容/唯一 id 集合不一致；或  
(B) 同册内缺的 id 在导入包里本就不存在 / 无向量被跳过，同时其它 id 填满了总数；或  
(C) 重复 `_id` 覆盖（需源侧 `chunk_id` 重复统计验证）。  
**(A)(B)(C) 须靠 `analyze_source_dupes` + `check_source_vs_es` 在线结果判定，此处不猜。**

---

## 二、源副本一致性

`qa4_import_src\es\data` vs `数据包\_stage_es\es\data` 下 text_* / map_note 的 `shards/*.jsonl` **逐文件 SHA256**：

| 索引 | files | only_a | only_b | sha_mismatch | 结果 |
|------|-------|--------|--------|--------------|------|
| panai4_text_life | 20/20 | 0 | 0 | 0 | **一致** |
| panai4_text_cwwl | 90/90 | 0 | 0 | 0 | **一致** |
| panai4_text_cwwn | 17/17 | 0 | 0 | 0 | **一致** |
| panai4_text_others | 8/8 | 0 | 0 | 0 | **一致** |
| panai4_map_note | 9/9 | 0 | 0 | 0 | **一致** |

（第三份「索引数据/…/带向量 shards」未做 SHA；任务只要求前两份。）

---

## 三、源侧离线统计（`analyze_source_dupes`）

源根：`G:\PanAI4.0专用\qa4_import_src\es\data`  
OUT：`G:\PanAI4.0专用\logs\stage2\analyze_source_dupes_20261116_215649.json`

| 索引 | 源条数 | 唯一 chunk_id | id 重复多余行 | 同文条数（去空白哈希） | 空文本 | 字数 |
|------|--------|---------------|---------------|------------------------|--------|------|
| text_life | 39463 | 39463 | 0 | 0 | 0 | 20..1313 |
| text_cwwl | 178107 | 178107 | 0 | 22（0.01%） | 0 | 32..1303 |
| text_cwwn | 32032 | 32032 | 0 | 380（1.19%） | 0 | 26..1269 |
| text_others | 15481 | 15481 | 0 | 0 | 0 | 28..1250 |
| map_note | 16052 | 16052 | 0 | 0 | 0 | 50..1255 |

**册 `cwwl_1994-1997-2`：** n=1714（整册，非单篇 452）；unique=1714；**与其它册文本完全相同：0 段**（`cross_volume_same_text_n=0`）。  
另抽查 message_key=`cwwl_1994-1997-2#1`：源 452 段；与其它册同文 0；与同册其它篇同文 0。

结论（离线）：缺段**不能**用「内容重复被导入去重丢弃」解释——导入脚本无文本哈希去重；本册亦无跨册同文；源内无 chunk_id 重复。缺口归因须靠在线 `check_source_vs_es`（ES 实际 id 集合 / 向量跳过等）。

---

## 四、工具

| 工具 | 作用 |
|------|------|
| `analyze_source_dupes.py` | 离线：重复 id、文本哈希、空文本、cwwl_1994-1997-2 跨册同文 |
| `check_source_vs_es.py` | 在线只读：源 id ↔ ES id；按册缺失率；重复型/独有型归因；写出 top3_missing_volumes |

检查 8：可用 `--source-vs-es-json` / `QA4_SOURCE_VS_ES_JSON` 附加缺失率最高前 3 册；无则沿用原样例；FAIL 如实。

---

## 五、小修

- `preprocess_ref_text`：去制表符/多余空白；全角 `：`→`:`；阿拉伯「章:节」→中文章+阿拉伯节（`腓\t1：5`→`腓一5`）。  
- `map_note_invalid_refs.md`：13 条（bible_data 核对章/节上限）。

---

## 六、收尾（补丁四当时）

- 单元测试：**163** OK  
- `verify_stage2.py`：`STAGE2 OFFLINE: ALL PASS`  
- `verify_stage3.py`：`STAGE3 OFFLINE: ALL PASS`  
- 新增文本 CRCRLF：**0**  
- vendor SHA256：仍以 `1A7C164F` 开头、以 `AB75` 结尾（未改文件）  

---

## 七、Srey 全量比对实况（补丁五回填）

五个索引 **source = es、missing=0、extra=0**：

| 索引 | n |
|------|--:|
| text_life | 39463 |
| text_cwwl | 178107 |
| text_cwwn | 32032 |
| text_others | 15481 |
| map_note | 16052 |

随后在自动探测 `outline_12490` 时，`iter_json_rows` 对源 `.json` 做整文件 `json.loads` 触发 `JSONDecodeError: Extra data`（实为 JSON Lines）并崩溃，结果 JSON/md 未写出。补丁五已修：格式自识别、坏行续跑、按索引捕获、增量写 JSON、`--resume-from`。

### 四个探测索引的 id / 文本字段（依据 `es_import.py` INDEX_SPECS）

| 逻辑名 | 源目录/文件（INDEX_SPECS.files） | id_field | 文本字段（mapping） |
|--------|----------------------------------|----------|---------------------|
| outline_12490 | `chunks_12490_vec.new.json` | `chunk_id`（`:240`） | `text`（OUTLINE_MAPPING `:95`） |
| outline_feasts | `chunks_feasts_vec.json` | `chunk_id`（`:248`） | `text` |
| bible | `chunks_bible_vec.json` | `chunk_id`（`:256`） | `text`（BIBLE_MAPPING `:127`） |
| hymns | `chunks_hymns_vec.json` | `chunk_id`（`:264`） | `text`（HYMNS_MAPPING `:165`） |

### 检查 8 假阳性原因（已修）

- 源侧：`chunk_ids_for_message(..., message_key=mk)` 按 **message_key** 取全组（`text_source.py`）。  
- 旧 ES 侧：`stage2_live_patch3.es_ids` 用 **book_title + message_number** term 过滤（原约 `:174–189`，调用约 `:270`）。  
- 实况：`cwwl_1994-1997-2#1` 共 **452** 段、`message_number` 全为 1，但跨 **13** 个不同 `book_title`；取首行 book_title「雅各书结晶读经」只有 **85** 段 → 报源=452 ES=85。  
- 全量比对已证明 text_cwwl id 集合一致，故为脚本假阳性。  
- 修正：ES 侧改为对源 id 清单做 `ids` 查询（每批≤1000）；有 `--source-vs-es-json` 时直接用全量结果判定、不重读源。
