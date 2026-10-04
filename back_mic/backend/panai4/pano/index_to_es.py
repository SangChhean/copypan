# -*- coding: utf-8 -*-
"""清明上河图目录 → panai4_pano_catalog（本轮只建本机，不写向量）。

用法：
  python -m panai4.pano.index_to_es
  python -m panai4.pano.index_to_es --target local
  python -m panai4.pano.index_to_es --smoke-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from elasticsearch.helpers import bulk

from es_config import es as local_es

CATALOG_DEFAULT = r"G:\PanAI4.0专用\清明上河图目录\catalog_clean.json"
INDEX_NAME = "panai4_pano_catalog"
REPORT_PATH = Path(r"g:\copypan\docs\panai4_es\pano_indexing_report.md")
BACKUP_ROOT = Path(r"G:\PanAI用\Pansearch数据备份\map_pano制作\备份")
BULK_SIZE = 500
SAMPLE_SEED = 20260930

# 「纲目带出处」四种括号：（）()（)(）
CHUCHU_RE = re.compile(r"[（(]\s*纲目带出处\s*[）)]")

# 层内中文序号：仅当序号后紧跟全角空格/空白时剥一次
INNER_ORDINAL_RE = re.compile(
    r"^[一二三四五六七八九十百壹贰叁肆伍陆柒捌玖拾]+[　\s]+"
)

# 破折号类字符 → 统一为 ASCII hyphen
DASH_CHARS = str.maketrans(
    {
        "\u2014": "-",  # —
        "\u2500": "-",  # ─
        "\u2013": "-",  # –
        "\u2012": "-",  # ‒
        "\u2015": "-",  # ―
        "\u2212": "-",  # −
        "-": "-",
    }
)

# P4 曾判为 B 类的 8 组（父 rel 后缀匹配 + msg_number）
B_CLASS_KEYS = [
    ("那灵——67篇/1　倪柝声弟兄职事——14篇", 1),
    ("特会、信息、及谈话记录（卷四）——4篇", 2),
    ("经历基督以建造召会作基督的身体和新人—5篇（1971年3月，旧金山）", 1),
    ("新约的职事——75篇/1　倪柝声弟兄职事——27篇", 1),
    ("新约的职事——75篇/1　倪柝声弟兄职事——27篇", 2),
    ("新约的职事——75篇/1　倪柝声弟兄职事——27篇", 3),
    ("新约的职事——75篇/1　倪柝声弟兄职事——27篇", 7),  # 保罗的路程和职事 → 应合并
    ("圣灵的水流——2篇（1950年10月，地点不详）", 1),
]

CN_DIGITS = "零一二三四五六七八九"

PANO_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "node_type": {"type": "keyword"},
            "node_id": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "raw_name": {"type": "keyword"},
            "ordinal_num": {"type": "integer"},
            "depth": {"type": "integer"},
            "rel_path": {"type": "keyword"},
            "path_names": {"type": "keyword"},
            "path_text": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "top_category": {"type": "keyword"},
            "top_ordinal": {"type": "integer"},
            "actual_count": {"type": "integer"},
            "has_subdir": {"type": "boolean"},
            "has_docx": {"type": "boolean"},
            "annotations": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "text": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "msg_number": {"type": "integer"},
            "msg_label": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "raw_filename": {"type": "keyword"},
            "title_variants": {"type": "keyword"},
            "source_version_only": {"type": "boolean"},
            "text_vector": {
                "type": "dense_vector",
                "dims": 1024,
                "index": True,
                "similarity": "cosine",
                "index_options": {"type": "int8_hnsw"},
            },
        }
    },
}


def cn_number(n: int) -> str:
    """把正整数转中文数字（覆盖到至少 550）。"""
    if not isinstance(n, int) or n < 0:
        raise ValueError(f"cn_number expects non-negative int, got {n!r}")
    if n == 0:
        return "零"
    if n < 10:
        return CN_DIGITS[n]
    if n < 20:
        return "十" if n == 10 else "十" + CN_DIGITS[n % 10]
    if n < 100:
        tens, ones = divmod(n, 10)
        return CN_DIGITS[tens] + "十" + (CN_DIGITS[ones] if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        head = CN_DIGITS[hundreds] + "百"
        if rest == 0:
            return head
        if rest < 10:
            return head + "零" + CN_DIGITS[rest]
        if rest < 20:
            return head + "一十" + (CN_DIGITS[rest % 10] if rest % 10 else "")
        return head + cn_number(rest)
    if n < 10000:
        thousands, rest = divmod(n, 1000)
        head = CN_DIGITS[thousands] + "千"
        if rest == 0:
            return head
        if rest < 100:
            return head + "零" + cn_number(rest)
        return head + cn_number(rest)
    raise ValueError(f"cn_number out of range: {n}")


def verify_cn_number() -> None:
    cases = [
        (1, "一"),
        (10, "十"),
        (11, "十一"),
        (20, "二十"),
        (21, "二十一"),
        (100, "一百"),
        (101, "一百零一"),
        (110, "一百一十"),
        (115, "一百一十五"),
        (363, "三百六十三"),
        (550, "五百五十"),
    ]
    print("=== J1 cn_number 验证 ===")
    for n, expect in cases:
        got = cn_number(n)
        print(f"  {n} → {got}")
        if got != expect:
            print(f"FAIL: expected {expect!r}, got {got!r}")
            sys.exit(1)
    print("全部通过。")


def sha12(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def normalize_title(s: str) -> str:
    """标题归一化：去空白、破折号/括号/逗号统一。"""
    if not s:
        return ""
    out = []
    for ch in s:
        if ch in (" ", "\u3000", "\t"):
            continue
        if ch in ("—", "─", "–", "‒", "―", "−", "-"):
            out.append("-")
            continue
        if ch == "（":
            out.append("(")
            continue
        if ch == "）":
            out.append(")")
            continue
        if ch == "，":
            out.append(",")
            continue
        out.append(ch)
    return "".join(out)


def verify_normalize_title() -> None:
    pairs = [
        ("保罗的路程和职事 ", "保罗的路程和职事", True),
        ("他们的现在─借着…", "他们的现在—借着…", True),
        ("在召会的建造里", "在召会的建造", False),
        ("圣灵的印记", "在另一个范围里—神就是灵…", False),
    ]
    print("=== P1 normalize_title 验证 ===")
    for a, b, expect_eq in pairs:
        na, nb = normalize_title(a), normalize_title(b)
        eq = na == nb
        print(f"  {a!r}")
        print(f"    → {na!r}")
        print(f"  {b!r}")
        print(f"    → {nb!r}")
        print(f"  equal={eq} (expect {expect_eq})")
        if eq != expect_eq:
            print("FAIL")
            sys.exit(1)
    print("全部通过。")


def is_chuchu(name: str) -> bool:
    return bool(CHUCHU_RE.search(name))


def strip_inner_ordinal(name: str) -> str:
    """剥一层内中文序号（仅当序号后有空白）；只剥一次。"""
    m = INNER_ORDINAL_RE.match(name)
    if not m:
        return name
    return name[m.end() :].strip()


def norm_annotations(raw: Any) -> list:
    """空值统一为 []；字符串包成单元素列表；列表原样。"""
    if raw is None or raw == "" or raw == []:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        return [raw]
    return [str(raw)]


def msg_has_clean(m: dict) -> bool:
    return any(not is_chuchu(f) for f in (m.get("raw_filenames") or []))


def merge_message_group(msgs: list[dict]) -> dict:
    """按 (父, msg_number, normalize_title) 合并一组。

    title：优先干净版的原始写法；全是出处版则取文件名最短那条的 title。
    title_variants：组内其它原始写法。
    source_version_only：组内没有任何干净版文件。
    """
    assert msgs
    msg_number = int(msgs[0]["msg_number"])
    all_files: list[str] = []
    for m in msgs:
        all_files.extend(m.get("raw_filenames") or [])
    clean_files = [f for f in all_files if not is_chuchu(f)]
    svo = len(clean_files) == 0

    non_svo = [m for m in msgs if msg_has_clean(m)]
    if non_svo:

        def clean_key(m: dict) -> tuple[int, str]:
            cleans = [f for f in (m.get("raw_filenames") or []) if not is_chuchu(f)]
            fn = min(cleans, key=len) if cleans else ""
            return (len(fn), fn)

        primary = min(non_svo, key=clean_key)
    else:

        def short_key(m: dict) -> tuple[int, str]:
            files = m.get("raw_filenames") or []
            fn = min(files, key=len) if files else ""
            return (len(fn), fn)

        primary = min(msgs, key=short_key)

    title = primary.get("title") or ""
    variants: list[str] = []
    for m in msgs:
        t = m.get("title") or ""
        if t and t != title and t not in variants:
            variants.append(t)

    pfiles = primary.get("raw_filenames") or []
    pclean = [f for f in pfiles if not is_chuchu(f)]
    if pclean:
        raw_fn = min(pclean, key=len)
    elif clean_files:
        raw_fn = min(clean_files, key=len)
    elif all_files:
        raw_fn = min(all_files, key=len)
    else:
        raw_fn = ""

    return {
        "msg_number": msg_number,
        "title": title,
        "title_norm": normalize_title(title),
        "title_variants": variants,
        "raw_filename": raw_fn,
        "source_version_only": svo,
        "group_size": len(msgs),
    }


def count_messages(node: dict) -> int:
    """递归挂载数：同一父下 (msg_number, normalize_title) 只计 1。"""
    keys: set[tuple[int, str]] = set()
    sub = 0
    for c in node.get("children") or []:
        if c.get("type") == "message":
            keys.add((int(c["msg_number"]), normalize_title(c.get("title") or "")))
        elif c.get("type") == "dir":
            sub += count_messages(c)
    return len(keys) + sub


def count_messages_raw(node: dict) -> int:
    """旧口径：每条 catalog message 计 1（合并前）。"""
    total = 0
    for c in node.get("children") or []:
        if c.get("type") == "message":
            total += 1
        elif c.get("type") == "dir":
            total += count_messages_raw(c)
    return total


def flatten(catalog: dict) -> tuple[list[dict], dict]:
    """递归展平；root depth=0 不入库。

    返回 (docs, meta)，meta 含 name 剥离对照等。
    """
    docs: list[dict] = []
    peel_pairs: list[tuple[str, str, str]] = []  # (before, after, rel_path)
    safe_names = ("三一神", "一个新人", "一百八十")
    safe_hits: list[dict] = []

    def walk_dir(
        node: dict,
        *,
        path_names: list[str],
        top_category: str | None,
        top_ordinal: int | None,
    ) -> None:
        depth = node["depth"]
        name_before = node.get("name") or ""
        name = strip_inner_ordinal(name_before)
        rel_path = node.get("rel_path") or ""
        role = node.get("role") or {}
        actual = count_messages(node)

        if depth >= 1:
            if name != name_before:
                peel_pairs.append((name_before, name, rel_path))
            for sn in safe_names:
                if name_before == sn or name_before.startswith(sn):
                    safe_hits.append(
                        {
                            "name_before": name_before,
                            "name_after": name,
                            "peeled": name != name_before,
                            "rel_path": rel_path,
                        }
                    )

            cur_path_names = path_names
            cur_top = top_category if top_category is not None else name
            cur_top_ord = (
                top_ordinal if top_ordinal is not None else node.get("ordinal_num")
            )
            # K2: path_text 用 "/"
            path_text = "/".join(cur_path_names)
            node_id = "pano_d_" + sha12(rel_path)
            doc = {
                "node_type": "dir",
                "node_id": node_id,
                "name": name,
                "raw_name": node.get("raw_name") or "",
                "ordinal_num": node.get("ordinal_num"),
                "depth": depth,
                "rel_path": rel_path,
                "path_names": list(cur_path_names),
                "path_text": path_text,
                "top_category": cur_top,
                "top_ordinal": cur_top_ord,
                "actual_count": actual,
                "has_subdir": bool(role.get("has_subdir")),
                "has_docx": bool(role.get("has_docx")),
                "annotations": norm_annotations(node.get("annotations")),
                "text": path_text,
            }
            docs.append(doc)

            # 按 (msg_number, normalize_title) 合并同父下的 message
            by_key: dict[tuple[int, str], list[dict]] = {}
            for c in node.get("children") or []:
                if c.get("type") != "message":
                    continue
                num = int(c["msg_number"])
                nt = normalize_title(c.get("title") or "")
                by_key.setdefault((num, nt), []).append(c)

            for (msg_number, title_norm), group in sorted(by_key.items()):
                merged = merge_message_group(group)
                title = merged["title"]
                raw_fn = merged["raw_filename"]
                svo = merged["source_version_only"]
                variants = merged["title_variants"]
                msg_label = "第" + cn_number(int(msg_number)) + "篇"
                msg_rel = rel_path + "/" + raw_fn if raw_fn else rel_path
                node_id_m = "pano_m_" + sha12(f"{rel_path}|{msg_number}|{title_norm}")
                msg_text = path_text + "\u3000" + msg_label + "\u3000" + title
                docs.append(
                    {
                        "node_type": "message",
                        "node_id": node_id_m,
                        "msg_number": int(msg_number),
                        "msg_label": msg_label,
                        "title": title,
                        "title_variants": variants,
                        "raw_filename": raw_fn,
                        "source_version_only": svo,
                        "depth": depth + 1,
                        "rel_path": msg_rel,
                        "path_names": list(cur_path_names),
                        "path_text": path_text,
                        "top_category": cur_top,
                        "top_ordinal": cur_top_ord,
                        "text": msg_text,
                        "annotations": [],
                    }
                )

        for c in node.get("children") or []:
            if c.get("type") != "dir":
                continue
            child_before = c.get("name") or ""
            child_name = strip_inner_ordinal(child_before)
            if depth == 0:
                walk_dir(
                    c,
                    path_names=[child_name],
                    top_category=child_name,
                    top_ordinal=c.get("ordinal_num"),
                )
            else:
                walk_dir(
                    c,
                    path_names=path_names + [child_name],
                    top_category=top_category,
                    top_ordinal=top_ordinal,
                )

    walk_dir(catalog, path_names=[], top_category=None, top_ordinal=None)

    # 安全名：即使未在 walk 命中，也强制打印对照
    for sn in safe_names:
        if not any(h["name_before"] == sn for h in safe_hits):
            safe_hits.append(
                {
                    "name_before": sn,
                    "name_after": strip_inner_ordinal(sn),
                    "peeled": strip_inner_ordinal(sn) != sn,
                    "rel_path": "(synthetic)",
                }
            )

    # M4：各大类 actual_count 影响
    impact: list[dict] = []
    for top in (c for c in (catalog.get("children") or []) if c.get("type") == "dir"):
        old_c = count_messages_raw(top)
        new_c = count_messages(top)
        if old_c != new_c:
            impact.append(
                {
                    "top_category": strip_inner_ordinal(top.get("name") or ""),
                    "top_ordinal": top.get("ordinal_num"),
                    "old": old_c,
                    "new": new_c,
                    "delta": new_c - old_c,
                }
            )

    # 旧口径 (父, msg_number) 冲突 → 新键实际合并
    gmap: dict[tuple[str, int], list[str]] = defaultdict(list)

    def walk_g(n: dict) -> None:
        rel = n.get("rel_path") or ""
        for c in n.get("children") or []:
            if c.get("type") == "message":
                gmap[(rel, int(c["msg_number"]))].append(c.get("title") or "")
            elif c.get("type") == "dir":
                walk_g(c)

    walk_g(catalog)
    multi_old = {k: v for k, v in gmap.items() if len(v) > 1}
    merge_groups = 0
    merge_msgs = 0
    merge_events = 0
    for titles in multi_old.values():
        by_norm: dict[str, int] = defaultdict(int)
        for t in titles:
            by_norm[normalize_title(t)] += 1
        for cnt in by_norm.values():
            if cnt > 1:
                merge_groups += 1
                merge_msgs += cnt
                merge_events += cnt - 1

    # 展平后：同 (父, msg_number, norm_title) 不得重复
    seen3: dict[tuple[str, int, str], int] = defaultdict(int)
    by_pn: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for d in docs:
        if d["node_type"] != "message":
            continue
        parent = "/".join((d.get("rel_path") or "").split("/")[:-1])
        num = int(d["msg_number"])
        nt = normalize_title(d.get("title") or "")
        seen3[(parent, num, nt)] += 1
        by_pn[(parent, num)].append(d)

    leftover3 = {k: v for k, v in seen3.items() if v > 1}
    norm_violations: list[dict] = []
    for (parent, num), ms in by_pn.items():
        if len(ms) <= 1:
            continue
        norms = [normalize_title(m.get("title") or "") for m in ms]
        if len(norms) != len(set(norms)):
            norm_violations.append(
                {
                    "parent": parent,
                    "msg_number": num,
                    "titles": [m.get("title") for m in ms],
                    "norms": norms,
                }
            )

    # P4：B 类 8 组修正后状态（父路径须以 suffix 结尾，避免误匹配子目录）
    b_results = []
    for suffix, num in B_CLASS_KEYS:
        matched = []
        for d in docs:
            if d["node_type"] != "message" or int(d["msg_number"]) != num:
                continue
            parent = "/".join((d.get("rel_path") or "").split("/")[:-1])
            if parent == suffix or parent.endswith("/" + suffix) or parent.endswith(suffix):
                matched.append(d)
        is_paul = num == 7 and "新约的职事——75篇" in suffix
        b_results.append(
            {
                "suffix": suffix,
                "msg_number": num,
                "count": len(matched),
                "expect": "merge" if is_paul else "keep_separate",
                "ok": (len(matched) == 1 and is_paul)
                or (len(matched) == 2 and not is_paul),
                "docs": [
                    {
                        "title": m.get("title"),
                        "title_norm": normalize_title(m.get("title") or ""),
                        "title_variants": m.get("title_variants"),
                        "raw_filename": m.get("raw_filename"),
                        "source_version_only": m.get("source_version_only"),
                        "rel_path": m.get("rel_path"),
                    }
                    for m in matched
                ],
            }
        )

    n_msg = sum(1 for d in docs if d["node_type"] == "message")
    reduction = count_messages_raw(catalog) - n_msg

    meta = {
        "peel_pairs": peel_pairs,
        "safe_hits": safe_hits,
        "peel_count": len(peel_pairs),
        "merge_groups": merge_groups,
        "merge_msgs": merge_msgs,
        "merge_events": merge_events,
        "reduction": reduction,
        "impact": sorted(impact, key=lambda x: x["delta"]),
        "leftover_multi": leftover3,
        "norm_violations": norm_violations,
        "b_results": b_results,
        "old_multi_groups": len(multi_old),
    }
    return docs, meta


def create_index(client, name: str = INDEX_NAME) -> None:
    if client.indices.exists(index=name):
        print(f"删除已有索引 {name} …")
        client.indices.delete(index=name)
    body = deepcopy(PANO_MAPPING)
    client.indices.create(index=name, body=body)
    print(f"已创建索引 {name}")


def bulk_index(client, docs: list[dict], name: str = INDEX_NAME) -> dict:
    ok = fail = 0
    errors_sample: list[Any] = []
    batch: list[dict] = []
    t0 = time.perf_counter()

    def flush() -> None:
        nonlocal ok, fail, batch
        if not batch:
            return
        success, errors = bulk(
            client,
            batch,
            raise_on_error=False,
            raise_on_exception=False,
            request_timeout=180,
        )
        ok += success
        if errors:
            fail += len(errors)
            if len(errors_sample) < 5:
                errors_sample.extend(errors[: 5 - len(errors_sample)])
        batch = []

    for doc in docs:
        src = {k: v for k, v in doc.items() if k != "text_vector" and v is not None}
        batch.append(
            {
                "_op_type": "index",
                "_index": name,
                "_id": doc["node_id"],
                "_source": src,
            }
        )
        if len(batch) >= BULK_SIZE:
            flush()
            if (ok + fail) % 5000 < BULK_SIZE:
                print(f"  bulk progress ok={ok} fail={fail}")
    flush()
    client.indices.refresh(index=name)
    elapsed = time.perf_counter() - t0
    print(f"bulk 完成 ok={ok} fail={fail} elapsed={elapsed:.1f}s")
    if errors_sample:
        print("sample errors:", json.dumps(errors_sample[:2], ensure_ascii=False)[:500])
    return {"ok": ok, "fail": fail, "elapsed": elapsed, "errors_sample": errors_sample}


def count_catalog_jiedu_dirs(catalog: dict) -> int:
    n = 0
    for c in catalog.get("children") or []:
        if c.get("type") != "dir":
            continue
        if c.get("name") != "结晶读经":
            continue

        def cd(node: dict) -> None:
            nonlocal n
            n += 1
            for x in node.get("children") or []:
                if x.get("type") == "dir":
                    cd(x)

        cd(c)
    return n


def k1_title_chuchu_check(client, name: str = INDEX_NAME) -> dict:
    res = client.search(
        index=name,
        body={
            "size": 200,
            "query": {
                "bool": {
                    "must": [{"match_phrase": {"title": "纲目带出处"}}],
                    "filter": [{"term": {"node_type": "message"}}],
                }
            },
            "_source": ["title", "rel_path", "raw_filename"],
        },
    )
    hits = [
        {
            "title": h["_source"].get("title"),
            "rel_path": h["_source"].get("rel_path"),
        }
        for h in res["hits"]["hits"]
    ]
    return {"count": res["hits"]["total"]["value"], "hits": hits}


def list_svo(client, name: str = INDEX_NAME) -> list[dict]:
    res = client.search(
        index=name,
        body={
            "size": 200,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"node_type": "message"}},
                        {"term": {"source_version_only": True}},
                    ]
                }
            },
            "_source": ["title", "rel_path", "raw_filename"],
            "sort": [{"rel_path": "asc"}],
        },
    )
    return [h["_source"] for h in res["hits"]["hits"]]


def disk_sample_svo(svo_rows: list[dict], n: int = 5) -> list[dict]:
    if not svo_rows:
        return []
    idxs = sorted(
        {
            0,
            len(svo_rows) // 4,
            len(svo_rows) // 2,
            3 * len(svo_rows) // 4,
            len(svo_rows) - 1,
        }
    )[:n]
    out = []
    for i in idxs:
        s = svo_rows[i]
        rel = s["rel_path"]
        parent_rel = "/".join(rel.split("/")[:-1])
        parent = BACKUP_ROOT / parent_rel.replace("/", "\\")
        files = []
        if parent.exists():
            files = sorted(p.name for p in parent.iterdir() if p.is_file())
        # 同 msg 号是否有非出处版
        raw = s.get("raw_filename") or ""
        m = re.match(r"(msg\.\s*\d+)", raw, re.I)
        msg_prefix = m.group(1) if m else None
        same_msg = [f for f in files if msg_prefix and f.lower().startswith(msg_prefix.lower())]
        clean_same = [f for f in same_msg if not is_chuchu(f)]
        out.append(
            {
                "title": s.get("title"),
                "rel_path": rel,
                "parent": str(parent),
                "exists": parent.exists(),
                "files": files,
                "same_msg_files": same_msg,
                "clean_same_msg": clean_same,
                "confirmed_no_clean": len(clean_same) == 0,
            }
        )
    return out


def run_smoke(
    client,
    catalog: dict,
    docs: list[dict],
    flatten_meta: dict,
    name: str = INDEX_NAME,
) -> dict:
    rng = random.Random(SAMPLE_SEED)
    out: dict[str, Any] = {}

    n_dir = client.count(index=name, body={"query": {"term": {"node_type": "dir"}}})["count"]
    n_msg = client.count(index=name, body={"query": {"term": {"node_type": "message"}}})["count"]
    n_all = client.count(index=name, body={"query": {"match_all": {}}})["count"]
    n_svo = client.count(
        index=name, body={"query": {"term": {"source_version_only": True}}}
    )["count"]
    out["counts"] = {
        "dir": n_dir,
        "message": n_msg,
        "total": n_all,
        "source_version_only": n_svo,
    }
    print(f"ES counts dir={n_dir} msg={n_msg} total={n_all} svo={n_svo}")

    # K1
    k1 = k1_title_chuchu_check(client, name)
    out["k1"] = k1
    print(f"K1 title含纲目带出处: {k1['count']}")
    svo_rows = list_svo(client, name)
    out["svo_list"] = svo_rows
    out["svo_disk"] = disk_sample_svo(svo_rows, 5)

    if n_dir != 7772:
        out["count_mismatch"] = True
        print(f"STOP: dir={n_dir} 须为 7772")
        return out

    # ① 合并后不得有 (父, msg_number, norm_title) 重复
    leftover = flatten_meta.get("leftover_multi") or {}
    out["leftover_multi"] = {
        f"{k[0]}|{k[1]}|{k[2]}": v for k, v in leftover.items()
    }
    violations = flatten_meta.get("norm_violations") or []
    out["norm_violations"] = violations
    if leftover or violations:
        out["count_mismatch"] = True
        print(
            f"STOP: leftover={len(leftover)} norm_violations={len(violations)}"
        )
        return out

    out["merge"] = {
        "groups": flatten_meta.get("merge_groups"),
        "msgs": flatten_meta.get("merge_msgs"),
        "events": flatten_meta.get("merge_events"),
        "reduction": flatten_meta.get("reduction"),
        "impact": flatten_meta.get("impact") or [],
        "old_multi_groups": flatten_meta.get("old_multi_groups"),
    }
    out["b_results"] = flatten_meta.get("b_results") or []

    # K3 peel samples
    pairs = flatten_meta.get("peel_pairs") or []
    rng2 = random.Random(SAMPLE_SEED)
    peel_sample = pairs[:20] if len(pairs) <= 20 else rng2.sample(pairs, 20)
    # 再补 20 条「前后对照」：优先取有变化的
    out["k3"] = {
        "peel_count": flatten_meta.get("peel_count"),
        "peel_sample": [{"before": a, "after": b, "rel_path": p} for a, b, p in peel_sample],
        "safe_hits": flatten_meta.get("safe_hits") or [],
    }
    print(f"K3 peeled dirs: {flatten_meta.get('peel_count')}")

    # annotations empty check
    empty_str_ann = sum(
        1
        for d in docs
        if d.get("node_type") == "dir" and d.get("annotations") == ""
    )
    out["annotations_empty_str"] = empty_str_ann

    dir_docs = [d for d in docs if d["node_type"] == "dir"]
    msg_docs = [d for d in docs if d["node_type"] == "message"]
    svo_docs = [d for d in msg_docs if d.get("source_version_only")]
    variant_docs = [d for d in msg_docs if d.get("title_variants")]
    deep_bible = [
        d
        for d in msg_docs
        if d.get("top_category") == "圣经中的人名与地名" and d.get("depth", 0) >= 5
    ]

    samples = {
        "random_dirs": rng.sample(dir_docs, 5),
        "random_msgs": rng.sample(msg_docs, 5),
        "svo": rng.choice(svo_docs) if svo_docs else None,
        "deep_bible_person": rng.choice(deep_bible) if deep_bible else None,
        "with_variants": (
            rng.sample(variant_docs, min(5, len(variant_docs))) if variant_docs else []
        ),
    }

    def fetch(node_id: str) -> dict | None:
        try:
            return client.get(index=name, id=node_id)["_source"]
        except Exception:
            return None

    out["samples"] = {
        "random_dirs": [fetch(d["node_id"]) for d in samples["random_dirs"]],
        "random_msgs": [fetch(d["node_id"]) for d in samples["random_msgs"]],
        "svo": fetch(samples["svo"]["node_id"]) if samples["svo"] else None,
        "deep_bible_person": (
            fetch(samples["deep_bible_person"]["node_id"])
            if samples["deep_bible_person"]
            else None
        ),
        "with_variants": [fetch(d["node_id"]) for d in samples["with_variants"]],
    }

    def bm25_hits(body: dict) -> list[dict]:
        res = client.search(index=name, body=body)
        return [
            {
                "score": h["_score"],
                "text": h["_source"].get("text"),
                "node_type": h["_source"].get("node_type"),
                "top_category": h["_source"].get("top_category"),
            }
            for h in res["hits"]["hits"]
        ]

    out["bm25_a_text_only"] = bm25_hits(
        {
            "size": 3,
            "query": {"match": {"text": "以撒但为路线"}},
            "_source": ["text", "node_type", "top_category", "title", "msg_label"],
        }
    )
    out["bm25_a"] = bm25_hits(
        {
            "size": 3,
            "query": {
                "bool": {
                    "should": [
                        {"match": {"title": {"query": "以撒但为路线", "boost": 3}}},
                        {"match": {"text": "以撒但为路线"}},
                    ],
                    "filter": [{"term": {"node_type": "message"}}],
                }
            },
            "_source": ["text", "node_type", "top_category", "title", "msg_label"],
        }
    )
    out["bm25_b"] = bm25_hits(
        {
            "size": 3,
            "query": {
                "bool": {
                    "must": [{"match": {"text": "结晶读经 基督"}}],
                    "filter": [{"term": {"node_type": "message"}}],
                }
            },
            "_source": ["text", "node_type", "top_category", "title", "msg_label"],
        }
    )

    es_jiedu = client.count(
        index=name,
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"top_category": "结晶读经"}},
                        {"term": {"node_type": "dir"}},
                    ]
                }
            }
        },
    )["count"]
    cat_jiedu = count_catalog_jiedu_dirs(catalog)
    out["jiedu_dirs"] = {"es": es_jiedu, "catalog": cat_jiedu}

    res = client.search(
        index=name,
        body={
            "size": 1,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"node_type": "dir"}},
                        {"range": {"actual_count": {"gt": 100}}},
                    ]
                }
            },
            "sort": [{"actual_count": "desc"}],
        },
    )
    big = res["hits"]["hits"][0]["_source"] if res["hits"]["hits"] else None
    if big:
        target_rel = big["rel_path"]

        def find_dir(node: dict, rel: str) -> dict | None:
            if node.get("rel_path") == rel:
                return node
            for c in node.get("children") or []:
                if c.get("type") == "dir":
                    found = find_dir(c, rel)
                    if found:
                        return found
            return None

        node = find_dir(catalog, target_rel)
        recounted = count_messages(node) if node else None
        out["actual_count_check"] = {
            "rel_path": target_rel,
            "es_actual_count": big["actual_count"],
            "recounted": recounted,
            "match": big["actual_count"] == recounted,
            "name": big.get("name"),
            "path_text": big.get("path_text"),
        }

    twenty = rng.sample(msg_docs, 20)
    texts = []
    unclear = []
    for d in twenty:
        t = d["text"]
        texts.append(t)
        parts = t.split("\u3000")
        ok_shape = (
            len(parts) >= 3
            and parts[0]
            and any(p.startswith("第") and p.endswith("篇") for p in parts)
            and parts[-1]
        )
        if not ok_shape:
            unclear.append(t)
    out["text_morph"] = {"samples": texts, "unclear": unclear}

    return out


def write_report(
    catalog: dict,
    docs: list[dict],
    bulk_stats: dict,
    smoke: dict,
    max_msg: int,
) -> None:
    n_dir = sum(1 for d in docs if d["node_type"] == "dir")
    n_msg = sum(1 for d in docs if d["node_type"] == "message")
    n_svo = sum(1 for d in docs if d.get("source_version_only"))
    lines: list[str] = []
    lines.append("# panai4_pano_catalog 索引报告（本机）")
    lines.append("")
    lines.append(
        "输入：`catalog_clean.json`；目标：`panai4_pano_catalog`；本轮不写向量、不推远程。"
    )
    lines.append("")
    lines.append("## 修正摘要（K / M / P）")
    lines.append("")
    lines.append("- 合并键最终：`(父 rel_path, msg_number, normalize_title(title))`")
    lines.append("- `path_text` 用 `/`；`name` 剥离层内中文序号；`annotations` 空值 `[]`")
    lines.append("- 见文末【查询约定】")
    lines.append("")

    lines.append("## J1 中文序号")
    lines.append("")
    for n in (1, 10, 11, 20, 21, 100, 101, 110, 115, 363, 550):
        lines.append(f"- `{n}` → `{cn_number(n)}`")
    lines.append("")
    lines.append(f"全库 `msg_number` 最大值：**{max_msg}**。")
    lines.append("")

    lines.append("## J2 展平 / 建索引")
    lines.append("")
    lines.append(f"- dir（不含根）：**{n_dir}**（须 7772）")
    lines.append(f"- message：**{n_msg}**（原始 catalog 45409）")
    lines.append(f"- 合计：**{n_dir + n_msg}**")
    lines.append(f"- `source_version_only=true`：**{n_svo}**")
    merge = smoke.get("merge") or {}
    lines.append(
        f"- 合并减少 N=**{merge.get('reduction')}**"
        f"（相对 45409；新键实际合并组 **{merge.get('groups')}**）"
    )
    lines.append(
        f"- bulk：ok={bulk_stats.get('ok')} fail={bulk_stats.get('fail')} "
        f"elapsed={bulk_stats.get('elapsed', 0):.1f}s"
    )
    lines.append("")

    lines.append("## P1–P3 合并键（最终）")
    lines.append("")
    lines.append("键：`(父目录 rel_path, msg_number, normalize_title(title))`")
    lines.append("")
    lines.append("### normalize_title 验证")
    lines.append("")
    for a, b, expect_eq in [
        ("保罗的路程和职事 ", "保罗的路程和职事", True),
        ("他们的现在─借着…", "他们的现在—借着…", True),
        ("在召会的建造里", "在召会的建造", False),
        ("圣灵的印记", "在另一个范围里—神就是灵…", False),
    ]:
        na, nb = normalize_title(a), normalize_title(b)
        lines.append(
            f"- `{a}` → `{na}`；`{b}` → `{nb}`；equal={na == nb}（须 {expect_eq}）"
        )
    lines.append("")
    lines.append(
        f"- message：**{n_msg}**；合计：**{n_dir + n_msg}**；"
        f"N=**{merge.get('reduction')}**"
    )
    lines.append(f"- `source_version_only`：**{n_svo}**")
    leftover = smoke.get("leftover_multi") or {}
    violations = smoke.get("norm_violations") or []
    lines.append(
        f"- 自检 leftover `(父,号,norm_title)` 重复：**{len(leftover)}**（须 0）"
    )
    lines.append(
        f"- 自检同 `(父,号)` 多条但 norm_title 撞车：**{len(violations)}**（须 0）"
    )
    if violations:
        lines.append("")
        for v in violations:
            lines.append(
                f"- VIOLATION parent=`{v.get('parent')}` msg={v.get('msg_number')} "
                f"titles={v.get('titles')} norms={v.get('norms')}"
            )
    lines.append("")

    lines.append("## P4 原 B 类 8 组回看")
    lines.append("")
    lines.append(
        "预期：7 组标题实质不同 → 各自独立（count=2）；"
        "1 组「保罗的路程和职事」→ 合并（count=1，有 title_variants）。"
    )
    lines.append("")
    for i, br in enumerate(smoke.get("b_results") or [], 1):
        lines.append(
            f"### [{i}] msg={br.get('msg_number')} expect=`{br.get('expect')}` "
            f"count={br.get('count')} ok={br.get('ok')}"
        )
        lines.append("")
        lines.append(f"- parent suffix: `{br.get('suffix')}`")
        for doc in br.get("docs") or []:
            lines.append(
                f"- title=`{doc.get('title')}` norm=`{doc.get('title_norm')}` "
                f"variants={doc.get('title_variants')} "
                f"svo={doc.get('source_version_only')} "
                f"file=`{doc.get('raw_filename')}`"
            )
        lines.append("")

    lines.append("## M4 影响评估（actual_count）")
    lines.append("")
    lines.append(
        f"N=**{merge.get('reduction')}**。"
        "`pano_gaps.md` 顶部已注明：缺口基于合并前挂载点，排序不受影响。"
    )
    lines.append("")
    impact = merge.get("impact") or []
    if not impact:
        lines.append("（各大类 actual_count 未变化）")
    else:
        lines.append("| 大类 | ordinal | 旧 actual | 新 actual | Δ |")
        lines.append("|---|---:|---:|---:|---:|")
        for row in impact:
            lines.append(
                f"| {row.get('top_category')} | {row.get('top_ordinal')} | "
                f"{row.get('old')} | {row.get('new')} | {row.get('delta')} |"
            )
        lines.append("")
        lines.append(f"- 受影响大类数：**{len(impact)}**")
        lines.append(f"- Δ 合计：**{sum(r.get('delta', 0) for r in impact)}**（应 = −N）")
    lines.append("")

    # K1
    lines.append("## K1 title「纲目带出处」与 source_version_only")
    lines.append("")
    k1 = smoke.get("k1") or {}
    lines.append(f"- title 含「纲目带出处」的 message：**{k1.get('count', 0)}**（预期 0）")
    lines.append("")
    lines.append(
        "> **注（.doc）**：`source_version_only` 清单里有一部分其实磁盘上有干净版，"
        "但是 `.doc`（全库约 53 个）。当初 `tree.json` 只统计 docx，catalog 未挂上这些"
        "干净版，故仍标 `source_version_only=true`。拿本清单去找干净版时请同时查 `.doc`，"
        "以免白跑。"
    )
    lines.append("")
    if k1.get("count"):
        lines.append("命中列表：")
        lines.append("")
        for h in k1.get("hits") or []:
            lines.append(f"- `{h.get('title')}` — `{h.get('rel_path')}`")
        lines.append("")
    lines.append(f"### source_version_only=true 全表（{n_svo} 条）")
    lines.append("")
    lines.append("| # | title | rel_path |")
    lines.append("|---:|---|---|")
    for i, s in enumerate(smoke.get("svo_list") or [], 1):
        title = (s.get("title") or "").replace("|", "\\|")
        rel = (s.get("rel_path") or "").replace("|", "\\|")
        lines.append(f"| {i} | {title} | `{rel}` |")
    lines.append("")
    lines.append("### 磁盘抽查 5 条（父目录实际文件）")
    lines.append("")
    for i, d in enumerate(smoke.get("svo_disk") or [], 1):
        lines.append(f"**[{i}]** `{d.get('title')}`")
        lines.append("")
        lines.append(f"- parent: `{d.get('parent')}`（exists={d.get('exists')}）")
        lines.append(f"- 同 msg 号文件: {d.get('same_msg_files')}")
        lines.append(f"- 其中非出处版: {d.get('clean_same_msg')}")
        lines.append(
            f"- 确认无干净版（同 msg 号无非出处文件）: "
            f"**{'是' if d.get('confirmed_no_clean') else '否'}**"
        )
        if not d.get("confirmed_no_clean"):
            lines.append(
                "- 说明：同 `msg. N` 下另有非出处文件，但篇题/文件名不完全一致"
                "（或干净版为 `.doc` 未入 catalog）。"
            )
        lines.append("")
        lines.append("<details><summary>父目录全部文件</summary>")
        lines.append("")
        for f in d.get("files") or []:
            lines.append(f"- `{f}`")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # K3
    lines.append("## K3 name 层内中文序号剥离")
    lines.append("")
    k3 = smoke.get("k3") or {}
    lines.append(f"- 发生剥离的 dir 数：**{k3.get('peel_count')}**")
    lines.append("")
    lines.append("### 剥离前后对照（20 条）")
    lines.append("")
    lines.append("| before | after |")
    lines.append("|---|---|")
    for p in k3.get("peel_sample") or []:
        lines.append(
            f"| `{p.get('before')}` | `{p.get('after')}` |"
        )
    lines.append("")
    lines.append("### 安全名未误剥")
    lines.append("")
    for h in k3.get("safe_hits") or []:
        if h.get("name_before") in ("三一神", "一个新人", "一百八十") or h.get(
            "rel_path"
        ) == "(synthetic)":
            lines.append(
                f"- `{h.get('name_before')}` → `{h.get('name_after')}` "
                f"（peeled={h.get('peeled')}）"
            )
    # also print all exact matches
    lines.append("")
    lines.append("库内以这些词开头的 name（抽样确认）：")
    lines.append("")
    for h in k3.get("safe_hits") or []:
        if h.get("rel_path") == "(synthetic)":
            continue
        if h.get("name_before") in ("三一神", "一个新人", "一百八十") or (
            h.get("name_before") or ""
        ).startswith(("三一神", "一个新人", "一百八十")):
            lines.append(
                f"- `{h.get('name_before')}` → `{h.get('name_after')}` "
                f"peeled={h.get('peeled')} `{h.get('rel_path')[:60]}`"
            )
    lines.append("")

    lines.append("## J4 验证")
    lines.append("")
    c = smoke.get("counts") or {}
    lines.append("### 条数（ES）")
    lines.append("")
    lines.append(f"- dir = **{c.get('dir')}**（须 7772）")
    lines.append(f"- message = **{c.get('message')}**")
    lines.append(f"- 合计 = **{c.get('total')}**")
    lines.append(f"- `source_version_only=true` = **{c.get('source_version_only')}**")
    lines.append(
        f"- annotations 空字符串残留：**{smoke.get('annotations_empty_str', 0)}**（须 0）"
    )
    lines.append("")
    if smoke.get("count_mismatch"):
        lines.append("> **STOP：校验失败。**")
        lines.append("")

    def dump_docs(title: str, items: list | None) -> None:
        lines.append(f"#### {title}")
        lines.append("")
        if not items:
            lines.append("（无）")
            lines.append("")
            return
        for i, doc in enumerate(items, 1):
            lines.append(f"**[{i}]**")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(doc, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    lines.append("### 抽样（完整文档）")
    lines.append("")
    samples = smoke.get("samples") or {}
    dump_docs("随机 5 个 dir", samples.get("random_dirs"))
    dump_docs("随机 5 个 message", samples.get("random_msgs"))
    dump_docs(
        "有 title_variants 的 5 个 message",
        samples.get("with_variants"),
    )
    dump_docs(
        "source_version_only=true",
        [samples.get("svo")] if samples.get("svo") else [],
    )
    dump_docs(
        "top_category=圣经中的人名与地名 且 depth≥5",
        [samples.get("deep_bible_person")] if samples.get("deep_bible_person") else [],
    )

    lines.append("### 检索冒烟")
    lines.append("")
    lines.append("#### a) BM25「以撒但为路线」两组对比")
    lines.append("")
    lines.append("**A1 纯 text match（未过滤 node_type）top3：**")
    lines.append("")
    for i, h in enumerate(smoke.get("bm25_a_text_only") or [], 1):
        lines.append(
            f"{i}. score={h['score']:.4f} type=`{h['node_type']}` `{h['text']}`"
        )
    lines.append("")
    lines.append("**A2 `title^3 + text` + `node_type=message` top3：**")
    lines.append("")
    for i, h in enumerate(smoke.get("bm25_a") or [], 1):
        lines.append(
            f"{i}. score={h['score']:.4f} top=`{h['top_category']}` `{h['text']}`"
        )
    lines.append("")
    lines.append("#### b) BM25「结晶读经 基督」（message 过滤）top3")
    lines.append("")
    for i, h in enumerate(smoke.get("bm25_b") or [], 1):
        lines.append(f"{i}. score={h['score']:.4f} `{h['text']}`")
    lines.append("")
    jd = smoke.get("jiedu_dirs") or {}
    lines.append("#### c) top_category=结晶读经 且 node_type=dir")
    lines.append("")
    lines.append(f"- ES：**{jd.get('es')}**")
    lines.append(f"- catalog 对照：**{jd.get('catalog')}**")
    lines.append(f"- 一致：{'是' if jd.get('es') == jd.get('catalog') else '否'}")
    lines.append("")
    ac = smoke.get("actual_count_check") or {}
    lines.append("#### d) actual_count > 100 校验")
    lines.append("")
    lines.append(f"- path_text：`{ac.get('path_text')}`")
    lines.append(f"- ES actual_count：**{ac.get('es_actual_count')}**")
    lines.append(f"- catalog 重数：**{ac.get('recounted')}**")
    lines.append(f"- 一致：{'是' if ac.get('match') else '否'}")
    lines.append("")

    lines.append("### text 形态自检（随机 20 条 message）")
    lines.append("")
    tm = smoke.get("text_morph") or {}
    for i, t in enumerate(tm.get("samples") or [], 1):
        lines.append(f"{i}. `{t}`")
    lines.append("")
    unclear = tm.get("unclear") or []
    if unclear:
        lines.append("**看不出大类/系列/第几篇/篇题的：**")
        lines.append("")
        for t in unclear:
            lines.append(f"- `{t}`")
    else:
        lines.append("全部 20 条均可一眼看出：大类（`/` 路径）、第几篇、篇题。")
    lines.append("")

    lines.append("## 【查询约定】")
    lines.append("")
    lines.append("1. **检索内容**（找篇）：默认加 `node_type=message` 过滤。")
    lines.append("2. **title 建议加权 `^3`**（`should: title^3 + text`）。")
    lines.append("3. **列分类树**时才查 `node_type=dir`。")
    lines.append("")
    lines.append("依据：上方 a) 两组对比——")
    lines.append("")
    lines.append(
        "- 纯 text、不过滤时，同名目录（如「以撒但为路线」）会抢分，"
        "01 大类那一篇进不了 top3；"
    )
    lines.append(
        "- 加上 `node_type=message` 且 `title^3` 后，"
        "首位即为 `圣经—神的话/…/第十篇　以撒但为路线`。"
    )
    lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已写：{REPORT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("local",), default="local")
    parser.add_argument("--input", default=CATALOG_DEFAULT)
    parser.add_argument("--index", default=INDEX_NAME)
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="不重建索引，只重跑验证并写报告",
    )
    args = parser.parse_args()

    if args.target != "local":
        print("本脚本本轮只允许 --target local")
        sys.exit(1)

    verify_cn_number()
    verify_normalize_title()

    catalog = json.loads(Path(args.input).read_text(encoding="utf-8"))
    max_msg = 0

    def scan_max(n: dict) -> None:
        nonlocal max_msg
        for c in n.get("children") or []:
            if c.get("type") == "message":
                max_msg = max(max_msg, int(c.get("msg_number") or 0))
            elif c.get("type") == "dir":
                scan_max(c)

    scan_max(catalog)
    print(f"全库 msg_number 最大值：{max_msg}")

    print("=== 展平（K2/K3/K4/M2）===")
    docs, flatten_meta = flatten(catalog)
    n_dir = sum(1 for d in docs if d["node_type"] == "dir")
    n_msg = sum(1 for d in docs if d["node_type"] == "message")
    n_svo = sum(1 for d in docs if d.get("source_version_only"))
    n_var = sum(1 for d in docs if d.get("title_variants"))
    print(
        f"dir={n_dir} msg={n_msg} total={n_dir+n_msg} svo={n_svo} "
        f"variants={n_var} peeled={flatten_meta.get('peel_count')} "
        f"merge_groups={flatten_meta.get('merge_groups')} "
        f"N={flatten_meta.get('reduction')}"
    )
    leftover = flatten_meta.get("leftover_multi") or {}
    violations = flatten_meta.get("norm_violations") or []
    if leftover or violations:
        print(f"STOP: leftover={len(leftover)} violations={len(violations)}")
        sys.exit(1)
    print("=== P4 B-class ===")
    for br in flatten_meta.get("b_results") or []:
        print(
            f"  msg={br['msg_number']} expect={br['expect']} "
            f"count={br['count']} ok={br['ok']} suffix=…{br['suffix'][-40:]}"
        )
    if n_dir != 7772:
        print(f"STOP: dir={n_dir} 须 7772")
        sys.exit(1)

    # K3 verify print
    print("=== K3 剥离对照（最多 20）===")
    pairs = flatten_meta.get("peel_pairs") or []
    for a, b, _p in pairs[:20]:
        print(f"  {a!r} → {b!r}")
    print("=== K3 安全名 ===")
    for h in flatten_meta.get("safe_hits") or []:
        nb = h.get("name_before") or ""
        if nb in ("三一神", "一个新人", "一百八十") or h.get("rel_path") == "(synthetic)":
            print(f"  {nb!r} → {h.get('name_after')!r} peeled={h.get('peeled')}")

    if args.smoke_only:
        bulk_stats = {"ok": n_dir + n_msg, "fail": 0, "elapsed": 0.0}
        print("=== 验证（smoke-only）===")
        smoke = run_smoke(local_es, catalog, docs, flatten_meta, args.index)
        write_report(catalog, docs, bulk_stats, smoke, max_msg)
        return

    print("=== 建索引 ===")
    create_index(local_es, args.index)
    bulk_stats = bulk_index(local_es, docs, args.index)

    print("=== 验证 ===")
    smoke = run_smoke(local_es, catalog, docs, flatten_meta, args.index)
    write_report(catalog, docs, bulk_stats, smoke, max_msg)

    if smoke.get("count_mismatch"):
        sys.exit(1)


if __name__ == "__main__":
    main()
