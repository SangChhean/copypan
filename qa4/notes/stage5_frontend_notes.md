# 阶段5 前端说明

## 目录
- `qa4/frontend/`：从 `front_qa` 复制后改造为 `qa4-frontend`（Vue3 + Vite5 + ant-design-vue）
- 核心新文件：`src/utils/streamState.js`（事件状态）、`src/utils/qa4Api.js`（相对路径 API）、`src/components/Qa4Page.vue`

## 开发
```powershell
cd G:\copypan\qa4\frontend
npm install
npm run dev
```
代理：`.env.development` 中 `VITE_BACKEND_URL` 默认 `http://127.0.0.1:8030`（与 `QA4_PORT` 一致，可改）。

## 假后端
```powershell
$env:PYTHONPATH = "G:\copypan\qa4\backend"
& G:\copypan\qa4\backend\.venv\Scripts\python.exe G:\copypan\qa4\backend\tools\dev_server_fake.py
```
邀请码 `DEVINVITE`；账号 `demo` / `pass1234`；管理令牌 `dev-admin-token`。  
假服注入诗歌/生命读经种子文档（`SeededFakeEs` + `_targeted_with_seeds`），便于看 direct 出处。

## 构建
`npm run build` → `dist/`

## 字段对照（与 orchestrator 事件）
- step / plan / token / direct / choose / done / error / heartbeat
- **done 正文字段名：`answer`**（引文核对后的最终文本，可含 `〔未核实〕`）；另有 `quote_checks`、`citations`、`not_found`、`request_id`、`premise_note` 等
- 前端 `streamState.doneAnswerText` 兼容 `answer_text` 别名，但假/真流水线实际发的是 `answer`
- plan：`main_type` / `complex` / `sensitive` / `subquestions` / `understanding`
- direct：`text` + `meta`（`book_title` / `ref` / `message_title` / `message_number` / `series` / `hymn_number` 等）→ 摘要行显示出处标题
- 正文 `[n]` → 上标；书目用 citations
- 历史只发最近 3 轮，回答截断 300 字
- **正文渲染**：`Qa4Page` **不**走 Markdown。仅对 `[n]`、`「」`、`〔归纳〕`、`〔未核实〕` 做简单 HTML 替换

### 第四轮复现结论（【错引】）
- 后端假模型流式 token **不含** `〔未核实〕`；`step08.finalize` 核对后写入 **`done.answer`**，且 `quote_checks[].ok=false`
- 原先前端只读 `answer_text`，忽略 `answer` → 页面看不到标记。已改为采用 `answer`

## 功能清单（对照阶段4/5 指令 P7）

| 项 | 状态 | 所在 |
|---|---|---|
| step 事件展示 | 已做 | `Qa4Page.vue`（stepHint）+ `streamState.applyEvent` |
| plan 事件（题型/理解） | 已做 | `Qa4Page.vue` plan / premise |
| plan 复杂子问题列表 | 已做 | 第四轮：`subq-list` + 进度 |
| plan 敏感标记 | 已做 | 第四轮：题型旁「敏感」 |
| token 流式正文 | 已做 | `streamState` tokens/text → `Qa4Page` html |
| direct 事件 | 已做 | `Qa4Page` directHtml；`<details>` 折叠多块 |
| direct 出处标题 | 已做 | 第四轮：`formatDirectTitle(meta)` |
| direct 目录 | 部分做 | 摘要为出处标题，仍无独立目录导航 |
| choose 事件与候选点击 | 已做 | `Qa4Page.pickChoose` + `chooseFollowupQuestion` |
| done 事件 | 已做 | doneMeta；正文用 `answer` |
| error 事件 | 已做 | `asst.error`；`invalidate_streamed` 清空正文 |
| citations 上标 | 已做 | `renderCitationsMarkdown` → `<sup class="cite">` |
| citations 书目列表 | 已做 | bibliography `<pre class="bib">` |
| 前提说明样式 | 已做 | `.premise`（plan.understanding） |
| 〔未核实〕标记 | 已做 | 第四轮：采用 `done.answer` 后渲染 `<mark>` |
| 诗歌回退说明 | 部分做 | doneMeta.lyrics_status；回退文案仍弱 |
| 历史 3 轮 | 已做 | `truncateHistory(…, 3)` + `historyPayload` |
| 登录 | 已做 | `LoginPage.vue` + `qa4Api.login` + 路由守卫 |
| 邀请码注册 | 已做 | `LoginPage` register + `qa4Api.register` |
| 每日次数提示 | 未做 | `usageText` 占位未赋值、未接 API |
| 👍/👎 | 已做 | `vote` → `sendFeedback` |
| 一键复制 | 已做 | `copyAnswer` |
| 手机适配 | 部分做 | bubble 窄屏占满；桌面 min/max 宽 |
| 加载状态 | 已做 | `m.loading` / 「进行中…」 |
| 出错状态 | 已做 | `.err` |
| 未找到提示 | 已做 | 第四轮：独立 `.not-found` 文案 |
| 降级提示 | 已做 | doneMeta.degraded |
| request_id | 已做 | 默认折叠在「详情」 |
| 管理后台 traces 列表与详情 | 已做 | `AdminPage.vue` |

