# 生命读经修订 阶段0备份 + 阶段1干跑

> 生成：2026-11-06T12:19:08；日志：`G:\copypan\logs\life_fix_apply_20261106_121639.log`；清单：`G:\copypan\docs\panai4_es\archive\life_12490_fix_final_v4.csv`。

## 结论摘要

(1) **清单 v4**：78 条（title=65 / book=12 / number=1）；相对「约78」差 0（剔除撒母耳#9，加 review6+srey3）。
(2) **备份**：`G:\PanAI4.0专用\备份_生命读经修订前_20261106`；5 个源文件 SHA256 与源一致；ES 导出 348 条 = 受影响唯一块 348。
(3) **outline 字段**：meta.title / meta.msg_no / book_title←book_path；复现性（build_message_chunks）：same=55841 diff=0；CLI=有 (same=55841 diff=0)。
(4) **改后**：受影响唯一块=348 篇≈78；reembed=343；vec_plan={'copy_embedding': 55493, 'reembed': 343, 'copy_embedding_update_meta': 5}。
(5) **自检 5a–5i**：全部通过（见明细）。
(6) **重算费用上限**：$0.0007（343 块，136866 字符）。
(7) **写法**：半角括号篇数=4；—=159；─=0（期望0）。
(8) **暂存**：`G:\PanAI4.0专用\_staging_life_fix` 文件 15 个。

## 1. 清单 v4

- 路径：`G:\copypan\docs\panai4_es\archive\life_12490_fix_final_v4.csv`
- 条数=78；field={'message_title': 65, 'book_title': 12, 'message_number': 1}；source={'final_v3': 69, 'review_decision': 6, 'srey_decision': 3}
- 不含撒母耳记 #9（题醒）。

## 2. 阶段0 备份

- 目录：`G:\PanAI4.0专用\备份_生命读经修订前_20261106`
- `outline_12490.json` sha256=`27709a28814e61631f9693cca83816d1f52cfdf8cb0ea94fa182e013f4e53c56` size=121121694
- `chunks_12490.json` sha256=`cb5a15bd5ff9fb0a387a5ad15ddc2dea50cc5e925fab27778d5f5a0c318f6305` size=118171428
- `chunks_12490_vec.json` sha256=`6f1592d07115f0a57bc0ed9283237be72d30c01bc170281d00f80f3b9236c198` size=1386787642
- `excluded_files.json` sha256=`815a677b8f84389bbec279826938cf440de4fa964881477cae148fb918db0fe1` size=121195
- `anomalies.json` sha256=`ea19e9cc093b5338be1f424133adda8008a16dda356f65db96d990cc20a09811` size=5360518
- affected 行=348 唯一块=348
- es_before_affected.jsonl=348
- ES count 55841/55841
- 纲目JSON 快照 {'files': 41, 'bytes': 4733504505} → {'files': 41, 'bytes': 4733504505}

## 3. outline 字段与复现性

### outline 里篇题 / 书名 / 篇号字段路径
| 语义 | outline 路径 | build_chunks 取值 |
| --- | --- | --- |
| 篇题 message_title | `record.meta.title`（另有 `doc_header.title_in_doc`，切块不用） | `meta.title` → `message_title`（build_chunks.py:180） |
| 篇号 message_number | `record.meta.msg_no` | `meta.msg_no` → `message_number`（:194） |
| 书名 book_title | 显示用 `meta.book`；权威路径 `meta.book_path` | `book_path_of(meta)` 去序号后 `book_title_of`（:110-126, 174-176）；生命读经一般为 `book_path[1]` |
| message_key | `record.id`（本轮不改） | 原样写入 `message_key`（:169） |
| tokens | （切块时计算） | `int(len(text) / 1.5)`（:199）；本干跑字段级改 text 后用同一公式重算 |

- **build_chunks_lines**：build_chunks.py:180-194, 110-126, 83-89（`render_header` = book_title + U+3000 + message_title）

