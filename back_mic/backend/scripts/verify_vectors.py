# -*- coding: utf-8 -*-
import sys
import os
_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_script_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
from es_config import es

# 验证段落型
r = es.search(index='cwwl', body={'query': {'exists': {'field': 'embedding'}}, '_source': ['id', 'embedding']}, size=1)
hit = r['hits']['hits'][0]
emb = hit['_source']['embedding']
print('cwwl embedding 维度: {}, 前3个值: {}'.format(len(emb), emb[:3]))

# 验证纲目型 chunks
r = es.search(index='map_note_chunks', size=1)
hit = r['hits']['hits'][0]
emb = hit['_source']['embedding']
print('map_note_chunks chunk_id: {}'.format(hit['_source']['chunk_id']))
print('map_note_chunks embedding 维度: {}, 前3个值: {}'.format(len(emb), emb[:3]))

# 验证经文型
r = es.search(index='bib', body={'query': {'exists': {'field': 'embedding'}}, '_source': ['id', 'embedding']}, size=1)
hit = r['hits']['hits'][0]
emb = hit['_source']['embedding']
print('bib embedding 维度: {}, 前3个值: {}'.format(len(emb), emb[:3]))
