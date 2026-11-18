# qa4 后端构建勘探报告（第四轮）

承接：`qa4/notes/qa4_backend_build_probe.md`、`_2.md`、`_3.md`  
约束：只读；未连 ES/Neo4j/Redis/API；未读 `.env` 内容。  
额外文件：`qa4/notes/lexicon_reconcile.csv`、`qa4/notes/devine_argument_distinct.csv`（UTF-8 带 BOM）。

背景口径（已定，本报告不论证）：本机开发、独立账号、统一 API 密钥（4.0 自有 env）、日限额 30、追问近 3 轮、缓存键不加数据版本号；词表以四档 2372 + 8 括号词为准。

---

## A. 对话历史（3.0）

### A.1 前端保存 / 请求；后端接收 / 裁剪 / 缓存键

**【已确认】**

- 前端内存 `history`（`ref([])`），每轮结束后 `push({question, answer})` 再 `slice(-3)`（`front_qa/src/components/QAPage.vue:743,1721–1725`）。
- 请求体字段：`history: [{question, answer}, …]`（同文件 `1521–1524`）；后端模型 `HistoryTurn`（`back_qa/qa/qa_router.py:35–37,52`）。
- 后端 Step1 只用最近 3 轮的**问题**（`qa_service.py:513–522`）；Step4 用最近 3 轮问答全文（`_build_history_context`，`979–1000`）。
- 缓存键：`question|hist_ser|PROMPT_VERSION|MODEL_PROFILE|FIREWALL_RULES_VERSION` 的 SHA256（`_make_cache_key`，`235–243`）。**含完整 history JSON**（含 answer）。

### A.2 是否含上一轮回答全文；长答处理

**【已确认】** 前端发送的 `answer` 为助手气泡当前全文（`1721–1724`）；Step4 模板原样嵌入（`prompts.py:86–88`）。  
**【未找到】** 对 history 中 answer 的字数截断逻辑（`_build_history_context` / 前端 push 均无切片）。

### A.3 新对话 / 历史列表 / 刷新

**【已确认】**
- 「+ 新对话」=`window.location.reload()`（`QAPage.vue:837–839`）→ 清空内存态。
- **未找到**独立「历史记录列表」UI（仅当前页 `messages` 气泡）。
- 刷新后：`history`/`messages` 不进 `localStorage`（仅 `qa_username` 等，`741`）→ **不保留**对话。

---

## B. debug 与前端字段

### B.1 后端 debug

**【已确认】** `QueryRequest.debug: bool`、`params: DebugParams`（`bm25_top_k/dense_top_k/expansion_top_n/rerank_top_n`）（`qa_router.py:40–52`）。  
`debug=True` 时结果带 `debug` 对象（targeted/surface/deep/rewritten_query/firewall/step4_prompt/retrieved_chunks 等，`qa_service.py:1368–1378,1545+`）；且 **`if not debug: _write_cache`** → debug **绕过写缓存**（`1379–1380`）。读缓存仍受 `skip_cache` 控制。

### B.2 前端对 done 的 sources / concepts / passages

**【已确认】** done 时赋值 `sources`、`concepts`、`cache_hit`、`elapsed`、`cost` 等（`QAPage.vue:1647–1655`）。  
- **显示**：`sources` →「引用书目」列表（`119–131`）；`concepts` **仅存入消息对象，模板中无渲染**。  
- **`passages`**：**未找到**前端读取 done.passages 的代码。  
- 点击：书目项无跳转/检索，仅展示与复制（`123–130`；`copyAnswer` `1756–1767`）。

### B.3 【引用书目】解析与渲染

**【已确认】**
- 流式：遇「【引用书目】」后截断打字机正文（`1608–1619`）。
- 渲染：`renderAnswer` 去掉书目段落后 markdown，并把引用数字做成 `<sup class="qa-cite-num">`（`841–863`）。
- 正式书目列表用 done 的 `sources` 数组，不用正文内书目块（`displaySources` `874–879`）。

---

## C. 全流程测试台可借鉴模式

