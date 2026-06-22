# KG-RAG 系统设计文档 v7.2
> **状态：** 当前有效设计（取代所有旧版本）
> **日期：** 2026-06-19
> **阶段：** Phase 2 完成 / Phase 4 进行中 / testX 全部退役
>
> **v7.2 变更（神圣启示进展·出处质量、全局流水号、重新职事化、UI 优化）：**
>
> **出处匹配质量全面提升：**
> - **`_strip_outline_line` 正则修复**：原正则 `[^一]*` 排除汉字导致经节含书卷名时剥离失败；改为 `[^—－\t-]+` 只匹配最后一段破折号，剥离准确率 36/37→37/37
> - **`_is_valid_source` 复合出处拆分**：支持「节期；文集」混合出处分号拆分，过滤节期子段后保留文集子段，不再整条丢弃；`match_source_from_outlines` 两处 candidate 取值同步更新
> - **生命读经阶段限制**：阶段1（倪柝声）和阶段2（李1932-1973）不能出现生命读经出处，阶段3-5可用
> - **`_clean_source` 新增**：清洗出处末尾「，第X段」（含「第X、Y段」「第X至Y段」「第X～Y段」多段格式）、年份季节标注（「，1993冬」「，1985夏」「，1986年」）、星号（`*`/`**`）
> - **复合出处只取第一个有效子段**：分号拆段匹配到多个出处时只保留第一个，避免脚注显示「出处A；出处B」
> - **Prompt 核心约束**：`_SEGMENT_RULES_CONTENT` 新增「核心约束」块，强化大纲行逐字引用，禁止概括句、分号拼接、定义式表述
> - **固定基准实测命中率**：62.5%（修复前）→ 97.6%（第一篇）/ 91.4%（第四组）
>
> **全局流水号（msg. 编号）：**
> - **规则**：介言固定 msg.1，各阶段实际生成篇数依序累加（不查 ES 总篇数）
> - **前端 `currentMsgNo` ref**：初始值1，切换系列时归零，每次职事化成功后 `+= articles.length`；传给后端 `global_article_offset = currentMsgNo + 1`
> - **后端优先用前端传入值**：`ministerialize_segment` 接收 `global_article_offset`，有值直接用，否则退回 ES 计算
> - **文件名**：`msg. {N} （{阶段}）{篇题}.docx`（去掉「含出处」，剥离篇题中已有的「第X篇　」前缀）
> - **Header 第3行**：保留原始「第X篇　篇题」（不被全局号覆盖），与文件名分离
>
> **重新职事化 Tab（新增）：**
> - 上传本地 DOCX（支持多选），自动从文件名识别篇号、阶段、篇题（兼容全角 `ｍ`）
> - 后端新增 `POST /api/progress/parse_docx_text`：解析 DOCX 正文，从读经行开始提取（支持 U+2236 `∶` 变体）
> - 单篇或批量职事化，处理中显示「处理中…」状态
> - 下载同现有「含出处下载」流程
>
> **数据质量排查：**
> - 全索引扫描发现 16 篇 outline 为空（0.3%），根因：Word 文档使用 `读经∶`（U+2236）未被识别；`ingest_pano.py` 已修复（`READING_MARKERS` 新增两个变体，`_split_para_by_color` 新增括号出处 fallback）
> - 空 outline 清单已导出，待有 Word 源文件时重新 ingest
> - source 有效率 87.2%；纯节期 5.8%、年份跨期 4.2%、source 为空 2.8%（均为预期行为）
>
> **UI 优化：**
> - 费用显示重构：去掉 token 数，只显示美元金额；三层结构（操作级 meta-row / 篇级标题栏 / 系列级底部栏）
> - 职事化费用为 $0 时不显示
> - 按钮文字「下载含出处 DOCX」→「含出处下载」
> - SOP 文档已生成（75系列纲目制作SOP.docx）
>
> **v7.1 变更（神圣启示进展·职事化与出处功能全面升级）：**
>
> **神圣启示进展·分段纲目职事化流水线（新增）：**
> - **整体流程**：生成分段纲目后自动接入职事化 → 进展75系列走文字匹配出处（不调 Claude/Haiku）→ 每篇生成带上标脚注的 DOCX；点击不同阶段时自动清空上一段结果
> - **按篇处理**：`segmentGroupResults` 每个 group = 一篇纲目；逐篇串行职事化，篇内并发处理各纲目行
> - **Header 构建**（四行）：第一行「主恢复中神圣启示的进展」、第二行「系列名 + 软回车 + 五段完整标题」、第三行「第{中文数字}篇　篇题」（支持用户手动输入第几篇前缀自动识别不重复）、第四行「读经：{经节}」；前三行 DOCX 居中
> - **五段完整标题映射**：1→「倪柝声弟兄职事」、2→「李常受弟兄职事第一阶段（1932-1973）」、3→「李常受弟兄职事第二阶段（1974-1984）」、4→「李常受弟兄职事第三阶段（1985-1990）」、5→「李常受弟兄职事第四阶段（1991-1997）」
> - **进展75系列出处匹配**：`progress_pano` 索引的 `outline[].source` 字段已含原始出处，不调 Claude/Haiku；`_strip_outline_line()` 剥离序号前缀和经节后缀，`_overlap_ratio()` 计算重叠率，整行匹配失败则按分号拆段逐段匹配；threshold=0.5；阶段1（倪柝声）仅保留倪柝声文集相关出处
> - **出处过滤**：`FESTIVAL_KEYWORDS`（15个节期纲目关键词）过滤节期内容；`STAGE_YEAR_RANGES` 按阶段年份范围过滤跨期出处；支持中文年份解析（如「一九九五年」→1995）；出处括号自动去除
> - **多段出处**：分号分割后各段出处不同时用「；」拼接；相同出处合并
> - **脚注上标格式**：纲目行末加 Word XML `<w:vertAlign w:val="superscript"/>` 上标数字（非 `[1]` 文字格式）；相同出处共用同一编号，首次出现顺序排列
> - **参考与参读资料**：标题行「参考与参读资料：」方正楷体_GBK 小四；条目格式「数字.[Tab]内容」方正书宋_GBK 小四，左缩进 2 字符，悬挂 1 字符，末尾不加标点；内容末尾标点自动清除
> - **类型统计栏**：每篇顶部显示全部/原文/微调/已替换/人工处理各类数量标签，点击筛选只显示该类型行
> - **费用统计**：每篇显示职事化费用（Haiku 输入/输出 tokens）；进展75系列不调 Claude 费用为 $0.0000；meta-row 新增职事化汇总费用；页面右下角悬浮蓝色圆角栏显示全系列累计费用（跨阶段点击持续累加，刷新归零）
> - **用户操作**：每行可「重跑」（单行重新调 `/api/kg_rag/ministerialize`）、「删除」；source_zh 编辑框修改后脚注编号自动联动更新；下载 DOCX 使用用户编辑后的版本
>
> **新增后端文件：**
> - `features/progress_outline/ministerialize_service.py`：`STAGE_FULL_TITLES`、`STAGE_YEAR_RANGES`、`FESTIVAL_KEYWORDS`、`_ZH_DIGITS`/`_to_zh_num()`、`parse_outline_text()`、`build_header_lines()`、`build_footnotes()`、`_strip_outline_line()`、`_overlap_ratio()`、`_is_valid_source()`、`match_source_from_outlines()`、`ministerialize_one_article()`、`ministerialize_one_article_pano()`、`ministerialize_segment()`
>
> **新增后端接口（2条）：**
> - `POST /api/progress/ministerialize_segment`：接收 `group_results + series_title + stage_no + outline_sources + is_pano`；进展75系列走 pano 路径（文字匹配），新增词条走 Claude/Haiku 路径
> - `POST /api/progress/ministerialize_download`：接收 `header_lines + outline_lines(含 footnote_no) + footnotes + article_title`；生成含上标和脚注的 DOCX
>
> **format_service.py 扩展：**
> - 新增 `_add_superscript_run()`：Word XML 上标 run
> - 新增 `make_zh_docx_with_headers()`：含 header_lines 居中、软回车、纲目行上标、参考资料格式的 DOCX 生成
> - 新增 `_apply_footnote_title_style()`：方正楷体_GBK 小四
> - 新增 `_apply_footnote_item_style()`：方正书宋_GBK 小四，左缩进2字符，悬挂1字符
> - 新增 `format_ministerialize_docx()`：对外接口，返回 (bytes, filename)
>
> **ProgressOutline.vue 扩展（1021行→1521行）：**
> - 新增 ref：`ministerializeResults`、`ministerializing`、`ministerializeError`、`articleExpanded`、`totalCumulativeCost`、`ministerializeUsage`、`activeFilterStatus`
> - 新增函数：`toggleArticle`、`computeFootnotes`、`onSourceZhChange`、`ministerialize`、`downloadArticleDocx`（改调新接口）、`statusColor/Label/Class`、`removeLine`、`rerunLine`、`articleStatusCounts`、`filteredLines`、`setFilter`
> - 新增 UI：「生成纲目职事化」按钮（紫色）、职事化结果卡片（可折叠，默认第1篇展开）、类型统计筛选栏、脚注区、每篇下载按钮、全系列累计费用悬浮栏
> - `onStageClick` 切换阶段时自动清空职事化结果和分段纲目结果
>
> **v7.0 变更（增强式翻译 v2 + 神圣启示进展 + testX 退役）：**
>
> **增强式翻译 v2（testD 协作者三轮迭代成果全量并入）：**
> - **行类型三分法**：新增 `_precompute_line_types()`，跨行上下文识别 `title`/`bible-reading`/`outline`/`reference` 四类；篇题行走专用 `_retrieve_title_line()`（Pool 精确→ES 子串召回→本地 pool 召回→Levenshtein 排序取 1~2 条）；读经行走 `_retrieve_bible_reading_line()`（空参考直入 Gemini，仅做格式转换）
> - **source_translator 全量重写**（142行→~960行）：`parse_source_from_line` 新签名返回 `list[str]`（支持多出处）；新增路1 `_kg_rag_source_lookup()`（结构化 query 变体+BM25召回+精确匹配）、路2 `_gemini_translate_sources()` 批量 Gemini、路3 `_feasts_pool_lookup()`+`_gemini_infer_source_en()`；新增调试工具 `SourceLookupResult`/`_kg_rag_source_lookup_debug()`/`verify_source_lines()`
> - **OpenCC 归一化 + 中文匹配增强**：`pool.py` 引入 OpenCC t2s + `_VARIANT_MAP`（11组异体字）；新增 `zh_eq/zh_contains/zh_fuzzy_eq/levenshtein_distance/recall_local_pool_hits`
> - **双出处支持**：`reference_source_zh_list: list[str]` 替代单字符串；出处费用累入 `cumulative_usage["cost_usd"]`
> - **英翻中完整链路**：新增 `enhanced_translate_en2zh()` 等；`POST /api/ai_search/enhanced_translate/en2zh`
> - **rerank 专属模块**：新建 `features/enhanced_translate/rerank.py`，降级必打 WARNING + 写入 `warnings[]`
> - **Pool 数据**：合并 testD 增量 176 条，当前 **2600 条**
>
> **工具箱·神圣启示进展（新增，v7.0 基础功能）：**
> - 双 Tab：进展75系列（ES `progress_pano` 索引）+ 新增词条（BM25+Dense+Rerank 检索）
> - Claude Sonnet 4.6 生成分段纲目；中文刷格式 DOCX 下载
>
> **testX 全部退役（v7.0）：**
> - testA/test_B/testC/testD 四目录物理删除；主站为唯一维护点

