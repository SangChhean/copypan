# neo4j-v4：括号外 → 括号内 标注与关系复制（8 对）

生成时间：2026-11-06 22:52:15；脚本：`panai4.graph.copy_to_bracket_inner`。
复制属性白名单（不含 name/same_as）；复制 29 种语义关系 + SUPPORTED_BY；不复制 4 种分类关系；不复制 O↔I。
只替换本端；`same_as` 保留。复制是快照——括号外以后再改，需重新同步。
未运行 build_v4.py；未打印密码；未修改已有脚本 / .gitignore。

## 摘要

1. **对数**：8；预期新增关系=229
2. **cross 端点情形**：n=0 → []
3. **闸门**：check_ok=True fails=[]
4. **copy**：{'aborted': False, 'progress': [{'inner': '产生得胜者', 'outer': '产生男孩子', 'new_rels': 3, 'props': 6}, {'inner': '圣灵的浇灌', 'outer': '那灵的浇灌', 'new_rels': 79, 'props': 7}, {'inner': '地狱', 'outer': '火湖', 'new_rels': 39, 'props': 5}, {'inner': '女人', 'outer': '妇人', 'new_rels': 5, 'props': 6}, {'inner': '忧虑', 'outer': '挂虑', 'new_rels': 6, 'props': 6}, {'inner': '扩展', 'outer': '扩增', 'new_rels': 5, 'props': 5}, {'inner': '显大', 'outer': '扩大', 'new_rels': 4, 'props': 5}, {'inner': '晨兴', 'outer': '晨晨复兴', 'new_rels': 88, 'props': 6}], 'total_new': 229, 'expected_total': 229}
5. **verify**：ok=True fails=[]

## check 明细（8 对）

### 产生男孩子 → 产生得胜者
- 外节点标注：['definition_3a', 'definition_3b', 'devine_argument', 'greek_terms', 'intrinsic_significance', 'name_en']（n=6）
- 出边按类型：{'SUPPORTED_BY': 3}；SUPPORTED_BY 出=3
- 入边按类型：{}；SUPPORTED_BY 入=0
- 预期新增：3
- O↔I 关系（不复制）：[]
- cross 端点：[]

### 那灵的浇灌 → 圣灵的浇灌
- 外节点标注：['definition_3a', 'definition_3b', 'devine_argument', 'greek_terms', 'hebrew_terms', 'intrinsic_significance', 'name_en']（n=7）
- 出边按类型：{'LEADS_TO': 17, 'LOCATED_IN': 5, 'CAUSES': 29, 'SIMULTANEOUS_WITH': 1, 'SUPPORTED_BY': 5}；SUPPORTED_BY 出=5
- 入边按类型：{'EXPERIENCES_ENJOYS': 22}；SUPPORTED_BY 入=0
- 预期新增：79
- O↔I 关系（不复制）：[]
- cross 端点：[]

### 火湖 → 地狱
- 外节点标注：['definition_3a', 'definition_3b', 'greek_terms', 'intrinsic_significance', 'name_en']（n=5）
- 出边按类型：{'SUPPORTED_BY': 4}；SUPPORTED_BY 出=4
- 入边按类型：{'LOCATED_IN': 3, 'CAUSES': 20, 'OPPOSES_CONTRASTS_WITH': 12}；SUPPORTED_BY 入=0
- 预期新增：39
- O↔I 关系（不复制）：[]
- cross 端点：[]

### 妇人 → 女人
- 外节点标注：['definition_3a', 'definition_3b', 'greek_terms', 'hebrew_terms', 'intrinsic_significance', 'name_en']（n=6）
- 出边按类型：{'SUPPORTED_BY': 5}；SUPPORTED_BY 出=5
- 入边按类型：{}；SUPPORTED_BY 入=0
- 预期新增：5
- O↔I 关系（不复制）：[]
- cross 端点：[]

### 挂虑 → 忧虑
- 外节点标注：['definition_3a', 'definition_3b', 'greek_terms', 'hebrew_terms', 'intrinsic_significance', 'name_en']（n=6）
- 出边按类型：{'SUPPORTED_BY': 5}；SUPPORTED_BY 出=5
- 入边按类型：{'OPPOSES_CONTRASTS_WITH': 1}；SUPPORTED_BY 入=0
- 预期新增：6
- O↔I 关系（不复制）：[]
- cross 端点：[]

### 扩增 → 扩展
- 外节点标注：['definition_3a', 'definition_3b', 'greek_terms', 'intrinsic_significance', 'name_en']（n=5）
- 出边按类型：{'SUPPORTED_BY': 5}；SUPPORTED_BY 出=5
- 入边按类型：{}；SUPPORTED_BY 入=0
- 预期新增：5
- O↔I 关系（不复制）：[]
- cross 端点：[]

### 扩大 → 显大
- 外节点标注：['definition_3a', 'definition_3b', 'greek_terms', 'intrinsic_significance', 'name_en']（n=5）
- 出边按类型：{'SUPPORTED_BY': 4}；SUPPORTED_BY 出=4
- 入边按类型：{}；SUPPORTED_BY 入=0
- 预期新增：4
- O↔I 关系（不复制）：[]
- cross 端点：[]

### 晨晨复兴 → 晨兴
- 外节点标注：['definition_3a', 'definition_3b', 'greek_terms', 'hebrew_terms', 'intrinsic_significance', 'name_en']（n=6）
- 出边按类型：{'LEADS_TO': 38, 'SUPPORTED_BY': 4}；SUPPORTED_BY 出=4
- 入边按类型：{'PRACTICED_AS': 46}；SUPPORTED_BY 入=0
- 预期新增：88
- O↔I 关系（不复制）：[]
- cross 端点：[]

