# PanAI 3.5 ES 现况勘探报告

- 勘探时间：2026-09-29 09:07（本机 UTC+7）
- 方式：只读。ES 只用了 `_cat`、`_mapping`、`_settings`、`_count`、`_search`、`_analyze`、`cluster.health`；Neo4j 只用 READ_ACCESS 会话读 `db.propertyKeys()`；文件只做了列目录、读取、统计。没有对 ES、Neo4j、SQLite 做任何写入。
- 对照文档：仓库根目录 `KG-RAG_Chunking方案_v7.md`（下称「v7」）。
- 本报告不转录任何密码。仓库里有两处明文 ES 密码：`back_mic/backend/scripts/reindex_local.py` 第 12 行的注释、`back_mic/backend/kg_rag/scripts/index_to_es_full.py` 第 12 行的说明文字，报告只注明位置。

---

## 一、ES 索引实况

### 1.1 本机 ES

| 项 | 值 |
|---|---|
| 地址 | `http://localhost:9200`（Docker 容器 `elasticsearch8`，镜像 `elasticsearch:8.19.0`） |
| 版本 | 8.19.0 |
| 集群 | `docker-cluster`，单节点 |
| 健康 | yellow；active_shards 60，unassigned_shards 47，active_shards_percent 56.07%（单节点，旧索引 replicas=1 无法分配） |
| 插件 | `analysis-ik` 8.19.0 |
| 索引数 | 56 个（不含隐藏索引 `.security-7`） |
| 9 个 `kg-rag_*` 合计 store.size | 7,848,516,148 字节（约 7.31 GiB，7,849 MB） |

连接配置在 `back_mic/backend/es_config.py`：读取 `back_mic/backend/.env` 里的 `ES_HOST`（本机值 `localhost`）、`ES_PORT`（`9200`）、`ES_USERNAME`（`elastic`）、`ES_PASSWORD`（已设置），拼成 `http://{ES_HOST}:{ES_PORT}`，用 basic_auth 连接，请求超时 60 秒。3.5 检索用的就是这个客户端（`kg_rag_router.py` 第 50 行 `from es_config import es`）。

### 1.2 全部索引清单

- 「docs（_count）」是 `_count` 的顶层文档数；「docs（_cat）」是 `_cat/indices` 的 Lucene 文档数，nested 字段会让它大于顶层数。
- 「embedding 非空」用 `{"exists": {"field": "embedding"}}` 的 `_count` 统计。
- 维度与 similarity 取自 mapping；「无」表示该索引 mapping 里没有 dense_vector 字段。

| 索引 | health | docs（_count） | docs（_cat） | store.size（字节） | 有 embedding 字段 | dense_vector 维度 | similarity | embedding 非空 |
|---|---|---:|---:|---:|---|---|---|---:|
| `bib` | yellow | 31,102 | 31,102 | 42,735,263 | 是（`embedding`） | 512 | cosine | 1,193 |
| `cws_cont` | yellow | 14 | 14 | 696,060 | 否 | 无 | 无 | 无 |
| `cws_cont_titles` | yellow | 436 | 436 | 790,849 | 否 | 无 | 无 | 无 |
| `cws_lee` | yellow | 1,140 | 1,140 | 16,683,493 | 否 | 无 | 无 | 无 |
| `cws_lee_titles` | yellow | 8,435 | 8,435 | 18,669,975 | 否 | 无 | 无 | 无 |
| `cws_life_titles` | yellow | 1,983 | 1,983 | 3,249,815 | 否 | 无 | 无 | 无 |
| `cws_nee` | yellow | 62 | 62 | 2,810,356 | 否 | 无 | 无 | 无 |
| `cws_nee_titles` | yellow | 1,336 | 1,336 | 2,969,013 | 否 | 无 | 无 | 无 |
| `cws_others_titles` | yellow | 301 | 301 | 585,074 | 否 | 无 | 无 | 无 |
| `cwwl` | yellow | 319,753 | 319,753 | 3,245,522,465 | 是（`embedding`） | 512 | cosine | 235,432 |
| `cwwl_booknames` | yellow | 1,135 | 1,135 | 951,091 | 否 | 无 | 无 | 无 |
| `cwwl_headings` | yellow | 70,251 | 70,251 | 37,790,888 | 否 | 无 | 无 | 无 |
| `cwwl_titles` | yellow | 8,346 | 8,346 | 6,193,482 | 否 | 无 | 无 | 无 |
| `cwwn` | yellow | 53,082 | 53,082 | 557,704,957 | 是（`embedding`） | 512 | cosine | 39,923 |
| `cwwn_booknames` | yellow | 62 | 62 | 55,620 | 否 | 无 | 无 | 无 |
| `cwwn_headings` | yellow | 11,294 | 11,294 | 5,320,579 | 否 | 无 | 无 | 无 |
| `cwwn_titles` | yellow | 1,432 | 1,432 | 948,291 | 否 | 无 | 无 | 无 |
| `feasts` | yellow | 97,314 | 97,314 | 113,735,412 | 否 | 无 | 无 | 无 |
| `feasts_booknames` | yellow | 233 | 233 | 200,317 | 否 | 无 | 无 | 无 |
| `feasts_ot1` | yellow | 10,096 | 10,096 | 12,445,729 | 否 | 无 | 无 | 无 |
| `feasts_titles` | yellow | 2,387 | 2,387 | 2,133,501 | 否 | 无 | 无 | 无 |
| `filewall` | yellow | 63 | 1,822 | 535,908 | 否 | 无 | 无 | 无 |
| `foo` | yellow | 16,091 | 16,091 | 22,321,067 | 否 | 无 | 无 | 无 |
| `hymn` | yellow | 5,363 | 5,363 | 3,594,446 | 否 | 无 | 无 | 无 |
| `kg-rag_7feasts` | green | 14,925 | 14,925 | 314,732,426 | 是（`embedding`） | 1024 | cosine | 14,925 |
| `kg-rag_bib` | green | 4,239 | 4,239 | 87,825,365 | 是（`embedding`） | 1024 | cosine | 4,239 |
| `kg-rag_cwwl` | green | 178,107 | 178,107 | 3,653,740,504 | 是（`embedding`） | 1024 | cosine | 178,107 |
| `kg-rag_cwwn` | green | 32,032 | 32,032 | 672,768,331 | 是（`embedding`） | 1024 | cosine | 32,032 |
| `kg-rag_dictionary` | green | 14,966 | 14,966 | 320,713,093 | 是（`embedding`） | 1024 | cosine | 14,966 |
| `kg-rag_life` | green | 39,463 | 39,463 | 838,632,148 | 是（`embedding`） | 1024 | cosine | 39,463 |
| `kg-rag_map_note` | green | 16,052 | 16,052 | 326,880,750 | 是（`embedding`） | 1024 | cosine | 16,052 |
| `kg-rag_others` | green | 15,481 | 15,481 | 316,946,151 | 是（`embedding`） | 1024 | cosine | 15,481 |
| `kg-rag_pano` | green | 63,333 | 63,333 | 1,316,277,380 | 是（`embedding`） | 1024 | cosine | 63,333 |
| `life` | yellow | 79,924 | 79,924 | 753,178,068 | 是（`embedding`） | 512 | cosine | 55,024 |
| `life_headings` | yellow | 22,916 | 22,916 | 11,539,505 | 否 | 无 | 无 | 无 |
| `life_titles` | yellow | 1,984 | 1,984 | 1,360,547 | 否 | 无 | 无 | 无 |
| `map_7feasts` | yellow | 2,513 | 169,302 | 65,252,966 | 是（`embedding`） | 512 | dot_product | 0 |
| `map_cont_bookname` | yellow | 14 | 14 | 605,036 | 否 | 无 | 无 | 无 |
| `map_cont_title` | yellow | 436 | 436 | 700,312 | 否 | 无 | 无 | 无 |
| `map_dictionary` | yellow | 1,803 | 83,385 | 36,925,642 | 是（`embedding`） | 512 | dot_product | 0 |
| `map_feasts_bookname` | yellow | 246 | 246 | 4,346,458 | 否 | 无 | 无 | 无 |
| `map_feasts_title` | yellow | 2,527 | 2,527 | 5,130,354 | 否 | 无 | 无 | 无 |
| `map_hymn` | yellow | 550 | 550 | 1,527,903 | 否 | 无 | 无 | 无 |
| `map_lee_bookname` | yellow | 918 | 918 | 7,936,551 | 否 | 无 | 无 | 无 |
| `map_lee_title` | yellow | 7,456 | 7,456 | 9,714,874 | 否 | 无 | 无 | 无 |
| `map_life` | yellow | 1,984 | 1,984 | 3,406,941 | 否 | 无 | 无 | 无 |
| `map_nee_bookname` | yellow | 62 | 62 | 1,789,593 | 否 | 无 | 无 | 无 |
| `map_nee_title` | yellow | 1,366 | 1,366 | 2,129,552 | 否 | 无 | 无 | 无 |
| `map_note` | yellow | 3,491 | 92,905 | 45,123,710 | 是（`embedding`） | 512 | dot_product | 0 |
| `map_others` | yellow | 302 | 302 | 603,829 | 否 | 无 | 无 | 无 |
| `map_pano` | yellow | 13,059 | 460,287 | 219,203,334 | 是（`embedding`） | 512 | dot_product | 0 |
| `others` | yellow | 34,776 | 34,776 | 294,656,832 | 是（`embedding`） | 512 | cosine | 21,479 |
| `others_booknames` | yellow | 3 | 3 | 11,286 | 否 | 无 | 无 | 无 |
| `others_headings` | yellow | 8,786 | 8,786 | 4,335,571 | 否 | 无 | 无 | 无 |
| `others_titles` | yellow | 704 | 704 | 385,758 | 否 | 无 | 无 | 无 |
| `pan_reading` | yellow | 56,966 | 56,966 | 2,208,645,803 | 否 | 无 | 无 | 无 |

