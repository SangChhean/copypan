# -*- coding: utf-8 -*-
"""neo4j-v4：把词条标注 JSON 写入 Truth_Point（通用，可复用）。

只 SET 指定标注名；不创建/删除节点或关系；不碰 name/same_as。
连接：NEO4J_V4_*（dotenv 加载 .env，绝不打印密码）。不运行 build_v4.py。

用法（在 back_mic/backend 下）:
    python -m panai4.graph.import_annotation --stage check \\
        --file "C:\\...\\xxx.json" --name devine_argument
    python -m panai4.graph.import_annotation --stage import --file ... --name ...
    python -m panai4.graph.import_annotation --stage verify --file ... --name ...

可选：
    --fields content_1,content_2,content_3
        要原样序列化进标注值的字段（默认：除 name 外、记录里实际有的键，保持原顺序）
    --report docs/panai4_graph/import_<name>.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parents[1]
_LOG_DIR = _REPO / "logs"
_IMPORT_ROOT = Path(r"C:\Users\28121\Desktop\可导入资料")

_EXPECTED = {
    "nodes_total": 2483,
    "Truth_Point": 2380,
    "Trunk": 12,
    "Branch": 91,
    "rels_total": 6527,
    "BELONGS_TO_TRUNK": 2380,
    "OF_BRANCH_DIRECTLY": 2380,
    "OF_BRANCH_INDIRECTLY": 1676,
    "GRAFTING": 91,
    "class_types": {
        "BELONGS_TO_TRUNK",
        "OF_BRANCH_DIRECTLY",
        "OF_BRANCH_INDIRECTLY",
        "GRAFTING",
    },
    "old6": {
        "LEADS_TO",
        "EXPERIENCES",
        "PRACTICED_AS",
        "CONTAINS",
        "OPPOSES",
        "LOCATED_IN",
    },
}

# 括号外 / 括号内（与 2373 词表、图谱 same_as 一致）
_PAREN_PAIRS = [
    ("产生男孩子", "产生得胜者"),
    ("晨晨复兴", "晨兴"),
    ("妇人", "女人"),
    ("挂虑", "忧虑"),
    ("火湖", "地狱"),
    ("扩大", "显大"),
    ("扩增", "扩展"),
    ("那灵的浇灌", "圣灵的浇灌"),
]
_BATCH = 50
_WRITE_HEAD = re.compile(
    r"^\s*(CREATE|MERGE|SET|REMOVE|DELETE|DETACH|DROP|LOAD\s+CSV)\b",
    re.IGNORECASE,
)
_PROP_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _redact(text: str, *secrets: str) -> str:
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
    return out


def _trunc(s: Any, n: int = 80) -> str:
    t = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    return t if len(t) <= n else t[:n] + "…"


def _load_env() -> dict[str, str]:
    env_path = _BACKEND / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    uri4 = (os.environ.get("NEO4J_V4_URI") or "").strip()
    user4 = (os.environ.get("NEO4J_V4_USER") or "").strip()
    pass4 = os.environ.get("NEO4J_V4_PASSWORD") or ""
    uri35 = (os.environ.get("NEO4J_URI") or "").strip()
    missing = [
        name
        for name, value in (
            ("NEO4J_V4_URI", uri4),
            ("NEO4J_V4_USER", user4),
            ("NEO4J_V4_PASSWORD", pass4),
        )
        if not str(value).strip()
    ]
    if missing:
        raise SystemExit("缺少环境变量（值不打印）: " + ", ".join(missing))
    if uri35 and uri35 == uri4:
        raise SystemExit("中止：NEO4J_V4_URI 与 NEO4J_URI 相同，拒绝连接。")
    return {"uri4": uri4, "user4": user4, "pass4": pass4}


def _read(tx, query: str, params: dict | None = None):
    if _WRITE_HEAD.search(query):
        raise RuntimeError(f"只读会话拒绝写语句: {query[:80]}")
    head = query.lstrip().split(None, 1)[0].upper()
    if head not in {"MATCH", "SHOW", "CALL", "WITH", "RETURN", "UNWIND"}:
        raise RuntimeError(f"只读会话拒绝语句头: {head}")
    return [record.data() for record in tx.run(query, params or {})]


def _run(session, query: str, params: dict | None = None):
    return session.execute_read(_read, query, params)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha_import_dir() -> dict[str, Any]:
    hashes = {}
    total = 0
    n = 0
    for p in sorted(_IMPORT_ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(_IMPORT_ROOT)).replace("\\", "/")
        hashes[rel] = _sha256(p)
        total += p.stat().st_size
        n += 1
    return {"n": n, "bytes": total, "hashes": hashes}


class Logger:
    def __init__(self, path: Path, pass4: str):
        self.path = path
        self.pass4 = pass4
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {_redact(msg, self.pass4)}"
        print(line)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def state_path(anno_name: str) -> Path:
    return _LOG_DIR / f"import_annotation_{anno_name}_state.json"


def default_report(anno_name: str) -> Path:
    return _REPO / "docs" / "panai4_graph" / f"import_{anno_name}.md"


def save_state(anno_name: str, data: dict) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    state_path(anno_name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def load_state(anno_name: str) -> dict:
    p = state_path(anno_name)
    if not p.is_file():
        raise SystemExit(f"缺少状态文件 {p}，请先 --stage check")
    return json.loads(p.read_text(encoding="utf-8"))


def snapshot_graph(session) -> dict[str, Any]:
    labels = {
        r["l"]: r["c"]
        for r in _run(
            session,
            "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c ORDER BY l",
        )
    }
    nodes_total = _run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
    same_as_n = _run(
        session,
        """
        MATCH (n:Truth_Point)
        WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
        RETURN count(n) AS c
        """,
    )[0]["c"]
    same_as_rows = _run(
        session,
        """
        MATCH (n:Truth_Point)
        WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
        RETURN n.name AS inner, n.same_as AS outer
        ORDER BY inner
        """,
    )
    # all TP name+same_as for later compare
    tp_props = _run(
        session,
        """
        MATCH (n:Truth_Point)
        RETURN n.name AS name,
               CASE WHEN n.same_as IS NULL THEN null ELSE n.same_as END AS same_as
        ORDER BY name
        """,
    )
    rels_total = _run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    by_type = {
        r["t"]: r["c"]
        for r in _run(
            session,
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t",
        )
    }
    node_keys = {}
    for label in ("Truth_Point", "Trunk", "Branch"):
        keys = _run(
            session,
            f"""
            MATCH (n:{label})
            UNWIND keys(n) AS k
            WITH k, count(*) AS nodes_with_key,
                 sum(CASE WHEN n[k] IS NULL THEN 0
                          WHEN toString(n[k]) = '' THEN 0
                          ELSE 1 END) AS nonempty
            RETURN k AS key, nodes_with_key, nonempty
            ORDER BY k
            """,
        )
        node_keys[label] = keys
    try:
        constraints = _run(session, "SHOW CONSTRAINTS")
    except Exception as exc:
        constraints = [{"error": str(exc)}]
    try:
        indexes = _run(session, "SHOW INDEXES")
    except Exception as exc:
        indexes = [{"error": str(exc)}]
    return {
        "labels": labels,
        "nodes_total": nodes_total,
        "same_as_n": same_as_n,
        "no_same_as_n": labels.get("Truth_Point", 0) - same_as_n,
        "same_as_rows": same_as_rows,
        "tp_props": tp_props,
        "rels_total": rels_total,
        "by_type": by_type,
        "node_keys": node_keys,
        "constraints": constraints,
        "indexes": indexes,
    }


def gate_baseline(base: dict) -> list[str]:
    fails = []
    if base["nodes_total"] != _EXPECTED["nodes_total"]:
        fails.append(f"nodes_total {base['nodes_total']} ≠ {_EXPECTED['nodes_total']}")
    for lab in ("Truth_Point", "Trunk", "Branch"):
        if base["labels"].get(lab) != _EXPECTED[lab]:
            fails.append(f"{lab} {base['labels'].get(lab)} ≠ {_EXPECTED[lab]}")
    if base["rels_total"] != _EXPECTED["rels_total"]:
        fails.append(f"rels_total {base['rels_total']} ≠ {_EXPECTED['rels_total']}")
    types = set(base["by_type"].keys())
    if types != _EXPECTED["class_types"]:
        fails.append(f"关系类型集合 {sorted(types)} ≠ {sorted(_EXPECTED['class_types'])}")
    for t in _EXPECTED["class_types"]:
        if base["by_type"].get(t, 0) != _EXPECTED[t]:
            fails.append(f"{t} {base['by_type'].get(t)} ≠ {_EXPECTED[t]}")
    for t in _EXPECTED["old6"]:
        if base["by_type"].get(t, 0) != 0:
            fails.append(f"旧关系 {t} 仍有 {base['by_type'].get(t)}")
    if base["same_as_n"] != 8:
        fails.append(f"same_as 非空 {base['same_as_n']} ≠ 8")
    return fails


def payload_of(record: dict, fields: list[str] | None) -> dict:
    """除 name 外要写入标注的字段；保持源记录键顺序。"""
    out = {}
    if fields:
        for k in fields:
            if k in record and k != "name":
                out[k] = record[k]
        return out
    for k, v in record.items():
        if k == "name":
            continue
        out[k] = v
    return out


def serialize_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def summarize_payload(payload: dict) -> dict:
    info = {}
    for k, v in payload.items():
        if isinstance(v, list):
            info[k] = {
                "n": len(v),
                "items": [
                    {
                        "title": _trunc(it.get("title"), 80) if isinstance(it, dict) else _trunc(it),
                        "description": _trunc(it.get("description"), 80)
                        if isinstance(it, dict)
                        else None,
                    }
                    for it in v[:20]
                ],
            }
        else:
            info[k] = _trunc(v, 80)
    return info


def parse_and_plan(file_path: Path, fields: list[str] | None) -> dict:
    raw = file_path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    data = json.loads(text)
    if not isinstance(data, list):
        raise SystemExit(f"顶层须为 list，实际 {type(data).__name__}")
    names = []
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            raise SystemExit(f"第 {i} 条不是 dict")
        if "name" not in row:
            raise SystemExit(f"第 {i} 条缺 name")
        names.append(row["name"])
    dup = [n for n, c in Counter(names).items() if c > 1]
    key_union: set[str] = set()
    for row in data:
        key_union |= set(row.keys())
    extra_keys = sorted(key_union - {"name", "content_1", "content_2", "content_3"})
    content_counts = {
        "content_1": sum(1 for r in data if r.get("content_1")),
        "content_2": sum(1 for r in data if r.get("content_2")),
        "content_3": sum(1 for r in data if r.get("content_3")),
    }
    by_name = {r["name"]: r for r in data}

    # paren preview
    paren_rows = []
    discard_inners: list[str] = []
    need_decision = []
    for outer, inner in _PAREN_PAIRS:
        o_in = outer in by_name
        i_in = inner in by_name
        row: dict[str, Any] = {
            "outer": outer,
            "inner": inner,
            "outer_in_json": o_in,
            "inner_in_json": i_in,
        }
        if o_in and i_in:
            po = payload_of(by_name[outer], fields)
            pi = payload_of(by_name[inner], fields)
            so = serialize_payload(po)
            si = serialize_payload(pi)
            same = so == si
            row["comparison"] = "完全相同" if same else "不同"
            row["outer_summary"] = summarize_payload(po)
            row["inner_summary"] = summarize_payload(pi)
            row["outer_len"] = len(so)
            row["inner_len"] = len(si)
            if same:
                discard_inners.append(inner)
                row["action"] = "丢弃括号内"
            else:
                row["action"] = "停止：内容不同，等决定"
                need_decision.append(
                    {
                        "case": "both_present_different",
                        "outer": outer,
                        "inner": inner,
                        "outer_summary": summarize_payload(po),
                        "inner_summary": summarize_payload(pi),
                    }
                )
        elif i_in and not o_in:
            pi = payload_of(by_name[inner], fields)
            row["comparison"] = "括号内在而括号外不在"
            row["inner_summary"] = summarize_payload(pi)
            row["action"] = "停止：等决定"
            need_decision.append(
                {
                    "case": "inner_only",
                    "outer": outer,
                    "inner": inner,
                    "inner_summary": summarize_payload(pi),
                }
            )
        elif o_in and not i_in:
            row["comparison"] = "仅括号外在 JSON"
            row["action"] = "写入括号外"
        else:
            row["comparison"] = "都不在 JSON"
            row["action"] = "无操作"
        paren_rows.append(row)

    write_rows = []
    for r in data:
        name = r["name"]
        if name in discard_inners:
            continue
        payload = payload_of(r, fields)
        if not payload:
            continue
        value = serialize_payload(payload)
        if value in ("null", "", "[]", "{}"):
            # empty object shouldn't happen if payload nonempty
            pass
        write_rows.append({"name": name, "value": value, "length": len(value)})

    lengths = [w["length"] for w in write_rows]
    lengths_sorted = sorted(lengths) if lengths else []
    plan = {
        "bom": bom,
        "n_records": len(data),
        "dup_names": dup,
        "extra_keys": extra_keys,
        "content_counts": content_counts,
        "has_city": "城市" in names,
        "names": names,
        "paren_rows": paren_rows,
        "discard_inners": discard_inners,
        "need_decision": need_decision,
        "write_count": len(write_rows),
        "write_names": [w["name"] for w in write_rows],
        "len_stats": {
            "min": lengths_sorted[0] if lengths_sorted else None,
            "median": int(statistics.median(lengths_sorted)) if lengths_sorted else None,
            "max": lengths_sorted[-1] if lengths_sorted else None,
            "total_chars": sum(lengths),
            "over_32000": sum(1 for x in lengths if x > 32000),
        },
        "null_or_empty_values": sum(
            1 for w in write_rows if w["value"] is None or w["value"] == ""
        ),
        # keep payloads for verify (name -> payload dict)
        "payloads": {
            r["name"]: payload_of(r, fields)
            for r in data
            if r["name"] not in discard_inners
        },
        "write_rows": write_rows,
    }
    return plan


def match_names(session, names: list[str]) -> dict:
    found = []
    missing = []
    multi = []
    for name in names:
        rows = _run(
            session,
            "MATCH (n:Truth_Point {name: $name}) RETURN n.name AS name",
            {"name": name},
        )
        if len(rows) == 0:
            missing.append(name)
        elif len(rows) == 1:
            found.append(name)
        else:
            multi.append({"name": name, "count": len(rows)})
    return {"found": found, "missing": missing, "multi": multi, "found_n": len(found), "missing_n": len(missing)}


def _set_batch(tx, anno_name: str, rows: list[dict]) -> int:
    if not _PROP_NAME_RE.fullmatch(anno_name):
        raise RuntimeError(f"标注名不合法: {anno_name}")
    # 标注名写死进语句（已校验为标识符），值与 name 用参数
    query = (
        f"UNWIND $rows AS row "
        f"MATCH (n:Truth_Point {{name: row.name}}) "
        f"SET n.`{anno_name}` = row.value "
        f"RETURN count(n) AS updated"
    )
    # 上面用 backticks；更稳妥：仅允许合法标识符时直接写
    query = (
        f"UNWIND $rows AS row "
        f"MATCH (n:Truth_Point {{name: row.name}}) "
        f"SET n.{anno_name} = row.value "
        f"RETURN count(n) AS updated"
    )
    result = tx.run(query, {"rows": rows})
    row = result.single()
    return int(row["updated"]) if row else 0


def stage_check(env: dict, log: Logger, file_path: Path, anno_name: str, fields: list[str] | None, report_path: Path) -> int:
    log.log(f"stage=check file={file_path} name={anno_name}")
    sha_before = _sha_import_dir()
    log.log(f"sha_before n={sha_before['n']} bytes={sha_before['bytes']}")

    plan = parse_and_plan(file_path, fields)
    log.log(
        f"JSON n={plan['n_records']} dup={plan['dup_names']} content={plan['content_counts']} "
        f"extra={plan['extra_keys']} city={plan['has_city']}"
    )

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = snapshot_graph(session)
            base_fails = gate_baseline(base)
            match = match_names(session, plan["names"])
    except Exception as exc:
        raise SystemExit("check 失败: " + _redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_after = _sha_import_dir()
    sha_ok = sha_before["hashes"] == sha_after["hashes"]

    fails = list(base_fails)
    if plan["dup_names"]:
        fails.append(f"JSON name 重复: {plan['dup_names']}")
    if match["missing_n"] or match["multi"]:
        fails.append(f"匹配失败 missing={match['missing']} multi={match['multi']}")
    if plan["need_decision"]:
        fails.append(f"括号词条需决定: {len(plan['need_decision'])} 项")
    if plan["null_or_empty_values"]:
        fails.append(f"拟写入值有 null/空: {plan['null_or_empty_values']}")
    if not sha_ok:
        fails.append("可导入资料 SHA256 盘点前后不一致")

    # strip heavy write_rows values from state? keep for import
    state = {
        "check_ok": not fails,
        "fails": fails,
        "anno_name": anno_name,
        "file": str(file_path),
        "fields": fields,
        "baseline": {
            k: v
            for k, v in base.items()
            if k != "tp_props"
        },
        "tp_props": base["tp_props"],
        "plan_summary": {
            "n_records": plan["n_records"],
            "dup_names": plan["dup_names"],
            "extra_keys": plan["extra_keys"],
            "content_counts": plan["content_counts"],
            "has_city": plan["has_city"],
            "paren_rows": [
                {kk: vv for kk, vv in r.items() if kk not in ()}
                for r in plan["paren_rows"]
            ],
            "discard_inners": plan["discard_inners"],
            "need_decision": plan["need_decision"],
            "write_count": plan["write_count"],
            "write_names": plan["write_names"],
            "len_stats": plan["len_stats"],
            "null_or_empty_values": plan["null_or_empty_values"],
        },
        "match": {
            "found_n": match["found_n"],
            "missing_n": match["missing_n"],
            "missing": match["missing"],
            "multi": match["multi"],
        },
        "payloads": plan["payloads"],
        "write_rows": plan["write_rows"],
        "sha_before": sha_before,
        "sha_after_check": sha_after,
        "sha_ok": sha_ok,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_state(anno_name, state)
    write_report(state, import_info=None, verify=None, env=env, log_path=log.path, report_path=report_path, stopped=None if not fails else "check")

    for f in fails:
        log.log("GATE FAIL: " + f)
    if fails:
        log.log("闸门未通过，停止。未进入 import。")
        return 2
    log.log(
        f"闸门通过。拟写入 {plan['write_count']}（丢弃括号内 {plan['discard_inners']}）；"
        f"len min/med/max={plan['len_stats']}"
    )
    return 0


def stage_import(env: dict, log: Logger, file_path: Path, anno_name: str, report_path: Path) -> int:
    state = load_state(anno_name)
    if not state.get("check_ok"):
        log.log("check 未通过，拒绝 import")
        return 2
    if Path(state["file"]).resolve() != file_path.resolve():
        log.log(f"文件路径与 check 不一致: {state['file']} vs {file_path}")
        return 2
    base = state["baseline"]
    write_rows = state["write_rows"]
    log.log(f"stage=import 拟写入 {len(write_rows)}")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    written = 0
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            # I1 recheck baseline
            now = snapshot_graph(session)
            light_now = {k: now[k] for k in ("nodes_total", "labels", "rels_total", "by_type", "same_as_n")}
            light_base = {k: base[k] for k in ("nodes_total", "labels", "rels_total", "by_type", "same_as_n")}
            if light_now != light_base:
                log.log(f"I1 失败：基线变化 now={light_now} base={light_base}")
                write_report(
                    state,
                    import_info={"aborted": True, "reason": "I1 baseline mismatch"},
                    verify=None,
                    env=env,
                    log_path=log.path,
                    report_path=report_path,
                    stopped="import-I1",
                )
                return 2
            log.log("I1 通过")

            for i in range(0, len(write_rows), _BATCH):
                batch = write_rows[i : i + _BATCH]
                rows = [{"name": r["name"], "value": r["value"]} for r in batch]
                updated = session.execute_write(_set_batch, anno_name, rows)
                if updated != len(batch):
                    log.log(
                        f"GATE FAIL: 批次更新数 {updated} ≠ {len(batch)}；"
                        f"names={ [r['name'] for r in batch] }"
                    )
                    write_report(
                        state,
                        import_info={
                            "aborted": True,
                            "written": written,
                            "failed_batch_start": i,
                            "failed_names": [r["name"] for r in batch],
                        },
                        verify=None,
                        env=env,
                        log_path=log.path,
                        report_path=report_path,
                        stopped="import-batch",
                    )
                    return 2
                written += updated
                log.log(f"batch {i}-{i+len(batch)-1} updated={updated} cumulative={written}")
    except Exception as exc:
        raise SystemExit("import 失败: " + _redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    info = {
        "aborted": False,
        "written": written,
        "failed": 0,
        "expected": len(write_rows),
        "discarded": state["plan_summary"]["discard_inners"],
    }
    state["import"] = info
    save_state(anno_name, state)
    write_report(state, import_info=info, verify=None, env=env, log_path=log.path, report_path=report_path, stopped=None)
    log.log(f"import 完成 written={written} failed=0")
    return 0


def stage_verify(env: dict, log: Logger, file_path: Path, anno_name: str, report_path: Path) -> int:
    state = load_state(anno_name)
    base = state["baseline"]
    plan = state["plan_summary"]
    payloads = state["payloads"]
    write_names = set(plan["write_names"])
    expected_write = plan["write_count"]
    sha_before = state["sha_before"]
    log.log("stage=verify")

    if not _PROP_NAME_RE.fullmatch(anno_name):
        raise SystemExit(f"标注名不合法: {anno_name}")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            now = snapshot_graph(session)
            # V1 counts — property name must be identifier; use fixed query form
            anno_count = _run(
                session,
                f"MATCH (n:Truth_Point) WHERE n.{anno_name} IS NOT NULL RETURN count(n) AS c",
            )[0]["c"]
            inner_anno = _run(
                session,
                f"""
                MATCH (n:Truth_Point)
                WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
                  AND n.{anno_name} IS NOT NULL
                RETURN count(n) AS c, collect(n.name) AS names
                """,
            )[0]
            without = _run(
                session,
                f"MATCH (n:Truth_Point) WHERE n.{anno_name} IS NULL RETURN count(n) AS c",
            )[0]["c"]
            # fetch all written values
            stored = _run(
                session,
                f"""
                MATCH (n:Truth_Point)
                WHERE n.{anno_name} IS NOT NULL
                RETURN n.name AS name, n.{anno_name} AS value
                ORDER BY name
                """,
            )
            # samples
            sample_names = [
                "巴路西亚",
                "被圣灵充满",
                "被圣灵充溢",
                "产生男孩子",
                "那灵的浇灌",
            ]
            # add 3 with content_2, 2 with content_3 from payloads
            c2 = [n for n, p in payloads.items() if p.get("content_2")][:3]
            c3 = [n for n, p in payloads.items() if p.get("content_3")][:2]
            for n in c2 + c3:
                if n not in sample_names:
                    sample_names.append(n)
            samples = []
            for name in sample_names:
                rows = _run(
                    session,
                    f"MATCH (n:Truth_Point {{name: $name}}) RETURN n.{anno_name} AS value",
                    {"name": name},
                )
                if not rows:
                    samples.append({"name": name, "present": False})
                    continue
                val = rows[0]["value"]
                samples.append(
                    {
                        "name": name,
                        "present": val is not None,
                        "length": len(val) if isinstance(val, str) else None,
                        "head80": _trunc(val, 80) if isinstance(val, str) else None,
                    }
                )
    except Exception as exc:
        raise SystemExit("verify 失败: " + _redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_now = _sha_import_dir()
    fails = []

    # V1
    if anno_count != expected_write:
        fails.append(f"V1 标注非空数 {anno_count} ≠ 拟写入 {expected_write}")
    if inner_anno["c"] != 0:
        fails.append(f"V1 括号内节点仍有标注: {inner_anno}")

    # V2 nodes/rels
    if now["nodes_total"] != base["nodes_total"] or now["labels"] != base["labels"]:
        fails.append(f"V2 节点变化 {base['labels']}→{now['labels']}")
    if now["rels_total"] != base["rels_total"] or now["by_type"] != base["by_type"]:
        fails.append(f"V2 关系变化 {base['by_type']}→{now['by_type']}")
    # name/same_as pairwise
    base_map = {r["name"]: r.get("same_as") for r in state["tp_props"]}
    now_map = {r["name"]: r.get("same_as") for r in now["tp_props"]}
    if len(base_map) != len(now_map):
        fails.append(f"V2 Truth_Point 数 {len(base_map)}→{len(now_map)}")
    diff_props = sum(1 for k, v in base_map.items() if now_map.get(k) != v)
    # also names only in one side
    only_base = set(base_map) - set(now_map)
    only_now = set(now_map) - set(base_map)
    if diff_props or only_base or only_now:
        fails.append(
            f"V2 name/same_as 不同数={diff_props} only_base={len(only_base)} only_now={len(only_now)}"
        )

    # V3 content
    content_diff = 0
    content_diff_names = []
    stored_map = {r["name"]: r["value"] for r in stored}
    for name, payload in payloads.items():
        if name not in write_names:
            continue
        expected = serialize_payload(payload)
        got = stored_map.get(name)
        if got != expected:
            # also try json loads compare
            try:
                same = json.loads(got) == payload if isinstance(got, str) else False
            except Exception:
                same = False
            if not same:
                content_diff += 1
                if len(content_diff_names) < 20:
                    content_diff_names.append(name)
    if content_diff:
        fails.append(f"V3 内容不一致 {content_diff} 个，样本 {content_diff_names}")

    # V4
    expect_without = _EXPECTED["Truth_Point"] - expected_write
    if without != expect_without:
        fails.append(f"V4 无标注节点 {without} ≠ {expect_without}")

    # V5 keys
    tp_keys = {r["key"] for r in now["node_keys"]["Truth_Point"]}
    if tp_keys != {"name", "same_as", anno_name}:
        fails.append(f"V5 Truth_Point 标注名 {tp_keys} ≠ {{name, same_as, {anno_name}}}")
    for lab in ("Trunk", "Branch"):
        keys = {r["key"] for r in now["node_keys"][lab]}
        if keys != {"name"}:
            fails.append(f"V5 {lab} 标注名 {keys} ≠ {{name}}")

    # V6 sha + constraints
    if sha_now["hashes"] != sha_before["hashes"]:
        fails.append("V6 可导入资料 SHA256 变化")

    def _ci_sig(rows):
        out = []
        for r in rows:
            out.append(
                {
                    k: r.get(k)
                    for k in ("name", "type", "entityType", "labelsOrTypes", "properties", "state")
                    if k in r
                }
            )
        return sorted(out, key=lambda x: str(x.get("name")))

    if _ci_sig(now["constraints"]) != _ci_sig(base["constraints"]):
        fails.append("V6 CONSTRAINTS 变化")
    if _ci_sig(now["indexes"]) != _ci_sig(base["indexes"]):
        fails.append("V6 INDEXES 变化")

    verify = {
        "ok": not fails,
        "fails": fails,
        "anno_count": anno_count,
        "inner_anno": inner_anno,
        "without": without,
        "expect_without": expect_without,
        "content_diff": content_diff,
        "content_diff_names": content_diff_names,
        "name_same_as_diff": diff_props,
        "samples": samples,
        "node_keys": now["node_keys"],
        "nodes_total": now["nodes_total"],
        "labels": now["labels"],
        "rels_total": now["rels_total"],
        "by_type": now["by_type"],
        "sha_ok": sha_now["hashes"] == sha_before["hashes"],
        "sha_now": {"n": sha_now["n"], "bytes": sha_now["bytes"]},
    }
    state["verify"] = verify
    # drop huge tp_props from re-save? keep
    save_state(anno_name, state)
    write_report(state, import_info=state.get("import"), verify=verify, env=env, log_path=log.path, report_path=report_path, stopped=None if not fails else "verify")
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        return 2
    log.log("verify 全部通过")
    return 0


def write_report(
    state: dict,
    import_info: dict | None,
    verify: dict | None,
    env: dict,
    log_path: Path,
    report_path: Path,
    stopped: str | None,
) -> None:
    base = state["baseline"]
    plan = state["plan_summary"]
    match = state["match"]
    anno = state["anno_name"]
    lines: list[str] = []
    a = lines.append
    a(f"# neo4j-v4 导入标注 `{anno}` 报告")
    a("")
    a(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.import_annotation`。")
    a(f"源文件：`{state['file']}`。只 SET `n.{anno}`；未运行 build_v4.py；未打印密码。")
    a("")
    a("## 摘要")
    a("")
    a(f"1. **基线 vs 预期**：{'相符' if not [x for x in (state.get('fails') or []) if x.startswith('nodes') or 'rels' in x or x.startswith('Truth') or x.startswith('BELONG') or '关系类型' in x or x.startswith('旧关系') or x.startswith('same_as')] else '见 fails'}；"
      f"节点={base['nodes_total']} labels={base['labels']}；关系={base['rels_total']} by_type={base['by_type']}；same_as={base['same_as_n']}/{base['no_same_as_n']}。")
    a(f"2. **JSON**：记录数={plan['n_records']}；content_1/2/3 非空={plan['content_counts']}；重复 name={plan['dup_names'] or '无'}；"
      f"其他键={plan['extra_keys'] or '无'}；含「城市」={plan['has_city']}。")
    a(f"3. **匹配**：找到 {match['found_n']}；找不到 {match['missing_n']} → {match['missing'] or '无'}；多匹配={match['multi'] or '无'}。")
    paren_brief = [
        f"{r['outer']}/{r['inner']}: {r['comparison']} → {r['action']}"
        for r in plan["paren_rows"]
        if r["outer_in_json"] or r["inner_in_json"]
    ]
    a(f"4. **括号词条**：{paren_brief or '本 JSON 未涉及任何一对'}；丢弃={plan['discard_inners']}；需决定={len(plan['need_decision'])}。")
    if import_info and not import_info.get("aborted"):
        a(f"5. **写入**：写入={import_info.get('written')}；丢弃={len(import_info.get('discarded') or [])}；失败={import_info.get('failed')}。")
    elif import_info:
        a(f"5. **写入中止**：{import_info}")
    else:
        a(f"5. **写入**：尚未 import；拟写入={plan['write_count']}；丢弃={plan['discard_inners']}。")
    if verify:
        a(f"6. **V1–V6**：ok={verify['ok']}；标注非空={verify['anno_count']}；括号内标注={verify['inner_anno']['c']}；"
          f"无标注节点={verify['without']}（预期 {verify['expect_without']}）；内容不一致={verify['content_diff']}；"
          f"name/same_as 不同={verify['name_same_as_diff']}；SHA ok={verify['sha_ok']}；fails={verify['fails'] or '无'}。")
    else:
        a("6. **V1–V6**：尚未 verify。")
    a(f"7. **长度分布**：{plan['len_stats']}。")
    a(f"8. **待决**：{plan['need_decision'] or '无'}；stopped={stopped}；check_ok={state.get('check_ok')}。")
    a("")

    a("## C. check")
    a(f"- 基线节点 {base['nodes_total']} {base['labels']}；same_as {base['same_as_n']}/{base['no_same_as_n']}")
    a(f"- 关系 {base['rels_total']} {base['by_type']}")
    a(f"- Truth_Point 标注非空：{base['node_keys']['Truth_Point']}")
    a(f"- SHA 可导入资料：n={state['sha_before']['n']} bytes={state['sha_before']['bytes']} check后一致={state.get('sha_ok')}")
    a("")
    a("### 括号 8 对")
    for r in plan["paren_rows"]:
        a(f"- {r['outer']} / {r['inner']}: outer_in={r['outer_in_json']} inner_in={r['inner_in_json']} "
          f"比较={r.get('comparison')} 动作={r.get('action')}")
        if r.get("comparison") == "不同":
            a(f"  - outer: {_trunc(r.get('outer_summary'), 200)}")
            a(f"  - inner: {_trunc(r.get('inner_summary'), 200)}")
    a("")
    a(f"### 拟写入 {plan['write_count']}；丢弃 {plan['discard_inners']}；长度 {plan['len_stats']}")
    a(f"- 闸门失败：{state.get('fails') or '无'}")
    a("")

    a("## I. import")
    a("未执行。" if not import_info else f"```json\n{json.dumps(import_info, ensure_ascii=False, indent=2)}\n```")
    a("")

    a("## V. verify")
    if not verify:
        a("未执行。")
    else:
        a(f"- ok={verify['ok']} fails={verify['fails'] or '无'}")
        a(f"- anno_count={verify['anno_count']} inner={verify['inner_anno']} without={verify['without']}")
        a(f"- nodes/rels: {verify['nodes_total']} {verify['labels']} / {verify['rels_total']} {verify['by_type']}")
        a(f"- node_keys: {verify['node_keys']}")
        a("- 抽样：")
        for s in verify["samples"]:
            a(f"  - {s}")
    a("")

    a("## 最终验证")
    draft = "\n".join(lines)
    leaked = bool(env["pass4"] and env["pass4"] in draft)
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    leaked_log = bool(env["pass4"] and env["pass4"] in log_text)
    a("- 只做了 SET 指定标注：是（若已 import）")
    a("- 未运行 build_v4.py：是")
    a("- 未读取并打印 .env 值：是")
    a(f"- 报告密码检查：{'不通过' if leaked else '通过'}；日志密码检查：{'不通过' if leaked_log else '通过'}")
    try:
        gs = subprocess.check_output(
            ["git", "status", "--short"],
            cwd=str(_REPO),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        gs = str(exc)
    a("- git status（本任务仅应新增 import_annotation.py / 本报告 / logs；其余为既有改动）：")
    a("```")
    a(gs)
    a("```")
    a("")

    text = "\n".join(lines) + "\n"
    if env["pass4"] and env["pass4"] in text:
        raise SystemExit("中止：报告含密码")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 Truth_Point 标注到 neo4j-v4")
    parser.add_argument("--stage", required=True, choices=["check", "import", "verify"])
    parser.add_argument("--file", required=True, help="源 JSON 路径")
    parser.add_argument("--name", required=True, help="标注名（Neo4j 属性名）")
    parser.add_argument(
        "--fields",
        default="",
        help="要序列化的字段，逗号分隔；默认=除 name 外原顺序全部字段",
    )
    parser.add_argument("--report", default="", help="报告路径")
    args = parser.parse_args()

    if not _PROP_NAME_RE.fullmatch(args.name):
        raise SystemExit(f"标注名必须是合法标识符: {args.name}")
    file_path = Path(args.file)
    if not file_path.is_file():
        raise SystemExit(f"文件不存在: {file_path}")
    fields = [x.strip() for x in args.fields.split(",") if x.strip()] or None
    report_path = Path(args.report) if args.report else default_report(args.name)

    env = _load_env()
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = Logger(_LOG_DIR / f"import_annotation_{args.name}_{_now()}.log", env["pass4"])
    log.log(
        f"stage={args.stage} name={args.name}；NEO4J_V4_URI/USER/PASSWORD（值不记录）"
    )

    if args.stage == "check":
        return stage_check(env, log, file_path, args.name, fields, report_path)
    if args.stage == "import":
        return stage_import(env, log, file_path, args.name, report_path)
    return stage_verify(env, log, file_path, args.name, report_path)


if __name__ == "__main__":
    sys.exit(main())
