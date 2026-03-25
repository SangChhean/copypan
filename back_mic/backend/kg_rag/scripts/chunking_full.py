# -*- coding: utf-8 -*-
"""统一 Chunking 脚本：支持 life / cwwl / cwwn / others / bib / map_note 六种数据源。

流式读取（ijson），增量写出，避免大文件（如 cwwl 3.2 GB）导致的内存问题。

用法示例：
    python -m kg_rag.scripts.chunking_full \
        --input  data/raw/cwwl.json \
        --output data/chunks/cwwl_chunks.json \
        --source cwwl
"""
import argparse
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Generator, IO

import ijson


class _EmbeddingByteFixer:
    """Replace every ``"embedding":[...]`` array with ``"embedding":[]``.

    cwwl.json contains a document where a 7 MB binary blob was embedded inside
    the ``embedding`` array, causing ijson to fail.  We do not need embedding
    values for chunking, so the safest fix is to discard array contents entirely.

    End-of-array detection: the REAL closing ``]`` is **always immediately
    followed by ``,``** (0x2C) in the cwwl doc structure (``"embedding":[...],"_id":``).
    Stray ``]`` bytes inside binary blobs are followed by non-comma bytes, making
    ``],`` a reliable terminator.

    Exposes only ``read(n)`` so ijson's Python backend can use it directly.
    """

    _KEY = b'"embedding"'

    def __init__(self, fp: IO[bytes]) -> None:
        self._fp = fp
        self._buf: bytearray = bytearray()
        self._in_arr: bool = False

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = 1 << 20  # 1 MiB default
        KL = len(self._KEY)
        out = bytearray()

        # Outer loop: keep reading until we have ≥n output bytes or true EOF.
        # This is critical when we are in embedding-skip mode: we may consume
        # millions of source bytes before emitting a single ']', and returning
        # b'' would cause callers (ijson) to treat it as EOF prematurely.
        while len(out) < n:
            # Ensure buffer has enough bytes for processing + lookahead
            while len(self._buf) < max(n - len(out), 1) + KL + 8:
                chunk = self._fp.read(65536)
                if not chunk:
                    break
                self._buf.extend(chunk)

            if not self._buf:
                break  # truly exhausted

            lim = len(self._buf)
            i = 0
            buf_exhausted_at = lim  # track if inner loop ran out of buffer

            inner_produced = len(out)  # track output growth in this inner pass

            while i < lim and len(out) < n:
                c = self._buf[i]

                if self._in_arr:
                    # Skip all bytes, looking for ], "_id" (the true array-close
                    # is followed by the `"_id"` field — the only field starting
                    # with `_` in cwwl docs).  This is 7-byte specific enough to
                    # avoid false positives in binary blobs.
                    if c == 0x5D:  # ']'
                        if i + 8 >= lim:
                            buf_exhausted_at = i
                            break  # need more lookahead — outer loop will refill
                        j = i + 1
                        # skip optional whitespace
                        while j < lim and self._buf[j] in (0x20, 0x09, 0x0A, 0x0D):
                            j += 1
                        if j >= lim:
                            buf_exhausted_at = i
                            break
                        if self._buf[j] == 0x2C:  # ','
                            j += 1
                            while j < lim and self._buf[j] in (0x20, 0x09, 0x0A, 0x0D):
                                j += 1
                            if j + 4 < lim and self._buf[j:j + 5] == b'"_id"':
                                out.append(0x5D)  # emit ']' closing the empty []
                                self._in_arr = False
                    i += 1  # always advance (discard)

                else:
                    # Normal mode: watch for "embedding":[ key;
                    # also sanitize stray control bytes (corruption in text fields).
                    if lim - i < KL + 4 and len(self._buf) >= (n - len(out)) + KL + 8:
                        # Not near EOF but insufficient lookahead — wait for refill
                        buf_exhausted_at = i
                        break
                    if self._buf[i: i + KL] == self._KEY:
                        j = i + KL
                        while j < lim and self._buf[j] in (0x3A, 0x20, 0x09, 0x0A, 0x0D):
                            j += 1
                        if j < lim and self._buf[j] == 0x5B:
                            out.extend(self._buf[i: j + 1])  # key + [
                            self._in_arr = True
                            i = j + 1
                        else:
                            # Replace ALL control chars (0x00–0x1F) with space.
                            # Raw 0x0A/0x0D inside a JSON string literal is
                            # illegal in YAJL; structural newlines between tokens
                            # are whitespace-insensitive, so replacing them with
                            # 0x20 still produces valid JSON.
                            out.append(c if c >= 0x20 else 0x20)
                            i += 1
                    else:
                        # Replace ALL control chars with space (same rationale).
                        out.append(c if c >= 0x20 else 0x20)
                        i += 1

            self._buf = self._buf[i:]

            # If inner loop made no progress (stuck at same position with no
            # output and buffer not growing), stop to avoid infinite loop.
            if len(out) == inner_produced and i == 0 and not self._buf:
                break

        return bytes(out)


