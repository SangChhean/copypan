# 阶段4 提示词检查报告

通道：draft

## step2 @ v0.1
- 字符数：286；估算令牌：343.2（约1.2 token/字）
- 变量：history, question
- 固定块靠前：False；ok=True

## step3 @ v0.1
- 字符数：6961；估算令牌：8353.2
- 变量：question, rule_hits, life_book_titles, feast_list, scope_options
- 固定块靠前：True；ok=True
- 节期清单：月份码对照 + 年份范围；259 场假数据下 feast_list 估约 236 token
- 草稿通道：`# 本问线索` 前 → system cacheable；其后 → user
- JSON 示例含比较（compare_objects 两对象）

## step4 @ v0.1
- 字符数：923；估算令牌：1107.6
- 变量：question, subquestions
- 固定块靠前：False；ok=True
- 单/多子问题两种 JSON；step04 多子问题扁平 words 后分配

## step5 @ v0.1
- 字符数：979；估算令牌：1174.8
- 变量：question, subquestions, layer1, caps
- 固定块靠前：True；ok=True

## step7 @ v0.1
- 字符数：1244；估算令牌：1492.8
- 变量：subquestion, qtype, passages, passage_chars
- 固定块靠前：False；ok=True

## step8 @ v0.1
- 字符数：1390；估算令牌：1668.0
- 变量：question, qtype, understanding, verdict, definitions, layers, devine, passages
- 固定块靠前：True；ok=True
- 正文：Qa4Page 不渲染 Markdown；勿用标题/列表/加粗语法

## 开发题集
- 总数：64 条
- **用途**：只验证流程与格式，不评准确率；hold-out 由 Srey 另备
- 与草稿提示词去标点逐字重合：0（`tools/check_dev_overlap.py`）

## 关于 format_probe_results_20261117.md
- 上轮验收跑 `probe_scripture_formats` 时曾未带 `--no-notes`，脚本按设计覆写了 `qa4/notes/format_probe_results_20261117.md`（故未列入当时「改动清单」但文件时间戳变了）。
- 内容仅为计数、组别标签与工具路径说明；**无歌词原文**。本轮探针统一加 `--no-notes`，避免再改该文件。

## 已知限制
- 定向摘要复用 step8
- 第5步小结/关键经节 v0.1 不输出
- 召会生活拆分边界待真调用 → OQ-COMPLEX-BOUNDARY
