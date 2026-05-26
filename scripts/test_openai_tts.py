"""OpenAI TTS 测试脚本"""
import os, sys, requests
from pathlib import Path

env_path = Path(__file__).resolve().parents[1] / "back_mic" / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("OPENAI_API_KEY", "")
if not API_KEY:
    print("❌ 未找到 OPENAI_API_KEY"); sys.exit(1)

OUTPUT_DIR = Path(__file__).resolve().parent / "tts_test_output" / "openai"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEXT_ZH = "神的经纶就是神的计划，祂要将自己分赐到人里面，使人得着神的生命与性情。召会是神经纶的中心，是基督的身体，也是神荣耀的彰显。愿我们在这条路上继续前行，经历祂丰富的供应。"
TEXT_EN = "God's economy is God's plan to dispense Himself into man, that man may receive the divine life and nature. The church is the center of God's economy, the Body of Christ, the fullness of Him who fills all in all."

# OpenAI TTS 女声
VOICES = ["alloy", "nova", "shimmer"]

def synthesize(voice, text, out_path):
    r = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": "tts-1-hd", "voice": voice, "input": text, "response_format": "mp3"},
        timeout=60,
    )
    if r.status_code == 200:
        out_path.write_bytes(r.content)
        print(f"  ✅ {out_path.name} ({len(r.content)//1024} KB)")
    else:
        print(f"  ❌ {r.status_code}: {r.text[:200]}")

print("=== OpenAI TTS 测试 ===\n")
for voice in VOICES:
    print(f"[{voice}]")
    synthesize(voice, TEXT_ZH, OUTPUT_DIR / f"{voice}_zh.mp3")
    synthesize(voice, TEXT_EN, OUTPUT_DIR / f"{voice}_en.mp3")
print(f"\n完成！音频在：{OUTPUT_DIR}")
