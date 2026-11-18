# PanAI 4.0 问答站 · 后端构建前只读勘探报告

> 日期：2026-11-13  
> 范围：只读勘探仓库；**未**修改/删除既有文件；**未** git add/commit/push。  
> 标注：【已确认】= 见代码；【推测】= 合理推断但未直接看到；【需要看服务器才能确认】= 仓库不足。  
> 「未找到」= 本仓库内未检索到，不猜测。

---

## A. 3.0 后端 `back_qa` 的结构

### A.1 入口、路由、流式与消息格式

**【已确认】** 入口：`back_qa/main.py`（模块 docstring 与 `__main__` 端口默认 8001）。

- 加载 `.env`：固定路径 `back_mic/backend/.env`（`main.py:10–18`）。
- 挂载路由：`/api/qa` ← `qa_router` + `bible_router`；`auth_router` 自带完整路径（`main.py:108–110`）。
- 请求超时中间件 120s（`main.py:85–100`）。

| 方法 | 路径 | 作用 | 出处 |
|------|------|------|------|
| GET | `/api/qa/liveness` | 存活探针 | `qa_router.py:185–188` |
| GET | `/api/qa/readiness` | ES/Neo4j/Redis + 数据基线 | `qa_router.py:191–236` |
| POST | `/api/qa/query` | 非流式问答 | `qa_router.py:239–262` |
| POST | `/api/qa/stream` | **SSE 流式问答** | `qa_router.py:265–301` |
| POST | `/api/qa/translate` | 简→繁 / EN | `qa_router.py:304–330` |
| POST | `/api/qa/tts` | Gemini TTS → WAV | `qa_router.py:333–421` |
| POST | `/api/qa/tts/minimax` | MiniMax TTS → MP3 | `qa_router.py:424–484` |
| POST | `/api/qa/tts/elevenlabs` | ElevenLabs TTS | `qa_router.py:487–532` |
| POST | `/api/qa/feedback` | 点赞/点踩 | `qa_router.py:535–551` |
| POST | `/api/qa/cache/clear` | 清缓存（Admin） | `qa_router.py:573–587` |
| POST | `/api/qa/stats/clear` | 清监控（Admin） | `qa_router.py:590–599` |
| GET | `/api/qa/stats` | 监控统计（Admin） | `qa_router.py:602–641` |
| GET | `/api/qa/feedback/stats` | 反馈统计（Admin） | `qa_router.py:644–649` |
| POST | `/api/qa/asr` | 语音转写 | `qa_router.py:652–685` |
| POST | `/api/qa/bible/query` | 经文问答 SSE | `bible_router.py:42–108` |
| POST | `/api/qa/auth/register` | 注册 | `auth_router.py:87–94` |
| POST | `/api/qa/auth/login` | 登录发 JWT | `auth_router.py:97–103` |
| GET | `/api/qa/auth/me` | 当前用户 | `auth_router.py:106–110` |
| GET | `/api/qa/auth/usage` | 日用量 | `auth_router.py:113–117` |
| POST | `/api/qa/auth/invite` | 建邀请码（Admin） | `auth_router.py:120–126` |
| GET | `/api/qa/auth/users` | 用户列表（Admin） | `auth_router.py:129–133` |
| DELETE | `/api/qa/auth/users/{username}` | 删用户（Admin） | `auth_router.py:136–144` |
| GET | `/api/qa/auth/invites` | 邀请码列表（Admin） | `auth_router.py:147–151` |
| POST | `/api/qa/auth/users/{username}/limit` | 设日限额（Admin） | `auth_router.py:158–167` |

**【已确认】** 问答流式：**SSE**（`sse_starlette.sse.EventSourceResponse`），非 WebSocket（`qa_router.py:15,301`）。

SSE 载荷：每条 `data` 为 JSON 字符串（`qa_router.py:297`）。`stream_query` 产出类型（`qa_service.py:1690–1891`）：