---

## 一、技术选型

| 模块 | 选型 | 职责 |
|------|------|------|
| 前端 | Vue 3（现有）| 首页 AI 纲目面板（正式）+ 测试工作台（保留）+ 工具箱 |
| API 层 | FastAPI（现有）| 查询编排 · 检索融合 · LLM 调用 |
| 检索引擎 | Elasticsearch 8.x（现有）| BM25 + kNN 双路 + 元数据存储 |
| 知识图谱 | Neo4j Community 5.x（Docker）| 概念网络 · 概念间路径 · Scripture 节点 · 关键经文 |
| LLM | Claude API（现有）| 概念选取 · 骨架构建 · 纲目生成 · 防火墙判断 · 负担说明生成 · 职事化抽句与判断 |
| 嵌入模型 | Qwen3-Embedding-8B（OpenRouter，1024 维）| 中文语义向量 |
| 精排模型 | Jina Reranker v3（现有）| RRF 融合后精排，10s 超时 + 重试 1 次 |
| 缓存 | Redis（现有）| KG-RAG 结果缓存 + 翻译缓存 + 监控 |
| 部署 | 搬瓦工 VPS（现有）| 同机器新增 Neo4j |

**Embedding 适配层：** `kg_rag/embedding_adapter.py`，profile="kg_rag"（Qwen3 1024 维）。

