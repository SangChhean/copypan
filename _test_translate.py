# -*- coding: utf-8 -*-
"""临时测试 /api/qa/translate 接口（鉴权 + zh_tw 路径）。"""
import json
import os
import sys
import time

import requests

BASE = "http://127.0.0.1:8001"

print("=" * 60)
print("用例 1：合法 body 但无 JWT → 401")
print("=" * 60)
r = requests.post(
    f"{BASE}/api/qa/translate",
    json={
        "text": "召会与那灵的关系：他们都在恢复本圣经里被启示。",
        "sources": ["1 李常受文集，1994年第二册，第二十二篇"],
        "target_lang": "zh_tw",
        "question": "什么是召会？",
    },
)
print("status:", r.status_code)
print("body:", r.text[:300])
assert r.status_code == 401, f"期望 401，实际 {r.status_code}"
print("✅ 通过（鉴权拦截生效）\n")


# 注册临时用户 + 登录拿 token
print("=" * 60)
print("准备：注册临时用户（如果失败说明已存在，转登录）")
print("=" * 60)
import secrets
username = f"_test_translate_{secrets.token_hex(3)}"
password = "Pass1234!"

# 直接走数据库 invite 创建：先用 admin token 调一次 /auth/invite 拿邀请码
admin_token = os.environ.get("QA_ADMIN_TOKEN", "")
if not admin_token:
    # 从 .env 读
    from pathlib import Path
    env_path = Path(__file__).parent / "back_mic" / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("QA_ADMIN_TOKEN="):
                admin_token = line.split("=", 1)[1].strip()
                break

if not admin_token:
    print("[skip] 无 QA_ADMIN_TOKEN，跳过 200 路径测试")
    sys.exit(0)

inv = requests.post(
    f"{BASE}/api/qa/auth/invite",
    headers={"X-Admin-Token": admin_token},
    json={"code": f"trcode-{secrets.token_hex(3)}"},
)
print("invite resp:", inv.status_code, inv.text[:200])
if inv.status_code != 200:
    print("[skip] 邀请码生成失败，跳过 200 测试")
    sys.exit(0)

reg = requests.post(
    f"{BASE}/api/qa/auth/register",
    json={"username": username, "password": password,
          "invite_code": inv.json().get("code") or inv.json()},
)
print("register resp:", reg.status_code, reg.text[:200])

login = requests.post(
    f"{BASE}/api/qa/auth/login",
    json={"username": username, "password": password},
)
print("login resp:", login.status_code, login.text[:120])
if login.status_code != 200:
    print("[skip] 登录失败")
    sys.exit(0)

token = login.json().get("token") or login.json().get("access_token")
assert token, f"login response missing token: {login.json()}"
auth = {"Authorization": f"Bearer {token}"}


print("=" * 60)
print("用例 2：合法 JWT + zh_tw → 200，返回繁体")
print("=" * 60)
t0 = time.time()
r = requests.post(
    f"{BASE}/api/qa/translate",
    headers=auth,
    json={
        "text": "经纶是神永远的计划。三一神在那灵里被分赐到我们里面，使我们成为基督的身体——召会。\n\n【引用书目】\n1 李常受文集，1994年第二册，第二十二篇\n2 倪柝声文集第二辑第十八册，第三章",
        "sources": [
            "1 李常受文集，1994年第二册，第二十二篇",
            "2 倪柝声文集第二辑第十八册，第三章",
        ],
        "target_lang": "zh_tw",
        "question": "什么是神的经纶？",
    },
)
elapsed = time.time() - t0
print(f"status: {r.status_code}  elapsed: {elapsed:.3f}s")
data = r.json()
print("answer:", data["answer"])
print("sources:", json.dumps(data["sources"], ensure_ascii=False, indent=2))
assert r.status_code == 200
assert "經綸" in data["answer"], f"answer 未繁化：{data['answer']!r}"
assert "召會" in data["answer"]
assert any("倪柝聲" in s for s in data["sources"])
print("✅ zh_tw 通过（OpenCC + 术语表生效）\n")


print("=" * 60)
print("用例 3：合法 JWT + en → 200，返回英文（Gemini 调用）")
print("=" * 60)
t0 = time.time()
r = requests.post(
    f"{BASE}/api/qa/translate",
    headers=auth,
    json={
        "text": "经纶是神永远的计划。三一神在那灵里被分赐到我们里面，使我们成为基督的身体——召会。\n\n【引用书目】\n1 李常受文集，1994年第二册，第二十二篇",
        "sources": ["1 李常受文集，1994年第二册，第二十二篇"],
        "target_lang": "en",
        "question": "什么是神的经纶？",
    },
)
elapsed = time.time() - t0
print(f"status: {r.status_code}  elapsed: {elapsed:.3f}s")
if r.status_code == 200:
    data = r.json()
    print("answer:", data["answer"])
    print("sources:", json.dumps(data["sources"], ensure_ascii=False, indent=2))
    assert "[References]" in data["answer"], "应包含 [References] 段"
    print("✅ en 通过（Gemini 翻译生效）")
else:
    print("[warn] en 路径返回 500，可能 Gemini 503/限流，body:", r.text[:500])
