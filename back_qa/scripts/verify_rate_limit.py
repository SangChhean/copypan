# -*- coding: utf-8 -*-
"""Quick check: rate_limit counter with real Redis (no full QA pipeline). Run from copypan root."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ["QA_RATE_LIMIT_PER_MINUTE"] = "15"
# Re-import after env
import importlib

import dotenv

dotenv.load_dotenv(ROOT / "back_mic" / "backend" / ".env")

import redis as redis_mod

from back_qa.qa import rate_limit as rl

importlib.reload(rl)


def main() -> None:
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    db = int(os.environ.get("REDIS_DB", "0"))
    try:
        r = redis_mod.Redis(host=host, port=port, db=db, decode_responses=True)
        r.ping()
    except Exception as e:
        print("SKIP: Redis unavailable:", e)
        return

    test_ip = "127.0.0.1"
    key = f"qa:ratelimit:{test_ip}"
    r.delete(key)

    class FakeClient:
        host = test_ip

    class FakeRequest:
        headers = {}
        client = FakeClient()

    req = FakeRequest()
    limit = rl.RATE_LIMIT_PER_MINUTE
    for i in range(limit + 2):
        ok = rl.check_rate_limit(req, r)
        print(f"{i + 1}: allow={ok}")
        assert ok == (i < limit), f"expected allow={i < limit} at iteration {i + 1}"

    print("OK: first", limit, "allowed, then blocked.")


if __name__ == "__main__":
    main()
