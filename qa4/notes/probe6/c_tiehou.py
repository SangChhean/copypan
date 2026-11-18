# -*- coding: utf-8 -*-
"""Probe6-C: 图谱经节「贴后」排查（只读）。"""
from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(r"G:\copypan")
OUT = REPO / "qa4" / "notes" / "probe6" / "c_result.json"
V21 = Path(r"C:\Users\28121\Desktop\get_vers_v2.1.py")
SCRIPTURE_STATE = REPO / "logs" / "import_annotation_scripture_nodes_state.json"
NODE_ANN = Path(r"C:\Users\28121\Desktop\可导入资料\1 一般标注\节点一般标注.json")
TD = REPO / "qa4" / "data" / "graph_annotations" / "truth_dictionary_3a3b.json"
BIBLE_DATA = REPO / "back_qa" / "bible_data"
TRUNK = REPO / "docs" / "panai4_graph" / "主恢复真理词典_词条主干枝子映射 (1).json"
BIBLE_CHUNKS = Path(r"G:\PanAI4.0专用\索引数据\panai4_bible\02_清洗JSON\chunks_bible.json")
MAP_NOTE = Path(r"G:\PanAI4.0专用\12490原文JSONL\kg-rag_map_note.jsonl")
PARSER = REPO / "back_qa" / "qa" / "bible_ref_parser.py"
DOCS = REPO / "docs"


def load_v21():
    spec = importlib.util.spec_from_file_location("get_vers_v21_p6c", V21)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def parse_ok(mod, text: str, validate=None) -> bool:
    p = mod.VerseParser(validate=validate)
    p.start_paragraph()
    groups = p.parse_text(text)
    toks = []
    for g in groups:
        for part in (g.get("verses") or "").split("，"):
            if part.strip():
                toks.append(part.strip())
    return bool(toks)


def fix_tiehou(ref: str) -> str:
    """贴后 → 帖后（仅替换书名简写，保守：整词前缀）。"""
    # 常见：贴后一1 / 贴后三16
    return ref.replace("贴后", "帖后")


def count_in_text_file(path: Path, term: str) -> dict:
    if not path.is_file():
        return {"path": str(path), "exists": False, "n": 0}
    text = path.read_text(encoding="utf-8", errors="replace")
    n = text.count(term)
    lines = []
    for i, line in enumerate(text.splitlines(), 1):
        if term in line:
            lines.append(i)
            if len(lines) >= 20:
                break
    return {"path": str(path), "exists": True, "n": n, "line_samples": lines[:10]}


def count_in_json_fields(path: Path, term: str, fields: tuple[str, ...]) -> dict:
    if not path.is_file():
        return {"path": str(path), "exists": False, "n": 0}
    # stream for large files
    n = 0
    hits = []
    # detect jsonl vs json array
    raw0 = path.read_text(encoding="utf-8", errors="replace")
    # For huge files this is memory heavy; bible_data is many files
    if path.suffix == ".jsonl" or "jsonl" in path.name:
        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if term in line:
                    n += line.count(term)
                    if len(hits) < 5:
                        hits.append({"line": lineno, "snip": line.strip()[:30]})
        return {"path": str(path), "exists": True, "n": n, "hits": hits, "mode": "jsonl_raw"}

    # try parse
    try:
        data = json.loads(raw0)
    except Exception:
        n = raw0.count(term)
        return {"path": str(path), "exists": True, "n": n, "mode": "raw_fallback"}

    def walk(o, path_s=""):
        nonlocal n
        if isinstance(o, dict):
            for k, v in o.items():
                if k in fields and isinstance(v, str) and term in v:
                    c = v.count(term)
                    n += c
                    if len(hits) < 8:
                        hits.append({"field": f"{path_s}.{k}", "snip": v[:30]})
                else:
                    walk(v, f"{path_s}.{k}")
        elif isinstance(o, list):
            for i, it in enumerate(o):
                walk(it, f"{path_s}[{i}]")
        elif isinstance(o, str) and term in o:
            # only count if parent field already handled; skip free strings unless fields empty
            pass

    walk(data)
    # also whole-file count for visibility
    whole = raw0.count(term)
    return {
        "path": str(path),
        "exists": True,
        "n_in_fields": n,
        "n_whole_file": whole,
        "hits": hits,
        "fields": list(fields),
    }


def extract_book_map_aliases(mod) -> dict:
    bm = getattr(mod, "BOOK_MAP", {})
    thess = {"帖前": [], "帖后": [], "贴前": [], "贴后": []}
    for k, v in bm.items():
        if v in ("帖前", "帖后"):
            thess.setdefault(v, []).append(k)
        if "贴" in k or "帖" in k:
            if "前" in k or v == "帖前":
                thess.setdefault("keys_with_贴或帖_前", []).append(f"{k}->{v}")
            if "后" in k or v == "帖后":
                thess.setdefault("keys_with_贴或帖_后", []).append(f"{k}->{v}")
    # cleaner
    out = {
        "帖前_keys": sorted([k for k, v in bm.items() if v == "帖前"]),
        "帖后_keys": sorted([k for k, v in bm.items() if v == "帖后"]),
        "keys_containing_贴": sorted([k for k in bm if "贴" in k]),
        "keys_containing_帖": sorted([k for k in bm if "帖" in k]),
    }
    return out


