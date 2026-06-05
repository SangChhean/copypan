# 增强式翻译（Enhanced Translate）完整设计文档

> 面向学生与 AI 辅助开发者。读完本文档后，应能理解每一个设计决策的原因，并能从零复刻同等功能。

---

## 一、产品定位与核心问题

### 1.1 要解决什么问题

职事文学（Watchman Nee / Witness Lee 著作）有大量固定术语和句式，已有官方英译本。如果直接用通用 LLM 翻译中文纲目，会出现两类问题：

1. **术语不一致**：LLM 自由发挥，同一个词每次译法不同，与已有英译本不符。
2. **成本与延迟**：同一批纲目反复翻译，每次都调用 Gemini，既浪费钱又慢。

增强式翻译的核心思路是：**先查，再译**。能从语料库里直接查到的，不调用 Gemini；查不到的，把相关语料作为参考一起送给 Gemini，让它在正确的术语框架内翻译。

### 1.2 输入与输出

**输入**：中文纲目文本，多行，每行结构为：

```
[序号前缀][正文内容][读经后缀]
```

例：
```
一	神圣的生命；基督的经历—约一1：
二	职事的路
壹	神的经纶
```

**输出**：
- 英文纲目（行对齐）
- 每行的参考语料明细（供审校）
- 统计摘要（命中率、Gemini 成本等）

---

## 二、整体架构：四个阶段

整个翻译流程分为严格的四个阶段，**前三个阶段不调用 Gemini**：

```
阶段一：解析（Parse）
    每行拆成 prefix / body / suffix
    判断行类型 outline / reference

阶段二：查缓存（Cache Lookup）
    两个 Pool 按优先级短路

阶段三：检索（Retrieve）
    未命中 Pool 的行，做子句级 ES 检索

阶段四：翻译与组装（Translate & Assemble）
    需要 batch 的行调用 Gemini 批量翻译
    有读经后缀的行额外调用 _translate_suffix（单独 Gemini）
```

---

## 三、阶段一：行解析（完整详解）

### 3.1 一行纲目的完整结构

```
[prefix]        [body]                    [suffix]
一\t            神圣的生命；基督的经历     —约一1：
壹\t            神的经纶
(一)\t          召会的建造                —太十六18：
```

| 部分 | 定义 | 英文处理 |
|------|------|----------|
| `prefix` | 行首序号 + 紧跟的 Tab 或全角空格 | 查 `_PREFIX_TO_EN` 规则表，不走 Gemini |
| `body` | prefix 之后、suffix 之前的正文 | 走 Pool → 检索 → Gemini 流程 |
| `suffix` | 行末读经标注，以 `—` 开头 | 单独调用 Gemini 翻译为英文缩写格式 |

---

### 3.2 所有正则与变量定义（逐行解释）

#### 3.2.1 `_MINISTERIALIZE_PREFIX_RE` — 识别序号 prefix

```python
_MINISTERIALIZE_PREFIX_RE = re.compile(
    r"^[壹貳贰參叄叁参肆伍陸陆柒捌玖拾一二三四五六七八九十\da-z（）()]+[\t　]"
)
```

**字符集逐一说明**：

| 字符 | 含义 |
|------|------|
| `壹貳贰參叄叁参肆伍陸陆柒捌玖拾` | 大写中文数字（繁简体兼容：贰/貳 都是二，参/參/叄 都是三，陆/陸 都是六） |
| `一二三四五六七八九十` | 小写中文数字（A/B/C/D/E 级序号） |
| `\d` | 阿拉伯数字 0-9 |
| `a-z` | 小写英文字母（(a)(b)(c) 子序号） |
| `（）()` | 中英文括号（用于 `(一)` `（a）` 等带括号序号） |
| `+` | 以上字符一个或多个 |
| `[\t　]` | Tab（`\t`）或全角空格（`　`，U+3000）—— 必须紧跟才算 prefix |

**匹配示例**：

| 行首内容 | 匹配结果 |
|----------|----------|
| `一\t神圣的生命` | ✅ prefix=`一\t` |
| `壹\t神的经纶` | ✅ prefix=`壹\t` |
| `(一)\t召会` | ✅ prefix=`(一)\t` |
| `1\t生命` | ✅ prefix=`1\t` |
| `a\t信心` | ✅ prefix=`a\t` |
| `神圣的生命` | ❌ 无序号+Tab 结构 |
| `一神圣的生命` | ❌ 序号后无 Tab 或全角空格 |

---

#### 3.2.2 圣经书卷相关变量（读经后缀识别）

**`_BIBLE_BOOKS_66`**：

```python
_BIBLE_BOOKS_66 = (
    "创出利民申书士得撒上撒下王上王下代上代下拉尼斯伯诗箴传歌赛耶哀结但"
    "何珥摩俄拿弥鸿哈番该亚玛"
    "太可路约徒罗林前林后加弗腓西帖前帖后提前提后多门来雅彼前彼后约壹约贰约叁犹启"
    "参"
)
```

66 卷圣经中文缩写字符串，旧约→新约顺序，包含多字缩写（撒上、王下、林前等）。末尾「参」是「参考」。

**`_BIBLE_BOOKS`**：

```python
_BIBLE_BOOKS = "".join(dict.fromkeys(_BIBLE_BOOKS_66))
```

用 `dict.fromkeys` 对字符去重（保持顺序）。「撒上撒下」里的「撒」去重后只保留一个，得到可放入正则字符类 `[...]` 的字符集。

**`_BOOK_PAT`**：

```python
_BOOK_PAT = rf"[{_BIBLE_BOOKS}]{{1,4}}"
```

匹配 1–4 个圣经字符（`{{1,4}}` 是 f-string 里 `{1,4}` 的转义写法）：
- 单字：`约`（约翰）、`太`（马太）
- 双字：`撒上`、`林前`
- 多字：`约壹`、`帖前`

**`_CHAP_PAT`**：

```python
_CHAP_PAT = r"[\d一二三四五六七八九十百～~\-至、\s]+"
```

匹配章节数字部分：

| 字符 | 用途 |
|------|------|
| `\d` | 阿拉伯数字 |
| `一二三四五六七八九十百` | 中文数字（如「三16」） |
| `～~` | 全/半角波浪号（范围，如「一～三」） |
| `\-` | 连字符（如「1-3」） |
| `至` | 汉字范围（如「一至三章」） |
| `、` | 顿号（列举，如「3、4、5」） |
| `\s` | 空白字符 |

**`_REF_UNIT`**：

```python
_REF_UNIT = rf"(?:{_BOOK_PAT})?{_CHAP_PAT}"
```

一个引用单元 = 可选书卷名 + 章节数字。用于多段引用里第二段可省略书卷名的情况（如「约三16；四14」）。

**`_SCRIPTURE_REF_RE`**：

```python
_SCRIPTURE_REF_RE = re.compile(
    rf"(—{_BOOK_PAT}{_CHAP_PAT}(?:[,，；;]{_REF_UNIT})*[：:。]?\s*)$"
)
```

| 部分 | 含义 |
|------|------|
| `—` | 破折号，读经后缀固定开头 |
| `{_BOOK_PAT}` | 第一个书卷名（必须有） |
| `{_CHAP_PAT}` | 第一段章节 |
| `(?:[,，；;]{_REF_UNIT})*` | 零个或多个后续引用，逗号/分号分隔 |
| `[：:。]?` | 可选冒号或句号结尾 |
| `\s*` | 可选尾部空白 |
| `$` | 行末锚点 |

匹配示例：`—约三16：`、`—太五3-12：`、`—林前十五45，约一1：`

**`_PURE_VERSE_RE`**：

```python
_PURE_VERSE_RE = re.compile(r"(—[\d～~\-至、\s\d]+节[。：:]?\s*)$")
```

备用，匹配「—3-5节」这类只有节数无书卷名的情况，在 `_SCRIPTURE_REF_RE` 失败时使用。

---

#### 3.2.3 `_PREFIX_TO_EN` — 序号翻译规则表

```python
_PREFIX_TO_EN = {
    "壹": "I.",   "贰": "II.",   "參": "III.",  "参": "III.",
    "肆": "IV.",  "伍": "V.",    "陆": "VI.",   "陸": "VI.",
    "柒": "VII.", "捌": "VIII.", "玖": "IX.",   "拾": "X.",
    "一": "A.",   "二": "B.",    "三": "C.",    "四": "D.",   "五": "E.",
}
```

- `参` 和 `參` 都映射 `"III."`（简繁体兼容）
- `陆` 和 `陸` 都映射 `"VI."`（简繁体兼容）
- 大写中文数字 → 罗马数字（I. II. III. …）
- 小写中文数字 → 英文字母（A. B. C. …）

---

#### 3.2.4 `_OUTLINE_HEAD_RE` — 判断行类型

