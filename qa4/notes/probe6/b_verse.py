# -*- coding: utf-8 -*-
"""Probe6-B: 经节补测（3a 整行 + qa4_bible X0 + 三源 X0 计数）。只读。"""
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
OUT = REPO / "qa4" / "notes" / "probe6" / "b_result.json"
V21 = Path(r"C:\Users\28121\Desktop\get_vers_v2.1.py")
TD = REPO / "qa4" / "data" / "graph_annotations" / "truth_dictionary_3a3b.json"
BIBLE_CHUNKS = Path(r"G:\PanAI4.0专用\索引数据\panai4_bible\02_清洗JSON\chunks_bible.json")
MAP_NOTE = Path(r"G:\PanAI4.0专用\12490原文JSONL\kg-rag_map_note.jsonl")
SCRIPTURE_STATE = REPO / "logs" / "import_annotation_scripture_nodes_state.json"
BIBLE_DATA = REPO / "back_qa" / "bible_data"

STD_ORDER = [
    "创", "出", "利", "民", "申", "书", "士", "得", "撒上", "撒下", "王上", "王下",
    "代上", "代下", "拉", "尼", "斯", "伯", "诗", "箴", "传", "歌", "赛", "耶", "哀",
    "结", "但", "何", "珥", "摩", "俄", "拿", "弥", "鸿", "哈", "番", "该", "亚", "玛",
    "太", "可", "路", "约", "徒", "罗", "林前", "林后", "加", "弗", "腓", "西",
    "帖前", "帖后", "提前", "提后", "多", "门", "来", "雅", "彼前", "彼后",
    "约壹", "约贰", "约叁", "犹", "启",
]
STD2IDX = {s: i + 1 for i, s in enumerate(STD_ORDER)}

# 「汉字十位数字 + 阿拉伯 0」：十位数字=一二三四五六七八九，如 三0→三十；十一0 中的「一0」亦命中
X0_RE = re.compile(r"([一二三四五六七八九])0")
# 补充观察：前接「十」的「十0」（如二十0）——单独统计
SHI0_RE = re.compile(r"十0")
# 章节数字串启发式：中文章号块或 中文/阿位数字连续
DIGITISH_RE = re.compile(
    r"(?:[一二三四五六七八九十百千〇零○]+|\d+)(?:[～~－—\-](?:[一二三四五六七八九十百千〇零○]+|\d+))?"
)


def load_v21():
    spec = importlib.util.spec_from_file_location("get_vers_v21_p6", V21)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def stub_bible_idx():
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
    from back_qa.qa.bible_service import load_bible_data

    load_bible_data(str(BIBLE_DATA))
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


def classify_tok(tok: str) -> str:
    if "_" in tok:
        return "cross_chapter"
    if ":" not in tok and re.search(r"\d+$", tok):
        return "whole_chapter"
    return "verse_or_range"


def parse_tok_key(tok: str):
    m = re.match(r"^(.+?)(\d+)(?::(\d+)(?:-(\d+))?)?$", tok)
    if not m:
        return None
    std, chap, v1, v2 = m.group(1), int(m.group(2)), m.group(3), m.group(4)
    bid = STD2IDX.get(std)
    if bid is None:
        return None
    if v1 is None:
        return (bid, chap, None, None)
    vs = int(v1)
    ve = int(v2) if v2 else vs
    return (bid, chap, vs, ve)


def in_bible(idx, key) -> bool:
    if key is None:
        return False
    b, c, vs, ve = key
    chmap = idx.get(int(b)) or {}
    if int(c) not in chmap:
        return False
    if vs is None:
        return True
    verses = chmap[int(c)]
    for v in range(int(vs), int(ve) + 1):
        if v not in verses:
            return False
    return True


def build_validator(bible_idx):
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


def parse_line(mod, text: str, validate=None):
    p = mod.VerseParser(validate=validate)
    p.start_paragraph()
    groups = p.parse_text(text)
    toks = []
    for g in groups:
        for part in (g.get("verses") or "").split("，"):
            part = part.strip()
            if part:
                toks.append(part)
    return groups, toks


def normalize_x0(s: str) -> str:
    """脚本内：汉字十位 + 阿拉伯 0 → 汉字十。例 三0→三十。"""
    return X0_RE.sub(r"\1十", s)


def extract_map_ref(source_zh: str) -> str | None:
    if not source_zh:
        return None
    s = source_zh.strip().strip("（）()")
    parts = re.split(r"[，,]", s)
    mid = []
    for i, p in enumerate(parts):
        p = p.strip()
        if i == 0 and ("恢复本" in p or "圣经" in p):
            continue
        if re.match(r"^注\s*\d+", p):
            continue
        if p:
            mid.append(p)
    return mid[0] if mid else None


