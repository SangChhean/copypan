# PanAI4 清理 · 阶段一：盘点待删项与引用（只读）

生成时间：2026-11-06；范围：`docs/3a_export.json`、`docs/panai4_graph/词条三档分类.json`、工具箱「PanAI 4.0 测试台」。  
本报告**只盘点**，未删、未改任何文件；未读 `.env`；未连图谱/ES；未跑 `build_v4.py`。

---

## 摘要

| 对象 | 结论类 | 一句话 |
|---|---|---|
| `docs/3a_export.json` | 需改引用后才能删 | 仍被 `panai4/sc/*` 与 `inventory_v4_pre.py` 读取；已被 `truth_dictionary_3a3b.json` 在图谱侧取代，但测试台 SC 路径仍依赖它 |
| `docs/panai4_graph/词条三档分类.json` | 需改引用后才能删 | 同上；`export_docx` 经 `sc.data.load_sc_data` 间接依赖 |
| PanAI 4.0 测试台（含 Prompt 测试版 / 多人运行 / docx 导出 / 内嵌 SC 页） | 需改引用后才能删 | 包内自洽；**应用启动**在 `main.py` 强制 `init_db` + 挂载两套路由，删文件前必须改 `main.py` + 前端入口 |
| `panai4/graph|outline|inherit|bible|pano` 等数据管线 | **不要删** | 非测试台 UI；图谱/ES 导入仍在用 |
| `organic_advance.json` / `truth_dictionary_3a3b.json` | **不要删** | 本轮明确排除 |

**共用结论（重要）**：`export_docx.py`、`db.py`、`runner.py`、`prompts/*`、`sc/*` 的引用检索结果均为 **panai4 包内互引**；前端仅 `PanAI4Test.vue` 及其子组件与 `/panai4-test` 路由使用。工具箱其他功能（纲目翻译、KG-RAG 测试台、圆桌等）**不 import** 这些模块。因此它们可随测试台一并删除，**不是**“被测试台以外业务共用、禁止删”的库。

---

## A. `docs/3a_export.json`（鸟瞰定义）

### A1. 文件清单

| 路径 | 大小 | git 跟踪 | 当前状态 |
|---|---|---|---|
| `docs/3a_export.json` | 16,777,777 字节（约 16.0 MiB） | 是（`git ls-files` 有） | `M`（已修改，未提交） |

### A2. 引用检查（grep）

| 位置 | 性质 |
|---|---|
| `back_mic/backend/panai4/sc/config.py` | 默认路径 `_DEFAULT_3A`；可用 env `PANAI4_SC_3A_JSON` 覆盖 |
| `back_mic/backend/panai4/sc/stage1.py` | 读取并参与生成三档分类 |
| `back_mic/backend/panai4/sc/data.py` | `load_sc_data()` → `export_3a_path()` 加载 `content_3a` |
| `back_mic/backend/panai4/export_docx.py` | 经 `load_sc_data()` 间接依赖（选词导出档次回查链路的数据源之一） |
| `back_mic/backend/panai4/graph/inventory_v4_pre.py` | 只读盘点：存在性/条数/键；报告文案提及 |
| `docs/panai4_graph/neo4j_v4_inventory_pre.md` 等 | 历史报告提及（非运行时） |
| `docs/panai4_es/archive/task5_*.md/ps1` | 归档 git 计划提及 |

**未发现**：`outline/`、`inherit/`、`bible/`、`pano/`、前端业务页、其他 toolbox 功能直接读取该文件。

### A3. 启动影响

- 单独删文件、**保留 SC/测试台**：`load_sc_data` 会记 `load_error` / 空表（代码有缺失路径分支），SC 页与依赖档次的导出变弱或失败；**不一定**导致整个 FastAPI 进程崩溃，但测试台 SC 功能不可用。
- 若同时拆除测试台并改掉 `main.py`：该文件可删；仍须改 `inventory_v4_pre.py` 以免盘点脚本报错。

### A4. 分类

→ **需同时修改引用后才能删**

建议修改方案（本阶段不改）：
1. 若保留 SC：把 `sc/config.export_3a_path` 默认改为 `panai4/data/graph_annotations/truth_dictionary_3a3b.json`（并核对字段：`title`/`content_3a` vs 旧 `id`/`title`/`content_3a`），同步改 `stage1.py`。
2. 若删除整个测试台+SC：删除该 JSON；从 `inventory_v4_pre.py` 的候选文件列表与报告文案中移除；归档文档可保留历史叙述或加“已删除”注记。

---

## B. `docs/panai4_graph/词条三档分类.json`

### B1. 文件清单

