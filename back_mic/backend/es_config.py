"""
Elasticsearch 统一配置
修改 ES 连接地址只需改此文件中的 ES_HOSTS
"""
from elasticsearch import Elasticsearch

# ES 连接地址，后续修改只需改此处
ES_HOSTS = ["http://localhost:9200"]

# 请求超时（秒），建索引、删索引等操作可能较慢，默认 10 秒易超时
ES_REQUEST_TIMEOUT = 60

# 全局 ES 客户端实例
es = Elasticsearch(hosts=ES_HOSTS, request_timeout=ES_REQUEST_TIMEOUT)
