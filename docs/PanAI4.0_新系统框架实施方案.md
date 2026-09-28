# PanAI 4.0 新系统框架实施方案

> 版本：2026.09.25 初稿
> 用途：给 Srey、Claude 与 Cursor 共同依据的实施方案。每一步实施指令都以本文件为准；各节标【待与 Cursor 确认】的地方，实施前先与 Cursor 讨论定案，再回填本文件。
> 对外版本：《【2026.09.25】PanAI 4.0 新系统框架搭建方案》（已获领导认可）。本文件是它的技术展开。

---

## 一、背景与总原则

1. **3.5 与 4.0 并存、互不影响**
   - 现有首页标为"PanAI 4.0"的模式实质是 3.5，更名为 3.5。
   - 真正的 4.0 另建：独立后端模块、独立前端页面、独立图谱数据库。
   - **不修改 3.5 的任何逻辑**（第一步更名除外，只改版本标识与显示文字）。
2. **测试台先放工具箱**：4.0 以工具箱中的"PanAI 4.0 测试台"存在，首页不变；整条流水线测试稳定后再转首页。
3. **先搭全框架，再逐段填充**：界面上整条流水线一次画好；本期只接通"主题 → 负担说明 → 龙骨"与"对照原纲目诊断"，其余阶段显示为"检索（待设计）""生成（待设计）""评估（待设计）"，不接后端。
4. **模型**：各步统一使用 Opus 5.5（`claude-opus-5-5`），不联网、不带任何工具。
5. **Prompt 管理**：四份 Prompt 集中存放在代码中，每份带版本号；修改一律经 Cursor 改代码，**页面上不能编辑 Prompt**；每次运行记录所用的 Prompt 版本。
6. **用语**：图谱节点上的"属性"一律称"**标注**"（领导要求，因与职事用法不同）。代码层面仍是 Neo4j 的 property，指令中写作"标注（即 Neo4j 节点 property）"。
7. **命名**：图谱节点、关系、标注的命名一律按《名称对照表》（见第九节）。
8. **每一步完成后都要能独立验证**；每一步都在本地先跑通，再部署到服务器。

---

## 二、实施顺序总表

| 步 | 内容 | 依赖 | 完成标准 |
|---|---|---|---|
| 1 | 3.5 更名 | 无 | 首页与 KgRagTest 显示"PanAI 3.5"，选 3.5 时仍走全索引与原 V4 prompt，结果与更名前一致 |
| 2 | 后端骨架 | 无 | 用一个测试用假 prompt 跑通"提交任务 → 后台逐步调用 Opus 5.5 → 每步写入 SQLite → 轮询查进度" |
| 3 | 接上四份 Prompt | 第 2 步；四份 Prompt 定稿文字 | 单篇可跑通负担说明、龙骨；附原纲目时可跑通诊断一、诊断二；支持从指定步骤重跑 |
| 4 | 前端测试台 | 第 2、3 步的接口 | 页面可填多行（篇题 + 原纲目）、保存题组、运行、看进度、看每篇详细结果、查历史 |
| 5 | 批量与导出 | 第 4 步 | 多篇依次跑完；可导出 docx（每篇一节，内容完整） |
| 6 | 4.0 专用图谱 | Sila 姊妹提供 2372 真理要点与分类资料；旧词对应文档 | 新容器运行；节点、分类关系、迁移数据按规则导入并通过核对 |

- 周末目标：完成第 1–4 步，下周开始单篇测试；第 5 步尽量完成。
- 第 6 步与第 1–5 步互不依赖，资料到位即可并行。
- 四份 Prompt 转成代码文字（第 3 步的前置）与第 6 步，**等 Srey 通知再开始**。

---

## 三、第一步：3.5 更名

### 3.1 改动原则
- 界面文字与系统内部的 `mode` 值**一并**由 `"4.0"` 改为 `"3.5"`，一次改干净，避免"4.0"在代码中两义并存。
- 3.5 的功能与输出不变：仍使用 `_INDICES_FULL` 与原 `STEP5_GENERATION_V4` / `STEP5_GENERATION_FLAT_V4` 两份 prompt。
- **Prompt 正文不动**（`prompts.py` 665 行正文中的 `【V4_MARK_0】` 等会送进模型的文字，保持原样）。
- 常量名 `STEP5_GENERATION_V4` / `_FLAT_V4` 是否改名为 `_V35`：【待与 Cursor 确认】（纯改名重构，不影响行为；倾向改，以免日后误认）。