---

## 十一、工具箱·神圣启示进展（v7.0 新增，v7.1 大幅升级）

### 11.1 功能概述

围绕李常受职事五个历史阶段（倪柝声弟兄职事 / 李常受弟兄职事第一至四阶段），辅助生成中文分段纲目并自动职事化加出处。两个 Tab：进展75系列使用专属 `progress_pano` ES 索引，新增词条使用 kg-rag 四索引检索。

**v7.1 核心新增**：生成分段纲目后自动串行职事化每篇 → 进展75系列直接从 ES 原始 `outline[].source` 字段文字匹配出处（不调 Claude/Haiku，费用 $0）→ 每篇生成带 Word 上标脚注的含出处 DOCX。

### 11.2 两个 Tab 的流程

**Tab 一：进展75系列（v7.0 + v7.1 升级）**
```
GET /series-list → 系列下拉框
用户选系列 + 点阶段按钮 → POST /pano/search → articles[]（含 outline[].source 字段）
→ Claude 分组 → Y 组检索结果展示
→ 点「生成分段纲目」→ 并发生成 Y 篇纲目
→ 自动判断是否有有效纲目（text 非空）
→ 有效 → 点「生成纲目职事化」→ POST /ministerialize_segment（is_pano=true）
  → 后端串行逐篇：
    parse_outline_text() 解析读经行 + 纲目行
    → match_source_from_outlines() 文字匹配 outline_sources（含分号分割）
    → _is_valid_source() 过滤节期/跨期出处
    → build_footnotes() 构建脚注编号
    → build_header_lines() 构建四行 header
  → 返回 articles[]（含 lines/footnotes/header_lines/usage）
→ 前端展示：可折叠篇卡 + 类型统计筛选栏 + 脚注区 + 费用
→ 点「下载含出处 DOCX」→ POST /ministerialize_download → 含上标脚注的 DOCX
```

