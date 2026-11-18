# -*- coding: utf-8 -*-
"""
经文出处识别 v2.1

相对 v2 的改动：

0. 中文节号列表
   「代上三章十一、十二节」「希伯来四章八、九、十一节」「以赛亚九章一、二节」「五、六节」
   这种用顿号列几节、共用一个「节」字的写法，v2 的章节式（B）与纯节式（D）都只认
   单节或「至」连起来的范围 —— 碰到顿号就断开：前半截「代上三章」成了整章出处，
   后半截只剩最后一个「十二节」，中间几节直接丢了。
   v2.1 让 B / D 的节号部分接受列表（VERSE_LIST_CN）：项与项之间用「、」「及」「和」，
   每项仍可以是「至」连起来的范围（「一至三、五节」）。一整串出一个片段，展开成逐节出处。
   用「，」分隔的不认 —— 逗号在行文里是句读，放进来会把下一句的数字吞掉。

（以下为 v2 相对 get_vers.py 的改动）

1. 书名表自动补全
   原表只收了部分写法。正文常写「以赛亚四十章」（无「书」）、「约壹」（而非「约一」），
   匹配不上时正则会退而在「以赛[亚]」里捞到「亚」＝撒迦利亚书 —— 张冠李戴比漏检更糟。
   v2 启动时从 bible.json 自动补出「去后缀写法」与「通行简称」。

2. 带校验的书名消歧
   「约二一15～19」有两种切法：约二|一15（约翰二书1:15）或 约|二一15（约翰福音21:15）。
   贪婪匹配必选前者，而约翰二书只有 13 节。v2 接受一个 validate 回调，
   逐个候选切法试，取第一个真实存在的。

3. 全局的卷/章，跨段纯继承；正文裸书名也更新它
   无书名的出处靠继承上文。文档层级（壹/一/1/a）不参与判断 ——
   解析器按段落顺序维护一个全局的「卷」和「章」，缺卷的继承卷，缺章的继承章。

   纯继承本来会在换卷处串味（上一段停在林后，下一段的「八3」就成了林后八章），
   救济来自正文本身：新段落回到本卷时几乎总会把卷名写出来
   （「壹　罗马书中深奥的神圣思想…─八3」）。v2 因此把正文里不带章节
   单独出现的书名也当作状态更新点，只认带书卷后缀的写法（见 _is_mention）。

4. 分辨正文里的杂数字
   纯继承让「卷」几乎总是有值，于是每个数字都够格当出处，正文里的条目编号、
   页码、诗歌号会成批冒充经节。v2 用四道关拦：
     - 不带「节」字的裸阿拉伯数字，必须紧跟在另一处出处后面（_is_stray_number）；
       括号里的节号例外，靠 _verse_parens 放行
     - 量词和指示词开头的不算（_is_count_idiom：「共四十一章」「下一节」「一节一节」）
     - 诗歌小节不算（HYMN：「诗歌六二八首，五至十节」）
     - 拼出来的出处逐条对回真实经文，对不上就整条作废（_check）

用法：

    from get_vers_v2 import VerseParser, build_validator, load_book_map

    validate = build_validator('data/bible')          # 可选
    p = VerseParser(validate=validate, volume_book='彼后')
    for para in paragraphs:
        p.start_paragraph()
        groups = p.parse_text(para['text'])
"""
import json
import os
import re

