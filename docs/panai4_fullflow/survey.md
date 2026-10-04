# 全流程测试改造：只读勘探报告

日期：2026-10-03  
范围：`back_mic/backend/panai4/`、`front_mic/frontend/src/components/toolbox/PanAI4*.vue`  
约束：本报告为只读勘探结果；不改正式 Prompt、不部署服务器、不触碰 3.5 / `kg_rag`。

已定目标流程（本报告按此评估）：

主题（可附原纲目）→ **选词** → **[人工确认]**（批量模式跳过）→ **取 3a**（内在+最内在送定义，外在仅名）→ **负担说明（直写 v3）** → **龙骨（skeleton_B4）** → **原纲目龙骨（Prompt3）** → **对比诊断（Prompt4）**；检索、生成继续占位。  
旧主线（Prompt1 v0.3 → Prompt2 v0.2）与普通版负担说明不再保留。

---

## 1. 现有流水线结构

### 1.1 模块分工

| 模块 | 路径 | 职责 |
|---|---|---|
| 步骤定义 | `panai4/pipeline.py` | `StepSpec`、主线/分析步骤表、范围判断、依赖跳过、负担正文截取 |
| 执行器 | `panai4/runner.py` | 排队/并发、按篇按步调用 LLM、写回 `step_results` |
| 库 | `panai4/db.py` | SQLite schema、迁移备份、runs/run_items/step_results、Prompt 测试版 |
| HTTP | `panai4/router.py` | `/api/panai4/*`：建跑、重跑、取消、进度、导出、Prompt 版本 |
| Prompt 库 | `panai4/prompts/` | 当前版正文、占位符校验、启动时与 extracted 逐字节比对 |
| LLM | `panai4/llm.py` | Claude 调用（测试台主线） |
| 导出 | `panai4/export_docx.py` | 按步骤导出 docx / zip |
| SC 子系统 | `panai4/sc/` | 选词→确认→加词条定义版（独立 API + `sc_runs`） |
| 挂载 | `back_mic/backend/main.py` L433–434 | `panai4_router` + `panai4_sc_router` |

结论：测试台「运行」与 SC「词条定义生成负担说明」是**两套并行流水线**（两套表、两套 API、两个 Vue 页签），尚未打通。

### 1.2 步骤如何定义与选择

`pipeline.py` L16–31：

- 主线 `MAIN_LINE`：`burden`（connected）→ `skeleton`（connected）→ `retrieval` / `generation` / `evaluation`（designed，跳过）
- 分析 `ANALYSIS`：`orig_skeleton` / `diagnosis`（analysis；无原纲目则跳过）

范围选择（`MAIN_SCOPES` / `ANALYSIS_SCOPES`，L43–44；`step_in_scope` L47–56）：

- `main_scope`：`none` | `burden` | `skeleton`
- `analysis_scope`：`none` | `orig_skeleton` | `diagnosis`
- 诊断强制要求主线跑到 `skeleton`（`router.py` `_validate_scopes` L140–147）

前端对应：`PanAI4Test.vue` L1176–1191（主线/分析单选）。

### 1.3 「从某一步重跑」如何实现

1. API：`POST /runs/{id}/rerun`、`POST /runs/{id}/items/{position}/rerun`（`router.py` L669–676）
2. `cover_start_step`（`pipeline.py` L59–71）扩 scope，保证起点被覆盖
3. `_prepare_rerun`（`router.py` L445–481）：复制父运行篇目；`start_step` **之前**的步骤用 `_copy_step` 沿用输出；之后重新 `pending`
4. 新运行 `parent_run_id` / `start_step` 写入 `runs`（`db.create_run` L409–447）
5. 执行时若已有 `done` 输出，`runner._execute_item` L173–177 先灌入 `outputs`，供后续步拼 Prompt

可重跑步骤常量：`RERUN_STEPS = ("burden", "skeleton", "orig_skeleton", "diagnosis")`（`router.py` L49）。

### 1.4 运行与每篇状态

`db.py` L17–18：

- 运行 `runs.status`：`pending` | `queued` | `running` | `done` | `failed` | `interrupted` | `cancelled`
- 篇/步 `run_items` / `step_results.status`：`pending` | `running` | `done` | `failed` | `skipped` | `interrupted` | `cancelled`

新建一律 `queued`（`create_run` L435）。启动时把残留 `running` 标 `interrupted`（`mark_running_interrupted`，`main.py` 启动调用）。

