# Git 合并冲突 · 阶段二：解决与验证

> 未 `git commit`、未 `git push`、未 `merge --abort`、未整文件 `--ours`/`--theirs`。  
> 除本报告与下列三个冲突文件外，未改其它业务文件。未打开/打印 `.env`；未连图谱/ES/服务器。

## 1. 三个冲突块：解决前 → 解决后

### 1.1 `back_mic/backend/main.py`

**解决前：**

```
app.include_router(kg_rag_router)
<<<<<<< HEAD
=======
app.include_router(panai4_router)
app.include_router(panai4_sc_router)
# PanAI 新测试台（/api/t35test）已拆到独立后端 main_t35test.py（端口 8001），不在主站进程里跑
>>>>>>> de95802a…
app.include_router(feast_router)
```

**解决后：**

```
app.include_router(kg_rag_router)
# PanAI 新测试台（/api/t35test）已拆到独立后端 main_t35test.py（端口 8001），不在主站进程里跑
app.include_router(feast_router)
```

- 去掉两行 `panai4_*` `include_router`
- 保留对方 8001 注释
- 冲突标记已删

### 1.2 `front_mic/frontend/src/components/toolbox/ToolBox.vue`

**解决前：**

```
<a-card-grid … go('/kg-rag-test') …>KG-RAG 测试工作台</a-card-grid>
<<<<<<< HEAD
=======
<a-card-grid … go('/panai4-test') …>PanAI 4.0 测试台</a-card-grid>
<a-card-grid … go('/panai35-test') …>PanAI 新测试台</a-card-grid>
>>>>>>> …
</a-card>
```

**解决后：**

```
<a-card-grid … go('/kg-rag-test') …>KG-RAG 测试工作台</a-card-grid>
<a-card-grid … go('/panai35-test') …>PanAI 新测试台</a-card-grid>
</a-card>
```

### 1.3 `front_mic/frontend/src/router/index.js`

**解决前：** `/kg-rag-test` 路由后，对方块含 `/panai4-test`→`PanAI4Test.vue` 与 `/panai35-test`→`Panai35Test.vue`；我方为空。

**解决后：** 仅保留：

```js
  {
    path: "/panai35-test",
    name: "Panai35Test",
    component: () => import("../components/toolbox/Panai35Test.vue"),
    meta: { requiresAuth: true },
  },
```

### 1.4 冲突标记扫尾

三文件均无 `<<<<<<<` / `=======` / `>>>>>>>`。

---

## 2. 验证：命令与结果

### 2.1 后端 `import main` 与 panai4 路由

```text
cd back_mic/backend
python -c "import main; … openapi paths …"
```

| 检查项 | 结果 |
|--------|------|
| `import main` | **OK** |
| OpenAPI 路径总数（解决后） | **96** |
| 含 `/api/panai4` 或 panai4 | **无** (`[]`) |
| `main.py` 源码 `panai4.router` / `panai4.sc` / `panai4.db` / `panai4_router` | **NONE** |

`app.include_router` 行数对比（源码层，解决前后代理「路由挂载数量」）：

| 版本 | `include_router(` 次数 | 说明 |
|------|------------------------|------|
| 我方 stage2 / 解决前意图 | **18** | 无 panai4 |
| 对方 stage3 | **20** | 多 `panai4_router`、`panai4_sc_router` |
| 解决后工作区 | **18** | 与我方一致；仅多 1 行注释，无多挂载 |

解决后 OpenAPI 抽样：`/api/kg_rag*` 20 条；feast 相关 7；roundtable 7 —— 主站原有能力仍在。对方多出的 2 个 panai4 挂载未纳入（模块已删，也无法安全 import 对方完整 `main` 做对拍）。

### 2.2 对方功能仍在

| 检查 | 命令/方式 | 结果 |
|------|-----------|------|
| `import main_t35test` | `python -c "import main_t35test"` | **OK** |
| `t35test.router` 前缀 | `from t35test.router import router` → `router.prefix` | **`/api/t35test`** |
| t35 OpenAPI | `main_t35test.app.openapi()` | **9** 条，均在 `/api/t35test/…`（如 `query`、`generate_burden`、`eval/outline` 等） |
| Amana | `back_cn/main.py` 含 `include_router(amana_router)`；`amana_router.py` | **已注册**，prefix **`/api/cn/amana`** |
| kg_rag / feast | 见上 OpenAPI | **未丢** |