# ---------------------------------------------------------------- 书卷名表
BOOK_MAP = {
    "创世记": "创", "创": "创", "出埃及记": "出", "出": "出", "利未记": "利", "利": "利",
    "民数记": "民", "民": "民", "申命记": "申", "申": "申", "约书亚记": "书", "书": "书",
    "士师记": "士", "士": "士", "路得记": "得", "得": "得", "撒母耳记上": "撒上", "撒上": "撒上",
    "撒母耳记下": "撒下", "撒下": "撒下", "列王纪上": "王上", "王上": "王上", "列王纪下": "王下", "王下": "王下",
    "历代志上": "代上", "代上": "代上", "历代志下": "代下", "代下": "代下", "以斯拉记": "拉", "拉": "拉",
    "尼希米记": "尼", "尼": "尼", "以斯帖记": "斯", "斯": "斯", "约伯记": "伯", "伯": "伯",
    "诗篇": "诗", "诗": "诗", "箴言": "箴", "箴": "箴", "传道书": "传", "传": "传", "雅歌": "歌", "歌": "歌",
    "以赛亚书": "赛", "赛": "赛", "耶利米书": "耶", "耶": "耶", "耶利米哀歌": "哀", "哀": "哀",
    "以西结书": "结", "结": "结", "但以理书": "但", "但": "但", "何西阿书": "何", "何": "何",
    "约珥书": "珥", "珥": "珥", "阿摩司书": "摩", "摩": "摩", "俄巴底亚书": "俄", "俄": "俄",
    "约拿书": "拿", "拿": "拿", "弥迦书": "弥", "弥": "弥", "那鸿书": "鸿", "鸿": "鸿",
    "哈巴谷书": "哈", "哈": "哈", "西番雅书": "番", "番": "番", "哈该书": "该", "该": "该",
    "撒迦利亚书": "亚", "亚": "亚", "玛拉基书": "玛", "玛": "玛",
    "马太福音": "太", "马太": "太", "太": "太", "马可福音": "可", "马可": "可", "可": "可",
    "路加福音": "路", "路加": "路", "路": "路", "约翰福音": "约", "约翰": "约", "约": "约",
    "使徒行传": "徒", "行传": "徒", "徒": "徒", "罗马书": "罗", "罗马": "罗", "罗": "罗",
    "哥林多前书": "林前", "林前": "林前", "哥林多后书": "林后", "林后": "林后",
    "加拉太书": "加", "加": "加", "以弗所书": "弗", "以弗所": "弗", "弗": "弗",
    "腓立比书": "腓", "腓立比": "腓", "腓": "腓", "歌罗西书": "西", "歌罗西": "西", "西": "西",
    "帖撒罗尼迦前书": "帖前", "帖前": "帖前", "帖撒罗尼迦后书": "帖后", "帖后": "帖后",
    "提摩太前书": "提前", "提前": "提前", "提摩太后书": "提后", "提后": "提后",
    "提多书": "多", "多": "多", "腓利门书": "门", "门": "门", "希伯来书": "来", "希伯来": "来", "来": "来",
    "雅各书": "雅", "雅各": "雅", "雅": "雅", "彼得前书": "彼前", "彼前": "彼前", "彼得后书": "彼后", "彼后": "彼后",
    # 约翰书信只能写作 约壹/约贰/约叁（或异体 约参）。
    # 「约一」「约二」「约三」是「约翰福音 + 章号」，不是书名 ——
    # 原表把它们当书名，会把约翰福音 1、2、3 章的引用系统性错判成约翰一/二/三书。
    "约翰一书": "约壹", "约壹": "约壹",
    "约翰二书": "约贰", "约贰": "约贰",
    "约翰三书": "约叁", "约叁": "约叁", "约参": "约叁",
    "犹大书": "犹", "犹大": "犹", "犹": "犹", "启示录": "启", "启示": "启", "启": "启",
}

ONE_CHAPTER_BOOKS = {"门", "犹", "约贰", "约叁", "俄"}

# 标准简称 → 卷序（1–66）
STD_ORDER = [
    "创", "出", "利", "民", "申", "书", "士", "得", "撒上", "撒下", "王上", "王下",
    "代上", "代下", "拉", "尼", "斯", "伯", "诗", "箴", "传", "歌", "赛", "耶", "哀",
    "结", "但", "何", "珥", "摩", "俄", "拿", "弥", "鸿", "哈", "番", "该", "亚", "玛",
    "太", "可", "路", "约", "徒", "罗", "林前", "林后", "加", "弗", "腓", "西",
    "帖前", "帖后", "提前", "提后", "多", "门", "来", "雅", "彼前", "彼后",
    "约壹", "约贰", "约叁", "犹", "启",
]
STD2IDX = {s: i + 1 for i, s in enumerate(STD_ORDER)}


def load_book_map(bible_toc_path='data/toc/bible.json'):
    """按 bible.json 自动补全书名写法（去后缀写法 + 通行简称）。找不到文件就跳过。"""
    if not os.path.exists(bible_toc_path):
        return 0
    added = 0
    for b in json.load(open(bible_toc_path, encoding='utf-8')):
        name = b['name']
        std = BOOK_MAP.get(name) or BOOK_MAP.get(b.get('acronym_name', ''))
        if not std:
            continue
        for form in (b.get('acronym_name'), *_strip_suffix(name)):
            if form and form not in BOOK_MAP:
                BOOK_MAP[form] = std
                added += 1
    if added:
        _rebuild_pattern()
    return added