def extract_parser30_aliases() -> dict:
    """从 bible_ref_parser.py 与 bible_data 名表相关代码静态提取含 贴/帖 的写法。"""
    text = PARSER.read_text(encoding="utf-8")
    # COMMON_ALIASES and comments
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if "贴" in line or "帖" in line:
            hits.append({"line": i, "snip": line.strip()[:80]})
    # Also load bible_data abbrs for 帖前/帖后 books 52/53
    from pathlib import Path as P
    import json as J

    aliases = {"from_parser_source_lines": hits, "from_bible_data": {}}
    # book numbers: 帖前=52 帖后=53 typically
    for p in sorted(BIBLE_DATA.glob("*.json")):
        if p.name.lower() == "index.json":
            continue
        try:
            d = J.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        book = d.get("book")
        name = d.get("name_gb") or ""
        if "帖撒罗尼迦" in name or "贴撒罗尼迦" in name:
            fields = {}
            for f in ("name_gb", "name_big5", "abbr_gb", "abbr_big5", "name_en", "abbr_en"):
                fields[f] = d.get(f)
            aliases["from_bible_data"][str(book)] = fields
    return aliases


def find_term_in_docs(term: str) -> list[dict]:
    hits = []
    for p in DOCS.rglob("*.md"):
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            if term in line:
                hits.append({"path": str(p), "line": i, "snip": line.strip()[:30]})
                if len(hits) >= 30:
                    return hits
    return hits


