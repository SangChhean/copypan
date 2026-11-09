# qa4 ES 导入脚本报告（C-2）
> 只写脚本与离线验证；**未**连接 9200/9202；**未** compose up/down；未改容器/卷。
> 日期：2026-11-09。

## 1. 与包内 import_to_local_es.py 的差异
- mapping/settings 常量块（`DENSE_EMB`/`OUTLINE_MAPPING`/`BIBLE_MAPPING`/`HYMNS_MAPPING`/`inherit_mapping`/`PANO_MAPPING`/`INDEX_SPECS`）逐字一致：**True**

完整 unified diff：

```diff
--- import_to_local_es.py
+++ es_import.py
@@ -1,15 +1,13 @@
 # -*- coding: utf-8 -*-
-"""将 PanAI 4.0 数据包中的十个 ES 索引导入本机 Elasticsearch 8.x。
+"""将 PanAI 4.0 数据包中的十个 ES 索引导入本机 qa4-es（目标名 qa4_*，不重算向量）。
 
 用法示例：
-  python import_to_local_es.py --dry-run
-  python import_to_local_es.py --es-url http://localhost:9200
-  python import_to_local_es.py --only panai4_bible
-  python import_to_local_es.py --force --only panai4_bible
-  python import_to_local_es.py --index-suffix __verify   # 仅测试用临时索引名
-
-不写死任何主机/账号/密码。账号密码来自 --user/--password 或环境变量 ES_USER/ES_PASSWORD
-（兼容 ES_USERNAME）。
+  python es_import.py --data-root <解压后 es/data> --offline --dry-run
+  python es_import.py --data-root <解压后 es/data> --only panai4_hymns panai4_bible
+  python es_import.py --data-root <解压后 es/data> --force --only panai4_bible
+
+密码只从环境变量 QA4_ES_PASSWORD 读取，无命令行密码参数；日志不得出现密码。
+默认目标 http://127.0.0.1:9202 ，用户 elastic，HTTP 无 SSL。
 """
 
 from __future__ import annotations
@@ -17,10 +15,12 @@
 import argparse
 import hashlib
 import json
+import logging
 import os
 import sys
 import time
 from copy import deepcopy
+from datetime import datetime
 from pathlib import Path
 from typing import Any, Iterable, Iterator
 
@@ -32,8 +32,13 @@
     raise
 
 HERE = Path(__file__).resolve().parent
-DEFAULT_DATA_ROOT = HERE / "data"
-MANIFEST_JSON = HERE.parent / "MANIFEST.json"  # optional sibling; also try HERE/MANIFEST.json
+DEFAULT_LOG_DIR = Path(r"G:\PanAI4.0专用\logs")
+SOURCE_PREFIX = "panai4_"
+DEFAULT_INDEX_PREFIX = "qa4_"
+DEFAULT_ES_URL = "http://127.0.0.1:9202"
+DEFAULT_ES_USER = "elastic"
+REQUIRED_CLUSTER_NAME = "qa4"
+
 VEC_DIMS = 1024
 BULK_SIZE = 200
 
@@ -367,6 +372,29 @@
     return n
 
 
+def files_total_bytes(paths: list[Path]) -> int:
+    return sum(p.stat().st_size for p in paths)
+
+
+def target_index_name(source: str, index_prefix: str, index_suffix: str) -> str:
+    if not source.startswith(SOURCE_PREFIX):
+        raise ValueError(f"源索引名必须以 {SOURCE_PREFIX!r} 开头: {source}")
+    stem = source[len(SOURCE_PREFIX) :]
+    return f"{index_prefix}{stem}{index_suffix or ''}"
+
+
+def assert_safe_target(target: str) -> None:
+    """任何一条不满足即中止（调用方须在写操作之前调用）。"""
+    if "*" in target or "?" in target:
+        raise SystemExit(f"拒绝：目标索引名含通配符: {target}")
+    if not target.startswith(DEFAULT_INDEX_PREFIX):
+        raise SystemExit(f"拒绝：目标索引名必须以 {DEFAULT_INDEX_PREFIX!r} 开头: {target}")
+    if target.startswith(SOURCE_PREFIX):
+        raise SystemExit(f"拒绝：禁止以 panai4_* 作为目标: {target}")
+    if target.startswith("kg-rag_") or target.startswith("kg_rag_"):
+        raise SystemExit(f"拒绝：禁止以 kg-rag_* 作为目标: {target}")
+
+
 def row_to_action(index: str, target_index: str, row: dict) -> dict | None:
     spec = INDEX_SPECS[index]
     kind = spec["kind"]
@@ -406,11 +434,14 @@
     raise ValueError(f"unknown kind {kind}")
 
 
-def make_client(es_url: str, user: str | None, password: str | None) -> Elasticsearch:
-    kwargs: dict[str, Any] = {"hosts": [es_url], "request_timeout": 180}
-    if user is not None and password is not None:
-        kwargs["basic_auth"] = (user, password)
-    return Elasticsearch(**kwargs)
+def make_client(es_url: str, user: str, password: str) -> Elasticsearch:
+    return Elasticsearch(
+        hosts=[es_url],
+        basic_auth=(user, password),
+        request_timeout=180,
+        verify_certs=False,
+        ssl_show_warn=False,
+    )
 
 
 def check_es_version(es: Elasticsearch) -> str:
@@ -418,82 +449,84 @@
     ver = str(info.get("version", {}).get("number") or "")
     major = ver.split(".", 1)[0]
     if major != "8":
-        print(f"ERROR: 目标 ES 主版本为 {ver!r}，本数据包要求 8.x（建议 8.19.0）。", file=sys.stderr)
-        sys.exit(2)
+        raise SystemExit(f"ERROR: 目标 ES 主版本为 {ver!r}，本数据包要求 8.x（建议 8.19.0）。")
     return ver
 
 
-def dry_run(data_root: Path, indices: list[str], expect: dict[str, int], sums_path: Path | None) -> int:
-    print("=== dry-run：校验文件与文档数（不连 ES）===")
-    if sums_path and sums_path.is_file():
-        print(f"校验 SHA256SUMS: {sums_path}")
-        bad = 0
-        for line in sums_path.read_text(encoding="utf-8").splitlines():
-            line = line.strip()
-            if not line or line.startswith("#"):
-                continue
-            parts = line.split()
-            if len(parts) < 2:
-                continue
-            digest, rel = parts[0], parts[-1]
-            # paths in SHA file are relative to pack root; dry-run may be inside es/
-            cand = [
-                sums_path.parent / rel,
-                HERE.parent / rel,
-                Path(rel),
-            ]
-            path = next((p for p in cand if p.is_file()), None)
-            if path is None:
-                # only check files under data_root for this dry-run context
-                continue
-            if not str(path).replace("\\", "/").endswith(
-                tuple(f"/{idx}/" for idx in indices)
-            ) and "/es/" not in str(path).replace("\\", "/") and not any(
-                idx in str(path) for idx in indices
-            ):
-                # still verify if file exists under pack
-                pass
-            got = sha256_file(path)
-            if got.lower() != digest.lower():
-                print(f"  SHA_FAIL {rel}")
-                bad += 1
-        # Full SHA check of entire SUMS when possible
-        bad = 0
-        base = sums_path.parent
-        for line in sums_path.read_text(encoding="utf-8").splitlines():
-            line = line.strip()
-            if not line or line.startswith("#"):
-                continue
-            parts = line.split()
-            if len(parts) < 2:
-                continue
-            digest, rel = parts[0], parts[-1].lstrip("*")
-            path = base / rel
-            if not path.is_file():
-                print(f"  SHA_MISSING {rel}")
-                bad += 1
-                continue
-            got = sha256_file(path)
-            if got.lower() != digest.lower():
-                print(f"  SHA_FAIL {rel}")
-                bad += 1
-        if bad:
-            print(f"SHA 校验失败 {bad} 项")
-            return 1
-        print("SHA 校验通过")
-    else:
-        print("未找到 SHA256SUMS.txt，跳过哈希校验（仍核对文档数）")
-
-    ok = True
-    print(f"{'index':28} {'file_docs':>10} {'manifest':>10} {'match':>6}")
+def assert_cluster_name(es: Elasticsearch) -> str:
+    info = es.info()  # GET /
+    name = str(info.get("cluster_name") or "")
+    if name != REQUIRED_CLUSTER_NAME:
+        raise SystemExit(
+            f"中止：cluster_name={name!r}，必须等于 {REQUIRED_CLUSTER_NAME!r}。"
+            "未执行任何写操作。"
+        )
+    return name
+
+
+class _RedactingFilter(logging.Filter):
+    def __init__(self, secrets: list[str]):
+        super().__init__()
+        self._secrets = [s for s in secrets if s]
+
+    def filter(self, record: logging.LogRecord) -> bool:
+        msg = record.getMessage()
+        for s in self._secrets:
+            if s and s in msg:
+                msg = msg.replace(s, "***")
+        record.msg = msg
+        record.args = ()
+        return True
+
+
+def setup_logging(log_file: Path, secrets: list[str]) -> logging.Logger:
+    log_file.parent.mkdir(parents=True, exist_ok=True)
+    logger = logging.getLogger("qa4_es_import")
+    logger.handlers.clear()
+    logger.setLevel(logging.INFO)
+    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
+    fh = logging.FileHandler(log_file, encoding="utf-8")
+    fh.setFormatter(fmt)
+    fh.addFilter(_RedactingFilter(secrets))
+    sh = logging.StreamHandler(sys.stdout)
+    sh.setFormatter(fmt)
+    sh.addFilter(_RedactingFilter(secrets))
+    logger.addHandler(fh)
+    logger.addHandler(sh)
+    return logger
+
+
+def offline_plan(
+    data_root: Path,
+    indices: list[str],
+    expect: dict[str, int],
+    index_prefix: str,
+    index_suffix: str,
+    log: logging.Logger,
+) -> int:
+    log.info("=== offline/dry-run：解析文件与导入计划（不连接 ES）===")
+    total_docs = 0
+    total_bytes = 0
+    log.info(
+        f"{'source':28} {'target':28} {'files':>6} {'bytes':>14} {'manifest':>10}"
+    )
     for idx in indices:
+        target = target_index_name(idx, index_prefix, index_suffix)
+        assert_safe_target(target)
         paths = resolve_files(idx, data_root)
-        n = count_jsonl(paths)
-        exp = expect[idx]
-        match = n == exp
-        ok = ok and match
-        print(f"{idx:28} {n:10d} {exp:10d} {str(match):>6}  files={len(paths)}")
-    return 0 if ok else 1
+        nbytes = files_total_bytes(paths)
+        exp = int(expect[idx])
+        total_docs += exp
+        total_bytes += nbytes
+        log.info(
+            f"{idx:28} {target:28} {len(paths):6d} {nbytes:14d} {exp:10d}"
+        )
+    log.info(f"MANIFEST 期望文档数合计 = {total_docs}")
+    log.info(f"文件总字节 = {total_bytes}")
+    if total_docs != 414082 and set(indices) == set(INDEX_SPECS.keys()):
+        log.error(f"期望文档数之和应为 414082，实际 {total_docs}")
+        return 1
+    return 0
 
 
 def import_one(
@@ -502,31 +535,41 @@
     data_root: Path,
     *,
     force: bool,
+    index_prefix: str,
     index_suffix: str,
     expect: dict[str, int],
+    log: logging.Logger,
 ) -> tuple[bool, int, int]:
     spec = INDEX_SPECS[index]
-    target = f"{index}{index_suffix}"
+    target = target_index_name(index, index_prefix, index_suffix)
+    assert_safe_target(target)
+
     paths = resolve_files(index, data_root)
     file_docs = count_jsonl(paths)
     exp = expect[index]
     if file_docs != exp:
-        print(f"FAIL {index}: 包内文档数 {file_docs} != MANIFEST {exp}")
+        log.error(f"FAIL {index}: 包内文档数 {file_docs} != MANIFEST {exp}")
         return False, file_docs, -1
 
-    exists = es.indices.exists(index=target)
+    exists = bool(es.indices.exists(index=target))
     if exists and not force:
         cur = int(es.count(index=target)["count"])
-        print(f"SKIP {target}: 已存在（docs={cur}）。如需重建请加 --force")
-        return True, file_docs, cur
+        log.error(
+            f"中止 {target}: 已存在（docs={cur}）。默认拒绝覆盖；"
+            "仅当 --force 且目标为明确列出的 qa4_* 时可删除重建。"
+        )
+        return False, file_docs, cur
 
     if exists and force:
+        # 再保险：禁止通配、必须 qa4_
+        assert_safe_target(target)
         cur = int(es.count(index=target)["count"])
-        print(f"FORCE 将删除索引 {target}（现有文档数={cur}）")
+        log.info(f"FORCE 将删除索引 {target}（现有文档数={cur}）")
         es.indices.delete(index=target)
 
     body = deepcopy(spec["mapping"])
-    print(f"CREATE {target}")
+    # 与原脚本一致：直接用 mapping 创建，不在导入期间改 refresh_interval 等 settings
+    log.info(f"CREATE {target}")
     es.indices.create(index=target, body=body)
 
     def gen():
@@ -548,91 +591,248 @@
     elapsed = time.perf_counter() - t0
     err_n = len(errors) if errors else 0
     final = int(es.count(index=target)["count"])
-    print(
+    log.info(
         f"DONE {target}: bulk_ok={ok_n} bulk_err={err_n} count={final} expect={exp} "
         f"elapsed={elapsed:.1f}s"
     )
     if errors:
-        print("sample_error", json.dumps(errors[0], ensure_ascii=False)[:400])
-    return final == exp and err_n == 0, file_docs, final
-
-
-def parse_args() -> argparse.Namespace:
-    p = argparse.ArgumentParser(description="Import PanAI4.0 ES pack into local Elasticsearch 8.x")
-    p.add_argument("--es-url", default="http://localhost:9200", help="ES URL")
-    p.add_argument("--user", default=None, help="ES username (else env ES_USER / ES_USERNAME)")
-    p.add_argument("--password", default=None, help="ES password (else env ES_PASSWORD)")
-    p.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT), help="es/data 目录")
-    p.add_argument("--only", default=None, help="只导入一个索引名")
-    p.add_argument("--force", action="store_true", help="删除已存在的目标索引后重建")
-    p.add_argument("--dry-run", action="store_true", help="只校验文件/SHA，不连 ES")
+        log.error("sample_error " + json.dumps(errors[0], ensure_ascii=False)[:400])
+    if final != exp or err_n != 0:
+        log.error(f"FAIL {target}: 导入后文档数/错误不达标 count={final} expect={exp} err={err_n}")
+        return False, file_docs, final
+    return True, file_docs, final
+
+
+def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
+    p = argparse.ArgumentParser(description="Import PanAI4.0 ES pack into qa4-es as qa4_* indices")
+    p.add_argument("--data-root", required=True, help="解压出的 es/data 目录（必需）")
+    p.add_argument("--es-url", default=DEFAULT_ES_URL, help="ES URL（默认 http://127.0.0.1:9202）")
+    p.add_argument("--user", default=DEFAULT_ES_USER, help="ES 用户名（默认 elastic）")
+    p.add_argument(
+        "--only",
+        nargs="+",
+        default=None,
+        help="只导入指定源索引名（可多个，如 panai4_hymns panai4_bible）",
+    )
+    p.add_argument("--force", action="store_true", help="删除已存在且以 qa4_ 开头的明确目标索引后重建")
+    p.add_argument("--dry-run", action="store_true", help="只解析/校验，不写 ES")
+    p.add_argument(
+        "--offline",
+        action="store_true",
+        help="与 --dry-run 合用：不连接 ES，只解析文件并打印计划",
+    )
+    p.add_argument(
+        "--index-prefix",
+        default=DEFAULT_INDEX_PREFIX,
+        help="目标索引前缀（默认 qa4_）",
+    )
     p.add_argument(
         "--index-suffix",
         default="",
-        help="目标索引名后缀（测试用，如 __verify）；正式导入请留空",
+        help="目标索引名后缀（测试用）；正式导入请留空",
     )
     p.add_argument(
-        "--sha-file",
+        "--log-file",
         default=None,
-        help="SHA256SUMS.txt 路径（dry-run 时校验）",
-    )
-    return p.parse_args()
-
-
-def main() -> int:
-    args = parse_args()
+        help="日志路径（默认 G:\\PanAI4.0专用\\logs\\qa4_import_<时间戳>.log）",
+    )
+    p.add_argument(
+        "--self-test",
+        action="store_true",
+        help="不连 ES 的自测（映射/拒绝/假密码脱敏）",
+    )
+    return p.parse_args(argv)
+
+
+def run_self_test(log: logging.Logger) -> int:
+    log.info("=== self-test（不连接 ES）===")
+    ok = True
+
+    # 1) 十个源名 → qa4_*
+    for src in INDEX_SPECS:
+        tgt = target_index_name(src, DEFAULT_INDEX_PREFIX, "")
+        try:
+            assert_safe_target(tgt)
+        except SystemExit as e:
+            log.error(f"映射失败 {src} -> {tgt}: {e}")
+            ok = False
+            continue
+        expect = DEFAULT_INDEX_PREFIX + src[len(SOURCE_PREFIX) :]
+        if tgt != expect:
+            log.error(f"映射错误 {src} -> {tgt} 期望 {expect}")
+            ok = False
+        else:
+            log.info(f"MAP_OK {src} -> {tgt}")
+
+    # 2) 拒绝危险目标
+    for bad in ("panai4_bible", "kg-rag_life", "qa4_*"):
+        try:
+            assert_safe_target(bad)
+            log.error(f"REJECT_FAIL 应拒绝但未拒绝: {bad}")
+            ok = False
+        except SystemExit:
+            log.info(f"REJECT_OK {bad}")
+
+    # 3) 模拟 cluster_name 非 qa4：在写之前中止，且无写调用
+    class _FakeES:
+        def __init__(self):
+            self.writes = []
+            self.indices = self
+
+        def info(self):
+            return {"cluster_name": "docker-cluster", "version": {"number": "8.19.0"}}
+
+        def exists(self, index=None):
+            self.writes.append(("exists", index))
+            return False
+
+        def create(self, **kwargs):
+            self.writes.append(("create", kwargs))
+
+        def delete(self, **kwargs):
+            self.writes.append(("delete", kwargs))
+
+        def count(self, **kwargs):
+            self.writes.append(("count", kwargs))
+            return {"count": 0}
+
+        def refresh(self, **kwargs):
+            self.writes.append(("refresh", kwargs))
+
+    fake = _FakeES()
+    write_before = list(fake.writes)
+    try:
+        assert_cluster_name(fake)
+        log.error("CLUSTER_FAIL 应因 cluster_name 中止")
+        ok = False
+    except SystemExit as e:
+        log.info(f"CLUSTER_OK 中止: {e}")
+    if fake.writes != write_before:
+        log.error(f"CLUSTER_FAIL 发生了写相关调用: {fake.writes}")
+        ok = False
+    else:
+        log.info("CLUSTER_OK 无写调用")
+
+    # 4) 假密码不得出现在日志消息路径（过滤器）
+    secret = "FAKE_SECRET_PASSWORD_XYZ_9977"
+    filt = _RedactingFilter([secret])
+    rec = logging.LogRecord(
+        name="t", level=logging.INFO, pathname=__file__, lineno=1,
+        msg=f"auth with {secret} ok", args=(), exc_info=None,
+    )
+    filt.filter(rec)
+    if secret in rec.getMessage():
+        log.error("REDACT_FAIL 密码仍出现在日志记录中")
+        ok = False
+    else:
+        log.info("REDACT_OK 日志记录已脱敏")
+
+    return 0 if ok else 1
+
+
+def main(argv: list[str] | None = None) -> int:
+    args = parse_args(argv)
+
+    password = os.environ.get("QA4_ES_PASSWORD") or ""
+    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
+    log_file = Path(args.log_file) if args.log_file else (DEFAULT_LOG_DIR / f"qa4_import_{ts}.log")
+    log = setup_logging(log_file, [password] if password else [])
+    log.info(f"log_file={log_file}")
+
+    if args.self_test:
+        code = run_self_test(log)
+        log.info(f"self-test exit={code}")
+        return code
+
+    if args.offline and not args.dry_run:
+        log.error("--offline 必须与 --dry-run 合用")
+        return 1
+
+    if not args.index_prefix.startswith(DEFAULT_INDEX_PREFIX):
+        # 允许仅等于 qa4_；若用户改前缀也必须仍以 qa4_ 开头
+        log.error(f"--index-prefix 必须以 {DEFAULT_INDEX_PREFIX!r} 开头，收到 {args.index_prefix!r}")
+        return 1
+
     data_root = Path(args.data_root)
     if not data_root.is_dir():
-        print(f"数据目录不存在: {data_root}", file=sys.stderr)
+        log.error(f"数据目录不存在: {data_root}")
         return 1
 
     if args.only:
-        if args.only not in INDEX_SPECS:
-            print(f"未知索引: {args.only}", file=sys.stderr)
-            return 1
-        indices = [args.only]
+        indices = list(args.only)
+        for idx in indices:
+            if idx not in INDEX_SPECS:
+                log.error(f"未知索引: {idx}")
+                return 1
     else:
         indices = list(INDEX_SPECS.keys())
+
+    # 预检全部目标名（任何写之前）
+    for idx in indices:
+        try:
+            tgt = target_index_name(idx, args.index_prefix, args.index_suffix or "")
+            assert_safe_target(tgt)
+        except (ValueError, SystemExit) as e:
+            log.error(str(e))
+            return 1
 
     expect = load_manifest_expect(data_root)
     for idx in indices:
         if idx not in expect:
             expect[idx] = INDEX_SPECS[idx]["expect"]
 
-    sha_file = Path(args.sha_file) if args.sha_file else (data_root.parent.parent / "SHA256SUMS.txt")
-
-    if args.dry_run:
-        return dry_run(data_root, indices, expect, sha_file if sha_file.is_file() else None)
-
-    user = args.user or os.environ.get("ES_USER") or os.environ.get("ES_USERNAME")
-    password = args.password if args.password is not None else os.environ.get("ES_PASSWORD")
-    # allow empty password only if explicitly provided; otherwise optional auth
-    es = make_client(args.es_url, user, password if user is not None else None)
-    if not es.ping():
-        print("无法连接 ES（ping 失败）。请检查 --es-url / 账号密码。", file=sys.stderr)
+    if args.dry_run or args.offline:
+        return offline_plan(
+            data_root,
+            indices,
+            expect,
+            args.index_prefix,
+            args.index_suffix or "",
+            log,
+        )
+
+    if not password:
+        log.error("环境变量 QA4_ES_PASSWORD 未设置或为空")
         return 1
-    ver = check_es_version(es)
-    print(f"ES version {ver} @ {args.es_url}")
+
+    es = make_client(args.es_url, args.user, password)
+    # 连接后先 GET / 校验 cluster_name，再做任何写
+    try:
+        if not es.ping():
+            log.error("无法连接 ES（ping 失败）。请检查 --es-url / QA4_ES_PASSWORD。")
+            return 1
+        ver = check_es_version(es)
+        cname = assert_cluster_name(es)
+        log.info(f"ES version {ver} cluster_name={cname} @ {args.es_url}")
+    except SystemExit as e:
+        log.error(str(e))
+        return 1
 
     rows = []
-    all_ok = True
     for idx in indices:
         ok, file_n, es_n = import_one(
             es,
             idx,
             data_root,
             force=args.force,
+            index_prefix=args.index_prefix,
             index_suffix=args.index_suffix or "",
             expect=expect,
+            log=log,
         )
         rows.append((idx, file_n, es_n, ok))
-        all_ok = all_ok and ok
-
-    print("\n=== 文档数对照 ===")
-    print(f"{'index':28} {'pack':>10} {'es':>10} {'ok':>6}")
+        if not ok:
+            log.error(f"索引导入失败，停止后续：{idx}")
+            log.info("\n=== 文档数对照（部分）===")
+            for i2, f2, e2, o2 in rows:
+                log.info(f"{i2:28} pack={f2} es={e2} ok={o2}")
+            return 1
+
+    log.info("\n=== 文档数对照 ===")
+    log.info(f"{'index':28} {'pack':>10} {'es':>10} {'ok':>6}")
     for idx, file_n, es_n, ok in rows:
-        print(f"{idx:28} {file_n:10d} {es_n:10d} {str(ok):>6}")
-    return 0 if all_ok else 1
+        log.info(f"{idx:28} {file_n:10d} {es_n:10d} {str(ok):>6}")
+    return 0
 
 
 if __name__ == "__main__":
```

