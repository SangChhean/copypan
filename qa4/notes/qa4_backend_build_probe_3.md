# qa4 后端构建勘探报告（第三轮）

承接：`qa4/notes/qa4_backend_build_probe.md`、`qa4/notes/qa4_backend_build_probe_2.md`  
约束：只读；本轮未连接 ES / Neo4j / Redis / 各家 API；不输出密钥值。  
额外新文件：`qa4/notes/wenji_volume_table_draft.csv`、`qa4/notes/zui_neizai_133_draft.txt`。

数据主路径（本机）：
- 文集正文：`G:\PanAI4.0专用\qa4_import_src\es\data\`（及同结构数据包目录）
- cwwl 原始 JSONL：`G:\PanAI4.0专用\12490原始JSONL\kg-rag_cwwl.jsonl`（探测时路径存在；控制台编码可能乱码显示）
- 图谱本机副本：`G:\copypan\qa4\data\graph_annotations\`、桌面 `C:\Users\28121\Desktop\可导入资料\`

---

## A. 李常受文集册表

### A.1 book_title 总数与命名格式

**【已确认】** 对 `qa4_text_cwwl` / `panai4_text_cwwl` 数据中 `book_title` 去重统计（探测汇总 `C:\Users\28121\AppData\Local\Temp\qa4_probe3\a_summary.json`，源数据来自 `G:\PanAI4.0专用\` 下 cwwl JSONL）：

- **不同 book_title 总数：1186**

命名格式变体（按探测分类键；均为「李常受文集…」前缀，年份以汉字为主）：

| 变体键 | 条数 | 样例（≤30字） |
|--------|------|----------------|
| 汉字四年+年+第X册汉字 | 884 | 李常受文集一九五七年第二册，召会的… |
| 汉字四年+年+汉字年范围至+第X册汉字 | 232 | 李常受文集一九九四至一九九七年第五册… |
| 第X册汉字+信函与拾遗系列 | 40 | 李常受文集信函与拾遗第三册，享受基督… |
| 汉字四年+年+第X册汉字+信函与拾遗系列 | 12 | 李常受文集信函与拾遗第二册，一九七一年… |
| 汉字四年+年+汉字年范围至+第X册汉字+含卷 | 6 | …一九三二至一九四九年第三册，圣经要道（卷三） |
| 第X册汉字+圣经笔记与诗歌系列 | 6 | 李常受文集圣经笔记与诗歌第三册，圣经笔记 |
| 汉字四年+年+第X册汉字+圣经笔记与诗歌系列 | 3 | …圣经笔记与诗歌第四册，第四部分　诗歌… |
| 汉字四年+年+第X册汉字+上中下册括注 | 2 | …一九七九年第一册，生命信息（下册） |
| 汉字四年+年+第X册汉字+含卷 | 1 | …一九八七年第二册，…新约头八卷书中… |

**【已确认】** 年份写法：探测样本中为**汉字数字 +「年」**（含「至」范围）；**未找到**阿拉伯数字年份作为 `book_title` 主体写法的变体键。  
册写法：**第X册**（汉字册号）为主；另有书名内**（上/下册）**括注、**（卷X）**；**未找到**「第X卷」作为册号主格式、**未找到**无「册」字的标准册号变体键（信函/笔记系列仍带「第X册」）。

出处：`a_summary.json` → `variants`；源：`G:\PanAI4.0专用\` cwwl 数据。

### A.2 year 字段 vs 书名年份；year=0

**【已确认】**

- 同一 `book_title` 可对应多个 `year`（至少 year=0 与正数年并存于同一书下）。
- **year=0：98 条 chunk**，涉及 **8** 个 `book_title`；书名内**均含汉字年份**（如一九六五）。列表见 `a_summary.json` → `year0_books`（例：`李常受文集一九六五年第三册，我们人的灵` years=[0,1965] year0=6）。
- **书名年份与 year 字段不一致：15 个 book_title**（`mismatch_n=15`）：
  - 多数为「信函与拾遗…拾遗」：书名含 1963–1975 等，数据 `year=1998`。
  - 「圣经笔记与诗歌第四册」三部分：书名括号内 1949/1950/1968，数据 `year=1931`。

出处：`a_summary.json` → `year0_books` / `mismatch`。

### A.3 同年多册 / 一册多年 / 同名重复

**【已确认】**

- **同一年下多册/多书名行**：常见。册表草案按「年 + book_title」展开共 **1293** 行；例如 `year_primary=1994` 有 71 行（`wenji_volume_table_draft.csv` 统计）。
- **一册（同一 book_title）跨多年（多个非 0 year）**：`multi_year_books_n=0`（`a_summary.json`）。【已确认】在「非 0 的 year 集合」意义下未发现一 title 跨多年；但存在 **year∈{0, YYYY}** 混存（见 A.2）。
- **同年同册重复 book_title**：草案 CSV 中 `book_title` 重复计数为 **0**。【已确认】

### A.4 与 outline_12490 对齐

**【已确认】**（`a_summary.json`）

| 集合 | 数量 |
|------|------|
| cwwl 唯一李文集 title | 1186 |
| outline 中李文集 title | 1144 |
| 两边都有 | 1037 |
| 仅 cwwl | 149 |
| 仅 outline | 107 |

两边对不上的书名样例（各最多 30；总数如上）：见 `only_cwwl_sample` / `only_outline_sample`（多为章节后缀、繁简「召会/教会」、部分标题用字差异）。

outline 李文集 chunk：探测读 `qa4_import_src\es\data\panai4_outline_12490\chunks_12490_vec.new.json` 得 wenji_chunks≈38943；`year` / `year_end` 均有取值（样例 top 年一致，如 1954）。【已确认】字段存在；**逐书 year 与 year_end 是否恒等**未做全量差分 → 部分细节【推测】多数单年书二者相同。

### A.5 册表草案

**【已确认】** 完整草案 **1293 行**（>200），报告只给汇总；全文：

- `qa4/notes/wenji_volume_table_draft.csv`（UTF-8 **带 BOM**）
- 列：`year_primary,ce_label,book_title,n_cwwl,n_outline,years_cwwl,years_title,year0_chunks`

汇总：`table_rows=1293`；`year_to_nbooks_sample` 见 `a_summary.json`（如 1954→24 行、1963→41 行）。

### A.6 3.0 是否有按文集年份/册检索的代码

**【已确认】有部分，但不是「年代限定过滤」产品能力：**

- 定向通道：把用户说法归一成 `book_keyword`（含中文年份+册），再 `book_title` match（`back_qa/qa/prompts.py:236–257`；`qa_service.py` `_step2_targeted` ~796–934）。
- kg_rag 用 `chunk_id` 抽年份做**重排加权**，非用户年代过滤（`back_mic/backend/kg_rag/kg_rag_service.py:152–178`）。
- ES mapping 有 `year` 整型字段（`kg_rag/scripts/index_to_es_full.py:37`）。

**【未找到】** 按「五十年代 / 1960 年以前」等对 `year` 做 range filter 的检索代码。

### A.7 用户「年代限定」现有处理（不自行设计）

**【已确认】** 仅见定向书名补全规则（`prompts.py:236–257,342–343`）：
- 「1958年」→「一九五八年」；范围例「一九九四至一九九七年」。
- 「必须有年份，无年份则 targeted: null」（同文件 ~257–258；感恩节/冬季训练无年份 → general）。

**【未找到】** 对「五十年代的」「1960年以前的」等说法的专门解析或过滤逻辑（代码/文档检索关键词：五十年代、年以前、year_start、year_end 过滤；`back_qa` 内仅命中上述 prompts 规则）。

---

## B. 4.0 防火墙 76 条

### B.1 条数为 76 的规则文件

**【未找到】** 键为防火墙规则、长度为 76、且含 `title`/`note` 的规则文件。

已搜位置与关键词：
- 仓库：`back_mic/backend/firewall_rules.json` → **63** 条，键 `title`,`note`（本机读入确认）。
- `G:\PanAI4.0专用\`：`firewall` / `防火` / `辩理` 文件名 → **0** 命中。
- 全盘 JSON `len==76` 扫描命中 2 个 `svo76.json`（键 `raw_filename,rel_path,title`，目录图册，**非**防火墙规则）。
- 桌面 `可导入资料`：`【devine_argument】…json` 为 **189** 条（键 `name,content_1`），非 76 规则。

与 63 条关系：**【未找到】** 76 版文件，故无法做「新增/修改/拆分」键名差异对照。现网仓内仅见 63。

### B.2 正文资料（类 firewall.json）76 版

**【已确认】** `back_mic/backend/firewall.json` = **63** 条。  
**【未找到】** 76 条正文版；无法做 title 一一对应。

### B.3 是否已被 qa4 / 应用使用

**【未找到】** qa4 引用 76 条防火墙的代码或配置。  
搜过：`qa4/`、`back_qa`（经 `kg_rag.firewall` 加载 63）、`docs/`、probe_2 记载、产品 md。关键词：`firewall_rules`、`FIREWALL_RULES_VERSION`、`76`、`防火墙`。

### B.4 版本号 / 更新日期

**【已确认】**
- 常量：`FIREWALL_RULES_VERSION = "v1.0"`（`back_shared/version_manifest.py:11`）。
- 本机文件 LastWriteTime：`firewall_rules.json` / `firewall.json` → **2026-06-02**（文件系统）。
- git log 触及这些文件的近期提交含 `2026-11-10`、`2026-04-22` 等（`git log -- back_mic/backend/firewall_rules.json`），**未在提交说明中写「76」**。

**【未找到】** 76 版的版本号或更新日期。

---

## C. 向量一致性（不连服务）

### C.1 模型名出处（原话 ≤30 字）

| 出处 | 原话 |
|------|------|
| `back_shared/embedding_adapter.py:14` | 默认 `qwen/qwen3-embedding-8b` |
| `panai4/outline/gen_embeddings.py:6` | embedding 输入 = text 本身 |
| `panai4/outline/gen_embeddings.py:26` | OpenRouter … qwen3-embedding-8b |
| `panai4/hymns/config.py:42` | OpenRouter qwen3-embedding-8b |
| `panai4/inherit/gen_embeddings.py:297` | profile=kg_rag（qwen3-embedding-8b / 1024） |
| `G:\PanAI4.0专用\…\panai4_hymns\MANIFEST.md` | 模型：`qwen/qwen3-embedding-8b`（OpenRouter） |
| `G:\PanAI4.0专用\qa4_import_src\MANIFEST.json` | `"embedding_dims": 1024`（**无模型名字段**） |
| `qa4/data_prep/es_import.py:51` | `VEC_DIMS = 1024` |

**【已确认】** 生成脚本与 hymns 包 MANIFEST 写明 qwen3-embedding-8b。  
**【需要看服务器才能确认】** 现网 ES 内向量是否确由该默认模型、当时 env 未改写生成。

### C.2 数据记录中的向量字段

**【已确认】**（探测 `d_chunk.json` meta + MANIFEST）

| 索引族 | 向量字段 | 维 | embedding_model 元数据 |
|--------|----------|----|------------------------|
| outline_*/bible/hymns | `embedding` | 1024 | 记录上 **无** `embedding_model`；偶见 `corpus`/`dim` |
| text_*/map_note | JSONL 内常为 `embedding`，导入 ES 为 `text_vector` | 1024 | 同上 |
| pano_catalog | 无向量 | — | — |

样例：`text_cwwl_meta.emb_dim=1024`，`model_keys=["corpus","dim"]`，`has_model_meta` 类字段为 false。

### C.3 入库喂给模型的文本（拼接规则）

**【已确认】**

| 索引 | 规则 | 出处 |
|------|------|------|
| outline_12490 / feasts / bible | `_embed_input` = `record["text"]`，不再拼 message_title | `panai4/outline/gen_embeddings.py:89–91,6` |
| text_life / cwwl / cwwn / others / map_note（inherit） | 渲染后 `text`；profile kg_rag | `panai4/inherit/gen_embeddings.py:297` |
| hymns | `r.get("text") or ""` 批嵌入 | `panai4/hymns/index_to_es.py:186–188` |
| pano_catalog | 无向量 | MANIFEST |

说明：bible 的 `text` 本身已含书名/纲目路径前缀（建块渲染），但 embedding 函数不再额外拼字段。

### C.4 查询侧 3.0 喂给模型的文本

**【已确认】**
- `dense_search(es, rewritten_query, …)`（`qa_service.py:690–691`）。
- `rewritten_query` 来自 Step1；空则回落 `question`（`qa_service.py:592–598`）。
- `get_embedding(query_text)` **无** query instruction 前缀（`back_shared/embedding_adapter.py:34–37`；`retrieval.py:86`）。
- 入库侧亦为纯 `text` → **两侧均无 instruction 前缀，相互对应**（同模型默认前提下）。

扩展检索会用 `f"{rewritten_query} {concept}"`（`qa_service.py:742`）再 dense。【已确认】

### C.5 抽样核对方案（只方案不写代码）

**【推测】**（方法设计；阈值需实测标定）

1. **每索引抽 20 条**（有向量的 9 个；pano 跳过）：分层随机——按 `tokens` 三档（&lt;150 / 150–800 / &gt;800）各抽，不足则合并。
2. **选法**：用本地 JSONL 的 `chunk_id`；避开空 `text`。
3. **核对指标**：
   - 用配置名 `EMBEDDING_KG_MODEL`、`EMBEDDING_KG_DIMS`、`OPENROUTER_*`（**不写值**）对 `text` 重算向量；
   - 与库内向量：余弦相似度、L2、维数是否=`EMBEDDING_KG_DIMS`；
   - 可选：用同 `text` 做 kNN，看 top1 是否回到同一 `chunk_id`。
4. **通过判据（建议先标定）**：
   - 维数 100% 一致；
   - 自相似余弦 **≥ 0.999**（浮点/量化容差；若 ES 存 int8_hnsw，应改为「重算后与本地 float 向量比 ≥0.99，且 kNN top1 命中率 ≥95%」——依据：MANIFEST 写明 `int8_hnsw`，精确 float 逐位相等不可期待）；
   - 失败清单按索引汇总。
5. **配置项名**：`EMBEDDING_KG_MODEL`、`EMBEDDING_KG_DIMS`、`OPENROUTER_API_KEY`、`OPENROUTER_BASE_URL`；ES 索引名/`vector_field` 以 `qa4_import_src/MANIFEST.json` 为准。

---

## D. chunk 编号与段落顺序

### D.1 十索引 chunk_id 格式（样例 ≤30 字）

| 索引 | 样例 | 格式含义 |
|------|------|----------|
| outline_12490 | `gm12490_94c04fd4e0a3_c3` | 前缀+内容哈希+`_c`+chunk_index |
| outline_feasts | `gmfeasts_ee37bc784d90_c1` | 同上 |
| bible | `gmbible_b4b0c8246b10` | 前缀+哈希（无 `_c` 后缀于样例） |
| hymns | `gmhymns_e9d83bf50583_c0` | 前缀+哈希+`_c`+index |
| pano_catalog | `pano_d_2bbdfe4ffc15` | `pano_`+类型+哈希 |
| text_life | `life_11-6-7` | `life_{卷}-{篇}-{段}` |
| text_cwwl | `cwwl_1998-1-3#1-1807` | `cwwl_{年}-{册}-{书}#{篇}-{段}` |
| text_cwwn | `cwwn_3-15#21-44` | `cwwn_{辑}-{册}#{篇}-{段}` |
| text_others | `others_2-4_30-31` | `others_…-{段}` |
| map_note | `map_note_75-1-1_c1` | `map_note_…_c{子块}` |

