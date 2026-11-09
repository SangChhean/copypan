# -*- coding: utf-8 -*-
"""将 PanAI 4.0 数据包中的十个 ES 索引导入本机 qa4-es（目标名 qa4_*，不重算向量）。

用法示例：
  python es_import.py --data-root <解压后 es/data> --offline --dry-run
  python es_import.py --data-root <解压后 es/data> --only panai4_hymns panai4_bible
  python es_import.py --data-root <解压后 es/data> --force --only panai4_bible

密码只从环境变量 QA4_ES_PASSWORD 读取，无命令行密码参数；日志不得出现密码。
默认目标 http://127.0.0.1:9202 ，用户 elastic，HTTP 无 SSL。

第三方依赖（非标准库）：
  - elasticsearch（官方 Python 客户端，含 elasticsearch.helpers.bulk）
    服务器已验证可用版本示例：elasticsearch==8.19.3
  其余均为 Python 标准库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk
except ImportError:
    print("需要安装 elasticsearch：pip install elasticsearch", file=sys.stderr)
    raise

HERE = Path(__file__).resolve().parent
# 日志目录：优先环境变量 QA4_LOG_DIR；未设置时 Windows 本机默认，Linux 回退 /opt/qa4_logs
DEFAULT_LOG_DIR = Path(
    os.environ.get("QA4_LOG_DIR")
    or (r"G:\PanAI4.0专用\logs" if os.name == "nt" else "/opt/qa4_logs")
)
SOURCE_PREFIX = "panai4_"
DEFAULT_INDEX_PREFIX = "qa4_"
DEFAULT_ES_URL = "http://127.0.0.1:9202"
DEFAULT_ES_USER = "elastic"
REQUIRED_CLUSTER_NAME = "qa4"

VEC_DIMS = 1024
BULK_SIZE = 200

DENSE_EMB = {
    "type": "dense_vector",
    "dims": VEC_DIMS,
    "index": True,
    "similarity": "cosine",
    "index_options": {"type": "int8_hnsw"},
}


def _text_ik() -> dict:
    return {
        "type": "text",
        "analyzer": "ik_max_word",
        "search_analyzer": "ik_smart",
    }


def _kw_with_text() -> dict:
    return {
        "type": "keyword",
        "fields": {"text": _text_ik()},
    }


def _text_with_keyword() -> dict:
    return {
        "type": "text",
        "analyzer": "ik_max_word",
        "search_analyzer": "ik_smart",
        "fields": {"keyword": {"type": "keyword"}},
    }


OUTLINE_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "message_key": {"type": "keyword"},
            "source_path": {"type": "keyword", "index": False},
            "batch": {"type": "keyword"},
            "text": _text_ik(),
            "embedding": dict(DENSE_EMB),
            "book_title": _kw_with_text(),
            "book_path": {"type": "keyword"},
            "message_title": _kw_with_text(),
            "message_number": {"type": "integer"},
            "author": {"type": "keyword"},
            "year": {"type": "integer"},
            "year_end": {"type": "integer"},
            "paragraph_type": {"type": "keyword"},
            "tokens": {"type": "integer"},
            "min_level": {"type": "integer"},
            "point_count": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            "chunk_total": {"type": "integer"},
            "para_nos": {"type": "integer", "index": False},
            "part_no": {"type": "integer"},
            "part_name": {"type": "keyword"},
            "conference": {"type": "keyword"},
            "month": {"type": "integer"},
        }
    },
}

BIBLE_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "message_key": {"type": "keyword"},
            "batch": {"type": "keyword"},
            "chunk_type": {"type": "keyword"},
            "text": _text_ik(),
            "embedding": dict(DENSE_EMB),
            "book_title": _kw_with_text(),
            "book_no": {"type": "integer"},
            "message_title": _kw_with_text(),
            "message_number": {"type": "integer"},
            "author": {"type": "keyword"},
            "verse_range": {"type": "keyword"},
            "outline_path": {"type": "keyword"},
            "outline_level": {"type": "integer"},
            "paragraph_type": {"type": "keyword"},
            "tokens": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            "chunk_total": {"type": "integer"},
            "split_rule": {"type": "keyword"},
            "source_keys": {"type": "integer", "index": False},
        }
    },
}

HYMNS_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "message_key": {"type": "keyword"},
            "series": {"type": "keyword"},
            "hymn_number": {"type": "integer"},
            "name": _kw_with_text(),
            "title": _kw_with_text(),
            "category": {"type": "keyword"},
            "subtitle": _kw_with_text(),
            "reference": {"type": "keyword", "index": False},
            "unit_type": {"type": "keyword"},
            "unit_label": {"type": "keyword"},
            "chunk_index": {"type": "integer"},
            "chunk_total": {"type": "integer"},
            "tokens": {"type": "integer"},
            "text": _text_ik(),
            "embedding": dict(DENSE_EMB),
        }
    },
}


def inherit_mapping(*, has_year: bool, has_section: bool) -> dict:
    props: dict[str, Any] = {
        "chunk_id": {"type": "keyword"},
        "message_key": {"type": "keyword"},
        "source_index": {"type": "keyword"},
        "corpus": {"type": "keyword"},
        "text": _text_ik(),
        "text_vector": dict(DENSE_EMB),
        "book_title": _text_with_keyword(),
        "message_title": _text_ik(),
        "message_number": {"type": "integer"},
        "author": {"type": "keyword"},
        "paragraph_type": {"type": "keyword"},
        "source_zh": {"type": "text", "index": False},
        "source_en": {"type": "text", "index": False},
        "en": {"type": "text", "index": False},
        "original_ids": {"type": "keyword"},
        "chars": {"type": "integer"},
    }
    if has_section:
        props["section_title"] = _text_ik()
    if has_year:
        props["year"] = {"type": "integer"}
    return {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {"properties": props},
    }


PANO_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "node_type": {"type": "keyword"},
            "node_id": {"type": "keyword"},
            "name": _text_ik(),
            "raw_name": {"type": "keyword"},
            "ordinal_num": {"type": "integer"},
            "depth": {"type": "integer"},
            "rel_path": {"type": "keyword"},
            "path_names": {"type": "keyword"},
            "path_text": _text_ik(),
            "top_category": {"type": "keyword"},
            "top_ordinal": {"type": "integer"},
            "actual_count": {"type": "integer"},
            "has_subdir": {"type": "boolean"},
            "has_docx": {"type": "boolean"},
            "annotations": _text_ik(),
            "text": _text_ik(),
            "msg_number": {"type": "integer"},
            "msg_label": {"type": "keyword"},
            "title": _text_ik(),
            "raw_filename": {"type": "keyword"},
            "title_variants": {"type": "keyword"},
            "source_version_only": {"type": "boolean"},
            "text_vector": dict(DENSE_EMB),
        }
    },
}

# kind:
#   embedding_jsonl  — outline/bible/hymns；向量字段 embedding
#   inherit_jsonl    — text_* / map_note；文件里 embedding → 写入 text_vector
#   pano_jsonl       — 无向量；_id = node_id
INDEX_SPECS: dict[str, dict[str, Any]] = {
    "panai4_outline_12490": {
        "expect": 55841,
        "vec_field": "embedding",
        "id_field": "chunk_id",
        "kind": "embedding_jsonl",
        "mapping": OUTLINE_MAPPING,
        "files": ["chunks_12490_vec.new.json"],
    },
    "panai4_outline_feasts": {
        "expect": 11110,
        "vec_field": "embedding",
        "id_field": "chunk_id",
        "kind": "embedding_jsonl",
        "mapping": OUTLINE_MAPPING,
        "files": ["chunks_feasts_vec.json"],
    },
    "panai4_bible": {
        "expect": 3691,
        "vec_field": "embedding",
        "id_field": "chunk_id",
        "kind": "embedding_jsonl",
        "mapping": BIBLE_MAPPING,
        "files": ["chunks_bible_vec.json"],
    },
    "panai4_hymns": {
        "expect": 9154,
        "vec_field": "embedding",
        "id_field": "chunk_id",
        "kind": "embedding_jsonl",
        "mapping": HYMNS_MAPPING,
        "files": ["chunks_hymns_vec.json"],
    },
    "panai4_text_life": {
        "expect": 39463,
        "vec_field": "text_vector",
        "id_field": "chunk_id",
        "kind": "inherit_jsonl",
        "mapping": inherit_mapping(has_year=False, has_section=True),
        "files_glob": "shards/*.jsonl",
    },
    "panai4_text_cwwl": {
        "expect": 178107,
        "vec_field": "text_vector",
        "id_field": "chunk_id",
        "kind": "inherit_jsonl",
        "mapping": inherit_mapping(has_year=True, has_section=True),
        "files_glob": "shards/*.jsonl",
    },
    "panai4_text_cwwn": {
        "expect": 32032,
        "vec_field": "text_vector",
        "id_field": "chunk_id",
        "kind": "inherit_jsonl",
        "mapping": inherit_mapping(has_year=False, has_section=True),
        "files_glob": "shards/*.jsonl",
    },
    "panai4_text_others": {
        "expect": 15481,
        "vec_field": "text_vector",
        "id_field": "chunk_id",
        "kind": "inherit_jsonl",
        "mapping": inherit_mapping(has_year=False, has_section=True),
        "files_glob": "shards/*.jsonl",
    },
    "panai4_map_note": {
        "expect": 16052,
        "vec_field": "text_vector",
        "id_field": "chunk_id",
        "kind": "inherit_jsonl",
        "mapping": inherit_mapping(has_year=False, has_section=False),
        "files_glob": "shards/*.jsonl",
    },
    "panai4_pano_catalog": {
        "expect": 53151,
        "vec_field": None,
        "id_field": "node_id",
        "kind": "pano_jsonl",
        "mapping": PANO_MAPPING,
        "files": ["docs.jsonl"],
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load_manifest_expect(data_root: Path) -> tuple[dict[str, int], str | None]:
    """优先读包内 MANIFEST.json；否则用内置 expect。

    返回 (expect_map, source)：
      source 为 MANIFEST.json 的绝对路径字符串；若回退内置则为 None。
    """
    for cand in (
        data_root.parent.parent / "MANIFEST.json",
        data_root.parent / "MANIFEST.json",
        HERE / "MANIFEST.json",
        HERE.parent / "MANIFEST.json",
    ):
        if cand.is_file():
            data = json.loads(cand.read_text(encoding="utf-8"))
            out = {}
            for row in data.get("indices", []):
                out[row["name"]] = int(row["doc_count"])
            if out:
                return out, str(cand.resolve())
    return {k: int(v["expect"]) for k, v in INDEX_SPECS.items()}, None


def resolve_files(index: str, data_root: Path) -> list[Path]:
    spec = INDEX_SPECS[index]
    base = data_root / index
    if "files" in spec:
        paths = [base / name for name in spec["files"]]
    else:
        paths = sorted(base.glob(spec["files_glob"]))
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"{index}: 缺少文件 {[str(p) for p in missing]}")
    if not paths:
        raise FileNotFoundError(f"{index}: 未找到数据文件 under {base}")
    return paths


def iter_jsonl(paths: Iterable[Path]) -> Iterator[dict]:
    for path in paths:
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{lineno}: JSON 解析失败: {e}") from e


def count_jsonl(paths: list[Path]) -> int:
    n = 0
    for path in paths:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
    return n


def files_total_bytes(paths: list[Path]) -> int:
    return sum(p.stat().st_size for p in paths)


def target_index_name(source: str, index_prefix: str, index_suffix: str) -> str:
    if not source.startswith(SOURCE_PREFIX):
        raise ValueError(f"源索引名必须以 {SOURCE_PREFIX!r} 开头: {source}")
    stem = source[len(SOURCE_PREFIX) :]
    return f"{index_prefix}{stem}{index_suffix or ''}"


def assert_safe_target(target: str) -> None:
    """任何一条不满足即中止（调用方须在写操作之前调用）。"""
    if "*" in target or "?" in target:
        raise SystemExit(f"拒绝：目标索引名含通配符: {target}")
    if not target.startswith(DEFAULT_INDEX_PREFIX):
        raise SystemExit(f"拒绝：目标索引名必须以 {DEFAULT_INDEX_PREFIX!r} 开头: {target}")
    if target.startswith(SOURCE_PREFIX):
        raise SystemExit(f"拒绝：禁止以 panai4_* 作为目标: {target}")
    if target.startswith("kg-rag_") or target.startswith("kg_rag_"):
        raise SystemExit(f"拒绝：禁止以 kg-rag_* 作为目标: {target}")


def row_to_action(index: str, target_index: str, row: dict) -> dict | None:
    spec = INDEX_SPECS[index]
    kind = spec["kind"]
    id_field = spec["id_field"]
    doc_id = row.get(id_field)
    if not doc_id:
        return None

    if kind == "embedding_jsonl":
        src = {k: v for k, v in row.items() if v is not None}
        emb = src.get("embedding")
        if not isinstance(emb, list) or len(emb) != VEC_DIMS:
            return None
        return {"_op_type": "index", "_index": target_index, "_id": doc_id, "_source": src}

    if kind == "inherit_jsonl":
        mapping_fields = set(spec["mapping"]["mappings"]["properties"].keys())
        emb = row.get("embedding") if row.get("embedding") is not None else row.get("text_vector")
        if not isinstance(emb, list) or len(emb) != VEC_DIMS:
            return None
        src: dict[str, Any] = {}
        for k in mapping_fields:
            if k == "text_vector":
                continue
            if k not in row:
                continue
            if k == "section_title" and (row[k] is None or row[k] == ""):
                continue
            src[k] = row[k]
        src["text_vector"] = emb
        return {"_op_type": "index", "_index": target_index, "_id": doc_id, "_source": src}

    if kind == "pano_jsonl":
        src = {k: v for k, v in row.items() if k != "text_vector" and v is not None}
        return {"_op_type": "index", "_index": target_index, "_id": doc_id, "_source": src}

    raise ValueError(f"unknown kind {kind}")


def make_client(es_url: str, user: str, password: str) -> Elasticsearch:
    return Elasticsearch(
        hosts=[es_url],
        basic_auth=(user, password),
        request_timeout=180,
        verify_certs=False,
        ssl_show_warn=False,
    )


def check_es_version(es: Elasticsearch) -> str:
    info = es.info()
    ver = str(info.get("version", {}).get("number") or "")
    major = ver.split(".", 1)[0]
    if major != "8":
        raise SystemExit(f"ERROR: 目标 ES 主版本为 {ver!r}，本数据包要求 8.x（建议 8.19.0）。")
    return ver


def assert_cluster_name(es: Elasticsearch) -> str:
    info = es.info()  # GET /
    name = str(info.get("cluster_name") or "")
    if name != REQUIRED_CLUSTER_NAME:
        raise SystemExit(
            f"中止：cluster_name={name!r}，必须等于 {REQUIRED_CLUSTER_NAME!r}。"
            "未执行任何写操作。"
        )
    return name


class _RedactingFilter(logging.Filter):
    def __init__(self, secrets: list[str]):
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for s in self._secrets:
            if s and s in msg:
                msg = msg.replace(s, "***")
        record.msg = msg
        record.args = ()
        return True


def setup_logging(log_file: Path, secrets: list[str]) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("qa4_es_import")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(_RedactingFilter(secrets))
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.addFilter(_RedactingFilter(secrets))
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def offline_plan(
    data_root: Path,
    indices: list[str],
    expect: dict[str, int],
    index_prefix: str,
    index_suffix: str,
    log: logging.Logger,
) -> int:
    log.info("=== offline/dry-run：解析文件与导入计划（不连接 ES）===")
    total_docs = 0
    total_bytes = 0
    log.info(
        f"{'source':28} {'target':28} {'files':>6} {'bytes':>14} {'manifest':>10}"
    )
    for idx in indices:
        target = target_index_name(idx, index_prefix, index_suffix)
        assert_safe_target(target)
        paths = resolve_files(idx, data_root)
        nbytes = files_total_bytes(paths)
        exp = int(expect[idx])
        total_docs += exp
        total_bytes += nbytes
        log.info(
            f"{idx:28} {target:28} {len(paths):6d} {nbytes:14d} {exp:10d}"
        )
    log.info(f"MANIFEST 期望文档数合计 = {total_docs}")
    log.info(f"文件总字节 = {total_bytes}")
    if total_docs != 414082 and set(indices) == set(INDEX_SPECS.keys()):
        log.error(f"期望文档数之和应为 414082，实际 {total_docs}")
        return 1
    return 0


def import_one(
    es: Elasticsearch,
    index: str,
    data_root: Path,
    *,
    force: bool,
    index_prefix: str,
    index_suffix: str,
    expect: dict[str, int],
    log: logging.Logger,
) -> tuple[bool, int, int]:
    spec = INDEX_SPECS[index]
    target = target_index_name(index, index_prefix, index_suffix)
    assert_safe_target(target)

    paths = resolve_files(index, data_root)
    file_docs = count_jsonl(paths)
    exp = expect[index]
    if file_docs != exp:
        log.error(f"FAIL {index}: 包内文档数 {file_docs} != MANIFEST {exp}")
        return False, file_docs, -1

    exists = bool(es.indices.exists(index=target))
    if exists and not force:
        cur = int(es.count(index=target)["count"])
        log.error(
            f"中止 {target}: 已存在（docs={cur}）。默认拒绝覆盖；"
            "仅当 --force 且目标为明确列出的 qa4_* 时可删除重建。"
        )
        return False, file_docs, cur

    if exists and force:
        # 再保险：禁止通配、必须 qa4_
        assert_safe_target(target)
        cur = int(es.count(index=target)["count"])
        log.info(f"FORCE 将删除索引 {target}（现有文档数={cur}）")
        es.indices.delete(index=target)

    body = deepcopy(spec["mapping"])
    # 与原脚本一致：直接用 mapping 创建，不在导入期间改 refresh_interval 等 settings
    log.info(f"CREATE {target}")
    es.indices.create(index=target, body=body)

    def gen():
        for row in iter_jsonl(paths):
            action = row_to_action(index, target, row)
            if action is not None:
                yield action

    t0 = time.perf_counter()
    ok_n, errors = bulk(
        es,
        gen(),
        chunk_size=BULK_SIZE,
        raise_on_error=False,
        raise_on_exception=False,
        request_timeout=180,
    )
    # 导入完成后必须先 refresh，再读取 count（顺序不可颠倒）
    es.indices.refresh(index=target)
    elapsed = time.perf_counter() - t0
    err_n = len(errors) if errors else 0
    final = int(es.count(index=target)["count"])
    log.info(
        f"DONE {target}: bulk_ok={ok_n} bulk_err={err_n} count={final} expect={exp} "
        f"elapsed={elapsed:.1f}s"
    )
    if errors:
        log.error("sample_error " + json.dumps(errors[0], ensure_ascii=False)[:400])
    if final != exp or err_n != 0:
        log.error(f"FAIL {target}: 导入后文档数/错误不达标 count={final} expect={exp} err={err_n}")
        return False, file_docs, final
    return True, file_docs, final


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import PanAI4.0 ES pack into qa4-es as qa4_* indices")
    p.add_argument("--data-root", default=None, help="解压出的 es/data 目录（非 --self-test 时必需）")
    p.add_argument("--es-url", default=DEFAULT_ES_URL, help="ES URL（默认 http://127.0.0.1:9202）")
    p.add_argument("--user", default=DEFAULT_ES_USER, help="ES 用户名（默认 elastic）")
    p.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="只导入指定源索引名（可多个，如 panai4_hymns panai4_bible）",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="必须与 --only 同时使用；仅删除 --only 明确列出且以 qa4_ 开头的目标索引后重建",
    )
    p.add_argument("--dry-run", action="store_true", help="只解析/校验，不写 ES")
    p.add_argument(
        "--offline",
        action="store_true",
        help="与 --dry-run 合用：不连接 ES，只解析文件并打印计划",
    )
    p.add_argument(
        "--index-prefix",
        default=DEFAULT_INDEX_PREFIX,
        help="目标索引前缀（默认 qa4_）",
    )
    p.add_argument(
        "--index-suffix",
        default="",
        help="目标索引名后缀（测试用）；正式导入请留空",
    )
    p.add_argument(
        "--log-file",
        default=None,
        help="日志路径（默认 $QA4_LOG_DIR/qa4_import_<时间戳>.log）",
    )
    p.add_argument(
        "--self-test",
        action="store_true",
        help="不连 ES 的自测（映射/拒绝/假密码脱敏）",
    )
    return p.parse_args(argv)


def run_self_test(log: logging.Logger) -> int:
    log.info("=== self-test（不连接 ES）===")
    ok = True

    # 1) 十个源名 → qa4_*
    for src in INDEX_SPECS:
        tgt = target_index_name(src, DEFAULT_INDEX_PREFIX, "")
        try:
            assert_safe_target(tgt)
        except SystemExit as e:
            log.error(f"映射失败 {src} -> {tgt}: {e}")
            ok = False
            continue
        expect = DEFAULT_INDEX_PREFIX + src[len(SOURCE_PREFIX) :]
        if tgt != expect:
            log.error(f"映射错误 {src} -> {tgt} 期望 {expect}")
            ok = False
        else:
            log.info(f"MAP_OK {src} -> {tgt}")

    # 2) 拒绝危险目标
    for bad in ("panai4_bible", "kg-rag_life", "qa4_*"):
        try:
            assert_safe_target(bad)
            log.error(f"REJECT_FAIL 应拒绝但未拒绝: {bad}")
            ok = False
        except SystemExit:
            log.info(f"REJECT_OK {bad}")

    # 3) 模拟 cluster_name 非 qa4：在写之前中止，且无写调用
    class _FakeES:
        def __init__(self):
            self.writes = []
            self.indices = self

        def info(self):
            return {"cluster_name": "docker-cluster", "version": {"number": "8.19.0"}}

        def exists(self, index=None):
            self.writes.append(("exists", index))
            return False

        def create(self, **kwargs):
            self.writes.append(("create", kwargs))

        def delete(self, **kwargs):
            self.writes.append(("delete", kwargs))

        def count(self, **kwargs):
            self.writes.append(("count", kwargs))
            return {"count": 0}

        def refresh(self, **kwargs):
            self.writes.append(("refresh", kwargs))

    fake = _FakeES()
    write_before = list(fake.writes)
    try:
        assert_cluster_name(fake)
        log.error("CLUSTER_FAIL 应因 cluster_name 中止")
        ok = False
    except SystemExit as e:
        log.info(f"CLUSTER_OK 中止: {e}")
    if fake.writes != write_before:
        log.error(f"CLUSTER_FAIL 发生了写相关调用: {fake.writes}")
        ok = False
    else:
        log.info("CLUSTER_OK 无写调用")

    # 4) 假密码不得出现在日志消息路径（过滤器）
    secret = "FAKE_SECRET_PASSWORD_XYZ_9977"
    filt = _RedactingFilter([secret])
    rec = logging.LogRecord(
        name="t", level=logging.INFO, pathname=__file__, lineno=1,
        msg=f"auth with {secret} ok", args=(), exc_info=None,
    )
    filt.filter(rec)
    if secret in rec.getMessage():
        log.error("REDACT_FAIL 密码仍出现在日志记录中")
        ok = False
    else:
        log.info("REDACT_OK 日志记录已脱敏")

    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    password = os.environ.get("QA4_ES_PASSWORD") or ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(args.log_file) if args.log_file else (DEFAULT_LOG_DIR / f"qa4_import_{ts}.log")
    log = setup_logging(log_file, [password] if password else [])
    log.info(f"log_file={log_file}")

    if args.self_test:
        code = run_self_test(log)
        log.info(f"self-test exit={code}")
        return code

    # --force 必须与 --only 同时使用（在任何连接之前拒绝）
    if args.force and not args.only:
        log.error(
            "拒绝：--force 必须与 --only 同时使用；"
            "--force 只作用于 --only 明确列出的索引。未尝试连接 ES。"
        )
        return 2

    if args.offline and not args.dry_run:
        log.error("--offline 必须与 --dry-run 合用")
        return 1

    if not args.index_prefix.startswith(DEFAULT_INDEX_PREFIX):
        # 允许仅等于 qa4_；若用户改前缀也必须仍以 qa4_ 开头
        log.error(f"--index-prefix 必须以 {DEFAULT_INDEX_PREFIX!r} 开头，收到 {args.index_prefix!r}")
        return 1

    if not args.data_root:
        log.error("缺少 --data-root")
        return 1
    data_root = Path(args.data_root)
    if not data_root.is_dir():
        log.error(f"数据目录不存在: {data_root}")
        return 1

    if args.only:
        indices = list(args.only)
        for idx in indices:
            if idx not in INDEX_SPECS:
                log.error(f"未知索引: {idx}")
                return 1
    else:
        indices = list(INDEX_SPECS.keys())

    # 预检全部目标名（任何写之前）
    for idx in indices:
        try:
            tgt = target_index_name(idx, args.index_prefix, args.index_suffix or "")
            assert_safe_target(tgt)
        except (ValueError, SystemExit) as e:
            log.error(str(e))
            return 1

    expect, expect_source = load_manifest_expect(data_root)
    for idx in indices:
        if idx not in expect:
            expect[idx] = INDEX_SPECS[idx]["expect"]

    if expect_source:
        log.info(f"期望文档数来源: MANIFEST.json → {expect_source}")
    else:
        log.info("期望文档数来源: 内置默认（INDEX_SPECS.expect）")

    if args.dry_run or args.offline:
        if expect_source is None:
            log.info("offline/dry-run 允许回退到内置默认；已在上方标明来源。")
        return offline_plan(
            data_root,
            indices,
            expect,
            args.index_prefix,
            args.index_suffix or "",
            log,
        )

    # 真实导入：找不到 MANIFEST.json 即中止（不静默回退）
    if expect_source is None:
        log.error(
            "中止：真实导入要求找到 MANIFEST.json（已搜索 data-root 上级等路径），"
            "不得回退到内置默认。未尝试连接 ES。"
        )
        return 3

    if not password:
        log.error("环境变量 QA4_ES_PASSWORD 未设置或为空")
        return 1

    es = make_client(args.es_url, args.user, password)
    # 连接后先 GET / 校验 cluster_name，再做任何写
    try:
        if not es.ping():
            log.error("无法连接 ES（ping 失败）。请检查 --es-url / QA4_ES_PASSWORD。")
            return 1
        ver = check_es_version(es)
        cname = assert_cluster_name(es)
        log.info(f"ES version {ver} cluster_name={cname} @ {args.es_url}")
    except SystemExit as e:
        log.error(str(e))
        return 1

    rows = []
    for idx in indices:
        ok, file_n, es_n = import_one(
            es,
            idx,
            data_root,
            force=args.force,
            index_prefix=args.index_prefix,
            index_suffix=args.index_suffix or "",
            expect=expect,
            log=log,
        )
        rows.append((idx, file_n, es_n, ok))
        if not ok:
            log.error(f"索引导入失败，停止后续：{idx}")
            log.info("\n=== 文档数对照（部分）===")
            for i2, f2, e2, o2 in rows:
                log.info(f"{i2:28} pack={f2} es={e2} ok={o2}")
            return 1

    log.info("\n=== 文档数对照 ===")
    log.info(f"{'index':28} {'pack':>10} {'es':>10} {'ok':>6}")
    for idx, file_n, es_n, ok in rows:
        log.info(f"{idx:28} {file_n:10d} {es_n:10d} {str(ok):>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