def chapter_style(vr: str) -> str:
    """归类 verse_range / 拼接串 的章号写法。"""
    if X0_RE.search(vr):
        return "汉字十位+阿拉伯0（如三0）"
    if re.search(r"[〇零○]0|[〇零○]\d", vr):
        return "含〇/零/○与数字"
    if re.search(r"[一二三四五六七八九十百]+0", vr):
        return "中文数后接0（广义）"
    if re.search(r"[一二三四五六七八九十百]+～", vr) or re.search(
        r"[一二三四五六七八九十百]+~", vr
    ):
        return "纯汉字章+波浪范围"
    if re.search(r"[上下]", vr):
        return "含上下半节"
    if re.search(r"\d", vr) and re.search(r"[一二三四五六七八九十]", vr):
        return "中阿混杂其它"
    if re.fullmatch(r"[一二三四五六七八九十百千〇零○～~\-－—\d上下]+", vr or ""):
        return "纯章节符号串"
    return "其它"


def count_x0(texts: list[str]) -> dict:
    n_hits = 0
    examples = []
    for t in texts:
        if X0_RE.search(t or ""):
            n_hits += 1
            if len(examples) < 10:
                examples.append((t or "")[:30])
    return {"n": n_hits, "examples": examples, "regex": r"([一二三四五六七八九])0"}


def heuristic_miss(line: str, n_toks: int) -> bool:
    """
    遗漏启发式（修订）：按逗号/顿号/分号切段，统计「含章节数字串」的段数 seg_n；
    若 seg_n >= 3 且 seg_n >= n_toks + 2，则疑似有段未解析成出处。
    （旧规则直接数 DIGITISH 命中会把同一出处内的章号+节号算两次，误报过高。）
    """
    segs = [s.strip() for s in re.split(r"[，,、；;]", line) if s.strip()]
    seg_n = sum(1 for s in segs if DIGITISH_RE.search(s))
    return seg_n >= 3 and seg_n >= n_toks + 2


