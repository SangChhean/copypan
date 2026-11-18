# -*- coding: utf-8 -*-
"""Probe5-C: 经节规范化覆盖率（只读；不联网；不读 .env）。"""
from __future__ import annotations

import importlib.util
import json
import random
import re
import sys
import types
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(r"G:\copypan")
NOTES = REPO / "qa4" / "notes"
OUT_JSON = NOTES / "probe5" / "c_result.json"

V21_PATH = Path(r"C:\Users\28121\Desktop\get_vers_v2.1.py")
BIBLE_DATA = REPO / "back_qa" / "bible_data"
SCRIPTURE_STATE = REPO / "logs" / "import_annotation_scripture_nodes_state.json"
TD_PATH = REPO / "qa4" / "data" / "graph_annotations" / "truth_dictionary_3a3b.json"
BIBLE_CHUNKS = Path(r"G:\PanAI4.0专用\索引数据\panai4_bible\02_清洗JSON\chunks_bible.json")
MAP_NOTE = Path(r"G:\PanAI4.0专用\12490原文JSONL\kg-rag_map_note.jsonl")

# v2.1 STD order for book index
STD_ORDER = [
    "创", "出", "利", "民", "申", "书", "士", "得", "撒上", "撒下", "王上", "王下",
    "代上", "代下", "拉", "尼", "斯", "伯", "诗", "箴", "传", "歌", "赛", "耶", "哀",
    "结", "但", "何", "珥", "摩", "俄", "拿", "弥", "鸿", "哈", "番", "该", "亚", "玛",
    "太", "可", "路", "约", "徒", "罗", "林前", "林后", "加", "弗", "腓", "西",
    "帖前", "帖后", "提前", "提后", "多", "门", "来", "雅", "彼前", "彼后",
    "约壹", "约贰", "约叁", "犹", "启",
]
STD2IDX = {s: i + 1 for i, s in enumerate(STD_ORDER)}


def find_v21_candidates() -> list[dict]:
    cands = []
    roots = [Path(r"G:\\"), Path(r"C:\Users\28121\Desktop")]
    patterns = ("*get_vers*", "*经文出处*", "*v2.1*")
    # Desktop shallow + known path; avoid full G:\ scan (too slow). Search G:\copypan and G:\PanAI4.0专用
    search_roots = [
        Path(r"C:\Users\28121\Desktop"),
        REPO,
        Path(r"G:\PanAI4.0专用"),
    ]
    for root in search_roots:
        if not root.exists():
            continue
        for pat in patterns:
            try:
                for p in root.rglob(pat):
                    if p.is_file():
                        cands.append({"path": str(p), "size": p.stat().st_size})
            except Exception:
                continue
    # dedupe
    seen = set()
    out = []
    for c in cands:
        if c["path"] in seen:
            continue
        seen.add(c["path"])
        out.append(c)
    return out


def stub_import_parse():
    sys.path.insert(0, str(REPO))
    fake_deps = types.ModuleType("back_qa.qa.dependencies")
    fake_deps.get_es_client = lambda: None
    fake_deps.get_neo4j_client = lambda: None
    fake_deps.get_redis_client = lambda: None
    sys.modules["back_qa.qa.dependencies"] = fake_deps
    fake_prompts = types.ModuleType("back_qa.qa.prompts")
    fake_prompts.BIBLE_STEP4_ANSWER_GENERATION = "x"
    sys.modules["back_qa.qa.prompts"] = fake_prompts
    fake_qs = types.ModuleType("back_qa.qa.qa_service")
    for name in [
        "STEP3_MODEL",
        "STEP4_MODEL",
        "_calc_cost",
        "_step1",
        "_build_history_context",
        "_call_llm",
        "_extract_step4_sources",
        "_get_async_claude_client",
        "_step2_with_expansion",
    ]:
        setattr(fake_qs, name, "x" if name.endswith("MODEL") else (lambda *a, **k: None))
    sys.modules["back_qa.qa.qa_service"] = fake_qs
    from back_qa.qa import bible_service
    from back_qa.qa.bible_service import load_bible_data, get_verse
    from back_qa.qa.bible_ref_parser import parse_bible_ref

    load_bible_data(str(BIBLE_DATA))
    return bible_service, parse_bible_ref, get_verse


