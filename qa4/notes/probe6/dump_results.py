# -*- coding: utf-8 -*-
import json
from pathlib import Path

P = Path(r"G:\copypan\qa4\notes\probe6")
a = json.loads((P / "a_result.json").read_text(encoding="utf-8"))
b = json.loads((P / "b_result.json").read_text(encoding="utf-8"))
c = json.loads((P / "c_result.json").read_text(encoding="utf-8"))

print("A n", a["n"], "unique", a["n_unique_names"], "multi", a["name_multi"])
print("content", a["content_len"], "title", a["title_len"])
print("bible", json.dumps(a["bible_rows"], ensure_ascii=False))
print("lead", a["content_str_stats"]["lead_types"])
print("stage", a["content_str_stats"]["stage_or_period_lines"], a["content_str_stats"]["stage_or_period_samples"])
print("headings", a["content_str_stats"]["heading_samples_heavenly"])
print("only_new", a["only_new_names"])
print("only_old", a["only_old_names"])
print("ratio", a["content_len_ratio_median"], "title_match", a["title_match_series_or_stages"])
print("import_vs", json.dumps(a["import_info"]["state"]["file_names_vs_new69"], ensure_ascii=False))
print("copy", json.dumps(a["import_info"]["state"].get("copy"), ensure_ascii=False)[:500])
print("written", a["import_info"]["state"].get("written"))
print("sha_related", a["import_info"]["state"].get("sha_related"))
print("repo_copies", json.dumps(a["repo_copies"], ensure_ascii=False, indent=2))
print("md", a["import_info"].get("md_snips", [])[:6])

print("B1", json.dumps(b["b1_3a_whole_line"], ensure_ascii=False, indent=2))
print("B2", json.dumps(b["b2_qa4_bible_fails"], ensure_ascii=False, indent=2))
print("B3", json.dumps(b["b3_x0_counts"], ensure_ascii=False, indent=2))

print("C1", json.dumps(c["c1_fail_details"], ensure_ascii=False, indent=2))
print("C2", json.dumps(c["c2_fix_collision"], ensure_ascii=False, indent=2))
print("C3", json.dumps(c["c3_locations"], ensure_ascii=False, indent=2))
print("C4v21", json.dumps(c["c4_v21_book_map"], ensure_ascii=False, indent=2))
print("C4p30", json.dumps(c["c4_parser30"], ensure_ascii=False, indent=2)[:3000])
print("C5", json.dumps(c["c5_change_list"], ensure_ascii=False, indent=2))