### 3.2 改动位置（依第一次勘探结果，实施前 Cursor 再核对一次行号）

| 文件 | 位置 | 改动 |
|---|---|---|
| `back_mic/backend/kg_rag/kg_rag_service.py` | 1144–1149 | `mode == "4.0"` → `"3.5"`（索引分叉） |
| 同上 | 1804–1812、1828–1836 | `mode == "4.0"` → `"3.5"`（Step5 prompt 分叉） |
| `front_mic/frontend/src/components/Search.vue` | 143（注释）、144（取值集合）、2014（按钮数组） | `"4.0"` → `"3.5"`；注释改为"3.5 全索引" |
| `front_mic/frontend/src/components/toolbox/KgRagTest.vue` | 231（注释）、232（取值）、1409（按钮数组） | 同上 |

- 按钮文案 `PanAI {{ m }}`、完成横幅 `Pan AI ${aiMode}` 由数组值带出，不需单独改。
- `QueryRequest.mode` 默认值 `"3.0"` 不变；`extract_concepts`、`prompt_preview`、CN 站不受影响。
- `llm_evaluator.py` 34 行的 `4.00` 是 Haiku 单价，与版本无关，**不要改**。

### 3.3 影响
- Redis 中 `mode="4.0"` 的旧缓存对不上新 key，7 天内自然过期；可选择部署后调用 `POST /api/kg_rag/cache/clear` 一次清掉。
- localStorage 历史（`kg_rag_history`）不含 mode，不受影响。

### 3.4 验证
1. 全仓库（排除 node_modules、dist、frontend/assets）再搜 `"4.0"`、`'4.0'`、`mode == "4.0"`，确认只剩 `llm_evaluator.py` 的单价。
2. 首页与 `#/kg-rag-test` 版本按钮显示 2.0 / 3.0 / 3.5。
3. 选 3.5 跑同一主题，确认 Step3 检索使用 9 个索引、Step5 使用原 V4 prompt（看 debug 输出或日志）。
4. 选 3.0 跑一次，确认行为不变。

---

## 四、第二步：后端骨架

### 4.1 模块位置与结构
新建 `back_mic/backend/panai4/`，**不 import `kg_rag` 的业务逻辑**（`kg_rag_service`、`prompts` 等）。

```
back_mic/backend/panai4/
├── __init__.py
├── router.py          # APIRouter，前缀 /api/panai4
├── config.py          # 模型名、超时、重试、价格、DB 路径、Neo4j V4 连接变量
├── llm.py             # 模型调用层（Anthropic SDK）
├── db.py              # SQLite 初始化与读写
├── runner.py          # 后台任务：逐篇、逐步执行
├── pipeline.py        # 各步骤定义（输入组装、调用、输出解析）
├── prompts/
│   ├── __init__.py    # 注册表：步骤 → 当前使用的 Prompt 与版本
│   ├── prompt1_burden.py
│   ├── prompt2_skeleton.py
│   ├── prompt3_orig_skeleton.py
│   └── prompt4_diagnosis.py
├── export_docx.py     # 第五步
└── graph_client.py    # 第六步之后（连接 4.0 图谱；本期不使用）
```

- 在 `back_mic/backend/main.py` 32–45 行附近导入、394–423 行附近 `app.include_router`（放在静态前端挂载之前）。
- 目录与文件名为初拟，【待与 Cursor 确认】。

### 4.2 模型调用层（`llm.py`）
- 模型：`claude-opus-5-5`，常量放 `config.py`。
- API key：读 `CLAUDE_API_KEY`（与项目其余部分一致）。
- **不传** `temperature`、`top_p`、`top_k`；**不传任何 tools**（不联网）。
- `max_tokens`：按步骤在 `config.py` 设定，【待与 Cursor 确认】具体数值。
- 单次调用超时：建议 600 秒；失败重试：对 429、5xx、网络超时重试 2 次，指数退避；其余错误直接记为失败。
- 每次调用记录：input_tokens、output_tokens、耗时、费用。
- 费用：Opus 5.5 单价写成 `config.py` 常量，**数值由 Srey 查证后填入**，不要沿用 `llm_pricing.py` 的前缀兜底。
- 服务器 anthropic SDK 版本为 0.105.2；本地版本【待 Cursor 核对】，两边保持一致。

