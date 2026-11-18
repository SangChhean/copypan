# 格式探测总结 2026-11-17

## 任务一：经文格式测试集

- 输出目录：`G:\PanAI4.0专用\logs\formats` → `scripture_format_results.csv` / `.md`
- 卷名映射来源：qa4/backend/scripture/vendor_get_vers_v21.py::BOOK_MAP（反推最长全称）
- 合计：{'一致': 171, '待定': 45}
- 不一致 id：（无）
- 报错 id：（无）

## 任务二：别名对照

- 别名条数：175；状态计数：{'一致': 175}
- AMBIGUOUS_BARE_BOOK_NAMES 条数：22
- 不一致别名：（无）
- qa4 不识别别名条数：0

## 任务三：诗歌现状

- 文本级诗歌首数识别器：**未找到**
- 中文数字工具：`vendor_get_vers_v21.cn2num`；另有 `gen_lookups._cn_num_to_int`
- 本地 hymns 源：None
- H 组中文数字实测条数：None

## 未完成 / 受限

- 未改 normalize/vendor；不支持的写法只如实记实际结果。
- 未跑 ES；诗歌 series 统计来自本地 jsonl。
- 未新增单元测试。

## 【待核实】

- 按时分粮 BOOK_NAME_MAP 与 VARIANT 表是否完全覆盖繁体别名。
- `创世记第一章第一节` 等用例若抽到「整章+单节」双 Ref，是否符合产品预期。
