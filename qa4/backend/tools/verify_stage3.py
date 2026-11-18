# -*- coding: utf-8 -*-
"""阶段 3 离线验证：fake 模式 + TestClient。

含既有五场景 + 规则前置（经文/诗歌/歌词）场景。
不联网、不需要任何环境变量。最后一行 STAGE3 OFFLINE: ALL PASS 或列出失败项。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
QA4 = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    extra = f" · {detail}" if detail else ""
    print(f"{mark} {name}{extra}")
    return cond


def _step3_calls(deps) -> int:
    return sum(1 for c in (deps.llm.calls or []) if c.get("step") == "step3")


def _install_synth_lyrics() -> None:
    from hymn.lyrics import LyricsIndex, reset_lyrics_index
    import hymn.lyrics as L

    rows = json.loads((BACKEND / "tests" / "fixtures" / "synth_lyrics_rows.json").read_text(encoding="utf-8"))
    reset_lyrics_index()
    L._INDEX = LyricsIndex.from_rows(rows)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="qa4_verify_s3_"))
    os.environ["QA4_LLM_MODE"] = "fake"
    os.environ["QA4_RETRIEVAL_MODE"] = "fake"
    os.environ["QA4_JWT_SECRET"] = "verify-stage3-jwt"
    os.environ["QA4_ADMIN_TOKEN"] = "verify-adm"
    # 用仓库 data 以便 bible_data / lookups 可加载；用户库与 traces 落到临时目录
    os.environ["QA4_DATA_DIR"] = str(QA4 / "data")
    os.environ["QA4_LOOKUP_DIR"] = str(QA4 / "data" / "lookups")
    os.environ["QA4_GRAPH_ANNOTATIONS_DIR"] = str(QA4 / "data" / "graph_annotations")
    os.environ["QA4_DAILY_LIMIT_DEFAULT"] = "100"
    os.environ["QA4_RATE_LIMIT_PER_MINUTE"] = "1000"

    from config import reset_settings_cache, get_settings
    from core.auth import AuthStore
    from core.es_client import FakeEsClient
    from core.neo4j_client import FakeNeo4jClient
    from core.redis_store import MemoryStore
    from fastapi.testclient import TestClient
    from main import create_app
    from pipeline.deps import build_deps

    reset_settings_cache()
    settings = get_settings(require_runtime=False)
    settings.traces_db_path = tmp / "traces.db"
    store = MemoryStore(prefix="qa4:")
    auth = AuthStore(
        tmp / "users.db",
        jwt_secret="verify-stage3-jwt",
        jwt_expire_days=1,
        daily_limit_default=100,
        tz_name="UTC",
        admin_token="verify-adm",
    )
    auth.create_invite("V", max_uses=10)
    auth.register("V", "vuser", "pass1234")
    deps = build_deps(
        settings,
        store=store,
        es=FakeEsClient(reachable=True),
        neo4j=FakeNeo4jClient(reachable=True),
        traces_db=tmp / "traces.db",
    )
    app = create_app(
        settings,
        redis_store=store,
        es_client=FakeEsClient(reachable=True),
        neo4j_client=FakeNeo4jClient(reachable=True),
        auth_store=auth,
        pipeline_deps=deps,
    )
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"username": "vuser", "password": "pass1234"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}

    fails: list[str] = []

    def ask(q: str, history=None):
        r = c.post("/api/qa/ask", headers=h, json={"question": q, "history": history or []})
        return r.status_code, r.json()

    # 1 简单
    code, body = ask("什么是神的爱")
    ev = body.get("events") or []
    print("场景1 简单 事件:", " → ".join(ev))
    ok = code == 200 and "plan" in ev and "token" in ev and ev[-1] == "done" and body.get("citations")
    if not _ok("场景1 简单问题端到端", ok, f"code={code}"):
        fails.append("simple")

    # 2 追问 + 缓存
    ask("神的爱是什么")
    code, body = ask(
        "请再说【改写:神的爱是什么】",
        history=[
            {"question": "a", "answer": "x" * 400},
            {"question": "b", "answer": "y" * 400},
            {"question": "c", "answer": "z" * 400},
            {"question": "d", "answer": "w" * 400},
        ],
    )
    print("场景2 追问 事件:", " → ".join(body.get("events") or []), "cache_hit=", body.get("cache_hit"))
    ok = code == 200 and body.get("cache_hit") is True
    if not _ok("场景2 追问改写后缓存命中", ok):
        fails.append("followup")

    # 3 拆分
    code, body = ask("【拆】请比较神的爱与爱神")
    print("场景3 拆分 事件:", " → ".join(body.get("events") or []), "type=", body.get("main_type"))
    ok = code == 200 and "plan" in (body.get("events") or [])
    if not _ok("场景3 复杂拆分", ok):
        fails.append("split")

    # 4 定向诗歌
    code, body = ask("请取【诗歌1】")
    ev = body.get("events") or []
    print("场景4 定向 事件:", " → ".join(ev))
    ok = code == 200 and "direct" in ev and "token" not in ev
    if not _ok("场景4 诗歌定向取篇", ok):
        fails.append("targeted")

    # 5 缓存命中第二次
    ask("什么是召会生活")
    n_calls = len(deps.llm.calls)
    code, body = ask("什么是召会生活")
    print("场景5 缓存 事件:", " → ".join(body.get("events") or []), "cache_hit=", body.get("cache_hit"))
    ok = code == 200 and body.get("cache_hit") is True and len(deps.llm.calls) == n_calls
    if not _ok("场景5 二次缓存命中且不再调模型", ok, f"calls_delta={len(deps.llm.calls)-n_calls}"):
        fails.append("cache")

    # ---- 规则前置场景 ----
    _install_synth_lyrics()

    # 6 纯出处经文
    n0 = _step3_calls(deps)
    code, body = ask("约3:16")
    ev = body.get("events") or []
    print("场景6 经文规则 事件:", " → ".join(ev), "source=", body.get("plan_source"), "type=", body.get("main_type"))
    ok = (
        code == 200
        and body.get("main_type") == "经文"
        and body.get("plan_source") == "scripture_rule"
        and "direct" in ev
        and _step3_calls(deps) == n0
    )
    if not _ok("场景6 纯出处经文规则短路", ok, f"step3_delta={_step3_calls(deps)-n0}"):
        fails.append("rule_scripture")

    # 7 纯出处诗歌
    n0 = _step3_calls(deps)
    code, body = ask("诗歌第1首")
    ev = body.get("events") or []
    print("场景7 诗歌规则 事件:", " → ".join(ev), "source=", body.get("plan_source"))
    ok = (
        code == 200
        and body.get("main_type") == "诗歌"
        and body.get("plan_source") == "hymn_rule"
        and "direct" in ev
        and _step3_calls(deps) == n0
    )
    if not _ok("场景7 纯出处诗歌规则短路", ok, f"step3_delta={_step3_calls(deps)-n0}"):
        fails.append("rule_hymn")

    # 8 歌词单首
    n0 = _step3_calls(deps)
    code, body = ask("哪首诗歌有这句：合成朝阳升起照亮测试山谷溪流")
    ev = body.get("events") or []
    print("场景8 歌词单首 事件:", " → ".join(ev), "source=", body.get("plan_source"))
    ok = (
        code == 200
        and body.get("plan_source") == "lyrics_rule"
        and body.get("main_type") == "诗歌"
        and "direct" in ev
        and _step3_calls(deps) == n0
    )
    if not _ok("场景8 歌词单首取整首", ok):
        fails.append("lyrics_one")

    # 9 歌词多首
    n0 = _step3_calls(deps)
    code, body = ask("哪首诗歌有这句：合成双命中专有短句金银铜铁")
    ev = body.get("events") or []
    print("场景9 歌词多首 事件:", " → ".join(ev), "awaiting=", body.get("awaiting_choice"))
    ok = (
        code == 200
        and body.get("awaiting_choice") is True
        and "choose" in ev
        and _step3_calls(deps) == n0
        and "合成双命中" in (body.get("answer") or "")
    )
    if not _ok("场景9 歌词多首 choose", ok):
        fails.append("lyrics_multi")

    # 10 too_short
    n0 = _step3_calls(deps)
    code, body = ask("哪首诗歌有这句：啊")
    print("场景10 too_short status=", body.get("lyrics_status"))
    ok = code == 200 and body.get("lyrics_status") == "too_short" and _step3_calls(deps) == n0
    if not _ok("场景10 歌词 too_short", ok):
        fails.append("lyrics_short")

    # 11 too_common
    n0 = _step3_calls(deps)
    code, body = ask("哪首诗歌有这句：合成共用短句重复出现在多样例中")
    print("场景11 too_common status=", body.get("lyrics_status"))
    ok = code == 200 and body.get("lyrics_status") == "too_common" and _step3_calls(deps) == n0
    if not _ok("场景11 歌词 too_common", ok):
        fails.append("lyrics_common")

    # 12 歌词 not_found → 模型
    n0 = _step3_calls(deps)
    code, body = ask("哪首诗歌有这句：完全虚构绝无命中的合成长句甲乙丙丁戊己")
    print("场景12 歌词未命中 事件:", " → ".join(body.get("events") or []), "source=", body.get("plan_source"))
    ok = code == 200 and _step3_calls(deps) == n0 + 1 and body.get("plan_source") in {None, "model", ""}
    if not _ok("场景12 歌词 not_found 落入模型", ok, f"step3_delta={_step3_calls(deps)-n0}"):
        fails.append("lyrics_miss")

    # 13 带实质问题的出处：不短路、有 rule_hits、调模型
    n0 = _step3_calls(deps)
    code, body = ask("约3:16是什么意思")
    hits = body.get("rule_hits") or []
    print("场景13 实质问题 事件:", " → ".join(body.get("events") or []), "hits=", hits)
    ok = (
        code == 200
        and _step3_calls(deps) == n0 + 1
        and any(h.get("kind") == "scripture" for h in hits)
        and body.get("plan_source") in {None, "model", ""}
    )
    if not _ok("场景13 实质问题不短路且记 rule_hits", ok):
        fails.append("substantive")

    # 14 开关关闭
    deps.cfg = dict(deps.cfg)
    deps.cfg["rule_preplan_enabled"] = False
    n0 = _step3_calls(deps)
    code, body = ask("约3:16")
    print("场景14 开关关闭 source=", body.get("plan_source"), "type=", body.get("main_type"))
    ok = code == 200 and _step3_calls(deps) == n0 + 1 and body.get("plan_source") in {None, "model", ""}
    if not _ok("场景14 rule_preplan 关闭走模型", ok):
        fails.append("switch_off")
    deps.cfg["rule_preplan_enabled"] = True

    # live 503 抽查
    deps.llm_mode = "live"
    code, body = ask("什么是神的爱")
    ok = code == 503 and "提示词" in (body.get("message") or "")
    if not _ok("live 占位提示词返回 503", ok, f"code={code}"):
        fails.append("live503")
    deps.llm_mode = "fake"

    # ---- 场景 15+：草稿通道（不改既有场景断言）----
    from prompts.loader import PromptRegistry

    prev_ch = os.environ.get("QA4_PROMPT_CHANNEL")
    os.environ["QA4_PROMPT_CHANNEL"] = "draft"
    deps.prompts = PromptRegistry(channel="draft")
    # 15 草稿通道一般问题
    code, body = ask("什么是神的爱")
    print("场景15 草稿一般 source=", body.get("plan_source"), "type=", body.get("main_type"))
    ok = code == 200 and body.get("main_type") in {"定义", "默认"}
    if not _ok("场景15 草稿通道一般问题", ok):
        fails.append("draft_general")
    # 16 比较
    code, body = ask("【比较】比较神的爱与爱神")
    print("场景16 草稿比较 type=", body.get("main_type"))
    ok = code == 200 and body.get("main_type") == "比较"
    if not _ok("场景16 草稿比较类", ok):
        fails.append("draft_compare")
    # 17 复杂拆分
    code, body = ask("【拆】请说明神的爱并如何经历")
    nsq = len((body.get("plan") or {}).get("subquestions") or body.get("subquestions") or [])
    # 响应里未必有 plan 全文；看 events 含 plan 且不 500
    print("场景17 草稿复杂 events=", " → ".join((body.get("events") or [])[:8]), "nsq~", nsq)
    ok = code == 200 and "plan" in (body.get("events") or [])
    if not _ok("场景17 草稿复杂拆分有 plan 事件", ok):
        fails.append("draft_complex")
    # 18 敏感
    code, body = ask("【敏感】怎样看这件事")
    ok = code == 200
    if not _ok("场景18 草稿敏感不崩溃", ok, f"code={code}"):
        fails.append("draft_sensitive")
    # 恢复
    if prev_ch is None:
        os.environ.pop("QA4_PROMPT_CHANNEL", None)
    else:
        os.environ["QA4_PROMPT_CHANNEL"] = prev_ch
    deps.prompts = PromptRegistry()

    if fails:
        print("STAGE3 OFFLINE: FAIL · " + ",".join(fails))
        return 1
    print("STAGE3 OFFLINE: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
