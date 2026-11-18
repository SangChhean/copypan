# 探针 5b · 模型疑点补查

脚本：`qa4/notes/probe5/probe5_check_models_b.py`  
SDK：`anthropic==2.8.0`（`qa4/backend/.venv`）  
结果/日志：`--out-dir`（默认 `G:\PanAI4.0专用\logs`）

## SDK 参数口径（已读本机 2.8.0 签名）

`messages.create` / `messages.stream` **顶层**参数包含：

| 参数 | 说明 |
|------|------|
| `thinking` | `disabled` / `enabled`(+budget_tokens) / `adaptive` |
| `output_config` | 含 `effort`: low\|medium\|high\|xhigh\|max（与 adaptive 搭配） |
| `cache_control` | 也可作请求顶层；本探针放在 **system text block** 上；`ttl`: `5m`\|`1h` |

**不必**为上述字段走 `extra_body`。

## Srey 运行步骤

```powershell
# 0) 用 SecureString 注入密钥到当前会话（不写文件、不进历史命令行参数）
$s = Read-Host "CLAUDE_API_KEY" -AsSecureString
$env:CLAUDE_API_KEY = [System.Net.NetworkCredential]::new("", $s).Password
Remove-Variable s

# 1) dry-run：看计划调用数与预算占用（不联网、不读密钥值）
qa4\backend\.venv\Scripts\python.exe qa4\notes\probe5\probe5_check_models_b.py --dry-run

# 2) 先小跑 identity
qa4\backend\.venv\Scripts\python.exe qa4\notes\probe5\probe5_check_models_b.py --yes --only identity

# 3) 其余分节
qa4\backend\.venv\Scripts\python.exe qa4\notes\probe5\probe5_check_models_b.py --yes --only e9
qa4\backend\.venv\Scripts\python.exe qa4\notes\probe5\probe5_check_models_b.py --yes --only json
qa4\backend\.venv\Scripts\python.exe qa4\notes\probe5\probe5_check_models_b.py --yes --only cache
qa4\backend\.venv\Scripts\python.exe qa4\notes\probe5\probe5_check_models_b.py --yes --only speed

# 或一次跑完全部（注意预算）
qa4\backend\.venv\Scripts\python.exe qa4\notes\probe5\probe5_check_models_b.py --yes

# 4) 结果与密钥泄漏检查
# - 打开 --out-dir 下最新 probe5b_*.json / *.log
# - Select-String 搜密钥片段；确认报告/日志仅有 key_present: true/false
Remove-Item Env:CLAUDE_API_KEY -ErrorAction SilentlyContinue
```

预算闸门：Haiku 输入 200000 / 输出 40000；Sonnet 输入 80000 / 输出 15000。超限标「预算已用尽」并停该模型后续调用。

## 结果汇总（跑完后由 Srey/脚本 json 填入）

### A. identity

| 模型 | 次 | 流式 | 响应 model | 与请求一致? | 回答摘要 |
|------|----|------|------------|-------------|----------|
| haiku-5-5 | 1–3 | 第3次 | 【待核实】 | 【待核实】 | 【待核实】 |
| sonnet-5-5 | 1–3 | 第3次 | 【待核实】 | 【待核实】 | 【待核实】 |

### B. e9（仅 Haiku，max_tokens=2000，各设置×3）

| 设置 | 成功次数 | max_tokens 吃光 | thinking 块 | 完整答案 | 耗时中位 |
|------|----------|-----------------|-------------|---------|----------|
| 不传 thinking | 【待核实】 | 【待核实】 | 【待核实】 | 【待核实】 | 【待核实】 |
| disabled | 【待核实】 | 【待核实】 | 【待核实】 | 【待核实】 | 【待核实】 |
| adaptive+low | 【待核实】 | 【待核实】 | 【待核实】 | 【待核实】 | 【待核实】 |
| adaptive+medium | 【待核实】 | 【待核实】 | 【待核实】 | 【待核实】 | 【待核实】 |
| adaptive+high | 【待核实】 | 【待核实】 | 【待核实】 | 【待核实】 | 【待核实】 |

### C. json（~6000 input，max_tokens=2000）

| 模型/设置 | n | 解析成功 | 评分通过 | stop_reason | out tok min/med/max | 耗时 min/med/max |
|-----------|---|----------|----------|-------------|---------------------|------------------|
| Haiku none/disabled/low/high ×4 | 【待核实】 | | | | | |
| Sonnet none/disabled ×2 | 【待核实】 | | | | | |

### D. cache

| 模型 | 600 | 1200 | 2400 | 4800 | 最小可缓存落在 | 1h ttl 接受? | 第二次命中? |
|------|-----|------|------|------|----------------|--------------|-------------|
| Haiku | 【待核实】 | | | | 【待核实】 | 【待核实】 | 【待核实】 |
| Sonnet | 【待核实】 | | | | 【待核实】 | 【待核实】 | 【待核实】 |

### E. speed（流式，max_tokens=4000，无 thinking）

| 模型 | 次 | ttft_s | 总耗时 | out tokens | tok/s |
|------|----|--------|--------|------------|-------|
| Sonnet | 2 | 【待核实】 | | | |
| Haiku | 1 | 【待核实】 | | | |

Sonnet 估 3000 out token 耗时：【待核实】

## 结论与建议

1. **Haiku 在固定 JSON 步骤（第 2、3、4、7 步）的 thinking / max_tokens**  
   【待核实】— 依据 C 节：优先选「解析成功+评分通过」高、且少被 `max_tokens` 吃光的设置；`max_tokens` 建议从本探针的 2000 起步，若 thinking 吃光再加大。

2. **响应 `model` 是否始终与请求一致；「通义千问」自称**  
   【待核实】— 看 A 节：若 `response_model` 始终等于请求且回答自称 Claude/Anthropic，则上次「通义千问」更可能是旧路由/其它端点；若 `model_mismatch` 或自称其它厂商，需在 1b 封装里记录并告警。

3. **最小可缓存长度、1h ttl 写法**  
   【待核实】— D 节 `min_cacheable_between_chars`；`ttl=1h` 为顶层/块内 `cache_control` 字段，若被拒则看错误体与 beta 头重试结果。

4. **Sonnet 输出速度与 3000 token 耗时**  
   【待核实】— E 节 `sonnet_est_seconds_for_3000_out`。

5. **未能确认的事项**  
   - 【待核实】正式跑数后的全部表项  
   - 【待核实】`cache_creation` 明细是否显式标注 1h  
   - 【待核实】OpenRouter / 其它网关是否与直连官方行为一致（本探针仅直连官方 SDK）

## 交付自检（不连网）

```text
qa4\backend\.venv\Scripts\python.exe qa4\notes\probe5\probe5_check_models_b.py --dry-run
# 应打印各节计划调用数与预算占用；key_present 为 null（未读密钥值）
```
