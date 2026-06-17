# testD/backend/check_index_sources.py
from testD.backend._bootstrap import ensure_main_backend_path
ensure_main_backend_path()

from es_config import es as es_client

indices = ["life", "cwwn", "cwwl", "others", "bib", "foo", "hymn", "feasts"]

for index in indices:
    resp = es_client.search(
        index=index,
        body={
            "query": {"function_score": {"functions": [{"random_score": {}}]}},
            "size": 5,
            "_source": ["source_zh", "book_title", "source", "title", "source_en"],
        }
    )
    print(f"\n=== {index} ===")
    for hit in resp["hits"]["hits"]:
        print(hit["_source"])
