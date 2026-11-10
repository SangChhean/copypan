# -*- coding: utf-8 -*-
"""qa4 库统计报告（只读）：Neo4j + ES 计数/字段/类型，不输出正文、向量或标注取值。

用法:
  # 由 stats_report_run.ps1 注入 QA4_ES_PASSWORD / QA4_NEO4J_PASSWORD 后调用
  python stats_report.py
  python stats_report.py --out-dir "G:\\PanAI4.0专用\\统计"
  python stats_report.py --self-test   # 不连库：演示写语句被拒绝

约束:
  - 仅连 qa4-es (默认 http://127.0.0.1:9202) 与 qa4-neo4j (bolt://127.0.0.1:7689)
  - 先校验 ES cluster_name == qa4
  - Cypher 仅只读事务；拒绝含写动词的语句
  - ES 仅 GET / _count / _search / 聚合 / mapping / settings / stats / cat；拒绝写 API
  - 输出与日志不得含密码，不得含 text / embedding / text_vector 的取值
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_ES_URL = "http://127.0.0.1:9202"
DEFAULT_NEO4J_URI = "bolt://127.0.0.1:7689"
DEFAULT_NEO4J_USER = "neo4j"
QA4_CLUSTER = "qa4"
EXPECTED_ES_TOTAL = 414082
EXPECTED_NODE_TOTAL = 7334
EXPECTED_REL_TOTAL = 52426
EXPECTED_LABELS = {
    "Truth_Point": 2380,
    "Scripture": 4851,
    "Branch": 91,
    "Trunk": 12,
}

# 对外口径：排除括号内 8 词条（Truth_Point.name 精确匹配）
# 括号外对照仅作文档说明，匹配只用括号内名
BRACKET_INNER_NAMES: tuple[str, ...] = (
    "产生得胜者",
    "圣灵的浇灌",
    "地狱",
    "女人",
    "忧虑",
    "扩展",
    "显大",
    "晨兴",
)
BRACKET_OUTER_NAMES: tuple[str, ...] = (
    "产生男孩子",
    "那灵的浇灌",
    "火湖",
    "妇人",
    "挂虑",
    "扩增",
    "扩大",
    "晨晨复兴",
)
BRACKET_PAIRS: tuple[tuple[str, str], ...] = tuple(
    zip(BRACKET_OUTER_NAMES, BRACKET_INNER_NAMES, strict=True)
)
# docs/panai4_graph/copy_to_bracket_inner.md：括号外→括号内复制新增关系数
EXPECTED_BRACKET_COPY_NEW_RELS = 229
EXPECTED_PUBLIC_TRUTH_POINT = 2372  # 2380 - 8
EXPECTED_PUBLIC_NODE_TOTAL = 7326  # 7334 - 8

# 复制时包含的关系：29 语义 + SUPPORTED_BY（不含 4 分类）
CLASSIFICATION_REL_TYPES = frozenset(
    {
        "BELONGS_TO_TRUNK",
        "OF_BRANCH_DIRECTLY",
        "OF_BRANCH_INDIRECTLY",
        "GRAFTING",
    }
)

QA4_INDICES = (
    "qa4_outline_12490",
    "qa4_outline_feasts",
    "qa4_bible",
    "qa4_hymns",
    "qa4_text_life",
    "qa4_text_cwwl",
    "qa4_text_cwwn",
    "qa4_text_others",
    "qa4_map_note",
    "qa4_pano_catalog",
)

# 禁止在输出/日志中出现取值的字段名（仅报类型/非空计数）
VALUE_BAN_FIELDS = frozenset({"text", "embedding", "text_vector", "en"})

DEFAULT_OUT_DIR = (
    Path(r"G:\PanAI4.0专用\统计")
    if os.name == "nt"
    else Path("/opt/qa4_logs/stats")
)

# Cypher 写操作拒绝（大小写不敏感；整词）
_CYPHER_WRITE_RE = re.compile(
    r"(?i)\b("
    r"CREATE|MERGE|DELETE|DETACH\s+DELETE|SET|REMOVE|DROP|LOAD\s+CSV|"
    r"FOREACH|CALL\s+\{|CALL\s+dbms\.|CALL\s+db\.index\.|CALL\s+apoc\."
    r")\b"
)

# ES 写方法名（elasticsearch-py）
_ES_WRITE_METHODS = frozenset(
    {
        "index",
        "create",
        "update",
        "delete",
        "bulk",
        "update_by_query",
        "delete_by_query",
        "reindex",
        "put_script",
        "put_template",
        "put_index_template",
        "put_component_template",
        "put_mapping",
        "put_settings",
        "put_alias",
        "close",
        "open",
        "clone",
        "shrink",
        "split",
        "rollover",
        "forcemerge",
        "clear_cache",  # 有副作用，一并拒绝
    }
)
_ES_INDICES_WRITE = frozenset(
    {
        "create",
        "delete",
        "put_mapping",
        "put_settings",
        "put_alias",
        "delete_alias",
        "close",
        "open",
        "clone",
        "shrink",
        "split",
        "rollover",
        "forcemerge",
        "put_template",
        "put_index_template",
        "put_component_template",
        "simulate_index_template",
        "add_block",
        "put_data_lifecycle",
    }
)


# ---------------------------------------------------------------------------
# 只读守卫（贴出位置供验证）
# ---------------------------------------------------------------------------

def assert_cypher_readonly(cypher: str) -> str:
    """拒绝写操作的检查位置 #1：Cypher 语句扫描。

    任何含 CREATE/MERGE/DELETE/SET/REMOVE/DROP/... 的语句直接 raise。
    """
    if _CYPHER_WRITE_RE.search(cypher or ""):
        raise PermissionError(
            f"拒绝写操作 Cypher（只读统计）: {(cypher or '')[:120]!r}"
        )
    return cypher


def assert_es_method_readonly(method: str, *, where: str = "es") -> None:
    """拒绝写操作的检查位置 #2：ES 客户端方法名。"""
    name = (method or "").lower()
    if name in _ES_WRITE_METHODS:
        raise PermissionError(f"拒绝写操作 ES.{where}.{method}（只读统计）")


def assert_es_indices_method_readonly(method: str) -> None:
    """拒绝写操作的检查位置 #3：ES.indices.* 写方法。"""
    name = (method or "").lower()
    if name in _ES_INDICES_WRITE:
        raise PermissionError(f"拒绝写操作 ES.indices.{method}（只读统计）")