预期改动仅限：模块说明、默认目标 `127.0.0.1:9202`、`--index-prefix`/`--offline`/`--log-file`、目标名映射、cluster_name/目标名保险、密码仅 `QA4_ES_PASSWORD`、失败即停与日志脱敏。

## 2. 离线计划（--offline --dry-run）

`--data-root G:\PanAI4.0专用\数据包\_stage_es\es\data`，exit=0。

```text
2026-11-09 09:37:03,609 INFO log_file=G:\copypan\qa4\data_prep\_offline_plan.log
2026-11-09 09:37:03,611 INFO === offline/dry-run：解析文件与导入计划（不连接 ES）===
2026-11-09 09:37:03,612 INFO source                       target                        files          bytes   manifest
2026-11-09 09:37:03,612 INFO panai4_outline_12490         qa4_outline_12490                 1     1386795176      55841
2026-11-09 09:37:03,613 INFO panai4_outline_feasts        qa4_outline_feasts                1      278483135      11110
2026-11-09 09:37:03,614 INFO panai4_bible                 qa4_bible                         1       91283031       3691
2026-11-09 09:37:03,614 INFO panai4_hymns                 qa4_hymns                         1      214410176       9154
2026-11-09 09:37:03,621 INFO panai4_text_life             qa4_text_life                    20      982971035      39463
2026-11-09 09:37:03,646 INFO panai4_text_cwwl             qa4_text_cwwl                    90     4475183876     178107
2026-11-09 09:37:03,650 INFO panai4_text_cwwn             qa4_text_cwwn                    17      806282342      32032
2026-11-09 09:37:03,653 INFO panai4_text_others           qa4_text_others                   8      385268164      15481
2026-11-09 09:37:03,655 INFO panai4_map_note              qa4_map_note                      9      391960028      16052
2026-11-09 09:37:03,655 INFO panai4_pano_catalog          qa4_pano_catalog                  1       50383000      53151
2026-11-09 09:37:03,655 INFO MANIFEST 期望文档数合计 = 414082
2026-11-09 09:37:03,656 INFO 文件总字节 = 9063019963
```

