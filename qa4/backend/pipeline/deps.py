# -*- coding: utf-8 -*-
"""流水线依赖容器：按 QA4_LLM_MODE / QA4_RETRIEVAL_MODE 装配。

fake 模式完全不需要任何密钥、不连任何外部服务（缓存与限流用内存 store）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("qa4.pipeline")

_BACKEND = Path(__file__).resolve().parents[1]


def _devine_content_key(raw: Any) -> tuple[str, dict[str, Any]]:
    """把图谱/文件里的辩理形态规范成 (去重键, 展示用 payload)。

    已知形态：JSON 字符串或 dict，含 title/description/outline（probe_4/5）；
    亦可能是纯文本。去重键：strip 后的规范化文本。
    """
    obj: Any = raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return "", {"content": ""}
        try:
            obj = json.loads(s)
        except Exception:
            return s, {"content": s, "form": "plain_string"}
    if isinstance(obj, dict):
        # content_1 列表或单对象
        if "content_1" in obj and isinstance(obj["content_1"], list) and obj["content_1"]:
            obj = obj["content_1"][0]
        title = str(obj.get("title") or "").strip()
        desc = str(obj.get("description") or "").strip()
        outline = str(obj.get("outline") or "").strip()
        key = "\n".join(x for x in (title, desc, outline) if x).strip()
        return key, {"title": title, "description": desc, "outline": outline, "form": "json_object", "content": key}
    text = str(obj or "").strip()
    return text, {"content": text, "form": type(obj).__name__}


class DevineProvider:
    """辩理材料。fake：读占位夹具；live：图谱 Truth_Point.devine_argument。"""

    def __init__(
        self,
        items: Optional[list[dict[str, Any]]] = None,
        *,
        neo4j: Any = None,
        same_as: Optional[dict[str, str]] = None,
        reason: str = "",
        max_items: int = 2,
    ) -> None:
        self.items = items
        self.neo4j = neo4j
        self.same_as = dict(same_as or {})
        self.reason = reason
        self.max_items = int(max_items)

    @property
    def available(self) -> bool:
        return self.items is not None or self.neo4j is not None

    def _resolve(self, term: str) -> str:
        return self.same_as.get(term, term)

    def fetch(self, terms: list[str], max_items: Optional[int] = None) -> list[dict[str, Any]]:
        cap = int(max_items if max_items is not None else self.max_items)
        if cap <= 0:
            return []
        # fake 夹具路径
        if self.items is not None:
            out: list[dict[str, Any]] = []
            seen: set[str] = set()
            term_map: dict[str, list[str]] = {}
            for t in terms:
                rt = self._resolve(t)
                for it in self.items:
                    if it.get("term") not in (t, rt):
                        continue
                    c = str(it.get("content") or "")
                    key = c.strip()
                    if not key:
                        continue
                    term_map.setdefault(key, []).append(t)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({"term": t, "terms": term_map[key], "content": c})
                    if len(out) >= cap:
                        for row in out:
                            row["terms"] = term_map.get(str(row.get("content") or "").strip(), [row["term"]])
                        return out
            for row in out:
                row["terms"] = term_map.get(str(row.get("content") or "").strip(), [row["term"]])
            return out

        if self.neo4j is None:
            return []
        resolved = []
        orig_for: dict[str, list[str]] = {}
        for t in terms:
            r = self._resolve(t)
            resolved.append(r)
            orig_for.setdefault(r, []).append(t)
        rows = self.neo4j.devine_for_names(list(dict.fromkeys(resolved)))
        buckets: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for row in rows:
            name = str(row.get("name") or "")
            key, payload = _devine_content_key(row.get("devine_argument"))
            if not key:
                continue
            if key not in buckets:
                buckets[key] = {**payload, "terms": [], "term": (orig_for.get(name) or [name])[0]}
                order.append(key)
            for ot in orig_for.get(name, [name]):
                if ot not in buckets[key]["terms"]:
                    buckets[key]["terms"].append(ot)
        out = []
        for key in order[:cap]:
            b = buckets[key]
            out.append(
                {
                    "term": b["term"],
                    "terms": list(b["terms"]),
                    "content": b.get("content") or key,
                    "title": b.get("title"),
                    "form": b.get("form"),
                }
            )
        return out


@dataclass
class PipelineDeps:
    settings: Any
    cfg: dict[str, Any]
    llm: Any
    retrieval: Any
    targeted: Any
    reverse: Any
    lookups: Any
    definitions: Any
    devine: DevineProvider
    bible: Any
    prompts: Any
    store: Any
    cache: Any
    traces: Any
    llm_mode: str = "live"
    retrieval_mode: str = "live"
    feasts: list[dict[str, Any]] = field(default_factory=list)
    hymn_series: dict[str, Any] = field(default_factory=dict)
    life_books: list[dict[str, Any]] = field(default_factory=list)
    generic: dict[str, Any] = field(default_factory=dict)

    def prompts_ready(self) -> tuple[bool, list[str]]:
        ph = self.prompts.placeholder_steps()
        return (not ph, ph)

    def live_blocked(self) -> Optional[str]:
        """live 模式且仍有占位提示词 → 返回原因（路由 503）。"""
        if self.llm_mode != "live":
            return None
        ok, ph = self.prompts_ready()
        if ok:
            return None
        return f"{self.cfg.get('placeholder_unready_message', '提示词尚未就绪')}：{','.join(ph)}"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def build_deps(
    settings: Any,
    *,
    store: Any,
    es: Any = None,
    neo4j: Any = None,
    llm: Any = None,
    retrieval: Any = None,
    traces_db: Optional[Path] = None,
) -> PipelineDeps:
    from config import load_config_json
    from lookups.definitions import DefinitionStore, same_as_map
    from pipeline.cache import AnswerCache
    from pipeline.traces import TraceStore
    from prompts.loader import PromptRegistry
    from retrieval.targeted import TargetedFetcher
    from scripture.reverse import ReverseFinder

    cfg = load_config_json("pipeline.json")
    llm_mode = getattr(settings, "llm_mode", "live")
    ret_mode = getattr(settings, "retrieval_mode", "live")

    lookups = None
    try:
        from lookups.loader import load_lookups

        lookups = load_lookups(settings.lookup_dir)
    except Exception as e:
        logger.warning("lookups 加载失败（第 3/4/5 步核对降级）: %s", type(e).__name__)

    bible = None
    try:
        from scripture.bible_text import BibleText

        bible = BibleText(settings.bible_dir)
    except Exception as e:
        logger.warning("bible_data 不可用: %s", type(e).__name__)

    lex = lookups.lexicon if lookups else []
    definitions = DefinitionStore(Path(settings.graph_annotations_dir) / "truth_dictionary_3a3b.json", same_as=same_as_map(lex))

    if llm is None:
        if llm_mode == "fake":
            from core.llm_fake import PipelineFakeLLM

            llm = PipelineFakeLLM(model_haiku=settings.model_haiku, model_sonnet=settings.model_sonnet)
        else:
            llm = _LazyLiveLLM(settings, store)

    if ret_mode == "fake":
        from retrieval.fake import FakeRetrievalService, FakeSearchES, load_fixture

        fixture = load_fixture(_BACKEND / str(cfg.get("fake_passages_path")))
        retrieval = retrieval or FakeRetrievalService(fixture)
        by_lg: dict[str, list[dict[str, Any]]] = {}
        for p in fixture:
            by_lg.setdefault(p["_logical"], []).append(p)
        es_for_targeted = FakeSearchES(by_lg)
        from core.neo4j_client import FakeNeo4jClient

        graph = neo4j if neo4j is not None and getattr(neo4j, "uri", "") == "fake" else FakeNeo4jClient()
        devine_items = _read_json(_BACKEND / str(cfg.get("fake_devine_path")), {}).get("items") or []
        devine = DevineProvider(
            devine_items,
            same_as=same_as_map(lex),
            max_items=int(cfg.get("devine_max_items", 2)),
        )
    else:
        from retrieval.service import make_retrieval_service

        retrieval = retrieval or make_retrieval_service(settings, es, fake=False)
        es_for_targeted = es
        graph = neo4j
        if neo4j is not None:
            devine = DevineProvider(
                None,
                neo4j=neo4j,
                same_as=same_as_map(lex),
                max_items=int(cfg.get("devine_max_items", 2)),
            )
        else:
            devine = DevineProvider(None, reason="辩理材料：未提供 Neo4j 客户端")

    feasts = _read_json(Path(settings.lookup_dir) / "feasts.json", [])
    hymn_series = _read_json(Path(settings.lookup_dir) / "hymn_series.json", {})
    life_books = _read_json(Path(settings.lookup_dir) / "life_books.json", [])
    targeted = TargetedFetcher(es_for_targeted, bible=bible, feasts=feasts, retrieval=retrieval)
    reverse = ReverseFinder(graph=graph, definitions=definitions, retrieval=retrieval, bible=bible)

    prompts = PromptRegistry()
    model_config = {
        "haiku": settings.model_haiku,
        "sonnet": settings.model_sonnet,
        "policy": (getattr(settings, "llm_policy", {}) or {}).get("roles"),
        "mode": llm_mode,
    }
    cache = AnswerCache(store, cfg, prompt_version=prompts.version_key(), model_config=model_config)
    tcfg = cfg.get("traces") if isinstance(cfg.get("traces"), dict) else {}
    traces = TraceStore(
        traces_db or settings.traces_db_path,
        retention_days=int(tcfg.get("retention_days") or cfg.get("traces_retention_days", 90)),
        store=store,
        monitor_key=str(cfg.get("monitor_key", "monitor:traces")),
        monitor_cap=int(cfg.get("monitor_cap", 5000)),
        store_question_text=bool(tcfg.get("store_question_text", True)),
    )
    return PipelineDeps(
        settings=settings,
        cfg=cfg,
        llm=llm,
        retrieval=retrieval,
        targeted=targeted,
        reverse=reverse,
        lookups=lookups,
        definitions=definitions,
        devine=devine,
        bible=bible,
        prompts=prompts,
        store=store,
        cache=cache,
        traces=traces,
        llm_mode=llm_mode,
        retrieval_mode=ret_mode,
        feasts=feasts,
        hymn_series=hymn_series,
        life_books=life_books,
        generic=load_config_json("generic_words.json"),
    )


class _LazyLiveLLM:
    """live 模式：首次调用时才建 LLMClient（占位提示词时路由已 503，不会走到这里）。"""

    def __init__(self, settings: Any, store: Any) -> None:
        self._settings = settings
        self._store = store
        self._client = None

    def _get(self):
        if self._client is None:
            from core.llm_client import LLMClient, make_redis_usage_sink

            s = self._settings
            self._client = LLMClient(
                s.anthropic_api_key,
                base_url=s.anthropic_base_url,
                model_haiku=s.model_haiku,
                model_sonnet=s.model_sonnet,
                policy=s.llm_policy if isinstance(s.llm_policy, dict) and "roles" in s.llm_policy else {},
                max_concurrency_haiku=s.llm_max_concurrency_haiku,
                max_concurrency_sonnet=s.llm_max_concurrency_sonnet,
                timeout_haiku_s=s.llm_timeout_haiku_s,
                timeout_sonnet_s=s.llm_timeout_sonnet_s,
                max_retries=s.llm_max_retries,
                strict_model=s.llm_strict_model,
                usage_sink=make_redis_usage_sink(self._store),
            )
        return self._client

    @property
    def last_stream_result(self):
        return getattr(self._get(), "last_stream_result", None)

    async def complete(self, *a, **kw):
        return await self._get().complete(*a, **kw)

    async def complete_json(self, *a, **kw):
        return await self._get().complete_json(*a, **kw)

    def stream(self, *a, **kw):
        return self._get().stream(*a, **kw)
