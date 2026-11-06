# -*- coding: utf-8 -*-
"""neo4j-v4 标注导入 v4：只写布尔标记（如 organic_advance = true），不把 JSON 内容写入图谱。

不修改 import_annotation.py / _v2.py / _v3.py。
复用 v1 连接/快照/SET，以及 v2 的 expect-anno SHA 工具。

额外提供 --stage copy：把源 JSON 复制到仓库内数据目录并写 SHA256SUMS / README。

用法（在 back_mic/backend 下）:
    python -m panai4.graph.import_annotation_v4 --stage copy \\
        --file "C:\\...\\源.json" --dest "...\\organic_advance.json" \\
        --expected-sha 63a2... --expected-size 38800482
    python -m panai4.graph.import_annotation_v4 --stage check \\
        --file "...\\organic_advance.json" --name organic_advance \\
        --expect-anno devine_argument=187 --expect-anno intrinsic_significance=2372 \\
        --expect-anno mutuality=116 --report docs/panai4_graph/import_organic_advance.md
    python -m panai4.graph.import_annotation_v4 --stage import|verify ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

from panai4.graph import import_annotation as v1
from panai4.graph import import_annotation_v2 as v2

_REPO = v1._REPO
_LOG_DIR = v1._LOG_DIR
_PROP_NAME_RE = v1._PROP_NAME_RE
_BATCH = 50
_DEFAULT_ALIASES = {"路得马丁": "路德马丁"}
_EXPECTED_SHA = "63a2320504c535e5b54d6ac8b33e0f76cafdfa5d330edfe9ccbbaa15abfb8178"
_EXPECTED_SIZE = 38800482
_STAGES = [f"content_{i}" for i in range(1, 7)]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_aliases(items: list[str]) -> dict[str, str]:
    out = dict(_DEFAULT_ALIASES)
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--alias 格式应为 旧=新，收到: {item}")
        a, b = item.split("=", 1)
        out[a.strip()] = b.strip()
    return out


def _gitignore_report(dest: Path) -> dict[str, Any]:
    root_gi = _REPO / ".gitignore"
    rules = []
    if root_gi.is_file():
        for line in root_gi.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "data" in s.lower() or s.endswith(".json") or "panai4" in s.lower() or "json" in s.lower():
                rules.append(line)
    other = []
    for p in [_REPO / "back_mic" / ".gitignore", _REPO / "back_mic" / "backend" / ".gitignore"]:
        if p.is_file():
            other.append(str(p.relative_to(_REPO)))
    check_ignore = None
    try:
        out = subprocess.check_output(
            ["git", "check-ignore", "-v", str(dest)],
            cwd=str(_REPO),
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip()
        check_ignore = out or "(未忽略：无输出)"
    except subprocess.CalledProcessError as exc:
        # exit 1 = not ignored
        check_ignore = f"(未被 ignore；exit={exc.returncode})"
    except Exception as exc:
        check_ignore = f"(check-ignore 失败: {exc})"
    return {"root_rules_related": rules, "other_gitignore_files": other, "check_ignore": check_ignore}


def write_data_readme(path: Path, *, src: Path, sha: str, size: int, n: int, copied_at: str) -> None:
    rel = path.relative_to(_REPO).as_posix()
    text = f"""# organic_advance.json

## 这是什么

「生机关联的进展」（organic advance）专特标注的**内容文件**，共 **{n}** 个词条。

每条含：`name`、`series`、`stages`、`content_1` … `content_6`；每个 content 项含 `title`、`book`、`date`、`source`、`outline`（职事原文）。

## 来源

- 桌面源路径：`{src}`
- 大小：{size} 字节
- SHA256：`{sha}`
- 复制日期：{copied_at}

## 与图谱的关系

图谱里 `Truth_Point` 节点的标注 `organic_advance = true` **只表示**：该词条在本文件里有内容。

内容本身**不在**图谱里；检索时按词条名 `name` 到本文件取。

这是例外：其他专特标注的内容都在图谱节点里。

## 部署

服务器上需在同一相对路径放一份（相对仓库根）：

`{rel}`

读取时用相对于仓库根的路径，不要写死盘符。