class _FixerBufferedIO(io.BufferedIOBase):
    """``io.BufferedIOBase`` adapter around ``_EmbeddingByteFixer``.

    ``io.TextIOWrapper`` requires a ``BufferedIOBase``.  By subclassing it
    directly and overriding ``read()`` we avoid the ``readinto`` +
    memoryview-slice-assignment incompatibility that arises when delegating
    through ``io.RawIOBase`` + ``io.BufferedReader``.
    """

    def __init__(self, fixer: "_EmbeddingByteFixer") -> None:
        super().__init__()
        self._fixer = fixer

    def readable(self) -> bool:
        return True

    def read(self, n: int = -1) -> bytes:  # type: ignore[override]
        if n is None or n < 0:
            n = 1 << 20
        return self._fixer.read(n)

    def read1(self, n: int = -1) -> bytes:  # type: ignore[override]
        return self.read(n)


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

# 圣经书卷简称（旧约 + 新约），多字书卷名排在单字之前（长优先匹配）
_BOOK_SET: list[str] = sorted([
    # 旧约
    "创", "出", "利", "民", "申", "书", "士", "得",
    "撒上", "撒下", "王上", "王下", "代上", "代下",
    "拉", "尼", "斯", "伯", "诗", "箴", "传", "歌",
    "赛", "耶", "哀", "结", "但",
    "何", "珥", "摩", "俄", "拿", "弥", "鸿", "哈", "番", "该", "亚", "玛",
    # 新约
    "太", "可", "路", "约", "徒", "罗",
    "林前", "林后", "加", "弗", "腓", "西",
    "帖前", "帖后", "提前", "提后", "多", "门", "来", "雅",
    "彼前", "彼后", "约壹", "约贰", "约叁", "犹", "启",
], key=len, reverse=True)

_BOOK_PATTERN = re.compile("|".join(re.escape(b) for b in _BOOK_SET))

# 经节引用匹配：书卷名后须紧跟章节数字（汉字数字或阿拉伯数字），避免误识别普通词汇
_SCRIPTURE_REF_RE = re.compile(
    r"(?:" + "|".join(re.escape(b) for b in _BOOK_SET) + r")"
    r"[一二三四五六七八九十百千〇\d]"
)

# 括号内容匹配（中/英文括号，最长 40 字符）
_BRACKET_RE = re.compile(r"[（(]([^）)]{1,40})[）)]")

# 标点断句正则
_PUNCT_SPLIT_RE = re.compile(r"(?<=[。！？；])")