期望文档数之和 = **414082**（要求 414082）。

## 3. 自测（--self-test，不连 ES）

exit=0。环境中设置假密码仅用于验证脱敏（值不写入本报告正文以外的永久配置）。

```text
2026-11-09 09:37:05,056 INFO log_file=G:\copypan\qa4\data_prep\_self_test.log
2026-11-09 09:37:05,057 INFO === self-test（不连接 ES）===
2026-11-09 09:37:05,057 INFO MAP_OK panai4_outline_12490 -> qa4_outline_12490
2026-11-09 09:37:05,057 INFO MAP_OK panai4_outline_feasts -> qa4_outline_feasts
2026-11-09 09:37:05,057 INFO MAP_OK panai4_bible -> qa4_bible
2026-11-09 09:37:05,057 INFO MAP_OK panai4_hymns -> qa4_hymns
2026-11-09 09:37:05,057 INFO MAP_OK panai4_text_life -> qa4_text_life
2026-11-09 09:37:05,057 INFO MAP_OK panai4_text_cwwl -> qa4_text_cwwl
2026-11-09 09:37:05,058 INFO MAP_OK panai4_text_cwwn -> qa4_text_cwwn
2026-11-09 09:37:05,058 INFO MAP_OK panai4_text_others -> qa4_text_others
2026-11-09 09:37:05,058 INFO MAP_OK panai4_map_note -> qa4_map_note
2026-11-09 09:37:05,058 INFO MAP_OK panai4_pano_catalog -> qa4_pano_catalog
2026-11-09 09:37:05,058 INFO REJECT_OK panai4_bible
2026-11-09 09:37:05,058 INFO REJECT_OK kg-rag_life
2026-11-09 09:37:05,058 INFO REJECT_OK qa4_*
2026-11-09 09:37:05,059 INFO CLUSTER_OK 中止: 中止：cluster_name='docker-cluster'，必须等于 'qa4'。未执行任何写操作。
2026-11-09 09:37:05,059 INFO CLUSTER_OK 无写调用
2026-11-09 09:37:05,059 INFO REDACT_OK 日志记录已脱敏
2026-11-09 09:37:05,059 INFO self-test exit=0
```

