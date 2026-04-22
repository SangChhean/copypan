# -*- coding: utf-8 -*-
"""API 端到端：释放 8001、起 uvicorn 写日志、清缓存、跑 query×2 + stats，再停服务。
用法（在 copypan 根目录）：python back_qa/scripts/run_qa_api_e2e.py
需本机 Neo4j/ES/Redis/CLAUDE 可用；管理员 Token 默认 e2e_admin_token（可用环境变量覆盖）。"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "_qa_e2e_uvicorn.log"
ADMIN = os.environ.get("QA_ADMIN_TOKEN", "e2e_admin_token")


def _kill_port(port: int) -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
            f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}",
        ],
        cwd=str(ROOT),
        capture_output=True,
    )
    time.sleep(2)


def _wait_http(url: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit(f"timeout waiting for {url}")


def main() -> int:
    _kill_port(8001)
    if LOG.exists():
        LOG.unlink()

    env = {**os.environ, "QA_ADMIN_TOKEN": ADMIN, "PYTHONIOENCODING": "utf-8"}
    logf = open(LOG, "wb")
    rows: list[tuple[str, dict]] = []
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "back_qa.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8001",
        ],
        cwd=str(ROOT),
        stdout=logf,
        stderr=subprocess.STDOUT,
        env=env,
    )
    try:
        _wait_http("http://127.0.0.1:8001/api/qa/liveness")

        def post(path: str, body: dict, headers: dict | None = None) -> dict:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h = {"Content-Type": "application/json; charset=utf-8"}
            if headers:
                h.update(headers)
            req = urllib.request.Request(
                "http://127.0.0.1:8001" + path, data=data, headers=h, method="POST"
            )
            with urllib.request.urlopen(req, timeout=420) as r:
                return json.loads(r.read().decode("utf-8"))

        def get(path: str, headers: dict | None = None) -> dict:
            req = urllib.request.Request("http://127.0.0.1:8001" + path, headers=headers or {})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))

        def post_clear() -> dict:
            data = b"{}"
            req = urllib.request.Request(
                "http://127.0.0.1:8001/api/qa/cache/clear",
                data=data,
                headers={"Content-Type": "application/json", "X-Admin-Token": ADMIN},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))

        post_clear()

        q = "神的经纶的中心是什么？"
        rows.append(("B_first_query", post("/api/qa/query", {"question": q, "skip_cache": False})))
        rows.append(("D_same_query_cache", post("/api/qa/query", {"question": q, "skip_cache": False})))
        rows.append(("F_obscure", post("/api/qa/query", {"question": "倪弟兄论蚂蚁", "skip_cache": False})))
        rows.append(("E_stats", get("/api/qa/stats", {"X-Admin-Token": ADMIN})))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        logf.close()

    time.sleep(0.5)
    log_text = LOG.read_text(encoding="utf-8", errors="replace")

    print("=== API results (summary) ===")
    for name, obj in rows:
        if name == "B_first_query":
            print(
                name,
                "found=",
                obj.get("found"),
                "cache_hit=",
                obj.get("cache_hit"),
                "sources=",
                len(obj.get("sources") or []),
                "elapsed_ms=",
                obj.get("total_elapsed_ms"),
            )
        elif name == "D_same_query_cache":
            print(name, "cache_hit=", obj.get("cache_hit"), "elapsed_ms=", obj.get("total_elapsed_ms"))
        elif name == "F_obscure":
            print(name, "found=", obj.get("found"), "answer_prefix=", (obj.get("answer") or "")[:40])
        elif name == "E_stats":
            print(name, "total_requests=", obj.get("total_requests"))

    print("\n=== Log needles (uvicorn stdout/stderr merged) ===")
    for needle in [
        "[QA] Step1 识别概念:",
        "[QA] Step2 BM25=",
        "[QA] Step3 relevant=",
        "[QA] 缓存命中",
    ]:
        print(needle, "->", "YES" if needle in log_text else "NO")

    b = rows[0][1]
    d = rows[1][1]
    f = rows[2][1]
    e = rows[3][1]
    ok = (
        b.get("found") is True
        and b.get("cache_hit") is False
        and len(b.get("sources") or []) > 0
        and d.get("cache_hit") is True
        and (e.get("total_requests") or 0) >= 1
        and "[QA] Step1 识别概念:" in log_text
        and "[QA] Step2 BM25=" in log_text
        and "[QA] Step3 relevant=" in log_text
        and "[QA] 缓存命中" in log_text
    )
    print(
        "\n场景 F（生僻问）实际 found=",
        f.get("found"),
        "（语料命中时仍为 True；验证「未找到」请换与索引无关的问句）",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
