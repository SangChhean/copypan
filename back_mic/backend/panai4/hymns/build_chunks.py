# -*- coding: utf-8 -*-
"""阶段 0–1：解析 hymns.json、生成块、闸门校验、写清洗 JSON。

用法（在 back_mic/backend 下）::

    python -m panai4.hymns.build_chunks
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from . import config

CN_NUM = r"[一二三四五六七八九十百零〇两]+"
UNIT_MARK_RE = re.compile(rf"(?:^|\n)(\s*)((?:{CN_NUM}|副)　)")
NAME_PATTERNS = (
    (re.compile(r"^(补充本诗歌)第(\d+)首　(.*)$"), "补充本诗歌"),
    (re.compile(r"^(诗歌附)(\d+)(.*)$"), "诗歌附"),
    (re.compile(r"^(诗歌)第(\d+)首　(.*)$"), "诗歌"),
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def parse_name(name: str) -> tuple[str, int, str]:
    for pat, _series in NAME_PATTERNS:
        m = pat.match(name)
        if m:
            return m.group(1), int(m.group(2)), m.group(3)
    raise ValueError(f"无法解析 name: {name!r}")


def split_title(title: str) -> tuple[str | None, str]:
    if "─" in title:
        left, right = title.split("─", 1)
        return left, right
    return None, title


def split_units(content: str) -> list[tuple[str, str, str, str | None]]:
    """返回 [(unit_type, unit_label, unit_text, special_note), ...]。

    不改歌词字符。首个标记之前的前缀（如「第一辞」、缺全角空格的「一」）
    并入第一个单位的 text，unit_label 仍取标记本身；special_note 记录此前缀。
    """
    text = content
    matches = list(UNIT_MARK_RE.finditer(text))
    if not matches:
        raise ValueError("正文无节/副歌标记")
    units: list[tuple[str, str, str, str | None]] = []
    for i, m in enumerate(matches):
        mark_start = m.start(2)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # 仅第一个单位吸收标记前的前缀，保证覆盖校验不丢字
        start = 0 if i == 0 else mark_start
        unit_text = text[start:end]
        if unit_text.endswith("\n"):
            unit_text = unit_text[:-1]
        if unit_text.endswith("\r"):
            unit_text = unit_text[:-1]
        label = m.group(2)[:-1]  # 去掉末尾全角空格
        utype = "chorus" if label == "副" else "stanza"
        special = None
        if i == 0 and start < mark_start:
            prefix = text[start:mark_start]
            special = f"preamble:{prefix!r}"
        units.append((utype, label, unit_text, special))
    return units


def normalize_lyrics(s: str) -> str:
    """忽略换行与行首 ASCII 空格后的歌词字符序列。"""
    return "".join(line.lstrip(" ") for line in (s or "").splitlines())


def chunk_id_of(message_key: str, chunk_index: int) -> str:
    digest = hashlib.sha1(message_key.encode("utf-8")).hexdigest()[:12]
    return f"{config.CHUNK_ID_PREFIX}_{digest}_c{chunk_index}"


def build_hymn_chunks(rec: dict) -> tuple[dict, list[dict]]:
    name = rec["name"]
    series, number, title = parse_name(name)
    category, subtitle = split_title(title)
    ref_raw = rec.get("reference")
    reference = None
    if isinstance(ref_raw, str) and ref_raw.strip():
        reference = ref_raw
    content = rec.get("content") or ""
    message_key = f"{series}|{number}"
    units = split_units(content)
    chunk_total = len(units)

    full_text = f"{name}\n{content}"
    full = {
        "chunk_id": chunk_id_of(message_key, 0),
        "message_key": message_key,
        "series": series,
        "hymn_number": number,
        "name": name,
        "title": title,
        "category": category,
        "subtitle": subtitle,
        "reference": reference,
        "unit_type": "full",
        "unit_label": None,
        "chunk_index": 0,
        "chunk_total": chunk_total,
        "text": full_text,
        "tokens": int(len(full_text) / 1.5),
    }
    unit_chunks = []
    specials = []
    for i, (utype, label, unit_text, special) in enumerate(units, start=1):
        text = f"{name}\n{unit_text}"
        unit_chunks.append(
            {
                "chunk_id": chunk_id_of(message_key, i),
                "message_key": message_key,
                "series": series,
                "hymn_number": number,
                "name": name,
                "title": title,
                "category": category,
                "subtitle": subtitle,
                "reference": reference,
                "unit_type": utype,
                "unit_label": label,
                "chunk_index": i,
                "chunk_total": chunk_total,
                "text": text,
                "tokens": int(len(text) / 1.5),
            }
        )
        if special:
            specials.append({"message_key": message_key, "chunk_index": i, "note": special})
    return full, unit_chunks, specials


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    report: dict = {"stage0": {}, "stage1": {}, "ok": False}
    src = config.SOURCE_PATH
    if not src.is_file():
        print("FAIL source missing", src)
        return 2

    sha_before = sha256_file(src)
    size = src.stat().st_size
    print("SRC_BYTES", size)
    print("SHA_BEFORE", sha_before)
    if size != config.SOURCE_EXPECT_BYTES or sha_before != config.SOURCE_EXPECT_SHA256:
        print("FAIL source gate", "bytes", size, "sha", sha_before)
        report["stage0"]["fail"] = "source_sha_or_bytes"
        return 2

    raw = src.read_text(encoding="utf-8")
    data = json.loads(raw)
    sha_after = sha256_file(src)
    print("SHA_AFTER", sha_after)
    if sha_after != sha_before:
        print("FAIL sha changed while reading")
        return 2
    if not isinstance(data, list):
        print("FAIL top type", type(data).__name__)
        return 2

    # ---- parse ----
    hymns = []
    parse_fail = []
    series_counter = Counter()
    keys = []
    category_counter = Counter()
    cat_null_by_series = Counter()
    cat_present_by_series = Counter()

    for i, rec in enumerate(data):
        try:
            series, number, title = parse_name(rec.get("name") or "")
        except ValueError as exc:
            parse_fail.append({"i": i, "name": rec.get("name"), "error": str(exc)})
            continue
        category, subtitle = split_title(title)
        message_key = f"{series}|{number}"
        keys.append(message_key)
        series_counter[series] += 1
        if category is None:
            cat_null_by_series[series] += 1
        else:
            cat_present_by_series[series] += 1
            category_counter[category] += 1
        hymns.append(
            {
                "i": i,
                "raw": rec,
                "series": series,
                "hymn_number": number,
                "title": title,
                "category": category,
                "subtitle": subtitle,
                "message_key": message_key,
            }
        )

    report["stage0"] = {
        "sha": sha_after,
        "bytes": size,
        "n": len(data),
        "series": dict(series_counter),
        "parse_fail": parse_fail,
        "message_key_unique": len(set(keys)),
        "message_key_n": len(keys),
        "category_kinds": len(category_counter),
        "category_counts": dict(category_counter.most_common()),
        "cat_null_by_series": dict(cat_null_by_series),
        "cat_present_by_series": dict(cat_present_by_series),
    }
    print("SERIES", dict(series_counter))
    print("PARSE_FAIL", len(parse_fail))
    print("CAT_KINDS", len(category_counter))
    print("CAT_NULL", dict(cat_null_by_series))

    if parse_fail:
        print("FAIL parse", parse_fail[:20])
        Path(r"C:\Users\28121\AppData\Local\Temp\hymns_build_stage0.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 2

    if len(hymns) != config.EXPECT_HYMNS:
        print("FAIL hymn count", len(hymns))
        return 2
    for s, n in config.EXPECT_SERIES.items():
        if series_counter.get(s) != n:
            print("FAIL series count", s, series_counter.get(s), "expect", n)
            return 2
    if len(keys) != len(set(keys)):
        dups = [k for k, v in Counter(keys).items() if v > 1]
        print("FAIL message_key dups", dups[:20])
        return 2

    print("STAGE0_OK")

    # ---- stage 1 chunks ----
    all_chunks: list[dict] = []
    n_full = n_stanza = n_chorus = 0
    coverage_fail = []
    empty_text = []
    special_notes: list[dict] = []

    for h in hymns:
        try:
            full, units, specials = build_hymn_chunks(h["raw"])
        except Exception as exc:
            coverage_fail.append({"name": h["raw"].get("name"), "error": str(exc)})
            continue
        # coverage：单位块正文（去掉 name 行）按序拼接
        unit_bodies = []
        for u in units:
            body = u["text"].split("\n", 1)[1] if "\n" in u["text"] else ""
            unit_bodies.append(body)
        joined = "\n".join(unit_bodies)
        content = h["raw"].get("content") or ""
        if normalize_lyrics(joined) != normalize_lyrics(content):
            coverage_fail.append(
                {
                    "name": h["raw"].get("name"),
                    "error": "coverage_mismatch",
                    "content_norm_len": len(normalize_lyrics(content)),
                    "joined_norm_len": len(normalize_lyrics(joined)),
                }
            )
            continue
        n_full += 1
        for u in units:
            if u["unit_type"] == "stanza":
                n_stanza += 1
            elif u["unit_type"] == "chorus":
                n_chorus += 1
        all_chunks.append(full)
        all_chunks.extend(units)
        special_notes.extend(specials)
        if not full["text"].strip():
            empty_text.append(full["chunk_id"])
        for u in units:
            if not u["text"].strip():
                empty_text.append(u["chunk_id"])

    ids = [c["chunk_id"] for c in all_chunks]
    id_dups = [k for k, v in Counter(ids).items() if v > 1]
    n_units = n_stanza + n_chorus
    n_total = len(all_chunks)

    report["stage1"] = {
        "n_full": n_full,
        "n_stanza": n_stanza,
        "n_chorus": n_chorus,
        "n_units": n_units,
        "n_total": n_total,
        "coverage_fail": coverage_fail[:50],
        "coverage_fail_n": len(coverage_fail),
        "id_dups": id_dups[:20],
        "empty_text_n": len(empty_text),
        "special_notes": special_notes,
    }
    print(
        "COUNTS",
        "full", n_full,
        "stanza", n_stanza,
        "chorus", n_chorus,
        "units", n_units,
        "total", n_total,
    )
    print("COVERAGE_FAIL", len(coverage_fail))
    print("ID_DUP", len(id_dups), "EMPTY_TEXT", len(empty_text))

    gates = [
        (n_full == config.EXPECT_FULL, "full"),
        (n_stanza == config.EXPECT_STANZA, "stanza"),
        (n_chorus == config.EXPECT_CHORUS, "chorus"),
        (n_units == config.EXPECT_UNITS, "units"),
        (n_total == config.EXPECT_TOTAL, "total"),
        (not coverage_fail, "coverage"),
        (not id_dups, "chunk_id_unique"),
        (not empty_text, "text_nonempty"),
    ]
    for ok, label in gates:
        if not ok:
            print("FAIL gate", label)
            Path(r"C:\Users\28121\AppData\Local\Temp\hymns_build_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return 2

    # write dirs + clean json + source copy
    config.DIR_SRC.mkdir(parents=True, exist_ok=True)
    config.DIR_CLEAN.mkdir(parents=True, exist_ok=True)
    config.DIR_VEC.mkdir(parents=True, exist_ok=True)
    if not config.SOURCE_COPY.exists() or sha256_file(config.SOURCE_COPY) != sha_after:
        shutil.copy2(src, config.SOURCE_COPY)
    config.SOURCE_MD.write_text(
        "\n".join(
            [
                "# 源文件",
                "",
                f"- 源路径：`{src}`",
                f"- 字节：{size}",
                f"- SHA256：`{sha_after}`",
                f"- 记录数：{len(data)}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_jsonl(config.CLEAN_JSON, all_chunks)
    print("WROTE", config.CLEAN_JSON, "n", n_total)

    report["ok"] = True
    report["clean_json"] = str(config.CLEAN_JSON)
    Path(r"C:\Users\28121\AppData\Local\Temp\hymns_build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # also a slim summary next to data
    (config.DATA_ROOT / "build_stage1_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("STAGE1_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
