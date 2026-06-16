# -*- coding: utf-8 -*-
"""
将「主恢复中神圣启示的进展」Word 纲目批量解析并写入 Elasticsearch。

用法：
  cd back_mic/backend
  python scripts/progress_outline/ingest_pano.py --source-dir <Word 文件根目录>
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, TextIO

from docx import Document
from dotenv import load_dotenv
from natsort import natsorted

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from es_config import es  # noqa: E402

ES_INDEX = "progress_pano"
BULK_CHUNK = 200
LOG_FILE = SCRIPT_DIR / "ingest_pano.log"

_log_fp: TextIO | None = None
_root_dir: Path | None = None

SOURCE_GROUP_MAP: dict[str, int] = {
    "倪柝声弟兄职事": 1,
    "李常受弟兄职事第一阶段": 2,
    "李常受弟兄职事第二阶段": 3,
    "李常受弟兄职事第三阶段": 4,
    "李常受弟兄职事第四阶段": 5,
    "李常受弟兄职事高峰阶段": 6,
}

SERIES_FOLDER_RE = re.compile(r"^(\d+)\s+(.+?)(?:——|—)\d+篇")
MSG_FILE_RE = re.compile(r"^msg\.\s*(\d+)\s+(.+?)\.docx$", re.IGNORECASE)
SKIP_FILE_TAG = "纲目带出处"

READING_MARKERS = ("读经：", "讀經：")
MINISTRY_MARKERS = ("职事信息摘录", "職事信息摘錄")

OUTLINE_TYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("ot1", re.compile(r"^[壹贰貳叁參叄肆伍陆陸柒捌玖拾][\t　]")),
    ("ot2", re.compile(r"^[一二三四五六七八九十百千万萬亿億]+[\t　]")),
    ("ot3", re.compile(r"^\d+[\t　]")),
    ("ot4", re.compile(r"^[a-z][\t　]")),
    ("ot6", re.compile(r"^\([一二三四五六七八九十百千万萬亿億]+\)[\t　]")),
    ("ot5", re.compile(r"^\(\d+\)[\t　]")),
    ("ot7", re.compile(r"^\([a-z]\)[\t　]")),
]

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "series_no": {"type": "integer"},
            "series_title": {"type": "keyword"},
            "source_group_no": {"type": "integer"},
            "source_group_title": {"type": "keyword"},
            "article_no": {"type": "integer"},
            "title": {"type": "keyword"},
            "metadata": {"type": "text"},
            "outline": {
                "type": "nested",
                "properties": {
                    "type": {"type": "keyword"},
                    "text": {"type": "text"},
                },
            },
            "ministry_excerpt": {
                "type": "nested",
                "properties": {"text": {"type": "text"}},
            },
        }
    }
}


def arabic_to_chinese(n: int) -> str:
    if not 1 <= n <= 999:
        raise ValueError(f"article_no 超出 1-999 范围: {n}")
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n % 10] if n % 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        text = digits[tens] + "十"
        if ones:
            text += digits[ones]
        return text
    hundreds, rem = divmod(n, 100)
    text = digits[hundreds] + "百"
    if rem == 0:
        return text
    if rem < 10:
        return text + "零" + digits[rem]
    if rem < 20:
        return text + "十" + (digits[rem % 10] if rem % 10 else "")
    tens, ones = divmod(rem, 10)
    text += digits[tens] + "十"
    if ones:
        text += digits[ones]
    return text


def parse_series_folder(name: str) -> dict[str, Any] | None:
    m = SERIES_FOLDER_RE.match(name.strip())
    if not m:
        return None
    return {"no": int(m.group(1)), "title": m.group(2).strip()}


def normalize_for_match(name: str) -> str:
    return name.replace("弟兄的职事", "弟兄职事")


def match_source_group(folder_name: str) -> dict[str, Any] | None:
    normalized = normalize_for_match(folder_name)
    best_len = 0
    best: dict[str, Any] | None = None
    for title, no in sorted(SOURCE_GROUP_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if title in normalized and len(title) > best_len:
            best_len = len(title)
            best = {"no": no, "title": title}
    return best


def parse_msg_file(name: str) -> dict[str, Any] | None:
    m = MSG_FILE_RE.match(name.strip())
    if not m:
        return None
    article_no = int(m.group(1))
    topic = m.group(2).strip()
    return {
        "article_no": article_no,
        "title": f"第{arabic_to_chinese(article_no)}篇　{topic}",
    }


def should_skip_file(path: Path) -> bool:
    return SKIP_FILE_TAG in path.name


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _outline_type(text: str) -> str:
    stripped = text.strip()
    if _contains_marker(stripped, READING_MARKERS):
        return "bible_reading"
    for type_name, pattern in OUTLINE_TYPE_RULES:
        if pattern.match(stripped):
            return type_name
    return "ot2"


def _normalize_ministry_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\n", " ").replace("\r", " ")).strip()


def _paragraph_is_bold(paragraph) -> bool:
    runs = [r for r in paragraph.runs if r.text and r.text.strip()]
    if not runs:
        return False
    return all(r.bold is True for r in runs)


def _parse_ministry_excerpt(paragraphs) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    title_parts: list[str] = []
    body_parts: list[str] = []

    def flush() -> None:
        nonlocal title_parts, body_parts
        chunks: list[str] = []
        if title_parts:
            chunks.append(_normalize_ministry_text(" ".join(title_parts)))
        if body_parts:
            chunks.append(_normalize_ministry_text(" ".join(body_parts)))
        text = " ".join(c for c in chunks if c).strip()
        if text:
            result.append({"text": text})
        title_parts = []
        body_parts = []

    for para in paragraphs:
        raw = para.text.strip()
        if not raw:
            continue
        text = _normalize_ministry_text(raw)
        if _paragraph_is_bold(para):
            if body_parts:
                flush()
                title_parts = [text]
            else:
                title_parts.append(text)
        else:
            body_parts.append(text)
    flush()
    return result


def parse_docx(path: Path) -> dict[str, Any]:
    doc = Document(str(path))
    para_objs = doc.paragraphs
    paragraphs = [p.text.strip() for p in para_objs]

    reading_idx: int | None = None
    ministry_idx: int | None = None
    for idx, text in enumerate(paragraphs):
        if not text:
            continue
        if reading_idx is None and _contains_marker(text, READING_MARKERS):
            reading_idx = idx
        if ministry_idx is None and _contains_marker(text, MINISTRY_MARKERS):
            ministry_idx = idx

    metadata: list[str] = []
    outline: list[dict[str, str]] = []
    ministry_excerpt: list[dict[str, str]] = []

    if reading_idx is None:
        metadata = [t for t in paragraphs if t]
    else:
        metadata = [t for t in paragraphs[:reading_idx] if t]
        outline_end = ministry_idx if ministry_idx is not None else len(paragraphs)
        for text in paragraphs[reading_idx:outline_end]:
            if text:
                outline.append({"type": _outline_type(text), "text": text})
        if ministry_idx is not None:
            ministry_excerpt = _parse_ministry_excerpt(para_objs[ministry_idx + 1 :])

    return {
        "metadata": metadata,
        "outline": outline,
        "ministry_excerpt": ministry_excerpt,
    }


def iter_docx_leaf_dirs(group_dir: Path) -> list[Path]:
    leaves: list[Path] = []
    if any(group_dir.glob("*.docx")):
        leaves.append(group_dir)
    for child in natsorted([p for p in group_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
        leaves.extend(iter_docx_leaf_dirs(child))
    return leaves


def collect_group_docx(group_dir: Path) -> list[Path]:
    files: list[Path] = []
    for leaf in natsorted(iter_docx_leaf_dirs(group_dir), key=lambda p: str(p)):
        for docx_path in natsorted(leaf.glob("*.docx"), key=lambda p: p.name):
            if should_skip_file(docx_path):
                continue
            if parse_msg_file(docx_path.name) is None:
                continue
            files.append(docx_path)
    return natsorted(files, key=lambda p: str(p.relative_to(group_dir)))


def iter_articles(root: Path) -> Iterator[dict[str, Any]]:
    if not root.is_dir():
        raise FileNotFoundError(f"source-dir 不存在: {root}")

    for series_dir in natsorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name):
        series = parse_series_folder(series_dir.name)
        if not series:
            continue

        group_dirs = natsorted(
            [p for p in series_dir.iterdir() if p.is_dir()],
            key=lambda p: p.name,
        )
        branches: dict[int, tuple[dict[str, Any], list[Path]]] = {}
        for group_dir in group_dirs:
            group = match_source_group(group_dir.name)
            if not group:
                continue
            if group["no"] not in branches:
                branches[group["no"]] = (group, [])
            branches[group["no"]][1].append(group_dir)

        for group_no in natsorted(branches.keys()):
            group, dirs = branches[group_no]
            docx_files: list[Path] = []
            for group_dir in natsorted(dirs, key=lambda p: p.name):
                docx_files.extend(collect_group_docx(group_dir))
            docx_files = natsorted(docx_files, key=lambda p: str(p))

            for seq_no, docx_path in enumerate(docx_files, start=1):
                msg = parse_msg_file(docx_path.name)
                if not msg:
                    continue
                parsed = parse_docx(docx_path)
                doc_id = f"{ES_INDEX}-{series['no']}-{group['no']}-{seq_no}"
                yield {
                    "_id": doc_id,
                    "series_no": series["no"],
                    "series_title": series["title"],
                    "source_group_no": group["no"],
                    "source_group_title": group["title"],
                    "article_no": msg["article_no"],
                    "title": msg["title"],
                    **parsed,
                }


def ensure_index(recreate: bool = False) -> None:
    if recreate and es.indices.exists(index=ES_INDEX):
        es.indices.delete(index=ES_INDEX)
        log(f"已删除索引: {ES_INDEX}")
    if not es.indices.exists(index=ES_INDEX):
        es.indices.create(index=ES_INDEX, body=INDEX_MAPPING)
        log(f"已创建索引: {ES_INDEX}")
    else:
        log(f"索引已存在: {ES_INDEX}")


def bulk_index(docs: list[dict[str, Any]]) -> None:
    if not docs:
        return
    operations: list[dict[str, Any]] = []
    for doc in docs:
        doc_id = doc.pop("_id")
        operations.append({"index": {"_index": ES_INDEX, "_id": doc_id}})
        operations.append(doc)
    es.bulk(operations=operations, refresh=False)


def log(msg: str) -> None:
    print(msg)
    if _log_fp is not None:
        _log_fp.write(msg + "\n")
        _log_fp.flush()


def open_log(source_dir: Path) -> None:
    global _log_fp
    _log_fp = LOG_FILE.open("w", encoding="utf-8")
    log(f"# ingest_pano {datetime.now().isoformat(timespec='seconds')}")
    log(f"# source-dir: {source_dir}")
    log(f"# LOG_FILE: {LOG_FILE}")
    log("")


def close_log() -> None:
    global _log_fp
    if _log_fp is not None:
        _log_fp.close()
        _log_fp = None


def print_series_summary(series_counts: dict[int, tuple[str, int]]) -> None:
    log("── 系列篇数统计 ──")
    total = 0
    for series_no in natsorted(series_counts.keys()):
        title, count = series_counts[series_no]
        log(f"  系列 {series_no:>2}　{title}：{count} 篇")
        total += count
    log(f"  合计：{total} 篇")
    log("")


def reindex_doc(source_dir: Path, doc_id: str) -> dict[str, Any]:
    target: dict[str, Any] | None = None
    for doc in iter_articles(source_dir):
        if doc["_id"] == doc_id:
            target = doc
            break
    if not target:
        raise ValueError(f"未找到文档: {doc_id}")
    bulk_index([target])
    es.indices.refresh(index=ES_INDEX)
    return target


def run_ingest(source_dir: Path, *, recreate: bool = True) -> None:
    global _root_dir
    _root_dir = source_dir
    open_log(source_dir)
    try:
        ensure_index(recreate=recreate)
        total = 0
        batch: list[dict[str, Any]] = []
        series_counts: dict[int, tuple[str, int]] = {}

        for doc in iter_articles(source_dir):
            log(f"✓ {doc['_id']} {doc['title']}")
            batch.append(doc)
            total += 1
            sno = doc["series_no"]
            if sno not in series_counts:
                series_counts[sno] = (doc["series_title"], 0)
            title, cnt = series_counts[sno]
            series_counts[sno] = (title, cnt + 1)
            if len(batch) >= BULK_CHUNK:
                bulk_index(batch)
                batch.clear()

        if batch:
            bulk_index(batch)

        es.indices.refresh(index=ES_INDEX)
        log("")
        print_series_summary(series_counts)
        log(f"总计入库 {total} 篇")
        log(f"日志已写入: {LOG_FILE}")
    finally:
        close_log()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将进展75系列 Word 纲目解析并写入 Elasticsearch 索引 progress_pano"
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Word 纲目根目录（含系列子文件夹）",
    )
    parser.add_argument(
        "--doc-id",
        help="仅重新入库指定 _id，如 progress_pano-1-1-1（需同时提供 --source-dir）",
    )
    parser.add_argument(
        "--no-recreate",
        action="store_true",
        help="全量入库时不重建索引（默认会 delete+create）",
    )
    args = parser.parse_args()

    if args.doc_id:
        if not args.source_dir:
            parser.error("--doc-id 需要同时指定 --source-dir")
        open_log(args.source_dir)
        try:
            ensure_index(recreate=False)
            doc = reindex_doc(args.source_dir, args.doc_id)
            log(
                f"✓ 已重新入库 {args.doc_id} "
                f"ministry_excerpt={len(doc.get('ministry_excerpt', []))} 条"
            )
        finally:
            close_log()
        return

    if not args.source_dir:
        parser.error("请指定 --source-dir，或使用 --help 查看用法")
    run_ingest(args.source_dir, recreate=not args.no_recreate)


if __name__ == "__main__":
    main()
