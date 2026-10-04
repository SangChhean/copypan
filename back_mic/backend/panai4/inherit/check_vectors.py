# -*- coding: utf-8 -*-
"""L1 向量分片完整性检查。

用法（在 back_mic/backend 下）::

    python -m panai4.inherit.check_vectors
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

VEC_DIR = Path(r"G:\PanAI4.0专用\12490原文JSONL\vectors")
RENDERED_DIR = Path(r"G:\PanAI4.0专用\12490原文JSONL\rendered")
REPORT = Path(__file__).resolve().parents[4] / "docs" / "panai4_es" / "vectors_integrity.md"
SAMPLE_SEED = 20260930
NORM_SAMPLE = 200
EXPECT_DIM = 1024

JOBS = [
    {"source": "kg-rag_life", "expect": 39463},
    {"source": "kg-rag_cwwl", "expect": 178107},
    {"source": "kg-rag_cwwn", "expect": 32032},
    {"source": "kg-rag_others", "expect": 15481},
    {"source": "kg-rag_map_note", "expect": 16052},
]


def _fmt_ids(ids, limit=30) -> str:
    ids = sorted(ids)
    if not ids:
        return "（无）"
    if len(ids) <= limit:
        return ", ".join(f"`{x}`" for x in ids)
    head = ", ".join(f"`{x}`" for x in ids[:limit])
    return f"{head} … 共 {len(ids)} 条"


def iter_shard_files(label: str, vec_dir: Path) -> list[Path]:
    files = []
    i = 0
    while True:
        path = vec_dir / f"{label}_shard_{i:05d}.jsonl"
        if not path.is_file():
            break
        files.append(path)
        i += 1
    return files


def check_parse(vec_dir: Path) -> list[dict]:
    """L1.1：全部分片能否完整解析。"""
    failures = []
    files = sorted(vec_dir.glob("*_shard_*.jsonl"))
    for path in files:
        try:
            with path.open("rb") as fp:
                raw = fp.read()
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            failures.append({
                "file": path.name,
                "line": None,
                "error": f"UTF-8 decode: {exc}",
            })
            continue
        try:
            with path.open(encoding="utf-8") as fp:
                for ln, line in enumerate(fp, 1):
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError as exc:
                        failures.append({
                            "file": path.name,
                            "line": ln,
                            "error": f"JSON: {exc}",
                        })
                        continue
                    if not isinstance(obj, dict):
                        failures.append({
                            "file": path.name,
                            "line": ln,
                            "error": f"not object: {type(obj).__name__}",
                        })
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "file": path.name,
                "line": None,
                "error": f"read: {exc}",
            })
    return failures


def load_input_ids(rendered_dir: Path, label: str) -> set[str]:
    path = rendered_dir / f"{label}.jsonl"
    ids = set()
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            cid = obj.get("chunk_id")
            if cid is not None:
                ids.add(str(cid))
    return ids


def scan_output(label: str, vec_dir: Path) -> dict:
    """扫输出片：chunk_id、维度、NaN/Inf/零向量、收集向量供抽样。"""
    files = iter_shard_files(label, vec_dir)
    counter: Counter = Counter()
    bad_dim: list[tuple] = []
    nan_inf: list[str] = []
    all_zero: list[str] = []
    # reservoir for norms: store (cid, norm) via reservoir of vectors indices
    reservoir: list[tuple] = []  # (chunk_id, vector)
    seen = 0
    n_rows = 0
    rng = random.Random(SAMPLE_SEED ^ hash(label) & 0xFFFFFFFF)

    for path in files:
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                row = json.loads(line)
                n_rows += 1
                cid = str(row.get("chunk_id") or "")
                counter[cid] += 1
                emb = row.get("embedding") if row.get("embedding") is not None else row.get("text_vector")
                if not isinstance(emb, list):
                    bad_dim.append((cid, type(emb).__name__))
                    continue
                dim = len(emb)
                if dim != EXPECT_DIM:
                    bad_dim.append((cid, dim))
                has_nan_inf = False
                all_z = True
                for v in emb:
                    try:
                        fv = float(v)
                    except (TypeError, ValueError):
                        has_nan_inf = True
                        all_z = False
                        continue
                    if math.isnan(fv) or math.isinf(fv):
                        has_nan_inf = True
                    if fv != 0.0:
                        all_z = False
                if has_nan_inf and cid:
                    nan_inf.append(cid)
                if all_z and cid:
                    all_zero.append(cid)
                seen += 1
                if len(reservoir) < NORM_SAMPLE:
                    reservoir.append((cid, emb))
                else:
                    j = rng.randint(0, seen - 1)
                    if j < NORM_SAMPLE:
                        reservoir[j] = (cid, emb)

    norms = []
    for cid, emb in reservoir:
        s = 0.0
        for v in emb:
            fv = float(v)
            s += fv * fv
        norms.append(math.sqrt(s))

    dup_ids = sorted(cid for cid, n in counter.items() if n > 1 and cid)
    out_ids = set(counter.keys())
    out_ids.discard("")

    norm_stats = None
    if norms:
        norm_stats = {
            "n": len(norms),
            "min": min(norms),
            "max": max(norms),
            "mean": sum(norms) / len(norms),
        }

    return {
        "n_files": len(files),
        "n_rows": n_rows,
        "out_ids": out_ids,
        "dup_ids": dup_ids,
        "dup_counts": {cid: counter[cid] for cid in dup_ids},
        "bad_dim": bad_dim,
        "nan_inf": nan_inf,
        "all_zero": all_zero,
        "norm_stats": norm_stats,
    }


def write_report(path: Path, parse_failures: list, per_job: list, gate_ok: bool) -> None:
    lines = ["# 继承索引向量分片完整性检查（L1）", ""]
    lines.append(f"向量目录：`{VEC_DIR}`")
    lines.append(f"输入目录：`{RENDERED_DIR}`")
    lines.append("")

    lines.append("## L1.1 分片解析")
    lines.append("")
    if not parse_failures:
        lines.append("全部 jsonl 分片可完整解析（UTF-8 + JSON）。失败：0。")
    else:
        lines.append(f"解析失败：**{len(parse_failures)}**")
        lines.append("")
        for f in parse_failures:
            loc = f" L{f['line']}" if f["line"] else ""
            lines.append(f"- `{f['file']}`{loc}：{f['error']}")
    lines.append("")

    lines.append("## L1.2 chunk_id 集合比对")
    lines.append("")
    lines.append("| 库 | 输出条数 | 输入条数 | 缺失 | 多余 | 输出内重复 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    all_id_ok = True
    for j in per_job:
        miss = len(j["missing"])
        extra = len(j["extra"])
        dup = len(j["dup_ids"])
        if miss or extra or dup:
            all_id_ok = False
        lines.append(
            f"| `{j['source']}` | {j['n_rows']:,} | {j['n_input']:,} | "
            f"{miss} | {extra} | {dup} |"
        )
    lines.append("")
    if all_id_ok:
        lines.append("硬要求：五库全部 缺失=0、多余=0、重复=0 → **通过**。")
    else:
        lines.append("硬要求：五库全部 缺失=0、多余=0、重复=0 → **未通过**。")
        lines.append("")
        for j in per_job:
            if not (j["missing"] or j["extra"] or j["dup_ids"]):
                continue
            lines.append(f"### `{j['source']}`")
            lines.append("")
            lines.append(f"- 缺失（只在输入）：{_fmt_ids(j['missing'])}")
            lines.append(f"- 多余（只在输出）：{_fmt_ids(j['extra'])}")
            if j["dup_ids"]:
                detail = ", ".join(
                    f"`{cid}`×{j['dup_counts'][cid]}" for cid in j["dup_ids"][:30]
                )
                more = f" … 共 {len(j['dup_ids'])}" if len(j["dup_ids"]) > 30 else ""
                lines.append(f"- 输出内重复：{detail}{more}")
            else:
                lines.append("- 输出内重复：（无）")
            lines.append("")
    lines.append("")

    lines.append("## L1.3 向量抽查")
    lines.append("")
    vec_ok = True
    for j in per_job:
        lines.append(f"### `{j['source']}`")
        lines.append("")
        bad = j["bad_dim"]
        nan_inf = j["nan_inf"]
        zeros = j["all_zero"]
        if bad or nan_inf or zeros:
            vec_ok = False
        lines.append(
            f"- 非 {EXPECT_DIM} 维：{len(bad)}"
            + (f" → {_fmt_ids([b[0] for b in bad], 20)}（dims={[b[1] for b in bad[:20]]}）" if bad else "")
        )
        lines.append(
            f"- NaN/Inf：{len(nan_inf)}"
            + (f" → {_fmt_ids(nan_inf)}" if nan_inf else "")
        )
        lines.append(
            f"- 全零向量：{len(zeros)}"
            + (f" → {_fmt_ids(zeros)}" if zeros else "")
        )
        ns = j["norm_stats"]
        if ns:
            lines.append(
                f"- 随机 {ns['n']} 条模长：min={ns['min']:.6f} / "
                f"max={ns['max']:.6f} / mean={ns['mean']:.6f}"
            )
        else:
            lines.append("- 随机模长：无样本")
            vec_ok = False
        lines.append("")

    if vec_ok:
        lines.append("L1.3 → **通过**（维度全 1024；无 NaN/Inf/全零；模长同量级）。")
    else:
        lines.append("L1.3 → **未通过**。")
    lines.append("")

    lines.append("## L2 闸门")
    lines.append("")
    if gate_ok:
        lines.append("L1.2 + L1.3 全部通过 → **可进 L3**。")
    else:
        lines.append("L1.2 或 L1.3 未通过 → **停下，等确认**。未删除/重算任何分片。")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {path}", flush=True)


def main() -> int:
    print("L1.1 parse…", flush=True)
    parse_failures = check_parse(VEC_DIR)
    print(f"PARSE_FAIL {len(parse_failures)}", flush=True)

    per_job = []
    for job in JOBS:
        label = job["source"]
        print(f"SCAN {label}…", flush=True)
        out = scan_output(label, VEC_DIR)
        print(f"  rows={out['n_rows']} files={out['n_files']}", flush=True)
        print(f"LOAD_INPUT {label}…", flush=True)
        in_ids = load_input_ids(RENDERED_DIR, label)
        missing = sorted(in_ids - out["out_ids"])
        extra = sorted(out["out_ids"] - in_ids)
        print(
            f"  in={len(in_ids)} out_unique={len(out['out_ids'])} "
            f"miss={len(missing)} extra={len(extra)} dup={len(out['dup_ids'])}",
            flush=True,
        )
        per_job.append({
            "source": label,
            "expect": job["expect"],
            "n_rows": out["n_rows"],
            "n_input": len(in_ids),
            "missing": missing,
            "extra": extra,
            "dup_ids": out["dup_ids"],
            "dup_counts": out["dup_counts"],
            "bad_dim": out["bad_dim"],
            "nan_inf": out["nan_inf"],
            "all_zero": out["all_zero"],
            "norm_stats": out["norm_stats"],
        })

    id_ok = all(
        len(j["missing"]) == 0 and len(j["extra"]) == 0 and len(j["dup_ids"]) == 0
        for j in per_job
    )
    vec_ok = all(
        not j["bad_dim"] and not j["nan_inf"] and not j["all_zero"] and j["norm_stats"]
        for j in per_job
    )
    # 模长同量级：max/min < 100 且 mean 非零
    for j in per_job:
        ns = j["norm_stats"]
        if not ns or ns["min"] <= 0 or ns["max"] / ns["min"] > 100:
            vec_ok = False

    gate_ok = id_ok and vec_ok and not parse_failures
    write_report(REPORT, parse_failures, per_job, gate_ok)
    print(f"GATE_OK={gate_ok} id_ok={id_ok} vec_ok={vec_ok}", flush=True)
    return 0 if gate_ok else 1


if __name__ == "__main__":
    sys.exit(main())
