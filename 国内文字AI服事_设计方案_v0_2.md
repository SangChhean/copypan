# 国内文字AI服事 设计文档 v0.2

> **状态：** 当前有效设计（取代 v0.1）
> **日期：** 2026-06-12
> **阶段：** 规划完成，勘察完成（任务一～六），闭环验证完成，待开工
> **目标：** 在 copypan 仓库内新增第三个独立应用（`back_cn` + `front_cn`），面向国内弟兄姊妹，
> 提供 QA 问答（全功能照搬）、PanAI 2.5、经文汇集、纲目翻译、简繁互转、资料下载六大功能。
> 新域名独立部署，仍使用现有搬瓦工 VPS 与共享基础设施（ES / Redis / Neo4j）。
>
> **v0.2 变更（闭环验证修订，13 项 + 任务六落地）：**
> - **附录 A 重写为双栏**：CN 覆盖层通过**覆盖 imported 代码读取的 QA_ 原名变量**生效
>   （v0.1 的 `CN_REDIS_PREFIX` 等命名对 imported 代码无效，属设计错误，已纠正）
> - **新增 §2.3 back_cn 初始化序列**：明确 KgRagService 单例的构造方式与启动步骤
> - **监控命名空间隔离（任务六）**：`ai_monitoring:*`、`qa:monitor:records`、`qa:ratelimit:*`
>   三处硬编码键前缀参数化（默认值不变），back_cn 设 `cn_monitoring:` / `cn:monitor:records` /
>   `cn:ratelimit:`；「改现有代码」清单从 1 处扩为 3 处（§十一）
> - **新增 §3.1 跨站共享缓存明示决策**：`kg_rag:cache:*` 与 `ai_search:translate:*` 刻意共享，
>   两条连带后果写明
> - **配额加固**：阶段0 个人日上限 20 次；ASR 个人日上限 20 次；TTS 本期仅 IP 限流（观察）；
>   `/api/qa/query` 非流式调试接口加 `X-Admin-Token` 保护（堵免配额后门）
> - **`daily_date` 改用 Asia/Shanghai**（QA 原 UTC 导致国内用户北京时间早 8 点才重置）
> - **§6.3 panai_router 路由清单补全**：英译 / 繁体 / cache_translation / format_outline_only 透传
> - **资料下载补 RFC 5987 中文文件名编码**（§8.2）
> - **部署补 certbot HTTPS 签发与续期、CN 数据备份脚本**（cn_users.db + cn_materials）（§10）
> - **QA 既有 bug 记录**：`POST /api/qa/stats/clear` 使用未初始化的 `app.state.redis_client`；
>   CN 复制 router 时修复，QA 侧列入其设计文档待办
> - **已知观察项**：双术语表（QA 172 条 / 主站 shared 482 条）导致 CN 站内繁体覆盖度不一致

---

## 〇、核心决策记录（已拍板）

| # | 决策 | 结论 |
|---|------|------|
| 1 | 端口 | 后端 **8014**（全仓库零引用），前端 dev **5176**；命名 `back_cn` / `front_cn` |
| 2 | 复用策略 | **逻辑层 import、壳层自建**：service 层 100% import 复用（主站更新自动同步）；router / auth / 配额 / 资料模块 back_cn 自建 |
| 3 | API 前缀 | **沿用原路径**（`/api/qa/*`、`/api/ai_search/*`、`/api/kg_rag/*`、新增 `/api/cn/*`），靠**域名分流**到 8014；front_qa 组件近零修改复制 |
| 4 | 配额 | 纲目制作 / 纲目翻译 / QA 问答**三组独立计数**，默认各 3 次/天；管理员 `-1` 不限；**v0.2 新增**：阶段0 与 ASR 各 20 次/天个人上限；经文汇集与简繁互转不计配额仅 IP 限流 |
| 5 | 环境变量 | 共享 `back_mic/backend/.env` + `back_cn/.env` 覆盖层；**v0.2 修正**：覆盖层直接覆盖 QA_ 等原名变量（见附录 A） |
| 6 | 大资源 | bible_data（97MB）back_cn 进程自载一份（VPS available 8.3Gi，可承受）；LSM PDF（543MB）移至共享目录，双站 Nginx alias 共用 |
| 7 | PanAI 2.5 | 2.0 管线**零改动**复用 + back_cn 新写阶段0（负担点检索式负担说明生成） |
| 8 | 资料模块 | 仅管理员上传/删除，用户登录后下载；SQLite 元数据 + Nginx X-Accel-Redirect 受保护下载 |
| 9 | 改现有代码 | **三处**键前缀参数化（默认值不变、零行为变化）：`rate_limit.py`、`monitoring.py`、`qa_service.py` 监控键（§十一） |
| 10 | 国内访问 | 搬瓦工 CN2 GIA 裸跑直连为主；备好换 IP + 备用域名两条预案；不做备案/国内 CDN（不可行）；中转层留作后手不先做 |
| 11 | 缓存共享（v0.2 明示） | `kg_rag:cache:*`、`ai_search:translate:*` **刻意跨站共享**（同管线同参数命中互惠省钱）；连带后果见 §3.1 |
| 12 | 监控隔离（v0.2） | 监控/统计键**必须隔离**（否则 CN 流量费用混入主站对账）；三处前缀参数化实现 |
| 13 | `/api/qa/query` 后门（v0.2） | 该非流式调试接口不受配额限制（QA 既有设计），CN 站保留但加 `X-Admin-Token` 保护 |

---

## 一、技术选型