### 4.3 Prompt 版本管理（`prompts/`）
- 每份 Prompt 一个文件，内含：`VERSION`（如 `"v0.3"`）、`SYSTEM`（如有）、`USER_TEMPLATE`、说明注释（来源文档名、定稿日期）。
- `prompts/__init__.py` 维护注册表：每个步骤当前使用哪一份、哪个版本。
- 同一份 Prompt 改版时：新增版本号，旧版本可保留在同文件或存档文件中（【待与 Cursor 确认】存放方式）。
- 运行时把"步骤 + Prompt 版本 + 实际送出的完整 prompt 文字"一起存入数据库，保证可追溯。

### 4.4 存储：SQLite
- 独立数据库文件，默认 `back_mic/backend/panai4.db`，可用环境变量 `PANAI4_DB_PATH` 改路径（仿照圆桌 `ROUNDTABLE_DB_PATH` 做法）。
- 该文件不进 git（加入 `.gitignore`）；服务器上放在不会被 `deploy.sh` 覆盖的位置，【待与 Cursor 确认】路径（建议 `/opt/pansearch/data/panai4/panai4.db`）。

表结构初拟（【待与 Cursor 确认】）：

| 表 | 用途 | 主要字段 |
|---|---|---|
| `topic_sets` | 题组 | id, name, created_at, updated_at |
| `topic_set_items` | 题组内每篇 | id, set_id, position, title, original_outline（可空） |
| `runs` | 一次运行（单篇或多篇） | id, created_at, status, topic_set_id（可空）, parent_run_id（重跑来源，可空）, start_step（从哪一步开始）, note |
| `run_items` | 运行中的每一篇 | id, run_id, position, title, original_outline（可空）, outline_hash（可空）, status, error |
| `step_results` | 每篇每一步的结果 | id, run_item_id, step, prompt_name, prompt_version, model, prompt_text（实际送出）, output_text, input_tokens, output_tokens, cost_usd, duration_ms, status, error, reused_from（沿用自哪条结果，可空）, created_at |
| `orig_skeleton_cache` | 诊断一（原纲目的龙骨）复用 | outline_hash, prompt3_version, output_text, source_step_result_id, created_at；（outline_hash, prompt3_version）唯一 |

- `step` 取值：`burden`（步骤一）、`skeleton`（步骤二）、`orig_skeleton`（诊断一）、`diagnosis`（诊断二）。
- `status` 取值：`pending` / `running` / `done` / `failed` / `skipped` / `interrupted`。

### 4.5 后台任务与轮询
- 所有生成（单篇、多篇）都走同一机制：
  1. 前端 `POST /api/panai4/runs` 提交，立即拿到 `run_id`；
  2. 后端用 `asyncio.create_task` 在进程内后台执行，逐篇、逐步调用模型；**每完成一步立即写入 SQLite**；
  3. 前端每 3 秒 `GET /api/panai4/runs/{run_id}` 查进度，已完成的步骤先显示。
- 这样每个请求都很短，不受 Nginx 超时影响（服务器主站 `/api/` 为 600 秒），也不需改 Nginx。
- 并发：同一时间只跑一个 run、篇与篇依次执行（先求稳，避免 API 限流）；【待与 Cursor 确认】是否允许同一篇内步骤之外的并行。
- 服务重启：启动时把状态为 `running` 的 run / run_item / step 标为 `interrupted`；已完成的步骤保留。前端可对中断的 run 执行"从中断处继续"（沿用已完成的步骤）。
- 某一篇某一步失败：记录错误，该篇后续步骤标 `skipped`，**不影响其他篇**继续执行。

### 4.6 接口初拟（【待与 Cursor 确认】）

