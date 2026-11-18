# qa4 后端构建前核对 · 第六轮（一）

约束：只读；未改既有文件；未 git add/commit/push；未联网；未连 ES/Neo4j/Redis；未读 `.env`。
产出：本报告；脚本 `qa4/notes/probe6/`。数字均由本轮脚本算出。

---

## A. organic_advance 新版结构

脚本：`python qa4/notes/probe6/a_organic.py`

- 基准：`G:\copypan\qa4\data\graph_annotations\organic_advance.json`
- SHA256 前16位：`2ab34918389a6640`（期望 2ab34918389a6640）→ **一致，继续**
- 顶层：list；条数 **70**；键 ['content', 'name', 'title']
- content 类型分布：{'str': 70}（均为 str）
- content 字数：min=2148 / median=2496.0 / max=2886
- title 字数：min=1 / median=5.0 / max=10；分布 {'1-10': 70}
- 不同 name：**69**；重名：{'圣经': 2}
- name=「圣经」两条：
  - title=`圣经—神的话`；content字数=2594；开头=`读经：提后三16～17，路二四27、44、46，约六63，启`
  - title=`圣经的结晶意义`；content字数=2413；开头=`读经：提后三16～17，约壹五11～12，太十六16、18，`

### content 内部（str）
- 行首类型：{'其他': 70, '天干序号(壹贰…)': 399, '地支/小写中文数(一二…)': 2254}
- 含「阶段」或「时期」的行数：345
- 阶段样例：['贰\u3000李常受弟兄职事第一阶段（1932-1960）：', '叁\u3000李常受弟兄职事第二阶段（1961-1973）：', '肆\u3000李常受弟兄职事第三阶段（1974-1984）：', '伍\u3000李常受弟兄职事第四阶段（1985-1990）：', '陆\u3000李常受弟兄职事高峰阶段（1991-1997）：']
- 天干标题样例：['壹\u3000倪柝声弟兄职事：', '贰\u3000李常受弟兄职事第一阶段（1932-1960）：', '叁\u3000李常受弟兄职事第二阶段（1961-1973）：', '肆\u3000李常受弟兄职事第三阶段（1974-1984）：', '伍\u3000李常受弟兄职事第四阶段（1985-1990）：']
- 非 str content：无

### 与旧版对照
- 旧版：`C:\Users\28121\Desktop\可导入资料\2 特殊标注\【organic_advance】生机关联的进展.json`；SHA前16=`63a2320504c535e5`（期望 63a2320504c535e5）
- 仅新版 name：['基督的十字架']
- 仅旧版 name：['基督的死']
- 共有 name 数：68；新/旧 content 字数比中位数：**0.0124**（旧版 content_1…6 为 list[dict] 的 JSON 字数远大于新版单段 str）
- 新版 title 与旧版同 name 的 series/stages 名称相同的条数：**60**

### 与图谱导入
- 文档：`docs/panai4_graph/import_organic_advance.md`；state：`logs/import_annotation_organic_advance_state.json`
- 当时只 SET `organic_advance=true`（布尔），**内容不入库**；写入 name 数：**69**
- 导入源 SHA：`63a2320504c535e5…`（旧版 69 条）；copy.n_records=69
- 与新版 69 个不同 name：**不完全相同** — {'file_n': 69, 'new_unique_n': 69, 'equal_to_new': False, 'only_in_import': ['基督的死'], 'only_in_new': ['基督的十字架']}
- 结论：图谱布尔旗标按旧版「基督的死」等 69 名写入；仓库 JSON 已换成新版（含「基督的十字架」、圣经双条）。

### 仓库内副本
- `G:\copypan\back_mic\backend\panai4\data\graph_annotations\organic_advance.json`｜498318 bytes｜sha16=`2ab34918389a6640`
- `G:\copypan\qa4\data\graph_annotations\organic_advance.json`｜498318 bytes｜sha16=`2ab34918389a6640`

---

## B. 经节补测

脚本：`python qa4/notes/probe6/b_verse.py`；V21=`C:\Users\28121\Desktop\get_vers_v2.1.py`（只读 import）

