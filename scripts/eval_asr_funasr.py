# -*- coding: utf-8 -*-
"""
阿里云 Fun-ASR 对比评测脚本
用法：python eval_asr_funasr.py
对比 Fun-ASR（带热词）vs 第二轮 Whisper+Haiku 基线
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
import unicodedata
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "back_mic" / "backend" / ".env")

# ── 配置 ──────────────────────────────────────────────────────────────────────
DASHSCOPE_API_KEY = "sk-b4cb71064b0a49a98f74f45f3d570a8d"
AUDIO_DIR = Path("scripts/asr_eval_audio")
ANSWERS_FILE = Path("scripts/asr_eval_answers.json")
BASELINE_FILE = Path("scripts/asr_eval_result_20260430_035759.json")  # 第二轮结果
CONCURRENCY = 3

# 热词表：与 back_qa/asr_corrections.json 完全对齐（已去重）
HOTWORDS = list(dict.fromkeys([
    "李常受", "倪柝声", "恢复本圣经", "生命读经", "晨兴圣言", "结晶读经",
    "话语的职事", "时代的职事", "三一神", "神圣三一", "新约的经纶", "经纶",
    "奥秘", "神圣启示的高峰", "高峰真理", "包罗万有", "那灵", "包罗万有的灵",
    "赐生命的灵", "终极完成的灵", "调和的灵", "七倍加强的灵", "生命之灵的律",
    "圣灵", "操练灵", "喝那灵", "回到灵里", "心思置于灵", "成为一灵",
    "魂生命", "人成为神", "神成为人", "话成肉体", "神人", "神人调和",
    "吃基督", "享受基督", "生机的救恩", "法理的救赎", "完整的救恩",
    "生机体", "生机的建造", "迁移", "召会", "召会生活", "召会的建造",
    "地方召会", "职事", "得胜者", "非拉铁非", "小排", "家聚会", "活力排",
    "同工", "配搭", "尽功用", "牧养", "祷读", "祷研背讲", "呼求主名",
    "申言", "分赐", "相调", "擘饼", "帐幕", "至圣所", "圣别", "禧年",
    "膏油", "受浸", "内住", "巴路西亚", "构成", "模成", "接枝", "异象",
    "总括时期", "末后的亚当", "千年国", "新耶路撒冷", "雷玛", "吗哪",
    "属灵", "作王", "联结", "撒但", "在生命中作王", "神人二性", "宇宙合并",
    "属灵新陈代谢", "终极完成之灵", "加强时期", "承继时代异象", "祭司",
]))


# ── CER 计算 ───────────────────────────────────────────────────────────────────
def _strip(text: str) -> str:
    """去除标点、空格，用于 CER 计算"""
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
    # 编辑距离
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


# ── Fun-ASR 调用 ───────────────────────────────────────────────────────────────
async def funasr_transcribe(audio_path: Path, semaphore: asyncio.Semaphore) -> str:
    """调用阿里云 Fun-ASR 识别单个音频文件"""
    import dashscope
    from dashscope.audio.asr import Transcription

    dashscope.api_key = DASHSCOPE_API_KEY
    dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"

    async with semaphore:
        loop = asyncio.get_event_loop()

        def _call():
            # 上传本地文件，使用 fun-asr 模型，传入热词
            response = Transcription.call(
                model="fun-asr",
                file_urls=[f"https://qa.aipansearch.org/asr_audio/{audio_path.name}"],
                language_hints=["zh"],
                hotwords=" ".join(HOTWORDS),
            )
            return response

        try:
            response = await loop.run_in_executor(None, _call)

            if response.status_code == 200:
                # 轮询等待结果
                task_id = response.output.get("task_id")
                if not task_id:
                    return "[ERROR: no task_id]"

                for _ in range(30):
                    await asyncio.sleep(2)
                    result = await loop.run_in_executor(
                        None,
                        lambda: Transcription.fetch(task_id=task_id),
                    )
                    status = result.output.get("task_status", "")
                    if status == "SUCCEEDED":
                        results = result.output.get("results", [])
                        if results:
                            return results[0].get("transcription_url", "")
                        return "[ERROR: no results]"
                    elif status == "FAILED":
                        return f"[ERROR: task failed]"

                return "[ERROR: timeout]"
            else:
                return f"[ERROR: {response.status_code} {response.message}]"
        except Exception as e:
            return f"[ERROR: {e}]"


async def funasr_transcribe_simple(audio_path: Path, semaphore: asyncio.Semaphore) -> str:
    """
    使用 Transcription 接口识别本地音频，取 transcription_url 解析文本
    """
    import dashscope
    import urllib.request

    dashscope.api_key = DASHSCOPE_API_KEY
    dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"

    async with semaphore:
        loop = asyncio.get_event_loop()

        def _transcribe():
            from dashscope.audio.asr import Transcription

            response = Transcription.call(
                model="fun-asr",
                file_urls=[f"https://qa.aipansearch.org/asr_audio/{audio_path.name}"],
                language_hints=["zh"],
                hotwords=" ".join(HOTWORDS),
            )

            if response.status_code != 200:
                return f"[ERROR: {response.status_code}]"

            results = response.output.get("results", [])
            if not results:
                return "[ERROR: no results]"

            transcription_url = results[0].get("transcription_url", "")
            if not transcription_url:
                return "[ERROR: no transcription_url]"

            try:
                with urllib.request.urlopen(transcription_url, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                transcripts = data.get("transcripts", [])
                if transcripts:
                    sentences = transcripts[0].get("sentences", [])
                    return "".join(s.get("text", "") for s in sentences)
                return "[ERROR: empty transcript]"
            except Exception as e:
                return f"[ERROR: fetch: {e}]"

        try:
            text = await loop.run_in_executor(None, _transcribe)
            if not text.startswith("[ERROR"):
                from back_qa.qa.asr_service import correct_transcript
                text = await correct_transcript(text)
            return text
        except Exception as e:
            return f"[ERROR: {e}]"


# ── 主流程 ─────────────────────────────────────────────────────────────────────
async def main():
    # 加载答案
    answers: dict[str, str] = {}
    if ANSWERS_FILE.exists():
        answers = json.loads(ANSWERS_FILE.read_text(encoding="utf-8"))

    # 加载第二轮 Whisper+Haiku 基线
    baseline: dict[str, dict] = {}
    if BASELINE_FILE.exists():
        bl = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        for r in bl.get("results", []):
            baseline[r["filename"]] = r
    else:
        print(f"⚠️  找不到基线文件 {BASELINE_FILE}，将只输出 Fun-ASR 结果")

    # 收集音频文件
    audio_files = sorted([
        f for f in AUDIO_DIR.iterdir()
        if f.suffix.lower() in {".m4a", ".mp3", ".wav", ".webm", ".ogg", ".aac"}
    ])
    if not audio_files:
        print(f"❌ 在 {AUDIO_DIR} 找不到音频文件")
        return

    print(f"找到 {len(audio_files)} 个音频文件，开始 Fun-ASR 识别（并发={CONCURRENCY}）...")
    print(f"热词数量：{len(HOTWORDS)} 个\n")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [funasr_transcribe_simple(f, semaphore) for f in audio_files]

    results = []
    funasr_cers = []
    whisper_cers = []
    haiku_cers = []
    funasr_better = 0
    funasr_worse = 0

    texts = await asyncio.gather(*tasks)

    for audio_path, funasr_text in zip(audio_files, texts):
        fname = audio_path.name
        ref = answers.get(fname, "")
        bl = baseline.get(fname, {})

        funasr_c = cer(funasr_text, ref) if ref else None
        whisper_c = bl.get("whisper_cer")
        haiku_c = bl.get("haiku_cer")

        if funasr_c is not None:
            funasr_cers.append(funasr_c)
        if whisper_c is not None:
            whisper_cers.append(whisper_c)
        if haiku_c is not None:
            haiku_cers.append(haiku_c)

        # 对比 Haiku（第二轮最优基线）
        if funasr_c is not None and haiku_c is not None:
            if funasr_c < haiku_c - 0.001:
                funasr_better += 1
            elif funasr_c > haiku_c + 0.001:
                funasr_worse += 1

        entry = {
            "filename": fname,
            "reference": ref,
            "funasr_text": funasr_text,
            "whisper_text": bl.get("whisper_text", ""),
            "haiku_text": bl.get("haiku_text", ""),
            "funasr_cer": round(funasr_c, 6) if funasr_c is not None else None,
            "whisper_cer": whisper_c,
            "haiku_cer": haiku_c,
            "funasr_better_than_haiku": (
                funasr_c < haiku_c - 0.001
                if funasr_c is not None and haiku_c is not None else None
            ),
        }
        results.append(entry)

        # 实时打印进度
        status = ""
        if funasr_c is not None and haiku_c is not None:
            if funasr_c < haiku_c - 0.001:
                status = "✅ 优于Haiku"
            elif funasr_c > haiku_c + 0.001:
                status = "❌ 劣于Haiku"
            else:
                status = "→ 持平"
        print(f"[{fname}] FunASR: {funasr_text[:40]}... | CER={funasr_c:.3f} {status}")

    # 汇总
    avg_funasr = sum(funasr_cers) / len(funasr_cers) if funasr_cers else None
    avg_whisper = sum(whisper_cers) / len(whisper_cers) if whisper_cers else None
    avg_haiku = sum(haiku_cers) / len(haiku_cers) if haiku_cers else None

    summary = {
        "total": len(results),
        "hotwords_count": len(HOTWORDS),
        "funasr_avg_cer": round(avg_funasr, 6) if avg_funasr is not None else None,
        "whisper_avg_cer_baseline": round(avg_whisper, 6) if avg_whisper is not None else None,
        "haiku_avg_cer_baseline": round(avg_haiku, 6) if avg_haiku is not None else None,
        "funasr_better_than_haiku": funasr_better,
        "funasr_worse_than_haiku": funasr_worse,
    }

    output = {"summary": summary, "results": results}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(f"scripts/asr_eval_funasr_{ts}.json")
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    # 打印 summary
    print("\n" + "=" * 60)
    print("Fun-ASR 对比评测结果")
    print("=" * 60)
    print(f"{'模型':<20} {'avg_CER':>10} {'近似准确率':>10}")
    print("-" * 45)
    if avg_whisper is not None:
        print(f"{'Whisper（第二轮基线）':<18} {avg_whisper:>10.4f} {(1-avg_whisper)*100:>9.1f}%")
    if avg_haiku is not None:
        print(f"{'Haiku校对（第二轮）':<19} {avg_haiku:>10.4f} {(1-avg_haiku)*100:>9.1f}%")
    if avg_funasr is not None:
        print(f"{'Fun-ASR + Haiku':<21} {avg_funasr:>10.4f} {(1-avg_funasr)*100:>9.1f}%")
    print("-" * 45)
    print(f"Fun-ASR 优于 Haiku：{funasr_better} 题")
    print(f"Fun-ASR 劣于 Haiku：{funasr_worse} 题")
    print(f"\n结果已写入 {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
