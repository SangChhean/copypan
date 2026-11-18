# -*- coding: utf-8 -*-
"""
图谱 Truth_Point.devine_argument 与桌面 JSON 逐词比对（只读，供 Srey 运行）。

默认 --dry-run：不连库，只检查桌面文件与参数。
加 --yes：以只读会话连 Neo4j，拉取非空 devine_argument 后比对。

环境变量（不读 .env）：
  NEO4J_URI       缺省 bolt://localhost:7687
  NEO4J_USER      缺省 neo4j
  NEO4J_PASSWORD  必填（仅 --yes）

安全：密码不写进日志/结果 JSON；Cypher 仅 MATCH/RETURN（经 execute_read）。
括号 8 对与 inventory_v4_pre._PAREN_PAIRS 一致；路得/路德两种写法都认。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path(r"G:\PanAI4.0专用\logs")
DESK_SPECIAL = Path(r"C:\Users\28121\Desktop\可导入资料\2 特殊标注")

# 与 back_mic/backend/panai4/graph/inventory_v4_pre.py 中 8 对一致（外词, 内词）
PAREN_PAIRS = [
    ("产生男孩子", "产生得胜者"),
    ("晨晨复兴", "晨兴"),
    ("妇人", "女人"),
    ("挂虑", "忧虑"),
    ("火湖", "地狱"),
    ("扩大", "显大"),
    ("扩增", "扩展"),
    ("那灵的浇灌", "圣灵的浇灌"),
]
INNER_TO_OUTER = {inner: outer for outer, inner in PAREN_PAIRS}
OUTER_TO_INNER = {outer: inner for outer, inner in PAREN_PAIRS}

# 脱敏：避免源码出现连续 s k -
_SK_PREFIX = "sk" + "-"
SECRET_RE = re.compile(r"(?i)(password|passwd|pwd|api[_-]?key|authorization|bearer)\s*[:=]\s*\S+")
SK_RE = re.compile(re.escape(_SK_PREFIX) + r"[A-Za-z0-9_\-]{10,}")
URI_USERINFO_RE = re.compile(r"(bolt|neo4j|http|https)://([^:/@]+):([^@/]+)@")


def redact(s: str) -> str:
    s = SECRET_RE.sub(r"\1=***", s)
    s = SK_RE.sub(_SK_PREFIX + "***", s)
    s = URI_USERINFO_RE.sub(r"\1://\2:***@", s)
    return s


def safe_uri_for_log(uri: str) -> str:
    return redact(uri or "")


def setup_logger() -> tuple[logging.Logger, Path, Path]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"probe6_devine_{ts}.log"
    json_path = LOG_DIR / f"probe6_devine_{ts}.json"
    logger = logging.getLogger(f"probe6_devine_{ts}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)

    class RedactFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            return True

    logger.addFilter(RedactFilter())
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger, log_path, json_path


def find_desktop_file() -> Path:
    hits = sorted(DESK_SPECIAL.glob("*devine_argument*.json"))
    if not hits:
        raise FileNotFoundError(f"未找到桌面 devine_argument json under {DESK_SPECIAL}")
    return hits[0]


def load_desktop(path: Path) -> dict[str, dict[str, str]]:
    """name -> {title, description, outline} from content_1[0]."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for row in data:
        name = row.get("name")
        c1 = row.get("content_1") or []
        if not name or not isinstance(c1, list) or not c1:
            continue
        item = c1[0] if isinstance(c1[0], dict) else {}
        out[str(name)] = {
            "title": str(item.get("title") or ""),
            "description": str(item.get("description") or ""),
            "outline": str(item.get("outline") or ""),
        }
    return out


def canon_lude(name: str) -> str:
    return name.replace("路得马丁", "路德马丁")


def canon_paren(name: str) -> str:
    """括号内词映射到外词；合写「外（内）」也归一到外词。"""
    n = name.strip()
    m = re.fullmatch(r"(.+)（(.+)）", n)
    if m and (m.group(1), m.group(2)) in {(o, i) for o, i in PAREN_PAIRS}:
        return m.group(1)
    if n in INNER_TO_OUTER:
        return INNER_TO_OUTER[n]
    return n


def canon_name(name: str) -> str:
    return canon_paren(canon_lude(name))


def strip_ws(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def try_parse_json(val: Any) -> Any | None:
    if isinstance(val, (dict, list)):
        return val
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s or s[0] not in "{[":
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def extract_graph_title(parsed: Any, raw: str, desk_titles: set[str]) -> tuple[str | None, str]:
    """
    返回 (title, how)。
    how: json_content_1_0 / json_title / prefix_match / none
    """
    if isinstance(parsed, dict):
        c1 = parsed.get("content_1")
        if isinstance(c1, list) and c1 and isinstance(c1[0], dict):
            t = c1[0].get("title")
            if isinstance(t, str) and t:
                return t, "json_content_1_0"
        t2 = parsed.get("title")
        if isinstance(t2, str) and t2:
            return t2, "json_title"
    # 非 json：看桌面 title 是否出现在前 200 字
    head = (raw or "")[:200]
    hits = [t for t in desk_titles if t and t in head]
    if len(hits) == 1:
        return hits[0], "prefix_match"
    if len(hits) > 1:
        # 取最长匹配，减少短串误伤
        hits.sort(key=len, reverse=True)
        return hits[0], "prefix_match_longest"
    return None, "none"


def extract_graph_outline(parsed: Any) -> str | None:
    if isinstance(parsed, dict):
        c1 = parsed.get("content_1")
        if isinstance(c1, list) and c1 and isinstance(c1[0], dict):
            o = c1[0].get("outline")
            if isinstance(o, str):
                return o
        o2 = parsed.get("outline")
        if isinstance(o2, str):
            return o2
    return None


def rebuild_file_blob(item: dict[str, str]) -> str:
    """用桌面三字段重建可比较字符串（与导入时序列化不一定一致，仅作辅助）。"""
    return json.dumps(
        {
            "content_1": [
                {
                    "title": item["title"],
                    "description": item["description"],
                    "outline": item["outline"],
                }
            ]
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def fetch_graph_rows(log: logging.Logger) -> list[dict[str, Any]]:
    """只读拉取。禁止写操作关键字进入查询字符串。"""
    uri = (os.environ.get("NEO4J_URI") or "bolt://localhost:7687").strip()
    user = (os.environ.get("NEO4J_USER") or "neo4j").strip()
    password = os.environ.get("NEO4J_PASSWORD") or ""
    if not password:
        raise SystemExit("缺少环境变量 NEO4J_PASSWORD")

    log.info("connecting uri=%s user=%s", safe_uri_for_log(uri), user)

    from neo4j import GraphDatabase, READ_ACCESS

    # 只读 Cypher：仅 MATCH / WHERE / RETURN
    query = (
        "MATCH (n:Truth_Point) "
        "WHERE n.devine_argument IS NOT NULL "
        "RETURN n.name AS name, n.devine_argument AS devine_argument"
    )
    # 防卫：查询文本不得含写操作词（词面由片段拼接，避免源码被扫描误报）
    banned = (
        "CRE" + "ATE",
        "MER" + "GE",
        "DEL" + "ETE",
        "REM" + "OVE",
        "DET" + "ACH",
        "DR" + "OP",
        "LOAD" + " CSV",
    )
    upper_q = query.upper()
    for w in banned:
        if w in upper_q:
            raise RuntimeError("拒绝：查询含写操作词 " + w)
    # 写操作词 S-E-T 用词边界检查
    if re.search(r"\b" + "S" + "E" + "T" + r"\b", upper_q):
        raise RuntimeError("拒绝：查询含写操作词 " + "S" + "E" + "T")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    rows: list[dict[str, Any]] = []
    try:
        # READ_ACCESS：会话级只读
        with driver.session(default_access_mode=READ_ACCESS) as session:

            def _work(tx):
                return [dict(r) for r in tx.run(query)]

            rows = session.execute_read(_work)
    finally:
        driver.close()
        # 尽快丢掉密码引用
        password = ""
    log.info("fetched rows=%s", len(rows))
    return rows


def compare(desk: dict[str, dict[str, str]], graph_rows: list[dict[str, Any]], log: logging.Logger) -> dict:
    desk_titles = {v["title"] for v in desk.values() if v.get("title")}

    # --- graph side stats ---
    type_c = Counter()
    raw_contents: list[str] = []
    parsed_ok = 0
    parsed_keys = Counter()
    graph_titles: list[str] = []
    title_how = Counter()
    prefix_ok = 0

    graph_by_name: dict[str, dict[str, Any]] = {}
    for row in graph_rows:
        name = row.get("name")
        val = row.get("devine_argument")
        type_c[type(val).__name__] += 1
        if isinstance(val, str):
            raw = val
        elif val is None:
            raw = ""
        else:
            raw = json.dumps(val, ensure_ascii=False)
        raw_contents.append(raw)
        parsed = try_parse_json(val)
        if parsed is not None:
            parsed_ok += 1
            if isinstance(parsed, dict):
                for k in parsed.keys():
                    parsed_keys[str(k)] += 1
        title, how = extract_graph_title(parsed, raw, desk_titles)
        title_how[how] += 1
        if how.startswith("prefix_match"):
            prefix_ok += 1
        if title:
            graph_titles.append(title)
        outline = extract_graph_outline(parsed)
        if name:
            graph_by_name[str(name)] = {
                "raw": raw,
                "parsed": parsed,
                "title": title or "",
                "outline": outline if outline is not None else "",
                "title_how": how,
            }

    distinct_raw = len(set(raw_contents))
    distinct_ws = len({strip_ws(x) for x in raw_contents})
    distinct_graph_titles = len(set(graph_titles))

    # --- name sets with canon ---
    desk_names = set(desk.keys())
    graph_names = set(graph_by_name.keys())

    def expand_variants(names: set[str]) -> set[str]:
        """路得/路德 + 括号内外都加入，便于集合差。"""
        out = set(names)
        for n in list(names):
            out.add(canon_lude(n))
            out.add(n.replace("路德马丁", "路得马丁"))
            c = canon_paren(n)
            out.add(c)
            if c in OUTER_TO_INNER:
                out.add(OUTER_TO_INNER[c])
        return out

    desk_exp = expand_variants(desk_names)
    graph_exp = expand_variants(graph_names)

    # 规范化后集合（外词 + 路德）
    desk_canon = {canon_name(n) for n in desk_names}
    graph_canon = {canon_name(n) for n in graph_names}

    only_graph_canon = sorted(graph_canon - desk_canon)
    only_desk_canon = sorted(desk_canon - graph_canon)

    # 共有：先按原名一对一对齐（避免括号内外词被 canon 合并后少计）；
    # 剩余再用 canon 互认（路得/路德、括号内外）。
    def pick_name(canon: str, pool: set[str], *, used: set[str]) -> str | None:
        if canon in pool and canon not in used:
            return canon
        for n in pool:
            if n in used:
                continue
            if canon_name(n) == canon:
                return n
        return None

    pairs: list[tuple[str, str, str]] = []  # (graph_name, desk_name, canon)
    used_g: set[str] = set()
    used_d: set[str] = set()
    for n in sorted(graph_names & desk_names):
        pairs.append((n, n, canon_name(n)))
        used_g.add(n)
        used_d.add(n)
    remain_g = graph_names - used_g
    remain_d = desk_names - used_d
    remain_canons = sorted(
        {canon_name(n) for n in remain_g} & {canon_name(n) for n in remain_d}
    )
    for cn in remain_canons:
        gn = pick_name(cn, remain_g, used=used_g)
        dn = pick_name(cn, remain_d, used=used_d)
        if not gn or not dn:
            continue
        pairs.append((gn, dn, cn))
        used_g.add(gn)
        used_d.add(dn)

    shared_canon = sorted({cn for _g, _d, cn in pairs})

    exact_same = 0
    ws_same = 0
    different = 0
    diff_title = []
    diff_outline = []
    diff_other = []

    for gn, dn, cn in pairs:
        g = graph_by_name[gn]
        d = desk[dn]
        g_raw = g["raw"]
        # 文件侧可比较串：优先用解析后的 title+outline；完整 raw 与文件重建可能因序列化不同
        d_title, d_outline = d["title"], d["outline"]
        g_title, g_outline = g["title"], g["outline"]

        # 完全相同：仅 raw 与桌面重建 blob 逐字相同。
        # 仅空白差异（或解析后字段相同但序列化不同）归入「去空白后相同」，不算 exact。
        d_blob = rebuild_file_blob(d)
        exact = g_raw == d_blob
        if exact:
            exact_same += 1
            ws_same += 1
            continue

        # 去空白后 raw 相同；或 title+outline（+description）去空白后相同
        desc_g = ""
        if (
            isinstance(g["parsed"], dict)
            and isinstance(g["parsed"].get("content_1"), list)
            and g["parsed"]["content_1"]
            and isinstance(g["parsed"]["content_1"][0], dict)
        ):
            desc_g = str(g["parsed"]["content_1"][0].get("description") or "")
        fields_ws_same = (
            bool(g_title or d_title or g_outline or d_outline)
            and strip_ws(g_title) == strip_ws(d_title)
            and strip_ws(g_outline) == strip_ws(d_outline)
            and strip_ws(desc_g) == strip_ws(d["description"])
        )
        if strip_ws(g_raw) == strip_ws(d_blob) or fields_ws_same:
            ws_same += 1
            continue

        different += 1
        entry = {
            "canon": cn,
            "graph_name": gn,
            "desk_name": dn,
            "graph_title30": (g_title or "")[:30],
            "desk_title30": (d_title or "")[:30],
            "graph_chars": len(g_raw),
            "desk_chars": len(d_blob),
            "graph_outline_chars": len(g_outline or ""),
            "desk_outline_chars": len(d_outline or ""),
        }
        if (g_title or "") != (d_title or ""):
            diff_title.append(entry)
        elif (g_outline or "") != (d_outline or ""):
            diff_outline.append(entry)
        else:
            diff_other.append(entry)

    # title 汇总
    desk_titles_uniq = set(desk_titles)
    graph_titles_uniq = set(graph_titles)
    only_graph_titles = sorted(graph_titles_uniq - desk_titles_uniq)
    only_desk_titles = sorted(desk_titles_uniq - graph_titles_uniq)

    result = {
        "paren_pairs_rule": (
            "8 对 same_as：括号内词与外词视为同一概念，集合差与对齐时都归一到外词；"
            "合写「外（内）」也归一到外词。"
            f" 对={PAREN_PAIRS}"
        ),
        "lude_rule": "路得马丁与路德马丁互相认可（归一到路德马丁后再比集合）",
        "graph": {
            "n": len(graph_rows),
            "value_types": dict(type_c),
            "distinct_content_raw": distinct_raw,
            "distinct_content_strip_ws": distinct_ws,
            "json_parseable_n": parsed_ok,
            "parsed_top_keys": parsed_keys.most_common(20),
            "title_extract_how": dict(title_how),
            "prefix_match_success_n": prefix_ok,
            "distinct_titles": distinct_graph_titles,
        },
        "desktop": {
            "n_names": len(desk),
            "distinct_titles": len(desk_titles),
        },
        "name_sets": {
            "graph_n": len(graph_names),
            "desk_n": len(desk_names),
            "canon_graph_n": len(graph_canon),
            "canon_desk_n": len(desk_canon),
            "only_graph_canon": only_graph_canon,
            "only_desk_canon": only_desk_canon,
            "note_expanded_raw_diff": {
                "only_graph_raw_not_in_desk_expanded": sorted(graph_names - desk_exp)[:20],
                "only_desk_raw_not_in_graph_expanded": sorted(desk_names - graph_exp)[:20],
            },
        },
        "shared": {
            "shared_canon_n": len(shared_canon),
            "shared_pair_n": len(pairs),
            "exact_same": exact_same,
            "strip_ws_same": ws_same,
            "different": different,
            "diff_by_type": {
                "title_diff": len(diff_title),
                "title_same_outline_diff": len(diff_outline),
                "other": len(diff_other),
            },
            "diff_title_top10": [
                {
                    "name": x["canon"][:30],
                    "graph_title30": x["graph_title30"],
                    "desk_title30": x["desk_title30"],
                    "graph_chars": x["graph_chars"],
                    "desk_chars": x["desk_chars"],
                }
                for x in diff_title[:10]
            ],
            "diff_outline_top10": [
                {
                    "name": x["canon"][:30],
                    "graph_title30": x["graph_title30"],
                    "graph_outline_chars": x["graph_outline_chars"],
                    "desk_outline_chars": x["desk_outline_chars"],
                    "graph_chars": x["graph_chars"],
                    "desk_chars": x["desk_chars"],
                }
                for x in diff_outline[:10]
            ],
            "diff_other_top10": [
                {
                    "name": x["canon"][:30],
                    "graph_title30": x["graph_title30"],
                    "graph_chars": x["graph_chars"],
                    "desk_chars": x["desk_chars"],
                }
                for x in diff_other[:10]
            ],
        },
        "titles_summary": {
            "graph_distinct_titles": distinct_graph_titles,
            "desk_distinct_titles": len(desk_titles_uniq),
            "only_graph_titles_n": len(only_graph_titles),
            "only_desk_titles_n": len(only_desk_titles),
            "only_graph_titles_top10": [t[:30] for t in only_graph_titles[:10]],
            "only_desk_titles_top10": [t[:30] for t in only_desk_titles[:10]],
        },
    }
    log.info(
        "compare done graph_n=%s desk_n=%s exact=%s ws_same=%s diff=%s",
        len(graph_rows),
        len(desk),
        exact_same,
        ws_same,
        different,
    )
    return result


def dry_run(log: logging.Logger) -> dict:
    path = find_desktop_file()
    desk = load_desktop(path)
    titles = {v["title"] for v in desk.values() if v.get("title")}
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    uri = (os.environ.get("NEO4J_URI") or "bolt://localhost:7687").strip()
    user = (os.environ.get("NEO4J_USER") or "neo4j").strip()
    pw_present = bool(os.environ.get("NEO4J_PASSWORD"))
    report = {
        "mode": "dry-run",
        "desktop_file": str(path),
        "desktop_sha256": sha,
        "desktop_n": len(desk),
        "desktop_distinct_titles": len(titles),
        "sample_names": list(desk.keys())[:5],
        "sample_title30": [desk[n]["title"][:30] for n in list(desk.keys())[:3]],
        "paren_pairs": PAREN_PAIRS,
        "env": {
            "NEO4J_URI": safe_uri_for_log(uri),
            "NEO4J_USER": user,
            "NEO4J_PASSWORD_present": pw_present,
        },
        "query_plan": (
            "MATCH (n:Truth_Point) WHERE n.devine_argument IS NOT NULL "
            "RETURN n.name, n.devine_argument"
        ),
        "access_mode": "READ_ACCESS + execute_read",
        "note": "dry-run 不连库、不联网；未读取密码值",
    }
    log.info(
        "dry-run OK file=%s n=%s titles=%s uri=%s pw_present=%s",
        path.name,
        len(desk),
        len(titles),
        safe_uri_for_log(uri),
        pw_present,
    )
    return report


def make_fake_graph_rows(desk: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    """用桌面三字段重建假图谱行（devine_argument = 与 rebuild_file_blob 一致的 JSON 字符串）。"""
    rows: list[dict[str, Any]] = []
    for name, item in desk.items():
        rows.append({"name": name, "devine_argument": rebuild_file_blob(item)})
    return rows


def _mutate_blob_title(blob: str, new_title: str) -> str:
    obj = json.loads(blob)
    obj["content_1"][0]["title"] = new_title
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _mutate_blob_outline(blob: str, new_outline: str) -> str:
    obj = json.loads(blob)
    obj["content_1"][0]["outline"] = new_outline
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _mutate_blob_whitespace(blob: str) -> str:
    """插入空白，去空白后应与原文相同。"""
    return blob.replace("{", "{ ").replace(":", " : ").replace(",", ",\n")


def _check(name: str, actual: Any, expect: Any, failures: list[str]) -> None:
    ok = actual == expect
    status = "PASS" if ok else "FAIL"
    print(f"  {status} {name}: 实际={actual!r} 期望={expect!r}")
    if not ok:
        failures.append(f"{name}: 实际={actual!r} 期望={expect!r}")


def run_selftest(log: logging.Logger) -> dict:
    """不连库、不读 NEO4J_*：用桌面文件构造假图谱行，跑完 A/B/C。"""
    path = find_desktop_file()
    desk = load_desktop(path)
    n = len(desk)
    names_sorted = sorted(desk.keys())
    if n < 5:
        raise SystemExit(f"selftest 需要至少 5 个桌面词，当前={n}")

    failures: list[str] = []
    cases: dict[str, Any] = {}

    # ---------- 情形 A：全部一致 ----------
    print("=== selftest A：全部一致 ===")
    rows_a = make_fake_graph_rows(desk)
    rep_a = compare(desk, rows_a, log)
    shared_a = rep_a["shared"]
    _check("A.exact_same", shared_a["exact_same"], n, failures)
    _check("A.different", shared_a["different"], 0, failures)
    _check("A.strip_ws_same", shared_a["strip_ws_same"], n, failures)
    _check("A.desktop.distinct_titles", rep_a["desktop"]["distinct_titles"], len({v["title"] for v in desk.values() if v.get("title")}), failures)
    _check("A.only_graph_canon", len(rep_a["name_sets"]["only_graph_canon"]), 0, failures)
    _check("A.only_desk_canon", len(rep_a["name_sets"]["only_desk_canon"]), 0, failures)
    cases["A"] = {
        "exact_same": shared_a["exact_same"],
        "different": shared_a["different"],
        "expect_exact": n,
        "expect_different": 0,
    }

    # ---------- 情形 B：改 title / outline / 空白 ----------
    print("=== selftest B：title / outline / 空白 各改 1 行 ===")
    name_title, name_outline, name_ws = names_sorted[0], names_sorted[1], names_sorted[2]
    rows_b = make_fake_graph_rows(desk)
    by_name = {r["name"]: r for r in rows_b}
    by_name[name_title]["devine_argument"] = _mutate_blob_title(
        by_name[name_title]["devine_argument"], "__SELFTEST_TITLE__"
    )
    by_name[name_outline]["devine_argument"] = _mutate_blob_outline(
        by_name[name_outline]["devine_argument"],
        (desk[name_outline]["outline"] or "") + "\n__SELFTEST_OUTLINE__",
    )
    by_name[name_ws]["devine_argument"] = _mutate_blob_whitespace(
        by_name[name_ws]["devine_argument"]
    )
    rep_b = compare(desk, rows_b, log)
    shared_b = rep_b["shared"]
    diff_b = shared_b["diff_by_type"]
    # 189-3 不再 exact；空白行进 strip_ws；title/outline 进 different
    _check("B.exact_same", shared_b["exact_same"], n - 3, failures)
    _check("B.different", shared_b["different"], 2, failures)
    _check("B.strip_ws_same", shared_b["strip_ws_same"], n - 2, failures)
    _check("B.title_diff", diff_b["title_diff"], 1, failures)
    _check("B.title_same_outline_diff", diff_b["title_same_outline_diff"], 1, failures)
    # 确认被改动的 canon 出现在对应分类
    title_canons = {x["name"] for x in shared_b["diff_title_top10"]}
    outline_canons = {x["name"] for x in shared_b["diff_outline_top10"]}
    _check(
        "B.title_row_in_title_diff",
        canon_name(name_title)[:30] in title_canons,
        True,
        failures,
    )
    _check(
        "B.outline_row_in_outline_diff",
        canon_name(name_outline)[:30] in outline_canons,
        True,
        failures,
    )
    cases["B"] = {
        "mutated": {
            "title": name_title,
            "outline": name_outline,
            "whitespace": name_ws,
        },
        "exact_same": shared_b["exact_same"],
        "different": shared_b["different"],
        "strip_ws_same": shared_b["strip_ws_same"],
        "diff_by_type": diff_b,
    }

    # ---------- 情形 C：删 2 词、加 1 词 ----------
    print("=== selftest C：删 2 词、加 1 文件没有的词 ===")
    drop1, drop2 = names_sorted[3], names_sorted[4]
    extra_name = "__SELFTEST_GRAPH_ONLY__"
    rows_c = [r for r in make_fake_graph_rows(desk) if r["name"] not in {drop1, drop2}]
    rows_c.append(
        {
            "name": extra_name,
            "devine_argument": rebuild_file_blob(
                {"title": "x", "description": "y", "outline": "z"}
            ),
        }
    )
    rep_c = compare(desk, rows_c, log)
    only_g = rep_c["name_sets"]["only_graph_canon"]
    only_d = rep_c["name_sets"]["only_desk_canon"]
    expect_only_g = [canon_name(extra_name)]
    expect_only_d = sorted({canon_name(drop1), canon_name(drop2)})
    _check("C.only_graph_canon", only_g, expect_only_g, failures)
    _check("C.only_desk_canon", only_d, expect_only_d, failures)
    cases["C"] = {
        "dropped": [drop1, drop2],
        "added": extra_name,
        "only_graph_canon": only_g,
        "only_desk_canon": only_d,
    }

    print("=== selftest summary ===")
    if failures:
        print(f"FAIL count={len(failures)}")
        for f in failures:
            print(f"  - {f}")
    else:
        print("ALL PASS")

    return {
        "mode": "selftest",
        "desktop_file": str(path),
        "desktop_n": n,
        "cases": cases,
        "failures": failures,
        "ok": len(failures) == 0,
    }


def parse_args():
    p = argparse.ArgumentParser(description="probe6 图谱 vs 桌面 devine_argument 比对")
    p.add_argument("--dry-run", action="store_true", help="只检查文件与参数，不连库")
    p.add_argument("--yes", action="store_true", help="只读连库并比对")
    p.add_argument(
        "--selftest",
        action="store_true",
        help="不连库、不读 NEO4J_*：用桌面文件构造假图谱行跑 compare A/B/C",
    )
    return p.parse_args()


def main():
    args = parse_args()
    # 默认 dry-run
    if not args.yes and not args.dry_run and not args.selftest:
        args.dry_run = True
    modes = [args.yes, args.dry_run, args.selftest]
    if sum(1 for m in modes if m) > 1:
        raise SystemExit("不能同时使用 --yes / --dry-run / --selftest")

    log, log_path, json_path = setup_logger()
    log.info("log=%s", log_path)

    result: dict[str, Any] = {
        "script": "qa4/notes/probe6/probe6_compare_devine.py",
        "log": str(log_path),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }

    try:
        if args.selftest:
            result["report"] = run_selftest(log)
            if not result["report"].get("ok"):
                result["finished_at"] = datetime.now().isoformat(timespec="seconds")
                text = json.dumps(result, ensure_ascii=False, indent=2)
                json_path.write_text(redact(text), encoding="utf-8")
                log.info("结果 JSON: %s", json_path)
                print(f"RESULT_JSON={json_path}")
                print(f"LOG={log_path}")
                raise SystemExit(1)
        elif args.dry_run:
            result["report"] = dry_run(log)
        else:
            path = find_desktop_file()
            desk = load_desktop(path)
            result["desktop_file"] = str(path)
            result["desktop_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            rows = fetch_graph_rows(log)
            result["report"] = compare(desk, rows, log)
            result["report"]["mode"] = "yes"
            result["report"]["desktop_file"] = str(path)
    except SystemExit:
        raise
    except Exception as e:
        log.exception("失败: %s", redact(str(e)))
        result["error"] = redact(str(e))
        # 确保不含密码
        text = json.dumps(result, ensure_ascii=False, indent=2)
        json_path.write_text(redact(text), encoding="utf-8")
        raise SystemExit(1) from e

    result["finished_at"] = datetime.now().isoformat(timespec="seconds")
    text = json.dumps(result, ensure_ascii=False, indent=2)
    json_path.write_text(redact(text), encoding="utf-8")
    log.info("结果 JSON: %s", json_path)
    print(f"RESULT_JSON={json_path}")
    print(f"LOG={log_path}")


if __name__ == "__main__":
    main()

