# neo4j-v4 导入标注 `intrinsic_significance` 报告（v2 / category-words）

生成时间：2026-11-06 21:29:03；脚本：`panai4.graph.import_annotation_v2 --mode category-words`。
源文件：`C:\Users\28121\Desktop\可导入资料\特殊标注\【intrinsic_significance】2372词条内在意义分类.json`。只 SET `n.intrinsic_significance` = 档次字符串；未运行 build_v4.py；未打印密码。

## 摘要

1. **基线**：节点=2483 {'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380}；关系=6527 {'BELONGS_TO_TRUNK': 2380, 'GRAFTING': 91, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676}；same_as=8/2372；TP keys=[{'key': 'devine_argument', 'nodes_with_key': 187, 'nonempty': 187}, {'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}]；expect_anno={'devine_argument': 187}。
2. **JSON**：words=2372；category 计数={'内在': 497, '外在': 1658, '显出为外在': 84, '最内在': 133}；categories 简表=[{'name': '外在', 'count': 1658, 'ratio': '69.9%', 'definition_len': 103}, {'name': '内在', 'count': 497, 'ratio': '21.0%', 'definition_len': 95}, {'name': '最内在', 'count': 133, 'ratio': '5.6%', 'definition_len': 121}, {'name': '显出为外在', 'count': 84, 'ratio': '3.5%', 'definition_len': 119}]；额外键=无；城市=False。
3. **匹配**：直接=2363；合并名=8；别名=1；找不到=0；映射到括号内=0；多对一=0。
4. **合并名明细**：[{'src': '产生男孩子（产生得胜者）', 'target': '产生男孩子', 'category': '内在'}, {'src': '晨晨复兴（晨兴）', 'target': '晨晨复兴', 'category': '显出为外在'}, {'src': '妇人（女人）', 'target': '妇人', 'category': '外在'}, {'src': '挂虑（忧虑）', 'target': '挂虑', 'category': '外在'}, {'src': '火湖（地狱）', 'target': '火湖', 'category': '外在'}, {'src': '扩大（显大）', 'target': '扩大', 'category': '显出为外在'}, {'src': '扩增（扩展）', 'target': '扩增', 'category': '显出为外在'}, {'src': '那灵的浇灌（圣灵的浇灌）', 'target': '那灵的浇灌', 'category': '内在'}]；**别名**：[{'src': '路得马丁', 'target': '路德马丁', 'category': '外在'}]。
5. **写入**：写入=2372；失败=0。
6. **验证**：ok=True；非空=2372；括号内=0；档次={'内在': 497, '外在': 1658, '显出为外在': 84, '最内在': 133}；内容差=0；其他标注SHA={'devine_argument': {'before_n': 187, 'now_n': 187, 'sha_mismatch': 0, 'only_before': [], 'only_now': []}}；fails=无。
7. **脚本**：import_annotation_v2 --mode category-words（复用 v1）。差异：['mode=category-words：标注值=category 字符串（非整条 JSON）', '合并名 X（Y）→ 括号外 X；别名表（默认 路得马丁→路德马丁）', '只写无 same_as 的 Truth_Point；括号内不写', '另写档次定义 md；batch=200']。
8. **待决**：missing=无；hit_inner=无；only_graph=无；only_json=无；stopped=None；check_ok=True；fails=无。
- 档次定义文档：`G:\copypan\docs\panai4_graph\annotation_intrinsic_significance_definitions.md`

## C / I / V 明细
- SHA ok=True n=8
- 对账 only_graph=[] only_json=[]
## I. import
```json
{
  "aborted": false,
  "written": 2372,
  "failed": 0,
  "expected": 2372
}
```
## V. verify
- samples: [{'name': '晨晨复兴', 'value': '显出为外在'}, {'name': '产生男孩子', 'value': '内在'}, {'name': '妇人', 'value': '外在'}, {'name': '挂虑', 'value': '外在'}, {'name': '火湖', 'value': '外在'}, {'name': '扩大', 'value': '显出为外在'}, {'name': '扩增', 'value': '显出为外在'}, {'name': '那灵的浇灌', 'value': '内在'}, {'name': '路德马丁', 'value': '外在'}, {'name': '神', 'value': '最内在'}, {'name': '基督', 'value': '最内在'}, {'name': '一', 'value': '最内在'}, {'name': '一灵', 'value': '最内在'}, {'name': '一个新人', 'value': '内在'}, {'name': '一个身体', 'value': '内在'}, {'name': '一个职事', 'value': '外在'}, {'name': '一切', 'value': '外在'}, {'name': '不爱世界', 'value': '显出为外在'}, {'name': '义', 'value': '显出为外在'}]
- city_nodes: []
- node_keys: {'Truth_Point': [{'key': 'devine_argument', 'nodes_with_key': 187, 'nonempty': 187}, {'key': 'intrinsic_significance', 'nodes_with_key': 2372, 'nonempty': 2372}, {'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}], 'Trunk': [{'key': 'name', 'nodes_with_key': 12, 'nonempty': 12}], 'Branch': [{'key': 'name', 'nodes_with_key': 91, 'nonempty': 91}]}

## 最终验证
- 只做了 SET intrinsic_significance：是（若已 import）
- 未运行 build_v4.py：是
- 报告密码检查：通过；日志：通过
- 未修改 import_annotation.py

