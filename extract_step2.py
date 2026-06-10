import pathlib
import re

text = pathlib.Path(r"C:/Users/czh/.cursor/projects/e-copypan/terminals/621569.txt").read_text(
    encoding="utf-8", errors="replace"
)
pattern = r"Step2 raw_skeleton preview: (.*?)(?=\nINFO:generate_outline:\[3\.5\] has_skeleton)"
m = re.search(pattern, text, re.DOTALL)
if not m:
    raise SystemExit("no match")
preview = m.group(1)
# logger only logs [:500] of raw_skeleton
preview500 = preview[:500]
full_line = f"INFO:generate_outline:[3.5] Step2 raw_skeleton preview: {preview500}"
pathlib.Path(r"E:/copypan/step2_log_line.txt").write_text(full_line, encoding="utf-8")
