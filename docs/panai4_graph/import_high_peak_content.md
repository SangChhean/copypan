# neo4j-v4 导入标注 `high_peak_content` 报告（v2）

生成时间：2026-11-06 21:16:08；脚本：`panai4.graph.import_annotation_v2`。
源文件：`C:\Users\28121\Desktop\可导入资料\特殊标注\【high_peak_content】从历史进展的差异看高峰时期的内涵.json`。只 SET `n.high_peak_content`；未运行 build_v4.py；未打印密码。

## 摘要

1. **基线**：节点=2483 labels={'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380}；关系=6527 by_type={'BELONGS_TO_TRUNK': 2380, 'GRAFTING': 91, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676}；same_as=8/2372；已有标注预期={'devine_argument': 187}；TP keys=[{'key': 'devine_argument', 'nodes_with_key': 187, 'nonempty': 187}, {'key': 'name', 'nodes_with_key': 2380, 'nonempty': 2380}, {'key': 'same_as', 'nodes_with_key': 8, 'nonempty': 8}]。
2. **JSON**：记录=87；键集合=['content_1', 'content_2', 'content_3', 'content_4', 'content_5', 'content_6', 'name', 'series', 'stages']；额外键=无；series 种类=1 values=[{'value': '从历史进展的差异看高峰时期的内涵', 'count': 87}]；stages 种类=1；content 非空={'content_1': 23, 'content_2': 37, 'content_3': 57, 'content_4': 59, 'content_5': 66, 'content_6': 61}；城市=False。
3. **匹配**：找到 87；找不到 0 → 无。
4. **括号**：未出现；丢弃内=[]。
5. **写入**：尚未 import；拟写入=80；丢弃括号内=[]；六阶段全空（未写入、等决定）=['内在的素质', '神中心的工作', '圣经中的奥秘', '读经之路', '事奉主', '团体神人生活', '末世论']。
6. **验证**：尚未 verify。
7. **长度**：{'min': 1594, 'median': 5408, 'max': 23312, 'total_chars': 494261, 'over_32000': 0}。
8. **脚本**：使用 import_annotation_v2（复用 v1 函数）。差异：['基线可声明已有标注非空数（--expect-anno）并快照 SHA256', '检测 content_1…6 全空并闸门停止（不写入这些 name）', 'verify 校验其他标注 SHA256 不变；抽样名可配置', '报告增加 series/stages 取值与全空名单']。
9. **待决**：六阶段全空=['内在的素质', '神中心的工作', '圣经中的奥秘', '读经之路', '事奉主', '团体神人生活', '末世论']；括号需决定=无；stopped=check；check_ok=False；fails=["六个阶段全空 7 条: ['内在的素质', '神中心的工作', '圣经中的奥秘', '读经之路', '事奉主', '团体神人生活', '末世论']"]。

## C. check 明细
- 基线节点/关系如上；SHA n=8 bytes=45767983 ok=True
- 全空名单：['内在的素质', '神中心的工作', '圣经中的奥秘', '读经之路', '事奉主', '团体神人生活', '末世论']
- 拟写入 80；丢弃括号内 []
- 闸门：["六个阶段全空 7 条: ['内在的素质', '神中心的工作', '圣经中的奥秘', '读经之路', '事奉主', '团体神人生活', '末世论']"]

## I. import
未执行。

## V. verify
未执行。

## 最终验证
- 只做了 SET 指定标注：是（若已 import）
- 未运行 build_v4.py：是
- 报告密码检查：通过；日志：通过
- 未修改 import_annotation.py；本轮使用 import_annotation_v2.py