# 标题分割正则（第X篇/题/课/章/问/期 或 特殊词）
_MSG_HEAD_RE = re.compile(
    r"第[一二三四五六七八九十百零〇\d]+[篇题课章问期]"
    r"|(?:介言|附录|自序|序|说明|引言|内容提要|前言|开头的话)"
)


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数：字符数 / 1.5，最小 0。"""
    return max(0, int(len(text) / 1.5))


def split_by_punctuation(text: str, max_tokens: int = 800) -> list[str]:
    """将超长文本按标点（。！？；）贪心拆分，每段 estimate_tokens ≤ max_tokens。

    - 保留标点在句末
    - 单句本身超过 max_tokens 时单独成段（不再拆）
    - 不产生空串
    """
    sentences = [s for s in _PUNCT_SPLIT_RE.split(text) if s]
    segments: list[str] = []
    current = ""
    for sent in sentences:
        candidate = current + sent
        if estimate_tokens(candidate) <= max_tokens:
            current = candidate
        else:
            if current:
                segments.append(current)
            # 单句超长时单独成段
            current = sent
    if current:
        segments.append(current)
    return segments


def extract_scripture_refs(text: str) -> list[str]:
    """提取文本中括号内含圣经书卷名+章节数字的经节引用，返回去重列表。
    书卷名后须紧跟章节数字（汉字或阿拉伯数字），避免误识别普通词汇（如「约定」）。
    """
    refs: list[str] = []
    seen: set[str] = set()
    for m in _BRACKET_RE.finditer(text):
        content = m.group(1)
        if _SCRIPTURE_REF_RE.search(content):
            key = m.group(0)
            if key not in seen:
                seen.add(key)
                refs.append(key)
    return refs


def parse_title(title: str) -> tuple[str, str]:
    """将完整 title 拆分为 (book_title, message_title)。

    第一层：找最后一个 第X篇/题/课/章/问/期 或 特殊词 的位置作为 message_title 起点。
    第二层兜底：若含 ，则按第一个 ， 拆；否则整个作为 book_title，message_title 为空。
    """
    matches = list(_MSG_HEAD_RE.finditer(title))
    if matches:
        last = matches[-1]
        book = title[: last.start()].rstrip("，, \t\u3000")
        msg = title[last.start():]
        return (book, msg)
    # 兜底
    if "，" in title:
        idx = title.index("，")
        return (title[:idx].strip(), title[idx + 1:].strip())
    return (title.strip(), "")


def _iter_top_array(fp: IO[bytes]) -> Generator[Any, None, None]:
    """流式迭代 JSON 文件顶层数组的每个元素。"""
    yield from ijson.items(fp, "item")


class _JsonArrayWriter:
    """增量写出 JSON 数组；逐条调用 write()，最后调用 close()。"""

    def __init__(self, path: str | Path):
        self._f = open(path, "w", encoding="utf-8")
        self._f.write("[\n")
        self._first = True

    def write(self, obj: Any) -> None:
        if not self._first:
            self._f.write(",\n")
        self._f.write(json.dumps(obj, ensure_ascii=False))
        self._first = False

    def close(self) -> None:
        self._f.write("\n]\n")
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ---------------------------------------------------------------------------
# 内部辅助：通用 chunk 构建
# ---------------------------------------------------------------------------

def _build_chunk(
    chunk_id: str,
    text: str,
    en: str,
    book_title: str,
    author: str,
    year: int | None,
    message_key: str,
    message_number: int,
    message_title: str,
    section_title: str | None,
    paragraph_type: str,
    source_zh: str,
    source_en: str,
    original_ids: list[str],
) -> dict:
    """构建标准 chunk dict（16 字段，不含 embedding）。"""
    return {
        "chunk_id": chunk_id,
        "text": text,
        "en": en,
        "book_title": book_title,
        "author": author,
        "year": year,
        "message_key": message_key,
        "message_number": message_number,
        "message_title": message_title,
        "section_title": section_title,
        "paragraph_type": paragraph_type,
        "scripture_refs": extract_scripture_refs(text),
        "source_zh": source_zh,
        "source_en": source_en,
        "tokens": estimate_tokens(text),
        "original_ids": original_ids,
    }


def _iter_cwwl_lines(filepath: Path) -> Generator[dict, None, None]:
    """逐行读取 cwwl.json，跳过 [ ] 行，每行 parse 为 dict。

    cwwl.json 每行是一条完整的 JSON 对象（可能有末尾逗号），
    此方法避开 ijson 流式解析，直接用 json.loads 逐行解析，
    从而彻底绕过文件中嵌入的二进制数据导致的 ijson 崩溃问题。
    丢弃 embedding / zh / _id 字段以节省内存。
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line == "[" or line == "]":
                continue
            if line.endswith(","):
                line = line[:-1]
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(doc, dict):
                continue
            doc.pop("embedding", None)
            doc.pop("zh", None)
            doc.pop("_id", None)
            yield doc


# ---------------------------------------------------------------------------
# 职事类通用处理引擎（life / cwwl / cwwn / others 共用）
# ---------------------------------------------------------------------------