**Tab 二：新增词条（v7.0，职事化待完善）**
```
用户输入词条 + 选阶段 → POST /entry/search
→ BM25 + Dense(qwen3-embedding-8b 1024维) + RRF + Jina Rerank
→ 检索 kg-rag 四索引（kg-rag_life/cwwl/cwwn/others，按 year_range 过滤）
→ items[] → 分组 → 生成分段纲目
→ 职事化（待完善：需按阶段过滤检索范围，避免跨期内容）
```

### 11.3 进展75系列出处匹配算法（v7.1 新增，v7.2 大幅升级）

**核心原理**：`progress_pano` 索引每条 `outline` 行已含 `source` 字段，Claude 生成纲目时逐字引用原文，因此可直接文字匹配，不调 LLM，费用 $0。

**v7.2 升级要点**：修复经节剥离正则、复合出处拆分、生命读经阶段限制、出处清洗，固定基准命中率 91-97%。

```python
# 1. 剥离序号和经节后缀（v7.2 修复）
_strip_outline_line("壹\t神圣属天的方庭—出二五8：")
→ "神圣属天的方庭"
# 修复：原正则排除汉字导致「—约一4。」等含书卷名后缀无法剥离
# 新正则：[^—－\t-]+ 只匹配最后一个破折号到末尾标点

# 2. 整行匹配（threshold=0.5）
→ 成功：取 candidate 后经 _clean_source() 清洗

# 3. 整行失败 → 按分号拆段逐段匹配
"A；B；C" → ["A", "B", "C"] → 各自匹配 → 只取第一个有效出处

# 4. 出处过滤（_is_valid_source，v7.2 升级）
→ 复合出处先按分号拆分，过滤含节期关键词子段，只取第一个有效子段
→ 过滤节期关键词（FESTIVAL_KEYWORDS 15个）
→ 过滤超出阶段年份范围（STAGE_YEAR_RANGES）
→ 生命读经：阶段1/2 过滤，阶段3/4/5 保留
→ 阶段1（倪柝声）额外限制：仅保留含「倪」/「柝声」的出处

# 5. 出处清洗（_clean_source，v7.2 新增）
→ 去掉末尾「，第X段」「，第X、Y段」「，第X至Y段」「，第X～Y段」
→ 去掉末尾年份季节标注（「，1993冬」「，1985夏」「，1986年」）
→ 去掉末尾星号（* / **）
```

