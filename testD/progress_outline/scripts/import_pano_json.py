# -*- coding: utf-8 -*-
"""
从 progress_pano.json 导入 Elasticsearch（供服务器使用）。

用法：
  cd testD/progress_outline/scripts
  python import_pano_json.py
  python import_pano_json.py /path/to/progress_pano.json
  python import_pano_json.py --no-recreate
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ingest_pano import (  # noqa: E402
    EXPORT_JSON,
    close_log,
    import_from_json,
    open_log,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="progress_pano.json → Elasticsearch")
    parser.add_argument(
        "json_file",
        nargs="?",
        default=str(EXPORT_JSON),
        help=f"JSON 路径（默认 {EXPORT_JSON.name}）",
    )
    parser.add_argument("--no-recreate", action="store_true", help="不删除已有索引")
    args = parser.parse_args()

    open_log()
    try:
        import_from_json(Path(args.json_file), recreate=not args.no_recreate)
    finally:
        close_log()


if __name__ == "__main__":
    main()