| 路径 | 大小 | git 跟踪 | 当前状态 |
|---|---|---|---|
| `docs/panai4_graph/词条三档分类.json` | 43,661 字节 | 是 | `M` |

### B2. 引用检查

| 位置 | 性质 |
|---|---|
| `panai4/sc/config.py` | `_DEFAULT_TIERS`；env `PANAI4_SC_TIERS_JSON` |
| `panai4/sc/stage1.py` | **写出**该文件 |
| `panai4/sc/data.py` | `load_sc_data()` 读三档名单 |
| `panai4/export_docx.py` | `_tier_lookup()` → `load_sc_data().tier_of`（加载失败则空表，导出不崩） |
| `panai4/graph/inventory_v4_pre.py` | 只读盘点 |
| 若干 `docs/panai4_graph/*.md`、`docs/panai4_es/archive/*` | 历史提及 |

图谱现用标注是节点上的 `intrinsic_significance`（字符串档次），**不再依赖**此 JSON。

### B3. 启动影响

与 A 类似：保留 SC 时删文件 → SC 数据加载失败/空；去掉测试台后仅 `inventory_v4_pre.py` 需改。

### B4. 分类

→ **需同时修改引用后才能删**（方案同 A：改路径 / 或随 SC 删除并清理 inventory）。

---

## C. 工具箱「PanAI 4.0 测试台」

边界定义：工具箱卡片「PanAI 4.0 测试台」→ 路由 `#/panai4-test` → `PanAI4Test.vue`，内嵌 **Prompt 测试版**（`PanAI4Prompts.vue`）与 **SC 页**（`PanAI4SC.vue`），后端前缀 `/api/panai4` 与 `/api/panai4/sc`。含多人运行（`runs`/`creators`/并发队列）、docx/zip 导出、Prompt 正式版与测试版管理。

**不含**：KG-RAG 测试工作台（`/kg-rag-test`）、图谱导入脚本、ES 索引管线。

### C1. 前端

| 路径 | 大小 | 跟踪 | 状态 | 角色 |
|---|---|---|---|---|
| `front_mic/frontend/src/components/toolbox/PanAI4Test.vue` | 84,088 | 是 | clean | 测试台主页（多人运行、进度、导出入口） |
| `front_mic/frontend/src/components/toolbox/PanAI4Prompts.vue` | 25,966 | 是 | clean | Prompt 正式/测试版 CRUD、diff |
| `front_mic/frontend/src/components/toolbox/PanAI4SC.vue` | 28,771 | 是 | clean | SC 子页（仅被 Test 引用，无独立路由） |
| `front_mic/frontend/src/router/index.js` L118–122 | — | 是 | — | `path: "/panai4-test"` |
| `front_mic/frontend/src/components/toolbox/ToolBox.vue` L76 | — | 是 | — | 菜单卡片入口 |

前端检索：全 `front_mic` 内对 `panai4-test` / `PanAI4*` / `/api/panai4` 的引用**仅上述文件**。`ToolsHeader.vue` 等被其他工具共用 → **不要删**。

### C2. 后端 · 路由与注册

| 模块 | 前缀 / 作用 | 注册点 |
|---|---|---|
| `panai4/router.py`（41,797 B） | `/api/panai4`：`meta`、`creators`、`estimate`、`topic_sets`、`runs`（创建/重跑/确认/取消/进度/删除）、逐步 `docx`、`export.zip`、`prompts`、`prompt_tests`、`prompt_diff` | `main.py`：`include_router(panai4_router)` |
| `panai4/sc/router.py` | `/api/panai4/sc/...`：SC 选词/生成/导出 | `main.py`：`include_router(panai4_sc_router)` |
| `panai4/db.py` | SQLite：`runs` / `run_items` / `step_results` / `prompt_test_versions` / `topic_sets` 等 | `main.py` lifespan：`init_db()`、`mark_running_interrupted()` |

**启动硬依赖**：即使前端不再进入测试台，只要 `main.py` 仍 import/`init_db`，删掉 `db.py`/`router.py` 会导致**后端无法启动**。

### C3. 后端 · 测试台核心模块（建议随台删除）

| 路径 | 大小 | 跟踪 | 说明 |
|---|---|---|---|
| `panai4/runner.py` | 29,893 | 是 | 多人运行执行器 |
| `panai4/pipeline.py` | 4,964 | 是 | 步骤标签/负担抽取 |
| `panai4/llm.py` | 9,702 | 是 | Claude 调用（测试台/SC） |
| `panai4/config.py` | 2,897 | 是 | DB 路径、并发、假 LLM、单价 |
| `panai4/export_docx.py` | 22,940 | 是 | 逐步 docx / 全文 / zip 文件名；读三档分类 |
| `panai4/prompt_diff.py` | 1,283 | 是 | Prompt 文本 diff API |
| `panai4/prompts/` | 17 文件 / 85,865 B | 是 | Prompt0–4 正式模板 + `prompt_test` + `texts/` |
| `panai4/sc/` | 26 个 `.py` / 343,570 B | 是 | SC API、实验脚本 `exp_*`、校验 `verify_*`、`stage1` |
| `panai4/verify_*.py`（8） | 共 139,754 B | 是 | 测试台自测脚本（bench/stepB–EF/export…） |
| `panai4/prompts/_verify_step_a.py` | — | 是 | Prompt 步骤自测 |