假密码出现在 stdout/stderr：**False**；出现在日志文件：**False**。

## 4. es_unpack_pack.ps1 小规模实测

### 4.1 成功解压+核对

exit=0

```text
﻿
[2026-11-09 09:38:48] 计算 zip SHA256: C:\Users\28121\AppData\Local\Temp\qa4_unpack_demo2_aq7sf_gz\mini.zip
[2026-11-09 09:38:48] zip SHA256 = 6E1633967B9F72EF3B54F72A08972BCED011EDB661262646108E8C080A4B7C09
[2026-11-09 09:38:48] SHA256 与期望一致。
[2026-11-09 09:38:48] 开始解压到: C:\Users\28121\AppData\Local\Temp\qa4_unpack_demo2_aq7sf_gz\dest_ok
zip 文件条目数=4
解压后文件数=4
核对文件数=3 不一致=0
汇总: 文件数=4 总字节=259 核对结果=OK
解压与 SHA 核对全部通过。
[2026-11-09 09:38:49] 完成。日志: G:\PanAI4.0专用\logs\qa4_unpack_20261109_093848.log
```

解压后文件数=4（期望 4）。

### 4.2 拒绝：Dest 非空

exit=2

```text
﻿
[2026-11-09 09:38:49] Dest 已存在且非空，拒绝解压（无覆盖）: C:\Users\28121\AppData\Local\Temp\qa4_unpack_demo2_aq7sf_gz\dest_ok
```

