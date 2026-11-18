# qa4 阶段 0 · 准备

目录骨架、环境变量模板、查表生成与启动核对。本阶段不连 ES / Neo4j / Redis，不写提示词正文。

## 目录

```
qa4/backend/
  main.py              # /healthz → {"ok": true}
  config.py            # QA4_* 环境变量；可选 QA4_ENV_FILE
  .env.example         # 变量名 + 说明，值留空
  api/ core/ pipeline/ retrieval/ scripture/
  lookups/             # aliases.json / loader.py / name_norm.py
  prompts/             # 仅占位 README（变量说明）
  tools/
    sources.example.json
    sources.json       # 本地另存填写（已 gitignore）
    gen_lookups.py
    verify_stage0.py
  tests/test_stage0.py
qa4/data/lookups/      # 生成物（整个 qa4/data 已 gitignore）
```

## sources.json 怎么填

1. 复制 `tools/sources.example.json` → `tools/sources.json`
2. 把各键改成**本机存在的绝对路径**（文件或目录）
3. 缺文件就留空或删掉该键：生成时该项标「缺来源」，其余照做

关键键：

| 键 | 用途 |
|----|------|
| `intrinsic_significance` | 四档分类权威（2372） |
| `trunk_branch_map` | 主干 / 枝 |
| `truth_dictionary_3a3b` | has_3a / has_3b |
| `devine_argument` | has_devine_argument（取 name） |
| `high_peak_content` | has_high_peak |
| `organic_advance` | 新版 organic_advance（取 name） |
| `text_cwwl_shards` | 文集正文 shards → 年代表 / 无年份 |
| `outline_12490` | 纲目书名清单（按年标记另列，不与 cwwl 合并） |
| `wenji_volume_draft_csv` | 册表列模板（期望 1293 行） |
| `text_life_shards` / `text_cwwn_shards` / `text_others_shards` | 书目 |
| `outline_feasts` / `hymns` | 节期 259；诗歌系列与重叠 398 |

## 怎么运行

在仓库根目录：

```bash
python qa4/backend/tools/gen_lookups.py --sources qa4/backend/tools/sources.json --dry-run
python qa4/backend/tools/gen_lookups.py --sources qa4/backend/tools/sources.json
python qa4/backend/tools/verify_stage0.py
python -m unittest discover -s qa4/backend/tests
```

`--out` 默认 `qa4/data/lookups`。先写临时目录，全部硬门禁通过后才原子替换。

## 查表与期望数

| 文件 | 期望 | 说明 |
|------|------|------|
| `lexicon.json` | 主词 2372；展开 2380 | 四档权威；8 对括号内词 `same_as`→外词 |
| 档次（主词） | 最内在 133 / 外在 1658 / 内在 497 / 显出为外在 84 | |
| 档次（展开） | 133 / 1661 / 499 / 87 | |
| `zui_neizai_133.json` | 133 | 与 other 无交，并=2372 |
| `other_2239.json` | 2239 | |
| `wenji_year_table.json` | 42 | 35 单年 + 7 区间；年份取自 `book_title` 第一个 `，` 之前 |
| `no_year_titles.json` | 61 书名 / 5551 段 | 永不参与年代筛选 |
| `wenji_volume_table.csv` | 1293 | 只说明涵盖册，不用于筛选 |
| `life_books.json` | 63 | |
| `cwwn_books.json` | 106 | 辑 + 册 |
| `others_books.json` | 3 | 新约总论、真理课程、生命课程 |
| `feasts.json` | 259 | year + month_code 01–09 + name |
| `hymn_series.json` | 重叠 398 | 大本默认 `series=诗歌` |
| `authors.json` | 3 | 李常受、倪柝声、恢复本圣经 |

主干数 / 枝数、以及各 `has_*` 计数只报告，不作通过条件。

**年代区间重叠即命中**的筛选规则只在此说明，阶段 0 不实现。

## 别名与忽略

`lookups/aliases.json`：`路得马丁→路德马丁`；忽略 `城市`。比较名字前先别名再忽略；每次写入 `name_norm_log.json`。

## loader

`lookups/loader.py` 读 `MANIFEST.json`，逐文件核条数与 SHA256；不符则抛中文错误并拒绝启动。