| 方法与路径 | 用途 |
|---|---|
| `POST /api/panai4/runs` | 提交运行：多行 `{title, original_outline?}`，或 `topic_set_id`；可选 `parent_run_id` + `start_step`（重跑） |
| `GET /api/panai4/runs` | 运行历史列表 |
| `GET /api/panai4/runs/{run_id}` | 运行详情与进度（含每篇每步结果） |
| `POST /api/panai4/runs/{run_id}/resume` | 从中断/失败处继续 |
| `GET /api/panai4/runs/{run_id}/export` | 导出 docx（第五步） |
| `GET/POST/PUT/DELETE /api/panai4/topic_sets` | 题组的列表、新建、修改、删除 |
| `GET /api/panai4/prompts` | 只读：列出当前各步骤使用的 Prompt 名称与版本（页面显示用，不可编辑） |

- 登录保护：比照 `KgRagTest` 所用接口的做法（`test_token` 等），【待 Cursor 核对现有机制后确认】。

### 4.7 第二步验证
- 用一份测试用假 prompt（例如"请用一句话复述题目"）跑通：提交 → 查进度 → 结果写入 SQLite → 查询得到。
- 故意制造一次失败（例如错误的模型名）确认错误被记录、其他篇继续。
- 运行中重启后端，确认状态变为 `interrupted`，且可以继续。
- 确认调用未传 temperature、未带 tools。

---

## 五、第三步：接上四份 Prompt

### 5.1 四份 Prompt 与版本

| 步骤 | 名称 | Prompt | 版本（暂定，之后会迭代） | 输入 | 输出 |
|---|---|---|---|---|---|
| 步骤一 | 负担说明 | Prompt1 | v0.3（结构调整版） | 篇题 | 【职事界定】【真理脉络】【负担说明】三段 |
| 步骤二 | 龙骨 | Prompt2 | 现行版 | 负担说明（**只传【负担说明】段**） | 龙骨 6–9 条 |
| 诊断一 | 原纲目的龙骨 | Prompt3 | 现行版（不改） | 原纲目全文 | 原纲目的龙骨 |
| 诊断二 | 两轴诊断 | Prompt4 | 新版（含规则③扩展） | 生成的龙骨 + 原纲目的龙骨 | 逐项两条差距：与原纲目的龙骨对比的差距、与六阶段满分定义的差距 |

- **转换方式**：由 Srey 提供四份定稿的纯文字，Claude 整理后交 Cursor 逐字写入 `prompts/`；不得凭记忆改写或精简。转换完成后逐字比对一次。
- **步骤一输出解析**：完整三段全部存档、全部在页面显示；按段落标记取出【负担说明】段传给步骤二。若解析不到标记，该篇该步标 `failed` 并保留原始输出。
- 各 Prompt 中需要替换的占位字段（篇题、负担说明、龙骨、原纲目）与具体输出格式，在转换时依 docx 原文确定。

### 5.2 何时跑诊断
- 原纲目**留空**：只跑步骤一、二；诊断一、二标 `skipped`。
- 原纲目**有内容**：步骤二完成后跑诊断一、诊断二。

### 5.3 诊断一复用
- 以"原纲目全文的 hash + Prompt3 版本"为键，存入 `orig_skeleton_cache`。
- 键相同则直接取用，不再调用模型（`step_results.reused_from` 记录来源）。
- 原纲目内容或 Prompt3 版本改变时，才重新生成。
- 用意：诊断二的对比基准保持固定，也节省时间与费用。
- 页面上提供"强制重新生成原纲目的龙骨"的选项，【待与 Srey 确认】是否需要。

### 5.4 从指定步骤重跑
提交时带 `parent_run_id` 与 `start_step`，起点之前的步骤沿用上次结果（记录 `reused_from`），起点及之后重新生成：

| 改了哪份 Prompt | 起点 | 沿用 | 重新生成 |
|---|---|---|---|
| Prompt1 | 步骤一 | 诊断一（复用缓存） | 步骤一、步骤二、诊断二 |
| Prompt2 | 步骤二 | 步骤一、诊断一 | 步骤二、诊断二 |
| Prompt3 | 诊断一 | 步骤一、步骤二 | 诊断一、诊断二 |
| Prompt4 | 诊断二 | 步骤一、步骤二、诊断一 | 诊断二 |

- 用意：Opus 输出每次都有差异，固定前面步骤，比较两版 Prompt 时只有改动的那一步在变。

### 5.5 第三步验证
- 单篇（2026 秋长任一篇）：留空原纲目跑一次、附原纲目跑一次，四步输出格式正确。
- 同一原纲目再跑一次，确认诊断一直接复用、未调用模型。
- 以"从步骤二重跑"测一次，确认步骤一内容与上次完全相同。
- 抽查存档的 `prompt_text` 与 Prompt 定稿逐字一致。

