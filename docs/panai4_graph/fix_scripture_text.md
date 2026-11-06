# neo4j-v4：修正 3 个 Scripture.text 为完整版

生成时间：2026-11-06 22:45:45；脚本：`panai4.graph.fix_scripture_text`。
只 SET `s.text`；不动 ref / 关系 / 其他节点；未改其他 49 个冲突 ref。
未运行 build_v4.py；未打印密码；未修改已有脚本 / .gitignore。

## 摘要

1. **源**：`C:\Users\28121\Desktop\可导入资料\节点一般标注.json`
2. **闸门**：check_ok=True fails=[]
3. **fix**：{'aborted': False, 'updated': {'约壹二15～16': {'len': 75, 'text': '不要爱世界，和世界上的事。人若爱世界，爱父的心就不在他里面了；因为凡世界上的事，就是肉体的情欲、眼目的情欲、并今生的骄傲，都不是出于父，乃是出于世界。'}, '何十三14': {'len': 56, 'text': '我必救赎他们脱离阴间的权势，救赎他们脱离死亡。死亡阿，你的灾害在那里？阴间哪，你的毁灭在那里？在我眼前绝无后悔。'}, '罗十六5': {'len': 38, 'text': '又问在他们家中的召会安。问我所亲爱的以拜尼土安，他是亚西亚归基督初结的果子。'}}}
4. **verify**：ok=True fails=[]

## check：版本与图谱现状

### `约壹二15～16`
- 版本数=2；短=31 长=75；短是长的前缀=True；短是子串=True
- 图谱修改前 len=31 indeg=2
- 修改前 text 全文：不要爱世界，和世界上的事。人若爱世界，爱父的心就不在他里面了；
- 完整版 text 全文：不要爱世界，和世界上的事。人若爱世界，爱父的心就不在他里面了；因为凡世界上的事，就是肉体的情欲、眼目的情欲、并今生的骄傲，都不是出于父，乃是出于世界。

### `何十三14`
- 版本数=2；短=48 长=56；短是长的前缀=False；短是子串=True
- 图谱修改前 len=48 indeg=2
- 修改前 text 全文：阴间的权势，救赎他们脱离死亡。死亡阿，你的灾害在那里？阴间哪，你的毁灭在那里？在我眼前绝无后悔。
- 完整版 text 全文：我必救赎他们脱离阴间的权势，救赎他们脱离死亡。死亡阿，你的灾害在那里？阴间哪，你的毁灭在那里？在我眼前绝无后悔。

### `罗十六5`
- 版本数=2；短=12 长=38；短是长的前缀=True；短是子串=True
- 图谱修改前 len=12 indeg=2
- 修改前 text 全文：又问在他们家中的召会安。
- 完整版 text 全文：又问在他们家中的召会安。问我所亲爱的以拜尼土安，他是亚西亚归基督初结的果子。

## fix
```json
{
  "约壹二15～16": {
    "len": 75
  },
  "何十三14": {
    "len": 56
  },
  "罗十六5": {
    "len": 38
  }
}
```

## verify
- Scripture=4851 SUPPORTED_BY=9768
- nodes=7334 rels=52197
- changed_refs=['何十三14', '约壹二15～16', '罗十六5']
- indegree_before={'约壹二15～16': 2, '何十三14': 2, '罗十六5': 2}
- indegree_after={'约壹二15～16': 2, '何十三14': 2, '罗十六5': 2}

### 修改后 text 全文

- `约壹二15～16`（len=75）：不要爱世界，和世界上的事。人若爱世界，爱父的心就不在他里面了；因为凡世界上的事，就是肉体的情欲、眼目的情欲、并今生的骄傲，都不是出于父，乃是出于世界。
- `何十三14`（len=56）：我必救赎他们脱离阴间的权势，救赎他们脱离死亡。死亡阿，你的灾害在那里？阴间哪，你的毁灭在那里？在我眼前绝无后悔。
- `罗十六5`（len=38）：又问在他们家中的召会安。问我所亲爱的以拜尼土安，他是亚西亚归基督初结的果子。

- anno_compare={"devine_argument": {"before_n": 187, "now_n": 187, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "intrinsic_significance": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "mutuality": {"before_n": 116, "now_n": 116, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "organic_advance": {"before_n": 69, "now_n": 69, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "name_en": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "greek_terms": {"before_n": 2257, "now_n": 2257, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "hebrew_terms": {"before_n": 1523, "now_n": 1523, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "definition_3a": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "definition_3b": {"before_n": 2062, "now_n": 2062, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "high_peak_content": {"before_n": 87, "now_n": 87, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}}
- fails=[]

## 最终验证
- 未修改已有 import_*.py / fix 以外脚本 / .gitignore
- 未运行 build_v4.py
- 报告与日志密码检查：通过（仅变量名）
- 未碰 high_peak_content；未做括号内复制；未删文件
- 日志：`G:\copypan\logs\fix_scripture_text_verify_20261106_224543.log`
