# -*- coding: utf-8 -*-
"""在线只读：源 jsonl/json chunk_id 集合 vs ES（scroll 只取 chunk_id）。

缺 QA4_ES_PASSWORD 时跳过，不匿名请求。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\stage2")
DEFAULT_INDICES = "text_life,text_cwwl,text_cwwn,text_others,map_note"

# 依据 qa4/data_prep/es_import.py INDEX_SPECS[*].id_field / mapping 的 text 字段
SOURCE_ID_FIELD: dict[str, str] = {
    "text_life": "chunk_id",
    "text_cwwl": "chunk_id",
    "text_cwwn": "chunk_id",
    "text_others": "chunk_id",
    "map_note": "chunk_id",
    "outline_12490": "chunk_id",
    "outline_feasts": "chunk_id",
    "bible": "chunk_id",
    "hymns": "chunk_id",
}
SOURCE_TEXT_FIELD: dict[str, str] = {
    "text_life": "text",
    "text_cwwl": "text",
    "text_cwwn": "text",
    "text_others": "text",
    "map_note": "text",
    "outline_12490": "text",
    "outline_feasts": "text",
    "bible": "text",
    "hymns": "text",
}

PROBE_INDICES = [
    ("outline_12490", "panai4_outline_12490"),
    ("outline_feasts", "panai4_outline_feasts"),
    ("bible", "panai4_bible"),
    ("hymns", "panai4_hymns"),
]


def _env(*names: str) -> list[str]:
    return [n for n in names if not (os.environ.get(n) or "").strip()]


def resolve_source_root(arg: Optional[Path]) -> Optional[Path]:
    if arg and Path(arg).is_dir():
        p = Path(arg)
        if (p / "panai4_text_life").is_dir() or (p / "panai4_bible").is_dir():
            return p
        if (p / "es" / "data").is_dir():
            return p / "es" / "data"
        return p
    env = (os.environ.get("QA4_SOURCE_ROOT") or "").strip()
    if env:
        return resolve_source_root(Path(env))
    cand = _BACKEND.parent / "data" / "es_src"
    return cand if cand.is_dir() else None


def jsonl_paths(root: Path, source_name: str) -> list[Path]:
    d = root / source_name
    if not d.exists():
        return []
    if (d / "shards").is_dir():
        return sorted((d / "shards").glob("*.jsonl"))
    files = list(d.glob("*.jsonl")) + list(d.glob("*.json"))
    nested = list(d.glob("**/*.jsonl")) + list(d.glob("**/*_vec.json")) + list(d.glob("**/chunks_*.json"))
    return sorted(set(files + nested))


def paths_stats(paths: list[Path]) -> dict[str, Any]:
    total = sum(p.stat().st_size for p in paths if p.is_file())
    return {
        "files": [str(p) for p in paths],
        "file_n": len(paths),
        "total_bytes": total,
    }


_ASCII_WS = b" \t\r\n"


def _strip_utf8_bom(data: bytes) -> bytes:
    return data[3:] if data.startswith(b"\xef\xbb\xbf") else data


def _first_non_ws_byte(data: bytes) -> int:
    """只跳过 ASCII 空白（空格/TAB/CR/LF），不把 U+2028 等当空白。"""
    data = _strip_utf8_bom(data)
    i = 0
    while i < len(data) and data[i : i + 1] in (b" ", b"\t", b"\r", b"\n"):
        i += 1
    return data[i] if i < len(data) else -1


def iter_json_rows(
    paths: Iterable[Path],
    *,
    bad_lines: Optional[list[dict[str, Any]]] = None,
) -> Iterator[dict[str, Any]]:
    """自动识别 JSON 数组 / JSON Lines；坏行记录后继续。

    JSONL 只按 b\"\\n\"（并去掉行尾 b\"\\r\"）切分：二进制读入再逐行 utf-8 解码。
    不得使用 str.splitlines()（会切开 U+2028/U+2029 等）。
    """
    for p in paths:
        p = Path(p)
        data = p.read_bytes()
        if not _strip_utf8_bom(data).strip(_ASCII_WS):
            continue
        head = _first_non_ws_byte(data)
        suffix = p.suffix.lower()
        is_json_ext = suffix == ".json" and not p.name.endswith(".jsonl")
        treat_as_array = head == 0x5B  # '['
        treat_as_json_obj = is_json_ext and head == 0x7B  # '{'

        if treat_as_array or treat_as_json_obj:
            try:
                raw = _strip_utf8_bom(data).decode("utf-8")
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                if "Extra data" in str(e) or getattr(e, "msg", "") == "Extra data":
                    yield from _iter_jsonl_bytes(data, p, bad_lines)
                    continue
                if bad_lines is not None:
                    bad_lines.append(
                        {"file": str(p), "line": None, "error": type(e).__name__, "msg": str(e)[:120]}
                    )
                continue
            except UnicodeDecodeError as e:
                if bad_lines is not None:
                    bad_lines.append(
                        {"file": str(p), "line": None, "error": type(e).__name__, "msg": str(e)[:120]}
                    )
                continue
            if isinstance(parsed, list):
                for row in parsed:
                    if isinstance(row, dict):
                        yield row
                continue
            if isinstance(parsed, dict) and "chunks" in parsed and isinstance(parsed["chunks"], list):
                for row in parsed["chunks"]:
                    if isinstance(row, dict):
                        yield row
                continue
            if isinstance(parsed, dict):
                yield parsed
                continue

        # JSON Lines（含 .jsonl，或以非 [ 开头）
        yield from _iter_jsonl_bytes(data, p, bad_lines)


def _iter_jsonl_bytes(
    data: bytes,
    path: Path,
    bad_lines: Optional[list[dict[str, Any]]],
) -> Iterator[dict[str, Any]]:
    """按 b'\\n' 切分；容忍行尾 b'\\r'；逐行 utf-8 解码。"""
    data = _strip_utf8_bom(data)
    parts = data.split(b"\n")
    for i, part in enumerate(parts, start=1):
        if part.endswith(b"\r"):
            part = part[:-1]
        if not part.strip(_ASCII_WS):
            continue
        try:
            s = part.decode("utf-8").strip()
        except UnicodeDecodeError as e:
            if bad_lines is not None:
                bad_lines.append(
                    {"file": str(path), "line": i, "error": type(e).__name__, "msg": str(e)[:120]}
                )
            continue
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            if bad_lines is not None:
                bad_lines.append(
                    {"file": str(path), "line": i, "error": type(e).__name__, "msg": str(e)[:120]}
                )
            continue
        if isinstance(obj, dict):
            yield obj


def text_hash(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", "", text or "").encode("utf-8")).hexdigest()


def volume_of(logical: str, cid: str, book_title: str = "") -> str:
    if logical == "text_cwwl" and cid.startswith("cwwl_"):
        body = cid[5:].split("#", 1)[0]
        parts = body.split("-")
        if parts and parts[0].isdigit() and len(parts[0]) == 4:
            if len(parts) >= 2 and parts[1].isdigit() and len(parts[1]) == 4:
                return "cwwl_" + "-".join(parts[:3]) if len(parts) >= 3 else "cwwl_" + "-".join(parts[:2])
            return "cwwl_" + "-".join(parts[:2])
        return "cwwl_" + body
    if logical == "text_life" and cid.startswith("life_"):
        parts = cid.split("-")
        return "-".join(parts[:2]) if len(parts) >= 2 else cid
    if book_title:
        return book_title
    if "#" in cid:
        return cid.split("#", 1)[0]
    if "-" in cid:
        return cid.rsplit("-", 1)[0]
    return cid or "_empty"


def load_source(
    paths: list[Path],
    logical: str,
    *,
    bad_lines: Optional[list[dict[str, Any]]] = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """返回 id→hash，id→volume。"""
    id_field = SOURCE_ID_FIELD.get(logical, "chunk_id")
    text_field = SOURCE_TEXT_FIELD.get(logical, "text")
    id_hash: dict[str, str] = {}
    id_vol: dict[str, str] = {}
    for row in iter_json_rows(paths, bad_lines=bad_lines):
        cid = str(row.get(id_field) or "")
        if not cid and id_field != "chunk_id":
            cid = str(row.get("chunk_id") or "")
        if not cid:
            continue
        id_hash[cid] = text_hash(str(row.get(text_field) or ""))
        id_vol[cid] = volume_of(logical, cid, str(row.get("book_title") or ""))
    return id_hash, id_vol


def scroll_es_ids(es, index: str, id_field: str = "chunk_id") -> set[str]:
    out: set[str] = set()
    body = {"size": 5000, "query": {"match_all": {}}, "_source": [id_field], "sort": ["_doc"]}
    resp = es.search(index, body, scroll="2m")
    sid = resp.get("_scroll_id")
    while True:
        hits = resp["hits"]["hits"]
        if not hits:
            break
        for h in hits:
            src = h.get("_source") or {}
            cid = src.get(id_field) or h.get("_id")
            if cid:
                out.add(str(cid))
        if not sid or not hasattr(es, "scroll"):
            break
        resp = es.scroll(scroll_id=sid, scroll="2m")
        sid = resp.get("_scroll_id") or sid
    if sid and hasattr(es, "clear_scroll"):
        es.clear_scroll(scroll_id=sid)
    return out


def compare_one(
    logical: str,
    source_name: str,
    paths: list[Path],
    es,
    actual_index: str,
) -> dict[str, Any]:
    bad_lines: list[dict[str, Any]] = []
    id_hash, id_vol = load_source(paths, logical, bad_lines=bad_lines)
    src_ids = set(id_hash)
    id_field = SOURCE_ID_FIELD.get(logical, "chunk_id")
    es_ids = scroll_es_ids(es, actual_index, id_field)
    missing = sorted(src_ids - es_ids)
    extra = sorted(es_ids - src_ids)

    es_hashes = {id_hash[i] for i in es_ids if i in id_hash}
    dup_type = []
    unique_type = []
    for cid in missing:
        h = id_hash.get(cid, "")
        if h and h in es_hashes:
            dup_type.append(cid)
        else:
            unique_type.append(cid)

    by_vol: dict[str, dict[str, Any]] = {}
    for cid in src_ids:
        vol = id_vol.get(cid, "_")
        slot = by_vol.setdefault(vol, {"source_n": 0, "es_n": 0, "missing": []})
        slot["source_n"] += 1
        if cid in es_ids:
            slot["es_n"] += 1
        else:
            slot["missing"].append(cid)

    vol_rows = []
    for vol, s in by_vol.items():
        miss_n = len(s["missing"])
        src_n = s["source_n"]
        rate = (miss_n / src_n) if src_n else 0.0
        vol_rows.append(
            {
                "volume": vol,
                "source_n": src_n,
                "es_n": s["es_n"],
                "missing_n": miss_n,
                "missing_rate": round(rate, 4),
                "missing_chunk_ids": sorted(s["missing"])[:50],
                "missing_chunk_ids_omitted": max(0, miss_n - 50),
            }
        )
    vol_rows.sort(key=lambda r: (-r["missing_rate"], -r["missing_n"], r["volume"]))

    return {
        "logical": logical,
        "source_name": source_name,
        "es_index": actual_index,
        "id_field": id_field,
        "text_field": SOURCE_TEXT_FIELD.get(logical, "text"),
        "source_n": len(src_ids),
        "es_n": len(es_ids),
        "missing_n": len(missing),
        "extra_n": len(extra),
        "missing_dup_content_n": len(dup_type),
        "missing_unique_content_n": len(unique_type),
        "extra_chunk_ids_sample": extra[:50],
        "volumes_top_missing": vol_rows[:30],
        "bad_source_lines": bad_lines[:50],
        "bad_source_lines_n": len(bad_lines),
        "pass": len(missing) == 0 and len(extra) == 0,
        "failed": False,
    }


def write_md(report: dict[str, Any], path: Path) -> None:
    lines = ["# 源 vs ES 全量比对汇总", "", f"时间：{report.get('started_at')}", ""]
    for ix, info in (report.get("indices") or {}).items():
        if info.get("skipped"):
            lines.append(f"## {ix}：跳过 — {info.get('reason')}")
            lines.append("")
            continue
        if info.get("failed"):
            lines.append(f"## {ix}：失败 — {info.get('error_type')}: {info.get('error')}")
            lines.append("")
            continue
        lines.append(f"## {ix}")
        lines.append(
            f"- source_n={info['source_n']} es_n={info['es_n']} "
            f"missing={info['missing_n']} extra={info['extra_n']} "
            f"缺且内容重复型={info['missing_dup_content_n']} 缺且独有型={info['missing_unique_content_n']} "
            f"PASS={info.get('pass')}"
        )
        lines.append("")
        lines.append("| 册/前缀 | 源 | ES | 缺失 | 缺失率 |")
        lines.append("|---|---:|---:|---:|---:|")
        for r in info.get("volumes_top_missing") or []:
            if r["missing_n"] <= 0:
                continue
            lines.append(
                f"| {r['volume']} | {r['source_n']} | {r['es_n']} | {r['missing_n']} | {r['missing_rate']} |"
            )
        lines.append("")
    if report.get("not_compared"):
        lines.append("## 未比对：缺源")
        for x in report["not_compared"]:
            lines.append(f"- {x.get('logical')}: {x.get('reason')}")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _finalize_tops(report: dict[str, Any]) -> None:
    tops = []
    for lg, info in (report.get("indices") or {}).items():
        if info.get("skipped") or info.get("failed"):
            continue
        for r in info.get("volumes_top_missing") or []:
            if r["missing_n"] > 0:
                tops.append({"logical": lg, **r})
    tops.sort(key=lambda r: (-r["missing_rate"], -r["missing_n"]))
    report["top3_missing_volumes"] = [
        {
            "logical": t["logical"],
            "volume": t["volume"],
            "source_n": t["source_n"],
            "es_n": t["es_n"],
            "missing_n": t["missing_n"],
            "missing_rate": t["missing_rate"],
        }
        for t in tops[:3]
    ]


def _write_json(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _index_done(info: dict[str, Any]) -> bool:
    """仅真正比对成功才可被 --resume-from 复用。

    failed / skipped 一律视为未完成，续跑时重跑。
    """
    if not isinstance(info, dict):
        return False
    if info.get("skipped") or info.get("failed"):
        return False
    return "source_n" in info and "es_n" in info


def collect_resume_indices(
    prev_indices: dict[str, Any],
    *,
    rerun: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """从 resume JSON 的 indices 中只挑可复用（成功）的项；rerun 中的逻辑名强制排除。"""
    force = {str(s).strip() for s in (rerun or []) if str(s).strip()}
    out: dict[str, Any] = {}
    for lg, info in (prev_indices or {}).items():
        if lg in force:
            continue
        if _index_done(info):
            out[lg] = info
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--indices", default=DEFAULT_INDICES)
    ap.add_argument(
        "--resume-from",
        type=Path,
        default=None,
        help="已有 check_source_vs_es JSON；已完成索引直接复用，只补跑未完成的",
    )
    ap.add_argument(
        "--rerun",
        default="",
        help="逗号分隔逻辑名；与 --resume-from 配合，即使已成功也强制重算",
    )
    args = ap.parse_args(argv)

    miss = _env("QA4_ES_URL", "QA4_ES_PASSWORD")
    if miss:
        print(f"跳过：缺少 {', '.join(miss)}")
        return 0

    root = resolve_source_root(args.source_root)
    if root is None:
        print("跳过：找不到源根目录（--source-root / QA4_SOURCE_ROOT）")
        return 1

    from config import get_settings
    from core.es_client import EsClient
    from core.ready import redact_secrets
    from retrieval.config import actual_index

    settings = get_settings(require_runtime=False)
    es = EsClient(settings.es_url, settings.es_user, settings.es_secret, verify=settings.es_verify, index_map=settings.index_map)

    wanted = [s.strip() for s in args.indices.split(",") if s.strip()]
    report: dict[str, Any] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(root),
        "indices": {},
        "not_compared": [],
    }

    rerun_set = {s.strip() for s in (args.rerun or "").split(",") if s.strip()}
    if args.resume_from and Path(args.resume_from).is_file():
        prev = json.loads(Path(args.resume_from).read_text(encoding="utf-8"))
        report["indices"] = collect_resume_indices(prev.get("indices") or {}, rerun=rerun_set)
        print(
            f"resume-from={args.resume_from} 已复用 {len(report['indices'])} 个索引"
            f"（仅成功比对；failed/skipped 将重跑"
            + (f"；--rerun 强制重算 {sorted(rerun_set)}" if rerun_set else "")
            + "）"
        )
    elif rerun_set:
        print(f"提示：--rerun={sorted(rerun_set)} 未搭配 --resume-from，将按 --indices 正常比对")

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = args.out / f"check_source_vs_es_{stamp}.json"
    out_md = args.out / f"check_source_vs_es_{stamp}.md"

    def run_one(lg: str, src_name: str, *, auto: bool = False) -> None:
        if lg in report["indices"] and _index_done(report["indices"][lg]):
            print(f"{lg}: 跳过（resume 已有结果）")
            return
        paths = jsonl_paths(root, src_name)
        if not paths:
            if auto:
                report["not_compared"].append({"logical": lg, "reason": "缺源"})
                print(f"{lg}: 未比对（缺源）")
            else:
                report["indices"][lg] = {"skipped": True, "reason": "缺源"}
                print(f"{lg}: 跳过（缺源）")
            _finalize_tops(report)
            _write_json(report, out_json)
            return
        st = paths_stats(paths)
        print(
            f"{lg}: 源 path_n={st['file_n']} total_bytes={st['total_bytes']} "
            f"files={st['files'][:3]}{'…' if st['file_n'] > 3 else ''}"
        )
        try:
            print(f"{lg}: 比对中…")
            info = compare_one(lg, src_name, paths, es, actual_index(lg))
            report["indices"][lg] = info
            print(
                f"  source={info['source_n']} es={info['es_n']} missing={info['missing_n']} "
                f"extra={info['extra_n']} dup_miss={info['missing_dup_content_n']} "
                f"uniq_miss={info['missing_unique_content_n']} bad_lines={info['bad_source_lines_n']}"
            )
        except Exception as e:
            msg = redact_secrets(f"{type(e).__name__}: {e}")[:300]
            print(f"{lg}: 失败 — {msg}")
            report["indices"][lg] = {
                "logical": lg,
                "source_name": src_name,
                "failed": True,
                "error_type": type(e).__name__,
                "error": msg,
                "pass": False,
            }
        _finalize_tops(report)
        _write_json(report, out_json)

    for lg in wanted:
        run_one(lg, f"panai4_{lg}", auto=False)

    for lg, src_name in PROBE_INDICES:
        if lg in report["indices"]:
            continue
        # 已在 wanted 里且缺源也会占位；探测只处理尚未出现的
        paths = jsonl_paths(root, src_name)
        if not paths:
            report["not_compared"].append({"logical": lg, "reason": "缺源"})
            st_msg = f"{lg}: 自动探测 — 缺源"
            print(st_msg)
            continue
        st = paths_stats(paths)
        print(
            f"{lg}: 自动探测到源 path_n={st['file_n']} total_bytes={st['total_bytes']} "
            f"files={st['files'][:3]}{'…' if st['file_n'] > 3 else ''}"
        )
        run_one(lg, src_name, auto=True)

    # 去重 not_compared
    seen = set()
    uniq = []
    for x in report["not_compared"]:
        k = x.get("logical")
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)
    report["not_compared"] = uniq

    if report["not_compared"]:
        print("未比对：缺源 → " + ", ".join(x["logical"] for x in report["not_compared"]))

    _finalize_tops(report)
    print("缺失率最高前 3 册：", json.dumps(report.get("top3_missing_volumes") or [], ensure_ascii=False))
    _write_json(report, out_json)
    write_md(report, out_md)
    print(f"OUT_JSON={out_json}")
    print(f"OUT_MD={out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
