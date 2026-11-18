# -*- coding: utf-8 -*-
"""独立核对（只读）。用法：python qa4/notes/probe5/verify_independent.py [1-5|all]"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

DEVINE = Path(
    r"C:\Users\28121\Desktop\可导入资料\2 特殊标注"
    r"\【devine_argument】越进入高峰，真理越需要辨明得准确.json"
)
IMPORT_MD = Path(r"G:\copypan\docs\panai4_graph\import_devine_argument.md")
CLASS4 = Path(
    r"C:\Users\28121\Desktop\可导入资料\2 特殊标注"
    r"\【intrinsic_significance】2372词条内在意义分类.json"
)
TXT2373 = Path(
    r"G:\copypan\docs\panai4_graph\2373个词条（已确定一一对应为concept节点）.txt"
)
ORG = Path(r"G:\copypan\qa4\data\graph_annotations\organic_advance.json")
V21 = Path(r"C:\Users\28121\Desktop\get_vers_v2.1.py")


def cmd1():
    b = DEVINE.read_bytes()
    d = json.loads(b)
    t1 = len({x["content_1"][0]["title"] for x in d})
    print(hashlib.sha256(b).hexdigest()[:16], len(d), t1)


def cmd2():
    t = IMPORT_MD.read_text(encoding="utf-8")
    m = re.search(r'"discarded"\s*:\s*\[(.*?)\]', t, re.S)
    print(re.findall(r'"([^"]+)"', m.group(1)))


def cmd3():
    w = json.loads(CLASS4.read_text(encoding="utf-8"))["words"]
    print([x["name"] for x in w if x["name"] in ("路得马丁", "路德马丁", "城市")])
    print(
        [
            ln.strip()
            for ln in TXT2373.read_text(encoding="utf-8").splitlines()
            if ln.strip() in ("城市", "路得马丁", "路德马丁")
        ]
    )


def cmd4():
    b = ORG.read_bytes()
    d = json.loads(b)
    print(len(d), sorted(d[0]), hashlib.sha256(b).hexdigest()[:16])


def cmd5():
    spec = importlib.util.spec_from_file_location("v21", V21)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    vp = mod.VerseParser()
    vp.start_paragraph()
    print(vp.parse_text("诗八九26"))


FUNCS = {"1": cmd1, "2": cmd2, "3": cmd3, "4": cmd4, "5": cmd5}


def main():
    arg = (sys.argv[1] if len(sys.argv) > 1 else "all").strip()
    if arg == "all":
        for k in "12345":
            print(f"#{k}")
            FUNCS[k]()
        return
    if arg not in FUNCS:
        raise SystemExit("usage: verify_independent.py [1-5|all]")
    FUNCS[arg]()


if __name__ == "__main__":
    main()
