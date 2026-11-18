# scripture normalize v2 补强说明（2026-11-17）

不改 `vendor_get_vers_v21.py`。补强在 `scripture/normalize.py` + `scripture/ref_enhance.py` + `scripture/data/*.json`。

## 规则摘要

| 规则 | 做什么 | 数据/代码位置 |
|------|--------|----------------|
| A 繁→简 | 解析前本地对照表替换（venv 无 OpenCC，requirements 亦无） | `scripture/data/t2s_chars.json`；`traditional_to_simplified` |
| B 空白/书名号 | 去《》『』「」；CJK↔CJK/数字空白；冒号两侧空白 | `ref_enhance._strip_marks_and_spaces` |
| C 别名 | 最长匹配；人名同形仅后接章节数字且非「书/福音/一书…」续写 | `scripture/data/book_aliases.json` |
| D 阿拉伯章篇节 | `N章/篇`、`N章M节`、`N章M-N节` → vendor 可认形 | `_rewrite_arabic_chapter_units` |
| E 范围/跨章 | `至/到/-/～`；`创1:1-2:3`→中文跨章形；短写跨章插入章/节 | `_rewrite_cross_*` / `_rewrite_same_ch_zhi` |
| F 整章+节合并 | 同 raw 内或相邻组：有同章经节则丢整章 | `merge_chapter_with_verse`（vendor group 有 start/end，合并仍按 Ref 序列启发式） |
| G 廿/卅/口语百 | 廿→二十、卅→三十；`一百二`→`一百二十` | `_fix_nian_sa` / `_fix_colloquial_hundreds` |
| H 整卷/章范围 | 新 kind：`whole_book`、`chapter_range`；人名裸名不整卷 | `match_whole_book` / `match_chapter_range`；`bare_chapter_forms` 仅 parse 回退 |
| I 英文 | 66 卷全称/常见缩写；大小写不敏感；en dash；整卷例外 | `scripture/data/en_books.json` |
| J 越界章 | 依赖 bible 校验：`太卅五1`→无出处；节越界同样被 validator 滤掉 | `build_validator` + bible_data |

## 排除的英文缩写

见 `en_books.json` → `excluded_abbreviations`：Am, So, No, He, Me, Is, At, Be, By, Do, If, In, It, My, Of, On, Or, To, Up, Us, We, As, An（避免 `I am 3…` 等误认）。Amos/Nahum/Song 用全称或其它安全缩写。

## 取篇层（targeted.scripture）

- **能处理**：既有 `verse_range` / `whole_chapter` / `cross_chapter`。
- **不能直接处理**：`whole_book`、`chapter_range`。`targeted.py` 的 `else` 会当节范围去 `get_range`，缺专门分支。
- **缺什么**：按卷取全书、按章范围逐章取文的 API/分支；pipeline 若把这两类 Ref 送入取篇需先展开或改 status=NOT_SUPPORTED。本任务未改取篇层。

## 已知局限

1. **S117 / S278**：期望 `诗篇 120:14`，但 `bible_data` 诗 120 仅 1–7 节；validate 后为「无出处」。口语改写 `一百二`→`一百二十` 已生效（见 preprocess）。最小方案：补数据，或产品接受「章存在、节越界仍出 Ref」。
2. **F 合并**：无 token 级偏移时靠 raw/相邻启发式；复杂夹杂句可能过度合并（3a 中有 3 处整章+节双计改为单计）。
3. **3a 读经行汇总变化**（相对补强前）：有读经 2365 不变；≥1 出处 2360→**2364**；出处总数 23103→**23066**；零出处 5→**1**（仅「祭牲」）；疑似遗漏 23→**22**。主因：跨章合并、整章简写回退、空白压缩、章范围识别。夹具与 `stage2_scripture_report.EXPECT` / `verify_stage2` 已同步。
4. **人名别名**：`约翰一书` 靠「后接一书」保护，避免先被改成「约翰福音」。

## 探测结果（v2 CSV）

- 路径：`G:\PanAI4.0专用\logs\formats_v2`
- 306 条中 **304 一致**；不一致仅 S117、S278（见上）。
- 别名对照：**175 一致 / 不一致 0 / 不识别 0**。

## 无法满足的用例（不改期望）

| id | 原因 | 最小替代方案 |
|----|------|----------------|
| S117 | `诗一百二14` 口语改写为 120:14 后，bible_data 诗120 无第14节，validate 滤掉 | 补 bible 数据；或产品接受「章在、节越界仍出 Ref」 |
| S278 | 同上（输入已是「一百二十」） | 同上 |
