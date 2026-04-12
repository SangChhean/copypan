# -*- coding: utf-8 -*-
"""
Sync seed_concepts.json concepts + relations to user target list:
- Remove concepts in REMOVE (and any relation touching them).
- Add concepts in ADD.
- Kept concepts preserve order from current seed; ADD appended in sorted order.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seed_concepts.json"
GOLDEN = ROOT / "golden_paths.json"

# In seed but not in user's 637 list (from prior compare)
REMOVE = {
    "一个救恩",
    "一个生命",
    "一个见证",
    "一位基督",
    "一位灵",
    "一位神",
    "一座城",
    "一本圣经",
    "一种生活",
    "三一神的工作",
    "世界",
    "二性品",
    "初信者",
    "加强到里面的人里",
    "变化为着建造",
    "宇宙的合并",
    "完成阶段",
    "宝贝与瓦器",
    "属灵的仗",
    "恢复召会的建造",
    "恢复基督作生命",
    "恢复基督的身体",
    "洋溢之义的恩赐",
    "珍赏职事",
    "生活并工作",
    "起初阶段",
    "长进阶段",
}

# In user's list but not in seed (from prior compare)
ADD = {
    "不住地祷告",
    "与基督一同作王",
    "与神是一",
    "事奉",
    "信心",
    "信爱望",
    "信靠",
    "内里生命",
    "基督作一切",
    "基督的复制",
    "成肉体的原则",
    "承受神的国",
    "接触人",
    "日常生活",
    "最高的享受",
    "治死",
    "父、子、灵",
    "神圣的启示",
    "神爱世人",
    "祭司",
    "祷告的人",
    "祷告的生活",
    "穿上新人",
    "管制的异象",
    "脱去旧人",
    "荣耀神",
    "被神构成",
    "跟随主",
    "身体得赎",
}


def main():
    data = json.loads(SEED.read_text(encoding="utf-8"))
    seed_names = [c["name"] for c in data["concepts"]]
    seed_set = set(seed_names)

    missing_remove = REMOVE - seed_set
    if missing_remove:
        raise SystemExit(f"REMOVE not in seed: {missing_remove}")

    overlap_add = ADD & seed_set
    if overlap_add:
        raise SystemExit(f"ADD already in seed: {overlap_add}")

    target = (seed_set - REMOVE) | ADD
    if len(target) != 637:
        raise SystemExit(f"expected 637 names, got {len(target)}")

    seen = set()
    new_concepts = []
    for name in seed_names:
        if name in target and name not in seen:
            new_concepts.append({"name": name})
            seen.add(name)
    for name in sorted(ADD):
        if name not in seen:
            new_concepts.append({"name": name})
            seen.add(name)

    if len(new_concepts) != 637 or seen != target:
        raise SystemExit("concept list mismatch")

    rel_seen = set()
    new_relations = []
    for r in data["relations"]:
        fr, to = r["from"], r["to"]
        if fr not in target or to not in target:
            continue
        key = (fr, to, r["type"])
        if key in rel_seen:
            continue
        rel_seen.add(key)
        new_relations.append({"from": fr, "to": to, "type": r["type"]})

    data["concepts"] = new_concepts
    data["relations"] = new_relations
    SEED.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    paths = []
    if GOLDEN.exists():
        paths = json.loads(GOLDEN.read_text(encoding="utf-8"))
        # Paths that would become empty: replace with nodes that remain in target
        overrides = {
            15: ["得救", "重生", "圣别", "变化", "模成", "得荣"],
            30: [
                "一道流",
                "一的立场",
                "一个身体",
                "一个职事",
                "一里事奉",
                "真正的一",
                "包罗万有的一",
                "保守那灵的一",
                "独一的一",
                "信仰上的一",
            ],
        }
        for p in paths:
            pid = p["id"]
            if pid in overrides:
                p["nodes"] = overrides[pid]
            else:
                p["nodes"] = [n for n in p["nodes"] if n in target]
            for n in p["nodes"]:
                if n not in target:
                    raise SystemExit(f"golden path {pid} has node not in target: {n!r}")
        GOLDEN.write_text(
            json.dumps(paths, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print("concepts", len(data["concepts"]))
    print("relations", len(data["relations"]))
    print("golden_paths", len(paths))


if __name__ == "__main__":
    main()
