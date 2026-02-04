from es_config import es


def get_mappings(tp):
    mappings = {
        "read": {
            "mappings": {
                "properties": {
                    "refid": {"type": "keyword"},
                    "bread": {"type": "nested"},
                    "zh": {"type": "keyword"},
                    "en": {"type": "keyword"},
                    "cells": {"type": "nested"},
                    "type": {"type": "keyword"},
                    "toc": {"type": "nested"},
                }
            }
        },
        "index": {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "text": {"type": "text"},
                    "zh": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                    },
                    "en": {"type": "text"},
                    "title": {"type": "keyword"},
                    "order": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    "source": {"type": "keyword"},
                }
            }
        },
        "map": {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "text": {"type": "text"},
                    "msg": {"type": "nested"},
                    "sn": {"type": "keyword"},
                    "source": {"type": "keyword"},
                }
            }
        },
    }
    return mappings[tp]


all_index = [
    ["bib", "index"],
    ["cws_cont", "map"],
    ["cws_lee", "map"],
    ["cws_nee", "map"],
    ["cwwl", "index"],
    ["cwwl_booknames", "index"],
    ["cwwl_headings", "index"],
    ["cwwl_titles", "index"],
    ["cwwn", "index"],
    ["cwwn_booknames", "index"],
    ["cwwn_headings", "index"],
    ["cwwn_titles", "index"],
    ["feasts", "index"],
    ["feasts_booknames", "index"],
    ["feasts_ot1", "index"],
    ["feasts_titles", "index"],
    ["foo", "index"],
    ["hymn", "index"],
    ["life", "index"],
    ["life_headings", "index"],
    ["life_titles", "index"],
    ["map_cont_bookname", "map"],
    ["map_cont_title", "map"],
    ["map_feasts_bookname", "map"],
    ["map_feasts_title", "map"],
    ["map_hymn", "map"],
    ["map_lee_bookname", "map"],
    ["map_lee_title", "map"],
    ["map_life", "map"],
    ["map_nee_bookname", "map"],
    ["map_nee_title", "map"],
    ["map_note", "map"],
    ["map_others", "map"],
    ["map_pano_bookname", "map"],
    ["map_pano_title", "map"],
    ["others", "index"],
    ["others_booknames", "index"],
    ["others_headings", "index"],
    ["others_titles", "index"],
    ["pan_reading", "read"],
    ["pano", "index"],
    ["pano_booknames", "index"],
    ["pano_headings", "index"],
    ["pano_msg", "index"],
    ["pano_ot1", "index"],
    ["pano_outlines", "index"],
    ["pano_titles", "index"],
]


def is_index_exists(index_name):
    return es.indices.exists(index=index_name)


for item in all_index:
    index = item[0]
    mapping = get_mappings(item[1])

    if is_index_exists(index):
        es.indices.delete(index=index)
        print(f"index {index} already exists, and was deleted")

    es.indices.create(index=index, body=mapping)
    print(f"create index {index}")