def _open_for_iter(path: Path, safe_mode: bool = False):
    """Return a context manager that opens *path* for ijson streaming.

    safe_mode=True wraps the binary stream with _EmbeddingByteFixer to handle
    files (e.g. cwwl.json) that contain corrupted bytes inside embedding arrays.
    When safe_mode=False the file is opened as UTF-8 text with errors='replace'
    which is sufficient for well-formed files.
    """
    if safe_mode:
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            raw = open(path, "rb")
            try:
                fixer = _EmbeddingByteFixer(raw)
                # Wrap in BufferedIOBase → TextIOWrapper so that:
                # 1. embedding arrays are replaced with []  (handled by fixer)
                # 2. any remaining invalid UTF-8 bytes in other fields are
                #    silently replaced with U+FFFD instead of crashing ijson.
                text = io.TextIOWrapper(_FixerBufferedIO(fixer), encoding="utf-8", errors="replace")
                yield text
            finally:
                raw.close()

        return _ctx()
    else:
        return open(path, "r", encoding="utf-8", errors="replace")


def _process_ministry_source(
    input_path: Path,
    output_path: Path,
    prefix: str,
    parse_id_fn: Any,   # (doc_id: str) -> (group_key: str, sort_key: tuple, msg_num: int)
    author: str,
    year: int | None,
    log_tag: str,
    year_from_key: Any = None,  # 可选：(group_key: str) -> int | None，用于动态提取 year
    safe_mode: bool = False,    # cwwl: True（修复 embedding 字段中的非 ASCII 字节）
    iter_fn: Any = None,        # 可选：(Path) -> Generator[dict]，替代默认的 _open_for_iter + _iter_top_array
) -> None:
    """职事类文档的两遍扫描 + chunking 引擎。

    Pass 1 — 收集所有 heading 元数据（group_key → sorted[(sort_key, text)]）
    Pass 2 — 流式处理 text 文档，按 sort_key 查表确定 section_title

    当 *iter_fn* 不为 None 时，直接调用 ``iter_fn(input_path)`` 获取迭代器
    （用于 cwwl 的逐行读取方案，绕过 ijson）。
    """

    def _default_iter():
        with _open_for_iter(input_path, safe_mode) as fp:
            yield from _iter_top_array(fp)

    def _make_iter():
        return iter_fn(input_path) if iter_fn else _default_iter()

    # ── Pass 1：收集 heading 元数据 ─────────────────────────────────────
    print(f"  [{log_tag}] Pass 1: 收集 heading 元数据...")
    heading_map: dict[str, list[tuple[tuple, str]]] = {}
    for doc in _make_iter():
        doc_id = doc.get("id", "")
        if not doc_id.startswith(prefix):
            continue
        doc_type = doc.get("type", "").strip()
        if "heading" not in doc_type and doc_type != "preface_heading":
            continue
        group_key, sort_key, _ = parse_id_fn(doc_id)
        heading_map.setdefault(group_key, []).append(
            (sort_key, (doc.get("text") or "").strip())
        )
    for gk in heading_map:
        heading_map[gk].sort()
    print(f"  [{log_tag}] 收集 heading: {sum(len(v) for v in heading_map.values())} 条"
          f"，{len(heading_map)} 个组")

    def _section_for(group_key: str, sort_key: tuple) -> str | None:
        section: str | None = None
        for hsk, htext in heading_map.get(group_key, []):
            if hsk < sort_key:
                section = htext or None
            else:
                break
        return section

    # ── Pass 2：流式处理 text 文档 ──────────────────────────────────────
    def _process_group(group_docs: list, writer: _JsonArrayWriter) -> None:
        if not group_docs:
            return
        group_docs.sort(key=lambda d: d["_sort_key"])

        message_key: str = group_docs[0]["_group_key"]
        message_number: int = group_docs[0]["_message_number"]
        raw_title = next((d.get("title", "") for d in group_docs if d.get("title")), "")
        book_title, message_title = parse_title(raw_title) if raw_title else ("", "")
        effective_year = year_from_key(message_key) if year_from_key else year

        buf: list[dict] = []

        def flush() -> None:
            if not buf:
                return
            first = buf[0]
            src: list = first.get("source") or []
            sec = _section_for(message_key, first["_sort_key"])
            if len(buf) == 1:
                chunk_id = first["id"]
                text = first.get("text", "")
                en = first.get("en", "")
                oids = [first["id"]]
            else:
                chunk_id = first["id"]
                text = "".join(d.get("text", "") for d in buf)
                en = "".join(d.get("en", "") for d in buf)
                oids = [d["id"] for d in buf]
            writer.write(_build_chunk(
                chunk_id=chunk_id, text=text, en=en,
                book_title=book_title, author=author, year=effective_year,
                message_key=message_key, message_number=message_number,
                message_title=message_title, section_title=sec,
                paragraph_type="text",
                source_zh=src[0] if src else "",
                source_en=src[1] if len(src) > 1 else "",
                original_ids=oids,
            ))
            buf.clear()

        def buf_tokens() -> int:
            return estimate_tokens("".join(d.get("text", "") for d in buf))

        for doc in group_docs:
            text = doc.get("text", "")
            if not text or not text.strip():   # 空文本或纯空白跳过
                continue
            tokens = estimate_tokens(text)
            src: list = doc.get("source") or []
            s_zh = src[0] if src else ""
            s_en = src[1] if len(src) > 1 else ""
            sec = _section_for(message_key, doc["_sort_key"])

            if tokens < 150:
                if buf:
                    buf_sec = _section_for(message_key, buf[0]["_sort_key"])
                    if buf_sec != sec or buf_tokens() + tokens > 800:
                        flush()
                buf.append(doc)

            elif tokens <= 800:
                flush()
                writer.write(_build_chunk(
                    chunk_id=doc["id"], text=text, en=doc.get("en", ""),
                    book_title=book_title, author=author, year=effective_year,
                    message_key=message_key, message_number=message_number,
                    message_title=message_title, section_title=sec,
                    paragraph_type="text",
                    source_zh=s_zh, source_en=s_en,
                    original_ids=[doc["id"]],
                ))

            else:  # tokens > 800
                flush()
                parts = split_by_punctuation(text, 800)
                for i, part in enumerate(parts):
                    cid = f"{doc['id']}_p{i + 1}" if len(parts) > 1 else doc["id"]
                    writer.write(_build_chunk(
                        chunk_id=cid, text=part,
                        en=doc.get("en", "") if i == 0 else "",
                        book_title=book_title, author=author, year=effective_year,
                        message_key=message_key, message_number=message_number,
                        message_title=message_title, section_title=sec,
                        paragraph_type="text",
                        source_zh=s_zh, source_en=s_en,
                        original_ids=[doc["id"]],
                    ))

        flush()

    with _JsonArrayWriter(output_path) as writer:
        current_key: str | None = None
        group_buf: list[dict] = []
        total = 0

        for doc in _make_iter():
            doc_id = doc.get("id", "")
            if not doc_id.startswith(prefix):
                continue
            if doc.get("type", "").strip() != "text":
                continue

            group_key, sort_key, msg_num = parse_id_fn(doc_id)
            doc["_group_key"] = group_key
            doc["_sort_key"] = sort_key
            doc["_message_number"] = msg_num

            if current_key is None:
                current_key = group_key
            if group_key != current_key:
                _process_group(group_buf, writer)
                group_buf = []
                current_key = group_key

            group_buf.append(doc)
            total += 1
            if total % 10000 == 0:
                print(f"  [{log_tag}] Pass 2: 已处理 {total} 条 text 文档...")

        _process_group(group_buf, writer)

    print(f"[{log_tag}] 完成，共处理 {total} 条 text 文档。")