def main():
    result = {"script": "qa4/notes/probe6/b_verse.py", "V21_PATH": str(V21)}
    mod = load_v21()
    bible_idx = stub_bible_idx()
    validate = build_validator(bible_idx)

    # ---------- B1 3a 整行 ----------
    td = json.loads(TD.read_text(encoding="utf-8"))
    reading_lines = []
    for row in td:
        c3a = row.get("content_3a") or ""
        if not c3a:
            continue
        first = c3a.splitlines()[0].strip()
        if first.startswith("读经："):
            body = first[len("读经：") :].strip()
        elif first.startswith("读经:"):
            body = first[len("读经:") :].strip()
        else:
            continue
        reading_lines.append({"title": row.get("title"), "line": body, "raw_first": first[:30]})

    n_with = len(reading_lines)
    n_ge1 = 0
    n_zero = 0
    zero_samples = []
    total_toks = 0
    kinds = Counter()
    inbib = 0
    miss_heuristic = 0
    miss_samples = []

    for item in reading_lines:
        line = item["line"]
        _, toks = parse_line(mod, line, validate=validate)
        total_toks += len(toks)
        if toks:
            n_ge1 += 1
        else:
            n_zero += 1
            if len(zero_samples) < 10:
                zero_samples.append(line[:30])
        for tok in toks:
            k = classify_tok(tok)
            kinds[k] += 1
            key = parse_tok_key(tok)
            if k == "cross_chapter":
                # 跨章单独计，不算 bible 失败；也不强求 in_bible
                pass
            elif in_bible(bible_idx, key):
                inbib += 1
        if heuristic_miss(line, len(toks)):
            miss_heuristic += 1
            if len(miss_samples) < 5:
                miss_samples.append(
                    {
                        "line30": line[:30],
                        "n_toks": len(toks),
                        "digitish_n": len(DIGITISH_RE.findall(line)),
                    }
                )

    result["b1_3a_whole_line"] = {
        "n_entries_with_reading": n_with,
        "n_lines_ge1_ref": n_ge1,
        "n_refs_total": total_toks,
        "kinds": dict(kinds),
        "n_in_bible_data": inbib,
        "n_zero_ref_lines": n_zero,
        "zero_samples": zero_samples,
        "miss_heuristic_n": miss_heuristic,
        "miss_heuristic_rule": (
            "DIGITISH_RE 匹配章节数字串个数 n；若 n>=3 且 n >= 解析出处数+2，计为疑似遗漏。"
            f" DIGITISH_RE={DIGITISH_RE.pattern}"
        ),
        "miss_samples": miss_samples,
        "split_note": "整行不切分；每行 start_paragraph + parse_text",
    }

    # ---------- B2 qa4_bible 失败 & X0 修复 ----------
    refs = []
    with BIBLE_CHUNKS.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            o = json.loads(line)
            if o.get("chunk_type") != "verses":
                continue
            bt = (o.get("book_title") or "").strip()
            vr = (o.get("verse_range") or "").strip()
            ref = f"{bt}{vr}" if bt and vr else bt
            refs.append({"book_title": bt, "verse_range": vr, "ref": ref, "chunk_id": o.get("chunk_id")})

    # 失败定义（与第五轮带 validate 口径一致）：校验后无任何 tok
    fail_rows = []
    for r in refs:
        _, toks = parse_line(mod, r["ref"], validate=validate)
        if not toks:
            fail_rows.append(r)

    by_book = Counter(r["book_title"] for r in fail_rows)
    by_style = Counter(chapter_style(r["verse_range"] or r["ref"]) for r in fail_rows)
    x0_pattern_n = sum(
        1 for r in fail_rows if X0_RE.search(r["verse_range"] or "") or X0_RE.search(r["ref"])
    )
    shi0_n = sum(1 for r in fail_rows if SHI0_RE.search(r["verse_range"] or ""))
    either_n = sum(
        1
        for r in fail_rows
        if X0_RE.search(r["verse_range"] or "") or SHI0_RE.search(r["verse_range"] or "")
    )
    # 是否「都」符合 X0_RE
    all_match_x0 = (x0_pattern_n == len(fail_rows)) if fail_rows else False

    # normalize and retest（仍带 validate）
    fixed_ok = 0
    still_fail = []
    for r in fail_rows:
        fixed = normalize_x0(r["ref"])
        # 另：十0 → 十十（仅脚本内试验，与「X0→X十」平行记录）
        fixed2 = SHI0_RE.sub("十十", fixed)
        _, toks = parse_line(mod, fixed, validate=validate)
        ok = bool(toks)
        if not ok and fixed2 != fixed:
            _, toks2 = parse_line(mod, fixed2, validate=validate)
            if toks2:
                ok = True
                fixed = fixed2
        if ok:
            fixed_ok += 1
        else:
            still_fail.append(
                {
                    "ref30": r["ref"][:30],
                    "fixed30": normalize_x0(r["ref"])[:30],
                    "style": chapter_style(r["verse_range"] or ""),
                }
            )

    still_styles = Counter(x["style"] for x in still_fail)
    still_ex = defaultdict(list)
    for x in still_fail:
        if len(still_ex[x["style"]]) < 3:
            still_ex[x["style"]].append(x["ref30"])

    result["b2_qa4_bible_fails"] = {
        "verses_total": len(refs),
        "v21_fail_n": len(fail_rows),
        "fail_book_title_top10": by_book.most_common(10),
        "chapter_style_counts": dict(by_style),
        "x0_regex": X0_RE.pattern,
        "shi0_regex": SHI0_RE.pattern,
        "n_matching_x0_regex": x0_pattern_n,
        "n_matching_shi0_regex": shi0_n,
        "n_matching_x0_or_shi0": either_n,
        "all_fails_match_x0": all_match_x0,
        "note_validate": "VerseParser(validate=bible_data)：节号0会被校验丢掉，与第五轮失败口径一致",
        "after_normalize_x0_success": fixed_ok,
        "after_normalize_still_fail": len(still_fail),
        "still_fail_top_styles": [
            {"style": k, "n": still_styles[k], "examples": still_ex[k]}
            for k, _ in still_styles.most_common(10)
        ],
        "fail_examples_raw": [r["ref"][:30] for r in fail_rows[:10]],
    }

    # ---------- B3 X0 in three sources ----------
    st = json.loads(SCRIPTURE_STATE.read_text(encoding="utf-8"))
    chosen_refs = list((st.get("chosen") or {}).keys())
    x0_graph = count_x0(chosen_refs)

    map_refs = []
    with MAP_NOTE.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            o = json.loads(line)
            ref = extract_map_ref(o.get("source_zh") or "")
            if ref:
                map_refs.append(ref)
    rng = random.Random(20261116)
    sample = rng.sample(map_refs, 2000) if len(map_refs) > 2000 else list(map_refs)
    x0_map = count_x0(sample)

    x0_3a = count_x0([x["line"] for x in reading_lines])

    result["b3_x0_counts"] = {
        "regex": X0_RE.pattern,
        "graph_chosen_4851": {"universe": len(chosen_refs), **x0_graph},
        "map_note_sample": {"universe": len(sample), "seed": 20261116, **x0_map},
        "def_3a_reading_lines": {"universe": len(reading_lines), **x0_3a},
    }

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT)
    print("B1", result["b1_3a_whole_line"]["n_entries_with_reading"], result["b1_3a_whole_line"]["n_lines_ge1_ref"], result["b1_3a_whole_line"]["n_refs_total"], result["b1_3a_whole_line"]["kinds"])
    print("B2 fail", result["b2_qa4_bible_fails"]["v21_fail_n"], "x0", x0_pattern_n, "fixed_ok", fixed_ok)
    print("B3", result["b3_x0_counts"])


if __name__ == "__main__":
    main()