### C4. 数据（运行结果 / DB / 临时）

| 路径 | 规模 | 跟踪 | 说明 |
|---|---|---|---|
| `back_mic/backend/data/panai4/` | 28 文件，约 83.1 MiB | **被 ignore**（`.gitignore:19`） | `panai4.db`（主库约 7.2 MiB）+ 多份 `panai4_step*_*.db` / `_precommit_*.db` / `_stepB_tmp/` |
| 运行导出产物 | 分散在 `docs/panai4_ui/run27/*.docx`、`docs/panai4_sc/exp_*` | 多数已跟踪 | 历史试跑 docx/txt/json |
| Prompt 存档 | `docs/panai4_prompts/`（16 文件 / 232 KB） | 是 | 上传稿、extracted txt、docx 原件 |
| SC 参考文本 | `docs/panai4_sc/ref/` 等 | 是 | `sc/config.ref_dir` 默认指向此处 |
| 日志 | `logs/sc_*.log`、`logs/sc_fullflow_*.log` 等（数十个） | 通常未强求入库 | 仅服务测试台/SC 校验 |

### C5. 文档与脚本（仅服务测试台）

| 路径 | 规模 | 跟踪 | 说明 |
|---|---|---|---|
| `docs/panai4_ui/` | 14 文件 / 约 1.15 MiB | 是 | `testbench_mock.html`、`prompt_versions_mock.html`、截图 `b_check/`、样例 `run27/` |
| `docs/panai4_prompts/` | 见上 | 是 | Prompt 文稿 |
| `docs/panai4_fullflow/survey.md` | 22,380 B | 是 | 全流程勘测 |
| `docs/panai4_sc/` | 100 文件 / 约 2.08 MiB | 是（`null_terms.csv` 现为 `M`） | SC 实验报告与导出 |
| `docs/PanAI4.0_新系统框架实施方案.md` | 25,740 B | 是 | 实施方案（含“测试台先放工具箱”） |

### C6. 引用检查 · 是否被测试台以外共用

| 模块 | 包外引用 | 结论 |
|---|---|---|
| `export_docx`（docx 导出） | 仅 `panai4/sc/*`、`panai4/verify_*`、`panai4/router` | **可随台删**；非纲目/翻译等其他工具的导出库 |
| `db` / `runner` / `prompt_tests` | 仅 `main.py` + 包内 | **可随台删**（须先改 `main.py`） |
| `prompts` 模板 | `sc/*`、`runner`、verify | **可随台删** |
| `sc/*` | 仅嵌在测试台 UI；无独立产品路由 | **可随台删** |
| `llm.py` / `config.py` | 包内 SC/runner | **可随台删**；勿与 `ai_search` 等其他 LLM 路由混淆 |

### C7. 启动影响（逐条）

| 若直接删除… | 后果 | 依据 |
|---|---|---|
| 仅前端 3 个 Vue + 不改路由 | 构建可能仍过，但点开测试台 404；菜单仍在 | 动态 import 失败 / 路由悬空 |
| 后端 `router.py`/`db.py` 但 **不改** `main.py` | **应用启动失败**（ImportError 或 lifespan 失败） | `main.py` L37–38、L61–64、L433–434 |
| 整台后端+前端并改掉 `main.py`/菜单/路由 | 其他功能应可启动 | 无包外业务 import |

### C8. 分类

→ **需同时修改引用后才能删**

建议修改方案（不实施）：
1. `main.py`：去掉 `panai4_router` / `panai4_sc_router` 的 import 与 `include_router`；lifespan 去掉 `init_db` / `mark_running_interrupted`。
2. `ToolBox.vue`：删除「PanAI 4.0 测试台」卡片。
3. `router/index.js`：删除 `/panai4-test` 路由。
4. 再删 Vue、测试台后端模块、`data/panai4`、相关 docs/logs。
5. 保留 `panai4/graph|outline|inherit|bible|pano|organize_index_data.py|push_remote_v2.py|data/graph_annotations/`。

---

## 三类汇总

### 1. 可直接删（无运行时代码引用；或仅历史/日志）