| `type` | 主要字段 |
|--------|----------|
| `step` | `stage`（step1/2/3）, `data` |
| `token` | `text` |
| `done` | `answer`,`sources`,`found`,`cache_hit`,`concepts`,`elapsed_ms`,`cost`,`request_id`,`cache_key` |
| `error` | `message` 或 `text`（两处写法并存：`1824` vs `1727`） |
| `verse_data` | `data`（经文分支） |

经文专用路由 `bible/query` 用 `{event, data}` 包一层（`bible_router.py:32–34`）。

---

### A.2 鉴权、用户存储、限额 / IP 限流 / 注入过滤

**【已确认】** JWT：

- 发：`create_token` — HS256，`sub`=username，过期 7 天，密钥 `QA_JWT_SECRET`（`auth.py:16–21,223–233`）。
- 验：`Authorization: Bearer …` → `verify_token`（`auth_router.py:66–74`；`auth.py:236–245`）。
- 登录返回 `{token, username}`（`auth_router.py:97–103`）。

**【已确认】** 用户存在 **SQLite 文件**：`back_qa/qa/qa_users.db`（`auth.py:15`）。表：`users`、`invite_codes`、`feedback`（`auth.py:40–76`）。

**【已确认】** 日限额：按用户字段 `daily_limit` / `daily_count` / `daily_date`（`auth.py:97–125`）；`/stream` 与经文流调用 `check_and_increment_daily_usage`（`qa_router.py:272–277`；`bible_router.py:45–50`）。默认建用户 `daily_limit=3`（`auth.py:179`）。环境变量 `QA_DAILY_LIMIT` 在 `qa_router.py:21` / `bible_router.py:20` **定义但同文件未见使用** → 【推测】可能是遗留；实际限额以 DB 为准。

**【已确认】** IP 限流：`back_qa/qa/rate_limit.py`（滑动窗口 Redis sorted set；默认 15/分钟；前缀 `qa:ratelimit:`）。

**【已确认】** 注入过滤：同文件 `check_prompt_injection`（`rate_limit.py:67–97`）；`/query` `/stream` 调用（`qa_router.py:248–249,280–281`）。

**【已确认】** 管理鉴权：头 `X-Admin-Token` 对 `QA_ADMIN_TOKEN`（`qa_router.py:559–566`；`auth_router.py:77–84`）。

---

### A.3 缓存（Redis）

**【已确认】**

- 键：`{QA_REDIS_PREFIX 默认 qa:cache:}{sha256(question|history|PROMPT_VERSION|MODEL_PROFILE|FIREWALL_RULES_VERSION)}`（`qa_service.py:235–243`；版本来自 `back_shared/version_manifest.py:8–14`）。
- 语言变体：`{cache_key}:zh_tw` / `:en`（`qa_service.py:1603+`）。
- TTL：`QA_CACHE_TTL` 默认 `259200` 秒（3 天）（`qa_service.py:262`）。
- **「未找到」会缓存**：`found=False` 时在非 debug 下 `_write_cache`（`qa_service.py:1358–1380`）。

---

### A.4 监控与 feedback

**【已确认】** `qa:monitor:records`：

- 键名：`QA_MONITOR_KEY` 默认 `qa:monitor:records`（`qa_service.py:272`）。
- 写入：`_write_monitor` → `LPUSH` + `LTRIM` 最多 5000（`qa_service.py:276–283`）。
- 字段（各调用点合集）：`request_id`,`question`,`cache_hit`,`found`,`ts`；失败时可有 `step_fail_stage`；另有 `total_elapsed_ms`,`total_cost_usd`（例：`1349–1357`,`1566–1573`,`1231–1236`）。

**【已确认】** `feedback` 表（`auth.py:66–75`）：

`id, request_id, username, question, answer, rating, created_at`；写入 `insert_feedback`（`280–291`）。

---

### A.5 管理后台相关接口

**【已确认】** 见 A.1 Admin 行：`cache/clear`、`stats`、`stats/clear`、`feedback/stats`、auth 下 invite/users/limit。前端 `#/admin` → `AdminPage.vue`（`front_qa/src/router/index.js:14–16`）。

---

### A.6 模型调用封装

