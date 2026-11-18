# 按时分粮：经文出处写法 / 诗歌首数写法 只读探查报告

日期：2026-11-17  
范围：`G:\copypan\back_anshifenliang`、`G:\copypan\front_anshifenliang`（只读；跳过 node_modules / .venv / .git / dist / build / __pycache__；未打开任何 .env / 密钥类文件内容）  
本文件为唯一新增输出：`qa4/notes/anshifenliang_format_probe.md`

---

## 一、总览

### back_anshifenliang
- Express 搜索后端：内存加载 `data/*.js`，经 JSDOM 复用 `data/scripts.js` 的搜索逻辑（`package.json:4-5`；`lib/bootstrap.js:1-3`）。
- 对外提供 `/api/search`；Telegram / LINE bot 调同一接口（`server.js`；`line_bot/README.md:1-8`）。
- 经文与诗歌的「写法识别 / 标准化」主实现在 `data/scripts.js`。

### front_anshifenliang
- 「按时分粮」浏览器前端；当前 `sendMessage` 把查询 POST 到 `/api/search`（`front_anshifenliang/scripts.js:939-962`）。
- 本地仍加载 `bible_verse.js`、`hymns.js` 等，用于展示 / TTS / `formatMessage`；`scripts.js` 内仍有近乎同构的经文解析函数。
- 前端当前搜索路径**没有**本地 `hymnNumberPattern` 分支（对 `front_anshifenliang/scripts.js` 检索 `hymnNumberPattern` / `大本1`：**无匹配**）。

### 与经文或诗歌写法有关的文件清单
- `G:\copypan\back_anshifenliang\data\scripts.js` — 主规则：预处理、书卷映射、章节/经节识别与转换、诗歌编号与目录同义词、控制台测试函数、出处展开与 TTS。
- `G:\copypan\front_anshifenliang\scripts.js` — 近副本：`preprocessInput`、`isBibleVerseReference`、`testBibleVerseStandardization` 等仍在；搜索走 API。
- `G:\copypan\back_anshifenliang\data\bible_verse.js` — 经文章节键值表，键形如 `创一1`（`:2`）。
- `G:\copypan\front_anshifenliang\bible_verse.js` — 同用途数据表（由 `index.html` 加载）。
- `G:\copypan\back_anshifenliang\data\hymns.js` — 诗歌键：`诗歌第N首…` / `补充本诗歌第N首…` / `儿童诗歌第N首…` / `诗歌附N…`（`:2`、`:782`、`:788`、`:1301`）。
- `G:\copypan\front_anshifenliang\hymns.js` — 同用途。
- `G:\copypan\back_anshifenliang\data\jing_jie_wen_da.js` — 问答正文内嵌出处示例（如 `赛九6`、`约十四16~17`）。
- `G:\copypan\front_anshifenliang\jing_jie_wen_da.js` — 同用途。
- `G:\copypan\back_anshifenliang\lib\bootstrap.js` — 加载 data + scripts.js，暴露搜索。
- `G:\copypan\back_anshifenliang\lib\search_parse.js` — 解析搜索结果 HTML 中的诗歌/经节条目（结果侧，非输入标准化）。
- `G:\copypan\back_anshifenliang\server.js` — `/api/search` 入口。
- `G:\copypan\back_anshifenliang\telegram_bot\bot.py` — 提示示例含 `诗歌第1首`（约 `:445`）。
- `G:\copypan\back_anshifenliang\telegram_bot\search_api.py` — Python 侧结果解析镜像。
- `G:\copypan\back_anshifenliang\line_bot\README.md` — LINE bot 说明；提到经节细解析未移植等（约 `:64-67`，【待核实】逐字句以该文件为准）。
- `G:\copypan\front_anshifenliang\index.html` — 登录标题含 `（林后十三14）`（`:17`）。
- `G:\copypan\back_anshifenliang\scripts\test_xinyue_search.js` — 手工探测经节分类关键词（非格式矩阵）。
- `G:\copypan\back_anshifenliang\test-search.mjs` — `/api/search` 冒烟（查询与格式无关）。

未找到单独成篇的「经文出处写法 / 诗歌首数写法」研究文档（`.md` 规则专文）：**未找到**。

---

## 二、经文写法

### 相关函数 / 规则（主文件：`back_anshifenliang\data\scripts.js`；front 有近副本）

