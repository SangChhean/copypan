# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from es_config import es

texts = ["神成为人，使人成为神", "神人", "神人调和"]
for text in texts:
    r = es.indices.analyze(index='filewall', body={"analyzer": "ik_max_word", "text": text})
    tokens = [t["token"] for t in r["tokens"]]
    print(f"\ntext={repr(text)}")
    print(f"tokens={tokens}")
