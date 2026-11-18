# 图谱修订包 · 2026-11-16

脚本：`fix_graph_20261116.py`  
修订：6 个「贴后」Scripture（3 合并 + 3 改名）+ 有机发展标记（十字架 ↔ 死）。

依赖：仅 **neo4j 官方驱动** + Python 标准库。最低驱动版本：**neo4j>=5.0.0**（显式 `Session.begin_transaction` / `commit` / `rollback`）。

## 模式用法

```bash
# 1) 只读检查（记下三个 *_all_sha 与 graph_other_sha 作为新基准）
python qa4/tools/graph_fixes/fix_graph_20261116.py --check --log-dir graph_fix_logs

# 2) 应用（先 check → 备份含快照哈希 → 显式事务内写+断言 → 全过才提交）
python qa4/tools/graph_fixes/fix_graph_20261116.py --apply --yes --log-dir graph_fix_logs --backup-dir graph_fix_backups

# 3) 验证最终态（显示 graph_other_sha；无改前基准时只显示不判错）
python qa4/tools/graph_fixes/fix_graph_20261116.py --verify --log-dir graph_fix_logs

# 4) 演练回滚（提交前核对接后 *_all / graph_other == 备份改前哈希）
python qa4/tools/graph_fixes/fix_graph_20261116.py --rollback graph_fix_backups/backup_before_apply_XXXX.json --yes
```

环境变量：`NEO4J_URI`（默认 `bolt://localhost:7687`）、`NEO4J_USER`（默认 `neo4j`）、`NEO4J_PASSWORD`（必填）。不读仓库内 env 文件。

## Srey 本机 / 服务器推荐顺序

**哈希口径已变：旧 `*_all_sha` 基准作废。** 请先重新 `--check` 取新基准（含 `graph_other_sha`）。

1. `--check` → 记下 `scripture_all_sha` / `supported_by_all_sha` / `organic_all_sha` / `graph_other_sha`
2. `--apply --yes` → 看 `BACKUP=`；失败时报告写明失败断言且「图谱未改动」
3. `--verify`
4. `--rollback <备份> --yes` 演练 → `--check`（四个哈希须与第 1 步完全一致）
5. 再 `--apply --yes` → `--verify`
6. 重复 `--apply --yes` 应打印「已应用」且不开写事务

服务器：同一脚本与参数；只改环境变量指向服务器库。

## 快照覆盖范围

受影响集合 `AFFECTED_REFS`（12）：6「贴后」+ 3 合并目标 + 3 改名目标。

| 快照 | 节点 | 属性 | 关系 |
|------|------|------|------|
| `scripture_keep_sha` | Scripture 且 ref∉受影响集合 | 全部属性（键名排序） | — |
| `supported_by_keep_sha` | — | 关系全部属性（键名排序） | `SUPPORTED_BY`，Scripture.ref∉受影响；两端=TP.name + Scripture.ref |
| `organic_keep_sha` | Truth_Point（除十字架/死） | 仅 `organic_advance` | — |
| `scripture_all_sha` | 全部 Scripture | 全部属性（键名排序） | — |
| `supported_by_all_sha` | — | 关系全部属性 | 全部 `SUPPORTED_BY`（含两端标识） |
| `organic_all_sha` | 凡带 `organic_advance` 的 TP | 该属性值 | — |
| `graph_other_sha` | Truth_Point / Branch / Trunk | 全部属性（去掉 `organic_advance`） | 三类之间全部关系（类型、两端 label+name、关系属性） |

## 缺陷说明（已修）

1. **缺陷一**：写后验证曾在 `execute_write` 提交之后才做；现改为显式事务内取改后快照并断言，失败 `rollback`、不提交。
2. **缺陷二（核实）**：旧 keep 集合只排除 6 贴后 + 3 合并目标；3 个改名目标应用后以新 ref 出现，节点与边进入 keep 集合导致 `scripture_keep_sha` / `supported_by_keep_sha` 对不上（`organic_keep_sha` 不受影响）。现 `AFFECTED_REFS` 含全部 12 个 ref。

## 同步 3a3b 副本（不连库）

```bash
python qa4/tools/graph_fixes/fix_graph_20261116.py --sync-sources \
  --src-fixed "<桌面改正后的 真理词典：3a和3b.json>" \
  --src-bak   "<同文件>.bak_20261116" \
  --dest qa4/data/graph_annotations/truth_dictionary_3a3b.json \
  --dest back_mic/backend/panai4/data/graph_annotations/truth_dictionary_3a3b.json
```

## 单测（不连库）

```bash
python -m unittest discover -s qa4/tools/graph_fixes -p 'test_*.py'
```