# ---------------------------------------------------------------------------
# 各数据源处理函数
# ---------------------------------------------------------------------------

def process_life(input_path: Path, output_path: Path) -> None:
    """life_gen 生命读经系列（life.json）。ID: life_{书号}-{篇号}-{段序号}"""

    def _parse_id(doc_id: str) -> tuple[str, tuple, int]:
        rest = doc_id[5:]  # strip "life_"
        parts = rest.split("-")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            nums = [0] * len(parts)
        while len(nums) < 3:
            nums.append(0)
        return f"life_{nums[0]}-{nums[1]}", tuple(nums), nums[1]

    _process_ministry_source(
        input_path, output_path,
        prefix="life_", parse_id_fn=_parse_id,
        author="李常受", year=None, log_tag="life",
    )


def process_cwwl(input_path: Path, output_path: Path) -> None:
    """cwwl 全时代得胜者文库（~3.2 GB）。ID: cwwl_{年份}-{册号}-{书序号}#{章号}-{段序号}
    使用 _process_ministry_source 两遍流式扫描，确保大文件不会 OOM。
    """

    def _parse_id(doc_id: str) -> tuple[str, tuple, int]:
        # cwwl_1963-1-10#4-13 → ("cwwl_1963-1-10#4", (1963,1,10,4,13), 4)
        rest = doc_id[5:]  # strip "cwwl_"
        if "#" not in rest:
            return doc_id, (0, 0, 0, 0, 0), 0
        left, right = rest.split("#", 1)
        left_parts = left.split("-")
        right_parts = right.split("-")
        try:
            l_nums = [int(p) for p in left_parts]
            r_nums = [int(p) for p in right_parts]
        except ValueError:
            l_nums, r_nums = [0, 0, 0], [0, 0]
        while len(l_nums) < 3:
            l_nums.append(0)
        while len(r_nums) < 2:
            r_nums.append(0)
        group_key = f"cwwl_{l_nums[0]}-{l_nums[1]}-{l_nums[2]}#{r_nums[0]}"
        sort_key = (l_nums[0], l_nums[1], l_nums[2], r_nums[0], r_nums[1])
        return group_key, sort_key, r_nums[0]

    def _year_from_key(group_key: str) -> int | None:
        # "cwwl_1963-1-10#4" → 1963
        try:
            rest = group_key[5:]   # strip "cwwl_"
            year_str = rest.split("-")[0]
            return int(year_str)
        except (ValueError, IndexError):
            return None

    _process_ministry_source(
        input_path, output_path,
        prefix="cwwl_", parse_id_fn=_parse_id,
        author="李常受", year=None, log_tag="cwwl",
        year_from_key=_year_from_key,
        iter_fn=_iter_cwwl_lines,
    )


