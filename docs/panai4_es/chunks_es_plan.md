# PanAI 4.0 纲目 chunks 与 ES 索引方案

- 版本：v0.2（2026-09-29 修订）
- 范围：把《PanAI 4.0 纲目 docx → 结构化 JSON 转换方案》产出的两份 JSON，切成 chunks、生成向量、建成两个 ES 索引
- 上游：`docs/panai4_es/docx_to_json_plan.md` v0.4，产出 `outline_12490.json`（12,328 篇）、`outline_feasts.json`（2,630 篇）
- 姊妹方案：`docs/panai4_es/bible_index_plan.md`（恢复本圣经索引），两份保持一致的字段命名、chunk_id 规则与向量化配置

### v0.2 相对 v0.1 的修订

| 节 | 修订 | 原因 |
|---|---|---|
| 〇 | **新增总则第 2 条**：块必须自带身份 | 抽样发现块里没有书名与篇题 |
| 三 | **改**：`text` 第一行加书名与篇题 | 同上 |
| 6.2 | **改**：embedding 输入由「篇题 + 换行 + text」改为**直接用 `text`** | 头部行已含篇题，消除「存的和算的不一样」 |
| 6.3 | **新增**：批次并发（4～8 路） | 串行 1,340 批约 89 分钟，并发可降到约 18 分钟 |
| 九 | 验证清单增加头部行与 BM25 书名命中的检查 | 配合上述改动 |
| 十 | **新增**：v0.1 已跑出的 chunks 与向量需按 v0.2 重跑 | 渲染格式变了 |

---

## 〇、总则

**一、chunk_id 只用于唯一标识与相等比较，任何代码都不得解析它。** 所有信息一律从显式字段取（`message_key`、`book_title`、`message_number`、`year`…）。

3.5 有个隐患正在于此：它从 `life_60-12-25` 里切出 `message_key`、篇号、年份，一旦换数据源就崩。4.0 不重复这个做法。这条规矩也意味着：不同索引的 `chunk_id` 格式不一致是无害的。

**二、块必须自带身份。** 每一块的 `text` 第一行写明书名与篇题，生成端拿到就知道出处，不依赖检索层补。理由见 3.2。

---

## 一、范围与产出

| | A 批 | B 批 |
|---|---|---|
| 输入 | `outline_12490.json` | `outline_feasts.json` |
| 篇数 | 12,328 | 2,630 |
| 索引名 | `panai4_outline_12490` | `panai4_outline_feasts` |
| chunk 数（v0.1 实测） | 55,841 | 11,110 |

**产出物**

| 文件 | 内容 |
|---|---|
| `chunks_12490.json` / `chunks_feasts.json` | chunks，不含向量，**JSONL：每行一条** |
| `chunks_12490_vec.json` / `chunks_feasts_vec.json` | chunks + 向量，同样 JSONL |
| `chunking_report.md` / `embedding_report.md` / `indexing_report.md` | 三份报告 |

> **所有 `.json` 产出物一律是 JSONL（每行一条）**，不是 JSON 数组。读取时必须逐行解析，**不得 `json.load()` 整个文件**——带向量的那一版约 900 MB，整体加载会吃爆内存。

分三步、三份报告，是为了每一步都能单独验证、单独重跑。chunks 先落地成不带向量的版本，向量单独一步生成，互不牵连。

---

## 二、切块规则

### 2.1 分组

**切块单位 = 一个分组点 + 其后直到下一个同级分组点之前的全部下属点。**
**分组基准 = 本篇 `stats.min_level`**，不是固定的第 1 级。

理由见转换方案 3.4 节：A 批有 622 篇整篇没有第 1 级点（《新约总论》续篇、《福音题纲》等），固定按第 1 级分组会让它们产出 0 个 chunk。

### 2.2 残留点

排在本篇首个分组点**之前**的 points，**并入本篇第一个单位**，不单独成块。实测 A 批 63 篇、867 个点，B 批 0。

### 2.3 不拆不合并