def _strip_suffix(name):
    """
    「以赛亚书」→「以赛亚」；单字结果不要，免得造出新的误匹配。
    「约翰一书」→「约翰一」也不要 —— 它和「约翰福音一章」的写法撞车。
    """
    for suf in ('福音', '书', '记', '纪'):
        if name.endswith(suf) and len(name) > len(suf):
            bare = name[:-len(suf)]
            if len(bare) < 2 or bare[-1] in '一二三壹贰叁参':
                return []
            return [bare]
    return []


# ---------------------------------------------------------------- 数字
def cn2num(cn_str):
    """中文数字（三十 / 二四 / 十五）→ 阿拉伯数字字符串"""
    if not cn_str:
        return ""
    cn_str = cn_str.replace(" ", "")
    if cn_str.isdigit():
        return cn_str

    # 零有三种写法：零、○（U+25CB）、〇（U+3007）。本语料三种都在用，
    # 「诗一〇〇1~3」「一一〇2~3」少一种就整条解析不出来。
    d = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
         '七': 7, '八': 8, '九': 9, '十': 10, '百': 100,
         '零': 0, '○': 0, '〇': 0}

    # 「二四」这类逐位写法
    if all(c in "一二三四五六七八九零○〇" for c in cn_str):
        return "".join(str(d[c]) for c in cn_str)

    total = cur = 0
    for ch in cn_str:
        if ch not in d:
            continue
        v = d[ch]
        if v >= 10:
            cur = cur or 1
            total += cur * v
            cur = 0
        else:
            cur = v
    return str(total + cur)


def _num(s):
    return None if s is None else (s if s.isdigit() else cn2num(s))


CN = "[一二三四五六七八九十百零○〇]+"

# 中文节号列表（v2.1）：「十一、十二」「八、九、十一」「一至三、五」。
# 只认「、及和」作分隔，逗号不认（见模块开头）
_CN_RANGE = rf"{CN}(?:[至到～~－—\-]{CN})?"
VERSE_LIST_CN = rf"{_CN_RANGE}(?:[、及和]{_CN_RANGE})*"

# ---------------------------------------------------------------- 正则
BOOK_NAMES_PATTERN = ""
REF_PATTERN = None
REF_BOOK_HEAD = None
BOOK_MENTION_PATTERN = None

# 正文裸书名（不带章节）只认带书卷后缀的写法。
# 去掉后缀的写法必须排除掉：「以弗所」「歌罗西」「腓立比」「罗马」是地名
# （「以弗所的信徒」不是在讲以弗所书），「约翰」「犹大」「雅各」「以赛亚」是人名，
# 「启示」是动词（「四福音所启示个人的基督」）。带后缀就没有这些歧义。
MENTION_SUFFIXES = ("书", "记", "纪", "志", "福音", "传", "篇", "录", "歌")


def _is_mention(name):
    """「罗马书」「诗篇」「使徒行传」「撒母耳记上」→ 真；「以弗所」「启示」「箴言」→ 假。"""
    stem = name[:-1] if name[-1:] in "上下" else name
    return len(name) >= 2 and stem.endswith(MENTION_SUFFIXES)


def _rebuild_pattern():
    """书名表变动后重建正则。长名优先，避免「哥林多前书」被「林前」抢先。"""
    global BOOK_NAMES_PATTERN, REF_PATTERN, BOOK_MENTION_PATTERN
    BOOK_NAMES_PATTERN = "|".join(sorted(map(re.escape, BOOK_MAP), key=len, reverse=True))
    B = BOOK_NAMES_PATTERN

    mentions = [n for n in BOOK_MAP if _is_mention(n)]
    BOOK_MENTION_PATTERN = re.compile(
        "|".join(sorted(map(re.escape, mentions), key=len, reverse=True))
    ) if mentions else None
    # 片段开头是不是书名（调用方判断「这处出处有没有自带书名」用）
    global REF_BOOK_HEAD
    REF_BOOK_HEAD = re.compile(rf"^(?:{B})")
    REF_PATTERN = re.compile(
        # A 跨章范围：…章…节和…章…节之间 / …章…节至…章…节
        rf"(?P<Abook>{B})?第?(?P<Ac1>{CN})[章篇](?P<Av1>{CN})节"
        rf"(?:和(?P<Ab2>{B})?第?(?P<Ac2>{CN})[章篇](?P<Av2>{CN})节之间"
        rf"|[至到](?P<Ab3>{B})?第?(?P<Ac3>{CN})[章篇](?P<Av3>{CN})节)"
        # F 共享「章」的章号列表：约翰十四、十五、十六章
        rf"|(?P<Fbook>{B})?第?(?P<Fc1>{CN})(?P<Frest>(?:[、，]{CN})+)(?P<Funit>[章篇])"
        # B 行文章节：(书)十四章[十六至十八节]；诗篇用「篇」作章号单位
        rf"|(?P<Bbook>{B})?第?(?P<Bc1>{CN})(?P<Bunit>[章篇])(?:(?P<Bvl>{VERSE_LIST_CN})节)?"
        # C 简写章节：(书)中文章 + 阿拉伯节
        rf"|(?P<Cbook>{B})(?P<Cc>{CN})(?P<Cv1>[0-9]+)[上下]?(?:[～~－—\-](?P<Cv2>[0-9]+)[上下]?)?"
        # G 单章书直接跟阿拉伯节：约参1 / 犹9 / 门5
        rf"|(?P<Gbook>{B})(?P<Gv1>[0-9]+)[上下]?(?:[～~－—\-](?P<Gv2>[0-9]+)[上下]?)?"
        # C' 承上文的中文章 + 阿拉伯节（无书名）
        rf"|(?P<Hc>{CN})(?P<Hv1>[0-9]+)[上下]?(?:[～~－—\-](?P<Hv2>[0-9]+)[上下]?)?"
        # D 中文纯节：二十一节 / 十六至十八节
        rf"|(?P<Dvl>{VERSE_LIST_CN})节"
        # E 阿拉伯纯节：37～38 / 39 / 13节
        rf"|(?P<Ev1>[0-9]+)[上下]?(?:[～~－—\-](?P<Ev2>[0-9]+)[上下]?)?节?"
    )


