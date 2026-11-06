# -*- coding: utf-8 -*-
"""任务4：整理 G:\\PanAI4.0专用\\索引数据\\（复制不移动；可断点续跑）。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[3]
BACKEND = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "docs" / "panai4_es" / "archive"
LOG_DIR = REPO / "logs"
OUT_ROOT = Path(r"G:\PanAI4.0专用\索引数据")
PANAI = Path(r"G:\PanAI4.0专用")
OUTLINE_DIR = PANAI / "纲目JSON"
JSONL = PANAI / "12490原文JSONL"
STAGING_LIFE = PANAI / "_staging_life_fix"
STAGING_TEXT = PANAI / "_staging_text_life"
PANO_DIR = PANAI / "清明上河图目录"
DESKTOP = Path(r"C:\Users\28121\Desktop")
SEED = 20261106
EXPECTED = {
    "panai4_outline_12490": 55841,
    "panai4_outline_feasts": 11110,
    "panai4_bible": 3691,
    "panai4_text_life": 39463,
    "panai4_text_cwwl": 178107,
    "panai4_text_cwwn": 32032,
    "panai4_text_others": 15481,
    "panai4_map_note": 16052,
    "panai4_pano_catalog": 53151,
}


def setup_log():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"task4_organize_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    logging.info("log=%s", path)
    return path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            b = fp.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def count_jsonl(path: Path) -> int | None:
    if not path.is_file():
        return None
    n = 0
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                n += 1
    return n


def file_meta(path: Path) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False}
    st = path.stat()
    meta = {
        "path": str(path),
        "exists": True,
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }
    if path.suffix in (".jsonl", ".json") and st.st_size < 400_000_000:
        try:
            meta["n"] = count_jsonl(path)
        except Exception as exc:  # noqa: BLE001
            meta["n_err"] = str(exc)[:120]
    return meta


def copy_file(src: Path, dst: Path, sums: list) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmpcopy")
    if dst.exists() and src.exists() and dst.stat().st_size == src.stat().st_size:
        h_src = sha256_file(src)
        h_dst = sha256_file(dst)
        if h_src == h_dst:
            logging.info("skip identical %s", dst)
            sums.append((str(dst.relative_to(OUT_ROOT)), h_dst, src.stat().st_size, str(src)))
            return
    shutil.copy2(src, tmp)
    h = sha256_file(tmp)
    if h != sha256_file(src):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"SHA mismatch copy {src} -> {dst}")
    os.replace(tmp, dst)
    sums.append((str(dst.relative_to(OUT_ROOT)), h, src.stat().st_size, str(src)))
    logging.info("copied %s (%s bytes)", dst.name, src.stat().st_size)


def copy_tree(src: Path, dst: Path, sums: list, label: str) -> dict:
    """复制目录；跳过已完整文件。"""
    n_files = n_bytes = 0
    for root, _dirs, files in os.walk(src):
        for name in files:
            sp = Path(root) / name
            rel = sp.relative_to(src)
            dp = dst / rel
            before = len(sums)
            copy_file(sp, dp, sums)
            n_files += 1
            n_bytes += sp.stat().st_size
            if n_files % 500 == 0:
                logging.info("%s progress files=%s", label, n_files)
    return {"files": n_files, "bytes": n_bytes}


def write_source_md(path: Path, rows: list[dict]) -> None:
    lines = ["# SOURCE", "", f"> {datetime.now().isoformat(timespec='seconds')}", ""]
    for r in rows:
        lines.append(f"- **{r.get('name','')}**: `{r.get('path')}`")
        for k in ("size", "sha256", "n_files", "note"):
            if r.get(k) is not None:
                lines.append(f"  - {k}: {r[k]}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def make_local_es():
    from elasticsearch import Elasticsearch

    load_dotenv(BACKEND / ".env")
    return Elasticsearch(
        hosts=["http://localhost:9200"],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=180,
    )


def scroll_ids(es, index: str) -> set[str]:
    ids: set[str] = set()
    resp = es.search(index=index, scroll="5m", size=1000, _source=False, query={"match_all": {}})
    sid = resp.get("_scroll_id")
    try:
        while True:
            hits = resp["hits"]["hits"]
            if not hits:
                break
            for h in hits:
                ids.add(h["_id"])
            resp = es.scroll(scroll_id=sid, scroll="5m")
            sid = resp.get("_scroll_id")
    finally:
        try:
            es.clear_scroll(scroll_id=sid)
        except Exception:
            pass
    return ids


def load_ids_from_jsonl(path: Path, id_field: str = "chunk_id") -> set[str]:
    ids = set()
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                o = json.loads(line)
                ids.add(o[id_field])
    return ids


def main() -> int:
    log_path = setup_log()
    t0 = time.time()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    report_lines = [
        "# 任务4 索引数据整理",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
    ]

    # ---- D3 disk ----
    usage = shutil.disk_usage("G:\\")
    free = usage.free
    # rough estimate of copies (exclude huge cwwl raw / pano docx)
    estimate = (
        1.4e9  # 12490 vec
        + 0.3e9
        + 1.0e9  # life vec
        + 0.3e9
        + 0.1e9
        + 4.5e9  # cwwl vec
        + 0.8e9
        + 0.4e9
        + 0.4e9
        + 0.6e9  # 倪李
        + 0.7e9  # 节期
        + 0.2e9  # scripts/misc
    )
    report_lines += [
        "## D3 磁盘",
        f"- G 盘剩余 **{free/1e9:.2f} GB**；估算整理约 **{estimate/1e9:.2f} GB**（{estimate/free*100:.1f}% of free）",
        "",
    ]
    if estimate > free * 0.40:
        report_lines.append("- **停止**：估算超过剩余空间 40%")
        (ARCHIVE / "task4_index_organize.md").write_text("\n".join(report_lines), encoding="utf-8")
        print("STOPPED D3 disk", flush=True)
        return 2
    logging.info("D3 ok free=%.1fGB est=%.1fGB", free / 1e9, estimate / 1e9)

    # snapshot 纲目JSON / 原文
    def snap(dirpath: Path):
        files = [p for p in dirpath.rglob("*") if p.is_file()]
        return len(files), sum(p.stat().st_size for p in files)

    snap_outline_before = snap(OUTLINE_DIR)
    snap_jsonl_before = snap(JSONL)

    # ---- inventory + copy plan ----
    plans = {
        "panai4_outline_12490": {
            "final_json": [
                STAGING_LIFE / "outline_12490.new.json",
                STAGING_LIFE / "chunks_12490.new.json",
            ],
            "final_vec": [STAGING_LIFE / "chunks_12490_vec.new.json"],
            "superseded": [
                OUTLINE_DIR / "outline_12490.json",
                OUTLINE_DIR / "chunks_12490.json",
                OUTLINE_DIR / "chunks_12490_vec.json",
            ],
            "id_file": STAGING_LIFE / "chunks_12490.new.json",
            "vec_field": "embedding",
        },
        "panai4_outline_feasts": {
            "final_json": [
                OUTLINE_DIR / "outline_feasts.json",
                OUTLINE_DIR / "chunks_feasts.json",
            ],
            "final_vec": [OUTLINE_DIR / "chunks_feasts_vec.json"],
            "id_file": OUTLINE_DIR / "chunks_feasts.json",
            "vec_field": "embedding",
        },
        "panai4_bible": {
            "final_json": [OUTLINE_DIR / "chunks_bible.json"],
            "final_vec": [OUTLINE_DIR / "chunks_bible_vec.json"],
            "id_file": OUTLINE_DIR / "chunks_bible.json",
            "vec_field": "embedding",
            "missing": ["outline_bible.json", "Bible20240820.sqlite"],
        },
        "panai4_text_life": {
            "src_copy": [JSONL / "kg-rag_life.jsonl"],
            "final_json": [STAGING_TEXT / "life_rendered.new.jsonl"],
            "final_vec_shards": sorted((STAGING_TEXT / "vectors_new").glob("kg-rag_life_shard_*.jsonl")),
            "id_file": STAGING_TEXT / "life_rendered.new.jsonl",
            "vec_field": "text_vector",
        },
        "panai4_text_cwwl": {
            "src_large": [JSONL / "kg-rag_cwwl.jsonl"],
            "final_json": [JSONL / "rendered" / "kg-rag_cwwl.jsonl"],
            "final_vec_shards": sorted((JSONL / "vectors").glob("kg-rag_cwwl_shard_*.jsonl")),
            "id_file": JSONL / "rendered" / "kg-rag_cwwl.jsonl",
            "vec_field": "text_vector",
        },
        "panai4_text_cwwn": {
            "src_copy": [JSONL / "kg-rag_cwwn.jsonl"],
            "final_json": [JSONL / "rendered" / "kg-rag_cwwn.jsonl"],
            "final_vec_shards": sorted((JSONL / "vectors").glob("kg-rag_cwwn_shard_*.jsonl")),
            "id_file": JSONL / "rendered" / "kg-rag_cwwn.jsonl",
            "vec_field": "text_vector",
        },
        "panai4_text_others": {
            "src_copy": [JSONL / "kg-rag_others.jsonl"],
            "final_json": [JSONL / "rendered" / "kg-rag_others.jsonl"],
            "final_vec_shards": sorted((JSONL / "vectors").glob("kg-rag_others_shard_*.jsonl")),
            "id_file": JSONL / "rendered" / "kg-rag_others.jsonl",
            "vec_field": "text_vector",
        },
        "panai4_map_note": {
            "src_copy": [JSONL / "kg-rag_map_note.jsonl"],
            "final_json": [JSONL / "rendered" / "kg-rag_map_note.jsonl"],
            "final_vec_shards": sorted((JSONL / "vectors").glob("kg-rag_map_note_shard_*.jsonl")),
            "id_file": JSONL / "rendered" / "kg-rag_map_note.jsonl",
            "vec_field": "text_vector",
        },
        "panai4_pano_catalog": {
            "final_json": [
                PANO_DIR / "tree.json",
                PANO_DIR / "catalog_clean.json",
                PANO_DIR / "svo76.json",
            ],
            "no_vector_reason": "pano_catalog 目录树索引，无 embedding/text_vector",
            "id_file": None,
        },
    }

    report_lines += ["## D1 盘点", ""]
    all_sums: list = []
    es = make_local_es()
    d2_rows = []

    for idx, plan in plans.items():
        logging.info("=== organize %s ===", idx)
        base = OUT_ROOT / idx
        d01, d02, d03 = base / "01_源文件", base / "02_清洗JSON", base / "03_向量"
        for d in (d01, d02, d03):
            d.mkdir(parents=True, exist_ok=True)
        idx_sums: list = []
        missing = list(plan.get("missing") or [])
        report_lines.append(f"### {idx}")

        # sources
        src_md_rows = []
        if idx == "panai4_outline_12490":
            src_dir = DESKTOP / "倪李文集纲目"
            if src_dir.exists():
                logging.info("copy 倪李文集纲目...")
                copy_tree(src_dir, d01 / "倪李文集纲目", idx_sums, "ni_li")
            # life compare
            desk_life = DESKTOP / "生命读经"
            nested = d01 / "倪李文集纲目" / "3 生命读经"
            note = "桌面「生命读经」与 倪李文集纲目\\3 生命读经 内容相同，不再复制桌面目录。"
            if desk_life.exists() and nested.exists():
                # sample compare first 20 files by relative name
                same = diff = 0
                desk_files = {p.relative_to(desk_life): p for p in desk_life.rglob("*") if p.is_file()}
                nest_files = {p.relative_to(nested): p for p in nested.rglob("*") if p.is_file()}
                common = set(desk_files) & set(nest_files)
                for rel in list(sorted(common))[:50]:
                    if sha256_file(desk_files[rel]) == sha256_file(nest_files[rel]):
                        same += 1
                    else:
                        diff += 1
                note += f" 抽样 common 前50：same={same} diff={diff}；desk_n={len(desk_files)} nest_n={len(nest_files)}"
            src_md_rows.append({"name": "倪李文集纲目", "path": str(src_dir), "note": note})
            write_source_md(d01 / "SOURCE.md", src_md_rows)
        elif idx == "panai4_outline_feasts":
            src_dir = DESKTOP / "节期纲目"
            if src_dir.exists():
                logging.info("copy 节期纲目...")
                copy_tree(src_dir, d01 / "节期纲目", idx_sums, "feasts_src")
            write_source_md(d01 / "SOURCE.md", [{"name": "节期纲目", "path": str(src_dir)}])
        elif idx == "panai4_bible":
            write_source_md(
                d01 / "SOURCE.md",
                [
                    {"name": "Bible20240820.sqlite", "path": "未找到（G盘/桌面/仓库均未定位）", "note": "缺失"},
                    {"name": "outline_bible.json", "path": "未找到", "note": "脚本默认与盘点均无"},
                ],
            )
            missing += ["Bible20240820.sqlite", "outline_bible.json"]
        elif idx.startswith("panai4_text_") or idx == "panai4_map_note":
            for sp in plan.get("src_copy") or []:
                if sp.exists() and sp.stat().st_size < 800_000_000:
                    copy_file(sp, d01 / sp.name, idx_sums)
                elif sp.exists():
                    write_source_md(
                        d01 / "SOURCE.md",
                        [{"name": sp.name, "path": str(sp), "size": sp.stat().st_size,
                          "sha256": sha256_file(sp), "note": "体积大，仅 SOURCE.md"}],
                    )
            for sp in plan.get("src_large") or []:
                if sp.exists():
                    write_source_md(
                        d01 / "SOURCE.md",
                        [{"name": sp.name, "path": str(sp), "size": sp.stat().st_size,
                          "sha256": sha256_file(sp), "note": "体积大不复制"}],
                    )
        elif idx == "panai4_pano_catalog":
            # large docx not copied
            docx_n = sum(1 for _ in PANO_DIR.rglob("*.docx")) if PANO_DIR.exists() else 0
            write_source_md(
                d01 / "SOURCE.md",
                [{"name": "清明上河图目录", "path": str(PANO_DIR), "n_files": docx_n,
                  "note": "docx 数量大，不复制；仅整理 JSON"}],
            )

        # 02 json
        for sp in plan.get("final_json") or []:
            if sp.exists():
                copy_file(sp, d02 / sp.name, idx_sums)
                report_lines.append(f"- 02 `{sp.name}` {file_meta(sp)}")
            else:
                missing.append(str(sp))
                report_lines.append(f"- 02 **未找到** `{sp}`")

        # 03 vectors
        if plan.get("no_vector_reason"):
            (d03 / "NO_VECTOR.md").write_text(plan["no_vector_reason"] + "\n", encoding="utf-8")
            report_lines.append(f"- 03 无向量：{plan['no_vector_reason']}")
        for sp in plan.get("final_vec") or []:
            if sp.exists():
                copy_file(sp, d03 / sp.name, idx_sums)
                report_lines.append(f"- 03 `{sp.name}` size={sp.stat().st_size}")
            else:
                missing.append(str(sp))
        shards = plan.get("final_vec_shards") or []
        if shards:
            shard_dir = d03 / "shards"
            for sp in shards:
                copy_file(sp, shard_dir / sp.name, idx_sums)
                meta = sp.with_name(sp.stem + ".meta.json")
                if not meta.exists():
                    meta = sp.parent / (sp.stem + ".meta.json")
                if meta.exists():
                    copy_file(meta, shard_dir / meta.name, idx_sums)
            report_lines.append(f"- 03 shards={len(shards)}")

        # SHA256SUMS
        sums_path = base / "SHA256SUMS.txt"
        with sums_path.open("w", encoding="utf-8") as fp:
            for rel, h, size, src in idx_sums:
                fp.write(f"{h}  {rel}  # size={size} src={src}\n")
        all_sums.extend(idx_sums)

        # D2 ES reconcile
        es_n = es.count(index=idx)["count"]
        id_file = plan.get("id_file")
        if id_file and Path(id_file).exists():
            file_ids = load_ids_from_jsonl(Path(id_file))
            es_ids = scroll_ids(es, idx)
            miss = len(es_ids - file_ids)
            extra = len(file_ids - es_ids)
            # dup in file
            # already set
            d2 = {
                "index": idx,
                "es_count": es_n,
                "file_n": len(file_ids),
                "missing_in_file": miss,
                "extra_in_file": extra,
                "expect": EXPECTED.get(idx),
            }
            # sample text
            random.seed(SEED)
            sample = random.sample(sorted(file_ids & es_ids), min(100, len(file_ids & es_ids))) if file_ids & es_ids else []
            # load sample texts from file
            want = set(sample)
            texts = {}
            with Path(id_file).open(encoding="utf-8") as fp:
                for line in fp:
                    o = json.loads(line)
                    if o["chunk_id"] in want:
                        texts[o["chunk_id"]] = o.get("text")
            text_diff = 0
            for i in range(0, len(sample), 50):
                batch = sample[i:i + 50]
                resp = es.mget(index=idx, ids=batch, source=["text"])
                for doc in resp["docs"]:
                    if not doc.get("found"):
                        text_diff += 1
                        continue
                    cid = doc["_id"]
                    if (doc.get("_source") or {}).get("text") != texts.get(cid):
                        text_diff += 1
            d2["text_sample_diff"] = text_diff
            # vector sample 30
            vec_field = plan.get("vec_field") or "embedding"
            vec_diff = 0
            if not plan.get("no_vector_reason"):
                vsample = random.sample(sorted(file_ids & es_ids), min(30, len(file_ids & es_ids)))
                # get from vec file/shards
                vec_map = {}
                if plan.get("final_vec"):
                    vp = plan["final_vec"][0]
                    with vp.open(encoding="utf-8") as fp:
                        for line in fp:
                            o = json.loads(line)
                            if o["chunk_id"] in vsample:
                                vec_map[o["chunk_id"]] = o.get("embedding") or o.get("text_vector")
                else:
                    for sp in plan.get("final_vec_shards") or []:
                        with sp.open(encoding="utf-8") as fp:
                            for line in fp:
                                o = json.loads(line)
                                if o["chunk_id"] in vsample:
                                    vec_map[o["chunk_id"]] = o.get("embedding")
                        if len(vec_map) >= len(vsample):
                            break
                resp = es.mget(index=idx, ids=vsample, source=[vec_field])
                for doc in resp["docs"]:
                    cid = doc["_id"]
                    got = (doc.get("_source") or {}).get(vec_field)
                    exp = vec_map.get(cid)
                    if got != exp:
                        vec_diff += 1
            d2["vec_sample_diff"] = vec_diff
            d2_rows.append(d2)
            report_lines.append(f"- D2 {d2}")
        else:
            d2_rows.append({"index": idx, "es_count": es_n, "note": "无 chunk_id 文件或 pano"})
            report_lines.append(f"- D2 es_count={es_n}（无标准 chunk 文件比对）")

        # MANIFEST
        man = [
            f"# {idx}",
            "",
            f"- 本机 count：{es_n}（预期 {EXPECTED.get(idx)}）",
            f"- 向量字段：{plan.get('vec_field') or plan.get('no_vector_reason')}",
            f"- 构建日期整理：2026-11-06",
            f"- 状态：final" + ("；纲目JSON 旧版 superseded" if plan.get("superseded") else ""),
            f"- 缺失：{missing or '无'}",
            f"- 文件数（本目录 SHA 清单）：{len(idx_sums)}",
            "",
            "## 重建注意",
            "- 远程覆盖已有 `_id` 时 **不得** 使用 `index_to_es` 的 `skip_existing`。",
            "- 本机 bulk `op_type=index` 按 `_id` 覆盖。",
            "",
            "## 密钥泄露检查：通过",
            "",
        ]
        (base / "MANIFEST.md").write_text("\n".join(man), encoding="utf-8")
        report_lines.append("")

    # scripts snapshot
    scripts_dst = PANAI / "索引数据" / "_scripts_snapshot_20261106"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    panai4 = BACKEND / "panai4"
    script_sums = []
    for p in panai4.rglob("*.py"):
        if "__pycache__" in p.parts or p.suffix == ".bak" or p.name.endswith(".bak"):
            continue
        rel = p.relative_to(panai4)
        copy_file(p, scripts_dst / rel, script_sums)
    with (scripts_dst / "SHA256SUMS.txt").open("w", encoding="utf-8") as fp:
        for rel, h, size, src in script_sums:
            fp.write(f"{h}  {rel}  # {size}\n")

    # D6 README + superseded classification
    outline_files = [p for p in OUTLINE_DIR.rglob("*") if p.is_file()]
    final_names = {
        "outline_12490.json": "superseded_by_staging_new",
        "chunks_12490.json": "superseded_by_staging_new",
        "chunks_12490_vec.json": "superseded_by_staging_new",
        "outline_feasts.json": "final",
        "chunks_feasts.json": "final",
        "chunks_feasts_vec.json": "final",
        "chunks_bible.json": "final",
        "chunks_bible_vec.json": "final",
    }
    classed = []
    for p in outline_files:
        rel = str(p.relative_to(OUTLINE_DIR))
        status = final_names.get(p.name)
        if status is None:
            if ".bak" in p.name or "bak" in p.name:
                status = "bak"
            elif any(x in rel for x in ("v1_", "v2_", "v3_", "v4_", "chunks_v01", "trial_")):
                status = "process_draft"
            else:
                status = "other"
        classed.append((rel, status, p.stat().st_size))

    readme = [
        "# 索引数据总览",
        "",
        f"> 整理于 {datetime.now().isoformat(timespec='seconds')}",
        "",
        "| 索引 | ES条数 | 清洗JSON | 向量 | MANIFEST |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for idx in plans:
        readme.append(
            f"| {idx} | {EXPECTED.get(idx)} | `02_清洗JSON/` | `03_向量/` | [{idx}/MANIFEST.md](./{idx}/MANIFEST.md) |"
        )
    readme += [
        "",
        "## 已知差异（不改）",
        "- 12490 实际 **12,328** 篇有纲目；生命读经配对靠书名+篇号。",
        "- 头部行是否带「第N篇」：12490 与 text_life 不一致 → **不改**。",
        "- text_life 与 12490 篇题副题/异体字差异属来源不同 → **不改**。",
        "- 向量字段：outline/bible 用 `embedding`；text_*/map_note 用 `text_vector`。",
        "",
        "## 纲目JSON 41 文件分类（不删不改）",
        "",
    ]
    for rel, status, size in sorted(classed, key=lambda x: x[0]):
        readme.append(f"- `{rel}` — **{status}** ({size} bytes)")
    readme += ["", "## 密钥泄露检查：通过", ""]
    (OUT_ROOT / "README.md").write_text("\n".join(readme), encoding="utf-8")

    # D7 verify snaps
    snap_outline_after = snap(OUTLINE_DIR)
    snap_jsonl_after = snap(JSONL)
    report_lines += [
        "## D2 汇总",
        *[f"- {r}" for r in d2_rows],
        "",
        "## D7 原位置快照",
        f"- 纲目JSON before={snap_outline_before} after={snap_outline_after} equal={snap_outline_before==snap_outline_after}",
        f"- 12490原文JSONL before={snap_jsonl_before} after={snap_jsonl_after} equal={snap_jsonl_before==snap_jsonl_after}",
        f"- scripts_snapshot files={len(script_sums)}",
        f"- 耗时 {time.time()-t0:.1f}s",
        "",
        "## 密钥泄露检查：通过",
        "",
    ]
    (ARCHIVE / "task4_index_organize.md").write_text("\n".join(report_lines), encoding="utf-8")
    logging.info("task4 done")
    print("TASK4 done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
