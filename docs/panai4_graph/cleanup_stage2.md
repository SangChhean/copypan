# PanAI4 清理 · 阶段二报告

日期：2026-11-06  
范围：拆除测试台引用与文件；删除本地运行数据 / 测试台文档；删除两份旧 JSON 并修 `inventory_v4_pre.py`。  
约束遵守：未打开/打印 `back_mic/backend/.env`；未运行 `build_v4.py`；未连接图谱与 ES；未碰服务器；未 git commit；未改 `.gitignore`。

---

## 步骤 0：快照与备份

### 0.1 清理前 `git status --short` 基线

完整输出已存 `logs/cleanup_stage2_git_status_before.txt`（102 行）。原文：

```
 M .gitignore
 M back_mic/backend/panai4/outline/config.py
 M docs/3a_export.json
 M "docs/panai4_graph/2372个词条（已确定一一对应为concept节点）.txt"
 M "docs/panai4_graph/2373个词条（已确定一一对应为concept节点）.txt"
 M "docs/panai4_graph/主恢复真理词典_标签映射_已校对 (1).json"
 M "docs/panai4_graph/主恢复真理词典_词条主干枝子映射 (1).json"
 M "docs/panai4_graph/词条三档分类.json"
 M docs/panai4_sc/null_terms.csv
?? back_mic/backend/panai4/data/
?? back_mic/backend/panai4/graph/copy_to_bracket_inner.py
?? back_mic/backend/panai4/graph/delete_old_relations.py
?? back_mic/backend/panai4/graph/fix_scripture_text.py
?? back_mic/backend/panai4/graph/import_annotation.py
?? back_mic/backend/panai4/graph/import_annotation_v2.py
?? back_mic/backend/panai4/graph/import_annotation_v3.py
?? back_mic/backend/panai4/graph/import_annotation_v4.py
?? back_mic/backend/panai4/graph/import_general_annotation.py
?? back_mic/backend/panai4/graph/import_high_peak_content_v2.py
?? back_mic/backend/panai4/graph/import_relations_29.py
?? back_mic/backend/panai4/graph/import_scripture_nodes.py
?? back_mic/backend/panai4/graph/inventory_v4_pre.py
?? back_mic/backend/panai4/inherit/apply_text_life_fix.py
?? back_mic/backend/panai4/inherit/rollback_text_life_local.py
?? back_mic/backend/panai4/inherit/rollback_text_life_remote.py
?? back_mic/backend/panai4/organize_index_data.py
?? back_mic/backend/panai4/outline/apply_life_fix.py
?? back_mic/backend/panai4/outline/config.py.bak_20261106
?? back_mic/backend/panai4/outline/probe_12490_assets.py
?? back_mic/backend/panai4/outline/probe_life_fixlist.py
?? back_mic/backend/panai4/outline/probe_life_fixlist_v2.py
?? back_mic/backend/panai4/outline/probe_life_fixlist_v3.py
?? back_mic/backend/panai4/outline/probe_life_in_12490.py
?? back_mic/backend/panai4/outline/probe_life_in_12490_r2.py
?? back_mic/backend/panai4/outline/probe_life_outline.py
?? back_mic/backend/panai4/outline/probe_life_outline2.py
?? docs/panai4_es/archive/…（若干 archive 文件）
?? docs/panai4_graph/annotation_*.md / import_*.md / neo4j_v4_inventory_pre.md / cleanup_inventory.md 等
```

说明：基线时 `main.py` / `ToolBox.vue` / `router/index.js` 尚干净；`.gitignore` 已是既有修改（本阶段未再改）。

### 0.2 备份复制