```python
_OUTLINE_HEAD_RE = re.compile(
    r"^(?:"
    r"[壹贰叁肆伍陆柒捌一二三四五六七八九十]"
    r"|\d+"
    r"|[a-z]"
    r"|[（(](?:[一二三四五六七八九十]+|\d+|[a-z])[)）]"
    r")"
)
```

四个分支：

| 分支 | 正则 | 匹配示例 |
|------|------|----------|
| 大/小写中文数字 | `[壹贰叁肆伍陆柒捌一二三四五六七八九十]` | `一神圣的生命`、`壹神的经纶` |
| 阿拉伯数字 | `\d+` | `1生命`、`12节` |
| 小写字母 | `[a-z]` | `a信心` |
| 带括号序号 | `[（(](?:[一二三四五六七八九十]+\|\d+\|[a-z])[)）]` | `(一)召会`、`（2）生命`、`(a)信心` |

**注意区别**：
- `_MINISTERIALIZE_PREFIX_RE` → 匹配**整行**开头，含 Tab，用于从整行剥离 prefix
- `_OUTLINE_HEAD_RE` → 匹配**body**开头，无 Tab，用于判断行类型

---

#### 3.2.5 ES Pool 相关变量

**`_POOL_INDICES`**：

```python
_POOL_INDICES = ",".join([
    "life", "cwwn", "cwwl", "others",
    "bib", "foo", "hymn", "feasts",
])
```

官方翻译池的 ES 索引名列表（逗号拼接，直接传给 `es_client.search` 的 `index` 参数）。这些是 Pansearch 段落库索引，字段是 `zh`/`en`，**无** `zh.keyword` 子字段，**无** `embedding` 字段，与 `kg-rag_*` 完全不同。

**`_POOL_KEYWORD_MAX_LEN = 10`**：

短/长子句的分界线（字符数）。`≤ 10` 用 `match_phrase`，`> 10` 用 BM25。这个阈值基于实验，短文本词少 BM25 不稳定，长文本 phrase 匹配太严格。

**`_normalize_pool_text`**：

```python
def _normalize_pool_text(s: str) -> str:
    return normalize_zh(s)
```

等同于 `normalize_zh`（去空白和常见标点），专门给 pool 命中校验用，语义上强调「这是 pool 的对齐函数」。

---

#### 3.2.6 其他模块级变量

**`_INDICES_BASE`**：

```python
_INDICES_BASE = ",".join([
    "kg-rag_cwwl", "kg-rag_life", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_7feasts", "kg-rag_bib",
])
```

chunk 检索使用的 ES 索引名列表（逗号拼接），对应职事著作的 6 个 kg-rag 索引。不含 `kg-rag_map_note`、`kg-rag_pano`、`kg-rag_dictionary`（这些不适合纲目翻译参考）。

**`MAX_CONTENT_CHARS = 100_000`**：请求体纲目最大字符数，超出直接返回错误。

**`_RERANK_SEM = asyncio.Semaphore(10)`**：rerank 步骤的并发限制，防止同时发出太多 Jina API 请求。

**`_PROMPT_OVERRIDE: str = ""`**：服务级 Prompt 覆盖（进程内内存），由 `POST /update_prompt` 写入。

**`_BATCH_LINE_OUT_RE`**：

```python
_BATCH_LINE_OUT_RE = re.compile(r"^Line\s+(\d+)\s*:\s*(.*)$", re.MULTILINE)
```

用于解析 Gemini batch 输出，匹配 `Line 1: ...`、`Line 2: ...` 格式。`re.MULTILINE` 让 `^` 匹配每行行首。

---

### 3.3 三个解析函数详解

#### `_find_scripture_suffix(rest: str) -> tuple[str, str]`

```python
def _find_scripture_suffix(rest: str) -> tuple[str, str]:
    matches = list(_SCRIPTURE_REF_RE.finditer(rest))
    if matches:
        m = matches[-1]            # 取最后一个匹配
        return rest[: m.start()], m.group(0)
    m = _PURE_VERSE_RE.search(rest)
    if m:
        return rest[: m.start()], m.group(0)
    return rest, ""
```

**为什么取 `matches[-1]`**：正文里可能含「约」等圣经字符（如「大约」），取最后一个匹配确保是行末的读经标注，而不是正文中的误匹配。

#### `_strip_scripture_suffix(line: str) -> tuple[str, str, str]`

```python
def _strip_scripture_suffix(line: str) -> tuple[str, str, str]:
    text = line
    m = _MINISTERIALIZE_PREFIX_RE.match(text)
    if m:
        prefix = m.group(0)        # 含序号字符 + Tab/全角空格
        rest = text[m.end():]
    else:
        prefix = ""
        rest = text
    body, suffix = _find_scripture_suffix(rest)
    return prefix, body.strip(), suffix
```

完整示例：

| 输入行 | prefix | body | suffix |
|--------|--------|------|--------|
| `一\t神圣的生命—约一1：` | `一\t` | `神圣的生命` | `—约一1：` |
| `壹\t神的经纶` | `壹\t` | `神的经纶` | `""` |
| `神圣的生命；基督的经历` | `""` | `神圣的生命；基督的经历` | `""` |
| `一\t—约一1：` | `一\t` | `""` | `—约一1：`（空 body） |
| `(一)\t召会—太十六18：` | `(一)\t` | `召会` | `—太十六18：` |

#### `_translate_prefix(prefix: str) -> str`

```python
def _translate_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    core = prefix.rstrip("\t　 ")    # 剥离分隔符，只留序号字符
    mapped = _PREFIX_TO_EN.get(core.strip())
    if mapped:
        sep = "\t" if "\t" in prefix else ("　" if "　" in prefix else " ")
        return mapped + sep          # 保留原始分隔符类型
    return prefix                    # 未识别则原样返回
```

**保留分隔符类型**：原来用 Tab 对齐，英文也用 Tab，保证纲目视觉格式不变。

#### `_split_body(body: str) -> list[str]`

```python
def _split_body(body: str) -> list[str]:
    body = (body or "").strip()
    if not body:
        return []
    if "；" in body:
        parts = [p.strip() for p in body.split("；")]
        return [p for p in parts if p]    # 过滤空字符串
    return [body]
```

| body | 子句列表 |
|------|----------|
| `神圣的生命；基督的经历；神圣的性情` | `["神圣的生命", "基督的经历", "神圣的性情"]` |
| `职事的路` | `["职事的路"]` |
| `""` | `[]` |
| `神圣的生命；` | `["神圣的生命"]`（末尾空子句被过滤） |

---

### 3.4 行类型判断：outline vs reference

#### `_detect_line_type(body: str, prefix: str = "") -> str`

```python
def _detect_line_type(body: str, prefix: str = "") -> str:
    if (prefix or "").strip():
        return "outline"
    s = (body or "").lstrip()    # 只去前导空白（lstrip，不是 strip）
    if not s:
        return "reference"
    if _OUTLINE_HEAD_RE.match(s):
        return "outline"
    return "reference"
```

**判断逻辑（两级）**：

| 条件 | 结果 |
|------|------|
| `prefix` 非空（如 `一\t`、`壹\t`） | `"outline"` |
| `body` 为空 | `"reference"` |
| `body` 开头匹配 `_OUTLINE_HEAD_RE` | `"outline"` |
| 其余 | `"reference"` |

**典型示例**：

| 原始行 | prefix | body | line_type |
|--------|--------|------|-----------|
| `一\t神圣的生命` | `一\t` | `神圣的生命` | `outline`（prefix 命中） |
| `壹\t神的经纶` | `壹\t` | `神的经纶` | `outline` |
| `神圣的生命是神自己的生命` | `""` | 同上 | `reference` |
| `一神圣的生命`（无 Tab） | `""` | `一神圣的生命` | `outline`（body 匹配 `_OUTLINE_HEAD_RE`） |

**`line_type` 的用途**：写入 `line_ref_group["line_type"]`，供前端区分样式（`outline` / `reference` 标签），**不影响翻译逻辑**。

**设计说明**：带 ministerialize prefix 的行（`一\t…`）在去掉 prefix 后 body 可能不以序号开头，因此优先用 `prefix` 非空判定为 `outline`，与手工验收「`一\t神圣的生命` → outline」一致。

---

### 3.5 解析阶段完整流程图

```
原始行 line
    │
    ├─ _MINISTERIALIZE_PREFIX_RE.match(line)
    │       命中 → prefix = m.group(0)，rest = line[m.end():]
    │       未命中 → prefix = ""，rest = line
    │
    └─ _find_scripture_suffix(rest)
            先试 _SCRIPTURE_REF_RE.finditer → 取 matches[-1]
            再试 _PURE_VERSE_RE.search
            都失败 → suffix = ""
            → body = rest[:m.start()].strip()，suffix = m.group(0)
                │
                ├─ _translate_prefix(prefix) → en_prefix
                │
                ├─ _split_body(body) → clauses[]
                │
                └─ _detect_line_type(body, prefix) → "outline" | "reference"
```

