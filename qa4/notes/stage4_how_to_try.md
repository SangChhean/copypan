# 本机试跑草稿提示词（PowerShell 5.1）

## 环境
- Python：`G:\copypan\qa4\backend\.venv\Scripts\python.exe`
- 草稿通道：`$env:QA4_PROMPT_CHANNEL = "draft"`
- 假模型：`$env:QA4_LLM_MODE = "fake"`（默认试跑）

## env 文件（`QA4_ENV_FILE`）
- 本机文件：`qa4\backend\.env`（已被 `qa4/.gitignore` 忽略；**禁止提交**）。模板：`qa4\backend\.env.example`。
- `prompt_trial` **不会**默认加载 `.env`。需要时显式设置：
  ```powershell
  $env:QA4_ENV_FILE = "G:\copypan\qa4\backend\.env"
  ```
  加载逻辑复用 `config.settings._load_env_file`（已存在的进程环境变量不被覆盖）。
- 约定：尚不知的机密值写字面量 `__FILL_ME__`。`--retrieval real` / `--live` 若仍看到 `__FILL_ME__`，只报「尚未填写」及**变量名**后拒绝启动（不打印值）。
- 把 `__FILL_ME__` 换成真实口令/密钥时，只在本机改 `.env` 或会话环境；勿写入笔记、聊天、git。

## 检查提示词
```powershell
$env:PYTHONPATH = "G:\copypan\qa4\backend"
& G:\copypan\qa4\backend\.venv\Scripts\python.exe G:\copypan\qa4\backend\tools\check_prompts.py --channel draft
```

## dry-run 题集
```powershell
& G:\copypan\qa4\backend\.venv\Scripts\python.exe G:\copypan\qa4\backend\tools\prompt_trial.py --max-questions 20 --out "G:\PanAI4.0专用\logs\prompt_trial"
```

## 检索模式 `--retrieval {fake,real}`（默认 fake）
- `fake`：夹具检索；与 `--live` 合用时会警告「第 7、8 步结果不能用于评价回答」。
- `real`：与问答服务相同的真实 ES / 嵌入 / 重排（复用 `main`→`build_deps`）；可与 `--dry-run` 组合（假模型 + 真检索，不花模型钱）。
- `real` 启动前检查：`QA4_ES_URL` / `QA4_ES_PASSWORD` / `QA4_EMBED_*` / `QA4_RERANK_*` / `QA4_NEO4J_URI` / `QA4_NEO4J_PASSWORD`（缺项或 `__FILL_ME__` 即拒绝，只列变量名）。
```powershell
# 假模型 + 真检索（先验证检索通路；需已填好 env）
$env:QA4_ENV_FILE = "G:\copypan\qa4\backend\.env"
& G:\copypan\qa4\backend\.venv\Scripts\python.exe G:\copypan\qa4\backend\tools\prompt_trial.py --dry-run --retrieval real --only-ids D01 --max-questions 1 --out "G:\PanAI4.0专用\logs\prompt_trial"
```

## 小规模 live（需密钥；无人值守任务不会替你跑）
```powershell
$s = Read-Host "QA4_ANTHROPIC_API_KEY" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
$env:QA4_ANTHROPIC_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
$env:QA4_PROMPT_CHANNEL = "draft"
# 评价回答请用真检索：
& G:\copypan\qa4\backend\.venv\Scripts\python.exe G:\copypan\qa4\backend\tools\prompt_trial.py --live --retrieval real --only-ids D01 --max-questions 1 --budget-usd 0.5 --out "G:\PanAI4.0专用\logs\prompt_trial"
Remove-Item Env:QA4_ANTHROPIC_API_KEY
```

## 看结果
- 指标与日志在 `G:\PanAI4.0专用\logs\prompt_trial\`（仓库外）
- 契约说明：`qa4/notes/stage4_prompt_contracts.md`

## JSONL 字段（供 show_trial / 人工阅卷）
每题一行；除原有 `answer` / `plan` / `tokens` 等外，第 9A 批新增：

| 字段 | 含义 |
|------|------|
| `citations` | 实际送入第 8 步的段落列表。每项：`n`（正文 `[n]` 编号）、`index`、`source`（书名/`source_zh`）、`title`（篇名）、`author`、`year_or_volume`、`chunk_id`（Passage.id）、`text_head`（正文前 60 字）。取不到的子字段为 `null`。 |
| `cited_numbers_in_order` | 回答正文中 `[n]` 按**首次出现**顺序的编号列表（去重），与 `pipeline.citations.extract_refs` 一致。 |
| `step_timings_ms` | 各步耗时（`ctx.timings_ms`，键如 `step3`…）。另含 `first_token_ms`：流式首字时延（毫秒），取自跑完后 `deps.llm.last_stream_result.ttft_s`；无流式/无 ttft 则为 `null`。注意：编排器未对第 8 步 `timed()`，故通常**没有** `step8` 键。 |
| `rewrite_info` | `{history_turns_passed, rewrite_skipped, rewrite_called, step2_input_chars}`。无上文则 skipped；有上文则 called，并用与 step2 相同模板重算输入字符数（未改 pipeline）。 |

顶层仍保留 `rewrite_skipped` / `citations_count`（后者仍为答案书目条数，与 `citations` 段落列表不同）。

## 一键启停（本机后端 + 前端）

脚本（仅这两个新文件；不改 pipeline / 提示词）：

- `qa4\tools\restart_qa4.bat` — 停旧进程 → 检查 `.env` → 启本地容器 → 开后端/前端窗口 → 健康检查 → 打开浏览器  
- `qa4\tools\stop_qa4.bat` — 只停后端/前端，**不动** Docker

### 怎么运行
```powershell
# 默认：真实模型 + 真实检索 + draft 提示词通道
G:\copypan\qa4\tools\restart_qa4.bat