### 4.3 拒绝：zip SHA 不符

exit=3

```text
﻿
[2026-11-09 09:38:50] 计算 zip SHA256: C:\Users\28121\AppData\Local\Temp\qa4_unpack_demo2_aq7sf_gz\mini.zip
[2026-11-09 09:38:50] zip SHA256 = 6E1633967B9F72EF3B54F72A08972BCED011EDB661262646108E8C080A4B7C09
[2026-11-09 09:38:50] SHA256 不一致，已中止。期望=0000000000000000000000000000000000000000000000000000000000000000 实际=6E1633967B9F72EF3B54F72A08972BCED011EDB661262646108E8C080A4B7C09
```

Dest 下残留条目数=0（SHA 失败应在解压前中止，期望 0）。

### 4.4 拒绝：解压后文件被改动（SHA 核对失败）

首次解压 exit=0；篡改 `sub/a.txt` 后按 SHA256SUMS 核对不一致数=1（期望 ≥1）。

内容与 SUMS 不一致的 zip：exit=7；Dest 文件数=4（解压后核对失败，脚本明确报告可能残留）。

```text
﻿
[2026-11-09 09:38:52] 计算 zip SHA256: C:\Users\28121\AppData\Local\Temp\qa4_unpack_demo2_aq7sf_gz\bad_content.zip
[2026-11-09 09:38:52] zip SHA256 = E7BF95223AA42B204C9CECBBDAE20FF2CC4E6EC7B101A53F0624F52D94AA485A
[2026-11-09 09:38:52] SHA256 与期望一致。
[2026-11-09 09:38:52] 开始解压到: C:\Users\28121\AppData\Local\Temp\qa4_unpack_demo2_aq7sf_gz\dest_mismatch
zip 文件条目数=4
解压后文件数=4
SHA_FAIL README.md
核对文件数=3 不一致=1
汇总: 文件数=4 总字节=272 核对结果=FAIL
[2026-11-09 09:38:52] 解压/核对失败，exit=7
[2026-11-09 09:38:52] 注意: Dest 中可能留有部分解压结果，文件数=4 路径=C:\Users\28121\AppData\Local\Temp\qa4_unpack_demo2_aq7sf_gz\dest_mismatch （请人工清理后重试）
```

