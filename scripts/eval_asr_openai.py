# -*- coding: utf-8 -*-
"""
OpenAI 音频模型对比评测脚本
对比 gpt-4o-transcribe / gpt-4o-mini-transcribe / gpt-4o-audio-preview
vs 第二轮 Whisper+Haiku 基线
用法：python scripts/eval_asr_openai.py
"""
from __future__ import annotations
import asyncio
import base64
import json
import os
import unicodedata
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "back_mic" / "backend" / ".env")

AUDIO_DIR = ROOT / "scripts" / "asr_eval_audio"
ANSWERS_FILE = ROOT / "scripts" / "asr_eval_answers.json"
BASELINE_FILE = ROOT / "scripts" / "asr_eval_result_20260430_035759.json"
CONCURRENCY = 3

# 测试的模型列表
MODELS = [
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
    "gpt-4o-audio-preview",
]

# Whisper-style prompt（与 asr_corrections.json 完全对齐，224 token 限制内）
WHISPER_PROMPT = (
    "以下是职事信息问答的简体中文内容。"
    "李常受、倪柝声、恢复本圣经、生命读经、晨兴圣言、结晶读经、"
    "话语的职事、时代的职事、三一神、神圣三一、新约的经纶、经纶、奥秘、"
    "神圣启示的高峰、高峰真理、包罗万有、那灵、包罗万有的灵、赐生命的灵、"
    "终极完成的灵、调和的灵、七倍加强的灵、生命之灵的律、圣灵、"
    "操练灵、成为一灵、吃基督、享受基督、生机的救恩、法理的救赎、"
    "召会、召会生活、地方召会、职事、得胜者、活力排、擘饼、相调、"
    "总括时期、加强时期、末后的亚当、新耶路撒冷、属灵、作王、撒但、祭司、联结"
)

# audio-preview 的 system prompt（同样完整对齐）
AUDIO_SYSTEM_PROMPT = (
    "你是语音转写助手，将用户的中文语音精确转写为简体中文文字。"
    "领域专有词包括：李常受、倪柝声、恢复本圣经、生命读经、晨兴圣言、结晶读经、"
    "话语的职事、时代的职事、三一神、神圣三一、新约的经纶、经纶、奥秘、"
    "神圣启示的高峰、高峰真理、包罗万有、那灵、包罗万有的灵、赐生命的灵、"
    "终极完成的灵、调和的灵、七倍加强的灵、生命之灵的律、圣灵、"
    "操练灵、成为一灵、吃基督、享受基督、生机的救恩、法理的救赎、"
    "召会、召会生活、地方召会、职事、得胜者、活力排、擘饼、相调、"
    "总括时期、加强时期、末后的亚当、新耶路撒冷、属灵、作王、撒但、祭司、联结。"
    "只输出转写文字，不要解释。"
)


# ── CER 计算 ───────────────────────────────────────────────────────────────────
def _strip(text: str) -> str:
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("Z") or ch in " \t\n\r":
            continue
        out.append(ch)
    return "".join(out)


def cer(hypothesis: str, reference: str) -> float:
    h = _strip(hypothesis)
    r = _strip(reference)
    if not r:
        return 0.0
    m, n = len(r), len(h)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            if r[i - 1] == h[j - 1]:
                dp[j] = prev[j - 1]
            else:
                dp[j] = 1 + min(prev[j], dp[j - 1], prev[j - 1])
    return dp[n] / len(r)


# ── OpenAI 转写 ────────────────────────────────────────────────────────────────
async def openai_transcribe(
    audio_path: Path,
    model: str,
    semaphore: asyncio.Semaphore,
) -> str:
    import os
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    async with semaphore:
        try:
            audio_bytes = audio_path.read_bytes()

            if model in ("gpt-4o-transcribe", "gpt-4o-mini-transcribe"):
                # 使用 transcriptions API（和 whisper-1 同接口）
                import io
                file_obj = io.BytesIO(audio_bytes)
                file_obj.name = audio_path.name
                response = await client.audio.transcriptions.create(
                    model=model,
                    file=file_obj,
                    language="zh",
                    prompt=WHISPER_PROMPT,
                )
                return (response.text or "").strip()

            elif model == "gpt-4o-audio-preview":
                # 使用 chat completions API，音频作为 input_audio
                suffix = audio_path.suffix.lstrip(".").lower()
                fmt = "mp4" if suffix == "m4a" else suffix
                b64 = base64.b64encode(audio_bytes).decode()
                response = await client.chat.completions.create(
                    model=model,
                    modalities=["text"],
                    messages=[
                        {
                            "role": "system",
                            "content": AUDIO_SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_audio",
                                    "input_audio": {"data": b64, "format": fmt},
                                }
                            ],
                        },
                    ],
                )
                return (response.choices[0].message.content or "").strip()

            else:
                return f"[ERROR: unknown model {model}]"

        except Exception as e:
            return f"[ERROR: {e}]"