# 假模型 + 假检索（不花模型钱；仍会起容器/前后端）
G:\copypan\qa4\tools\restart_qa4.bat fake

# 真实 + stable 通道
G:\copypan\qa4\tools\restart_qa4.bat real stable

# 只停止
G:\copypan\qa4\tools\stop_qa4.bat
```

### 两个参数
| 位置 | 取值 | 默认 | 作用 |
|------|------|------|------|
| 1 | `real` / `fake` | `real` | 切换真/假：`QA4_LLM_MODE`、`QA4_RETRIEVAL_MODE`（取值 `live`/`fake`；bat 的 `real` 映射为 `live`），并同步 `QA4_FAKE_LLM`（`0`/`1`，settings 遗留字段） |
| 2 | `draft` / `stable` | `draft` | `QA4_PROMPT_CHANNEL` |

脚本固定 `QA4_ENV_FILE=G:\copypan\qa4\backend\.env`。若文件不存在或仍含 `__FILL_ME__`，只打印**变量名**后退出（不打印值）。

### 日志位置
`G:\PanAI4.0专用\logs\qa4_run\`

- `backend_<yyyyMMdd_HHmmss>.log`
- `frontend_<yyyyMMdd_HHmmss>.log`

后端默认 `http://127.0.0.1:8030`（`QA4_PORT`），健康检查用 `/healthz`；前端默认 `http://127.0.0.1:5174`（`VITE_DEV_PORT`，可在 `frontend\.env.development` 改）。

### 本地怎样得到能登录的测试账号

**机制（只读摘要）**  
- 用户在 SQLite：`{QA4_DATA_DIR}/qa4_users.db`（默认 `qa4/data/qa4_users.db`），见 `main.py` → `AuthStore(settings.data_dir / "qa4_users.db")`。  
- 注册必须邀请码：`POST /api/auth/register`（`api/auth_routes.py`）→ `AuthStore.register` 先 `use_invite` 再 `create_user`。  
- 建邀请码：`POST /api/admin/invites`（`api/admin_routes.py`），请求头 `X-Admin-Token`，变量名 **`QA4_ADMIN_TOKEN`**（未配置则 503）。  
- 登录：`POST /api/auth/login`；库里无用户或密码错 → **401**（首次空库属正常）。

**PowerShell 5.1（服务已用 `restart_qa4.bat` 拉起；令牌用 SecureString，不写进文件）**

```powershell
# 0) 端口（与 .env 中 QA4_PORT 一致；默认 8030）
$base = "http://127.0.0.1:8030"

# 1) 管理令牌：交互输入，不出现在命令行历史的明文参数里
$sec = Read-Host "QA4_ADMIN_TOKEN" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$admin = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

# 2) 创建邀请码（可改 code / max_uses）
$invite = "LOCAL01"
Invoke-RestMethod -Method Post -Uri "$base/api/admin/invites" `
  -Headers @{ "X-Admin-Token" = $admin } `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ code = $invite; note = "local"; max_uses = 10 } | ConvertTo-Json)
$admin = $null; $sec = $null

# 3) 注册测试用户（密码交互输入）
$user = "demo"
$psec = Read-Host "新用户密码" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($psec)
$pass = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
Invoke-RestMethod -Method Post -Uri "$base/api/auth/register" `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ invite_code = $invite; username = $user; password = $pass } | ConvertTo-Json)

# 4) 登录校验（应返回 token；勿把 token 贴进笔记）
Invoke-RestMethod -Method Post -Uri "$base/api/auth/login" `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ username = $user; password = $pass } | ConvertTo-Json) | Select-Object username
$pass = $null; $psec = $null
```

也可在前端登录页点「去注册」，填同一邀请码与账号密码。  
磁盘上只会多出用户库里的 **bcrypt 密码哈希** 与邀请码行；**不会**把 `QA4_ADMIN_TOKEN` / 明文密码写入日志或本笔记。

每日提问上限看 `QA4_DAILY_LIMIT_DEFAULT`（`real` 启动时脚本会打印该数字）。

### 本机免登录（`QA4_DEV_AUTOLOGIN`）
- **默认关闭**。不写进 `.env` / `.env.example`；仅 `restart_qa4.bat`（real/fake）在启动后端窗口时设 `QA4_DEV_AUTOLOGIN=1` 与 `QA4_BIND_HOST=127.0.0.1`（与 `uvicorn --host 127.0.0.1` 一致）。
- 生效条件（**须同时满足**，否则与原来相同 → 401）：
  1. 开关开启；
  2. 绑定 `127.0.0.1` / `::1`；
  3. 请求来自本机回环；
  4. **无** `X-Forwarded-For` / `X-Real-IP` / `Forwarded` 头（防经反向代理误放行）；
  5. `Host` 为 `localhost` / `127.0.0.1` / `[::1]`（可带端口）。
- 生效时：`POST /api/auth/login` 用户名固定 `dev`，密码任意非空；首次自动在本地用户库建户并返回正常 JWT。
- 若开关开启但绑定非回环（如 `0.0.0.0`）→ **拒绝启动**（`ConfigError`）。服务器环境绝不能有该变量（见 `stage7_server_checklist.md`）。
