# neo4j-v4 导入通用标注报告

生成时间：2026-11-06 22:30:51；脚本：`panai4.graph.import_general_annotation`。
正文不进图谱；只 SET name_en / greek_terms / hebrew_terms / related_scriptures / definition_3a / definition_3b。
未运行 build_v4.py；未打印密码；未修改 import_annotation*.py。

## 摘要

1. **源文件**：gen=`C:\Users\28121\Desktop\可导入资料\节点一般标注.json` n=2372；dict=`C:\Users\28121\Desktop\可导入资料\真理词典：3a和3b.json` n=2372；集合一致=True。
2. **匹配**：found=2372 missing=0 hit_inner=[]；括号整体名映射例=[{"src": "产生男孩子（产生得胜者）", "graph": "产生男孩子"}, {"src": "晨晨复兴（晨兴）", "graph": "晨晨复兴"}…。
3. **一致性**：def.3a true=2372；def.3b true=2062；content_3b nonempty/empty=2062/310；mismatch=0；name_en=2372 greek=2257 hebrew=1523 scriptures=2372；max_3a=16323 max_3b=17032。
4. **copy**：{"src": "C:\\Users\\28121\\Desktop\\可导入资料\\真理词典：3a和3b.json", "dest": "G:\\copypan\\back_mic\\backend\\panai4\\data\\graph_annotations\\truth_dictionary_3a3b.json", "size": 31627640, "sha": "98721fd096…。
5. **gitignore**：{"paths": {"back_mic/backend/panai4/data/graph_annotations/organic_advance.json": {"before": ".gitignore:58:back_mic/backend/panai4/data/graph_annotations/*.json\t\"G:\\\\copypan\\\\back_mic\\\\backend\\\\panai4\\\\data\\\\graph_annotations\\\\organic_advance.json\"", "ignored": true, "after": ".git…。
6. **import**：{'aborted': False, 'written': 2372, 'failed': 0, 'expected': 2372}。
7. **verify**：ok=True counts={'name_en': 2372, 'greek_terms': 2257, 'hebrew_terms': 1523, 'related_scriptures': 2372, 'definition_3a': 2372, 'definition_3b': 2062} fails=[]。
8. **闸门**：check_ok=True fails=[]。

## A1 check 明细
- baseline nodes=2483 rels=6527 labels={'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380} by_type={'BELONGS_TO_TRUNK': 2380, 'GRAFTING': 91, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676}
- protected expected={'devine_argument': 187, 'intrinsic_significance': 2372, 'mutuality': 116, 'organic_advance': 69}
- composite_names=['产生男孩子（产生得胜者）', '晨晨复兴（晨兴）', '妇人（女人）', '挂虑（忧虑）', '火湖（地狱）', '扩大（显大）', '扩增（扩展）', '那灵的浇灌（圣灵的浇灌）']

## A2/A3 copy & gitignore
- dest=G:\copypan\back_mic\backend\panai4\data\graph_annotations\truth_dictionary_3a3b.json size=31627640 sha=98721fd096cbdb1e10080089d22fedba3a7973eb0f2c7b2f9bc14b66f3e7dac1 n=2372
- gitignore={"paths": {"back_mic/backend/panai4/data/graph_annotations/organic_advance.json": {"before": ".gitignore:58:back_mic/backend/panai4/data/graph_annotations/*.json\t\"G:\\\\copypan\\\\back_mic\\\\backend\\\\panai4\\\\data\\\\graph_annotations\\\\organic_advance.json\"", "ignored": true, "after": ".gitignore:58:back_mic/backend/panai4/data/graph_annotations/*.json\t\"G:\\\\copypan\\\\back_mic\\\\backend\\\\panai4\\\\data\\\\graph_annotations\\\\organic_advance.json\""}, "back_mic/backend/panai4/data/graph_annotations/truth_dictionary_3a3b.json": {"before": ".gitignore:58:back_mic/backend/panai4/data/graph_annotations/*.json\t\"G:\\\\copypan\\\\back_mic\\\\backend\\\\panai4\\\\data\\\\graph_annotations\\\\truth_dictionary_3a3b.json\"", "ignored": true, "after": ".gitignore:58:back_mic/backend/panai4/data/graph_annotations/*.json\t\"G:\\\\copypan\\\\back_mic\\\\backend\\\\panai4\\\\data\\\\graph_annotations\\\\truth_dictionary_3a3b.json\""}}, "added": []}

## A4 import
```json
{
  "aborted": false,
  "written": 2372,
  "failed": 0,
  "expected": 2372
}
```

## A5 verify
- counts={'name_en': 2372, 'greek_terms': 2257, 'hebrew_terms': 1523, 'related_scriptures': 2372, 'definition_3a': 2372, 'definition_3b': 2062}
- protected_compare={"devine_argument": {"before_n": 187, "now_n": 187, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "intrinsic_significance": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "mutuality": {"before_n": 116, "now_n": 116, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "organic_advance": {"before_n": 69, "now_n": 69, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}}
- samples=[{"name": "阿爸", "src_name": "阿爸", "scriptures_ok": true, "name_en": "Abba", "definition_3a": true, "definition_3b": true}, {"name": "阿拉法与俄梅嘎", "src_name": "阿拉法与俄梅嘎", "scriptures_ok": true, "name_en": "The Alpha And the Omega", "definition_3a": true, "definition_3b": true}, {"name": "阿利路亚", "src_name": "阿利路亚", "scriptures_ok": true, "name_en": "Hallelujah", "definition_3a": true, "definition_3b": true}, {"name": "阿摩司书", "src_name": "阿摩司书", "scriptures_ok": true, "name_en": "Amos", "definition_3a": true, "definition_3b": null}, {"name": "哀恸", "src_name": "哀恸", "scriptures_ok": true, "name_en": "Mourn", "definition_3a": true, "definition_3b": true}]
- dest_sha_ok=True nodes=2483 rels=6527
- tp_keys=[{'key': 'definition_3a', 'nodes_with_key': 2372, 'nonempty': 2372}, {'key': 'definition_3b', 'nodes_with_key': 2062, 'nonempty': 2062}, {'key': 'devine_argument', 'nodes_with_key': 187, 'nonempty': 187}, {'key': 'greek_terms', 'nodes_with_key': 2257, 'nonempty': 2257}, {'key': 'hebrew_terms', 'nodes_with_key': 1523, 'nonempty': 1523}, {'key': 'intrinsic_significance', 'nodes_with_key': 2372, 'nonempty': 2372}, {'key': 'mutuality', 'nodes_with_key': 116, 'nonempty': 116}, {'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'name_en', 'nodes_with_key': 2372, 'nonempty': 2372}, {'key': 'organic_advance', 'nodes_with_key': 69, 'nonempty': 69}, {'key': 'related_scriptures', 'nodes_with_key': 2372, 'nonempty': 2372}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}]
- fails=[]

## 最终验证
- 未修改 import_annotation.py / _v2.py / _v3.py / _v4.py / delete_old_relations.py
- 未运行 build_v4.py
- 报告与日志密码检查：通过（仅变量名）
- 日志：`G:\copypan\logs\import_general_annotation_verify_20261106_223048.log`