**状态标记**：
- 匹配到有效出处 → `status: "original"`（绿色）
- 无法匹配 → `status: "manual"`（红色，需手动输入出处）

**实测命中率（v7.2，固定基准）**：
| 测试篇 | 命中率 | 未命中原因 |
|--------|--------|-----------|
| 神的行政·第一篇（42行）| 97.6% | 1行：ES 出处纯节期无文集子段 |
| 神的行政·第四组（35行）| 91.4% | 3行：出处年份属 stage5，stage3 下正确过滤 |

### 11.4 Header 与 DOCX 格式规范（v7.1 新增）

**Header 四行**：
| 行 | 内容 | DOCX 样式 | 对齐 |
|----|------|-----------|------|
| 第1行 | 主恢复中神圣启示的进展 | `0系列` | 居中 |
| 第2行 | `{series_title}\n{stage_full_title}` | `11111西列`，软回车 | 居中 |
| 第3行 | `第{中文数字}篇　{篇题}` | `00篇题` | 居中 |
| 第4行 | `读经：{经节}` | `11读经` | 默认 |

**篇号智能识别**：若用户在主题框手动输入「第一篇　篇题」，正则检测到 `^第[中文/数字]+篇` 前缀则直接使用，不再追加编号。

**上标格式**：Word XML `<w:vertAlign w:val="superscript"/>`，紧跟纲目文本，无标点。

**参考与参读资料**：
```
参考与参读资料：          ← 方正楷体_GBK，小四
1.[Tab]出处内容           ← 方正书宋_GBK，小四，左缩进2字符，悬挂1字符，末尾无标点
2.[Tab]出处内容
```

### 11.5 后端结构（`features/progress_outline/`，v7.1 更新）

