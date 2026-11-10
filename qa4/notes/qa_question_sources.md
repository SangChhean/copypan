# back_qa（3.0）用户提问保存位置 — 只读勘探

目的：便于之后在服务器上只读统计提问数量。未改其他文件、未跑服务。

---

## 1. Redis 监控记录（最近 5000 条）

| 项 | 结论 |
|----|------|
| Key 名 | 默认 `qa:monitor:records`；可用环境变量 `QA_MONITOR_KEY` 覆盖 |
| 类型 | Redis **list**（`lpush` + `ltrim`） |
| 写入函数 | `_write_monitor` |

代码：

- Key / 上限：`back_qa/qa/qa_service.py:272-273`
- 写入实现（自动补 `ts`）：`back_qa/qa/qa_service.py:276-285`
- 管理端读取：`back_qa/qa/qa_router.py:602-613`（`r.lrange(_MONITOR_KEY, 0, -1)`）
- 清空：`back_qa/qa/qa_router.py:590-599`

### 每条记录字段

`_write_monitor` **统一追加** `ts`（UTC ISO 字符串）。其余字段由调用方传入，**不完全相同**：

| 场景 | 字段 | 文件:行号 |
|------|------|-----------|
| 缓存命中 | `request_id`, `question`, `cache_hit=True`, `found` | `qa_service.py:1231-1236` |
| Step3 未通过 | `request_id`, `question`, `cache_hit=False`, `found=False`, `step_fail_stage="step3"`, `total_elapsed_ms`, `total_cost_usd` | `qa_service.py:1349-1357` |
| 正常完成（非流式） | `request_id`, `question`, `cache_hit=False`, `found=True`, `total_elapsed_ms`, `total_cost_usd` | `qa_service.py:1566-1573` |
| 正常完成（流式） | 同上（`question` 取自 `q`） | `qa_service.py:1871-1878` |

**字段并集（含 `ts`）**：`request_id`, `question`, `cache_hit`, `found`, `ts`；可选 `step_fail_stage`, `total_elapsed_ms`, `total_cost_usd`。

**统计用途**：监控 list 中的 `question` 是服务器上统计「用户提问」最完整、最直接的持久化来源之一（最多保留最近 5000 条）。

---

## 2. 答案缓存的 key 前缀与内容

| 项 | 结论 |
|----|------|
| Key 前缀 | 默认 `qa:cache:`；环境变量 `QA_REDIS_PREFIX` |
| Key 形态 | `{prefix}{sha256(question|history|PROMPT_VERSION|MODEL_PROFILE|FIREWALL_RULES_VERSION)}` |
| 是否保存原始问题 | **否**：value 的 JSON **不含** `question` 字段；问题只参与 key 哈希 |

代码：

- `_make_cache_key`：`back_qa/qa/qa_service.py:235-243`
- `_write_cache`（`setex` + TTL，默认 `QA_CACHE_TTL=259200`）：`258-266`
- 写入的 `result` 示例字段：`request_id`, `answer`, `sources`, `concepts`, `found`, `cache_hit`, `total_elapsed_ms`, `total_cost_usd`, `passages`（无 `question`）：`1533-1543`, `1846-1856`
- 清理接口也使用同一前缀：`qa_router.py:573-587`
- 另有语言后缀缓存 `{cache_key}:zh_tw` / `{cache_key}:en`：`qa_service.py:1603-1634`（内容为译文，仍无原始问题）

说明：`debug=True` 时不写答案缓存（`if not debug: _write_cache(...)`：`1564-1565`, `1869-1870`）。

---

## 3. SQLite 反馈表

| 项 | 结论 |
|----|------|
| 默认路径 | `back_qa/qa/qa_users.db`（相对 `auth.py` 所在目录：`Path(__file__).resolve().parent / "qa_users.db"`） |
| 环境变量名 | **代码中未见**用于覆盖 DB 路径的环境变量（仅见 `QA_JWT_SECRET` 等鉴权相关）。部署是否另拷路径：**未确认**（`DEPLOY.md` 未写明 `qa_users.db` 路径）。 |
| 表名 | `feedback` |
| 字段 | `id`, `request_id`, `username`, `question`, `answer`, `rating`, `created_at` |

代码：

- `DB_PATH`：`back_qa/qa/auth.py:15`
- `CREATE TABLE feedback`：`auth.py:64-75`
- 写入 `insert_feedback`：`auth.py:280-291`
- HTTP：`POST /feedback` → `qa_router.py:535-551`
- 管理端读差评（含 `question`）：`get_feedback_stats` `auth.py:294-311`；路由 `qa_router.py:644-649`

注意：仅用户提交反馈时才写入；**不是**全量提问日志。

