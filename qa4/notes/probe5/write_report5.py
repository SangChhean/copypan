# -*- coding: utf-8 -*-
"""Assemble qa4_backend_build_probe_5.md from probe5/*.json (UTF-8)."""
from __future__ import annotations

import json
from pathlib import Path

NOTES = Path(r"G:\copypan\qa4\notes")
A = json.loads((NOTES / "probe5" / "a_result.json").read_text(encoding="utf-8"))
B = json.loads((NOTES / "probe5" / "b_result.json").read_text(encoding="utf-8"))
C = json.loads((NOTES / "probe5" / "c_result.json").read_text(encoding="utf-8"))
OUT = NOTES / "qa4_backend_build_probe_5.md"


def j(o):
    return json.dumps(o, ensure_ascii=False)


lines: list[str] = []
W = lines.append

W("# qa4 后端构建前核对 · 第五轮（一）")
W("")
W("约束：只读；未改既有文件；未 git add/commit/push；未联网；未连 ES/Neo4j/Redis；未读 `.env`。")
W("产出：本报告；脚本 `qa4/notes/probe5/`；CSV `qa4/notes/devine_argument_items_all.csv`、`qa4/notes/lexicon_consistency.csv`。")
W("数字均由本轮脚本算出；不引用前几轮报告数字作依据。")
W("")
W("---")
W("")
W("## A. 辩理材料")
W("")
W("脚本：`python qa4/notes/probe5/a_devine.py`")
W("")
W("### A.1 两份主文件")
W("")
ast = A["a"]["stats"]
W(f"- (a) 路径：`{A['a']['path']}`")
W(f"- (a) SHA256：`{A['a']['sha256']}`")
W(f"- (a) 条目数：**{A['a']['n']}**；顶层键：{A['a']['top_keys']}")
W(f"- (b) 路径：`{A['b']['path']}`")
W(f"- (b) SHA256：`{A['b']['sha256']}`")
W(f"- (b) 条目数：**{A['b']['n']}**；顶层键：{A['b']['top_keys']}")
W("- 说明：(b) 仓库内 `qa4/.../organic_advance.json` 与桌面「（新）」同 SHA，键为 `content,name,title`（非旧式 `content_1…6`）。")
W("")
W("其它接近 189/73/72/69 的文件（同脚本扫描桌面 `可导入资料`）：")
for h in A["near_count_files"]:
    W(f"- n={h['n']} 键={h['keys']} 路径=`{h['path']}`")
W("")
W("桌面 organic 两份：")
for h in A["desk_organic"]:
    W(f"- n={h['n']} sha=`{h['sha256']}` 键={h['keys']} 路径=`{h['path']}`")