### 1.3 与 v7 第 7.5 节「实际产出」逐行对照

| v7 索引名 | ES 索引 | v7 实际 chunk 数 | v7 ES docs | 现 ES docs（_count） | 现存 chunks 文件条数 | ES docs 是否一致 | chunks 文件是否与 v7 实际 chunk 数一致 |
|---|---|---:|---:|---:|---:|---|---|
| life | `kg-rag_life` | 39,463 | 39,463 | 39,463 | 39,463 | 一致 | 一致 |
| cwwl | `kg-rag_cwwl` | 178,107 | 178,107 | 178,107 | 178,107 | 一致 | 一致 |
| cwwn | `kg-rag_cwwn` | 32,033 | 32,032 | 32,032 | 32,033 | 一致 | 一致 |
| others | `kg-rag_others` | 15,481 | 15,481 | 15,481 | 15,481 | 一致 | 一致 |
| bib | `kg-rag_bib` | 4,239 | 4,239 | 4,239 | 4,239 | 一致 | 一致 |
| map_note | `kg-rag_map_note` | 16,052 | 16,052 | 16,052 | 15,774 | 一致 | **不一致** |
| 7feasts | `kg-rag_7feasts` | 14,925 | 14,925 | 14,925 | 14,925 | 一致 | 一致 |
| pano | `kg-rag_pano` | 63,333 | 63,333 | 63,333 | 63,333 | 一致 | 一致 |
| dictionary | `kg-rag_dictionary` | 14,966 | 14,966 | 14,966 | 14,966 | 一致 | 一致 |
| **合计** | | 378,599 | 378,598 | 378,598 | 378,321 | 一致 | **不一致** |

**对不上的索引：**
- 按「ES docs」一栏：9 个 `kg-rag_*` 全部与 v7 一致，没有对不上的。
- 按「实际 chunk 数」一栏：`kg-rag_map_note` 的 chunks 文件现有 15,774 条，v7 与 ES 都是 16,052 条（见第四节、第六节）。
- v7 第 7.5 节只列了 9 个 `kg-rag_*`。本机另有 47 个索引，不在 v7 表中，见 1.2 节；它们不是 3.5 检索的对象（见第三节）。
- v7 记的「ES 索引总大小 ~573 MB」与实际 7,848,516,148 字节（约 7.31 GiB，7,849 MB） 不符（见第六节）。

### 1.4 各索引完整 mapping（原样）

- 56 个索引的 mapping 只有 10 种写法，完全相同的合并成一组贴出，组内每个索引的 mapping 逐字相同。
- 所有索引的 settings 里都没有自定义 `analysis`。用到的 analyzer 只有 `kg-rag_*` 与 `filewall` 两组 mapping 里写明的 `ik_max_word`（索引时）与 `ik_smart`（检索时）；其余 text 字段为 ES 默认 `standard`。
- dense_vector 的 `index_options`（`int8_hnsw`、`m: 16`、`ef_construction: 100`）建索引脚本里没有写，是 ES 8.x 的默认值。

#### mapping 组 1（9 个索引）

索引：`kg-rag_7feasts`、`kg-rag_bib`、`kg-rag_cwwl`、`kg-rag_cwwn`、`kg-rag_dictionary`、`kg-rag_life`、`kg-rag_map_note`、`kg-rag_others`、`kg-rag_pano`

settings 中 `analysis`：无；shards=1，replicas=0

```json
{
  "properties": {
    "author": {
      "type": "keyword"
    },
    "book_title": {
      "type": "keyword"
    },
    "chunk_id": {
      "type": "keyword"
    },
    "embedding": {
      "type": "dense_vector",
      "dims": 1024,
      "index": true,
      "similarity": "cosine",
      "index_options": {
        "type": "int8_hnsw",
        "m": 16,
        "ef_construction": 100
      }
    },
    "en": {
      "type": "text",
      "index": false
    },
    "message_key": {
      "type": "keyword"
    },
    "message_number": {
      "type": "integer"
    },
    "message_title": {
      "type": "keyword"
    },
    "original_ids": {
      "type": "keyword"
    },
    "paragraph_type": {
      "type": "keyword"
    },
    "scripture_refs": {
      "type": "keyword"
    },
    "section_title": {
      "type": "keyword"
    },
    "source_en": {
      "type": "text",
      "index": false
    },
    "source_zh": {
      "type": "text",
      "index": false
    },
    "text": {
      "type": "text",
      "analyzer": "ik_max_word",
      "search_analyzer": "ik_smart"
    },
    "tokens": {
      "type": "integer"
    },
    "year": {
      "type": "integer"
    }
  }
}
```

#### mapping 组 2（1 个索引）

索引：`bib`

settings 中 `analysis`：无；shards=1，replicas=1

```json
{
  "properties": {
    "embedding": {
      "type": "dense_vector",
      "dims": 512,
      "index": true,
      "similarity": "cosine",
      "index_options": {
        "type": "int8_hnsw",
        "m": 16,
        "ef_construction": 100
      }
    },
    "en": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "id": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "order": {
      "type": "long"
    },
    "source": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "tags": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "text": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "title": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "zh": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    }
  }
}
```

#### mapping 组 3（19 个索引）

索引：`cws_cont`、`cws_cont_titles`、`cws_lee`、`cws_lee_titles`、`cws_life_titles`、`cws_nee`、`cws_nee_titles`、`cws_others_titles`、`map_cont_bookname`、`map_cont_title`、`map_feasts_bookname`、`map_feasts_title`、`map_hymn`、`map_lee_bookname`、`map_lee_title`、`map_life`、`map_nee_bookname`、`map_nee_title`、`map_others`

settings 中 `analysis`：无；shards=1，replicas=1

```json
{
  "properties": {
    "id": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "msg": {
      "properties": {
        "text": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "type": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        }
      }
    },
    "sn": {
      "type": "long"
    },
    "source": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "text": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    }
  }
}
```

#### mapping 组 4（4 个索引）

