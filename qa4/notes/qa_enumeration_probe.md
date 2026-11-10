# back_qa（3.0）对「列举类」提问的只读勘探

范围：只读代码与提示词，未改文件（除本笔记）、未跑服务、未做实验。  
示例问法：「神的名有哪些」「耶和华的复名有哪些」「召会的异象有哪几点」。

---

## 1. 开头预判（TARGETED_DETECTION 及其调用处）

### 结论

遇到「……有哪些 / 有哪几个 / 列举……」这类**未点名书目篇章、也未点名经文章节**的问题，按提示词规则应归入 **intent = `"general"`（一般）**，不会进定向（`targeted`）或经文（`bible`）。  
调用处对 `general` / 解析失败返回 `None`，随后走完整流水线（Step1→2→3→4）。

### 分类依据（提示词）

- `targeted`：须同时满足「明确书/书系名」+「明确篇号/章号」。`back_qa/qa/prompts.py:167-173`
- `bible`：须能识别书卷与范围（verse / range / chapter）。`back_qa/qa/prompts.py:175-188`
- `general`：「其他所有情况」。`back_qa/qa/prompts.py:193-194`

示例「神的名有哪些」等不满足 targeted/bible 条件 → **general**。

### 提示词里有无「列举 / 汇集 / 枚举」字样或例子？

**没有。** 对 `back_qa/qa/prompts.py` 全文检索「有哪些」「列举」「枚举」「哪几」「列出」「汇集」：**无匹配**（本文件内 TARGETED / STEP1 / STEP3 / STEP4 模板均无此类字样或专例）。

### 调用处

- `_detect_targeted`：`back_qa/qa/qa_service.py:372-394`（加载 `TARGETED_DETECTION` 并调用 LLM）
- 流水线入口：`back_qa/qa/qa_service.py:1251-1254`（`precheck_targeted = await _detect_targeted(question)`）
- `intent == "bible"` 短路：`back_qa/qa/qa_service.py:1256-1264`
- `intent == "targeted"` 走定向检索：`back_qa/qa/qa_service.py:1266-1292`
- 否则（含 general → `None`）进完整流水线：`back_qa/qa/qa_service.py:1300+`

`general` 返回路径：`intent` 非 targeted/bible 时函数落到返回 `None`（失败亦同）。`back_qa/qa/qa_service.py:401-414` 起分支；文档字符串写明 `None` = general 或解析失败。`back_qa/qa/qa_service.py:372-378`

---

## 2. 推荐重点（STEP1_CONCEPT_EXTRACTION 及调用处）

### 有没有区分「要找一个答案」与「要找一组项目」？

**没有。** 模板只要求从词表抽 `surface`（1–3）与 `deep`（1–5），以及 `rewritten_query`；未出现单答案 / 列表 / 列举 / 项目组等区分。`back_qa/qa/prompts.py:22-50`

### 对「神的名有哪些」：按规则最可能选出的浅层 / 深层词

> **以下为按提示词规则的推断，不是实测 LLM 输出。**

推断逻辑（提示词约束）：

| 层 | 规则摘要 | 文件:行号 |
|----|----------|-----------|
| surface | 题面直接出现或与主语直接对应；必须词表逐字存在；1–3 个 | `prompts.py:25-28`, `45` |
| deep | 回答不可绕过、题面未直接说出；非泛词；不与 surface 重复；1–5 个 | `prompts.py:30-35`, `46` |

对「神的名有哪些」的推断：

- **surface（推断）**：若词表中存在与题面逐字对应的概念（例如含「神的名」或题面已写明的近义条目），模型应优先选这类作 surface；数量通常 1 个左右（题面核心主语）。
- **deep（推断）**：应选「回答该列举问题不可绕过、但题面未写出」的词表概念（例如与神之名相关、却未出现在问句字面中的条目）；具体名称**完全依赖运行时 Neo4j 词表**。

### 具体词条能否确认？

**未确认。** 词表由 `neo4j_client.get_concept_names()` 运行时加载（`MATCH (c:Concept) RETURN c.name`），仓库内 `back_qa` 无静态词表快照可供只读核对。  
加载实现：`back_shared/neo4j_client.py:60-86`  
Step1 注入：`back_qa/qa/qa_service.py:526-533`

### 调用处

- `_step1`：`back_qa/qa/qa_service.py:497-533`（`STEP1_CONCEPT_EXTRACTION.format(...)`）
- 流水线：`back_qa/qa/qa_service.py:1301-1308`

---

## 3. 检索（Step 2）

### 「主路 20 段」「深层词扩展各 5 段」在哪里设定？

| 数字 | 设定位置 | 说明 |
|------|----------|------|
| 主路 Top 20 | `RERANK_TOP_N = 20`：`back_qa/qa/qa_service.py:112` | `_step2` 默认 `rerank_top_n`：`688`；注释写明主路 Top 20：`714` |
| 扩展每 deep 概念 5 段 | 默认 `expansion_top_n` / `_expansion_top_n = 5`：`back_qa/qa/qa_service.py:720`, `1242`；debug 可覆盖：`1247` | `_expand_one` 内 `rerank(..., top_n=exp_rerank)`：`726` |
| 路由默认 | `expansion_top_n: int = 5`：`back_qa/qa/qa_router.py:43` | |