- **不拆超长**：嵌入模型 `qwen/qwen3-embedding-8b` 原生上下文 32,768 token，实测最长单位 A 批 6,436（估算）／7,618（接口实计），余量充足。拆开会切断纲目结构。
- **不合并短块**：一个分组点连同下属就是一个完整的纲目单元。

### 2.4 过滤

`tokens == 0` 的 chunk 不写入 ES。切块阶段照常产出，建索引阶段过滤，并在报告中列出。

### 2.5 验证要求

**两批都不得有任何一篇产出 0 个单位。**

---

## 三、text 的渲染

### 3.1 格式（v0.2 修订）

```
〔第一行〕书名　篇题
〔空行〕
〔纲目正文，每点一行〕
```

- 第一行 = `book_title` + 一个全角空格 + `message_title`；
- 空一行；
- 纲目正文：每个纲目点占一行，行首缩进 = `(本点 level − 本篇 min_level)` 个**全角空格**，label 与正文之间一个全角空格；
- 并入的说明文字（`has_note` 的那些）跟在所属点的正文之后，各占一行，缩进与所属点相同。

例（A 批）：

```
倪柝声文集第一辑第一册，灵修指微　回到十字架罢

壹　罪的结果是与神分开；十字架是我们与神和好的地方—罗三24~25。
　一　于十字架上，基督负我们的罪担，为我们的罪受了刑罚。
　　1　架是救药，不是止痛剂。
```

例（B 批）：

```
2003年夏季训练　新约的众执事和他们的职事

壹　……
　一　……
```

### 3.2 第一行为什么要有书名与篇题

v0.1 的渲染里，块的全文是「壹　罪的结果…／一　于十字架上…」——**没有书名、没有篇题**。这影响两头：

- **检索**：查询里带书名或篇题时，BM25 在 `text` 上匹配不到。靠多字段查询也能解决，但 `book_title` 才十几个字、`text` 两百字，词频权重天差地别，boost 不好调；写进 `text` 行为可预测。
- **生成**：4.0 的约束是「只从 ES 原文库挑段落、按次序拼接成纲目」。生成端拿到二十块材料拼纲目，每块出自哪篇是必须知道的——职事纲目历来带出处。靠检索层在拼装时补，是个「有人记得写、而且一直记得」的约定，一旦漏了就是**静默失败**。
- **排查**：检索结果 dump 出来如果是二十条无名的纲目片段，评估和调参会很难受。

代价是与 `book_title` / `message_title` 字段重复几十个字。值得。

### 3.3 为什么带 label

3.5 的 map 类 chunk 本来就是带编号的——v7 里 `map_note` 的 text 是「壹　奴仆救主…」「一　神在出埃及记…」直接拼起来的，同一套数据、同一个分词器、同一个嵌入模型已经验证过。

带 label 还让生成端直接拿到层级关系：纲目本身有层级，原纲目里的层级关系是现成且准确的，丢掉可惜。

### 3.4 label 在 JSON 里是分离的

转换方案 6.3 节规定 `points[].text` **不含 label 与分隔符**。切块时重新拼回去：`缩进 + label + 全角空格 + text`。

---

## 四、字段清单

两个索引用**完全相同的 mapping**，不适用的字段留 `null`。

