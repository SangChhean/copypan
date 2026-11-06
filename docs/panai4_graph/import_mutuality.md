# neo4j-v4 导入标注 `mutuality` 报告（v3 / field-words）

生成时间：2026-11-06 21:43:27；脚本：`panai4.graph.import_annotation_v3`。
源文件：`C:\Users\28121\Desktop\可导入资料\特殊标注\【mutuality】彼此互相.json`。只 SET `n.mutuality` = `phrasing` 字符串；未运行 build_v4.py；未打印密码。

## 摘要

1. **基线**：节点=2483 {'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380}；关系=6527 {'BELONGS_TO_TRUNK': 2380, 'GRAFTING': 91, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676}；same_as=8/2372；TP keys=[{'key': 'devine_argument', 'nodes_with_key': 187, 'nonempty': 187}, {'key': 'intrinsic_significance', 'nodes_with_key': 2372, 'nonempty': 2372}, {'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}]；expect_anno={'devine_argument': 187, 'intrinsic_significance': 2372}。
2. **JSON**：words=116；顶层 count=116；相等=True；含斜杠=4 前10=[{'name': '爱里建造', 'value': '爱里建造/彼此建造'}, {'name': '彼此对说', 'value': '彼此对说/彼此相对说话'}, {'name': '身体的供应', 'value': '身体的供应/彼此供应'}, {'name': '肢体', 'value': '互相作肢体/彼此相顾'}]；phrasing 长度={'min': 3, 'median': 4, 'max': 13}；空值=[]；城市=False；额外键=无。
3. **匹配**：找到=116；找不到=[]；括号内=[]；多对一=无；别名=无。
4. **写入**：写入=116；失败=0。
5. **验证**：ok=True；非空=116；括号内=0；内容差=0；其他标注SHA={'devine_argument': {'before_n': 187, 'now_n': 187, 'sha_mismatch': 0, 'only_before': [], 'only_now': []}, 'intrinsic_significance': {'before_n': 2372, 'now_n': 2372, 'sha_mismatch': 0, 'only_before': [], 'only_now': []}}；fails=无。
6. **脚本**：新建 import_annotation_v3（复用 v1/v2）。差异：['新建 v3：--value-field 指定 words[] 字段作为标注字符串', '不写死 category；无四档计数闸门', '可选 --meta-doc 写出顶层 tag/definition/note/count', 'batch 默认 50；复用 v1 SET 与 v2 expect-anno SHA']。
7. **待决**：stopped=None；check_ok=True；fails=无。
- 说明文档：`G:\copypan\docs\panai4_graph\annotation_mutuality_definition.md`

## 明细
- SHA ok=True n=8
## I. import
```json
{
  "aborted": false,
  "written": 116,
  "failed": 0,
  "expected": 116
}
```
## V. verify
- samples: [{'name': '爱里建造', 'value': '爱里建造/彼此建造', 'length': 9}, {'name': '彼此对说', 'value': '彼此对说/彼此相对说话', 'length': 11}, {'name': '身体的供应', 'value': '身体的供应/彼此供应', 'length': 10}, {'name': '爱', 'value': '彼此相爱', 'length': 4}, {'name': '爱弟兄', 'value': '爱弟兄', 'length': 3}, {'name': '担负', 'value': '互相担负来传福音以实行新路', 'length': 13}]
- node_keys: {'Truth_Point': [{'key': 'devine_argument', 'nodes_with_key': 187, 'nonempty': 187}, {'key': 'intrinsic_significance', 'nodes_with_key': 2372, 'nonempty': 2372}, {'key': 'mutuality', 'nodes_with_key': 116, 'nonempty': 116}, {'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}], 'Trunk': [{'key': 'name', 'nodes_with_key': 12, 'nonempty': 12}], 'Branch': [{'key': 'name', 'nodes_with_key': 91, 'nonempty': 91}]}

## 最终验证
- 只做了 SET mutuality：是（若已 import）
- 未运行 build_v4.py：是
- 报告密码检查：通过；日志：通过
- 未修改 import_annotation.py / import_annotation_v2.py

