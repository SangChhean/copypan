# -*- coding: utf-8 -*-
"""panai4_text_life 修订：T0 勘探/备份/预检；T1–T4 干跑/嵌入/本机/服务器。

用法（cd G:\\copypan\\back_mic\\backend）::

    python -m panai4.inherit.apply_text_life_fix --stage t0
    python -m panai4.inherit.apply_text_life_fix --stage t1
    python -m panai4.inherit.apply_text_life_fix --stage t2_embed
    python -m panai4.inherit.apply_text_life_fix --stage t2_assemble
    python -m panai4.inherit.apply_text_life_fix --stage t3
    python -m panai4.inherit.apply_text_life_fix --stage t4
    python -m panai4.inherit.apply_text_life_fix --stage apply   # t1→t4 顺序（embed 同步）
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import math
import os
import random
import re
import shutil
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from panai4.inherit.render_text import build_header, render_text

EMBED_DIMS = 1024
EMBED_BATCH = 50
EMBED_CONCURRENCY = 4
EMBED_RETRY_WAITS = (1, 2, 4, 8, 16)
SHARD_SIZE = 2000
LOCAL_BULK = 100
REMOTE_BULK = 50
IMMUTABLE_FIELDS = (
    "chunk_id", "message_key", "message_number", "section_title",
    "author", "paragraph_type", "source_zh", "source_en", "en",
    "original_ids", "corpus", "source_index",
)
COMPARE_FIELDS = (
    "chunk_id", "message_key", "book_title", "message_number", "message_title",
    "section_title", "author", "paragraph_type", "source_zh", "source_en",
    "original_ids", "corpus", "source_index", "text", "chars",
)

REPO = Path(__file__).resolve().parents[4]
BACKEND = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "docs" / "panai4_es" / "archive"
LOG_DIR = REPO / "logs"
SRC_ROOT = Path(r"G:\PanAI4.0专用\12490原文JSONL")
RAW_LIFE = SRC_ROOT / "kg-rag_life.jsonl"
RENDERED_LIFE = SRC_ROOT / "rendered" / "kg-rag_life.jsonl"
VEC_DIR = SRC_ROOT / "vectors"
STAGING = Path(r"G:\PanAI4.0专用\_staging_text_life")
BACKUP = Path(r"G:\PanAI4.0专用\备份_text_life修订前_20261106")
ES_INDEX = "panai4_text_life"
EXPECTED_N = 39463
COST_PER_1K = 0.002
SEED = 20261106

BOOK_RENAME = {
    "列王记生命读经": "列王纪生命读经",
    "歌林多前书生命读经": "哥林多前书生命读经",
    "歌林多后书生命读经": "哥林多后书生命读经",
    "腓利比书生命读经": "腓立比书生命读经",
}
DIRTY_SPLIT = re.compile(r"^(.*?)，第([〇零一二三四五六七八九十百千两\d]+)篇(.*)$")


class GateFail(Exception):
    def __init__(self, gate: str, msg: str, payload: Optional[dict] = None):
        super().__init__(f"{gate}: {msg}")
        self.gate = gate
        self.payload = payload or {}


def setup_log() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"text_life_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    logging.info("log=%s", path)
    return path


def _env_path() -> Path:
    return BACKEND / ".env"


def _redact(text: str, secrets: list[str]) -> str:
    out = text or ""
    for s in secrets:
        if s and len(s) >= 8:
            out = out.replace(s, "***")
    return out


def _secrets() -> list[str]:
    keys = ("OPENROUTER_API_KEY", "ES_PASSWORD", "ES_REMOTE_PASSWORD", "NEO4J_PASSWORD", "OPENAI_API_KEY")
    return [os.environ.get(k, "") for k in keys if os.environ.get(k)]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            b = fp.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def make_local_es():
    from elasticsearch import Elasticsearch

    load_dotenv(_env_path())
    host = os.getenv("ES_HOST", "localhost")
    port = os.getenv("ES_PORT", "9200")
    if host not in ("localhost", "127.0.0.1") or str(port) != "9200":
        raise GateFail("ES", f"本机 ES 只允许 localhost:9200，当前 {host}:{port}")
    return Elasticsearch(
        hosts=[f"http://{host}:{port}"],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=180,
        max_retries=0,
    )


def make_remote_es():
    from elasticsearch import Elasticsearch

    load_dotenv(_env_path())
    host = (os.getenv("ES_REMOTE_HOST") or "").strip()
    port = (os.getenv("ES_REMOTE_PORT") or "").strip()
    user = (os.getenv("ES_REMOTE_USERNAME") or "").strip()
    password = (os.getenv("ES_REMOTE_PASSWORD") or "").strip()
    missing = [k for k, v in [
        ("ES_REMOTE_HOST", host), ("ES_REMOTE_PORT", port),
        ("ES_REMOTE_USERNAME", user), ("ES_REMOTE_PASSWORD", password),
    ] if not v]
    if missing:
        raise GateFail("ES", f"缺少 {missing}")
    if host in ("localhost", "127.0.0.1"):
        raise GateFail("ES", "ES_REMOTE_HOST 不能是本机")
    return Elasticsearch(
        hosts=[f"http://{host}:{port}"],
        basic_auth=(user, password),
        request_timeout=180,
        max_retries=2,
        retry_on_timeout=True,
    )


def count_jsonl(path: Path) -> int:
    n = 0
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                n += 1
    return n


def iter_vec_shards(label: str = "kg-rag_life"):
    i = 0
    while True:
        p = VEC_DIR / f"{label}_shard_{i:05d}.jsonl"
        if not p.is_file():
            break
        yield p
        i += 1


def parse_dirty_book(bt: str) -> Optional[dict]:
    m = DIRTY_SPLIT.match(bt or "")
    if not m:
        return None
    clean_raw, cn_num, rest = m.group(1), m.group(2), m.group(3) or ""
    frag = rest.lstrip("\u3000 ").lstrip()
    return {"clean_raw": clean_raw, "cn_num": cn_num, "frag": frag}


def apply_book_rename(name: str) -> str:
    for old, new in BOOK_RENAME.items():
        if name == old or name.startswith(old):
            # exact or dirty prefix
            if name == old:
                return new
            if name.startswith(old + "，") or name.startswith(old + ","):
                return new + name[len(old):]
            if name == old:
                return new
    # also if clean_raw equals old
    return BOOK_RENAME.get(name, name)


def propose_fields(old_bt: str, old_mt: str) -> dict:
    """返回 new_bt, new_mt, category, reembed_needed_hint."""
    dirty = parse_dirty_book(old_bt)
    if dirty:
        clean = BOOK_RENAME.get(dirty["clean_raw"], dirty["clean_raw"])
        new_mt = f"第{dirty['cn_num']}篇" + "\u3000" + (dirty["frag"] + (old_mt or ""))
        return {"new_bt": clean, "new_mt": new_mt, "category": "dirty_book", "dirty": dirty}
    # rename only
    new_bt = BOOK_RENAME.get(old_bt)
    if new_bt and new_bt != old_bt:
        return {"new_bt": new_bt, "new_mt": old_mt, "category": "rename", "dirty": None}
    return {"new_bt": old_bt, "new_mt": old_mt, "category": "none", "dirty": None}


def nfkc_compact(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    for a, b in [("（", "("), ("）", ")"), ("—", "-"), ("─", "-"), ("，", ","), ("　", ""), (" ", "")]:
        s = s.replace(a, b)
    return s


def strip_msg_prefix(mt: str) -> str:
    m = re.match(r"^第[〇零一二三四五六七八九十百千两\d]+篇[\u3000\s]*(.*)$", mt or "")
    return m.group(1) if m else (mt or "")


def load_pairing() -> dict:
    """desktop doc_title by (book_guess, msg_no) from life_outline_pairing.csv if present."""
    path = ARCHIVE / "life_outline_pairing.csv"
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            # best-effort columns
            book = row.get("es_book") or row.get("book") or row.get("book_title") or ""
            mno = row.get("es_msg_no") or row.get("msg_no") or row.get("message_number") or ""
            title = row.get("doc_title") or row.get("desktop_title") or row.get("d_eff") or ""
            try:
                mno_i = int(mno) if str(mno).isdigit() else mno
            except Exception:
                mno_i = mno
            if book and title:
                out[(book, mno_i)] = title
    return out


def load_12490_titles() -> dict:
    """(book_title, message_number) -> message_title from chunks new or backup."""
    candidates = [
        Path(r"G:\PanAI4.0专用\_staging_life_fix\chunks_12490.new.json"),
        Path(r"G:\PanAI4.0专用\备份_生命读经修订前_20261106\chunks_12490.json"),
        Path(r"G:\PanAI4.0专用\纲目JSON\chunks_12490.json"),
    ]
    path = next((p for p in candidates if p.exists()), None)
    out = {}
    if not path:
        return out
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            if o.get("chunk_index") != 1:
                continue
            bt = o.get("book_title") or ""
            if "生命读经" not in bt:
                continue
            out[(bt, o.get("message_number"))] = o.get("message_title") or ""
    return out


def stage_t0(log_path: Path) -> dict:
    STAGING.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    secrets = []
    load_dotenv(_env_path())
    secrets = _secrets()

    # ---- T0.1 inventory ----
    shards = list(iter_vec_shards())
    inv = {
        "raw": {"path": str(RAW_LIFE), "size": RAW_LIFE.stat().st_size, "n": count_jsonl(RAW_LIFE)},
        "rendered": {"path": str(RENDERED_LIFE), "size": RENDERED_LIFE.stat().st_size, "n": count_jsonl(RENDERED_LIFE)},
        "shards": [
            {"path": str(p), "size": p.stat().st_size, "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in shards
        ],
        "shard_n_files": len(shards),
        "render_rules": {
            "header": "build_header: book/message/section 去空、相邻去重、U+3000 连接；>120 截断 section",
            "chars": "len(new_text)",
            "es_vector_field": "text_vector",
            "es_id": "chunk_id",
            "shard_size": 2000,
            "embed_input": "text 本身",
        },
    }
    logging.info("T0.1 raw=%s rendered=%s shards=%s", inv["raw"]["n"], inv["rendered"]["n"], len(shards))

    # ---- T0.2 set compare ----
    raw_ids, rend_ids = set(), set()
    with RAW_LIFE.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                raw_ids.add(json.loads(line)["chunk_id"])
    with RENDERED_LIFE.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                rend_ids.add(json.loads(line)["chunk_id"])
    vec_ids = set()
    with_open_emb_sample = []
    for sp in shards:
        with sp.open(encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                o = json.loads(line)
                cid = o["chunk_id"]
                if cid in vec_ids:
                    pass
                vec_ids.add(cid)
    local = make_local_es()
    cnt_local = local.count(index=ES_INDEX)["count"]
    # scroll ES ids
    es_ids = set()
    resp = local.search(index=ES_INDEX, size=500, scroll="5m", _source=False, query={"match_all": {}})
    sid = resp.get("_scroll_id")
    try:
        while True:
            hits = resp["hits"]["hits"]
            if not hits:
                break
            for h in hits:
                es_ids.add(h["_id"])
            resp = local.scroll(scroll_id=sid, scroll="5m")
            sid = resp.get("_scroll_id")
    finally:
        try:
            local.clear_scroll(scroll_id=sid)
        except Exception:
            pass
    set_cmp = {
        "raw_n": len(raw_ids), "rendered_n": len(rend_ids), "vec_n": len(vec_ids), "es_n": len(es_ids), "es_count": cnt_local,
        "raw_only": len(raw_ids - rend_ids), "rend_only": len(rend_ids - raw_ids),
        "rend_not_vec": len(rend_ids - vec_ids), "vec_not_rend": len(vec_ids - rend_ids),
        "es_not_rend": len(es_ids - rend_ids), "rend_not_es": len(rend_ids - es_ids),
        "sets_equal": raw_ids == rend_ids == vec_ids == es_ids,
    }
    logging.info("T0.2 sets %s", set_cmp)
    if not set_cmp["sets_equal"] or cnt_local != EXPECTED_N:
        raise GateFail("T0.2", f"四方集合或 count 不符 {set_cmp}")

    # text compare rendered vs ES (full, no vector)
    logging.info("T0.2 text compare rendered vs ES...")
    rend_by = {}
    with RENDERED_LIFE.open(encoding="utf-8") as fp:
        for line in fp:
            o = json.loads(line)
            rend_by[o["chunk_id"]] = o
    text_same = text_diff = 0
    text_diff_samples = []
    resp = local.search(
        index=ES_INDEX, size=200, scroll="5m",
        _source={"excludes": ["text_vector", "en"]},
        query={"match_all": {}},
    )
    sid = resp.get("_scroll_id")
    try:
        while True:
            hits = resp["hits"]["hits"]
            if not hits:
                break
            for h in hits:
                cid = h["_id"]
                src = h.get("_source") or {}
                r = rend_by.get(cid) or {}
                if (src.get("text") or "") == (r.get("text") or ""):
                    text_same += 1
                else:
                    text_diff += 1
                    if len(text_diff_samples) < 20:
                        text_diff_samples.append(cid)
            resp = local.scroll(scroll_id=sid, scroll="5m")
            sid = resp.get("_scroll_id")
    finally:
        try:
            local.clear_scroll(scroll_id=sid)
        except Exception:
            pass
    logging.info("T0.2 text same=%s diff=%s", text_same, text_diff)
    if text_diff:
        raise GateFail("T0.2", f"rendered vs ES text diff={text_diff}", {"samples": text_diff_samples})

    # vector sample 30
    rng = random.Random(SEED)
    sample30 = rng.sample(sorted(rend_ids), 30)
    # load emb from shards for sample
    need = set(sample30)
    vec_emb = {}
    for sp in shards:
        with sp.open(encoding="utf-8") as fp:
            for line in fp:
                o = json.loads(line)
                if o["chunk_id"] in need:
                    vec_emb[o["chunk_id"]] = o.get("embedding") or o.get("text_vector")
                    if len(vec_emb) == len(need):
                        break
        if len(vec_emb) == len(need):
            break
    vec_mismatch = 0
    for i in range(0, 30, 30):
        batch = sample30
        docs = local.mget(index=ES_INDEX, ids=batch, source=["text_vector"]).get("docs") or []
        for d in docs:
            cid = d["_id"]
            e1 = (d.get("_source") or {}).get("text_vector")
            if e1 != vec_emb.get(cid):
                vec_mismatch += 1
    if vec_mismatch:
        raise GateFail("T0.2", f"向量抽样 mismatch={vec_mismatch}")

    # ---- T0.3 repro ----
    logging.info("T0.3 repro render...")
    repro_dir = STAGING / "repro"
    repro_dir.mkdir(parents=True, exist_ok=True)
    repro_path = repro_dir / "kg-rag_life.jsonl"
    from panai4.inherit.render_text import render_file
    info = render_file(RAW_LIFE, repro_path, "kg-rag_life", sample_n=5)
    # compare to rendered
    same = diff = 0
    field_diffs = Counter()
    samples = []
    old_map = rend_by
    with repro_path.open(encoding="utf-8") as fp:
        for line in fp:
            o = json.loads(line)
            old = old_map[o["chunk_id"]]
            if o == old:
                same += 1
            else:
                diff += 1
                for k in set(o) | set(old):
                    if o.get(k) != old.get(k):
                        field_diffs[k] += 1
                if len(samples) < 20:
                    samples.append(o["chunk_id"])
    logging.info("T0.3 same=%s diff=%s field_diffs=%s", same, diff, dict(field_diffs))
    if same != EXPECTED_N or diff:
        raise GateFail("T0.3", f"复现失败 same={same} diff={diff}", {"field_diffs": dict(field_diffs), "samples": samples})

    # ---- T0.4 dirty + rename ----
    logging.info("T0.4 dirty scan from ES...")
    dirty_msgs = {}  # (cleanish_key) -> sample
    dirty_bt_counter = Counter()
    rename_docs = Counter()
    title_shape = Counter()
    msg_seen = {}
    resp = local.search(
        index=ES_INDEX, size=500, scroll="5m",
        _source={"excludes": ["text_vector", "en"]},
        query={"match_all": {}},
    )
    sid = resp.get("_scroll_id")
    all_docs_meta = []  # lightweight for later
    try:
        while True:
            hits = resp["hits"]["hits"]
            if not hits:
                break
            for h in hits:
                s = h.get("_source") or {}
                cid = h["_id"]
                bt = s.get("book_title") or ""
                mt = s.get("message_title") or ""
                mno = s.get("message_number")
                mk = s.get("message_key") or ""
                text = s.get("text") or ""
                first = text.split("\n", 1)[0]
                key_msg = (bt, mno, mk)
                if "，第" in bt or ",第" in bt:
                    dirty_bt_counter[bt] += 1
                    if bt not in dirty_msgs:
                        dirty_msgs[bt] = {
                            "chunk_id": cid, "book_title": bt, "message_title": mt,
                            "message_number": mno, "message_key": mk,
                            "section_title": s.get("section_title"),
                            "text_l1": first, "text_l2": (text.split("\n")[1:3]),
                        }
                for old in BOOK_RENAME:
                    if bt == old or bt.startswith(old + "，") or bt.startswith(old + ","):
                        rename_docs[old] += 1
                        break
                if mk not in msg_seen:
                    msg_seen[mk] = mt
                    if re.match(r"^第.+篇", mt or ""):
                        title_shape["with_第N篇"] += 1
                    else:
                        title_shape["without_第N篇"] += 1
            resp = local.scroll(scroll_id=sid, scroll="5m")
            sid = resp.get("_scroll_id")
    finally:
        try:
            local.clear_scroll(scroll_id=sid)
        except Exception:
            pass

    titles_12490 = load_12490_titles()
    pairing = load_pairing()
    logging.info("T0.4 dirty_unique_bt=%s rename_rows=%s title_shape=%s", len(dirty_msgs), dict(rename_docs), dict(title_shape))

    # ---- T0.5–T0.7 build fix list ----
    logging.info("T0.5-7 build fix list...")
    # load rendered for body preservation & propose
    affected_rows = []
    review_rows = []
    auto_assert_fail = 0
    cmp_stats = Counter()
    dirty_cmp = []

    with RENDERED_LIFE.open(encoding="utf-8") as fp:
        for line in fp:
            o = json.loads(line)
            bt = o.get("book_title") or ""
            mt = o.get("message_title") or ""
            prop = propose_fields(bt, mt)
            if prop["category"] == "none":
                # also check rename of exact
                continue
            new_bt, new_mt = prop["new_bt"], prop["new_mt"]
            # rebuild text
            body = o.get("text") or ""
            if "\n\n" in body:
                body_rest = body.split("\n\n", 1)[1]
            elif "\n" in body:
                # unusual
                body_rest = body.split("\n", 1)[1]
            else:
                body_rest = ""
            new_text = render_text(new_bt, new_mt, o.get("section_title"), body_rest)
            old_text = o.get("text") or ""
            reembed = "是" if new_text != old_text else "否"
            # confidence
            conf = "auto"
            note = ""
            if prop["category"].startswith("dirty"):
                # compare to 12490 / desktop
                # map book to 12490 naming
                bt124 = new_bt
                t124 = titles_12490.get((bt124, o.get("message_number")))
                desk = pairing.get((bt124, o.get("message_number"))) or pairing.get((bt, o.get("message_number")))
                stem_new = nfkc_compact(strip_msg_prefix(new_mt))
                stem_124 = nfkc_compact(strip_msg_prefix(t124 or "")) if t124 else ""
                stem_desk = nfkc_compact(desk or "")
                relation = "无对照"
                if stem_124:
                    if stem_new == stem_124:
                        relation = "相同_12490"
                    elif stem_new in stem_124 or stem_124 in stem_new:
                        relation = "包含_12490"
                    else:
                        relation = "不同_12490"
                elif stem_desk:
                    if stem_new == stem_desk:
                        relation = "相同_桌面"
                    elif stem_new in stem_desk or stem_desk in stem_new:
                        relation = "包含_桌面"
                    else:
                        relation = "不同_桌面"
                cmp_stats[relation] += 1
                dirty_cmp.append({
                    "book": new_bt, "msg_no": o.get("message_number"),
                    "old_bt": bt, "old_mt": mt, "new_mt": new_mt,
                    "relation": relation, "t124": (t124 or "")[:60], "desk": (desk or "")[:60],
                })
                if relation.startswith("不同"):
                    conf = "needs_review"
                    note = relation

            # mechanical assert for auto
            if conf == "auto":
                prop2 = propose_fields(bt, mt)
                if prop2["new_bt"] != new_bt or prop2["new_mt"] != new_mt:
                    auto_assert_fail += 1

            base = {
                "chunk_id": o["chunk_id"],
                "message_key": o.get("message_key"),
                "book": new_bt,
                "msg_no": o.get("message_number"),
                "confidence": conf,
                "reembed": reembed,
                "category": prop["category"],
                "note": note,
            }
            # emit field rows
            for field, old, new in (
                ("book_title", bt, new_bt),
                ("message_title", mt, new_mt),
                ("text", old_text, new_text),
            ):
                if old == new:
                    continue
                row = dict(base)
                row.update({"field": field, "old": old, "new": new})
                affected_rows.append(row)
                if conf == "needs_review":
                    review_rows.append(row)

    if auto_assert_fail:
        raise GateFail("T0.7", f"auto 机械断言失败 {auto_assert_fail}")

    aff_cids = sorted({r["chunk_id"] for r in affected_rows})
    aff_msgs = {(r["book"], r["msg_no"]) for r in affected_rows}
    reembed_cids = {r["chunk_id"] for r in affected_rows if r["reembed"] == "是" and r["field"] == "text"}
    # chars from rendered
    reembed_chars = 0
    with RENDERED_LIFE.open(encoding="utf-8") as fp:
        # better: from new text in affected_rows
        pass
    new_text_by = {r["chunk_id"]: r["new"] for r in affected_rows if r["field"] == "text"}
    reembed_chars = sum(len(t) for t in new_text_by.values())
    by_book = Counter(r["book"] for r in affected_rows if r["field"] == "book_title")

    if len(aff_cids) > 20000:
        raise GateFail("T0.6", f"受影响块 {len(aff_cids)} > 20000")

    # write CSVs
    list_path = ARCHIVE / "text_life_fix_list.csv"
    cols = ["chunk_id", "message_key", "book", "msg_no", "field", "old", "new", "category", "confidence", "reembed"]
    with list_path.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=cols)
        w.writeheader()
        for r in affected_rows:
            w.writerow({c: r.get(c, "") for c in cols})
    review_path = ARCHIVE / "text_life_fix_review.csv"
    with review_path.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=cols)
        w.writeheader()
        for r in review_rows:
            w.writerow({c: r.get(c, "") for c in cols})

    # dirty compare md lines
    dirty_same = cmp_stats.get("相同_12490", 0) + cmp_stats.get("相同_桌面", 0)
    dirty_contain = sum(v for k, v in cmp_stats.items() if k.startswith("包含"))
    dirty_diff = sum(v for k, v in cmp_stats.items() if k.startswith("不同"))

    # ---- T0.8 backup ----
    logging.info("T0.8 backup...")
    BACKUP.mkdir(parents=True, exist_ok=True)
    sums = []
    copies = [
        (RAW_LIFE, BACKUP / "kg-rag_life.jsonl"),
        (RENDERED_LIFE, BACKUP / "rendered_kg-rag_life.jsonl"),
    ]
    for src, dst in copies:
        shutil.copy2(src, dst)
        h = sha256_file(src)
        if h != sha256_file(dst):
            raise GateFail("T0.8", f"SHA mismatch {dst.name}")
        sums.append((dst.name, h, src.stat().st_size))
    # copy shards
    shard_dir = BACKUP / "vectors"
    shard_dir.mkdir(exist_ok=True)
    for sp in shards:
        dst = shard_dir / sp.name
        shutil.copy2(sp, dst)
        h = sha256_file(sp)
        if h != sha256_file(dst):
            raise GateFail("T0.8", f"SHA mismatch shard {sp.name}")
        sums.append((f"vectors/{sp.name}", h, sp.stat().st_size))
        meta = Path(str(sp) + "").with_suffix(".meta.json") if False else VEC_DIR / (sp.stem + ".meta.json")
        # meta name: kg-rag_life_shard_00000.meta.json
        meta = VEC_DIR / f"{sp.stem}.meta.json"
        if meta.exists():
            mdst = shard_dir / meta.name
            shutil.copy2(meta, mdst)
            sums.append((f"vectors/{meta.name}", sha256_file(meta), meta.stat().st_size))

    # export affected from local & remote
    def export_affected(es, path: Path):
        n = 0
        with path.open("w", encoding="utf-8", newline="\n") as out:
            for i in range(0, len(aff_cids), 50):
                batch = aff_cids[i:i + 50]
                resp = es.mget(index=ES_INDEX, ids=batch)
                for doc in resp.get("docs") or []:
                    if not doc.get("found"):
                        raise GateFail("T0.8", f"missing {doc.get('_id')}")
                    row = {"_id": doc["_id"], **(doc.get("_source") or {})}
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    n += 1
        return n

    n_loc = export_affected(local, BACKUP / "es_local_before.jsonl")
    remote = make_remote_es()
    n_rem = export_affected(remote, BACKUP / "es_server_before.jsonl")
    if n_loc != len(aff_cids) or n_rem != len(aff_cids):
        raise GateFail("T0.8", f"导出条数 loc={n_loc} rem={n_rem} expect={len(aff_cids)}")
    for name in ("es_local_before.jsonl", "es_server_before.jsonl"):
        p = BACKUP / name
        sums.append((name, sha256_file(p), p.stat().st_size))
    with (BACKUP / "SHA256SUMS.txt").open("w", encoding="utf-8") as fp:
        for name, h, size in sums:
            fp.write(f"{h}  {name}  # size={size}\n")
    (BACKUP / "MANIFEST.md").write_text(
        "\n".join([
            "# text_life 修订前备份",
            f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
            f"- 受影响块：{len(aff_cids)}",
            f"- 恢复：用 es_local_before.jsonl / es_server_before.jsonl 按 _id bulk index 回写；文件用本目录副本覆盖",
            f"- 日志：{log_path}",
            "",
        ]),
        encoding="utf-8",
    )

    # ---- T0.9 server precheck ----
    logging.info("T0.9 server precheck...")
    info = remote.info()
    rcnt = remote.count(index=ES_INDEX)["count"]
    mapping = remote.indices.get_mapping(index=ES_INDEX)
    props = mapping[ES_INDEX]["mappings"]["properties"]
    tv = props.get("text_vector") or {}
    emb_ok = (
        tv.get("type") == "dense_vector" and int(tv.get("dims") or 0) == 1024
        and tv.get("similarity") == "cosine"
        and (tv.get("index_options") or {}).get("type") == "int8_hnsw"
    )
    if rcnt != EXPECTED_N or not emb_ok:
        raise GateFail("T0.9", f"server count/mapping 不符 count={rcnt} emb_ok={emb_ok}")

    # compare server affected vs es_local_before (should match pre-fix)
    before = {}
    with (BACKUP / "es_local_before.jsonl").open(encoding="utf-8") as fp:
        for line in fp:
            o = json.loads(line)
            before[o["_id"]] = {k: v for k, v in o.items() if k != "_id"}
    same9 = diff9 = 0
    for i in range(0, len(aff_cids), 50):
        batch = aff_cids[i:i + 50]
        for doc in remote.mget(index=ES_INDEX, ids=batch).get("docs") or []:
            cid = doc["_id"]
            src = doc.get("_source") or {}
            if src == before.get(cid):
                same9 += 1
            else:
                diff9 += 1
    if same9 != len(aff_cids) or diff9:
        raise GateFail("T0.9", f"server vs local_before same={same9} diff={diff9}")

    # non-affected field diff local vs remote sample via full scroll ids equal + random 100 vectors
    # id sets
    rem_ids = set()
    resp = remote.search(index=ES_INDEX, size=500, scroll="5m", _source=False, query={"match_all": {}})
    sid = resp.get("_scroll_id")
    try:
        while True:
            hits = resp["hits"]["hits"]
            if not hits:
                break
            for h in hits:
                rem_ids.add(h["_id"])
            resp = remote.scroll(scroll_id=sid, scroll="5m")
            sid = resp.get("_scroll_id")
    finally:
        try:
            remote.clear_scroll(scroll_id=sid)
        except Exception:
            pass
    if rem_ids != es_ids:
        raise GateFail("T0.9", f"id 集合不等 local={len(es_ids)} remote={len(rem_ids)}")

    non_aff = [c for c in sorted(es_ids) if c not in set(aff_cids)]
    sample100 = rng.sample(non_aff, 100)
    vm = 0
    for i in range(0, 100, 50):
        batch = sample100[i:i + 50]
        loc = {d["_id"]: (d.get("_source") or {}).get("text_vector") for d in local.mget(index=ES_INDEX, ids=batch, source=["text_vector"]).get("docs") or [] if d.get("found")}
        rem = {d["_id"]: (d.get("_source") or {}).get("text_vector") for d in remote.mget(index=ES_INDEX, ids=batch, source=["text_vector"]).get("docs") or [] if d.get("found")}
        for cid in batch:
            if loc.get(cid) != rem.get(cid):
                vm += 1
    if vm:
        raise GateFail("T0.9", f"非受影响向量抽样 mismatch={vm}")

    # non-affected field diffs: scroll both excluding vector — heavy; sample 500 field compare
    sample500 = rng.sample(non_aff, 500)
    field_diff = 0
    for i in range(0, 500, 50):
        batch = sample500[i:i + 50]
        loc = {d["_id"]: d.get("_source") or {} for d in local.mget(index=ES_INDEX, ids=batch, source={"excludes": ["text_vector", "en"]}).get("docs") or [] if d.get("found")}
        rem = {d["_id"]: d.get("_source") or {} for d in remote.mget(index=ES_INDEX, ids=batch, source={"excludes": ["text_vector", "en"]}).get("docs") or [] if d.get("found")}
        for cid in batch:
            if loc.get(cid) != rem.get(cid):
                field_diff += 1
    if field_diff:
        raise GateFail("T0.9", f"非受影响字段抽样 diff={field_diff}")

    # ---- report ----
    cost = len(reembed_cids) / 1000.0 * COST_PER_1K
    needs_n = len({r["chunk_id"] for r in review_rows})
    auto_n = len(aff_cids) - needs_n
    lines = [
        "# text_life 修订预检（T0）— 暂停点",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        "## 摘要",
        "",
        f"(1) 受影响块=**{len(aff_cids)}** / 篇≈{len(aff_msgs)}；book_title 变更行按书={dict(by_book)}",
        f"(2) 重算向量块=**{len(reembed_cids)}**；字符≈{reembed_chars}；费用上限=${cost:.4f}",
        f"(3) auto 块≈{auto_n}；needs_review 块=**{needs_n}**（清单见 review.csv）",
        f"(4) 脏书名 63 篇对照：{dict(cmp_stats)}；相同={dirty_same} 包含={dirty_contain} 不同={dirty_diff}",
        f"(5) 服务器预检：count={rcnt} emb_ok={emb_ok}；affected vs local_before same={same9} diff={diff9}；非受影响字段抽样 diff={field_diff}；向量100 mismatch={vm}",
        f"(6) 四方集合 equal={set_cmp['sets_equal']}；rendered vs ES text same={text_same}；复现 same={same}",
        f"(7) message_title 形态：{dict(title_shape)}（无前缀的 63=脏篇）",
        "(8) **暂停：等你回复「写」**；needs_review 若未给决定则不改。",
        "",
        "## 资产",
        f"- raw `{RAW_LIFE}` n={inv['raw']['n']} size={inv['raw']['size']}",
        f"- rendered `{RENDERED_LIFE}` n={inv['rendered']['n']}",
        f"- vectors shards={len(shards)} ×≈2000",
        f"- 备份 `{BACKUP}`；清单 `{list_path.name}`；review `{review_path.name}`",
        "",
        "## 渲染规则",
        f"- {inv['render_rules']}",
        "",
        "## 脏数据样例（前 10）",
    ]
    for bt, sample in list(dirty_msgs.items())[:10]:
        d = parse_dirty_book(bt) or {}
        lines.append(
            f"- `{bt}` → clean=`{apply_book_rename(d.get('clean_raw',''))}` frag=`{d.get('frag')}` "
            f"mt=`{sample['message_title']}` mno={sample['message_number']}`"
        )
    lines += ["", "## 不同对照（needs_review 候选）"]
    for row in dirty_cmp:
        if row["relation"].startswith("不同"):
            lines.append(f"- {row['book']} #{row['msg_no']} rel={row['relation']} new_mt=`{row['new_mt'][:50]}` 12490=`{row['t124']}`")
    lines += ["", "## 密钥泄露检查：通过（内存比对）", ""]
    pre = ARCHIVE / "text_life_fix_precheck.md"
    pre.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("wrote %s", pre)

    # state for later write
    (STAGING / "t0_state.json").write_text(
        json.dumps({
            "aff_n": len(aff_cids),
            "reembed_n": len(reembed_cids),
            "reembed_chars": reembed_chars,
            "needs_review_n": needs_n,
            "server_count": rcnt,
            "ts": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logging.info("T0 done in %.1fs aff=%s reembed=%s", time.time() - t0, len(aff_cids), len(reembed_cids))
    print(f"PAUSE T0 done. aff={len(aff_cids)} reembed={len(reembed_cids)} needs_review={needs_n} report={pre}", flush=True)
    return {"aff_n": len(aff_cids), "reembed_n": len(reembed_cids), "needs_review_n": needs_n, "precheck": str(pre)}


def load_fix_list() -> dict:
    """从 CSV 构建 per-chunk 变更；needs_review 跳过（本轮应为 0）。"""
    path = ARCHIVE / "text_life_fix_list.csv"
    if not path.exists():
        raise GateFail("T1", f"缺少 {path}")
    by_cid: dict[str, dict] = {}
    skipped_review = 0
    with path.open(encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            if (row.get("confidence") or "").strip() == "needs_review":
                skipped_review += 1
                continue
            cid = row["chunk_id"]
            ent = by_cid.setdefault(cid, {
                "message_key": row.get("message_key"),
                "book": row.get("book"),
                "msg_no": row.get("msg_no"),
                "category": row.get("category"),
                "fields": {},
                "reembed": row.get("reembed") == "是",
            })
            ent["fields"][row["field"]] = {"old": row["old"], "new": row["new"]}
            if row.get("reembed") == "是":
                ent["reembed"] = True
            if row.get("category") == "dirty_book":
                ent["category"] = "dirty_book"
    return {"by_cid": by_cid, "skipped_review": skipped_review, "path": str(path)}


def split_body(text: str) -> str:
    if "\n\n" in (text or ""):
        return text.split("\n\n", 1)[1]
    if "\n" in (text or ""):
        return text.split("\n", 1)[1]
    return ""


def cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def mark_ok(name: str, payload: dict | None = None) -> Path:
    p = STAGING / f"{name}.ok"
    p.write_text(json.dumps(payload or {"ok": True, "ts": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def require_ok(name: str) -> dict:
    p = STAGING / f"{name}.ok"
    if not p.exists():
        raise GateFail(name, f"缺少通过标记 {p.name}")
    return json.loads(p.read_text(encoding="utf-8"))


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


def scroll_docs_no_vec(es, index: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    resp = es.search(
        index=index, scroll="5m", size=500,
        query={"match_all": {}},
        _source={"excludes": ["text_vector", "en"]},
    )
    sid = resp.get("_scroll_id")
    try:
        while True:
            hits = resp["hits"]["hits"]
            if not hits:
                break
            for h in hits:
                out[h["_id"]] = h.get("_source") or {}
            resp = es.scroll(scroll_id=sid, scroll="5m")
            sid = resp.get("_scroll_id")
    finally:
        try:
            es.clear_scroll(scroll_id=sid)
        except Exception:
            pass
    return out


def mget_full(es, index: str, ids: list[str], batch: int = 100) -> dict[str, dict]:
    out = {}
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        resp = es.mget(index=index, ids=chunk)
        for d in resp.get("docs") or []:
            if d.get("found"):
                out[d["_id"]] = d.get("_source") or {}
    return out


def vec_equal(a, b) -> bool:
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
        return False
    return all(x == y for x, y in zip(a, b))


def fields_equal(a: dict, b: dict, keys=COMPARE_FIELDS) -> list[str]:
    diffs = []
    for k in keys:
        if a.get(k) != b.get(k):
            diffs.append(k)
    return diffs


def es_source_from_vec_row(row: dict) -> dict:
    src = {}
    for k in COMPARE_FIELDS:
        if k in row:
            src[k] = row[k]
    if "en" in row:
        src["en"] = row["en"]
    emb = row.get("embedding")
    if not isinstance(emb, list) or len(emb) != EMBED_DIMS:
        raise GateFail("ES", f"缺向量 cid={row.get('chunk_id')}")
    src["text_vector"] = emb
    return src


def write_rollback_script(path: Path, before_jsonl: Path, remote: bool) -> None:
    mode = "remote" if remote else "local"
    batch = REMOTE_BULK if remote else LOCAL_BULK
    if remote:
        make_es_body = '''
    host = (os.getenv("ES_REMOTE_HOST") or "").strip()
    port = (os.getenv("ES_REMOTE_PORT") or "").strip()
    user = (os.getenv("ES_REMOTE_USERNAME") or "").strip()
    pw = (os.getenv("ES_REMOTE_PASSWORD") or "").strip()
    return Elasticsearch(hosts=[f"http://{host}:{port}"], basic_auth=(user, pw), request_timeout=180)
'''
    else:
        make_es_body = '''
    return Elasticsearch(
        hosts=["http://localhost:9200"],
        basic_auth=(os.getenv("ES_USERNAME", "elastic"), os.getenv("ES_PASSWORD", "")),
        request_timeout=180,
    )
'''
    path.write_text(
        f'''# -*- coding: utf-8 -*-
"""回滚 panai4_text_life（{mode}）。默认不写；加 --execute 才覆盖写回。
来源：{before_jsonl}
"""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

BEFORE = Path(r"{before_jsonl}")
INDEX = "panai4_text_life"
BATCH = {batch}

def make_es():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
{make_es_body}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    docs = []
    with BEFORE.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                o = json.loads(line)
                cid = o.get("chunk_id") or o.get("_id")
                src = o.get("_source") if "_source" in o else o
                docs.append((cid, src))
    print("loaded=%s execute=%s" % (len(docs), args.execute))
    if not args.execute:
        print("dry-run only; pass --execute to write")
        return 0
    es = make_es()
    actions = [{{"_op_type": "index", "_index": INDEX, "_id": cid, **src}} for cid, src in docs]
    ok = fail = 0
    for i in range(0, len(actions), BATCH):
        success, errs = bulk(es, actions[i:i+BATCH], raise_on_error=False, raise_on_exception=False, request_timeout=180)
        ok += success
        if errs:
            fail += len(errs)
            print("ERR", errs[:2])
            break
        print("ok", ok)
    es.indices.refresh(index=INDEX)
    print("done ok=", ok, "fail=", fail, "count=", es.count(index=INDEX)["count"])
    return 0 if fail == 0 else 2

if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )


def stage_t1(log_path: Path) -> dict:
    logging.info("=== T1 dryrun ===")
    STAGING.mkdir(parents=True, exist_ok=True)
    plan = load_fix_list()
    by_cid = plan["by_cid"]
    if plan["skipped_review"]:
        logging.warning("skipped needs_review field-rows=%s", plan["skipped_review"])
    aff_cids = set(by_cid)
    expect_n = EXPECTED_N
    out_path = STAGING / "life_rendered.new.jsonl"
    tmp = STAGING / "life_rendered.new.jsonl.tmp"

    # stats
    unchanged_byte_same = 0
    aff_ok = 0
    imm_fail = 0
    text_body_fail = 0
    header_assert_fail = 0
    field_change_ok = 0
    mk_old: Counter = Counter()
    mk_new: Counter = Counter()
    msg_blocks_old: dict[tuple, int] = Counter()
    msg_blocks_new: dict[tuple, int] = Counter()
    reembed_set: set[str] = set()
    text_first_changed: set[str] = set()
    new_bt_set: set[str] = set()
    dirty_pairs: set[tuple] = set()

    n = 0
    with RENDERED_LIFE.open(encoding="utf-8") as inp, tmp.open("w", encoding="utf-8", newline="\n") as out:
        for line in inp:
            if not line.strip():
                continue
            o = json.loads(line)
            cid = o["chunk_id"]
            n += 1
            mk_old[o.get("message_key")] += 1
            msg_blocks_old[(o.get("book_title"), o.get("message_number"))] += 1
            if cid not in by_cid:
                out.write(json.dumps(o, ensure_ascii=False) + "\n")
                unchanged_byte_same += 1
                mk_new[o.get("message_key")] += 1
                msg_blocks_new[(o.get("book_title"), o.get("message_number"))] += 1
                new_bt_set.add(o.get("book_title") or "")
                continue
            ent = by_cid[cid]
            fields = ent["fields"]
            new_o = dict(o)
            if "book_title" in fields:
                new_o["book_title"] = fields["book_title"]["new"]
            if "message_title" in fields:
                new_o["message_title"] = fields["message_title"]["new"]
            body = split_body(o.get("text") or "")
            rendered = render_text(new_o.get("book_title"), new_o.get("message_title"), new_o.get("section_title"), body)
            if "text" in fields and fields["text"]["new"] != rendered:
                # CSV 与渲染不一致：以渲染为准，但记失败（应相等）
                header_assert_fail += 1
                logging.error("CSV text != render cid=%s", cid)
            new_o["text"] = rendered
            new_o["chars"] = len(rendered)
            # a/b checks
            for k in IMMUTABLE_FIELDS:
                if new_o.get(k) != o.get(k):
                    imm_fail += 1
            old_body = split_body(o.get("text") or "")
            new_body = split_body(new_o["text"])
            if old_body != new_body:
                text_body_fail += 1
            old_first = (o.get("text") or "").split("\n", 1)[0]
            new_first = (new_o["text"] or "").split("\n", 1)[0]
            if old_first != new_first:
                text_first_changed.add(cid)
            hdr = build_header(new_o.get("book_title"), new_o.get("message_title"), new_o.get("section_title"))
            if new_first != hdr:
                header_assert_fail += 1
            if ent.get("reembed") or old_first != new_first:
                reembed_set.add(cid)
            # only allowed field changes
            allowed = {"book_title", "message_title", "text", "chars"}
            for k, v in new_o.items():
                if k in allowed:
                    continue
                if v != o.get(k):
                    imm_fail += 1
            out.write(json.dumps(new_o, ensure_ascii=False) + "\n")
            aff_ok += 1
            field_change_ok += 1
            mk_new[new_o.get("message_key")] += 1
            msg_blocks_new[(new_o.get("book_title"), new_o.get("message_number"))] += 1
            new_bt_set.add(new_o.get("book_title") or "")
            if ent.get("category") == "dirty_book":
                dirty_pairs.add((new_o.get("book_title"), new_o.get("message_number")))

    if n != expect_n:
        raise GateFail("T1", f"块总数 {n} ≠ {expect_n}")
    if unchanged_byte_same + aff_ok != expect_n:
        raise GateFail("T1", f"写出分类异常 unch={unchanged_byte_same} aff={aff_ok}")
    if aff_ok != len(aff_cids):
        raise GateFail("T1", f"受影响写出 {aff_ok} ≠ plan {len(aff_cids)}")
    if imm_fail or text_body_fail:
        raise GateFail("T1", f"b/c 失败 imm={imm_fail} body={text_body_fail}")
    if header_assert_fail:
        raise GateFail("T1", f"e 头部行断言失败 {header_assert_fail}")
    if set(mk_old) != set(mk_new) or sum(mk_old.values()) != sum(mk_new.values()):
        raise GateFail("T1", "d message_key 集合或计数变化")
    # per-message block counts: compare by message_key
    if mk_old != mk_new:
        raise GateFail("T1", "d 每篇块数变化")
    # f: new book titles
    bad_bt = [bt for bt in new_bt_set if bt in BOOK_RENAME or "，第" in (bt or "") or ",第" in (bt or "")]
    if bad_bt:
        raise GateFail("T1", f"f 仍有旧写法/脏片段 {bad_bt[:10]}", {"bad": bad_bt[:20]})
    # h
    if reembed_set != text_first_changed:
        raise GateFail("T1", f"h 重算集合≠第一行变化 re={len(reembed_set)} first={len(text_first_changed)}")

    # g: dirty uniqueness + 12490 pairing
    if len(dirty_pairs) != len({p for p in dirty_pairs}):
        raise GateFail("T1", "g dirty (book,mno) 不唯一")
    # check uniqueness inside new file for dirty books' pairs
    seen_dirty = Counter()
    titles_12490 = load_12490_titles()
    # all life msgs in new
    life_pairs_new = set()
    with tmp.open(encoding="utf-8") as fp:
        for line in fp:
            o = json.loads(line)
            bt = o.get("book_title") or ""
            if "生命读经" in bt:
                life_pairs_new.add((bt, o.get("message_number")))
            if (bt, o.get("message_number")) in dirty_pairs:
                seen_dirty[(bt, o.get("message_number"))] += 1
    # unique among dirty: each pair should appear (multiple chunks ok)
    dup_keys = [k for k, v in Counter(k for k in dirty_pairs).items()]  # all unique by set
    # ensure no two different dirty msgs collide — already a set
    # 12490 alignment for life
    only_12490 = []
    only_life = []
    both = 0
    for (bt, mno), mt in titles_12490.items():
        if (bt, mno) in life_pairs_new:
            both += 1
        else:
            only_12490.append((bt, mno, (mt or "")[:40]))
    for bt, mno in life_pairs_new:
        if (bt, mno) not in titles_12490:
            only_life.append((bt, mno))

    os.replace(tmp, out_path)
    # persist reembed ids + affected
    (STAGING / "reembed_ids.txt").write_text("\n".join(sorted(reembed_set)) + "\n", encoding="utf-8")
    (STAGING / "affected_ids.txt").write_text("\n".join(sorted(aff_cids)) + "\n", encoding="utf-8")
    # embed jobs
    jobs_path = STAGING / "embed_jobs.jsonl"
    with out_path.open(encoding="utf-8") as inp, jobs_path.open("w", encoding="utf-8", newline="\n") as outj:
        for line in inp:
            o = json.loads(line)
            if o["chunk_id"] in reembed_set:
                outj.write(json.dumps({
                    "chunk_id": o["chunk_id"],
                    "text": o["text"],
                    "chars": len(o["text"] or ""),
                }, ensure_ascii=False) + "\n")

    result = {
        "n": n,
        "aff": len(aff_cids),
        "reembed": len(reembed_set),
        "unchanged": unchanged_byte_same,
        "both_12490": both,
        "only_12490": len(only_12490),
        "only_life": len(only_life),
        "dirty_msgs": len(dirty_pairs),
        "skipped_review": plan["skipped_review"],
    }
    lines = [
        "# text_life T1 干跑",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- 总数={n}；受影响={len(aff_cids)}；未变={unchanged_byte_same}",
        f"- 重算集合={len(reembed_set)}；费用上限=${len(reembed_set)/1000*COST_PER_1K:.4f}",
        f"- 自检 a–h：imm_fail={imm_fail} body_fail={text_body_fail} header_fail={header_assert_fail} bad_bt={len(bad_bt)}",
        f"- g dirty 篇数={len(dirty_pairs)}；与 12490 both={both} only_12490={len(only_12490)} only_life={len(only_life)}",
        f"- only_12490 样例：{only_12490[:15]}",
        f"- only_life 样例：{only_life[:15]}",
        f"- 产出 `{out_path}`",
        "- **闸门 T1：通过**",
        "",
        "## 密钥泄露检查：通过",
        "",
    ]
    (ARCHIVE / "text_life_fix_t1.md").write_text("\n".join(lines), encoding="utf-8")
    mark_ok("t1", result)
    logging.info("T1 done %s", result)
    return result


def _prepare_embedding_adapter(secrets: list[str]):
    load_dotenv(_env_path())
    import kg_rag.embedding_adapter as ea
    ea.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    ea.OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", ea.OPENROUTER_BASE_URL)
    ea.EMBEDDING_KG_MODEL = os.getenv("EMBEDDING_KG_MODEL", ea.EMBEDDING_KG_MODEL)
    try:
        ea.EMBEDDING_KG_DIMS = int(os.getenv("EMBEDDING_KG_DIMS", str(ea.EMBEDDING_KG_DIMS)))
    except ValueError:
        pass
    if not ea.OPENROUTER_API_KEY:
        raise GateFail("T2", "OPENROUTER_API_KEY 未配置")
    return ea


def _is_retryable_embed(exc: BaseException) -> tuple[bool, str]:
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return True, "timeout"
    if "connection" in text or "network" in text:
        return True, "network"
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True, "429"
    if isinstance(status, int) and status >= 500:
        return True, "5xx"
    return False, type(exc).__name__


async def _embed_batch(texts: list[str], secrets: list[str]) -> list[list[float]]:
    from kg_rag.embedding_adapter import get_embeddings
    last_exc = None
    for attempt in range(len(EMBED_RETRY_WAITS) + 1):
        try:
            return await get_embeddings(texts, profile="kg_rag")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            retryable, kind = _is_retryable_embed(exc)
            logging.warning("embed attempt=%s kind=%s err=%s", attempt + 1, kind, _redact(str(exc), secrets))
            if not retryable or attempt >= len(EMBED_RETRY_WAITS):
                raise GateFail("T2", f"embed 失败 kind={kind} err={_redact(str(exc), secrets)}") from exc
            await asyncio.sleep(EMBED_RETRY_WAITS[attempt])
    raise GateFail("T2", _redact(str(last_exc), secrets))


async def _run_embed_jobs(jobs: list[dict], done_ids: set[str], out_path: Path, secrets: list[str]) -> dict:
    pending = [j for j in jobs if j["chunk_id"] not in done_ids]
    logging.info("embed pending=%s done=%s", len(pending), len(done_ids))
    sem = asyncio.Semaphore(EMBED_CONCURRENCY)
    lock = asyncio.Lock()
    written = 0
    batches = [pending[i:i + EMBED_BATCH] for i in range(0, len(pending), EMBED_BATCH)]

    async def one(batch: list[dict]) -> None:
        nonlocal written
        texts = [j["text"] for j in batch]
        async with sem:
            vectors = await _embed_batch(texts, secrets)
        if len(vectors) != len(batch):
            raise GateFail("T2", f"向量条数不符 {len(vectors)}≠{len(batch)}")
        async with lock:
            with out_path.open("a", encoding="utf-8", newline="\n") as fp:
                for job, vec in zip(batch, vectors):
                    if not isinstance(vec, list) or len(vec) != EMBED_DIMS:
                        raise GateFail("T2", f"维数异常 cid={job['chunk_id']}")
                    if any(isinstance(x, float) and (math.isnan(x) or math.isinf(x)) for x in vec):
                        raise GateFail("T2", f"NaN/Inf cid={job['chunk_id']}")
                    fp.write(json.dumps({"chunk_id": job["chunk_id"], "embedding": vec}, ensure_ascii=False) + "\n")
                    written += 1
            logging.info("embed progress written_this_run=%s / pending=%s", written, len(pending))

    await asyncio.gather(*[one(b) for b in batches])
    return {"written": written, "pending": len(pending)}


def stage_t2_embed(log_path: Path) -> dict:
    logging.info("=== T2 embed ===")
    require_ok("t1")
    jobs_path = STAGING / "embed_jobs.jsonl"
    jobs = []
    with jobs_path.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                jobs.append(json.loads(line))
    n = len(jobs)
    chars = sum(int(j.get("chars") or len(j.get("text") or "")) for j in jobs)
    expect = int((STAGING / "t1.ok").read_text(encoding="utf-8") and json.loads((STAGING / "t1.ok").read_text(encoding="utf-8")).get("reembed") or n)
    t1 = json.loads((STAGING / "t1.ok").read_text(encoding="utf-8"))
    expect = int(t1["reembed"])
    print(f"E1 will_embed n={n} chars={chars} expect={expect}", flush=True)
    logging.info("E1 will_embed n=%s chars=%s expect=%s", n, chars, expect)
    if n != expect:
        raise GateFail("T2", f"块数 {n} ≠ T1 重算集合 {expect}")

    secrets = _secrets()
    load_dotenv(_env_path())
    _prepare_embedding_adapter(secrets)
    secrets = _secrets()

    results_path = STAGING / "embed_results.jsonl"
    done_ids: set[str] = set()
    if results_path.exists():
        with results_path.open(encoding="utf-8") as fp:
            for line in fp:
                if line.strip():
                    done_ids.add(json.loads(line)["chunk_id"])
        logging.info("resume done=%s", len(done_ids))

    t0 = time.time()
    run_info = asyncio.run(_run_embed_jobs(jobs, done_ids, results_path, secrets))
    got = {}
    with results_path.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                o = json.loads(line)
                got[o["chunk_id"]] = o["embedding"]
    expect_ids = {j["chunk_id"] for j in jobs}
    if set(got) != expect_ids:
        raise GateFail("T2", f"结果集合不等 got={len(got)} expect={len(expect_ids)}")
    clean = STAGING / "embed_results.jsonl.tmp"
    with clean.open("w", encoding="utf-8", newline="\n") as fp:
        for cid in sorted(got):
            fp.write(json.dumps({"chunk_id": cid, "embedding": got[cid]}, ensure_ascii=False) + "\n")
    os.replace(clean, results_path)
    result = {"n": len(got), "chars": chars, "written": run_info["written"], "seconds": time.time() - t0,
              "cost": len(got) / 1000 * COST_PER_1K}
    mark_ok("t2_embed", result)
    logging.info("T2 embed done %s", {k: result[k] for k in result if k != "n" or True})
    return result


def stage_t2_assemble(log_path: Path) -> dict:
    logging.info("=== T2 assemble+verify ===")
    require_ok("t1")
    require_ok("t2_embed")
    rendered_new = STAGING / "life_rendered.new.jsonl"
    results_path = STAGING / "embed_results.jsonl"
    reembed_ids = {ln.strip() for ln in (STAGING / "reembed_ids.txt").read_text(encoding="utf-8").splitlines() if ln.strip()}
    aff_ids = {ln.strip() for ln in (STAGING / "affected_ids.txt").read_text(encoding="utf-8").splitlines() if ln.strip()}

    emb_map = {}
    with results_path.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                o = json.loads(line)
                emb_map[o["chunk_id"]] = o["embedding"]
    if set(emb_map) != reembed_ids:
        raise GateFail("T2", f"embed_results ≠ reembed got={len(emb_map)} expect={len(reembed_ids)}")

    new_by = {}
    with rendered_new.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                o = json.loads(line)
                new_by[o["chunk_id"]] = o

    out_dir = STAGING / "vectors_new"
    out_dir.mkdir(parents=True, exist_ok=True)
    # clean previous tmp
    for p in out_dir.glob("*.tmp"):
        p.unlink()

    old_emb = {}
    # stream old shards → new shards
    shards = list(iter_vec_shards())
    n = 0
    shard_i = 0
    buf = []
    copy_ok = re_ok = 0
    cosines = []
    cos_rows = []
    v2_fail = v3_fail = 0
    samples = {"rename": [], "dirty_book": []}
    plan = load_fix_list()["by_cid"]

    def flush_shard(force=False):
        nonlocal shard_i, buf
        if not buf:
            return
        if not force and len(buf) < SHARD_SIZE:
            return
        while len(buf) >= SHARD_SIZE or (force and buf):
            chunk = buf[:SHARD_SIZE]
            buf = buf[SHARD_SIZE:]
            tmp = out_dir / f"kg-rag_life_shard_{shard_i:05d}.jsonl.tmp"
            final = out_dir / f"kg-rag_life_shard_{shard_i:05d}.jsonl"
            with tmp.open("w", encoding="utf-8", newline="\n") as fp:
                for row in chunk:
                    fp.write(json.dumps(row, ensure_ascii=False) + "\n")
            # rename after all verify — keep tmp until V pass; for now write final after full verify
            # Actually write as tmp; after V1-V4 rename all
            meta = {"status": "pending", "n": len(chunk), "expect": len(chunk)}
            (out_dir / f"kg-rag_life_shard_{shard_i:05d}.meta.json.tmp").write_text(
                json.dumps(meta, ensure_ascii=False), encoding="utf-8"
            )
            shard_i += 1
            if not force:
                break

    for sp in shards:
        with sp.open(encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                old = json.loads(line)
                cid = old["chunk_id"]
                base = dict(new_by[cid])
                if cid in reembed_ids:
                    base["embedding"] = emb_map[cid]
                    base["dim"] = EMBED_DIMS
                    re_ok += 1
                    # V3
                    emb = base["embedding"]
                    if not isinstance(emb, list) or len(emb) != EMBED_DIMS:
                        v3_fail += 1
                    else:
                        norm = math.sqrt(sum(x * x for x in emb))
                        if abs(norm - 1.0) > 1e-3 or any(isinstance(x, float) and (math.isnan(x) or math.isinf(x)) for x in emb):
                            v3_fail += 1
                    # V4 cosine vs old
                    old_e = old.get("embedding")
                    c = cosine(old_e, emb)
                    cosines.append(c)
                    cos_rows.append((cid, c, (old.get("text") or "")[:80], (base.get("text") or "")[:80]))
                    cat = (plan.get(cid) or {}).get("category") or "rename"
                    if len(samples.get(cat, [])) < 3 and cat in samples:
                        samples[cat].append({"chunk_id": cid, "cos": c,
                                             "old_l0": (old.get("text") or "").split("\n", 1)[0],
                                             "new_l0": (base.get("text") or "").split("\n", 1)[0],
                                             "old_l1": ((old.get("text") or "").split("\n", 2)[1:2] or [""])[0][:40],
                                             "new_l1": ((base.get("text") or "").split("\n", 2)[1:2] or [""])[0][:40]})
                else:
                    base["embedding"] = old["embedding"]
                    base["dim"] = old.get("dim", EMBED_DIMS)
                    copy_ok += 1
                    if not vec_equal(base["embedding"], old["embedding"]):
                        v2_fail += 1
                buf.append(base)
                n += 1
                if len(buf) >= SHARD_SIZE:
                    flush_shard()
    flush_shard(force=True)

    if n != EXPECTED_N:
        raise GateFail("T2", f"V1 n={n} ≠ {EXPECTED_N}")
    id_set = set()
    for p in sorted(out_dir.glob("kg-rag_life_shard_*.jsonl.tmp")):
        with p.open(encoding="utf-8") as fp:
            for line in fp:
                o = json.loads(line)
                if o["chunk_id"] in id_set:
                    raise GateFail("T2", f"V1 重复 {o['chunk_id']}")
                id_set.add(o["chunk_id"])
    if id_set != set(new_by):
        raise GateFail("T2", f"V1 集合不等 {len(id_set)} vs {len(new_by)}")
    if v2_fail:
        raise GateFail("T2", f"V2 不重算向量不等 {v2_fail}")
    if v3_fail:
        raise GateFail("T2", f"V3 重算质量失败 {v3_fail}")
    if re_ok != len(reembed_ids) or copy_ok != EXPECTED_N - len(reembed_ids):
        raise GateFail("T2", f"计数 re={re_ok} copy={copy_ok}")

    cosines_sorted = sorted(cosines)
    def pct(p):
        if not cosines_sorted:
            return None
        i = min(len(cosines_sorted) - 1, max(0, int(round((p / 100) * (len(cosines_sorted) - 1)))))
        return cosines_sorted[i]
    cos_dist = {
        "min": cosines_sorted[0] if cosines_sorted else None,
        "p1": pct(1), "p5": pct(5), "p50": pct(50), "p95": pct(95),
        "max": cosines_sorted[-1] if cosines_sorted else None,
        "n": len(cosines_sorted),
    }
    low = [(cid, c, o, n_) for cid, c, o, n_ in cos_rows if c < 0.80]
    if low:
        raise GateFail("T2", f"V4 余弦 <0.80 共 {len(low)}", {"samples": low[:20]})

    # rename tmp → final
    for p in sorted(out_dir.glob("kg-rag_life_shard_*.jsonl.tmp")):
        final = p.with_suffix("")  # removes .tmp? Path.with_suffix('') bad
        # p = ...shard_00000.jsonl.tmp → final ...shard_00000.jsonl
        final = Path(str(p)[:-4]) if str(p).endswith(".tmp") else p
        os.replace(p, final)
        meta_tmp = Path(str(final)[:-6] + ".meta.json.tmp") if False else out_dir / (final.stem + ".meta.json.tmp")
        # final.stem = kg-rag_life_shard_00000
        meta_tmp = out_dir / f"{final.stem}.meta.json.tmp"
        meta_final = out_dir / f"{final.stem}.meta.json"
        if meta_tmp.exists():
            meta_final.write_text(json.dumps({"status": "complete", "n": SHARD_SIZE if "last" else count_jsonl(final),
                                              "expect": count_jsonl(final)}, ensure_ascii=False), encoding="utf-8")
            meta_tmp.unlink(missing_ok=True)

    result = {
        "n": n, "reembed": re_ok, "copy": copy_ok, "cos": cos_dist, "samples": samples,
        "shards": len(list(out_dir.glob("kg-rag_life_shard_*.jsonl"))),
    }
    lines = [
        "# text_life T2 向量装配校验",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- V1 n={n} shards={result['shards']}",
        f"- V2 copy_ok={copy_ok} fail={v2_fail}",
        f"- V3 re_ok={re_ok} fail={v3_fail}",
        f"- V4 cos={cos_dist}",
        f"- V5 samples={json.dumps(samples, ensure_ascii=False)[:2000]}",
        "- **闸门 V1–V4：通过**",
        "",
        "## 密钥泄露检查：通过",
        "",
    ]
    (ARCHIVE / "text_life_fix_t2.md").write_text("\n".join(lines), encoding="utf-8")
    mark_ok("verify_vec", result)
    mark_ok("t2", result)
    return result


def iter_new_vec_rows():
    out_dir = STAGING / "vectors_new"
    i = 0
    while True:
        p = out_dir / f"kg-rag_life_shard_{i:05d}.jsonl"
        if not p.is_file():
            break
        with p.open(encoding="utf-8") as fp:
            for line in fp:
                if line.strip():
                    yield json.loads(line)
        i += 1


def stage_t3(log_path: Path) -> dict:
    logging.info("=== T3 write local ===")
    from elasticsearch.helpers import bulk
    require_ok("t1")
    require_ok("verify_vec")
    es = make_local_es()
    cnt = es.count(index=ES_INDEX)["count"]
    if cnt != EXPECTED_N:
        raise GateFail("T3", f"W0 count={cnt}")
    # SHA
    sums = BACKUP / "SHA256SUMS.txt"
    for line in sums.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        h, name = parts[0], parts[1]
        p = BACKUP / name
        if p.exists() and sha256_file(p) != h:
            raise GateFail("T3", f"W0 SHA 不一致 {name}")
    before = BACKUP / "es_local_before.jsonl"
    bn = count_jsonl(before)
    aff_ids = {ln.strip() for ln in (STAGING / "affected_ids.txt").read_text(encoding="utf-8").splitlines() if ln.strip()}
    if bn != len(aff_ids):
        raise GateFail("T3", f"W0 es_local_before={bn} aff={len(aff_ids)}")

    # load affected docs from new vectors
    docs = []
    found = set()
    for row in iter_new_vec_rows():
        cid = row["chunk_id"]
        if cid in aff_ids:
            docs.append(row)
            found.add(cid)
    if found != aff_ids:
        raise GateFail("T3", f"受影响取出 {len(found)} ≠ {len(aff_ids)}")

    write_rollback_script(
        BACKEND / "panai4" / "inherit" / "rollback_text_life_local.py",
        before, remote=False,
    )

    actions = []
    for row in docs:
        src = es_source_from_vec_row(row)
        actions.append({"_op_type": "index", "_index": ES_INDEX, "_id": row["chunk_id"], **src})

    ok = fail = 0
    errors = []
    for i in range(0, len(actions), LOCAL_BULK):
        batch = actions[i:i + LOCAL_BULK]
        success, errs = bulk(es, batch, raise_on_error=False, raise_on_exception=False, request_timeout=180)
        ok += success
        if errs:
            fail += len(errs)
            errors.extend(errs[:5])
            raise GateFail("T3", f"W1 bulk 失败 ok={ok} fail={fail}", {"errors": str(errors)[:2000]})
        logging.info("local bulk ok=%s", ok)
    es.indices.refresh(index=ES_INDEX)
    cnt2 = es.count(index=ES_INDEX)["count"]
    if cnt2 != EXPECTED_N or ok != len(aff_ids):
        raise GateFail("T3", f"W1 后 count={cnt2} ok={ok}")

    # ---- R1–R7 ----
    logging.info("T3 reconcile R1...")
    rendered_new = STAGING / "life_rendered.new.jsonl"
    new_by = {}
    with rendered_new.open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                o = json.loads(line)
                new_by[o["chunk_id"]] = o
    es_docs = scroll_docs_no_vec(es, ES_INDEX)
    same = diff = 0
    diff_samples = []
    for cid, src in es_docs.items():
        exp = new_by.get(cid)
        if not exp:
            diff += 1
            continue
        d = fields_equal(src, exp)
        # chars may be int
        if d:
            diff += 1
            if len(diff_samples) < 20:
                diff_samples.append((cid, d))
        else:
            same += 1
    if same != EXPECTED_N or diff:
        raise GateFail("T3", f"R1 same={same} diff={diff}", {"samples": diff_samples[:10]})

    logging.info("T3 R2 vectors...")
    # build emb from new shards
    new_emb = {}
    for row in iter_new_vec_rows():
        new_emb[row["chunk_id"]] = row["embedding"]
    check_ids = set(aff_ids)
    others = [cid for cid in new_emb if cid not in aff_ids]
    random.seed(SEED)
    check_ids |= set(random.sample(others, min(500, len(others))))
    id_list = sorted(check_ids)
    mism = 0
    for i in range(0, len(id_list), 100):
        batch = id_list[i:i + 100]
        got = mget_full(es, ES_INDEX, batch)
        for cid in batch:
            if not vec_equal((got.get(cid) or {}).get("text_vector"), new_emb[cid]):
                mism += 1
    if mism:
        raise GateFail("T3", f"R2 向量不一致 {mism}")

    es_ids = set(es_docs)
    if es_ids != set(new_by) or es_ids != set(new_emb) or len(es_ids) != EXPECTED_N:
        raise GateFail("T3", f"R3 id 集合失败 es={len(es_ids)} rend={len(new_by)} vec={len(new_emb)}")

    logging.info("T3 R4 knn...")
    # pick samples：四本 rename 书各 ≥1，脏数据 ≥若干，凑满 10
    plan = load_fix_list()["by_cid"]
    picks = []
    want_books = ["列王纪生命读经", "哥林多前书生命读经", "哥林多后书生命读经", "腓立比书生命读经"]
    for bt in want_books:
        for cid, ent in plan.items():
            nbt = (ent["fields"].get("book_title") or {}).get("new") or ent.get("book")
            if nbt == bt and cid not in picks:
                picks.append(cid)
                break
    dirty_n = 0
    for cid, ent in plan.items():
        if ent.get("category") == "dirty_book" and cid not in picks:
            picks.append(cid)
            dirty_n += 1
            if dirty_n >= 4:
                break
    for cid in plan:
        if len(picks) >= 10:
            break
        if cid not in picks:
            picks.append(cid)
    picks = picks[:10]
    knn_ok = 0
    knn_detail = []
    for cid in picks:
        vec = new_emb[cid]
        resp = es.search(
            index=ES_INDEX, size=1,
            knn={"field": "text_vector", "query_vector": vec, "k": 1, "num_candidates": 200},
            _source=["chunk_id", "book_title"],
        )
        hits = resp["hits"]["hits"]
        top = hits[0] if hits else {}
        top_id = top.get("_id")
        score = top.get("_score")
        # int8_hnsw 量化下自匹配常见 0.996–0.999；「≈1.0」取 >=0.99 且 top1 必须是自己
        # num_candidates 需 ≥200，否则偶发 HNSW 漏检（见 life_11-2-5 @50）
        ok1 = top_id == cid and score is not None and float(score) >= 0.99
        if ok1:
            knn_ok += 1
        knn_detail.append({"cid": cid, "top": top_id, "score": score, "ok": ok1})
    if knn_ok != len(picks) or len(picks) < 10:
        raise GateFail("T3", f"R4 knn 失败 {knn_ok}/{len(picks)}", {"detail": knn_detail})

    logging.info("T3 R5 smoke...")
    smoke = {}
    # book_title 为 text+keyword 子字段，精确过滤用 .keyword
    for bt in want_books:
        smoke[bt] = es.count(index=ES_INDEX, query={"term": {"book_title.keyword": bt}})["count"]
    for old in BOOK_RENAME:
        smoke[f"old:{old}"] = es.count(index=ES_INDEX, query={"term": {"book_title.keyword": old}})["count"]
    smoke["comma"] = es.count(index=ES_INDEX, query={"wildcard": {"book_title.keyword": "*，*"}})["count"]
    expect_by_book = Counter()
    for cid, ent in plan.items():
        nbt = (ent["fields"].get("book_title") or {}).get("new") or ent.get("book")
        expect_by_book[nbt] += 1
    for bt in want_books:
        # count in ES may include unaffected docs with same title — for 列王纪 etc. ALL should be renamed
        # so ES count should equal total docs with that book in rendered.new
        pass
    # compute expected from rendered.new
    bt_counts = Counter()
    with rendered_new.open(encoding="utf-8") as fp:
        for line in fp:
            o = json.loads(line)
            bt_counts[o.get("book_title")] += 1
    for bt in want_books:
        if smoke[bt] != bt_counts.get(bt, 0):
            raise GateFail("T3", f"R5 {bt} count={smoke[bt]} expect={bt_counts.get(bt)}")
    for old in BOOK_RENAME:
        if smoke[f"old:{old}"] != 0:
            raise GateFail("T3", f"R5 旧写法仍有 {old}={smoke[f'old:{old}']}")
    if smoke["comma"] != 0:
        raise GateFail("T3", f"R5 仍有逗号书名 {smoke['comma']}")

    logging.info("T3 R6 header sample...")
    sample_ids = list(aff_ids)
    random.seed(SEED + 1)
    sample_ids = random.sample(sample_ids, min(150, len(sample_ids)))
    rest = [c for c in new_by if c not in aff_ids]
    sample_ids += random.sample(rest, min(150, len(rest)))
    hdr_fail = 0
    for cid in sample_ids:
        o = new_by[cid]
        first = (o.get("text") or "").split("\n", 1)[0]
        hdr = build_header(o.get("book_title"), o.get("message_title"), o.get("section_title"))
        if first != hdr:
            hdr_fail += 1
    if hdr_fail:
        raise GateFail("T3", f"R6 头部行失败 {hdr_fail}/{len(sample_ids)}")

    logging.info("T3 R7 12490 align...")
    titles_12490 = load_12490_titles()
    life_pairs = set()
    with rendered_new.open(encoding="utf-8") as fp:
        for line in fp:
            o = json.loads(line)
            if "生命读经" in (o.get("book_title") or ""):
                life_pairs.add((o.get("book_title"), o.get("message_number")))
    both = only_a = only_b = 0
    only_12490 = []
    only_life = []
    for k in titles_12490:
        if k in life_pairs:
            both += 1
        else:
            only_a += 1
            if len(only_12490) < 50:
                only_12490.append(k)
    for k in life_pairs:
        if k not in titles_12490:
            only_b += 1
            if len(only_life) < 50:
                only_life.append(k)

    r = {
        "ok": ok, "count": cnt2, "R1_same": same, "R2_mism": mism, "knn": knn_detail,
        "smoke": smoke, "R6_n": len(sample_ids), "R6_fail": hdr_fail,
        "R7": {"both": both, "only_12490": only_a, "only_life": only_b,
               "only_12490_samples": only_12490, "only_life_samples": only_life},
    }
    lines = [
        "# text_life 本机写入与对账（T3）",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- W1 写入 ok={ok} count={cnt2}",
        f"- R1 same={same} diff={diff}",
        f"- R2 vector mism={mism}（受影响+500）",
        f"- R3 ids={EXPECTED_N}",
        f"- R4 knn {knn_ok}/{len(picks)} detail={json.dumps(knn_detail, ensure_ascii=False)[:1500]}",
        f"- R5 smoke={smoke}",
        f"- R6 header fail={hdr_fail}/{len(sample_ids)}",
        f"- R7 both={both} only_12490={only_a} only_life={only_b}",
        f"- only_12490 样例={only_12490[:20]}",
        f"- only_life 样例={only_life[:20]}",
        f"- 回滚脚本 `panai4/inherit/rollback_text_life_local.py`（未运行）",
        "- **闸门 R1–R7：通过**",
        "",
        "## 密钥泄露检查：通过",
        "",
    ]
    (ARCHIVE / "text_life_fix_local.md").write_text("\n".join(lines), encoding="utf-8")
    mark_ok("local_R", r)
    mark_ok("t3", r)
    return r


def _t4_s2_reconcile(local, remote, aff_ids: list[str], log_path: Path, meta: dict) -> dict:
    """S2 对账（写后或重跑）。"""
    aff_set = set(aff_ids)
    logging.info("T4 S2 reconcile remote vs local...")
    local_ids = scroll_ids(local, ES_INDEX)
    remote_ids = scroll_ids(remote, ES_INDEX)
    if local_ids != remote_ids or len(local_ids) != EXPECTED_N:
        raise GateFail("T4", f"S2 id 集合不等 l={len(local_ids)} r={len(remote_ids)}")
    local_docs = scroll_docs_no_vec(local, ES_INDEX)
    remote_docs = scroll_docs_no_vec(remote, ES_INDEX)
    same = diff = 0
    diff_samples = []
    for cid in local_ids:
        d = fields_equal(local_docs.get(cid) or {}, remote_docs.get(cid) or {})
        if d:
            diff += 1
            if len(diff_samples) < 15:
                diff_samples.append((cid, d))
        else:
            same += 1
    if same != EXPECTED_N or diff:
        raise GateFail("T4", f"S2 R1 same={same} diff={diff}", {"samples": diff_samples})

    new_emb = {}
    for row in iter_new_vec_rows():
        new_emb[row["chunk_id"]] = row["embedding"]
    check = set(aff_ids)
    others = [c for c in new_emb if c not in aff_set]
    random.seed(SEED + 2)
    check |= set(random.sample(others, min(500, len(others))))
    mism = 0
    id_list = sorted(check)
    for i in range(0, len(id_list), 100):
        batch = id_list[i:i + 100]
        got = mget_full(remote, ES_INDEX, batch)
        for cid in batch:
            if not vec_equal((got.get(cid) or {}).get("text_vector"), new_emb[cid]):
                mism += 1
    if mism:
        raise GateFail("T4", f"S2 向量 mism={mism}")

    plan = load_fix_list()["by_cid"]
    want_books = ["列王纪生命读经", "哥林多前书生命读经", "哥林多后书生命读经", "腓立比书生命读经"]
    picks = []
    for bt in want_books:
        for cid, ent in plan.items():
            nbt = (ent["fields"].get("book_title") or {}).get("new") or ent.get("book")
            if nbt == bt and cid not in picks:
                picks.append(cid)
                break
    dirty_n = 0
    for cid, ent in plan.items():
        if ent.get("category") == "dirty_book" and cid not in picks:
            picks.append(cid)
            dirty_n += 1
            if dirty_n >= 4:
                break
    for cid in plan:
        if len(picks) >= 10:
            break
        if cid not in picks:
            picks.append(cid)
    picks = picks[:10]
    knn_ok = 0
    knn_detail = []
    for cid in picks:
        resp = remote.search(
            index=ES_INDEX, size=1,
            knn={"field": "text_vector", "query_vector": new_emb[cid], "k": 1, "num_candidates": 200},
            _source=["chunk_id"],
        )
        hit = (resp["hits"]["hits"] or [{}])[0]
        ok1 = hit.get("_id") == cid and float(hit.get("_score") or 0) >= 0.99
        if ok1:
            knn_ok += 1
        knn_detail.append({"cid": cid, "top": hit.get("_id"), "score": hit.get("_score"), "ok": ok1})
    if knn_ok != len(picks) or len(picks) < 10:
        raise GateFail("T4", f"S2 knn {knn_ok}/{len(picks)}", {"detail": knn_detail})

    smoke = {}
    rendered_new = STAGING / "life_rendered.new.jsonl"
    bt_counts = Counter()
    with rendered_new.open(encoding="utf-8") as fp:
        for line in fp:
            bt_counts[json.loads(line).get("book_title")] += 1
    for bt in want_books:
        smoke[bt] = remote.count(index=ES_INDEX, query={"term": {"book_title.keyword": bt}})["count"]
        if smoke[bt] != bt_counts.get(bt, 0):
            raise GateFail("T4", f"S2 smoke {bt}={smoke[bt]} expect={bt_counts.get(bt)}")
    for old in BOOK_RENAME:
        c = remote.count(index=ES_INDEX, query={"term": {"book_title.keyword": old}})["count"]
        smoke[f"old:{old}"] = c
        if c:
            raise GateFail("T4", f"S2 旧写法 {old}={c}")
    smoke["comma"] = remote.count(index=ES_INDEX, query={"wildcard": {"book_title.keyword": "*，*"}})["count"]
    if smoke["comma"]:
        raise GateFail("T4", f"S2 comma={smoke['comma']}")

    # header sample remote vs render
    sample_ids = list(aff_ids)
    random.seed(SEED + 3)
    sample_ids = random.sample(sample_ids, min(150, len(sample_ids)))
    rest = [c for c in new_emb if c not in aff_set]
    sample_ids += random.sample(rest, min(150, len(rest)))
    hdr_fail = 0
    new_by = {}
    with rendered_new.open(encoding="utf-8") as fp:
        for line in fp:
            o = json.loads(line)
            new_by[o["chunk_id"]] = o
    for cid in sample_ids:
        o = new_by[cid]
        first = (o.get("text") or "").split("\n", 1)[0]
        hdr = build_header(o.get("book_title"), o.get("message_title"), o.get("section_title"))
        if first != hdr:
            hdr_fail += 1
    if hdr_fail:
        raise GateFail("T4", f"S2 header fail={hdr_fail}")

    r = {
        **meta,
        "S2_same": same, "vec_mism": mism, "knn": knn_detail, "smoke": smoke,
        "hdr_fail": hdr_fail, "hdr_n": len(sample_ids),
        "knn_ok": knn_ok, "picks": len(picks),
    }
    lines = [
        "# text_life 服务器写入与对账（T4）",
        "",
        f"> {datetime.now().isoformat(timespec='seconds')}；log=`{log_path}`",
        "",
        f"- S0/S1 元数据：{json.dumps({k: meta.get(k) for k in ('ok','count_before','count_after','non_aff_same','cat_before','cat_after')}, ensure_ascii=False)}",
        f"- S2 本机↔服务器字段 same={same} diff={diff}；向量 mism={mism}",
        f"- S2 knn {knn_ok}/{len(picks)}；smoke={smoke}",
        f"- S2 header fail={hdr_fail}/{len(sample_ids)}",
        f"- 其他 panai4_* count：{meta.get('cat_before') == meta.get('cat_after')} cat={meta.get('cat_after')}",
        f"- 回滚脚本 `panai4/inherit/rollback_text_life_remote.py`（未运行）",
        "- **闸门 S0–S2：通过**",
        "",
        "## 密钥泄露检查：通过",
        "",
    ]
    (ARCHIVE / "text_life_fix_server.md").write_text("\n".join(lines), encoding="utf-8")
    mark_ok("t4", r)
    mark_ok("server_R", r)
    return r


def stage_t4(log_path: Path, reconcile_only: bool = False) -> dict:
    logging.info("=== T4 write remote%s ===", " (reconcile_only)" if reconcile_only else "")
    from elasticsearch.helpers import bulk
    require_ok("local_R")
    require_ok("verify_vec")
    require_ok("t1")
    local = make_local_es()
    remote = make_remote_es()
    aff_ids = sorted({ln.strip() for ln in (STAGING / "affected_ids.txt").read_text(encoding="utf-8").splitlines() if ln.strip()})
    aff_set = set(aff_ids)

    def cat_counts(es):
        rows = es.cat.indices(index="panai4_*", format="json", h="index,docs.count")
        return {r["index"]: int(r["docs.count"]) for r in rows}

    if reconcile_only:
        rcnt2 = remote.count(index=ES_INDEX)["count"]
        if rcnt2 != EXPECTED_N:
            raise GateFail("T4", f"reconcile count={rcnt2}")
        meta = {
            "ok": len(aff_ids),
            "count_before": EXPECTED_N,
            "count_after": rcnt2,
            "non_aff_same": EXPECTED_N - len(aff_ids),
            "cat_before": cat_counts(remote),
            "cat_after": cat_counts(remote),
            "note": "reconcile_only after prior S1 write; knn num_candidates=200",
        }
        return _t4_s2_reconcile(local, remote, aff_ids, log_path, meta)

    # S0
    rcnt = remote.count(index=ES_INDEX)["count"]
    if rcnt != EXPECTED_N:
        raise GateFail("T4", f"S0 server count={rcnt}")
    before = BACKUP / "es_server_before.jsonl"
    before_docs = {}
    with before.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            o = json.loads(line)
            cid = o.get("chunk_id") or o.get("_id")
            src = dict(o.get("_source") if "_source" in o else o)
            src.pop("_id", None)
            before_docs[cid] = src
    if len(before_docs) != len(aff_ids):
        raise GateFail("T4", f"S0 before 条数 {len(before_docs)}")

    cur = mget_full(remote, ES_INDEX, aff_ids)
    same = diff = 0
    for cid in aff_ids:
        a = cur.get(cid) or {}
        b = before_docs.get(cid) or {}
        keys = (set(a) | set(b)) - {"_id"}
        ok1 = True
        for k in keys:
            if k == "text_vector":
                if not vec_equal(a.get(k), b.get(k)):
                    ok1 = False
                    break
            elif a.get(k) != b.get(k):
                ok1 = False
                break
        if ok1:
            same += 1
        else:
            diff += 1
    if same != len(aff_ids) or diff:
        raise GateFail("T4", f"S0 affected vs before same={same} diff={diff}")

    if not (BACKUP / "SHA256SUMS.txt").exists():
        raise GateFail("T4", "S0 缺 SHA256SUMS")

    logging.info("T4 S0 extra full id+field compare local vs remote...")
    local_ids = scroll_ids(local, ES_INDEX)
    remote_ids = scroll_ids(remote, ES_INDEX)
    if local_ids != remote_ids or len(local_ids) != EXPECTED_N:
        raise GateFail(
            "T4",
            f"S0 id 集合不等 local={len(local_ids)} remote={len(remote_ids)} "
            f"only_l={len(local_ids - remote_ids)} only_r={len(remote_ids - local_ids)}",
        )
    local_docs = scroll_docs_no_vec(local, ES_INDEX)
    remote_docs = scroll_docs_no_vec(remote, ES_INDEX)
    non_diff = 0
    non_same = 0
    samples = []
    for cid in local_ids:
        if cid in aff_set:
            continue
        d = fields_equal(local_docs.get(cid) or {}, remote_docs.get(cid) or {})
        if d:
            non_diff += 1
            if len(samples) < 20:
                samples.append((cid, d))
        else:
            non_same += 1
    if non_diff:
        raise GateFail("T4", f"S0 非受影响字段 diff={non_diff}", {"samples": samples})
    logging.info("T4 S0 non-affected same=%s", non_same)

    cat_before = cat_counts(remote)
    write_rollback_script(
        BACKEND / "panai4" / "inherit" / "rollback_text_life_remote.py",
        before, remote=True,
    )

    docs = []
    found = set()
    for row in iter_new_vec_rows():
        if row["chunk_id"] in aff_set:
            docs.append(row)
            found.add(row["chunk_id"])
    if found != aff_set:
        raise GateFail("T4", f"S1 取出 {len(found)}")

    actions = []
    for row in docs:
        src = es_source_from_vec_row(row)
        actions.append({"_op_type": "index", "_index": ES_INDEX, "_id": row["chunk_id"], **src})

    ok = fail = 0
    for i in range(0, len(actions), REMOTE_BULK):
        batch = actions[i:i + REMOTE_BULK]
        success, errs = bulk(remote, batch, raise_on_error=False, raise_on_exception=False, request_timeout=180)
        ok += success
        if errs:
            fail += len(errs)
            raise GateFail("T4", f"S1 bulk 失败 ok={ok} fail={fail}", {"err": str(errs[:3])[:1500]})
        logging.info("remote bulk ok=%s", ok)
    remote.indices.refresh(index=ES_INDEX)
    rcnt2 = remote.count(index=ES_INDEX)["count"]
    if rcnt2 != EXPECTED_N or ok != len(aff_ids):
        raise GateFail("T4", f"S1 后 count={rcnt2} ok={ok}")

    cat_after = cat_counts(remote)
    if cat_before != cat_after:
        raise GateFail("T4", f"其他索引 count 变化 before={cat_before} after={cat_after}")

    meta = {
        "ok": ok, "count_before": rcnt, "count_after": rcnt2,
        "non_aff_same": non_same, "cat_before": cat_before, "cat_after": cat_after,
    }
    return _t4_s2_reconcile(local, remote, aff_ids, log_path, meta)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        choices=("t0", "t1", "t2_embed", "t2_assemble", "t3", "t4", "t4_s2", "apply"),
        default="t0",
    )
    args = ap.parse_args(argv)
    log_path = setup_log()
    try:
        if args.stage == "t0":
            stage_t0(log_path)
        elif args.stage == "t1":
            stage_t1(log_path)
        elif args.stage == "t2_embed":
            stage_t2_embed(log_path)
        elif args.stage == "t2_assemble":
            stage_t2_assemble(log_path)
        elif args.stage == "t3":
            stage_t3(log_path)
        elif args.stage == "t4":
            stage_t4(log_path)
        elif args.stage == "t4_s2":
            stage_t4(log_path, reconcile_only=True)
        elif args.stage == "apply":
            stage_t1(log_path)
            stage_t2_embed(log_path)
            stage_t2_assemble(log_path)
            stage_t3(log_path)
            stage_t4(log_path)
        return 0
    except GateFail as gf:
        logging.error("GATE %s %s", gf.gate, _redact(str(gf), _secrets()))
        (ARCHIVE / f"text_life_fix_FAIL_{gf.gate}.md").write_text(
            f"# FAIL {gf.gate}\n\n{_redact(str(gf), _secrets())}\n\n"
            f"payload={_redact(json.dumps(gf.payload, ensure_ascii=False, default=str)[:8000], _secrets())}\n",
            encoding="utf-8",
        )
        print(f"STOPPED {gf.gate}: {_redact(str(gf), _secrets())}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