def load_v21(module_path: Path):
    spec = importlib.util.spec_from_file_location("get_vers_v21_probe", module_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def build_bible_index(bible_service) -> dict:
    """book -> chapter -> set(verse_nums)"""
    idx = {}
    for book, vol in bible_service._bible.items():
        chmap = {}
        for ch in vol.get("chapters") or []:
            if not isinstance(ch, dict):
                continue
            cnum = ch.get("chapter")
            verses = set()
            for v in ch.get("verses") or []:
                if isinstance(v, dict) and v.get("verse") is not None:
                    try:
                        verses.add(int(v["verse"]))
                    except Exception:
                        pass
            if cnum is not None:
                chmap[int(cnum)] = verses
        idx[int(book)] = chmap
    return idx


def build_v21_validator(bible_idx):
    def validate(std, chap, verse=None):
        bid = STD2IDX.get(std)
        if bid is None:
            return False
        chmap = bible_idx.get(bid) or {}
        try:
            chap = int(chap)
        except Exception:
            return False
        if chap not in chmap:
            return False
        if verse is None:
            return True
        try:
            verse = int(verse)
        except Exception:
            return False
        return verse in chmap[chap]

    return validate


def parse_v21_refs(mod, text: str, validate):
    """Return list of verse strings from v2.1 parser for a standalone ref string."""
    p = mod.VerseParser(validate=validate)
    p.start_paragraph()
    groups = p.parse_text(text)
    verses = []
    for g in groups:
        vs = g.get("verses") or ""
        for part in vs.split("，"):
            part = part.strip()
            if part:
                verses.append(part)
    return groups, verses


def classify_v21_token(tok: str) -> str:
    """whole_chapter / cross_chapter / verse_or_range / other"""
    # cross: 太5:1_7:29 style or 太5_7
    if "_" in tok:
        return "cross_chapter"
    # whole chapter: 太5  (no colon)
    if re.fullmatch(r"[^\d:]+?\d+", tok) and ":" not in tok:
        return "whole_chapter"
    # also 太5，太6 style already split
    if ":" not in tok and re.search(r"\d+$", tok):
        return "whole_chapter"
    return "verse_or_range"


def v21_token_to_keys(tok: str) -> tuple[str, list[tuple]]:
    """
    Convert v2.1 token to list of (book_id, chap, v_start, v_end).
    Returns (kind, keys).
    """
    kind = classify_v21_token(tok)
    if kind == "cross_chapter":
        return kind, []
    # book+chap[:verse[-verse]]
    m = re.match(r"^(.+?)(\d+)(?::(\d+)(?:-(\d+))?)?$", tok)
    if not m:
        return "other", []
    std, chap, v1, v2 = m.group(1), int(m.group(2)), m.group(3), m.group(4)
    bid = STD2IDX.get(std)
    if bid is None:
        return "other", []
    if v1 is None:
        return "whole_chapter", [(bid, chap, None, None)]
    vs = int(v1)
    ve = int(v2) if v2 else vs
    return "verse_or_range", [(bid, chap, vs, ve)]


def parse3_to_key(res: dict | None) -> tuple[str, list[tuple]]:
    if not res:
        return "fail", []
    t = res.get("type")
    book = res.get("book")
    ch = res.get("chapter")
    if t == "chapter":
        return "whole_chapter", [(book, ch, None, None)]
    if t == "verse":
        v = res.get("verse")
        return "verse_or_range", [(book, ch, v, v)]
    if t == "range":
        return "verse_or_range", [(book, ch, res.get("verse_start"), res.get("verse_end"))]
    return "other", []


def in_bible(bible_idx, book, ch, vs, ve) -> bool:
    chmap = bible_idx.get(int(book)) or {}
    if int(ch) not in chmap:
        return False
    verses = chmap[int(ch)]
    if vs is None:
        return True  # whole chapter exists
    for v in range(int(vs), int(ve) + 1):
        if v not in verses:
            return False
    return True


def split_3a_reading_line(content: str) -> list[str]:
    """切分 content_3a 开头「读经：」行的单个出处。规则写进报告。"""
    if not content:
        return []
    first = content.splitlines()[0].strip()
    if first.startswith("读经："):
        body = first[len("读经：") :].strip()
    elif first.startswith("读经:"):
        body = first[len("读经:") :].strip()
    else:
        return []  # 无读经行
    # 以中文/英文逗号、分号、顿号切；保留每段
    parts = re.split(r"[，,；;、]", body)
    return [p.strip() for p in parts if p.strip()]


def extract_map_note_ref(source_zh: str) -> str | None:
    """从（恢复本圣经，可十四24，注1）取出经节部分。"""
    if not source_zh:
        return None
    s = source_zh.strip()
    # strip outer parens
    s = s.strip("（）()")
    # expect: 恢复本圣经，<ref>，注N
    parts = re.split(r"[，,]", s)
    if len(parts) < 2:
        return None
    # drop leading 恢复本... and trailing 注N
    mid = []
    for i, p in enumerate(parts):
        p = p.strip()
        if i == 0 and ("恢复本" in p or "圣经" in p):
            continue
        if re.match(r"^注\s*\d+", p):
            continue
        if p:
            mid.append(p)
    if not mid:
        return None
    return mid[0]


def fail_bucket(ref: str) -> str:
    """粗分失败写法类别。"""
    r = ref or ""
    if not r:
        return "空串"
    if re.search(r"至|到", r) and re.search(r"[章篇]|[一二三四五六七八九十百]+$", r):
        return "跨章/整段至（如太五至七）"
    if re.search(r"[～~－—\-]", r) and "注" in r:
        return "含注号+范围"
    if "注" in r:
        return "含注号"
    if re.search(r"[上下]", r):
        return "含上下半节"
    if re.search(r"[、及和].*节|节.*[、及和]", r):
        return "中文节号列表"
    if re.fullmatch(r".+[一二三四五六七八九十百〇零○\d]+章?", r) and not re.search(r"[节:~～\d]$", r):
        return "疑似整章"
    if re.search(r"\d+:\d+", r):
        return "阿拉伯章:节"
    if re.search(r"[一二三四五六七八九十百〇零○]+\d+", r):
        return "中文章+阿拉伯节"
    if re.search(r"[a-zA-Z]", r):
        return "含英文"
    if len(r) > 40:
        return "超长串"
    if "：" in r or ":" in r:
        return "含冒号其它"
    return "其它"


_CROSS_PAT = re.compile(
    r"^(.+?)([一二三四五六七八九十百〇零○\d]+)(?:章|篇)?\s*[至到～~－—\-]\s*"
    r"(.+?)?([一二三四五六七八九十百〇零○\d]+)(?:章|篇)?$"
)
_WHOLE_PAT = re.compile(
    r"^(.+?)第?([一二三四五六七八九十百〇零○\d]+)(?:章|篇)$"
)


def preclassify_special(ref: str) -> str | None:
    """跨章/整章启发式：解析器失败时仍单独计数、不算失败。"""
    r = (ref or "").strip()
    if not r:
        return None
    # 太五至七 / 马太五至七章 / 约十四章至十六章
    if _CROSS_PAT.match(r) and re.search(r"[至到]", r):
        # 避免把「1～3」节范围误判：若无书名特征且纯数字范围，不算跨章
        if re.fullmatch(r"\d+\s*[～~－—\-]\s*\d+", r):
            return None
        # 两侧都像章号且整体不像「章X节至章Y节」带节
        if "节" not in r:
            return "cross_chapter"
        # 带节的跨章：…章…节至…章…节
        if r.count("章") + r.count("篇") >= 2 and r.count("节") >= 2:
            return "cross_chapter"
    if _WHOLE_PAT.match(r) and "节" not in r and not re.search(r"\d", r.split("章")[0][-3:] if "章" in r else ""):
        return "whole_chapter"
    return None


def evaluate_ref(ref: str, parse_bible_ref, mod, validate, bible_idx) -> dict:
    """Evaluate one ref with both parsers."""
    special = preclassify_special(ref)
    # --- 3.0 ---
    r3 = parse_bible_ref(ref)
    kind3, keys3 = parse3_to_key(r3)
    ok3 = False
    inbib3 = False
    if kind3 == "whole_chapter":
        ok3 = True
        inbib3 = all(in_bible(bible_idx, b, c, None, None) for b, c, _, _ in keys3)
    elif kind3 == "verse_or_range" and keys3:
        ok3 = True
        inbib3 = all(in_bible(bible_idx, b, c, vs, ve) for b, c, vs, ve in keys3)
    elif special in ("cross_chapter", "whole_chapter"):
        kind3 = special
        ok3 = True
        inbib3 = True  # 不列原文，不算 bible 失败
    # --- v2.1 ---
    groups, toks = parse_v21_refs(mod, ref, validate)
    kinds = []
    keys21 = []
    for tok in toks:
        k, ks = v21_token_to_keys(tok)
        kinds.append(k)
        keys21.extend(ks)
    if not toks:
        if special in ("cross_chapter", "whole_chapter"):
            kind21 = special
            ok21 = True
            inbib21 = True
        else:
            kind21 = "fail"
            ok21 = False
            inbib21 = False
    elif any(k == "cross_chapter" for k in kinds):
        kind21 = "cross_chapter"
        ok21 = True
        inbib21 = False  # not counted as bible lookup success requirement
    elif all(k == "whole_chapter" for k in kinds):
        kind21 = "whole_chapter"
        ok21 = True
        inbib21 = all(in_bible(bible_idx, b, c, None, None) for b, c, _, _ in keys21) if keys21 else False
    else:
        kind21 = "verse_or_range"
        ok21 = True
        inbib21 = all(in_bible(bible_idx, b, c, vs, ve) for b, c, vs, ve in keys21) if keys21 else False

    # comparable normalized key for disagreements: first verse key if any
    def norm_set(kind, keys):
        if kind in ("fail", "other"):
            return ("fail",)
        if kind == "cross_chapter":
            return ("cross", tuple(toks))
        if kind == "whole_chapter":
            return ("ch", tuple((b, c) for b, c, _, _ in keys))
        return ("vr", tuple(keys))

    return {
        "ref": ref,
        "r3": r3,
        "kind3": kind3,
        "ok3": ok3,
        "inbib3": inbib3 and ok3,
        "toks21": toks,
        "kind21": kind21,
        "ok21": ok21,
        "inbib21": (inbib21 and ok21) if kind21 not in ("cross_chapter", "whole_chapter") else (ok21 and (inbib21 if kind21 == "whole_chapter" else True)),
        "norm3": norm_set(kind3, keys3),
        "norm21": norm_set(kind21, keys21),
        "keys3": keys3,
        "keys21": keys21,
    }


def summarize(results: list[dict], tag: str) -> dict:
    n = len(results)
    s = {
        "tag": tag,
        "total": n,
        "v21": {
            "ok": sum(1 for r in results if r["ok21"]),
            "in_bible": sum(1 for r in results if r["inbib21"]),
            "whole": sum(1 for r in results if r["kind21"] == "whole_chapter"),
            "cross": sum(1 for r in results if r["kind21"] == "cross_chapter"),
            "fail": sum(1 for r in results if not r["ok21"]),
        },
        "p30": {
            "ok": sum(1 for r in results if r["ok3"]),
            "in_bible": sum(1 for r in results if r["inbib3"]),
            "whole": sum(1 for r in results if r["kind3"] == "whole_chapter"),
            "cross": 0,  # 3.0 parser 无跨章类型
            "fail": sum(1 for r in results if not r["ok3"]),
        },
    }
    # disagreement: both attempted; compare norm
    disagree = []
    for r in results:
        # treat whole/cross specially
        if r["norm3"] != r["norm21"]:
            disagree.append(r)
    s["disagree_n"] = len(disagree)
    s["disagree_examples"] = [
        {
            "ref": x["ref"][:30],
            "p30": x["kind3"],
            "v21": x["kind21"],
            "toks21": [t[:20] for t in x["toks21"][:3]],
            "r3": (x["r3"] or {}).get("type") if x["r3"] else None,
        }
        for x in disagree[:5]
    ]
    # fail taxonomy (union of fails for either parser, prefer v21 fails + p30 fails separately)
    fail_v21 = Counter()
    fail_ex_v21 = defaultdict(list)
    fail_p30 = Counter()
    fail_ex_p30 = defaultdict(list)
    for r in results:
        if not r["ok21"]:
            b = fail_bucket(r["ref"])
            fail_v21[b] += 1
            if len(fail_ex_v21[b]) < 3:
                fail_ex_v21[b].append(r["ref"][:30])
        if not r["ok3"]:
            b = fail_bucket(r["ref"])
            fail_p30[b] += 1
            if len(fail_ex_p30[b]) < 3:
                fail_ex_p30[b].append(r["ref"][:30])
    s["fail_v21_top15"] = [
        {"bucket": k, "n": n, "examples": fail_ex_v21[k]}
        for k, n in fail_v21.most_common(15)
    ]
    s["fail_p30_top15"] = [
        {"bucket": k, "n": n, "examples": fail_ex_p30[k]}
        for k, n in fail_p30.most_common(15)
    ]
    return s


def collect_keys(results: list[dict], which: str) -> set:
    """Unified keys (book, chap, v_start, v_end) from successful verse_or_range parses."""
    out = set()
    for r in results:
        keys = r["keys21"] if which == "v21" else r["keys3"]
        kind = r["kind21"] if which == "v21" else r["kind3"]
        inbib = r["inbib21"] if which == "v21" else r["inbib3"]
        if kind != "verse_or_range" or not inbib:
            continue
        for b, c, vs, ve in keys:
            if b is None or c is None or vs is None or ve is None:
                continue
            out.add((int(b), int(c), int(vs), int(ve)))
    return out


def main():
    result = {"script": "qa4/notes/probe5/c_verse_norm.py", "V21_PATH": str(V21_PATH)}
    cands = find_v21_candidates()
    result["v21_candidates"] = cands

    if not V21_PATH.is_file():
        result["status"] = "待 Srey 提供路径"
        result["note"] = "V21_PATH 不存在；仅列出候选。A/B 已完成。"
        OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("V21 missing; wrote", OUT_JSON)
        return

    # API report from reading source (static)
    result["v21_api"] = {
        "entry": "VerseParser.parse_text / process_data",
        "call": "p=VerseParser(validate=...); p.start_paragraph(); p.parse_text(text)",
        "output": "list[{text,verses,start,end}]; verses 如 太5:1-3 或 太5:1_7:29 或 太5",
        "deps": ["本地正则", "可选 bible 校验器 build_validator", "可选 load_book_map(bible.json)"],
        "path": str(V21_PATH),
        "size": V21_PATH.stat().st_size,
    }

    bible_service, parse_bible_ref, get_verse = stub_import_parse()
    bible_idx = build_bible_index(bible_service)
    result["bible_data_books"] = len(bible_idx)
    result["bible_data_chapters"] = sum(len(v) for v in bible_idx.values())
    result["bible_data_verses"] = sum(len(vs) for ch in bible_idx.values() for vs in ch.values())

    mod = load_v21(V21_PATH)
    validate = build_v21_validator(bible_idx)

    # smoke
    smoke_refs = [
        "约三16",
        "创一1～3",
        "太五至七",
        "诗八九26",
        "约翰福音三章十六节",
        "可十四24",
        "罗八28",
        "诗篇一章",
    ]
    smoke = []
    for ref in smoke_refs:
        smoke.append(evaluate_ref(ref, parse_bible_ref, mod, validate, bible_idx))
    result["smoke"] = [
        {
            "ref": s["ref"],
            "ok3": s["ok3"],
            "kind3": s["kind3"],
            "ok21": s["ok21"],
            "kind21": s["kind21"],
            "toks21": s["toks21"],
        }
        for s in smoke
    ]

    # --- datasets ---
    datasets = {}

    # (i) scripture chosen keys
    st = json.loads(SCRIPTURE_STATE.read_text(encoding="utf-8"))
    chosen = st.get("chosen") or {}
    refs_i = list(chosen.keys())
    datasets["graph_scripture"] = refs_i

    # (ii) 3a 读经
    td = json.loads(TD_PATH.read_text(encoding="utf-8"))
    refs_ii = []
    n_with = 0
    for row in td:
        parts = split_3a_reading_line(row.get("content_3a") or "")
        if parts:
            n_with += 1
            refs_ii.extend(parts)
    result["3a_split_rule"] = (
        "取 content_3a 首行；若以「读经：」或「读经:」开头则去掉前缀；"
        "再按中文逗号/英文逗号/分号/顿号切开；去空白；空段丢弃。"
    )
    result["3a_entries_with_reading"] = n_with
    result["3a_entries_total"] = len(td)
    datasets["def_3a"] = refs_ii

    # (iii) qa4_bible verses
    refs_iii = []
    n_verses = 0
    with BIBLE_CHUNKS.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            o = json.loads(line)
            if o.get("chunk_type") != "verses":
                continue
            n_verses += 1
            bt = (o.get("book_title") or "").strip()
            vr = (o.get("verse_range") or "").strip()
            if bt and vr:
                refs_iii.append(f"{bt}{vr}")
            elif bt:
                refs_iii.append(bt)
    result["qa4_bible_verses_n"] = n_verses
    datasets["qa4_bible"] = refs_iii

    # (iv) map_note sample 2000
    map_refs = []
    with MAP_NOTE.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            o = json.loads(line)
            ref = extract_map_note_ref(o.get("source_zh") or "")
            if ref:
                map_refs.append(ref)
    rng = random.Random(20261116)
    if len(map_refs) > 2000:
        refs_iv = rng.sample(map_refs, 2000)
    else:
        refs_iv = list(map_refs)
    result["map_note_extractable"] = len(map_refs)
    result["map_note_sample_n"] = len(refs_iv)
    result["map_note_extract_rule"] = (
        "去掉外层括号；按逗号切分；丢弃含「恢复本/圣经」的首段与「注N」段；取剩余第一段。"
    )
    datasets["map_note"] = refs_iv

    summaries = {}
    all_results = {}
    for name, refs in datasets.items():
        print("evaluating", name, len(refs), flush=True)
        rows = [evaluate_ref(r, parse_bible_ref, mod, validate, bible_idx) for r in refs]
        all_results[name] = rows
        summaries[name] = summarize(rows, name)
        print("  done", name, summaries[name]["v21"], summaries[name]["p30"], flush=True)

    result["summaries"] = summaries

    # unified key feasibility across 5 sources (use v21 successful verse keys + bible_data itself)
    keys = {}
    for name, rows in all_results.items():
        keys[name] = collect_keys(rows, "v21")
    # bible_data as single-verse keys
    bd_keys = set()
    for b, chmap in bible_idx.items():
        for c, verses in chmap.items():
            for v in verses:
                bd_keys.add((b, c, v, v))
    keys["bible_data"] = bd_keys

    result["unified_key_sizes"] = {k: len(v) for k, v in keys.items()}
    # pairwise overlap ratios vs bible_data
    overlap = {}
    for k, s in keys.items():
        if k == "bible_data":
            continue
        inter = len(s & bd_keys)
        only = len(s - bd_keys)
        overlap[k] = {
            "n": len(s),
            "in_bible_data": inter,
            "not_in_bible_data": only,
            "note": "keys are (book,chap,v_start,v_end); ranges kept as-is (not expanded)",
        }
    result["unified_vs_bible_data"] = overlap

    # mismatch types
    mismatch_types = []
    for name, rows in all_results.items():
        n_range = sum(
            1
            for r in rows
            if r["kind21"] == "verse_or_range"
            and any(vs != ve for _, _, vs, ve in r["keys21"])
        )
        n_whole = sum(1 for r in rows if r["kind21"] == "whole_chapter")
        n_cross = sum(1 for r in rows if r["kind21"] == "cross_chapter")
        n_fail = sum(1 for r in rows if not r["ok21"])
        mismatch_types.append(
            {
                "source": name,
                "range_not_single": n_range,
                "whole_chapter": n_whole,
                "cross_chapter": n_cross,
                "parse_fail": n_fail,
            }
        )
    result["unified_mismatch_types"] = mismatch_types

    # keep compact: drop per-ref dumps
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT_JSON)


if __name__ == "__main__":
    main()