出处：`d_chunk.json` samples。【已确认】

### D.2 无 chunk_index 的索引：阅读顺序抽样

对象：text_life / text_cwwl / text_cwwn / text_others / map_note。各抽 5 个 `message_key`（`d_chunk.json`）。

**【已确认】** 均可按 **chunk_id 末段数字（及 map_note 的 `_cN`）** 排序对齐原文段序意图；抽样中段号**常有断档**（切块跳段/合并），不是 1…N 密铺。  
判定摘要：**有断档、可排序还原相对阅读顺序**（非「连续无洞」）。

### D.3 「篇的总段数」字段

**【已确认】** mapping/数据中存在 `chunk_total`（如 `qa4/data_prep/es_import.py:109,140,163`；bible 样例 `chunk_total=123`）。  
**【已确认】** life/cwwl 等继承索引探测样本 **无 chunk_index**；是否每条都有可靠 `chunk_total` 需按索引再扫 → 未在本轮对五索引全量计数。  
**【推测】** 有 `chunk_total` 的索引可用「取回数 vs chunk_total」判断篇是否取全；定向通道上限 50（下节）可能截断。

### D.4 3.0 定向通道如何保序

**【已确认】** Step B：`term message_key`，`size=_TARGETED_MAX_PASSAGES`，**请求体无 `sort`**（`qa_service.py:902–934`）。  
返回顺序依赖 ES 默认相关性/_doc，**代码未按 chunk_id / 段号排序**。  
→ **未保证阅读顺序显示**。【已确认】缺口；现网表现【需要看服务器才能确认】。