## 5. PowerShell 5.1：BOM 与 Parser

- `es_unpack_pack.ps1` BOM=[239, 187, 191] (OK)
- `es_import_run.ps1` BOM=[239, 187, 191] (OK)

```text
es_unpack_pack.ps1 errors=0

es_import_run.ps1 errors=0
```

### 拒绝路径中文提示

exit=1

```text
﻿
[2026-11-09 09:38:53] 找不到 zip: G:\copypan\qa4\data_prep\_no_such_pack.zip
```

## 6. Docker 对照

docker ps -a / volume ls / images 与任务前完全相同：**True**

## 7. git status 与密码字面量

```text
?? docs/panai4_graph/export_pack.md
?? docs/panai4_graph/git_merge_conflict.md
?? docs/panai4_graph/git_merge_resolve.md
?? qa4/
```

`qa4/` 下疑似真实密码字面量命中数：0
（无）

## 8. 产物清单

- `qa4/data_prep/es_unpack_pack.ps1`
- `qa4/data_prep/es_import.py`
- `qa4/data_prep/es_import_run.ps1`
- `qa4/data_prep/README.md`（已更新运行顺序）
- 本报告

未对真实 `PanAI4.0_ES数据包_20261107.zip` 做解压；未连接任何 ES。

---

## 9. C-2b 小修订（--force/--only、期望值来源、refresh）

