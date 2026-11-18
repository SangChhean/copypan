# qa4 后端构建前核对 · 第五轮（一）

约束：只读；未改既有文件；未 git add/commit/push；未联网；未连 ES/Neo4j/Redis；未读 `.env`。
产出：本报告；脚本 `qa4/notes/probe5/`；CSV `qa4/notes/devine_argument_items_all.csv`、`qa4/notes/lexicon_consistency.csv`。
数字均由本轮脚本算出；不引用前几轮报告数字作依据。

---

## A. 辩理材料

脚本：`python qa4/notes/probe5/a_devine.py`

### A.1 两份主文件

- (a) 路径：`C:\Users\28121\Desktop\可导入资料\2 特殊标注\【devine_argument】越进入高峰，真理越需要辨明得准确.json`
- (a) SHA256：`3539cc9f1c035d958f9dc1313d64f0085b61151e4687ccea98971a99f710f4d6`
- (a) 条目数：**189**；顶层键：['content_1', 'name']
- (b) 路径：`G:\copypan\qa4\data\graph_annotations\organic_advance.json`
- (b) SHA256：`2ab34918389a6640bd6d96e1ed9e6f4a19d80e73d3afa574b2dea28dd6cec565`
- (b) 条目数：**70**；顶层键：['content', 'name', 'title']
- 说明：(b) 仓库内 `qa4/.../organic_advance.json` 与桌面「（新）」同 SHA，键为 `content,name,title`（非旧式 `content_1…6`）。

其它接近 189/73/72/69 的文件（同脚本扫描桌面 `可导入资料`）：
- n=189 键=['content_1', 'name'] 路径=`C:\Users\28121\Desktop\可导入资料\2 特殊标注\【devine_argument】越进入高峰，真理越需要辨明得准确.json`
- n=69 键=['content_1', 'content_2', 'content_3', 'content_4', 'content_5', 'content_6', 'name', 'series', 'stages'] 路径=`C:\Users\28121\Desktop\可导入资料\2 特殊标注\【organic_advance】生机关联的进展.json`
- n=70 键=['content', 'name', 'title'] 路径=`C:\Users\28121\Desktop\可导入资料\2 特殊标注\【organic_advance】生机关联的进展（新）.json`

桌面 organic 两份：
- n=69 sha=`63a2320504c535e5b54d6ac8b33e0f76cafdfa5d330edfe9ccbbaa15abfb8178` 键=['content_1', 'content_2', 'content_3', 'content_4', 'content_5', 'content_6', 'name', 'series', 'stages'] 路径=`C:\Users\28121\Desktop\可导入资料\2 特殊标注\【organic_advance】生机关联的进展.json`
- n=70 sha=`2ab34918389a6640bd6d96e1ed9e6f4a19d80e73d3afa574b2dea28dd6cec565` 键=['content', 'name', 'title'] 路径=`C:\Users\28121\Desktop\可导入资料\2 特殊标注\【organic_advance】生机关联的进展（新）.json`

### A.2 (a) content_1 统计

- 条目数：189；不同 name 数：189；重名：无
- content_1 项数分布：{'1': 189}（全部为 1 项）
- 总项数：189
- T1（每条第一项不同 title）：**72**
- T2（全部项不同 title，精确相同）：**72**
- T3（去空白/标点 + NFKC 全半角后）：**72**
- C1 不同 (title+outline)：72；C2 不同 outline（去空白）：72
- 只出现在非第一项的 title：无（因每条仅 1 项，故空）
- 同 title 不同 outline：0；不同 title 同 outline：0
- 结论：72 份辩理 = 72 个不同 title（=不同 outline）；189 词条共享这 72 份；**不是 73**；非第一项差额候选为空。
- CSV：`G:\copypan\qa4\notes\devine_argument_items_all.csv`（189 行）

### A.3 name ↔ 2380 集合

- 四档 words 数：2372；按 inventory 8 对拆括号后集合大小：**2380**
- 四档内路德写法：路得马丁=True，路德马丁=False（本文件为「路得马丁」）
- 对照时两种写法都认（variants 大小 2381）
- (a) 189 个 name 落在集合内：189；不在：0 （无）
- 重名：无

### A.4 189 vs 图谱非空约 187