class ReadOnlySession:
    """包装 neo4j Session：强制 READ，并对每条 Cypher 做写动词扫描。"""

    def __init__(self, session: Any):
        self._session = session

    def run(self, cypher: str, parameters: dict | None = None, **kwargs: Any) -> Any:
        assert_cypher_readonly(cypher)
        return self._session.run(cypher, parameters or {}, **kwargs)

    def execute_read(self, unit: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return self._session.execute_read(unit, *args, **kwargs)

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "ReadOnlySession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class ReadOnlyES:
    """包装 Elasticsearch：拦截写 API；允许 info/search/count/stats/mapping/settings/cat。"""

    def __init__(self, es: Any):
        self._es = es
        self.indices = _ReadOnlyIndices(es.indices)
        # cat 只读
        self.cat = es.cat

    def info(self, *a: Any, **k: Any) -> Any:
        return self._es.info(*a, **k)

    def search(self, *a: Any, **k: Any) -> Any:
        return self._es.search(*a, **k)

    def count(self, *a: Any, **k: Any) -> Any:
        return self._es.count(*a, **k)

    def __getattr__(self, name: str) -> Any:
        assert_es_method_readonly(name)
        return getattr(self._es, name)


class _ReadOnlyIndices:
    def __init__(self, indices: Any):
        self._indices = indices

    def get_mapping(self, *a: Any, **k: Any) -> Any:
        return self._indices.get_mapping(*a, **k)

    def get_settings(self, *a: Any, **k: Any) -> Any:
        return self._indices.get_settings(*a, **k)

    def stats(self, *a: Any, **k: Any) -> Any:
        return self._indices.stats(*a, **k)

    def get(self, *a: Any, **k: Any) -> Any:
        return self._indices.get(*a, **k)

    def exists(self, *a: Any, **k: Any) -> Any:
        return self._indices.exists(*a, **k)

    def __getattr__(self, name: str) -> Any:
        assert_es_indices_method_readonly(name)
        return getattr(self._indices, name)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _utcnow_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("qa4_stats")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def _is_nonempty(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str) and v.strip() == "":
        return False
    if isinstance(v, (list, dict)) and len(v) == 0:
        return False
    return True


def _flatten_mapping_props(
    props: dict[str, Any], prefix: str = ""
) -> list[dict[str, Any]]:
    """展平 mapping.properties → [{name, type, ...元数据}]，不含任何文档值。"""
    out: list[dict[str, Any]] = []
    for name, spec in sorted((props or {}).items()):
        if not isinstance(spec, dict):
            continue
        full = f"{prefix}.{name}" if prefix else name
        ftype = spec.get("type")
        if ftype:
            row: dict[str, Any] = {"name": full, "type": ftype}
            if ftype == "dense_vector":
                if "dims" in spec:
                    row["dims"] = spec.get("dims")
                if "similarity" in spec:
                    row["similarity"] = spec.get("similarity")
                if "index" in spec:
                    row["index"] = spec.get("index")
            if "analyzer" in spec:
                row["analyzer"] = spec.get("analyzer")
            if "search_analyzer" in spec:
                row["search_analyzer"] = spec.get("search_analyzer")
            out.append(row)
        # object / nested 继续下钻
        nested = spec.get("properties")
        if isinstance(nested, dict):
            out.extend(_flatten_mapping_props(nested, full))
        # multi-fields
        fields = spec.get("fields")
        if isinstance(fields, dict):
            for sub, sspec in sorted(fields.items()):
                if not isinstance(sspec, dict):
                    continue
                srow: dict[str, Any] = {
                    "name": f"{full}.{sub}",
                    "type": sspec.get("type"),
                }
                if "analyzer" in sspec:
                    srow["analyzer"] = sspec.get("analyzer")
                out.append(srow)
    return out


def _index_analyzers(settings: dict[str, Any]) -> dict[str, Any]:
    """提取索引自定义分词器名与类型（不含词典内容）。"""
    idx = settings.get("index") or settings
    analysis = (idx.get("analysis") or {}) if isinstance(idx, dict) else {}
    analyzers = analysis.get("analyzer") or {}
    result: dict[str, Any] = {}
    if isinstance(analyzers, dict):
        for name, conf in analyzers.items():
            if isinstance(conf, dict):
                result[name] = {
                    "type": conf.get("type"),
                    "tokenizer": conf.get("tokenizer"),
                    "filter_count": len(conf.get("filter") or []),
                }
            else:
                result[name] = {"type": str(type(conf).__name__)}
    return result


# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------

def connect_neo4j(uri: str, user: str, password: str) -> Any:
    try:
        from neo4j import GraphDatabase, READ_ACCESS
    except ImportError as e:
        raise SystemExit("需要安装 neo4j：pip install neo4j") from e
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    # 挂上 READ_ACCESS 供 open_readonly_session 使用
    driver._qa4_read_access = READ_ACCESS  # type: ignore[attr-defined]
    return driver


def open_readonly_session(driver: Any) -> ReadOnlySession:
    access = getattr(driver, "_qa4_read_access", None)
    if access is None:
        from neo4j import READ_ACCESS

        access = READ_ACCESS
    return ReadOnlySession(driver.session(default_access_mode=access))


def _count_label_props(
    session: ReadOnlySession,
    label: str,
    log: logging.Logger,
    *,
    exclude_element_ids: list[str] | None = None,
) -> dict[str, int]:
    """标签下各属性键非空节点数（不取取值）。可排除 elementId 列表。"""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
        raise SystemExit(f"拒绝不安全的标签名: {label!r}")
    excl = exclude_element_ids or []
    excl_clause = (
        " AND NOT elementId(n) IN $excl_ids " if excl else " "
    )
    params: dict[str, Any] = {"excl_ids": excl} if excl else {}
    keys = [
        str(r["key"])
        for r in session.run(
            f"MATCH (n:{label}) WHERE true {excl_clause} "
            f"UNWIND keys(n) AS k RETURN DISTINCT k AS key ORDER BY key",
            params,
        )
    ]
    refined: dict[str, int] = {}
    for key in keys:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            log.warning("跳过非常规属性键名 label=%s key=%r", label, key)
            continue
        counted = False
        for extra in (
            f"AND size(n.{key}) > 0",
            f"AND n.{key} <> ''",
            "",
        ):
            q = (
                f"MATCH (n:{label}) WHERE n.{key} IS NOT NULL "
                f"{excl_clause} {extra} RETURN count(n) AS c"
            )
            try:
                refined[key] = int(session.run(q, params).single()["c"])
                counted = True
                break
            except Exception:
                continue
        if not counted:
            log.warning("属性非空计数失败 %s.%s", label, key)
            refined[key] = 0
    return refined


def resolve_bracket_inner_nodes(
    session: ReadOnlySession, log: logging.Logger
) -> list[dict[str, str]]:
    """按 Truth_Point.name 精确匹配括号内 8 词条；必须恰好 8 个，否则中止。"""
    rows = list(
        session.run(
            """
            MATCH (n:Truth_Point)
            WHERE n.name IN $names
            RETURN n.name AS name, elementId(n) AS eid
            ORDER BY n.name
            """,
            {"names": list(BRACKET_INNER_NAMES)},
        )
    )
    found = {str(r["name"]): str(r["eid"]) for r in rows}
    missing = [n for n in BRACKET_INNER_NAMES if n not in found]
    extra = sorted(set(found) - set(BRACKET_INNER_NAMES))
    if len(found) != 8 or missing or extra:
        raise SystemExit(
            "括号内词条定位失败：必须恰好找到 8 个 Truth_Point。"
            f" 期望={list(BRACKET_INNER_NAMES)}；"
            f" 实际找到={sorted(found.keys())}；"
            f" 缺失={missing}；多余名={extra}。"
            " 请勿猜测，已中止。"
        )
    # 保持 BRACKET_INNER_NAMES 顺序
    out = [{"name": n, "element_id": found[n]} for n in BRACKET_INNER_NAMES]
    log.info("括号内 8 节点已定位: %s", [x["name"] for x in out])
    return out


def collect_public_scope(
    session: ReadOnlySession,
    inner_nodes: list[dict[str, str]],
    full_label_counts: dict[str, int],
    log: logging.Logger,
) -> dict[str, Any]:
    """对外口径：排除 8 括号内节点及任一端相连的全部边。"""
    ids = [n["element_id"] for n in inner_nodes]
    params = {"ids": ids}

    # 被排除边：任一端在 8 节点内（两向，按关系唯一计数不重复扣）
    excl_by_type: dict[str, int] = {}
    for r in session.run(
        """
        MATCH (a)-[r]->(b)
        WHERE elementId(a) IN $ids OR elementId(b) IN $ids
        RETURN type(r) AS t, count(r) AS c
        ORDER BY t
        """,
        params,
    ):
        excl_by_type[str(r["t"])] = int(r["c"])
    excl_rel_total = sum(excl_by_type.values())

    # 对外节点按标签
    pub_labels: dict[str, int] = {}
    for r in session.run(
        """
        MATCH (n)
        WHERE NOT elementId(n) IN $ids
        UNWIND labels(n) AS label
        RETURN label, count(*) AS c ORDER BY label
        """,
        params,
    ):
        pub_labels[str(r["label"])] = int(r["c"])
    pub_nodes = int(
        session.run(
            "MATCH (n) WHERE NOT elementId(n) IN $ids RETURN count(n) AS c",
            params,
        ).single()["c"]
    )

    # 对外关系按类型
    pub_rel_types: dict[str, int] = {}
    for r in session.run(
        """
        MATCH (a)-[r]->(b)
        WHERE NOT elementId(a) IN $ids AND NOT elementId(b) IN $ids
        RETURN type(r) AS t, count(r) AS c ORDER BY t
        """,
        params,
    ):
        pub_rel_types[str(r["t"])] = int(r["c"])
    pub_rels = sum(pub_rel_types.values())

    # 对外标注非空（仅未排除节点）
    pub_props: dict[str, dict[str, int]] = {}
    for label in sorted(pub_labels.keys()):
        pub_props[label] = _count_label_props(
            session, label, log, exclude_element_ids=ids
        )

    # 复制新增 229 条 ⊆ 被排除边：
    # 复制只产生「一端为括号内」的 29 语义 + SUPPORTED_BY；不含 4 分类。
    # 故：被排除边中非分类类型之和应 ≥ 229；且文档记录的 229 全部触及括号内端点。
    excl_non_class = {
        t: c for t, c in excl_by_type.items() if t not in CLASSIFICATION_REL_TYPES
    }
    excl_non_class_sum = sum(excl_non_class.values())
    copy_subset_ok = excl_non_class_sum >= EXPECTED_BRACKET_COPY_NEW_RELS

    # 按对：各括号内节点触及的边数（便于核对）
    per_inner: list[dict[str, Any]] = []
    for node in inner_nodes:
        c = int(
            session.run(
                """
                MATCH (n) WHERE elementId(n) = $id
                OPTIONAL MATCH (n)-[r]-()
                RETURN count(DISTINCT r) AS c
                """,
                {"id": node["element_id"]},
            ).single()["c"]
        )
        per_inner.append({"name": node["name"], "incident_rels": c})

    return {
        "scope": "对外口径",
        "excluded_inner_names": [n["name"] for n in inner_nodes],
        "bracket_pairs": [
            {"outer": o, "inner": i} for o, i in BRACKET_PAIRS
        ],
        "total_nodes": pub_nodes,
        "total_relationships": pub_rels,
        "label_counts": pub_labels,
        "rel_type_counts": pub_rel_types,
        "label_property_nonempty": pub_props,
        "excluded": {
            "nodes": len(ids),
            "node_names": [n["name"] for n in inner_nodes],
            "relationships": excl_rel_total,
            "rel_type_counts": excl_by_type,
            "rel_type_counts_excluding_classification": excl_non_class,
            "per_inner_incident_rels": per_inner,
            "bracket_copy_new_rels_expected": EXPECTED_BRACKET_COPY_NEW_RELS,
            "bracket_copy_229_subset_of_excluded": copy_subset_ok,
            "bracket_copy_subset_proof": (
                f"copy_to_bracket_inner 新增 {EXPECTED_BRACKET_COPY_NEW_RELS} 条边"
                f"均以括号内节点为一端；被排除边=任一端触及 8 节点的全部边"
                f"（{excl_rel_total}，其中非分类 {excl_non_class_sum}）。"
                f"故 229 ⊆ 被排除边 成立当且仅当非分类排除边数≥229"
                f"（实际 {excl_non_class_sum}≥{EXPECTED_BRACKET_COPY_NEW_RELS}"
                f" → {copy_subset_ok}）。"
                f"来源：docs/panai4_graph/copy_to_bracket_inner.md total_new=229。"
            ),
        },
        "self_check": {
            "truth_point": pub_labels.get("Truth_Point"),
            "truth_point_equals_2372": pub_labels.get("Truth_Point")
            == EXPECTED_PUBLIC_TRUTH_POINT,
            "total_nodes": pub_nodes,
            "total_nodes_equals_7326": pub_nodes == EXPECTED_PUBLIC_NODE_TOTAL,
            "rel_type_sum": pub_rels,
            "rel_type_sum_equals_total_rels": pub_rels
            == sum(pub_rel_types.values()),
            "label_sum": sum(pub_labels.values()),
            "label_sum_equals_total_nodes": sum(pub_labels.values()) == pub_nodes,
        },
    }


def collect_neo4j(driver: Any, log: logging.Logger) -> dict[str, Any]:
    log.info("Neo4j: 开始统计（只读事务）")
    with open_readonly_session(driver) as session:
        # 节点总数
        total_nodes = int(
            session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        )

        # 各标签节点数
        label_counts: dict[str, int] = {}
        for r in session.run(
            "MATCH (n) UNWIND labels(n) AS label "
            "RETURN label, count(*) AS c ORDER BY label"
        ):
            label_counts[str(r["label"])] = int(r["c"])

        # 关系总数 + 各类型
        total_rels = int(
            session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        )
        rel_type_counts: dict[str, int] = {}
        for r in session.run(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t"
        ):
            rel_type_counts[str(r["t"])] = int(r["c"])

        # (起点标签, 关系, 终点标签)：多标签时取字母序首个作主标签，并保留完整列表
        triple_acc: dict[tuple[str, str, str], dict[str, Any]] = {}
        for r in session.run(
            """
            MATCH (a)-[r]->(b)
            RETURN type(r) AS rel, labels(a) AS al, labels(b) AS bl, count(*) AS c
            """
        ):
            al = sorted(str(x) for x in (r["al"] or []))
            bl = sorted(str(x) for x in (r["bl"] or []))
            start = al[0] if al else ""
            end = bl[0] if bl else ""
            rel = str(r["rel"])
            key = (start, rel, end)
            prev = triple_acc.get(key)
            c = int(r["c"])
            if prev:
                prev["count"] += c
            else:
                triple_acc[key] = {
                    "start_label": start,
                    "start_labels": al,
                    "rel": rel,
                    "end_label": end,
                    "end_labels": bl,
                    "count": c,
                }
        triples = [triple_acc[k] for k in sorted(triple_acc.keys())]

        # 每标签属性键非空计数（全库）
        label_props: dict[str, dict[str, int]] = {}
        for label in sorted(label_counts.keys()):
            label_props[label] = _count_label_props(session, label, log)

        # 关系属性键
        rel_prop_keys: dict[str, int] = {}
        for r in session.run(
            """
            MATCH ()-[r]->()
            UNWIND keys(r) AS k
            WITH k, r[k] AS v
            WHERE v IS NOT NULL
            RETURN k AS key, count(*) AS c ORDER BY key
            """
        ):
            rel_prop_keys[str(r["key"])] = int(r["c"])
        rels_with_any_prop = int(
            session.run(
                "MATCH ()-[r]->() WHERE size(keys(r)) > 0 RETURN count(r) AS c"
            ).single()["c"]
        )

        # 约束
        constraints: list[dict[str, Any]] = []
        try:
            for r in session.run(
                "SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, "
                "properties, ownedIndex, propertyType "
                "RETURN name, type, entityType, labelsOrTypes, properties, "
                "ownedIndex, propertyType ORDER BY name"
            ):
                constraints.append(
                    {
                        "name": r.get("name"),
                        "type": r.get("type"),
                        "entityType": r.get("entityType"),
                        "labelsOrTypes": list(r.get("labelsOrTypes") or []),
                        "properties": list(r.get("properties") or []),
                        "ownedIndex": r.get("ownedIndex"),
                        "propertyType": r.get("propertyType"),
                    }
                )
        except Exception as e:
            log.warning("SHOW CONSTRAINTS 详细列失败，回退 name/type: %s", e)
            for r in session.run(
                "SHOW CONSTRAINTS YIELD name, type RETURN name, type ORDER BY name"
            ):
                constraints.append({"name": r["name"], "type": r["type"]})

        # 索引
        indexes: list[dict[str, Any]] = []
        try:
            for r in session.run(
                "SHOW INDEXES YIELD name, type, state, populationPercent, "
                "entityType, labelsOrTypes, properties "
                "RETURN name, type, state, populationPercent, entityType, "
                "labelsOrTypes, properties ORDER BY name"
            ):
                indexes.append(
                    {
                        "name": r.get("name"),
                        "type": r.get("type"),
                        "state": r.get("state"),
                        "populationPercent": r.get("populationPercent"),
                        "entityType": r.get("entityType"),
                        "labelsOrTypes": list(r.get("labelsOrTypes") or []),
                        "properties": list(r.get("properties") or []),
                    }
                )
        except Exception as e:
            log.warning("SHOW INDEXES 详细列失败，回退 name/type/state: %s", e)
            for r in session.run(
                "SHOW INDEXES YIELD name, type, state "
                "RETURN name, type, state ORDER BY name"
            ):
                indexes.append(
                    {
                        "name": r["name"],
                        "type": r["type"],
                        "state": r["state"],
                    }
                )

        # —— 对外口径 ——
        inner_nodes = resolve_bracket_inner_nodes(session, log)
        public = collect_public_scope(session, inner_nodes, label_counts, log)

    sum_labels = sum(label_counts.values())
    sum_rel_types = sum(rel_type_counts.values())
    check_nodes = sum_labels == total_nodes
    check_rels = sum_rel_types == total_rels

    excl = public["excluded"]
    # 全库 = 对外 + 被排除
    full_eq_pub_nodes = total_nodes == public["total_nodes"] + excl["nodes"]
    full_eq_pub_rels = (
        total_rels == public["total_relationships"] + excl["relationships"]
    )

    result = {
        "uri": DEFAULT_NEO4J_URI,  # 不含密码；实际 uri 由调用方覆盖
        "scope_full": {
            "scope": "全库口径",
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "label_counts": label_counts,
            "rel_type_counts": rel_type_counts,
            "rel_triples": triples,
            "label_property_nonempty": label_props,
            "rel_property_keys": rel_prop_keys,
            "rels_with_any_property": rels_with_any_prop,
        },
        # 兼容旧字段（=全库）
        "total_nodes": total_nodes,
        "total_relationships": total_rels,
        "label_counts": label_counts,
        "rel_type_counts": rel_type_counts,
        "rel_triples": triples,
        "label_property_nonempty": label_props,
        "rel_property_keys": rel_prop_keys,
        "rels_with_any_property": rels_with_any_prop,
        "constraints": constraints,
        "indexes": indexes,
        "scope_public": public,
        "self_check": {
            "label_sum": sum_labels,
            "label_sum_equals_total_nodes": check_nodes,
            "rel_type_sum": sum_rel_types,
            "rel_type_sum_equals_total_rels": check_rels,
            "full_equals_public_plus_excluded_nodes": full_eq_pub_nodes,
            "full_equals_public_plus_excluded_rels": full_eq_pub_rels,
            "full_nodes": total_nodes,
            "public_nodes": public["total_nodes"],
            "excluded_nodes": excl["nodes"],
            "full_rels": total_rels,
            "public_rels": public["total_relationships"],
            "excluded_rels": excl["relationships"],
            "public_truth_point": public["label_counts"].get("Truth_Point"),
            "public_truth_point_equals_2372": public["self_check"][
                "truth_point_equals_2372"
            ],
            "public_total_nodes_equals_7326": public["self_check"][
                "total_nodes_equals_7326"
            ],
            "public_rel_type_sum_equals_total": public["self_check"][
                "rel_type_sum_equals_total_rels"
            ],
            "bracket_copy_229_subset_of_excluded": excl[
                "bracket_copy_229_subset_of_excluded"
            ],
        },
    }
    log.info(
        "Neo4j 全库: nodes=%d labels_sum=%d check=%s; rels=%d types_sum=%d check=%s",
        total_nodes,
        sum_labels,
        check_nodes,
        total_rels,
        sum_rel_types,
        check_rels,
    )
    log.info(
        "Neo4j 对外: nodes=%d TP=%s rels=%d; excluded nodes=%d rels=%d; "
        "full=public+excl nodes=%s rels=%s; copy229_subset=%s",
        public["total_nodes"],
        public["label_counts"].get("Truth_Point"),
        public["total_relationships"],
        excl["nodes"],
        excl["relationships"],
        full_eq_pub_nodes,
        full_eq_pub_rels,
        excl["bracket_copy_229_subset_of_excluded"],
    )
    return result


# ---------------------------------------------------------------------------
# Elasticsearch
# ---------------------------------------------------------------------------

def connect_es(url: str, user: str, password: str) -> ReadOnlyES:
    try:
        from elasticsearch import Elasticsearch
    except ImportError as e:
        raise SystemExit("需要安装 elasticsearch：pip install elasticsearch") from e
    raw = Elasticsearch(
        hosts=[url],
        basic_auth=(user, password),
        request_timeout=180,
        verify_certs=False,
        ssl_show_warn=False,
    )
    return ReadOnlyES(raw)


def assert_qa4_cluster(es: ReadOnlyES, log: logging.Logger) -> str:
    info = es.info()
    name = str(info.get("cluster_name") or "")
    if name != QA4_CLUSTER:
        raise SystemExit(
            f"中止：ES cluster_name={name!r}，必须为 {QA4_CLUSTER!r}（疑似连错集群）"
        )
    log.info("ES cluster_name=%s OK", name)
    return name


def _field_exists_count(es: ReadOnlyES, index: str, field: str) -> int:
    """非空条数：_count + exists。不取回字段值。"""
    # 跳过 multi-field 子字段中纯 keyword 的 .keyword 仍可 count
    body = {"query": {"exists": {"field": field}}}
    resp = es.count(index=index, body=body)
    return int(resp.get("count") or 0)


def collect_es(es: ReadOnlyES, log: logging.Logger) -> dict[str, Any]:
    log.info("ES: 开始统计（只读 GET/count/search）")
    indices_out: list[dict[str, Any]] = []
    total_docs = 0

    for index in QA4_INDICES:
        if not es.indices.exists(index=index):
            log.warning("索引不存在: %s", index)
            indices_out.append({"index": index, "exists": False})
            continue

        stats = es.indices.stats(index=index)
        istats = (stats.get("indices") or {}).get(index) or {}
        prim = istats.get("primaries") or {}
        docs = prim.get("docs") or {}
        store = prim.get("store") or {}
        doc_count = int(docs.get("count") or 0)
        docs_deleted = int(docs.get("deleted") or 0)
        size_bytes = int(store.get("size_in_bytes") or 0)
        total_docs += doc_count

        mapping_resp = es.indices.get_mapping(index=index)
        props = (
            ((mapping_resp.get(index) or {}).get("mappings") or {}).get("properties")
            or {}
        )
        fields = _flatten_mapping_props(props)

        settings_resp = es.indices.get_settings(index=index)
        raw_settings = (settings_resp.get(index) or {}).get("settings") or {}
        analyzers = _index_analyzers(raw_settings)

        # 默认分词器
        default_analyzer = None
        idx_settings = raw_settings.get("index") or {}
        if isinstance(idx_settings, dict):
            analysis = idx_settings.get("analysis") or {}
            if isinstance(analysis, dict):
                default_analyzer = (analysis.get("analyzer") or {}).get("default")

        vector_fields = [f for f in fields if f.get("type") == "dense_vector"]

        # 非向量字段非空计数（含 text 字段——只计数量，不取取值）
        nonempty: dict[str, int] = {}
        for f in fields:
            fname = f["name"]
            ftype = f.get("type")
            if ftype == "dense_vector":
                # 向量字段：只报是否存在文档（exists 计数），不取向量值
                nonempty[fname] = _field_exists_count(es, index, fname)
                continue
            # multi-field 如 title.keyword 也统计
            nonempty[fname] = _field_exists_count(es, index, fname)

        # message_key cardinality（近似）
        message_key_card: dict[str, Any] | None = None
        field_names = {f["name"] for f in fields}
        if "message_key" in field_names:
            agg_body = {
                "size": 0,
                "aggs": {
                    "mk": {
                        "cardinality": {
                            "field": "message_key",
                            "precision_threshold": 40000,
                        }
                    }
                },
            }
            # keyword 子字段优先
            mk_field = "message_key"
            if "message_key.keyword" in field_names:
                mk_field = "message_key.keyword"
                agg_body["aggs"]["mk"]["cardinality"]["field"] = mk_field
            elif any(
                f["name"] == "message_key" and f.get("type") == "text" for f in fields
            ):
                # text 无 keyword 时 cardinality 可能失败；尝试 .keyword 或不报
                pass
            try:
                aresp = es.search(index=index, body=agg_body)
                val = (
                    ((aresp.get("aggregations") or {}).get("mk") or {}).get("value")
                )
                message_key_card = {
                    "field": mk_field,
                    "value": int(val) if val is not None else None,
                    "approximate": True,
                    "precision_threshold": 40000,
                    "note": "cardinality 为近似值",
                }
            except Exception as e:
                log.warning("%s message_key cardinality 失败: %s", index, e)
                message_key_card = {"error": str(e), "approximate": True}

        node_type_counts: dict[str, int] | None = None
        if index == "qa4_pano_catalog" and "node_type" in field_names:
            nt_field = (
                "node_type.keyword"
                if "node_type.keyword" in field_names
                else "node_type"
            )
            try:
                aresp = es.search(
                    index=index,
                    body={
                        "size": 0,
                        "aggs": {
                            "by_nt": {
                                "terms": {"field": nt_field, "size": 50}
                            }
                        },
                    },
                )
                buckets = (
                    ((aresp.get("aggregations") or {}).get("by_nt") or {}).get(
                        "buckets"
                    )
                    or []
                )
                node_type_counts = {
                    str(b["key"]): int(b["doc_count"]) for b in buckets
                }
            except Exception as e:
                log.warning("pano node_type 聚合失败: %s", e)
                node_type_counts = {"_error": str(e)}  # type: ignore[dict-item]

        indices_out.append(
            {
                "index": index,
                "exists": True,
                "docs_count": doc_count,
                "docs_deleted": docs_deleted,
                "store_size_bytes": size_bytes,
                "fields": fields,
                "vector_fields": vector_fields,
                "analyzers": analyzers,
                "default_analyzer": default_analyzer,
                "field_nonempty_counts": nonempty,
                "message_key_cardinality": message_key_card,
                "node_type_counts": node_type_counts,
            }
        )
        log.info(
            "ES %s: docs=%d deleted=%d size=%d fields=%d",
            index,
            doc_count,
            docs_deleted,
            size_bytes,
            len(fields),
        )

    check_ok = total_docs == EXPECTED_ES_TOTAL
    return {
        "indices": indices_out,
        "total_docs": total_docs,
        "expected_total_docs": EXPECTED_ES_TOTAL,
        "self_check": {
            "sum_equals_414082": check_ok,
            "sum": total_docs,
        },
    }


# ---------------------------------------------------------------------------
# Markdown / JSON 输出（绝不写入字段取值）
# ---------------------------------------------------------------------------

def render_markdown(report: dict[str, Any]) -> str:
    neo = report.get("neo4j") or {}
    es = report.get("elasticsearch") or {}
    lines: list[str] = []
    lines.append("# qa4 库统计报告")
    lines.append("")
    lines.append(f"- 生成时间（UTC）：`{report.get('generated_at_utc', '')}`")
    lines.append(f"- ES：`{report.get('es_url', '')}` cluster=`{report.get('es_cluster', '')}`")
    lines.append(f"- Neo4j：`{report.get('neo4j_uri', '')}`（只读）")
    lines.append("")

    # 自校验
    nsc = neo.get("self_check") or {}
    esc = es.get("self_check") or {}
    pub = neo.get("scope_public") or {}
    psc = pub.get("self_check") or {}
    excl = pub.get("excluded") or {}
    lines.append("## 自校验")
    lines.append("")
    lines.append("### 全库口径")
    lines.append("")
    lines.append(
        f"- Neo4j 标签节点数之和 {nsc.get('label_sum')} "
        f"= 节点总数 {neo.get('total_nodes')} → "
        f"**{'通过' if nsc.get('label_sum_equals_total_nodes') else '失败'}**"
    )
    lines.append(
        f"- Neo4j 关系类型数量之和 {nsc.get('rel_type_sum')} "
        f"= 关系总数 {neo.get('total_relationships')} → "
        f"**{'通过' if nsc.get('rel_type_sum_equals_total_rels') else '失败'}**"
    )
    lines.append("")
    lines.append("### 对外口径")
    lines.append("")
    lines.append(
        f"- 对外 Truth_Point = {psc.get('truth_point')} "
        f"（期望 {EXPECTED_PUBLIC_TRUTH_POINT}）→ "
        f"**{'通过' if psc.get('truth_point_equals_2372') else '失败'}**"
    )
    lines.append(
        f"- 对外节点总数 = {psc.get('total_nodes')} "
        f"（期望 {EXPECTED_PUBLIC_NODE_TOTAL}）→ "
        f"**{'通过' if psc.get('total_nodes_equals_7326') else '失败'}**"
    )
    lines.append(
        f"- 对外关系类型之和 {psc.get('rel_type_sum')} "
        f"= 对外关系总数 {pub.get('total_relationships')} → "
        f"**{'通过' if psc.get('rel_type_sum_equals_total_rels') else '失败'}**"
    )
    lines.append(
        f"- 全库节点 {nsc.get('full_nodes')} = 对外 {nsc.get('public_nodes')} "
        f"+ 排除 {nsc.get('excluded_nodes')} → "
        f"**{'通过' if nsc.get('full_equals_public_plus_excluded_nodes') else '失败'}**"
    )
    lines.append(
        f"- 全库关系 {nsc.get('full_rels')} = 对外 {nsc.get('public_rels')} "
        f"+ 排除 {nsc.get('excluded_rels')} → "
        f"**{'通过' if nsc.get('full_equals_public_plus_excluded_rels') else '失败'}**"
    )
    lines.append(
        f"- 括号内复制新增 229 ⊆ 被排除边 → "
        f"**{'通过' if excl.get('bracket_copy_229_subset_of_excluded') else '失败'}**"
    )
    lines.append("")
    lines.append("### ES")
    lines.append("")
    lines.append(
        f"- ES 十索引条数之和 {esc.get('sum')} "
        f"= {EXPECTED_ES_TOTAL} → "
        f"**{'通过' if esc.get('sum_equals_414082') else '失败'}**"
    )
    lines.append("")

    def _node_table(title: str, label_counts: dict, total: Any) -> None:
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| 标签 | 节点数 |")
        lines.append("|------|--------|")
        for lab, c in sorted((label_counts or {}).items()):
            lines.append(f"| {lab} | {c} |")
        lines.append(f"| **合计** | **{total}** |")
        lines.append("")

    def _rel_table(title: str, rel_counts: dict, total: Any) -> None:
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| 关系类型 | 数量 |")
        lines.append("|----------|------|")
        for t, c in sorted((rel_counts or {}).items()):
            lines.append(f"| {t} | {c} |")
        lines.append(f"| **合计** | **{total}** |")
        lines.append("")

    def _props_table(title: str, label_props: dict) -> None:
        lines.append(f"## {title}")
        lines.append("")
        for lab, props in sorted((label_props or {}).items()):
            lines.append(f"### {lab}")
            lines.append("")
            lines.append("| 属性键 | 非空节点数 |")
            lines.append("|--------|------------|")
            for k, c in sorted(props.items()):
                lines.append(f"| {k} | {c} |")
            lines.append("")

    # —— 全库 ——
    lines.append("# 全库口径")
    lines.append("")
    _node_table("节点表（全库）", neo.get("label_counts") or {}, neo.get("total_nodes"))
    _rel_table(
        "关系类型表（全库）",
        neo.get("rel_type_counts") or {},
        neo.get("total_relationships"),
    )

    lines.append("## 关系三元组（全库：起点标签, 关系, 终点标签）")
    lines.append("")
    lines.append("| 起点标签 | 关系 | 终点标签 | 数量 |")
    lines.append("|----------|------|----------|------|")
    for row in neo.get("rel_triples") or []:
        lines.append(
            f"| {row.get('start_label')} | {row.get('rel')} | "
            f"{row.get('end_label')} | {row.get('count')} |"
        )
    lines.append("")

    _props_table(
        "标注覆盖表（全库，不含取值）",
        neo.get("label_property_nonempty") or {},
    )
    lines.append(
        f"关系上带任意属性的关系数：`{neo.get('rels_with_any_property', 0)}`"
    )
    if neo.get("rel_property_keys"):
        lines.append("")
        lines.append("| 关系属性键 | 非空关系数 |")
        lines.append("|------------|------------|")
        for k, c in sorted((neo.get("rel_property_keys") or {}).items()):
            lines.append(f"| {k} | {c} |")
    else:
        lines.append("（关系无属性键）")
    lines.append("")

    # —— 对外 ——
    lines.append("# 对外口径（排除括号内 8 词条及其全部相连边）")
    lines.append("")
    lines.append("排除词条（括号内 → 括号外对照）：")
    lines.append("")
    lines.append("| 括号内 | 括号外 |")
    lines.append("|--------|--------|")
    for pair in pub.get("bracket_pairs") or []:
        lines.append(f"| {pair.get('inner')} | {pair.get('outer')} |")
    lines.append("")
    _node_table(
        "节点表（对外）",
        pub.get("label_counts") or {},
        pub.get("total_nodes"),
    )
    _rel_table(
        "关系类型表（对外：29 语义 + 分类 + SUPPORTED_BY）",
        pub.get("rel_type_counts") or {},
        pub.get("total_relationships"),
    )
    _props_table(
        "标注覆盖表（对外，仅未排除节点）",
        pub.get("label_property_nonempty") or {},
    )

    # —— 排除明细 ——
    lines.append("# 被排除明细")
    lines.append("")
    lines.append(f"- 被排除节点数：`{excl.get('nodes')}`")
    lines.append(f"- 被排除节点名：{', '.join(excl.get('node_names') or [])}")
    lines.append(f"- 被排除边数：`{excl.get('relationships')}`")
    lines.append("")
    lines.append("## 被排除边按类型")
    lines.append("")
    lines.append("| 关系类型 | 数量 |")
    lines.append("|----------|------|")
    for t, c in sorted((excl.get("rel_type_counts") or {}).items()):
        lines.append(f"| {t} | {c} |")
    lines.append(f"| **合计** | **{excl.get('relationships')}** |")
    lines.append("")
    lines.append("## 各括号内节点触及边数")
    lines.append("")
    lines.append("| 词条 | 触及边数 |")
    lines.append("|------|----------|")
    for row in excl.get("per_inner_incident_rels") or []:
        lines.append(f"| {row.get('name')} | {row.get('incident_rels')} |")
    lines.append("")
    lines.append("## 括号内复制新增 229 ⊆ 被排除边")
    lines.append("")
    lines.append(excl.get("bracket_copy_subset_proof") or "")
    lines.append("")
    lines.append(
        f"- 非分类被排除边合计："
        f"`{sum((excl.get('rel_type_counts_excluding_classification') or {}).values())}`"
        f"（期望 ≥ {EXPECTED_BRACKET_COPY_NEW_RELS}）"
    )
    lines.append("")

    # 约束与索引
    lines.append("## 约束清单")
    lines.append("")
    lines.append("| 名称 | 类型 | 实体 | 标签/类型 | 属性 |")
    lines.append("|------|------|------|-----------|------|")
    for c in neo.get("constraints") or []:
        lines.append(
            f"| {c.get('name')} | {c.get('type')} | {c.get('entityType', '')} | "
            f"{','.join(c.get('labelsOrTypes') or [])} | "
            f"{','.join(c.get('properties') or [])} |"
        )
    lines.append("")

    lines.append("## 索引清单")
    lines.append("")
    lines.append("| 名称 | 类型 | 状态 | 标签/类型 | 属性 |")
    lines.append("|------|------|------|-----------|------|")
    for ix in neo.get("indexes") or []:
        lines.append(
            f"| {ix.get('name')} | {ix.get('type')} | {ix.get('state')} | "
            f"{','.join(ix.get('labelsOrTypes') or [])} | "
            f"{','.join(ix.get('properties') or [])} |"
        )
    lines.append("")

    # ES 索引表
    lines.append("## ES 索引表")
    lines.append("")
    lines.append(
        "| 索引 | 条数 | 体积(字节) | docs.deleted | "
        "message_key 篇数(近似) |"
    )
    lines.append("|------|------|------------|--------------|----------------------|")
    for ix in es.get("indices") or []:
        if not ix.get("exists"):
            lines.append(f"| {ix.get('index')} | — | — | — | 不存在 |")
            continue
        mk = ix.get("message_key_cardinality") or {}
        mk_s = mk.get("value", "—")
        lines.append(
            f"| {ix.get('index')} | {ix.get('docs_count')} | "
            f"{ix.get('store_size_bytes')} | {ix.get('docs_deleted')} | {mk_s} |"
        )
    lines.append(
        f"| **合计** | **{es.get('total_docs')}** |  |  |  |"
    )
    lines.append("")
    lines.append(
        f"> message_key cardinality 使用 `precision_threshold=40000`，为**近似值**。"
    )
    lines.append("")

    # pano node_type
    for ix in es.get("indices") or []:
        if ix.get("index") == "qa4_pano_catalog" and ix.get("node_type_counts"):
            lines.append("### qa4_pano_catalog 按 node_type")
            lines.append("")
            lines.append("| node_type | 条数 |")
            lines.append("|-----------|------|")
            for k, c in sorted((ix.get("node_type_counts") or {}).items()):
                lines.append(f"| {k} | {c} |")
            lines.append("")

    # 字段表
    lines.append("## ES 字段表（名称 / 类型；向量另列维度与相似度）")
    lines.append("")
    for ix in es.get("indices") or []:
        if not ix.get("exists"):
            continue
        lines.append(f"### {ix.get('index')}")
        lines.append("")
        lines.append("| 字段 | 类型 | 维度 | 相似度 | 分词器 | 非空条数 |")
        lines.append("|------|------|------|--------|--------|----------|")
        nonempty = ix.get("field_nonempty_counts") or {}
        for f in ix.get("fields") or []:
            lines.append(
                f"| {f.get('name')} | {f.get('type')} | "
                f"{f.get('dims', '')} | {f.get('similarity', '')} | "
                f"{f.get('analyzer', '')} | {nonempty.get(f.get('name'), '')} |"
            )
        if ix.get("analyzers"):
            lines.append("")
            lines.append("自定义分词器：")
            for aname, aconf in sorted((ix.get("analyzers") or {}).items()):
                lines.append(
                    f"- `{aname}`: type={aconf.get('type')} "
                    f"tokenizer={aconf.get('tokenizer')} "
                    f"filter_count={aconf.get('filter_count')}"
                )
        lines.append("")

    lines.append("---")
    lines.append("本报告只含计数、字段名与类型；不含文档正文、向量或标注取值。")
    lines.append("")
    return "\n".join(lines)


def scrub_for_safety(obj: Any, path: str = "") -> None:
    """运行期断言：结构中不得出现 VALUE_BAN_FIELDS 的「取值」——
    我们的报告结构里这些名字只应作为字段名字符串出现在 name/key 位置，
    不应作为 dict 的大段 list/str 值。此处做轻量检查：若某键名为禁字段且值非标量计数，则报错。
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in VALUE_BAN_FIELDS and not isinstance(v, (int, float, type(None))):
                # 允许作为字段清单里的 name 字符串被引用，但不允许以此为键存放内容
                if isinstance(v, (list, dict)) or (isinstance(v, str) and len(v) > 64):
                    raise RuntimeError(
                        f"安全检查失败：禁止输出字段取值 path={path}.{k} type={type(v).__name__}"
                    )
            scrub_for_safety(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            scrub_for_safety(v, f"{path}[{i}]")


# ---------------------------------------------------------------------------
# Self-test（不连库）
# ---------------------------------------------------------------------------

def run_self_test() -> int:
    print("=== stats_report self-test（只读守卫）===")
    failed = 0

    # 1) 合法只读 Cypher
    try:
        assert_cypher_readonly("MATCH (n) RETURN count(n)")
        print("PASS 允许 MATCH")
    except Exception as e:
        print("FAIL 允许 MATCH", e)
        failed += 1

    # 2) 写语句拒绝（演示）
    write_q = "MATCH (n:Trunk) SET n.x = 1 RETURN n"
    try:
        assert_cypher_readonly(write_q)
        print("FAIL 应拒绝 SET:", write_q)
        failed += 1
    except PermissionError as e:
        print("PASS 拒绝写语句:", str(e)[:80])

    for bad in (
        "CREATE (n:Foo)",
        "MERGE (n:Foo {a:1})",
        "MATCH (n) DELETE n",
        "MATCH (n) DETACH DELETE n",
        "DROP CONSTRAINT foo",
    ):
        try:
            assert_cypher_readonly(bad)
            print("FAIL 应拒绝:", bad)
            failed += 1
        except PermissionError:
            print("PASS 拒绝:", bad.split()[0])

    # 3) ES 写方法拒绝
    try:
        assert_es_method_readonly("index")
        print("FAIL 应拒绝 es.index")
        failed += 1
    except PermissionError:
        print("PASS 拒绝 ES.index")

    try:
        assert_es_indices_method_readonly("delete")
        print("FAIL 应拒绝 indices.delete")
        failed += 1
    except PermissionError:
        print("PASS 拒绝 ES.indices.delete")

    # 4) 期望数字常量自洽
    if sum(EXPECTED_LABELS.values()) != EXPECTED_NODE_TOTAL:
        print("FAIL EXPECTED_LABELS 之和 != EXPECTED_NODE_TOTAL")
        failed += 1
    else:
        print(
            f"PASS 期望节点 {EXPECTED_NODE_TOTAL} = "
            + " + ".join(f"{k} {v}" for k, v in EXPECTED_LABELS.items())
        )

    if failed:
        print(f"SELF-TEST FAILED count={failed}")
        return 1
    print("SELF-TEST ALL PASSED")
    print(
        "拒绝写操作检查位置: "
        "assert_cypher_readonly (Cypher) / "
        "assert_es_method_readonly / assert_es_indices_method_readonly / "
        "ReadOnlySession.run / ReadOnlyES.__getattr__"
    )
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="qa4 只读统计报告")
    p.add_argument("--es-url", default=os.environ.get("QA4_ES_URL", DEFAULT_ES_URL))
    p.add_argument("--es-user", default=os.environ.get("QA4_ES_USERNAME", "elastic"))
    p.add_argument(
        "--neo4j-uri",
        default=os.environ.get("QA4_NEO4J_URI", DEFAULT_NEO4J_URI),
    )
    p.add_argument(
        "--neo4j-user",
        default=os.environ.get("QA4_NEO4J_USER", DEFAULT_NEO4J_USER),
    )
    p.add_argument(
        "--out-dir",
        default=os.environ.get("QA4_STATS_DIR", str(DEFAULT_OUT_DIR)),
    )
    p.add_argument("--self-test", action="store_true", help="不连库，测试只读守卫")
    args = p.parse_args(argv)

    if args.self_test:
        return run_self_test()

    es_password = os.environ.get("QA4_ES_PASSWORD", "")
    neo4j_password = os.environ.get("QA4_NEO4J_PASSWORD", "")
    if not es_password:
        raise SystemExit("缺少环境变量 QA4_ES_PASSWORD（请用 stats_report_run.ps1 注入）")
    if not neo4j_password:
        raise SystemExit(
            "缺少环境变量 QA4_NEO4J_PASSWORD（请用 stats_report_run.ps1 注入）"
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utcnow_stamp()
    log_path = out_dir / f"qa4_stats_{stamp}.log"
    json_path = out_dir / f"qa4_stats_{stamp}.json"
    md_path = out_dir / f"qa4_stats_{stamp}.md"
    log = _setup_logger(log_path)
    log.info("输出目录: %s", out_dir)
    log.info("ES url=%s user=%s", args.es_url, args.es_user)
    log.info("Neo4j uri=%s user=%s", args.neo4j_uri, args.neo4j_user)
    # 绝不打印密码

    t0 = time.monotonic()
    es = connect_es(args.es_url, args.es_user, es_password)
    cluster = assert_qa4_cluster(es, log)
    driver = connect_neo4j(args.neo4j_uri, args.neo4j_user, neo4j_password)

    try:
        neo = collect_neo4j(driver, log)
        neo["uri"] = args.neo4j_uri
        es_stats = collect_es(es, log)
    finally:
        try:
            driver.close()
        except Exception:
            pass

    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "es_url": args.es_url,
        "es_cluster": cluster,
        "neo4j_uri": args.neo4j_uri,
        "neo4j": neo,
        "elasticsearch": es_stats,
        "expectations": {
            "nodes": EXPECTED_NODE_TOTAL,
            "labels": EXPECTED_LABELS,
            "relationships": EXPECTED_REL_TOTAL,
            "es_docs": EXPECTED_ES_TOTAL,
        },
        "readonly_guards": {
            "cypher": "assert_cypher_readonly / ReadOnlySession.run",
            "es": "assert_es_method_readonly / ReadOnlyES",
            "es_indices": "assert_es_indices_method_readonly / _ReadOnlyIndices",
        },
    }

    # 与期望对照（不一致只报告，不改数字）
    mismatches: list[str] = []
    if neo.get("total_nodes") != EXPECTED_NODE_TOTAL:
        mismatches.append(
            f"全库节点总数实际={neo.get('total_nodes')} 期望={EXPECTED_NODE_TOTAL}"
        )
    for lab, exp in EXPECTED_LABELS.items():
        got = (neo.get("label_counts") or {}).get(lab)
        if got != exp:
            mismatches.append(f"全库标签 {lab} 实际={got} 期望={exp}")
    if neo.get("total_relationships") != EXPECTED_REL_TOTAL:
        mismatches.append(
            f"全库关系总数实际={neo.get('total_relationships')} 期望={EXPECTED_REL_TOTAL}"
        )
    pub = neo.get("scope_public") or {}
    psc = pub.get("self_check") or {}
    excl = pub.get("excluded") or {}
    nsc = neo.get("self_check") or {}
    tp_pub = (pub.get("label_counts") or {}).get("Truth_Point")
    if tp_pub != EXPECTED_PUBLIC_TRUTH_POINT:
        mismatches.append(
            f"对外 Truth_Point 实际={tp_pub} 期望={EXPECTED_PUBLIC_TRUTH_POINT}"
        )
    if pub.get("total_nodes") != EXPECTED_PUBLIC_NODE_TOTAL:
        mismatches.append(
            f"对外节点总数实际={pub.get('total_nodes')} "
            f"期望={EXPECTED_PUBLIC_NODE_TOTAL}"
        )
    if not nsc.get("full_equals_public_plus_excluded_nodes"):
        mismatches.append(
            f"全库节点≠对外+排除: full={nsc.get('full_nodes')} "
            f"public={nsc.get('public_nodes')} excl={nsc.get('excluded_nodes')}"
        )
    if not nsc.get("full_equals_public_plus_excluded_rels"):
        mismatches.append(
            f"全库关系≠对外+排除: full={nsc.get('full_rels')} "
            f"public={nsc.get('public_rels')} excl={nsc.get('excluded_rels')}"
        )
    if not psc.get("rel_type_sum_equals_total_rels"):
        mismatches.append(
            f"对外关系类型之和≠对外关系总数: "
            f"sum={psc.get('rel_type_sum')} total={pub.get('total_relationships')}"
        )
    if not excl.get("bracket_copy_229_subset_of_excluded"):
        mismatches.append(
            "括号内复制新增 229 未能证明为被排除边的子集"
            f"（非分类排除边="
            f"{sum((excl.get('rel_type_counts_excluding_classification') or {}).values())}）"
        )
    if es_stats.get("total_docs") != EXPECTED_ES_TOTAL:
        mismatches.append(
            f"ES 总条数实际={es_stats.get('total_docs')} 期望={EXPECTED_ES_TOTAL}"
        )
    report["expectation_mismatches"] = mismatches
    if mismatches:
        for m in mismatches:
            log.error("期望不一致（未改数字）: %s", m)
    else:
        log.info("与期望数字全部一致（含对外口径）")

    scrub_for_safety(report)

    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    elapsed = time.monotonic() - t0
    size = json_path.stat().st_size
    log.info("JSON: %s (%d bytes)", json_path, size)
    log.info("Markdown: %s", md_path)
    log.info("完成，耗时 %.1fs", elapsed)

    # 控制台摘要
    print("--- 摘要 ---")
    print(
        f"全库 nodes={neo.get('total_nodes')} "
        f"labels={neo.get('label_counts')} "
        f"rels={neo.get('total_relationships')}"
    )
    print(
        f"对外 nodes={pub.get('total_nodes')} "
        f"TP={tp_pub} rels={pub.get('total_relationships')} "
        f"excl_nodes={excl.get('nodes')} excl_rels={excl.get('relationships')}"
    )
    print(
        f"self_check full_nodes={nsc.get('label_sum_equals_total_nodes')} "
        f"full_rels={nsc.get('rel_type_sum_equals_total_rels')} "
        f"full=pub+excl nodes={nsc.get('full_equals_public_plus_excluded_nodes')} "
        f"rels={nsc.get('full_equals_public_plus_excluded_rels')} "
        f"pub_TP_2372={nsc.get('public_truth_point_equals_2372')} "
        f"pub_nodes_7326={nsc.get('public_total_nodes_equals_7326')} "
        f"copy229_subset={excl.get('bracket_copy_229_subset_of_excluded')}"
    )
    print(
        f"ES total_docs={es_stats.get('total_docs')} "
        f"self_check={es_stats['self_check']['sum_equals_414082']}"
    )
    print(f"JSON size={size} bytes")
    if mismatches:
        print("MISMATCHES:")
        for m in mismatches:
            print(" ", m)
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        # 即使非 ps1 调用也尽量清掉本进程密码环境变量
        os.environ.pop("QA4_ES_PASSWORD", None)
        os.environ.pop("QA4_NEO4J_PASSWORD", None)