**【已确认】** 仓库工作区 **已删除** `back_mic/backend/panai4/{pipeline,runner,db,config,router}.py` 等（见 `docs/panai4_graph/cleanup_stage2.md:130+`）；本机快照仍在：  
`G:\PanAI4.0专用\清理备份\_scripts_snapshot_20261106\`（及 `panai4_backup_20260930_2116\`）。以下出处均指该快照。

### C.1 PANAI4_FAKE_LLM

**【已确认】** `config.fake_llm_enabled()`：`PANAI4_FAKE_LLM=="1"`；可选 `PANAI4_FAKE_DELAY`（快照 `config.py:73–77`）。  
`llm.py`：`fake_llm_enabled()` 时 `asyncio.sleep(delay)` 后返回 `_fake_text(...)`，`model="fake"`，`cost_usd=0`（约 `234–248`）；按 step 分 `_fake_select_text` / `_fake_burden_text` / `_fake_skeleton_text`（`171–221`）。

### C.2 提示词 CURRENT / ENABLED

**【已确认】** 各 `prompts/prompt*.py` 设 `CURRENT = "v…"`；选词另有 `ENABLED = True`（如 `prompt0_select.py:19–21`）。  
回滚方式：改模块内 `CURRENT`/`ENABLED` 指针（`verify_step_c.py` 日志说明约 `497–501`）。模板文件在 `prompts/texts/*_vX.Y.txt`。

### C.3 并发与 SQLite

**【已确认】** `MAX_CONCURRENT_RUNS=3`，可被 `PANAI4_MAX_CONCURRENT_RUNS` 覆盖（`config.py:25–65`）；`runner.py` 按槽位调度。  
`db.py`：`CREATE TABLE` 含 runs / step 明细（含 `cost_usd`）、`topic_sets`、`topic_set_items`、`orig_skeleton_cache` 等（约 `58–196`）；`sqlite3.connect(..., timeout=30)`。

### C.4 verify_step_*.py

**【已确认】** 快照有 `verify_step_b/c/d/ef.py`、`prompts/_verify_step_a.py`：设 FAKE、起 TestClient、poll 状态、断言 step 状态/`cost_usd==0`/CURRENT 哈希等；`log(...)` 打到 stdout（各文件顶部与分段 `===`）。仓库内仅残留 `__pycache__/*.pyc`。

### C.5 与 3.0 `_call_llm` 差异

**【已确认】** 快照 `llm.py`：显式 `TIMEOUT_SECONDS`、`MAX_RETRIES`、可重试异常、费用 `_cost`、FAKE 短路。  
3.0 `_call_llm`（`qa_service.py:171–203`）：`AsyncAnthropic.messages.create`，失败直接 raise，**未见**同文件内重试/超时常量；费用另 `_calc_cost`（`218+`）。

---

## D. 词表对账

来源：
| 代号 | 路径 | 条数 |
|------|------|------|
| (a) | `docs/panai4_graph/2373个词条（已确定一一对应为concept节点）.txt` | 2373 |
| (b) | `docs/panai4_graph/主恢复真理词典_词条主干枝子映射 (1).json` 的 `name` | 2373 |
| (c) | 桌面 `可导入资料/2 特殊标注/【intrinsic_significance】…json` 的 `words[].name` | 2372 |
| (d) | `qa4/data/graph_annotations/truth_dictionary_3a3b.json` 的 `title` | 2372 |
| (e) | **工作区已删**；自 git `1e5e6980:docs/panai4_graph/词条三档分类.json` 恢复统计 | 2381（外在1760+内在488+最内在133） |

**【已确认】** 全量并集写入 `qa4/notes/lexicon_reconcile.csv`（列 `name,in_a…in_e`，UTF-8 BOM）。

两两只在一边（总数；样例≤30 见探测 `d_lexicon.json` / CSV 过滤）：
- a≡b；a\c=2（城市、路德马丁）；c\a=1（路得马丁）；…
- 括号：a/b/c/d 多为**合写**；e 为**外词+内词拆开**（8 对，`inventory_v4_pre.py:69–77` 同序）。
- 「最内在」133：**(c) 与 (e) 集合相同**（`zui_same=True`）。

### D.4 建议（【推测】产品口径）

权威：**以 (c) 四档分类 + 合写括号名（与 a/d 对齐）为准**（共 2372）；图谱侧用 same_as 挂 8 内词。  
需补：路德马丁/路得马丁用字统一；「城市」是否入 4.0；e 的拆词仅作图节点，不作 Step1 主列表。

---

## E. devine_argument

### E.1 位置与结构

**【已确认】** 桌面 JSON：189 条；每条 `name` + `content_1`（**list[dict]**，键恒为 `title,description,outline`）（探测 `e_devine.json`）。  
图谱属性：导入文档记 `devine_argument` 非空约 187（`docs/panai4_graph/import_devine_argument.md` 等）。  
**【需要看服务器才能确认】** 库内 187 与桌面 189/去重 72 的最终对齐。  
**【推测】** 多词条共享同一辩理文，故 189→72。

### E.2–E.3 去重与字数

**【已确认】** 原样去重与去空白去重均为 **72** 份；字数 median **2192.5**，P90 **2666**，max **3856**。  
清单：`qa4/notes/devine_argument_distinct.csv`。

### E.4 结构规律（不贴正文）

**【已确认】** 每份 `content_1[0]` 固定三键：`title`（辩理题）、`description`（一行短说明）、`outline`（字符串提纲）。识别：JSON 对象三字段，而非纯文本分段。

---

## F. 3a 定义文本结构

### F.1 组成与读经行

**【已确认】** `content_3a` 典型：首行「读经：…」+ 纲目体（壹/一　…）（样例见 `truth_dictionary_3a3b.json` 阿爸等；探测 `f_3a.json`）。  
读经识别：行首 `读经`/`讀經` + `：`/`:`；出处以 `，`/`、` 等分隔；经文多用简称+章（汉字/阿拉伯）+节，范围用 `~`。

抽 5 条开头≤30字：见 `f_3a.json` samples（阿爸/阿拉法…）。

### F.2 读经统计

**【已确认】** 有读经行 **2365**/2372；每行出处个数 median **10**（min1 max71）。