| 文件 | 说明 |
|------|------|
| `router.py` | **11 条接口**（v7.0 原9条 + v7.1 新增2条），全路由 `Depends(test_token)` |
| `prompts.py` | 分段纲目 Prompt（PANO/ENTRY × SEGMENT），详细写作规范（7维展开 + 4.5~4.7节） |
| `llm_client.py` | Claude Sonnet 4.6；`call_claude(system, user, max_tokens=16000)`；费用计算 |
| `pano_series_service.py` | ES `progress_pano` 查询；`list_series()`/`search_articles()`/`group_articles_by_theme()`；ES 异常降级 |
| `new_entry_service.py` | BM25+Dense+RRF+Rerank 检索 kg-rag 四索引 |
| `format_service.py` | 中文刷格式 DOCX（`format_zh_docx`）+ **含出处版 DOCX（`format_ministerialize_docx`，v7.1 新增）** |
| `ministerialize_service.py` | **v7.1 新建，v7.2 大幅升级**；新增 `_clean_source`、生命读经过滤、复合出处拆分、`_get_global_article_offset` |
| `group_edit_service.py` | 分组编辑与重新计算 |
| `token_utils.py` | token 估算 + `default_output_length` 建议 |
| `中文纲目模板.docx` | 刷格式模板（同目录） |

### 11.6 后端接口（`/api/progress/*`，v7.1 更新为 11 条）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/series-list` | 返回系列下拉数据 |
| POST | `/pano/search` | 按系列+阶段检索，返回 articles + 分组 + 分组费用 |
| POST | `/entry/search` | 按词条+阶段检索，返回 items + 分组 |
| POST | `/pano/generate/segment` | 生成分段纲目（进展75材料） |
| POST | `/entry/generate/segment` | 生成分段纲目（新增词条材料） |
| POST | `/format_download` | 刷格式 DOCX 下载（普通版） |
| POST | `/format_download_batch` | 多组 ZIP 下载 |
| POST | `/groups/recompute/pano` | 分组拖拽重算（pano） |
| POST | `/groups/recompute/entry` | 分组拖拽重算（entry） |
| POST | `/ministerialize_segment` | **v7.1 新增**；职事化分段纲目；`is_pano=true` 走文字匹配，`false` 走 Claude/Haiku |
| POST | `/ministerialize_download` | **v7.1 新增**；生成含上标脚注的 DOCX |
| POST | `/parse_docx_text` | **v7.2 新增**；解析上传 DOCX，从读经行起提取纯文字（支持 U+2236 变体） |

**`/ministerialize_segment` 请求体**：
```json
{
  "group_results": [{"title": "篇题", "text": "纲目正文"}],
  "series_title": "神的行政",
  "stage_no": 3,
  "outline_sources": [{"text": "原始outline行", "source": "出处"}],
  "is_pano": true,
  "global_article_offset": 2
}
```
`global_article_offset`：前端传入本次第一篇的全局 msg. 号（介言=1，各阶段实际生成篇数累加），后端优先用此值，否则退回 ES 计算。

**`/ministerialize_download` 请求体**：
```json
{
  "header_lines": ["主恢复中神圣启示的进展", "系列名\n阶段标题", "第一篇　篇题", "读经：约一14"],
  "outline_lines": [{"text": "壹\t纲目行", "footnote_no": 1}],
  "footnotes": [{"no": 1, "source_zh": "倪柝声文集..."}],
  "article_title": "神所设立的权柄制度"
}
```

### 11.7 数据索引（`progress_pano`）

共 4630 篇文档（实际灌入数），mapping 含：`series_no`（integer）、`series_title`（keyword）、`source_group_no`（integer）、`source_group_title`（keyword）、`article_no`（integer）、`title`（keyword）、`metadata`（text）、`outline`（nested: `type`/`text`/`source`）、`ministry_excerpt`（nested: `text`）。

**关键字段**：`outline[].source` 存储每条纲目行的职事书出处，v7.1 职事化功能直接从此字段提取，无需调 LLM。

### 11.8 前端组件（`features/progress_outline/ProgressOutline.vue`，v7.1 更新为 1521 行）

