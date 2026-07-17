# -*- coding: utf-8 -*-
"""按主题从文集目录筛选相关篇题，输出主题文档。"""
from __future__ import annotations

import re
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "ministry_catalog_by_stage.md"
OUT_DIR = Path(__file__).resolve().parent / "topic_catalogs"

STAGE_LABELS = {
    1: "倪柝声弟兄职事",
    2: "李常受弟兄职事第一阶段（1932-1960）",
    3: "李常受弟兄职事第二阶段（1961-1973）",
    4: "李常受弟兄职事第三阶段（1974-1984）",
    5: "李常受弟兄职事第四阶段（1985-1990）",
    6: "李常受弟兄职事第五阶段（1991-1997）",
}

STAGE_COUNT = 6

# 篇数较多、需按阶段收紧到约 50~100 篇的主题
TIGHT_FILTER_TOPICS = frozenset({"基督的身位与工作", "基督与召会", "召会生活"})
# 先收紧至约 200 篇，再二次筛选至终稿篇数的主题
TWO_STAGE_FILTER_TOPICS = frozenset({"基督与召会", "召会生活"})
INTERMEDIATE_TARGET_TOTAL = 200  # 第一阶段目标总篇数
TARGET_TOTAL = 75  # 终稿目标总篇数（50~100 区间中部）
MIN_PER_STAGE = 1

TOPICS: dict[str, dict] = {
    "基督的身位与工作": {
        "contains": [
            "基督的身位", "身位与工作", "基督的工作", "关于基督的身位",
            "基督的职分", "主的身位", "道成肉身", "神人二性",
        ],
        "patterns": [
            r"基督.{0,6}身位", r"身位.{0,6}基督", r"基督.{0,6}工作", r"工作.{0,6}基督",
            r"关于基督", r"基督是谁", r"基督的位格", r"道成肉身",
            r"神也成为人", r"人子与神子", r"神子与人子",
            r"基督的职", r"基督救赎", r"基督救", r"基督的救赎",
            r"基督是神救主", r"基督是人救主", r"基督是.*救主",
            r"完全的神.*完全的人", r"神人二性",
            r"基督的.*使命", r"基督的.*职任",
        ],
        "exclude": [
            r"基督的丰富", r"基督的扩大", r"基督与召会", r"基督的身体",
            r"基督是神的中心", r"基督的新妇", r"基督的配偶",
        ],
    },
    "新妇": {
        "contains": ["新妇", "童女", "新郎新妇", "婚筵", "配偶"],
        "patterns": [
            r"新妇", r"童女", r"新郎", r"婚筵", r"婚礼",
            r"基督.{0,4}妻", r"妻.{0,4}基督", r"基督.{0,4}配偶", r"配偶.{0,4}基督",
            r"聪明的童女", r"愚拙的童女", r"十个童女", r"贞洁的童女",
            r"迎娶新妇", r"新妇的预备",
        ],
        "exclude": [r"寡妇，妇人与童女"],
    },
    "基督与召会": {
        "contains": [
            "基督与召会", "召会与基督", "基督的身体", "基督的扩大",
            "基督的丰满", "头是基督", "基督是头",
        ],
        "patterns": [
            r"基督与召会", r"召会与基督", r"基督的身体", r"身体是基督",
            r"身体就是召会", r"召会是基督", r"教会就是基督", r"基督在召会",
            r"基督的扩大", r"基督的丰满", r"头与身体", r"元首与身体",
            r"基督作头", r"基督是头", r"基督的.*身体", r"身体的.*基督",
            r"基督与教会", r"教会与基督", r"基督的身体和基督的新妇",
            r"建造基督身体", r"建造.*基督.*身体", r"基督身体的",
            r"活在基督身体里", r"基督身体的律", r"基督身体的覆庇",
            r"基督身体的长大", r"基督身体的建造", r"基督身体的交通",
            r"基督身体的知觉", r"基督身体的感觉",
        ],
        "exclude": [
            r"归于基督的名", r"教会是归于", r"召会的组织", r"召会的治理",
            r"召会的见证$", r"地方召会.*成立",
        ],
    },
    "召会生活": {
        "contains": [
            "召会生活", "教会生活", "聚会生活", "聚会的生活",
            "相调", "擘饼", "圣徒相爱", "金链的生命", "爱弟兄",
        ],
        "patterns": [
            r"召会生活", r"教会生活", r"聚会生活", r"聚会的生活",
            r"相调", r"擘饼", r"擘开饼", r"记念主",
            r"圣徒相爱", r"爱弟兄", r"金链的生命", r"爱德的生活",
            r"彼此相爱", r"圣徒相交", r"圣徒的相交",
            r"召会的交通", r"身体的交通", r"在身体里",
            r"同过.*生活", r"过召会", r"召会里的生活",
            r"擘饼聚会", r"交通聚会", r"祷告聚会",
            r"爱伙伴", r"圣徒之间",
            r"为着召会生活", r"基督徒聚会",
        ],
        "exclude": [
            r"召会的组织", r"召会的治理", r"召会的见证", r"地方召会.*成立",
            r"基督在召会", r"基督与召会", r"长老", r"使徒", r"职分",
            r"全时间训练", r"治理", r"权柄的实行",
            r"正常的基督徒生活",
        ],
    },
    "青少年儿童工作": {
        "contains": [
            "青少年", "青年工作", "儿童工作", "少年工作", "儿童聚会",
            "主日学", "托儿", "带领少年", "少年人",
        ],
        "patterns": [
            r"青少年", r"青年工作", r"儿童工作", r"少年工作", r"孩童工作",
            r"儿童聚会", r"主日学", r"托儿", r"带领少年", r"少年人",
            r"与少年", r"对少年", r"与青年", r"对青年", r"青年同工",
            r"青年服事", r"校园", r"小学生", r"中学生", r"大学生",
            r"下一代", r"小孩子", r"孩童", r"幼儿", r"年少的圣徒",
            r"转移时代的少年", r"如何带领少年",
        ],
        "exclude": [
            r"男孩子", r"属灵的儿女", r"神的儿女", r"神儿女",
            r"逃避青年人的私欲", r"两个奥秘", r"妇人生了",
            r"谈话记录.*男孩子", r"不再作小孩子",
        ],
    },
}


