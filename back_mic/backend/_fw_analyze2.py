# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from es_config import es

texts = ["神成为人，使人成为神", "神人", "神人调和"]
result = {}
for text in texts:
    r = es.indices.analyze(index='filewall', body={"analyzer": "ik_max_word", "text": text})
    tokens = [t["token"] for t in r["tokens"]]
    result[text] = tokens

with open('_fw_analyze_result.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("done")
