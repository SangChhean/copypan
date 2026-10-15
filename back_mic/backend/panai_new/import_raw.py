# -*- coding: utf-8 -*-
"""把「结晶读经新加Json资料」里的五份 Json 原样导入 Elasticsearch 新索引。

原则：
- 只写以 panai_new_ 开头的索引，绝不碰其他索引（脚本里有前缀保护）。
- 原样导入：不切块、不向量化、不挂标注、不做词条匹配。保留原始字段，以后要切块、
  挂词条、做标注，都可以从这些已导入的数据直接做。
- 可重复运行：每个文档用固定的 _id，重复导入只是覆盖，不会重复。

用法（在 back_mic/backend 下）：
    python -m panai_new.import_raw --dry-run     只读 Json、打印将要导入的数量，不连接写入
    python -m panai_new.import_raw                正式导入
    python -m panai_new.import_raw --recreate     先删除并重建这些 panai_new_ 索引再导入
    python -m panai_new.import_raw --only panai_new_pano_catalog   只处理指定的索引
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PREFIX = "panai_new_"
# 资料已挪到仓库外（避免提交时一起上传）；可用环境变量 PANAI_NEW_DATA_DIR 改位置
DATA_DIR = Path(os.environ.get("PANAI_NEW_DATA_DIR") or "A:/PanAI新测试台资料/结晶读经新加Json资料")

F_CATEGORY = "2373词条内在意义分类-完整资料.json"
F_MUTUAL = "彼此互相词条分类-完整资料.json"
F_SHENGJI = "生机进展的关联（词条及其标注）完整资料.json"
F_HISTORY = "从历史进展的差异看高峰时期的内涵（词条及其标注）完整资料.json"
F_DISPUTE = "神圣的辩理（词条及其标注）完整资料.json"
F_PANO = "上河图目录catalog_clean.json"

IDX_CATEGORY = PREFIX + "term_category"
IDX_MUTUAL = PREFIX + "mutual"
IDX_SHENGJI = PREFIX + "shengji"
IDX_HISTORY = PREFIX + "history"
IDX_DISPUTE = PREFIX + "dispute"
IDX_PANO = PREFIX + "pano_catalog"
ALL_INDICES = [IDX_CATEGORY, IDX_MUTUAL, IDX_SHENGJI, IDX_HISTORY, IDX_DISPUTE, IDX_PANO]

_IK_TEXT = {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"}
_KW = {"type": "keyword"}
_NAME = {"type": "keyword", "fields": {"text": _IK_TEXT}}

SETTINGS = {"number_of_shards": 1, "number_of_replicas": 0}

MAPPINGS = {
    IDX_CATEGORY: {
        "properties": {
            "doc_type": _KW,            # word=词条 / category_def=分类定义
            "term_no": {"type": "integer"},
            "name": _NAME,
            "category": _KW,
            "definition": _IK_TEXT,
            "count": {"type": "integer"},
            "ratio": _KW,
            "source_file": _KW,
        }
    },
    IDX_MUTUAL: {
        "properties": {
            "doc_type": _KW,            # word=词条 / tag=标签（含定义和说明）
            "term_no": {"type": "integer"},
            "name": _NAME,
            "phrasing": _KW,
            "tag": _KW,
            "definition": _IK_TEXT,
            "note": _IK_TEXT,
            "count": {"type": "integer"},
            "source_file": _KW,
        }
    },
}
_ENTRY_PROPS = {
    "name": _NAME,                      # 词条名（原样）
    "series": _KW,
    "stage_no": {"type": "integer"},
    "stage_name": _KW,
    "entry_idx": {"type": "integer"},   # 该词条该阶段里的第几条
    "title": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart", "fields": {"raw": _KW}},
    "book": _KW,
    "date": _KW,
    "source": _KW,
    "description": _IK_TEXT,
    "outline": _IK_TEXT,                # 纲目全文（原样，不切块）
    "outline_len": {"type": "integer"},
    "source_file": _KW,
}
for _i in (IDX_SHENGJI, IDX_HISTORY, IDX_DISPUTE):
    MAPPINGS[_i] = {"properties": dict(_ENTRY_PROPS)}

# 上河图目录：一个节点（目录或篇）一个文档，原样保留路径、层级、篇号、篇题
MAPPINGS[IDX_PANO] = {
    "properties": {
        "node_id": _KW,
        "parent_id": _KW,
        "node_type": _KW,               # dir=目录 / message=篇
        "depth": {"type": "integer"},
        "name": _NAME,                  # 目录名（篇节点留空）
        "raw_name": _KW,
        "ordinal_raw": _KW,
        "ordinal_num": {"type": "integer"},
        "declared_count": {"type": "integer"},
        "count_unit": _KW,
        "annotations": _KW,             # 目录上的标注（如“1996年12月，安那翰”）
        "rel_path": {"type": "keyword", "fields": {"text": _IK_TEXT}},
        "path_names": _KW,              # 从根到本节点的名字数组
        "path_text": _IK_TEXT,          # 路径拼成一串，用于关键词检索
        "role": {"properties": {"has_subdir": {"type": "boolean"}, "has_docx": {"type": "boolean"}, "has_declared_count": {"type": "boolean"}}},
        "child_count": {"type": "integer"},
        "msg_number": {"type": "integer"},
        "title": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart", "fields": {"raw": _KW}},
        "has_source_version": {"type": "boolean"},
        "raw_filenames": _KW,
        "ext": _KW,
        "source_file": _KW,
    }
}


def _load(name: str):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def docs_category():
    d = _load(F_CATEGORY)
    for c in d["categories"]:
        yield f"category_def:{c['name']}", {
            "doc_type": "category_def", "name": c["name"], "category": c["name"],
            "definition": c.get("definition", ""), "count": c.get("count"), "ratio": c.get("ratio"),
            "source_file": F_CATEGORY,
        }
    for w in d["words"]:
        yield f"word:{w['no']}", {
            "doc_type": "word", "term_no": w["no"], "name": str(w["name"]).strip(),
            "category": w.get("category"), "source_file": F_CATEGORY,
        }


def docs_mutual():
    d = _load(F_MUTUAL)
    yield "tag:" + str(d.get("tag", "")), {
        "doc_type": "tag", "tag": d.get("tag"), "definition": d.get("definition", ""),
        "note": d.get("note", ""), "count": d.get("count"), "source_file": F_MUTUAL,
    }
    for w in d["words"]:
        yield f"word:{w['no']}", {
            "doc_type": "word", "term_no": w["no"], "name": str(w["name"]).strip(),
            "phrasing": w.get("phrasing"), "source_file": F_MUTUAL,
        }


def _entries_staged(fname: str):
    """生机进展 / 历史进展差异：每个词条 6 个阶段，每个阶段若干条目。"""
    for e in _load(fname):
        stages = e.get("stages") or {}
        for key, val in e.items():
            if not key.startswith("content_"):
                continue
            try:
                stage_no = int(key.split("_")[1])
            except ValueError:
                continue
            for idx, it in enumerate(val or []):
                if not isinstance(it, dict):
                    continue
                outline = str(it.get("outline") or "")
                yield f"{e['name']}|{stage_no}|{idx}", {
                    "name": str(e["name"]).strip(), "series": e.get("series"),
                    "stage_no": stage_no, "stage_name": stages.get(key), "entry_idx": idx,
                    "title": it.get("title"), "book": it.get("book"), "date": it.get("date"),
                    "source": it.get("source"), "outline": outline, "outline_len": len(outline),
                    "source_file": fname,
                }


def docs_shengji():
    return _entries_staged(F_SHENGJI)


def docs_history():
    return _entries_staged(F_HISTORY)


def docs_dispute():
    for e in _load(F_DISPUTE):
        for key, val in e.items():
            if not key.startswith("content_"):
                continue
            for idx, it in enumerate(val or []):
                if not isinstance(it, dict):
                    continue
                outline = str(it.get("outline") or "")
                yield f"{e['name']}|{key}|{idx}", {
                    "name": str(e["name"]).strip(), "entry_idx": idx,
                    "title": it.get("title"), "description": it.get("description"),
                    "outline": outline, "outline_len": len(outline), "source_file": F_DISPUTE,
                }


def docs_pano():
    import hashlib

    def h(x: str) -> str:
        return hashlib.sha1(x.encode("utf-8")).hexdigest()[:16]

    root = _load(F_PANO)
    seen: dict[str, int] = {}

    def uniq(base: str) -> str:
        n = seen.get(base, 0)
        seen[base] = n + 1
        return base if n == 0 else f"{base}#{n}"

    # 深度优先，保持原有顺序
    stack = [(root, None, [])]
    while stack:
        node, parent_id, ancestors = stack.pop()
        if node.get("type") == "dir":
            rel = node.get("rel_path") or ""
            nid = uniq("d:" + h("dir|" + rel))
            names = ancestors + [str(node.get("name"))]
            children = node.get("children") or []
            role = node.get("role") or {}
            yield nid, {
                "node_id": nid, "parent_id": parent_id, "node_type": "dir", "depth": node.get("depth"),
                "name": node.get("name"), "raw_name": node.get("raw_name"), "ordinal_raw": node.get("ordinal_raw"),
                "ordinal_num": node.get("ordinal_num"), "declared_count": node.get("declared_count"),
                "count_unit": node.get("count_unit"), "annotations": node.get("annotations") or [],
                "rel_path": rel, "path_names": names, "path_text": " / ".join(names),
                "role": {k: bool(v) for k, v in role.items()}, "child_count": len(children), "source_file": F_PANO,
            }
            for c in reversed(children):
                stack.append((c, nid, names))
        else:
            title = str(node.get("title") or "")
            nid = uniq("m:" + h(f"msg|{parent_id}|{node.get('msg_number')}|{title}"))
            names = ancestors + [title]
            yield nid, {
                "node_id": nid, "parent_id": parent_id, "node_type": "message", "depth": len(ancestors),
                "rel_path": "/".join(ancestors[1:]) if len(ancestors) > 1 else "", "path_names": names,
                "path_text": " / ".join(names), "msg_number": node.get("msg_number"), "title": title,
                "has_source_version": node.get("has_source_version"), "raw_filenames": node.get("raw_filenames") or [],
                "ext": node.get("ext"), "source_file": F_PANO,
            }


SOURCES = [
    (IDX_CATEGORY, docs_category),
    (IDX_MUTUAL, docs_mutual),
    (IDX_SHENGJI, docs_shengji),
    (IDX_HISTORY, docs_history),
    (IDX_DISPUTE, docs_dispute),
    (IDX_PANO, docs_pano),
]


def _es():
    from dotenv import load_dotenv
    from elasticsearch import Elasticsearch

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    return Elasticsearch(
        f"http://{os.environ['ES_HOST']}:{os.environ['ES_PORT']}",
        basic_auth=(os.environ.get("ES_USERNAME"), os.environ.get("ES_PASSWORD")),
        request_timeout=120,
    )


def _guard(index: str) -> None:
    if not index.startswith(PREFIX):
        raise SystemExit(f"拒绝操作非 {PREFIX} 前缀的索引：{index}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--recreate", action="store_true")
    ap.add_argument("--only", nargs="*", help="只处理指定的索引名（如 panai_new_pano_catalog），不写则处理全部")
    args = ap.parse_args()
    sources = [(i, g) for i, g in SOURCES if not args.only or i in args.only]

    if args.dry_run:
        print("【演算】只读 Json，不连接 ES，不写入")
        for index, gen in sources:
            n = sum(1 for _ in gen())
            ids = [i for i, _ in gen()]
            dup = len(ids) - len(set(ids))
            print(f"  {index:28s} 将导入 {n:6d} 个文档 | 重复的 _id: {dup}")
        return

    from elasticsearch import helpers

    es = _es()
    for index, gen in sources:
        _guard(index)
        if args.recreate and es.indices.exists(index=index):
            es.indices.delete(index=index)
            print(f"已删除并重建：{index}")
        if not es.indices.exists(index=index):
            es.indices.create(index=index, settings=SETTINGS, mappings=MAPPINGS[index])
            print(f"已创建索引：{index}")
        actions = ({"_op_type": "index", "_index": index, "_id": _id, "_source": src} for _id, src in gen())
        ok, errors = helpers.bulk(es, actions, chunk_size=200, request_timeout=180, raise_on_error=False, stats_only=False)
        es.indices.refresh(index=index)
        cnt = es.count(index=index)["count"]
        print(f"{index:28s} 写入成功 {ok} | 失败 {len(errors) if isinstance(errors, list) else errors} | 索引内文档数 {cnt}")
        if errors:
            print("  失败样例：", str(errors[:2])[:300])


if __name__ == "__main__":
    main()
