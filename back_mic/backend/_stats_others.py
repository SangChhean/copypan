# -*- coding: utf-8 -*-
import json

data = json.load(open(r'E:\12490_with_bib\kg-rag_others_chunks.json', encoding='utf-8'))
tokens = [d['tokens'] for d in data]
merged = [d for d in data if len(d['original_ids']) > 1]
split_chunks = [d for d in data if '_p' in d['chunk_id']]
print('=== others 基本统计 ===')
print('chunk总数:', len(data))
print('字段数:', len(data[0]))
print(f'token: min={min(tokens)}, max={max(tokens)}, avg={sum(tokens)/len(tokens):.1f}')
print(f'合并chunk数: {len(merged)} ({len(merged)/len(data)*100:.1f}%)')
print(f'拆分chunk数: {len(split_chunks)}')
print(f'空token(=0)数: {sum(1 for t in tokens if t == 0)}')
print()
print('=== 字段覆盖 ===')
print('book_title覆盖:', sum(1 for d in data if d['book_title']) / len(data))
print('message_key样本:', data[0]['message_key'])
print('message_number样本:', data[0]['message_number'])
print('author样本:', data[0]['author'])
print()
print('=== ID 变体验证 ===')
variant = [d for d in data if '-' in d['message_key'].split('others_')[1].split('_')[0]]
print(f'含连字符系列标识的chunk数: {len(variant)}')
if variant:
    print('变体message_key样本:', variant[0]['message_key'])
print()
print('=== 抽样 ===')
print(json.dumps(data[0], ensure_ascii=False, indent=2))