---

## 4. 进程日志 `qa_backend.log`

| 项 | 结论 |
|----|------|
| 日志文件（部署约定） | `/opt/pansearch/logs/qa_backend.log`（systemd 把 stdout/stderr append 到此文件） |
| 是否常规写入用户原始问题 | **否**（`qa_service` 主路径日志无完整 `question=`） |
| 例外：会打出问题文本的语句 | 见下 |

部署：`back_qa/DEPLOY.md:8`, `167-168`  
日志初始化：`back_qa/main.py:8`（`logging.basicConfig`，消息进 stdout → 上述文件）

会写入问题相关文本的日志：

1. **提示注入拦截**（截断前 100 字）：  
   `logger.warning("[QA] 疑似提示注入，已拦截: pattern=%r question=%r", pattern, question[:100])`  
   `back_qa/qa/rate_limit.py:95`  
   → 仅疑似注入时出现，不是全量提问。

2. **ASR 语音转写**（若用户语音提问）：  
   `logging.info(f"[ASR] [{asr_model}] 原文：{raw_text}")`  
   `back_qa/qa/asr_service.py:129`  
   → 记的是转写原文，不是 HTTP 字段名 `question`；是否算「用户提问」取决于产品定义。

主问答流水线常见日志（如缓存命中、Step1/2/3）**不**打印原始问题字符串：`qa_service.py` 内 `logger.info/warning` 检索未见常规 `question=` 全量输出。

---

## 5. `eval_set_v3.json`

| 项 | 结论 |
|----|------|
| 仓库路径 | `scripts/eval_set_v3.json` |
| 顶层结构 | **JSON 数组**（`list`），元素为对象 |
| 题目总数 | **120** |
| 题型/来源分类 | 有 **`query_type`**（题型）；**无** `source` / `category` 字段 |

每题字段并集：

`query_id`, `query`, `query_type`, `expected_answer_state`, `gold_chunks`, `gold_answer_summary`, `forbidden_concepts`, `notes`

`query_type` 计数（只读解析）：

| query_type | 数量 |
|------------|------|
| 教义解释 | 62 |
| 概念澄清 | 26 |
| 经节对比 | 26 |
| 实践应用 | 5 |
| 实际应用 | 1 |

说明：这是评估集，**不是**线上用户提问落库。

---

## 6. 其他可能记录提问的地方

| 来源 | 是否持久化原始问题 | 说明 | 文件:行号 |
|------|-------------------|------|-----------|
| 管理后台 `GET /api/qa/stats` | 间接（读 Redis monitor） | 汇总统计；`step_fail_records` 返回最近最多 20 条未找到记录（含 `question`） | `qa_router.py:602-641` |
| 管理后台 `GET /api/qa/feedback/stats` | 间接（读 SQLite feedback） | 赞/踩统计 + 最近 20 条差评含 `question` | `qa_router.py:644-649`, `auth.py:303-311` |
| 前端 Admin 页 | 不落库 | 展示上述接口返回的 `rec.question` | `front_qa/src/components/AdminPage.vue:67`, `103`, `263`, `398` |
| 前端 Debug 面板 | **不持久化** | 本机 UI 调试提问；token 用 localStorage，问题本身未见写入 localStorage | `front_qa/src/components/DebugPanel.vue`（提问区约 40+ 行） |
| 前端 QA 会话 `history` | **仅内存** | `history` 最多保留最近 3 轮，随请求发给后端；localStorage 只存 token/username | `QAPage.vue:723`, `1701-1705`, `721`；`LoginPage.vue:70-71` |
| `users.daily_count` | **不存问题文本** | 仅日请求计数 | `auth.py:97-120` |
| 答案 Redis 缓存 | **不存问题文本** | 见第 2 节 | — |
| 专门「导出全部提问」接口 | **未见** | 无 csv/json dump 类 export；仅有 cache/stats clear 与 stats 查看 | `qa_router.py:573-649` |

---

## 服务器只读统计建议（非实现，仅指向）

优先顺序（按「是否保存原始问题 + 覆盖面」）：

1. **Redis list** `qa:monitor:records`（或 `QA_MONITOR_KEY`）→ 最近最多 5000 条全量提问字段  
2. **SQLite** `back_qa/qa/qa_users.db` 表 `feedback.question` → 仅有反馈的子集  
3. **`qa_backend.log`** → 不全；最多偶发截断/ASR  
4. **`scripts/eval_set_v3.json`** → 评估题，非线上用户  

---

## 验证备注

本文件路径：`qa4/notes/qa_question_sources.md`。  
预期：`git diff --stat` 为空；`git status --short` 在既有未跟踪文件之外，新增多本笔记文件。
