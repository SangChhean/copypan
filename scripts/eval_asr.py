#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch ASR evaluation: Whisper + Haiku (+ optional Sonnet) with optional reference CER."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".webm", ".ogg"}
SONNET_MODEL = "claude-sonnet-4-6"


def _normalize_for_cer(s: str) -> str:
    return "".join(
        ch for ch in s if not ch.isspace() and unicodedata.category(ch)[0] != "P"
    )


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    la, lb = len(a), len(b)
    if lb == 0:
        return la
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, lb + 1):
            tmp = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = tmp
    return dp[lb]


def compute_cer(hypothesis: str, reference: str) -> float:
    h = _normalize_for_cer(hypothesis)
    r = _normalize_for_cer(reference)
    if len(r) == 0:
        return 0.0 if len(h) == 0 else 1.0
    return _levenshtein(h, r) / len(r)


def _collect_audio_files(audio_dir: Path) -> list[Path]:
    found: list[Path] = []
    for p in audio_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            found.append(p)
    return sorted(found, key=lambda x: x.name)


async def _whisper_transcribe(
    client: AsyncOpenAI, audio_bytes: bytes, filename: str, prompt: str
) -> str:
    file_obj = io.BytesIO(audio_bytes)
    file_obj.name = filename
    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=file_obj,
        language="zh",
        prompt=prompt,
    )
    return (getattr(response, "text", "") or "").strip()


async def _run_eval_for_file(
    sem: asyncio.Semaphore,
    path: Path,
    openai_client: AsyncOpenAI,
    whisper_prompt: str,
    answers: dict[str, str],
    skip_sonnet: bool,
) -> dict:
    from back_qa.qa.asr_service import correct_transcript

    name = path.name
    ref = answers.get(name)
    out: dict = {
        "filename": name,
        "reference": ref if ref is not None else None,
        "whisper_text": None,
        "haiku_text": None,
        "sonnet_text": None,
        "whisper_cer": None,
        "haiku_cer": None,
        "sonnet_cer": None,
        "haiku_changed": False,
        "sonnet_changed": False,
        "error": None,
    }
    async with sem:
        try:
            data = path.read_bytes()
            whisper_text = await _whisper_transcribe(
                openai_client, data, name, whisper_prompt
            )
            out["whisper_text"] = whisper_text
            haiku_text = await correct_transcript(whisper_text)
            out["haiku_text"] = haiku_text
            out["haiku_changed"] = haiku_text != whisper_text
            if not skip_sonnet:
                sonnet_text = await correct_transcript(whisper_text, model=SONNET_MODEL)
                out["sonnet_text"] = sonnet_text
                out["sonnet_changed"] = sonnet_text != whisper_text
            if ref is not None:
                out["whisper_cer"] = compute_cer(whisper_text, ref)
                out["haiku_cer"] = compute_cer(haiku_text, ref)
                if out["sonnet_text"] is not None:
                    out["sonnet_cer"] = compute_cer(out["sonnet_text"], ref)
        except Exception as e:
            out["error"] = str(e)
    return out


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _summarize(rows: list[dict], skip_sonnet: bool, has_refs: bool) -> dict:
    summary: dict = {
        "total": len(rows),
        "whisper_avg_cer": None,
        "haiku_avg_cer": None,
        "sonnet_avg_cer": None,
        "haiku_improved": 0,
        "haiku_degraded": 0,
        "sonnet_improved": 0,
        "sonnet_degraded": 0,
    }
    if not has_refs:
        return summary
    wc, hc, sc = [], [], []
    for r in rows:
        if r.get("error"):
            continue
        w, h = r.get("whisper_cer"), r.get("haiku_cer")
        if w is not None and h is not None:
            wc.append(w)
            hc.append(h)
            if h < w:
                summary["haiku_improved"] += 1
            elif h > w:
                summary["haiku_degraded"] += 1
        s = r.get("sonnet_cer")
        if not skip_sonnet and w is not None and s is not None:
            sc.append(s)
            if s < w:
                summary["sonnet_improved"] += 1
            elif s > w:
                summary["sonnet_degraded"] += 1
    summary["whisper_avg_cer"] = _mean(wc)
    summary["haiku_avg_cer"] = _mean(hc)
    summary["sonnet_avg_cer"] = _mean(sc) if sc else None
    return summary