---

## E. 经文数据与解析

### E.1 文件清单与大小

| 路径 | 大小（字节） |
|------|----------------|
| `back_qa/qa/bible_ref_parser.py` | 16138 |
| `back_qa/qa/bible_service.py` | 12736 |
| `back_qa/bible_data/` 目录（66 个 `*.json` 合计） | 102122657 |

**【已确认】** `bible_data` 格式：每卷一文件；顶层 `book,name_gb,name_big5,name_en,abbr_*,chapters[]`；章 `chapter,verses[]`；节含 `text_gb/big5/en`、`text_*_plain`、`footnotes`、`crossrefs` 等（`43_john.json` 抽样）。  
**【已确认】** 层级：卷→章→节。  
**【已确认】** qa4 圣经索引 `author=恢复本圣经`（chunks 样例）；`panai4/bible/config.py:10` `AUTHOR = "恢复本圣经"`。`bible_data` 含脚注标记，与恢复本配套。【已确认】用途为恢复本经文服务数据。

### E.2 parse_bible_ref 支持写法

**【已确认】** 返回结构（`bible_ref_parser.py:287–296`）：
- verse: `{book, chapter, verse, type:"verse", ref_raw}`
- range: `{book, chapter, verse_start, verse_end, type:"range", ref_raw}`
- chapter: `{book, chapter, type:"chapter", ref_raw}`

