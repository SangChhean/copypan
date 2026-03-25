# -*- coding: utf-8 -*-
import json

data = json.load(open(r'E:\12490_with_bib\kg-rag_bib_chunks.json', encoding='utf-8'))
tokens = [d['tokens'] for d in data]
multi = [d for d in data if len(d['original_ids']) > 1]
single = [d for d in data if len(d['original_ids']) == 1]
print('=== bib 基本统计 ===')
print('chunk总数:', len(data))
print('字段数:', len(data[0]))
print(f'token: min={min(tokens)}, max={max(tokens)}, avg={sum(tokens)/len(tokens):.1f}')
print(f'多节合并chunk: {len(multi)} ({len(multi)/len(data)*100:.1f}%)')
print(f'单节chunk: {len(single)}')
print()
print('=== 字段覆盖 ===')
print('book_title样本:', data[0]['book_title'])
print('author样本:', data[0]['author'])
print('message_key样本:', data[0]['message_key'])
print('message_number样本:', data[0]['message_number'])
print('paragraph_type样本:', data[0]['paragraph_type'])
print('section_title样本:', data[0]['section_title'])
print('year样本:', data[0]['year'])
print()
print('=== chunk_id 格式验证 ===')
print('多节样本id:', multi[0]['chunk_id'] if multi else 'N/A')
print('单节样本id:', single[0]['chunk_id'] if single else 'N/A')
print('多节original_ids:', multi[0]['original_ids'][:5] if multi else 'N/A')
print()
print('=== 抽样：多节合并chunk ===')
if multi:
    print(json.dumps(multi[0], ensure_ascii=False, indent=2))
