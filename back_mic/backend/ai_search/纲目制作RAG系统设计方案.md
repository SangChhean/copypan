# 纲目制作 RAG 系统设计方案

## 一、主要技术栈

| 技术 | 用途 |
|------|------|
| **Elasticsearch** | BM25 全文检索（多索引、按纲目性质加权）；kNN 向量检索（段落/经文/纲目型索引）。 |
| **OpenAI Embedding** | 将主题/子主题/摘要方向句编码为向量，供 kNN 语义检索。 |
| **Jina Reranker v3** | 对 RRF 融合结果做 query-document 精排，提升送生成段落的准确性。 |
| **Claude (Anthropic)** | 子主题展开、摘要解析、纲目生成；所有「理解+生成」环节。 |
| **Redis** | 检索结果/上下文缓存；两步模式下的 search_id → 上下文存储；监控统计与错误日志。 |

**开关**：`USE_VECTOR_SEARCH=true` 时启用双路混合（BM25 + kNN）；否则仅 BM25（旧版）。`USE_RERANK=true` 时启用 Jina 精排，否则 RRF 后直接索引加权截断。

---

## 二、整体流程概览

- **入口**：用户输入「纲目主题」+ 可选「负担说明/简单摘要（约 50 字）」+ 纲目性质 + 深度（普通/深度）。
- **分支**：
  - **无有效负担说明**（或实质字数 &lt; 10）→ **方式一**：仅按主题做双路检索，再生成纲目。
  - **有有效负担说明**（实质字数 ≥ 10）→ **方式二**：把负担说明当摘要，先解析成 2～5 个大点，再按大点检索，最后按框架生成纲目。
- **接口形态**：可一步完成（search 内完成检索+生成），或两步（search_only 只检索并写 Redis → generate_only 读上下文再生成）。

---

## 三、方式一：主题生成纲目（无摘要）

1. **Claude 子主题展开（Prompt #1）**  
   输入：主题 + 纲目性质 + 可选负担说明。  
   输出：5 个短句（启示/真理/经历/应用等角度），JSON 数组；不足 5 条用主题补齐，最多 6 条（含负担一句）。  
   用途：得到多路语义查询，供后续向量检索。

2. **Embedding**  
   对「主题 + 子主题（最多 6 条）」批量调用 OpenAI Embedding，得到 1 + N 个向量。

3. **双路检索**  
   - **路 1**：BM25，`_multi_index_search(主题, size, 纲目性质)`，多索引、按性质加权。  
   - **路 2**：子主题向量并发 kNN，多索引、每路取 k 条，合并去重。

4. **RRF 融合**  
   对 BM25 与 kNN 结果做 RRF（k=60），得到统一排序列表。

5. **Reranker（可选）**  
   使用 Jina Reranker v3，query=主题，对 RRF 结果精排并截断（如 Top 100/200）。

6. **索引加权**  
   按纲目性质对索引/年份段加权，再截断到 Top 15～20 条。

7. **Claude 纲目生成（Prompt #2）**  
   输入：主题 + 纲目性质/面对对象等元数据 + 上一步得到的参考段落（reference + content）。  
   System prompt：固定纲目格式与逐字引用等规范（`_build_generate_system_prompt`）。  
   输出：完整纲目正文。

---

## 四、方式二：主题 + 摘要（负担说明）生成纲目

1. **Claude 摘要解析（Prompt #1）**  
   输入：主题 + 摘要（即用户填写的负担说明/简单摘要）+ 纲目性质 + 可选负担说明。  
   输出：2～5 个大点，每点含 `title`、`search_query`、`sub_directions`（4 句），JSON 结构。  
   用途：把摘要拆成可独立检索的「大点」。

2. **按大点并发检索**（每个大点独立）  
   - **路 1**：BM25，query=该点 `search_query`。  
   - **路 2**：`sub_directions` 批量 Embedding → 多路 kNN → 合并。  
   - 每个大点内：RRF 融合 → Jina Reranker（query=该点 search_query）→ 索引加权 → 截断到每点 Top 4～6 条。

3. **Claude 按框架生成（Prompt #2）**  
   与方式一共用 **同一套** system prompt（`_build_generate_system_prompt`）。  
   输入：主题 + 摘要（骨架）+ 按大点组织好的参考段落（每点下若干条 content）。  
   输出：严格按摘要结构填充的完整纲目。

---

## 五、使用 Prompt 的步骤汇总

| 步骤 | 方式 | Prompt 类型 | 说明 |
|------|------|-------------|------|
| 子主题展开 | 方式一 | Claude system + user | 将主题展开为 5～6 个短句，JSON 数组；含纲目性质、可选负担说明。 |
| 摘要解析 | 方式二 | Claude system + user | 将主题+摘要解析为 2～5 个大点，每点 title/search_query/sub_directions；含纲目性质、可选负担说明。 |
| 纲目生成 | 方式一、方式二 | Claude system + user | **共用** `_build_generate_system_prompt()`；user 中为「主题 + 元数据 + 参考段落」，方式二还带摘要骨架。 |

其余步骤（Embedding、BM25、kNN、RRF、Reranker、索引加权）均为非 LLM 的检索与排序，无 prompt。

---

## 六、检索与数据流要点

- **深度**：`depth=general` 时条数较少（如 50/200），`depth=deep` 时放大（如 200/400），影响 BM25 size、RRF top_n、Reranker top_n、最终送 Claude 的条数。  
- **索引**：段落型（cwwl/cwwn/life/others）、经文型（bib）、纲目型（map_*_chunks + 父文档），RRF 去重键为 `_id` 或 `chunk_id`。  
- **缓存**：同一 question + depth + metadata（含 skeleton/burden）共用一个缓存 key；命中则直接返回，不再检索与生成。  
- **两步模式**：search_only 将方式一的 hybrid_docs 或方式二的 skeleton 大点结果写入 Redis（约 5 分钟 TTL），generate_only 凭 search_id 读出后再调用 Claude 生成。

---

## 七、监控与统计

- **Redis**：全局统计（`ai_monitoring:stats`）、每日统计（`ai_monitoring:daily:YYYY-MM-DD`，TTL 30 天）、错误列表、检索日志；`record_query` 记录每次生成/缓存命中的 mode（新版方式一/二、旧版）、depth、tokens/cost。  
- **检索统计**：`_multi_index_search` 末尾调用 `record_retrieval_stats`，记录 BM25 检索条数/使用条数/浪费率等，供后台展示。

---

## 八、文档与代码入口

- 设计规格：`ai_search/DESIGN_SPEC_V2.md`  
- 核心实现：`ai_search/ai_service.py`（`_hybrid_search_mode1`、`_hybrid_search_mode2`、`_generate_answer`、`_generate_mode2`、`_build_generate_system_prompt`）  
- 检索与排序：`embedding_service.py`、`vector_search.py`、`rrf.py`、`reranker_service.py`  
- 路由与元数据：`ai_router.py`（search/search_only、generate_only、metadata 中的 burden_description/skeleton）