---

## 四、阶段二：两个 Pool 的短路逻辑

### 4.1 两个 Pool 的对比

| | Additional Pool | ES Pool（官方翻译池） |
|---|---|---|
| 存储位置 | 本地 `pool.jsonl` 文件 | Elasticsearch（`life`, `cwwn`, `cwwl` 等索引） |
| 数据来源 | 系统自动积累 + 手动导入 | 职事著作官方英译本段落库 |
| 匹配粒度 | **整行**（含 prefix+body+suffix） | **整行 body**（不含 prefix 和 suffix） |
| 匹配键 | `normalize_zh(整行)` 全等 | ≤10字 match_phrase + 全等；>10字 BM25 top1 + 全等 |
| 命中后 | 直接输出缓存英文，跳过一切后续 | 直接输出 pool 英文，跳过检索和 Gemini |

### 4.2 Additional Pool 详解

**数据结构**（`pool.jsonl` 每行一条 JSON）：
```json
{
  "zh": "一\t生命",
  "en": "A.\tLife",
  "norm_zh": "一生命",
  "saved_at": "2026-06-01T10:00:00Z",
  "source": "enhanced_translate"
}
```

**匹配逻辑**：内存字典 `_pool`，键为 `norm_zh`，O(1) 查询。`normalize_zh` 去掉空白和标点，使「一\t生命」和「一 生命」命中同一条。

**自动回写**：每次翻译后把新翻行按 `norm_zh` 去重写入 `pool.jsonl`，Pool 随使用自动增长。

**为什么含序号**：同一正文在不同序号位置（「一\t生命」vs「二\t生命」）对应不同英文前缀，不能共享缓存。

### 4.3 ES Pool 详解

**`_pool_lookup_keyword(clause: str) -> str | None`**（≤10字）：

```python
body = {
    "query": {"match_phrase": {"zh": {"query": clause}}},
    "size": 3,
    "_source": ["zh", "en", "text"],
}
# 对每个 hit：normalize_zh(clause) == normalize_zh(hit_zh) 才采纳 en
```

**`_pool_lookup_bm25_punct(clause: str) -> str | None`**（>10字）：

```python
body = {
    "query": {"match": {"zh": {"query": clause, "analyzer": "ik_smart"}}},
    "size": 1,
    "_source": ["zh", "en", "text"],
}
# 取 top1：normalize_zh(clause) == normalize_zh(hit_zh) 才采纳 en
```

**`_pool_lookup(clause: str) -> str | None`**：

```python
async def _pool_lookup(clause: str) -> str | None:
    clause = (clause or "").strip()
    if not clause:
        return None
    if len(clause) <= _POOL_KEYWORD_MAX_LEN:    # <= 10 字
        return await _pool_lookup_keyword(clause)
    return await _pool_lookup_bm25_punct(clause)
```

**全等校验的原理**：BM25/phrase 可能召回相近句，`normalize_zh` 去标点后全等是最后一道防线。「神圣的生命，」和「神圣的生命」视为相同；「神圣的生命与性情」和「神圣的生命」不同。

### 4.4 两个 Pool 在代码中的位置

```python
# ── 主流程最开头：Additional Pool ──
line_cached_en: dict[int, str] = {}
for i, line in enumerate(lines):
    cached = lookup_line_en(line)     # 整行含序号
    if cached:
        line_cached_en[i] = cached

# ── _retrieve_line 最开头：ES Pool ──
pool_en = await _pool_lookup(body)    # 整行 body，clauses 循环之前
if pool_en is not None:
    return {
        "needs_batch": False,
        "pool_line_en": pool_en,
        ...
    }
# 以下才是子句循环（exact / retrieve_top1）
```

**优先级**：Additional Pool > ES Pool > 子句检索 + Gemini

---

## 五、阶段三：子句检索（_retrieve_line）

只有两个 Pool 都未命中的行才进入这个阶段。

### 5.1 `_RetrievalCtx` 数据类

```python
@dataclass
class _RetrievalCtx:
    index: str              # ES 索引名（逗号拼接的 _INDICES_BASE）
    es_enabled: bool = True
    dense_enabled: bool = True
    warnings: list[str] = field(default_factory=list)
    _es_down_logged: bool = False   # 防止重复打日志
```

`create` 类方法：检查 `OPENROUTER_API_KEY`，没有则 `dense_enabled=False` 并加 warning。

`mark_es_down`：首次调用时关闭 `es_enabled`，加 warning，打一条 log（`_es_down_logged` 防止重复）。

**`_is_es_failure(exc)`**：判断异常是否是 ES 故障：

```python
def _is_es_failure(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "503" in msg
        or "search_phase_execution_exception" in msg
        or "unavailable" in msg
        or "connection" in msg
        or "timeout" in msg
    )
```

**`_probe_es(ctx)`**：请求开始时对第一个索引发一次 `match_all size=0` 探测，失败则 `ctx.mark_es_down`。

### 5.2 检索流程（每个子句）

```
子句
 ├─ _exact_match（match_phrase on kg-rag_*.text）
 │    命中条件：clause in chunk["text"]（子句字符串出现在 chunk 正文中）
 │    命中后：match_kind = "exact"，前端绿色标签「直接引用」
 │
 ├─ 未命中 → _retrieve_top1
 │    bm25_search（top 5）
 │    + dense_search（top 20，需 OpenRouter）
 │    → rrf_merge（k=60，bm25_weight=1.0，dense_weight=1.0）
 │    → rerank（top 3 → 取 top1，_RERANK_SEM 限并发）
 │    命中后：match_kind = "retrieved"，前端蓝色标签「参考翻译」
 │
 └─ 都未命中 → match_kind = "none"
```

### 5.3 `_build_ref_entry` — 统一 ref 结构

```python
def _build_ref_entry(line_index, clause_index, clause, hit) -> dict:
```

根据 `hit` 的 `match_kind` 构造统一结构：

| 字段 | 说明 |
|------|------|
| `line_index` | 行索引 |
| `clause_index` | 子句索引（同行多子句时用） |
| `zh` | 子句原文 |
| `match_kind` | `"exact"` / `"retrieved"` / `"none"` |
| `match_type` | `"direct"` / `"reference"` / `"none"` |
| `zh_snippet` | exact 时=子句本身；retrieved 时=chunk text 前200字 |
| `en_snippet` | chunk 的英文译文 |
| `text` | chunk 完整中文原文 |
| `en` | chunk 完整英文译文 |
| `chunk_id` | chunk 唯一标识 |
| `source` / `ch_source` | 中文来源（书名+消息号） |
| `en_source` | 英文来源 |

### 5.4 去重与编号

```python
deduped_refs = _dedupe_refs_by_chunk_id(line_refs)
# 同一 chunk 被多子句命中时，只保留第一次出现（按 chunk_id 去重）
# chunk_id 为空的 ref 不参与去重（每个都保留）

deduped_refs = _assign_paragraph_numbers(deduped_refs)
# 给去重后的 refs 编号 paragraph=1,2,3...
# 供 _format_ref_block_for_gemini 用「Paragraph N」引用
```

---

## 六、阶段四：翻译与组装

### 6.1 批量翻译（_translate_batch）

每批最多 10 行。送入 Gemini 的中文行**去掉读经后缀**（`_zh_line_for_batch`），后缀由 `_translate_suffix` 单独翻译后在组装阶段拼接。

**`contents` 拼装顺序**（自上而下）：

```
[blocks 区]     ← 每行一个 block，用 "\n\n" 连接
+
[extra]         ← "\n\n" + prompt_extra（ENHANCED_TRANSLATE_PROMPT_SUFFIX 或覆盖值）
+
"\n\n"
+
[OUTLINE_TRANSLATE_PROMPT_ZH2EN]
+
"\n\nTranslate each line above to English. Output ONLY in this exact format:\n"
+
[输出格式模板]   ← Line 1: {english translation}\nLine 2: ...
```

**单个 block 结构**（`_format_ref_block_for_gemini` 生成参考语料块）：

```
Line {pos}: {zh_line}

参考语料：
Paragraph 1 [直接引用]
id: chunk_abc
text: {chunk 中文}
en: {chunk 英文}

Paragraph 2 [参考翻译]
id: chunk_def
text: {chunk 中文}
en: {chunk 英文}
```

- `pos`：batch 内序号（1, 2, 3…），**不是**原始 `line_i`
- `zh_line`：去掉读经后缀的中文行（含序号 prefix + body）
- 无参考语料时 `ref_block` 为空串

**完整示例**（3 行 batch，第 1 行有 2 段语料）：