---

## 六、第四步：前端测试台

### 6.1 入口
- 新页面 `front_mic/frontend/src/components/toolbox/PanAI4Test.vue`（名称【待与 Cursor 确认】）。
- 路由 `#/panai4-test`，`meta.requiresAuth: true`。
- 工具箱 `ToolBox.vue` 的"图谱测试"组加一张卡片"PanAI 4.0 测试台"。
- UI 使用 ant-design-vue（项目现用 4.2.6）。

### 6.2 页面布局（由上而下）
1. **流水线示意**：主题输入 → 负担说明 → 龙骨 → 检索（待设计）→ 生成（待设计）→ 评估（待设计）；另有"对照原纲目诊断"。已接通的阶段正常显示，待设计的灰色显示、不可点。
2. **当前 Prompt 版本**（只读）：列出四步各用哪份 Prompt、哪个版本。
3. **输入区**：
   - 每行一篇：左边"篇题"单行输入框，右边"原纲目"多行文字框（手动贴全文，可留空），行尾"−"删除该行。
   - 下方"＋ 增加一篇"按钮。
   - 题组：可"存为题组"（输入名称）、"载入题组"（下拉选择）、修改后"另存"或"更新"。
4. **运行控制**：
   - "开始运行"。
   - 重跑：从历史选一次运行，选择"从哪一步开始重跑"（步骤一 / 步骤二 / 诊断一 / 诊断二）。
   - 中断的运行显示"继续"。
5. **进度**：每篇一行，显示各步骤状态（等待 / 进行中 / 完成 / 失败 / 跳过 / 沿用）；每 3 秒刷新，全部结束后停止轮询。
6. **结果**：每篇一张可展开的结果卡，显示完整内容：
   - 篇题；
   - 负担说明（【职事界定】【真理脉络】【负担说明】三段全文）；
   - 龙骨；
   - 原纲目的龙骨（有原纲目时）；
   - 诊断（有原纲目时）；
   - 每步的 Prompt 版本、耗时、费用。
   - **不做整批总表**（领导要求看每一篇的详细内容）。
7. **历史**：历次运行列表（时间、篇数、状态、Prompt 版本），点开查看结果。

### 6.3 第四步验证
- 未登录访问 `#/panai4-test` 会跳到登录页。
- 填 2 行（一行附原纲目、一行留空）运行，进度与结果正确显示。
- 关闭浏览器再打开，历史中可看到该次运行，结果完整。
- 保存题组、重新载入、修改、另存均正常。

---

## 七、第五步：批量与导出

### 7.1 批量
- 批量即多行输入，机制与单篇相同（第四节 4.5）；篇与篇依次执行，某篇失败不影响其他篇。
- 典型用法：载入"2026 秋长 9 篇"题组 → 运行 → 改 Prompt 后从相应步骤重跑。

### 7.2 导出 docx
- 一次运行导出一个 docx，每篇一节，内容完整。
- 文件开头：运行时间、各步骤 Prompt 名称与版本、模型。
- 每篇一节：篇题（标题）→ 负担说明（三段）→ 龙骨 → 原纲目的龙骨 → 诊断。
- 字体 Microsoft YaHei；用 `python-docx` 生成。
- 版面细节参照目前测试文档的结构，【待与 Srey 确认】样式细节。

### 7.3 第五步验证
- 以 2026 秋长 9 篇整组跑一次，全部完成；导出 docx 打开检查内容完整、各篇齐全。

---

## 八、第六步：4.0 专用图谱

### 8.1 容器（服务器与本地规格一致）

| 项 | 定案 |
|---|---|
| 容器名 | `neo4j-v4` |
| 镜像 | `neo4j:5.26.23`（Community，与服务器现有 Neo4j 一致；本地现为 `neo4j:5`，本地新容器同样指定 5.26.23） |
| 端口 | `7475:7474`（浏览器）、`7688:7687`（Bolt），对外开放，靠密码保护 |
| 数据卷 | 具名卷 `neo4j_v4_data` → `/data`、`neo4j_v4_logs` → `/logs` |
| 内存 | heap 1G（initial = max），pagecache 512M，经环境变量设定 |
| 重启策略 | `unless-stopped` |
| 密码 | 足够长的随机密码，**不与 3.5 的 Neo4j 共用** |