### 复现性（旧 outline → chunks）
- build_message_chunks：n_a=55841 n_b=55841 same=55841 diff=0 field_diffs={}
- CLI build_chunks：same=55841 diff=0 field_diffs={}（CLI 退出码 2=STOP_V02，因 staging 无 v0.1 对照；产出 chunks 已逐字段比对完全相同）

### outline.new → regen vs field-edit new
- same=55789 diff=52 field_diffs={'book_path': 52}
- 说明：diff 若仅 `book_path`，属预期——字段级改块按 5c **不改** chunk.book_path；outline.new 为 SoT 已改 meta.book_path 末段，故 regen 的 book_path 不同。title/number 类应 same；book 类 book_title/text 应与字段级一致。
  - `gm12490_39111bf9aab9_c1` {'book_path': ("['生命读经', '雅歌书生命读经']", "['生命读经', '雅歌生命读经']")}
  - `gm12490_39111bf9aab9_c2` {'book_path': ("['生命读经', '雅歌书生命读经']", "['生命读经', '雅歌生命读经']")}
  - `gm12490_39111bf9aab9_c3` {'book_path': ("['生命读经', '雅歌书生命读经']", "['生命读经', '雅歌生命读经']")}
  - `gm12490_39111bf9aab9_c4` {'book_path': ("['生命读经', '雅歌书生命读经']", "['生命读经', '雅歌生命读经']")}
  - `gm12490_26b8814abecd_c1` {'book_path': ("['生命读经', '雅歌书生命读经']", "['生命读经', '雅歌生命读经']")}
  - `gm12490_26b8814abecd_c2` {'book_path': ("['生命读经', '雅歌书生命读经']", "['生命读经', '雅歌生命读经']")}
  - `gm12490_26b8814abecd_c3` {'book_path': ("['生命读经', '雅歌书生命读经']", "['生命读经', '雅歌生命读经']")}
  - `gm12490_26b8814abecd_c4` {'book_path': ("['生命读经', '雅歌书生命读经']", "['生命读经', '雅歌生命读经']")}
  - `gm12490_26b8814abecd_c5` {'book_path': ("['生命读经', '雅歌书生命读经']", "['生命读经', '雅歌生命读经']")}
  - `gm12490_e81da329d6a9_c1` {'book_path': ("['生命读经', '雅歌书生命读经']", "['生命读经', '雅歌生命读经']")}
- diff 是否仅 book_path：True（field_diffs={'book_path': 52}）

## 4. 改后统计

- chunks 总数=55841
- 受影响唯一块=348；text 变化(reembed)=343
- vec_plan actions={'copy_embedding': 55493, 'reembed': 343, 'copy_embedding_update_meta': 5}

## 5. 自检

- 5a_unaffected_identical_fail = 0
- 5b_affected_fields_or_body_fail = 0
- 5c_immutable_fail = 0
- 5d_mk_count_mismatch = 0
- 5d_n_chunks = 55841
- 5d_n_mk = 12328
- 5e_all_pair_conflicts_new = 63
- 5e_all_pair_conflicts_old = 63
- 5e_esther_pairs = [('以斯帖记生命读经', 1, 'gm12490/3 生命读经/14 以斯帖记生命读经/msg. 1 介言及隐藏的神在祂受压制的选民分散时，秘密的照顾他们'), ('以斯帖记生命读经', 2, 'gm12490/3 生命读经/14 以斯帖记生命读经/msg. 2 隐藏的神在祂受逼迫的选民被掳时，在隐密中公开的拯救他们'), ('以斯帖记生命读经', 3, 'gm12490/3 生命读经/14 以斯帖记生命读经/附录\u3000合乎圣经神圣启示的召会末世论')]
- 5e_life_pair_conflicts_new = 0
- 5e_life_pair_conflicts_old = 0
- 5e_life_samples = []
- 5e_pair_conflicts = 0（生命读经范围内 (book_title, message_number) 唯一）
- 5e 说明：全集含 None 键时新旧皆 63 冲突（文集预存，与本轮无关）；生命读经 0；附录 #3 已写入且不冲突
- 5f_header_fail = 0
- tokens 算法：`int(len(text) / 1.5)`（与 build_chunks.py:199 相同）；仅 text 变化的块重算
- 5g_plan_eq_text = True
- 5g_reembed_eq_plan = True
- 5g_reembed_eq_text = True
- 5h_copy_verify_fail = 0
- 5h_copy_verify_ok = 55498
- 5i_cost = 0.0006860000000000001
- 5i_reembed_chars = 136866
- 5i_reembed_n = 343
- copy_verify fail=0 ok=55498