def parse_catalog(text: str):
    stage = 0
    volume = ""
    book = ""
    for line in text.splitlines():
        if line.startswith("## ") and re.match(r"## \d+\.", line):
            m = re.match(r"## (\d+)\.", line)
            if m:
                stage = int(m.group(1))
        elif line.startswith("### 册："):
            volume = line.split("：", 1)[1].strip()
            book = ""
        elif line.startswith("#### "):
            book = line[5:].strip()
        elif line.startswith("- "):
            yield stage, volume, book, line[2:].strip()


def core_title(title: str) -> str:
    return re.sub(r"^第[一二三四五六七八九十百千万〇零\d]+篇[　\s]*", "", title)


def is_match(topic: str, title: str, book: str = "") -> bool:
    cfg = TOPICS[topic]
    core = core_title(title)
    for ex in cfg.get("exclude", []):
        if re.search(ex, core) or re.search(ex, title) or re.search(ex, book):
            return False
    if topic in core or topic in title or topic in book:
        return True
    for s in cfg["contains"]:
        if s in core or s in title or s in book:
            return True
    for pat in cfg["patterns"]:
        if re.search(pat, core) or re.search(pat, title) or re.search(pat, book):
            return True
    if topic == "基督的身位与工作":
        if ("身位" in core and "基督" in core) or (
            "工作" in core and ("基督" in core or "主" in core)
        ):
            return True
    if topic == "基督与召会":
        if "基督" in core and ("召会" in core or "教会" in core or "身体" in core):
            if not re.search(r"组织|治理|见证$|成立", core):
                return True
    if topic == "召会生活":
        life_terms = ("召会生活", "教会生活", "聚会生活", "聚会的生活")
        if any(t in core or t in book for t in life_terms):
            return True
        if "召会" in core and ("生活" in core or "交通" in core):
            return True
    return False