def process_cwwn(input_path: Path, output_path: Path) -> None:
    """cwwn 倪柝声著作（全集）。ID: cwwn_{辑号}-{册号}#{篇号}-{段序号}"""

    def _parse_id(doc_id: str) -> tuple[str, tuple, int]:
        # cwwn_2-21#11-16 → ("cwwn_2-21#11", (2, 21, 11, 16), 11)
        rest = doc_id[5:]  # strip "cwwn_"
        if "#" not in rest:
            return doc_id, (0, 0, 0, 0), 0
        left, right = rest.split("#", 1)
        left_parts = left.split("-")
        right_parts = right.split("-")
        try:
            l_nums = [int(p) for p in left_parts]
            r_nums = [int(p) for p in right_parts]
        except ValueError:
            l_nums, r_nums = [0, 0], [0, 0]
        while len(l_nums) < 2:
            l_nums.append(0)
        while len(r_nums) < 2:
            r_nums.append(0)
        group_key = f"cwwn_{l_nums[0]}-{l_nums[1]}#{r_nums[0]}"
        sort_key = (l_nums[0], l_nums[1], r_nums[0], r_nums[1])
        return group_key, sort_key, r_nums[0]

    _process_ministry_source(
        input_path, output_path,
        prefix="cwwn_", parse_id_fn=_parse_id,
        author="倪柝声", year=None, log_tag="cwwn",
    )


def process_others(input_path: Path, output_path: Path) -> None:
    """others 其他零散书目。ID: others_{系列标识}_{篇号}-{段序号}（最后一个 _ 分割）"""

    def _parse_id(doc_id: str) -> tuple[str, tuple, int]:
        # 以最后一个 _ 分割：左部 = "others_{系列标识}"，右部 = "{篇号}-{段序号}"
        # others_1_138-29  → left="others_1",   right="138-29"  → group="others_1_138",   msg=138, seq=29
        # others_2-1_1-3   → left="others_2-1", right="1-3"     → group="others_2-1_1",   msg=1,   seq=3
        idx = doc_id.rfind("_")
        if idx < 0:
            return doc_id, (0,), 0
        left = doc_id[:idx]        # "others_1" / "others_2-1"
        right = doc_id[idx + 1:]   # "138-29"   / "1-3"
        right_parts = right.split("-")
        try:
            msg_num = int(right_parts[0])
            seq = int(right_parts[1]) if len(right_parts) > 1 else 0
        except (ValueError, IndexError):
            msg_num, seq = 0, 0
        group_key = f"{left}_{msg_num}"
        return group_key, (seq,), msg_num

    _process_ministry_source(
        input_path, output_path,
        prefix="others_", parse_id_fn=_parse_id,
        author="李常受", year=None, log_tag="others",
    )


