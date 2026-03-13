from elasticsearch import Elasticsearch
from dotenv import load_dotenv
import os, json

load_dotenv('back_mic/backend/.env')

es = Elasticsearch(
    "http://localhost:9200",
    basic_auth=("elastic", os.getenv("ES_PASSWORD")),
)

def export_large_index(index_name):
    """Stream export for large indices"""
    output_path = f"scripts/kg_export/{index_name}.json"
    
    print(f"Exporting {index_name}...")
    
    resp = es.search(
        index=index_name,
        body={"query": {"match_all": {}}},
        scroll="5m",
        size=100
    )
    scroll_id = resp["_scroll_id"]
    hits = resp["hits"]["hits"]
    total = resp["hits"]["total"]["value"]
    
    print(f"Total docs: {total}")
    
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("[\n")
        first = True
        
        while hits:
            for hit in hits:
                doc = hit["_source"]
                doc["_id"] = hit["_id"]
                
                if not first:
                    f.write(",\n")
                first = False
                
                json.dump(doc, f, ensure_ascii=False)
                count += 1
                
            if count % 10000 == 0:
                print(f"  Processed {count}/{total} ({100*count//total}%)")
            
            resp = es.scroll(scroll_id=scroll_id, scroll="5m")
            scroll_id = resp["_scroll_id"]
            hits = resp["hits"]["hits"]
        
        f.write("\n]")
    
    es.clear_scroll(scroll_id=scroll_id)
    print(f"OK {index_name}: {count} docs -> {output_path}")

export_large_index("cwwl")
