# PanAI 4.0 图谱脚本

`build_v4.py` 只写 `NEO4J_V4_URI`。它和 3.5 的 `NEO4J_URI` 相同时会直接停下来。密码从环境变量读取，不写进报告。

节点上的 property 在这里称为标注。

## 依据的资料

| 资料 | 用途 |
|---|---|
| `docs/panai4_graph/2372个词条（已确定一一对应为concept节点）.txt` | 词条原名。8 个带括号的词条拆成括号外、括号内两个真理要点 |
| `docs/panai4_graph/主恢复真理词典_词条主干枝子映射 (1).json` | 每个词条的 trunk、branch_directly、branch_indirectly。带括号词条的归属同时给拆开的两个节点 |
| `docs/panai4_graph/12大类与91小类的对应关系.txt` | 12 个主干、91 个枝子，以及枝子接在哪个主干上 |
| `docs/panai4_graph/concept_mapping_35_to_40.csv` | 3.5 Concept 旧名到新名。处理方式为「删除」的端点，其旧关系不迁 |

3.5 图谱只读。从那里补建的只有 Concept→Concept 的六种旧关系：`CONTAINS`、`EXPERIENCES`、`LEADS_TO`、`LOCATED_IN`、`OPPOSES`、`PRACTICED_AS`。不迁 Scripture、`SUPPORTED_BY`、`greek_terms`。

## 参数

在 `back_mic/backend` 下执行，或直接用仓库里的脚本路径。

```text
python panai4/graph/build_v4.py
python panai4/graph/build_v4.py --apply
python panai4/graph/build_v4.py --dry-run
python panai4/graph/build_v4.py --cleanup
python panai4/graph/build_v4.py --cleanup --confirm
```

不带参数和 `--apply` 相同。

| 参数 | 做什么 |
|---|---|
| （无）或 `--apply` | 只 MERGE。缺少的节点和关系会补上。`same_as` 只在资料里有值时 `SET n.same_as = ...`。不删除节点、关系或标注 |
| `--dry-run` | 只按资料和 3.5 计算数量，写 `docs/panai4_graph/reports/build_v4_report_dry_run.md`，不连接 v4 写入 |
| `--cleanup` | 只列出与资料不符的候选，写入 `docs/panai4_graph/reports/cleanup_candidates.md`，不删除 |
| `--cleanup --confirm` | 只删除上一份清单代码块里的那些项，不重新扫描。删除前后的节点数、关系数记在同一份报告末尾 |

`--confirm` 不能单独使用。`--cleanup` 不能和 `--dry-run` / `--apply` 一起用。

本脚本负责的标注只有 `name` 和 `same_as`。更新时只 SET 这一个键，不会用整组赋值盖掉以后别的批次写入的英文名、定义等。

## 分批上传

词条与一般标注、边、专特标注会分批进入。每批之后重跑一次默认命令（或 `--apply`）：

1. 先把这一批的新资料放进上表对应的文件。真理要点的名字和分类仍以那三份词表为准；旧关系仍以 CSV 和 3.5 为准。
2. 跑 `python panai4/graph/build_v4.py --apply`。已有节点会按 `name` 合并，已有关系会按两端和类型合并，数量不应无故减少。
3. 看 `docs/panai4_graph/reports/build_v4_report.md`。写入前后的 v4 节点数、关系数应与这一批实际新增的一致。

专特标注和其他关系类型由后续批次自己的脚本写入。本脚本重跑时不会清掉它们。

## 清理

清理只针对本脚本负责的范围：

- 节点：`Truth_Point`、`Trunk`、`Branch` 中名字不在资料名单里的
- 关系：`GRAFTING`、`BELONGS_TO_TRUNK`、`OF_BRANCH_DIRECTLY`、`OF_BRANCH_INDIRECTLY` 中与资料不符的
- 标注：`same_as` 的值与资料不符的（确认时只去掉这个键）

不清理、也不删除：上面六种迁移来的旧关系，以及以后新增的任何关系类型、标注、节点标签。

删除节点时不用 `DETACH DELETE`。节点上若还连着不在清理范围内的关系，这一次会跳过该节点并写进报告，那些关系保留。

顺序必须是：先 `--cleanup` 看清单，确认清单里只有要删的项，再 `--cleanup --confirm`。确认步骤按文件里的清单删除；清单生成之后库若又有变化，它不会把新出现的东西一并删掉。
