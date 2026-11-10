# 一键复制出现两份书目 — 只读勘探

现象：复制结果里先有一份无「【引用书目】」标题、编号完整（1–13）的列表，再有一份「【引用书目】」标题下、按书名去重后编号断层的列表。页面展示通常不双份。与本次 Step1/Step4 提示词改动无直接关系（复制/解析逻辑更早）。

未改代码、未跑服务、未提交。

---

## 1. 后端：【引用书目】解析与 `sources`

### 解析位置

`_extract_step4_sources`：`back_qa/qa/qa_service.py:1053-1075`

- 用 `"【引用书目】"` 切开，取后半块逐行解析。`1056-1058`
- 兼容旧格式含 `➡️`，或行首数字。`1065-1070`
- **按书名去重**：`key = re.sub(r"^\d+[\.\s]+", "", after)`，`seen` 去重。`1071-1074`
- **保留原编号**：`sources.append(after)`，`after` 仍带原行首数字，**不去重后重排 1..n**。注释写明「保留编号；按书名去重」。`1054`, `1074`

### 谁调用、如何进响应

| 路径 | 行为 | 行号 |
|------|------|------|
| 非流式 `_step4` | `sources = _extract_step4_sources(raw)`，`answer = raw.strip()`（**全文含书目块**） | `1199-1200` |
| 流式 | `full_text` 累积后同样提取；`answer = full_text.strip()`（**全文含书目块**）；`done` 同时带 `answer` 与 `sources` | `1831-1839`, `1880-1883` |

返回字段名：`sources`（list[str]，元素形如 `"1 李常受文集……"`）。

结论：第二份「缺号」列表来自后端 **同名合并且保留首次出现的原编号**；不是重新编号。

---

## 2. 前端：正文 vs `sources` 渲染

### 答案正文

- 模板：`v-html="renderAnswer(displayAnswer(msg))"` — `front_qa/src/components/QAPage.vue:112-117`
- `displayAnswer`：按语言取 `msg.answer` / 译文 — `847-852`
- `renderAnswer`：**展示前去掉** `【引用书目】` 及之后、以及 `[References]` 及之后 — `821-829`，再 `marked.parse`

→ 页面上**不应**再显示模型写在正文末尾的「【引用书目】」块（被 `renderAnswer` 裁掉）。

### 书目列表（第二套 UI）

- `displaySources(msg)` → `msg.sources`（或译文 sources）— `854-860`
- 单独区块 `.qa-sources`，标题为「引用书目」/「引用書目」/ `References`（**无【】**）— `119-132`

流式时：遇到含 `【引用书目】` 的 token 后截断打字机，`_bodyDone` 后不再追加书目 token — `1371-1372`, `1584-1605`；`done` 时若已有 `answer` **不覆盖**为完整 `chunk.answer` — `1624-1627`，`sources` 仍写入 `chunk.sources` — `1627`。

说明：页面设计是「正文（无书目块）+ 下方 sources」。若打字机因 token 切分未识别到完整 `【引用书目】`，书目行可能进入 `msg.answer`；此时 `renderAnswer` 仍可能裁掉带标记的块，但若标记被拆开/洗掉，行为需实测 — **未确认**每种线上路径 `msg.answer` 是否始终不含书目行。

---

## 3. 「一键复制」拼什么？

`copyAnswer`：`QAPage.vue:1736-1747`

```text
fullText = stripAnswerPlain(displayAnswer(msg))  +  "\n\n" + 【引用书目】/References + "\n" + sources.join("\n")
```

即：**清洗后的答案正文** + **再拼一份 sources 书目**。

`stripAnswerPlain`：`692-709`

- 有 `参考书目…`、`References…`、`書目…` 等，**没有**对简体 **`引用书目` / `【引用书目】` 整块删到文末** 的可靠处理。
- `.replace(/【[^】]*】/g, '')`（`707`）只会删掉「【引用书目】」**这几个字**，**留下后面的 `1 书名…` 编号行**。
- `/m` 下 `$` 多为行尾，不能保证删掉整段书目块。

因此当 `msg.answer` 里仍带模型书目行时：

1. 第一份：正文末尾编号列表（标题被剥掉，1–13 仍在）  
2. 第二份：`sources` 去重后带 `【引用书目】`（缺号）

**是的：正文残留书目 + sources 都被拼进剪贴板。** 与提示词改动无关；复制逻辑自 2026-04/05 起即如此结构。

---

## 4. git 历史与 dist

### 前端复制 / 展示

```text
git log -3 --format="%h %ad %s" --date=short -- front_qa/src/components/QAPage.vue
e2357eed 2026-09-24 QA登录过期返回登录页
0a7d37e1 2026-07-04 feat(qa): 自动语言检测…
eaf0b863 2026-06-09 回答质量与格式改进…
```