- `preprocessInput`（`:6099-6116`）— 去掉空格与一批标点；`篇`→`章`，但保护 `诗篇`。
- `CHAPTER_FORMAT_PATTERNS`（`:6120-6182`）— 整章写法正则：`…第N章` / `…N章` / `…篇` 等。
- `detectChapterFormat`（`:6185-6186`）— 是否命中任一章节模式。
- `BOOK_VARIANT_COMPLETE_MAP`（约 `:5930` 起）— 书名变体 → 全称。
- `standardizeBookNameEnhanced`（约 `:6276-6300`）— 查表标准化书名。
- `standardizeChapterNumberEnhanced`（约 `:6308-6340`）— 章号中文/阿拉伯互转相关。
- `identifyAndExtractChapterInfo`（约 `:6348-6374`）— 抽出书+章。
- `standardizeChapterInputEnhanced`（约 `:6382-6414`）— 整章输入标准化为 `书第中文章` 一类结果。
- `AMBIGUOUS_BARE_BOOK_NAMES`（`:6419-6423`）— 裸书名易歧义集合（如 `约翰`、`雅各`）。
- `isBookNameOnlyEnhanced`（`:6430` 起）— 是否纯书名。
- `BOOK_NAME_MAP`（约 `:6613` 起）— 全称/变体 → 简写键（对接 `bible_verse`）。
- `ARABIC_TO_CHINESE` / `B_ARABIC_TO_CHINESE` / `C_ARABIC_TO_CHINESE`（约 `:6794`、`:6908`、`:6926` 起）— 章号数字表；`C_` 表含条目 `'九五': '九十five'`（`:6948`）。
- `arabicToCustomChinese`（约 `:225-239`）— 出处展开时阿章→自定义中文章。
- `isBibleVerseReference`（`:6978-7026`）— 七种经节引用模式识别。
- `convertToStandardFormat`（`:7029` 起）— 转为 `书简写+中文章+阿节`。
- `prioritizeBibleVerse`（约 `:7177` 起）— 识别→转换→查 `window.bibleVerse`。
- `isBibleAnnotationReference` / `parseAnnotationReferenceDetails`（约 `:7300` 起）— 注解引用（可带节注）。
- `formatMessage` 内「重要经节出处」块（约 `:372-419`）— 展开列表与同章范围。
- TTS：`processTextForReadingFromMessage`（约 `:4331` 起）— 把简写出处扩成可朗读形式。

前端对应（仅列已核对）：`preprocessInput`（`front_anshifenliang\scripts.js:5711`）；`isBibleVerseReference`（`:6609`）；`testBibleVerseStandardization`（`:6872`）。

### 支持的写法清单（逐字示例）

**数据键（canonical）**
- `创一1` — 数据 — `back_anshifenliang\data\bible_verse.js:2`
- `创一2` — 数据 — 同文件 `:3`

**控制台测试 `testBibleVerseStandardization`（`:7245-7256`）— 测试**
- `创一1`
- `创 1:1`
- `创1:1`
- `创世记一章1节`
- `创世记第一章一节`
- `创世记第一章第1节`
- `创世记第一章第一节`
- `太一1`
- `太1:1`
- `马太福音第一章第一节`

**模式名/注释中的写法（代码）**
- 模式名 `标准格式(创一1)` — `scripts.js:6996`
- 模式名 `带章字格式(约1章14节)` — `:6999`
- 注释 `模式3: 创11 (连续数字格式)`，但同条 regex 为 `(\d+)[：:](\d+)`（`:7001-7002`、转换侧 `:7070-7071`）— **注释名与实现不一致**
- 出处范围注释：`弗四22-24 / 林前三1~3` — `:393`
- TTS 注释：`创二二1`、`创一1` 等 — 约 `:4426-4428`

**整章测试 `testChapterStandardization`（`:5868-5877`）— 测试**
- `创世记第一章`
- `创世记1章`
- `马太第3章`
- `太1章`
- `罗马书第十二章`
- `罗马12章`
- `林前第一章`
- `哥林多前书1章`

**书名测试 `testBookNameRecognition`（`:5898-5907`）— 测试**
- `创世记`、`马太`、`太`、`罗马`、`罗马书`、`箴言`、`箴言书`、`林前`、`哥林多前书`

**正文/UI 内嵌（数据/前端）**
- `赛九6` — `jing_jie_wen_da.js:2`（标签内）
- `约十四16~17` — `:6`
- `出三十22～25` — `:8`（全角 `～`）
- `（林后十三14）` — `front_anshifenliang\index.html:17`

### 覆盖维度

