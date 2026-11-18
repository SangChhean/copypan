"""qa4 配置：仅读 QA4_ 前缀环境变量；可选 QA4_ENV_FILE。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


class ConfigError(RuntimeError):
    """配置缺失或非法。"""


def _env() -> Any:
    return getattr(os, "environ")


def _load_env_file(path: Path) -> None:
    """简单 KEY=VALUE 加载；不打印取值。已存在的环境变量不覆盖。"""
    text = path.read_text(encoding="utf-8")
    env = _env()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in env:
            env[key] = value


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    return _env().get(name, default)


def _require(name: str) -> str:
    value = _env().get(name)
    if value is None or str(value).strip() == "":
        raise ConfigError(f"缺少必要配置项：{name}")
    return value


@dataclass
class Settings:
    port: int
    data_dir: Path
    lookup_dir: Path
    redis_url: str
    redis_prefix: str
    es_url: str
    es_user: str
    es_secret: str
    es_verify: bool
    neo4j_uri: str
    neo4j_user: str
    neo4j_secret: str
    claude_api_key: str
    openrouter_api_key: str
    model_fast: str
    model_main: str
    daily_limit_default: int
    fake_llm: bool
    jwt_secret: str
    jwt_expire_days: int
    admin_token: str
    tz_name: str
    rate_limit_per_minute: int
    index_map: dict[str, Any] = field(default_factory=dict)
    expected_counts: dict[str, Any] = field(default_factory=dict)
    # 阶段 1b
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    model_haiku: str = "claude-haiku-5-5"
    model_sonnet: str = "claude-sonnet-5-5"
    llm_max_concurrency_haiku: int = 16
    llm_max_concurrency_sonnet: int = 6
    llm_timeout_haiku_s: float = 30.0
    llm_timeout_sonnet_s: float = 120.0
    llm_max_retries: int = 2
    llm_strict_model: bool = False
    llm_policy: dict[str, Any] = field(default_factory=dict)
    # 阶段 2：经文 / 检索
    bible_dir: Path = field(default_factory=lambda: _QA4_ROOT / "data" / "bible_data")
    graph_annotations_dir: Path = field(
        default_factory=lambda: _QA4_ROOT / "data" / "graph_annotations"
    )
    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_model: str = "qwen/qwen3-embedding-8b"
    rerank_base_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = "jina-reranker-v3"
    # 阶段 3：模式开关与记录
    llm_mode: str = "live"
    retrieval_mode: str = "live"
    traces_db_path: Path = field(
        default_factory=lambda: _QA4_ROOT / "data" / "qa4_traces.db"
    )
    # 本机调试：免登录（默认关；仅允许绑定回环）
    dev_autologin: bool = False
    bind_host: str = "0.0.0.0"


_SETTINGS: Optional[Settings] = None
_CONFIG_DIR = Path(__file__).resolve().parent
_QA4_ROOT = _CONFIG_DIR.parents[1]


def load_config_json(name: str) -> dict[str, Any]:
    """读取 config/ 下的 json（阶段 2/3 新增配置用）。"""
    return json.loads((_CONFIG_DIR / name).read_text(encoding="utf-8"))


def load_expected_counts() -> dict[str, Any]:
    path = _CONFIG_DIR / "expected_counts.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_index_map() -> dict[str, Any]:
    path = _CONFIG_DIR / "index_map.json"
    return json.loads(path.read_text(encoding="utf-8"))


def get_settings(*, require_runtime: bool = False) -> Settings:
    """加载并缓存配置。

    require_runtime=True 时要求 JWT 等必要项（启动服务用）。
    ES/Neo4j/Redis 可空：就绪探针报告，不阻止启动。
    """
    global _SETTINGS
    if _SETTINGS is not None:
        return _SETTINGS

    env_file = _get("QA4_ENV_FILE")
    if env_file:
        path = Path(env_file)
        if not path.is_file():
            raise ConfigError(f"QA4_ENV_FILE 指向的文件不存在")
        _load_env_file(path)

    port = int(_get("QA4_PORT", "8030") or "8030")
    data_dir_raw = _get("QA4_DATA_DIR")
    lookup_dir_raw = _get("QA4_LOOKUP_DIR")

    backend_root = Path(__file__).resolve().parents[1]
    qa4_root = backend_root.parent
    # 用户库目录与查表目录独立：查表默认固定为仓库内 qa4/data/lookups，不随 QA4_DATA_DIR
    data_dir = Path(data_dir_raw) if data_dir_raw else (qa4_root / "data")
    lookup_dir = (
        Path(lookup_dir_raw) if lookup_dir_raw else (qa4_root / "data" / "lookups")
    )

    redis_prefix = _get("QA4_REDIS_PREFIX", "qa4:") or "qa4:"
    model_fast = _get("QA4_MODEL_FAST", "claude-haiku-5-5") or "claude-haiku-5-5"
    model_main = _get("QA4_MODEL_MAIN", "claude-sonnet-5-5") or "claude-sonnet-5-5"
    daily_limit = int(_get("QA4_DAILY_LIMIT_DEFAULT", "30") or "30")
    fake_llm = (_get("QA4_FAKE_LLM", "0") or "0").strip() in {"1", "true", "True", "yes", "YES"}
    jwt_expire_days = int(_get("QA4_JWT_EXPIRE_DAYS", "7") or "7")
    tz_name = (_get("QA4_TZ", "UTC") or "UTC").strip()
    rate_limit = int(_get("QA4_RATE_LIMIT_PER_MINUTE", "15") or "15")
    es_verify = (_get("QA4_ES_VERIFY", "1") or "1").strip() not in {"0", "false", "False", "no"}

    redis_url = _get("QA4_REDIS_URL", "") or ""
    es_url = _get("QA4_ES_URL", "") or ""
    es_user = _get("QA4_ES_USER", "") or ""
    es_secret = _get("QA4_ES_PASSWORD", "") or ""
    neo4j_uri = _get("QA4_NEO4J_URI", "") or ""
    neo4j_user = _get("QA4_NEO4J_USER", "") or ""
    neo4j_secret = _get("QA4_NEO4J_PASSWORD", "") or ""
    claude_api_key = _get("CLAUDE_API_KEY", "") or ""
    openrouter_api_key = _get("OPENROUTER_API_KEY", "") or ""
    jwt_secret = _get("QA4_JWT_SECRET", "") or ""
    admin_token = _get("QA4_ADMIN_TOKEN", "") or ""

    # 1b：优先 QA4_ANTHROPIC_API_KEY，否则回退 CLAUDE_API_KEY
    anthropic_api_key = (_get("QA4_ANTHROPIC_API_KEY", "") or "").strip() or claude_api_key
    anthropic_base_url = (
        (_get("QA4_ANTHROPIC_BASE_URL", "") or "").strip() or "https://api.anthropic.com"
    )
    model_haiku = (_get("QA4_MODEL_HAIKU", "") or "").strip() or model_fast
    model_sonnet = (_get("QA4_MODEL_SONNET", "") or "").strip() or model_main
    llm_max_concurrency_haiku = int(_get("QA4_LLM_MAX_CONCURRENCY_HAIKU", "16") or "16")
    llm_max_concurrency_sonnet = int(_get("QA4_LLM_MAX_CONCURRENCY_SONNET", "6") or "6")
    llm_timeout_haiku_s = float(_get("QA4_LLM_TIMEOUT_HAIKU_S", "30") or "30")
    llm_timeout_sonnet_s = float(_get("QA4_LLM_TIMEOUT_SONNET_S", "120") or "120")
    llm_max_retries = int(_get("QA4_LLM_MAX_RETRIES", "2") or "2")
    llm_strict_model = (_get("QA4_LLM_STRICT_MODEL", "0") or "0").strip() in {
        "1",
        "true",
        "True",
        "yes",
        "YES",
    }

    if require_runtime and not jwt_secret:
        raise ConfigError("缺少必要配置项：QA4_JWT_SECRET")

    llm_policy: dict[str, Any] = {}
    try:
        from core.llm_client import load_llm_policy

        llm_policy = load_llm_policy(_CONFIG_DIR / "llm_policy.json")
    except Exception as e:
        # 启动不因策略文件暂时失败而阻断 get_settings（readyz 会报）
        llm_policy = {"_load_error": type(e).__name__}

    _SETTINGS = Settings(
        port=port,
        data_dir=data_dir,
        lookup_dir=lookup_dir,
        redis_url=redis_url,
        redis_prefix=redis_prefix,
        es_url=es_url,
        es_user=es_user,
        es_secret=es_secret,
        es_verify=es_verify,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_secret=neo4j_secret,
        claude_api_key=claude_api_key,
        openrouter_api_key=openrouter_api_key,
        model_fast=model_fast,
        model_main=model_main,
        daily_limit_default=daily_limit,
        fake_llm=fake_llm,
        jwt_secret=jwt_secret or "test-secret-not-for-production",
        jwt_expire_days=jwt_expire_days,
        admin_token=admin_token,
        tz_name=tz_name,
        rate_limit_per_minute=rate_limit,
        index_map=load_index_map(),
        expected_counts=load_expected_counts(),
        anthropic_api_key=anthropic_api_key,
        anthropic_base_url=anthropic_base_url,
        model_haiku=model_haiku,
        model_sonnet=model_sonnet,
        llm_max_concurrency_haiku=llm_max_concurrency_haiku,
        llm_max_concurrency_sonnet=llm_max_concurrency_sonnet,
        llm_timeout_haiku_s=llm_timeout_haiku_s,
        llm_timeout_sonnet_s=llm_timeout_sonnet_s,
        llm_max_retries=llm_max_retries,
        llm_strict_model=llm_strict_model,
        llm_policy=llm_policy,
        bible_dir=data_dir / "bible_data",
        graph_annotations_dir=(
            Path(_get("QA4_GRAPH_ANNOTATIONS_DIR") or "")
            if _get("QA4_GRAPH_ANNOTATIONS_DIR")
            else data_dir / "graph_annotations"
        ),
        embed_base_url=(_get("QA4_EMBED_BASE_URL", "") or "").strip(),
        embed_api_key=(_get("QA4_EMBED_API_KEY", "") or "").strip(),
        embed_model=(_get("QA4_EMBED_MODEL", "") or "").strip() or "qwen/qwen3-embedding-8b",
        rerank_base_url=(_get("QA4_RERANK_BASE_URL", "") or "").strip(),
        rerank_api_key=(_get("QA4_RERANK_API_KEY", "") or "").strip(),
        rerank_model=(_get("QA4_RERANK_MODEL", "") or "").strip() or "jina-reranker-v3",
        llm_mode=_mode_value("QA4_LLM_MODE"),
        retrieval_mode=_mode_value("QA4_RETRIEVAL_MODE"),
        traces_db_path=data_dir / "qa4_traces.db",
        dev_autologin=_flag("QA4_DEV_AUTOLOGIN", "0"),
        bind_host=(_get("QA4_BIND_HOST", "0.0.0.0") or "0.0.0.0").strip() or "0.0.0.0",
    )
    return _SETTINGS


def _mode_value(name: str) -> str:
    """fake | live；非法值按 live（保守：live 下占位提示词会 503）。"""
    v = (_get(name, "live") or "live").strip().lower()
    return v if v in {"fake", "live"} else "live"


def _flag(name: str, default: str = "0") -> bool:
    return (_get(name, default) or default).strip() in {"1", "true", "True", "yes", "YES"}


def is_loopback_bind(host: str) -> bool:
    """服务监听地址是否为本机回环（不含 0.0.0.0）。"""
    return (host or "").strip().lower() in {"127.0.0.1", "::1"}


def is_loopback_client(host: Optional[str]) -> bool:
    """请求对端是否为本机回环。"""
    h = (host or "").strip().lower()
    if h in {"127.0.0.1", "::1", "localhost"}:
        return True
    # IPv4-mapped IPv6
    if h.startswith("::ffff:") and h.rsplit(":", 1)[-1] == "127.0.0.1":
        return True
    return False


def assert_dev_autologin_safe(settings: "Settings") -> None:
    """QA4_DEV_AUTOLOGIN 开启时必须绑定回环，否则拒绝启动。"""
    if getattr(settings, "dev_autologin", False) and not is_loopback_bind(
        getattr(settings, "bind_host", "") or ""
    ):
        raise ConfigError(
            "QA4_DEV_AUTOLOGIN 已开启，但绑定地址不是 127.0.0.1/::1（见 QA4_BIND_HOST）；拒绝启动"
        )


def reset_settings_cache() -> None:
    global _SETTINGS
    _SETTINGS = None