与书目复制更相关的提交（`git blame` / `-S`）：

| 提交 | 日期 | 内容 |
|------|------|------|
| `65bbb0f6` | 2026-04-24 | 引入 `copyAnswer`（`cleanAnswer + sourcesText`） |
| `88d682a8` | 2026-04-30 | `displayAnswer`/`displaySources`；复制改用二者；`sourcesHeader` |
| `cdd30b6b` | 2026-05-03 | 引入 `stripAnswerPlain`（当前清洗逻辑，**未正确剥简体引用书目块**） |

`git blame`：`stripAnswerPlain` 全体 `cdd30b6b`；`copyAnswer` 拼装核心 `65bbb0f6`/`88d682a8`/`cdd30b6b`。

### 后端书目提取

```text
git log -3 --format="%h %ad %s" --date=short -- back_qa/qa/qa_service.py
a6ccc20f 2026-06-12 refactor: parameterize redis key prefixes…
eaf0b863 2026-06-09 回答质量与格式改进…
0bea3056 2026-05-06 QA经节问答
```

| 提交 | 日期 | 内容 |
|------|------|------|
| `52dc4be2` | 2026-04-23 | 引入 `_extract_step4_sources` |
| `64094e75` | 2026-04-24 | 「保留编号；按书名去重」及数字行解析（当前去重逻辑） |

片段要点（`64094e75` / 现状）：去重 key 去掉行首数字，`append(after)` 保留原编号 → 缺 6、7、8、12 的形态由此而来。

### 本机 `front_qa` vs 线上

- 部署用构建产物：`/opt/pansearch/code/front_qa/dist`（`back_qa/DEPLOY.md:9`, `64-72`, `124`）。
- 本机存在 `front_qa/dist/`，近期资源时间戳约 **2026/9/24 18:34**（与 `e2357eed` 同日量级）。
- **线上 dist 是否等于本机 dist / 是否已含当前 `src`：未确认**（需服务器看文件日期或构建记录）。开发用 `npm run dev` 走 `src`，生产走 `dist`，二者可能不一致。

---

## 5. 最小改法方案（只谈方案，不改）

目标：整份回答里书目只出现一次，且与正文引用编号一致。

### 方案 A — 只改前端复制清洗（最小、专治双份）

**文件：** `front_qa/src/components/QAPage.vue`  
**位置：** `stripAnswerPlain`（约 692–709）或 `copyAnswer`（约 1739–1746）

- 在拼 `sources` **之前**，用与 `renderAnswer` 相同方式切掉 `【引用书目】` / `[References]` 及之后（`split` 取 `[0]`），再拼 `sources`。
- 效果：剪贴板只剩一份（sources）。  
- 编号：仍可能是去重后的缺号；与正文 1–13 **仍可能不一致**。

### 方案 B — 前端最终答案规范化

**文件：** `QAPage.vue` 流式 `done` 处理（约 1624–1627）

- `done` 时把 `row.answer` 设为「去掉书目块后的正文」（来自 `chunk.answer` 或现有 answer 再 strip），避免书目行留在 `msg.answer`。
- 复制仍只依赖 `sources`（可叠加方案 A）。  
- 编号一致性仍取决于后端是否去重。

### 方案 C — 后端返回的 `answer` 不含书目块

**文件：** `back_qa/qa/qa_service.py`（非流式约 1199–1200；流式约 1838–1839 / `done` 载荷）

- 返回前：`answer = full_text.split("【引用书目】",1)[0].strip()`，书目只放在 `sources`。
- 前端展示/复制天然单源。  
- 缺号问题仍在，除非同时改提取逻辑。

### 方案 D — 去重策略与编号一致（治「缺号」）

**文件：** `qa_service.py` `_extract_step4_sources`（1053–1075）

- **D1**：不去重，保留模型 1–13 原行 → 与正文编号一致，但 UI 可能出现同名多行。  
- **D2**：去重后 **重排为 1..n**，并同步改写正文里的引用上标（改动面大，不「最小」）。  
- **D3**：去重但展示时去掉行首数字、改用列表序；正文编号与列表序需另约定。

### 建议组合（仍仅方案）

- **只修复制双份：** A（必做）± B。  
- **还要编号与正文一致：** 在 A/B/C 之上加 **D1**（最简单）或接受缺号。  
- 改完前端需 **重新 `npm run build` 并部署 dist**，否则线上仍用旧产物。

---

## 验证备注

- 本文件：`qa4/notes/qa_bibliography_probe.md`（新建）。  
- 工作区已跟踪改动应仍仅为：`back_qa/qa/prompts.py`、`back_shared/version_manifest.py`（本笔记为未跟踪）。  
- `git diff --stat` 不应因本笔记增加已跟踪文件变更。