| 模块 | 选型 | 说明 |
|------|------|------|
| 后端 | Python + FastAPI，端口 **8014** | 新建 `back_cn/main.py`，模式照 `back_qa` |
| 前端 | Vue 3 + Vite + Ant Design Vue，dev 端口 **5176** | 新建 `front_cn/`；**按需引入 + 路由懒加载**（境外直连必须瘦身） |
| 检索 / 重排 / 图谱 | ES 8.x / Jina Reranker / Neo4j（现有共享） | 复用 `back_shared` 与 `back_mic/backend/kg_rag/retrieval.py` |
| LLM | Claude（QA 流水线、PanAI 2.5）、Gemini（翻译、TTS） | API key 共享 `.env` |
| 用户数据 | SQLite（`back_cn/cn_users.db`）+ JWT（`CN_JWT_SECRET`） | 与主站、QA 用户体系完全隔离 |
| 缓存 | Redis；缓存前缀 `cn:cache:*`，限流 `cn:ratelimit:*`，监控 `cn_monitoring:*` / `cn:monitor:records` | 与 `qa:*`、`ai_monitoring:*` 命名空间隔离；`kg_rag:cache:*` / `ai_search:translate:*` 刻意共享（§3.1） |
| 部署 | 搬瓦工 VPS（同机），新域名独立 Nginx server 块 | HTTPS 强制（certbot），80 仅 301 |

---

## 二、总体架构

```
服务器（同一台搬瓦工 VPS）
├── 基础设施（三应用共享）
│   ├── Elasticsearch 8.x（9200）
│   ├── Neo4j 5.x（7687）
│   └── Redis（6379）
│       ├── 各站独占：ai_search:* / ai_monitoring:*（主站）
│       │            qa:cache/ratelimit/monitor（QA）
│       │            cn:cache/ratelimit/monitor + cn_monitoring:*（CN）
│       └── 跨站共享（刻意）：kg_rag:cache:* / ai_search:translate:*
│
├── back_mic（8000）→ aipansearch.org
├── back_qa （8001）→ qa.aipansearch.org
├── back_cn （8014）→ <国内站新域名>          ← 本项目
│
└── 共享数据目录
    ├── /opt/pansearch/data/lsm/           # LSM PDF（543MB，QA 与 CN 共用）
    └── /opt/pansearch/data/cn_materials/  # 资料下载模块存储
```

### 2.1 back_cn 目录结构（规划）

```
back_cn/
├── main.py                  # FastAPI 入口（8014），初始化序列见 §2.3
├── requirements.txt
├── .env                     # CN 覆盖层（见附录 A）
├── DEPLOY.md                # 照 back_qa/DEPLOY.md 模板
├── cn_users.db              # SQLite（用户 + 资料元数据同库）
├── auth.py                  # 复制改造自 back_qa/qa/auth.py（三组配额 + 两个轻量计数 + Asia/Shanghai）
├── routers/
│   ├── qa_router.py         # 复制改造自 back_qa（换 CN auth + feature 配额 + /query 加 Admin-Token + 修 stats/clear bug）
│   ├── bible_router.py      # 同上
│   ├── auth_router.py       # 同上（含分功能限额管理接口）
│   ├── tools_router.py      # 经文汇集 / 纲目翻译 / 简繁互转（自建薄壳）
│   ├── panai_router.py      # PanAI 2.5（路由清单见 §6.3）
│   └── materials_router.py  # 资料模块（用户下载 + 管理员上传/删除/分类）
└── panai/
    ├── burden_service.py    # 阶段0：负担点检索式负担说明生成（新逻辑）
    └── burden_prompts.py    # BURDEN_POINT_REWRITE_PROMPT + BURDEN_RAG_PROMPT
```

**back_cn 不含**：QA 业务逻辑（import `back_qa.qa.*`）、工具业务逻辑（import
`back_mic/backend` 各模块）、检索原语（import `kg_rag.retrieval`）、防火墙
（import `kg_rag.firewall`）。

### 2.2 sys.path 接线（沿用 QA 先例）

```python
_repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo_root))                            # back_qa 包
sys.path.insert(0, str(_repo_root / "back_mic" / "backend"))   # features/ kg_rag/ ai_search/
load_dotenv(_repo_root / "back_mic" / "backend" / ".env")      # 共享层
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)  # CN 覆盖层
```

**关键**：CN `.env` 必须在任何 back_mic / back_qa 模块 import **之前** load 完成，
因为 `ai_service` 等在 import 时即读取环境变量初始化客户端。

### 2.3 back_cn 初始化序列（v0.2 新增，Phase 1/4 验收依据）

`back_cn/main.py` 严格按以下顺序：

```
1. sys.path 接线 + load_dotenv ×2（§2.2，模块顶部，先于一切业务 import）
2. import 业务模块（此时 ai_service 单例完成模块级初始化：ES/Redis/Claude/Gemini，约 8s）
3. lifespan 启动段：
   a. es_client / neo4j_client：复用 back_qa.qa.dependencies 的
      get_es_client() / get_neo4j_client()（@lru_cache 单例）
   b. KgRagService 单例构造：
        from kg_rag.kg_rag_service import KgRagService
        app.state.kg_rag_service = KgRagService(es_client, neo4j_client)
      ——构造时自动从 Neo4j 加载概念词表；Redis 取自 ai_service.redis_client。
      不复用主站 kg_rag_router.get_service()（避免引入主站路由模块及其鉴权依赖），
      back_cn 自持单例，panai_router 经 app.state 取用
   c. load_firewall()（from kg_rag.firewall import load_firewall, match_firewall，
      QA 先例 _ensure_backend_on_path() 写法）
   d. load_bible_data(back_qa/bible_data)（同 QA lifespan，+~100MB 内存）
   e. app.state.redis_client = get_redis_client()（修复 QA stats/clear 既有 bug
      的依赖前提，见 §五）
4. include_router：qa / bible / auth / tools / panai / materials 六组
```

任何一步失败应 fail-fast（启动报错退出），不允许半残运行。