W("")
W("### A.2 (a) content_1 统计")
W("")
W(f"- 条目数：{ast['n_entries']}；不同 name 数：{ast['n_unique_names']}；重名：{ast['dup_names'] or '无'}")
W(f"- content_1 项数分布：{ast['content1_len_dist']}（全部为 1 项）")
W(f"- 总项数：{ast['total_items']}")
W(f"- T1（每条第一项不同 title）：**{ast['T1_first_titles']}**")
W(f"- T2（全部项不同 title，精确相同）：**{ast['T2_all_titles']}**")
W(f"- T3（去空白/标点 + NFKC 全半角后）：**{ast['T3_norm_titles']}**")
W(f"- C1 不同 (title+outline)：{ast['C1_title_outline']}；C2 不同 outline（去空白）：{ast['C2_outline_ws']}")
W(f"- 只出现在非第一项的 title：{ast['non_first_only_titles'] or '无'}（因每条仅 1 项，故空）")
W(f"- 同 title 不同 outline：{ast['n_titles_multi_outline']}；不同 title 同 outline：{ast['n_outlines_multi_title']}")
W("- 结论：72 份辩理 = 72 个不同 title（=不同 outline）；189 词条共享这 72 份；**不是 73**；非第一项差额候选为空。")
W(f"- CSV：`{A['a']['csv']}`（{A['a']['csv_rows']} 行）")
W("")
W("### A.3 name ↔ 2380 集合")
W("")
lex = A["lex2380"]
W(f"- 四档 words 数：{lex['class4_n']}；按 inventory 8 对拆括号后集合大小：**{lex['set_2380_size']}**")
W(f"- 四档内路德写法：路得马丁={lex['has_路得马丁']}，路德马丁={lex['has_路德马丁']}（本文件为「路得马丁」）")
W(f"- 对照时两种写法都认（variants 大小 {lex['set_with_variants_size']}）")
vs = A["name_vs_2380"]
W(f"- (a) 189 个 name 落在集合内：{vs['n_in']}；不在：{vs['n_out']} {vs['out_names'] or '（无）'}")
W(f"- 重名：{vs['dup_names'] or '无'}")
W("")
W("### A.4 189 vs 图谱非空约 187")
W("")
d = A["diff_189_187"]
W(f"- 已找到。丢弃 2 名：{d['discarded']}")
W("- 来源：`docs/panai4_graph/import_devine_argument.md` 与 `logs/import_annotation_devine_argument_state.json`")
W("- 原因：括号词对「产生男孩子/产生得胜者」「那灵的浇灌/圣灵的浇灌」内容完全相同 → 丢弃括号内，只写外词；故写入 187。")
W("")
W("### A.5 (b) 点数")
W("")
W(f"- 条目数：{A['b']['n']}；不同 name：{A['b']['n_unique_names']}；重名：{A['b']['dup_names']}")
W(f"- name 均在 2380 集合：是（in={A['b']['n_in_2380']}，missing={A['b']['missing'] or '无'}）")
W("- 注：旧桌面 69 条文件键为 name/series/stages/content_1…6；仓库 (b) 为新 70 条。")
W("")
W("---")
W("")
W("## B. 词表写法一致性")
W("")
W("脚本：`python qa4/notes/probe5/b_lexicon.py`")
W("口径：词条名/标题字段 = json 的 name/title/words[].name，以及边文件 from/to；txt 独占一行；「城市」只计整词相等。")
W("")
W("### B.1–B.2 各文件统计（摘要）")
W("")
for r in B["rows"]:
    if not r["exists"]:
        W(f"- 未找到：`{r['path']}`")
        continue
    hit = (
        r["as_name_路得马丁"]
        or r["as_name_路德马丁"]
        or r["as_name_城市"]
        or r["body_路得马丁"]
        or r["body_路德马丁"]
    )
    if not hit:
        continue
    W(
        f"- `{r['path']}`｜名:路得{r['as_name_路得马丁']}/路德{r['as_name_路德马丁']}/城市{r['as_name_城市']}｜"
        f"正文:路得{r['body_路得马丁']}/路德{r['body_路德马丁']}｜需改:{'是' if r['need_change'] else '否'}"
        + (f"｜{r['note']}" if r.get("note") else "")
    )
W("")
W("- `12大类与91小类的对应关系.txt`：三词均 0（已扫）。")
W("- `qa4/notes/zui_neizai_133_draft.txt`：三词均 0。")
W("- `qa4/notes/lexicon_reconcile.csv`：正文路得1/路德1（notes 仅记录）。")
W("- 标签映射 json：词条名无三词；正文「路德马丁」1。")
W("")
W("仍写「路得马丁」的源文件：")
W("- 桌面四档分类 json：`words[1136].name`")
W("- 桌面 `29种关系_成立边.json`：`pairs[].from`×2")
W("")
W("仍含词条名「城市」的文件：")
W("- `docs/panai4_graph/2373个词条….txt` L206")
W("- `docs/panai4_graph/2372个词条….txt` L206")
W("- `docs/panai4_graph/主恢复真理词典_词条主干枝子映射 (1).json` `[1816].name`")
W("")
W("### B.3 四源词名集合比较")
W("")
sc = B["set_compare"]
W(f"- 原始词数：{sc['raw_sizes']}")
W(f"- 规范化后词数（路得→路德；去掉城市）：{sc['norm_sizes']}")
W("- 规范化后两两是否完全相同：**全部 True**")
W(f"- 各源是否含三词（原始）：{j(sc['raw_has'])}")
W("- 不规范化差异（用于定位要改的文件）：")
for k, v in sc["pairwise_raw"].items():
    if v["equal"]:
        continue
    W(f"  - {k}：only_a={v['only_a']}；only_b={v['only_b']}")
