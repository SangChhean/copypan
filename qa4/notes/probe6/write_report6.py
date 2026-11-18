# -*- coding: utf-8 -*-
"""Assemble qa4_backend_build_probe_6.md from probe6 results."""
from __future__ import annotations

import json
from pathlib import Path

P = Path(r"G:\copypan\qa4\notes\probe6")
OUT = Path(r"G:\copypan\qa4\notes\qa4_backend_build_probe_6.md")
a = json.loads((P / "a_result.json").read_text(encoding="utf-8"))
b = json.loads((P / "b_result.json").read_text(encoding="utf-8"))
c = json.loads((P / "c_result.json").read_text(encoding="utf-8"))

L: list[str] = []
W = L.append

W("# qa4 后端构建前核对 · 第六轮（一）")
W("")
W("约束：只读；未改既有文件；未 git add/commit/push；未联网；未连 ES/Neo4j/Redis；未读 `.env`。")
W("产出：本报告；脚本 `qa4/notes/probe6/`。数字均由本轮脚本算出。")
W("")
W("---")
W("")
W("## A. organic_advance 新版结构")
W("")
W("脚本：`python qa4/notes/probe6/a_organic.py`")
W("")
W(f"- 基准：`{a['new_path']}`")
W(f"- SHA256 前16位：`{a['new_sha16']}`（期望 2ab34918389a6640）→ **一致，继续**")
W(f"- 顶层：{a['top_type']}；条数 **{a['n']}**；键 {a['keys']}")
W(f"- content 类型分布：{a['content_types']}（均为 str）")
W(f"- content 字数：min={a['content_len']['min']} / median={a['content_len']['median']} / max={a['content_len']['max']}")
W(f"- title 字数：min={a['title_len']['min']} / median={a['title_len']['median']} / max={a['title_len']['max']}；分布 {a['title_len']['bins']}")
W(f"- 不同 name：**{a['n_unique_names']}**；重名：{a['name_multi']}")
W("- name=「圣经」两条：")
for row in a["bible_rows"]:
    W(f"  - title=`{row['title']}`；content字数={row['content_len']}；开头=`{row['content_head30']}`")
W("")
W("### content 内部（str）")
W(f"- 行首类型：{a['content_str_stats']['lead_types']}")
W(f"- 含「阶段」或「时期」的行数：{a['content_str_stats']['stage_or_period_lines']}")
W(f"- 阶段样例：{a['content_str_stats']['stage_or_period_samples']}")
W(f"- 天干标题样例：{a['content_str_stats']['heading_samples_heavenly']}")
W(f"- 非 str content：{a['content_str_stats']['non_str'] or '无'}")
W("")
W("### 与旧版对照")
W(f"- 旧版：`{a['old_path']}`；SHA前16=`{a['old_sha16']}`（期望 63a2320504c535e5）")
W(f"- 仅新版 name：{a['only_new_names']}")
W(f"- 仅旧版 name：{a['only_old_names']}")
W(f"- 共有 name 数：{a['shared_n']}；新/旧 content 字数比中位数：**{a['content_len_ratio_median']:.4f}**（旧版 content_1…6 为 list[dict] 的 JSON 字数远大于新版单段 str）")
W(f"- 新版 title 与旧版同 name 的 series/stages 名称相同的条数：**{a['title_match_series_or_stages']}**")
W("")
W("### 与图谱导入")
W(f"- 文档：`docs/panai4_graph/import_organic_advance.md`；state：`logs/import_annotation_organic_advance_state.json`")
W("- 当时只 SET `organic_advance=true`（布尔），**内容不入库**；写入 name 数：**69**")
W(f"- 导入源 SHA：`63a2320504c535e5…`（旧版 69 条）；copy.n_records=69")
W(f"- 与新版 69 个不同 name：**不完全相同** — {a['import_info']['state']['file_names_vs_new69']}")
W("- 结论：图谱布尔旗标按旧版「基督的死」等 69 名写入；仓库 JSON 已换成新版（含「基督的十字架」、圣经双条）。")
W("")
W("### 仓库内副本")
for cp in a["repo_copies"]:
    W(f"- `{cp['path']}`｜{cp['bytes']} bytes｜sha16=`{cp['sha16']}`")