- 服务器端口 7475、7688 已确认未被占用；服务器可用内存约 14G，余量充足。
- 创建容器是一次性手动操作，完整 `docker run` 命令记录在本文件附录（实施时补上）。
- 启动脚本：`deploy.sh` 与 `start_all.bat` 加上"`neo4j-v4` 未运行则 `docker start neo4j-v4`"。

### 8.2 连接
- 环境变量：`NEO4J_V4_URI`、`NEO4J_V4_USER`、`NEO4J_V4_PASSWORD`（不可沿用 `NEO4J_URI` 等，否则会连到 3.5 的库）。
- `.env.example` 补上这三项说明。
- 连接程序放 `panai4/graph_client.py`，可参考 `kg_rag/neo4j_client.py` 的写法（零业务依赖），但读取 V4 变量。

### 8.3 节点

| 节点 | 数量 | 来源 |
|---|---|---|
| 真理要点 `Truth_Point` | 2372 | Sila 姊妹提供的新词表 |
| 主干 `Trunk` | 7 | 七大类 |
| 枝子 `Branch` | 91 | 九十一小类 |
| 经文 `Scripture` | — | 从 3.5 图谱迁移 |

- 第一期真理要点只填中文名与分类归属，其余标注**不预先铺设**，之后用到哪一项再逐项加。
- 唯一性约束：`Truth_Point`、`Trunk`、`Branch` 的名称唯一；`Scripture` 沿用 3.5 的唯一键。【待与 Cursor 确认】标注字段名。

### 8.4 分类关系

| 关系 | 方向 | 含义 |
|---|---|---|
| `BELONGS_TO_TRUNK` | 真理要点 → 主干 | 属于主干 |
| `OF_BRANCH_DIRECTLY` | 真理要点 → 枝子 | 直接属于（主要枝子） |
| `OF_BRANCH_INDIRECTLY` | 真理要点 → 枝子 | 间接属于（次要枝子） |
| `GRAFTING` | 枝子 → 主干 | 接枝 |

### 8.5 旧数据迁移（从 3.5 图谱）
- 按已整理好的对应文档，把 3.5 的 Concept 对应到 2372 个真理要点：直接对应 / 改名对应 / 删除。
- 迁移内容：
  - 全部 `Scripture` 节点；
  - `SUPPORTED_BY`（真理要点 → 经文）；
  - `LOCATED_IN`（真理要点 ↔ 真理要点，如"重生 LOCATED_IN 人的灵"）；
  - 其余旧关系（`LEADS_TO`、`EXPERIENCES`、`PRACTICED_AS`、`CONTAINS`、`OPPOSES`）。
- 规则：两端都能对应上的关系照搬（改名的按新名接上）；任一端被删除的关系不迁移。
- **不加来源标记**（旧关系除 SUPPORTED_BY 外之后不再做）。
- **不迁移** `greek_terms`，原文之后重新制作。
- 迁移只读 3.5 的库，**不对 3.5 的库做任何写入**。

### 8.6 第六步验证
- 节点数：Truth_Point 2372、Trunk 7、Branch 91、Scripture 与 3.5 一致。
- 每个真理要点恰有一条 `BELONGS_TO_TRUNK`、至少一条 `OF_BRANCH_DIRECTLY`；每个枝子恰有一条 `GRAFTING`。
- 迁移报告：各关系类型的"3.5 原有数 / 迁移数 / 因删除而舍弃数"。
- 3.5 的 Neo4j 节点与关系数与迁移前完全一致。

### 8.7 前置资料
- Sila 姊妹：2372 真理要点、7 大类与 91 小类、真理要点与主/次枝子的归属。
- Srey：3.5 词条 → 2372 的对应文档。

---

## 九、命名对照（《名称对照表》）