W("")
W("### B.4 需要改动的文件与位置（只报告，未改）")
W("")
for ch in B["change_list"]:
    W(f"- `{ch['file']}`｜{ch['loc']}｜现=`{ch['current']}`｜应=`{ch['should']}`")
W("- 另：2373/2372 清单 L1138 与主干枝 `[1844].name` 已是「路德马丁」（正确，无需改）。")
W("- 四档分类应改为「路德马丁」；清单/主干枝应删除「城市」。")
W("")
W("### B.5 md 提及（docs/panai4_graph 与 qa4/docs）")
W("")
if B["md_mentions"]:
    for h in B["md_mentions"]:
        flags = []
        if h["has_路得"]:
            flags.append("路得")
        if h["has_路德"]:
            flags.append("路德")
        if h["has_城市"]:
            flags.append("城市")
        W(f"- `{h['path']}`:{h['line']}（{','.join(flags)}）｜{h['snip'][:30]}")
else:
    W("- 未找到")
W("")
W(f"- CSV：`qa4/notes/lexicon_consistency.csv`（{B['n_files_scanned']} 行）")
W("")
W("---")
W("")
W("## C. 经节规范化覆盖率")
W("")
W("脚本：`python qa4/notes/probe5/c_verse_norm.py`")
W(f"- V21_PATH：`{C['V21_PATH']}`（存在，size={C['v21_api']['size']}）")
W(f"- 候选：{j(C['v21_candidates'])}")
W("")
W("### C.1 v2.1 只读接口")
W("")
api = C["v21_api"]
W(f"- 入口：`{api['entry']}`")
W(f"- 调用：`{api['call']}`")
W(f"- 输出：{api['output']}")
W(f"- 依赖：{api['deps']}")
W("- 支持（据源码）：单节/范围/同章连续/多出处并列（组内连接）；整章（无节）；跨章（`章:节_章:节` 或章列表）；简称与全称（BOOK_MAP+load_book_map）；汉字章号（如诗八九26→诗89:26）；中文节号列表（顿号，v2.1）。")
W("- 已定：整章与跨章不列原文 → 本统计单独计数、不算失败（启发式 `preclassify_special` + 解析器 kind）。")
W("")
W("### C.2 测试集")
W("")
W(f"- (i) 图谱：`logs/import_annotation_scripture_nodes_state.json` 的 `chosen` 键，n={C['summaries']['graph_scripture']['total']}")
W(f"- (ii) 3a：`truth_dictionary_3a3b.json` 有读经行 {C['3a_entries_with_reading']}/{C['3a_entries_total']}；切出 {C['summaries']['def_3a']['total']} 段")
W(f"- 切分规则：{C['3a_split_rule']}")
W(f"- (iii) qa4_bible：`G:\\PanAI4.0专用\\索引数据\\panai4_bible\\02_清洗JSON\\chunks_bible.json` 中 chunk_type=verses n={C['qa4_bible_verses_n']}；引用=book_title+verse_range")
W(f"- (iv) map_note：`G:\\PanAI4.0专用\\12490原文JSONL\\kg-rag_map_note.jsonl` 可抽取 {C['map_note_extractable']}；种子 20261116 抽样 {C['map_note_sample_n']}")
W(f"- 抽取规则：{C['map_note_extract_rule']}")
W(f"- bible_data：`back_qa/bible_data` books={C['bible_data_books']} chapters={C['bible_data_chapters']} verses={C['bible_data_verses']}")
W("")
W("烟雾（同脚本）：")
for s in C["smoke"]:
    W(f"- `{s['ref']}`｜3.0 {s['kind3']}/ok={s['ok3']}｜v21 {s['kind21']}/ok={s['ok21']} toks={s['toks21']}")