| 字段 | 类型 | 来源 | 建索引 |
|---|---|---|---|
| `chunk_id` | keyword | 见第五节，同时作 ES 的 `_id` | 是 |
| `message_key` | keyword | JSON 的 `id`（可读路径） | 是 |
| `source_path` | keyword | `meta.source_path` | 否 |
| `batch` | keyword | `12490` / `feasts` | 是 |
| `text` | text | 第三节渲染结果 | 是（ik） |
| `embedding` | dense_vector | 第六节 | 是（knn） |
| `book_title` | keyword + `.text` 子字段 | 见 4.1 | 是 |
| `book_path` | keyword（数组） | `meta.book_path` 去数字前缀 | 是 |
| `message_title` | keyword + `.text` 子字段 | `meta.title`（篇题） | 是 |
| `message_number` | integer | `meta.msg_no`，无则 `null` | 是 |
| `author` | keyword | 见 4.2 | 是 |
| `year` / `year_end` | integer | 见 4.3 | 是 |
| `paragraph_type` | keyword | 固定 `"outline"` | 是 |
| `tokens` | integer | `len(text) / 1.5` | 是 |
| `min_level` | integer | `stats.min_level` | 是 |
| `point_count` | integer | 本单位含几个纲目点 | 是 |
| `chunk_index` / `chunk_total` | integer | 本篇内第几个单位 / 共几个 | 是 |
| `para_nos` | integer（数组） | 本单位各点在原 docx 的段号 | 否 |
| `part_no` / `part_name` | integer / keyword | 福音题纲的「第N部分」 | 是 |
| `conference` / `month` | keyword / integer | B 批特会与月份 | 是 |

**不要的字段**：`en`、`source_en`、`section_title`、`scripture_refs`、`original_ids`、`source_zh`。

### 4.1 `book_title`

照 3.5 的做法——v7 的职事类 `book_title` 是从 `title` 切出的，册名与书名都留着、用逗号连（如「李常受文集一九六三年第一册，约翰福音精选重点」）。

**A 批规则**：`book_path` 去掉第一层（类别）之后，各层去掉数字前缀、用「，」连接。若去掉第一层后为空，则用第一层本身。另有 `BOOK_TITLE_OVERRIDES` 对照表，覆盖新约总论、真理课程、生命课程三类共 34 个册名。

**B 批规则**：照 3.5 的 `7feasts`——阿拉伯数字年份 + 特会名，如 `2003-04 夏季训练` → `2003年夏季训练`。

### 4.2 `author`

A 批 `category` 为「倪柝声文集」→ `倪柝声`，其余 → `李常受`；B 批 → `null`。

### 4.3 `year` / `year_end`

跨年是职事信息本身的分法，用两个整数表示。B 批从目录名前缀取；A 批李常受文集从册名的中文年份解析（「一九九四至一九九七年」→ 1994 / 1997）；倪柝声文集、生命读经、真理课程、生命课程为 `null`。

### 4.4 为什么不做 `scripture_refs`

3.5 这个字段是脏的（带括号带标点、同一引用重复存、`kg-rag_life` 里 730 个根本不是经文）。而经文引用本就写在 chunk 正文里，BM25 能命中；4.0 的经文检索思路也已改为直接检索经文，不走「锚点经文 → 交集过滤」。**本版不做，连空字段都不留。**

---

## 五、chunk_id 规则

```
chunk_id = {batch前缀}_{sha1(message_key) 的前 12 位十六进制}_c{单位序号}

例：gm12490_a3f19c4d2b81_c1
    gmfeasts_7c2e81f04a39_c3
```

A 批前缀 `gm12490`，B 批 `gmfeasts`；单位序号从 1 起，与 `chunk_index` 一致；同时作 ES 的 `_id`，按 `_id` 覆盖写入即幂等。

### 5.1 为什么用哈希

| 方案 | 第四辑并入时 | 跨索引一致性 | 排查 |
|---|---|---|---|
| 可读路径 | 安全 | 与 3.5 及 4.0 其他索引不一致 | 直接可读 |
| **哈希** | **安全** | **与 3.5 风格一致（短 ASCII）** | 靠 `message_key` |
| 全局序号 | **会被打破**——新书插入后序号平移 | 一致 | 一般 |

2027 年倪文集第四辑要并入，全局序号方案会在那时崩掉。可读路径与哈希都安全，选哈希是因为后续还要建 12490 正文、恢复本经文、map_note 等索引，它们多半沿用 3.5 那种短 ASCII id。排查性由 `message_key` 补上——**所有报告一律列 `message_key`，不列 `chunk_id`**。

### 5.2 硬性约束

> **哈希的输入只能是 `message_key`，不得掺入篇序号、文件总数、日期等任何会变的东西。**

