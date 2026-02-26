"""
Elasticsearch 统一配置
修改 ES 连接地址只需改此文件中的 ES_HOSTS
"""
from elasticsearch import Elasticsearch
import os
from dotenv import load_dotenv

load_dotenv()

ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")

# 请求超时（秒），建索引、删索引等操作可能较慢，默认 10 秒易超时
ES_REQUEST_TIMEOUT = 60

# 全局 ES 客户端实例
es = Elasticsearch(
    hosts=[f"http://{ES_HOST}:{ES_PORT}"],
    basic_auth=(ES_USERNAME, ES_PASSWORD),
    request_timeout=ES_REQUEST_TIMEOUT
)