_rebuild_pattern()

# 两处出处之间只隔标点/连接词 → 归为一组。
# 括号不算连接符：它是结构边界，跨过去就把两句话并成一处高亮了 ——
# 「…差遣我。”（9，11）八节中的“我”指…」会圈出「9，11）八节」，
# 把下一句的主语「八节」一起吞掉。括号内外分开成组才对。
CONNECTOR = re.compile(r"[\s，,、；;：:“”\"'’‘–—－\-~～·　和至到]*")

# 全角括号里的数字是节号（「话就是神（1）」「（3～11）」），
# 半角括号里的是条目编号或英文（「(3)，长老的设立」「(1) In the Stage of…」）。
# 这个排版习惯在本语料里很干净：全角 123 处全是出处，半角 77 处没有一处是。
PAREN_FULL = re.compile(r"（([^（）]*)）|〔([^〔〕]*)〕|【([^【】]*)】")
PAREN_HALF = re.compile(r"\(([^()]*)\)")
# 括号里整个就是一串节号：3～11 / 16上 / 12下，14上，17上
VERSE_LIST = re.compile(r"^\d+[上下]?(?:[～~－—\-]\d+[上下]?)?"
                        r"(?:[，,、]\d+[上下]?(?:[～~－—\-]\d+[上下]?)?)*$")
# 半角括号要再带上范围号、上下半节或逗号列表才当出处，光一个数字不算
VERSE_SIGNAL = re.compile(r"[～~－—\-上下，,、]")

# 出处旁边常挂一个批注词：「（7下，另译）」「（如10，12，18）」「腓一19，参看12~13」
ANNOTATION = "原文|参看|另参|另译|直译|下同|英文|参|见|如"
NOTE_LEAD = re.compile(rf"^(?:{ANNOTATION})?[\s　]*")
NOTE_TAIL = re.compile(rf"[，,、][\s　]*(?:{ANNOTATION})[\s　]*$")
# 两处出处之间夹着批注词，仍算紧挨着（「太十六25原文，参看24~27」夹了两个）
ADJACENT = re.compile(rf"{CONNECTOR.pattern}(?:(?:{ANNOTATION}){CONNECTOR.pattern})*")


# 「共四十一章」「头三十九章」「最后一章」「前一篇」数的是篇幅，
# 「下一节圣经」「这一节」指的是上下文里的某节，都不是出处
IDIOM_PREFIX = "前后头共末首上下这那每另本同读念"


# 「每天读三章旧约、一章新约」里的章数的是分量
QUANTITY_HEAD = ("旧约", "新约", "圣经")


def _is_count_idiom(m, text):
    """章号/节号是不是量词或指示词，而不是出处。

    只在没有书名时判：「林前十一章」「彼后一章」里的「前」「后」是书名的一部分，
    早被书名吃掉了，轮不到这里。
    """
    g = m.groupdict()
    if (g["Bc1"] is None or g["Bbook"] is not None) and g["Dvl"] is None:
        return False
    frag, n = m.group(), len(m.group())
    # 叠词：「一卷书一节一节的读」「一章一章的查」
    if text[m.end():m.end() + n] == frag or text[m.start() - n:m.start()] == frag:
        return True
    # 「共四十一章」「最后一章」「下一节圣经」「每天读三章」
    if m.start() and text[m.start() - 1] in IDIOM_PREFIX:
        return True
    # 「三章旧约」「一章新约」
    return text[m.end():m.end() + 2] in QUANTITY_HEAD