### F.3 与 ES book_title

**【已确认】** 正文括注常见「李常受文集一九××年第×册…」（2354 条含文集/生命读经字样）。  
例（≤30字）：
1. `李常受文集一九九一至一九九二年第一册` ↔ cwwl `book_title` 同前缀可 match。  
2. `阿摩司书生命读经` ↔ life/outline 的 `…生命读经`。  
3. 括注过长截断时可能与完整 `book_title` **不完全相等**（需规范化）。【推测】检索应用前缀/归一化而非全等。

---

## G. 经节格式对照

### G.1 五类例子（各≤30字）

| 来源 | 例 |
|------|----|
| 图谱 Scripture `ref` | `可十四36`；`罗八15`；`约壹二15～16`（`import_scripture_nodes.md` / state `chosen`） |
| qa4_bible | `book_title=出埃及记` + `verse_range=十六10～12` |
| bible_data | `book=43` 章3节16 → `ref_gb=约三16` |
| 3a 读经 | `读经：可十四36，罗八15~16，加四6` |
| map_note | 无独立 verse 字段；`source_zh` 如 `（恢复本圣经，可十四24，注1）` |

### G.2 转换规则 / 歧义

**【已确认/推测】** 需：简称↔卷号表；汉字章↔阿拉伯；`～/~` 范围；图谱「不拆范围 ref」vs bible 单节；map_note 从 `source_zh` 抽「书+章+节+注号」。  
歧义：同简称多书、范围一端、繁简「惟/唯」「阿/啊」、注号与经节并存。

### G.3 本机可算匹配

**【已确认】** `logs/import_annotation_scripture_nodes_state.json` 有 `chosen` **4851** refs。用现有 `parse_bible_ref`+`get_verse` 粗测：ok≈1542，parse_fail≈3308（多数中文简称章节未被该解析器吃下，如 `诗八九26`）。  
**【未找到】** 不经解析器、直接按图谱 ref 规范批量对齐 bible_data 的现成脚本结果。  
→ 精确「能在 bible_data 找到的比例」还需专用 ref→(book,ch,vs) 表；差：与图谱一致的解析器或对照表。