本文件体积大，**不进 git**，需要单独备份与部署。

词条改名或删除后，要核对本文件里的 `name` 与图谱是否一致。
"""
    path.write_text(text, encoding="utf-8")


def stage_copy(
    env: dict,
    log: v1.Logger,
    src: Path,
    dest: Path,
    expected_sha: str,
    expected_size: int,
    report_path: Path,
) -> int:
    log.log(f"stage=copy src={src} dest={dest}")
    if not src.is_file():
        raise SystemExit(f"源文件不存在: {src}")
    size = src.stat().st_size
    sha = _sha256(src)
    log.log(f"F1 size={size} sha={sha}")
    if size != expected_size or sha != expected_sha:
        log.log(f"GATE FAIL F1: size/sha 不符 expected size={expected_size} sha={expected_sha}")
        _write_partial_report_copy_fail(report_path, src, dest, size, sha, expected_size, expected_sha, "F1")
        return 2
    if dest.exists():
        log.log(f"GATE FAIL F2: 目标已存在，拒绝覆盖: {dest}")
        _write_partial_report_copy_fail(report_path, src, dest, size, sha, expected_size, expected_sha, "F2 dest exists")
        return 2
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    size2 = dest.stat().st_size
    sha2 = _sha256(dest)
    data = json.loads(dest.read_text(encoding="utf-8-sig"))
    n = len(data) if isinstance(data, list) else None
    log.log(f"F3 dest size={size2} sha={sha2} n={n}")
    if size2 != size or sha2 != sha or n != 69:
        log.log("GATE FAIL F3")
        _write_partial_report_copy_fail(report_path, src, dest, size, sha, expected_size, expected_sha, "F3", dest_sha=sha2, dest_size=size2, n=n)
        return 2

    sums = dest.parent / "SHA256SUMS.txt"
    sums.write_text(f"{sha2}  organic_advance.json\n", encoding="utf-8")
    log.log(f"F4 wrote {sums}")
    readme = dest.parent / "README.md"
    write_data_readme(
        readme,
        src=src,
        sha=sha2,
        size=size2,
        n=n,
        copied_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    log.log(f"F5 wrote {readme}")
    gi = _gitignore_report(dest)
    log.log(f"F6 check-ignore: {gi['check_ignore']}")

    # also sha import dir for later stages baseline of desktop files
    sha_import = v1._sha_import_dir()
    state = {
        "version": 4,
        "mode": "flag-true",
        "copy_ok": True,
        "src": str(src),
        "dest": str(dest),
        "sha": sha2,
        "size": size2,
        "n_records": n,
        "gitignore": gi,
        "sha_import_after_copy": sha_import,
        "copied_at": datetime.now().isoformat(timespec="seconds"),
    }
    # stash under anno name later; for now save with organic_advance key when name known
    v1.save_state("organic_advance_copy", state)
    log.log("copy 完成，可进入 --stage check")
    # minimal report stub updated in check
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        f"# neo4j-v4 导入标注 `organic_advance`（进行中：copy 完成）\n\n"
        f"- dest=`{dest}`\n- size={size2}\n- sha=`{sha2}`\n- n={n}\n"
        f"- git check-ignore: {gi['check_ignore']}\n",
        encoding="utf-8",
    )
    return 0


def _write_partial_report_copy_fail(report_path, src, dest, size, sha, exp_size, exp_sha, reason, dest_sha=None, dest_size=None, n=None):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        f"# organic_advance copy 失败\n\nreason={reason}\n"
        f"src={src} size={size} sha={sha}\nexpected size={exp_size} sha={exp_sha}\n"
        f"dest={dest} dest_size={dest_size} dest_sha={dest_sha} n={n}\n",
        encoding="utf-8",
    )


def _has_any_stage_content(rec: dict) -> bool:
    for st in _STAGES:
        items = rec.get(st)
        if isinstance(items, list) and len(items) > 0:
            return True
    return False


def write_report(
    state: dict,
    import_info: dict | None,
    verify: dict | None,
    env: dict,
    log_path: Path,
    report_path: Path,
    stopped: str | None,
) -> None:
    base = state.get("baseline") or {}
    plan = state.get("plan_summary") or {}
    copy = state.get("copy") or {}
    anno = state["anno_name"]
    lines: list[str] = []
    a = lines.append
    a(f"# neo4j-v4 导入标注 `{anno}` 报告（v4 / flag-true）")
    a("")
    a(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.import_annotation_v4`。")
    a(f"只 SET `n.{anno} = true`（布尔）；内容留在仓库 JSON，不写入图谱；未运行 build_v4.py；未打印密码。")
    a("")
    a("## 摘要")
    a("")
    a(
        f"1. **文件复制**：dest=`{copy.get('dest')}`；size={copy.get('size')}；"
        f"SHA={copy.get('sha')}；与源一致={copy.get('sha_ok')}；记录数={copy.get('n_records')}。"
    )
    gi = copy.get("gitignore") or {}
    a(f"2. **gitignore**：相关规则={gi.get('root_rules_related')}；check-ignore={gi.get('check_ignore')}。")
    if base:
        a(
            f"3. **基线**：节点={base.get('nodes_total')} {base.get('labels')}；关系={base.get('rels_total')} {base.get('by_type')}；"
            f"same_as={base.get('same_as_n')}/{base.get('no_same_as_n')}；TP keys={base.get('node_keys', {}).get('Truth_Point')}；"
            f"expect_anno={state.get('expect_anno')}。"
        )
    else:
        a("3. **基线**：尚未 check。")
    a(
        f"4. **匹配**：找到={plan.get('found_n')}；找不到={plan.get('missing')}；括号内={plan.get('hit_inner')}；多对一={plan.get('multi') or '无'}。"
    )
    if import_info and not import_info.get("aborted"):
        a(f"5. **写入**：写入={import_info.get('written')}；失败={import_info.get('failed')}。")
    elif import_info:
        a(f"5. **写入中止**：{import_info}")
    else:
        a(f"5. **写入**：尚未 import；拟写入={plan.get('write_count')}。")
    if verify:
        a(
            f"6. **验证**：ok={verify['ok']}；非空={verify.get('anno_count')}；全为 true={verify.get('all_true')}；"
            f"括号内={verify.get('inner_anno', {}).get('c')}；集合差 graph_only={verify.get('graph_only')} file_only={verify.get('file_only')}；"
            f"其他标注SHA={verify.get('other_anno_sha')}；fails={verify.get('fails') or '无'}。"
        )
    else:
        a("6. **验证**：尚未 verify。")
    a(f"7. **脚本**：新建 import_annotation_v4（复用 v1/v2）。差异：{state.get('v4_diff')}。")
    a(f"8. **待决**：stopped={stopped}；check_ok={state.get('check_ok')}；fails={state.get('fails') or '无'}。")
    a("")
    a("## copy / check / import / verify 明细")
    a(f"- copy: {json.dumps(copy, ensure_ascii=False, default=str)}")
    a(f"- plan: found={plan.get('found_n')} write={plan.get('write_count')} no_content={plan.get('no_content')}")
    a("## I. import")
    a("未执行。" if not import_info else f"```json\n{json.dumps(import_info, ensure_ascii=False, indent=2)}\n```")
    a("## V. verify")
    if not verify:
        a("未执行。")
    else:
        a(f"- samples: {verify.get('samples')}")
        a(f"- node_keys: {verify.get('node_keys')}")
        a(f"- dest_sha_ok: {verify.get('dest_sha_ok')}")
    a("")
    a("## 最终验证")
    draft = "\n".join(lines)
    leaked = bool(env["pass4"] and env["pass4"] in draft)
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    leaked_log = bool(env["pass4"] and env["pass4"] in log_text)
    a(f"- 对图谱只做了 SET {anno}=true：是（若已 import）")
    a("- 未运行 build_v4.py：是")
    a(f"- 报告密码检查：{'不通过' if leaked else '通过'}；日志：{'不通过' if leaked_log else '通过'}")
    a("- 未修改 import_annotation.py / _v2.py / _v3.py / .gitignore")
    a("")
    text = "\n".join(lines) + "\n"
    if env["pass4"] and env["pass4"] in text:
        raise SystemExit("中止：报告含密码")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


def stage_check(
    env: dict,
    log: v1.Logger,
    file_path: Path,
    anno_name: str,
    report_path: Path,
    expect_anno: dict[str, int],
    aliases: dict[str, str],
    expected_sha: str,
) -> int:
    log.log(f"v4 check file={file_path} name={anno_name}")
    # load copy state if present
    copy_state = {}
    try:
        copy_state = v1.load_state("organic_advance_copy")
    except SystemExit:
        copy_state = {}

    sha_import_before = v1._sha_import_dir()
    file_sha = _sha256(file_path)
    data = json.loads(file_path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise SystemExit("organic_advance.json 顶层须为 list")
    names = [r.get("name") for r in data]
    dups = [n for n, c in Counter(names).items() if c > 1]
    has_city = "城市" in names
    key_sets = Counter(tuple(r.keys()) for r in data)
    no_content = [r.get("name") for r in data if not _has_any_stage_content(r)]

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = v1.snapshot_graph(session)
            fails = v1.gate_baseline(base)
            tp_keys = {r["key"]: r["nonempty"] for r in base["node_keys"]["Truth_Point"]}
            expect_keys = {"name", "same_as"} | set(expect_anno)
            if set(tp_keys) != expect_keys:
                fails.append(f"基线 Truth_Point 标注名 {set(tp_keys)} ≠ {expect_keys}")
            existing_hashes: dict[str, dict[str, str]] = {}
            for prop, expected_n in expect_anno.items():
                actual_n = v2._anno_nonempty(session, prop)
                if actual_n != expected_n:
                    fails.append(f"已有标注 {prop} 非空 {actual_n} ≠ {expected_n}")
                amap = v2._fetch_anno_map(session, prop)
                # values may be bool/str; stringify for sha
                existing_hashes[prop] = {
                    n: v2._sha_text(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
                    for n, v in amap.items()
                }

            tp_rows = v1._run(
                session,
                """
                MATCH (n:Truth_Point)
                RETURN n.name AS name,
                       CASE WHEN n.same_as IS NULL OR toString(n.same_as)='' THEN null
                            ELSE n.same_as END AS same_as
                """,
            )
            by_name = {r["name"]: r for r in tp_rows}

            found = []
            missing = []
            hit_inner = []
            target_to_sources: dict[str, list[str]] = {}
            write_names = []
            for src in names:
                target = aliases.get(src, src)
                if target not in by_name:
                    missing.append(src)
                    continue
                if by_name[target]["same_as"] is not None:
                    hit_inner.append({"name": src, "target": target, "same_as": by_name[target]["same_as"]})
                    continue
                target_to_sources.setdefault(target, []).append(src)
                found.append(src)
                write_names.append(target)
            multi = {t: s for t, s in target_to_sources.items() if len(s) > 1}
    except Exception as exc:
        raise SystemExit("check 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_import_after = v1._sha_import_dir()
    fails = list(fails)
    if len(data) != 69:
        fails.append(f"记录数 {len(data)} ≠ 69")
    if dups:
        fails.append(f"name 重复: {dups}")
    if missing:
        fails.append(f"找不到 {len(missing)}: {missing}")
    if hit_inner:
        fails.append(f"括号内 {hit_inner}")
    if multi:
        fails.append(f"多对一 {multi}")
    if no_content:
        fails.append(f"无阶段内容: {no_content}")
    if file_sha != expected_sha:
        fails.append(f"仓库内文件 SHA {file_sha} ≠ 预期 {expected_sha}")
    if sha_import_before["hashes"] != sha_import_after["hashes"]:
        fails.append("可导入资料 SHA 变化")

    write_rows = [{"name": n, "value": True} for n in sorted(set(write_names))]
    gi = copy_state.get("gitignore") or _gitignore_report(file_path)
    state = {
        "version": 4,
        "mode": "flag-true",
        "check_ok": not fails,
        "fails": fails,
        "anno_name": anno_name,
        "file": str(file_path),
        "expect_anno": expect_anno,
        "aliases": aliases,
        "v4_diff": [
            "mode=flag-true：只 SET 布尔 true，不序列化内容",
            "另有 --stage copy 复制到 panai4/data/graph_annotations/",
            "batch=50；复用 v1/v2",
        ],
        "copy": {
            "src": copy_state.get("src"),
            "dest": str(file_path),
            "size": file_path.stat().st_size,
            "sha": file_sha,
            "sha_ok": file_sha == expected_sha,
            "n_records": len(data),
            "gitignore": gi,
        },
        "baseline": {k: v for k, v in base.items() if k != "tp_props"},
        "tp_props": base["tp_props"],
        "existing_anno_sha256": existing_hashes,
        "plan_summary": {
            "n_records": len(data),
            "dups": dups,
            "has_city": has_city,
            "key_sets": [{"keys": list(k), "count": c} for k, c in key_sets.most_common()],
            "no_content": no_content,
            "found_n": len(found),
            "missing": missing,
            "hit_inner": hit_inner,
            "multi": multi,
            "write_count": len(write_rows),
            "write_names": [r["name"] for r in write_rows],
        },
        "write_rows": write_rows,
        "file_names": names,
        "sha_import_before": sha_import_before,
        "sha_import_after_check": sha_import_after,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    v1.save_state(anno_name, state)
    write_report(state, None, None, env, log.path, report_path, None if not fails else "check")
    for f in fails:
        log.log("GATE FAIL: " + f)
    if fails:
        log.log("闸门未通过，停止。")
        return 2
    log.log(f"闸门通过。拟写入 {len(write_rows)}")
    return 0


def stage_import(env: dict, log: v1.Logger, file_path: Path, anno_name: str, report_path: Path) -> int:
    state = v1.load_state(anno_name)
    if state.get("version") != 4 or state.get("mode") != "flag-true" or not state.get("check_ok"):
        log.log("v4 check 未通过，拒绝 import")
        return 2
    if Path(state["file"]).resolve() != file_path.resolve():
        log.log("文件路径与 check 不一致")
        return 2
    base = state["baseline"]
    write_rows = state["write_rows"]
    expect_anno = state.get("expect_anno") or {}
    log.log(f"v4 import 拟写入 {len(write_rows)}（布尔 true）")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    written = 0
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            now = v1.snapshot_graph(session)
            light_now = {k: now[k] for k in ("nodes_total", "labels", "rels_total", "by_type", "same_as_n")}
            light_base = {k: base[k] for k in ("nodes_total", "labels", "rels_total", "by_type", "same_as_n")}
            if light_now != light_base:
                write_report(state, {"aborted": True, "reason": "I1"}, None, env, log.path, report_path, "import-I1")
                return 2
            for prop, expected_n in expect_anno.items():
                if v2._anno_nonempty(session, prop) != expected_n:
                    write_report(state, {"aborted": True, "reason": prop}, None, env, log.path, report_path, "import-I1")
                    return 2
            log.log("I1 通过")
            for i in range(0, len(write_rows), _BATCH):
                batch = write_rows[i : i + _BATCH]
                # Neo4j driver accepts Python True as boolean
                rows = [{"name": r["name"], "value": True} for r in batch]
                updated = session.execute_write(v1._set_batch, anno_name, rows)
                if updated != len(batch):
                    write_report(
                        state,
                        {"aborted": True, "written": written, "failed_batch_start": i,
                         "failed_names": [r["name"] for r in batch]},
                        None, env, log.path, report_path, "import-batch",
                    )
                    return 2
                written += updated
                log.log(f"batch {i}-{i+len(batch)-1} updated={updated} cumulative={written}")
    except Exception as exc:
        raise SystemExit("import 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    info = {"aborted": False, "written": written, "failed": 0, "expected": len(write_rows)}
    state["import"] = info
    v1.save_state(anno_name, state)
    write_report(state, info, None, env, log.path, report_path, None)
    log.log(f"import 完成 written={written}")
    return 0


def stage_verify(
    env: dict,
    log: v1.Logger,
    file_path: Path,
    anno_name: str,
    report_path: Path,
    expected_sha: str,
) -> int:
    state = v1.load_state(anno_name)
    if state.get("version") != 4 or state.get("mode") != "flag-true":
        log.log("状态不是 v4 flag-true")
        return 2
    base = state["baseline"]
    plan = state["plan_summary"]
    expect_anno = state.get("expect_anno") or {}
    existing_sha = state.get("existing_anno_sha256") or {}
    file_names = set(state["file_names"])
    expected_write = plan["write_count"]
    sha_import_before = state["sha_import_before"]
    log.log("v4 verify")

    samples_want = [
        "召会生活", "基督的身位", "基督的工作", "基督的神性", "基督的人性",
        "帐幕", "圣殿", "信", "金灯台",
    ]

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            now = v1.snapshot_graph(session)
            anno_count = v2._anno_nonempty(session, anno_name)
            typed = v1._run(
                session,
                f"""
                MATCH (n:Truth_Point)
                WHERE n.{anno_name} IS NOT NULL
                RETURN n.name AS name, n.{anno_name} AS value,
                       valueType(n.{anno_name}) AS vtype
                ORDER BY name
                """,
            )
            true_count = sum(1 for r in typed if r["value"] is True)
            not_true = [{"name": r["name"], "value": r["value"], "vtype": r["vtype"]} for r in typed if r["value"] is not True]
            inner_anno = v1._run(
                session,
                f"""
                MATCH (n:Truth_Point)
                WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
                  AND n.{anno_name} IS NOT NULL
                RETURN count(n) AS c, collect(n.name) AS names
                """,
            )[0]
            graph_names = {r["name"] for r in typed}
            samples = []
            for name in samples_want:
                rows = v1._run(
                    session,
                    f"MATCH (n:Truth_Point {{name:$name}}) RETURN n.{anno_name} AS value",
                    {"name": name},
                )
                samples.append({"name": name, "value": rows[0]["value"] if rows else None, "present": bool(rows)})

            other_sha_check = {}
            for prop, before_map in existing_sha.items():
                now_map = v2._fetch_anno_map(session, prop)
                now_sha = {
                    n: v2._sha_text(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
                    for n, v in now_map.items()
                }
                other_sha_check[prop] = {
                    "before_n": len(before_map),
                    "now_n": len(now_map),
                    "sha_mismatch": sum(1 for n, h in before_map.items() if now_sha.get(n) != h),
                    "only_before": sorted(set(before_map) - set(now_map))[:10],
                    "only_now": sorted(set(now_map) - set(before_map))[:10],
                }
    except Exception as exc:
        raise SystemExit("verify 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_import_now = v1._sha_import_dir()
    dest_sha = _sha256(file_path)
    fails = []
    if anno_count != expected_write:
        fails.append(f"V1 非空 {anno_count}≠{expected_write}")
    if true_count != expected_write or not_true:
        fails.append(f"V1 非全部 true: true_count={true_count} not_true={not_true[:10]}")
    if inner_anno["c"] != 0:
        fails.append(f"V1 括号内有标注 {inner_anno}")

    if now["nodes_total"] != base["nodes_total"] or now["labels"] != base["labels"]:
        fails.append("V2 节点变化")
    if now["rels_total"] != base["rels_total"] or now["by_type"] != base["by_type"]:
        fails.append("V2 关系变化")
    base_map = {r["name"]: r.get("same_as") for r in state["tp_props"]}
    now_map = {r["name"]: r.get("same_as") for r in now["tp_props"]}
    diff_props = sum(1 for k, v in base_map.items() if now_map.get(k) != v)
    if diff_props or set(base_map) != set(now_map):
        fails.append(f"V2 name/same_as 不同={diff_props}")
    for prop, chk in other_sha_check.items():
        if chk["sha_mismatch"] or chk["only_before"] or chk["only_now"] or chk["now_n"] != chk["before_n"]:
            fails.append(f"V2 已有标注 {prop} 变化 {chk}")
        if expect_anno.get(prop) is not None and chk["now_n"] != expect_anno[prop]:
            fails.append(f"V2 {prop} 非空 {chk['now_n']}≠{expect_anno[prop]}")

    graph_only = sorted(graph_names - file_names)
    file_only = sorted(file_names - graph_names)
    if graph_only or file_only:
        fails.append(f"V3 集合差 graph_only={graph_only} file_only={file_only}")

    tp_keys = {r["key"] for r in now["node_keys"]["Truth_Point"]}
    expect_keys = {"name", "same_as", anno_name} | set(expect_anno)
    if tp_keys != expect_keys:
        fails.append(f"V4 标注名 {tp_keys} ≠ {expect_keys}")
    for lab in ("Trunk", "Branch"):
        if {r["key"] for r in now["node_keys"][lab]} != {"name"}:
            fails.append(f"V4 {lab} 标注异常")

    if sha_import_now["hashes"] != sha_import_before["hashes"]:
        fails.append("V5 可导入资料 SHA 变化")
    if dest_sha != expected_sha:
        fails.append(f"V5 仓库文件 SHA {dest_sha}≠{expected_sha}")

    def _ci_sig(rows):
        out = []
        for r in rows:
            out.append({k: r.get(k) for k in ("name", "type", "entityType", "labelsOrTypes", "properties", "state") if k in r})
        return sorted(out, key=lambda x: str(x.get("name")))

    if _ci_sig(now["constraints"]) != _ci_sig(base["constraints"]):
        fails.append("V5 CONSTRAINTS 变化")
    if _ci_sig(now["indexes"]) != _ci_sig(base["indexes"]):
        fails.append("V5 INDEXES 变化")

    verify = {
        "ok": not fails,
        "fails": fails,
        "anno_count": anno_count,
        "all_true": true_count == anno_count and not not_true,
        "true_count": true_count,
        "not_true": not_true,
        "inner_anno": inner_anno,
        "graph_only": graph_only,
        "file_only": file_only,
        "other_anno_sha": other_sha_check,
        "samples": samples,
        "node_keys": now["node_keys"],
        "dest_sha_ok": dest_sha == expected_sha,
        "dest_sha": dest_sha,
        "sha_import_ok": sha_import_now["hashes"] == sha_import_before["hashes"],
    }
    state["verify"] = verify
    v1.save_state(anno_name, state)
    write_report(state, state.get("import"), verify, env, log.path, report_path, None if not fails else "verify")
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        return 2
    log.log("verify 全部通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 Truth_Point 布尔标记标注（v4）")
    parser.add_argument("--stage", required=True, choices=["copy", "check", "import", "verify"])
    parser.add_argument("--file", required=True, help="源文件（copy）或仓库内文件（check/import/verify）")
    parser.add_argument("--dest", default="", help="copy 目标路径")
    parser.add_argument("--name", default="organic_advance", help="标注名")
    parser.add_argument("--report", default="")
    parser.add_argument("--expect-anno", action="append", default=[])
    parser.add_argument("--alias", action="append", default=[])
    parser.add_argument("--expected-sha", default=_EXPECTED_SHA)
    parser.add_argument("--expected-size", type=int, default=_EXPECTED_SIZE)
    args = parser.parse_args()

    if not _PROP_NAME_RE.fullmatch(args.name):
        raise SystemExit(f"标注名不合法: {args.name}")
    file_path = Path(args.file)
    report_path = (
        Path(args.report)
        if args.report
        else _REPO / "docs" / "panai4_graph" / f"import_{args.name}.md"
    )
    expect_anno = v2._parse_expect_anno(args.expect_anno)
    aliases = _parse_aliases(args.alias)

    env = v1._load_env()
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = v1.Logger(_LOG_DIR / f"import_annotation_v4_{args.name}_{v1._now()}.log", env["pass4"])
    log.log(f"stage={args.stage} name={args.name}（v4；密码不记录）")

    if args.stage == "copy":
        if not args.dest:
            raise SystemExit("copy 需要 --dest")
        return stage_copy(env, log, file_path, Path(args.dest), args.expected_sha, args.expected_size, report_path)
    if not file_path.is_file():
        raise SystemExit(f"文件不存在: {file_path}")
    if args.stage == "check":
        return stage_check(env, log, file_path, args.name, report_path, expect_anno, aliases, args.expected_sha)
    if args.stage == "import":
        return stage_import(env, log, file_path, args.name, report_path)
    return stage_verify(env, log, file_path, args.name, report_path, args.expected_sha)


if __name__ == "__main__":
    sys.exit(main())
