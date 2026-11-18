# -*- coding: utf-8 -*-
"""Read-only ES check for panai4_hymns. Never prints secrets."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

OUT = Path(r"G:\PanAI4.0专用\logs\hymn\hymn_es_check.json")
OUT.parent.mkdir(parents=True, exist_ok=True)

env = Path(r"G:/copypan/back_mic/backend/.env")
result: dict = {"env_file": str(env), "env_exists": env.is_file()}

if not env.is_file():
    result["status"] = "no_env"
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    sys.exit(0)

try:
    from dotenv import load_dotenv
except ImportError:
    result["status"] = "no_dotenv"
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    sys.exit(0)

load_dotenv(env)

remote_host = (os.getenv("ES_REMOTE_HOST") or "").strip()
local_host = (os.getenv("ES_HOST") or "").strip()
result["remote_host_set"] = bool(remote_host)
result["local_host_set"] = bool(local_host)
result["remote_pw_set"] = bool((os.getenv("ES_REMOTE_PASSWORD") or "").strip())
result["local_pw_set"] = bool((os.getenv("ES_PASSWORD") or "").strip())

try:
    from elasticsearch import Elasticsearch
except ImportError as e:
    result["status"] = "no_elasticsearch_pkg"
    result["err"] = type(e).__name__
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    sys.exit(0)


def probe(label: str, es: Elasticsearch) -> dict:
    info: dict = {"label": label}
    try:
        info["ping"] = bool(es.ping())
    except Exception as e:
        info["ping"] = False
        info["ping_err"] = f"{type(e).__name__}: {str(e)[:160]}"
        return info
    for name in ("panai4_hymns", "qa4_hymns"):
        entry: dict = {}
        try:
            exists = es.indices.exists(index=name)
            entry["exists"] = bool(exists)
            if exists:
                entry["count"] = int(es.count(index=name)["count"])
                m = es.indices.get_mapping(index=name)[name]["mappings"]["properties"]
                text = m.get("text") or {}
                entry["text"] = {
                    "type": text.get("type"),
                    "analyzer": text.get("analyzer"),
                    "search_analyzer": text.get("search_analyzer"),
                    "fields": sorted((text.get("fields") or {}).keys()),
                }
                entry["property_names"] = sorted(m.keys())
        except Exception as e:
            entry["err"] = f"{type(e).__name__}: {str(e)[:160]}"
        info[name] = entry
    return info


probes = []
if remote_host:
    url = f"https://{remote_host}:{os.getenv('ES_REMOTE_PORT') or '9200'}"
    auth = (
        os.getenv("ES_REMOTE_USERNAME") or "",
        os.getenv("ES_REMOTE_PASSWORD") or "",
    )
    es = Elasticsearch(
        hosts=[url],
        basic_auth=auth,
        verify_certs=False,
        request_timeout=30,
    )
    probes.append(probe("remote", es))

if local_host:
    url = f"http://{local_host}:{os.getenv('ES_PORT') or '9200'}"
    auth = (os.getenv("ES_USERNAME") or "", os.getenv("ES_PASSWORD") or "")
    es = Elasticsearch(hosts=[url], basic_auth=auth, request_timeout=30)
    probes.append(probe("local", es))

if not probes:
    result["status"] = "no_host"
else:
    result["status"] = "probed"
    result["probes"] = probes

OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote", OUT)
print("status", result["status"])
for p in result.get("probes") or []:
    print(p.get("label"), "ping", p.get("ping"), "panai4", (p.get("panai4_hymns") or {}).get("count"))