def main():
    result = {"script": "qa4/notes/probe6/c_tiehou.py"}
    mod = load_v21()
    st = json.loads(SCRIPTURE_STATE.read_text(encoding="utf-8"))
    chosen = st.get("chosen") or {}
    refs = list(chosen.keys())

    # C1: find 6 failures
    fails = [r for r in refs if not parse_ok(mod, r)]
    result["c1_fail_n"] = len(fails)
    result["c1_fails"] = fails

    # locate term-scripture links in state
    # possible keys: term_refs, scripture_rows, link_rows, match
    term_refs = st.get("term_refs") or {}
    scripture_rows = st.get("scripture_rows") or []
    link_rows = st.get("link_rows") or []

    # map ref -> terms
    ref_to_terms = {}
    # term_refs: term -> list of refs?
    if isinstance(term_refs, dict):
        for term, v in term_refs.items():
            if isinstance(v, list):
                for ref in v:
                    if isinstance(ref, str):
                        ref_to_terms.setdefault(ref, []).append(term)
                    elif isinstance(ref, dict):
                        rr = ref.get("ref") or ref.get("name") or ref.get("scripture")
                        if rr:
                            ref_to_terms.setdefault(rr, []).append(term)
            elif isinstance(v, dict):
                # maybe {ref: ...}
                for rr in v.keys():
                    ref_to_terms.setdefault(rr, []).append(term)

    # scripture_rows may have name/ref and terms
    row_by_ref = {}
    if isinstance(scripture_rows, list):
        for row in scripture_rows:
            if not isinstance(row, dict):
                continue
            rr = row.get("ref") or row.get("name") or row.get("scripture")
            if rr:
                row_by_ref[rr] = row

    # link_rows: {name: Truth_Point名, ref: 经节}
    if isinstance(link_rows, list):
        for row in link_rows:
            if not isinstance(row, dict):
                continue
            rr = row.get("ref") or row.get("scripture") or row.get("to")
            term = row.get("name") or row.get("term") or row.get("from") or row.get("truth")
            if rr and term and rr != term:
                ref_to_terms.setdefault(rr, []).append(term)
    # term_refs: {term: [ref, ...]}
    if isinstance(term_refs, dict):
        for term, v in term_refs.items():
            if isinstance(v, list):
                for ref in v:
                    if isinstance(ref, str):
                        ref_to_terms.setdefault(ref, []).append(term)

    fail_details = []
    for ref in fails:
        terms = sorted(set(ref_to_terms.get(ref) or []))
        row = row_by_ref.get(ref)
        extra = None
        if row:
            # pick small safe fields
            extra = {
                k: row.get(k)
                for k in list(row.keys())[:12]
                if k not in ("text", "content", "value") and not isinstance(row.get(k), (list, dict))
            }
        fail_details.append(
            {
                "ref": ref,
                "terms": terms if terms else "未找到",
                "row_meta": extra,
            }
        )
    result["c1_fail_details"] = fail_details

    # C2: after 贴后→帖后, exists in chosen?
    c2 = []
    for ref in fails:
        fixed = fix_tiehou(ref)
        c2.append(
            {
                "ref": ref,
                "fixed": fixed,
                "changed": fixed != ref,
                "fixed_already_in_chosen": fixed in chosen,
                "fixed_parses": parse_ok(mod, fixed) if fixed != ref else None,
            }
        )
    result["c2_fix_collision"] = c2

    # C3: where 贴后 appears
    locations = []
    # 节点一般标注
    locations.append(
        {
            "label": "节点一般标注.json",
            **count_in_json_fields(NODE_ANN, "贴后", ("name", "scripture", "ref", "text", "content")),
        }
    )
    # also raw count
    if NODE_ANN.is_file():
        raw = NODE_ANN.read_text(encoding="utf-8", errors="replace")
        locations[-1]["n_whole_file"] = raw.count("贴后")
        # find field context via regex
        field_hits = []
        for m in re.finditer(r"贴后[^\"']{0,20}", raw):
            # look back for key
            start = max(0, m.start() - 40)
            field_hits.append(raw[start : m.end()][:50])
            if len(field_hits) >= 5:
                break
        locations[-1]["context_samples"] = field_hits

    locations.append(
        {
            "label": "truth_dictionary_3a3b.json",
            **count_in_json_fields(TD, "贴后", ("title", "content_3a", "content_3b")),
        }
    )

    # bible_data: scan all json for 贴后
    bd_n = 0
    bd_files = []
    for p in sorted(BIBLE_DATA.glob("*.json")):
        t = p.read_text(encoding="utf-8", errors="replace")
        c = t.count("贴后")
        if c:
            bd_n += c
            bd_files.append({"file": p.name, "n": c})
    locations.append({"label": "back_qa/bible_data", "n": bd_n, "files": bd_files})

    locations.append(
        {
            "label": "主干枝映射",
            **count_in_json_fields(TRUNK, "贴后", ("name", "trunk", "branch_directly", "branch_indirectly")),
        }
    )

    # qa4_bible chunks
    b_n = 0
    b_hits = []
    if BIBLE_CHUNKS.is_file():
        with BIBLE_CHUNKS.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if "贴后" in line:
                    c = line.count("贴后")
                    b_n += c
                    if len(b_hits) < 5:
                        b_hits.append({"line": lineno, "snip": line.strip()[:30]})
    locations.append({"label": "qa4_bible chunks_bible.json", "path": str(BIBLE_CHUNKS), "n": b_n, "hits": b_hits})

    # map_note
    m_n = 0
    m_hits = []
    if MAP_NOTE.is_file():
        with MAP_NOTE.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if "贴后" in line:
                    m_n += line.count("贴后")
                    if len(m_hits) < 5:
                        m_hits.append({"line": lineno, "snip": line.strip()[:30]})
    locations.append({"label": "map_note jsonl", "path": str(MAP_NOTE), "n": m_n, "hits": m_hits})

    # docs import reports
    doc_hits = find_term_in_docs("贴后")
    locations.append({"label": "docs/**/*.md", "n": len(doc_hits), "hits": doc_hits[:15]})

    # also search scripture state itself
    st_text = SCRIPTURE_STATE.read_text(encoding="utf-8", errors="replace")
    locations.append(
        {
            "label": "import_annotation_scripture_nodes_state.json",
            "n": st_text.count("贴后"),
            "path": str(SCRIPTURE_STATE),
        }
    )

    result["c3_locations"] = locations

    # C4 aliases
    result["c4_v21_book_map"] = extract_book_map_aliases(mod)
    result["c4_parser30"] = extract_parser30_aliases()

    # C5 change list (report only)
    change_list = []
    for d in fail_details:
        ref = d["ref"]
        fixed = fix_tiehou(ref)
        change_list.append(
            {
                "node_hint": "Scripture 节点（以 ref/name=该经节字符串标识）",
                "property_hint": "name / ref 字符串属性（以 state/导入脚本实际字段为准）",
                "from": ref,
                "to": fixed,
                "linked_terms": d["terms"],
                "relation_hint": "Truth_Point -[:引用/RELATED]-> Scripture（以图谱实际关系类型为准；本任务不连库）",
                "collision_if_rename": fixed in chosen,
            }
        )
    result["c5_change_list"] = change_list

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT)
    print("fails", fails)
    print("c2", c2)
    print("c3 n summary", [(x["label"], x.get("n", x.get("n_whole_file", x.get("n_in_fields")))) for x in locations])
    print("v21 帖后 keys", result["c4_v21_book_map"]["帖后_keys"])
    print("v21 keys with 贴", result["c4_v21_book_map"]["keys_containing_贴"])


if __name__ == "__main__":
    main()
