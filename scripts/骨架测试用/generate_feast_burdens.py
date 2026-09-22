# -*- coding: utf-8 -*-
"""批量生成节期纲目负担说明：直接调 Claude，不走 /api/kg_rag/generate_burden。

复用同目录 burden_prompt_dev.py 的 BURDEN_DESCRIPTION_PROMPT / BURDEN_DESCRIPTION_SYSTEM
（正式链路仍用 back_mic/backend/kg_rag/prompts.py，本脚本不改那边）。

用法：
  python generate_feast_burdens.py --trial   # 只跑 1真理启示 中编号为 1 的文件，打印结果
  python generate_feast_burdens.py           # 跑全部 30 篇，写出 feast_burdens_30_sonnet5.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from docx import Document

from burden_prompt_dev import BURDEN_DESCRIPTION_PROMPT, BURDEN_DESCRIPTION_SYSTEM

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "back_mic" / "backend"
INPUT_ROOT = SCRIPT_DIR / "第一次测试" / "30个特会题目"
OUTPUT_JSON = SCRIPT_DIR / "第一次测试" / "feast_burdens_30_sonnet5.json"

MODEL = "claude-sonnet-5"
# sonnet-5 可能占用 thinking token，criteria 变长后 8192 仍可能只剩空正文
MAX_TOKENS = 8192
TEMPERATURE = 0.3

FOLDER_TO_CATEGORY = {
    "1真理启示": "真理类",
    "2生命经历": "生命类",
    "3应用实行": "实行类",
}

FOLDER_ORDER = ("1真理启示", "2生命经历", "3应用实行")


def _load_api_key() -> str:
    load_dotenv(BACKEND_DIR / ".env")
    key = (os.getenv("CLAUDE_API_KEY") or "").strip()
    if not key:
        raise SystemExit("未找到 CLAUDE_API_KEY（请检查 back_mic/backend/.env）")
    return key


def _numeric_prefix(path: Path) -> int:
    m = re.match(r"^(\d+)", path.stem)
    return int(m.group(1)) if m else 10**9


def list_docx_in_folder(folder: Path) -> list[Path]:
    files = [p for p in folder.glob("*.docx") if not p.name.startswith("~$")]
    return sorted(files, key=_numeric_prefix)


def read_docx_title_and_excerpt(path: Path) -> tuple[str, str]:
    doc = Document(str(path))
    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    if not paras:
        raise ValueError(f"空文档: {path}")
    title = paras[0]
    excerpt = "\n".join(paras[1:]).strip()
    if not excerpt:
        raise ValueError(f"无纲目正文: {path}")
    return title, excerpt


def build_user_prompt(query: str, excerpt: str) -> str:
    return BURDEN_DESCRIPTION_PROMPT.format(
        query=query,
        outline_nature="",
        audience="",
        reference_excerpt=excerpt,
    )


def call_claude(api_key: str, user_prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": BURDEN_DESCRIPTION_SYSTEM,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    # claude-sonnet-5 拒绝 temperature（invalid_request_error: deprecated）
    if not str(MODEL).startswith("claude-sonnet-5"):
        kwargs["temperature"] = TEMPERATURE
    last_empty_info = ""
    for attempt in range(3):
        if attempt == 1:
            kwargs["max_tokens"] = max(int(kwargs["max_tokens"]), 16000)
        elif attempt >= 2:
            kwargs["max_tokens"] = max(int(kwargs["max_tokens"]), 24000)
        msg = client.messages.create(**kwargs)
        print(
            f"  API model={getattr(msg, 'model', MODEL)} "
            f"stop={getattr(msg, 'stop_reason', None)} attempt={attempt + 1}",
            flush=True,
        )
        parts = []
        block_types = []
        for block in msg.content or []:
            btype = getattr(block, "type", None) or type(block).__name__
            block_types.append(str(btype))
            if btype and btype != "text":
                continue
            text = getattr(block, "text", None)
            if text and str(text).strip():
                parts.append(str(text).strip())
        raw = "\n".join(parts).strip()
        if raw:
            return raw
        last_empty_info = (
            f"stop_reason={getattr(msg, 'stop_reason', None)} "
            f"block_types={block_types}"
        )
        print(f"  空正文，将重试 | {last_empty_info}", flush=True)
    raise RuntimeError(f"Claude 返回为空 | {last_empty_info}")


def parse_burden_text(raw: str) -> str:
    """情境 A：去掉「负担说明：」前缀，只留正文。"""
    text = (raw or "").strip()
    if not text:
        raise RuntimeError("解析失败：空输出")
    m = re.search(r"(?:负担说明|負擔說明)[：:]\s*(.+)", text, re.DOTALL)
    body = m.group(1).strip() if m else text
    body = re.sub(r"\s+", " ", body).strip()
    if not body:
        raise RuntimeError("解析失败：负担说明正文为空")
    return body


def process_one(path: Path, category: str, api_key: str) -> dict:
    title, excerpt = read_docx_title_and_excerpt(path)
    user_prompt = build_user_prompt(title, excerpt)
    raw = call_claude(api_key, user_prompt)
    burden = parse_burden_text(raw)
    return {
        "id": path.stem,
        "分类": category,
        "主题": title,
        "负担说明": burden,
    }


def collect_jobs(*, trial: bool) -> list[tuple[Path, str]]:
    jobs: list[tuple[Path, str]] = []
    for folder_name in FOLDER_ORDER:
        folder = INPUT_ROOT / folder_name
        if not folder.is_dir():
            raise SystemExit(f"找不到输入目录: {folder}")
        category = FOLDER_TO_CATEGORY[folder_name]
        files = list_docx_in_folder(folder)
        if not files:
            raise SystemExit(f"目录无 docx: {folder}")
        if trial:
            if folder_name == "1真理启示":
                return [(files[0], category)]
            continue
        jobs.extend((p, category) for p in files)
    return jobs


def collect_jobs_from_dir(folder: Path, category: str) -> list[tuple[Path, str]]:
    if not folder.is_dir():
        raise SystemExit(f"找不到输入目录: {folder}")
    files = [
        p
        for p in list_docx_in_folder(folder)
        if p.name != "2026秋长.docx"
    ]
    if not files:
        raise SystemExit(f"目录无 docx: {folder}")
    return [(p, category) for p in files]


def main() -> None:
    parser = argparse.ArgumentParser(description="批量生成节期纲目负担说明")
    parser.add_argument(
        "--trial",
        action="store_true",
        help="只处理 1真理启示 中编号最小的一篇，打印结果，不写 JSON",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="自定义输入目录（扁平 docx 列表）。不指定则用第一次测试/30个特会题目",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="自定义输出 JSON 路径。不指定则写第一次测试/feast_burdens_30_sonnet5.json",
    )
    parser.add_argument(
        "--category",
        default="",
        help="--input 模式下写入「分类」字段；默认空",
    )
    args = parser.parse_args()

    out_path = args.output.resolve() if args.output else OUTPUT_JSON
    if args.input:
        jobs = collect_jobs_from_dir(args.input.resolve(), args.category)
    else:
        jobs = collect_jobs(trial=args.trial)

    api_key = _load_api_key()
    records: list[dict] = []
    errors: list[str] = []
    for i, (path, category) in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] {category} {path.name}", flush=True)
        try:
            rec = process_one(path, category, api_key)
        except Exception as e:
            errors.append(f"{path.stem}: {e}")
            print(f"  失败: {e}", flush=True)
            continue
        records.append(rec)
        if args.trial and not args.input:
            print("---")
            print(f"model: {MODEL}")
            print(f"id: {rec['id']}")
            print(f"分类: {rec['分类']}")
            print(f"主题: {rec['主题']}")
            print(f"负担说明: {rec['负担说明']}")
            print("---")
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    if not args.trial or args.input:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"已写入 {out_path}（{len(records)} 条）")
        if errors:
            print("失败列表：")
            for line in errors:
                print(f"  - {line}")


if __name__ == "__main__":
    main()
