import json
p = r"E:\copypan\_tmp_stream.json"
with open(p, "w", encoding="utf-8") as f:
    json.dump({"question": "神的经纶是什么", "history": [], "skip_cache": True}, f, ensure_ascii=False)