def process_bib(input_path: Path, output_path: Path) -> None:
    """bib 圣经正文。ID: bib_{书号}-{章号}-{节号}，按章分组，相邻经节合并至 150-300 tokens。"""

    def _parse_id(doc_id: str) -> tuple[str, tuple, int, int, int]:
        # bib_23-18-3 → ("bib_23-18", (23,18,3), 23, 18, 3)
        rest = doc_id[4:]  # strip "bib_"
        parts = rest.split("-")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            nums = [0, 0, 0]
        while len(nums) < 3:
            nums.append(0)
        return f"bib_{nums[0]}-{nums[1]}", tuple(nums), nums[0], nums[1], nums[2]

    def _parse_bib_title(title: str) -> tuple[str, str]:
        # "恢复本圣经，以赛亚书，第十八章" → ("以赛亚书", "第十八章")
        parts = [p.strip() for p in title.split("，")]
        book = parts[1] if len(parts) >= 2 else ""
        msg = parts[-1] if len(parts) >= 1 else ""
        return book, msg

    def _flush(buf: list, writer: _JsonArrayWriter) -> None:
        if not buf:
            return
        first = buf[0]
        last = buf[-1]
        _, _, book_num, chap_num, first_verse = _parse_id(first["id"])
        _, _, _, _, last_verse = _parse_id(last["id"])
        group_key = f"bib_{book_num}-{chap_num}"
        chunk_id = f"{group_key}-{first_verse}_{last_verse}"
        text = "\n".join(d.get("text", "") for d in buf)
        en = "\n".join(d.get("en", "") for d in buf)
        raw_title = first.get("title", "")
        book_title, message_title = _parse_bib_title(raw_title)
        src: list = first.get("source") or []
        chunk = _build_chunk(
            chunk_id=chunk_id, text=text, en=en,
            book_title=book_title, author="恢复本圣经", year=None,
            message_key=group_key, message_number=chap_num,
            message_title=message_title, section_title=None,
            paragraph_type="verse",
            source_zh=src[0] if src else "",
            source_en=src[1] if len(src) > 1 else "",
            original_ids=[d["id"] for d in buf],
        )
        chunk["scripture_refs"] = []   # 经文本身不提取引用
        writer.write(chunk)
        buf.clear()

    def _process_chapter(chapter_docs: list, writer: _JsonArrayWriter) -> None:
        if not chapter_docs:
            return
        chapter_docs.sort(key=lambda d: d["_sort_key"])
        buf: list[dict] = []

        for doc in chapter_docs:
            text = doc.get("text", "")
            if not text or not text.strip():
                continue
            tokens = estimate_tokens(text)
            if not buf:
                buf.append(doc)
            else:
                cur = estimate_tokens("\n".join(d.get("text", "") for d in buf))
                if cur + tokens > 300:
                    _flush(buf, writer)
                    buf.append(doc)
                else:
                    buf.append(doc)

        _flush(buf, writer)  # 章末 flush，不跨章

    with open(input_path, "rb") as fp, _JsonArrayWriter(output_path) as writer:
        current_key: str | None = None
        group_buf: list[dict] = []
        total = 0

        for doc in _iter_top_array(fp):
            doc_id = doc.get("id", "")
            if not doc_id.startswith("bib_"):
                continue
            group_key, sort_key, *_ = _parse_id(doc_id)
            doc["_sort_key"] = sort_key

            if current_key is None:
                current_key = group_key
            if group_key != current_key:
                _process_chapter(group_buf, writer)
                group_buf = []
                current_key = group_key

            group_buf.append(doc)
            total += 1
            if total % 10000 == 0:
                print(f"  [bib] 已处理 {total} 条...")

        _process_chapter(group_buf, writer)

    print(f"[bib] 完成，共处理 {total} 条经节。")