```
Line 1: 一	神圣的生命；基督的经历

参考语料：
Paragraph 1 [直接引用]
id: chunk_abc
text: 神圣的生命是神自己的生命
en: The divine life is God's own life

Paragraph 2 [参考翻译]
id: chunk_def
text: 基督的经历就是基督所经过的一切
en: The experience of Christ is all that Christ has passed through

Line 2: 二	职事的路

Line 3: 三	召会的建造

{ENHANCED_TRANSLATE_PROMPT_SUFFIX 全文}

{OUTLINE_TRANSLATE_PROMPT_ZH2EN}

Translate each line above to English. Output ONLY in this exact format:
Line 1: {english translation}
Line 2: {english translation}
Line 3: {english translation}
```

**`_parse_batch_translations`**：用 `_BATCH_LINE_OUT_RE` 解析输出，按 `Line N:` 对齐；缺失行 fallback 为原始中文行（不让整批崩掉）。

**Fallback 机制**：主模型失败则试 `GEMINI_TRANSLATION_FALLBACK_MODEL`；fallback 也失败则每行退化为原文 `zh_line` 占位。

**Token 均摊**：`usage["in_tok"] // max(len(items), 1)` 均摊到每行，用于 `stats.gemini_in_tok` / `gemini_out_tok`。

### 6.2 组装（_assemble_line）

```python
# 优先级 1：Additional Pool 命中
if cached_en:
    return cached_en, _build_line_ref_group(..., additional_pool_line=True, retrieval_skipped=True)

# 优先级 2：ES Pool 命中
pool_line_en = (prep.get("pool_line_en") or "").strip()
if pool_line_en:
    en_suffix = await _translate_suffix(suffix, prompt_extra) if suffix else ""
    translated = en_prefix + pool_line_en + en_suffix
    return translated, _build_line_ref_group(..., pool_line=True)

# 优先级 3：空 body（仅序号+读经）
if not prep["needs_batch"]:
    en_suffix = await _translate_suffix(suffix, prompt_extra) if suffix else ""
    return en_prefix + en_suffix, _build_line_ref_group(...)

# 优先级 4：Gemini batch 结果
zh_for_batch = _zh_line_for_batch(line, suffix)   # 去掉后缀的中文行
body_en = translate_by_line.get(line_i) or zh_for_batch
en_suffix = await _translate_suffix(suffix, prompt_extra) if suffix else ""
return body_en + en_suffix, _build_line_ref_group(..., gemini_translate=body_en)
```

**组装说明**：
- Additional Pool 命中：直接返回缓存整行英文（已含 prefix，不再拼接）
- ES Pool 命中：`en_prefix + pool_line_en + en_suffix`
- 空 body：`en_prefix + en_suffix`
- Batch 命中：`body_en + en_suffix`（batch 输入已含 prefix+body，不含 suffix）

### 6.3 并行策略

```python
# 检索阶段：所有行并行
preps = await asyncio.gather(*[_prep_one(i, line) for i, line in enumerate(lines)])

# 翻译阶段：多个 batch chunk 并行（Semaphore(10) 限流）
batch_sem = asyncio.Semaphore(10)
batch_outcomes = await asyncio.gather(*[_run_batch_chunk(chunk) for chunk in chunks])

# 组装阶段：所有行并行
results = await asyncio.gather(*[_assemble_line(...) for prep in preps])
```

### 6.4 Gemini API 调用（_call_gemini_sync）

所有 Gemini 请求统一经 `_call_gemini_sync` 发起，由 `_translate_batch`（批量纲目）和 `_translate_suffix`（读经后缀）通过 `asyncio.to_thread` 调用。

**调用点**：

| 函数 | 用途 | fallback 模型 |
|------|------|---------------|
| `_translate_batch` | 批量翻译纲目行 | 有（主模型空响应时） |
| `_translate_suffix` | 单独翻译读经后缀 | 无（失败则返回原 suffix） |

**`generate_content` 参数**：

```python
response = gemini_client.models.generate_content(
    model=use_model,           # GEMINI_MODEL 或 GEMINI_TRANSLATION_FALLBACK_MODEL
    contents=contents,         # user 消息（拼装字符串）
    config=_gemini_config(),   # system_instruction + max_output_tokens 等
)
```

**`_gemini_config()`**：调用主工程 `gemini_translation_generate_config(GEMINI_TRANSLATION_SYSTEM_INSTRUCTION)`，设置：
- `system_instruction`：职事术语表（`GEMINI_TRANSLATION_SYSTEM_INSTRUCTION`）
- `automatic_function_calling`：`disable=True`
- `max_output_tokens`：来自环境变量 `GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS`（默认 32768，范围 1024–65536）
- **未设置** `temperature`、`thinking_config`

**模型来源**：从 `ai_search.ai_service` 导入 `GEMINI_MODEL` / `GEMINI_TRANSLATION_FALLBACK_MODEL`。可在 `enhanced_translate_service.py` import 后覆盖为本模块专用值，不影响主站其他翻译功能。

**重试逻辑**：
- `_gemini_error_is_retryable(err)` 为真时，sleep 2 秒后重试 **1 次**（`retry_count` 0→1）
- 无显式 API timeout 参数

**并发控制**：
- `GEMINI_SEMAPHORE`（主工程全局，默认 10）：所有 `generate_content` 共享
- `batch_sem = asyncio.Semaphore(10)`：限制并行 batch chunk 数
- `_RERANK_SEM = asyncio.Semaphore(10)`：限制 rerank 并发（检索阶段，非 Gemini）

**`_translate_suffix` 的 contents 拼装**（与 batch 顺序不同）：

```
任务说明（只翻译读经后缀）
+
"\n\n"
+
{suffix 原文}
+
"\n\n"
+
OUTLINE_TRANSLATE_PROMPT_ZH2EN
+
extra（"\n\n" + prompt_extra）
```

---

## 七、数据结构全景

### 7.1 prep 字典

```python
{
    "line_i": int,
    "line": str,            # 原始行
    "body": str,            # 去掉 prefix 和 suffix 的正文
    "suffix": str,          # 读经后缀（可能为空串）
    "en_prefix": str,       # 已翻序号（如 "A.\t"，可能为空串）
    "line_type": str,       # "outline" | "reference"
    "line_refs": [...],     # 子句级 ref 列表（池命中行为 []）
    "deduped_refs": [...],  # 去重+编号后的 refs（进 Gemini prompt）
    "needs_batch": bool,    # True → 需要进 _translate_batch
    "line_cached_en": str,  # Additional Pool 命中的英文（非空则短路）
    "pool_line_en": str,    # ES Pool 命中的英文（非空则跳过检索和 Gemini）
}
```

### 7.2 line_ref_group（API 响应单行）

```python
{
    "line_index": int,
    "original_line": str,
    "line_type": "outline" | "reference",   # _detect_line_type 的结果
    "gemini_translate": str,                # 最终英文译文
    "deduped_refs": [...],
    "line_refs": [...],
    "stats": {
        "pool": int,                 # 子句级 pool 命中数
        "exact": int,
        "retrieved": int,
        "none": int,
        "gemini_in_tok": int,
        "gemini_out_tok": int,
        "additional_pool_line": bool,
        "retrieval_skipped": bool,
        "pool_line": bool,           # 整行命中 ES Pool
    }
}
```

### 7.3 summary

```python
{
    "total_lines": int,
    "pool": int,
    "exact": int,
    "retrieved": int,
    "none": int,
    "additional_pool_lines": int,
    "pool_full_match_lines": int,       # 整行命中 ES Pool 的行数
    "additional_pool_appended": int,
    "additional_pool_append_skipped": int,
    "gemini_cost_usd": float,           # (in*1.25 + out*10) / 1_000_000
    "total_cost_usd": float,
}
```

---

## 八、Prompt 设计

### 8.1 四层 Prompt 结构

| 层 | 内容 | 来源 |
|----|------|------|
| System Instruction | 职事术语表（数百条中英对照） | `GEMINI_TRANSLATION_SYSTEM_INSTRUCTION` |
| 任务说明 | 纲目翻译通用规则 | `OUTLINE_TRANSLATE_PROMPT_ZH2EN` |
| 增强规则 | 直接引用/参考翻译使用说明（含正反例） | `testD/backend/enhanced_translate_prompts.py` → `ENHANCED_TRANSLATE_PROMPT_SUFFIX` |
| 可覆盖层 | 用户自定义规则 | `_PROMPT_OVERRIDE` 或请求体 `prompt_override` |

### 8.2 Prompt 覆盖优先级

```python
if prompt_override is not None:
    prompt_extra = prompt_override.strip()    # 请求级（单次有效）
else:
    prompt_extra = (_PROMPT_OVERRIDE or ENHANCED_TRANSLATE_PROMPT_SUFFIX).strip()
    # _PROMPT_OVERRIDE 非空 → 服务级（POST /update_prompt，进程内持久）
    # _PROMPT_OVERRIDE 为空 → 默认规则
```

---

## 九、完整主流程伪代码

