# Stage 4/5 开放问题（open_questions）

## OQ-DOC-1
- 问题：本机仓库未找到《PanAI4.0_问答流程设计_技术版_20261112》《后端构建方案_20261116》《功能列表_20261117》原件。
- 采用：按用户本条指令中的要点与现有 pipeline/schemas 实现编写提示词与前端。
- 其它选项：停工等待文档；从其它盘符搜索。

## OQ-P3-SUMMARY
- 问题：第5步小结与关键经节【待定】。
- 采用：v0.1 不输出小结与关键经节。
- 其它选项：输出空字段；输出占位字符串。

## OQ-P3-INDUCTION-STYLE
- 问题：归纳的视觉样式【待定】。
- 采用：前端用最朴素两种样式（正文默认 / 归纳用斜体或浅色前缀「〔归纳〕」），具体美化后议。
- 其它选项：Markdown 引用块；单独颜色主题。

## OQ-P3-CHURCH-LIFE-ANGLES
- 问题：召会生活复杂拆分四角度【暂定】。
- 采用：写入 step3 草稿提示词，并注明【暂定】；程序不强制校验角度枚举。
- 其它选项：做成 config 开关；完全不写进提示词。

## OQ-P1-CHANNEL
- 问题：草稿通道环境变量名与默认值。
- 采用：`QA4_PROMPT_CHANNEL=stable|draft`，默认 `stable`；registry CURRENT 不变。
- 其它选项：配置文件开关；按版本号直接指定。

## OQ-SUMMARY-REUSE
- 问题：定向摘要是否单独提示词文件。
- 采用：复用 step8 + 程序前缀「（归纳）」。
- 其它选项：新增 step8_summary_v0.1；摘要专用短提示词。
- 文件：pipeline/step08_answer.py、prompts/texts/step8_v0.1.txt

## OQ-FRONTEND-LEGACY
- 问题：是否保留 front_qa 复制来的大型 QAPage.vue。
- 采用：路由改用 Qa4Page；旧文件暂留不引用。
- 其它选项：删除旧页；逐步移植全部 UI。
- 文件：qa4/frontend/src/components/Qa4Page.vue

## OQ-E2E-SKIP
- 问题：Playwright 冒烟是否必做。
- 采用：本次跳过并记录；vitest 覆盖事件状态机。
- 其它选项：补装 Playwright 后补 e2e。

## OQ-LSM-PUBLIC
- 问题：qa4/frontend/public/lsm（约 544MB、1984 文件，与 front_qa/public/lsm 一致）是否进仓库。
- 采用：gitignore，不进仓库；部署时由阶段7决定来源（front_qa 本身只跟踪该目录 1 个文件）。本地可仍保留目录供 BibleMessage 等组件开发引用。
- 其它选项：删除死组件后再删 lsm；或改为按需 CDN。
- 文件：BibleMessage.vue、public/lsm、qa4/frontend/.gitignore

## OQ-README-RESTORE
- 问题：qa4/frontend/README.md 曾在快照后缺失。
- 采用：从 qa4_snapshot_20261117.zip 原样恢复；记为复制整理时误删。
- 其它选项：重写 README。

## OQ-SCRIPTURE-SUBQ-CHANNEL
- 问题：技术版「带经文出处且还问别的事 → 其中一子问题走经文通道取职事对该节讲论」。
- 采用：现无专用字段/机制（仅有 SubQuestion.scope 收窄 ES 索引）；提示词不写该通道。
- 其它选项：为子问题增加 scripture_ref / channel=scripture_ministry 并由 step06 走注解或 targeted。
- 文件：step03_plan、step06_retrieve、schemas.SubQuestion

## OQ-STEP3-LIST-SIZE
- 问题：step3 注入真实 feast_list+life_book_titles 后估约 13298 token（>1500）。
- 状态：**已处理**。
- 采用：月份码对照（去重名称）+ 年份范围；生命读经书名清单保留。259 场假数据下节期块估约 236 token。
- 其它选项：模型侧 tools 查清单；节期按年过滤后再注入。

## OQ-STABLE-VERSION-KEY
- 问题：stable version_key 是否与改前逐字相同。
- 采用：采用 channel= 前缀，qa4 尚无线上缓存，无影响。现为 `channel=stable;step2=v1.0;…`；测试固定现形。
- 其它选项：stable 省略 channel 前缀（可能与旧缓存兼容，但与 draft 隔离变弱）。

## OQ-STEP3-CACHE
- 问题：step3 草稿是否拆 system cacheable 段。
- 采用：是——`# 本问线索` 之前为 system cacheable；可变 rule_hits/问题放 user。stable 通道不变。
- 其它选项：整段 user；或把清单再拆独立 cache 块。
- 文件：pipeline/step03_plan.py、prompts/texts/step3_v0.1.txt

## OQ-STEP3-SCOPE-VALUES
- 问题：scope 可选值列表是否需 Srey 书面确认。
- 采用：程序从 `retrieval.json` 的 `default_scope` 注入，提示词不写死；待 Srey 确认该列表是否即为产品口径。
- 其它选项：单独 config；提示词写死子集。
- 文件：config/retrieval.json、step03_plan.format_scope_options

## OQ-COMPLEX-BOUNDARY
- 问题：召会生活类何时拆分子问题（complex）的边界。
- 采用：**拆不拆由试答质量决定**——待真模型并排比较「拆」与「不拆」的答案后再定；提示词暂保留「弟兄姊妹离婚了还可以擘饼吗？」为复杂正例。
- 其它选项：一律不拆召会生活；或按关键词规则强制拆。
- 文件：prompts/texts/step3_v0.1.txt

