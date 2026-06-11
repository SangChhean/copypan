"""
快速检查当前 .env 下的 Elasticsearch 是否可连接。
在 back_mic/backend 目录执行: python check_es_connection.py
"""
import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_ROOT)

# 确保能读到 backend 根目录的 .env
if os.path.exists(os.path.join(_BACKEND_ROOT, ".env")):
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_BACKEND_ROOT, ".env"))

from es_config import ES_HOST, ES_PORT, ES_USERNAME, ES_PASSWORD, es

def main():
    print("当前 ES 配置:")
    print("  ES_HOST   =", ES_HOST)
    print("  ES_PORT   =", ES_PORT)
    print("  ES_USERNAME =", ES_USERNAME)
    print("  ES_PASSWORD =", "(已设置)" if ES_PASSWORD else "(未设置)")
    print()
    try:
        ok = es.ping()
        print("ES 连接: 成功" if ok else "ES 连接: 失败(ping 返回 False)")
        if ok:
            info = es.info()
            print("ES 版本:", info.get("version", {}).get("number", "?"))
    except Exception as e:
        print("ES 连接失败:", type(e).__name__, str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