```python
async def enhanced_translate(content, prompt_override=None):
    # 输入验证
    if not outline: return error
    if len > MAX_CONTENT_CHARS: return error
    if not gemini_client: return error

    # Prompt 选择
    prompt_extra = prompt_override or _PROMPT_OVERRIDE or ENHANCED_TRANSLATE_PROMPT_SUFFIX

    lines = [ln for ln in content.splitlines() if ln.strip()]

    # ── 阶段二A：Additional Pool（整行含序号）──
    line_cached_en: dict[int, str] = {}
    for i, line in enumerate(lines):
        en = lookup_line_en(line)
        if en:
            line_cached_en[i] = en

    # ── ES 探测 ──
    ctx = _RetrievalCtx.create(_INDICES_BASE)
    if any(i not in line_cached_en for i in range(len(lines))):
        await _probe_es(ctx)

    # ── 阶段二B + 阶段三：并行检索 ──
    async def _prep_one(i, line):
        if i in line_cached_en:
            return _prep_cached_line(i, line, line_cached_en[i])
        prep = await _retrieve_line(i, line, ctx)
        # _retrieve_line 内部：
        #   1. _pool_lookup(body) → 命中则 pool_line_en=..., needs_batch=False
        #   2. 未命中 → for clause in clauses: exact → retrieve_top1 → enrich
        prep["line_cached_en"] = ""
        return prep

    preps = await gather(_prep_one for all lines)

    # ── 阶段四A：收集 batch ──
    batch_items = [
        (prep["line_i"], _zh_line_for_batch(prep["line"], prep["suffix"]), prep["deduped_refs"], prompt_extra)
        for prep in preps
        if prep["needs_batch"] and not prep.get("line_cached_en")
        # Additional Pool 命中 → line_cached_en 非空 → 跳过
        # ES Pool 命中 → needs_batch=False → 跳过
    ]

    # ── 阶段四B：批量翻译（每批 ≤10 行，并行多批）──
    chunks = [batch_items[i:i+10] for i in range(0, len(batch_items), 10)]
    batch_outcomes = await gather(_translate_batch for each chunk)
    translate_by_line, usage_by_line = 整理结果

    # ── 阶段四C：组装 ──
    results = await gather(
        _assemble_line(prep, prompt_extra, translate_by_line, usage_by_line)
        for prep in preps
    )
    # 优先级：cached_en > pool_line_en > gemini_result
    # Additional Pool：整行缓存；ES Pool：en_prefix + pool_body + en_suffix
    # Batch：body_en + en_suffix（body_en 已含 prefix+body 的英文）

    # ── 自动回写 Additional Pool ──
    if auto_append_enabled():
        rows = collect_auto_append_rows(line_ref_groups, out_lines)
        added, skipped = append_records(rows)

    return { result, refs, summary, error: None, warnings }
```

---

## 十、Elasticsearch 索引设计

### 10.1 两套索引族对比

| | kg-rag_* 索引族 | Pool 索引族 |
|---|---|---|
| 索引名 | `kg-rag_cwwl`, `kg-rag_life`, `kg-rag_cwwn`, `kg-rag_others`, `kg-rag_7feasts`, `kg-rag_bib` | `life`, `cwwn`, `cwwl`, `others`, `bib`, `foo`, `hymn`, `feasts` |
| 用途 | chunk 级检索（exact/BM25/dense） | 整行 body 官方译文查询 |
| 主要字段 | `text`, `en`, `embedding` | `zh`, `en` |
| 查询字段 | `text` | `zh` |
| 有无向量 | 有（1024维，bge-m3） | 无 |
| `zh.keyword` | 无 | 无（不能用 term 查询） |

**常见错误**：
- 用 `zh.keyword` 做 term 查询（字段不存在）
- 把 `life` 当 chunk 索引（无 `text` / `embedding` 字段）
- 把 `kg-rag_life` 当 pool 索引（无 `zh` 字段）

---

## 十一、从零实现步骤

### 阶段 A：骨架
1. `_bootstrap.py`：把主工程 backend 加入 sys.path
2. `enhanced_translate_router.py`：两个 POST 端点（`/enhanced_translate`、`/enhanced_translate/update_prompt`）
3. 空壳 `enhanced_translate`，直接返回原文
4. 接入主工程 `main.py`

### 阶段 B：行解析
5. 定义所有正则变量（`_MINISTERIALIZE_PREFIX_RE`、`_BIBLE_BOOKS_66`、`_BIBLE_BOOKS`、`_BOOK_PAT`、`_CHAP_PAT`、`_REF_UNIT`、`_SCRIPTURE_REF_RE`、`_PURE_VERSE_RE`）
6. `_PREFIX_TO_EN` 规则表（17 个条目，含繁简体兼容）
7. `_find_scripture_suffix`、`_strip_scripture_suffix`
8. `_split_body`
9. `_translate_prefix`（保留原始分隔符类型）
10. `_OUTLINE_HEAD_RE` 和 `_detect_line_type`

### 阶段 C：ES 检索
11. `_RetrievalCtx` dataclass（`index`, `es_enabled`, `dense_enabled`, `warnings`, `_es_down_logged`）
12. `_is_es_failure`、`_probe_es`、`mark_es_down`
13. `_exact_match`（match_phrase on `text`，验证 `clause in hit["text"]`）
14. `_retrieve_top1`（bm25 + dense + rrf_merge + rerank，`_RERANK_SEM` 限流）
15. `_enrich_hit_en`（补全 en 字段）
16. `_build_ref_entry`（统一 ref 结构，处理 pool/exact/retrieved/none 四种 match_kind）
17. `_dedupe_refs_by_chunk_id`、`_assign_paragraph_numbers`
18. `_format_ref_block_for_gemini`

### 阶段 D：ES Pool
19. `_POOL_INDICES`、`_POOL_KEYWORD_MAX_LEN = 10`、`_normalize_pool_text`
20. `_pool_lookup_keyword`（match_phrase + 全等校验）
21. `_pool_lookup_bm25_punct`（BM25 + 全等校验）
22. `_pool_lookup`（分流 ≤10 / >10 字）
23. 在 `_retrieve_line` 里，`clauses` 非空后立即调 `_pool_lookup(body)`，命中则提前返回

### 阶段 E：Gemini 翻译
24. `_call_gemini_sync`（同步，在 `asyncio.to_thread` 里跑，含一次重试）
25. `_translate_batch`（合并 prompt，`_parse_batch_translations`，fallback 原文占位）
26. `_translate_suffix`（读经标注单独小 prompt）
27. `_assemble_line`（四级优先级判断）

### 阶段 F：Additional Pool
28. `additional_pool.py`：`normalize_zh`, `lookup_line_en`, `append_records`, `collect_auto_append_rows`
29. 主流程开头循环 `lookup_line_en` → `line_cached_en`
30. `_prep_cached_line`（短路路径，`pool_line_en: ""`）

### 阶段 G：统计
31. `_stats_from_line_refs`（统计各 match_kind 数量）
32. `_gemini_cost_usd`（公式：`(in*1.25 + out*10) / 1_000_000`）
33. `_build_line_ref_group`（含 `pool_line` 参数）
34. `_build_summary`（含 `pool_full_match_lines`）

### 阶段 H：验证
35. `test_translate.py`：mock `_retrieve_line` 和 `_translate_batch`，断言 Additional Pool 命中行不进这两个函数

---

## 十二、关键设计决策总结

| 决策 | 原因 |
|------|------|
| Additional Pool 含序号整行匹配 | 不同序号对应不同英文前缀，不能共享缓存 |
| ES Pool 匹配整行 body（不含序号/后缀） | 段落库数据是正文本身；序号和后缀单独处理 |
| Pool 都是整行匹配，不看子句 | 官方译文要么整句用，要么不用，不做部分替换 |
| ES Pool 查询在子句循环之前 | 整行能命中就不需要分解子句，节省时间 |
| 检索与翻译严格分两阶段 | 翻译需等所有检索完成才能合理分 batch |
| Gemini 最多 10 行一 batch | 太多行 LLM 容易丢失；太少则 API 调用次数多 |
| ES 503 时降级而不报错 | 可用性优先，无参考仍可翻译 |
| Pool 查询做全等校验 | BM25/phrase 可能召回相近句，全等是最后一道防线 |
| `_detect_line_type` 优先看 prefix | 带 ministerialize prefix 的行（`一\t…`）直接判 outline；无 prefix 时再匹配 body |
| token 按行均摊 | 一次 batch 无法精确归因每行，均摊是合理近似 |

---

## 十三、测试验证

### 13.1 test_translate.py

文件：`testD/backend/test_translate.py`

```bash
# 仓库根目录
python testD/backend/test_translate.py
# 或
python -m pytest testD/backend/test_translate.py -v
```

**测试项**：
- `test_parse_line`：行解析、prefix 翻译、`line_type` 判断
- `test_split_body`：分号拆句
- `test_normalize_zh`：Additional Pool 归一化
- `test_pool_skip_gemini`：Additional Pool 短路验证