| 输入例 | 结构类型 |
|--------|----------|
| 约三16 / 约翰福音3:16 | verse |
| 约3:16-18 / 创一1～16 | range |
| 罗马书八章 / 创世记一章 | chapter |
| John 3:16 / John 3:16-18 | 英文 verse/range |

**【未找到】** 代码对「太五至七」（跨章）的专门 range 模式（现有中文 range 锚定同章节至节）。跨书、纯「第 X 页」、无书卷名等 → 返回 `None`（空串亦然）。

### E.3 import 依赖与复制清单

**【已确认】**
- `bible_ref_parser` → `from back_qa.qa import bible_service`（查卷名表）。
- `bible_service` → `dependencies`、`prompts`、`qa_service` 多个符号（问答流水线）。

复制到 `qa4/backend` 最低连带：
1. `bible_ref_parser.py`、`bible_service.py`（可拆「仅解析+取经文」与「问答 SSE」）。
2. 整目录 `bible_data/`。
3. 若跑完整经文问答：`prompts` 中 `BIBLE_STEP4_*`、`qa_service` 依赖子集、`dependencies` 的 ES/Neo4j getter。  
纯解析+内存取节：**parser + service 的 load/get_verse 部分 + bible_data**，可不依赖 back_mic。【已确认】无 `back_mic` import。

