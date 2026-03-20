# Embedding 使用规则

项目通过 **embedding_adapter** 统一接入多档位 Embedding，避免在业务代码中写死模型与维度。

## 规则一览

| profile    | 用途               | 后端           | 维度 | 环境变量 |
|-----------|--------------------|----------------|------|----------|
| `default` | 现有 AI 纲目 / 双路 RAG | OpenAI         | 512  | OPENAI_API_KEY |
| `kg_rag`  | KG-RAG 模块        | OpenRouter     | 1024 | OPENROUTER_API_KEY, EMBEDDING_KG_MODEL, EMBEDDING_KG_DIMS |

## 调用方式

- **现有 ai_search：** 继续使用 `ai_search.embedding_service.get_embeddings`（即 default 行为），无需改调用方。
- **KG-RAG：** 使用 `embedding_adapter.get_embeddings(texts, profile="kg_rag")`，维度通过 `get_embedding_dims("kg_rag")` 获取（如 ES mapping、kNN 配置）。

## 配置

见 `.env.example` 中「Embedding 适配层」与「Neo4j」相关项；未配置 `OPENROUTER_API_KEY` 时，调用 `profile="kg_rag"` 会抛出明确错误。
