"""
Elasticsearch 统一配置
修改 ES 连接地址只需改此文件中的 ES_HOSTS
"""
from elasticsearch import Elasticsearch

# ES 连接地址，后续修改只需改此处
ES_HOSTS = ["http://localhost:9200"]

# 全局 ES 客户端实例
es = Elasticsearch(hosts=ES_HOSTS)