def process_map_note(input_path: Path, output_path: Path) -> None:
    """map_note 注解纲目。每 doc 含 msg 数组，按 ot1 分组合并为 chunk。"""

    def _parse_doc_id(doc_id: str) -> tuple[str, int]:
        # map_note_75-1-1 → message_key="map_note_75-1", message_number=1
        parts = doc_id.split("-")
        try:
            msg_num = int(parts[-1])
        except (ValueError, IndexError):
            msg_num = 0
        message_key = "-".join(parts[:-1])
        return message_key, msg_num

    def _process_doc(doc: dict, writer: _JsonArrayWriter) -> None:
        doc_id: str = doc.get("id", "")
        book_title: str = doc.get("source", "") or ""
        message_title: str = (doc.get("text") or "").strip()
        message_key, message_number = _parse_doc_id(doc_id)

        msg_list: list = doc.get("msg") or []
        ot1_index = 0          # 当前 ot1 的序号（1-based）
        buf_texts: list[str] = []   # 当前 ot1 chunk 的 text 行
        buf_source_zh: str = ""     # 当前 ot1 的 source

        def flush(idx: int) -> None:
            """将 buf 写出为一个或多个 chunk。"""
            if not buf_texts:
                return
            text = "\n".join(buf_texts)
            base_cid = f"{doc_id}_c{idx}"
            tokens = estimate_tokens(text)
            if tokens > 800:
                parts = split_by_punctuation(text, 800)
                for i, part in enumerate(parts):
                    cid = f"{base_cid}_p{i + 1}" if len(parts) > 1 else base_cid
                    writer.write(_build_chunk(
                        chunk_id=cid, text=part, en="",
                        book_title=book_title, author="李常受", year=None,
                        message_key=message_key, message_number=message_number,
                        message_title=message_title, section_title=None,
                        paragraph_type="note",
                        source_zh=buf_source_zh, source_en="",
                        original_ids=[doc_id],
                    ))
            else:
                writer.write(_build_chunk(
                    chunk_id=base_cid, text=text, en="",
                    book_title=book_title, author="李常受", year=None,
                    message_key=message_key, message_number=message_number,
                    message_title=message_title, section_title=None,
                    paragraph_type="note",
                    source_zh=buf_source_zh, source_en="",
                    original_ids=[doc_id],
                ))
            buf_texts.clear()

        for item in msg_list:
            item_type = (item.get("type") or "").strip()
            item_text = (item.get("text") or "").strip()

            if item_type in ("bookname", "title", "b_read"):
                continue

            if item_type == "ot1":
                flush(ot1_index)          # flush 上一个 ot1（若有）
                ot1_index += 1
                buf_source_zh = item.get("source") or ""
                if item_text:
                    buf_texts.append(item_text)

            elif item_type in ("ot2", "ot3", "ot4"):
                if item_text:
                    buf_texts.append(item_text)
            # 其余 type 跳过

        flush(ot1_index)  # doc 结束：flush 最后一个 ot1

    with open(input_path, "rb") as fp, _JsonArrayWriter(output_path) as writer:
        total = 0
        for doc in _iter_top_array(fp):
            doc_id = doc.get("id", "")
            if not doc_id.startswith("map_note_"):
                continue
            _process_doc(doc, writer)
            total += 1
            if total % 1000 == 0:
                print(f"  [map_note] 已处理 {total} 个 doc...")

    print(f"[map_note] 完成，共处理 {total} 个 doc。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

SOURCES = {
    "life":     process_life,
    "cwwl":     process_cwwl,
    "cwwn":     process_cwwn,
    "others":   process_others,
    "bib":      process_bib,
    "map_note": process_map_note,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chunking_full",
        description="统一 Chunking 脚本，支持六种数据源（流式读取，增量写出）。",
    )
    parser.add_argument(
        "--input", required=True, metavar="INPUT_JSON",
        help="输入 JSON 文件路径（顶层为数组）",
    )
    parser.add_argument(
        "--output", required=True, metavar="OUTPUT_JSON",
        help="输出 JSON 文件路径（写入 chunk 数组）",
    )
    parser.add_argument(
        "--source", required=True, choices=list(SOURCES.keys()),
        metavar="SOURCE",
        help=f"数据源类型，可选值：{', '.join(SOURCES.keys())}",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"[chunking_full] 错误：输入文件不存在 → {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    handler = SOURCES[args.source]
    print(f"[chunking_full] 开始处理：source={args.source}  input={input_path}  output={output_path}")
    handler(input_path, output_path)
    print("[chunking_full] 完成。")


if __name__ == "__main__":
    main()