---

## H. 诗歌与注解

### H.1 hymns

**【已确认】**（`panai4_hymns/chunks_hymns_vec.json`）

| series | chunks | hymn_number min–max | distinct # |
|--------|--------|---------------------|------------|
| 诗歌 | 6101 | 1–780 | 780 |
| 诗歌附 | 30 | 1–6 | 6 |
| 补充本诗歌 | 3023 | 1–1005 | 513 |

- 大本与补充本 **号码重叠 398** 个（两 series 共有的 `hymn_number`）。  
- **默认大本**应依据字段 **`series=="诗歌"`**（非 number）。【已确认】  
- 需去重原因：`unit_type` 为 `full/stanza/chorus`（1299/5836/2019），同一 `(series,hymn_number)` 多 chunk（pairs>1 = 1299）。结果展示应按 `(series,hymn_number)` 或 `full` 聚合。

### H.2 map_note

**【已确认】** 16052 条；键含 `chunk_id,message_key,book_title,message_title,source_zh,original_ids…`；**无** `note_no` 字段。  
- 去重键建议：`chunk_id`（唯一）；业务「同一注」可用 `source_zh` 或 `original_ids`。【推测】注号在 `source_zh` 文本「注N」或 `chunk_id` 段号。  
- `message_key` 重复多（一篇多注/多 `_cN` 子块，max 单 key 2947 段）。  
- 经节：无结构化 verse 字段；格式在 `source_zh`（恢复本+经节+注号）。

---

## I. 定位字段取值表

### I.1 outline_feasts

**【已确认】** `conference` 形如 `YYYY-MM 名称`；代码取自 **月份映射到 01–09**（样例 `2005-02 春季长老训练`→02）。  
各 code 的 chunk 数：01:585 … 09:1543（`supp2.json`）。  
名称字段：展示名主要在 **`book_title`**（如 `1997年感恩节特会`）；`conference` 含年-月+简称。  
不同 `(code, book_title)` 组合约 **259**（= unique conference 数）。

### I.2 生命读经

**【已确认】** `panai4_text_life`：**63** 个 `book_title`，皆「…生命读经」；篇数=不同 `message_key` 数（如创世记120、出埃及记185…，完整表见探测 `supp2.json`→`life_msgs`）。  
outline_12490 含同名生命读经书；【已确认】名称可对齐；篇数是否逐书一致未做逐项差分 → 细节【需要看服务器/再扫】或【推测】大体一致。

### I.3 cwwn

**【已确认】** **106** 个 `book_title`；前10见探测（如 `倪柝声文集第一辑第一册`…）。  
结构：书名含 **第X辑第Y册**，可做 (辑,册) 查表。【已确认】

### I.4 text_others

**【已确认】** 3 本：`新约总论`（436 个 message_key）、`生命课程`（48）、`真理课程`（218）。新约总论以 `message_key`/`message_number` 篇号组织。

---

## J. 年代表对账

### J.1 来源与复现

**【已确认】** 技术版：`C:\Users\28121\Desktop\PanAI4.0_问答流程设计_技术版_20261111.md:84` 写「42 行（35 单年＋7 区间）；61 个无年份书名（5,551 段）」。  
用 `kg-rag_cwwl.jsonl` 复现：`distinct_year_marks=42`（single35+range7）；`no_year_titles_n=61`；`no_year_chunks=5551` → **与技术版一致**（`j_years.json`）。

### J.2 与第三轮 1293 行册表

**【已确认】** 口径不同：
- 42 行：按书名前缀**年份标记**聚合（筛选轴）。  
- 1293 行：按 **year_primary + 完整 book_title**（书名级册表）。  
差异来自「一年多书/多册」展开。  
**【推测】** 年代筛选用 **42 行年标记**；展示/解释用册表（书名级）。

---

## K. Redis 使用概况

### K.1 各包