### B.1 3a 读经行整行重测
- 有读经行：**2365**
- 整行解析出≥1 出处：**2360**
- 出处总数：**23102**；其中 {'verse_or_range': 23097, 'whole_chapter': 5}
- 能在 bible_data 找到：**23102**（整章/单节范围均计入；本轮无跨章 tok）
- 零出处行：**5**；样例：['士六~九', '林后三 2~3、6、8', '利一~七38，八14，诗八四', '番一~三', '约十三']
- 遗漏启发式：DIGITISH_RE 匹配章节数字串个数 n；若 n>=3 且 n >= 解析出处数+2，计为疑似遗漏。 DIGITISH_RE=(?:[一二三四五六七八九十百千〇零○]+|\d+)(?:[～~－—\-](?:[一二三四五六七八九十百千〇零○]+|\d+))?
- 疑似遗漏行数：**23**；样例：[{'line30': '启一4，四5，五6，来四16，九12、24，二十11～15，', 'n_toks': 16, 'digitish_n': 33}, {'line30': '太四18~22，十六19，徒二14~41，四4，弗四12，彼', 'n_toks': 6, 'digitish_n': 14}, {'line30': '徒五15，雅六12，七11，约十七21~23，弗四3，六1，', 'n_toks': 5, 'digitish_n': 14}]
- 做法：整行不切分；每行 start_paragraph + parse_text；带 bible_data validate

### B.2 qa4_bible 的 v2.1 失败
- verses 总数 3625；校验后失败 **116**
- 按 book_title 前10：[['诗篇', 116]]
- 章号写法：{'汉字十位+阿拉伯0（如三0）': 103, '中文数后接0（广义）': 13}
- 正则 X0=`([一二三四五六七八九])0` 命中 103；补充 `十0`=`十0` 命中 12；合计 115/116
- 是否都符合仅 X0 正则：False（其余为「二十0」类，前接「十」）
- 脚本内把 X0→X十（并试 十0→十十）后成功数：**0**；仍失败 116
- 剩余失败类：
  - 汉字十位+阿拉伯0（如三0） ×103｜例 ['诗篇三0～8', '诗篇四0～8', '诗篇五0～12']
  - 中文数后接0（广义） ×13｜例 ['诗篇二十0～9', '诗篇三十0～12', '诗篇四十0～17']
- 说明：无校验时 `诗篇三0～8` 会解析成 `诗3:0-8`（节号0）；带校验则失败。`三0→三十` 后变成 `诗篇三十～8`，仍无 tok；**推测**需写成 `三十1～8` 才过（本轮未改规则，仅记录）。
- 失败样例：['诗篇三0～8', '诗篇四0～8', '诗篇五0～12', '诗篇六0～10', '诗篇七0～17', '诗篇八0～9', '诗篇九0～20', '诗篇十一0～7', '诗篇十二0～8', '诗篇十三0～6']

### B.3 「X0」在其它来源
- 正则：`([一二三四五六七八九])0`
- 图谱 chosen：universe=4851｜命中 **0**
- map_note 抽样(seed=20261116)：universe=2000｜命中 **0**
- 3a 读经行：universe=2365｜命中 **1**｜例 ['王上七16、18~19，太一5、5~16、18、20下~23']

---

## C. 图谱经节「贴后」排查

脚本：`python qa4/notes/probe6/c_tiehou.py`

### C.1 失败 6 个
- 失败数：6
- `贴后三5`｜所属词条：['爱神', '神的爱']
- `贴后二3`｜所属词条：['方法']
- `贴后三17`｜所属词条：['记号']
- `贴后二13`｜所属词条：['那灵的圣别']
- `贴后三16`｜所属词条：['平安']
- `贴后三1`｜所属词条：['主的话']

### C.2 改成「帖后」后是否已存在
- `贴后三5`→`帖后三5`｜已在 chosen：True｜改正后可解析：True
- `贴后二3`→`帖后二3`｜已在 chosen：False｜改正后可解析：True
- `贴后三17`→`帖后三17`｜已在 chosen：True｜改正后可解析：True
- `贴后二13`→`帖后二13`｜已在 chosen：True｜改正后可解析：True
- `贴后三16`→`帖后三16`｜已在 chosen：False｜改正后可解析：True
- `贴后三1`→`帖后三1`｜已在 chosen：False｜改正后可解析：True
- 已在 chosen 的 3 个：改正会产生 **Scripture 键重复**（需合并关系，不能简单改名）。

### C.3 「贴后」出现位置
- 节点一般标注：整文件 **7** 次；字段 `related_scriptures[].ref`；命中例：['[15].related_scriptures[2].ref', '[452].related_scriptures[2].ref', '[831].related_scriptures[4].ref', '[1211].related_scriptures[0].ref', '[1262].related_scriptures[4].ref', '[1427].related_scriptures[1].ref', '[2296].related_scriptures[3].ref']
- truth_dictionary_3a3b：content_3a 等字段 **1** 次；hit=[{'field': '[695].content_3a', 'snip': '读经：罗八30，创十一28，十二1，出二23~25，三7、9'}]
- bible_data：**0**
- 主干枝映射：**0**
- qa4_bible chunks：**0**
- map_note jsonl：**0**
- docs md：检索命中 1 处；例 [{'path': 'G:\\copypan\\docs\\panai4_es\\archive\\docx_checks.md', 'line': 306, 'snip': '- **经节简称**：只在 B 批的【带经文的纲目】里出现。'}]
- scripture state：整文件 **26** 次（含 chosen/link 等）