**【已确认】**

| 项 | 内容 | 出处 |
|----|------|------|
| 库 | `anthropic.AsyncAnthropic` | `qa_service.py:136–138,171–203` |
| Step1/3/4 模型 | Step1=`QA_STEP1_MODEL` 默认 `claude-sonnet-4-6`；Step3 硬编码 `claude-haiku-4-5-20251001`；Step4 硬编码 `claude-sonnet-4-6` | `qa_service.py:104–106` |
| 流式 Step4 | `client.messages.stream` | `qa_service.py:1414–1441` |
| LLM 重试 | **主问答 `_call_llm` 无重试** | `qa_service.py:171–203` |
| 超时 | 应用层请求 120s；Anthropic SDK 默认超时未在本文件单独配置 | `main.py:85–96`；LLM 超时 **未找到**专用配置 |
| 费用 | `_calc_cost` + `_PRICING` | `qa_service.py:210–228` |
| 翻译 | Gemini（`google`/`translation_service`），带重试 | `translation_service.py:256+` |
| Embedding | OpenRouter via `openai.AsyncOpenAI` | `back_shared/embedding_adapter.py:18–38` |
| Rerank | Jina HTTP，最多 2 次尝试 | `reranker_service.py:74–109` |

---

### A.7 配置读取与环境变量名（仅名，无值）

**【已确认】** 加载：`python-dotenv` 读 `back_mic/backend/.env`（`main.py:10–18`）。清单（代码中出现的名）：

**共享 / 基础设施：** `ES_HOST`,`ES_PORT`,`ES_USERNAME`,`ES_PASSWORD`,`REDIS_HOST`,`REDIS_PORT`,`REDIS_DB`,`NEO4J_URI`,`NEO4J_USER`,`NEO4J_PASSWORD`,`CLAUDE_API_KEY`,`OPENROUTER_API_KEY`,`OPENROUTER_BASE_URL`,`EMBEDDING_KG_MODEL`,`EMBEDDING_KG_DIMS`,`JINA_API_KEY`

**QA 业务：** `QA_PORT`,`QA_JWT_SECRET`,`QA_ADMIN_TOKEN`,`QA_STEP1_MODEL`,`QA_STEP3_MODEL`（`bible_service.py:31`）、`QA_ES_INDEX`,`QA_REDIS_PREFIX`,`QA_CACHE_TTL`,`QA_MONITOR_KEY`,`QA_RATE_LIMIT_PER_MINUTE`,`QA_RATELIMIT_PREFIX`,`QA_DAILY_LIMIT`,`QA_SKIP_TARGETED`,`QA_TRANSLATION_GEMINI_MODEL`

**语音/翻译等：** `GEMINI_API_KEY`,`MINIMAX_API_KEY`,`MINIMAX_GROUP_ID`,`ELEVENLABS_API_KEY`,`ELEVENLABS_VOICE_ZH`,`ELEVENLABS_MODEL`,`OPENAI_API_KEY`,`ANTHROPIC_API_KEY`

部署文档另列同上部分（`back_qa/DEPLOY.md:91–111`）。服务器上 `.env` 实际是否齐全 → 【需要看服务器才能确认】。

---

### A.8 对 `back_shared` 的依赖与共用面

**【已确认】** `back_qa` 直接 import：

| import | 用途 | 出处 |
|--------|------|------|
| `back_shared.neo4j_client.Neo4jClient` | 图谱客户端 | `dependencies.py:9–10` |
| `back_shared.retrieval` | BM25/Dense/RRF/rerank | `qa_service.py:683,717` |
| `back_shared.version_manifest` | 缓存版本常量 | `qa_service.py:236`；`qa_router.py:195`；`prompts.py:7` |

间接（经 retrieval）：`embedding_adapter`、`reranker_service`（`retrieval.py:9–10`）。

**【已确认】** 其他服务对 `back_shared`：