| 位置 | DB 默认 | 键前缀 | TTL |
|------|---------|--------|-----|
| `back_qa/dependencies.py:36` | `REDIS_DB` 默认 **0** | `QA_REDIS_PREFIX` 默认 `qa:cache:`（`qa_service.py:242`） | `QA_CACHE_TTL` 默认 259200 |
| 监控 | 同连接 | `QA_MONITOR_KEY` 默认 `qa:monitor:records`（`272`） | 列表 LTRIM 5000，非 TTL |
| `back_mic` ai_search | **未传 db**→0（`ai_service.py:86`） | `kg_rag:cache:`（`kg_rag_service.py:129`） | 604800 |
| `back_cn/.env.example` | （同基础设施） | 覆盖为 `cn:cache:` / `cn:monitor:records` | — |
| `back_shared` | **未找到**独立 Redis 客户端 | | |

### K.2 清缓存 / 清监控

**【已确认】**
- QA：`KEYS {prefix}*` + `delete(*keys)`（`qa_router.py:573–587`）— **非 flushdb**。  
- 监控：`delete(_MONITOR_KEY)`（`590–599`）。  
- kg_rag：`keys("kg_rag:cache:*")` + delete（`kg_rag_router.py:310–312`）。  
**【未找到】** `flushdb`/`flushall` 于上述清缓存路径（若他处有运维脚本未搜到则另计）。

### K.3 4.0 建议

**【推测】** 同实例时用 **`REDIS_DB=1`（或未占用库）** + 前缀 **`qa4:cache:`** / **`qa4:monitor:records`**，依据：3.0/cn/kg_rag 均默认 DB0 且靠前缀隔离；DB 分离可降低误 `KEYS`/`delete` 影响面。仍避免 flushdb。【已确认】前缀隔离已是 cn 做法（`.env.example`）。

---

## L. 依赖与兼容

### L.1 requirements 草稿（写在报告，不新建文件）

```
# qa4 backend draft (from back_qa + back_shared imports)
fastapi>=0.100.0
uvicorn[standard]>=0.22.0
starlette
pydantic>=2.0.0
python-dotenv>=1.0.0
python-multipart>=0.0.9
bcrypt
python-jose[cryptography]
sse-starlette>=1.6.5
openai>=1.0.0
anthropic>=0.18.0
httpx>=0.25.0
redis>=4.0.0
elasticsearch>=8.0.0,<9.0.0
neo4j>=5.0.0
```

出处：`back_qa/requirements.txt`；`back_mic/backend/requirements.txt`；各模块 import（`auth.py`→bcrypt/jose；`reranker_service`→httpx；`neo4j_client`→neo4j；`dependencies`→elasticsearch/redis）。

### L.2 Python 3.10 / OS

**【已确认】** 本机探测与 `__pycache__/*.cpython-310.pyc` 表明按 3.10 使用。上列包均为跨平台常见轮子。  
**【未找到】** 仅 Windows 或仅 Linux 的硬依赖声明（`docx2pdf` 在 mic 全量 req 中，**不在**拟复制的 qa 子集）。

### L.3 剥离取经文

**【已确认】** 可剥离：`load_bible_data`、`get_verse`、`get_verse_range`（及章节辅助）+ `bible_data/` + `bible_ref_parser`（依赖 `bible_service` 名表）。  
问答流水线部分依赖 `qa_service._step1/_step2…`（`bible_service.py:15–25`）— 复制「只取经文」**不必**带 qa_service。【已确认】

---

## M. 第 5 步候选词表规模

**【已确认】** 以 (c) 2372 名 + 档次 + (b) 主干拼行：

| 版本 | 字符数 | 令牌粗估（×1～1.5） |
|------|--------|---------------------|
| `词｜档｜主干` 全表 | 28846 | **约 2.9万–4.3万** |
| 仅词名 | 9773 | **约 1.0万–1.5万** |
| 最内在 133 | 741 | **约 0.07万–0.11万** |

估法：中文约每字 1–1.5 token（`m_size.json`）。

---

## N. 本机开发条件

### N.1 启动