索引：`cwwl`、`cwwn`、`life`、`others`

settings 中 `analysis`：无；shards=1，replicas=1

```json
{
  "properties": {
    "embedding": {
      "type": "dense_vector",
      "dims": 512,
      "index": true,
      "similarity": "cosine",
      "index_options": {
        "type": "int8_hnsw",
        "m": 16,
        "ef_construction": 100
      }
    },
    "en": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "id": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "source": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "tags": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "text": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "title": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "type": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "zh": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    }
  }
}
```

#### mapping 组 5（16 个索引）

索引：`cwwl_booknames`、`cwwl_headings`、`cwwl_titles`、`cwwn_booknames`、`cwwn_headings`、`cwwn_titles`、`feasts`、`feasts_booknames`、`feasts_ot1`、`feasts_titles`、`hymn`、`life_headings`、`life_titles`、`others_booknames`、`others_headings`、`others_titles`

settings 中 `analysis`：无；shards=1，replicas=1

```json
{
  "properties": {
    "en": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "id": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "source": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "tags": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "text": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "title": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "type": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "zh": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    }
  }
}
```

#### mapping 组 6（1 个索引）

索引：`filewall`

settings 中 `analysis`：无；shards=1，replicas=1

```json
{
  "properties": {
    "id": {
      "type": "keyword"
    },
    "msg": {
      "type": "nested",
      "properties": {
        "source": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "text": {
          "type": "text",
          "analyzer": "ik_max_word",
          "search_analyzer": "ik_smart"
        },
        "type": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        }
      }
    },
    "sn": {
      "type": "keyword"
    },
    "source": {
      "type": "keyword"
    },
    "text": {
      "type": "text",
      "analyzer": "ik_max_word",
      "search_analyzer": "ik_smart"
    }
  }
}
```

#### mapping 组 7（1 个索引）

索引：`foo`

settings 中 `analysis`：无；shards=1，replicas=1

```json
{
  "properties": {
    "en": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "id": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "index": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "source": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "tags": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "text": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "title": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "zh": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    }
  }
}
```

#### mapping 组 8（1 个索引）

索引：`map_7feasts`

settings 中 `analysis`：无；shards=1，replicas=1

```json
{
  "properties": {
    "embedding": {
      "type": "dense_vector",
      "dims": 512,
      "index": true,
      "similarity": "dot_product",
      "index_options": {
        "type": "int8_hnsw",
        "m": 16,
        "ef_construction": 100
      }
    },
    "id": {
      "type": "keyword"
    },
    "msg": {
      "type": "nested",
      "properties": {
        "text": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "type": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        }
      }
    },
    "sn": {
      "type": "keyword"
    },
    "source": {
      "type": "keyword"
    },
    "text": {
      "type": "text"
    }
  }
}
```

#### mapping 组 9（3 个索引）

索引：`map_dictionary`、`map_note`、`map_pano`

settings 中 `analysis`：无；shards=1，replicas=1

```json
{
  "properties": {
    "embedding": {
      "type": "dense_vector",
      "dims": 512,
      "index": true,
      "similarity": "dot_product",
      "index_options": {
        "type": "int8_hnsw",
        "m": 16,
        "ef_construction": 100
      }
    },
    "id": {
      "type": "keyword"
    },
    "msg": {
      "type": "nested",
      "properties": {
        "source": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "text": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "type": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        }
      }
    },
    "sn": {
      "type": "keyword"
    },
    "source": {
      "type": "keyword"
    },
    "text": {
      "type": "text"
    }
  }
}
```

#### mapping 组 10（1 个索引）

索引：`pan_reading`

settings 中 `analysis`：无；shards=1，replicas=1

```json
{
  "properties": {
    "bread": {
      "properties": {
        "refid": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "text": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        }
      }
    },
    "cells": {
      "properties": {
        "refid": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "text": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        }
      }
    },
    "en": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "refid": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "showButtons": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "toc": {
      "properties": {
        "refid": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "text": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "type": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        }
      }
    },
    "type": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "zh": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    }
  }
}
```


### 1.5 服务器 ES

我无法直接访问服务器。

- **连接方式与本机相同**：服务器后端同样由 `back_mic/backend/es_config.py` 读取 `.env` 的 `ES_HOST`、`ES_PORT`、`ES_USERNAME`、`ES_PASSWORD`。
- **代码目录**：按 `deploy.sh` 第 6 行，服务器代码目录为 `/opt/pansearch/code`，所以配置文件应在 `/opt/pansearch/code/back_mic/backend/.env`。
- **是否用 Docker**：仓库里没有服务器 ES 的 compose 文件，不能确认服务器 ES 是否也跑在 Docker 里。

下面是可以在服务器上手动执行的等效只读命令。命令从 `.env` 读取密码，不会在屏幕上显示密码：

```bash
cd /opt/pansearch/code/back_mic/backend
set -a; . ./.env; set +a
ES="http://${ES_HOST:-localhost}:${ES_PORT:-9200}"
AUTH="${ES_USERNAME:-elastic}:${ES_PASSWORD}"

# 版本、健康、插件
curl -s -u "$AUTH" "$ES"
curl -s -u "$AUTH" "$ES/_cluster/health?pretty"
curl -s -u "$AUTH" "$ES/_cat/plugins?v"

# 索引清单（docs 数、字节数）
curl -s -u "$AUTH" "$ES/_cat/indices?v&bytes=b&s=index&h=index,health,docs.count,store.size,pri,rep"

# 每个索引的完整 mapping 与 settings
curl -s -u "$AUTH" "$ES/_all/_mapping?pretty"   > es_mapping_all.json
curl -s -u "$AUTH" "$ES/_all/_settings?pretty"  > es_settings_all.json

# 顶层文档数与 embedding 非空数（逐个索引）
for i in $(curl -s -u "$AUTH" "$ES/_cat/indices?h=index" | sort); do
  total=$(curl -s -u "$AUTH" "$ES/$i/_count" | sed -E 's/.*"count":([0-9]+).*/\1/')
  emb=$(curl -s -u "$AUTH" -H 'Content-Type: application/json' "$ES/$i/_count" \
        -d '{"query":{"exists":{"field":"embedding"}}}' | sed -E 's/.*"count":([0-9]+).*/\1/')
  echo "$i total=$total embedding=$emb"
done

# IK 分词是否可用（本机此处报 500，见第三节）
curl -s -u "$AUTH" -H 'Content-Type: application/json' "$ES/kg-rag_life/_analyze" \
     -d '{"analyzer":"ik_smart","text":"基督是神的奥秘"}'

# 如果服务器 ES 也跑在 Docker 里：看 IK 词典加载日志与插件配置目录
docker ps --format '{{.Names}} {{.Image}}' | grep -i elastic
docker logs <ES容器名> 2>&1 | grep -iE 'ik-analyzer|IKAnalyzer.cfg.xml|Dict not found'
docker exec <ES容器名> ls -la /usr/share/elasticsearch/plugins/analysis-ik/ /usr/share/elasticsearch/config/analysis-ik/
```

---

## 二、建索引与向量化脚本

`back_mic/backend/kg_rag/scripts/` 下与三类工作相关的脚本如下：

| 类别 | 现用脚本 | 旧脚本（仍在目录中） |
|---|---|---|
| chunking | `chunking_full.py`（1,274 行，九种数据源） | `chunking.py`（319 行，只处理 life，`BOOK_TITLE="创世记生命读经"`、`YEAR=1974` 写死，另有 `TARGET_MIN/MAX=400/800`、`OVERLAP_CHARS=180`） |
| 建索引 | `index_to_es_full.py` | `index_to_es.py`（建 `kg-rag_test`） |
| 生成 embedding | `generate_embeddings.py`（调用 `kg_rag/embedding_adapter.py`） | — |