SC 侧 `sc_runs.status` 为自由文本（如 `select_done`，见 `sc/router.py` L182），**不在**上述枚举里。

### 1.5 并发与排队

- 上限默认 3：`config.MAX_CONCURRENT_RUNS` / `max_concurrent_runs()`（`config.py` L23–24, L60–67）
- `runner.dispatch`（L71–82）：`active` 未满时 `db.claim_next_queued()`（按 `id` 最早，`db.py` L380–393）拉起 `_execute`
- 单运行内：**一篇一篇、一步一步**顺序执行（`runner.py` 模块注释 L1–3；`_execute` L124–128）
- 同一 asyncio 事件循环，不开线程（同上）

### 1.6 每步 Prompt 版本如何选取与记录

建立运行时（`router._Choices` L156–211）：

- 请求体 `prompt_tests: {step → test_id}`；未列步骤用 `current_prompt(step)`
- 写入 `runs.prompt_selection`（JSON）与每条 `step_results.prompt_name` / `prompt_version` / `prompt_test_version_id`

执行时（`runner._template_for` L141–152）：

- 有 `prompt_test_version_id` → 读 `prompt_test_versions.template`
- 否则 `load_template(step, prompt_version)` 从 `prompts/texts/` 取当前/历史文件名

当前版只由代码模块的 `CURRENT` 决定（如 `prompt1_burden.CURRENT = "v0.3"`）；测试版任何人可建（`POST /prompt_tests`，`router.py` L863+）。

---

## 2. 「待确认」状态与批量模式

### 2.1 现状缺口

主线 `runner` **无暂停/人工闸门**：`pending` 步一旦被调度就会调模型。  
SC 的「人工确认」在**前端内存 + 第二次 API**（`PanAI4SC.vue` 选词 → 编辑 `selected` → `generate` 带 `final_terms`），后端没有「等确认」状态机。

### 2.2 建议改法（状态机）

在 `pipeline.MAIN_LINE` 插入（名称可再定）：

| 新 step id | kind | 含义 |
|---|---|---|
| `select` | connected | 调选词模型 |
| `await_confirm` | **gate**（新 kind） | 不调模型；`batch_mode=false` 时步状态进入 `awaiting_confirm`，**整篇（或整运行）阻塞** |
| `term_defs` | connected（或纯本地） | `build_term_defs` 取 3a / 外在仅名 |
| `burden` | connected | 直写 v3 + `{TERM_DEFS}` |
| `skeleton` | connected | skeleton_B4 |
| … | | 检索/生成仍 designed；分析线不变 |

配套改动要点：

1. **`_STATUS_ITEM` 增加** `awaiting_confirm`（需迁移 CHECK，见 §7）  
2. **`runner._execute_item`**：遇到 `gate` 且非批量 → `update_step(..., status="awaiting_confirm")`，**return**（篇状态可标 `awaiting_confirm` 或保持 `running` 并在进度 API 暴露）  
3. **新 API** 如 `POST /runs/{id}/items/{pos}/confirm`：写入 `final_terms_json`，把 `await_confirm`→`done`，后续 `term_defs`/`burden`/… 置 `pending`，再 `dispatch()`  
4. **重跑**：`start_step=burden` 时必须能**沿用**已确认词表（见 §3.3），不重跑 `select`  
5. **依赖跳过**：`dependency_skip` 扩展——`select`/`await_confirm` 失败则跳过后续主线

批量模式：

- 建跑参数 `batch_mode: bool`（`runs` 新列或写入 `prompt_selection`/note 旁的 JSON 字段）  
- 为真时：`await_confirm` 立即 `done`，`final_terms` = 选词解析出的全部 `name`（等同 SC 不经人工编辑）  
- 前端「运行」页勾选；与 SC 页行为对齐

风险：多篇运行中一篇卡在确认时，当前 runner 是**同运行串行**，会堵住同运行后续篇——可接受（先做），或改为「篇级可并行等待」再迭代。

---

## 3. `sc/` 可复用性与记录合并

### 3.1 可直接复用（建议原样调用，勿拷贝逻辑）

