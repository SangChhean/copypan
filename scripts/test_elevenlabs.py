"""
ElevenLabs TTS 测试脚本
生成中英文测试音频，输出到 scripts/tts_test_output/
用法：python scripts/test_elevenlabs.py
"""
import os
import sys
from pathlib import Path

# 加载 .env
env_path = Path(__file__).resolve().parents[1] / "back_mic" / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
if not API_KEY:
    print("❌ 未找到 ELEVENLABS_API_KEY")
    sys.exit(1)

import requests

OUTPUT_DIR = Path(__file__).resolve().parent / "tts_test_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# 测试文本
TEXT_ZH = "神的经纶就是神的计划，祂要将自己分赐到人里面，使人得着神的生命与性情。召会是神经纶的中心，是基督的身体。"
TEXT_EN = "God's economy is God's plan to dispense Himself into man, that man may receive the divine life and nature. The church is the center of God's economy, the Body of Christ."

# 待测试音色：(voice_id, 名称, 语言说明)
VOICES = [
    ("bhJUNIXWQQ94l8eI2VUf", "Amy",    "普通话北京女声"),
    ("r6qgCCGI7RWKXCagm158", "Anna_Su", "普通话北京女声"),
    ("5qr5FEpvZGzmVOPBS55W", "Zi_Yue", "普通话北京女声"),
]

MODEL_ZH = "eleven_v3"
MODEL_EN = "eleven_v3"

def synthesize(voice_id, text, model, out_path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    if r.status_code == 200:
        out_path.write_bytes(r.content)
        print(f"  ✅ 已生成：{out_path.name}")
    else:
        print(f"  ❌ 失败 {r.status_code}：{r.text[:200]}")

print("=== ElevenLabs TTS 测试 ===\n")
for voice_id, name, desc in VOICES:
    print(f"[{name}] {desc}")
    synthesize(voice_id, TEXT_ZH, MODEL_ZH, OUTPUT_DIR / f"{name}_zh.mp3")
    synthesize(voice_id, TEXT_EN, MODEL_EN, OUTPUT_DIR / f"{name}_en.mp3")
    print()

print(f"完成！音频文件在：{OUTPUT_DIR}")
