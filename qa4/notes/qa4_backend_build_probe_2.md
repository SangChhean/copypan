# PanAI 4.0 问答站 · 后端构建前只读勘探报告（第二轮）

> 日期：2026-11-13  
> 承接：`qa4/notes/qa4_backend_build_probe.md`  
> 约束：未改既有文件；未 git 写操作；未连接 ES/Neo4j/Redis/外部 API；未读取密钥值。  
> 本机数据包：`G:\PanAI4.0专用\qa4_import_src\es\data\`（统计来源）；样例值均 ≤30 字。  
> 标注：【已确认】/【推测】/【需要看服务器才能确认】；查无则「未找到」。

---

## A. 各索引筛选字段

### A.1 字段名与类型（mapping）

出处：`qa4/data_prep/es_import.py`（OUTLINE / BIBLE / HYMNS / inherit / PANO）。

| 索引 | 书名 | 作者 | 年代 | 来源类别 | 篇/章/节/小节 | 页码 | 首数等 |
|------|------|------|------|----------|---------------|------|--------|
| outline_12490 / outline_feasts | `book_title` keyword+text | `author` keyword | `year`/`year_end` integer | `batch`/`conference`/`part_name` keyword | `message_title` kw+text；`message_number` int；`chunk_index`/`chunk_total` int；`para_nos` int(不索引) | **未找到**页码字段 | — |
| bible | `book_title`；`book_no` int | `author` keyword | **未找到** year | `batch`；`chunk_type` | `message_title`；`verse_range` keyword；`outline_path`/`outline_level` | **未找到** | — |
| hymns | `name`/`title`/`subtitle` kw+text | **未找到** author | **未找到** | `series`/`category` keyword | `unit_type`/`unit_label`；`chunk_index`/`chunk_total` | **未找到** | `hymn_number` integer |
| text_life / text_cwwn / map_note | `book_title` text+keyword | `author` keyword | **未找到**（`inherit_mapping(has_year=False)`，`es_import.py:270–307`） | `corpus`/`source_index` keyword | `message_title`；`message_number`；`section_title`（map_note 无 section） | **未找到** | — |
| text_cwwl | 同上 | 同上 | `year` integer（`has_year=True`，`L277–284`） | 同上 | 同上 + section | **未找到** | — |
| text_others | 同上 | 同上 | mapping **无** year（`has_year=False`，`L293–299`） | 同上 | 同上 | **未找到** | — |
| pano_catalog | `name`/`title`/`raw_name` 等 | **未找到** | **未找到** | `top_category`/`node_type` | `msg_number`/`msg_label`；`depth`/`ordinal_num` | **未找到** | — |

另：inherit 有 `source_zh`/`source_en`/`en`（text，`index:False`）（`es_import.py:185–187`）。

### A.2 本机数据文件统计

统计脚本只读 JSONL（outline/bible/hymns 虽 `.json` 后缀实为 JSONL，`chunks_es_plan.md:48`）。结果固化于本机临时摘要（会话内生成，非仓库文件）。

| 索引 | n | 作者取值 | 年代 | 书名唯一数 |
|------|---|----------|------|------------|
| outline_12490 | 55841 | 李常受 50259；倪柝声 5582（共 2） | int 1932–1994；空 17874（32.01%）；有值时均有 `year_end` | 1334 |
| outline_feasts | 11110 | 全部 `<EMPTY>`（字段存在但空） | int 1997–2026；空 0 | 259（多为「2002年安那翰…」类） |
| bible | 3691 | 仅「恢复本圣经」 | 无 year 字段 | 66（卷名） |
| hymns | 9154 | 无 author 字段 | 无 | `name` 唯一 1299；`hymn_number` 唯一 895；`title` 为类别串 |
| text_life | 39463 | 仅「李常受」 | 无 year | 63（皆「…生命读经」） |
| text_cwwl | 178107 | 仅「李常受」 | int；min 显示 0（**year==0 共 98 条**）；max 1998；空 0 | 1186 |
| text_cwwn | 32032 | 仅「倪柝声」 | 无 year | 106 |
| text_others | 15481 | 仅「李常受」 | 文档中 **无 year 键**（空值比例按「字段不存在」计 100%） | **3**：新约总论 / 真理课程 / 生命课程 |
| map_note | 16052 | 仅「李常受」 | 无 year | 309（「圣经真理题库，…」） |
| pano_catalog | 53151 | 无 author | 无 | `name` 唯一 4776 |

**【已确认】** 作者种类均 ≤60，上表已列全。

### A.3 跨索引写法一致性

**【已确认】**

- 作者：出现处统一为简体「李常受」「倪柝声」，未见繁体异写（数据包字段扫描）。
- 生命读经书名：outline 与 text_life 同形，如「出埃及记生命读经」（outline 有；life 有）。
- 文集书名：outline/cwwl 同形「李常受文集一九五四年第三册，福音题纲」。
- source_zh（正文索引）常带全角括号前缀，如「（李常受文集…，」（kw 样例截断 ≤30 字）。
- **书名号**：数据书名中 **未找到**《》包裹；多为直写书名。
- outline_feasts 的 `book_title` 是训练营名（含西文地名音译），与文集/生命读经命名体系不同。

### A.4 关键词出现位置

| 词 | 出现索引与字段（摘要） | text_others？ |
|----|------------------------|---------------|
| 结晶读经 | outline_12490/`book_title`；text_cwwl/`book_title`+`source_zh`；pano/`top_category`+`path_text` | **未出现**（kw 未命中） |
| 生命读经 | outline_12490/`book_title`；text_life/`book_title`；cwwl 少量标题谈及；pano/`top_category` | **未出现** |
| 李常受 | 多索引 `author` 或 `book_title`/`path_text`/`name` | **是**：`author=李常受`（15481） |
| 倪柝声 | outline/`author`+书名；cwwn/`author`；cwwl 书名含「倪柝声…」；pano path/name | **未出现**（kw 未命中） |

### A.5 text_others

**【已确认】** 作者仅「李常受」；书仅 3 本：新约总论(9392)、真理课程(5397)、生命课程(692)；`corpus=others`。年代字段：**mapping 无 year**（`es_import.py:293–299`），数据 fields_seen 亦无 year → 有年代字段比例 **0%**。

### A.6 outline_12490：12490 vs 12328 vs 55841

**【已确认】** 三者指不同对象，不是互相矛盾的「文档数」：

| 数字 | 含义 | 出处 |
|------|------|------|
| **55,841** | ES/数据包 **chunk 文档数** | `MANIFEST.json` `doc_count`；`es_import.py:238` `expect:55841`；本机文件行数 55841 |
| **12,328** | **篇/message_key 数**（切块前篇数） | 本机 unique `message_key`=12328；`docs/panai4_es/chunks_es_plan.md:36–38`；`docx_to_json_plan.md:50` A 批输出 12328 |
| **12,490** | **语料/目录绰号**（索引名 `outline_12490`），**不是**当前 chunk 数也不是最终篇数 | 索引命名；历史 A 批读入曾近 12509 篇再排除 181→12328（`docx_to_json_plan.md:50`） |

差异来源：**12490≈原料规模绰号；12328=定稿篇数；55841=篇切成纲目单位后的 chunk 数。**

---

## B. 分块与上下文

### B.1 chunk 语义与长度

| 索引 | 一块代表什么 | text 字数中位 / 最大 |
|------|--------------|----------------------|
| outline_* | 一个纲目分组单位（分组点+下属点）（`chunks_es_plan.md:58–59`）；`paragraph_type=outline` | 336 / 9677；feasts 421.5 / 3701 |
| bible | `chunk_type`：verses 3625 + book_outline 66；注解/经文块 | 335 / 5144 |
| hymns | `unit_type`：stanza/chorus/full；一首可多 chunk；`hymn_number` 首号 | 66 / 1313 |
| text_* / map_note | 正文段落块（`paragraph_type=text`，life 全为 text） | life 257/1313；cwwl 279/1303；cwwn 286/1269；others 254/1250；map 377/1255 |
| pano_catalog | 目录树节点（非职事正文 chunk） | 45 / 170 |

### B.2 相邻段落标记

**【已确认】**

- outline/bible/hymns：有 `chunk_index` + `chunk_total` + 同 `message_key` → **可按篇内顺序取邻块**。
- text_* / map_note：有 `message_key`、`message_number`；**本机统计 `chunk_index` 出现次数=0** → 邻段需靠其他字段（如 `original_ids`/`source_zh`）或重新约定；**未找到** `prev`/`next` 字段。
- pano：树路径 `path_text`/`rel_path`/`depth`，非线性邻段。

### B.3 「每个深层词扩展：取 15 精排留 5」

**【已确认】** `back_qa/qa/qa_service.py` `_step2_with_expansion`（`L703–765`）：

- 每 deep 概念：`bm25_search(..., top_k=15)` + `dense_search(..., top_k=15)` → RRF → `rerank(..., top_n=exp_rerank)`，默认 **`expansion_top_n=5`**（`L720–726`）。
- 主路默认精排 Top **20**（`RERANK_TOP_N`，`L112`）。
- 扩展结果按 `chunk_id` 对主路去重后追加（`L752–765`）。

---

## C. 3.0 检索写法

### C.1 BM25

**【已确认】** `back_shared/retrieval.py:29–50`：

- 单字段 `match` on **`text`**，`analyzer: ik_smart`；**无** multi_match / phrase / 字段权重。
- `size` = `top_k`（默认 30，`qa_service.py:109`）。

### C.2 向量

**【已确认】** `retrieval.py:90–97`：

- `knn.field=embedding`；`k=top_k`；`num_candidates` 默认 **100**；**无** filter 子句。
- 索引侧相似度 cosine（qa4 mapping；3.0 查询侧未再写 similarity 参数）。

### C.3 RRF

**【已确认】** `retrieval.py:129–171`：`k` 默认 **60**（`qa_service.py:111` `RRF_K`）；两路全量传入；按 `chunk_id` 累加分数去重合并。

### C.4 精排保留

**【已确认】** 主路：RRF 全量进精排，截断 **top_n=20**；扩展路 **15→精排 5**（见 B.3）。**未找到**「超过某分数阈值才保留」逻辑（Jina 只排序截断）。

### C.5 按作者/年代过滤

**【已确认】** 通用 BM25/Dense **未找到** author/year filter。定向通道只按 `book_title`/`message_key`（`qa_service.py:811–904`），**未**按 author/year 过滤。

### C.6 进入生成的段落字段与引用编号

**【已确认】** `_step4_build_prompt`（`qa_service.py:1007–1050`）：每段拼  
`[来源：{source_zh 清洗或 book_title}]\n{text}`。  
清洗：去掉「，第…段/节」后缀与外层括号（`L1024–1030`）。  
引用编号：模型按 prompt 在正文标数字，书目块 `【引用书目】`；服务端 `_extract_step4_sources` 解析该书目列表（`L1053+`；`prompts.py:111–112`）。**编号由模型生成**，非检索层预编号。

---

## D. 定向类问题

### D.1 3.0 定向类型与解析

**【已确认】** Haiku 预判 `_detect_targeted`（`qa_service.py:372–`）+ 模板 `TARGETED_DETECTION`（`prompts.py:166–`）：

| intent | 解析要点 |
|--------|----------|
| `targeted` | 需 `book_keyword` + `message_keyword`；再 `_step2_targeted` 两步 ES |
| `bible` | `type`=verse/range/chapter + book/chapter/… 数字 |
| `general` | 走完整流水线 |

定向执行：`book_title` match → agg `message_key` → 归一化比篇号 → `term message_key` 取最多 50 段（`qa_service.py:796–934`）。支持索引集合 `_TARGETED_SUPPORTED_INDICES`（`kg-rag_*`，`L769–777`）。

另：路由层经文可用 `parse_bible_ref`（`bible_ref_parser.py`）在 `bible/query`（`bible_router.py:60`）。

### D.2 经文出处识别 / get_vers

| 组件 | 位置 | 与 3.0 QA 关系 |
|------|------|----------------|
| `POST /api/getvers` | `back_mic/.../bible_co/router.py:16–19` → `biblecollection` | **主站经文汇集**，非 QA 流 |
| QA 经文 | `bible_ref_parser.parse_bible_ref` + `bible_service.get_verse*` + Haiku bible intent | **3.0 QA 使用这一套** |
| 「经文出处识别（v2.1）」字样 | **未找到** | — |

**【已确认】** QA 解析可复制到 4.0（独立复制 `bible_ref_parser`/`bible_service`/`bible_data`）；`getvers`/`biblecollection` 是另一条产品线，可选用但不是现 QA 路径。

### D.3 qa4 十索引：定向取数字段建议（只列字段）

| 场景 | 索引 | 建议过滤/定位字段 |
|------|------|-------------------|
| 书名+篇号取生命读经一篇 | `qa4_text_life`（正文）或 `qa4_outline_12490`（纲目） | `book_title` + `message_number` 或 `message_title`；同篇段落用 `message_key` |
| 按节期取纲目一篇 | `qa4_outline_feasts` | `book_title`/`conference`/`year`/`month` + `message_number`/`message_key` |
| 按首数取诗 | `qa4_hymns` | `hymn_number`（+可选 `series`）；同首 `message_key`/`chunk_index` |
| 按经文取注解 | `qa4_bible` | `book_title`/`book_no` + `verse_range`；`chunk_type`；`message_key` |
| 按经文取经文原文 | `qa4_bible`（`chunk_type`/内容区分）或 3.0 式本地 `bible_data` JSON | `verse_range`/`book_no`；或 `bible_service` 卷章节 |

**【推测】** 恢复本「经文原文」若需连续章节文本，本地 `bible_data` 比 ES bible 索引更直接（QA 3.0 已走本地）。

---

## E. 图谱与词表

### E.1 外在/内在/最内在/显出为外在；2380 vs 2372

**【已确认】**

- 档次存在属性 **`intrinsic_significance`**（字符串四选一）（`import_intrinsic_significance.md:4,9,13`；定义说明 `annotation_intrinsic_significance_definitions.md`）。
- 计数：外在 1658、内在 497、最内在 133、显出为外在 84；写入 2372 个无 `same_as` 的节点；括号内 8 个不写该档（`import_intrinsic_significance.md:9–13`）。
- **2380 = 2372 词表拆括号**：8 个「外（内）」各拆成两名 → 2380 节点名（`docs/panai4_graph/reports/source_check.md:92–96`）。
- `same_as`：8 个括号内节点指向括号外（例见 `delete_old_relations.md:222`）。

### E.2 最内在 133 / 其余 2239 名单

**【已确认】** 可读途径：

1. Neo4j：`MATCH (n:Truth_Point) WHERE n.intrinsic_significance = '最内在' RETURN n.name`（思路；本轮**未连库**执行）。
2. 导入源 JSON：报告记载桌面路径 `【intrinsic_significance】2372词条内在意义分类.json`（`import_intrinsic_significance.md:4`）— **仓库内未找到该文件**。
3. 档次定义仅有四类说明 md，**无** 133 名单清单文件。

其余词：2372−133=**2239** 为非「最内在」档（含外在/内在/显出为外在）；对外口径排除括号内 8 后 Truth_Point 期望 2372（`stats_report.py:75–76`）。

### E.3 定义字段

| 字段 | 含义（文档） | 覆盖（dump 基线） |
|------|--------------|-------------------|
| `definition_3a` / `definition_3b` | 词典 3a/3b 定义（`import_general_annotation.md`） | 非空约 2380 / 2070（`server_deploy_dump.md:60–61`） |
| `intrinsic_significance` | 四档分类名 | 2372 |
| `greek_terms` / `hebrew_terms` | 原文 | 2265 / 1527 |
| `name_en` 等 | 英文名等 | 见 dump 表 |

长度：本轮**未**对大 JSON 做全文长度统计（文件在 gitignore / 桌面源）。  
按词名取定义思路：`MATCH (n:Truth_Point {name:$name}) RETURN n.definition_3a, n.definition_3b, n.intrinsic_significance, …`（若命中 `same_as` 内名则先解析到 outer）。

### E.4 同义词 / same_as

**【已确认】** 属性 `same_as`：括号内 → 括号外名；导入分类时合并名规则见 `import_intrinsic_significance.md:11,14`。无通用多别名数组字段 **未找到**（除该 8 对与导入别名表「路得马丁→路德马丁」）。

### E.5 12 大类 / 91 小类

**【已确认】** 文字说明：`docs/panai4_graph/12大类与91小类的对应关系.txt`。  
图谱结构：`BELONGS_TO_TRUNK`→`Trunk`；`OF_BRANCH_DIRECTLY`/`INDIRECTLY`→`Branch`；另有标签映射 JSON：`主恢复真理词典_词条主干枝子映射 (1).json`、`主恢复真理词典_标签映射_已校对 (1).json`。

### E.6 关系是否参与检索；4.0 可用关系

**【已确认】** 3.0：关系**不参与检索召回**，仅 Step1 后拼 `graph_context`「概念关系参考」注入 Step4（`qa_service.py:633–651`）。标签映射仍用旧名 `CONTAINS`/`OPPOSES`/…（`L639–646`），与 4.0 图中 `OPPOSES_CONTRASTS_WITH`/`EXPERIENCES_ENJOYS` 等**不完全同名**。

4.0 可用：34 种关系类型（`server_deploy_dump.md:21–41`）；关系上**无属性**（`import_relations_29.md:4`「关系上无属性」）。扩展词条可走 Truth_Point↔Truth_Point 语义边 + `SUPPORTED_BY`→Scripture。

---

## F. 敏感问题与防火墙

### F.1 存放 / 格式 / 匹配 / 版本

**【已确认】**

- 规则笔记：`back_mic/backend/firewall_rules.json` — **list 长度 63**（非传说中的 76；本仓库计数 63）；元素键 `title`,`note`。
- 正文资料：`back_mic/backend/firewall.json` — list 长度 **63**。
- 加载/匹配：`back_mic/backend/kg_rag/firewall.py`；匹配方式 = **LLM（Sonnet）对标题列表做语义对应**，非关键词/向量（`L22–36,143–208`）。
- 版本常量：`FIREWALL_RULES_VERSION = "v1.0"`（`back_shared/version_manifest.py:11`）。
- 「76 条」：**未找到**与本仓库 `firewall_rules.json` 条数相符的依据。

### F.2 命中后如何进 Step4

**【已确认】** `_run_firewall` 并发后，命中文档经 `FIREWALL_INSTRUCTION` 拼入 Step4 prompt（`prompts.py:148+`；`qa_service.py:1034–1049`）：含 title、note、full_text。

### F.3 可否复用到 4.0

**【已确认】** 可复制 **文件路径与 JSON 格式**（`title`/`note` + `firewall.json` 文档结构）及 `kg_rag/firewall.py` 逻辑；内容是否产品认可另议。注意运行时现依赖 `sys.path` 插入 `back_mic/backend`（`qa_service.py:329–345`）。

---

## G. 模型调用与输出格式

### G.1 固定 JSON 步骤

| 步骤 | 要求 | 解析 | 失败 |
|------|------|------|------|
| 定向预判 | system 要求只输出 JSON | `_safe_parse_json` | 返回 None→降级完整流水线（`qa_service.py:396–399`） |
| Step1 概念 | system 要求 JSON | `_safe_parse_json` | 空概念等降级（见 Step1 返回默认） |
| Step3 相关 | prompt JSON | 解析 relevant | 视为不相关路径 |
| Firewall | JSON `matched` | `_safe_parse_matched_json` | 视为未命中 |

### G.2 anthropic 版本与模型名

**【已确认】** `back_qa/requirements.txt:6` 与 `back_mic/backend/requirements.txt:6`：`anthropic>=0.18.0`（**下限，非钉死精确版**）。  
模型名位置：`qa_service.py:104–106`（STEP1/3/4）；firewall `FIREWALL_MATCH_MODEL`（`firewall.py:39`）；可被 `QA_STEP1_MODEL` 覆盖。  
「该下限是否支持更新模型名」：仓库**未找到**兼容性矩阵 → 【推测】SDK≥0.18 通常可传新 model 字符串，以 Anthropic 侧为准；**【需要看服务器才能确认】** 实装 `pip show anthropic` 版本。

### G.3 caching / system / 温度 / 流式拼接

**【已确认】**

- prompt caching / `cache_control`：**未找到**。
- system：各步有独立 system 字符串（例 Step4 `qa_service.py:1196,1419`）。
- 温度：Step1/定向/Step3=0；Step4=0.3（非 opus-4-7 时）（`L186–187,1426–1427`）。
- 流式：`messages.stream` → `text_stream` 累加 `full_text`，逐 token yield（`L1414–1832`）。

### G.4 `_PRICING` 结构

**【已确认】** `dict[str, tuple[float, float]]`：键=模型名；值=`(input_usd_per_MTok, output_usd_per_MTok)`（`qa_service.py:211–216`）。

---

## H. 并发与性能

### H.1 ES

**【已确认】** 同步 `elasticsearch.Elasticsearch`（`dependencies.py:23–27`）；在 async 中 `asyncio.to_thread(es.search, …)`（例 `retrieval.py:52`；定向 `qa_service.py:827`）。

### H.2 Redis / Neo4j

**【已确认】** Redis：同步 `redis.Redis`（`dependencies.py:31–38`）。Neo4j：同步 `GraphDatabase.driver` + session（`neo4j_client.py:30–35`）。

### H.3 并行

**【已确认】** `asyncio.gather`：BM25∥Dense（`qa_service.py:693`）；主路∥各 deep 扩展（`L745`）；Step1 与 firewall 并发（流水线内，见既有摸底）。4.0 子问题并行可直接借鉴 **create_task + gather + return_exceptions** 模式（`L731–745`）。

### H.4 Python / requirements / 3.10

**【已确认】** 服务器 Python 3.10（`qa4_server_deploy_record.md:14`）。依赖见 `back_mic/backend/requirements.txt` + `back_qa/requirements.txt`。代码使用 `X | Y`、`list[str]` 等 **3.10+** 语法（例 `qa_service.py:211`）→ 与 3.10 **兼容**；**未找到** 仅 3.11+ 语法。

### H.5 日志与 request_id

**【已确认】** `logging.basicConfig(level=INFO, format="%(message)s")`（`main.py:8`）；logger 名 `"qa"`。`request_id` 入参并写入监控/响应（`qa_router.py:151–148`；`_write_monitor`）；**未找到** logging Filter 把 request_id 自动注入每条日志的配置。

---

## I. 前端补充

### I.1 SSE `step` 显示

**【已确认】** `QAPage.vue` 流式循环处理 `verse_data` / `token` / `done` / `error`（约 `L1568–1663`）；**未找到**对 `chunk.type === 'step'` 的分支 → 后端 step 事件**当前被忽略**。  
扩展九步/子问题：需新增 UI 状态机；现结构可加分支，但**不能**「原写法零改」支撑。

### I.2 功能 ↔ 接口 / 密钥依赖

| 功能 | 后端接口 | 密钥/配置（名） |
|------|----------|-----------------|
| 登录/注册 | `/api/qa/auth/*` | `QA_JWT_SECRET` |
| 问答流 | `/api/qa/stream` | `CLAUDE_API_KEY` 等 |
| 翻译 | `/api/qa/translate` | `GEMINI_API_KEY`（英） |
| 朗读 | `/api/qa/tts` `/tts/minimax` `/tts/elevenlabs` | `GEMINI_*` / `MINIMAX_*` / `ELEVENLABS_*` |
| 语音输入 | `/api/qa/asr` | `OPENAI_API_KEY`（+可选 Claude） |
| 反馈 | `/api/qa/feedback` | 无第三方 |
| 管理 | `/api/qa/stats` 等 + `X-Admin-Token` | `QA_ADMIN_TOKEN` |

### I.3 nginx SSE

**【已确认】** `DEPLOY.md` 示例：超时 120s；**未找到** `proxy_buffering off`；**未找到** 后端设置 `X-Accel-Buffering`。  
→ SSE 缓冲问题需在服务器实配中验证（【需要看服务器才能确认】）。

### I.4 构建内存 / 本机构建

**【已确认】** `deploy.sh:42–49` 在服务器 `npm ci` + `npm run build` front_qa。仓库**未找到**构建耗时/内存数字。  
可本机构建上传 `dist`：注意 `deploy.sh` 仍会再 build；且 `git pull`/`stash` 可能影响未跟踪 dist；应用独立 4.0 目录或改脚本跳过 build。服务器内存紧见 `qa4_server_deploy_record.md:15`。

---

## J. 评测与数据版本

### J.1 `scripts/eval_set_v3.json`

**【已确认】** 顶层数组；元素字段：

- `query_id` string  
- `query` string  
- `query_type` string  
- `expected_answer_state` string  
- `gold_chunks` string[]  
- `gold_answer_summary` string  
- `forbidden_concepts` string[]  
- `notes` string  

`gold_chunks` 样例格式：`life_1-1-66`（`{corpus}_{a}-{b}-{c}` 三段数字，**3.5/旧 id 风格**；与 qa4 `chunk_id` 如 `gm12490_…` **不同**）。共 120 题。

### J.2 DATA_MANIFEST 与缓存版本号

**【已确认】** `qa4/docs/DATA_MANIFEST.md`：包名日期 `20261107`、各 zip SHA256、neo4j.dump SHA。  
适合做缓存键的数据版本：`MANIFEST.json` 的 pack 名 + indices 的 doc_count 指纹，或 zip/dump SHA256；应用层可仿 3.0 `PROMPT_VERSION|MODEL_PROFILE|FIREWALL_RULES_VERSION`（`version_manifest.py`）再加 **`DATA_PACK_ID`**。

### J.3 纲目同步重跑环节

**【已确认】** 尚未有「纲目→qa4 单向同步」成品脚本（`qa4_server_deploy_record.md:10,104` 写明未做）。  
若纲目源更新，按装库链需重跑：切块/向量（业务仓 panai4）→ 打包 → `es_import`；图谱则 dump/load。仓库内 qa4 侧：**未找到**增量同步脚本。

---

## K. 其他构建前须知（补充）

1. **高** Firewall 规则数是 **63** 不是 76；产品文档若写 76 需核对来源。  
2. **高** 3.0 关系标签映射与 4.0 关系类型改名不一致，照搬 `rel_labels` 会丢展示。  
3. **高** `text_others` 名不副实：仅总论/课程三类，不含「其他作者」。  
4. **高** `text_cwwl.year==0` 有 98 条，过滤年代时需特殊处理。  
5. **中** outline_feasts `author` 全空，不能按作者筛节期纲目。  
6. **中** 评测 `gold_chunks` 与 qa4 `chunk_id` 体系不兼容，4.0 评测需重标。  
7. **中** 前端忽略 `step` 事件；九步进度需前后端协议重做。  
8. **中** nginx 示例缺 `proxy_buffering off`，SSE 可能被缓冲。  
9. **中** pano 有向量 mapping 字段但导入 `vec_field=None`，勿当正文检索索引。  
10. **低** hymns `series` 含「诗歌」「补充本诗歌」等（控制台编码乱但不影响字段存在）。  
11. **低** `QA_DAILY_LIMIT` env 与 DB `daily_limit` 脱节（上轮已记）。  
12. **高** 定向索引集合仍是 `kg-rag_*`，4.0 必须改写为 `qa4_*` 并适配 `text_vector`/`embedding` 双字段。

---

## 附录：本轮「未找到 / 需看服务器」摘录

**未找到（摘要）：** 页码字段；通用 author/year 过滤；prev/next；prompt caching；X-Accel-Buffering；proxy_buffering off；经文出处识别 v2.1；仓库内 133 词名单文件；76 条防火墙依据；qa4 增量同步脚本；前端 step 处理；钉死 anthropic 精确版本。

**需看服务器：** 实装 anthropic 版本；nginx SSE 实配；本机构建上传流程与磁盘权限；Neo4j 现场查最内在名单（若不用源 JSON）。