# ── 主流程 ─────────────────────────────────────────────────────────────────────
async def main():
    answers: dict[str, str] = {}
    if ANSWERS_FILE.exists():
        answers = json.loads(ANSWERS_FILE.read_text(encoding="utf-8"))

    baseline: dict[str, dict] = {}
    if BASELINE_FILE.exists():
        bl = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        for r in bl.get("results", []):
            baseline[r["filename"]] = r
    else:
        print(f"⚠️  找不到基线文件 {BASELINE_FILE}")

    audio_files = sorted([
        f for f in AUDIO_DIR.iterdir()
        if f.suffix.lower() in {".m4a", ".mp3", ".wav", ".webm", ".ogg", ".aac"}
    ])
    if not audio_files:
        print(f"❌ 在 {AUDIO_DIR} 找不到音频文件")
        return

    print(f"找到 {len(audio_files)} 个音频，测试模型：{MODELS}\n")

    # 逐模型跑，避免并发费用叠加
    all_results: dict[str, list] = {m: [] for m in MODELS}
    model_cers: dict[str, list] = {m: [] for m in MODELS}

    for model in MODELS:
        print(f"\n{'='*50}")
        print(f"模型：{model}")
        print(f"{'='*50}")
        semaphore = asyncio.Semaphore(CONCURRENCY)
        tasks = [openai_transcribe(f, model, semaphore) for f in audio_files]
        texts = await asyncio.gather(*tasks)

        for audio_path, text in zip(audio_files, texts):
            fname = audio_path.name
            ref = answers.get(fname, "")
            bl = baseline.get(fname, {})
            c = cer(text, ref) if ref else None
            if c is not None:
                model_cers[model].append(c)
            haiku_c = bl.get("haiku_cer")
            status = ""
            if c is not None and haiku_c is not None:
                if c < haiku_c - 0.001:
                    status = "✅"
                elif c > haiku_c + 0.001:
                    status = "❌"
                else:
                    status = "→"
            cer_str = f"{c:.3f}" if c is not None else "N/A"
            print(f"  {status} [{fname}] CER={cer_str} | {text[:50]}")
            all_results[model].append({
                "filename": fname,
                "reference": ref,
                "text": text,
                "cer": round(c, 6) if c is not None else None,
                "whisper_cer": bl.get("whisper_cer"),
                "haiku_cer": haiku_c,
            })

    # 汇总
    haiku_cers = [
        baseline[f.name].get("haiku_cer", 0)
        for f in audio_files if f.name in baseline
    ]
    avg_haiku = sum(haiku_cers) / len(haiku_cers) if haiku_cers else None

    print(f"\n{'='*60}")
    print("OpenAI 音频模型对比评测结果")
    print(f"{'='*60}")
    print(f"{'模型':<30} {'avg_CER':>10} {'准确率':>10}")
    print("-" * 55)
    if avg_haiku is not None:
        print(f"{'Whisper+Haiku（第二轮基线）':<26} {avg_haiku:>10.4f} {(1-avg_haiku)*100:>9.1f}%")
    for model in MODELS:
        cers = model_cers[model]
        avg = sum(cers) / len(cers) if cers else None
        better = sum(
            1 for r in all_results[model]
            if r["cer"] is not None and r["haiku_cer"] is not None
            and r["cer"] < r["haiku_cer"] - 0.001
        )
        worse = sum(
            1 for r in all_results[model]
            if r["cer"] is not None and r["haiku_cer"] is not None
            and r["cer"] > r["haiku_cer"] + 0.001
        )
        if avg is not None:
            print(f"{model:<30} {avg:>10.4f} {(1-avg)*100:>9.1f}%  ✅{better} ❌{worse}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "scripts" / f"asr_eval_openai_{ts}.json"
    out_path.write_text(
        json.dumps({"models": MODELS, "results": all_results}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n结果已写入 {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