# 「诗歌六二八首，五至十节」「诗歌128，123，49」数的是诗歌，不是圣经的章节。
# 从诗歌标记一直圈到本小句结束（句号/分号/右括号），圈内的数字一律不当出处。
# 两种写法都要认：带「首」的，和「诗歌」后面直接跟号码的。
# 不能只写成「诗歌后面整句都不算」—— 那样「（诗歌三六二首）这首诗歌出自作者对腓三10
# 的经历」里的腓三10 会被一起圈掉。
HYMN = re.compile(r"(?:诗歌|福音诗|擘饼诗|补充本|英诗)"
                  r"(?:[^。；）)]{0,24}?首[^。；）)]*"
                  rf"|[\s　]*第?[0-9{CN[1:-2]}][^。；）)]*)")


def _verse_parens(text):
    """找出「整个括号里就是一串节号」的括号，返回其内容的位置区间。

    这些节号（「话就是神（1）」「本章第一段（3～11）」）不跟在别的出处后面，
    没有这一关就会被 _is_stray_number 当成正文里的杂数字扔掉。
    """
    out = []
    for pat, need_signal in ((PAREN_FULL, False), (PAREN_HALF, True)):
        for m in pat.finditer(text):
            inner = next((g for g in m.groups() if g is not None), "")
            if not inner:
                continue
            lead = len(NOTE_LEAD.match(inner).group())        # 「（如10，12，18）」
            core = NOTE_TAIL.sub("", inner[lead:])            # 「（7下，另译）」
            if not core or not VERSE_LIST.match(core):
                continue
            if need_signal and not VERSE_SIGNAL.search(core):
                continue
            st = m.start() + 1 + lead
            out.append((st, st + len(core)))
    return out