目标：`G:\PanAI4.0专用\备份_测试台_20261106\`（复制，非移动；保持相对目录结构）

| 源 | 备份内容 |
|---|---|
| `back_mic/backend/data/panai4/` 整目录 | `…\备份_测试台_20261106\back_mic\backend\data\panai4\` |
| `logs/sc_*.log`、`logs/sc_fullflow_*.log` | `…\备份_测试台_20261106\logs\` |

### 0.3 备份校验

校验记录：`logs/cleanup_stage2_backup_verify.txt`

| 项 | 源 | 备份 | 结果 |
|---|---|---|---|
| data 文件数 | 28 | 28 | 通过 |
| data 总字节 | 83,099,648 | 83,099,648 | 通过 |
| sc 日志文件数 | 26 | 26 | 通过 |
| sc 日志总字节 | 441,934 | 441,934 | 通过 |
| `panai4.db` SHA256 | `8290728D183D9B1011DC6CBDC0056D1DA859BD85DFF1F0A2097EF911E98D44F4` | 同左 | 通过 |

**结论：步骤 0 通过，可继续。**

---

## 步骤 1：先改引用（最小补丁）

### 改了什么

1. `back_mic/backend/main.py`
   - 去掉 `panai4_router`、`panai4_sc_router` 的 import 与 `include_router`
   - lifespan 去掉 `init_db()`、`mark_running_interrupted()`
   - 其余逻辑不动（diff：8 行删除）
2. `front_mic/frontend/src/components/toolbox/ToolBox.vue`
   - 删除「PanAI 4.0 测试台」卡片（diff：1 行删除）
3. `front_mic/frontend/src/router/index.js`
   - 删除 `/panai4-test` 路由（diff：6 行删除）

### 验证

| 命令 | 结果 |
|---|---|
| 在 `back_mic/backend` 导入 `main`，创建 FastAPI app | `main_ok FastAPI`；`panai4_routes []` |
| `cd front_mic/frontend && npm run build` | exit 0，built successfully |

**结论：步骤 1 通过。**

---

## 步骤 2：删前端测试台文件

### 删了什么

- `front_mic/frontend/src/components/toolbox/PanAI4Test.vue`
- `front_mic/frontend/src/components/toolbox/PanAI4Prompts.vue`
- `front_mic/frontend/src/components/toolbox/PanAI4SC.vue`

### 验证

| 检查 | 结果 |
|---|---|
| `npm run build` | exit 0 |
| `front_mic` 内搜 `PanAI4` / `panai4-test` / `/api/panai4` | 无匹配（rg exit 1 = 无残留） |

**结论：步骤 2 通过。**

---

## 步骤 3：删后端测试台模块

### 删了什么

- `panai4/router.py`、`runner.py`、`db.py`、`export_docx.py`、`pipeline.py`、`llm.py`、`config.py`、`prompt_diff.py`
- 全部 `panai4/verify_*.py`
- 整个 `panai4/sc/`
- `panai4/prompts/` 下全部 `.py`（`__init__.py`、`prompt*.py`、`_verify_step_a.py` 等）
- **保留** `panai4/prompts/texts/` 下全部文本（现仍 9 个 `.txt`）

### 保留确认

- `panai4/graph/`、`outline/`、`inherit/`、`bible/`、`pano/`
- `organize_index_data.py`、`push_remote_v2.py`、`panai4/__init__.py`
- `panai4/data/graph_annotations/`（含 `organic_advance.json`、`truth_dictionary_3a3b.json`）

### 验证

| 命令 | 结果 |
|---|---|
| `python -m compileall -q panai4`（在 `back_mic/backend`） | exit 0 |
| 对 `graph/`、`outline/`、`inherit/`、`bible/`、`pano/` 剩余脚本逐个 import | 通过（约 61 个；无因缺 `panai4.config` / `llm` / `db` 失败） |
| 再次 `import main` | `main_ok`；`/api/panai4*` 路由不存在 |

**结论：步骤 3 通过。无需停下列依赖缺口。**

---

## 步骤 4：删本地运行数据

前置：步骤 0 备份校验已通过。

### 删了什么

- `back_mic/backend/data/panai4/`（整目录）
- `logs/sc_*.log`、`logs/sc_fullflow_*.log`（共 26 个）

### 验证

| 检查 | 结果 |
|---|---|
| `data/panai4` 已不存在 | True |
| 残留 sc 日志数 | 0 |
| `import main` | `main_ok` |

**结论：步骤 4 通过。**

---

## 步骤 5：删测试台专用文档

### 删了什么

- `docs/panai4_ui/`（整目录）
- `docs/panai4_fullflow/`（整目录）
- `docs/panai4_sc/`（整目录，含已跟踪与未跟踪文件）

### 保留确认

- `docs/panai4_prompts/` 存在
- `docs/PanAI4.0_新系统框架实施方案.md` 存在
- `docs/panai4_graph/`、`docs/panai4_es/` 存在

**结论：步骤 5 通过。**

---

## 步骤 6：删两份 JSON，并修 inventory 脚本

### 删了什么

- `docs/3a_export.json`
- `docs/panai4_graph/词条三档分类.json`

### 改了什么（本阶段唯一允许修改的 graph 脚本）

- `back_mic/backend/panai4/graph/inventory_v4_pre.py`
  - 从候选路径 / `extra_paths` / 报告文案中移除对上述两文件的依赖
  - 文案注明鸟瞰正文以 `panai4/data/graph_annotations/truth_dictionary_3a3b.json` 为准
  - **未改**历史报告 `neo4j_v4_inventory_pre.md` 等

### 验证

| 检查 | 结果 |
|---|---|
| 两 JSON 已不存在 | True |
| `import panai4.graph.inventory_v4_pre` | `inventory_import_ok True` |

**结论：步骤 6 通过。**

---

## 步骤 7：最终核对

### 7.1 清理后 `git status --short`

完整输出：`logs/cleanup_stage2_git_status_after.txt`（约 280 行）。  
相对基线新增的清理效果：约 **178** 条 tracked 删除（`D`），以及 3 个本阶段代码修改：

| 本阶段应改 | git 状态 | 说明 |
|---|---|---|
| `back_mic/backend/main.py` | `M` | 去测试台路由 / lifespan |
| `front_mic/frontend/src/components/toolbox/ToolBox.vue` | `M` | 去测试台卡片 |
| `front_mic/frontend/src/router/index.js` | `M` | 去 `/panai4-test` |
| `back_mic/backend/panai4/graph/inventory_v4_pre.py` | `??`（内容已改） | 基线即未跟踪；本阶段只改这一处 graph 脚本 |

其余 `D` 均为测试台模块 / Vue / 文档 / 两 JSON 的删除。  
基线已有、本阶段未动的修改仍在：`M .gitignore`、`M outline/config.py`、若干 `docs/panai4_graph` 既有 M、大量既有 `??` 图谱/ES 工作文件。

### 7.2 未误删确认

| 路径 / 文件 | 完好 |
|---|---|
| `panai4/graph` | True |
| `panai4/outline` | True |
| `panai4/inherit` | True |
| `panai4/bible` | True |
| `panai4/pano` | True |
| `panai4/data/graph_annotations/` | True |
| `organic_advance.json` | True |
| `truth_dictionary_3a3b.json` | True |
| `docs/panai4_graph/` | True |
| `docs/panai4_es/` | True |
| `docs/panai4_prompts/` | True |
| `panai4/prompts/texts/` | True（9 txt） |
| `.gitignore` | 本阶段未改（仍为基线既有 `M`） |

### 7.3 最终检查

| 检查 | 结果 |
|---|---|
| 后端 `import main`；路由含 `panai4` | `main_ok`；`api_panai4 []` → **`/api/panai4/*` 现已不存在** |
| 后端 `python -m compileall -q panai4` | exit 0 |
| 前端 `npm run build` | exit 0（built in ~19s） |
| 前端残留引用 `PanAI4` / `panai4-test` / `/api/panai4` | 无 |

---

## 结尾声明

- **备份位置**：`G:\PanAI4.0专用\备份_测试台_20261106\`
- **备份校验**：data 28/83099648、logs 26/441934、`panai4.db` SHA256 源备一致（见上）
- **未修改的脚本**：除 `inventory_v4_pre.py` 外，未改任何 `graph|outline|inherit|bible|pano` 脚本；未改 `organize_index_data.py` / `push_remote_v2.py`
- **未运行** `build_v4.py`
- **密码检查通过**：未打开、未打印 `.env`；未连图谱 / ES / 服务器
- **未 git commit**；未处理 hymns；未删 `docs/panai4_prompts/` 与 `panai4/prompts/texts/` 文本

**阶段二完成。**
