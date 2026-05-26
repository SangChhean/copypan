import os
from pathlib import Path
import requests

env_path = Path(__file__).resolve().parents[1] / "back_mic" / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
r = requests.get(
    "https://api.elevenlabs.io/v1/voices",
    headers={"xi-api-key": API_KEY},
    timeout=15,
)
voices = r.json().get("voices", [])
print(f"共 {len(voices)} 个音色：\n")
for v in voices:
    labels = v.get("labels", {})
    gender = labels.get("gender", "unknown")
    lang = labels.get("language", "")
    accent = labels.get("accent", "")
    print(f"  [{gender}] {v['name']:20s} id={v['voice_id']}  lang={lang} accent={accent}")
