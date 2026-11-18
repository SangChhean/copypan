# Git 合并冲突盘点（阶段一 · 只读）

> 生成说明：只读盘点，未解决冲突，未 `git add` / commit / push / `merge --abort` / checkout / reset；未打开 `.env`；未连接图谱与 ES。  
> 盘点时点：合并进行中（`git pull origin master` 之后）。

## 0. 合并身份

| 角色 | 提交 | 说明 |
|------|------|------|
| HEAD（我方） | `1050801b` | 数据全导入、删除原 4.0 测试台 |
| MERGE_HEAD / `origin/master`（对方） | `de95802a` | Merge PR #132 … |
| 共同祖先 | `1e5e6980` | — |

分支：`master` 与 `origin/master` 已分叉（我方 1 个提交，对方 21 个提交）。

---

## 1. 状态确认

### 1.1 `git status` 完整输出（盘点时）

```
On branch master
Your branch and 'origin/master' have diverged,
and have 1 and 21 different commits each, respectively.
  (use "git pull" if you want to integrate the remote branch with yours)

You have unmerged paths.
  (fix conflicts and run "git commit")
  (use "git merge --abort" to abort the merge)

Changes to be committed:
	modified:   .gitignore
	modified:   back_cn/.env.example
	modified:   back_cn/main.py
	new file:   back_cn/routers/amana_router.py
	modified:   back_mic/backend/kg_rag/kg_rag_service.py
	new file:   back_mic/backend/kg_rag/v40_burden/__init__.py
	new file:   back_mic/backend/kg_rag/v40_burden/prompt_diff_vs_3.5.diff
	new file:   back_mic/backend/kg_rag/v40_burden/prompts_v40.py
	new file:   back_mic/backend/kg_rag/v40_burden/router.py
	new file:   back_mic/backend/kg_rag/v40_burden/service.py
	new file:   back_mic/backend/kg_rag/v40_burden/term_layer_count.py
	new file:   back_mic/backend/kg_rag/v40_burden/terms_2373.json
	new file:   back_mic/backend/main_t35test.py
	new file:   back_mic/backend/panai_new/__init__.py
	new file:   back_mic/backend/panai_new/import_raw.py
	new file:   back_mic/backend/run_backend.py
	new file:   back_mic/backend/t35test/__init__.py
	new file:   back_mic/backend/t35test/common.py
	new file:   back_mic/backend/t35test/embedding_service.py
	new file:   back_mic/backend/t35test/kg/__init__.py
	new file:   back_mic/backend/t35test/kg/bird_view_prompts.py
	new file:   back_mic/backend/t35test/kg/embedding_adapter.py
	new file:   back_mic/backend/t35test/kg/firewall.py
	new file:   back_mic/backend/t35test/kg/kg_rag_service.py
	new file:   back_mic/backend/t35test/kg/llm_pricing.py
	new file:   back_mic/backend/t35test/kg/neo4j_client.py
	new file:   back_mic/backend/t35test/kg/prompts.py
	new file:   back_mic/backend/t35test/kg/retrieval.py
	new file:   back_mic/backend/t35test/outline_eval/__init__.py
	new file:   back_mic/backend/t35test/outline_eval/llm_evaluator.py
	new file:   back_mic/backend/t35test/outline_eval/prompts.py
	new file:   back_mic/backend/t35test/reranker_service.py
	new file:   back_mic/backend/t35test/router.py
	new file:   back_mic/backend/t35test/translate/__init__.py
	new file:   back_mic/backend/t35test/translate/formatters/__init__.py
	new file:   back_mic/backend/t35test/translate/formatters/format_chinese_outline.py
	new file:   back_mic/backend/t35test/translate/formatters/format_english_outline.py
	new file:   back_mic/backend/t35test/translate/gemini_response_utils.py
	new file:   back_mic/backend/t35test/translate/gemini_translation_instruction.py
	new file:   back_mic/backend/t35test/translate/service.py
	modified:   front_cn/src/components/HomePage.vue
	modified:   front_mic/frontend/src/components/Search.vue
	new file:   front_mic/frontend/src/components/toolbox/Panai35Test.vue

Unmerged paths:
  (use "git add <file>..." to mark resolution)
	both modified:   back_mic/backend/main.py
	both modified:   front_mic/frontend/src/components/toolbox/ToolBox.vue
	both modified:   front_mic/frontend/src/router/index.js
```

### 1.2 冲突类型汇总

| 路径 | 冲突类型 | 说明 |
|------|----------|------|
| `back_mic/backend/main.py` | **both modified (UU)** | 各 1 个冲突块 |
| `front_mic/frontend/src/components/toolbox/ToolBox.vue` | **both modified (UU)** | 各 1 个冲突块 |
| `front_mic/frontend/src/router/index.js` | **both modified (UU)** | 各 1 个冲突块 |