def _score_rules(topic: str, core: str, book: str) -> int:
    """篇题 / 书名与主题贴近程度，分数越高越应保留。"""
    text = f"{core} {book}"

    if topic == "基督的身位与工作":
        rules: list[tuple[int, list[str]]] = [
            (100, ["基督的身位", "身位与工作", "主的身位与工作", "主的身位"]),
            (95, ["关于基督的身位", "基督身位"]),
            (90, ["基督的工作", "基督救赎的工作", "基督救赎"]),
            (85, ["道成肉身", "神人二性", "完全的神，也是完全的人", "完全的神.*完全的人"]),
            (80, ["关于基督和十字架", "关于基督"]),
            (70, ["基督是谁", "基督的位格", "人子与神子", "神子与人子"]),
            (60, ["基督是神救主", "基督是人救主", "基督是神又是人"]),
            (50, ["身位", "基督的职分", "基督的职事", "基督的职任"]),
        ]
    elif topic == "基督与召会":
        rules = [
            (100, ["基督与召会", "召会与基督", "基督与教会", "教会与基督"]),
            (95, ["基督的身体和基督的新妇", "基督的身体就是召会", "身体就是召会"]),
            (90, ["基督的身体", "身体是基督", "在基督的身体里", "基督身体的"]),
            (88, ["召会是基督", "教会就是基督", "基督在召会", "基督在召会里"]),
            (85, ["基督的扩大", "基督的丰满", "基督的扩增"]),
            (82, ["建造基督身体", "建造基督的身体", "基督身体的建造", "基督身体的长大"]),
            (80, ["头与身体", "元首与身体", "基督是头", "基督作头", "头是基督"]),
            (75, ["活在基督身体里", "基督身体的感觉", "基督身体的知觉", "基督身体的交通"]),
            (70, ["基督身体的律", "基督身体的覆庇", "基督身体的覆庇约束和供应"]),
            (55, ["身体的基督", "身体的长大", "身体的建造"]),
        ]
    elif topic == "召会生活":
        rules = [
            (100, ["召会生活", "教会生活", "聚会生活", "聚会的生活"]),
            (95, ["为着召会生活", "过召会生活", "正确的召会生活", "在召会生活的"]),
            (90, ["擘饼记念主", "擘饼—接受基督", "擘饼—", "擘饼聚会", "擘开饼"]),
            (88, ["相调", "相调聚会", "相调特会"]),
            (85, ["圣徒相爱", "爱弟兄", "金链的生命", "爱德的生活", "彼此相爱"]),
            (80, ["召会的交通", "身体的交通", "圣徒相交", "圣徒的相交"]),
            (75, ["交通聚会", "祷告聚会", "擘饼聚会祷告", "记念主"]),
            (70, ["怎样聚会", "交通的实行", "聚会生活", "基督徒聚会"]),
            (60, ["在身体里", "圣徒之间", "爱伙伴"]),
            (50, ["全教会祷告聚会"]),
        ]
    else:
        return 50

    best = 0
    for score, keys in rules:
        for key in keys:
            if key in core or key in book:
                best = max(best, score)
            elif any(c in key for c in ".*+"):
                if re.search(key, core) or re.search(key, book):
                    best = max(best, score)
    if best:
        return best

    # 篇题字面弱匹配仍给低分
    if topic == "基督的身位与工作":
        if "身位" in core and "基督" in core:
            return 45
        if "工作" in core and ("基督" in core or "主" in core):
            return 40
    if topic == "基督与召会":
        if "基督" in core and ("召会" in core or "教会" in core or "身体" in core):
            return 35
    if topic == "召会生活":
        if any(t in book for t in ("聚会的生活", "教会生活", "召会生活")):
            return 30
        if "擘饼" in core:
            return 45
    return 20