- `back_cn/routers/qa_router.py:193` 引用 `version_manifest`。
- `back_mic`：**未找到** `from back_shared` / `import back_shared`（本仓库 Python 检索）。
- `format_utils`：在 `back_shared` 内，但 **未找到** 被 `back_qa`/`back_mic`/`back_cn` 直接 import；`back_mic` 用的是本地 `formatters.*`（例：`ai_service.py:63–64`）。

**【已确认】** 改 `back_shared` 的风险面：

- `retrieval` / `embedding_adapter` / `reranker_service` / `neo4j_client`：主要为 QA 路径（embedding_adapter 文件头写「仅供 back_qa」，`embedding_adapter.py:3–5`）。
- `version_manifest`：**被 back_qa + back_cn 共用**，改版本会影响双方缓存语义。
- 【推测】`format_utils` 目前近似闲置拷贝，改动对现网影响小，但仍属共享包。

---

## B. 可复用与不可复用（对照 A）

| 块 | 判断 | 理由 |
|----|------|------|
| A.1 入口/路由骨架 | **需改造** | FastAPI+SSE 模式可参考，但索引/图谱/端口/API 前缀与 4.0 数据面不同 |
| A.1 经文 bible 子系统 | **3.0 专有不宜原样带入**（或独立评估） | 依赖 `bible_data` JSON + 独立流水线；4.0 另有 `qa4_bible` 索引 |
| A.2 鉴权/SQLite | **可原样复用（逻辑）/需隔离存储** | JWT+邀请码模式可复制；DB 路径与密钥必须新建，不可共用 `qa_users.db` |
| A.2 限流/注入 | **可原样复用** | 与业务数据无关；前缀建议改为 `qa4:*` |
| A.3 缓存 | **需改造** | 键算法可复用，但前缀/版本常量/索引变更需独立，避免冲 3.0 缓存 |
| A.4 监控/feedback | **可原样复用（逻辑）** | Redis list + SQLite 表结构清晰；键/库需独立 |
| A.5 管理接口 | **可原样复用（逻辑）** | 与 Admin 页配对；Token/路径可平行一份 |
| A.6 LLM 封装 | **需改造** | Anthropic 调用可参考；模型名/Prompt/费用表需按 4.0 重配 |
| A.7 配置 | **需改造** | 3.0 绑死 `back_mic/backend/.env`（`main.py:13`）；4.0 应用 `QA4_*` / 独立 `.env` |
| A.8 back_shared 原样 import | **3.0 专有不宜直接 import 进 4.0 运行时** | `qa4/README.md:37` 明确要求复制进 qa4；且 Neo4j 标签/向量字段与 4.0 不一致（见 C/G） |
| retrieval 双路+RRF+Jina | **需改造后复用思路** | 算法可迁；`dense` 字段名、索引列表必须改 |

---

## C. 检索相关代码

### C.1 3.0 如何连接 ES 与 Neo4j

**【已确认】**

| 组件 | 连接位置 | 配置项名 |
|------|----------|----------|
| ES | `dependencies.py:13–27` → `Elasticsearch(_es_base_url(), basic_auth=…)` | `ES_HOST`,`ES_PORT`,`ES_USERNAME`,`ES_PASSWORD` |
| Neo4j | `Neo4jClient.startup`（`neo4j_client.py:27–38`）；实例由 `dependencies.get_neo4j_client` | `NEO4J_URI`,`NEO4J_USER`,`NEO4J_PASSWORD` |

默认索引列表 `QA_ES_INDEX`：`kg-rag_7feasts,kg-rag_bib,…`（`qa_service.py:115–118`）——均为 **3.0 `kg-rag_*`**，非 `qa4_*`。

### C.2 查询向量生成 vs qa4 索引向量（重要）

| 侧 | 模型 | 维度 | 出处 | 标注 |
|----|------|------|------|------|
| **3.0 查询向量** | 默认 `qwen/qwen3-embedding-8b`（可被 `EMBEDDING_KG_MODEL` 覆盖） | 默认 **1024**（`EMBEDDING_KG_DIMS`） | `back_shared/embedding_adapter.py:14–15,34–37`；由 `retrieval.dense_search` 调用（`retrieval.py:86`） | 【已确认】 |
| **qa4 十索引（仓库内）** | **未找到**模型名（`qa4/` 的导入脚本/文档只写维度与「不重算向量」） | **1024** | `qa4/data_prep/es_import.py:51–59`（`VEC_DIMS`/`DENSE_EMB`）；说明「不重算向量」`es_import.py:1–2` | 【已确认】维；模型名在 **qa4/ 内未找到** |
| **数据包生成侧（仓内 panai4，不在 qa4/）** | `kg_rag` profile → 同默认 `qwen/qwen3-embedding-8b` / 1024 | 1024 | 例：`panai4/inherit/gen_embeddings.py:297`；`panai4/outline/gen_embeddings.py:26,297`；`panai4/hymns/config.py:42`；适配层 `kg_rag/embedding_adapter.py:24–25` | 【已确认】生成脚本写法；**现网包是否用该默认** → 【需要看服务器才能确认】/生成时 env |

**是否一致：**

- **维度：一致（均为 1024）** — 【已确认】。
- **模型名：在「3.0 查询默认」与「panai4 生成脚本默认」层面一致（同 env 默认）** — 【已确认】默认值相同。
- **「qa4/ 文档自证模型名」：未找到**；若部署时改过 `EMBEDDING_KG_MODEL`，查询与入库可能不一致 → 【需要看服务器才能确认】当时生成与现网 `.env`。

### C.3 精排（Jina）

**【已确认】** `back_shared/reranker_service.py`：

- Endpoint：`https://api.jina.ai/v1/rerank`（`L13`）
- Model：`jina-reranker-v3`（`L14`）
- Timeout：`10.0`（`L15`）
- Payload：`model,query,documents,top_n`（`L63–68`）
- 调用链：`retrieval.rerank` → `reranker_service.rerank`（`retrieval.py:174–190`）；QA 默认 `RERANK_TOP_N=20`（`qa_service.py:112`）

### C.4 qa4 十个索引 mapping 摘要

来源：`qa4/data_prep/es_import.py`（导入后目标名默认前缀 `qa4_`，`L46`；`INDEX_SPECS` 源名 `panai4_*`，`L236–317`）。

公共向量定义：`dense_vector` dims=1024, cosine, `int8_hnsw`（`L54–60`）。文本默认：`ik_max_word` / search `ik_smart`（`L63–67`）。

| 目标索引（导入后） | 向量字段 | 主要字段类型要点 |
|--------------------|----------|------------------|
| `qa4_outline_12490` / `qa4_outline_feasts` | `embedding` | `OUTLINE_MAPPING`：`chunk_id` keyword；`text` IK；书名等 keyword+text；大量 meta integer/keyword（`L87–117`） |
| `qa4_bible` | `embedding` | `BIBLE_MAPPING`：含 `verse_range`,`outline_path`,`chunk_type` 等（`L119–145`） |
| `qa4_hymns` | `embedding` | `HYMNS_MAPPING`：`name`/`title` keyword+text；`hymn_number` int（`L147–169`） |
| `qa4_text_life` | `text_vector` | `inherit_mapping(has_section=True)`（`L270–275`） |
| `qa4_text_cwwl` | `text_vector` | inherit + `year`（`L277–284`） |
| `qa4_text_cwwn` | `text_vector` | inherit + section（`L285–291`） |
| `qa4_text_others` | `text_vector` | inherit + section（`L293–299`） |
| `qa4_map_note` | `text_vector` | inherit **无** section（`L301–307`） |
| `qa4_pano_catalog` | 导入规格 `vec_field: None`（`L310–311`）；但 `PANO_MAPPING` **定义了** `text_vector`（`L227`） | 目录节点字段：`node_id`,`name`,`path_text` 等；kind=`pano_jsonl` |

inherit 共用字段含：`chunk_id`,`text`,`text_vector`,`book_title`,`source_zh`/`source_en`/`en`（后三者 `index:False`）等（`L172–198`）。

**【已确认】** 3.0 `dense_search` **只查字段 `embedding`**（`retrieval.py:93`）→ 直接打在 `qa4_text_*`（`text_vector`）上会失败，必须改造。

### C.5 qa4 Neo4j 标签 / 关系 / 属性

**【已确认】**（`docs/panai4_graph/server_deploy_dump.md:14–70`；服务器核对见 `qa4/docs/qa4_server_deploy_record.md:58`）

**标签与数量：** `Truth_Point` 2380，`Scripture` 4851，`Branch` 91，`Trunk` 12（合计节点 7334）。

**无 `Concept` 标签**（与 3.0 `neo4j_client` 的 `MATCH (c:Concept)` 不同 — `neo4j_client.py:67`）。

**关系类型（34）：** 分类 4（`BELONGS_TO_TRUNK`,`OF_BRANCH_DIRECTLY`,`OF_BRANCH_INDIRECTLY`,`GRAFTING`）+ `SUPPORTED_BY` + 29 语义（如 `LEADS_TO`,`CONTAINS`,`EXPERIENCES_ENJOYS`,`OPPOSES_CONTRASTS_WITH`,… 完整表见 `server_deploy_dump.md:21–41`）。

**主要属性：**

- `Truth_Point`：`name`,`name_en`,`definition_3a/b`,`intrinsic_significance`,`greek_terms`,`hebrew_terms`,`high_peak_content`,`mutuality`,`organic_advance`,`same_as`,`devine_argument` 等（`server_deploy_dump.md:54–69`）。
- `Scripture`：`ref`,`text`；关系 `(Truth_Point)-[:SUPPORTED_BY]->(Scripture)`（`docs/panai4_graph/import_scripture_nodes.md:4`）。
- `Trunk`/`Branch`：至少 `name`（约束见 dump 文档 `L45–52`）。

**【已确认】** 3.0 客户端查 `s.id`（`neo4j_client.py:145`），4.0 Scripture 用 `ref` → **属性名不兼容**。

---

## D. 3.0 前端 `front_qa`

### D.1 技术栈 / 目录 / 路由 / 构建

**【已确认】**

- 栈：Vue 3 + Vite 5 + vue-router + pinia + ant-design-vue + axios + marked（`package.json:5–22`）。
- 目录：`src/components/`（QA/Login/Admin/Bible/Debug）、`src/router/`、`src/utils/auth.js`、`src/style/index.css`、`public/`。
- 路由：hash — `/login`,`/`,`/admin`（`router/index.js:3–25`）。
- 构建：`npm run build` → Vite 默认输出 **`dist/`**（`package.json:7`；`vite.config.js` **未**自定义 `build.outDir`；`DEPLOY.md:9,72` 写明 `front_qa/dist`）。
- 开发：端口 5174，代理 `/api/qa` → `localhost:8001`（`vite.config.js:12–19`）。

### D.2 调后端位置与基础地址

**【已确认】** 前端请求多为**相对路径** `/api/qa/...`（例：`LoginPage.vue:68`；`QAPage.vue:1514`；`auth.js:70–78`）。生产依赖 Nginx 同域反代；开发依赖 Vite proxy。

**【已确认】** **不能**只改一个 `VITE_*` 环境变量换后端——**未找到** `import.meta.env` / `VITE_API` 类配置；换后端需改：`vite.config.js` proxy target，以及生产 Nginx `proxy_pass`。

### D.3 流式接收

**【已确认】** `QAPage.vue`：`authFetch('/api/qa/stream')` + `ReadableStream` `getReader()` 解析 SSE JSON（约 `L1514–1627`）。

### D.4 功能文件定位

| 功能 | 位置 |
|------|------|
| 登录/注册 | `LoginPage.vue`；token：`utils/auth.js` |
| 语音输入 ASR | `QAPage.vue`（MediaRecorder + `/api/qa/asr`，约 `L1187+`） |
| 朗读 TTS | `QAPage.vue` `toggleTTS` → `/api/qa/tts*`（约 `L919–1014`）；开关常量 `SHOW_*_TTS`（`L419–422`） |
| 复制 | `copyAnswer`（`QAPage.vue:1756+`） |
| 点赞点踩 | `submitFeedback` → `/api/qa/feedback`（`L1732+`） |
| 多语言 | `langOptions` + `switchLang` → `/api/qa/translate`（`L816+`,`L1079+`）；经文展示 `BibleMessage.vue` |

### D.5 样式/主题可否整体复制

**【已确认】** 样式集中在 `front_qa/src/style/index.css` + 各组件 scoped less（如 `LoginPage.vue`）。目录独立于主站/`front_mic`，**复制到 `qa4/frontend` 不会改 3.0 文件**。  
【推测】若生产 Nginx 仍指 `front_qa/dist`，需新站点配置，否则只影响构建产物路径，不影响 3.0 源码。

---

## E. 部署（仅仓库内）

### E.1 仓库内相关产物

| 项 | 仓库情况 |
|----|----------|
| systemd unit 文件 | **未找到** `.service` 实体文件；仅有 `DEPLOY.md:149–181` 示例（单元名示例 `qa-backend.service`）与 `deploy.sh:77` 调用 `systemctl restart back-qa`（名称与文档示例不一致） |
| nginx QA 配置 | **未找到** 生产 `qa.conf`；仅有 `DEPLOY.md:119–145` 示例块 |
| `deploy.sh` | 根目录存在：构建 `front_qa`、`systemctl restart back-qa`、提示 `https://qa.aipansearch.org`（`deploy.sh:42–49,76–77,97,101`） |
| 其他 nginx | `nginx.conf.example` / `nginx.windows.conf`：**未找到** QA/`8001` 段 |

### E.2 新增独立 4.0 站需改/新增（基于仓库）

**【推测】建议新增：**

- `qa4/backend/` 应用入口与依赖；独立 `.env`（或沿用 `qa4/.env.example` 扩展）。
- `qa4/frontend/` 前端工程（可由 `front_qa` 复制改造）。
- systemd：如 `back-qa4.service`（仓库内需新增单元模板；现网路径【需要看服务器才能确认】）。
- nginx：新 `server_name` + `root` 指向新 `dist` + `location /api/...` → 新端口。
- 可选：`deploy.sh` 增加 4.0 构建/重启段（勿误伤 3.0）。

**【已确认】** 占用端口（仓库记录）：8000 / 8001 / 8014 / 8020（`qa4/docs/qa4_server_deploy_record.md:17`）。qa4 数据面已用 9202 / 7689 / 7476（`infra/README.md:8–10`）。

**建议应用端口：`8030`**（与 80xx 现网块拉开，避开 8000–8020；仓库内 **未找到** 8030 占用记录）。最终是否空闲 → 【需要看服务器才能确认】。

### E.3 须到服务器确认的事项清单

1. 实际 systemd 单元名与内容（`back-qa` vs 文档 `qa-backend`）。
2. 实际 nginx sites（域名、证书、SSE/`proxy_read_timeout`、是否 HTTP/2）。
3. DNS：`qa.aipansearch.org` 与拟用 4.0 域名解析。
4. TLS 证书签发/续期方式。
5. `back_mic/backend/.env` 中 QA 相关变量是否齐全、与默认值差异。
6. 3.0 与 qa4 容器/进程内存余量是否够再跑 4.0 后端。
7. Redis DB/前缀是否与 3.0 隔离策略。
8. 防火墙/ufw 与 Docker 端口暴露现状（记录见 `qa4_server_deploy_record.md:20`）。
9. 4.0 后端建议端口（如 8030）是否已被占用。
10. 数据包生成时实际 `EMBEDDING_KG_MODEL` 是否仍为默认。

---

## F. `qa4/` 目录现状

### F.1 一级目录及用途

| 目录 | 用途（一行） |
|------|----------------|
| `backend/` | 4.0 后端占位（当前仅 README） |
| `frontend/` | 4.0 前端占位（当前仅 README） |
| `data_prep/` | ES/Neo4j 装库、校验、统计脚本 |
| `docs/` | 摸底、等价性、部署记录等文档 |
| `infra/` | compose、Dockerfile.es、IK 插件/词典 |
| `eval/` | 评估题集占位（有 `es_verify_queries.json`） |
| `tests/` | 自动化测试占位 |
| `notes/` | 探针/笔记（含本报告） |
| `data/` | 大数据放置（gitignore；图谱 JSON 等） |

