# neo4j-v4 导入标注 `organic_advance` 报告（v4 / flag-true）

生成时间：2026-11-06 22:11:14；脚本：`panai4.graph.import_annotation_v4`。
只 SET `n.organic_advance = true`（布尔）；内容留在仓库 JSON，不写入图谱；未运行 build_v4.py；未打印密码。

## 摘要

1. **文件复制**：dest=`G:\copypan\back_mic\backend\panai4\data\graph_annotations\organic_advance.json`；size=38800482；SHA=63a2320504c535e5b54d6ac8b33e0f76cafdfa5d330edfe9ccbbaa15abfb8178；与源一致=True；记录数=69。
2. **gitignore**：相关规则=['es_data/', 'back_mic/backend/data/panai4/', 'progress_pano.json', 'back_mic/backend/user/users.json', 'back_anshifenliang/data/private/', 'back_anshifenliang/data/zhi_shi_html/ ', 'back_mic/backend/data/enhanced_translate/pool.jsonl', 'back_mic/backend/data/enhanced_translate/pool.jsonl.bak', 'back_mic/backend/data/enhanced_translate/source_pool.jsonl']；check-ignore=(未被 ignore；exit=1)。
3. **基线**：节点=2483 {'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380}；关系=6527 {'BELONGS_TO_TRUNK': 2380, 'GRAFTING': 91, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676}；same_as=8/2372；TP keys=[{'key': 'devine_argument', 'nodes_with_key': 187, 'nonempty': 187}, {'key': 'intrinsic_significance', 'nodes_with_key': 2372, 'nonempty': 2372}, {'key': 'mutuality', 'nodes_with_key': 116, 'nonempty': 116}, {'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}]；expect_anno={'devine_argument': 187, 'intrinsic_significance': 2372, 'mutuality': 116}。
4. **匹配**：找到=69；找不到=[]；括号内=[]；多对一=无。
5. **写入**：写入=69；失败=0。
6. **验证**：ok=True；非空=69；全为 true=True；括号内=0；集合差 graph_only=[] file_only=[]；其他标注SHA={'devine_argument': {'before_n': 187, 'now_n': 187, 'sha_mismatch': 0, 'only_before': [], 'only_now': []}, 'intrinsic_significance': {'before_n': 2372, 'now_n': 2372, 'sha_mismatch': 0, 'only_before': [], 'only_now': []}, 'mutuality': {'before_n': 116, 'now_n': 116, 'sha_mismatch': 0, 'only_before': [], 'only_now': []}}；fails=无。
7. **脚本**：新建 import_annotation_v4（复用 v1/v2）。差异：['mode=flag-true：只 SET 布尔 true，不序列化内容', '另有 --stage copy 复制到 panai4/data/graph_annotations/', 'batch=50；复用 v1/v2']。
8. **待决**：stopped=None；check_ok=True；fails=无。

## copy / check / import / verify 明细
- copy: {"src": "C:\\Users\\28121\\Desktop\\可导入资料\\特殊标注\\【organic_advance】生机关联的进展.json", "dest": "G:\\copypan\\back_mic\\backend\\panai4\\data\\graph_annotations\\organic_advance.json", "size": 38800482, "sha": "63a2320504c535e5b54d6ac8b33e0f76cafdfa5d330edfe9ccbbaa15abfb8178", "sha_ok": true, "n_records": 69, "gitignore": {"root_rules_related": ["es_data/", "back_mic/backend/data/panai4/", "progress_pano.json", "back_mic/backend/user/users.json", "back_anshifenliang/data/private/", "back_anshifenliang/data/zhi_shi_html/ ", "back_mic/backend/data/enhanced_translate/pool.jsonl", "back_mic/backend/data/enhanced_translate/pool.jsonl.bak", "back_mic/backend/data/enhanced_translate/source_pool.jsonl"], "other_gitignore_files": [], "check_ignore": "(未被 ignore；exit=1)"}}
- plan: found=69 write=69 no_content=[]
## I. import
```json
{
  "aborted": false,
  "written": 69,
  "failed": 0,
  "expected": 69
}
```
## V. verify
- samples: [{'name': '召会生活', 'value': True, 'present': True}, {'name': '基督的身位', 'value': True, 'present': True}, {'name': '基督的工作', 'value': True, 'present': True}, {'name': '基督的神性', 'value': True, 'present': True}, {'name': '基督的人性', 'value': True, 'present': True}, {'name': '帐幕', 'value': True, 'present': True}, {'name': '圣殿', 'value': True, 'present': True}, {'name': '信', 'value': True, 'present': True}, {'name': '金灯台', 'value': True, 'present': True}]
- node_keys: {'Truth_Point': [{'key': 'devine_argument', 'nodes_with_key': 187, 'nonempty': 187}, {'key': 'intrinsic_significance', 'nodes_with_key': 2372, 'nonempty': 2372}, {'key': 'mutuality', 'nodes_with_key': 116, 'nonempty': 116}, {'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'organic_advance', 'nodes_with_key': 69, 'nonempty': 69}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}], 'Trunk': [{'key': 'name', 'nodes_with_key': 12, 'nonempty': 12}], 'Branch': [{'key': 'name', 'nodes_with_key': 91, 'nonempty': 91}]}
- dest_sha_ok: True

## 最终验证
- 对图谱只做了 SET organic_advance=true：是（若已 import）
- 未运行 build_v4.py：是
- 报告密码检查：通过；日志：通过
- 未修改 import_annotation.py / _v2.py / _v3.py / .gitignore