第四辑并入时，新增的篇得到新哈希，原有的篇路径没变、哈希不变、`chunk_id` 不变，按 `_id` 覆盖写入即原地更新。

### 5.3 碰撞与孤儿

12 位十六进制 = 48 位空间，约 1.5 万篇的碰撞概率约百万分之一。切块阶段做**全量唯一性校验**，真撞了立即报错停下。

路径变了哈希就变，旧文档会成为孤儿。建索引脚本要输出「**本次没有被写到的存量文档**」清单，供人工确认是不是误改了文件名。

---

## 六、向量生成

### 6.1 模型与接口

| 项 | 值 |
|---|---|
| 接口 | **OpenRouter** |
| 模型 | `qwen/qwen3-embedding-8b` |
| 维度 | 1024 |
| 环境变量 | `OPENROUTER_API_KEY`、`EMBEDDING_KG_MODEL`、`EMBEDDING_KG_DIMS` |
| 适配层 | `kg_rag/embedding_adapter.py`，`profile="kg_rag"` |

> v7.4 明确记载：旧 `profile="default"`（OpenAI 512 维）**已无调用方，代码保留**。4.0 不使用。

### 6.2 embedding 输入 = `text` 本身（v0.2 修订）

v0.1 设计的是「`message_title` + 换行 + `text`」临时拼接、不落库。v0.2 把书名与篇题写进了 `text` 第一行，**这个拼接就不需要了**。

改成直接用 `text` 的好处是消除了一个不对称：v0.1 里存的内容和算向量的内容不一样，将来谁改了渲染格式而忘了同步拼接逻辑，向量和正文就会悄悄对不上。现在**存什么就算什么**。

### 6.3 批量、并发与容错

- 每批 50 条；
- **并发 4～8 路**（v0.2 新增）。串行 1,340 批、每批约 4 秒，约 89 分钟；5 路并发约 18 分钟。速率限制是按账号算的，触发 429 时由重试退避消化；
- 只对 429 / 5xx / 超时重试，指数退避（1、2、4、8、16 秒，最多 5 次），其余错误记为失败并继续；
- **按 `chunk_id` 增量写入**，中断后重跑只补没有向量的条目，不重复计费；
- 失败条目单独列清单，不静默跳过。

> 跨机并行（本地 + 服务器同时跑）**不建议**：速率限制按账号算，两台机器撞同一个上限；还要切分输入、合并输出，中断更难收拾。单机并发能拿到同样的收益。

### 6.4 正式跑之前先试跑

1. 取 100 条跑通全流程，确认维度 1024、无报错；
2. 单独拿最长的那条试一次，确认 OpenRouter 对单条输入的限制；
3. 两项都过，再跑全量。

**v0.1 的试跑结论**：OpenRouter 接受了最长的一条（9,657 字符，接口实计 7,618 token），未测到拒绝上限。另发现**接口实计 token 比 `len/1.5` 估算高约 15.5%**——用 `tokens` 字段估算上限时要记得乘 1.15。

> 限制：我们只知道上限 ≥7,618 token。2027 年第四辑并入时若出现更长的块，要重新确认一次。

### 6.5 成本与时间

约 6.7 万条、合计约 2,090 万 token（实计）。按 OpenRouter 标价 $0.01/百万 token，全量约 **$0.21**；并发之下约 20 分钟。

---

## 七、建索引

### 7.1 mapping（两个索引相同）

