# Scripture 4851 → 4848：本机操作溯源

## 结论

| 项 | 值 |
|---|---|
| 脚本 | `qa4/tools/graph_fixes/fix_graph_20261116.py` |
| 成功 apply 日志 | `G:\PanAI4.0专用\logs\graph_fix\apply_20261116_091018.json` |
| 运行时间（日志名 UTC） | **2026-11-16 09:10:18 UTC**（约北京时间 17:10） |
| 应用前备份 | `G:\PanAI4.0专用\backups\graph_fix\backup_before_apply_20261116_091012.json` |
| 结果 | `ok=true`，`tx_outcome=committed`；节点 7334→7331；Scripture 4851→4848；SUPPORTED_BY 仍为 9803 |

更早两次同日尝试（`apply_20261116_084643.json`、`090628.json`）未作为最终态；最终以 `091018` 为准。

## 做了什么

### 1. 合并 3 个「贴后」→ 已有「帖后」（净删 3 个 Scripture）

对每条：把 `(Truth_Point)-[:SUPPORTED_BY]->(贴后…)` **迁到** 已存在的 `帖后…`；若目标已有同 Truth_Point 边则合并掉重复边；然后 **`DETACH DELETE` 错误节点**。

| 删除的 wrong ref | 合并到 correct | 迁边的 Truth_Point |
|---|---|---|
| 贴后三5 | 帖后三5 | 神的爱、爱神 |
| 贴后三17 | 帖后三17 | 记号 |
| 贴后二13 | 帖后二13 | 那灵的圣别 |

→ Scripture **-3**（4851→4848）。

### 2. 改名 3 个「贴后」→「帖后」（不删节点，只改 `ref`）

| from | to | 关联 term（校验用） |
|---|---|---|
| 贴后二3 | 帖后二3 | 方法 |
| 贴后三16 | 帖后三16 | 平安 |
| 贴后三1 | 帖后三1 | 主的话 |

关系：节点保留，`SUPPORTED_BY` 入边随节点保留，无删边。

### 3. 有机发展标记（与 Scripture 计数无关）

- `set_organic_true`：`基督的十字架`
- `remove_organic`：`基督的死`

## 关系处理要点

- 仅处理 `SUPPORTED_BY`（Truth_Point → Scripture）。
- 合并：边迁移到正确 Scripture；若已存在同端点边则净减少 1 条重复边；随后删除错误 Scripture。
- 改名：不迁移边，只改 `ref`。
- apply 期望：`expect_supported_by_after = 9803`（与改前一致）。