def _print_table(summary: dict, skip_sonnet: bool) -> None:
    def fmt(x: float | None) -> str:
        if x is None:
            return "N/A"
        return f"{x:.4f}"

    wa = summary.get("whisper_avg_cer")
    ha = summary.get("haiku_avg_cer")
    sa = summary.get("sonnet_avg_cer")
    print()
    print("ASR eval summary — average CER (Character Error Rate, punct/space stripped)")
    print(f"{'model':<12} {'avg_cer':>10}")
    print(f"{'Whisper':<12} {fmt(wa):>10}")
    print(f"{'Haiku':<12} {fmt(ha):>10}")
    if not skip_sonnet:
        print(f"{'Sonnet':<12} {fmt(sa):>10}")
    print()
    print(
        f"Haiku vs Whisper:  improved {summary['haiku_improved']}  "
        f"degraded {summary['haiku_degraded']}"
    )
    if not skip_sonnet:
        print(
            f"Sonnet vs Whisper: improved {summary['sonnet_improved']}  "
            f"degraded {summary['sonnet_degraded']}"
        )
    print(f"Total files: {summary['total']}")
    print()


async def _async_main(args: argparse.Namespace) -> Path:
    env_path = ROOT / "back_mic" / "backend" / ".env"
    load_dotenv(env_path)

    from back_qa.qa.asr_service import _build_prompt

    whisper_prompt = _build_prompt()
    audio_dir = Path(args.audio_dir).resolve()
    if not audio_dir.is_dir():
        raise SystemExit(f"audio dir not found: {audio_dir}")

    answers_path = Path(args.answers).resolve()
    answers: dict[str, str] = {}
    if answers_path.is_file():
        answers = json.loads(answers_path.read_text(encoding="utf-8"))
        if not isinstance(answers, dict):
            raise SystemExit("--answers must be a JSON object")

    files = _collect_audio_files(audio_dir)
    if not files:
        print(f"No audio files under {audio_dir}")
    sem = asyncio.Semaphore(max(1, int(args.concurrency)))
    api_key = __import__("os").environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set")

    openai_client = AsyncOpenAI(api_key=api_key)
    tasks = [
        _run_eval_for_file(
            sem, p, openai_client, whisper_prompt, answers, args.skip_sonnet
        )
        for p in files
    ]
    rows = list(await asyncio.gather(*tasks))
    rows.sort(key=lambda r: r["filename"])
    summary = _summarize(rows, args.skip_sonnet, answers_path.is_file())
    payload = {"summary": summary, "results": rows}

    out_path = Path(args.output).resolve()
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _print_table(summary, args.skip_sonnet)
    print(f"Wrote {out_path}")
    return out_path


def main() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_out = ROOT / "scripts" / f"asr_eval_result_{ts}.json"
    parser = argparse.ArgumentParser(description="ASR batch eval (Whisper + Haiku + Sonnet)")
    parser.add_argument(
        "--audio-dir",
        default=str(ROOT / "scripts" / "asr_eval_audio"),
        help="Directory to scan recursively for m4a/mp3/wav/webm/ogg",
    )
    parser.add_argument(
        "--answers",
        default=str(ROOT / "scripts" / "asr_eval_answers.json"),
        help='JSON map: {"file.wav": "reference text", ...}',
    )
    parser.add_argument(
        "--output",
        default=str(default_out),
        help="Output JSON path",
    )
    parser.add_argument("--concurrency", type=int, default=3, help="Max concurrent files")
    parser.add_argument(
        "--skip-sonnet",
        action="store_true",
        help="Skip Sonnet correction (Whisper + Haiku only)",
    )
    args = parser.parse_args()
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