- 已找到。丢弃 2 名：['产生得胜者', '圣灵的浇灌']
- 来源：`docs/panai4_graph/import_devine_argument.md` 与 `logs/import_annotation_devine_argument_state.json`
- 原因：括号词对「产生男孩子/产生得胜者」「那灵的浇灌/圣灵的浇灌」内容完全相同 → 丢弃括号内，只写外词；故写入 187。

### A.5 (b) 点数

- 条目数：70；不同 name：69；重名：['圣经']
- name 均在 2380 集合：是（in=70，missing=无）
- 注：旧桌面 69 条文件键为 name/series/stages/content_1…6；仓库 (b) 为新 70 条。

---

## B. 词表写法一致性

脚本：`python qa4/notes/probe5/b_lexicon.py`
口径：词条名/标题字段 = json 的 name/title/words[].name，以及边文件 from/to；txt 独占一行；「城市」只计整词相等。

### B.1–B.2 各文件统计（摘要）

- `C:\Users\28121\Desktop\可导入资料\1 一般标注\真理词典：3a和3b.json`｜名:路得0/路德1/城市0｜正文:路得0/路德38｜需改:否
- `C:\Users\28121\Desktop\可导入资料\1 一般标注\节点一般标注.json`｜名:路得0/路德1/城市0｜正文:路得0/路德1｜需改:否
- `C:\Users\28121\Desktop\可导入资料\2 特殊标注\【devine_argument】越进入高峰，真理越需要辨明得准确.json`｜名:路得0/路德0/城市0｜正文:路得0/路德1｜需改:否
- `C:\Users\28121\Desktop\可导入资料\2 特殊标注\【high_peak_content】从历史进展的差异看高峰时期的内涵.json`｜名:路得0/路德0/城市0｜正文:路得0/路德4｜需改:否
- `C:\Users\28121\Desktop\可导入资料\2 特殊标注\【intrinsic_significance】2372词条内在意义分类.json`｜名:路得1/路德0/城市0｜正文:路得1/路德0｜需改:是
- `C:\Users\28121\Desktop\可导入资料\2 特殊标注\【organic_advance】生机关联的进展.json`｜名:路得0/路德0/城市0｜正文:路得0/路德84｜需改:否
- `C:\Users\28121\Desktop\可导入资料\2 特殊标注\【organic_advance】生机关联的进展（新）.json`｜名:路得0/路德0/城市0｜正文:路得0/路德1｜需改:否
- `C:\Users\28121\Desktop\可导入资料\3 边\29种关系_成立边.json`｜名:路得2/路德0/城市0｜正文:路得2/路德0｜需改:是
- `G:\copypan\docs\panai4_graph\2373个词条（已确定一一对应为concept节点）.txt`｜名:路得0/路德1/城市1｜正文:路得0/路德1｜需改:是
- `G:\copypan\docs\panai4_graph\主恢复真理词典_词条主干枝子映射 (1).json`｜名:路得0/路德1/城市1｜正文:路得0/路德1｜需改:是
- `G:\copypan\docs\panai4_graph\主恢复真理词典_标签映射_已校对 (1).json`｜名:路得0/路德0/城市0｜正文:路得0/路德1｜需改:否
- `G:\copypan\docs\panai4_graph\2372个词条（已确定一一对应为concept节点）.txt`｜名:路得0/路德1/城市1｜正文:路得0/路德1｜需改:是
- `G:\copypan\qa4\data\graph_annotations\organic_advance.json`｜名:路得0/路德0/城市0｜正文:路得0/路德1｜需改:否
- `G:\copypan\qa4\data\graph_annotations\truth_dictionary_3a3b.json`｜名:路得0/路德1/城市0｜正文:路得0/路德38｜需改:否
- `G:\copypan\back_mic\backend\panai4\data\graph_annotations\organic_advance.json`｜名:路得0/路德0/城市0｜正文:路得0/路德1｜需改:否
- `G:\copypan\back_mic\backend\panai4\data\graph_annotations\truth_dictionary_3a3b.json`｜名:路得0/路德1/城市0｜正文:路得0/路德38｜需改:否
- `G:\copypan\qa4\notes\lexicon_reconcile.csv`｜名:路得0/路德0/城市0｜正文:路得1/路德1｜需改:否｜notes_record_only

