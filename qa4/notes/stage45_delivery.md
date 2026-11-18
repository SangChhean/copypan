# Stage 4/5 交付说明

## 做了什么
- P0：基线 Ran 292；file_manifest；快照 zip + SHA256；PROGRESS
- P1：草稿通道 `QA4_PROMPT_CHANNEL`；registry v0.1；check_prompts；contracts
- P2：step3_v0.1 完整草稿 + 对抗 fixtures/测试
- P3：step2/4/5/7/8 的 v0.1 草稿；pipeline 渲染变量最小配合；verify_stage3 场景 15–18
- P4：dev_questions_draft.csv（60 条）；prompt_trial.py（dry-run 60/60）
- P5：stage4_prompt_report.md、stage4_how_to_try.md
- P6–P7：qa4/frontend（qa4-frontend）；stream 状态机 + vitest；Qa4Page；dev_server_fake.py；npm build 通过
- P8：单测 303 OK；verify2/3 ALL PASS；诗歌 146/146；经文 306/306；manifest diff PROTECTED_CHANGED=0

## 没做什么
- 真实模型 live 试跑（工具拒绝无人值守调用；Srey 本机按 how_to_try）
- Playwright e2e（记录缺口）
- 第5步小结/关键经节；归纳视觉终稿
- 翻译/朗读/语音（阶段6）

## 与设计不一致 / 取舍
- 依据技术版/构建方案原件本机缺失 → 按指令要点（OQ-DOC-1）
- 定向摘要复用 step8（最小改动）
- 前端未沿用 front_qa 大页，改用 Qa4Page 对接 qa4 事件

## 给 Srey 的验证清单（PowerShell 5.1）
```powershell
$py = "G:\copypan\qa4\backend\.venv\Scripts\python.exe"
$env:PYTHONPATH = "G:\copypan\qa4\backend"
# vendor 哈希（若有既有脚本可再跑）
Get-FileHash "G:\PanAI4.0专用\backup\qa4_snapshot_20261117.zip" -Algorithm SHA256
cd G:\copypan
& $py -m unittest discover -s qa4/backend/tests -q
& $py qa4/backend/tools/verify_stage2.py
& $py qa4/backend/tools/verify_stage3.py
& $py qa4/backend/tools/file_manifest.py --out "G:\PanAI4.0专用\logs\stage45\manifest_check.csv" --compare "G:\PanAI4.0专用\logs\stage45\manifest_before.csv"
& $py qa4/backend/tools/check_prompts.py --channel draft
& $py qa4/backend/tools/dev_server_fake.py
# 另开窗口：
cd G:\copypan\qa4\frontend; npm run build
```