### 9.1 修订要点

1. `--force` 必须与 `--only` 同时使用；否则在连接前拒绝。
2. 期望文档数来源可见：日志打印 `MANIFEST.json` 路径或「内置默认」；dry-run 可回退；真实导入缺 MANIFEST 即中止。
3. 每个索引导入完成后，**先** `es.indices.refresh`，**再** `es.count`（已确认存在，并加注释）。

相关代码行：

```text
594:     # 导入完成后必须先 refresh，再读取 count（顺序不可颠倒）
595:     es.indices.refresh(index=target)
598:     final = int(es.count(index=target)["count"])
```

### 9.2a `--force` 不带 `--only`（离线）

exit=2；`make_client` 调用次数=0（期望 0）。

```text
2026-11-09 11:12:22,387 INFO log_file=G:\copypan\qa4\data_prep\_c2b_force.log
2026-11-09 11:12:22,387 ERROR 拒绝：--force 必须与 --only 同时使用；--force 只作用于 --only 明确列出的索引。未尝试连接 ES。
```

### 9.2b 离线 dry-run（`_stage_es\es\data`）

exit=0

```text
2026-11-09 11:12:23,959 INFO log_file=G:\copypan\qa4\data_prep\_c2b_manifest.log
2026-11-09 11:12:23,962 INFO 期望文档数来源: MANIFEST.json → G:\PanAI4.0专用\数据包\_stage_es\MANIFEST.json
2026-11-09 11:12:23,963 INFO === offline/dry-run：解析文件与导入计划（不连接 ES）===
2026-11-09 11:12:23,963 INFO source                       target                        files          bytes   manifest
2026-11-09 11:12:23,964 INFO panai4_outline_12490         qa4_outline_12490                 1     1386795176      55841
2026-11-09 11:12:23,964 INFO panai4_outline_feasts        qa4_outline_feasts                1      278483135      11110
2026-11-09 11:12:23,965 INFO panai4_bible                 qa4_bible                         1       91283031       3691
2026-11-09 11:12:23,966 INFO panai4_hymns                 qa4_hymns                         1      214410176       9154
2026-11-09 11:12:23,972 INFO panai4_text_life             qa4_text_life                    20      982971035      39463
2026-11-09 11:12:24,007 INFO panai4_text_cwwl             qa4_text_cwwl                    90     4475183876     178107
2026-11-09 11:12:24,015 INFO panai4_text_cwwn             qa4_text_cwwn                    17      806282342      32032
2026-11-09 11:12:24,019 INFO panai4_text_others           qa4_text_others                   8      385268164      15481
2026-11-09 11:12:24,022 INFO panai4_map_note              qa4_map_note                      9      391960028      16052
2026-11-09 11:12:24,023 INFO panai4_pano_catalog          qa4_pano_catalog                  1       50383000      53151
2026-11-09 11:12:24,023 INFO MANIFEST 期望文档数合计 = 414082
2026-11-09 11:12:24,023 INFO 文件总字节 = 9063019963
```