### E.4 qa4_bible chunk_type

**【已确认】** `chunks_bible_vec.json`：`verses` 3625 + `book_outline` 66 = 3691。

抽样（字段名 + text 前 30 字）：
- verses：`chunk_type,text,verse_range,outline_path,author,…` — `出埃及记　十六10～12\n参　蒙引领　十五22～十八27\n　`
- book_outline：同上键 — `创世记\n主题：神创造，撒但败坏，人堕落，耶和华应许拯救\n\n纲`

**【已确认】** `verses` = **经文块**（恢复本正文 + 纲目路径头），**不是**注解专篇；注解在 `bible_data` 的 `footnotes`，不在该 chunk_type 名下。

---

## F. 词表与图谱数据（只读本机）

### F.1 文件路径与结构

| 路径 | 结构 | 条数 |
|------|------|------|
| `G:\copypan\qa4\data\graph_annotations\truth_dictionary_3a3b.json` | list；键 `id,title,content_3a,content_3b` | 2372 |
| `G:\copypan\qa4\data\graph_annotations\organic_advance.json` | list；键 `name,series,stages,content_1…6` | 69 |
| `G:\copypan\back_mic\backend\panai4\data\graph_annotations\` 同上两文件 | 同左 | 同左 |
| `docs/panai4_graph/主恢复真理词典_词条主干枝子映射 (1).json` | list；`name,trunk,branch_directly,branch_indirectly` | 2373 |
| `docs/panai4_graph/主恢复真理词典_标签映射_已校对 (1).json` | dict；值含 `主干分类,主标签,副标签` | 91 顶键 |
| `C:\Users\28121\Desktop\可导入资料\2 特殊标注\【intrinsic_significance】2372词条内在意义分类.json` | `{categories,words}`；word:`no,name,category` | words=2372 |

**【未找到】** `G:\PanAI4.0专用\` 下独立的同名 intrinsic JSON（本轮按文件名/内容检索未列到专用副本；桌面与 qa4/back_mic 有词典类文件）。

### F.2 四档计数与 133 名单

**【已确认】** 桌面 intrinsic 文件 `category` 互斥计数：

| 档 | 条数 | 目标 |
|----|------|------|
| 最内在 | 133 | 133 ✓ |
| 外在 | 1658 | 1658 ✓ |
| 内在 | 497 | 497 ✓ |
| 显出为外在 | 84 | 84 ✓ |
| 合计 | 2372 | 2372 ✓ |

名单已导出：`qa4/notes/zui_neizai_133_draft.txt`（133 行，UTF-8）。

注：产品文档 v0.2 另有「133 / 488 / 1760」口径（`G:\PanAI4.0专用\PanAI_4.0_产品设计_v0.2.md` 附近行）与本文件四档**不同** → 【已确认】存在第二套叙述；本轮以 intrinsic JSON 四档为准。

### F.3 定义类字段统计

本地文件**字段名**与 Neo4j 文档中的 `definition_3a/3b` 不完全同名：

| 来源 | 字段 | 非空 | 中位 | P90 | 最大 |
|------|------|------|------|-----|------|
| 词典 3a3b JSON | content_3a | 2372 | 2267.5 | 4754 | 16323 |
| 同上 | content_3b | 2062 | 1883.5 | 4087 | 17032 |
| 节点一般标注 JSON | definition | （作定义正文；非 definition_3a 名） | — | — | — |
| intrinsic 分类 JSON | category | 2372 | （短标签，非长定义） | | |
| qa4 truth_dictionary | definition_3a/3b/intrinsic_significance | **0**（无此键） | | | |

**【已确认】** 导入文档记载 Neo4j 上 `definition_3a` 非空 2372、`definition_3b` 2062、`intrinsic_significance` 2372（`docs/panai4_graph/import_general_annotation.md:42`）→ 与 content_3a/3b 非空数一致，**属性名在库内不同**。【需要看服务器才能确认】库内字符串是否即 content_* 原文。

### F.4 括号词（8）与 same_as

**【已确认】** 代码硬编码 8 对（外,内）：`inventory_v4_pre.py:69–77`（如 妇人/女人，火湖/地狱…）。  
图谱语义：括号**内**节点属性 `same_as` → 括号**外**名（同文件注释 L67–68；`docs/panai4_graph/delete_old_relations.md` 列出 8 对）。  
本轮读到的 `truth_dictionary_3a3b.json` / intrinsic 分类 JSON：**无 same_as 字段**。【已确认】same_as 在图谱节点/构建脚本侧，不在这两份词表 JSON 里。

---

## G. 其他（构建前风险）

| 项 | 等级 | 说明 |
|----|------|------|
| 防火墙 76 vs 仓内 63 | **高** | 产品若要求 76，本机无文件；不能假装已对齐 |
| 定向通道无 sort | **高** | 取篇后显示顺序可能乱；上限 50 段可能截断长篇 |
| year=0 与信函 year=1998 | **高** | 年代限定若滤 `year` 字段会漏/错；宜用册表+书名年 |
| cwwl vs outline 书名 149+107 不对齐 | **中** | 年代/册 UI 与纲目联动需别名或规范化 |
| 向量模型 env 漂移 | **中** | MANIFEST 多只写 1024；需抽样核对（C.5） |
| int8_hnsw vs float 重算 | **中** | 一致性阈值不能按逐位相等 |
| 查询用 rewritten_query | **中** | 与入库 text 分布不同属预期，但改写质量影响召回 |
| bible_service 紧耦 qa_service | **中** | 复制经文通道需拆依赖或整包搬 |
| 产品文档 133/488/1760 vs JSON 133/1658/497/84 | **中** | 对外口径需选定一版 |
| map_note chunk_id 含 `_cN` | **低** | 排序规则与 life/cwwl 末段数字略有不同 |
| 桌面「可导入资料」非仓库 | **低** | 构建机需约定资料落位，避免只在个人 Desktop |

---

## 附录：本轮新增文件

1. `qa4/notes/qa4_backend_build_probe_3.md`（本报告）
2. `qa4/notes/wenji_volume_table_draft.csv`
3. `qa4/notes/zui_neizai_133_draft.txt`
