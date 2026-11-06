# 索引事项 1–5 汇总

> 2026-11-06 完成；顺序 2 → 5 → 1〔T0→「写」→T1–T4〕→ 4。任务 3：不改。

(任务 2) overrides **已加**；52 块 book_title/text 与 new 一致（仅 book_path 差 52）；feasts **same=11110 diff=0**。`task2_book_overrides.md`
(任务 5) 组 A–G；建议提交 C→D(+config)→E 精选；**未执行 git 写**。`task5_git_plan.md` / `task5_git_commands.ps1`
(任务 1) 受影响 **5054/268**；重算 **5054**；$0.0101；auto=5054 needs_review=0。本机 R1=39463/0；R2 mism=0；R4 knn 10/10；R5 507/1248/987/1072、旧写法=0；R7 both=1984 only_12490=17。服务器写 5054；S2 same=39463；其他 panai4_* count 不变。回滚脚本已写未跑。
(任务 4) 九索引已整理至 `G:\PanAI4.0专用\索引数据\`（约 **11.3 GB**）。D2：8 个有 chunk 的索引 missing/extra/text/vec 抽样 **全 0**；bible 缺 sqlite/outline；pano 无向量属预期。纲目JSON **41/4,733,504,505** 前后不变。`task4_index_organize.md`；被取代分类见 `索引数据\README.md`。
(任务 3) **不改**——text_life↔12490 篇题副题/异体字差异；配对靠书名+篇号。

## 最终验证

- 备份目录原文件未改；纲目JSON 41 / 4,733,504,505；12490原文JSONL 298 文件 / 8,297,200,099 字节前后一致。
- ES 仅覆盖写本机+服务器 `panai4_text_life` 的 5054 个 `_id`；count 仍 39463。
- panai4/：改 `outline/config.py`；新增 `inherit/apply_text_life_fix.py`、rollback×2、`organize_index_data.py`；kg_rag/ 未改。
- 密钥泄露检查：**通过**。
