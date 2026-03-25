# -*- coding: utf-8 -*-
import json

data = json.load(open(r'E:\12490_with_bib\kg-rag_life_chunks.json', encoding='utf-8'))
tokens = [d['tokens'] for d in data]
merged = [d for d in data if len(d['original_ids']) > 1]
print('=== 基本统计 ===')
print('chunk总数:', len(data))
print('字段数:', len(data[0]))
print(f'token: min={min(tokens)}, max={max(tokens)}, avg={sum(tokens)/len(tokens):.1f}')
print(f'合并chunk数: {len(merged)} ({len(merged)/len(data)*100:.1f}%)')
print()
print('=== 字段覆盖 ===')
print('book_title覆盖:', sum(1 for d in data if d['book_title']) / len(data))
print('message_key样本:', data[0]['message_key'])
print('message_number样本:', data[0]['message_number'])
print('year样本:', data[0]['year'])
print('section_title非空:', sum(1 for d in data if d['section_title']))
print('scripture_refs非空:', sum(1 for d in data if d['scripture_refs']))
print('en非空:', sum(1 for d in data if d.get('en')) / len(data))
print()
print('=== 字段列表 ===')
print(sorted(data[0].keys()))
print()
print('=== 抽样：合并chunk ===')
if merged:
    print(json.dumps(merged[0], ensure_ascii=False, indent=2))
print()
print('=== 抽样：单段chunk ===')
single = [d for d in data if len(d['original_ids']) == 1]
if single:
    print(json.dumps(single[0], ensure_ascii=False, indent=2))