- 卷名全称 / 简称 / 极简写：有（`BOOK_NAME_MAP`、`BOOK_VARIANT_COMPLETE_MAP`；测试含 `太`、`林前`、`哥林多前书`）。
- 繁体输入：前端 `sendMessage` 会 `convertTraditionalToSimplified`（`front_anshifenliang\scripts.js:946`），但请求体仍传 `rawUserMessage`（`:959`）；后端如何对待繁体【待核实】。
- 英文卷名缩写（John 3:16）：**未找到**解析器。
- 章节分隔：中文章+阿节无分隔（`创一1`）；`章`/`节` 字；半角 `:` / 全角 `：`（模式3 regex `:7002`）。
- 中文数字与阿拉伯混写：有（测试与模式4–6）。
- 全角/半角：预处理去掉一批标点；冒号全半角在识别中保留用途；范围支持 `-` / `~` / `～`（`:394`）。
- `〇`/`零`：识别模式字符类含 `〇`（`:6996`、`:7005`）；`convertToStandardFormat` 模式1 的中文章类**未含** `〇`（`:7047`）— 识别与转换不完全一致。
- 同章范围：出处展开支持（`:393-412`）。
- 跨章范围：展开循环只变节号（`:408-409`），**未见**跨章专用逻辑。
- 整章：`CHAPTER_FORMAT_PATTERNS` + 章节测试。
- 整卷（仅书名）：模式7「仅书名格式」（`:7014`）；另有纯书名增强逻辑。
- 多出处并列分隔：`；;、，,、\s` 等（`:380`）。
- 「第」「章」「节」「篇」：有；`篇`→`章`（保护诗篇）。
- 错别字/异体：主要靠变体表；无独立错别字引擎 — **未找到**专门模块。
- 注解「节注」：有注解引用模块（约 `:7288` 起）。

### 已知不支持或注释中的缺陷
- 模式3 注释写 `创11`，实现要求冒号（`:7001-7002`、`:7070`）。
- 出处范围解析失败时 `无法解析范围`（`:415`）；跨章未实现（见上）。
- `C_ARABIC_TO_CHINESE` 含 `'九五': '九十five'`（`:6948`）。
- 针对经文写法的 `TODO`/`FIXME`：**未找到**（在 `scripts.js` 相关片段检索范围内）。

---

## 三、诗歌写法

### 相关函数 / 规则（`back_anshifenliang\data\scripts.js`，诗歌分类分支）

- 诗歌分类入口（约 `:976` 起）— `selectedCategory === '诗歌'`。
- 含系列关键词时去空格标点（`:980-982`）。
- `normalizeDirectoryName`（`:992-1024`）— 目录同义词：`大本`→`诗歌目录`，`补充本`/`小本目录`→`补充本诗歌目录`，`儿童`→`儿童诗歌目录` 等。
- `hymnNumberPattern` / `hymnPattern`（`:1067-1074`）— 识别 `大本`/`补充本`/`小本`/`补`/`儿童`/`童`/`儿`/`诗歌第` + 数字 + 可选 `首`；或纯数字。
- 纯数字时按 `诗歌第N首` → `补充本诗歌第N首` → `儿童诗歌第N首` 三系列查找（`:1082-1092`）。
- 错误提示示例（`:1276`）：`大本1`、`补充本5`、`儿童10`。
- `formatMessage` 中「查看全文」类链接正则含 `(大本诗歌|补充本诗歌|儿童诗歌)第\d+首` 与 `附\d+` 等（约 `:514-528`，【待核实】精确行号以文件为准）。
- `lib/search_parse.js` — 结果 HTML 里识别诗歌标题（结果侧）。
- Telegram 提示：`诗歌第1首`（`telegram_bot\bot.py:445`）。

前端：当前搜索**不**跑上述 `hymnNumberPattern`（见总览）。

### 支持的写法清单（逐字）

**数据键**
- `诗歌第1首　颂赞三一神─祂的计划…` — `hymns.js:2`（键前缀为 `诗歌第1首`）
- `诗歌附1赞美主─一般…` — `:782`（`附` 后无 `首`）
- `补充本诗歌第1首　开口赞美…` — `:788`
- `儿童诗歌第1首　神说要有光` — `:1301`
- 目录键：`诗歌目录` / `补充本诗歌目录` / `儿童诗歌目录` — 约 `:1631-1633`【待核实精确行】