- **无** `deleted by us` / `deleted by them` / `added by both` / `both added` 等其它未合并类型（`git ls-files -u` 仅上述 3 个路径，各 stage 1/2/3）。
- **冲突文件确实只有这 3 个。**

### 1.3 自动合并已完成的相关部分（重要）

对 `main.py`，工作区在冲突块之外已自动采用我方结果：

- **已无** `from panai4.router` / `from panai4.sc.router`
- **已无** lifespan 内 `panai4.db.init_db` / `mark_running_interrupted`
- 唯一留下的冲突在 `include_router(panai4_*)` 一带

测试台源文件（`panai4/router.py`、`panai4/sc/`、`PanAI4*.vue` 等）在工作区仍为**不存在**；对方树里仍有这些文件，但相对共同祖先**内容未改** → 合并规则为「我方删除胜出」，**不会**以 UD 冲突形式再现，也不会自动加回。

---

## 2. 对方带来了什么

### 2.1 `git log --oneline` 等价信息：`HEAD..origin/master`

（作者、日期、说明；不含邮箱）

| 短哈希 | 作者 | 日期 | 说明 |
|--------|------|------|------|
| `de95802a` | SangChhean | 2026-11-06 | Merge pull request #132 from SangChhean/feature/P+S-fix_practical_stage_move_keywords_tool |
| `9eeedd5a` | SangChhean | 2026-11-06 | Merge pull request #131 from SangChhean/feature/vannakamana |
| `3d96a02b` | vannakjey | 2026-11-06 | feat: 首页新增 Amana书库入口（新标签页打开，后端下发免登录链接） |
| `774dfa8c` | Piseth | 2026-11-06 | 新测试台拆成独立后端进程（端口 8001），主站去掉新测试台与4.0测试台接口 |
| `b0fcb6c6` | Piseth | 2026-10-22 | 新测试台：删除旧4.0测试台入口，补回跳过负担说明，防火墙改接ES，Step1加关键圣经节 |
| `8cd92de4` | Piseth | 2026-10-17 | 新测试台：Step1 思考过程/翻译，负担说明改名与四候选，推荐理由前端展示 |
| `30241856` | Piseth | 2026-10-16 | 新测试台：Step1 推荐重点记录思考文字、丢弃与截断词 |
| `d76267b3` | Piseth | 2026-10-15 | PanAI 新测试台：内在素质层（方案 A）、负担说明调整、新资料导入脚本 |
| `ba2fc391` | Piseth | 2026-10-06 | 4.0测试台：情境B采用“混合版”写作约束… |
| `09a4c529` | Piseth | 2026-10-06 | 4.0测试台：情境B加约束… |
| `506ead57` | Piseth | 2026-10-06 | 4.0测试台：约束句放宽… |
| `86a5f5a9` | Piseth | 2026-10-06 | 4.0测试台：情境B…不得复述… |
| `5e468e8e` | Piseth | 2026-10-06 | 4.0测试台：情境B每条目标改为280-360… |
| `8ee3b821` | Piseth | 2026-10-06 | 4.0测试台：情境B字数下限 260… |
| `cb611a87` | Piseth | 2026-10-06 | 4.0测试台：情境A字数目标… |
| `cbb65282` | Piseth | 2026-10-06 | 后端启动器 run_backend.py：日志同时写入 logs/… |
| `bbf6e67f` | Piseth | 2026-10-06 | 4.0测试台：历史记录支持删除… |
| `b0eb67c8` | Piseth | 2026-10-06 | 4.0测试台：页面新增历史记录… |
| `8fd85dca` | Piseth | 2026-10-06 | 4.0测试台：把属于该层的词标出来… |
| `b2637c94` | Piseth | 2026-10-06 | 4.0测试台：字数改为目标300-360… |
| `6fd2015a` | Piseth | 2026-10-06 | 新增【原流程不变】4.0测试台（第1项…） |

### 2.2 对方相对共同祖先的文件变更（`git diff --stat <base>...origin/master`）

共 **46 files, +32528 / −4**。要点：

- **新测试台独立进程**：`main_t35test.py`、`t35test/**`、`run_backend.py`、前端 `Panai35Test.vue`
- **v40_burden 包保留**：`kg_rag/v40_burden/**`（含 `terms_2373.json`）；`774dfa8c` 已从主站 `main.py` **卸下** `v40_burden` 与 `t35test` 挂载（文件夹保留）
- **Amana**：`back_cn/routers/amana_router.py`、`front_cn` 首页入口
- **其它**：`Search.vue` 文案、「负担的重点」标签；`.gitignore` 增加 `back_mic/backend/data/v40_burden/`
- **对冲突三文件的净改动很小**：`main.py` +1 行（注释）、`ToolBox.vue` +1、`router/index.js` +6（相对 base 的 stat）；实质是在保留旧 `/panai4-test` 的同时叠加 `/panai35-test`，以及主站卸下 t35/v40 挂载后留下注释