| 能力 | 位置 |
|---|---|
| 选词填槽 | `sc/data.fill_select_prompt` L193–206 |
| 选词默认稿 | `sc/prompts/select_prompt.txt`（经 `load_sc_data`） |
| 解析选词 | `sc/parse_select.parse_select_output` |
| 取 3a / TERM_DEFS | `sc/data.build_term_defs` L209+（已：内在+最内在定义，外在仅名） |
| 直写 v3 模板 | `sc/prompt_v3.build_ref_prompt_default_v3`；`sc/data.build_ref_prompt_default` L77–79 |
| 参考块 | `sc/prompts/ref_block.txt` |
| 填 ref | `sc/data.fill_ref_prompt` |
| SC 占位符检查 | `sc/data.check_sc_placeholders` L278–293（含 `TERM_DEFS`） |
| LLM 封装 | `sc/llm_call.sc_complete` / `usage_dict`（或统一改用 `panai4.llm.complete`） |
| 费用 | `sc/cost.calc_cost_usd` / `format_usd`（与主线 `llm.Result.cost_usd` 对齐即可） |
| 导出选词/负担 | `sc/export_sc.build_kind_docx`（选词结果已有） |
| 龙骨 B4 正文 | `sc/prompts/skeleton_B4.txt`（实验产物；纳入版本库时迁入 `prompts/texts/`） |

### 3.2 需迁移或重写

| 项 | 说明 |
|---|---|
| `sc/router.py` 独立 HTTP | 全流程应走 `panai4/router` + `runner`；SC 页可薄封装或逐步废弃「普通版」 |
| `sc/store.sc_runs` | 与 `runs` 双轨；全流程应以 `runs`/`step_results` 为准（§3.3） |
| `fill_plain_prompt` / 普通版并行 | 产品已定「普通版不再保留」——全流程不接入 |
| `runner._filled_prompt` / `render_user` | 需支持 `select`/`burden` 新占位符与 `TERM_DEFS`（今日 `PLACEHOLDERS` 无此键，`prompts/__init__.py` L58–63） |
| `extract_burden_body` | 现认 Prompt1 的 `【负担说明】`（`pipeline.py` L74–83）；直写版仍有该标记时可沿用，但需用 SC 的 `extract_burden_export` 规则（截到下一 `【`）统一，避免把「用到的参考材料」带进龙骨 |
| 龙骨模板 | 用 B4 替换 Prompt2 当前版；`PLACEHOLDERS["skeleton"]` 仍为 `{query},{burden}` |

### 3.3 `sc_runs` 与 `runs`：合并 / 关联建议

**推荐：以测试台 `runs` 为唯一运行真相；`sc_runs` 保留只读历史，新全流程不再写入。**

| 数据 | 建议落点 |
|---|---|
| 选词原文 / usage | `step_results` where `step='select'` 的 `output_text` / token 字段 |
| **确认后的词表** | **`run_items.final_terms_json`**（新列，JSON 数组：`[{name,tier,reason},…]`） |
| TERM_DEFS 文本 | `step_results` where `step='term_defs'` 的 `output_text`（或仅作中间产物写入 `prompt_text` 侧车字段） |
| 负担 / 龙骨 / 诊断 | 现有 `burden` / `skeleton` / … |

「从负担说明一步重跑、不重新选词」：

- `_prepare_rerun(..., start_step='burden')`：`select`/`await_confirm`/`term_defs` 整步 `_copy_step`（或至少拷贝 `final_terms_json`）  
- `term_defs` 若需随 3a 数据更新可强制重算，但**不得**重调选词模型  
- 若父篇无 `final_terms_json` → 400 提示先确认或从更早步进

可选关联：旧 `sc_runs.id` 写入 `runs.note` 或 `runs.sc_run_id`（可空），仅便于对照实验数据，非必须。

---

## 4. Prompt 版本库

### 4.1 当前版如何存储

- 元数据：`panai4/prompts/promptN_*.py`（`NAME` / `CURRENT` / `VERSIONS` / `EXTRACTED_NAME` / `SOURCE_DOCX`）  
- 正文：`panai4/prompts/texts/*.txt`  
- 核对源：`docs/panai4_prompts/extracted/*.txt`  
- 注册：`prompts/__init__.py` `REGISTRY` L13–18；`assert_prompt_texts_match()` L28–36 在 **import 时**执行（L138）

测试版：表 `prompt_test_versions`（`db.py` L134–152），按 `step` 挂靠。

### 4.2 无 docx 原件的新提示词（选词 / 直写 ref / B4）

`assert_prompt_texts_match` **假定**每个正式模块都有 extracted 双份。建议：