def relevance_score(topic: str, volume: str, book: str, title: str) -> int:
    core = core_title(title)
    score = _score_rules(topic, core, book)
    # 篇题命中比仅书名命中优先
    if score >= 50 and any(k in core for k in TOPICS[topic].get("contains", [])):
        score += 5
    if topic in core:
        score += 10
    return score


def allocate_stage_quotas(stage_counts: dict[int, int], target: int) -> dict[int, int]:
    """按阶段分配保留篇数：每阶段至少 MIN_PER_STAGE，合计约 target。"""
    stages = [s for s in range(1, STAGE_COUNT + 1) if stage_counts.get(s, 0) > 0]
    if not stages:
        return {}

    quotas = {s: MIN_PER_STAGE for s in stages}
    remaining = max(0, target - sum(quotas.values()))

    weights = {s: stage_counts[s] ** 0.45 for s in stages}
    total_w = sum(weights.values()) or 1.0
    for s in stages:
        quotas[s] += int(remaining * weights[s] / total_w)

    while sum(quotas.values()) < target:
        grow = max(
            (s for s in stages if quotas[s] < stage_counts[s]),
            key=lambda s: stage_counts[s] - quotas[s],
            default=None,
        )
        if grow is None:
            break
        quotas[grow] += 1

    while sum(quotas.values()) > target:
        shrink = max(
            (s for s in stages if quotas[s] > MIN_PER_STAGE),
            key=lambda s: quotas[s],
            default=None,
        )
        if shrink is None:
            break
        quotas[shrink] -= 1

    for s in stages:
        quotas[s] = min(quotas[s], stage_counts[s])
        quotas[s] = max(quotas[s], MIN_PER_STAGE)
    return quotas


def tight_filter_hits(
    topic: str,
    hits: dict[int, list[tuple[str, str, str]]],
    target: int = TARGET_TOTAL,
) -> dict[int, list[tuple[str, str, str]]]:
    stage_counts = {s: len(hits[s]) for s in range(1, STAGE_COUNT + 1) if hits[s]}
    if not stage_counts:
        return hits

    if sum(stage_counts.values()) <= target:
        return hits

    quotas = allocate_stage_quotas(stage_counts, target)
    out: dict[int, list[tuple[str, str, str]]] = {s: [] for s in range(1, STAGE_COUNT + 1)}

    for stage, quota in quotas.items():
        ranked = sorted(
            hits[stage],
            key=lambda item: relevance_score(topic, item[0], item[1], item[2]),
            reverse=True,
        )
        out[stage] = ranked[:quota]

    return out


def apply_topic_filters(
    topic: str,
    hits: dict[int, list[tuple[str, str, str]]],
) -> tuple[
    dict[int, list[tuple[str, str, str]]],
    dict[int, list[tuple[str, str, str]]],
    str,
]:
    """返回 (终稿, 筛选对照基准, 筛选说明)。

    对照基准用于 Word 导出：单阶段主题为初筛全量；两阶段主题为第一阶段结果（≤200）。
    """
    initial_total = sum(len(v) for v in hits.values())

    if topic in TWO_STAGE_FILTER_TOPICS:
        stage1 = tight_filter_hits(topic, hits, INTERMEDIATE_TARGET_TOTAL)
        final = tight_filter_hits(topic, stage1, TARGET_TOTAL)
        note = (
            f"已分两阶段筛选：先由初筛 {initial_total} 篇收紧至约 "
            f"{INTERMEDIATE_TARGET_TOTAL} 篇（实际 {sum(len(v) for v in stage1.values())} 篇），"
            f"再保留约 {TARGET_TOTAL} 篇（实际 {sum(len(v) for v in final.values())} 篇），"
            f"每阶段至少 {MIN_PER_STAGE} 篇。"
        )
        return final, stage1, note

    if topic in TIGHT_FILTER_TOPICS:
        final = tight_filter_hits(topic, hits, TARGET_TOTAL)
        note = (
            f"已按阶段筛选与主题最密切相关的篇题（目标约 {TARGET_TOTAL} 篇，"
            f"每阶段至少 {MIN_PER_STAGE} 篇）。"
        )
        return final, hits, note

    return hits, hits, ""