**Pool 短路断言**（mock `_retrieve_line` / `_translate_batch`）：

```python
# 前置条件：Additional Pool 里有「一\t生命」和「二\t职事」
# 输入：「一\t生命\n二\t职事\n三\t建造」

assert retrieve_line_ids == [2]         # 只有 line_i=2 进检索
assert probe_mock.await_count == 1       # ES 只探测一次
assert batch_line_ids == [[2]]           # 只有 line_i=2 进 batch
assert r["summary"]["additional_pool_lines"] == 2
assert refs[0]["stats"]["retrieval_skipped"] is True
assert refs[1]["stats"]["retrieval_skipped"] is True
assert out[0] == "A.\tLife"
assert out[1] == "B.\tMinistry"
assert out[2].startswith("GEMINI_")
```

### 13.2 手工验证要点

| 场景 | 验证点 |
|------|--------|
| 含 `；` 的行 | `line_refs` 有多个子句条目 |
| `line_type` 判断 | 「一\t神圣的生命」→ outline；「神乃是灵」→ reference |
| ES Pool 命中 | `stats.pool_line=True`，`pool_full_match_lines` 增加 |
| Additional Pool 命中 | `stats.additional_pool_line=True`，`retrieval_skipped=True` |
| ES 关闭 | `warnings` 含降级，仍返回 Gemini 译文 |
| 重复翻译同一纲目 | 第二次 `additional_pool_lines` 上升，耗时下降 |
| 统计摘要 | 前端展示 `summary`（命中率、Gemini 费用、Pool 写入数） |
| 行类型标签 | 参考语料区显示 `outline` / `reference`；Pool 命中显示绿色/蓝色标签 |

---

*文档版本：2026-06-05，对应 enhanced_translate_service.py 约 988 行版本。*

---

## 十四、testD/ 其他文件详解

### 14.1 `_bootstrap.py` — 主工程路径挂载

```python
# -*- coding: utf-8 -*-
"""将 back_mic/backend 加入 sys.path，供 testD 复用主工程模块。"""
from __future__ import annotations
import sys
from pathlib import Path

_MAIN_BACKEND: Path | None = None

def ensure_main_backend_path() -> Path:
    global _MAIN_BACKEND
    if _MAIN_BACKEND is None:
        root = Path(__file__).resolve().parents[2]
        backend = root / "back_mic" / "backend"
        if not backend.is_dir():
            raise RuntimeError(f"主后端目录不存在: {backend}")
        _MAIN_BACKEND = backend
        s = str(backend)
        if s not in sys.path:
            sys.path.insert(0, s)
    return _MAIN_BACKEND
```

**作用**：`testD/` 是独立子目录，不能直接 `import` 主工程的模块。`ensure_main_backend_path()` 把 `back_mic/backend` 加入 `sys.path`，之后就能直接 `from kg_rag.retrieval import ...`、`from es_config import es` 等。

**路径计算**：

```
__file__ = 仓库根/testD/backend/_bootstrap.py
parents[0] = 仓库根/testD/backend/
parents[1] = 仓库根/testD/
parents[2] = 仓库根/               ← root
root / "back_mic" / "backend"      ← 主工程 backend
```

**变量**：

| 变量 | 类型 | 含义 |
|------|------|------|
| `_MAIN_BACKEND` | `Path \| None` | 模块级单例，首次调用后缓存，避免重复计算和重复插入 sys.path |

**调用时机**：`enhanced_translate_service.py` 文件顶部调用两次：

```python
from testD.backend._bootstrap import ensure_main_backend_path
ensure_main_backend_path()       # 第一次：确保路径存在后再 import 主工程模块
load_dotenv(ensure_main_backend_path() / ".env")  # 第二次：加载主工程的 .env
```

第二次调用因为有 `_MAIN_BACKEND` 缓存，直接返回，不重复操作。

---

### 14.2 `additional_pool.py` — Additional Pool 完整实现

#### 14.2.1 模块级变量

```python
_POOL_DIR  = Path(__file__).resolve().parent / "Additional-pool"
_POOL_FILE = _POOL_DIR / "pool.jsonl"
```

Pool 文件位于 `testD/backend/Additional-pool/pool.jsonl`，目录由代码自动创建（`_POOL_DIR.mkdir(parents=True, exist_ok=True)`）。

```python
_PUNCT_RE = re.compile(
    r"[\s\u3000\.,，。、；;：:!?！？\"'""''（）()\\[\\]【】《》〈〉—…·-]+"
)
```

`normalize_zh` 用的正则，匹配所有需要去除的字符：

| 字符/类 | 含义 |
|---------|------|
| `\s` | 所有 ASCII 空白（空格、Tab、换行） |
| `\u3000` | 全角空格 |
| `\.,，。、` | 中英文句号、逗号、顿号 |
| `；;：:` | 中英文分号、冒号 |
| `!?！？` | 中英文感叹号、问号 |
| `\"'""''` | 中英文双引号、单引号 |
| `（）()\[\]【】《》〈〉` | 各种括号 |
| `—\-…·` | 破折号、连字符、省略号、间隔号 |
| `+` | 一个或多个连续匹配，一次性替换为空串 |

```python
_cache_by_norm: dict[str, dict[str, Any]] = {}
_cache_mtime: float = 0.0
```

内存缓存：`_cache_by_norm` 是 `norm_zh → 完整记录` 的字典；`_cache_mtime` 是上次加载时的文件修改时间戳，用于按需重载。

---

#### 14.2.2 `normalize_zh(zh: str) -> str`

```python
def normalize_zh(zh: str) -> str:
    return _PUNCT_RE.sub("", (zh or "").strip())
```

输入先 `strip()` 再用 `_PUNCT_RE` 去掉所有标点空白，返回纯汉字+字母+数字的字符串。

**作用范围**：被 `additional_pool.py` 和 `enhanced_translate_service.py`（通过 `from testD.backend.additional_pool import normalize_zh`）共同使用，统一了 Additional Pool 和 ES Pool 的全等校验逻辑。

**示例**：

| 输入 | 输出 |
|------|------|
| `一\t生命` | `一生命` |
| `神圣的生命，` | `神圣的生命` |
| `神圣的生命；基督的经历` | `神圣的生命基督的经历` |
| `  （一）召会  ` | `一召会` |

---

#### 14.2.3 `_load_pool_file() -> dict[str, dict]`

```python
def _load_pool_file() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    path = _POOL_FILE
    if not path.is_file():
        return out
    with path.open(encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("[additional_pool] pool.jsonl L%s 无效 JSON: %s", line_no, e)
                continue
            zh = (rec.get("zh") or "").strip()
            en = (rec.get("en") or "").strip()
            if not zh or not en:
                continue
            norm = (rec.get("norm_zh") or "").strip() or normalize_zh(zh)
            if not norm:
                continue
            out[norm] = {**rec, "zh": zh, "en": en, "norm_zh": norm}
    return out
```

**细节**：

- `encoding="utf-8-sig"`：处理 Windows 下可能带 BOM 的文件
- `json.loads` 失败只警告不中断，跳过损坏行
- `norm_zh` 字段优先使用记录里已有的（避免重复计算），没有才调 `normalize_zh(zh)`
- 后读的行覆盖前读的同 `norm` 行（`out[norm] = ...`），即文件里靠后的记录优先

---

#### 14.2.4 `reload_pool(force: bool = False) -> int`

```python
def reload_pool(force: bool = False) -> int:
    global _cache_by_norm, _cache_mtime
    path = _POOL_FILE
    if not path.is_file():
        _cache_by_norm = {}
        _cache_mtime = 0.0
        return 0
    mtime = path.stat().st_mtime
    if not force and mtime == _cache_mtime and _cache_by_norm:
        return len(_cache_by_norm)    # 文件未变，直接返回
    _cache_by_norm = _load_pool_file()
    _cache_mtime = mtime
    logger.info("[additional_pool] 已加载 %s 条", len(_cache_by_norm))
    return len(_cache_by_norm)
```

**三个条件都满足才跳过重载**：`not force`（非强制）AND `mtime == _cache_mtime`（文件未改）AND `_cache_by_norm`（缓存非空）。任一不满足则重新读文件。

`force=True` 用于：写入完成后强制刷新缓存（`append_records` 里调用）、测试里手动触发（`test_translate.py`）。

#### 14.2.8 `auto_append_enabled() -> bool`

```python
def auto_append_enabled() -> bool:
    raw = (os.environ.get("ENHANCED_TRANSLATE_AUTO_APPEND") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")
```

默认开启自动回写。设 `ENHANCED_TRANSLATE_AUTO_APPEND=0` 可关闭。

---

#### 14.2.5 `lookup_line_en(zh_line: str) -> str | None`

```python
def lookup_line_en(zh_line: str) -> str | None:
    zh_line = (zh_line or "").strip()
    if not zh_line:
        return None
    reload_pool()               # 按 mtime 懒加载
    rec = _cache_by_norm.get(normalize_zh(zh_line))
    if not rec:
        return None
    en = (rec.get("en") or "").strip()
    return en or None
```