1. **为每个新当前版仍写入** `docs/panai4_prompts/extracted/<name>.txt`，内容 = `texts/` 定稿的逐字节拷贝（即使没有 Word 源）  
2. 模块字段：`SOURCE_DOCX = None` 或 `"（无 docx，以 texts 为准）"`；`SOURCE_TITLE` 注明来源路径（如 `sc/prompts/skeleton_B4.txt`）  
3. 可选增强：`assert_prompt_texts_match` 跳过 `SOURCE_DOCX is None` 且设置了 `SKIP_DOCX_ASSERT = True` 的模块——**不如双份文件稳**，双份文件不改 assert 逻辑  
4. 定稿流程：实验文件 → 评审 → 拷入 `texts/` + `extracted/` → 改 `CURRENT`

### 4.3 占位符校验与 `{TERM_DEFS}` 等

今日两套：

- 主线：`prompts.check_placeholders`（`query`/`burden`/…，L58–98）  
- SC：`check_sc_placeholders`（`TERM_DEFS`、`LIST_*` 等，`data.py` L278–293）

改造：

- 扩展 `PLACEHOLDERS`：如 `select` 用 SC 那套键；`burden` 改为直写版所需（至少 `query` + `TERM_DEFS`，以及 ref_block 侧 `DEF_*` 若仍留在模板中）  
- `render_user` / `_filled_prompt` 增加对应实参（从 `run_items.final_terms_json` + `build_term_defs` 注入）  
- Prompt 测试页「检查」应对新 step 走同一套规则

### 4.4 Prompt1 / Prompt2 被取代后，历史如何可看

- **不要删** `texts/prompt1_burden_v0.3.txt`、`prompt2_skeleton_v0.1.txt` / `v0.2.txt`  
- 历史 `step_results` 已存 `prompt_version` + 当时的 `prompt_text`（执行时写入，`runner` L222）→ 详情页仍可展示当时全文  
- `REGISTRY` 的 `CURRENT` 改指向新文件后，**旧版本名仍留在 `VERSIONS` dict**，`load_template(step, "v0.3")` 可读  
- UI：Prompt 版本页标注「已归档（非当前）」；运行史按记录的 version 展示，不强制 = CURRENT

Prompt3 / Prompt4：**不动**（任务已定）。

---

## 5. 前端

### 5.1 `PanAI4Test.vue`「运行」页签结构

顶栏三页签（L1087–1090）：`run` | `prompts` | `sc`。

`run`（L1125+）大致：

1. **输入**：题组载入/保存、篇题 + 可选原纲目  
2. **范围**：主线 / 分析单选 + Prompt 版本条  
3. **开始运行** / 进度 / 费用  
4. **结果**：按篇展开各步卡片、负担说明子 Tab、重跑菜单、导出 zip  
5. **历史列表**

逻辑依赖现有四步 id（`RERUN_STEPS`、`STEP_ORDER`、burden 子 Tab 等）。

### 5.2 `PanAI4SC.vue` 可复用部分

可迁到全流程「运行」或抽成共享组件：

- 选词提示词编辑 + 占位符检查（L412–415）  
- 选词按钮与费用行（L417–428）  
- **选词结果表**：删词、按名搜索加词、档位/依据展示（L423–480 一带）  
- 「确认并生成」语义 → 改为「确认词表并继续」调用新 confirm API  

不宜原样照搬：普通版并行、SC 历史 `sc_runs` 列表、与测试台 runs 割裂的导出入口（应并入运行导出）。

### 5.3 「全流程测试」阶段卡片建议排布

每篇一张纵向时间线（替代现「主线跑到龙骨」粗粒度 scope，或保留 scope 但选项改为全流程阶段）：

1. 选词（模型输出 + 原始列表）  
2. 确认词表（可编辑；批量模式显示「已自动确认」）  
3. 词条定义块（TERM_DEFS 预览，只读）  
4. 负担说明（直写）  
5. 新龙骨（B4）  
6. 原纲目龙骨（有纲目才亮）  
7. 对比诊断  
8. 检索 / 生成（灰置「待设计」）

顶栏可将原「SC」页签改为说明链接或隐藏，避免两套入口打架（实施阶段再定）。

---

## 6. docx 导出

### 6.1 差异

