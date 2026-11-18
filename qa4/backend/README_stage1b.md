# qa4 阶段 1b · 模型封装

Anthropic 异步封装、假模型、策略文件与冒烟脚本。不含提示词、九步流水线、前端。

## 依赖

```bash
qa4\backend\.venv\Scripts\python.exe -m pip install -r qa4/backend/requirements.txt
# anthropic>=2.8.0,<3
```

## 配置（QA4_ 前缀）

| 变量 | 说明 |
|------|------|
| `QA4_ANTHROPIC_API_KEY` | API 密钥（优先；否则回退 `CLAUDE_API_KEY`） |
| `QA4_ANTHROPIC_BASE_URL` | 留空=官方 `https://api.anthropic.com`，显式传给 SDK |
| `QA4_MODEL_HAIKU` / `QA4_MODEL_SONNET` | 默认 `claude-haiku-5-5` / `claude-sonnet-5-5` |
| `QA4_LLM_MAX_CONCURRENCY_*` | Haiku 16 / Sonnet 6 |
| `QA4_LLM_TIMEOUT_*_S` | Haiku 30 / Sonnet 120 |
| `QA4_LLM_MAX_RETRIES` | 默认 2 |
| `QA4_LLM_STRICT_MODEL` | `1` 时响应 model 不一致抛错 |

策略：`config/llm_policy.json`（haiku 默认 `thinking.disabled`；sonnet 默认 `omit`）。

## 接口

- `core/llm_client.py`：`LLMClient.complete` / `complete_json` / `stream`
- `core/llm_fake.py`：`FakeLLM` 同接口，可注入错误

### 失败调用的用量与 meta

收到 API 响应后若校验失败（`LLMStopReasonError` / `LLMEmptyOutputError` / `LLMModelMismatchError`），异常带 `meta`（role、step、request/response model、id、stop_reason、usage 全字段、thinking_blocks、text_len、elapsed_s、attempts；**不含**用户输入、提示词或生成文本原文），并先写入 `usage_sink`（`ok=false`、`error_type`）。网络错误与 400/401/403/404 **不**记用量。

**流式**：抛错前可能已产出部分文本增量；一旦抛错，调用方必须把已收到的增量视为无效。

## 冒烟（花钱）

见 `qa4/notes/qa4_backend_build_probe_5c.md`。

```powershell
$env:QA4_ANTHROPIC_API_KEY = Read-Host "QA4_ANTHROPIC_API_KEY"
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --dry-run
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --yes --only haiku_json
Remove-Item Env:QA4_ANTHROPIC_API_KEY
```

## 测试

```bash
qa4\backend\.venv\Scripts\python.exe -m unittest discover -s qa4/backend/tests
```
