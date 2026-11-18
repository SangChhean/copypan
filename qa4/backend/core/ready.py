# -*- coding: utf-8 -*-
"""就绪检查：Redis / ES / Neo4j / lookups。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("qa4.ready")

# 仓库根 = qa4/backend/core → parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_QA4_ROOT = Path(__file__).resolve().parents[2]

# 匹配 ://user:pass@ 与 ://:pass@（空用户名）
_USERINFO_RE = re.compile(r"(://)([^/@\s]*):([^/@\s]*)@")
_SECRET_KV_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)\b\s*([=:])\s*([^\s,;]+)"
)
_ABS_PATH_RE = re.compile(
    r"(?i)(?:[A-Za-z]:[\\/][^\s\"']+|/(?:home|Users|var|tmp|opt|mnt|data)[^\s\"']+)"
)


def redact_secrets(text: str) -> str:
    """去掉 URL user:pass@ 与含 password/token/secret 的片段。"""
    if not text:
        return text
    out = _USERINFO_RE.sub(r"\1***:***@", text)
    out = _SECRET_KV_RE.sub(r"\1\2***", out)
    # 再扫一遍：token_xxx 紧贴在 ://: 后的形态（无独立 token= 键）
    out = re.sub(r"(://)\*\*\*:\*\*\*@", r"\1***:***@", out)
    return out


def _redacted_exc_info(exc: BaseException):
    """构造脱敏后的 exc_info，避免 traceback 末行泄露明文口令。"""
    try:
        redacted = type(exc)(redact_secrets(str(exc)))
    except Exception:
        redacted = RuntimeError(redact_secrets(str(exc)))
    return (type(redacted), redacted, exc.__traceback__)


def relativize_paths(text: str, *, extra_roots: Optional[list[Path]] = None) -> str:
    """把绝对路径改成相对仓库根 / qa4 / 额外根的相对路径。"""
    if not text:
        return text
    roots: list[Path] = []
    for r in [_REPO_ROOT, _QA4_ROOT, *(extra_roots or [])]:
        try:
            roots.append(r.resolve())
        except Exception:
            roots.append(r)

    def _repl(m: re.Match) -> str:
        raw = m.group(0)
        try:
            p = Path(raw)
            if not p.is_absolute():
                return raw
            for root in roots:
                try:
                    rel = p.resolve().relative_to(root)
                    return rel.as_posix()
                except Exception:
                    continue
            # 无法相对化：只保留末两级，避免泄露本机目录
            parts = p.parts
            if len(parts) >= 2:
                return "/".join(parts[-2:])
            return p.name
        except Exception:
            return "<path>"

    return _ABS_PATH_RE.sub(_repl, text)


def format_check_error(
    exc: BaseException,
    *,
    extra_roots: Optional[list[Path]] = None,
) -> str:
    """异常类型 + 简短原因；脱敏 + 相对路径。"""
    reason = redact_secrets(str(exc) or type(exc).__name__)
    reason = relativize_paths(reason, extra_roots=extra_roots)
    # 压成一行，避免响应体过长
    reason = " ".join(reason.split())
    if len(reason) > 300:
        reason = reason[:297] + "..."
    return f"{type(exc).__name__}: {reason}"


def _log_check_error(component: str, exc: BaseException, *, extra_roots=None) -> str:
    msg = format_check_error(exc, extra_roots=extra_roots)
    # 完整异常进服务端日志（exc_info 使用脱敏后的异常对象）
    logger.error(
        "ready check %s failed: %s | %s",
        component,
        msg,
        redact_secrets(repr(exc)),
        exc_info=_redacted_exc_info(exc),
    )
    return msg


def check_lookups(lookup_dir: Path) -> dict[str, Any]:
    try:
        from lookups.loader import load_lookups

        store = load_lookups(lookup_dir)
        return {
            "status": "ok",
            "lexicon_n": len(store.lexicon),
            "zui_n": len(store.zui_neizai),
        }
    except Exception as e:
        msg = _log_check_error("lookups", e, extra_roots=[Path(lookup_dir)])
        return {"status": "error", "message": msg}


def _safe_ping(component: str, client: Any) -> tuple[bool, Optional[str]]:
    if client is None:
        return False, f"MissingClient: {component} 未配置"
    try:
        ok = bool(client.ping())
        if ok:
            return True, None
        # ping 返回 False：尽量取客户端上的诊断
        detail = getattr(client, "last_ping_error", None)
        if isinstance(detail, dict) and detail:
            bits = [
                detail.get("exc_type") or "PingFalse",
                detail.get("message") or "ping()=False",
            ]
            if detail.get("status_code") is not None:
                bits.append(f"status={detail['status_code']}")
            raw = " ".join(str(b) for b in bits if b)
            msg = redact_secrets(raw)
            msg = relativize_paths(msg)
            logger.error("ready check %s ping false: %s", component, msg)
            return False, f"PingFalse: {msg}"
        return False, "PingFalse: ping()=False"
    except Exception as e:
        return False, _log_check_error(component, e)


def build_ready_report(
    *,
    redis_store: Any,
    es_client: Any,
    neo4j_client: Any,
    lookup_dir: Path,
    expected: dict[str, Any],
    index_map: Optional[dict] = None,
    llm_settings: Optional[dict[str, Any]] = None,
    prompts_info: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    overall = "ok"

    # Redis
    r_ok, r_msg = _safe_ping("redis", redis_store)
    checks["redis"] = {"status": "ok" if r_ok else "error", "ping": r_ok}
    if not r_ok:
        overall = "not_ready"
        if r_msg:
            checks["redis"]["message"] = r_msg

    # ES
    es_expected = expected.get("es") or {}
    es_ping, es_msg = _safe_ping("elasticsearch", es_client)
    if not es_ping:
        checks["elasticsearch"] = {"status": "error", "ping": False}
        if es_msg:
            checks["elasticsearch"]["message"] = es_msg
        overall = "not_ready"
    else:
        try:
            stats = es_client.stats_by_logical(es_expected)
            mismatches = [
                k for k, v in stats.items() if v.get("status") == "count_mismatch"
            ]
            missing = [
                k for k, v in stats.items() if v.get("status") in {"missing", "error"}
            ]
            st = "ok"
            if missing:
                st = "error"
                overall = "not_ready"
            elif mismatches:
                st = "degraded"
                if overall == "ok":
                    overall = "degraded"
            checks["elasticsearch"] = {
                "status": st,
                "ping": True,
                "indices": stats,
                "mismatches": mismatches,
                "missing": missing,
            }
            if st == "error":
                checks["elasticsearch"]["message"] = (
                    f"IndexError: missing={missing}" if missing else "IndexError"
                )
        except Exception as e:
            msg = _log_check_error("elasticsearch", e)
            checks["elasticsearch"] = {
                "status": "error",
                "ping": True,
                "message": msg,
            }
            overall = "not_ready"

    # Neo4j
    neo_expected = expected.get("neo4j") or {}
    n_ping, n_msg = _safe_ping("neo4j", neo4j_client)
    if not n_ping:
        checks["neo4j"] = {"status": "error", "ping": False}
        if n_msg:
            checks["neo4j"]["message"] = n_msg
        overall = "not_ready"
    else:
        try:
            labels = list(neo_expected.keys())
            counts = neo4j_client.label_counts(labels)
            mismatches = []
            missing = []
            for lb, exp in neo_expected.items():
                actual = counts.get(lb)
                if actual is None:
                    missing.append(lb)
                elif int(actual) != int(exp):
                    mismatches.append(
                        {"label": lb, "actual": actual, "expected": exp}
                    )
            st = "ok"
            if missing:
                st = "error"
                overall = "not_ready"
            elif mismatches:
                st = "degraded"
                if overall == "ok":
                    overall = "degraded"
            checks["neo4j"] = {
                "status": st,
                "ping": True,
                "counts": counts,
                "expected": neo_expected,
                "mismatches": mismatches,
                "missing": missing,
            }
            if st == "error":
                checks["neo4j"]["message"] = (
                    f"LabelError: missing={missing}" if missing else "LabelError"
                )
        except Exception as e:
            msg = _log_check_error("neo4j", e)
            checks["neo4j"] = {"status": "error", "ping": True, "message": msg}
            overall = "not_ready"

    # lookups
    lu = check_lookups(lookup_dir)
    checks["lookups"] = lu
    if lu.get("status") != "ok":
        overall = "not_ready"

    # llm（不联网）
    if llm_settings is not None:
        llm_mode = str(llm_settings.get("llm_mode") or "live")
        if llm_mode == "fake":
            llm = {"status": "ok", "mode": "fake", "message": "假模型模式，不检查密钥"}
        else:
            try:
                from core.llm_client import check_llm_ready

                llm = check_llm_ready(
                    key_present=bool(llm_settings.get("key_present")),
                    model_haiku=str(llm_settings.get("model_haiku") or ""),
                    model_sonnet=str(llm_settings.get("model_sonnet") or ""),
                    policy=llm_settings.get("policy"),
                )
            except Exception as e:
                llm = {
                    "status": "not_ready",
                    "message": format_check_error(e),
                }
            llm["mode"] = llm_mode
        checks["llm"] = llm
        st = llm.get("status")
        if st == "not_ready":
            overall = "not_ready"
        elif st == "degraded" and overall == "ok":
            overall = "degraded"

    # prompts（阶段 3）：live 且仍有占位 → degraded，并说明原因（路由会 503）
    if prompts_info is not None:
        mode = str(prompts_info.get("mode") or "live")
        ready = bool(prompts_info.get("ready"))
        ph = list(prompts_info.get("placeholder_steps") or [])
        if mode == "fake":
            checks["prompts"] = {
                "status": "ok",
                "mode": "fake",
                "placeholder_steps": ph,
                "ready": True,
            }
        elif ready:
            checks["prompts"] = {
                "status": "ok",
                "mode": mode,
                "placeholder_steps": [],
                "ready": True,
            }
        else:
            msg = prompts_info.get("message") or (
                f"提示词尚未就绪：{','.join(ph)}" if ph else "提示词尚未就绪"
            )
            checks["prompts"] = {
                "status": "degraded",
                "mode": mode,
                "placeholder_steps": ph,
                "ready": False,
                "message": msg,
            }
            if overall == "ok":
                overall = "degraded"

    return {"status": overall, "checks": checks}