| | `export_docx.py`（测试台） | `export_sc.py`（SC） |
|---|---|---|
| 对象 | 运行内一步 / 整跑 zip | 选词原文、普通/加词条负担、整份 SC 包 |
| 标题 | `【{步骤标签}】第N篇_主题` | 选词：主题三号居中；负担：带【加词条定义版-负担说明】前缀 |
| 字体 | 微软雅黑（`_FONT`，L19） | 同（L23） |
| 主题字号 | 见 `build_step_docx`（标题样式） | `_set_title_paragraph` **16pt 加粗居中**（L68–76，注释写明三号） |
| 负担截取 | `extract_burden_body`（pipeline） | `extract_burden_export`（截到下一【） |
| 额外 | 步骤格式（编号龙骨等） | 引用统计页、费用行（`build_sc_docx`） |

### 6.2 合并方案

- **统一排版底座**：抽共享 `_FONT` / `_set_run_font` / `_set_title_paragraph`（已有交叉 import：`export_sc` 用 `export_docx.safe_filename_part`）  
- 全流程导出步骤扩展：`select` | `term_defs`(可选) | `burden` | `skeleton` | `orig_skeleton` | `diagnosis`  
- **选词结果 docx**：直接复用 `build_kind_docx("select", topic, text)`（`export_sc.py` L139–163）——已是雅黑 + 篇题三号居中 + 正文 11pt；文件名 `【选词结果】{主题}.docx`（`kind_docx_filename` L122–128）  
- 负担说明导出改走 `extract_burden_export`，与 SC 一致  
- 整跑 zip：在现有 `build_run_zip` 中按新 `EXPORT_STEPS` 打包；费用汇总可选用 SC 的 `_cost_line` 风格作为封面可选页

---

## 7. 数据库字段与迁移

### 7.1 现有备份规矩（必须遵守）

`db.py`：

- `backup_path_for` / `_backup`（L238–250）：改库前 `conn.backup` 到 `panai4_YYYYMMDD_HHMMSS.db`  
- `_migrate_to_v2`（L269+）：重建带 CHECK 的表前先备份，行数/id 不一致则回滚  
- `SCHEMA_VERSION = 2`（L16）；`init_db` 在 `user_version < SCHEMA_VERSION` 时迁移

### 7.2 建议 SCHEMA_VERSION = 3 变更

**`runs`**

- `batch_mode INTEGER NOT NULL DEFAULT 0`  
- （可选）`flow_kind TEXT`：`legacy` | `full` —— 便于历史旧跑只读  
- （可选）`sc_run_id` 关联旧实验  

**`run_items`**

- `final_terms_json TEXT` —— 确认后的词表（重跑负担的锚点）  

**`step_results.step` CHECK**

- 扩展允许：`select`、`await_confirm`、`term_defs`（及保留旧 id）  
- SQLite 改 CHECK → **重建表**（同 v2 手法：关外键 → 新表 → 拷贝 → 校验 → `PRAGMA user_version=3`）  

**状态 CHECK**

- item/step 增加 `awaiting_confirm`  

**`prompt_test_versions.step` CHECK**

- 同步加入新 prompt 步骤名  

`sc_*` 表：本阶段可不删，避免破坏 SC 页；全流程稳定后再标废弃。

### 7.3 迁移步骤（实施时）

1. 停写（或短窗维护）  
2. `_backup(conn)`  
3. 重建/ALTER + `user_version=3`  
4. `_snapshot` 前后计数/id 摘要写入迁移报告（沿用 `migration_report`）  
5. 验证：旧 runs 可打开；新全流程可建跑  

---

## 8. 完整改动清单与分步实施

### 8.1 改动清单（文件级）

**后端**

- `pipeline.py`：新步骤、gate、依赖、burden 截取对齐  
- `runner.py`：gate 暂停/恢复、`TERM_DEFS` 注入、B4/直写模板、max_tokens 策略  
- `db.py`：v3 迁移、新列、新状态、新 step id  
- `router.py`：建跑参数（batch）、confirm API、scope/重跑、estimate、导出  
- `prompts/`：新模块（select / burden_v3 或替换 prompt1 / skeleton_B4 替换 prompt2 CURRENT）；扩展 `PLACEHOLDERS` / `render_user`；extracted 双份  
- `export_docx.py` (+ 可选抽共享)：新步骤导出  
- `sc/*`：被 runner 调用；HTTP 可保留兼容或只读  
- **禁止**：`kg_rag/prompts.py`、`kg_rag_service.py`、一切 3.5 路径  

**前端**

