# neo4j-v4 删除旧 6 种关系报告

生成时间：2026-11-06 17:35:33；脚本：`panai4.graph.delete_old_relations`。
只删除 LEADS_TO / EXPERIENCES / PRACTICED_AS / CONTAINS / OPPOSES / LOCATED_IN（两端 Truth_Point）；未运行 build_v4.py；未打印密码。

## 摘要

1. **基线 vs 预期**：一致；不一致项：无。
   实测节点=2483（TP=2380 Trunk=12 Branch=91）；关系=45700；分类=6527；旧6=39173；by_type={'BELONGS_TO_TRUNK': 2380, 'CONTAINS': 5977, 'EXPERIENCES': 7725, 'GRAFTING': 91, 'LEADS_TO': 14140, 'LOCATED_IN': 528, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676, 'OPPOSES': 3372, 'PRACTICED_AS': 7431}。
2. **删除条数**：{'LEADS_TO': 14140, 'EXPERIENCES': 7725, 'PRACTICED_AS': 7431, 'CONTAINS': 5977, 'OPPOSES': 3372, 'LOCATED_IN': 528}；合计 **39173**（预期 39173）。
3. **删除后关系**：总数=6527；类型={'BELONGS_TO_TRUNK': 2380, 'GRAFTING': 91, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676}；db.relationshipTypes 仍列旧名=无（以 MATCH count 为准）。
4. **分类关系不变**：与基线比较失败项中分类相关见 verify.fails；当前 {'BELONGS_TO_TRUNK': 2380, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676, 'GRAFTING': 91} vs 基线 {'BELONGS_TO_TRUNK': 2380, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676, 'GRAFTING': 91}。
5. **节点/标注/约束/索引**：节点 2483 labels={'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380}；same_as=[{'inner': '产生得胜者', 'outer': '产生男孩子', 'outer_exists': True}, {'inner': '圣灵的浇灌', 'outer': '那灵的浇灌', 'outer_exists': True}, {'inner': '地狱', 'outer': '火湖', 'outer_exists': True}, {'inner': '女人', 'outer': '妇人', 'outer_exists': True}, {'inner': '忧虑', 'outer': '挂虑', 'outer_exists': True}, {'inner': '扩展', 'outer': '扩增', 'outer_exists': True}, {'inner': '显大', 'outer': '扩大', 'outer_exists': True}, {'inner': '晨兴', 'outer': '晨晨复兴', 'outer_exists': True}]；verify.ok=True；失败=无。
6. **孤立 Truth_Point**：0（预期 0）。
7. **闸门/待决**：stopped=None；check_ok=True；verify_ok=True。

## C. check 基线
- docker：`neo4j-v4	Up 9 hours	neo4j:5.26.28	0.0.0.0:7475->7474/tcp, [::]:7475->7474/tcp, 0.0.0.0:7688->7687/tcp, [::]:7688->7687/tcp`
- 组件：`[{"name": "Neo4j Kernel", "versions": ["5.26.28"], "edition": "community"}]`
- 节点标签：{'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380}；合计 2483；same_as 有/无 = 8/2372
| 预期项 | 预期 | 实测 | 一致 |
|---|---:|---:|---|
| nodes_total | 2483 | 2483 | True |
| Truth_Point | 2380 | 2380 | True |
| Trunk | 12 | 12 | True |
| Branch | 91 | 91 | True |
| rels_total | 45700 | 45700 | True |
| class_total | 6527 | 6527 | True |
| old6_total | 39173 | 39173 | True |
| BELONGS_TO_TRUNK | 2380 | 2380 | True |
| OF_BRANCH_DIRECTLY | 2380 | 2380 | True |
| OF_BRANCH_INDIRECTLY | 1676 | 1676 | True |
| GRAFTING | 91 | 91 | True |
| LEADS_TO | 14140 | 14140 | True |
| EXPERIENCES | 7725 | 7725 | True |
| PRACTICED_AS | 7431 | 7431 | True |
| CONTAINS | 5977 | 5977 | True |
| OPPOSES | 3372 | 3372 | True |
| LOCATED_IN | 528 | 528 | True |

### 起止标签
- BELONGS_TO_TRUNK: Truth_Point→Trunk ×2380
- CONTAINS: Truth_Point→Truth_Point ×5977
- EXPERIENCES: Truth_Point→Truth_Point ×7725
- GRAFTING: Branch→Trunk ×91
- LEADS_TO: Truth_Point→Truth_Point ×14140
- LOCATED_IN: Truth_Point→Truth_Point ×528
- OF_BRANCH_DIRECTLY: Truth_Point→Branch ×2380
- OF_BRANCH_INDIRECTLY: Truth_Point→Branch ×1676
- OPPOSES: Truth_Point→Truth_Point ×3372
- PRACTICED_AS: Truth_Point→Truth_Point ×7431

### 旧6两端皆 Truth_Point
- LEADS_TO: both_tp=14140 total=14140 equal=True
- EXPERIENCES: both_tp=7725 total=7725 equal=True
- PRACTICED_AS: both_tp=7431 total=7431 equal=True
- CONTAINS: both_tp=5977 total=5977 equal=True
- OPPOSES: both_tp=3372 total=3372 equal=True
- LOCATED_IN: both_tp=528 total=528 equal=True

### 节点标注
- Truth_Point name_stats={'total': 2380, 'name_nonempty': 2380, 'name_distinct': 2380} keys=[{'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}]
- Trunk name_stats={'total': 12, 'name_nonempty': 12, 'name_distinct': 12} keys=[{'key': 'name', 'nodes_with_key': 12, 'nonempty': 12}]
- Branch name_stats={'total': 91, 'name_nonempty': 91, 'name_distinct': 91} keys=[{'key': 'name', 'nodes_with_key': 91, 'nonempty': 91}]

### same_as 8 对
- 产生得胜者 → 产生男孩子 (exists=True)
- 圣灵的浇灌 → 那灵的浇灌 (exists=True)
- 地狱 → 火湖 (exists=True)
- 女人 → 妇人 (exists=True)
- 忧虑 → 挂虑 (exists=True)
- 扩展 → 扩增 (exists=True)
- 显大 → 扩大 (exists=True)
- 晨兴 → 晨晨复兴 (exists=True)

### 约束 / 索引（简表）
```json
[
  {
    "name": "branch_name",
    "type": "UNIQUENESS",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Branch"
    ],
    "properties": [
      "name"
    ]
  },
  {
    "name": "trunk_name",
    "type": "UNIQUENESS",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Trunk"
    ],
    "properties": [
      "name"
    ]
  },
  {
    "name": "truth_point_name",
    "type": "UNIQUENESS",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Truth_Point"
    ],
    "properties": [
      "name"
    ]
  }
]
```
```json
[
  {
    "name": "branch_name",
    "type": "RANGE",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Branch"
    ],
    "properties": [
      "name"
    ],
    "state": "ONLINE"
  },
  {
    "name": "index_343aff4e",
    "type": "LOOKUP",
    "entityType": "NODE",
    "labelsOrTypes": null,
    "properties": null,
    "state": "ONLINE"
  },
  {
    "name": "index_f7700477",
    "type": "LOOKUP",
    "entityType": "RELATIONSHIP",
    "labelsOrTypes": null,
    "properties": null,
    "state": "ONLINE"
  },
  {
    "name": "trunk_name",
    "type": "RANGE",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Trunk"
    ],
    "properties": [
      "name"
    ],
    "state": "ONLINE"
  },
  {
    "name": "truth_point_name",
    "type": "RANGE",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Truth_Point"
    ],
    "properties": [
      "name"
    ],
    "state": "ONLINE"
  }
]
```
- 删除预演：将删旧6=39173；剩余=6527；删除后无分类关系的 TP=0 样本=[]
- 闸门失败：无

## D. delete
```json
{
  "aborted": false,
  "deleted": {
    "LEADS_TO": 14140,
    "EXPERIENCES": 7725,
    "PRACTICED_AS": 7431,
    "CONTAINS": 5977,
    "OPPOSES": 3372,
    "LOCATED_IN": 528
  },
  "batches": {
    "LEADS_TO": [
      5000,
      5000,
      4140
    ],
    "EXPERIENCES": [
      5000,
      2725
    ],
    "PRACTICED_AS": [
      5000,
      2431
    ],
    "CONTAINS": [
      5000,
      977
    ],
    "OPPOSES": [
      3372
    ],
    "LOCATED_IN": [
      528
    ]
  },
  "total": 39173,
  "expected_total": 39173
}
```

## V. verify
- ok=True fails=无
- rels=6527 by_type={'BELONGS_TO_TRUNK': 2380, 'GRAFTING': 91, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676}
- db.relationshipTypes=['GRAFTING', 'BELONGS_TO_TRUNK', 'OF_BRANCH_DIRECTLY', 'OF_BRANCH_INDIRECTLY']；仍列旧6=[]
- belong={'exactly_one': 2380, 'bad': 0, 'points': 2380} direct={'exactly_one': 2380, 'bad': 0, 'points': 2380}
- paren=[{'outer': '产生男孩子', 'inner': '产生得胜者', 'trunk_eq': True, 'direct_eq': True, 'indirect_eq': True}, {'outer': '晨晨复兴', 'inner': '晨兴', 'trunk_eq': True, 'direct_eq': True, 'indirect_eq': True}, {'outer': '妇人', 'inner': '女人', 'trunk_eq': True, 'direct_eq': True, 'indirect_eq': True}, {'outer': '挂虑', 'inner': '忧虑', 'trunk_eq': True, 'direct_eq': True, 'indirect_eq': True}, {'outer': '火湖', 'inner': '地狱', 'trunk_eq': True, 'direct_eq': True, 'indirect_eq': True}, {'outer': '扩大', 'inner': '显大', 'trunk_eq': True, 'direct_eq': True, 'indirect_eq': True}, {'outer': '扩增', 'inner': '扩展', 'trunk_eq': True, 'direct_eq': True, 'indirect_eq': True}, {'outer': '那灵的浇灌', 'inner': '圣灵的浇灌', 'trunk_eq': True, 'direct_eq': True, 'indirect_eq': True}]
- nodes=2483 labels={'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380} isolated=0
- same_as=[{'inner': '产生得胜者', 'outer': '产生男孩子', 'outer_exists': True}, {'inner': '圣灵的浇灌', 'outer': '那灵的浇灌', 'outer_exists': True}, {'inner': '地狱', 'outer': '火湖', 'outer_exists': True}, {'inner': '女人', 'outer': '妇人', 'outer_exists': True}, {'inner': '忧虑', 'outer': '挂虑', 'outer_exists': True}, {'inner': '扩展', 'outer': '扩增', 'outer_exists': True}, {'inner': '显大', 'outer': '扩大', 'outer_exists': True}, {'inner': '晨兴', 'outer': '晨晨复兴', 'outer_exists': True}]
- volume: ['neo4j_v4_data                                                      1         543.7MB']

## 最终验证
- 只执行按类型删除旧6种：是（若已 delete）
- 未运行 build_v4.py：是
- 未读取并打印 .env 值：是
- 报告密码检查：通过；日志密码检查：通过
- git status（本任务仅应新增 delete_old_relations.py / 本报告 / logs；其余为既有改动）：
```
 M back_mic/backend/panai4/outline/config.py
 M docs/3a_export.json
 M "docs/panai4_graph/2372\344\270\252\350\257\215\346\235\241\357\274\210\345\267\262\347\241\256\345\256\232\344\270\200\344\270\200\345\257\271\345\272\224\344\270\272concept\350\212\202\347\202\271\357\274\211.txt"
 M "docs/panai4_graph/2373\344\270\252\350\257\215\346\235\241\357\274\210\345\267\262\347\241\256\345\256\232\344\270\200\344\270\200\345\257\271\345\272\224\344\270\272concept\350\212\202\347\202\271\357\274\211.txt"
 M "docs/panai4_graph/\344\270\273\346\201\242\345\244\215\347\234\237\347\220\206\350\257\215\345\205\270_\346\240\207\347\255\276\346\230\240\345\260\204_\345\267\262\346\240\241\345\257\271 (1).json"
 M "docs/panai4_graph/\344\270\273\346\201\242\345\244\215\347\234\237\347\220\206\350\257\215\345\205\270_\350\257\215\346\235\241\344\270\273\345\271\262\346\236\235\345\255\220\346\230\240\345\260\204 (1).json"
 M "docs/panai4_graph/\350\257\215\346\235\241\344\270\211\346\241\243\345\210\206\347\261\273.json"
 M docs/panai4_sc/null_terms.csv
?? back_mic/backend/panai4/graph/delete_old_relations.py
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
?? docs/panai4_es/archive/12490_assets_check.md
?? docs/panai4_es/archive/_git_diff_stat.txt
?? docs/panai4_es/archive/_git_status_raw.txt
?? docs/panai4_es/archive/_git_untracked.txt
?? docs/panai4_es/archive/_task5_scan.py
?? docs/panai4_es/archive/index_tasks_summary.md
?? docs/panai4_es/archive/life_12490_fix_final.csv
?? docs/panai4_es/archive/life_12490_fix_final_v4.csv
?? docs/panai4_es/archive/life_12490_fix_list.csv
?? docs/panai4_es/archive/life_12490_fix_list.md
?? docs/panai4_es/archive/life_12490_fix_list_v2.csv
?? docs/panai4_es/archive/life_12490_fix_list_v2.md
?? docs/panai4_es/archive/life_12490_fix_list_v3.csv
?? docs/panai4_es/archive/life_12490_fix_list_v3.md
?? docs/panai4_es/archive/life_12490_fix_review.csv
?? docs/panai4_es/archive/life_fix_stage01.md
?? docs/panai4_es/archive/life_fix_stage2_assemble.md
?? docs/panai4_es/archive/life_fix_stage2_embed.md
?? docs/panai4_es/archive/life_fix_stage2_prepare.md
?? docs/panai4_es/archive/life_fix_stage2_reconcile.md
?? docs/panai4_es/archive/life_fix_stage2_rollback_local.md
?? docs/panai4_es/archive/life_fix_stage2_summary.md
?? docs/panai4_es/archive/life_fix_stage2_verify_vec.md
?? docs/panai4_es/archive/life_fix_stage2_write_local.md
?? docs/panai4_es/archive/life_fix_stage3_precheck.md
?? docs/panai4_es/archive/life_fix_stage3_remote_backup.md
?? docs/panai4_es/archive/life_fix_stage3_remote_check.md
?? docs/panai4_es/archive/life_fix_stage3_remote_reconcile.md
?? docs/panai4_es/archive/life_fix_stage3_remote_write.md
?? docs/panai4_es/archive/life_fix_stage3_summary.md
?? docs/panai4_es/archive/life_in_12490_check.md
?? docs/panai4_es/archive/life_in_12490_check2.md
?? docs/panai4_es/archive/life_outline_pairing.csv
?? docs/panai4_es/archive/life_outline_probe.md
?? docs/panai4_es/archive/life_outline_probe2.md
?? docs/panai4_es/archive/life_text_life_diff.csv
?? docs/panai4_es/archive/task2_book_overrides.md
?? docs/panai4_es/archive/task4_index_organize.md
?? docs/panai4_es/archive/task5_git_commands.ps1
?? docs/panai4_es/archive/task5_git_plan.md
?? docs/panai4_es/archive/text_life_fix_FAIL_T3.md
?? docs/panai4_es/archive/text_life_fix_FAIL_T4.md
?? docs/panai4_es/archive/text_life_fix_list.csv
?? docs/panai4_es/archive/text_life_fix_local.md
?? docs/panai4_es/archive/text_life_fix_precheck.md
?? docs/panai4_es/archive/text_life_fix_review.csv
?? docs/panai4_es/archive/text_life_fix_server.md
?? docs/panai4_es/archive/text_life_fix_t1.md
?? docs/panai4_es/archive/text_life_fix_t2.md
?? docs/panai4_graph/delete_old_relations.md
?? docs/panai4_graph/neo4j_v4_inventory_pre.md

```

