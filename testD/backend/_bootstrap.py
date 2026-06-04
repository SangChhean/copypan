# -*- coding: utf-8 -*-
"""将 back_mic/backend 加入 sys.path，供 testD 复用主工程模块。"""
from __future__ import annotations

import sys
from pathlib import Path

_MAIN_BACKEND: Path | None = None


def ensure_main_backend_path() -> Path:
    global _MAIN_BACKEND
    if _MAIN_BACKEND is None:
        root = Path(__file__).resolve().parents[2]
        backend = root / "back_mic" / "backend"
        if not backend.is_dir():
            raise RuntimeError(f"主后端目录不存在: {backend}")
        _MAIN_BACKEND = backend
        s = str(backend)
        if s not in sys.path:
            sys.path.insert(0, s)
    return _MAIN_BACKEND
