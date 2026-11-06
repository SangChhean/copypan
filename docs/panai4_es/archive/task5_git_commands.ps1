# 任务5：建议的 git 命令（只写入本文件，请你自行审阅后执行；本脚本不要被 agent 自动执行）
# 用法示例：在 G:\copypan 下逐段复制运行。

Set-Location G:\copypan

# --- 可选：先把临时文件加入 ignore（需你手动编辑 .gitignore）---
# *.bak
# docs/panai4_es/archive/_git_*.txt
# docs/panai4_es/archive/_task5_scan.py

# === 提交1：BOOK_TITLE_OVERRIDES ===
# git add -- back_mic/backend/panai4/outline/config.py
# git commit -m "chore(outline): 生命读经书名 BOOK_TITLE_OVERRIDES"

# === 提交2：修订脚本 ===
# git add -- `
#   back_mic/backend/panai4/outline/apply_life_fix.py `
#   back_mic/backend/panai4/outline/probe_12490_assets.py `
#   back_mic/backend/panai4/outline/probe_life_fixlist.py `
#   back_mic/backend/panai4/outline/probe_life_fixlist_v2.py `
#   back_mic/backend/panai4/outline/probe_life_fixlist_v3.py `
#   back_mic/backend/panai4/outline/probe_life_in_12490.py `
#   back_mic/backend/panai4/outline/probe_life_in_12490_r2.py `
#   back_mic/backend/panai4/outline/probe_life_outline.py `
#   back_mic/backend/panai4/outline/probe_life_outline2.py
# git commit -m "feat(outline): 生命读经修订 apply_life_fix 与探测脚本"

# === 提交3：ES 最终报告（精选）===
# git add -- `
#   docs/panai4_es/archive/life_12490_fix_final_v4.csv `
#   docs/panai4_es/archive/life_fix_stage01.md `
#   docs/panai4_es/archive/life_fix_stage2_summary.md `
#   docs/panai4_es/archive/life_fix_stage3_summary.md `
#   docs/panai4_es/archive/life_fix_stage3_precheck.md `
#   docs/panai4_es/archive/task2_book_overrides.md `
#   docs/panai4_es/archive/task5_git_plan.md `
#   docs/panai4_es/archive/task5_git_commands.ps1
# git commit -m "docs(es): 生命读经 12490 修订最终报告与清单"

# === 提交4：图谱 docs（确认后）===
# git add -- docs/panai4_graph/
# git commit -m "docs(graph): 更新词条映射与分类"

# === 旁系（确认或丢弃）===
# git add -- docs/3a_export.json
# git add -- docs/panai4_sc/null_terms.csv
# 或：git restore -- docs/3a_export.json docs/panai4_sc/null_terms.csv

# === 不要 add ===
# config.py.bak_20261106
# docs/panai4_es/archive/_git_*.txt
# docs/panai4_es/archive/_task5_scan.py
# logs/
# __pycache__/
