# neo4j-v4 导入标注 `devine_argument` 报告

生成时间：2026-11-06 17:56:55；脚本：`panai4.graph.import_annotation`。
源文件：`C:\Users\28121\Desktop\可导入资料\防火墙\【devine_argument】越进入高峰，真理越需要辨明得准确.json`。只 SET `n.devine_argument`；未运行 build_v4.py；未打印密码。

## 摘要

1. **基线 vs 预期**：相符；节点=2483 labels={'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380}；关系=6527 by_type={'BELONGS_TO_TRUNK': 2380, 'GRAFTING': 91, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676}；same_as=8/2372。
2. **JSON**：记录数=189；content_1/2/3 非空={'content_1': 189, 'content_2': 7, 'content_3': 2}；重复 name=无；其他键=无；含「城市」=False。
3. **匹配**：找到 189；找不到 0 → 无；多匹配=无。
4. **括号词条**：['产生男孩子/产生得胜者: 完全相同 → 丢弃括号内', '那灵的浇灌/圣灵的浇灌: 完全相同 → 丢弃括号内']；丢弃=['产生得胜者', '圣灵的浇灌']；需决定=0。
5. **写入**：写入=187；丢弃=2；失败=0。
6. **V1–V6**：ok=True；标注非空=187；括号内标注=0；无标注节点=2193（预期 2193）；内容不一致=0；name/same_as 不同=0；SHA ok=True；fails=无。
7. **长度分布**：{'min': 1334, 'median': 2221, 'max': 6449, 'total_chars': 442547, 'over_32000': 0}。
8. **待决**：无；stopped=None；check_ok=True。

## C. check
- 基线节点 2483 {'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380}；same_as 8/2372
- 关系 6527 {'BELONGS_TO_TRUNK': 2380, 'GRAFTING': 91, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676}
- Truth_Point 标注非空：[{'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}]
- SHA 可导入资料：n=8 bytes=45767983 check后一致=True

### 括号 8 对
- 产生男孩子 / 产生得胜者: outer_in=True inner_in=True 比较=完全相同 动作=丢弃括号内
- 晨晨复兴 / 晨兴: outer_in=False inner_in=False 比较=都不在 JSON 动作=无操作
- 妇人 / 女人: outer_in=False inner_in=False 比较=都不在 JSON 动作=无操作
- 挂虑 / 忧虑: outer_in=False inner_in=False 比较=都不在 JSON 动作=无操作
- 火湖 / 地狱: outer_in=False inner_in=False 比较=都不在 JSON 动作=无操作
- 扩大 / 显大: outer_in=False inner_in=False 比较=都不在 JSON 动作=无操作
- 扩增 / 扩展: outer_in=False inner_in=False 比较=都不在 JSON 动作=无操作
- 那灵的浇灌 / 圣灵的浇灌: outer_in=True inner_in=True 比较=完全相同 动作=丢弃括号内

### 拟写入 187；丢弃 ['产生得胜者', '圣灵的浇灌']；长度 {'min': 1334, 'median': 2221, 'max': 6449, 'total_chars': 442547, 'over_32000': 0}
- 闸门失败：无

## I. import
```json
{
  "aborted": false,
  "written": 187,
  "failed": 0,
  "expected": 187,
  "discarded": [
    "产生得胜者",
    "圣灵的浇灌"
  ]
}
```

## V. verify
- ok=True fails=无
- anno_count=187 inner={'c': 0, 'names': []} without=2193
- nodes/rels: 2483 {'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380} / 6527 {'BELONGS_TO_TRUNK': 2380, 'GRAFTING': 91, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676}
- node_keys: {'Truth_Point': [{'key': 'devine_argument', 'nodes_with_key': 187, 'nonempty': 187}, {'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}], 'Trunk': [{'key': 'name', 'nodes_with_key': 12, 'nonempty': 12}], 'Branch': [{'key': 'name', 'nodes_with_key': 91, 'nonempty': 91}]}
- 抽样：
  - {'name': '巴路西亚', 'present': True, 'length': 2198, 'head80': '{"content_1": [{"title": "基督的再来", "description": "公开一面，基督驾云降临时，全地都要看见祂", "outlin…'}
  - {'name': '被圣灵充满', 'present': True, 'length': 2166, 'head80': '{"content_1": [{"title": "圣灵里面的充满与外面的充溢", "description": "素质与经纶两面并重，同时注重里外两面", "…'}
  - {'name': '被圣灵充溢', 'present': True, 'length': 2166, 'head80': '{"content_1": [{"title": "圣灵里面的充满与外面的充溢", "description": "素质与经纶两面并重，同时注重里外两面", "…'}
  - {'name': '产生男孩子', 'present': True, 'length': 2549, 'head80': '{"content_1": [{"title": "信徒的被提", "description": "信徒不是全体一次被提，乃是多次被提", "outline":…'}
  - {'name': '那灵的浇灌', 'present': True, 'length': 2166, 'head80': '{"content_1": [{"title": "圣灵里面的充满与外面的充溢", "description": "素质与经纶两面并重，同时注重里外两面", "…'}
  - {'name': '得救', 'present': True, 'length': 6415, 'head80': '{"content_1": [{"title": "得救是神的拣选和预定，也需要人愿意", "description": "出于神的拣选和预定，也需人“信”",…'}
  - {'name': '地方召会', 'present': True, 'length': 4408, 'head80': '{"content_1": [{"title": "地方召会—“真正的信徒与基督身体里同作肢体者”", "description": "由所有的真信徒组成", …'}
  - {'name': '基督与宗教相对', 'present': True, 'length': 4363, 'head80': '{"content_1": [{"title": "基督与宗教相对", "description": "圣经里只有基督，没有‘教’", "outline": "…'}
  - {'name': '神格', 'present': True, 'length': 6449, 'head80': '{"content_1": [{"title": "神格的三个身位", "description": "不是三位神，乃是一位神有三面的讲究", "outline…'}

## 最终验证
- 只做了 SET 指定标注：是（若已 import）
- 未运行 build_v4.py：是
- 未读取并打印 .env 值：是
- 报告密码检查：通过；日志密码检查：通过
- git status（本任务仅应新增 import_annotation.py / 本报告 / logs；其余为既有改动）：
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
?? back_mic/backend/panai4/graph/import_annotation.py
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
?? docs/panai4_graph/import_devine_argument.md
?? docs/panai4_graph/neo4j_v4_inventory_pre.md

```