主路 + 按 deep 并发扩展、去重后拼接：`back_qa/qa/qa_service.py:731-765`  
调用：`back_qa/qa/qa_service.py:1318-1326`

### 有没有按「项目」逐项检索的机制？

**没有。** 扩展路是「对每个 **deep 概念名**」做 `"{rewritten_query} {concept}"` 检索，不是按答案里的各个「项目」（如各个神的名）拆开检索。`back_qa/qa/qa_service.py:712-715`, `741-743`

代码中未见「列举项 / 项目列表」解析后再检索的逻辑。

### 检索结果有没有数量或覆盖面的检查？

**没有**针对列举完整性 / 覆盖面的检查。仅有日志打印段落数量（如 `750`, `764`, `1292`, `1802` 的 `passage_count`），无「是否列全」「项目是否覆盖」类断言或二次检索。

---

## 4. 相关性把关（Step 3）与生成（Step 4）

### Step 3：有无列举类要求（列全 / 标明出处 / 不得凭记忆补充）？

**没有。** `STEP3_RELEVANCE_CHECK` 只判断段落是否足以回答检索查询指向的具体问题；标准含「能直接回答」「主题相关可参考」「多书对比但单源 → false」「无关 → false」「主题相关但无法直接回答 → false」。无「列全」「枚举」「列举」字样。`back_qa/qa/prompts.py:57-75`  
调用：`back_qa/qa/qa_service.py:941-976`（送入 LLM 时仅取 `passages[:10]`、每段最多 200 字作摘要：`950-951`）

### Step 4：有无列举类要求？

**没有。** `STEP4_ANSWER_GENERATION` 强调从职事段落找答案、原文引用、书目编号、禁止改写原文等；无「列全」「列举完整」「不得凭记忆补充列表项」等专条。`back_qa/qa/prompts.py:95-136`

### Step 4 是否允许用检索段落之外的内容？

分两层：

1. **系统提示（硬约束表述）**  
   「严格基于所提供的段落作答……不编造，不拼凑。」  
   - 非流式：`back_qa/qa/qa_service.py:1196`  
   - 流式：`back_qa/qa/qa_service.py:1419`

2. **用户 prompt 实际注入的非 ES 段落上下文**（同属「所提供」材料，但**不是** Step2 检索段落）：  
   - `{greek_context}` / `{verse_context}` / `{graph_context}`（Step1 自 Neo4j）：`prompts.py:101-102`；组装：`qa_service.py:1042-1049`  
   - `{firewall_instruction}`：`prompts.py:103`  
   - 要求 1、11 允许需要时提及【关键经文】与【希腊/希伯来原文】：`prompts.py:105`, `115`

因此：

- 提示词要求答案主线来自所给职事段落，`「」` 内须逐字原文，禁止改写/总结顶替原文：`prompts.py:105-109`, `113`  
- **未**写「不得凭记忆补充列举项」的专门条款  
- **允许**使用一并注入的 Neo4j 希腊文/经文/关系与 firewall 文案（相对 Step2 passages 而言是段落外参考）  
- 模型是否会用参数知识补全列表：**未确认**（提示词未显式禁止「记忆补全列表」，也未专测）

---

## 5. 全仓库搜索（列举相关词）

检索词：`有哪些`、`列举`、`枚举`、`哪几`、`列出`（及对 `back_qa/qa`、`prompts` 补搜 `汇集`）。

| 范围 | 结果 |
|------|------|
| `back_qa/qa/`（服务与提示词） | **无匹配** — 无列举类专用逻辑或提示 |
| `back_shared/` | **无匹配** |
| `front_qa/` | **无匹配** |
| `front_cn/`（与 QA 相关前端） | **无匹配**（本次对源码目录检索） |
| `qa4/frontend/` | **无匹配** |
| `back_qa/bible_data/*.json` | 有「列举」「汇集」「有哪些」等，均为**经文/注解语料正文**，非问答路由逻辑 |
| 其他目录（如 `back_mic` 负担 prompt、`scripts/骨架测试用`） | 有「列出要点」等，属**另一产品线**，与 `back_qa` 列举类问答无关 |

结论：在 **back_qa 流水线、back_shared、front_qa** 中，**未发现**针对「列举类提问」的专用分支、意图标签或提示词条款。

---

## 总表

| 环节 | 对列举类是否有特殊处理 |
|------|------------------------|
| TARGETED_DETECTION | 否 → general |
| STEP1 | 否（仍 surface/deep；无单答 vs 列表区分） |
| Step2 | 否（固定 topN；按 deep 概念扩检，非按项目） |
| Step3 | 否 |
| Step4 | 否（无列全/禁记忆补全专条；有「严格基于段落」+ Neo4j/firewall 注入） |
| 前端 / shared | 无相关逻辑 |

---

## 验证备注

本笔记路径：`qa4/notes/qa_enumeration_probe.md`。  
预期：`git status --short` 仅多此一个未跟踪文件；`git diff --stat` 为空（无已跟踪文件改动）。
