# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from es_config import es

# 1. 读 filewall_rules.json 的标题
rules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'filewall_rules.json')
with open(rules_path, encoding='utf-8') as f:
    rules = json.load(f)
rule_titles = [r['title'] for r in rules if r.get('title')]
print(f'filewall_rules.json 共 {len(rule_titles)} 条标题')
print(f'示例标题: {repr(rule_titles[0])}')

# 2. 用 get 直接取 filewall_1，对比 text 字段的字节
doc = es.get(index='filewall', id='filewall_1')
es_text = doc['_source']['text']
print(f'\nES filewall_1 text (repr): {repr(es_text)}')
print(f'ES filewall_1 text bytes (utf-8): {es_text.encode("utf-8")[:60]}')

# 3. 对比 rule 第一个标题
rt = rule_titles[0]
print(f'\nrule[0] title (repr): {repr(rt)}')
print(f'rule[0] title bytes (utf-8): {rt.encode("utf-8")[:60]}')
print(f'ES text == rule title: {es_text.strip() == rt.strip()}')

# 4. 用 rule 标题做 match_phrase 查询
r = es.search(index='filewall', body={
    'query': {'match_phrase': {'text': rt}},
    'size': 1, '_source': ['id', 'text']
})
print(f'\nmatch_phrase with rule title hits: {r["hits"]["total"]["value"]}')

# 5. 用 match (不 phrase) 查
r2 = es.search(index='filewall', body={
    'query': {'match': {'text': rt}},
    'size': 1, '_source': ['id', 'text']
})
print(f'match (no phrase) with rule title hits: {r2["hits"]["total"]["value"]}')

# 6. match_all 确认索引里有文档
r3 = es.count(index='filewall')
print(f'\nfilewall 文档总数: {r3["count"]}')

# 7. 写文件供人工确认
with open('_fw_query3_result.json', 'w', encoding='utf-8') as f:
    json.dump({
        'rule_title_repr': repr(rt),
        'es_text_repr': repr(es_text),
        'equal': es_text.strip() == rt.strip(),
        'rule_title_bytes_hex': es_text.encode('utf-8').hex()[:40],
        'es_text_bytes_hex': rt.encode('utf-8').hex()[:40],
    }, f, ensure_ascii=False, indent=2)
print('详细结果已写入 _fw_query3_result.json')
