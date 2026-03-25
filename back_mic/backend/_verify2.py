# -*- coding: utf-8 -*-
from kg_rag.scripts.chunking_full import parse_title, estimate_tokens, extract_scripture_refs, split_by_punctuation

r1 = parse_title('彼得前书生命读经，第十二篇\u3000三一神完全的救恩')
assert r1 == ('彼得前书生命读经', '第十二篇\u3000三一神完全的救恩'), f"fail 1: {r1}"

r2 = estimate_tokens('abc')
assert r2 == 2, f"fail 2: {r2}"

refs = extract_scripture_refs('这段话（约三16）和（罗八2）很重要')
assert len(refs) == 2, f"fail 3: {refs}"

empty = extract_scripture_refs('（这是约定的事）')
assert empty == [], f"fail 4: {empty}"

print('ALL PASS')
