# 任务 5：git 整理计划（只读，未执行任何写操作）

> 盘点时间：2026-11-06；仓库 `G:\copypan`。仅使用 `status` / `diff --stat` / `ls-files` / `check-ignore`。

## 1. 现状盘点

| 类别 | 数量 | 说明 |
| --- | ---: | --- |
| 已修改（M） | **8** | 见分组 |
| 未跟踪（??） | **46** | 见分组 |
| 被忽略（!!） | **约 2,049** | 主要为 `__pycache__`、`logs/`、`*.env` 等 |

### 按目录汇总（未跟踪）

- `back_mic/backend/panai4/outline/`：10（`apply_life_fix.py` + 8×`probe_*.py` + `config.py.bak_20261106`）
- `docs/panai4_es/archive/`：36（本轮 ES 报告/CSV/临时扫描文件）

### 已修改（8）

- `back_mic/backend/panai4/outline/config.py`（+3，任务2 overrides）
- `docs/3a_export.json`（±1）
- `docs/panai4_graph/` 下 5 个数据/映射文件（各 ±1）
- `docs/panai4_sc/null_terms.csv`（±1）

`git diff --stat`：`8 files changed, 10 insertions(+), 7 deletions(-)`。

## 2. 分组

### 组 A：全流程测试台
- **当前工作区：几乎为空**（无 Vue/pipeline 未提交改动）。
- 仅旁系：`docs/panai4_sc/null_terms.csv`（M）——是否并入 A 由你决定；也可并入 G。

### 组 B：kg_rag
- **当前工作区：空**（无 kg_rag 改动）。若你本地另有未保存改动，请自行补入本计划。

### 组 C：图谱
- M×5：`docs/panai4_graph/` 下列文件（文件名含中文，git 显示八进制转义）：
  - `2372个词条…txt`、`2373个词条…txt`
  - `主恢复真理词典_标签映射_已校对 (1).json`
  - `主恢复真理词典_词条主干枝子映射 (1).json`
  - `词条三档分类.json`

### 组 D：ES 脚本
- M：`back_mic/backend/panai4/outline/config.py`
- ??：`apply_life_fix.py` + `probe_12490_assets.py` + `probe_life_*.py`（共 9 个 .py）
- **不要**提交：`config.py.bak_20261106`

### 组 E：docs/panai4_es
- ??×36：`docs/panai4_es/archive/` 下本轮清单/阶段报告/配对 CSV 等。
- **建议**：入库「最终结论性」报告与清单（`life_12490_fix_final_v4.csv`、`life_fix_stage{01,2_summary,3_summary}.md`、`task2_book_overrides.md`、后续 `task5_*` / `text_life_*` / `index_tasks_summary.md`）；过程稿（`fix_list_v1/v2`、大量 `stage2_*` 中间报告、`_git_*` 临时文件、`_task5_scan.py`）可只保留 summary 或移出仓库。
- **体积**：当前 archive 未跟踪文件均 **&lt;5MB**（无超大 JSONL）。

### 组 F：不应入库
- `config.py.bak_20261106`
- `__pycache__/`、`logs/`（已忽略）
- `.env`（已忽略）
- 建议新增 ignore：`*.bak`、`docs/panai4_es/archive/_*.txt`、`docs/panai4_es/archive/_*.py`

### 组 G：无法归类
- M：`docs/3a_export.json`（与本次生命读经/ES 修订无直接关系）

## 3. 风险清单

1. **`git clean -fd` 会删的未跟踪脚本（仅列出，勿执行）**  
   `apply_life_fix.py`、全部 `probe_life_*.py`、`probe_12490_assets.py`，以及 `docs/panai4_es/archive/` 下全部 ?? 报告。
2. **未跟踪 &gt;5MB**：无。
3. **硬编码密钥检查**（`panai4/` + `kg_rag/` 已改/未跟踪）：**0 条**疑似密钥赋值。
4. **路径硬编码（G:\\ / C:\\）出现次数（仅 .py）**  
   - `config.py`: 3  
   - `apply_life_fix.py`: 4  
   - 各 `probe_*.py`: 1–4  
   - `_task5_scan.py`: 2  

## 4. 建议提交顺序与信息

1. **组 D-config**：`chore(outline): 生命读经书名 BOOK_TITLE_OVERRIDES`  
   add：仅 `back_mic/backend/panai4/outline/config.py`
2. **组 D-scripts**：`feat(outline): 生命读经修订 apply_life_fix 与探测脚本`  
   add：`apply_life_fix.py` + 9 个 probe（不含 `.bak`）
3. **组 E（精选）**：`docs(es): 生命读经 12490 修订最终报告与清单`  
   add：见下方精选清单
4. **组 C**：`docs(graph): 更新词条映射与分类`（若确认改动有意）
5. **组 G / A 旁系**：单独或丢弃：`docs/3a_export.json`、`docs/panai4_sc/null_terms.csv`

### 组 E 建议精确 add（示例）

```
docs/panai4_es/archive/life_12490_fix_final_v4.csv
docs/panai4_es/archive/life_fix_stage01.md
docs/panai4_es/archive/life_fix_stage2_summary.md
docs/panai4_es/archive/life_fix_stage3_summary.md
docs/panai4_es/archive/life_fix_stage3_precheck.md
docs/panai4_es/archive/task2_book_overrides.md
docs/panai4_es/archive/task5_git_plan.md
docs/panai4_es/archive/task5_git_commands.ps1
```

（过程 probe 报告 / v1–v3 清单是否入库由你定；默认可不 add。）

### 建议加入 .gitignore（只给文本，未改文件）

```
*.bak
docs/panai4_es/archive/_git_*.txt
docs/panai4_es/archive/_task5_scan.py
```

## 5. 密钥泄露检查
- 本报告内存比对：**通过**。