### C.4 简称收录（贴/帖）
- v2.1 BOOK_MAP 帖前：['帖前', '帖撒罗尼迦前书']
- v2.1 BOOK_MAP 帖后：['帖后', '帖撒罗尼迦后书']
- v2.1 含「贴」的键：无
- 3.0 bible_data 卷52 abbr_gb=`帖前` name=`帖撒罗尼迦前书`
- 3.0 bible_data 卷53 abbr_gb=`帖后` name=`帖撒罗尼迦后书`
- bible_ref_parser.py 源码中含贴/帖的行：无（简称来自 bible_data 名表，非写死贴）
- 结论：两侧都收「帖前/帖后」，**都不收「贴后」**。

### C.5 若要改图谱需要动的位置（只报告，未改）
- Scripture 节点 name/ref：`贴后三5`→`帖后三5`；关联 Truth_Point：['爱神', '神的爱']；关系：词条→经节链接；改名冲突=True
- Scripture 节点 name/ref：`贴后二3`→`帖后二3`；关联 Truth_Point：['方法']；关系：词条→经节链接；改名冲突=False
- Scripture 节点 name/ref：`贴后三17`→`帖后三17`；关联 Truth_Point：['记号']；关系：词条→经节链接；改名冲突=True
- Scripture 节点 name/ref：`贴后二13`→`帖后二13`；关联 Truth_Point：['那灵的圣别']；关系：词条→经节链接；改名冲突=True
- Scripture 节点 name/ref：`贴后三16`→`帖后三16`；关联 Truth_Point：['平安']；关系：词条→经节链接；改名冲突=False
- Scripture 节点 name/ref：`贴后三1`→`帖后三1`；关联 Truth_Point：['主的话']；关系：词条→经节链接；改名冲突=False
- 源数据同步：桌面 `节点一般标注.json` 的 `related_scriptures[].ref`（7 处）；再重跑经节导入/去重。
- 已存在「帖后*」的 3 个：应 **合并** 到已有 Scripture，并把边迁过去，勿新建重复节点。

---

## 独立核对命令

以下不依赖 probe6 脚本；在仓库根目录执行。

1) 新版 organic SHA 前16与条数
```
python -c "import hashlib,json;from pathlib import Path;p=Path(r'G:/copypan/qa4/data/graph_annotations/organic_advance.json');b=p.read_bytes();d=json.loads(b);print(hashlib.sha256(b).hexdigest()[:16], len(d), len({x['name'] for x in d}))
```
预期：`2ab34918389a6640 70 69`

2) 旧版 SHA 前16与条数
```
python -c "import hashlib,json;from pathlib import Path;p=Path(r'C:/Users/28121/Desktop/可导入资料/2 特殊标注/【organic_advance】生机关联的进展.json');b=p.read_bytes();d=json.loads(b);print(hashlib.sha256(b).hexdigest()[:16], len(d))
```
预期：`63a2320504c535e5 69`

3) 图谱 chosen 中含「贴后」的 ref
```
python -c "import json;from pathlib import Path;c=json.loads(Path(r'G:/copypan/logs/import_annotation_scripture_nodes_state.json').read_text(encoding='utf-8'))['chosen'];print(sorted(k for k in c if '贴后' in k))" 
```
预期：6 个 `贴后…` 字符串列表

4) v2.1 对「贴后三5」与「帖后三5」
```
python -c "import importlib.util;from pathlib import Path;p=Path(r'C:/Users/28121/Desktop/get_vers_v2.1.py');s=importlib.util.spec_from_file_location('v21',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for t in ['贴后三5','帖后三5']:
 vp=m.VerseParser();vp.start_paragraph();print(t, vp.parse_text(t))" 
```
预期：前者空列表；后者含 `帖后3:5` 一类 verses

5) qa4_bible 中「汉字+ASCII 0」的 verse_range 条数
```
python -c "import json,re;from pathlib import Path;n=0
for line in Path(r'G:/PanAI4.0专用/索引数据/panai4_bible/02_清洗JSON/chunks_bible.json').open(encoding='utf-8'):
 o=json.loads(line)
 if o.get('chunk_type')=='verses' and re.search(r'[一二三四五六七八九]0', o.get('verse_range') or ''): n+=1
print(n)" 
```
预期：接近 103～115 的整数（本轮失败集相关）

---

## 验证

- 本轮新增均在 `qa4/notes/`；`git diff --stat` 应为空。
