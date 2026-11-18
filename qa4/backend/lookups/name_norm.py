"""名字规范化：先别名、再忽略。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class NameNorm:
    aliases: dict[str, str]
    ignore: set[str]
    logs: list[dict] = field(default_factory=list)

    @classmethod
    def from_aliases_file(cls, path: Path) -> "NameNorm":
        data = json.loads(path.read_text(encoding="utf-8"))
        aliases = {str(k): str(v) for k, v in (data.get("aliases") or {}).items()}
        ignore = {str(x) for x in (data.get("ignore") or [])}
        return cls(aliases=aliases, ignore=ignore)

    def normalize(self, name: str, *, context: str = "") -> Optional[str]:
        """返回规范化后的名字；若应忽略则返回 None。"""
        raw = str(name)
        if raw in self.ignore:
            self.logs.append(
                {"action": "ignore", "name": raw, "context": context}
            )
            return None
        if raw in self.aliases:
            mapped = self.aliases[raw]
            self.logs.append(
                {
                    "action": "alias",
                    "from": raw,
                    "to": mapped,
                    "context": context,
                }
            )
            # 别名结果仍可能在忽略表
            if mapped in self.ignore:
                self.logs.append(
                    {
                        "action": "ignore",
                        "name": mapped,
                        "context": context,
                        "via_alias_from": raw,
                    }
                )
                return None
            return mapped
        return raw

    def normalize_many(
        self, names: Iterable[str], *, context: str = ""
    ) -> list[str]:
        out: list[str] = []
        for n in names:
            v = self.normalize(n, context=context)
            if v is not None:
                out.append(v)
        return out