| 类别 | 原用词 | 修改后 |
|---|---|---|
| 节点 | 词条节点 Concept | 真理要点 `Truth_Point` |
| 节点 | 经文节点 Scripture | 经文 `Scripture` |
| 节点 | 主干分类节点 MainTaxonomy | 主干 `Trunk` |
| 节点 | 横切标签节点 FacetedTag | 枝子 `Branch` |
| 专特标注 | 敏感词条 sensitive_status | 被误解的题目 `misunderstood_topics` |
| 专特标注 | 论证图 argument_graph | 神圣的辩理 `divine_argument` |
| 专特标注 | 本体论 ontology_tier | 属灵的本质 `spiritual_substance` |
| 专特标注 | 经文支撑强度 sal_level_scripture | 圣经根据 `scriptural_ground` |
| 专特标注 | 真理要点强度 sal_level_truth | 真理品质 `truth_quality` |
| 关系 | TAXONOMY_MAIN | `BELONGS_TO_TRUNK`（属于主干） |
| 关系 | TAGS_PRIMARY | `OF_BRANCH_DIRECTLY`（直接属于） |
| 关系 | TAGS_SECONDARY | `OF_BRANCH_INDIRECTLY`（间接属于） |
| 关系 | BELONGS_TO_MAIN | `GRAFTING`（接枝） |

---

## 十、待定与留待之后的事项

- **占位阶段**：检索、生成、评估尚未设计，本期只画界面。
- **领导提出的五项上下文材料**（差异词典、神圣经纶主线图、范例、检索原文带编号出处、BethanyEval 题库）：都用在"主题 → 龙骨"这一段；框架搭好后另研究方案、逐项接入。架构上步骤一、二的 prompt 组装需预留"上下文材料"插入位置。
- **图谱标注**：定义（双鸟瞰）、英文名、原文、五类专特标注等，之后逐项加。
- **服务器安全**（与 4.0 无直接关系）：
  - Redis 已于 2026.09.25 处理（曾被入侵但未得逞；已改为只绑定本机，旧数据目录保留为 `redis_data_compromised_20260925`）。
  - Docker 发布的端口会绕过 ufw；Neo4j（7474/7687）、ES（9201）仍对外开放，需确认密码强度。
  - root SSH 目前为密码登录，之后考虑改为密钥登录。

---

## 十一、勘探依据摘要

**代码（第一次勘探）**
- 现有 `mode="4.0"` 与 3.0 共用 `full_query`，只在索引集合（`_INDICES_FULL`）与 Step5 prompt 两处分叉。
- 可沿用的底层零件：`kg_rag/neo4j_client.py`（零业务依赖）、`retrieval.py` 的 bm25/dense、`embedding_adapter`、ai_search 版 reranker（带分数）、`monitoring`。路 3 `skeleton_route_search` 反向依赖 `kg_rag_service`，不可直接搬。
- LLM 调用封装分散十余处，无一支持 Opus 5.5，故 4.0 自建调用层。
- 骨架测试脚本均为独立脚本，Prompt 副本已与正式版分叉；无参考测试目录中只有旧版负担说明 prompt，无 v0.3 及 Prompt2–4。

**代码（第二次勘探）**
- 无 docker-compose；本地容器由 `start_all.bat` 启动，`deploy.sh` 只 `docker start neo4j`。
- 长时间任务：主站圆桌用 SSE + 心跳 + SQLite；CN 小排用内存任务 + 3 秒轮询（重启会丢）。4.0 采用"后台任务 + 每步落 SQLite + 轮询"。
- 存储：无关系型数据库，只有圆桌用 SQLite；另有 Redis、ES、JSON 文件。
- 前端：ant-design-vue 4.2.6；工具箱入口在 `ToolBox.vue`；登录守卫靠路由 `meta.requiresAuth`；无统一请求封装。
- 依赖：`anthropic>=0.18.0`、`python-docx>=1.0.0`、`neo4j>=5.0.0`（均为下界）；Claude key 为 `CLAUDE_API_KEY`。

**服务器（2026.09.25）**
- Nginx：主站 `aipansearch.org` 的 `/api/` 读写超时 600 秒，`/api/ws/` 3600 秒。
- 现有 Neo4j：`neo4j:5.26.23` Community，匿名卷，未限内存，`unless-stopped`。
- 端口 7475、7688 未被占用。
- 内存 23G，可用约 14G；swap 有旧页面但无换页活动；磁盘剩 141G。
- anthropic SDK 0.105.2。

---

## 附录：实施记录

（每步完成后在此记录：完成日期、实际改动、与方案的差异、验证结果。）

| 步 | 完成日期 | 备注 |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |
