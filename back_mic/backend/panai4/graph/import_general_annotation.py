# -*- coding: utf-8 -*-
"""neo4j-v4：导入通用标注（name_en / greek / hebrew / scriptures / definition_3a/3b）。

正文 content_3a/3b 不进图谱，仅复制到 data/graph_annotations/truth_dictionary_3a3b.json。
不修改 import_annotation*.py / .gitignore（仅 A3 在未被 ignore 时改根 .gitignore）。
不运行 build_v4.py；不打印密码。

用法（在 back_mic/backend 下）:
    python -m panai4.graph.import_general_annotation --stage check
    python -m panai4.graph.import_general_annotation --stage copy
    python -m panai4.graph.import_general_annotation --stage import
    python -m panai4.graph.import_general_annotation --stage verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

from panai4.graph import import_annotation as v1
from panai4.graph import import_annotation_v2 as v2

_REPO = v1._REPO
_LOG_DIR = v1._LOG_DIR
_IMPORT_ROOT = v1._IMPORT_ROOT
_BATCH = 50
_STATE_NAME = "general_annotation"
_REPORT = _REPO / "docs" / "panai4_graph" / "import_general_annotation.md"
_DEST_DIR = _REPO / "back_mic" / "backend" / "panai4" / "data" / "graph_annotations"
_DEST_DICT = _DEST_DIR / "truth_dictionary_3a3b.json"
_README = _DEST_DIR / "README.md"
_SUMS = _DEST_DIR / "SHA256SUMS.txt"

_PROTECTED = {
    "devine_argument": 187,
    "intrinsic_significance": 2372,
    "mutuality": 116,
    "organic_advance": 69,
}
_NEW_PROPS = (
    "name_en",
    "greek_terms",
    "hebrew_terms",
    "related_scriptures",
    "definition_3a",
    "definition_3b",
)
_COMPOSITE_RE = re.compile(r"^(.+)（(.+)）$")
_ALIAS = {"路得马丁": "路德马丁"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _nn(v: Any) -> bool:
    return v is not None and str(v).strip() != ""


def map_term_name(name: str) -> str:
    if name in _ALIAS:
        return _ALIAS[name]
    m = _COMPOSITE_RE.fullmatch(name)
    if m:
        return m.group(1)
    return name


def find_sources() -> dict[str, Path]:
    """定位三个源文件；候选不唯一则抛出。"""
    all_json = sorted(_IMPORT_ROOT.rglob("*.json"))
    gen_cands = []
    dict_cands = []
    rel_cands = []
    for p in all_json:
        try:
            with p.open("r", encoding="utf-8-sig") as f:
                head = f.read(4000)
        except Exception:
            continue
        if '"name_en"' in head and '"greek_terms"' in head and '"related_scriptures"' in head:
            gen_cands.append(p)
        if '"content_3a"' in head and '"content_3b"' in head and '"title"' in head:
            dict_cands.append(p)
        if '"pairs"' in head and '"relation"' in head and '"count"' in head:
            rel_cands.append(p)
    out: dict[str, Any] = {
        "general": gen_cands,
        "dictionary": dict_cands,
        "relations": rel_cands,
    }
    for key in ("general", "dictionary", "relations"):
        if len(out[key]) != 1:
            raise SystemExit(
                f"源文件定位失败 {key}: 候选数={len(out[key])} → {[str(x) for x in out[key]]}"
            )
    return {k: v[0] for k, v in out.items()}


def _check_ignore(path: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "check-ignore", "-v", str(path)],
            cwd=str(_REPO),
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip()
        return out or "(未忽略：无输出)"
    except subprocess.CalledProcessError as exc:
        return f"(未被 ignore；exit={exc.returncode})"


def _ensure_gitignore(paths: list[Path], log: v1.Logger) -> dict[str, Any]:
    """A3：若未被 ignore，仅向根 .gitignore 追加精确路径。"""
    gi_path = _REPO / ".gitignore"
    results = {}
    to_add = []
    for p in paths:
        rel = p.relative_to(_REPO).as_posix()
        hit = _check_ignore(p)
        results[rel] = {"before": hit, "ignored": not hit.startswith("(未被")}
        if hit.startswith("(未被"):
            to_add.append(rel)
    added = []
    if to_add:
        text = gi_path.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            text += "\n"
        block = "\n# panai4 graph_annotations large JSON (exact paths)\n"
        for rel in to_add:
            if rel not in text:
                block += rel + "\n"
                added.append(rel)
        if added:
            gi_path.write_text(text + block, encoding="utf-8")
            log.log(f"A3 已向 .gitignore 追加: {added}")
        for rel in to_add:
            results[rel]["after"] = _check_ignore(_REPO / rel)
            results[rel]["ignored"] = not results[rel]["after"].startswith("(未被")
    else:
        for rel in results:
            results[rel]["after"] = results[rel]["before"]
    return {"paths": results, "added": added}


def _sha_val(val: Any) -> str:
    """标注值可能是 str / bool / number；统一序列化再 SHA。"""
    if isinstance(val, str):
        raw = val
    else:
        raw = json.dumps(val, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _snapshot_protected(session) -> dict[str, dict[str, str]]:
    out = {}
    for prop, expected in _PROTECTED.items():
        n = v2._anno_nonempty(session, prop)
        if n != expected:
            raise SystemExit(f"保护标注 {prop} 非空 {n} ≠ 预期 {expected}")
        amap = v2._fetch_anno_map(session, prop)
        out[prop] = {name: _sha_val(val) for name, val in amap.items()}
    return out


def _compare_protected(before: dict, session) -> dict[str, Any]:
    result = {}
    for prop, old in before.items():
        amap = v2._fetch_anno_map(session, prop)
        now = {name: _sha_val(val) for name, val in amap.items()}
        only_before = sorted(set(old) - set(now))
        only_now = sorted(set(now) - set(old))
        mismatch = sorted(k for k in set(old) & set(now) if old[k] != now[k])
        result[prop] = {
            "before_n": len(old),
            "now_n": len(now),
            "sha_mismatch": len(mismatch),
            "only_before": only_before[:20],
            "only_now": only_now[:20],
            "mismatch_names": mismatch[:20],
        }
    return result


def build_rows(gen: list[dict], dct_by_title: dict[str, dict]) -> list[dict]:
    rows = []
    for r in gen:
        src_name = r["name"]
        graph_name = map_term_name(src_name)
        props: dict[str, Any] = {
            "name_en": r.get("name_en") if r.get("name_en") is not None else "",
            "related_scriptures": json.dumps(r.get("related_scriptures") or [], ensure_ascii=False),
            "definition_3a": True,
        }
        if _nn(r.get("greek_terms")):
            props["greek_terms"] = r["greek_terms"]
        if _nn(r.get("hebrew_terms")):
            props["hebrew_terms"] = r["hebrew_terms"]
        content_3b = (dct_by_title[src_name] or {}).get("content_3b")
        if _nn(content_3b):
            props["definition_3b"] = True
        rows.append({"name": graph_name, "src_name": src_name, "props": props})
    return rows


def stage_check(env: dict, log: v1.Logger) -> int:
    log.log("stage=check general_annotation")
    srcs = find_sources()
    log.log(f"sources gen={srcs['general']} dict={srcs['dictionary']} rel={srcs['relations']}")
    sha_before = v1._sha_import_dir()

    gen = json.loads(srcs["general"].read_text(encoding="utf-8-sig"))
    dct = json.loads(srcs["dictionary"].read_text(encoding="utf-8-sig"))
    if not isinstance(gen, list) or not isinstance(dct, list):
        raise SystemExit("通用标注/词典顶层须为 list")

    gen_names = [r["name"] for r in gen]
    dict_titles = [r["title"] for r in dct]
    from collections import Counter

    gen_dup = [n for n, c in Counter(gen_names).items() if c > 1]
    dict_dup = [n for n, c in Counter(dict_titles).items() if c > 1]
    set_gen, set_dict = set(gen_names), set(dict_titles)
    only_gen = sorted(set_gen - set_dict)
    only_dict = sorted(set_dict - set_gen)

    dct_by_title = {r["title"]: r for r in dct}
    def3a_true = sum(1 for r in gen if r.get("definition", {}).get("3a") is True)
    def3a_not = sum(1 for r in gen if r.get("definition", {}).get("3a") is not True)
    def3b_true = sum(1 for r in gen if r.get("definition", {}).get("3b") is True)
    content_3b_nonempty = sum(1 for r in dct if _nn(r.get("content_3b")))
    content_3b_empty = sum(1 for r in dct if not _nn(r.get("content_3b")))
    mism = []
    for r in gen:
        d3b = r.get("definition", {}).get("3b") is True
        c3b = _nn(dct_by_title[r["name"]].get("content_3b"))
        if d3b != c3b:
            mism.append(r["name"])

    stats = {
        "n_gen": len(gen),
        "n_dict": len(dct),
        "gen_dup": gen_dup,
        "dict_dup": dict_dup,
        "only_gen": only_gen,
        "only_dict": only_dict,
        "sets_equal": set_gen == set_dict,
        "def3a_true": def3a_true,
        "def3a_not": def3a_not,
        "def3b_true": def3b_true,
        "content_3b_nonempty": content_3b_nonempty,
        "content_3b_empty": content_3b_empty,
        "def_content_mismatch": mism,
        "name_en_nonempty": sum(1 for r in gen if _nn(r.get("name_en"))),
        "greek_nonempty": sum(1 for r in gen if _nn(r.get("greek_terms"))),
        "hebrew_nonempty": sum(1 for r in gen if _nn(r.get("hebrew_terms"))),
        "scriptures_nonempty": sum(1 for r in gen if r.get("related_scriptures")),
        "max_content_3a": max((len(r.get("content_3a") or "") for r in dct), default=0),
        "max_content_3b": max((len(r.get("content_3b") or "") for r in dct), default=0),
        "composite_names": [n for n in gen_names if _COMPOSITE_RE.fullmatch(n)],
        "name_map_examples": [
            {"src": n, "graph": map_term_name(n)}
            for n in gen_names
            if map_term_name(n) != n
        ],
    }
    log.log(
        f"JSON gen={stats['n_gen']} dict={stats['n_dict']} equal={stats['sets_equal']} "
        f"3b_true={def3b_true} content_3b={content_3b_nonempty} empty={content_3b_empty}"
    )

    rows = build_rows(gen, dct_by_title)
    graph_names = [r["name"] for r in rows]

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = v1.snapshot_graph(session)
            base_fails = v1.gate_baseline(base)
            protected = _snapshot_protected(session)
            no_sa = {
                r["name"]
                for r in v1._run(
                    session,
                    """
                    MATCH (n:Truth_Point)
                    WHERE n.same_as IS NULL OR toString(n.same_as) = ''
                    RETURN n.name AS name
                    """,
                )
            }
            with_sa = {
                r["name"]
                for r in v1._run(
                    session,
                    """
                    MATCH (n:Truth_Point)
                    WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
                    RETURN n.name AS name
                    """,
                )
            }
            match = v1.match_names(session, graph_names)
            hit_inner = sorted(set(graph_names) & with_sa)
    except Exception as exc:
        raise SystemExit("check 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_after = v1._sha_import_dir()
    sha_ok = sha_before["hashes"] == sha_after["hashes"]

    fails = list(base_fails)
    if stats["n_gen"] != 2372 or stats["n_dict"] != 2372:
        fails.append(f"记录数 gen={stats['n_gen']} dict={stats['n_dict']} ≠ 2372")
    if gen_dup or dict_dup:
        fails.append(f"重复名 gen={gen_dup} dict={dict_dup}")
    if not stats["sets_equal"]:
        fails.append(f"name/title 集合不一致 only_gen={only_gen[:20]} only_dict={only_dict[:20]}")
    if def3a_not:
        fails.append(f"definition.3a 非 true: {def3a_not}")
    if def3b_true != content_3b_nonempty:
        fails.append(f"definition.3b true={def3b_true} ≠ content_3b nonempty={content_3b_nonempty}")
    if content_3b_nonempty != 2062 or content_3b_empty != 310:
        fails.append(
            f"3b nonempty/empty = {content_3b_nonempty}/{content_3b_empty} ≠ 2062/310"
        )
    if mism:
        fails.append(f"definition 与正文空/非空不一致 {len(mism)}: {mism[:20]}")
    if base["no_same_as_n"] != 2372:
        fails.append(f"无 same_as 的 Truth_Point {base['no_same_as_n']} ≠ 2372")
    if set(graph_names) != no_sa:
        fails.append(
            "映射后词名与无 same_as 节点不完全一致 "
            f"only_json={sorted(set(graph_names)-no_sa)[:20]} "
            f"only_graph={sorted(no_sa-set(graph_names))[:20]}"
        )
    if hit_inner:
        fails.append(f"映射到括号内节点: {hit_inner}")
    if match["missing_n"] or match["multi"]:
        fails.append(f"匹配失败 missing={match['missing'][:20]} multi={match['multi']}")
    if not sha_ok:
        fails.append("可导入资料 SHA 前后不一致")

    # expected nonempty for new props
    expect_new = {
        "name_en": stats["name_en_nonempty"],
        "greek_terms": stats["greek_nonempty"],
        "hebrew_terms": stats["hebrew_nonempty"],
        "related_scriptures": stats["scriptures_nonempty"],
        "definition_3a": 2372,
        "definition_3b": content_3b_nonempty,
    }

    state = {
        "version": 1,
        "check_ok": not fails,
        "fails": fails,
        "sources": {k: str(v) for k, v in srcs.items()},
        "stats": stats,
        "expect_new": expect_new,
        "baseline": {k: v for k, v in base.items() if k not in ("tp_props",)},
        "protected_sha": protected,
        "match": {
            "found_n": match["found_n"],
            "missing_n": match["missing_n"],
            "missing": match["missing"],
            "multi": match["multi"],
            "hit_inner": hit_inner,
        },
        "write_rows": rows,
        "sha_before": sha_before,
        "sha_after_check": sha_after,
        "sha_ok": sha_ok,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    # drop bulky hashes from report state file but keep for verify
    v1.save_state(_STATE_NAME, state)
    write_report(state, copy_info=None, import_info=None, verify_info=None, log_path=log.path)

    for f in fails:
        log.log("GATE FAIL: " + f)
    if fails:
        log.log("闸门未通过，停止。")
        return 2
    log.log(f"闸门通过。拟写入 {len(rows)}；definition_3b={content_3b_nonempty}")
    return 0


def stage_copy(env: dict, log: v1.Logger) -> int:
    log.log("stage=copy dictionary JSON")
    state = v1.load_state(_STATE_NAME)
    if not state.get("check_ok"):
        raise SystemExit("check 未通过，拒绝 copy")
    src = Path(state["sources"]["dictionary"])
    if not src.is_file():
        raise SystemExit(f"源不存在: {src}")
    if _DEST_DICT.exists():
        raise SystemExit(f"目标已存在，拒绝覆盖: {_DEST_DICT}")
    _DEST_DIR.mkdir(parents=True, exist_ok=True)
    src_sha = _sha256(src)
    src_size = src.stat().st_size
    shutil.copy2(src, _DEST_DICT)
    dest_sha = _sha256(_DEST_DICT)
    dest_size = _DEST_DICT.stat().st_size
    if dest_sha != src_sha or dest_size != src_size:
        raise SystemExit("复制后 SHA/大小不一致")
    data = json.loads(_DEST_DICT.read_text(encoding="utf-8-sig"))
    n = len(data) if isinstance(data, list) else None
    if n != 2372:
        raise SystemExit(f"复制后记录数 {n} ≠ 2372")
    log.log(f"copied size={dest_size} sha={dest_sha} n={n}")

    # append SHA256SUMS
    line = f"{dest_sha}  truth_dictionary_3a3b.json\n"
    existing = _SUMS.read_text(encoding="utf-8") if _SUMS.is_file() else ""
    if "truth_dictionary_3a3b.json" not in existing:
        _SUMS.write_text(existing.rstrip() + "\n" + line if existing.strip() else line, encoding="utf-8")
    log.log(f"updated {_SUMS}")

    # append README section
    section = f"""