另外，`back_mic/backend/scripts/vectorize_map.py`、`vectorize_paragraph.py`、`vectorize_bib.py` 是给旧索引（非 `kg-rag_*`）生成 512 维向量的脚本。`vectorize_map.py` 的对象是 `map_7feasts`、`map_note`、`map_pano`、`map_dictionary`、`filewall`，本机这四个 `map_*` 的 embedding 非空数都是 0。

### 2.1 `chunking_full.py` 实际参数

**token 估算**：`estimate_tokens(text) = max(0, int(len(text) / 1.5))`，按字符数算，没有调用分词器。

**超长拆分**：`split_by_punctuation(text, 800)`。

- 按 `(?<=[。！？；])` 切句后贪心拼接，每段估算 ≤ 800。
- 单句本身超过 800 时单独成段，不再拆。
- 拆出多段时 chunk_id 加 `_p1`、`_p2`……

**职事类**：`life`、`cwwl`、`cwwn`、`others` 共用 `_process_ministry_source`。

- **两遍扫描**：Pass 1 收集 heading（`type` 去空白后含 `heading` 或等于 `preface_heading`），按 `(组键, 排序键)` 建表；Pass 2 只处理 `type == "text"`，`section_title` 取排序键之前最近的一条 heading。
- **分组**：同组（同一篇或同一章）的文档按连续出现归组，组内按全 int 排序键排序。
- **合并阈值 `< 150`**：放入缓冲区。缓冲区原有内容与本段的 `section_title` 不同，或「缓冲区估算 + 本段估算 > 800」时，先把缓冲区写出。缓冲区达到 150 不会自动写出。
- **`150 ≤ tokens ≤ 800`**：先写出缓冲区，本段独立成块。
- **拆分阈值 `> 800`**：先写出缓冲区，再按标点拆分。
- **组结束**：写出缓冲区。
- **合并时**：`text`、`en` 直接拼接（无分隔符）；`chunk_id` 取首段 id；`original_ids` 记录全部 id；`source_zh`、`source_en` 取首段 `source[0]`、`source[1]`。
- **空文本或纯空白段跳过**。

九个数据源的处理分支：

| `--source` | 函数 | 读取方式 | 分组/合并 | author | year | paragraph_type | 其他 |
|---|---|---|---|---|---|---|---|
| life | `process_life` | ijson 流式 | 职事类 | 李常受 | null | text | 组键 `life_{书}-{篇}` |
| cwwl | `process_cwwl` | `_iter_cwwl_lines` 逐行 `json.loads`（丢弃 embedding/zh/_id） | 职事类 | 李常受 | 从组键取年份 | text | 组键 `cwwl_{年}-{册}-{书序}#{章}` |
| cwwn | `process_cwwn` | ijson | 职事类 | 倪柝声 | null | text | 组键 `cwwn_{辑}-{册}#{篇}` |
| others | `process_others` | ijson | 职事类 | 李常受 | null | text | 以最后一个 `_` 分割，排序键只用段序号 |
| bib | `process_bib` | ijson | 同章相邻经节合并：已有缓冲区时，「缓冲区估算 + 本节估算 > 300」就写出；没有 150 下限；单节超过 300 也独立成块；不跨章 | 恢复本圣经 | null | verse | chunk_id `bib_{书}-{章}-{首节}_{末节}`；`text`/`en` 用换行拼接；`scripture_refs` 固定写 `[]` |
| map_note | `process_map_note` | ijson | 每个 ot1 开新块，只追加 ot2/ot3/ot4（ot5 及以下会被丢弃），不跨 ot1 | 李常受 | null | note | `source_zh` 取该 ot1 的 source；doc_id 不去重 |
| 7feasts | `process_7feasts` | ijson | 每个 ot1 开新块，所有以 `ot` 开头的 type 都追加 | 李常受 | null | note | `book_title` 为顶层 source 第一个「，」之前；`source_zh` 为顶层 source 全串；doc_id 重复时加 `_d2`、`_d3` |
| pano | `process_pano` | ijson | 遇到 ot1 时缓冲区估算 ≥ 150 才写出（跨 ot1 合并），所有 `ot*` 追加，不跨 doc | 本块首个 ot1 的 source 含「倪柝声」则为倪柝声，否则李常受 | null | note | `book_title` 为顶层 source 全串；`source_zh` 为本块首个 ot1 的 source；`_c` 序号是块序号；doc_id 去重 |
| dictionary | `process_dictionary` | ijson | 每个 ot1 开新块，所有 `ot*` 追加 | 同 pano 规则（看该 ot1 的 source） | null | note | `book_title` 为所有 bookname 用「，」拼接；`message_key` 为完整 doc_id（保留 a/b）；`source_zh` 去掉外层全角括号；doc_id 去重 |

map 类的 `en`、`source_en` 一律为空串，`section_title` 为 null，`original_ids` 为 `[doc_id]`。map 类超长块同样按 800 拆分。

`scripture_refs` 由 `extract_scripture_refs(text)` 生成，bib 除外。

- **括号模式**：`[（(]([^）)]{1,40})[）)]`。括号内容里必须出现「书卷简称 + 紧跟一个章节数字」，数字为汉字数字或阿拉伯数字，匹配规则是 `(书卷)[一二三四五六七八九十百千〇\d]`。存入的是**含括号的整段**。
- **破折号模式**：`[—－](…书卷…)(?=$|\n|。|；)`。同样要满足上面的数字条件，存入的是**去掉破折号、首尾去空白**后的内容。
- **去重**：按完整字符串去重并保序。
- **书卷简称**：66 个，长的优先匹配。

### 2.2 `index_to_es_full.py` 的设定

- **settings**：`number_of_shards: 1`，`number_of_replicas: 0`，无 `analysis` 段。
- **mapping**：与 1.4 节 `kg-rag_*` 一组一致。
  - `text` 为 `text`，`analyzer: ik_max_word`、`search_analyzer: ik_smart`。
  - `en`、`source_zh`、`source_en` 为 `text` 且 `index: false`。
  - `embedding` 为 `dense_vector`，`dims: 1024`、`index: true`、`similarity: cosine`，脚本没有写 `index_options`。
  - 其余字段为 `keyword` 或 `integer`。
- **写入**：
  - 写入 16 个字段（不含 embedding）。
  - `_id = chunk_id`，值为 None 的字段不写。
  - 先过滤掉 `tokens == 0` 的 chunk。
  - bulk 每批 200 条，`request_timeout=120`。
- **重建**：`--recreate` 时先删索引再建。建索引报 analysis、analyzer、ik_ 相关错误时，提示「ES 未安装 IK 分词插件」。
- **说明文字不符**：文件开头的说明文字写「六个数据源共用同一套 mapping」，实际九个 `kg-rag_*` 都是这套。

### 2.3 `generate_embeddings.py` 与 `embedding_adapter.py`

| 项 | 值 |
|---|---|
| 模型 | `qwen/qwen3-embedding-8b`（环境变量 `EMBEDDING_KG_MODEL`，本机 `.env` 同值） |
| 维度 | 1024（`EMBEDDING_KG_DIMS`，作为 `dimensions` 参数传给接口） |
| 调用方式 | 远程 API，不是本地模型：OpenRouter 的 OpenAI 兼容接口，`openai.AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)`，`OPENROUTER_BASE_URL` 默认 `https://openrouter.ai/api/v1`；本机 `.env` 已设 `OPENROUTER_API_KEY` |
| profile | `kg_rag`；`default` profile 转发到 `ai_search.embedding_service`，是 OpenAI `text-embedding-3-small` 512 维，供旧索引使用 |
| 批大小 | `--batch-size` 默认 50 |
| 选取范围 | 只处理 `must_not exists embedding` 的文档；先用 scroll（每页 5000，`scroll=2m`）收集 `chunk_id` 与 `text`，再逐批调用 |
| 失败处理 | 一批失败时等 5 秒重试一次；再失败则记入失败列表跳过；向量条数不符也跳过 |
| 写回 | bulk `update`，只写 `embedding` 字段；每批之间 `sleep(1)` |
| 默认索引 | `--index` 默认 `kg-rag_test`（实际使用时需指定） |

