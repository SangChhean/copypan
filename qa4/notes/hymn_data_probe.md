# 诗歌数据只读探测报告

日期：2026-11-17  
约束：未改任何业务代码、测试、夹具、源数据；探测脚本仅写在 `qa4/notes/`；CSV/汇总 JSON 写在 `G:\PanAI4.0专用\logs\hymn\`。  
对话与本报告均不贴诗歌全文。

## 数据来源

| 项 | 值 |
|---|---|
| 本地清洗 JSON | `G:\PanAI4.0专用\索引数据\panai4_hymns\02_清洗JSON\chunks_hymns.json` |
| 本地块数 | **9154**（full 1299 + stanza 5836 + chorus 2019） |
| 号码 CSV | `G:\PanAI4.0专用\logs\hymn\hymn_numbers.csv`（1299 首 + 表头） |
| 机读汇总 | `G:\PanAI4.0专用\logs\hymn\hymn_probe_summary.json` |
| 在线 ES | `panai4_hymns` **count=9154**（与本地一致；`http` 可达，`https` 同端口失败） |

系列块数：诗歌 6101 / 诗歌附 30 / 补充本诗歌 3023。

---

## 一、号码清单

### 1.1 各系列首数（整首块）

| series | 首数 | 号码范围 | 连续无缺 |
|---|---:|---|---|
| 诗歌 | **780** | 1..780 | **是** |
| 诗歌附 | **6** | 1..6 | **是** |
| 补充本诗歌 | **513** | 1..1005（有缺） | **否** |

CSV 列：`series, hymn_number, name, 整首块的字数`。

### 1.2 补充本缺号区间（只列区间）

```
38-100
151-200
259-300
350-400
471-500
544-600
630-700
763-800
881-900
931-1000
```

共 **10** 个区间。

### 1.3 补充本 781–1005 实际存在

**115** 首（在 781..1005 闭区间内有号码的整首块数）。

---

## 二、文本结构

### 2.1 整首块是否全文；与节/副歌块关系

- `unit_type=full` 的 `text`：**是整首全文**（诗名行 + 全部诗节/副歌正文）。
- 同 `message_key` 另有 `stanza` / `chorus` 块：各自 `text` = **诗名行 + 该单位正文**。
- 抽样 15 首（诗歌 1–15）：每首其它块正文均可在对应 full 文本中找到（`missing_probe=0`）。结论：**整首块已包含全部节与副歌内容**；节/副歌块是切分副本，不是额外独有正文。
- 建索引说明（`docs/panai4_es/hymns_index.md`）口径：`text = name + \n + content/单位正文`，不含 `reference`。

### 2.2 分隔方式（3 首不同系列，仅字段名 + 每行前 6 字 + 长度）

分隔：**换行**；诗节行首为中文数字 + 全角空格（如 `一　`）；副歌行首 `副　`；部分续行前有普通空格。无空白行作节间分隔（抽样 3 首）。

字段名（三首一致）：  
`category, chunk_id, chunk_index, chunk_total, hymn_number, message_key, name, reference, series, subtitle, text, title, tokens, unit_label, unit_type`

| 样本 | 行预览（prefix6 / len） |
|---|---|
| 诗歌 261 full（4 行） | `诗歌第261`/22；`一　哦来，蒙`/69；` 二　哦来，`/70；` 三　哦来，`/70 |
| 补充本 327 full（2 行） | `补充本诗歌第`/17；`一　主阿！我`/100 |
| 诗歌附 3 full（7 行） | `诗歌附3福音`/12；`一　诸天述说`/77；` 二　创造天`/80；` 三　天地之`/84；` 四　不见之`/78；` 五　奥秘基`/80；` 六　神的神`/79 |

同三首的块切分（仅类型/标签/字数，无正文）：

- 诗歌\|261：full(234) + stanza 一/二/三
- 补充本诗歌\|327：full(118) + stanza 一（单节时 full 与唯一 stanza 同长）
- 诗歌附\|3：full(496) + stanza 一..六

### 2.3 text 开头是否「诗名 + 换行」；诗名是否带编号

- **是**：全部 1299 首 full 的首行 **等于** `name` 字段（`first_eq_name=1299`）。
- 诗名 **带编号**：大本/补充本为「系列第N首　…」；诗歌附为「诗歌附N…」（无「第N首」字样，但仍含数字编号）。

---

## 三、行级统计

### 3.1 按换行拆行（仅 full）

| 指标 | 值 |
|---|---:|
| 总行数 | **9211** |
| 最小长度 | 0 |
| 中位长度 | 41 |
| 最大长度 | 280 |
| 少于 6 字的行 | **8** |

### 3.2 跨诗重复行（规范化：去标点空白）

| 指标 | 值 |
|---|---:|
| 出现在多于 1 首的规范行 | **7** |
| 其中出现在 ≥5 首 | **0** |

出现次数前 10（prefix6 + 出现诗数；不足 10 则全列）：

1. `第一辞` ×3  
2. `第二辞` ×3  
3. `二　主，何希` ×2  
4. `三　你是我的` ×2  
5. `四　但是我心` ×2  
6. `一　速兴起传` ×2  
7. `副　速兴起传` ×2  

### 3.3 标点全集；繁体抽检

**标点字符全集（逐字）**：  
`—` `)` `”` `“` `!` `,` `;` `?` `…` `、` `。` `！` `，` `．` `：` `；` `？` `(`

**繁体抽检**：随机 **200** 首 full；方法：文本中是否出现标记字集合  
`國們為時會過還這對開關長東體業經發點實現應萬與麼於` 中任一字。  
结果：**hit_hymns=0**（该抽样未检出上述繁体倾向标记字；正文以简体为主）。

---

## 四、检索现状

### 4.1 ES `panai4_hymns` 的 `text` 映射（在线核对）

| 项 | 值 |
|---|---|
| count | **9154**（= 本地块数） |
| `text.type` | `text` |
| `text.analyzer` | `ik_max_word` |
| `text.search_analyzer` | `ik_smart` |
| `text.fields`（子字段） | **无**（无字符级/单字/n-gram 子字段） |

属性名：`category, chunk_id, chunk_index, chunk_total, embedding, hymn_number, message_key, name, reference, series, subtitle, text, title, tokens, unit_label, unit_type`。  
（与 `back_mic/backend/panai4/hymns/config.py` 的 `mapping_body()` 一致。）

### 4.2 targeted `hymn(number, series)` 返回结构

源：`qa4/backend/retrieval/targeted.py` + `config/retrieval.json` → `hymns`。

- 过滤：`series` + `hymn_number` + `chunk_index = full_chunk_index(0)` → **只取整首块**。
- 顶层：`TargetedResult` → `status`, `blocks`, `meta`, `kind="诗歌"`。
- `meta`：`series`, `hymn_number`（未命中时另有 `missing`）。
- `blocks[0]` 字段名与顺序（`_block`）：

  1. `index`（逻辑名 `"hymns"`）  
  2. `id`（`_id` 或 `chunk_id`）  
  3. `order`（`chunk_index`）  
  4. `book_title`（回落 `name`）  
  5. `message_title`（回落 `title`）  
  6. `message_number`  
  7. `text`  

（本报告不贴诗歌全文。）

---

## 五、内存匹配可行性

条件：全部 **1299** 首 full 读入内存并规范化；随机 **1000** 个 **8 字**片段做子串匹配。

| 指标 | 值 |
|---|---:|
| 总耗时 | **0.3832 s** |
| 每次耗时 | **0.3832 ms** |
| 命中 1 首 | **981** |
| 命中 2–4 首 | **13** |
| 命中 ≥5 首 | **6** |
| 命中 0 首 | 0 |
| 最大命中诗数 | 12 |
| 平均命中诗数 | 1.067 |

结论：全量内存子串匹配在本机毫秒级可接受；绝大多数片段唯一命中一首。

---

## 产出路径

| 文件 | 路径 |
|---|---|
| 本报告 | `qa4/notes/hymn_data_probe.md` |
| 号码 CSV | `G:\PanAI4.0专用\logs\hymn\hymn_numbers.csv` |
| 汇总 JSON | `G:\PanAI4.0专用\logs\hymn\hymn_probe_summary.json` |
| ES 核对 JSON | `G:\PanAI4.0专用\logs\hymn\hymn_es_check.json` |