W("")
W("### C.3 各测试集结果")
W("")
for name, s in C["summaries"].items():
    W(f"**{name}** total={s['total']}")
    W(
        f"- v2.1：成功 {s['v21']['ok']}；成功且在 bible_data {s['v21']['in_bible']}；"
        f"整章 {s['v21']['whole']}；跨章 {s['v21']['cross']}；失败 {s['v21']['fail']}"
    )
    W(
        f"- 3.0 parse_bible_ref：成功 {s['p30']['ok']}；成功且在 bible_data {s['p30']['in_bible']}；"
        f"整章 {s['p30']['whole']}；跨章 {s['p30']['cross']}；失败 {s['p30']['fail']}"
    )
    W(f"- 两解析器不一致：{s['disagree_n']}；例：")
    for ex in s["disagree_examples"]:
        W(f"  - `{ex['ref']}`｜p30={ex['p30']}｜v21={ex['v21']} toks={ex['toks21']}")
    W("")
W("要点：3.0 对「诗八九26」「可十四24」等简称+中文章+阿拉伯节大量失败；v2.1 对此类很强。")
W("3a 失败主因：按逗号/顿号切开后出现无书名的承前片段（如「一17」「8」「29~33」），单条喂入无法继承上文卷章。")
W("")
W("### C.4 失败写法归类（最多 15 类）")
W("")
for name, s in C["summaries"].items():
    W(f"**{name} · v2.1 失败**")
    for bkt in s["fail_v21_top15"]:
        W(f"- {bkt['bucket']} ×{bkt['n']}｜例 {bkt['examples']}")
    W(f"**{name} · 3.0 失败**")
    for bkt in s["fail_p30_top15"][:8]:
        W(f"- {bkt['bucket']} ×{bkt['n']}｜例 {bkt['examples']}")
    W("")
W("### C.5 统一键可行性")
W("")
W("键定义：成功解析的 `(卷号, 章, 起节, 止节)`；整章/跨章不进此键集。")
W(f"- 各源键数：{C['unified_key_sizes']}")
W(f"- 相对 bible_data（单节键）重叠：{j(C['unified_vs_bible_data'])}")
W("- 对不上的主要类型：")
for m in C["unified_mismatch_types"]:
    W(
        f"  - {m['source']}：范围键(起≠止) {m['range_not_single']}；整章 {m['whole_chapter']}；"
        f"跨章 {m['cross_chapter']}；解析失败 {m['parse_fail']}"
    )
W("- 结论：图谱/map_note 以单节为主，易与 bible_data 对齐；qa4_bible/3a 含大量范围键，需先展开成单节或约定范围键才能五源共键。")
W("")
W("---")
W("")
W("## 独立核对命令")
W("")
W("以下只读。可直接跑打包核对：`python qa4/notes/probe5/verify_independent.py`（打印 5 行，与下方预期对照）。")
W("")
W("1) (a) 条数与 T1")
W("命令：`python qa4/notes/probe5/verify_independent.py 1`")
W("预期：`3539cc9f1c035d95 189 72`")
W("")
W("2) 189→187 丢弃名")
W("命令：`python qa4/notes/probe5/verify_independent.py 2`")
W("预期：`['产生得胜者', '圣灵的浇灌']`")
W("")
W("3) 四档「路得马丁」与清单「城市」")
W("命令：`python qa4/notes/probe5/verify_independent.py 3`")
W("预期：`['路得马丁']` 与 `['城市', '路德马丁']`（顺序以文件出现为准）")
W("")
W("4) organic 仓库副本条数")
W("命令：`python qa4/notes/probe5/verify_independent.py 4`")
W("预期：`70 ['content', 'name', 'title'] 2ab34918389a6640`")
W("")
W("5) v2.1 解析「诗八九26」")
W("命令：`python qa4/notes/probe5/verify_independent.py 5`")
W("预期：输出中含 `诗89:26`")
W("")
W("---")
W("")
W("## 验证")
W("")
W("- 本轮新增均在 `qa4/notes/`（报告/脚本/CSV/中间 json）；`git diff --stat` 为空（无已跟踪改动）。")
W("- 工作区另有既有未跟踪文件（如 `docs/panai4_graph/export_pack.md` 等），非本轮产出。")

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("WROTE", OUT, "lines", len(lines))
