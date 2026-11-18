# -*- coding: utf-8 -*-
"""本机假后端：SeededFakeEs + PipelineFakeLLM + 内存缓存，不连真实 ES/Neo4j/Redis，不需密钥。

SeededFakeEs：为取具体对象（诗歌/生命读经）注入最小文档，便于前端看 direct 出处标题。
引文核对走真实 step08 finalize（〔未核实〕写在 done.answer / quote_checks）。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
_QA4 = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

INVITE = "DEVINVITE"
ADMIN = "dev-admin-token"
USER = "demo"
PASS = "pass1234"


SEED_HYMN = {
    "_id": "hymn-big-15",
    "chunk_id": "hymn-big-15",
    "series": "诗歌",
    "hymn_number": 15,
    "chunk_index": 0,
    "name": "大本 15",
    "book_title": "诗歌",
    "message_title": "第15首",
    "text": "（假后端占位歌词，非职事原文）主啊我爱你。",
}
SEED_LIFE = {
    "_id": "life-rom-3",
    "chunk_id": "life-rom-3",
    "book_title": "罗马书生命读经",
    "message_title": "第三篇",
    "message_number": 3,
    "chunk_index": 1,
    "text": "（假后端占位纲目段落）关于称义的要点。",
}


def seed_docs_by_logical() -> dict[str, list[dict[str, Any]]]:
    return {"hymns": [dict(SEED_HYMN)], "outline_12490": [dict(SEED_LIFE)]}


def merge_seeded_search_es(fixture_docs: list[dict[str, Any]] | None = None):
    """夹具段落 + 取对象种子 → FakeSearchES（供 fake 模式 targeted）。"""
    from retrieval.fake import FakeSearchES, load_fixture

    by_lg: dict[str, list[dict[str, Any]]] = {}
    for p in fixture_docs if fixture_docs is not None else load_fixture():
        by_lg.setdefault(str(p.get("_logical") or "text_others"), []).append(dict(p))
    for lg, docs in seed_docs_by_logical().items():
        by_lg.setdefault(lg, []).extend(docs)
    return FakeSearchES(by_lg)


def _targeted_with_seeds(deps: Any):
    from retrieval.targeted import TargetedFetcher

    es_t = merge_seeded_search_es()
    return TargetedFetcher(
        es_t,
        bible=getattr(deps, "bible", None),
        feasts=list(getattr(deps, "feasts", None) or []),
        retrieval=getattr(deps, "retrieval", None),
    )


class SeededFakeEs:
    """可 search 的假 ES：种子文档供 targeted 取诗歌/生命读经。"""

    def __init__(self, *, reachable: bool = True):
        from core.es_client import FakeEsClient

        self._ping = FakeEsClient(reachable=reachable)
        self.url = "fake-seeded"
        self.index_map = {}
        self.last_ping_error = self._ping.last_ping_error
        self._search = merge_seeded_search_es([])

    def ping(self) -> bool:
        ok = self._ping.ping()
        self.last_ping_error = self._ping.last_ping_error
        return ok

    def index_exists(self, index: str) -> bool:
        return True

    def count(self, index: str) -> Optional[int]:
        return 1

    def stats_by_logical(self, expected: dict[str, int]) -> dict[str, dict]:
        return self._ping.stats_by_logical(expected)

    def search(self, index: str, body: dict, *, scroll: Optional[str] = None) -> dict:
        return self._search.search(index, body)

    def scroll(self, *, scroll_id: str, scroll: str = "2m") -> dict:
        return {"hits": {"hits": []}, "_scroll_id": scroll_id}

    def clear_scroll(self, *, scroll_id: str) -> None:
        return None

    def get_mapping(self, index: str) -> dict:
        return {index: {"mappings": {}}}


def main() -> int:
    os.environ.setdefault("QA4_LLM_MODE", "fake")
    os.environ.setdefault("QA4_RETRIEVAL_MODE", "fake")
    os.environ.setdefault("QA4_PROMPT_CHANNEL", os.environ.get("QA4_PROMPT_CHANNEL") or "draft")
    os.environ.setdefault("QA4_JWT_SECRET", "dev-fake-jwt-not-a-real-secret")
    os.environ.setdefault("QA4_ADMIN_TOKEN", ADMIN)
    os.environ.setdefault("QA4_DAILY_LIMIT_DEFAULT", "100")
    os.environ.setdefault("QA4_RATE_LIMIT_PER_MINUTE", "1000")
    # 不读真实 anthropic key
    os.environ.pop("QA4_ANTHROPIC_API_KEY", None)

    tmp = Path(tempfile.mkdtemp(prefix="qa4_dev_fake_"))
    os.environ["QA4_DATA_DIR"] = str(_QA4 / "data")
    os.environ["QA4_LOOKUP_DIR"] = str(_QA4 / "data" / "lookups")
    os.environ["QA4_GRAPH_ANNOTATIONS_DIR"] = str(_QA4 / "data" / "graph_annotations")

    from config import reset_settings_cache, get_settings
    from core.auth import AuthStore
    from core.neo4j_client import FakeNeo4jClient
    from core.redis_store import MemoryStore
    from main import create_app
    from pipeline.deps import build_deps
    import uvicorn

    reset_settings_cache()
    settings = get_settings(require_runtime=False)
    settings.traces_db_path = tmp / "traces.db"
    store = MemoryStore(prefix="qa4:")
    auth = AuthStore(
        tmp / "users.db",
        jwt_secret=settings.jwt_secret,
        jwt_expire_days=7,
        daily_limit_default=100,
        tz_name="UTC",
        admin_token=ADMIN,
    )
    auth.create_invite(INVITE, max_uses=1000)
    try:
        auth.register(INVITE, USER, PASS)
    except Exception:
        pass

    es = SeededFakeEs(reachable=True)
    deps = build_deps(
        settings,
        store=store,
        es=es,
        neo4j=FakeNeo4jClient(reachable=True),
        traces_db=tmp / "traces.db",
    )
    # retrieval_mode=fake 时 build_deps 用夹具 FakeSearchES，不含诗歌种子 → 再挂载合并版
    deps.targeted = _targeted_with_seeds(deps)
    app = create_app(
        settings,
        redis_store=store,
        es_client=es,
        neo4j_client=FakeNeo4jClient(reachable=True),
        auth_store=auth,
        pipeline_deps=deps,
    )

    port = int(os.environ.get("QA4_PORT") or getattr(settings, "port", None) or 8030)
    print("=== qa4 fake 开发服 ===")
    print(f"监听: http://127.0.0.1:{port}")
    print(f"邀请码: {INVITE}")
    print(f"演示账号: {USER} / {PASS}")
    print(f"管理令牌: {ADMIN}")
    print(f"提示词通道: {os.environ.get('QA4_PROMPT_CHANNEL')}")
    print("事件覆盖: step/plan/token/direct/choose/done/error（及 heartbeat）")
    print("done.answer 含引文核对后正文；quote_checks 含核对结果。")
    print("不连真实 ES/Neo4j/Redis；无 Anthropic 密钥。")
    print("前端: cd qa4/frontend && npm run dev （代理 /api → 本端口）")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
