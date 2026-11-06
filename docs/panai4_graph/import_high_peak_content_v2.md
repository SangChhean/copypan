# neo4j-v4 重新导入 `high_peak_content`（v2 报告）

生成时间：2026-11-06 22:43:38；脚本：`panai4.graph.import_high_peak_content_v2`。
设计沿用 `import_annotation_v2`：SET `n.high_peak_content` = json.dumps(series/stages/content_1…6)；六阶段全空闸门。
本报告不覆盖旧报告 `import_high_peak_content.md`。
未运行 build_v4.py；未打印密码；未修改已有 import_annotation*.py。

## 摘要

1. **源**：`C:\Users\28121\Desktop\可导入资料\特殊标注\【high_peak_content】从历史进展的差异看高峰时期的内涵.json` size=1383859；记录=87；重复=[]；全空=[]；仅1阶段=8 ['结晶意义', '基督的身位', '生命的认识', '高峰的真理', '主恢复的道路', '团体神人生活', '撒但的混乱', '末世论']。
2. **阶段分布**：{'content_1': 25, 'content_2': 40, 'content_3': 61, 'content_4': 61, 'content_5': 69, 'content_6': 65}。
3. **匹配**：found=87 missing=[] hit_inner=[] multi=[]；映射=[]。
4. **基线**：nodes=7334 rels=52197 Scripture=4851 SUPPORTED_BY=9768。
5. **import**：{'aborted': False, 'written': 87, 'failed': 0, 'expected': 87}。
6. **verify**：ok=True fails=[]。
7. **闸门**：check_ok=True fails=[]。

## check 明细
- keys=['content_1', 'content_2', 'content_3', 'content_4', 'content_5', 'content_6', 'name', 'series', 'stages'] extra=[]
- len_stats={'min': 1594, 'median': 4910, 'max': 23312, 'total_chars': 515850, 'over_32000': 0}
- write_count=87
- preexisting high_peak=0

## import
```json
{
  "aborted": false,
  "written": 87,
  "failed": 0,
  "expected": 87
}
```

## verify
- anno_n=87 inner_n=0
- nodes=7334 rels=52197
- Scripture=4851 SUPPORTED_BY=9768
- mismatch_n=0
- samples=[{"name": "经历并享受基督", "ok": true, "len": 4910, "head80": "{\"series\": \"从历史进展的差异看高峰时期的内涵\", \"stages\": {\"content_1\": \"倪柝声弟兄职事\", \"content_2\": \"…"}, {"name": "基督的工作", "ok": true, "len": 8307, "head80": "{\"series\": \"从历史进展的差异看高峰时期的内涵\", \"stages\": {\"content_1\": \"倪柝声弟兄职事\", \"content_2\": \"…"}, {"name": "三一神", "ok": true, "len": 13867, "head80": "{\"series\": \"从历史进展的差异看高峰时期的内涵\", \"stages\": {\"content_1\": \"倪柝声弟兄职事\", \"content_2\": \"…"}, {"name": "信徒", "ok": true, "len": 11074, "head80": "{\"series\": \"从历史进展的差异看高峰时期的内涵\", \"stages\": {\"content_1\": \"倪柝声弟兄职事\", \"content_2\": \"…"}, {"name": "基督的来临", "ok": true, "len": 5567, "head80": "{\"series\": \"从历史进展的差异看高峰时期的内涵\", \"stages\": {\"content_1\": \"倪柝声弟兄职事\", \"content_2\": \"…"}]
- prop_compare={"devine_argument": {"before_n": 187, "now_n": 187, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "intrinsic_significance": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "mutuality": {"before_n": 116, "now_n": 116, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "organic_advance": {"before_n": 69, "now_n": 69, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "name_en": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "greek_terms": {"before_n": 2257, "now_n": 2257, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "hebrew_terms": {"before_n": 1523, "now_n": 1523, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "definition_3a": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "definition_3b": {"before_n": 2062, "now_n": 2062, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}}
- fails=[]

## 最终验证
- 未修改 import_annotation.py / _v2.py / _v3.py / _v4.py 及其他已有脚本 / .gitignore
- 未运行 build_v4.py
- 报告与日志密码检查：通过（仅变量名）
- 未做括号内复制；未删文件；未覆盖旧报告
- 日志：`G:\copypan\logs\import_high_peak_content_v2_verify_20261106_224337.log`