---

## 三、复用与隔离对照表

| 能力 | 复用方式 | 来源 | 主站更新后自动同步？ |
|------|---------|------|:---:|
| QA 四步流水线 / 经文通道 / 翻译 / ASR / TTS | import | `back_qa.qa.qa_service` / `bible_service` / `translation_service` / `asr_service` / `prompts` | ✅ |
| QA / Bible / Auth 路由层 | **复制改造** | `back_qa/qa/*_router.py` → `back_cn/routers/` | ❌ 手动跟（维护约定 §十三） |
| 经文汇集解析 | import | `features.bible_co.biblecollection` | ✅ |
| 纲目翻译 / 简繁互转 / DOCX 格式化 | import | `ai_search.ai_service`（`ai_service` 单例方法） | ✅ |
| PanAI 2.0 管线 | import | `kg_rag.kg_rag_service.full_query(mode="2.0")` | ✅ |
| 检索原语（bm25/dense/rrf/rerank） | import | `kg_rag.retrieval` + `kg_rag.embedding_adapter` | ✅ |
| 防火墙 | import | `kg_rag.firewall` | ✅ |
| 检索 / 重排 / Neo4j 基础 | import | `back_shared.*` | ✅ |
| 用户 / 鉴权 / 配额 | 自建 | `back_cn/auth.py` | ❌（刻意隔离） |
| 资料模块 / PanAI 2.5 阶段0 | 自建 | `back_cn/` 专属 | ❌（CN 独有功能） |
| 前端界面 | 复制改造 + 新写 | `front_qa` 组件近零修改；工具组件取自 `front_mic/src/features/` | ❌ 手动跟 |

**已知接受的成本**：import `ai_service` 触发整包模块级初始化（约 8s 启动开销）。
back_cn 进程本就需要这些客户端，接受现状；纯逻辑下沉 `back_shared` 列为二期。

### 3.1 跨站共享缓存（v0.2 明示决策）

`kg_rag:cache:{sha256}` 与 `ai_search:translate:{sha256}` 前缀在主站代码中硬编码，
back_cn 调用 `full_query` / `translate_outline` 时**与主站读写同一命名空间**。
经评估这是**收益**而非缺陷：同 query + mode + 参数走同一管线，跨站命中省钱省时。
**刻意保留共享**，并接受两条连带后果（写入两站管理员须知）：

1. 主站管理员执行 `POST /api/kg_rag/cache/clear` 会**连带清空 CN 站**的 KG-RAG 缓存
   （反之 CN 站若挂清缓存接口同理）；
2. `cache_translation` 翻译追加写入（answer_en / answer_zh_tw）两站互见——一站翻译过，
   另一站缓存命中即带译文。

与之相反，**监控/统计键必须隔离**（任务六结论：全部硬编码，env 无法覆盖），否则
CN 流量的费用与请求数会混入主站 `ai_monitoring:*` 与 QA `qa:monitor:records`，
导致主站成本对账失真、CN 管理后台无独立数据。隔离方案见 §十一改动清单。

---

## 四、用户、鉴权与配额

### 4.1 users 表（`back_cn/cn_users.db`）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `id` | INTEGER PK | — | |
| `username` | TEXT UNIQUE | — | |
| `hashed_password` | TEXT | — | bcrypt |
| `created_at` | TEXT | — | UTC |
| `daily_date` | TEXT | '2000-01-01' | 各组计数共用同一日期字段，跨天统一清零；**按 Asia/Shanghai 取「今天」**（v0.2，QA 原 UTC 会令国内用户北京时间早 8 点才重置） |
| `count_outline` / `limit_outline` | INTEGER | 0 / **3** | 纲目制作（每次 `/api/kg_rag/query` 计 1） |
| `count_translate` / `limit_translate` | INTEGER | 0 / **3** | 纲目翻译（每次 `/api/ai_search/outline_translate` 计 1） |
| `count_qa` / `limit_qa` | INTEGER | 0 / **3** | QA 问答（`/api/qa/stream` 与 `/api/qa/bible/query` 计 1） |
| `count_burden` / `limit_burden` | INTEGER | 0 / **20** | **v0.2**：阶段0 负担说明生成（轻量防滥用上限） |
| `count_asr` / `limit_asr` | INTEGER | 0 / **20** | **v0.2**：语音转写（OpenAI 按量计费，防脚本刷） |

- `limit = -1` 表示不限（管理员账户全字段 -1）
- **不计任何配额**（仅 IP 限流）：经文汇集、简繁互转、易错字检查、QA 翻译、**TTS**
  （v0.2 拍板：本期仅 IP 限流，上线后观察 MiniMax 用量再定）、反馈、资料下载、
  DOCX 格式化下载
- `count_burden` / `count_asr` 是防滥用护栏而非产品配额：前端**不展示**这两组用量，
  仅超限时 429 提示

### 4.2 核心函数（复制改造 `back_qa/qa/auth.py`）

```
check_and_increment_daily_usage(username, feature)
    # feature ∈ {outline, translate, qa, burden, asr}
    → {"allowed": bool, "used": int, "limit": int, "feature": str}
get_daily_usage(username) → {outline: {used, limit}, translate: {...}, qa: {...}}
    # 仅返回三组产品配额；burden/asr 不返回
set_user_daily_limit(username, feature, daily_limit)   # 五个 feature 均可设
create_user(username, password, limits: dict | None)
_today() → Asia/Shanghai 当日日期字符串（v0.2，替换 QA 的 UTC 写法）
```

超限返回 HTTP 429，`detail` 按功能区分文案（如「今日纲目制作次数已达上限（3次），请明天再来」）。