计数（上表逐行）：已做 **25**；部分做 **3**；未做 **1**（共 29 行）。

## 六类问题页面元素清单（假后端第四轮实测）

| 问题 | 题型标签 | 子问题列表 | 〔未核实〕 | 书目条数 | 取对象块出处标题 |
|---|---|---|---|---|---|
| 什么是神的经纶？ | 定义 | 无（不复杂） | 无 | 2 | （无 direct） |
| 【拆】什么是神的爱？ | 默认 +「复杂」 | 有（3 条） | 无 | 2 | （无 direct） |
| 【敏感】怎样看宗派？ | 默认 +「敏感」 | 无 | 无 | 2 | （无 direct） |
| 【错引】什么是神的经纶？ | 定义 | 无 | **有** | 2 | （无 direct） |
| 约3:16 | 经文 | 无 | 无 | 0 | **约翰福音 约三16** |
| 诗歌第15首 | 诗歌 | 无 | 无 | 0 | **诗歌 第15首** |

## 已知缺口
- 未做 Playwright e2e（可后续补）
- 归纳/原话样式为朴素方案（OQ-P3-INDUCTION-STYLE）
- 旧 front_qa 大页 QAPage.vue 仍留在目录但路由已改用 Qa4Page
- 翻译/朗读/语音未做（阶段6）
- **每日次数提示未接线**（`Qa4Page.vue` 的 `usageText` 恒为空）— 查后端结论如下（只查不改）：
  - **有用户侧只读接口**：`GET /api/auth/me`（需登录 Bearer）  
    - 路由：`qa4/backend/api/auth_routes.py` 第 57–66 行  
    - 返回：`username`、`daily_limit`、以及 `usage` 对象  
    - `usage` 由 `AuthStore.get_usage` 生成（`qa4/backend/core/auth.py` 第 303–317 行）：`{ used, limit, day }`（`used`=当日已问次数，`limit`=日上限，`day`=日期串）  
    - 注意：顶层还有一份 `daily_limit`（与 `usage.limit` 同义），前端取 `data.usage.used` / `data.usage.limit`（或 `data.daily_limit`）即可。
  - **问答流/ask 的 done 事件不带次数字段**（`orchestrator._done_payload` 无 used/limit）；扣次在入口 `step01_entry.entry_checks` → `auth.check_and_increment_usage`（`pipeline/step01_entry.py` 第 16–20 行；实现 `auth.py` 第 275–301 行，返回 `{ allowed, used, limit }`），但该返回值**未写进 SSE/HTTP 响应体**，前端无法从单次问答事件里读剩余次数。
  - **管理端汇总**（非普通用户页）：`GET /api/admin/usage`（`api/admin_routes.py` 第 78–80 行）→ 全用户当日统计；另有 `POST /api/admin/users/{username}/limit` 改上限。
  - **旧页对照**：`qa4/frontend/src/components/QAPage.vue` 仍调旧路径 `/api/qa/auth/usage`（约 781–788 行），与 qa4 现行 `/api/auth/me` **路径不一致**，不可直接照搬。
  - **`usageText` 应接在哪里**（接线指引，尚未改代码）：
    1. `qa4Api.js` 增 `fetchMe()` → `GET /api/auth/me`，解析 `usage.used` / `usage.limit`。
    2. `Qa4Page.vue`：在 `onMounted`（或登录进入页时）调用一次，设 `usageText = \`今日 ${used}/${limit}\``（或「剩余 limit−used」）；header 已有 `<span class="usage" v-if="usageText">`（约第 5 行）。
    3. 每次 `streamAsk` **成功结束**（收到 `done`）后再拉一次 `/api/auth/me` 刷新（因扣次发生在请求入口，本地 +1 也可，但以接口为准更稳）；429 时应提示已达上限。
- **direct 无独立目录**；诗歌回退文案仍弱
- **手机适配仅基础宽度**