### 2.3 是否碰到「我们已删除的测试台文件」

对路径过滤日志（`panai4/router.py`、`panai4/sc/`、`PanAI4*.vue`、`docs/panai4_*` 等）在 `HEAD..origin/master` 下：

- **对方这些提交没有改动那些已被我们删除的测试台源文件/文档路径**（path 过滤 log 为空）。
- 对方树中这些文件仍在，但相对共同祖先 **内容未变** → 合并后删除胜出（无 UD）。
- **仍有「引用层」碰撞**（见下节）：对方 `main.py` / `ToolBox.vue` / `router/index.js` **仍引用** 已删除的 `panai4_*` 与 `PanAI4Test.vue`。这才是 3 个 UU 的根因。

单独列出「对方仍依赖、但我方已删」的引用目标：

| 对方仍引用 | 我方 HEAD | 合并后默认 |
|------------|-----------|------------|
| `panai4.router` / `panai4.sc.router` / `panai4.db` | 已删模块与 lifespan 调用 | 模块不存在 |
| `/panai4-test` + `PanAI4Test.vue` | 组件已删、路由/菜单已去 | 组件不存在 |
| （对比）`/panai35-test` + `Panai35Test.vue` + `t35test` | 我方无此功能 | **对方新增，应保留**（API 在 8001） |

---

## 3. 逐个冲突文件 · 逐个冲突块

约定：`<<<<<<< HEAD` = 我方；`>>>>>>>` 侧 = `origin/master`。

### 3.1 `back_mic/backend/main.py`（1 块）

**标记行号（工作区）：** `<<<<<<<` L427 · `=======` L428 · `>>>>>>>` L432  

| | 内容 |
|--|------|
| **我方 (HEAD)** | （空）— 删除两行 `include_router(panai4_*)` |
| **对方** | `app.include_router(panai4_router)`<br>`app.include_router(panai4_sc_router)`<br>`# PanAI 新测试台（/api/t35test）已拆到独立后端 main_t35test.py（端口 8001），不在主站进程里跑` |

上下文：上一行是 `include_router(kg_rag_router)`，下一行是 `include_router(feast_router)`。

**我方意图：** 拆除 4.0 测试台在主站的挂载（与已删的 import / `init_db` 一致）。  
**对方意图：** 保留旧 `panai4`/`panai4_sc` 主站挂载；用注释说明 **新测试台** 已迁到 `main_t35test.py:8001`（`774dfa8c` 同时卸下了主站上的 `t35test` 与 `v40_burden` 挂载）。  
**是否互斥：** **对 `panai4_*` 两行是真互斥**（删 vs 留）。注释行与「删除挂载」**不互斥**，可单独保留。  
**相邻自动合并：** import / lifespan 已按我方去掉 panai4；若此处误收对方两行 `include_router`，会变成 **有调用、无 import、无模块** → `NameError` / `ModuleNotFoundError`。

### 3.2 `front_mic/frontend/src/components/toolbox/ToolBox.vue`（1 块）

**标记行号：** `<<<<<<<` L76 · `=======` L77 · `>>>>>>>` L80  

| | 内容 |
|--|------|
| **我方** | （空）— 去掉图谱测试区里的 PanAI 4.0 卡片 |
| **对方** | `/panai4-test`「PanAI 4.0 测试台」卡片<br>`/panai35-test`「PanAI 新测试台」卡片 |

**我方意图：** 菜单不再进入已删的 4.0 测试台。  
**对方意图：** 保留 4.0 入口，并 **新增** 新测试台入口。  
**是否互斥：** 对 `panai4-test` 卡片 **真互斥**；`panai35-test` 与「删 4.0」**不互斥**，应保留对方新增卡片。

### 3.3 `front_mic/frontend/src/router/index.js`（1 块）

**标记行号：** `<<<<<<<` L117 · `=======` L118 · `>>>>>>>` L131  

| | 内容 |
|--|------|
| **我方** | （空）— 去掉 `/panai4-test` 路由 |
| **对方** | `/panai4-test` → `PanAI4Test.vue`<br>`/panai35-test` → `Panai35Test.vue` |

**我方意图：** 不再注册已删组件路由。  
**对方意图：** 保留旧路由 + **新增** 新测试台路由（`Panai35Test.vue` 已在「Changes to be committed」）。  
**是否互斥：** `/panai4-test` **真互斥**；`/panai35-test` **应保留**。若整段收对方且组件已删 → `npm run build` 动态 import 失败。

