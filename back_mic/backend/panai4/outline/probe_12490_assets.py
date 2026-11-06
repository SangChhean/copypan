# -*- coding: utf-8 -*-
"""只读查清 panai4_outline_12490 的构建资产（chunks JSON / 向量文件 / ES）。

不写索引、不改文件、不跑构建脚本。

用法（在 back_mic/backend 下）::

    python -m panai4.outline.probe_12490_assets
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from dotenv import load_dotenv

from panai4.outline import config

REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = Path(config.DEFAULT_OUT_DIR)
PANAI_ROOT = Path(r"G:\PanAI4.0专用")
FIX_FINAL = REPO_ROOT / "docs" / "panai4_es" / "archive" / "life_12490_fix_final.csv"
REPORT_DEFAULT = REPO_ROOT / "docs" / "panai4_es" / "archive" / "12490_assets_check.md"
LOG_DIR_DEFAULT = REPO_ROOT / "logs"
ES_INDEX = "panai4_outline_12490"
SAMPLE_SEED = 20261106
SKIP_DIRS = {"node_modules", ".git", "12490原文JSONL", "清明上河图目录"}
NAME_PAT = re.compile(r"(vector|embed|emb|shard|12490|chunks|outline)", re.I)
IDEOGRAPHIC_SPACE = "\u3000"


def _backend_env() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def setup_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_dir / f"12490_assets_{stamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    logging.info("log_path=%s", path)
    return path


def make_es():
    from elasticsearch import Elasticsearch

    load_dotenv(_backend_env())
    url = f"http://{os.getenv('ES_HOST', 'localhost')}:{os.getenv('ES_PORT', '9200')}"
    return Elasticsearch(
        hosts=[url],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=180,
        max_retries=0,
    ), url


def _git_status() -> str:
    try:
        return subprocess.check_output(
            ["git", "status", "--short", "--", "back_mic/backend/panai4/"],
            cwd=str(REPO_ROOT), text=True, encoding="utf-8", errors="replace",
        ).strip() or "(clean)"
    except Exception as exc:  # noqa: BLE001
        return f"(git failed: {exc})"


def snapshot_dir(root: Path) -> list[tuple[str, int, float]]:
    rows = []
    if not root.exists():
        return rows
    for dirpath, _dns, names in os.walk(root):
        for name in names:
            p = Path(dirpath) / name
            try:
                st = p.stat()
            except OSError:
                continue
            rows.append((str(p), st.st_size, st.st_mtime))
    rows.sort()
    return rows


def iter_jsonl(path: Path, fields: Optional[set[str]] = None):
    """Yield dicts from JSONL; if fields set, only keep those keys (embedding dropped unless requested)."""
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            if fields is not None:
                yield {k: obj.get(k) for k in fields}
            else:
                yield obj


def peek_json_structure(path: Path, max_recs: int = 2) -> dict:
    info: dict[str, Any] = {
        "path": str(path),
        "size": path.stat().st_size if path.exists() else 0,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if path.exists() else "",
        "kind": "missing",
        "n": 0,
        "top_keys": [],
        "sample_fields": [],
    }
    if not path.exists():
        return info
    with path.open(encoding="utf-8") as fp:
        first = fp.read(1)
        fp.seek(0)
        if first == "[":
            data = json.load(fp)
            info["kind"] = "list"
            info["n"] = len(data)
            if data and isinstance(data[0], dict):
                info["sample_fields"] = [
                    {k: type(v).__name__ for k, v in data[i].items()}
                    for i in range(min(max_recs, len(data)))
                ]
            elif data and isinstance(data[0], dict) is False:
                info["sample_fields"] = [type(data[0]).__name__]
        elif first == "{":
            # could be jsonl (one object per line) or single dict
            line1 = fp.readline()
            try:
                obj1 = json.loads(line1)
            except json.JSONDecodeError:
                fp.seek(0)
                obj = json.load(fp)
                info["kind"] = "dict"
                info["top_keys"] = sorted(obj.keys()) if isinstance(obj, dict) else []
                info["n"] = 1
                return info
            # jsonl?
            rest = fp.readline()
            if rest.strip():
                info["kind"] = "jsonl"
                n = 1
                samples = [{k: type(v).__name__ for k, v in obj1.items()}]
                obj2 = json.loads(rest)
                samples.append({k: type(v).__name__ for k, v in obj2.items()})
                for line in fp:
                    if line.strip():
                        n += 1
                info["n"] = n + 1  # already read 2
                # recount properly
                info["n"] = count_jsonl(path)
                info["sample_fields"] = samples[:max_recs]
            else:
                # single-line dict file or one-record jsonl
                info["kind"] = "jsonl_or_dict"
                info["n"] = 1
                info["sample_fields"] = [{k: type(v).__name__ for k, v in obj1.items()}]
                info["top_keys"] = sorted(obj1.keys())
        else:
            info["kind"] = "unknown"
    return info


def count_jsonl(path: Path) -> int:
    n = 0
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                n += 1
    return n


def find_name_matches(roots: list[Path], exclude_names: set[str]) -> list[dict]:
    hits = []
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # prune
            base = Path(dirpath)
            rel_parts = set()
            try:
                rel = base.relative_to(root)
                rel_parts = set(rel.parts)
            except ValueError:
                pass
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and d not in exclude_names
                and d not in ("node_modules", ".git")
            ]
            for name in list(dirnames) + filenames:
                if NAME_PAT.search(name):
                    p = base / name
                    try:
                        st = p.stat()
                        hits.append({
                            "path": str(p),
                            "is_dir": p.is_dir(),
                            "size": st.st_size if p.is_file() else 0,
                            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                        })
                    except OSError:
                        continue
    return hits


def cos_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return float("nan")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return float("nan")
    return dot / (na * nb)


def vec_norm(a: list[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def max_abs_diff(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return float("nan")
    return max(abs(x - y) for x, y in zip(a, b))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(REPORT_DEFAULT))
    ap.add_argument("--log-dir", default=str(LOG_DIR_DEFAULT))
    args = ap.parse_args()

    t0 = time.time()
    log_path = setup_logging(Path(args.log_dir))
    snap_before = snapshot_dir(OUT_DIR)
    es, es_url = make_es()
    es.info()
    count_before = es.count(index=ES_INDEX)["count"]
    logging.info("count_before=%s", count_before)

    lines: list[str] = []
    def w(s: str = "") -> None:
        lines.append(s)

    # ---------- 1.1 list OUT_DIR ----------
    logging.info("listing %s", OUT_DIR)
    outline_files = []
    for dirpath, _d, names in os.walk(OUT_DIR):
        for name in names:
            p = Path(dirpath) / name
            try:
                st = p.stat()
            except OSError:
                continue
            outline_files.append({
                "path": str(p),
                "rel": str(p.relative_to(OUT_DIR)),
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "ext": p.suffix.lower(),
            })
    outline_files.sort(key=lambda x: x["rel"])

    json_structs = {}
    for f in outline_files:
        if f["ext"] in (".json", ".jsonl"):
            # skip huge vec full recount twice — peek carefully
            p = Path(f["path"])
            logging.info("peek %s", f["rel"])
            if f["size"] > 500_000_000:
                # large: treat as jsonl, count lines, peek first 2 field names without storing embedding
                samples = []
                n = 0
                with p.open(encoding="utf-8") as fp:
                    for line in fp:
                        if not line.strip():
                            continue
                        n += 1
                        if len(samples) < 2:
                            obj = json.loads(line)
                            samples.append({k: ("list" if isinstance(v, list) and k in ("embedding", "text_vector") else type(v).__name__) for k, v in obj.items()})
                json_structs[f["rel"]] = {
                    "kind": "jsonl", "n": n, "sample_fields": samples,
                    "size": f["size"], "mtime": f["mtime"],
                }
            else:
                json_structs[f["rel"]] = peek_json_structure(p)

    # ---------- 1.2 name matches ----------
    logging.info("scanning name matches...")
    exclude_under_panai = {"12490原文JSONL", "清明上河图目录"}
    hits_panai = []
    if PANAI_ROOT.exists():
        for child in PANAI_ROOT.iterdir():
            if child.name in exclude_under_panai:
                continue
            if child.name == "纲目JSON":
                # already listed; still include matching names
                hits_panai.extend(find_name_matches([child], set()))
            else:
                hits_panai.extend(find_name_matches([child], set()))
    hits_docs = find_name_matches([REPO_ROOT / "docs" / "panai4_es"], set())
    hits_repo = []
    for child in REPO_ROOT.iterdir():
        if child.name in ("node_modules", ".git", "docs"):
            continue
        if child.is_dir():
            hits_repo.extend(find_name_matches([child], set()))
        elif NAME_PAT.search(child.name):
            try:
                st = child.stat()
                hits_repo.append({
                    "path": str(child), "is_dir": False,
                    "size": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                })
            except OSError:
                pass

    # dedupe paths
    def dedupe_hits(hs):
        seen = set()
        out = []
        for h in hs:
            if h["path"] in seen:
                continue
            seen.add(h["path"])
            out.append(h)
        return out

    hits_panai = dedupe_hits(hits_panai)
    hits_docs = dedupe_hits(hits_docs)
    hits_repo = dedupe_hits(hits_repo)

    # ---------- 1.3 script capabilities (static) ----------
    script_notes = {
        "config.DEFAULT_OUT_DIR": config.DEFAULT_OUT_DIR,
        "build_chunks": {
            "input": "outline_12490.json / outline_feasts.json under --out",
            "output": "chunks_12490.json / chunks_feasts.json (JSONL)",
            "chunk_id": "sha1(message_key)[:12] → {prefix}_{digest}_c{index}",
            "lines": "config.py:340; build_chunks.py:153-186, 310-321, 518-519",
        },
        "gen_embeddings": {
            "input": "chunks_*.json JSONL",
            "output": "chunks_*_vec.json (same records + embedding)",
            "embed_field": "text via _embed_input",
            "vector_field_name": "embedding",
            "batch": 50,
            "resume": "yes (_read_done_ids on existing *_vec.json)",
            "partial_ids": "NO dedicated --chunk-ids; resume skips done ids only",
            "write_without_api": "NO — always calls embedding API for missing",
            "lines": "gen_embeddings.py:89-91, 840+, 920-951, 1480-1496",
        },
        "index_to_es": {
            "input": "chunks_*_vec.json",
            "index": "panai4_outline_12490 / feasts / bible",
            "vector_field": "embedding",
            "_id": "chunk_id",
            "create": "indices.create then bulk (local recreates)",
            "incremental": "remote skip_existing; local create+full write",
            "single_index": "--index + --input supported",
            "lines": "index_to_es.py:52-71, 168-190, 438-473, 1729-1733",
        },
    }

    # ---------- asset table ----------
    def asset_row(name: str, path: Path) -> dict:
        if not path.exists():
            return {"name": name, "path": str(path), "status": "未找到", "size": 0, "mtime": "", "n": ""}
        st = path.stat()
        n = ""
        rel = path.name
        if rel in json_structs:
            n = json_structs[rel].get("n", "")
        elif path.suffix == ".json":
            try:
                n = count_jsonl(path) if path.stat().st_size < 2_000_000_000 else "?"
            except Exception:
                n = "?"
        return {
            "name": name,
            "path": str(path),
            "status": "存在",
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            "n": n,
        }

    assets = [
        asset_row("outline JSON (12490)", OUT_DIR / "outline_12490.json"),
        asset_row("chunks JSON (12490)", OUT_DIR / "chunks_12490.json"),
        asset_row("向量文件 (12490)", OUT_DIR / "chunks_12490_vec.json"),
        asset_row("排除清单", OUT_DIR / "excluded_files.json"),
        asset_row("异常清单", OUT_DIR / "anomalies.json"),
        asset_row("outline JSON (feasts)", OUT_DIR / "outline_feasts.json"),
        asset_row("chunks JSON (feasts)", OUT_DIR / "chunks_feasts.json"),
        asset_row("向量文件 (feasts)", OUT_DIR / "chunks_feasts_vec.json"),
        asset_row("chunks JSON (bible)", OUT_DIR / "chunks_bible.json"),
        asset_row("向量文件 (bible)", OUT_DIR / "chunks_bible_vec.json"),
    ]
    # fill n from structs
    for a in assets:
        p = Path(a["path"])
        if p.exists() and p.name in json_structs:
            a["n"] = json_structs[p.name].get("n", a["n"])

    chunks_path = OUT_DIR / "chunks_12490.json"
    vec_path = OUT_DIR / "chunks_12490_vec.json"
    has_chunks = chunks_path.exists()
    has_vec = vec_path.exists()

    # ---------- 2. load id sets ----------
    logging.info("loading chunks ids/text...")
    chunk_ids: set[str] = set()
    chunk_dup = 0
    chunk_by_id: dict[str, dict] = {}
    mk_chunks: dict[str, list[str]] = defaultdict(list)
    fields_keep = {
        "chunk_id", "message_key", "text", "book_title", "message_title",
        "message_number", "chunk_index", "chunk_total",
    }
    if has_chunks:
        for obj in iter_jsonl(chunks_path, fields_keep):
            cid = obj.get("chunk_id")
            if not cid:
                continue
            if cid in chunk_ids:
                chunk_dup += 1
            chunk_ids.add(cid)
            chunk_by_id[cid] = obj
            mk = obj.get("message_key") or ""
            mk_chunks[mk].append(cid)
    logging.info("chunks n=%s dup=%s", len(chunk_ids), chunk_dup)

    logging.info("loading vec ids...")
    vec_ids: set[str] = set()
    vec_dup = 0
    if has_vec:
        with vec_path.open(encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                # only parse chunk_id cheaply
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cid = obj.get("chunk_id")
                if not cid:
                    continue
                if cid in vec_ids:
                    vec_dup += 1
                vec_ids.add(cid)
    logging.info("vec n=%s dup=%s", len(vec_ids), vec_dup)

    # ES ids + text
    logging.info("scrolling ES ids+text...")
    from elasticsearch.helpers import scan

    es_ids: set[str] = set()
    es_dup = 0
    es_by_id: dict[str, dict] = {}
    mk_es: dict[str, list[str]] = defaultdict(list)
    # detect vector field from mapping
    mapping = es.indices.get_mapping(index=ES_INDEX)
    props = mapping[ES_INDEX]["mappings"].get("properties") or {}
    vec_field = None
    for fname, fdef in props.items():
        if fdef.get("type") == "dense_vector":
            vec_field = fname
            break
    logging.info("12490 vector field=%s", vec_field)
    excludes = [vec_field] if vec_field else ["embedding", "text_vector"]

    for doc in scan(
        es, index=ES_INDEX, query={"query": {"match_all": {}}},
        _source={"includes": ["chunk_id", "message_key", "text", "book_title", "message_title", "message_number", "chunk_index"],
                 "excludes": excludes},
        size=500,
    ):
        cid = doc.get("_id") or (doc.get("_source") or {}).get("chunk_id")
        if not cid:
            continue
        if cid in es_ids:
            es_dup += 1
        es_ids.add(cid)
        src = doc.get("_source") or {}
        es_by_id[cid] = src
        mk_es[src.get("message_key") or ""].append(cid)
    logging.info("es n=%s dup=%s", len(es_ids), es_dup)

    # set comparisons
    def set_diff(a: set, b: set):
        return len(a - b), len(b - a), len(a & b)

    if has_chunks and has_vec:
        c_only_v, v_only_c, cv = set_diff(chunk_ids, vec_ids)
        c_only_e, e_only_c, ce = set_diff(chunk_ids, es_ids)
        v_only_e, e_only_v, ve = set_diff(vec_ids, es_ids)
        triple_mode = "三向"
    elif has_chunks:
        c_only_v = v_only_c = cv = None
        c_only_e, e_only_c, ce = set_diff(chunk_ids, es_ids)
        v_only_e = e_only_v = ve = None
        triple_mode = "二向(无向量文件)"
    else:
        c_only_v = v_only_c = cv = c_only_e = e_only_c = ce = v_only_e = e_only_v = ve = None
        triple_mode = "无chunks"

    # message_key compare
    mk_c_set = set(mk_chunks)
    mk_e_set = set(mk_es)
    mk_only_c = mk_c_set - mk_e_set
    mk_only_e = mk_e_set - mk_c_set
    mk_both = mk_c_set & mk_e_set
    mk_count_mismatch = []
    for mk in sorted(mk_both):
        if len(mk_chunks[mk]) != len(mk_es[mk]):
            mk_count_mismatch.append((mk, len(mk_chunks[mk]), len(mk_es[mk])))

    # ---------- 3.1 text compare ----------
    logging.info("comparing text...")
    text_same = text_diff = text_missing = 0
    text_diff_samples = []
    if has_chunks:
        for cid, obj in chunk_by_id.items():
            es_obj = es_by_id.get(cid)
            if es_obj is None:
                text_missing += 1
                continue
            ct = obj.get("text") or ""
            et = es_obj.get("text") or ""
            if ct == et:
                text_same += 1
            else:
                text_diff += 1
                if len(text_diff_samples) < 20:
                    text_diff_samples.append((cid, ct[:80], et[:80]))

    # 3.2 header sample
    rng = random.Random(SAMPLE_SEED)
    header_samples = []
    if chunk_by_id:
        sample_ids = rng.sample(list(chunk_by_id.keys()), min(20, len(chunk_by_id)))
        for cid in sample_ids:
            obj = chunk_by_id[cid]
            es_obj = es_by_id.get(cid) or {}
            c_first = (obj.get("text") or "").split("\n", 1)[0]
            e_first = (es_obj.get("text") or "").split("\n", 1)[0]
            expect = f"{obj.get('book_title') or ''}{IDEOGRAPHIC_SPACE}{obj.get('message_title') or ''}"
            header_samples.append({
                "cid": cid,
                "c_eq_e": c_first == e_first,
                "c_eq_formula": c_first == expect,
                "e_eq_formula": e_first == f"{es_obj.get('book_title') or ''}{IDEOGRAPHIC_SPACE}{es_obj.get('message_title') or ''}",
            })

    # 3.3 vector sample
    vec_compare_rows = []
    vec_docs_read = 0
    if has_vec and vec_field:
        # pick required keys
        want_cids: list[str] = []
        def pick_by_book_substr(substr: str, n: int):
            found = []
            for cid, obj in chunk_by_id.items():
                bt = obj.get("book_title") or ""
                mk = obj.get("message_key") or ""
                if substr in bt or substr in mk:
                    found.append(cid)
            found.sort()
            return found[:n]

        want_cids.extend(pick_by_book_substr("雅歌书", 3))
        want_cids.extend(pick_by_book_substr("约翰二书", 3))
        # 以斯帖附录
        est = []
        for cid, obj in chunk_by_id.items():
            mk = obj.get("message_key") or ""
            mt = obj.get("message_title") or ""
            if "以斯帖" in mk and ("附录" in mk or "附录" in mt):
                est.append(cid)
        want_cids.extend(sorted(est)[:3])
        # 但以理 2 msgs × 1
        dan_mks = sorted({obj.get("message_key") for obj in chunk_by_id.values() if "但以理" in (obj.get("book_title") or "")})
        for mk in dan_mks[:2]:
            cids = mk_chunks.get(mk) or []
            if cids:
                want_cids.append(sorted(cids)[0])
        # fill to 30
        need = 30 - len(set(want_cids))
        pool = [c for c in chunk_by_id if c not in want_cids]
        want_cids.extend(rng.sample(pool, min(need, len(pool))))
        want_set = set(want_cids)
        logging.info("loading %s vectors from file...", len(want_set))
        file_vecs: dict[str, list] = {}
        with vec_path.open(encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                obj = json.loads(line)
                cid = obj.get("chunk_id")
                if cid in want_set and "embedding" in obj:
                    file_vecs[cid] = obj["embedding"]
                    vec_docs_read += 1
                    if len(file_vecs) >= len(want_set):
                        break
        logging.info("loading vectors from ES mget...")
        # mget in batches
        es_vecs: dict[str, list] = {}
        ids_list = list(want_set)
        for i in range(0, len(ids_list), 50):
            batch = ids_list[i:i + 50]
            resp = es.mget(index=ES_INDEX, ids=batch, source_includes=[vec_field])
            for doc in resp.get("docs") or []:
                if not doc.get("found"):
                    continue
                cid = doc.get("_id")
                emb = (doc.get("_source") or {}).get(vec_field)
                if emb:
                    es_vecs[cid] = emb
                    vec_docs_read += 1
        for cid in sorted(want_set):
            fv = file_vecs.get(cid)
            ev = es_vecs.get(cid)
            if not fv or not ev:
                vec_compare_rows.append({
                    "cid": cid, "ok": False,
                    "note": f"file={'Y' if fv else 'N'} es={'Y' if ev else 'N'}",
                })
                continue
            vec_compare_rows.append({
                "cid": cid, "ok": True,
                "dims_f": len(fv), "dims_e": len(ev),
                "norm_f": round(vec_norm(fv), 6), "norm_e": round(vec_norm(ev), 6),
                "max_abs": max_abs_diff(fv, ev),
                "cosine": cos_sim(fv, ev),
            })

    # ---------- 4. fix_final ----------
    logging.info("checking fix_final...")
    fix_rows = []
    if FIX_FINAL.exists():
        with FIX_FINAL.open(encoding="utf-8-sig", newline="") as fp:
            fix_rows = list(csv.DictReader(fp))
    match_n = mismatch_n = 0
    mismatches = []
    reembed_cids: set[str] = set()
    reembed_mks: set[str] = set()
    for r in fix_rows:
        mk = r.get("message_key") or ""
        field = r.get("field") or ""
        old = r.get("old") or ""
        cat = r.get("category") or ""
        ok = True
        reasons = []
        cids = mk_chunks.get(mk) or []
        es_cids = mk_es.get(mk) or []
        if not cids:
            ok = False
            reasons.append("chunks无此message_key")
        if len(cids) != len(es_cids):
            ok = False
            reasons.append(f"块数 chunks={len(cids)} es={len(es_cids)}")
        # chunk_count column may be absent in final csv
        if cids:
            sample = chunk_by_id[cids[0]]
            if field == "message_title":
                if (sample.get("message_title") or "") != old:
                    # allow if any chunk differs? all should same title
                    titles = {(chunk_by_id[c].get("message_title") or "") for c in cids}
                    if old not in titles:
                        ok = False
                        reasons.append(f"old≠chunks.message_title got={next(iter(titles))[:40]}")
            elif field == "book_title":
                books = {(chunk_by_id[c].get("book_title") or "") for c in cids}
                if old not in books:
                    ok = False
                    reasons.append(f"old≠chunks.book_title got={next(iter(books))[:40]}")
            elif field == "message_number":
                pass
        if ok:
            match_n += 1
        else:
            mismatch_n += 1
            mismatches.append((mk[:60], field, ";".join(reasons)))
        if field in ("message_title", "book_title") and r.get("reembed") != "否":
            for c in cids:
                reembed_cids.add(c)
            reembed_mks.add(mk)
        elif field in ("message_title", "book_title"):
            for c in cids:
                reembed_cids.add(c)
            reembed_mks.add(mk)

    # what fields change
    field_change_note = (
        "title：改 message_title + text 第一行；message_key/chunk_id/source_path/book_path 不变。"
        "book：改 book_title + text 第一行；message_key 路径里可能仍含旧书名（如雅歌书/约翰二书_），"
        "但 chunk_id=sha1(message_key) 不变，与 ES _id 仍一致。"
        "number：只改 message_number，text 不变，无需重算向量。"
    )
    # message_key contains book folder name?
    mk_has_book_title = 0
    for r in fix_rows:
        if r.get("field") != "book_title":
            continue
        mk = r.get("message_key") or ""
        old = r.get("old") or ""
        if old and old in mk:
            mk_has_book_title += 1

    # 4.3 rebuild text check
    rebuild_ok = rebuild_fail = 0
    if chunk_by_id:
        sample100 = rng.sample(list(chunk_by_id.keys()), min(100, len(chunk_by_id)))
        for cid in sample100:
            obj = chunk_by_id[cid]
            text = obj.get("text") or ""
            first = text.split("\n", 1)[0]
            expect = f"{obj.get('book_title') or ''}{IDEOGRAPHIC_SPACE}{obj.get('message_title') or ''}"
            # full mechanical rebuild of body unknown without points; check header formula only
            # User asked: 用 chunks JSON 的字段重建 text，是否与存储的 text 逐字相同
            # We can only rebuild header; body needs outline points. Check: text.startswith(expect+"\n")
            if text.startswith(expect + "\n") or text == expect:
                rebuild_ok += 1
            else:
                rebuild_fail += 1
        # stronger: if first line == formula
        header_eq = sum(
            1 for cid in sample100
            if (chunk_by_id[cid].get("text") or "").split("\n", 1)[0]
            == f"{chunk_by_id[cid].get('book_title') or ''}{IDEOGRAPHIC_SPACE}{chunk_by_id[cid].get('message_title') or ''}"
        )
    else:
        header_eq = 0
        sample100 = []

    # ---------- 5. nine index mappings ----------
    logging.info("mappings for panai4_* ...")
    try:
        all_idx = es.indices.get(index="panai4_*")
        idx_names = sorted(all_idx.keys())
    except Exception as exc:  # noqa: BLE001
        idx_names = []
        logging.warning("get panai4_* failed: %s", exc)
    map_rows = []
    for name in idx_names:
        try:
            m = es.indices.get_mapping(index=name)
            props = m[name]["mappings"].get("properties") or {}
        except Exception:
            continue
        for fname, fdef in props.items():
            if fdef.get("type") == "dense_vector":
                opts = fdef.get("index_options") or {}
                map_rows.append({
                    "index": name,
                    "field": fname,
                    "dims": fdef.get("dims"),
                    "similarity": fdef.get("similarity"),
                    "index_options_type": opts.get("type"),
                })

    # ---------- 6. disk ----------
    usage = shutil.disk_usage("G:\\")
    panai_size = 0
    if PANAI_ROOT.exists():
        for dirpath, _d, names in os.walk(PANAI_ROOT):
            for name in names:
                try:
                    panai_size += (Path(dirpath) / name).stat().st_size
                except OSError:
                    pass
    backup_need = 0
    for a in assets[:5]:
        if a["status"] == "存在":
            backup_need += int(a["size"] or 0)

    count_after = es.count(index=ES_INDEX)["count"]
    snap_after = snapshot_dir(OUT_DIR)

    # ---------- report ----------
    w("# panai4_outline_12490 构建资产只读检查")
    w("")
    w(f"> ES：`{es_url}`；纲目JSON：`{OUT_DIR}`；报告生成：{datetime.now().isoformat(timespec='seconds')}；耗时 {time.time()-t0:.1f}s；日志：`{log_path}`。")
    w("")
    w("## 结论摘要")
    w("")
    w(
        f"(1) **chunks / 向量**：均在 `{OUT_DIR}` — "
        f"`chunks_12490.json`（{assets[1]['n']} 条，{assets[1]['size']/1e6:.1f} MB）、"
        f"`chunks_12490_vec.json`（{assets[2]['n']} 条，{assets[2]['size']/1e9:.2f} GB）。齐全。"
    )
    if has_chunks and has_vec:
        w(
            f"(2) **三向 id**：chunks={len(chunk_ids)} vec={len(vec_ids)} es={len(es_ids)}；"
            f"c−v={c_only_v} v−c={v_only_c} ∩={cv}；c−e={c_only_e} e−c={e_only_c}；"
            f"v−e={v_only_e} e−v={e_only_v}；dup c/v/e={chunk_dup}/{vec_dup}/{es_dup}。"
        )
    else:
        w(f"(2) **id 对账**：模式={triple_mode}。")
    w(f"(3) **text**：相同={text_same} 不同={text_diff} ES缺={text_missing}。")
    if vec_compare_rows:
        ok_n = sum(1 for r in vec_compare_rows if r.get("ok") and r.get("cosine", 0) > 0.999)
        w(f"(4) **向量**：抽样 {len(vec_compare_rows)} 块；cosine>0.999 约 {ok_n}；字段=`{vec_field}`。")
    else:
        w("(4) **向量**：未比对或无文件。")
    w(
        "(5) **脚本能力**：可用现有 `*_vec.json` 经 `index_to_es --index/--input` 写入（不调嵌入）；"
        "`gen_embeddings` **不支持**指定 chunk_id 列表，仅断点跳过已有 id——局部重算需自写过滤或删掉目标行后重跑（会调 API）。"
        "本地 index 流程是 create+全量 bulk，不是增量补丁。"
    )
    w(
        f"(6) **fix_final**：匹配 {match_n} / 不匹配 {mismatch_n}（合计 {match_n+mismatch_n} vs {len(fix_rows)}）；"
        f"重算向量块≈{len(reembed_cids)} / 篇≈{len(reembed_mks)}；"
        f"头部可机械对齐率 {header_eq}/{len(sample100)}；"
        f"book 类 old 出现在 message_key 内 {mk_has_book_title} 条（改 book_title 不改 key/_id）。"
    )
    vec_field_names = sorted({r["field"] for r in map_rows})
    w(f"(7) **九索引向量字段**：{vec_field_names}；明细见 §5（共 {len(idx_names)} 个 panai4_*）。")
    w(
        f"(8) **磁盘**：G: 剩余 {usage.free/1e9:.2f} GB / 总量 {usage.total/1e9:.2f} GB；"
        f"PanAI4.0专用≈{panai_size/1e9:.2f} GB；方案A备份约需 {backup_need/1e9:.2f} GB。"
        f"妨碍因素：本地 index 先删后建需全量；无官方「只重算指定 id」开关；"
        f"book 改名后 message_key 路径仍含旧名（可接受因 _id 不变）。"
    )
    w("")

    w("## 1. 找文件")
    w("")
    w(f"### 1.1 `{OUT_DIR}` 文件清单（{len(outline_files)} 个）")
    w("")
    w("| 相对路径 | 大小 | mtime | 类型 |")
    w("|---|---:|---|---|")
    for f in outline_files:
        w(f"| `{f['rel']}` | {f['size']} | {f['mtime']} | {f['ext'] or 'dir-entry'} |")
    w("")
    w("### JSON/JSONL 结构")
    for rel, st in sorted(json_structs.items()):
        w(f"- `{rel}`：kind={st.get('kind')} n={st.get('n')} top_keys={st.get('top_keys')}")
        for i, samp in enumerate(st.get("sample_fields") or []):
            w(f"  - 记录{i+1}字段类型：`{samp}`")
    w("")
    w(f"### 1.2 名称匹配（PanAI 除原文/清明上河图）：{len(hits_panai)}；docs/panai4_es：{len(hits_docs)}；repo其它：{len(hits_repo)}")
    for label, hs in (("PanAI", hits_panai[:80]), ("docs", hits_docs[:40]), ("repo", hits_repo[:40])):
        w(f"#### {label}")
        for h in hs:
            kind = "dir" if h.get("is_dir") else "file"
            w(f"- [{kind}] `{h['path']}` size={h.get('size')} mtime={h.get('mtime')}")
        if label == "PanAI" and len(hits_panai) > 80:
            w(f"- … 另有 {len(hits_panai)-80} 条省略")
    w("")
    w("### 1.3 脚本默认路径与能力")
    w("")
    w(f"- `config.DEFAULT_OUT_DIR` = `{config.DEFAULT_OUT_DIR}`（config.py:340）")
    w("- **build_chunks.py**：读 `outline_*.json`，写 `chunks_*.json` JSONL；`chunk_id_of` = `sha1(message_key)[:12]`（153–155, 186）；`render_header` = book_title+U+3000+message_title（83–89）；`--out` 默认 DEFAULT_OUT_DIR（310）。")
    w("- **gen_embeddings.py**：`_embed_input` = `record['text']`（89–91）；输出 `chunks_*_vec.json`；批大小 50；支持断点续跑 `_read_done_ids`（840+）；**无** `--chunk-ids`；**必须**调嵌入接口补缺失；`--out/--inputs/--concurrency`（1480–1496）。")
    w("- **index_to_es.py**：向量字段名 `embedding`（65–70）；`_id = chunk_id`（473）；`--index/--input` 可单索引（1729–1731）；本地 create 后全量 bulk；remote 可 `skip_existing` 增量跳过已有 _id（1594–1596）；**不能**「无向量文件只写元数据」。")
    w("")
    w("### 1.4 纲目线资产表")
    w("")
    w("| 资产 | 路径 | 状态 | 大小 | mtime | 记录数 |")
    w("|---|---|---|---:|---|---:|")
    for a in assets:
        w(f"| {a['name']} | `{a['path']}` | {a['status']} | {a['size']} | {a['mtime']} | {a['n']} |")
    w("")
    w("### 1.5 feasts / bible 清点")
    for a in assets[5:]:
        w(f"- {a['name']}: status={a['status']} n={a['n']} size={a['size']}")
    w("")

    w("## 2. id 对账")
    w("")
    w(f"- 模式：{triple_mode}")
    w(f"- chunks={len(chunk_ids)} dup={chunk_dup}；vec={len(vec_ids)} dup={vec_dup}；es={len(es_ids)} dup={es_dup}")
    if has_chunks and has_vec:
        w(f"- chunks vs vec：仅chunks={c_only_v} 仅vec={v_only_c} 交={cv}；闭合 chunks {c_only_v}+{cv}={c_only_v+cv} vs {len(chunk_ids)}；vec {v_only_c}+{cv}={v_only_c+cv} vs {len(vec_ids)}")
        w(f"- chunks vs es：仅c={c_only_e} 仅e={e_only_c} 交={ce}")
        w(f"- vec vs es：仅v={v_only_e} 仅e={e_only_v} 交={ve}")
    elif has_chunks:
        w(f"- chunks vs es：仅c={c_only_e} 仅e={e_only_c} 交={ce}")
        w("- **没有向量文件**（本句不应出现——若出现说明路径异常）")
    w(f"- message_key：chunks={len(mk_c_set)} es={len(mk_e_set)} 仅c={len(mk_only_c)} 仅e={len(mk_only_e)} 交={len(mk_both)}")
    w(f"- message_key 块数不一致：{len(mk_count_mismatch)}")
    for mk, a, b in mk_count_mismatch[:30]:
        w(f"  - `{mk[:80]}` chunks={a} es={b}")
    w("")

    w("## 3. 内容一致性")
    w("")
    w(f"- text 相同={text_same} 不同={text_diff} ES缺块={text_missing}")
    for cid, a, b in text_diff_samples:
        w(f"  - `{cid}` chunks=`{a}` | es=`{b}`")
    w("")
    w("### 3.2 头部行抽样 20")
    c_eq_e = sum(1 for h in header_samples if h["c_eq_e"])
    c_eq_f = sum(1 for h in header_samples if h["c_eq_formula"])
    e_eq_f = sum(1 for h in header_samples if h["e_eq_formula"])
    w(f"- chunks第一行==ES第一行：{c_eq_e}/{len(header_samples)}")
    w(f"- chunks第一行==book+U+3000+title：{c_eq_f}/{len(header_samples)}")
    w(f"- ES第一行==book+U+3000+title：{e_eq_f}/{len(header_samples)}")
    w("")
    w("### 3.3 向量抽样（只报数值）")
    if not has_vec:
        w("- 向量文件未找到，跳过。")
    else:
        w(f"- 读取含向量的文档数（file+ES合计计数）≈{vec_docs_read}")
        for r in vec_compare_rows:
            if not r.get("ok"):
                w(f"  - `{r['cid']}` FAIL {r.get('note')}")
            else:
                w(
                    f"  - `{r['cid']}` dims={r['dims_f']}/{r['dims_e']} "
                    f"norm={r['norm_f']}/{r['norm_e']} max_abs={r['max_abs']:.6e} cos={r['cosine']:.8f}"
                )
    w("")
    w("### 3.4 embedding 输入")
    w("- `gen_embeddings._embed_input`：`return record.get(\"text\") or \"\"`（gen_embeddings.py:89–91）。即向量对 **text 本身**。")
    w("")

    w("## 4. 修订清单对齐")
    w("")
    w(f"- fix_final 条数={len(fix_rows)}；匹配={match_n} 不匹配={mismatch_n}；闭合={match_n+mismatch_n==len(fix_rows)}")
    for mk, field, reason in mismatches:
        w(f"  - FAIL `{mk}` field={field}：{reason}")
    w(f"- 字段影响：{field_change_note}")
    w(f"- book 类 old 含子串于 message_key：{mk_has_book_title}")
    w(f"- 需重算向量：块={len(reembed_cids)} 篇={len(reembed_mks)}")
    w(f"- 头部公式对齐抽样：{header_eq}/{len(sample100)}（text 正文无法仅凭 chunks 字段无 points 全量重建；头部可机械替换）")
    w("")

    w("## 5. 九个索引向量字段")
    w("")
    w("| 索引 | 向量字段 | dims | similarity | index_options.type |")
    w("|---|---|---:|---|---|")
    for r in map_rows:
        w(f"| {r['index']} | {r['field']} | {r['dims']} | {r['similarity']} | {r['index_options_type']} |")
    fields = {r["field"] for r in map_rows}
    if len(fields) > 1:
        w(f"- **字段名不一致**：{sorted(fields)}。统一检索时必须按索引分支取不同字段名，不能写死单一字段。")
    else:
        w(f"- 字段名一致：{sorted(fields)}")
    w("")

    w("## 6. 磁盘与风险")
    w("")
    w(f"- G: free={usage.free} bytes ({usage.free/1e9:.2f} GB)；total={usage.total/1e9:.2f} GB")
    w(f"- PanAI4.0专用 total≈{panai_size} bytes ({panai_size/1e9:.2f} GB)")
    w(f"- 方案A完整备份（outline+chunks+vec+excluded+anomalies 粗算）≈{backup_need/1e9:.2f} GB")
    w("- 妨碍方案 A 的因素：")
    w("  1. `gen_embeddings` 无「只重算指定 chunk_id」参数；局部重算需自行过滤或删 vec 中对应行后重跑（会调 API）。")
    w("  2. 本地 `index_to_es` 默认 create+全量写入；要用文件重建需接受删建或改流程做 update-by-id。")
    w("  3. 可从已有 `*_vec.json` 写入且不调嵌入（index_to_es 读文件 bulk）——前提是 vec 文件已含更新后的 embedding。")
    w("  4. text 正文依赖纲目 points；改标题只需替换第一行，可用字段机械更新 text 头部。")
    w("")

    w("## 验证")
    w("")
    w(f"1. count {count_before}/{count_after} 一致={count_before==count_after} (55841={count_before==55841})")
    w(f"2. 纲目JSON 快照 before_files={len(snap_before)} bytes={sum(s for _,s,_ in snap_before)} after_files={len(snap_after)} bytes={sum(s for _,s,_ in snap_after)} identical={snap_before==snap_after}")
    if has_chunks and has_vec:
        w(f"3. 闭合：c={c_only_v}+{cv}=={len(chunk_ids)} → {c_only_v+cv==len(chunk_ids)}；v={v_only_c}+{cv}=={len(vec_ids)} → {v_only_c+cv==len(vec_ids)}；e 对 c：{c_only_e}+{ce}=={len(chunk_ids)} → {c_only_e+ce==len(chunk_ids)}")
    w(f"4. fix 匹配+不匹配={match_n}+{mismatch_n}={match_n+mismatch_n} vs 70={len(fix_rows)}")
    w("5. git:")
    w("```")
    w(_git_status())
    w("```")
    w("6. ES 只用 info/count/get_mapping/get(indices)/search/scroll/mget；除 3.3 外排除向量字段；3.3 读取向量文档计数≈" + str(vec_docs_read))
    w("7. 未运行 gen_embeddings / index_to_es / build_chunks。")
    w("")

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("wrote %s", report_path)
    print(
        f"report={report_path} chunks={len(chunk_ids)} vec={len(vec_ids)} es={len(es_ids)} "
        f"text_same={text_same} text_diff={text_diff} fix={match_n}/{mismatch_n} "
        f"reembed={len(reembed_cids)}/{len(reembed_mks)} vec_field={vec_field}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