**【已确认】** 后端：`python -m uvicorn back_qa.main:app --host 0.0.0.0 --port 8001`（或 `QA_PORT`）；`main.py` 加载 **`back_mic/backend/.env`**（`main.py:10–18,114–116`）。  
前端：`front_qa` Vite `port 5174`，proxy `/api/qa`→`http://localhost:8001`（`vite.config.js:12–18`）。

### N.2 qa4/.env.example

**【已确认】** 现有：`QA4_ES_*`、`QA4_NEO4J_*`、堆/内存注释（`qa4/.env.example`）。  
**【推测】** 后端应用键建议继续 `QA4_` 前缀，并增：`QA4_REDIS_DB`、`QA4_REDIS_PREFIX`、`QA4_CACHE_TTL`、`QA4_MONITOR_KEY`、`QA4_PORT`、模型/OpenRouter/Anthropic 名（值放 4.0 自有 env）。

### N.3 .gitignore

**【已确认】** 根 `.gitignore` 已有：`.env`、`*.env`、`*.db`、`*.log`、`logs/`。  
**【未找到】** 显式 `qa4/backend/.env`、`qa4/frontend/.env*` 行——但 `*.env` / `.env` 已覆盖常见 env；`*.db` 覆盖 sqlite。若使用无后缀密钥文件名则需另加。

### N.4 版本要求

**【已确认】** 前端：`package.json` 未写 engines；Vue3 + Vite5。后端 req 未钉死 Python；本机 3.10 缓存文件存在。【未找到】README 强制 `python_requires` 句。

---

## O. 语料构成统计

数据根：`G:\PanAI4.0专用\qa4_import_src\es\data\`。

### O.1 各索引 book_title 基数与 top（摘要）

| 索引 | chunks | 不同书名 | top 例 |
|------|--------|----------|--------|
| bible | 3691 | 66 | 诗篇201… |
| hymns | 9154 | 1299（按 name） | 诗歌第152首… |
| outline_12490 | 55841 | 1334 | （纲目书名） |
| outline_feasts | 11110 | 259 | conference/book_title |
| text_life | 39463 | 63 | 生命读经 |
| text_cwwl | 178107 | 1186 | 文集书名 |
| text_cwwn | 32032 | 106 | 倪文集 |
| text_others | 15481 | 3 | 新约总论等 |
| map_note | 16052 | 309 | 真理题库系列… |
| pano_catalog | （上轮）目录节点 | — | 本轮未重扫关键词 |

完整 top30：`o_corpus.json` / `o_text.json`。

### O.2 敏感词在书名/篇名（chunk 命中计数）

**【已确认】** 分索引见上终端汇总；例：cwwl 书名含「长老」6124、「召会生活」4977；life 篇名「职事」2116；feasts 书名「长老」2154。`主的桌子` 多索引为 0。

### O.3 长老训练 02/05

**【已确认】** conference 月码 **02** 春季：chunks **1046**，message_key **250**，year **1997–2026**；**05** 秋季：chunks **1108**，msgs **274**，year **1997–2026**。

---

## P. 其他风险

| 项 | 等级 |
|----|------|
| history answer 不截断致缓存键膨胀/Prompt 过长 | **高** |
| 测试台已删，仅快照可借鉴；勿假定仓内仍有 runner | **中** |
| 词表路德/路得、城市、括号拆合不一致 | **高** |
| 图谱 Scripture ref 与 `parse_bible_ref` 不通用 | **高** |
| hymns 号码跨 series 重叠，默认必须带 series | **高** |
| map_note 无结构化注号/经节字段 | **中** |
| Redis 默认 DB0 多前缀共存，清缓存用 KEYS | **中**（避免 flush） |
| qa4/.env.example 尚缺应用层 Redis/模型键 | **中** |
| 定向无 sort（上轮）+ 追问带全文 | **中** |
| o/pano 等统计以本机数据包为准，与现网可能漂移 | **需要看服务器才能确认** |

---

## 附录：本轮产出

1. `qa4/notes/qa4_backend_build_probe_4.md`  
2. `qa4/notes/lexicon_reconcile.csv`  
3. `qa4/notes/devine_argument_distinct.csv`  