**每次调用都触发 `reload_pool()`**，但因为有 mtime 缓存，文件未变时是 O(1) 的。

---

#### 14.2.6 `append_records(records, *, force=False) -> tuple[int, int]`

```python
def append_records(records, *, force=False) -> tuple[int, int]:
    if not records:
        return 0, 0
    reload_pool(force=True)         # 先强制刷新，拿到最新状态
    existing = dict(_cache_by_norm) # 复制一份，避免直接改缓存
    added = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()
    for rec in records:
        zh = (rec.get("zh") or "").strip()
        en = (rec.get("en") or "").strip()
        if not zh or not en:
            continue
        norm = (rec.get("norm_zh") or "").strip() or normalize_zh(zh)
        if norm in existing and not force:
            skipped += 1
            continue
        existing[norm] = {
            "zh": zh, "en": en, "norm_zh": norm,
            "saved_at": rec.get("saved_at") or now,
            "prompt_version": rec.get("prompt_version") or "",
            "source": rec.get("source") or "enhanced_translate",
        }
        added += 1

    if added == 0:
        return 0, skipped

    # 原子写入：先写 .tmp，再 rename 替换
    _POOL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _POOL_FILE.with_suffix(".jsonl.tmp")
    if _POOL_FILE.is_file():
        shutil.copy2(_POOL_FILE, _POOL_FILE.with_suffix(".jsonl.bak"))  # 备份
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in existing.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(_POOL_FILE)         # 原子替换，避免写到一半崩溃导致文件损坏
    reload_pool(force=True)         # 刷新内存缓存
    return added, skipped
```

**写入流程**：

```
1. 强制重载最新 pool → existing dict
2. 逐条检查：norm 已存在且非 force → skipped++；否则 existing[norm] = 新记录
3. added == 0 → 提前返回，不写文件
4. 写 .tmp 文件（完整覆盖写）
5. 备份原文件为 .bak
6. .tmp rename 为 .jsonl（原子操作）
7. 强制重载缓存
```

**原子写入的意义**：直接覆盖写 `.jsonl` 若中途崩溃会产生损坏文件；先写 `.tmp` 再 `rename` 是操作系统级原子操作，保证文件要么是旧的完整版，要么是新的完整版。

---

#### 14.2.7 `collect_auto_append_rows(line_ref_groups, out_lines) -> list[dict]`

```python
def collect_auto_append_rows(line_ref_groups, out_lines) -> list[dict]:
    rows = []
    for i, group in enumerate(line_ref_groups):
        st = group.get("stats") or {}
        if st.get("additional_pool_line"):
            continue            # 本来就是从 Additional Pool 命中的，不重复写入
        if not (group.get("gemini_translate") or "").strip():
            continue            # 没有译文（空行、仅序号行等）跳过
        zh = (group.get("original_line") or "").strip()
        en = (out_lines[i] if i < len(out_lines) else "").strip()
        if not zh or not en:
            continue
        if zh == en:
            continue            # 译文与原文相同（fallback 到原文的情况）跳过
        rows.append({
            "zh": zh,
            "en": en,
            "norm_zh": normalize_zh(zh),
            "source": "enhanced_translate",
        })
    return rows
```

**过滤逻辑**：

| 条件 | 原因 |
|------|------|
| `additional_pool_line == True` | 已在 Pool 里，不重复写 |
| `gemini_translate` 为空 | 没有实质译文（仅序号+读经的行） |
| `zh == en` | Gemini 失败时 fallback 返回原文，不能入库 |
| `zh` 或 `en` 为空 | 无效记录 |

**注意**：ES Pool 命中行（`pool_line=True`）不在过滤条件里，因为 `gemini_translate` 字段填的是 `pool_line_en`（非空），且 `zh != en`，所以 **ES Pool 命中行会被写入 Additional Pool**。这是有意设计——下次同一行再来，Additional Pool 直接命中，连 ES Pool 查询都省了。

---

### 14.3 `enhanced_translate_prompts.py` — Prompt 常量

#### 14.3.1 `ENHANCED_TRANSLATE_PROMPT_SUFFIX`

完整内容见 `testD/backend/enhanced_translate_prompts.py`（约 96 行）。结构为 **11 条规则 + 多组正反例**，分四段：

**开场角色设定**：专业基督教事奉文字翻译员，熟悉恢复版圣经术语与李常受/倪柝声著作风格。

**【语料结构说明】**：解释 `参考语料` 区块中 `text` / `en` / `[直接引用]` / `[参考翻译]` 各字段含义。

**【语料使用规则】**（1–4条）：

| 条 | 规则 |
|----|------|
| 1 | `[直接引用]`：`en` 字段**一字不改**照搬；附 2 组错误示范（改词、改介词） |
| 2 | `[参考翻译]`：`en` 视为已审定译文，**最大限度原样复用**；仅缺口部分补译；附错误示范（漏译语料已有句子） |
| 3 | 语料覆盖范围：语料已覆盖的内容不得删减或重译；无对应才补译 |
| 4 | 多语料段落按原文片段顺序拼接；语料多余句子忽略 |

**【序号格式规则】**（5–6条）：

| 条 | 规则 |
|----|------|
| 5 | 序号转换表（含 `六→F.`、括号序号 `(一)→1)` 等），附 3 个完整示例 |
| 6 | 序号必须原样保留在译文最前，不可省略或移位 |

完整序号对照：

```
壹→I.  贰→II.  叁→III.  肆→IV.  伍→V.  陆→VI.  柒→VII.  捌→VIII.
一→A.  二→B.   三→C.    四→D.   五→E.  六→F.
1→1.   2→2.    3→3.
a→a.   b→b.    c→c.
(一)→1)  (二)→2)  (三)→3)
```

**【术语与输出规则】**（7–11条）：

| 条 | 规则 |
|----|------|
| 7 | 严格使用 System instructions 专用术语表 |
| 8 | 纲目标题末尾读经标注保持缩写（附 `—约三16：`、`—林前十五45：` 示例） |
| 9 | 正文经文引用转标准英文缩写（附 `Rom. 1:1`、`John 3:16` 示例） |
| 10 | 直接输出译文，不缩进 |
| 11 | 只输出翻译结果，不附加解释或备注 |

**这个 prompt 在哪里被使用**：

```python
# enhanced_translate_service.py 主流程
from testD.backend.enhanced_translate_prompts import ENHANCED_TRANSLATE_PROMPT_SUFFIX
prompt_extra = (_PROMPT_OVERRIDE or ENHANCED_TRANSLATE_PROMPT_SUFFIX).strip()

# 拼入 _translate_batch（extra 在 OUTLINE_TRANSLATE_PROMPT_ZH2EN 之前）
contents = (
    "\n\n".join(blocks)
    + extra                           # extra = f"\n\n{prompt_extra}"
    + "\n\n"
    + OUTLINE_TRANSLATE_PROMPT_ZH2EN
    + "\n\nTranslate each line above..."
)

# 拼入 _translate_suffix（extra 在 OUTLINE_TRANSLATE_PROMPT_ZH2EN 之后）
contents = (
    "Translate ONLY this Chinese scripture suffix..."
    + f"\n\n{suffix}"
    + f"\n\n{OUTLINE_TRANSLATE_PROMPT_ZH2EN}{extra}"
)
```

#### 14.3.2 `PROOFREAD_OUTLINE_PROMPT`

```python
PROOFREAD_OUTLINE_PROMPT = (
    "Proofread ONLY the following English outline line translation.\n"
    "Fix numbering formats: 壹→I., 一→A., 1→1., a→a., (一)→1) etc.\n"
    "Ensure terminology matches the system instruction glossary.\n"
    "Fix scripture reference abbreviations (e.g. —约三16： → —John 3:16:).\n"
    "Output ONLY the corrected English text, with no explanation or notes.\n\n"
)
```

用于校对步骤（Proofread）的 prompt，检查序号格式、术语和读经标注。当前主流程**已移除**校对步骤（`_proofread_batch` 已删除），此常量保留备用。

---

### 14.4 `Additional-pool/tools/` 工具脚本

#### 14.4.1 `lookup.py` — 命令行查询

```bash
python lookup.py "一\t生命"
```

输出：`norm_zh` 和命中的 `en`，或「未命中」。用于调试 Pool 是否有某条记录。

**核心逻辑**：`reload_pool(force=True)` → `lookup_line_en(zh)` → 打印结果。

#### 14.4.2 `stats.py` — 条数统计

```bash
python stats.py
```

输出 Pool 文件路径和当前条数。用于快速了解 Pool 规模。

#### 14.4.3 `validate.py` — 校验文件完整性

```bash
python validate.py
```

逐行检查 `pool.jsonl`：

