"""
test_B 职事问答测试后端入口。

启动（在 test_B/ministry-qa/backend 目录）：
    uvicorn main:app --host 0.0.0.0 --port 8041 --reload
"""
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../../back_mic/backend/.env"))

from elasticsearch import Elasticsearch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from neo4j_client import Neo4jClient
from qa_router_b import router as qa_router_b

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ministry-qa")

_INDICES_BASE = ",".join([
    "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_bib", "kg-rag_map_note",
    "kg-rag_7feasts",
])

ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    es_client = Elasticsearch(
        hosts=[f"http://{ES_HOST}:{ES_PORT}"],
        basic_auth=(ES_USERNAME, ES_PASSWORD),
        request_timeout=30,
    )
    app.state.es_client = es_client
    app.state.es_indices = _INDICES_BASE
    logger.info("[ministry-qa] ES 客户端已初始化: %s:%s 索引=%s", ES_HOST, ES_PORT, _INDICES_BASE)

    neo4j = Neo4jClient()
    neo4j.startup()
    app.state.neo4j_client = neo4j
    concept_count = len(neo4j.get_concept_names())
    logger.info("[ministry-qa] Neo4j 概念词表加载完成: %d 个概念", concept_count)

    yield

    neo4j.shutdown()


app = FastAPI(title="test_B Ministry QA API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(qa_router_b)


@app.get("/ping")
def ping():
    return {"status": "ok", "service": "ministry-qa"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8041, reload=True)
