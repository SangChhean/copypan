# -*- coding: utf-8 -*-
import json

data = json.load(open(r'E:\12490_with_bib\kg-rag_cwwn_chunks.json', encoding='utf-8'))
tokens = [d['tokens'] for d in data]
merged = [d for d in data if len(d['original_ids']) > 1]
split_chunks = [d for d in data if '_p' in d['chunk_id']]
print('=== cwwn 基本统计 ===')
print('chunk总数:', len(data))
print('字段数:', len(data[0]))
print(f'token: min={min(tokens)}, max={max(tokens)}, avg={sum(tokens)/len(tokens):.1f}')
print(f'合并chunk数: {len(merged)} ({len(merged)/len(data)*100:.1f}%)')
print(f'拆分chunk数: {len(split_chunks)}')
print()
print('=== 字段覆盖 ===')
print('book_title覆盖:', sum(1 for d in data if d['book_title']) / len(data))
print('message_key样本:', data[0]['message_key'])
print('message_number样本:', data[0]['message_number'])
print('author样本:', data[0]['author'])
print('year样本:', data[0]['year'])
print('section_title非空:', sum(1 for d in data if d['section_title']))
print()
print('=== 抽样 ===')
if split_chunks:
    print('拆分chunk样本:', json.dumps(split_chunks[0], ensure_ascii=False, indent=2))
else:
    print('无拆分chunk')
print()
print('字段列表:', sorted(data[0].keys()))