在**已完成** `main.py` + 前端入口修改、并决定拆除测试台的前提下，下列可视为无外部业务引用：

- 前端：`PanAI4Test.vue` / `PanAI4Prompts.vue` / `PanAI4SC.vue`
- 后端测试台包内：`router.py`、`runner.py`、`db.py`、`export_docx.py`、`pipeline.py`、`llm.py`、`config.py`、`prompt_diff.py`、`prompts/`、`sc/`、全部 `verify_*.py`
- 数据：`back_mic/backend/data/panai4/**`（本就 gitignore）
- 文档：`docs/panai4_ui/**`、`docs/panai4_prompts/**`、`docs/panai4_fullflow/**`、`docs/panai4_sc/**`（含实验产物）、可选 `docs/PanAI4.0_新系统框架实施方案.md`
- 日志：`logs/sc_*.log`、`logs/sc_fullflow_*.log` 等

> 注意：在未改 `main.py` 前，**没有一项后端模块属于“可直接删”**。

### 2. 需同时修改引用后才能删

| 项 | 必须先改的位置 |
|---|---|
| 测试台整体 | `back_mic/backend/main.py`；`ToolBox.vue`；`front_mic/.../router/index.js` |
| `docs/3a_export.json` | 若保留 SC：`sc/config.py`、`sc/stage1.py`、`sc/data.py`；无论是否保留：`graph/inventory_v4_pre.py` |
| `docs/panai4_graph/词条三档分类.json` | 同上（`sc/config`/`stage1`/`data`/`export_docx` 间接；`inventory_v4_pre`） |

### 3. 不要删

| 项 | 原因 |
|---|---|
| `back_mic/backend/panai4/graph/**` | neo4j-v4 导入/盘点管线 |
| `panai4/outline/**`、`inherit/**`、`bible/**`、`pano/**` | ES/文本索引与生命读经等数据管线 |
| `panai4/organize_index_data.py`、`push_remote_v2.py` | 索引整理与远端推送 |
| `panai4/data/graph_annotations/**`（含 `organic_advance.json`、`truth_dictionary_3a3b.json`） | 图谱内容外置；本轮明确排除 |
| `docs/panai4_graph/**`（除拟删的三档 JSON） | 图谱导入报告与说明 |
| `docs/panai4_es/**` | ES 任务文档 |
| `ToolsHeader.vue`、`ToolBox.vue`（文件本身）、`KgRagTest.vue` | 共用壳 / 其他测试台 |
| 其他 toolbox 功能与其导出 | 与 panai4 测试台 docx **无代码共用** |

---

## 建议删除顺序（阶段二再执行）

1. **先改引用（最小补丁）**  
   - `main.py` 去路由与 `init_db`  
   - 前端去卡片与 `/panai4-test` 路由  
2. **验证后端能启动**（见下）  
3. **删前端三 Vue**  
4. **删测试台后端模块**（router/runner/db/export_docx/pipeline/llm/config/prompt_diff/prompts/sc/verify_*）  
5. **删 `backend/data/panai4/`**（本地 DB；已 ignore）  
6. **删测试台专用 docs + sc 日志**（`panai4_ui` / `panai4_prompts` / `panai4_fullflow` / `panai4_sc` / 相关 logs）  
7. **处理两份 JSON**  
   - 若 SC 已删：删 `3a_export.json`、`词条三档分类.json`，并改 `inventory_v4_pre.py`  
   - 若仍留 SC：不要删 JSON，先改路径到 `truth_dictionary_3a3b.json` 等  
8. **最后**再考虑是否归档/删 `PanAI4.0_新系统框架实施方案.md`

---

## 删除后建议验证步骤

1. 在 `back_mic/backend` 启动 FastAPI：确认无 `panai4.router` / `init_db` ImportError。  
2. 打开前端工具箱：无「PanAI 4.0 测试台」卡片；访问 `#/panai4-test` 应无有效页。  
3. 冒烟其他工具箱入口（如纲目相关、`#/kg-rag-test`）仍可打开。  
4. `curl`/浏览器确认 `/api/panai4/*`、`/api/panai4/sc/*` 返回 404。  
5. 可选：`python -m panai4.graph.inventory_v4_pre`（若仍保留）应不再依赖已删 JSON，或已改列表。  
6. `git status`：确认未误删 `graph_annotations`、未改 `.gitignore`（本阶段要求如此）。

---

## 最终核对（本盘点）

- 未删除、未移动、未重命名任何文件  
- 未修改 `.gitignore`  
- 未碰 `organic_advance.json` / `truth_dictionary_3a3b.json` / 服务器  
- 未读 `.env`；报告无密码  
- 未运行 `build_v4.py`；未连接图谱或 ES  