```json
{
  "settings": { "number_of_shards": 1, "number_of_replicas": 0 },
  "mappings": {
    "properties": {
      "chunk_id":    { "type": "keyword" },
      "message_key": { "type": "keyword" },
      "source_path": { "type": "keyword", "index": false },
      "batch":       { "type": "keyword" },

      "text": {
        "type": "text",
        "analyzer": "ik_max_word",
        "search_analyzer": "ik_smart"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 1024,
        "index": true,
        "similarity": "cosine",
        "index_options": { "type": "int8_hnsw" }
      },

      "book_title": {
        "type": "keyword",
        "fields": { "text": { "type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart" } }
      },
      "book_path":  { "type": "keyword" },
      "message_title": {
        "type": "keyword",
        "fields": { "text": { "type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart" } }
      },
      "message_number": { "type": "integer" },
      "author":         { "type": "keyword" },
      "year":           { "type": "integer" },
      "year_end":       { "type": "integer" },
      "paragraph_type": { "type": "keyword" },

      "tokens":       { "type": "integer" },
      "min_level":    { "type": "integer" },
      "point_count":  { "type": "integer" },
      "chunk_index":  { "type": "integer" },
      "chunk_total":  { "type": "integer" },
      "para_nos":     { "type": "integer", "index": false },

      "part_no":    { "type": "integer" },
      "part_name":  { "type": "keyword" },
      "conference": { "type": "keyword" },
      "month":      { "type": "integer" }
    }
  }
}
```

### 7.2 写入

`_id` = `chunk_id`，bulk 每批 200 条；过滤 `tokens == 0` 并列出；写入后核对 `docs.count`。

### 7.3 前置检查

- **本机 ES 磁盘余量**：现有 9 个 `kg-rag_*` 索引已占 7.3 GiB，新增这两个预计再加 1 GB 出头；
- **IK 词典**：已于 2026-09-29 从服务器移植 13 个词典文件（含自定义 `pansearch.dic`），本机分词与 BM25 已与服务器逐位一致。

---

## 八、上传到服务器（两条路，待定）

约 6.7 万条 chunk，带向量后落地约 **800～900 MB**（gzip 后约 400 MB）。

| | 做法 | 优点 | 风险 |
|---|---|---|---|
| **路一** | 本地算好向量，直接往服务器 ES bulk 写入 | 不传文件，走 HTTP 分批，断了能续 | 依赖本机到服务器 9201 的连通与稳定 |
| **路二** | 只传不带向量的 chunks（约 150 MB），服务器上重跑 embedding | 传输轻 | 服务器上再跑一遍 |

v7 曾栽在 SCP 上传只有 ~20 KB/s，所以**倾向路一**。本条待实际文件大小与网速确认后定，选最省事的那条。服务器的 `OPENROUTER_API_KEY` 已确认存在，路二可行。

安全提醒（不属本方案，记录备查）：服务器 ES 的 9201 端口绕过 ufw 对外开放，仅靠密码保护。索引建完后值得单独议一次是否收紧。

---

## 九、验证清单

### 9.1 切块阶段（`chunking_report.md`）

1. **条数对账**：两批各自的篇数、单位数；**没有任何一篇产出 0 个单位**；
2. **唯一性**：`chunk_id` 全局唯一（含跨批），碰撞 0；
3. **完整性**：每篇 `sum(point_count)` = 该篇 `len(points)`，全量一致；
4. **`chunk_index` / `chunk_total`**：每篇从 1 连续到 `chunk_total`，无断号；
5. **头部行（v0.2 新增）**：每块 `text` 的第一行必须等于 `book_title + 全角空格 + message_title`，全量校验，不符者逐条列出；第二行必须为空行；
6. **token 分布**：min / max / avg / median，以及 <150、150～800、>800 三档。因加了头部行，数值会略高于 v0.1，须与 v0.1 并列对照；
7. **`tokens == 0`** 的条目清单；
8. **字段覆盖率**：`book_title`、`message_title` 100%；`author` 在 A 批 100%、B 批全 `null`；`year` 的覆盖率与分布；`part_no` 只出现在福音题纲；`conference` / `month` 只出现在 B 批；
9. **`book_title` 取值清单**：A 批去重后前 50 个及其 chunk 数；B 批**全部**取值及其 chunk 数（核对「2003年夏季训练」这类转换）；
10. **抽样比对**（种子 20260929）：两批各随机抽 10 篇，逐篇列出该篇**全部 chunk 的 `text` 全文**，与 JSON 的 `points` 对照；另单独抽 3 篇《福音题纲》（验证说明文字并入后的渲染）、1 篇《李常受弟兄个人笔记》（该篇应切出约 67 个单位，不是 283）。

