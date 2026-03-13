from elasticsearch import Elasticsearch
from dotenv import load_dotenv
import os, json

load_dotenv('back_mic/backend/.env')

es = Elasticsearch(
    "http://localhost:9200",
    basic_auth=("elastic", os.getenv("ES_PASSWORD")),
)

def export_all():
    os.makedirs("scripts/kg_export", exist_ok=True)
    
    indices = list(es.indices.get_alias(index="*").keys())
    indices = sorted([i for i in indices if not i.startswith(".")])
    print(f"共发现 {len(indices)} 个索引")
    
    for index_name in indices:
        output_path = f"scripts/kg_export/{index_name}.json"
        
        if os.path.exists(output_path):
            print(f"跳过（已存在）：{index_name}")
            continue
        
        try:
            docs = []
            resp = es.search(
                index=index_name,
                body={"query": {"match_all": {}}},
                scroll="5m",
                size=200
            )
            scroll_id = resp["_scroll_id"]
            hits = resp["hits"]["hits"]
            
            while hits:
                for hit in hits:
                    doc = hit["_source"]
                    doc["_id"] = hit["_id"]
                    docs.append(doc)
                resp = es.scroll(scroll_id=scroll_id, scroll="5m")
                scroll_id = resp["_scroll_id"]
                hits = resp["hits"]["hits"]
            
            es.clear_scroll(scroll_id=scroll_id)
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(docs, f, ensure_ascii=False, indent=2)
            
            print(f"OK {index_name}: {len(docs)} docs -> {output_path}")
        
        except Exception as e:
            print(f"FAIL {index_name}: {e}")

export_all()