W("")
W("---")
W("")
W("## B. 经节补测")
W("")
W("脚本：`python qa4/notes/probe6/b_verse.py`；V21=`C:\\Users\\28121\\Desktop\\get_vers_v2.1.py`（只读 import）")
W("")
W("### B.1 3a 读经行整行重测")
b1 = b["b1_3a_whole_line"]
W(f"- 有读经行：**{b1['n_entries_with_reading']}**")
W(f"- 整行解析出≥1 出处：**{b1['n_lines_ge1_ref']}**")
W(f"- 出处总数：**{b1['n_refs_total']}**；其中 {b1['kinds']}")
W(f"- 能在 bible_data 找到：**{b1['n_in_bible_data']}**（整章/单节范围均计入；本轮无跨章 tok）")
W(f"- 零出处行：**{b1['n_zero_ref_lines']}**；样例：{b1['zero_samples']}")
W(f"- 遗漏启发式：{b1['miss_heuristic_rule']}")
W(f"- 疑似遗漏行数：**{b1['miss_heuristic_n']}**；样例：{b1['miss_samples'][:3]}")
W(f"- 做法：{b1['split_note']}；带 bible_data validate")
W("")
W("### B.2 qa4_bible 的 v2.1 失败")
b2 = b["b2_qa4_bible_fails"]
W(f"- verses 总数 {b2['verses_total']}；校验后失败 **{b2['v21_fail_n']}**")
W(f"- 按 book_title 前10：{b2['fail_book_title_top10']}")
W(f"- 章号写法：{b2['chapter_style_counts']}")
W(f"- 正则 X0=`{b2['x0_regex']}` 命中 {b2['n_matching_x0_regex']}；补充 `十0`=`{b2['shi0_regex']}` 命中 {b2['n_matching_shi0_regex']}；合计 {b2['n_matching_x0_or_shi0']}/116")
W(f"- 是否都符合仅 X0 正则：{b2['all_fails_match_x0']}（其余为「二十0」类，前接「十」）")
W(f"- 脚本内把 X0→X十（并试 十0→十十）后成功数：**{b2['after_normalize_x0_success']}**；仍失败 {b2['after_normalize_still_fail']}")
W("- 剩余失败类：")
for st in b2["still_fail_top_styles"]:
    W(f"  - {st['style']} ×{st['n']}｜例 {st['examples']}")
W("- 说明：无校验时 `诗篇三0～8` 会解析成 `诗3:0-8`（节号0）；带校验则失败。`三0→三十` 后变成 `诗篇三十～8`，仍无 tok；**推测**需写成 `三十1～8` 才过（本轮未改规则，仅记录）。")
W(f"- 失败样例：{b2['fail_examples_raw']}")
W("")
W("### B.3 「X0」在其它来源")
b3 = b["b3_x0_counts"]
W(f"- 正则：`{b3['regex']}`")
W(f"- 图谱 chosen：universe={b3['graph_chosen_4851']['universe']}｜命中 **{b3['graph_chosen_4851']['n']}**")
W(f"- map_note 抽样(seed=20261116)：universe={b3['map_note_sample']['universe']}｜命中 **{b3['map_note_sample']['n']}**")
W(f"- 3a 读经行：universe={b3['def_3a_reading_lines']['universe']}｜命中 **{b3['def_3a_reading_lines']['n']}**｜例 {b3['def_3a_reading_lines']['examples']}")
W("")
W("---")
W("")
W("## C. 图谱经节「贴后」排查")
W("")
W("脚本：`python qa4/notes/probe6/c_tiehou.py`")
W("")
W("### C.1 失败 6 个")
W(f"- 失败数：{c['c1_fail_n']}")
for d in c["c1_fail_details"]:
    W(f"- `{d['ref']}`｜所属词条：{d['terms']}")
W("")
W("### C.2 改成「帖后」后是否已存在")
for d in c["c2_fix_collision"]:
    W(
        f"- `{d['ref']}`→`{d['fixed']}`｜已在 chosen：{d['fixed_already_in_chosen']}｜改正后可解析：{d['fixed_parses']}"
    )
W("- 已在 chosen 的 3 个：改正会产生 **Scripture 键重复**（需合并关系，不能简单改名）。")
W("")
W("### C.3 「贴后」出现位置")
for loc in c["c3_locations"]:
    label = loc.get("label")
    if label == "节点一般标注.json":
        W(f"- 节点一般标注：整文件 **{loc.get('n_whole_file', loc.get('n'))}** 次；字段 `related_scriptures[].ref`；命中例：{[h.get('field') for h in (loc.get('hits') or [])]}")
    elif label == "truth_dictionary_3a3b.json":
        W(f"- truth_dictionary_3a3b：content_3a 等字段 **{loc.get('n_whole_file', loc.get('n'))}** 次；hit={loc.get('hits')}")
    elif label == "back_qa/bible_data":
        W(f"- bible_data：**{loc.get('n')}**")
    elif label == "主干枝映射":
        W(f"- 主干枝映射：**{loc.get('n_whole_file', loc.get('n'))}**")
    elif label == "qa4_bible chunks_bible.json":
        W(f"- qa4_bible chunks：**{loc.get('n')}**")
    elif label == "map_note jsonl":
        W(f"- map_note jsonl：**{loc.get('n')}**")
    elif label == "docs/**/*.md":
        hits = loc.get("hits") or []
        W(f"- docs md：检索命中 {loc.get('n')} 处；例 {hits[:2]}")
    elif "scripture_nodes_state" in (label or ""):
        W(f"- scripture state：整文件 **{loc.get('n')}** 次（含 chosen/link 等）")
    else:
        W(f"- {label}：{loc.get('n', loc.get('n_whole_file'))}")