### 9.2c 无 MANIFEST 的临时目录

dry-run（应报内置默认）exit=0：

```text
2026-11-09 11:12:25,693 INFO log_file=G:\copypan\qa4\data_prep\_c2b_builtin.log
2026-11-09 11:12:25,694 INFO 期望文档数来源: 内置默认（INDEX_SPECS.expect）
2026-11-09 11:12:25,694 INFO offline/dry-run 允许回退到内置默认；已在上方标明来源。
2026-11-09 11:12:25,695 INFO === offline/dry-run：解析文件与导入计划（不连接 ES）===
2026-11-09 11:12:25,695 INFO source                       target                        files          bytes   manifest
2026-11-09 11:12:25,696 INFO panai4_hymns                 qa4_hymns                         1              4       9154
2026-11-09 11:12:25,696 INFO MANIFEST 期望文档数合计 = 9154
2026-11-09 11:12:25,696 INFO 文件总字节 = 4
```

真实模式（应中止且不连接）exit=3 / instrumented exit=3；`make_client` 调用次数=0（期望 0）：

```text
2026-11-09 11:12:27,377 INFO log_file=G:\copypan\qa4\data_prep\_c2b_real_abort.log
2026-11-09 11:12:27,378 INFO 期望文档数来源: 内置默认（INDEX_SPECS.expect）
2026-11-09 11:12:27,378 ERROR 中止：真实导入要求找到 MANIFEST.json（已搜索 data-root 上级等路径），不得回退到内置默认。未尝试连接 ES。
```

### 9.2d 与上一版差异 / Docker / git

```diff
（es_import.py 仍在未跟踪的 qa4/ 内；关键片段）

4 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load_manifest_expect(data_root: Path) -> tuple[dict[str, int], str | None]:
    """优先读包内 MANIFEST.json；否则用内置 expect。

    返回 (expect_map, source)：
      source 为 MANIFEST.json 的绝对路径字符串；若回退内置则为 Non
---
test(log)
        log.info(f"self-test exit={code}")
        return code

    # --force 必须与 --only 同时使用（在任何连接之前拒绝）
    if args.force and not args.only:
        log.error(
            "拒绝：--force 必须与 --only 同时使用；"
            "--force 只作用于 --only 明确列出的索引。未尝试连接 ES。"
        )
     
---
ect[idx] = INDEX_SPECS[idx]["expect"]

    if expect_source:
        log.info(f"期望文档数来源: MANIFEST.json → {expect_source}")
    else:
        log.info("期望文档数来源: 内置默认（INDEX_SPECS.expect）")

    if args.dry_run or args.offline:
        if expect_source is None:
            log.info(
---
_prefix,
            args.index_suffix or "",
            log,
        )

    # 真实导入：找不到 MANIFEST.json 即中止（不静默回退）
    if expect_source is None:
        log.error(
            "中止：真实导入要求找到 MANIFEST.json（已搜索 data-root 上级等路径），"
            "不得回退到内置默认。未尝试连接 ES。"
        )
        ret
---
lse,
        raise_on_exception=False,
        request_timeout=180,
    )
    # 导入完成后必须先 refresh，再读取 count（顺序不可颠倒）
    es.indices.refresh(index=target)
    elapsed = time.perf_counter() - t0
    err_n = len(errors) if errors else 0
    final = int(es.count(index=target)["count"])
```

docker ps -a / volume ls 前后相同：**True**

```text
?? docs/panai4_graph/export_pack.md
?? docs/panai4_graph/git_merge_conflict.md
?? docs/panai4_graph/git_merge_resolve.md
?? qa4/
```