- 基线 nodes=7334 rels=52197

## copy
```json
{
  "aborted": false,
  "progress": [
    {
      "inner": "产生得胜者",
      "outer": "产生男孩子",
      "new_rels": 3,
      "props": 6
    },
    {
      "inner": "圣灵的浇灌",
      "outer": "那灵的浇灌",
      "new_rels": 79,
      "props": 7
    },
    {
      "inner": "地狱",
      "outer": "火湖",
      "new_rels": 39,
      "props": 5
    },
    {
      "inner": "女人",
      "outer": "妇人",
      "new_rels": 5,
      "props": 6
    },
    {
      "inner": "忧虑",
      "outer": "挂虑",
      "new_rels": 6,
      "props": 6
    },
    {
      "inner": "扩展",
      "outer": "扩增",
      "new_rels": 5,
      "props": 5
    },
    {
      "inner": "显大",
      "outer": "扩大",
      "new_rels": 4,
      "props": 5
    },
    {
      "inner": "晨兴",
      "outer": "晨晨复兴",
      "new_rels": 88,
      "props": 6
    }
  ],
  "total_new": 229,
  "expected_total": 229
}
```

## verify
- nodes=7334 rels=52426 expect=52426
- Scripture=4851 SUPPORTED_BY=9803
- new_by_type={'SUPPORTED_BY': 35, 'LEADS_TO': 55, 'LOCATED_IN': 8, 'CAUSES': 49, 'SIMULTANEOUS_WITH': 1, 'EXPERIENCES_ENJOYS': 22, 'OPPOSES_CONTRASTS_WITH': 13, 'PRACTICED_AS': 46}
- pair_verify=[{"inner": "产生得胜者", "outer": "产生男孩子", "props": ["definition_3a", "definition_3b", "devine_argument", "greek_terms", "intrinsic_significance", "name_en"], "out": {"SUPPORTED_BY": 3}, "in": {}, "same_as": "产生男孩子"}, {"inner": "圣灵的浇灌", "outer": "那灵的浇灌", "props": ["definition_3a", "definition_3b", "devine_argument", "greek_terms", "hebrew_terms", "intrinsic_significance", "name_en"], "out": {"LEADS_TO": 17, "LOCATED_IN": 5, "CAUSES": 29, "SIMULTANEOUS_WITH": 1, "SUPPORTED_BY": 5}, "in": {"EXPERIENCES_ENJOYS": 22}, "same_as": "那灵的浇灌"}, {"inner": "地狱", "outer": "火湖", "props": ["definition_3a", "definition_3b", "greek_terms", "intrinsic_significance", "name_en"], "out": {"SUPPORTED_BY": 4}, "in": {"OPPOSES_CONTRASTS_WITH": 12, "CAUSES": 20, "LOCATED_IN": 3}, "same_as": "火湖"}, {"inner": "女人", "outer": "妇人", "props": ["definition_3a", "definition_3b", "greek_terms", "hebrew_terms", "intrinsic_significance", "name_en"], "out": {"SUPPORTED_BY": 5}, "in": {}, "same_as": "妇人"}, {"inner": "忧虑", "outer": "挂虑", "props": ["definition_3a", "definition_3b", "greek_terms", "hebrew_terms", "intrinsic_significance", "name_en"], "out": {"SUPPORTED_BY": 5}, "in": {"OPPOSES_CONTRASTS_WITH": 1}, "same_as": "挂虑"}, {"inner": "扩展", "outer": "扩增", "props": ["definition_3a", "definition_3b", "greek_terms", "intrinsic_significance", "name_en"], "out": {"SUPPORTED_BY": 5}, "in": {}, "same_as": "扩增"}, {"inner": "显大", "outer": "扩大", "props": ["definition_3a", "definition_3b", "greek_terms", "intrinsic_significance", "name_en"], "out": {"SUPPORTED_BY": 4}, "in": {}, "same_as": "扩大"}, {"inner": "晨兴", "outer": "晨晨复兴", "props": ["definition_3a", "definition_3b", "greek_terms", "hebrew_terms", "intrinsic_significance", "name_en"], "out": {"LEADS_TO": 38, "SUPPORTED_BY": 4}, "in": {"PRACTICED_AS": 46}, "same_as": "晨晨复兴"}]
- samples=[{"inner": "产生得胜者", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "产生得胜者", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "圣灵的浇灌", "dir": "out", "type": "LEADS_TO", "ok": true}, {"inner": "圣灵的浇灌", "dir": "out", "type": "LEADS_TO", "ok": true}, {"inner": "地狱", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "地狱", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "女人", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "女人", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "忧虑", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "忧虑", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "扩展", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "扩展", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "显大", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "显大", "dir": "out", "type": "SUPPORTED_BY", "ok": true}, {"inner": "晨兴", "dir": "out", "type": "LEADS_TO", "ok": true}, {"inner": "晨兴", "dir": "out", "type": "LEADS_TO", "ok": true}]
- fails=[]

## 最终说明
- `same_as` 保留，未删除
- 复制是快照；括号外节点以后再改标注或关系，要重新同步
- 未修改已有脚本；未运行 build_v4.py；密码检查通过（仅变量名）
- 未删文件；未改括号外节点
- 日志：`G:\copypan\logs\copy_to_bracket_inner_verify_20261106_225213.log`