**代码提示 / 正则**
- `大本1`、`补充本5`、`儿童10` — `:1276`
- 目录输入字面量列表见 `:986` 正则与 `:997-1019` 同义词表
- 编号正则字面：`大本诗歌第|大本第|大本|补充本诗歌第|…|诗歌第` + `^\d{1,4}[\s首]*$` — `:1067`

### 覆盖维度
- 阿拉伯首数：有（`\d{1,4}`）。
- 中文数字首数（「第一百首」）：**未找到**输入解析。
- `第N首` / `N首` / `诗歌第N`：正则允许前缀 + 数字 + 可选 `首`。
- `#N`：**未找到**。
- 大本 / 补充本 / 小本 / 补 / 儿童 / 童 / 儿：有同义词与前缀。
- 系列与号码重叠：纯数字时三系列都查（`:1087-1092`）。
- `附N`：数据键存在（`:782`）；编号输入正则 **不含** `附`（`:1067`）。
- 多首并列 / 首数范围：**未找到**输入侧规则。
- 标题内英文号 `(英 1　西 1)`：仅数据展示（`hymns.js:2`），非输入解析。

### 已知缺陷 / 缺口
- 输入侧不接受 `附1` 作为编号模式（对比数据键 `诗歌附1`）。
- 展示正则若含 `其他格式`，`hymns.js` 中对应键检索为 0 — **未找到**数据键（此前全文件检索结论）。
- 前端搜索路径不再本地解析诗歌编号。

---

## 四、测试与样例

- `testBibleVerseStandardization` — 10 条 — `scripts.js:7245-7256`（front 亦有）。
- `testChapterStandardization` — 8 条 — `:5865-5891`。
- `testBookNameRecognition` — 9 条 — `:5895-5918`。
- 以上均为挂到 `window.*` 的**控制台手工函数**，不是 jest/mocha/pytest 自动化套件。
- `scripts/test_xinyue_search.js` — 约 5 个分类关键词探测 — **不是**出处格式矩阵。
- `test-search.mjs` — 1 次 API 冒烟 — 与写法无关。
- 成批真实用户输入日志 / 语料库：**未找到**。
- 数据侧大量真实出处字符串散布在 `jing_jie_wen_da.js`、经文 HTML 等，但不是「用户输入样例集」。

---

## 五、没找到的

- 独立研究/设计文档专述「经文出处写法」或「诗歌首数写法」。
- 用 LLM / 模型提示词解析出处或诗歌号。
- 英文圣经引用解析（如 `John 3:16`）。
- 经节标准化中的跨章范围（如 `太三1-四2`）。
- 诗歌输入：中文数字首数、`#N`、多首并列、首数范围、`附N` 编号输入。
- 自动化回归测试（带期望输入输出对）针对上述规则。
- 名为 `series` 的一等字段/表；系列仅为字符串前缀。
- 前端当前搜索路径上的本地诗歌编号解析。

---

## 六、可复用性（只写事实）

- 经节识别/转换：**正则 + 查表**（`BOOK_NAME_MAP`、`ARABIC_TO_CHINESE` 等），命中后查 `bible_verse.js`。
- 整章：**正则 + 变体表**；并可能触达 JSON 目录/索引文件（章节处理路径中有加载，【待核实】具体文件名与行）。
- 「重要经节出处」展开：**正则** + `window.bibleVerse`。
- TTS 扩写：**正则** + 函数内书名映射。
- 诗歌编号：**正则** + 拼出前缀 + `Object.keys(hymns).find(startsWith…)`（实现细节【待核实】精确 API），依赖 `hymns.js` 键。
- 诗歌目录：**同义词对象** + 直接键取值。
- Bot / `search_parse`：结果 HTML **正则**抽取，不做输入标准化。
- 无模型提示词依赖：**未找到**。

**规范化目标形态（数据事实）**
- 经节键：`创一1`（`bible_verse.js:2`）
- 整章测试目标形如 `创世记第一章`（测试输入侧，`:5869`）
- 诗歌键前缀：`诗歌第N首` / `补充本诗歌第N首` / `儿童诗歌第N首` / `诗歌附N`

---

## 附录：架构要点（事实）

- 用户搜索查询的解析发生在后端 `data/scripts.js`（经 `lib/bootstrap.js` + JSDOM）。
- 前端把 `query: rawUserMessage` 交给 API（`front_anshifenliang\scripts.js:955-962`）。
- 两边 `scripts.js` 大量重复；改规则时需同时意识到前后端副本是否仍同步【待核实当前是否字节级一致】。