- `PanAI4Test.vue`：全流程卡片、确认闸、批量勾选、重跑选项  
- 抽离或复用 `PanAI4SC.vue` 选词确认 UI  
- `PanAI4Prompts.vue`：新步骤版本管理  

**文档 / 验证脚本**

- 本目录后续可加 `plan.md`；verify 脚本仿 `verify_bench.py` / `sc/verify_*`  

### 8.2 建议分步

| 步 | 内容 | 验证 |
|---|---|---|
| **A** | Prompt 入库：select + 直写 burden + skeleton_B4 进 `REGISTRY`/`texts`/`extracted`；Prompt1/2 归档仍可读；assert 通过 | `python -c "from panai4 import prompts"`；Prompt 页可开测试版；旧 run 详情仍显示旧 `prompt_text` |
| **B** | DB v3 迁移（备份→新列/状态/step） | 自动备份文件存在；旧历史列表/打开；`user_version=3` |
| **C** | runner 接 `select`→`term_defs`→新 `burden`→B4 `skeleton`（**先强制 batch_mode=true**，无闸门） | FAKE_LLM 干跑 1 篇；真跑 1 篇费用与步骤齐全；龙骨机械检查可复用 exp_skel4 规则抽检 |
| **D** | `awaiting_confirm` + confirm API + 前端确认表；batch 勾选 | 非批量停在确认；改词后继续；批量跳过；从 burden 重跑不重新选词 |
| **E** | 导出 zip/docx 含选词；截取规则统一 | 打开 docx：雅黑、篇题三号；负担无「参考材料」尾巴 |
| **F** | 收回旧 scope UI / 隐藏普通版入口；文档与 verify 日志 | 回归：Prompt3/4、无纲目跳过、并发 3、取消排队 |

### 8.3 风险点

1. **3.5 / kg_rag**：全流程只用 `panai4.*` 与 `sc.data` 已导出的 3a JSON；禁止改 `kg_rag_service.py` / `kg_rag/prompts.py`。  
2. **import 时 assert**：新 Prompt 若缺 extracted 会导致整站 `import panai4.prompts` 失败（`__init__.py` L138）。  
3. **双表并存**：实施中若 SC 页与全流程同时写，易晕数据——应用 `flow_kind` 或冻结 SC 写路径。  
4. **串行确认堵运行**：多篇非批量时一篇不确认则同 run 后续篇不跑。  
5. **负担截取**：Prompt1 规则 vs 直写版带【用到的参考材料】——必须统一到 `extract_burden_export`，否则 B4 输入被污染。  
6. **CHECK 迁移**：与 v2 相同，失败必须回滚并保留备份库。  
7. **费用预估**：`ESTIMATE_USD_*`（`config.py`）需加选词/定义块量级，否则顶栏预估偏差。  
8. **占位符两套逻辑**：合并不当会导致测试版「检查通过」但 runner 填槽 KeyError。

---

## 9. 出处速查（结论 → 代码）

| 结论 | 出处 |
|---|---|
| 主线四步+designed | `pipeline.py` L16–22 |
| 重跑扩 scope | `pipeline.py` `cover_start_step` L59–71 |
| 并发 3 + 排队 | `config.py` L23–24；`runner.dispatch` L71–82；`db.claim_next_queued` L380–393 |
| 版本选择与落库 | `router._Choices` L156–211；`db.create_run` L419–447 |
| 测试版模板优先 | `runner._template_for` L141–152 |
| extracted 逐字节 | `prompts/__init__.py` `assert_prompt_texts_match` L28–36 |
| SC 选词/生成 API | `sc/router.py` `select_terms` L158+；`generate` L194+ |
| build_term_defs 外在仅名 | `sc/data.py` L209–216 文档字符串与实现 |
| sc_runs 字段 | `sc/store.py` L24–45 |
| 迁移备份 | `db.py` `_backup` L243–250；`_migrate_to_v2` L269–304 |
| 运行页结构 | `PanAI4Test.vue` L1087–1191 |
| SC 确认 UI | `PanAI4SC.vue` L403–484 |
| 选词 docx 规格 | `sc/export_sc.py` `build_kind_docx` / `_set_title_paragraph` L68–76, L139–163 |
| 路由器挂载 | `main.py` L433–434 |

---

## 10. 勘探验证

- 本文件：`docs/panai4_fullflow/survey.md`  
- 日志：`logs/sc_fullflow_survey.log`  
- 除上述新增外，不应改动其它仓库文件（以 `git status` 为准）。