### 4.3 鉴权接口（`/api/cn/auth/*`，照 QA 模式）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/cn/auth/register` | 邀请码注册（公开） |
| POST | `/api/cn/auth/login` | 登录返回 JWT（`CN_JWT_SECRET` 签名，7 天） |
| GET | `/api/cn/auth/me` | 当前用户 |
| GET | `/api/cn/auth/usage` | 当日三组产品配额用量（不递增） |
| POST | `/api/cn/auth/invite` | 创建邀请码（`X-Admin-Token` = `CN_ADMIN_TOKEN`） |
| GET | `/api/cn/auth/invites` / `/users` | 管理列表 |
| DELETE | `/api/cn/auth/users/{username}` | 删除用户 |
| POST | `/api/cn/auth/users/{username}/limit` | 设置分功能限额，Body `{feature, daily_limit}`（五个 feature 均可设） |

### 4.4 限流、缓存与监控隔离（v0.2 按任务六落地）

back_cn 通过 `.env` 覆盖层设置（变量名见附录 A）：

| 类别 | back_cn 键空间 | 实现方式 |
|------|---------------|---------|
| 答案缓存 | `cn:cache:*` | 覆盖 `QA_REDIS_PREFIX`（QA 机制现成） |
| IP 限流 | `cn:ratelimit:*` | `rate_limit.py` 前缀参数化（改动 #1） |
| 主站系监控 | `cn_monitoring:*` | `monitoring.py` 前缀参数化（改动 #2） |
| QA 系监控 | `cn:monitor:records` | `qa_service.py` 监控键参数化（改动 #3） |

- 前端 token 存储 key 区分（如 `cn_token`），避免与 QA 站同浏览器互踩
- CN 管理后台的统计页读 `cn_monitoring:*` 与 `cn:monitor:records`，与主站/QA 后台
  数据完全独立

---

## 五、QA 问答（全功能照搬）

- **业务逻辑零新增**：`qa_service`（三通道流水线）、`bible_service`（经文通道）、
  `translation_service`（简繁英）、`asr_service`（ASR）全部 import
- **router 层复制改造**（`back_cn/routers/qa_router.py` 等），改动点六类：
  1. 鉴权依赖 → CN 的 JWT 校验
  2. 配额调用 → `check_and_increment_daily_usage(username, "qa")`；
     ASR 接口 → `(username, "asr")`（v0.2）
  3. 管理 token → `CN_ADMIN_TOKEN`
  4. **`POST /api/qa/query`（非流式调试接口）加 `X-Admin-Token` 保护**（v0.2，
     该接口在 QA 设计中不受配额限制，原样照搬等于免配额后门）
  5. **修复 `POST /api/qa/stats/clear` 既有 bug**：QA 原代码使用
     `request.app.state.redis_client`，但 `back_qa/main.py` lifespan 从未设置该字段
     （勘察任务六发现）。CN 版统一改用 `get_redis_client()`；back_cn lifespan 同时
     设置 `app.state.redis_client` 兜底（§2.3-e）。QA 侧此 bug 记入 QA 设计文档待办
  6. 环境变量读取 → CN 覆盖层（附录 A）
- API 路径**原样保留** `/api/qa/*`（决策三），front_qa 组件的相对路径请求无须改动
- bible_data：back_cn lifespan 自行 `load_bible_data()`（+~100MB 内存，已确认可承受）
- 监控统计：经改动 #3 写入 `cn:monitor:records`，CN 管理后台独立查看
- LSM PDF：`BibleMessage.vue` 的 `/lsm/` 与 `/lsm_mapping.json` 路径不变，由
  Nginx alias 指向共享目录（§9.3）

---

## 六、PanAI 2.5

### 6.1 定位

在 2.0 简洁管线（无 Step1/Step2/路3、FLAT prompt、放大检索参数、防火墙保留）基础上，
新增**检索式负担说明生成（阶段0）**：负担点由**用户自行输入**（1～5 个，动态增删），
每个负担点先检索职事原文 top1 段落作为依据，再生成单条负担说明（150～200 字）。
与主站情境 A/B（纯 LLM 无检索）本质不同：负担说明本身先过一遍小型 RAG，有原文锚定。

### 6.2 阶段0 管线（`back_cn/panai/burden_service.py`，新写）

```
输入：query（主题）+ outline_nature + burden_points: [str]（1~5 个）
    |
    v
对每个负担点（asyncio.gather 并发）：
  ① 轻量 Query Rewrite（新 prompt，见 6.4）
     输入：负担点 + 主题 → 输出：1 条检索式
     模型：claude-sonnet-4-6，temperature=0.2，max_tokens=200
     解析失败降级：直接用「主题 + 负担点」原文拼接作为检索式
  ② 检索（kg_rag.retrieval 原语，索引 _INDICES_BASE）：
     k=30, fetch=k*3
     bm25_search(es, q, fetch) ∥ dense_search(es, q, fetch, num_candidates=100)
       → rrf_merge(bm25[:k], dense[:k], k=60)
       → rerank(merged, q, top_n=1) → top1 段落
     rerank 异常/空结果 → 该点降级为「无参考」，warnings 追加说明
    |
    v
③ 负担说明生成（一次 LLM 调用）：
   输入：主题 + 纲目性质 + N 组（负担点 + top1 段落原文）
   Prompt：BURDEN_RAG_PROMPT（见 6.4）
   模型：claude-sonnet-4-6，temperature=0.3，max_tokens=600
   输出：单条负担说明，150~200 字
    |
    v
返回前端：负担说明（可编辑）+ 每个负担点的命中段落（出处 + 预览，前端展示）
```

阶段0 最小 import 集（勘察任务三确认）：`kg_rag.retrieval`（四原语）、
`kg_rag.embedding_adapter`（dense 路）、`es_config.es`（或 dependencies 单例）、
自建 LLM 调用封装（或复用 `_call_kg_rag_llm`）。
阶段0 **不写** `ai_monitoring:*`（CN 自有监控按需记入 `cn:monitor:records` 风格的
轻量记录，开发时定）。

### 6.3 panai_router 路由清单（v0.2 补全）

| 方法 | 路径 | 配额 | 说明 |
|------|------|------|------|
| POST | `/api/cn/panai/generate_burden` | **burden（20/天）** | 阶段0，请求 `{query, outline_nature, burden_points: [str]}`（1~5 个，每个 ≤60 字）；返回 `{burden_description, points: [{point, rewritten_query, top1: {source_zh, book_title, message_title, text_preview} | null}], warnings, elapsed_ms, cost_usd}` |
| POST | `/api/kg_rag/query` | **outline（3/天）** | 透传 `app.state.kg_rag_service.full_query(query, params, mode="2.0")`；params 固定注入 burden_description / outline_nature / depth="general"；CN 站不暴露 mode 切换（恒 2.0） |
| POST | `/api/kg_rag/cache_translation` | 不计 | 透传（翻译/繁体结果追加写共享缓存，§3.1 后果 2 即源于此） |
| POST | （纲目英译，路径与主站 2.0 前端一致） | 不计 | 透传主站对应翻译入口（开发时按 Search.vue 实际调用的接口对齐） |
| POST | `/api/ai_search/outline_to_traditional` | 不计 | 繁体转换（与工具箱共用 tools_router 亦可，二选一，避免重复挂载） |
| POST | `/api/ai_search/format_outline_only` | 不计 | DOCX 下载 |

> 开发注意：纲目英译的确切接口名以 front_mic `Search.vue`（2.0 模式）实际请求为准，
> Phase 4 开工前由 Cursor 对齐一次，避免文档臆测接口名。

### 6.4 Prompt 草案（`back_cn/panai/burden_prompts.py`，开发时打磨）

**BURDEN_POINT_REWRITE_PROMPT**（轻量改写，每负担点一次）：

```
你是职事文库检索助手。请将以下负担点结合主题，改写为一条适合全文检索的查询语句。
要求：保留负担点的核心词汇与属灵术语；补足主题中的限定语境；不展开、不引申；
只输出查询语句本身，不输出任何解释。

主题：{query}
负担点：{point}
```

**BURDEN_RAG_PROMPT**（负担说明生成，整单一次）：

```
你是纲目负担说明撰写助手。请基于下列负担点及其对应的职事信息参考段落，
为这篇纲目撰写一条负担说明。

要求：
1. 150~200 字，单段，不分点
2. 必须涵盖所有负担点的核心方向，按其内在推进次序自然衔接
3. 用词以参考段落的职事语言为据，不得使用参考段落之外的神学框架词
4. 不复述主题原句，不使用「本篇纲目」「我们将看见」等框架性套语
5. 某负担点无参考段落时，仅以负担点本身的措辞带过，不自行发挥
6. 只输出负担说明正文

主题：{query}
纲目性质：{outline_nature}

{points_block}
# 每组格式：
# 负担点{i}：{point}
# 参考段落：{top1_text}（出处：{source_zh}）  # 无参考时写「（无参考段落）」
```

风格规则参照主站 `BURDEN_DESCRIPTION_PROMPT` 的禁用框架词约定，新增第 3、5 条
「以参考段落为据」的 RAG 约束。

### 6.5 前端工作流（front_cn 纲目制作页）

```
纲目主题（必填）
纲目性质（必选：一般性/真理启示/生命经历/应用实行）

负担点输入区：
  ├── 动态输入框列表：默认 1 个，「+ 添加负担点」（上限 5），每框右侧 × 删除
  ├── 「生成负担说明」按钮（至少 1 个非空负担点才可点）
  └── 也可直接跳过，在负担说明框手填

阶段0 结果区：
  ├── 负担说明编辑框（预填 AI 结果，可改写，auto-size）
  └── 负担点命中展示：每点一张小卡（负担点 + top1 出处 + 段落预览，可折叠）

「生成纲目」（扣 outline 配额）→ 纲目结果 + 复制 / 繁体 / 英文 / DOCX 下载
顶栏显示三组用量（今日 纲目 1/3 · 翻译 0/3 · 问答 2/3）
```

---

## 七、工具箱三件套

| 工具 | 后端 import | CN 路由（沿用原路径） | 配额 |
|------|------------|----------------------|------|
| 经文汇集 | `features.bible_co.biblecollection` + `ai_service.format_english_bibco_docx` / `format_feast_outline_docx` | `POST /api/getvers`、`/api/getvers/format_download`、`format_download_zh` | 不计，IP 限流 |
| 纲目翻译 | `ai_service.translate_outline` / `translate_outline_en2zh` / `format_outline_only` | `POST /api/ai_search/outline_translate`、`format_outline_only` | **计 translate 配额**（translate 接口本身；format 下载不计） |
| 简繁互转 | `ai_service.outline_to_traditional` / `traditional_to_simplified` / `check_error_chars` | `POST /api/ai_search/outline_to_traditional` 等 | 不计，IP 限流 |

- `tools_router.py` 自建薄壳：CN 鉴权 + （翻译）配额 + 调 import 的 service，
  请求/响应模型照抄主站对应 router 的 Pydantic 定义
- 已知依赖随 sys.path 自然满足：DOCX 模板（`back_mic/backend/*.docx`，相对
  `__file__` 定位）、`shared/zh_tw_terms.json`（相对仓库根定位）——勘察任务一已确认
  均不依赖 cwd
- 纲目翻译的 tool 监控写入（`translation_zh2en` 等 `record_tool_usage`）经改动 #2
  自动落入 `cn_monitoring:*`，CN 后台可见翻译费用
- CN 站 v0.2 仍只开 **中↔英**，zh2ko / en2es 按需后加
- `biblecollection.main()` 模块级 `global bim/cim/vim` 并发不安全为主站既有现状，
  CN 沿用，列入观察项

---

## 八、资料下载模块（CN 独有，新建）

### 8.1 存储与元数据

```
/opt/pansearch/data/cn_materials/{category_dir}/{stored_name}.pdf
```

SQLite（与 cn_users.db 同库）：

```sql
CREATE TABLE material_categories (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,       -- 显示名
  dir_name TEXT NOT NULL UNIQUE,   -- 磁盘目录名（ASCII，安全）
  sort_order INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE materials (
  id INTEGER PRIMARY KEY,
  category_id INTEGER NOT NULL REFERENCES material_categories(id),
  display_name TEXT NOT NULL,      -- 用户可见文件名
  stored_name TEXT NOT NULL,       -- 磁盘文件名（uuid.pdf，防路径注入/重名）
  size_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
```

### 8.2 接口

**用户侧（已登录，不计配额）**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/cn/materials/categories` | 分类列表（含各类文件数） |
| GET | `/api/cn/materials?category_id=N` | 某分类文件列表（名称/大小/时间） |
| GET | `/api/cn/materials/{id}/download` | 校验 JWT → 返回 `X-Accel-Redirect: /protected_materials/{category_dir}/{stored_name}` |

下载响应头（v0.2 补充，中文文件名必须 RFC 5987 编码，否则部分浏览器乱码）：

```
X-Accel-Redirect: /protected_materials/{category_dir}/{stored_name}
Content-Disposition: attachment; filename*=UTF-8''{urlencode(display_name)}.pdf
Content-Type: application/pdf
```

**管理侧（`X-Admin-Token` = `CN_ADMIN_TOKEN`）**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/cn/materials/categories` | 建分类 `{name, dir_name}` |
| DELETE | `/api/cn/materials/categories/{id}` | 删空分类（非空拒绝） |
| POST | `/api/cn/materials/upload` | multipart 上传 `{category_id, file}`；仅 PDF，单文件 ≤ 200MB |
| DELETE | `/api/cn/materials/{id}` | 删除文件（磁盘 + 元数据） |

### 8.3 Nginx 受保护下载

```nginx
location /protected_materials/ {
    internal;                                  # 仅接受 X-Accel-Redirect 内部跳转
    alias /opt/pansearch/data/cn_materials/;
}
client_max_body_size 200m;                     # 管理员上传
```

大 PDF 传输由 Nginx 完成，不经 Python；下载鉴权由 FastAPI 完成。
搜索与下载统计：**二期**。

---

## 九、front_cn 前端

### 9.1 页面结构

```
#/login        登录/邀请码注册（复制 front_qa LoginPage，改 token key：cn_token）
#/             首页导航（六功能入口卡片 + 三组用量显示）
#/qa           QA 问答（复制 front_qa QAPage + BibleMessage + DebugPanel，近零修改）
#/outline      PanAI 2.5 纲目制作（新写，见 §6.5）
#/bibco        经文汇集（取自 front_mic features/bible_co 组件改造）
#/translate    纲目翻译（取自 front_mic features/outline_translate 组件，只留中↔英）
#/zh-convert   简繁互转（取自 front_mic features/zh_convert 组件）
#/materials    资料下载（新写：分类侧栏 + 文件列表 + 下载按钮）
#/admin        管理后台（复制 front_qa AdminPage 扩展：统计/邀请码/用户/分功能限额/资料管理）
```

### 9.2 复制改造检查点（勘察任务二 f + 任务五第 4 节）

- front_qa 组件：API 全相对路径零硬编码端口（良好范例），仅改 token 存储 key、
  `vite.config.js` proxy（`/api` → `http://localhost:8014`，dev 端口 5176）
- front_mic 工具组件：必须取 `src/features/` 下**正式版**组件；`components/toolbox/`
  下的测试/学生版组件（如含 `localhost:8005` 硬编码的 `ZhConvertTest.vue`）一律不取
- 性能硬要求（境外直连）：Ant Design Vue 按需引入、路由级 code-split、gzip/brotli、
  `index.html` no-cache + hash assets 长缓存（沿用主站 Nginx 约定）

### 9.3 LSM PDF 共享化（涉及 front_qa 一次性调整）

1. 服务器：PDF 移至 `/opt/pansearch/data/lsm/`
2. QA 站与 CN 站 Nginx 各加：`location /lsm/ { alias /opt/pansearch/data/lsm/; }`
3. `front_qa/public/lsm/` 从构建产物中移除（`lsm_mapping.json` 保留在 public）
4. front_cn 的 public 只放 `lsm_mapping.json` 与 `polly_replacement_map.json`

收益：磁盘不翻倍、front_cn 构建不背 543MB、PDF 一处更新两站生效。

---

## 十、部署与国内访问

### 10.1 Nginx（新域名 server 块，照 back_qa/DEPLOY.md 模板）

```nginx
server {
    listen 80;
    server_name <国内站域名>;
    return 301 https://$host$request_uri;      # 80 仅跳转
}
server {
    listen 443 ssl;
    server_name <国内站域名>;
    # ssl_certificate 由 certbot 管理（§10.4）
    root /opt/pansearch/code/front_cn/dist;
    index index.html;

    location / { try_files $uri $uri/ /index.html; }
    location = /index.html { add_header Cache-Control "no-cache"; }
    location /assets/ { expires 1y; add_header Cache-Control "immutable"; }

    location /api/ {                     # 决策三：整体反代，路径原样
        proxy_pass http://127.0.0.1:8014;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;         # 同 QA；SSE 流式依赖
        proxy_buffering off;             # SSE 必需
    }
    location /lsm/ { alias /opt/pansearch/data/lsm/; }
    location /protected_materials/ { internal; alias /opt/pansearch/data/cn_materials/; }
    client_max_body_size 200m;
}
```

### 10.2 启动脚本

`start_cn.bat` 照 `start_qa.bat`：`uvicorn back_cn.main:app --host 127.0.0.1 --port 8014`
+ `front_cn` `npm run dev -- --port 5176`；配套 `stop_cn.bat` / `status_cn.bat`。

### 10.3 国内访问预案（决策十）

| 层级 | 措施 | 状态 |
|------|------|------|
| 主路 | 搬瓦工 CN2 GIA 直连 + 强制 HTTPS + 域名命名中性化 | 上线即用 |
| 预案一 | 搬瓦工付费换 IP + DNS 切换（被墙最常见恢复路径，小时级） | 预案 |
| 预案二 | 注册 1~2 个备用域名；front_cn API 地址不硬编码域名（相对路径已天然满足） | 上线前注册 |
| 后手 | 香港 CN2 小 VPS 反代中转 | 不先做，出问题再上 |
| 不做 | ICP 备案 / 国内 CDN（宗教内容备案不可行） | 已排除 |

### 10.4 HTTPS 证书（v0.2 新增）

- certbot 为新域名（含备用域名）签发 Let's Encrypt 证书，`certbot --nginx` 自动改写
  server 块；`systemctl status certbot.timer` 确认自动续期已启用
- 备用域名预先签好证书，切换时仅改 DNS 即可

### 10.5 备份（v0.2 新增）

现有备份目录 `/opt/pansearch/backups`，新增两项 CN 资产纳入每日备份脚本：

| 资产 | 路径 | 方式 |
|------|------|------|
| 用户库 + 资料元数据 | `back_cn/cn_users.db` | `sqlite3 .backup` 快照（避免热拷贝损坏） |
| 资料文件 | `/opt/pansearch/data/cn_materials/` | rsync 增量 |

`qa_users.db` 是否已在现有备份内一并核查（部署日检查项）。

### 10.6 内存评估

当前 VPS：total 23Gi，available 8.3Gi。back_cn 预计常驻 ≈ 0.5~1Gi（bible_data
~100MB + ai_service/QA 各客户端 + FastAPI 本体），余量充足。**观察项**：Swap 已用
904Mi/1Gi，提示历史上有过内存峰值——上线后用 `free -h` + 监控观察一周，必要时给
三个 uvicorn 进程配 systemd `MemoryMax` 或扩 Swap。

---

## 十一、对现有代码的全部改动（控制清单，v0.2 扩为三处参数化 + 两处部署层）

| # | 文件 | 改动 | 风险 |
|---|------|------|------|
| 1 | `back_qa/qa/rate_limit.py:38` | 限流 key 前缀参数化：`os.getenv("QA_RATELIMIT_PREFIX", "qa:ratelimit:")` | 零（默认行为不变） |
| 2 | `back_mic/backend/ai_search/monitoring.py:10-12,40-43` | 四个键常量前缀参数化：`os.getenv("AI_MONITORING_PREFIX", "ai_monitoring:")`，`KEY_STATS` / `KEY_DAILY_PREFIX` / `KEY_ERRORS` / `KEY_RETRIEVAL_LOG` 改为前缀拼接 | 零（默认行为不变；主站 stats 路由经 `get_monitoring` 取键，无需改） |
| 3 | `back_qa/qa/qa_service.py:272` | `_MONITOR_KEY = os.getenv("QA_MONITOR_KEY", "qa:monitor:records")`；`qa_router.py:597-613` 两处读写同步取该值 | 零（默认行为不变） |
| 4 | `front_qa` 构建/Nginx | LSM PDF 移出 public 改共享 alias（§9.3） | 低（部署层，一次性） |
| 5 | （服务器）Nginx | 新增 CN server 块 + QA 站 `/lsm/` alias + certbot | 低 |

三处代码改动同构（环境变量 + 默认值不变），建议一次提交，提交信息注明
「为 back_cn 命名空间隔离做准备，主站/QA 零行为变化」。
除此之外**不动 back_mic、back_qa、back_shared 任何业务代码**。

**连带记录**：QA 既有 bug（`stats/clear` 的 `app.state.redis_client` 未初始化）
**不在本项目内修 QA 侧**（控制改动面），仅在 CN 复制版修复；QA 设计文档下次更新时
列入其待办。

---

## 十二、开发阶段规划

### Phase 1：骨架与鉴权
back_cn 入口（§2.3 初始化序列）+ sys.path 接线 + CN auth（五组计数字段 +
Asia/Shanghai）+ auth_router + start_cn.bat + **三处键前缀参数化（§十一 #1~#3，
一次提交）**
验收：8014 起服务且 fail-fast 生效；注册/登录/usage 通；五组配额 429 文案正确；
主站/QA 在默认 env 下行为零变化（回归点：`qa:ratelimit:`、`ai_monitoring:`、
`qa:monitor:records` 键名不变）

### Phase 2：QA 全功能搬运
qa/bible router 复制改造（含 `/query` Admin-Token、stats/clear 修复、ASR 配额）+
bible_data lifespan + front_cn 复制 QAPage 等组件
验收：CN 域名（本地 5176）下 QA 三通道、翻译、TTS、ASR、反馈全通；配额计 qa/asr 组；
监控写入 `cn:monitor:records` 且 QA 站 `qa:monitor:records` 无 CN 流量混入

### Phase 3：工具三件套
tools_router + front_cn 三个工具页（取 features/ 正式版组件）
验收：经文汇集中英 + DOCX、纲目翻译中↔英 + translate 配额、简繁互转 + 易错字；
翻译费用出现在 `cn_monitoring:*` 而非主站 `ai_monitoring:*`

### Phase 4：PanAI 2.5
burden_service + burden_prompts + panai_router（§6.3 全清单，开工前对齐英译接口名）+
前端纲目制作页
验收：阶段0（多负担点 → top1 展示 → 150~200 字负担说明，burden 配额 20）→
2.0 生成（outline 配额）→ 繁体/英译/cache_translation/DOCX 闭环；
KG-RAG 缓存与主站互通命中（§3.1 验证：主站生成过的 query CN 站秒回）

### Phase 5：资料模块 + 管理后台
materials 表 + 上传/下载/分类接口 + X-Accel-Redirect（RFC 5987 文件名）+
AdminPage 扩展（统计读 CN 命名空间）
验收：管理员传 PDF → 用户分类浏览下载（中文文件名不乱码）；未登录下载 401；
internal location 直接访问 404

### Phase 6：部署上线
DEPLOY.md + Nginx + certbot（含备用域名）+ LSM 共享化 + 备份脚本（§10.5）+
备用域名注册 + 内存观察一周

---

## 十三、文档维护约定（新增条款）

1. 本文件随 back_cn / front_cn 结构变动同步更新（同主仓约定）
2. **主站作为被依赖方的义务**：修改 `features/*` service、`ai_service` 公开方法、
   `kg_rag_service.full_query`、`back_qa/qa` 各 service 的**函数签名或行为**时，
   必须把 back_cn 当作调用方检查；仓库结构重构（如再来一次 v6.7）必须同步修正
   back_cn 的 sys.path / import
3. **router 手动同步清单**：back_qa 新增/修改路由后，评估是否同步到
   `back_cn/routers/`，在两边设计文档变更记录中互相注明
4. **禁止复制业务逻辑**：back_cn 需要主站某段逻辑时，只允许 import 或推动下沉
   `back_shared`，不允许复制粘贴（testD 双轨并存为刻意隔离特例，不得效仿）
5. **共享键空间公约（v0.2）**：`kg_rag:cache:*`、`ai_search:translate:*` 为跨站共享，
   任何一站清理这两类缓存前须知会另一站管理员；新增 Redis 键一律带本站前缀，
   禁止再引入无前缀/硬编码跨站键

---

## 附录 A：环境变量（v0.2 重写为双栏）

### A.1 覆盖 imported 代码的原名变量（back_cn/.env，关键：必须用原变量名才生效）

```bash
# —— QA 系（back_qa.qa.* 读取）——
QA_REDIS_PREFIX=cn:cache:            # 答案缓存隔离
QA_RATELIMIT_PREFIX=cn:ratelimit:    # 改动#1 生效后
QA_MONITOR_KEY=cn:monitor:records    # 改动#3 生效后
QA_CACHE_TTL=259200                  # 可按需独立
QA_ES_INDEX=<默认同 QA，按需覆盖>
QA_STEP1_MODEL=<默认同 QA>
QA_RATE_LIMIT_PER_MINUTE=15

# —— 主站系（ai_search / kg_rag 读取）——
AI_MONITORING_PREFIX=cn_monitoring:  # 改动#2 生效后
# KG_RAG_ES_INDEX 不覆盖（与主站同索引，保证 kg_rag:cache 共享命中有效）
```

> 注意：QA_JWT_SECRET / QA_ADMIN_TOKEN / QA_PORT **不需要覆盖**——back_cn 不使用
> back_qa 的 auth 与入口（自建 CN auth），这三个变量在 back_cn 进程中无消费方。

### A.2 back_cn 自建代码读取的 CN_ 变量

```bash
# 必填
CN_PORT=8014
CN_JWT_SECRET=<32字节随机hex，独立生成>
CN_ADMIN_TOKEN=<独立管理密钥>

# 配额默认值（可省略）
CN_DAILY_LIMIT_OUTLINE=3
CN_DAILY_LIMIT_TRANSLATE=3
CN_DAILY_LIMIT_QA=3
CN_DAILY_LIMIT_BURDEN=20
CN_DAILY_LIMIT_ASR=20

# 资料模块
CN_MATERIALS_DIR=/opt/pansearch/data/cn_materials
CN_MATERIALS_MAX_MB=200
```

### A.3 沿用共享 .env、不重复配置

基础设施（ES_* / REDIS_* / NEO4J_*）与全部 API key（CLAUDE / GEMINI / OPENAI /
MINIMAX / OPENROUTER / JINA）。

## 附录 B：已知观察项与待办

| 事项 | 类型 | 优先级 |
|------|------|--------|
| 备用域名注册（1~2 个）+ 预签证书 | 待办 | 上线前 |
| translate / zh_convert / format 纯逻辑下沉 back_shared | 待办 | 二期 |
| 资料模块搜索 + 下载统计 | 待办 | 二期 |
| TTS 个人上限（本期仅 IP 限流，观察 MiniMax 用量后定） | 观察 | 上线后 |
| 双术语表覆盖度不一致：QA 流水线繁体输出用 back_qa 副本（172 条），简繁互转工具用 shared/（482 条）——CN 站内两处繁体效果可能不一致；统一方案（QA 切 shared 版）留待 QA 侧评估 | 观察 | 二期 |
| biblecollection 模块级 global 并发安全 | 观察 | 主站既有 |
| QA `stats/clear` app.state bug（QA 侧） | 移交 | QA 文档待办 |
| 内存监控（Swap 历史占用） | 观察 | 上线后一周 |
| 香港中转层 | 后手 | 按需 |

---

*最后更新：2026 年 6 月 12 日（v0.2：闭环验证修订——附录 A 双栏重写、初始化序列、
监控命名空间三处参数化、共享缓存明示、配额加固、Asia/Shanghai、panai 路由补全、
RFC 5987、certbot 与备份）*
