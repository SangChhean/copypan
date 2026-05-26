"""
Gemini TTS 女声测试脚本
生成中文测试音频，输出到 scripts/tts_test_output/gemini/
用法：python scripts/test_gemini_tts.py
"""
import os
import sys
import base64
import struct
import requests
from pathlib import Path

env_path = Path(__file__).resolve().parents[1] / "back_mic" / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    print("❌ 未找到 GEMINI_API_KEY")
    sys.exit(1)

OUTPUT_DIR = Path(__file__).resolve().parent / "tts_test_output" / "gemini"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEXT = "神的经纶就是神的计划，祂要将自己分赐到人里面，使人得着神的生命与性情。召会是神经纶的中心，是基督的身体，也是神荣耀的彰显。愿我们在这条路上继续前行，经历祂丰富的供应。"

PROMPT = (
    "你是一位朗读圣经职事信息的朗读者，请用平静、庄重、温和的语气朗读，"
    "语速适中，情感内敛而真诚。以下是要朗读的内容：\n\n" + TEXT
)

FEMALE_VOICES = [
    "Achernar", "Aoede", "Autonoe", "Callirrhoe", "Despina",
    "Erinome", "Gacrux", "Kore", "Laomedeia", "Leda",
    "Pulcherrima", "Sulafat", "Vindemiatrix", "Zephyr",
]

URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-tts-preview:generateContent?key={API_KEY}"

def pcm_to_wav(pcm_bytes, sample_rate=24000):
    num_channels, bits = 1, 16
    byte_rate = sample_rate * num_channels * bits // 8
    block_align = num_channels * bits // 8
    data_size = len(pcm_bytes)
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, num_channels, sample_rate,
        byte_rate, block_align, bits,
        b'data', data_size
    )
    return header + pcm_bytes

def synthesize(voice, out_path):
    payload = {
        "contents": [{"parts": [{"text": PROMPT}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice}
                }
            }
        }
    }
    r = requests.post(URL, json=payload, timeout=60)
    if r.status_code == 200:
        b64 = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        wav = pcm_to_wav(base64.b64decode(b64))
        out_path.write_bytes(wav)
        print(f"  ✅ {out_path.name}  ({len(wav)//1024} KB)")
    else:
        print(f"  ❌ {r.status_code}: {r.text[:200]}")

print("=== Gemini TTS 女声测试（含风格 prompt）===\n")
for voice in FEMALE_VOICES:
    print(f"[{voice}]")
    synthesize(voice, OUTPUT_DIR / f"{voice}.wav")
    import time; time.sleep(7)  # 避免超过10QPM限制

print(f"\n完成！音频在：{OUTPUT_DIR}")
