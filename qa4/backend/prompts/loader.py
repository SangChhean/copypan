# -*- coding: utf-8 -*-
"""提示词加载：registry.json 的 CURRENT 指针 → texts/*.txt；占位识别；草稿通道。"""

from __future__ import annotations

import json
import os
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent


class PromptError(RuntimeError):
    pass


class PromptVariableError(PromptError):
    pass


def prompt_channel() -> str:
    """stable（默认）| draft。由 QA4_PROMPT_CHANNEL 控制。"""
    raw = (os.environ.get("QA4_PROMPT_CHANNEL") or "stable").strip().lower()
    if raw in {"draft", "dev", "v0"}:
        return "draft"
    return "stable"


@dataclass(frozen=True)
class PromptTemplate:
    step: str
    version: str
    text: str
    variables: tuple[str, ...]
    placeholder: bool
    draft: bool = False
    channel: str = "stable"

    def render(self, **values: Any) -> str:
        missing = [v for v in self.variables if v not in values]
        if missing:
            raise PromptVariableError(f"{self.step}@{self.version} 缺少变量：{missing}")
        fields = {f for _, f, _, _ in string.Formatter().parse(self.text) if f}
        unknown = fields - set(self.variables)
        if unknown:
            raise PromptVariableError(f"{self.step}@{self.version} 模板含未登记变量：{sorted(unknown)}")
        return self.text.format(**{k: values[k] for k in self.variables})


class PromptRegistry:
    def __init__(self, base_dir: Optional[Path] = None, *, channel: Optional[str] = None) -> None:
        self.base_dir = Path(base_dir or _HERE)
        self.reg = json.loads((self.base_dir / "registry.json").read_text(encoding="utf-8"))
        self.marker = str(self.reg.get("placeholder_marker") or "【占位】")
        self.channel = (channel or prompt_channel()).strip().lower()
        if self.channel not in {"stable", "draft"}:
            self.channel = "stable"
        self._cache: dict[str, PromptTemplate] = {}

    def steps(self) -> list[str]:
        return list((self.reg.get("steps") or {}).keys())

    def _pick_version(self, step: str, meta: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        versions = meta.get("versions") or {}
        if self.channel == "draft":
            # 优先带 draft:true 的版本；同名多个时取版本号字符串最大者
            drafts = [(ver, vm) for ver, vm in versions.items() if bool((vm or {}).get("draft"))]
            if drafts:
                ver, vmeta = sorted(drafts, key=lambda x: x[0])[-1]
                return str(ver), dict(vmeta or {})
        ver = meta.get("CURRENT")
        vmeta = versions.get(ver)
        if not vmeta:
            raise PromptError(f"{step} 的 CURRENT 指向不存在的版本：{ver}")
        return str(ver), dict(vmeta)

    def get(self, step: str) -> PromptTemplate:
        cache_key = f"{self.channel}:{step}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        meta = (self.reg.get("steps") or {}).get(step)
        if not meta:
            raise PromptError(f"未登记的提示词步骤：{step}")
        ver, vmeta = self._pick_version(step, meta)
        path = self.base_dir / "texts" / str(vmeta.get("file"))
        if not path.is_file():
            raise PromptError(f"{step}@{ver} 文件不存在：prompts/texts/{vmeta.get('file')}")
        text = path.read_text(encoding="utf-8")
        tpl = PromptTemplate(
            step=step,
            version=str(ver),
            text=text,
            variables=tuple(vmeta.get("variables") or ()),
            placeholder=bool(vmeta.get("placeholder")) or (self.marker in text),
            draft=bool(vmeta.get("draft")),
            channel=self.channel,
        )
        self._cache[cache_key] = tpl
        return tpl

    def versions(self) -> dict[str, str]:
        return {s: self.get(s).version for s in self.steps()}

    def version_key(self) -> str:
        # 通道写入缓存键，避免 stable/draft 互相命中
        body = ";".join(f"{k}={v}" for k, v in sorted(self.versions().items()))
        return f"channel={self.channel};{body}"

    def placeholder_steps(self) -> list[str]:
        return [s for s in self.steps() if self.get(s).placeholder]

    def status(self) -> dict[str, Any]:
        ph = self.placeholder_steps()
        return {
            "channel": self.channel,
            "versions": self.versions(),
            "placeholder_steps": ph,
            "ready": not ph,
        }