---

## 4. 建议解决方式（阶段一仅建议，未执行）

原则：**保留对方新功能（PanAI 新测试台 / Amana / t35 独立进程等），同时保留我对旧 4.0 测试台引用的删除。**

| 文件 | 建议结果 | 说明 |
|------|----------|------|
| `main.py` | 冲突块最终为：**不要**两行 `include_router(panai4_*)`；**建议保留**对方那条 8001 注释 | 与已自动合并的「无 panai4 import / 无 init_db」一致 |
| `ToolBox.vue` | **只留** `go('/panai35-test')` 卡片；**不要** `panai4-test` | 新功能入口 + 旧台拆除 |
| `router/index.js` | **只留** `/panai35-test` → `Panai35Test.vue`；**不要** `/panai4-test` | 同上 |

### 依赖已删测试台的风险（必须明确）

1. **若对三文件盲目 `checkout --theirs`：**  
   - 后端：`panai4_router` 未导入或模块已删 → 主站无法启动。  
   - 前端：`PanAI4Test.vue` 已删 → build/路由失败。  
2. **若盲目全收我方（三处都变空）：**  
   - 旧台引用没了（好），但 **丢失** `/panai35-test` 菜单与路由；`Panai35Test.vue` 虽已 staged，UI 进不去。  
3. **对方新测试台 API 不在主站进程：** 前端打 `/api/t35test/*`，需独立 `main_t35test.py`（8001）及 nginx/`location ^~ /api/t35test/`（配置不在仓库，见 `774dfa8c`）。只合代码不配代理时，页面在但接口 404。  
4. **`kg_rag/v40_burden/`：** 对方保留包、主站已不挂载；前端 `V40BurdenTest` 亦已在对方历史中删入口。合并后包会进来，但 **不会** 因本 3 个冲突块自动恢复 `/api/v40burden`。这不是本冲突的阻塞项，但不要误以为「保留对方 main 冲突块」就能恢复 v40（对方当前 main 也未挂 v40）。  
5. **旧 `/api/panai4*`：** 按建议解决后主站不应再挂；与「删除测试台」目标一致。

---

## 5. 合并后验证计划（解决冲突并完成合并提交之后）

1. **后端**  
   - 在 `back_mic/backend`：`python -c "import main"`（或项目惯用入口）应成功。  
   - 确认源码/OpenAPI：**无** `/api/panai4`、`/api/panai4_sc`（或等价 panai4 测试台前缀）挂在主站。  
   - 确认对方功能仍在：`main_t35test` 可 import；`t35test.router` 前缀 `/api/t35test`；`back_cn` Amana 路由仍注册；主站既有 `kg_rag` / feast 等未丢。  
2. **前端**  
   - `front_mic/frontend`：`npm run build` 通过。  
   - 路由表有 `/panai35-test`，**无** `/panai4-test`；工具箱有「PanAI 新测试台」、无「PanAI 4.0 测试台」。  
3. **忽略规则**  
   - `.gitignore` 仍含 `back_mic/backend/panai4/data/graph_annotations/*.json`（我方大 JSON 忽略）。  
   - 且含对方 `back_mic/backend/data/v40_burden/`。  
   - `git check-ignore` / `git status`：两大图谱标注 JSON 不应变成待提交。  
4. **可选联调（不连生产图谱/ES 也可做静态检查）**  
   - 文档/脚本确认：新测试台需 8001 + 代理；勿期望主站进程提供 `/api/t35test`。

---

## 6. 两种选择的利弊与推荐

### A. 继续解决冲突并完成合并

- **利：** 一次纳入对方 21 个提交（新测试台独立进程、Amana、Search 文案、run_backend 等）与我方删台 + 数据导入；冲突面极小（3 文件 × 1 块），意图清晰。  
- **弊：** 需手工拼出「删 panai4 引用 + 留 panai35」；还要注意 8001/nginx 不在仓库；合并提交后仍有大量已 staged 新文件，应用验证计划挡回归。

### B. `git merge --abort` 回到合并前再重做

- **利：** 工作区立刻干净；可改用 rebase、或先在分支上预演冲突策略。  
- **弊：** 不消除实质冲突，重 pull/merge 仍会打在同一 3 处；已自动合并进 index 的对方文件需再走一遍；浪费当前已算清的盘点。

### 推荐

**推荐 A：继续解决冲突（按第 4 节手工合并），不要 abort。**  
理由：冲突仅引用层、与「删旧台 / 留新台」原则一一对应；abort 不降低难度，只推迟。  
（本阶段仍 **不要** 执行解决或 abort；等明确指令再动 git 状态。）
