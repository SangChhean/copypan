# -*- coding: utf-8 -*-
import json
from pathlib import Path

rows = json.loads(Path(__file__).with_name("scan_all_qa4_index_fields_out.json").read_text(encoding="utf-8"))
print("| 索引 | 总条数 | book_title 有/空/无 | message_title 有/空/无 | source_zh 有/空/无 | source_en 有/空/无 | 样例 |")
print("|---|---:|---|---|---|---|---|")
for r in rows:
    c = r["counts"]

    def fmt(f):
        x = c[f]
        return f"{x['present']}/{x['empty']}/{x['missing_key']}"

    s = r.get("any_sample") or {}
    sample = f"bt={s.get('book_title')!r} mt={s.get('message_title')!r} sz={s.get('source_zh')!r} se={s.get('source_en')!r}"
    print(
        f"| {r['index']} | {r['total']} | {fmt('book_title')} | {fmt('message_title')} | "
        f"{fmt('source_zh')} | {fmt('source_en')} | {sample[:80]} |"
    )
    print("SAMPLE", r["index"], json.dumps(s, ensure_ascii=False))
