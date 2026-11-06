# 任务 2：BOOK_TITLE_OVERRIDES

> 2026-11-06；备份：`config.py.bak_20261106`（同目录；`.gitignore` 已忽略 `*.bak`）。

## 1. 结构与用法（只读查明）

- **定义**：`panai4/outline/config.py` 约 588–626 行；`BOOK_TITLE_OVERRIDES` 为 `dict[tuple[str,str], str]`。
- **键**：`book_path_of` 去掉目录序号后的 **前两层** `(book_path[0], book_path[1])`。生命读经例：`("生命读经", "雅歌书生命读经")`。
- **值**：覆盖后的 **`book_title` 字符串**。
- **使用处**：`build_chunks.book_title_of`（`build_chunks.py:110–126`，命中 override 则直接返回值）。`convert_outline.py` **不引用** 此表。
- **影响范围**：只改 chunk 的 `book_title`（及由它算出的 text 第一行 / tokens）；**不改** `book_path`、`message_key`、`chunk_id`。

## 2. 本次新增（仅此）

```diff
--- bak
+++ config.py
@@ -620,6 +620,9 @@
     ("生命课程", "卷四"): "生命课程，卷四",
+    # 2026-11-06 生命读经书名修订：键 = strip 序号后的 book_path 前两层；只改 book_title，不改 book_path
+    ("生命读经", "雅歌书生命读经"): "雅歌生命读经",
+    ("生命读经", "约翰二书生命读经_"): "约翰二书生命读经",
 }
```

## 3. 验证（闸门）

### a. diff
- 与 `.bak_20261106` 对比：**仅增加上述 1 行注释 + 2 条 override**；无其他改动。

### b. 旧 outline + override → 与 `chunks_12490.new.json`
- 输入：`备份_…\outline_12490.json`（只读）；输出暂存：`_staging_life_fix\override_test\chunks_from_old_outline_with_override.json`（55,841）。
- **52 个书名类块**：`book_title` 与 new **一致 52/52**；`text` 与 new **一致 52/52**；与 new 的字段差 **仅 `book_path`（52/52）**。
  - 原因：override **只改 book_title**；`chunks_12490.new.json` 在阶段2 prepare 里已把 `book_path` 末段写成新书名，而从旧 outline 重建时 `book_path` 仍为 `雅歌书生命读经` / `约翰二书生命读经_`。
- 对照旧备份 chunks：same=**55,789** / diff=**52**（仅这 52 块的 `book_title`+`text`(+tokens)），证明 override 生效且无误伤。
- 与 new 整体：非书名块中 55,493 与 new 相同；另 296 块差在 title/number 修订（旧 outline 无这些 meta 改动，**与本次 override 无关**）。

### c. feasts
- `outline_feasts.json` → regen vs `纲目JSON\chunks_feasts.json`：**same=11,110 diff=0**。

### d. 代码范围
- `panai4/` 本任务只改 `outline/config.py`；另新增 `config.py.bak_20261106`（被 ignore）。

## 4. 密钥泄露检查
- 本报告与相关日志内存比对：**通过**。