### 2.3 前端

```text
cd front_mic/frontend
npm run build
```

| 检查 | 结果 |
|------|------|
| `npm run build` | **通过**（vite build，~22s，exit 0） |
| 路由有 `/panai35-test` | **有** |
| 路由无 `/panai4-test` | **无** |
| 工具箱「PanAI 新测试台」 | **有** |
| 工具箱「PanAI 4.0 测试台」 | **无** |
| 全前端搜 `PanAI4Test` / `PanAI4Prompts` / `PanAI4SC` / `panai4-test`（排除 node_modules/dist） | **无残留** |

### 2.4 忽略规则

```text
git check-ignore -v back_mic/backend/panai4/data/graph_annotations/organic_advance.json
git check-ignore -v back_mic/backend/panai4/data/graph_annotations/truth_dictionary_3a3b.json
```

| 规则/文件 | 结果 |
|-----------|------|
| `.gitignore` 含 `back_mic/backend/panai4/data/graph_annotations/*.json` | **有**（L59） |
| `.gitignore` 含 `back_mic/backend/data/v40_burden/` | **有**（L20，合并已暂存） |
| `organic_advance.json` | 被上述 graph_annotations 规则忽略 |
| `truth_dictionary_3a3b.json` | 同上 |
| `git diff --cached --name-only` 含上述两 JSON | **无** |

### 2.5 相对我方 / 对方的 diff（无误改面）

相对 **我方 HEAD / stage2**（解决后多保留了对方新增）：

| 文件 | numstat（+ / −） |
|------|------------------|
| `back_mic/backend/main.py` | +1 / 0（仅 8001 注释） |
| `ToolBox.vue` | +1 / 0（panai35 卡片） |
| `router/index.js` | +6 / 0（panai35 路由对象） |
| **合计** | **+8 / 0** |

相对 **对方 MERGE_HEAD / stage3**（去掉旧 4.0 引用）：

| 文件 | numstat（+ / −） |
|------|------------------|
| `main.py` | 0 / 8（含去掉 panai4 import+lifespan 差异的对拍；工作区相对 stage3 文件 diff 为删 panai4 相关） |
| `ToolBox.vue` | 0 / 1（去掉 panai4 卡片） |
| `router/index.js` | 0 / 6（去掉 panai4 路由） |
| **合计（三文件 vs MERGE_HEAD）** | **0 / 15** |

说明：`git diff --stat` vs `MERGE_HEAD` 的 `main.py` −8 行，包含对方仍保留的 `panai4` import/lifespan 与我方已自动合并删除部分的差异，不仅是冲突块内两行；冲突块本身只去掉了两行 `include_router` 并保留注释。三文件以外未做业务编辑。

### 2.6 密码检查

对三个已解决文件做字面量口令/Bearer/api_key 形态扫描：**PASS**（无命中）。未读取 `.env`。

---

## 3. 暂存

```text
git add back_mic/backend/main.py
git add front_mic/frontend/src/components/toolbox/ToolBox.vue
git add front_mic/frontend/src/router/index.js
```

未使用 `git add .`。

### 最终 `git status`（摘要）

```text
On branch master
Your branch and 'origin/master' have diverged,
and have 1 and 21 different commits each, respectively.

All conflicts fixed but you are still merging.
  (use "git commit" to conclude merge)

Changes to be committed:
  …（含上述三文件 + 对方已自动合并入 index 的 Amana/t35test/v40_burden 等）…

Untracked files:
  docs/panai4_graph/git_merge_conflict.md
  （以及本报告 git_merge_resolve.md，若尚未 add）
```

- **无未合并路径（unmerged = 0）**
- **等待合并提交**（本阶段未执行 commit）

---

## 4. 收尾声明

- **未 commit、未 push**
- **未修改**上述三个冲突文件以外的业务文件（本报告 `docs/panai4_graph/git_merge_resolve.md` 按任务要求写入）
- **密码检查通过**
- 未连接图谱、ES、服务器