## OQ-STEP4-FLATTEN
- 问题：多子问题 JSON 扁平丢 index 后如何重分配；共用词是否回填所有匹配子问题。
- **采用（第6批已改）**：`assign_to_subquestions` 把词回填到**每一个** `w in sq.text` 的非综合子问题；综合性子问题仍跳过；整题上限 8 按**去重后不同词数**计；每子问题仍 ≤3（比较 ≤4）。未出现在任何 text 的词仍落到第一个有空位的非综合子问题。
- **第5批旧实测**（改前，仅留档）：离婚/擘饼 → 仅子问题0 有词，1/2 为空。
- **第6批新行为**（同输入）：三个非综合子问题各得 `["离婚","擘饼"]`；综合 `[]`。示例 6：`[生机的救恩,素质]` 与 `[生机的救恩,经历]`。
- **风险**：各子问题 `layer1_words` 重叠 → step06 短语检索重叠度可能上升（段落去重仍按 id）。
- **step05/step06 上限核查（第6批只查）**：二者**没有**「把各子问题 layer1 词数相加」来卡整题预算。step05 的 `complex_total_cap=10` 只约束第 2–5 层（`truncate_complex`）；layer1 仅拼进提示词。step06 按子问题独立 `cap`，`layer1_words` 作 phrases。故回填后若有人用 `sum(len(layer1))` 理解「整题 8」，会看到合计可大于 8，但配置口径已改为 unique≤8；**不会**因此自动超出 `step5_caps.json` 的 2–5 层合计上限。
- **`_force_compare_objects`（第6批补充）**：仍用 `sum(len(layer1))` 作挤占启发式（`step04_layer1.py`），回填后比较类子问题的 layer1 **条数合计**可能变大，与整题「去重词数≤8」口径不一致；**目前未改**，试答时关注比较题多子问题场景。
- **重复词（第6批补充只查）**：`run()` 扁平（约 L226–235）后必经 `postprocess_words`（L52–53 `if final in out: continue` 去重；调用 L238 / 兜底 L243）再进 `assign`。故流水线到达 `assign_to_subquestions` 的 `words` **必定已去重**；直接把含重复的列表喂给 `assign` 仍可能误入兜底，但正常路径不会。用例 `test_step4_assign_dup_words` 固定「经 postprocess 后 sq2 不含离婚则不得拿到」。
- 其它选项（未采）：按 index 保留分桶；扁平后按原 index 回填；assign 内对已出现词 skip 兜底（因上游已去重未做）。
- 文件：pipeline/step04_layer1.py、prompts/texts/step4_v0.1.txt；测试 `test_step4_example6_assign.py`、`test_step4_assign_dup_words.py`

## OQ-LAYER-DROPPED-DETAIL
- 问题：prompt_trial 需要「程序丢弃的词 + 原因（不在名单/超上限/重复/不在原文）」逐词列表。
- 现行为：step04 只记 `model_words`/`kept_words` 计数；step05 只记 `dropped_not_in_list`/`dropped_dup` 计数；无词表。
- 采用：JSONL `layers.dropped=[]` + `dropped_note`/`dropped_stats`；不改 pipeline。
- 其它选项：在 step04/step05 `ctx.record` 写入 `dropped:[{word,reason}]`。
- 文件：pipeline/step04_layer1.py、step05_layers.py；tools/prompt_trial.py

## OQ-HISTORY-COL
- 问题：题集「上文」列若混用「上一轮问：」与「问：/答：」、或缺「答：」、或用中文分号/其它分隔，解析边界不清。
- 采用：prompt_trial 优先认标准 `问：/答：` 块；其次 `上一轮问：…答：…`；多段简写仅认单独一行 `---`。无法解析则当空 history。
- 其它选项：强制 CSV 只允许一种格式；校验失败直接报错跳过该题。
- 文件：tools/prompt_trial.py `parse_history`；contracts step2 / prompt_trial 节。

## OQ-VERIFY-CONTRADICT
- 问题：核实说法题，检索材料**只有相反说法**（无原话、无近似）时程序如何处理？
- 现行为：`apply_rules` 仅在模型标 `has_original`/`has_approx` 时强制 overall=够；**不检测「相反」**。若模型未标这两项，overall 保持模型输出（常为不够或自判）；段落是否相反全靠模型。
- 提示词现写法：相反或无关不算 has_original/has_approx；两者都没有才够不上。
- 其它选项：程序侧对立检测；强制 overall=够并 note=相反材料；或单独 verdict 档。
- 文件：pipeline/step07_judge.py（约 34–39）、prompts/texts/step7_v0.1.txt
- 本批：不改程序，只记开放问题。

## OQ-TRIAL-STEP8-TIMING
- 问题：prompt_trial 的 `step_timings_ms` 通常缺 `step8`（整段回答耗时）。
- 原因：`orchestrator` 对第 8 步流式调用未包 `timed()`，只写了 step 事件；`ctx.timings_ms` 无 step8。首字时延可从 `deps.llm.last_stream_result.ttft_s` 记为 `first_token_ms`，无需改 pipeline。
- 若要整段 step8 毫秒：在 `orchestrator` 流式前后记时并写入 `ctx.timings_ms["step8"]`，或让 `note_llm("step8", …)` / trace 带上 `elapsed_s`。
- 本批（9A）：只读现有返回值，不改 pipeline。
- 文件：pipeline/orchestrator.py（step8 流式段）、pipeline/context.py `timed` / `note_llm`；tools/prompt_trial.py
