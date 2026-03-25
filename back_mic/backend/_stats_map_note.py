# -*- coding: utf-8 -*-
import json

data = json.load(open(r'E:\12490_with_bib\kg-rag_map_note_chunks.json', encoding='utf-8'))
tokens = [d['tokens'] for d in data]
split_chunks = [d for d in data if '_p' in d['chunk_id'] and '_c' in d['chunk_id']]
short = [d for d in data if d['tokens'] < 150]
print('=== map_note 基本统计 ===')
print('chunk总数:', len(data))
print('字段数:', len(data[0]))
print(f'token: min={min(tokens)}, max={max(tokens)}, avg={sum(tokens)/len(tokens):.1f}')
print(f'拆分chunk数(_p后缀): {len(split_chunks)}')
print(f'短chunk(<150 tokens): {len(short)} ({len(short)/len(data)*100:.1f}%)')
print()
print('=== 字段覆盖 ===')
print('book_title样本:', data[0]['book_title'])
print('author样本:', data[0]['author'])
print('message_key样本:', data[0]['message_key'])
print('message_number样本:', data[0]['message_number'])
print('message_title样本:', data[0]['message_title'])
print('paragraph_type样本:', data[0]['paragraph_type'])
print('en样本:', repr(data[0]['en']))
print('source_zh样本:', data[0]['source_zh'])
print('year样本:', data[0]['year'])
print('scripture_refs非空:', sum(1 for d in data if d['scripture_refs']))
print()
print('=== chunk_id 格式验证 ===')
c1 = [d for d in data if d['chunk_id'].endswith('_c1')]
c2 = [d for d in data if d['chunk_id'].endswith('_c2')]
print(f'_c1 chunks: {len(c1)}')
print(f'_c2 chunks: {len(c2)}')
print('chunk_id样本:', data[0]['chunk_id'], data[1]['chunk_id'] if len(data) > 1 else '')
print()
print('=== 抽样 ===')
print(json.dumps(data[0], ensure_ascii=False, indent=2))