---

## 三、3.5 检索侧怎么用这些索引

### 3.1 入口

- **代码位置**：前端调用 `POST /api/kg_rag/query`（`mode: "3.5"`），进入 `kg_rag/kg_rag_router.py`，再到 `kg_rag/kg_rag_service.py` 的 `KGRAGService.full_query`。
- **Mode 分支**：约第 1156 行。
  - `mode == "3.5"`：`active_index = os.environ.get("KG_RAG_ES_INDEX", _INDICES_FULL)`。
  - 其他 mode：`active_index` 取 `_INDICES_BASE`。
- **检索函数**：都在 `kg_rag/retrieval.py`（`bm25_search`、`dense_search`、`rrf_merge`、`rerank`、`skeleton_route_search`）。

### 3.2 一次检索查哪些索引、有没有索引级权重

- **`_INDICES_FULL`（3.5）**：`kg-rag_life,kg-rag_cwwl,kg-rag_cwwn,kg-rag_others,kg-rag_bib,kg-rag_map_note,kg-rag_7feasts,kg-rag_pano,kg-rag_dictionary`，共 9 个。
- **`_INDICES_BASE`（2.0/3.0）**：同上去掉 `kg-rag_pano`、`kg-rag_dictionary`，共 7 个。
- **怎么查**：每一路检索都是**一个** `es.search(index="逗号连接的 9 个索引名")` 请求，没有按索引分别查询。
- **ES 层权重**：没有 `indices_boost`，也没有按索引设置不同参数。
- **Python 层权重**：结果返回后，按「纲目性质」`outline_nature` 乘倍数（`OUTLINE_NATURE_WEIGHTS`，第 167–180 行）。多条规则同时命中时取最大倍数，不叠乘，然后按加权分重排。

| outline_nature | 条件 | 倍数 |
|---|---|---|
| 一般性（默认） | chunk_id 以 `cwwl_` 开头且年份在 1994–1997 | 1.1 |
| 真理启示 | cwwl 且年份 1994–1997 | 1.5 |
| 生命经历 | `_index` 为 `kg-rag_cwwn` 或 `kg-rag_life` | 1.5 |
| 应用实行 | cwwl 且年份 1985–1993 | 1.5 |

### 3.3 BM25

- **查询体**：`{"match": {"text": {"query": 原始主题, "analyzer": "ik_smart"}}}`，只查 `text` 一个字段，没有字段权重和 multi_match。
- **查询文本**：只用原始主题，改写后的问题不走 BM25。
- **取数**：取 `bm25_top_k × 3` 条（默认 90，`depth=deep` 时 180）。按纲目性质加权重排后，保留前 `bm25_top_k` 条（默认 30，deep 60）。
- **返回字段**：`_source` 请求了 `source` 字段，`kg-rag_*` 的 mapping 里没有这个字段。

### 3.4 kNN

- **查询向量**：由 `get_embedding(query, profile="kg_rag")` 生成，即 qwen3-embedding-8b，1024 维。
- **请求体**：`{"size": k, "knn": {"field": "embedding", "query_vector": …, "k": k, "num_candidates": num_candidates}}`。
- **similarity**：来自 mapping，`cosine`（`int8_hnsw`，m=16，ef_construction=100）。
- **路数**：改写成功时为「原始主题 + 改写问题」，通常 5 路，每路单独发一次 kNN。
- **每路 k**：`dense_top_k = ceil(bm25_top_k / 路数)`，默认 30/5 = 6（deep 为 12）。请求时 `k = size = dense_top_k × 3`，默认 18（deep 36）。
- **num_candidates**：100（`DEFAULT_PARAMS`）。
- **每路处理**：加权后保留前 `dense_top_k` 条。
- **多路合并**：按 chunk_id 去重，保留加权分最高的一条。合并后列表的顺序是各路结果的插入顺序，没有按分数重排，而这个顺序直接作为 RRF 的名次。
- **返回字段**：`_source` 里 `source_zh` 写了两次，没有 `source_en`。

### 3.5 融合与精排

- **RRF**：在 Python 里做（`retrieval.rrf_merge`），不是 ES 内置的 rrf。公式为 Σ weight / (k + rank)，`rrf_k = 60`，`bm25_weight = 1.0`，`dense_weight = 1.0`。
- **精排**：用 Jina Reranker（`ai_search/reranker_service.py`，`RERANK_MODEL = "jina-reranker-v3"`）取前 `rerank_top_n` 条，默认 15，deep 为 25。
- **路 3（骨架扩展节点）**：每个扩展节点单独跑一遍，流程同上。
  - 查询文本为「原始主题 + 节点名」。
  - BM25 与 kNN 各取 `skeleton_route_top_k × 3` 条，默认 135，deep 225。
  - kNN 的 `num_candidates = min(300, 取数 × 3)` = 300。
  - 之后依次 RRF（k=60）、纲目性质加权、截断到 `skeleton_route_top_k`（45）、Jina 精排。
  - 每个节点最后并入的条数上限为 `skeleton_route_top_k // 节点数`。
- **防火墙**：命中时把 `firewall.json`（本地文件，不走 ES）的整篇作为第一条 main_result 注入。

### 3.6 过滤字段

检索请求里**没有任何过滤条件**。`retrieval.py` 与 `kg_rag_service.py` 的 ES 查询中，找不到 `filter`、`term`、`terms`、`range`、`bool` 子句，`author`、`year`、`paragraph_type`、`book_title` 都没有参与过滤。只有 cwwl 的年份会用于检索后的加权，而且是从 chunk_id 解析出来的，不读 `year` 字段。

### 3.7 feasts / pano / dictionary 是否走不同路径

没有。`kg-rag_7feasts`、`kg-rag_pano`、`kg-rag_dictionary` 与职事类索引在同一个请求里一起查询，查询体、参数、加权、融合、精排完全相同，代码里没有按索引分支。

差别只有两点：

- **哪些 mode 会查**：`kg-rag_pano`、`kg-rag_dictionary` 只在 3.5 查询；`kg-rag_7feasts` 在 2.0、3.0、3.5 都会查。
- **加权**：「纲目性质」加权规则只对 cwwl、cwwn、life 生效，这三个 map 类索引在任何纲目性质下倍数都是 1.0。

### 3.8 「停用词为空」告警

- **出处**：不在项目代码里。整个仓库搜不到「停用词」或 stopword 字样。它来自 ES 的 IK 分词插件。本机调用 IK 分词时，ES 返回：
  `null_pointer_exception: Cannot invoke "org.wltea.analyzer.dic.DictSegment.match(char[], int, int)" because "org.wltea.analyzer.dic.Dictionary.singleton._StopWords" is null`
- **根因**：容器内 IK 插件的配置和词典目录不存在。
  - 容器里只有 `/usr/share/elasticsearch/plugins/analysis-ik/` 的 jar，没有 `config/`，`/usr/share/elasticsearch/config/analysis-ik/` 也不存在。
  - 每次 ES 启动，日志依次记录：找不到 `IKAnalyzer.cfg.xml`（两处都找）、`ik-analyzer: Main Dict not found`（找不到 `main.dic`）、`ik-analyzer: Surname not found`（找不到 `surname.dic`）。
  - 当前日志里这两条 ERROR 各出现 24 次。
  - 词典初始化在加载姓氏词典时抛出 RuntimeException 中止，停用词词典没有加载，`_StopWords` 保持为 null。
  - 日志里 `.security-7` 的分片报「failed to create index」，记录的失败原因就是 `ik-analyzer: Surname not found!!!`（13 次）。`.ds-ilm-history-7-2026.05.04-000005` 也有 11 次「failed to create index」，我没有逐条核对它的原因。
