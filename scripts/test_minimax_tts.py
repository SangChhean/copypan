"""MiniMax TTS 测试脚本"""
import os, sys, json, requests
from pathlib import Path

env_path = Path(__file__).resolve().parents[1] / "back_mic" / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("MINIMAX_API_KEY", "")
GROUP_ID = os.environ.get("MINIMAX_GROUP_ID", "")
if not API_KEY or not GROUP_ID:
    print("❌ 未找到 MINIMAX_API_KEY 或 MINIMAX_GROUP_ID"); sys.exit(1)

OUTPUT_DIR = Path(__file__).resolve().parent / "tts_test_output" / "minimax"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEXT_ZH = "神的经纶就是神的计划，祂要将自己分赐到人里面，使人得着神的生命与性情。召会是神经纶的中心，是基督的身体，也是神荣耀的彰显。愿我们在这条路上继续前行，经历祂丰富的供应。"
TEXT_EN = "God's economy is God's plan to dispense Himself into man, that man may receive the divine life and nature. The church is the center of God's economy, the Body of Christ, the fullness of Him who fills all in all."

# MiniMax 中文女声（常用）
VOICES_ZH = [
    ("Chinese (Mandarin)_Kind-hearted_Antie", "亲切大妈"),
]
VOICES_EN = [
    ("English_Graceful_Lady", "优雅女声"),
]

URL = f"https://api-uw.minimax.io/v1/t2a_v2?GroupId={GROUP_ID}"

def synthesize(voice_id, text, out_path):
    payload = {
        "model": "speech-02-hd",
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
        },
    }
    r = requests.post(
        URL,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if r.status_code == 200:
        print(f"  响应 keys: {list(r.json().keys())}")
        print(f"  data keys: {list(r.json().get('data', {}).keys())}")
        data = r.json()
        audio_file = data.get("data", {}).get("audio", "")
        if audio_file:
            # MiniMax 返回 hex 编码的 MP3（非 base64）
            audio_bytes = bytes.fromhex(audio_file)
            out_path.write_bytes(audio_bytes)
            print(f"  ✅ {out_path.name} ({len(audio_bytes)//1024} KB)")
        else:
            print(f"  ❌ 响应无音频：{json.dumps(data)[:200]}")
    else:
        print(f"  ❌ {r.status_code}: {r.text[:200]}")

print("=== MiniMax TTS 测试 ===\n")
print("--- 中文 ---")
for voice_id, desc in VOICES_ZH:
    print(f"[{voice_id}] {desc}")
    synthesize(voice_id, TEXT_ZH, OUTPUT_DIR / f"{voice_id}_zh.mp3")
print("\n--- 英文 ---")
for voice_id, desc in VOICES_EN:
    print(f"[{voice_id}] {desc}")
    synthesize(voice_id, TEXT_EN, OUTPUT_DIR / f"{voice_id}_en.mp3")
print(f"\n完成！音频在：{OUTPUT_DIR}")