- `12大类与91小类的对应关系.txt`：三词均 0（已扫）。
- `qa4/notes/zui_neizai_133_draft.txt`：三词均 0。
- `qa4/notes/lexicon_reconcile.csv`：正文路得1/路德1（notes 仅记录）。
- 标签映射 json：词条名无三词；正文「路德马丁」1。

仍写「路得马丁」的源文件：
- 桌面四档分类 json：`words[1136].name`
- 桌面 `29种关系_成立边.json`：`pairs[].from`×2

仍含词条名「城市」的文件：
- `docs/panai4_graph/2373个词条….txt` L206
- `docs/panai4_graph/2372个词条….txt` L206
- `docs/panai4_graph/主恢复真理词典_词条主干枝子映射 (1).json` `[1816].name`

### B.3 四源词名集合比较

- 原始词数：{'2373清单': 2373, '主干枝映射': 2373, '四档分类': 2372, 'truth_dictionary_3a3b': 2372}
- 规范化后词数（路得→路德；去掉城市）：{'2373清单': 2372, '主干枝映射': 2372, '四档分类': 2372, 'truth_dictionary_3a3b': 2372}
- 规范化后两两是否完全相同：**全部 True**
- 各源是否含三词（原始）：{"2373清单": {"路得马丁": false, "路德马丁": true, "城市": true}, "主干枝映射": {"路得马丁": false, "路德马丁": true, "城市": true}, "四档分类": {"路得马丁": true, "路德马丁": false, "城市": false}, "truth_dictionary_3a3b": {"路得马丁": false, "路德马丁": true, "城市": false}}
- 不规范化差异（用于定位要改的文件）：
  - 2373清单 vs 四档分类：only_a=['城市', '路德马丁']；only_b=['路得马丁']
  - 2373清单 vs truth_dictionary_3a3b：only_a=['城市']；only_b=[]
  - 主干枝映射 vs 四档分类：only_a=['城市', '路德马丁']；only_b=['路得马丁']
  - 主干枝映射 vs truth_dictionary_3a3b：only_a=['城市']；only_b=[]
  - 四档分类 vs truth_dictionary_3a3b：only_a=['路得马丁']；only_b=['路德马丁']

### B.4 需要改动的文件与位置（只报告，未改）

- `C:\Users\28121\Desktop\可导入资料\2 特殊标注\【intrinsic_significance】2372词条内在意义分类.json`｜.words[1136].name=路得马丁｜现=`路得马丁`｜应=`路德马丁`
- `C:\Users\28121\Desktop\可导入资料\3 边\29种关系_成立边.json`｜[28].pairs[520].from=路得马丁｜现=`路得马丁`｜应=`路德马丁`
- `C:\Users\28121\Desktop\可导入资料\3 边\29种关系_成立边.json`｜[28].pairs[521].from=路得马丁｜现=`路得马丁`｜应=`路德马丁`
- `G:\copypan\docs\panai4_graph\2373个词条（已确定一一对应为concept节点）.txt`｜L206:城市｜现=`城市`｜应=`删除`
- `G:\copypan\docs\panai4_graph\主恢复真理词典_词条主干枝子映射 (1).json`｜[1816].name=城市｜现=`城市`｜应=`删除`
- `G:\copypan\docs\panai4_graph\2372个词条（已确定一一对应为concept节点）.txt`｜L206:城市｜现=`城市`｜应=`删除`
- 另：2373/2372 清单 L1138 与主干枝 `[1844].name` 已是「路德马丁」（正确，无需改）。
- 四档分类应改为「路德马丁」；清单/主干枝应删除「城市」。

### B.5 md 提及（docs/panai4_graph 与 qa4/docs）