| 检查项 | 错误提示 |
|--------|----------|
| JSON 格式 | `L{n}: JSON 错误` |
| `zh` 或 `en` 为空 | `L{n}: 缺少 zh 或 en` |
| `norm_zh` 与 `normalize(zh)` 不一致 | `L{n}: norm_zh 与 normalize(zh) 不一致` |
| `norm_zh` 重复 | `L{n}: 重复 norm_zh=...` |

全部通过输出「通过：N 条」，有问题输出「失败：N 个问题」并返回退出码 1。

#### 14.4.4 `export_draft.py` — 导出 draft.jsonl

```bash
# 方式 1（推荐）：从 API 响应 JSON 导出
python export_draft.py --response response.json -o draft.jsonl

# 方式 2：中英文两个文本文件对齐导出
python export_draft.py --zh outline_zh.txt --en outline_en.txt -o draft.jsonl
```

**方式 1 的过滤逻辑**（`from_response`）：

- 跳过 `stats.additional_pool_line == True` 的行（已在 Pool 里）
- 跳过 `en` 为空的行
- 行数不一致时打 warning，按 `refs` 顺序对齐

**方式 2 的验证**（`from_zh_en`）：中英文行数必须严格一致，否则抛出 `ValueError`。

输出的每条记录包含：`zh`、`en`、`norm_zh`、`saved_at`、`source="enhanced_translate"`。

#### 14.4.5 `append.py` — 合并 draft 进 pool

```bash
python append.py draft.jsonl
python append.py draft.jsonl --force   # 同 norm_zh 时强制覆盖
```

**流程**：

1. 读取现有 `pool.jsonl` → `existing` dict（key=`norm_zh`）
2. 逐行读 `draft.jsonl`，跳过空 `zh`/`en`
3. `norm` 已存在且非 `--force` → `skipped++`；否则 `existing[norm] = 新记录`
4. 备份 `.bak`，写 `.tmp`，rename 替换
5. 打印「新增/更新 N，跳过 N，合计 N 条」

**与 `additional_pool.append_records` 的关系**：逻辑完全一致，`append.py` 是命令行版本，`append_records` 是 Python API 版本，两者可互换操作同一个 `pool.jsonl`。

---

### 14.5 文件依赖关系图

```
testD/
├── docs/
│     ├── ENHANCED_TRANSLATE_DESIGN.md   ← 本文档
│     └── …
├── frontend/src/components/
│     └── EnhancedTranslate.vue          ← 前端页面（统计摘要、行类型、Pool 标签）
└── backend/
      ├── _bootstrap.py
      │     └── 作用：把 back_mic/backend 加入 sys.path
      │
      ├── additional_pool.py
      │     ├── 提供：normalize_zh, lookup_line_en, append_records,
      │     │         collect_auto_append_rows, auto_append_enabled, reload_pool
      │     └── 数据：Additional-pool/pool.jsonl
      │
      ├── enhanced_translate_prompts.py
      │     └── 提供：ENHANCED_TRANSLATE_PROMPT_SUFFIX, PROOFREAD_OUTLINE_PROMPT
      │
      ├── enhanced_translate_service.py
      │     ├── import _bootstrap → ensure_main_backend_path()
      │     ├── import additional_pool → normalize_zh, lookup_line_en 等
      │     ├── import enhanced_translate_prompts → ENHANCED_TRANSLATE_PROMPT_SUFFIX
      │     └── import（经 bootstrap）back_mic/backend 下：
      │           kg_rag.retrieval, es_config, ai_search.*, embedding_adapter
      │
      ├── enhanced_translate_router.py
      │     └── import enhanced_translate_service → enhanced_translate, get/set_prompt_override
      │
      ├── test_translate.py
      │     └── 单元测试（行解析 + Pool 短路验证）
      │
      ├── app.py
      │     └── 本地调试入口（端口 8010）
      │
      └── Additional-pool/
            ├── pool.jsonl            ← 实际数据文件
            ├── README.md
            └── tools/
                  ├── lookup.py       ← 命令行查询
                  ├── stats.py        ← 条数统计
                  ├── validate.py     ← 文件校验
                  ├── export_draft.py ← 从翻译结果导出 draft
                  └── append.py       ← 合并 draft 进 pool
```

---

### 14.6 pool.jsonl 记录结构（完整字段）

```json
{
  "zh":             "一\t生命",
  "en":             "A.\tLife",
  "norm_zh":        "一生命",
  "saved_at":       "2026-06-01T10:00:00+00:00",
  "prompt_version": "",
  "source":         "enhanced_translate"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `zh` | str | 原始中文行（含序号和读经后缀） |
| `en` | str | 对应英文行 |
| `norm_zh` | str | `normalize_zh(zh)` 的结果，作为查询键 |
| `saved_at` | str | ISO 8601 UTC 时间戳 |
| `prompt_version` | str | 生成时使用的 prompt 版本（当前未填，预留字段） |
| `source` | str | 来源标识，自动写入为 `"enhanced_translate"`，手动导入为 `"manual"` |


---

### 14.7 `app.py` — 本地独立调试入口

```python
# -*- coding: utf-8 -*-
"""testD 本地调试入口（方式 B），默认端口 8010。上线仍依赖主站 main.py 挂载路由。"""
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from testD.backend.enhanced_translate_router import router

app = FastAPI(title="testD Enhanced Translate (debug)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("TESTD_PORT", "8010"))
    uvicorn.run("testD.backend.app:app", host="0.0.0.0", port=port, reload=True)
```

#### 作用

增强翻译有两种运行方式：

| 方式 | 入口 | 端口 | 适用场景 |
|------|------|------|----------|
| **方式 A（上线）** | 主工程 `back_mic/backend/main.py` `include_router(enhanced_translate_router)` | 主站端口 | 生产环境，增强翻译作为主站子功能 |
| **方式 B（调试）** | `testD/backend/app.py` | 8010（可配置） | 本地开发，单独启动，不依赖主站 |

方式 B 的意义：改 `enhanced_translate_service.py` 后只需重启这一个小服务，不用动主站，启动速度快，调试周期短。

#### 路径计算

```python
_REPO = Path(__file__).resolve().parents[2]
# __file__ = 仓库根/testD/backend/app.py
# parents[0] = 仓库根/testD/backend/
# parents[1] = 仓库根/testD/
# parents[2] = 仓库根/               ← _REPO
sys.path.insert(0, str(_REPO))
```

把**仓库根**加入 `sys.path`，这样 `from testD.backend.enhanced_translate_router import router` 才能找到 `testD` 包。

**与 `_bootstrap.py` 的区别**：

| | `app.py` | `_bootstrap.py` |
|---|---|---|
| 加入 sys.path 的路径 | 仓库根（让 `testD` 包可 import） | `back_mic/backend`（让主工程模块可 import） |
| 调用时机 | `app.py` 启动时 | `enhanced_translate_service.py` 顶部 |

两个路径都需要，缺一不可。`app.py` 保证 `testD` 自身可被引用，`_bootstrap.py` 保证主工程的 `kg_rag`、`es_config`、`ai_search` 等可被引用。

#### 启动方式

```bash
# 默认端口 8010
python testD/backend/app.py

# 自定义端口
TESTD_PORT=8020 python testD/backend/app.py
```

`reload=True` 开启 uvicorn 热重载，修改代码后自动重启服务，无需手动操作。

#### CORS 配置

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

调试模式下允许所有跨域请求，方便前端 `EnhancedTranslate.vue` 直接访问 `http://localhost:8010`，不受浏览器同源策略限制。**生产环境由主站统一管理 CORS，不使用此文件。**

---

### 14.8 `EnhancedTranslate.vue` — 前端页面

路径：`testD/frontend/src/components/EnhancedTranslate.vue`

**主要功能**：
- 粘贴中文纲目 → 调用 `POST /api/kg_rag/enhanced_translate`
- 展示英文纲目、参考语料（绿色=直接引用，蓝色=参考翻译）
- 下载 DOCX（`format_outline_only`）、下载原文+语料 TXT
- 保存/覆盖服务端 Prompt（`POST /enhanced_translate/update_prompt`）

**API 响应字段使用**：

| 字段 | 前端用途 |
|------|----------|
| `result` | 英文纲目展示区 |
| `refs` | 按行展示参考语料（`line_ref_groups`） |
| `summary` | 统计摘要面板（总行数、命中率、Gemini 费用、Pool 写入数等） |
| `warnings` | 顶部警告横幅（ES 降级、无 OpenRouter Key 等） |

**行级 UI 增强**（相对初版）：
- `line_type` 标签：`outline`（紫色）/ `reference`（灰色）
- Pool 命中标签：`stats.additional_pool_line` → 绿色「Additional Pool」；`stats.pool_line` → 蓝色「ES Pool」
- `summary` 网格：展示 `total_lines`、`exact`、`retrieved`、`gemini_cost_usd`、`additional_pool_appended` 等

