"""
Google Cloud TTS 测试脚本
生成中英文测试音频，输出到 scripts/tts_test_output/google/
用法：python scripts/test_google_tts.py
"""
import os
import sys
import requests
from pathlib import Path

# 加载 .env
env_path = Path(__file__).resolve().parents[1] / "back_mic" / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("GOOGLE_TTS_API_KEY", "")
if not API_KEY:
    print("❌ 未找到 GOOGLE_TTS_API_KEY")
    sys.exit(1)

OUTPUT_DIR = Path(__file__).resolve().parent / "tts_test_output" / "google"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEXT_ZH = "神的经纶就是神的计划，祂要将自己分赐到人里面，使人得着神的生命与性情。召会是神经纶的中心，是基督的身体。"
TEXT_EN = "God's economy is God's plan to dispense Himself into man, that man may receive the divine life and nature. The church is the center of God's economy, the Body of Christ."

# (name, languageCode, ssmlGender, 描述)
VOICES = [
    ("cmn-CN-Chirp3-HD-Aoede",   "cmn-CN", "FEMALE", "普通话 Chirp3-HD Aoede"),
    ("cmn-CN-Chirp3-HD-Charon",  "cmn-CN", "FEMALE", "普通话 Chirp3-HD Charon"),
    ("cmn-CN-Chirp3-HD-Fenrir",  "cmn-CN", "FEMALE", "普通话 Chirp3-HD Fenrir"),
    ("cmn-CN-Chirp3-HD-Kore",    "cmn-CN", "FEMALE", "普通话 Chirp3-HD Kore"),
    ("en-US-Chirp3-HD-Aoede",    "en-US",  "FEMALE", "英文 Chirp3-HD Aoede"),
    ("en-US-Chirp3-HD-Kore",     "en-US",  "FEMALE", "英文 Chirp3-HD Kore"),
    ("en-US-Journey-F",          "en-US",  "FEMALE", "英文 Journey F"),
]

URL = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={API_KEY}"

def synthesize(voice_name, lang_code, gender, text, out_path):
    payload = {
        "input": {"text": text},
        "voice": {
            "languageCode": lang_code,
            "name": voice_name,
            "ssmlGender": gender,
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": 1.0,
            "pitch": 0.0,
        },
    }
    r = requests.post(URL, json=payload, timeout=30)
    if r.status_code == 200:
        import base64
        audio = base64.b64decode(r.json()["audioContent"])
        out_path.write_bytes(audio)
        print(f"  ✅ {out_path.name}  ({len(audio)//1024} KB)")
    else:
        print(f"  ❌ {r.status_code}: {r.text[:200]}")

print("=== Google Cloud TTS 测试 ===\n")
for voice_name, lang_code, gender, desc in VOICES:
    print(f"[{voice_name}] {desc}")
    text = TEXT_ZH if lang_code.startswith("cmn") else TEXT_EN
    out_file = OUTPUT_DIR / f"{voice_name.replace('-', '_')}.mp3"
    synthesize(voice_name, lang_code, gender, text, out_file)
print(f"\n完成！音频在：{OUTPUT_DIR}")