W("")
W("### C.4 简称收录（贴/帖）")
v21 = c["c4_v21_book_map"]
W(f"- v2.1 BOOK_MAP 帖前：{v21['帖前_keys']}")
W(f"- v2.1 BOOK_MAP 帖后：{v21['帖后_keys']}")
W(f"- v2.1 含「贴」的键：{v21['keys_containing_贴'] or '无'}")
bd = c["c4_parser30"]["from_bible_data"]
W(f"- 3.0 bible_data 卷52 abbr_gb=`{(bd.get('52') or {}).get('abbr_gb')}` name=`{(bd.get('52') or {}).get('name_gb')}`")
W(f"- 3.0 bible_data 卷53 abbr_gb=`{(bd.get('53') or {}).get('abbr_gb')}` name=`{(bd.get('53') or {}).get('name_gb')}`")
W(f"- bible_ref_parser.py 源码中含贴/帖的行：{c['c4_parser30']['from_parser_source_lines'] or '无（简称来自 bible_data 名表，非写死贴）'}")
W("- 结论：两侧都收「帖前/帖后」，**都不收「贴后」**。")
W("")
W("### C.5 若要改图谱需要动的位置（只报告，未改）")
for d in c["c5_change_list"]:
    W(
        f"- Scripture 节点 name/ref：`{d['from']}`→`{d['to']}`；"
        f"关联 Truth_Point：{d['linked_terms']}；"
        f"关系：词条→经节链接；改名冲突={d['collision_if_rename']}"
    )
W("- 源数据同步：桌面 `节点一般标注.json` 的 `related_scriptures[].ref`（7 处）；再重跑经节导入/去重。")
W("- 已存在「帖后*」的 3 个：应 **合并** 到已有 Scripture，并把边迁过去，勿新建重复节点。")
W("")
W("---")
W("")
W("## 独立核对命令")
W("")
W("以下不依赖 probe6 脚本；在仓库根目录执行。")
W("")
W("1) 新版 organic SHA 前16与条数")
W("```")
W(r"""python -c "import hashlib,json;from pathlib import Path;p=Path(r'G:/copypan/qa4/data/graph_annotations/organic_advance.json');b=p.read_bytes();d=json.loads(b);print(hashlib.sha256(b).hexdigest()[:16], len(d), len({x['name'] for x in d}))""" )
W("```")
W("预期：`2ab34918389a6640 70 69`")
W("")
W("2) 旧版 SHA 前16与条数")
W("```")
W(r"""python -c "import hashlib,json;from pathlib import Path;p=Path(r'C:/Users/28121/Desktop/可导入资料/2 特殊标注/【organic_advance】生机关联的进展.json');b=p.read_bytes();d=json.loads(b);print(hashlib.sha256(b).hexdigest()[:16], len(d))""" )
W("```")
W("预期：`63a2320504c535e5 69`")
W("")
W("3) 图谱 chosen 中含「贴后」的 ref")
W("```")
W(r"""python -c "import json;from pathlib import Path;c=json.loads(Path(r'G:/copypan/logs/import_annotation_scripture_nodes_state.json').read_text(encoding='utf-8'))['chosen'];print(sorted(k for k in c if '贴后' in k))" """ )
W("```")
W("预期：6 个 `贴后…` 字符串列表")
W("")
W("4) v2.1 对「贴后三5」与「帖后三5」")
W("```")
W(r"""python -c "import importlib.util;from pathlib import Path;p=Path(r'C:/Users/28121/Desktop/get_vers_v2.1.py');s=importlib.util.spec_from_file_location('v21',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for t in ['贴后三5','帖后三5']:
 vp=m.VerseParser();vp.start_paragraph();print(t, vp.parse_text(t))" """ )
W("```")
W("预期：前者空列表；后者含 `帖后3:5` 一类 verses")
W("")
W("5) qa4_bible 中「汉字+ASCII 0」的 verse_range 条数")
W("```")
W(r"""python -c "import json,re;from pathlib import Path;n=0
for line in Path(r'G:/PanAI4.0专用/索引数据/panai4_bible/02_清洗JSON/chunks_bible.json').open(encoding='utf-8'):
 o=json.loads(line)
 if o.get('chunk_type')=='verses' and re.search(r'[一二三四五六七八九]0', o.get('verse_range') or ''): n+=1
print(n)" """ )
W("```")
W("预期：接近 103～115 的整数（本轮失败集相关）")
W("")
W("---")
W("")
W("## 验证")
W("")
W("- 本轮新增均在 `qa4/notes/`；`git diff --stat` 应为空。")

OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print("WROTE", OUT, "lines", len(L))