- `G:\copypan\docs\panai4_graph\import_intrinsic_significance.md`:11（路得,路德）｜4. **合并名明细**：[{'src': '产生男孩子（产
- `G:\copypan\docs\panai4_graph\import_intrinsic_significance.md`:14（路得,路德）｜7. **脚本**：import_annotation_v2
- `G:\copypan\docs\panai4_graph\import_intrinsic_significance.md`:31（路德）｜- samples: [{'name': '晨晨复兴', '
- `G:\copypan\docs\panai4_graph\import_relations_29.md`:10（路得,路德）｜3. **端点映射**：{"路得马丁": "路德马丁", "
- `G:\copypan\docs\panai4_graph\import_relations_29.md`:247（路德）｜- luther_samples=[{"type": "LO
- `G:\copypan\docs\panai4_graph\neo4j_v4_inventory_pre.md`:518（路得）｜- 找不到的前 50：[{"name": "晨晨复兴（晨兴）
- `G:\copypan\docs\panai4_graph\neo4j_v4_inventory_pre.md`:796（路得）｜- 找不到前 50：[{"name": "产生男孩子（产生得

- CSV：`qa4/notes/lexicon_consistency.csv`（24 行）

---

## C. 经节规范化覆盖率

脚本：`python qa4/notes/probe5/c_verse_norm.py`
- V21_PATH：`C:\Users\28121\Desktop\get_vers_v2.1.py`（存在，size=35645）
- 候选：[{"path": "C:\\Users\\28121\\Desktop\\get_vers_v2.1.py", "size": 35645}, {"path": "C:\\Users\\28121\\Desktop\\__pycache__\\get_vers_v2.1.cpython-310.pyc", "size": 28527}]

### C.1 v2.1 只读接口

- 入口：`VerseParser.parse_text / process_data`
- 调用：`p=VerseParser(validate=...); p.start_paragraph(); p.parse_text(text)`
- 输出：list[{text,verses,start,end}]; verses 如 太5:1-3 或 太5:1_7:29 或 太5
- 依赖：['本地正则', '可选 bible 校验器 build_validator', '可选 load_book_map(bible.json)']
- 支持（据源码）：单节/范围/同章连续/多出处并列（组内连接）；整章（无节）；跨章（`章:节_章:节` 或章列表）；简称与全称（BOOK_MAP+load_book_map）；汉字章号（如诗八九26→诗89:26）；中文节号列表（顿号，v2.1）。
- 已定：整章与跨章不列原文 → 本统计单独计数、不算失败（启发式 `preclassify_special` + 解析器 kind）。

### C.2 测试集

- (i) 图谱：`logs/import_annotation_scripture_nodes_state.json` 的 `chosen` 键，n=4851
- (ii) 3a：`truth_dictionary_3a3b.json` 有读经行 2365/2372；切出 23181 段
- 切分规则：取 content_3a 首行；若以「读经：」或「读经:」开头则去掉前缀；再按中文逗号/英文逗号/分号/顿号切开；去空白；空段丢弃。
- (iii) qa4_bible：`G:\PanAI4.0专用\索引数据\panai4_bible\02_清洗JSON\chunks_bible.json` 中 chunk_type=verses n=3625；引用=book_title+verse_range
- (iv) map_note：`G:\PanAI4.0专用\12490原文JSONL\kg-rag_map_note.jsonl` 可抽取 15642；种子 20261116 抽样 2000
- 抽取规则：去掉外层括号；按逗号切分；丢弃含「恢复本/圣经」的首段与「注N」段；取剩余第一段。
- bible_data：`back_qa/bible_data` books=66 chapters=1189 verses=31103

烟雾（同脚本）：
- `约三16`｜3.0 fail/ok=False｜v21 verse_or_range/ok=True toks=['约3:16']
- `创一1～3`｜3.0 verse_or_range/ok=True｜v21 verse_or_range/ok=True toks=['创1:1-3']
- `太五至七`｜3.0 cross_chapter/ok=True｜v21 cross_chapter/ok=True toks=[]
- `诗八九26`｜3.0 fail/ok=False｜v21 verse_or_range/ok=True toks=['诗89:26']
- `约翰福音三章十六节`｜3.0 verse_or_range/ok=True｜v21 verse_or_range/ok=True toks=['约3:16']
- `可十四24`｜3.0 fail/ok=False｜v21 verse_or_range/ok=True toks=['可14:24']
- `罗八28`｜3.0 fail/ok=False｜v21 verse_or_range/ok=True toks=['罗8:28']
- `诗篇一章`｜3.0 whole_chapter/ok=True｜v21 whole_chapter/ok=True toks=['诗1']

### C.3 各测试集结果

**graph_scripture** total=4851
- v2.1：成功 4845；成功且在 bible_data 4845；整章 0；跨章 0；失败 6
- 3.0 parse_bible_ref：成功 1543；成功且在 bible_data 1542；整章 0；跨章 0；失败 3308
- 两解析器不一致：3305；例：
  - `诗八九26`｜p30=fail｜v21=verse_or_range toks=['诗89:26']
  - `赛六四8`｜p30=fail｜v21=verse_or_range toks=['赛64:8']
  - `可十四36`｜p30=fail｜v21=verse_or_range toks=['可14:36']
  - `罗八15`｜p30=fail｜v21=verse_or_range toks=['罗8:15']
  - `启二一6`｜p30=fail｜v21=verse_or_range toks=['启21:6']

**def_3a** total=23181
- v2.1：成功 14562；成功且在 bible_data 14562；整章 2；跨章 0；失败 8619
- 3.0 parse_bible_ref：成功 7354；成功且在 bible_data 7342；整章 2；跨章 0；失败 15827
- 两解析器不一致：7327；例：
  - `可十四36`｜p30=fail｜v21=verse_or_range toks=['可14:36']
  - `启二二13`｜p30=fail｜v21=verse_or_range toks=['启22:13']
  - `来二14`｜p30=fail｜v21=verse_or_range toks=['来2:14']
  - `诗一四六1`｜p30=fail｜v21=verse_or_range toks=['诗146:1']
  - `徒二十31`｜p30=fail｜v21=verse_or_range toks=['徒20:31']

**qa4_bible** total=3625
- v2.1：成功 3509；成功且在 bible_data 3509；整章 0；跨章 0；失败 116
- 3.0 parse_bible_ref：成功 3285；成功且在 bible_data 3285；整章 0；跨章 0；失败 340
- 两解析器不一致：280；例：
  - `创世记一2下～5`｜p30=verse_or_range｜v21=verse_or_range toks=['创1:2-5']
  - `创世记一26`｜p30=fail｜v21=verse_or_range toks=['创1:26']
  - `创世记一27`｜p30=fail｜v21=verse_or_range toks=['创1:27']
  - `创世记一28`｜p30=fail｜v21=verse_or_range toks=['创1:28']
  - `创世记一31`｜p30=fail｜v21=verse_or_range toks=['创1:31']

**map_note** total=2000
- v2.1：成功 1999；成功且在 bible_data 1999；整章 0；跨章 0；失败 1
- 3.0 parse_bible_ref：成功 746；成功且在 bible_data 744；整章 0；跨章 0；失败 1254
- 两解析器不一致：1255；例：
  - `约十五11`｜p30=fail｜v21=verse_or_range toks=['约15:11']
  - `林前十四26`｜p30=fail｜v21=verse_or_range toks=['林前14:26']
  - `太十五27`｜p30=fail｜v21=verse_or_range toks=['太15:27']
  - `撒下七14`｜p30=fail｜v21=verse_or_range toks=['撒下7:14']
  - `出十七12`｜p30=fail｜v21=verse_or_range toks=['出17:12']

要点：3.0 对「诗八九26」「可十四24」等简称+中文章+阿拉伯节大量失败；v2.1 对此类很强。
3a 失败主因：按逗号/顿号切开后出现无书名的承前片段（如「一17」「8」「29~33」），单条喂入无法继承上文卷章。

### C.4 失败写法归类（最多 15 类）

**graph_scripture · v2.1 失败**
- 中文章+阿拉伯节 ×6｜例 ['贴后三5', '贴后二3', '贴后三17']
**graph_scripture · 3.0 失败**
- 中文章+阿拉伯节 ×3143｜例 ['诗八九26', '赛六四8', '可十四36']
- 含上下半节 ×157｜例 ['代上二九3', '代下三六15', '王上七19']
- 其它 ×8｜例 ['约贰2', '犹20', '犹2']

**def_3a · v2.1 失败**
- 中文章+阿拉伯节 ×4554｜例 ['一17', '二8', '一8']
- 其它 ×3916｜例 ['8', '29~33', '16']
- 疑似整章 ×83｜例 ['创六', '彼前二', '启二~三']
- 含上下半节 ×66｜例 ['20下~23', '十五16下', '十9~10下']
**def_3a · 3.0 失败**
- 中文章+阿拉伯节 ×11592｜例 ['可十四36', '启二二13', '一17']
- 其它 ×3943｜例 ['8', '29~33', '16']
- 含上下半节 ×228｜例 ['王上十八21', '王上七16', '20下~23']
- 疑似整章 ×62｜例 ['创六', '彼前二', '启二~三']
- 含注号 ×2｜例 ['结四八31注1', '创三五10注1']

**qa4_bible · v2.1 失败**
- 中文章+阿拉伯节 ×116｜例 ['诗篇三0～8', '诗篇四0～8', '诗篇五0～12']
**qa4_bible · 3.0 失败**
- 中文章+阿拉伯节 ×264｜例 ['创世记一26', '创世记一27', '创世记一28']
- 含上下半节 ×76｜例 ['创世记二十七27下～41', '士师记三11下～31', '撒母耳记上一21～二11']

**map_note · v2.1 失败**
- 中文章+阿拉伯节 ×1｜例 ['创十二30']
**map_note · 3.0 失败**
- 中文章+阿拉伯节 ×1199｜例 ['约十五11', '林前十四26', '太十五27']
- 含上下半节 ×52｜例 ['撒下七14', '代上二二3', '王下二15']
- 其它 ×3｜例 ['约贰1', '门5', '约贰8']

### C.5 统一键可行性

键定义：成功解析的 `(卷号, 章, 起节, 止节)`；整章/跨章不进此键集。
- 各源键数：{'graph_scripture': 4834, 'def_3a': 5107, 'qa4_bible': 3597, 'map_note': 1240, 'bible_data': 31103}
- 相对 bible_data（单节键）重叠：{"graph_scripture": {"n": 4834, "in_bible_data": 4606, "not_in_bible_data": 228, "note": "keys are (book,chap,v_start,v_end); ranges kept as-is (not expanded)"}, "def_3a": {"n": 5107, "in_bible_data": 2984, "not_in_bible_data": 2123, "note": "keys are (book,chap,v_start,v_end); ranges kept as-is (not expanded)"}, "qa4_bible": {"n": 3597, "in_bible_data": 420, "not_in_bible_data": 3177, "note": "keys are (book,chap,v_start,v_end); ranges kept as-is (not expanded)"}, "map_note": {"n": 1240, "in_bible_data": 1240, "not_in_bible_data": 0, "note": "keys are (book,chap,v_start,v_end); ranges kept as-is (not expanded)"}}
- 对不上的主要类型：
  - graph_scripture：范围键(起≠止) 228；整章 0；跨章 0；解析失败 6
  - def_3a：范围键(起≠止) 4092；整章 2；跨章 0；解析失败 8619
  - qa4_bible：范围键(起≠止) 3177；整章 0；跨章 0；解析失败 116
  - map_note：范围键(起≠止) 0；整章 0；跨章 0；解析失败 1
- 结论：图谱/map_note 以单节为主，易与 bible_data 对齐；qa4_bible/3a 含大量范围键，需先展开成单节或约定范围键才能五源共键。

---

## 独立核对命令

以下只读。可直接跑打包核对：`python qa4/notes/probe5/verify_independent.py`（打印 5 行，与下方预期对照）。

1) (a) 条数与 T1  
命令：`python qa4/notes/probe5/verify_independent.py 1`  
预期：`3539cc9f1c035d95 189 72`

2) 189→187 丢弃名  
命令：`python qa4/notes/probe5/verify_independent.py 2`  
预期：`['产生得胜者', '圣灵的浇灌']`

3) 四档「路得马丁」与清单「城市」  
命令：`python qa4/notes/probe5/verify_independent.py 3`  
预期：`['路得马丁']` 与 `['城市', '路德马丁']`（顺序以文件出现为准）

4) organic 仓库副本条数  
命令：`python qa4/notes/probe5/verify_independent.py 4`  
预期：`70 ['content', 'name', 'title'] 2ab34918389a6640`

5) v2.1 解析「诗八九26」  
命令：`python qa4/notes/probe5/verify_independent.py 5`  
预期：输出中含 `诗89:26`

---

## 验证

- 本轮新增均在 `qa4/notes/`（报告/脚本/CSV/中间 json）；`git diff --stat` 为空（无已跟踪改动）。
- 工作区另有既有未跟踪文件（如 `docs/panai4_graph/export_pack.md` 等），非本轮产出。
