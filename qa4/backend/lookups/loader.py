# -*- coding: utf-8 -*-
"""查表加载与启动核对。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from .name_norm import NameNorm


class LookupStoreError(RuntimeError):
    """查表损坏或与 MANIFEST 不符。"""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rel_in_lookups(name: str) -> str:
    """相对查表目录的展示路径（不含绝对路径）。"""
    return f"lookups/{name}"


class LookupStore:
    def __init__(
        self,
        lookup_dir: Path,
        *,
        aliases_path: Optional[Path] = None,
    ) -> None:
        self.lookup_dir = Path(lookup_dir)
        self.manifest = self._verify_manifest()
        aliases_path = aliases_path or (
            Path(__file__).resolve().parent / "aliases.json"
        )
        self.norm = NameNorm.from_aliases_file(aliases_path)

        self.lexicon: list[dict] = _load_json(self.lookup_dir / "lexicon.json")
        self.by_name: dict[str, dict] = {e["name"]: e for e in self.lexicon}
        self.zui_neizai: list[str] = _load_json(
            self.lookup_dir / "zui_neizai_133.json"
        )
        self.zui_set = set(self.zui_neizai)
        self.other_2239: list[str] = _load_json(
            self.lookup_dir / "other_2239.json"
        )

    def _verify_manifest(self) -> dict:
        man_path = self.lookup_dir / "MANIFEST.json"
        if not man_path.is_file():
            raise LookupStoreError(
                f"缺少 MANIFEST.json：{_rel_in_lookups('MANIFEST.json')}"
            )
        manifest = _load_json(man_path)
        files = manifest.get("files") or {}
        if not files:
            raise LookupStoreError("MANIFEST.json 中 files 为空")

        for name, meta in files.items():
            path = self.lookup_dir / name
            if not path.is_file():
                raise LookupStoreError(
                    f"MANIFEST 列出的文件不存在：{_rel_in_lookups(name)}"
                )
            actual_sha = _sha256_file(path)
            expect_sha = meta.get("sha256")
            if actual_sha != expect_sha:
                raise LookupStoreError(
                    f"文件 SHA256 与 MANIFEST 不符：{_rel_in_lookups(name)} "
                    f"（拒绝启动；不打印期望/实际摘要以外的文件内容）"
                    f" expect={expect_sha} actual={actual_sha}"
                )
            # 条数核对
            expect_count = meta.get("count")
            actual_count = self._count_file(name, path)
            if expect_count is not None and actual_count != expect_count:
                raise LookupStoreError(
                    f"文件条数与 MANIFEST 不符：{_rel_in_lookups(name)} "
                    f"实际={actual_count} 期望={expect_count}"
                )
        return manifest

    def _count_file(self, name: str, path: Path) -> int:
        if name.endswith(".csv"):
            # 数据行数（不含表头）
            text = path.read_text(encoding="utf-8-sig")
            lines = [ln for ln in text.splitlines() if ln.strip()]
            return max(0, len(lines) - 1)
        data = _load_json(path)
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            if "title_count" in data:
                return int(data["title_count"])
            if name == "hymn_series.json":
                return int(data.get("daben_buchong_number_overlap") or 0)
            if name == "name_norm_log.json":
                return len(data) if isinstance(data, list) else len(data)
            return len(data)
        return 0

    def normalize_name(self, name: str) -> Optional[str]:
        return self.norm.normalize(name, context="lookup")

    def get_term(self, name: str) -> Optional[dict]:
        """按名取词；先别名/忽略；括号内词仍可直接取到自身条目。"""
        n = self.normalize_name(name)
        if n is None:
            return None
        return self.by_name.get(n)

    def resolve_outer(self, name: str) -> Optional[str]:
        """括号内词映射到括号外词；无 same_as 则返回自身规范化名。"""
        entry = self.get_term(name)
        if entry is None:
            return None
        return entry.get("same_as") or entry.get("name")

    def get_zui_neizai(self) -> list[str]:
        return list(self.zui_neizai)

    def is_zui_neizai(self, name: str) -> bool:
        n = self.normalize_name(name)
        if n is None:
            return False
        entry = self.by_name.get(n)
        if entry and entry.get("same_as"):
            n = entry["same_as"]
        return n in self.zui_set


def load_lookups(lookup_dir: Path, *, aliases_path: Optional[Path] = None) -> LookupStore:
    return LookupStore(lookup_dir, aliases_path=aliases_path)