- **触发条件**：任何要用 IK 分析文本的操作都会触发，不限于 BM25。本机实测三种操作都失败：
  - `_analyze` 用 `ik_smart` 或 `ik_max_word`；
  - `_analyze` 用 `field: text`；
  - 对 9 个 `kg-rag_*` 发出 3.5 的 BM25 查询：无论是否显式写 `analyzer: ik_smart`，都返回 400 `search_phase_execution_exception … _StopWords is null`。

  `standard` 分词正常（逐字切分）。往 `text` 字段写入新文档时，索引分析器 `ik_max_word` 同样会走 IK。
- **对 3.5 的实际影响（本机）**：
  - `bm25_search` 捕获异常，打印 `[KG-RAG] BM25 检索失败 (query=…)`，返回空列表，并把原因追加到 `es_call_errors`。
  - `full_query` 看到 `es_call_errors` 非空，调用 `get_monitoring(self.redis).record_degradation(source="es_retrieval", …)` 记一条降级事件。
  - 路 3 每个节点的 BM25 也会同样失败。
  - 因此本机 3.5 目前只有 kNN 在出结果。服务器是否相同，需要用 1.5 节的命令确认。
- **仓库里的 IK 词典**：`G:\copypan\es_plugins\es_plugins\ik\config\` 下有一套 IK 词典。它属于旁边的 7.17.9 版插件（`elasticsearch-analysis-ik-7.17.9.jar`），8.19.0 版插件目录没有 `config/`。这套词典里有：

  | 文件 | 字节 |
  |---|---|
  | `IKAnalyzer.cfg.xml` | 625 |
  | `main.dic` | 3,058,510 |
  | `extra_main.dic` | 5,225,922 |
  | `stopword.dic` | 164 |
  | `extra_stopword.dic` | 156 |
  | `surname.dic` | 752 |

---

## 四、源数据实况

### 4.1 chunking 的输入与输出

v7 第 1.1 节写的目录 `E:\12490_with_bib\` **不存在**（E 盘存在，但没有该目录）。在各磁盘按文件名搜索后，九个源 json 与九个 chunks json 都在 **`G:\PanAI用\new_clear_data\`**（项目目录之外）：

**九个源 json**

| 文件 | 在不在 | 字节 | 修改时间 | v7 记载大小 |
|---|---|---:|---|---|
| `life.json` | 在 | 950,596,945 | 2026-06-02 15:12 | 950 MB |
| `cwwl.json` | 在 | 3,238,395,789 | 2026-03-12 10:07 | 3.2 GB |
| `cwwn.json` | 在 | 706,937,381 | 2026-03-12 09:55 | 707 MB |
| `others.json` | 在 | 373,326,713 | 2026-03-12 09:58 | 373 MB |
| `bib.json` | 在 | 40,478,560 | 2026-03-24 16:56 | 40 MB |
| `map_note.json` | 在 | 31,841,354 | 2026-03-24 14:51 | 28 MB |
| `map_7feasts.json` | 在 | 0 | 2026-03-25 20:33 | 41 MB |
| `map_pano.json` | 在 | 185,915,731 | 2026-03-25 20:31 | 186 MB |
| `map_dictionary.json` | 在 | 25,877,813 | 2026-03-25 20:36 | 26 MB |

**九个 chunks json**

| 文件 | 在不在 | 字节 | 修改时间 | 条数 | 其中 tokens=0 | 首条 chunk_id | v7 实际 chunk 数 |
|---|---|---:|---|---:|---:|---|---:|
| `kg-rag_life_chunks.json` | 在 | 80,816,684 | 2026-06-02 15:09 | 39,463 | 0 | `life_60-12-25` | 39,463 |
| `kg-rag_cwwl_chunks.json` | 在 | 395,768,514 | 2026-03-24 19:00 | 178,107 | 0 | `cwwl_1963-1-10#4-13` | 178,107 |
| `kg-rag_cwwn_chunks.json` | 在 | 73,204,847 | 2026-06-08 19:20 | 32,033 | 1 | `cwwn_2-21#11-16` | 32,033 |
| `kg-rag_others_chunks.json` | 在 | 31,589,890 | 2026-03-24 16:50 | 15,481 | 0 | `others_1_138-27` | 15,481 |
| `kg-rag_bib_chunks.json` | 在 | 9,668,324 | 2026-03-24 21:05 | 4,239 | 0 | `bib_23-18-3_7` | 4,239 |
| `kg-rag_map_note_chunks.json` | 在 | 26,180,755 | 2026-03-24 17:01 | 15,774 | 0 | `map_note_75-1-1_c1` | 16,052 |
| `kg-rag_7feasts_chunks.json` | 在 | 35,468,291 | 2026-03-25 22:44 | 14,925 | 0 | `map_7feasts_1997-02-1_c1` | 14,925 |
| `kg-rag_pano_chunks.json` | 在 | 133,173,304 | 2026-03-25 22:42 | 63,333 | 0 | `map_pano-1-1_c1` | 63,333 |
| `kg-rag_dictionary_chunks.json` | 在 | 22,197,931 | 2026-03-25 22:44 | 14,966 | 0 | `map_dictionary-1-a_c1` | 14,966 |

另有同名文件：
- `C:\Users\28121\Desktop\bib.json`，5,555,242 字节，修改时间 2026-09-14 21:42，内容与上表的 bib.json 不同（大小不同）。
- `G:\PanAI用\Pansearch数据备份\note_temp\json备份\map_note.json`，31,841,354 字节，与上表 map_note.json 大小相同。

chunks 文件按行统计：`_JsonArrayWriter` 每条一行，所以行数就是条数。每条 16 个字段，与 `_build_chunk` 一致。

### 4.2 三类新数据

搜索范围是项目目录 `G:\copypan`（全部子目录，排除 node_modules、.git、dist）。另外，为了回答第一项「chunking 输入输出在不在」，我在 C、D、E、F、G 各盘按文件名做过一次搜索（深度 ≤ 7），顺带看到的项目外位置也列在下面，并标明「项目外」。

**① 恢复本圣经注解的 JSON（带经文出处）：已找到（项目内）**

