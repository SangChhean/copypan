# -*- coding: utf-8 -*-
"""3a/3b 定义加载（truth_dictionary_3a3b.json），括号词映射到外词。"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Optional


class DefinitionStore:
    def __init__(self, td_path: Path, *, same_as: Optional[dict[str, str]] = None) -> None:
        self.td_path = Path(td_path)
        self.same_as = dict(same_as or {})
        self._rows: Optional[dict[str, dict[str, Any]]] = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.td_path.is_file()

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._rows is not None:
            return self._rows
        with self._lock:
            if self._rows is None:
                if not self.td_path.is_file():
                    self._rows = {}
                else:
                    data = json.loads(self.td_path.read_text(encoding="utf-8"))
                    self._rows = {str(r.get("title")): r for r in data if r.get("title")}
        return self._rows

    def resolve(self, name: str) -> str:
        return self.same_as.get(name, name)

    def get(self, name: str) -> Optional[dict[str, Any]]:
        return self._load().get(self.resolve(name))

    def content_3a(self, name: str) -> str:
        row = self.get(name)
        return str((row or {}).get("content_3a") or "")

    def titles(self) -> list[str]:
        return list(self._load().keys())


def truncate_by_paragraph(text: str, max_chars: int) -> str:
    """按段落截断到 max_chars 字以内（至少保留第一段的前 max_chars 字）。"""
    if not text or len(text) <= max_chars:
        return text or ""
    paras = [p for p in re.split(r"\n+", text) if p.strip()]
    out: list[str] = []
    total = 0
    for p in paras:
        if total + len(p) + (1 if out else 0) > max_chars:
            break
        out.append(p)
        total += len(p) + (1 if len(out) > 1 else 0)
    if not out:
        return paras[0][:max_chars] if paras else text[:max_chars]
    return "\n".join(out)


def same_as_map(lexicon: list[dict[str, Any]]) -> dict[str, str]:
    """括号内词 → 括号外词。"""
    return {e["name"]: e["same_as"] for e in lexicon if e.get("same_as")}
