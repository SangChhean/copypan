# 完整最终设计规格 v2

---

## 一、环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `USE_VECTOR_SEARCH` | false | true=双路混合检索 |
| `USE_RERANK` | true | true=启用 Jina Reranker |
| `JINA_API_KEY` | - | Jina Reranker API Key |
| `OPENAI_API_KEY` | - | 已有，Embedding 用 |

**Jina 模型 ID**：`jina-reranker-v3`（实现时写死，无需再猜）

---

## 二、方式一：主题生成纲目

```
用户输入主题
    ↓
Claude 展开为 5 个短句子主题（批量 Embedding，1 次 API）
    ↓
并发执行：
  路1：BM25 检索原始主题（_multi_index_search，取 60 条）
  路2：5 路并发 kNN（每路各取 60 条）→ 合并去重
    ↓
RRF 融合（k=60）→ Top 60
    ↓
Jina Reranker v3（query=原始主题）→ Top 30
    ↓
索引加权微调 → Top 15～20 送 Claude
    ↓
Claude 自由生成完整纲目
```

**降级**：Jina 不可用时，RRF Top60 → 索引加权 → Top 15～20

**方式一 Claude 子主题输出格式**：JSON 数组 `["短句1", "短句2", "短句3", "短句4", "短句5"]`，解析稳定。

---

## 三、方式二：主题+龙骨生成纲目

```
用户输入主题 + 龙骨原文（自由文本）
    ↓
一次 Claude 调用：解析龙骨 + 为每大点生成 search_query + sub_directions
    ↓
N 个大点并发执行，每大点独立：
  路1：BM25 检索 search_query（取 15 条）
  路2：sub_directions 批量 Embedding → 并发 kNN → 合并去重（取 15 条）
    ↓
每大点独立 RRF（k=60）→ Top 15
    ↓
每大点独立 Jina Reranker（query=该大点 search_query）→ Top 5～8
    ↓
每大点索引加权 → Top 4～6
    ↓
按大点组织内容 → Claude 严格按框架填充
```

**降级**：Jina 不可用时，每大点 RRF Top15 → 索引加权 → Top 4～6

**方式二 Claude 龙骨解析输出格式**：JSON 结构，每大点含 `title`、`search_query`、`sub_directions`（2～3 条短句数组），写死 JSON 便于解析。

---

## 四、段落单位

| 索引类型 | 单位 | 附加 |
|----------|------|------|
| cwwl / cwwn / life / others | 文档本身 | 无 |
| bib | 章级文档 | 无 |
| map_note_chunks / map_7feasts_chunks / map_pano_chunks / map_dictionary_chunks | chunk | 附父文档 title + b_read |

---

## 五、索引加权

| 纲目性质 | 索引 | 系数 |
|----------|------|------|
| 一般性 | cwwl(94-97) | 1.1，其余 1.0 |
| 真理 | cwwl(94-97) | 1.5，其余 1.0 |
| 生命 | cwwn / life | 1.5，其余 1.0 |
| 实行 | cwwl(85-93) | 1.5，其余 1.0 |

纲目型按**父索引**查表：`map_note_chunks → map_note`，年份段复用现有 `_CWWL_EXTRA_WEIGHT_PATTERNS_*`。

---

## 六、RRF 去重键

- 段落型 / 经文型：`_id`
- 纲目型：`chunk_id`

---

## 七、API 接口

**方式一（现有接口不变）：**

```
POST /api/ai_search/search
{
  "question": "主题",
  "depth": "general|deep",
  "special_needs": "一般性|高真理浓度|高生命浓度|重实行应用"
}
```

**方式二（新增字段）：**

```
POST /api/ai_search/search
{
  "question": "主题",
  "skeleton": "龙骨原文（有则走方式二，无则走方式一）",
  "depth": "general|deep",
  "special_needs": "一般性|高真理浓度|高生命浓度|重实行应用"
}
```

- **depth**：`general` 与现有代码一致，勿用 `normal`。
- **缓存 key**：方式二须包含 `hash(skeleton)`，避免同一主题不同龙骨命中错误缓存。

---

## 八、两步流（search_only + generate）

- 方式二的 context 按大点组织存 Redis，结构示例：

```json
{
  "mode": "skeleton",
  "points": [
    { "title": "壹 ...", "context": ["段落1", "段落2"] },
    { "title": "贰 ...", "context": ["段落1", "段落2"] }
  ]
}
```

- **generate 步骤无需再传 skeleton**，按 `search_id` 取回已存的按大点 context 即可，避免前端多传。

---

## 九、任务列表

| 任务 | 文件 | 内容 |
|------|------|------|
| 1 | ai_search/embedding_service.py | OpenAI 批量 Embedding |
| 2 | ai_search/reranker_service.py | Jina Reranker v3 + 降级 |
| 3 | ai_search/vector_search.py | 并发 kNN，纲目型附 title+b_read |
| 4 | ai_search/rrf.py | RRF 融合（k=60），去重截断 |
| 5 | ai_search/ai_service.py | 方式一完整流程 |
| 6 | ai_search/ai_service.py | 方式二完整流程 |
| 7 | Search.vue | 龙骨文本框开关 |
| 8a | ai_search/ai_service.py | 方式一 prompt 防幻觉 |
| 8b | ai_search/ai_service.py | 方式二 prompt 框架填充约束 |
| 9 | back_mic/backend/.env.example | 新增变量说明 |

**执行顺序**：1 → 2/3/4 并行 → 5+8a → 6+8b；7 与 5 并行；9 随时可做。