（另有顶层文件：`README.md`、`.env.example`、`.gitignore`、`.gitattributes`。）

### F.2 可复用客户端 / 日志 / 测试

**【已确认】**

- ES/Neo4j **装库与只读校验客户端**：`data_prep/es_import.py`、`es_verify.py`、`graph_verify.py`、`stats_report.py` 等——**不是**问答运行时客户端。
- 问答运行时 ES/Neo4j 客户端：**未找到**于 `qa4/backend`（仍为空）。
- 日志规范：脚本侧有 `QA4_LOG_DIR` 等（`es_import.py:40–44`）；统一应用日志规范 **未找到**。
- 测试：`tests/` 为空骨架（`tests/README.md`）；`eval/` 骨架 + 少量查询 JSON。

### F.3 4.0 前后端建议位置与 `back_shared` 策略

**【已确认】** 既定约定：`qa4/backend/`、`qa4/frontend/`（`qa4/README.md:21–22,37`；两处 README）。

**理由：** 与 3.0 并存隔离；数据面已在 `qa4/infra`+`data_prep`；服务器已用独立 `/opt/qa4_repo` sparse 目录（`qa4_server_deploy_record.md:27`）。

**对 `back_shared`：** 按 `qa4/README.md:37` → **复制进 qa4 后改造**（只读参考 3.0，**不要**运行时 `import back_shared`）。尤其必须改：Neo4j 标签/`ref`、向量字段名多策略、索引列表、环境变量前缀。

---

## G. 风险与阻碍

1. **图谱标签不兼容**：3.0 `Concept` vs 4.0 `Truth_Point`（`neo4j_client.py:67` vs `server_deploy_dump.md:16`）。原样复用客户端会空结果。  
2. **Scripture 属性不兼容**：3.0 `id` vs 4.0 `ref`（`neo4j_client.py:145` vs `import_scripture_nodes.md:4`）。  
3. **向量字段分裂**：`embedding` vs `text_vector`；3.0 dense 写死 `embedding`（`retrieval.py:93`）。  
4. **索引名/集合不同**：`kg-rag_*` vs `qa4_*`；默认 `QA_ES_INDEX` 不含 4.0 十索引（`qa_service.py:115–118`）。  
5. **pano 无业务向量字段规格 vs mapping 含 `text_vector`**：导入 `vec_field: None`（`es_import.py:310–311`）与 mapping 定义（`L227`）不一致，检索策略需明确。  
6. **`.env` 绑死 `back_mic/backend/.env`**（`main.py:13`）— 4.0 若照搬会与 3.0/主站配置耦合。  
7. **Redis/监控键默认 `qa:*`**：与 3.0 共 Redis 时会串数据，除非改前缀/DB。  
8. **SQLite 用户库路径硬编码**于 `back_qa/qa/qa_users.db`（`auth.py:15`）— 不可共用。  
9. **SSE `error` 字段不统一**（`message`/`text`）— 前端需两边兼容或统一。  
10. **systemd 文档名与 `deploy.sh` 不一致**（`qa-backend` vs `back-qa`）— 部署脚本易误操作。  
11. **`QA_DAILY_LIMIT` env 疑似未接入真正日限路径**（见 A.2）— 运营配置易误解。  
12. **服务器资源紧**（部署记录内存/swap）（`qa4_server_deploy_record.md:15`）— 再挂 4.0 应用需评估。  
13. **向量模型一致性**：qa4/ 内无模型名自证；依赖生成时 env — 见 C.2。  
14. **前端无单一 API base 配置** — 换后端成本 >「改一个配置」。

---

## 附录：本报告写作约束核对

- 仅新增本文件；未改其他文件；未执行 git 写操作。  
- 每个关键结论附路径:行号；查不到标「未找到」。