**新增 UI 区域**（v7.1/v7.2）：
```
检索 + 分组（已有）
  ↓
生成分段纲目（已有）
  ↓
[新增] 「生成纲目职事化」按钮（紫色，disabled 直到有分段纲目结果）
  ↓
[新增] 纲目职事化结果卡片
  ├── 每篇可折叠子卡片（默认第1篇展开）
  │   ├── 折叠标题：「第N篇　篇题」+ 费用 + 下载按钮
  │   └── 展开内容：
  │       ├── [新增] 类型统计筛选栏（全部/原文/微调/已替换/人工处理 + 行数/tokens）
  │       ├── 前四行 header（居中）
  │       ├── 职事化行列表（状态标签/重跑/删除/结果编辑框/上标/source_zh编辑框）
  │       ├── 脚注区（参考与参读资料）
  │       └── 本篇费用
  └── （页面右下角）全系列累计费用悬浮栏
```

**费用统计位置**（v7.2 重构）：
- `meta-row`：一行显示「费用：分组 $X · 纲目 $X · 职事化 $X」（去掉 token 数）
- 每篇标题栏：费用 > 0 时显示金额，$0 不显示
- 右下角悬浮：「本阶段 $X · 跨阶段累计 $X」

**v7.2 新增 ref/函数**：
- `currentMsgNo`：全局流水号计数器，初始1，切换系列归零，职事化成功后 += 篇数
- `reprocessFiles/reprocessParsed/reprocessing/reprocessError`：重新职事化 Tab 状态
- `parseFilename()`：从文件名解析篇号/阶段/篇题（兼容全角 ｍ）
- `handleReprocessUpload()`：上传解析 DOCX
- `reprocessMinisterialize()`：单篇职事化
- `reprocessAll()`：批量职事化（跳过已完成篇）
- `downloadReprocessDocx()`：下载含出处 DOCX

### 11.9 出处联动规则（v7.1）

| 操作 | 效果 |
|------|------|
| 修改某行 source_zh | 脚注列表同步更新，编号重新整理 |
| 多行相同 source_zh | 共用同一脚注编号 |
| 清空 source_zh | 该行上标移除，后续编号重排 |
| 手动输入 source_zh（manual 行）| 新增脚注条目，获得编号 |
| 点「重跑」 | 单行重调 `/api/kg_rag/ministerialize`，结果更新后脚注重算 |
| 点「删除」 | 从行列表移除，脚注重算 |

### 11.10 已知挂起与待完善（v7.2）

- **新增词条职事化**：目前调用全库 `ministerialize_outline()`，可能检索到跨期或节期内容；待按 `stage_no` 过滤检索索引和年份范围（设计方案已定，实现待做）
- **进展75匹配率（v7.2 已大幅提升）**：固定基准实测 91-97%；剩余未命中均为数据边界（ES 出处纯节期或年份跨阶段），算法层面已到天花板
- **16 篇空 outline**：根因已找到（`读经∶` U+2236），`ingest_pano.py` 已修复，待有 Word 源文件时重新 ingest（清单见 `empty_outline_16.json`，已清理）
- `progress_pano` 索引服务器导入（`import_pano_json.py` 已备）
- Prompt 内容可按实际使用效果迭代
- **重做某阶段**：刷新页面 `currentMsgNo` 自动归零，从头重新累计

---

## 十二、开发阶段记录

### Phase 1：已完成
离线流水线 + ES 九索引 + Neo4j + 测试工作台 + 322 概念节点

### Phase 2：已完成
（详见 v7.0 文档，含 v3.7~v7.0 全部变更记录）

- 纲目职事化·四状态 + Haiku 判断 + 含出处下载（v5.8/v5.9）
- 神圣启示进展 feature 化迁入主站（v7.0）
- testA/test_B/testC/testD 全部退役删除（v7.0）
- **神圣启示进展·分段纲目职事化流水线（v7.1）**：文字匹配出处、脚注上标、含出处 DOCX、类型统计、费用累计、阶段切换清空
- **神圣启示进展·出处质量与全局流水号全面升级（v7.2）**：正则修复、复合出处拆分、生命读经过滤、`_clean_source`、全局 msg. 号 `currentMsgNo`、重新职事化 Tab、费用 UI 重构、ingest_pano 修复