# ---------------------------------------------------------------- 校验器
def build_validator(bible_dir='data/bible'):
    """
    返回 validate(std, chap, verse) -> bool，用真实圣经数据判断该节是否存在。
    没有数据就返回 None（解析器退回无校验模式）。
    """
    if not os.path.isdir(bible_dir):
        return None
    exists = set()
    for idx in range(1, 67):
        path = os.path.join(bible_dir, '%d.json' % idx)
        if not os.path.exists(path):
            continue
        for _, verses in json.load(open(path, encoding='utf-8')).items():
            for v in verses:
                m = re.match(r'^(\d+)-(\d+)-(\d+)', v.get('id') or '')
                if m:
                    exists.add((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    if not exists:
        return None

    def validate(std, chap, verse=None):
        idx = STD2IDX.get(std)
        if idx is None:
            return False
        if verse is None:                      # 只验章存在
            return any((idx, chap, v) in exists for v in range(1, 4))
        return (idx, chap, verse) in exists

    return validate


# ---------------------------------------------------------------- 解析器
class VerseParser:
    def __init__(self, validate=None, volume_book=None,
                 reset_book_each_paragraph=False):
        """
        validate: 可选的 (std, chap, verse) -> bool，用于书名消歧
        volume_book: 起始卷（标准简称），只作为第一段之前的初值
        reset_book_each_paragraph: 兼容旧行为的开关，默认关闭（见 start_paragraph）
        """
        self.validate = validate
        self.volume_book = volume_book
        self.reset_book_each_paragraph = reset_book_each_paragraph
        self.current_book = volume_book
        self.current_chap = None

    def start_paragraph(self):
        """段落边界默认什么都不做 —— 「卷」和「章」都跨段继承。

        文档层级（壹/一/1/a）不参与判断。缺卷的出处继承上文的卷，缺章的继承上文的章，
        全局状态只被两件事改写：出处自带的书名，以及正文里单独出现的书名
        （「按照罗马书，神的福音…」，见 parse_text）。后者是纯继承能站得住的前提 ——
        新的顶层段落回到本卷时，正文几乎总会把卷名写出来。

        reset_book_each_paragraph=True 恢复旧行为（新段落把卷重置为 volume_book）。
        """
        if self.reset_book_each_paragraph:
            self.current_book = self.volume_book

    # ---------------- 内部 ----------------
    def _set_book(self, raw):
        if raw:
            self.current_book = BOOK_MAP[raw]
            if self.current_book in ONE_CHAPTER_BOOKS:
                self.current_chap = "1"

    # 输出串形如 罗8:14 / 罗8:14-15 / 罗12 / 罗1:3_2:5 / 罗14，罗15
    _OUT = re.compile(r"^(?P<b>\D+)?(?P<c>\d+)(?::(?P<v1>\d+)(?:-(?P<v2>\d+))?)?$")

    def _check(self, out):
        """把拼好的输出串逐条对回真实经文，有一条不存在就整条作废。

        承上文的出处（「百节各按各职」的「百节」、正文里的页码和诗歌号）没有别的
        信号可判真假，只能靠这一关拦。没有校验器时原样放行。
        """
        if out is None or not self.validate:
            return out
        for part in out.split("，"):
            book = None
            for seg in part.split("_"):        # 跨章范围的后半段不带书名
                m = self._OUT.match(seg)
                if not m:
                    return None
                book = m.group("b") or book
                chap = m.group("c")
                verses = [v for v in (m.group("v1"), m.group("v2")) if v]
                if not verses:
                    if not self._ok(book, chap):
                        return None
                elif not all(self._ok(book, chap, v) for v in verses):
                    return None
        return out

    def _unit_ok(self, unit):
        """「篇」只有诗篇拿来作章号单位。

        没有这一关，「听一篇信息」「诗歌六二八首」里的「篇」都会被当成章号。
        """
        return unit != "篇" or self.current_book == "诗"

    def _ok(self, std, chap, verse=None):
        if not self.validate:
            return True
        try:
            return self.validate(std, int(chap), int(verse) if verse else None)
        except (TypeError, ValueError):
            return False

    def _split_candidates(self, frag):
        """
        把「约二一15～19」这类片段按不同书名切法列出候选。
        长书名优先（保持原行为），但后面会用校验挑出真正成立的那个。
        """
        out = []
        for name in sorted(BOOK_MAP, key=len, reverse=True):
            if frag.startswith(name):
                out.append((name, frag[len(name):]))
        return out

    def _disambiguate(self, m):
        """
        书名贪婪匹配的救济：整段重新按各种切法解析，取第一个通过校验的。
        没有校验器或都不通过时返回 None，交回原路径。
        """
        if not self.validate:
            return None
        frag = m.group()
        for name, rest in self._split_candidates(frag):
            std = BOOK_MAP[name]
            # rest 形如「二一15～19」/「一15」/「9」
            mm = re.match(rf"^(?P<c>{CN})?(?P<v1>[0-9]+)(?:[～~－—\-](?P<v2>[0-9]+))?$", rest)
            if not mm:
                continue
            if mm.group('c'):
                chap = _num(mm.group('c'))
            elif std in ONE_CHAPTER_BOOKS:
                chap = "1"
            else:
                continue
            v1 = mm.group('v1')
            v2 = mm.group('v2')
            if not self._ok(std, chap, v1):
                continue
            if v2 and not self._ok(std, chap, v2):
                continue
            self.current_book, self.current_chap = std, chap
            return f"{std}{chap}:{v1}-{v2}" if v2 else f"{std}{chap}:{v1}"
        return None

    def _verse_list(self, raw):
        """「十一、十二」「一至三、五」→「代上3:11，代上3:12」「代上3:1-3，代上3:5」（当前卷章）。"""
        out = []
        for item in re.split(r"[、及和]", raw):
            parts = re.split(r"[至到～~－—\-]", item)
            v1 = _num(parts[0])
            if len(parts) > 1 and parts[1]:
                out.append(f"{self.current_book}{self.current_chap}:{v1}-{_num(parts[1])}")
            else:
                out.append(f"{self.current_book}{self.current_chap}:{v1}")
        return "，".join(out)

    def _emit(self, m):
        g = m.groupdict()

        # A 跨章范围
        if g["Ac1"] is not None:
            self._set_book(g["Abook"])
            if not self.current_book:
                return None
            c1, v1 = _num(g["Ac1"]), _num(g["Av1"])
            if g["Ac2"] is not None:
                c2, v2 = _num(g["Ac2"]), _num(g["Av2"])
            else:
                c2, v2 = _num(g["Ac3"]), _num(g["Av3"])
            self.current_chap = c2
            if c1 == c2:
                return f"{self.current_book}{c1}:{v1}-{v2}"
            return f"{self.current_book}{c1}:{v1}_{c2}:{v2}"

        # F 章号列表
        if g["Fc1"] is not None:
            self._set_book(g["Fbook"])
            if not self.current_book or not self._unit_ok(g["Funit"]):
                return None
            chaps = [_num(g["Fc1"])] + [_num(c) for c in re.findall(CN, g["Frest"])]
            self.current_chap = chaps[-1]
            return "，".join(f"{self.current_book}{c}" for c in chaps)

        # B 行文章节
        if g["Bc1"] is not None:
            self._set_book(g["Bbook"])
            if not self.current_book or not self._unit_ok(g["Bunit"]):
                return None
            self.current_chap = _num(g["Bc1"])
            if g["Bvl"] is not None:
                return self._verse_list(g["Bvl"])
            return f"{self.current_book}{self.current_chap}"

        # C 带书名的简写章节 —— 书名可能被贪婪切错，先试消歧
        if g["Cc"] is not None:
            alt = self._disambiguate(m)
            if alt:
                return alt
            self._set_book(g["Cbook"])
            if not self.current_book:
                return None
            self.current_chap = _num(g["Cc"])
            if g["Cv2"] is not None:
                return f"{self.current_book}{self.current_chap}:{g['Cv1']}-{g['Cv2']}"
            return f"{self.current_book}{self.current_chap}:{g['Cv1']}"

        # G 单章书 + 阿拉伯节
        if g["Gv1"] is not None:
            std = BOOK_MAP[g["Gbook"]]
            if std not in ONE_CHAPTER_BOOKS:
                alt = self._disambiguate(m)
                if alt:
                    return alt
                return None
            self.current_book, self.current_chap = std, "1"
            if g["Gv2"] is not None:
                return f"{std}1:{g['Gv1']}-{g['Gv2']}"
            return f"{std}1:{g['Gv1']}"

        # H 承上文的中文章 + 阿拉伯节
        if g["Hc"] is not None:
            if not self.current_book:
                return None
            self.current_chap = _num(g["Hc"])
            if g["Hv2"] is not None:
                return f"{self.current_book}{self.current_chap}:{g['Hv1']}-{g['Hv2']}"
            return f"{self.current_book}{self.current_chap}:{g['Hv1']}"

        # D 中文纯节
        if g["Dvl"] is not None:
            if not self.current_book or not self.current_chap:
                return None
            return self._verse_list(g["Dvl"])

        # E 阿拉伯纯节
        if g["Ev1"] is not None:
            if not self.current_book or not self.current_chap:
                return None
            if g["Ev2"] is not None:
                return f"{self.current_book}{self.current_chap}:{g['Ev1']}-{g['Ev2']}"
            return f"{self.current_book}{self.current_chap}:{g['Ev1']}"

        return None

    # ---------------- 杂数字 ----------------
    @staticmethod
    def _is_bare(m, verse_parens):
        """光秃秃的阿拉伯数字：没有书名、没有章号，也没有「节」字。

        「罗八2，4，6」里的 4、6 是这样，「1创造万物」「一锤150元」也是这样，
        单看它自己分不出来，得看它所在的那一串（见 _anchored）。
        括号里的节号（「本章第一段（3～11）」）自带出处的身份，不算光秃秃。
        """
        if m.groupdict()["Ev1"] is None or m.group().endswith("节"):
            return False
        return not any(st <= m.start() and m.end() <= en for st, en in verse_parens)

    @staticmethod
    def _anchored(refs, text, verse_parens):
        """把出处按「中间只隔标点或批注词」串成链，逐链判断该不该收。

        一串里只要有一处不是光秃秃的数字（自带书名、章号或「节」字），
        整串就都是出处：「罗八2，4，6」的锚在头，「19，22～23，16节」的锚在尾，
        两种写法都常见，所以只往一边看是不够的。
        整串都光秃秃的（「1创造万物，2启示圣经」「一锤150元」）就全丢。

        返回与 refs 等长的布尔表：这一处是否放行。
        """
        bare = [VerseParser._is_bare(m, verse_parens) for m in refs]
        keep = [True] * len(refs)
        i = 0
        while i < len(refs):
            j = i + 1
            while j < len(refs) and ADJACENT.fullmatch(text[refs[j - 1].end():refs[j].start()]):
                j += 1
            if all(bare[k] for k in range(i, j)):        # 整串没有锚
                for k in range(i, j):
                    keep[k] = False
            i = j
        return keep

    # ---------------- 对外 ----------------
    def parse_text(self, text):
        # 行首纲目序号（「1　在神的创造里…」）不是经文；等长空格替换以保持位置
        text = re.sub(r"^[0-9]+(?=[　\s])", lambda x: " " * len(x.group()), text)

        # 先把出处扫出来，好让下面的裸书名跳过落在出处内部的那些
        # （「哥林多前书一章」里的「哥林多前书」已由出处自己处理）
        hymns = [(m.start(), m.end()) for m in HYMN.finditer(text)]
        refs = [m for m in REF_PATTERN.finditer(text)
                if not m.group().startswith("第")    # 「第三章」多为文档结构编号
                and not _is_count_idiom(m, text)
                and not any(st <= m.start() < en for st, en in hymns)]
        spans = [(m.start(), m.end()) for m in refs]

        # 正文里不带章节单独出现的书名，同样更新全局的卷
        mentions = []
        if BOOK_MENTION_PATTERN is not None:
            for m in BOOK_MENTION_PATTERN.finditer(text):
                if any(st < m.end() and m.start() < en for st, en in spans):
                    continue
                mentions.append((m.start(), m.group()))

        # 按出现位置交错处理：书名先于其后的出处生效
        verse_parens = _verse_parens(text)
        keep = self._anchored(refs, text, verse_parens)
        tokens = []
        i = 0
        for idx, m in enumerate(refs):
            while i < len(mentions) and mentions[i][0] < m.start():
                self._set_book(mentions[i][1])
                i += 1
            if not keep[idx]:
                continue
            saved = (self.current_book, self.current_chap)
            verse = self._check(self._emit(m))
            if verse:
                tokens.append((m.start(), m.end(), verse))
            elif any(m.groupdict()[k] for k in ("Abook", "Bbook", "Cbook", "Fbook", "Gbook")):
                # 出处作废，但白纸黑字写着的书名仍算数：「诗一百97，20，一2」里
                # 诗一百没有第 97 节，可「诗」是真的，后面的「一2」还得靠它
                self.current_chap = saved[1]
            else:
                self.current_book, self.current_chap = saved   # 全靠猜的，不留痕迹
        for _, name in mentions[i:]:        # 末尾的书名留给下一段继承
            self._set_book(name)

        groups = []
        for st, en, verse in tokens:
            if groups and CONNECTOR.fullmatch(text[groups[-1][1]:st]):
                groups[-1][1] = en
                groups[-1][2].append(verse)
            else:
                groups.append([st, en, [verse]])

        # 带上起止位置：渲染层据此定位，不必再拿 text 去正文里搜。
        # 搜出来的位置不可靠 —— 同一串「6」「1节」在一段里可能出现好几次。
        # 位置一直是准的：开头的纲目序号是用等长空格替换的，没有移位。
        return [{"text": text[st:en], "verses": "，".join(vs), "start": st, "end": en}
                for st, en, vs in groups]


def process_data(json_msg, validate=None, volume_book=None):
    """兼容 v1：整篇喂入，逐段解析，状态跨段继承。"""
    data = json.loads(json_msg) if isinstance(json_msg, str) else json_msg
    parser = VerseParser(validate=validate, volume_book=volume_book)
    out = []
    for item in data:
        parser.start_paragraph()
        out.append({
            "id": item.get("id"),
            "text": item.get("text"),
            "type": item.get("type"),
            "verses": parser.parse_text(item.get("text", "")),
        })
    return out


# 载入时自动补全书名表
load_book_map()


if __name__ == "__main__":
    validate = build_validator()
    paras = [
        "彼后一章十二节说，“所以，你们虽已知道这些事，且在现有的真理上得了坚固，我还要常常提醒你们。”",
        "在本章第一段（3～11），彼得用那为着正当基督徒生活之神圣生命的供备，预防背道的事。"
        "在第二段（12～21），他用神圣真理的启示，作第二种抗毒剂。",
        "在十三至十四节彼得说，“我认为趁我还在这帐幕的时候，以提醒激发你们，是正当的。”"
        "他记得主吩咐他要喂养主的羊时，对他说到他死的事（约二一15～19）。",
    ]
    paras += [
        # v2.1：中文节号列表
        "八节说，“约兰生乌西亚。”请比较这记载与代上三章十一、十二节，那里说，",
        "希伯来四章八、九、十一节也说到耶稣是我们的真约书亚。",
        "自然而然应验了以赛亚九章一、二节的预言。",
        "约翰引荐的方式，第一面是将人浸在水里；五、六节启示，",
    ]
    p = VerseParser(validate=validate, volume_book="彼后")
    for t in paras:
        p.start_paragraph()
        for g in p.parse_text(t):
            print("  %-18s → %s" % (g["text"], g["verses"]))