## 6. 费用

- reembed 块=343 字符=136866 上限=$0.0007

## 7. 写法统计（修改后生命读经篇题）

- 半角括号篇数=4（前20）：
  - 马可福音生命读经 #69 `一种完全照着神新约经纶，并为着神新约经纶的生活(十八)`
  - 路加福音生命读经 #1 `路加福音的引言、主题、与内容(一)`
  - 使徒行传生命读经 #35 `借着保罗一班同工的职事，在外邦地的繁殖(一)`
  - 使徒行传生命读经 #36 `借着保罗一班同工的职事，在外邦地的繁殖(二)`
- 「—」篇数=159；「─」篇数=0

## 8. 暂存文件

- `changes_by_chunk.csv` size=99330
- `chunking_report_repro.md` size=293516
- `chunks_12490.new.json` size=118180235
- `chunks_12490.regen.json` size=118180101
- `chunks_12490.repro_from_old_outline.json` size=118171428
- `outline_12490.new.json` size=121122683
- `reembed_ids.txt` size=8581
- `repro_cli\chunks_12490.json` size=118171428
- `repro_cli\chunks_feasts.json` size=26035954
- `repro_cli\chunks_v1_20260929\chunks_12490.json` size=118171428
- `repro_cli\chunks_v2_20260929\chunks_feasts.json` size=26035954
- `repro_cli\outline_12490.json` size=121121694
- `repro_cli\outline_feasts.json` size=33155313
- `repro_old\outline_12490.json` size=121121694
- `vec_plan.csv` size=2233566

## 验证

1. 原文件 SHA256 与备份一致（见备份 SHA256SUMS）；纲目JSON 快照={'files': 41, 'bytes': 4733504505} 期望={'files': 41, 'bytes': 4733504505} ok=True
2. ES count=55841（55841=True）；本轮只用了 **count / mget**（未用 info/search；未写 ES）
3. 备份导出条数=348 == 受影响块=348；备份 5 文件 SHA256 与源一致
4. v4 每条 old==当前值（构建时断言失败数0）；无撒母耳#9；source=final_v3:69 / review_decision:6 / srey_decision:3
5. 自检 5a–5i 全过=True（失败数 0）；5e 生命读经 pair 冲突 0；全集预存冲突 63→63 未增；以斯帖附录 message_number=3 不冲突
6. git status `back_mic/backend/panai4/`：仅新增 apply_life_fix.py 与既有 probe_*（无改现有代码）
```
?? back_mic/backend/panai4/outline/apply_life_fix.py
?? back_mic/backend/panai4/outline/probe_12490_assets.py
?? back_mic/backend/panai4/outline/probe_life_fixlist.py
?? back_mic/backend/panai4/outline/probe_life_fixlist_v2.py
?? back_mic/backend/panai4/outline/probe_life_fixlist_v3.py
?? back_mic/backend/panai4/outline/probe_life_in_12490.py
?? back_mic/backend/panai4/outline/probe_life_in_12490_r2.py
?? back_mic/backend/panai4/outline/probe_life_outline.py
?? back_mic/backend/panai4/outline/probe_life_outline2.py
```
7. **未调用嵌入接口、未读取/打印/保存任何密钥、未写任何 ES。** 原文件与 `纲目JSON` 目录快照未变（41 文件 / 4,733,504,505 字节）。