STAGE_ZH = ["", "壹", "贰", "叁", "肆", "伍", "陆"]


def to_zh_num(n: int) -> str:
    digits = "〇一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n % 10] if n % 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        text = digits[tens] + "十"
        if ones:
            text += digits[ones]
        return text
    return str(n)


def _group_by_book(
    items: list[tuple[str, str, str]],
) -> list[tuple[str, str, list[str]]]:
    """按出现顺序将 (册, 书名) 相同的篇题归组。"""
    groups: list[tuple[str, str, list[str]]] = []
    cur_key: tuple[str, str] | None = None
    for volume, book, title in items:
        key = (volume, book)
        if key != cur_key:
            groups.append((volume, book, [title]))
            cur_key = key
        else:
            groups[-1][2].append(title)
    return groups


def write_topic_doc(
    topic: str,
    hits: dict[int, list[tuple[str, str, str]]],
    *,
    filter_note: str = "",
) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{topic}.md"
    total = sum(len(v) for v in hits.values())
    lines = [
        "# 主恢复中神圣启示的进展",
        "",
        f"## {topic}——{total}篇",
        "",
    ]
    if filter_note:
        lines.append(filter_note)
    if topic == "召会生活":
        lines.append("备注：「召会生活」与「教会生活」「聚会生活」「聚会的生活」等同视之。")
    lines.append("")

    for sn in range(1, STAGE_COUNT + 1):
        items = hits[sn]
        if not items:
            continue
        stage_zh = STAGE_ZH[sn]
        stage_label = STAGE_LABELS[sn]
        lines.append(f"## {stage_zh}　{stage_label}——{len(items)}篇")
        lines.append("")

        book_groups = _group_by_book(items)
        for book_idx, (volume, book, titles) in enumerate(book_groups, start=1):
            book_zh = to_zh_num(book_idx)
            lines.append(f"**{book_zh}　{book}——{len(titles)}篇（{volume}）**")
            lines.append("")
            for art_idx, title in enumerate(titles, start=1):
                lines.append(f"{art_idx}. {title}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    text = CATALOG.read_text(encoding="utf-8")
    all_stats: dict[str, dict[int, int]] = {}

    for topic in TOPICS:
        hits: dict[int, list[tuple[str, str, str]]] = {
            s: [] for s in range(1, STAGE_COUNT + 1)
        }
        for stage, volume, book, title in parse_catalog(text):
            if is_match(topic, title, book):
                hits[stage].append((volume, book, title))

        before = sum(len(v) for v in hits.values())
        hits, _, filter_note = apply_topic_filters(topic, hits)
        after = sum(len(v) for v in hits.values())
        per = [len(hits[s]) for s in range(1, STAGE_COUNT + 1)]
        if topic in TWO_STAGE_FILTER_TOPICS:
            print(f"{topic}: {before} -> stage1<={INTERMEDIATE_TARGET_TOTAL} -> {after} (per stage {per})")
        elif topic in TIGHT_FILTER_TOPICS:
            print(f"{topic}: {before} -> {after} (per stage {per})")
        else:
            print(f"{topic}: {after} (per stage {per})")

        write_topic_doc(topic, hits, filter_note=filter_note)
        all_stats[topic] = {s: len(hits[s]) for s in range(1, STAGE_COUNT + 1)}

    print("\n=== 各主题各阶段篇数统计 ===")
    header = "主题\t" + "\t".join(f"阶段{s}" for s in range(1, STAGE_COUNT + 1)) + "\t合计"
    print(header)
    for topic, counts in all_stats.items():
        row = [topic] + [str(counts[s]) for s in range(1, STAGE_COUNT + 1)]
        row.append(str(sum(counts.values())))
        print("\t".join(row))


if __name__ == "__main__":
    main()