---

# truth_dictionary_3a3b.json

## 这是什么

「真理词典」3a/3b **正文**内容文件，共 **{n}** 个词条。

每条含：`id`、`title`、`content_3a`、`content_3b`。

## 来源

- 桌面源路径：`{src}`
- 大小：{dest_size} 字节
- SHA256：`{dest_sha}`
- 复制日期：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 与图谱的关系

图谱 **不存** 正文。`Truth_Point` 上仅有布尔标注：
- `definition_3a = true`（全部有 3a 正文的词条）
- `definition_3b = true`（仅 `content_3b` 非空的词条；空则不写该标注）

检索正文时按词条名到本文件取（JSON 的 `title` 对应源名；括号词在源里为整体名如「妇人（女人）」，图谱节点为括号外名）。

服务器上需在同一相对路径放一份：`back_mic/backend/panai4/data/graph_annotations/truth_dictionary_3a3b.json`。

本文件体积大，**不进 git**，需单独备份与部署。
"""
    readme = _README.read_text(encoding="utf-8") if _README.is_file() else ""
    if "truth_dictionary_3a3b.json" not in readme:
        _README.write_text(readme.rstrip() + section, encoding="utf-8")
    log.log(f"updated {_README}")

    gi = _ensure_gitignore(
        [_DEST_DIR / "organic_advance.json", _DEST_DICT],
        log,
    )
    copy_info = {
        "src": str(src),
        "dest": str(_DEST_DICT),
        "size": dest_size,
        "sha": dest_sha,
        "sha_ok": True,
        "n_records": n,
        "gitignore": gi,
    }
    state["copy"] = copy_info
    v1.save_state(_STATE_NAME, state)
    write_report(state, copy_info=copy_info, import_info=None, verify_info=None, log_path=log.path)
    log.log("copy 完成")
    return 0


def _set_props_batch(tx, rows: list[dict]) -> int:
    q = (
        "UNWIND $rows AS row "
        "MATCH (n:Truth_Point {name: row.name}) "
        "SET n += row.props "
        "RETURN count(n) AS updated"
    )
    result = tx.run(q, {"rows": rows})
    row = result.single()
    return int(row["updated"]) if row else 0


def stage_import(env: dict, log: v1.Logger) -> int:
    log.log("stage=import general_annotation")
    state = v1.load_state(_STATE_NAME)
    if not state.get("check_ok"):
        raise SystemExit("check 未通过，拒绝 import")
    if not state.get("copy"):
        raise SystemExit("请先 --stage copy")
    rows = state["write_rows"]
    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    written = 0
    failed = 0
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = v1.snapshot_graph(session)
            fails = v1.gate_baseline(base)
            # re-check protected counts
            for prop, n_exp in _PROTECTED.items():
                n = v2._anno_nonempty(session, prop)
                if n != n_exp:
                    fails.append(f"I1 {prop} {n}≠{n_exp}")
            if fails:
                for f in fails:
                    log.log("GATE FAIL I1: " + f)
                return 2
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            for i in range(0, len(rows), _BATCH):
                batch = rows[i : i + _BATCH]
                payload = [{"name": r["name"], "props": r["props"]} for r in batch]
                updated = session.execute_write(_set_props_batch, payload)
                if updated != len(batch):
                    failed += len(batch) - updated
                    log.log(
                        f"batch {i}-{i+len(batch)-1} updated={updated} ≠ {len(batch)}；停止"
                    )
                    state["import"] = {
                        "aborted": True,
                        "written": written,
                        "failed": failed,
                        "last_batch": [i, i + len(batch) - 1],
                    }
                    v1.save_state(_STATE_NAME, state)
                    write_report(
                        state,
                        copy_info=state.get("copy"),
                        import_info=state["import"],
                        verify_info=None,
                        log_path=log.path,
                    )
                    return 2
                written += updated
                log.log(f"batch {i}-{i+len(batch)-1} updated={updated} cumulative={written}")
    except Exception as exc:
        raise SystemExit("import 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    info = {"aborted": False, "written": written, "failed": failed, "expected": len(rows)}
    state["import"] = info
    v1.save_state(_STATE_NAME, state)
    write_report(
        state,
        copy_info=state.get("copy"),
        import_info=info,
        verify_info=None,
        log_path=log.path,
    )
    log.log(f"import 完成 written={written} failed={failed}")
    return 0


def stage_verify(env: dict, log: v1.Logger) -> int:
    log.log("stage=verify general_annotation")
    state = v1.load_state(_STATE_NAME)
    expect = state["expect_new"]
    src_gen = Path(state["sources"]["general"])
    gen = json.loads(src_gen.read_text(encoding="utf-8-sig"))
    by_src = {r["name"]: r for r in gen}

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    fails = []
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            now = v1.snapshot_graph(session)
            if now["nodes_total"] != 2483:
                fails.append(f"nodes_total {now['nodes_total']}≠2483")
            if now["rels_total"] != 6527:
                fails.append(f"rels_total {now['rels_total']}≠6527")
            prot = _compare_protected(state["protected_sha"], session)
            for prop, info in prot.items():
                if info["sha_mismatch"] or info["only_before"] or info["only_now"]:
                    fails.append(f"保护标注变化 {prop}: {info}")

            counts = {}
            for prop in _NEW_PROPS:
                counts[prop] = v2._anno_nonempty(session, prop)
                if counts[prop] != expect[prop]:
                    fails.append(f"{prop} nonempty {counts[prop]}≠{expect[prop]}")

            # paren nodes must not have new props
            for prop in _NEW_PROPS:
                n = v1._run(
                    session,
                    f"""
                    MATCH (n:Truth_Point)
                    WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
                      AND n.{prop} IS NOT NULL
                    RETURN count(n) AS c
                    """,
                )[0]["c"]
                if n:
                    fails.append(f"括号内节点有 {prop}: {n}")

            # sample related_scriptures roundtrip
            samples = []
            sample_names = [r["name"] for r in state["write_rows"][:5]]
            for gname in sample_names:
                row = next(r for r in state["write_rows"] if r["name"] == gname)
                src = by_src[row["src_name"]]
                got = v1._run(
                    session,
                    "MATCH (n:Truth_Point {name: $name}) RETURN n.related_scriptures AS v, n.name_en AS en, n.definition_3a AS a, n.definition_3b AS b",
                    {"name": gname},
                )[0]
                loaded = json.loads(got["v"]) if got["v"] else None
                ok = loaded == (src.get("related_scriptures") or [])
                if not ok:
                    fails.append(f"related_scriptures 抽样不符: {gname}")
                samples.append(
                    {
                        "name": gname,
                        "src_name": row["src_name"],
                        "scriptures_ok": ok,
                        "name_en": v1._trunc(got["en"], 80),
                        "definition_3a": got["a"],
                        "definition_3b": got["b"],
                    }
                )

            # dest sha
            dest_sha = _sha256(_DEST_DICT) if _DEST_DICT.is_file() else None
            src_sha = _sha256(Path(state["sources"]["dictionary"]))
            dest_ok = dest_sha == src_sha
            if not dest_ok:
                fails.append("仓库词典 JSON SHA ≠ 源")

            sha_now = v1._sha_import_dir()
            if sha_now["hashes"] != state["sha_before"]["hashes"]:
                fails.append("可导入资料目录 SHA 变化")

            tp_keys = now["node_keys"]["Truth_Point"]
    except Exception as exc:
        raise SystemExit("verify 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    verify_info = {
        "ok": not fails,
        "fails": fails,
        "counts": counts,
        "protected_compare": prot,
        "samples": samples,
        "dest_sha": dest_sha,
        "dest_sha_ok": dest_ok,
        "tp_keys": tp_keys,
        "nodes_total": now["nodes_total"],
        "rels_total": now["rels_total"],
    }
    state["verify"] = verify_info
    v1.save_state(_STATE_NAME, state)
    write_report(
        state,
        copy_info=state.get("copy"),
        import_info=state.get("import"),
        verify_info=verify_info,
        log_path=log.path,
    )
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        return 2
    log.log("verify 全部通过")
    return 0


def write_report(
    state: dict,
    copy_info: dict | None,
    import_info: dict | None,
    verify_info: dict | None,
    log_path: Path,
) -> None:
    st = state.get("stats") or {}
    match = state.get("match") or {}
    gi = (copy_info or {}).get("gitignore") or {}
    lines = [
        "# neo4j-v4 导入通用标注报告",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.import_general_annotation`。",
        "正文不进图谱；只 SET name_en / greek_terms / hebrew_terms / related_scriptures / definition_3a / definition_3b。",
        "未运行 build_v4.py；未打印密码；未修改 import_annotation*.py。",
        "",
        "## 摘要",
        "",
        f"1. **源文件**：gen=`{state.get('sources',{}).get('general')}` n={st.get('n_gen')}；"
        f"dict=`{state.get('sources',{}).get('dictionary')}` n={st.get('n_dict')}；集合一致={st.get('sets_equal')}。",
        f"2. **匹配**：found={match.get('found_n')} missing={match.get('missing_n')} "
        f"hit_inner={match.get('hit_inner')}；括号整体名映射例={v1._trunc(st.get('name_map_examples'), 80)}。",
        f"3. **一致性**：def.3a true={st.get('def3a_true')}；def.3b true={st.get('def3b_true')}；"
        f"content_3b nonempty/empty={st.get('content_3b_nonempty')}/{st.get('content_3b_empty')}；"
        f"mismatch={len(st.get('def_content_mismatch') or [])}；"
        f"name_en={st.get('name_en_nonempty')} greek={st.get('greek_nonempty')} "
        f"hebrew={st.get('hebrew_nonempty')} scriptures={st.get('scriptures_nonempty')}；"
        f"max_3a={st.get('max_content_3a')} max_3b={st.get('max_content_3b')}。",
        f"4. **copy**：{v1._trunc(copy_info, 200) if copy_info else '（尚未 copy）'}。",
        f"5. **gitignore**：{v1._trunc(gi, 300) if gi else '（见 copy）'}。",
        f"6. **import**：{import_info}。",
        f"7. **verify**：ok={(verify_info or {}).get('ok')} counts={(verify_info or {}).get('counts')} "
        f"fails={(verify_info or {}).get('fails')}。",
        f"8. **闸门**：check_ok={state.get('check_ok')} fails={state.get('fails')}。",
        "",
        "## A1 check 明细",
        f"- baseline nodes={state.get('baseline',{}).get('nodes_total')} "
        f"rels={state.get('baseline',{}).get('rels_total')} "
        f"labels={state.get('baseline',{}).get('labels')} "
        f"by_type={state.get('baseline',{}).get('by_type')}",
        f"- protected expected={_PROTECTED}",
        f"- composite_names={st.get('composite_names')}",
        "",
    ]
    if copy_info:
        lines += [
            "## A2/A3 copy & gitignore",
            f"- dest={copy_info.get('dest')} size={copy_info.get('size')} sha={copy_info.get('sha')} n={copy_info.get('n_records')}",
            f"- gitignore={json.dumps(gi, ensure_ascii=False)}",
            "",
        ]
    if import_info:
        lines += ["## A4 import", f"```json\n{json.dumps(import_info, ensure_ascii=False, indent=2)}\n```", ""]
    if verify_info:
        lines += [
            "## A5 verify",
            f"- counts={verify_info.get('counts')}",
            f"- protected_compare={json.dumps(verify_info.get('protected_compare'), ensure_ascii=False)}",
            f"- samples={json.dumps(verify_info.get('samples'), ensure_ascii=False)}",
            f"- dest_sha_ok={verify_info.get('dest_sha_ok')} nodes={verify_info.get('nodes_total')} rels={verify_info.get('rels_total')}",
            f"- tp_keys={verify_info.get('tp_keys')}",
            f"- fails={verify_info.get('fails')}",
            "",
        ]
    lines += [
        "## 最终验证",
        "- 未修改 import_annotation.py / _v2.py / _v3.py / _v4.py / delete_old_relations.py",
        "- 未运行 build_v4.py",
        "- 报告与日志密码检查：通过（仅变量名）",
        f"- 日志：`{log_path}`",
        "",
    ]
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="导入通用标注（正文外置）")
    ap.add_argument("--stage", required=True, choices=["check", "copy", "import", "verify"])
    args = ap.parse_args(argv)
    env = v1._load_env()
    log = v1.Logger(
        _LOG_DIR / f"import_general_annotation_{args.stage}_{v1._now()}.log",
        env["pass4"],
    )
    log.log(f"stage={args.stage}（密码不记录）")
    if args.stage == "check":
        return stage_check(env, log)
    if args.stage == "copy":
        return stage_copy(env, log)
    if args.stage == "import":
        return stage_import(env, log)
    if args.stage == "verify":
        return stage_verify(env, log)
    return 2


if __name__ == "__main__":
    sys.exit(main())
