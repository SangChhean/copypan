# 探针 5c · 阶段 1b 冒烟（真实 API）

脚本：`qa4/backend/tools/smoke_models.py`  
结果目录：`--out-dir`（默认 `G:\PanAI4.0专用\logs`）

## Srey 运行步骤

```powershell
# 1) 安全注入密钥（不写文件、不进命令行参数）
$s = Read-Host "QA4_ANTHROPIC_API_KEY" -AsSecureString
$env:QA4_ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new("", $s).Password
Remove-Variable s

# 2) dry-run（不联网、不读密钥值）
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --dry-run

# 3) 分节真跑
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --yes --only haiku_json
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --yes --only sonnet_json
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --yes --only sonnet_between_tools
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --yes --only sonnet_adaptive
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --yes --only cache_ttl
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --yes --only sonnet_disabled_error
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --yes --only haiku_truncate
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\smoke_models.py --yes --only sonnet_stream

# 4) 泄漏检查：结果 json / 日志不得含密钥；仅 key_present
# 5) 清变量
Remove-Item Env:QA4_ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
```

当日预算（跨多次运行累计于 out-dir）：Haiku in 20000 / out 5000；Sonnet in 30000 / out 6000。

## 结果表（跑后回填；未跑前均为【待核实】）

| 节 | 期望 | 结果 |
|----|------|------|
| haiku_json | complete_json 通过；model 一致；thinking_blocks=0 | 【待核实】 |
| sonnet_json | 记录 thinking 块数与 output_tokens | 【待核实】 |
| sonnet_between_tools | 是否接受 | 【待核实】 |
| sonnet_adaptive low/medium | 是否接受；out_tok/文本长之比 | 【待核实】 |
| cache_ttl 1h | create 有 1h 创建迹象；第二次 read>0 | 【待核实】 |
| cache_ttl 5m | 对照命中 | 【待核实】 |
| sonnet_disabled_error | 400 → LLMBadRequestError | 【待核实】 |
| haiku_truncate | LLMStopReasonError | 【待核实】 |
| sonnet_stream | 文本增量 + ttft_s + usage | 【待核实】 |

## 结论

【待核实】— 勿把推测写成已验证。