### Phase 3：全量调优
参数定型 · 质量评估

### Phase 4：正式前端完善（进行中）
图谱可视化 · 段落溯源可读化

### Phase 5：持续迭代
概念演进追踪 · 问答系统（希腊原文启用）

---

## 附录 A：环境变量

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<密码>
OPENROUTER_API_KEY=<key>
EMBEDDING_KG_MODEL=qwen/qwen3-embedding-8b
EMBEDDING_KG_DIMS=1024
ES_USERNAME=elastic
ES_PASSWORD=<密码>
CLAUDE_API_KEY=<key>
JINA_API_KEY=<key>
# v6.6 增强式翻译（均可省略，使用默认值）
ENHANCED_TRANSLATE_GEMINI_MODEL=gemini-3.5-flash
ENHANCED_TRANSLATE_GEMINI_FALLBACK=gemini-2.5-flash
ENHANCED_TRANSLATE_AUTO_APPEND=1
```

---

## 附录 C：待办

| 事项 | 优先级 |
|------|--------|
| 参数定型 | Phase 3 |
| 质量评估 | Phase 3 |
| 图谱可视化 | Phase 4 |
| 段落溯源可读化 | Phase 4 |
| 概念演进追踪 | Phase 5 |
| 问答系统（希腊原文启用）| Phase 5 |
| 增强式翻译·rerank 分数阈值 | 待定 |
| 增强式翻译·Pool 并发写保护与容量规划 | 二期 |
| 学生练习区（testX）删除 | ✅ v7.0 已完成 |
| 神圣启示进展 progress_pano 索引服务器导入 | 待执行 |
| 神圣启示进展·新增词条职事化按阶段过滤 | 待开发 |
| 神圣启示进展·16篇空 outline 重新 ingest | 待执行（需 Word 源文件） |
| 神圣启示进展·完整 E2E 验证（进展75 + 新增词条） | 待执行 |

---

## 附录 D：涉及文件清单（v7.1 新增/变更）

| 文件 | 变更说明 |
|------|---------|
| `back_mic/backend/features/progress_outline/ministerialize_service.py` | v7.2：`_clean_source`（去段/去季节/去星号）；`_is_valid_source` 复合出处拆分；`_get_global_article_offset`；生命读经阶段过滤；`_strip_outline_line` 正则修复；`match_source_from_outlines` 只取第一个有效子段 |
| `back_mic/backend/features/progress_outline/router.py` | v7.2：新增 `POST /parse_docx_text`；`MinisterializeSegmentRequest` 新增 `global_article_offset`、`series_no`、`active_stage_no` |
| `back_mic/backend/features/progress_outline/format_service.py` | v7.1：新增 `_add_superscript_run`、`make_zh_docx_with_headers`（含软回车/上标/脚注格式）、`_apply_footnote_title_style`（方正楷体_GBK）、`_apply_footnote_item_style`（方正书宋_GBK，悬挂缩进）、`format_ministerialize_docx` |
| `back_mic/backend/scripts/progress_outline/ingest_pano.py` | v7.2：`READING_MARKERS` 新增 `读经∶`/`讀經∶`（U+2236）；`_split_para_by_color` 新增括号出处 fallback |
| `front_mic/frontend/src/features/progress_outline/ProgressOutline.vue` | v7.2：新增「重新职事化」Tab（上传/解析/批量职事化/下载）；`currentMsgNo` 全局流水号；费用 UI 重构（三层，去 token 数）；文件名剥离「第X篇　」前缀；按钮文字「含出处下载」；`parseFilename/handleReprocessUpload/reprocessMinisterialize/reprocessAll/downloadReprocessDocx` |

---

*最后更新：2026 年 6 月 19 日（v7.2：出处质量全面提升·全局流水号·重新职事化 Tab·UI 优化）*