- **路径**：`G:\copypan\back_anshifenliang\data\private\foo_jie_single\`。这个目录被 `.gitignore` 第 48 行 `back_anshifenliang/data/private/` 忽略，不在 git 里。
- **数量**：
  - `files\` 下 15,759 个 json，每条注解一个文件；
  - `content_index.json`（4,843,422 字节）：list，15,759 条，字段为 `title`、`file`、`text`；
  - `title_index.json`（3,848,179 字节）：dict，把标题的多种写法映射到文件名。
- **文件命名**：`foo_{书号}-{章}-{节}-{注号}_恢复本圣经，{经文出处}注{n}.json`，例如 `foo_1-1-1-1_恢复本圣经，创一1注1.json`。首条为创一1注1，末条为撒上九6注1。
- **`content_index.json` 单条结构**：

  ```json
  {"title": "创一1注1", "file": "foo_1-1-1-1_恢复本圣经，创一1注1.json", "text": "圣经由旧约和新约二约组成，是神写给人完整的神圣启示。……"}
  ```

- **`files\` 下单个文件**：整个文件是一个 JSON 字符串（HTML），开头如下：

  ```text
  "<h3>恢复本圣经　创一1注1</h3><div align='justify'>圣经由旧约和新约二约组成，……(弗一10，三9，提前一4下)。……</div>"
  ```

- **ES 里的对应数据**：本机 ES 的 `foo` 索引有 16,091 条（比文件多 332 条）。`_id` 形如 `foo_1-1-1-1`，`text` 为 HTML，内含锚点 `<a id="1_1_1_1">创1:1<sup>1</sup></a>`；mapping 见 1.4 节「foo」一组。

**② 读经 app 来的圣经纲目数据：未找到**

项目内没有圣经纲目（按经卷与章节组织的纲目条目）数据。容易混淆的两处如下，它们都不是圣经纲目：

- **ES `pan_reading` 索引**（56,966 条，2,208,645,803 字节）：是网站「阅读」页面的数据。
  - 文档类型有 `msg` 54,987、`toc` 1,862、`cell` 68、`cells` 49，字段为 `refid`、`bread`、`toc`、`cells`、`zh`、`en`；
  - 其中 `bib_*` 的 msg（1,256 条）内容只有经文行，行类型只有 `ver`；
  - 使用者为 `back_mic/backend/search/search_reading.py` 等。
- **项目外 `G:\audio-app\`**（「活泉」app 工程）：`bible-source\bible_gb_recovery.sqlite` 与 `app\assets\bible\bible_gb_recovery.sqlite`（3,932,160 字节），只有两张表：
  - `verse_all_final_gb_26`：31,295 行经文，字段 `id, chapter_code, section_code, segment_code, unit_code, content`；
  - `volume_all_gb_22`：66 行书卷，字段 `id, chapter_code, chapter_name, abbreviation, chapter_sum`。

  没有纲目表。`bible-charts\` 是 9 张 png 图。

**③ 12490 篇的纲目 docx：项目内未找到**

- **项目内**：`G:\copypan` 只有 154 个 docx：`scripts\` 136、`docs\` 8、`back_mic\` 7、`back_shared\` 2、`back_cn\` 1，没有成批的纲目 docx。
- **项目外**找到下列成批纲目 docx：

| 路径（项目外） | docx 数 | 组成 |
|---|---|---|
| `G:\0已作内容\00 工作记录【重要】\02 作SOP\11 AI辅助的作稿新流程\信息检索程序\Books\12490\` | 12,505 | 倪柝声文集 1,346、李常受文集 8,437、生命读经 1,984、新约总论 436、生命课程 48、今时代神圣启示的先见—倪柝声 33、真理课程 221 |
| `G:\0已作内容\Books【2024.11.20】\` | 21,263 | 与上一行相同的 7 类（数量逐类相同），加上节期纲目 5,076、圣经真理题库 3,682；同目录另有 `12490.7z`（286,798,664 字节） |
| `C:\Users\28121\Desktop\倪李文集纲目\` | 12,513 | 7 类，李常受文集纲目 8,445（比上面多 8 篇），其余逐类相同 |

单个文件结构样例：`…\Books\12490\1 倪柝声文集\1 倪柝声文集第一辑第一册，灵修指微\msg. 1 回到十字架罢.docx`，共 71 段。前几段的段落样式与文字如下：

```text
[0系列]      倪柝声文集第一辑第一册
[11111西列]  灵修指微
[00篇题]     第一篇　回到十字架罢
[11读经]     读经：罗三24~25，林后五14，腓三10~11，加五24，约壹一7~9，……
[2大点]      壹<Tab>罪的结果是与神分开；十字架是我们与神和好的地方—罗三24~25，林后五14：
[3中点]      一<Tab>于十字架上，基督负我们的罪担，……
[4小点]      1<Tab>架是救药；……—加五24。
```

层级用段落样式区分（`2大点`、`3中点`、`4小点`），行首为「壹 / 一 / 1」加 Tab，经文出处放在破折号之后。

---

## 五、chunk 字段与图谱的衔接

### 5.1 chunk_id 生成规则：代码与 v7 对照

| 数据源 | v7 规则 | 代码（`chunking_full.py`） | 实际数据（ES） |
|---|---|---|---|
| 职事类 | 单段沿用原 id；合并取首段 id；拆分加 `_p1/_p2` | 一致 | 一致。`_pN` 块：life 0、cwwl 16、cwwn 49、others 2；合并块（`original_ids` > 1）：life 8,259、cwwl 26,349、cwwn 4,384、others 3,366 |
| bib | `bib_{书}-{章}-{起始节}_{结束节}` | 一致 | 格式一致；分组结果与 v7 不同（见第六节） |
| map_note | `doc_id_c{ot1序号}`，超长加 `_p` | 一致 | 16,052 条全为 `_cN`，其中 104 条 `_cN_pN` |
| 7feasts | `doc_id_c{序号}`，超长 `_p`，重复 id 加 `_d2/_d3` | 一致（`_dN` 加在 doc_id 上，所以是 `…_d2_c1`） | `_cN_pN` 4,370 条；`_dN` 105 条，例：`map_7feasts_2000-02-1_d2_c1` |
| pano | `doc_id_c{最终块序号}`，超长 `_p`，去重 | 一致 | `_cN_pN` 5,877 条；`_dN` 0 条 |
| dictionary | `doc_id_c{序号}`，超长 `_p`，去重 | 一致 | `_cN_pN` 123 条；`_dN` 389 条，例：`map_dictionary-907-a_d2_c1` |

在所有 9 个索引里，ES 的 `_id` 都等于 `chunk_id`，这是 `index_to_es_full.py` 写入时设定的。

### 5.2 与图谱的衔接

代码与数据中都**没有**任何把 chunk 与图谱节点连起来的字段或逻辑：

- **代码**：`kg_rag/neo4j_client.py`、`kg_rag/scripts/import_concepts.py`、`kg_rag/scripts/scripture_data/*.py`、`panai4/graph/*.py` 中都没有出现 `chunk_id`、`scripture_refs`、`original_ids`、`message_key`。
- **3.5 图谱（bolt://localhost:7687）**：全库只有 5 个属性键 `aliases`、`greek_terms`、`id`、`name`、`text`，没有 chunk、经文、ES 相关的键。
- **neo4j-v4（bolt://localhost:7688）**：全库只有 2 个属性键 `name`、`same_as`。
- **检索中的实际关系**：3.5 里图谱只提供概念名与扩展节点名，它们作为查询文本参与 ES 检索（路 3 的「原始主题 + 节点名」），检索结果不回写图谱。
- **v7 文档**：没有定义 chunk 与图谱的衔接规则。

### 5.3 `scripture_refs` 实际取值样例（各索引 3 条）

「非空」指 `exists scripture_refs` 的条数（空数组不算）。

**`kg-rag_life`**（非空 11,116 / 39,463）

- `life_1-25-20`：`["（诗歌第二一○首）"]`
- `life_53-2-11`：`["（包括犹太教和天主教）"]`
- `life_62-9-27`：`["（西二9）", "（约一18，51，提前二5）", "（西二16～17，约四23～24）", "（约十一25，十四6）", "（约八12，九5）", "（约十四6）", "（林前一30）", "（约十四6，弗四21）"]`

**`kg-rag_cwwl`**（非空 38,034 / 178,107）

- `cwwl_1977-2-11#9-17`：`["（约四24。）"]`
- `cwwl_1991-1992-1-3#31-9`：`["（帖前一3。）"]`
- `cwwl_1968-2-9#5-23`：`["（弗六12，二2）"]`

**`kg-rag_cwwn`**（非空 5,252 / 32,032）

- `cwwn_2-19#13-2`：`["（来六5，）", "（太十二28，）", "（启十一15。）"]`
- `cwwn_1-14#7-48`：`["（罗五5）"]`
- `cwwn_1-12#2-56`：`["（箴二九11）", "（赛二九24）", "（但五20）"]`

**`kg-rag_others`**（非空 6,566 / 15,481）

- `others_2-1_34-45`：`["（加三27下。）"]`
- `others_2-4_18-62`：`["（启十一3，）"]`
- `others_1_30-53`：`["（徒六7，提前一19）"]`

**`kg-rag_bib`**（非空 0 / 4,239）

- 无样例：`process_bib` 对 bib 固定写 `scripture_refs = []`，4,239 条全部为空。

**`kg-rag_map_note`**（非空 12,344 / 16,052）

- `map_note_75-24-40_c3`：`["（启二十6、14，二一8）"]`
- `map_note_75-3-39_c1`：`["（见太二八19注6）", "（罗六3，加三27）", "（林前十五45、47）", "（林前十五47）"]`
- `map_note_75-1-394_c6`：`["（约十一25，启一18）", "（利三1）", "（利四28，五6）", "（利一10）", "（约二19，十一25，来九14）", "（太十八16，林后十三1）", "（约十四19~20，加二20）"]`

**`kg-rag_7feasts`**（非空 14,178 / 14,925）

- `map_7feasts_2010-06-3_c3_p2`：`["腓二17~18：", "腓二17~18", "腓四4~6：", "腓四4", "腓一19：", "腓一19", "腓三7~9上，弗三8，创十五1，林后十二2", "腓三9下，参赛六四6，太五20，启三18，十九8", "腓三8、10，二2，三13：", "腓三8", "腓三10", "徒九5", "腓二2", "腓三14", "四4，来十三15，诗一一九164："]`
- `map_7feasts_2006-09-12_c2`：`["腓一8，弗四16：", "路二49，约二17，太二六39，赛五三12，四二4，可二8", "腓二5，林前二16下，罗八6：", "林后十一10", "林前十六24", "腓一21上，8：", "西三12", "约十五4上", "腓一7，四23", "腓四7、12、20节：", "腓一8，二1，西三12", "门12", "腓一8：", "腓一8节", "腓二1，西三12", "林前十二12~27：", "太十六24，弗四16", "林前十二26~27，罗十二15"]`
- `map_7feasts_2018-08-3_c12`：`["参诗三六8~9，十六11，耶十五16，诗五一12，赛六一10", "腓四11~13"]`

**`kg-rag_pano`**（非空 56,232 / 63,333）

- `map_pano-66-59_c2`：`["徒十五36～29，腓一15～18：", "创二10～14，启二二1", "林前十六10，约壹一3"]`
- `map_pano-40-88_c4`：`["腓三13～14，启二二12"]`
- `map_pano-88-73_c2`：`["太九38：", "太二十7", "林前九17", "路十六9", "林后五13：", "可三21", "徒二六24～25"]`

**`kg-rag_dictionary`**（非空 13,572 / 14,966）

- `map_dictionary-847-a_c4`：`["加二20：", "罗九23，徒二21", "罗十二1，加二20", "可四19，西三2", "徒十45，伯八21", "诗一一〇3，林后八4", "加二20，诗一一〇3", "提前二4，弗二15"]`
- `map_dictionary-230-b_c9`：`["弗一17，二22，三5、16，四23，五18，六18：", "弗二22"]`
- `map_dictionary-64-a_c4`：`["（太一18～20，路一35）", "太八23~27：", "太八23~27", "约十四9～10", "创一26，西一15~16"]`


- **两种模式的存储形态**：职事类以括号模式为主，值**带括号**，还可能带句号或逗号，如 `（约四24。）`、`（启四5，）`。map 类以破折号模式为主，值**不带破折号**，可能带结尾冒号，如 `腓二17~18：`；带冒号与不带冒号的同一段引用会作为两个值并存，例如 `腓二17~18：` 与 `腓二17~18`。
- **有些值不是经文引用**：`kg-rag_life` 中有 730 个值（657 条 chunk）的括号内容里没有「书卷简称 + 章节数字」，例如 `（诗歌第二一○首）`、`（包括犹太教和天主教）`、`（但不是在神格上）`、`（如台湾一班基督徒所实行的）`。按现行 `extract_scripture_refs`，这些都不会被提取。我把现行代码原样复制出来跑过这些文本，结果都是空列表。其余 7 个有值的索引里，这类值为 0。

---

## 六、不一致之处

以下每条都是「代码或 v7 这样写，但实际不是这样」。

| # | 代码或 v7 的写法 | 实际情况 |
|---|---|---|
| 1 | v7 1.1：输入输出目录 `E:\12490_with_bib\` | 该目录不存在；18 个文件在 `G:\PanAI用\new_clear_data\` |
| 2 | v7 1.2：`map_7feasts.json` 41 MB | `G:\PanAI用\new_clear_data\map_7feasts.json` 为 **0 字节**（修改时间 2026-03-25 20:33）；其 chunks 文件与 ES 索引完整（14,925 条） |
| 3 | v7 1.2：`map_note.json` 28 MB；bib.json 约 40,000 条 | `map_note.json` 为 31,841,354 字节；`bib.json` 大小 40,478,560 字节与 v7 相符，但只有 31,102 个经节 id（不重复） |
| 4 | v7 7.5：map_note 实际 chunk 数 16,052 | ES 为 16,052，但现存 `kg-rag_map_note_chunks.json` 只有 15,774 条（修改时间 2026-03-24 17:01），比 ES 少 278 条；现存文件不是写入 ES 的那一版 |
| 5 | v7 7.5：「ES 索引总大小 ~573 MB（原 416 MB + 新增 157 MB）」 | 9 个 `kg-rag_*` 的 store.size 合计 7,848,516,148 字节（约 7.31 GiB，7,849 MB） |
| 6 | v7 4.2 与 `process_bib` 的设计：同章相邻经节合并到 150–300 tokens，只有章末或单节超过 300 才会产生短块 | 1,293 个 chunk 只含一节（占 4,239 的 30.5%）。例：创世记第一章被切成 `bib_1-1-1_1`（6 tokens）、`bib_1-1-2_2`（16）、`bib_1-1-3_19`、`bib_1-1-20_30`、`bib_1-1-31_31`。原因是 `bib.json` 里同一章的经节不连续存放：文件从 `bib_23-18-3` 开始，创一3–30 在第 20,527 个位置起，创一1、2、31 在别处；1,189 章在文件顺序中切换了 2,402 次，而 `process_bib` 只按相邻的同章经节分组 |
| 7 | v7 5.2：bib 的 author 固定为「圣经」 | 代码与 ES 都是「恢复本圣经」（4,239 条） |
| 8 | v7 附录速查表：bib「无 embedding」 | `kg-rag_bib` 4,239 条全部有 1024 维 embedding；旧 `bib` 索引 31,102 条中 1,193 条有 512 维 embedding |
| 9 | v7 第二节：每条 chunk「共 17 个字段（不含后续生成的 embedding）」 | v7 自己的字段表只列了 16 个；`_build_chunk` 与 chunks 文件都是 16 个；ES mapping 为 17 个 property（16 个加 embedding） |
| 10 | v7 5.3：`extract_scripture_refs` 用 `re.findall` 取括号内部（不含括号）、不限长度、只要求出现书卷名 | 现行代码存的是含括号的整段，括号内容限 1–40 字，并要求书卷名后紧跟章节数字；ES 中职事类的值都带括号 |
| 11 | 现行代码：括号内容必须有「书卷 + 数字」 | `kg-rag_life` 有 730 个值（657 条 chunk）不满足这一条（见 5.3 节）；cwwl、cwwn、others 为 0。ES 中的 life 数据是用另一版提取规则生成的。现存 `kg-rag_life_chunks.json` 修改于 2026-06-02，条数与 ES 相同（39,463） |
| 12 | v7 4.1：拆分阈值 `> 800` | `kg-rag_cwwl` 有 3 条 tokens = 801。代码按「各段估算之和 > 800」判断是否写出缓冲区，而写出后按整段重新估算，两次取整结果可能差 1 |
| 13 | `index_to_es_full.py` 按已装好 IK 插件建立 `text` 字段（`ik_max_word` / `ik_smart`） | 本机 ES 装有 `analysis-ik` 8.19.0，但容器内没有它的配置与词典。所有 IK 分析都报 `_StopWords is null`，3.5 的 BM25 查询全部失败并被静默降级为空结果（见 3.8 节） |
| 14 | `index_to_es_full.py` 开头的说明文字：「六个数据源共用同一套 mapping」 | 九个 `kg-rag_*` 共用这套 mapping |
| 15 | v7 文首与 7.5：「全部完成（chunking + 建索引 + embedding 生成 + 检索适配）」 | 建索引、embedding 在 ES 中完整（9 个索引 embedding 覆盖率 100%），但检索的 BM25 一路在本机不可用（第 13 条） |

---

*报告由只读勘探生成。项目内除本文件外没有新增、修改、删除任何文件；勘探用的临时脚本放在系统临时目录（项目外），结束后已删除。*