### 9.2 向量阶段（`embedding_report.md`）

试跑结果、覆盖率 100%、维度全为 1024、失败清单、重试次数按错误类型分类、实际耗时与成本。

### 9.3 建索引阶段（`indexing_report.md`）

1. 两个索引的 `docs.count` 与输入条数对账；
2. mapping 与 7.1 逐字段比对；
3. **孤儿文档清单**；
4. **BM25 冒烟测试**：「基督作我们的生命」「神的经纶」「召会的建造」各查一次；另加**一个书名查询**（如「福音题纲」）与**一个篇题查询**，专门验证 3.1 的头部行是否生效；
5. **kNN 冒烟测试**：同样的查询；
6. **过滤冒烟测试**：按 `book_title`、`year` 范围、`part_no`、`batch` 各过滤一次；
7. 索引占用大小。

---

## 十、执行顺序

```
① 切块           → chunks_*.json（不含向量）+ chunking_report.md
       ↓ 验证 9.1 通过
② 试跑 embedding → 100 条 + 最长一条
       ↓ 确认 OpenRouter 单条限制
③ 全量 embedding → chunks_*_vec.json + embedding_report.md
       ↓ 验证 9.2 通过
④ 本机建索引     → 两个索引 + indexing_report.md
       ↓ 验证 9.3 通过
⑤ 上服务器       → 第八节两条路择一
```

每一步验证通过再进下一步。

### 10.1 v0.1 已跑出的产物需要重跑（v0.2 新增）

v0.1 已完成①②③（chunks 与全量向量）。因 3.1 的渲染格式改变，**①与③须按 v0.2 重跑**：

1. 先验收 v0.1 的 `embedding_report.md`（覆盖率 100%、失败 0）——这一趟的价值是把 embedding 这一步整条验证了一遍；
2. 改 `build_chunks.py` 的渲染，重跑切块（几分钟）；
3. 重跑 embedding，顺便启用 6.3 的并发（约 20 分钟）。

v0.1 的 chunks 与向量移入带日期的子目录保留，不要覆盖。

---

## 十一、代码位置

```
back_mic/backend/panai4/outline/
├── config.py            # 渲染格式、字段规则、索引名、BOOK_TITLE_OVERRIDES
├── docx_parser.py       # 已有
├── convert_outline.py   # 已有
├── build_chunks.py      # JSON → chunks
├── gen_embeddings.py    # chunks → chunks_vec
├── index_to_es.py       # chunks_vec → ES
└── README.md
```

输出：`C:\Users\28121\Desktop\纲目JSON\`，每轮重跑前把上一版移入带日期的子目录保留。

---

## 十二、待定事项

| 事项 | 状态 |
|---|---|
| 上传服务器走哪条路 | 待实际大小与网速确认（第八节） |
| `pansearch.dic` 是否用 2,372 词条重做 | 待办，影响新索引 BM25 的分词准度 |
| 经文引用的查询端改写 | 正文写「约三16」，查询写「约翰福音3:16」匹配不上；属查询端 |
| 检索端 BM25 多字段 | `text` 为主，`book_title.text`、`message_title.text` 为辅 |
| 时期字段（六期映射） | 本版不加，`year` / `year_end` 可作部分替代 |
| 体裁字段 | 本版不加，待纲目生成场景的按钮取值清单 |
| 服务器 ES 9201 对外开放 | 索引建完后单独议是否收紧 |
| 倪文集第四辑（2027） | 并入时重跑转换与切块即可；哈希方案保证存量 `chunk_id` 不变 |

---

## 十三、工作约定

- 本方案经 Srey 确认后，再写 Cursor 实施指令；指令须附验证步骤；
- 三步分开执行、分开验证、可单独重跑；
- 报告一律列 `message_key`，不列 `chunk_id`；
- 两份源 JSON 与两个 docx 源目录只读；
- 图谱节点上的「属性」一律称「标注」（本方案未涉及）。
