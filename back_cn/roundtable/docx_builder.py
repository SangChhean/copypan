"""
小排生命读经材料制作 - Step 5 排版模块
基于对四份正式模版 document.xml 的逆向分析构建。
策略：不新建文档，而是复用模版原始 docx（保留 styles.xml/theme/footer 等一切基础设施），
只替换 word/document.xml 里 <w:body> 的段落内容，段落样式引用（pStyle）和 run 级别字号覆盖
严格复刻自模版本身已有的真实段落。
"""
import re
import shutil
import zipfile
from pathlib import Path
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W_NS}

# 没有指定角色专属字体时的兜底默认值，确保 ascii/hAnsi 槽位不会空着交给 Word 自己决定
DEFAULT_FALLBACK_FONT = "方正书宋_GBK"


def W(tag):
    return f"{{{W_NS}}}{tag}"


def _write_xml_with_double_quote_declaration(tree, path):
    """
    lxml 的 tree.write(xml_declaration=True) 默认输出单引号XML声明，
    这个写法在真实 Word 里解析 .rels 和 [Content_Types].xml 这类包级别文件时
    可能导致图片等资源加载失败。这里手动拼接标准双引号声明，避免这个坑。

    注意：不能同时传 standalone=True，lxml 会无视 xml_declaration=False 强行
    带出（单引号版本的）声明行，导致文件里出现两行XML声明、变成不合法的XML。
    """
    xml_bytes = etree.tostring(
        tree.getroot(), xml_declaration=False, encoding="UTF-8"
    )
    declaration = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    with open(path, "wb") as f:
        f.write(declaration + xml_bytes)


# ---------------------------------------------------------------------------
# 每个版本、每种"角色"段落的样式规格（从真实模版逆向提取，数值不要改）
# ---------------------------------------------------------------------------

STYLE_SPEC = {
    "truth": {  # 真理加强版
        "has_outline": True,
        "title":   {"pStyle": "000", "run_extra": []},
        "source":  {"pStyle": "000", "sz": "24"},
        "reading": {"pPr": {"spacing": {"w:line": "320", "w:lineRule": "exact"},
                             "ind": {"w:leftChars": "136", "w:left": "1192", "w:hangingChars": "412", "w:hanging": "906"},
                             "jc": "left"},
                    "rFonts": "方正书宋_GBK", "sz": "22"},
        "verse":   {"pPr": {"spacing": {"w:line": "320", "w:lineRule": "exact"},
                             "ind": {"w:leftChars": "236", "w:left": "1361", "w:hangingChars": "412", "w:hanging": "865"},
                             "jc": "left"},
                    "rFonts": "方正书宋_GBK", "szCs": "21"},
        "verse_blank_after_each": False,
        "outline_major": {"pStyle": "21", "sz": "24"},
        "outline_minor": {"pStyle": "31", "sz": "21"},
        "blank_after_outline": {"pStyle": "31", "sz": "22"},
        "heading":  {"pStyle": "21", "spacing": {"w:line": "320", "w:lineRule": "exact"}, "jc": "center", "sz": "24"},
        "para":     {"pStyle": "31", "spacing": {"w:line": "320", "w:lineRule": "exact"},
                     "ind": {"w:left": "0", "w:firstLineChars": "200", "w:firstLine": "420"}, "sz": "21"},
        "blank_before_qa": {"spacing": {"w:line": "320", "w:lineRule": "exact"}, "rFonts": "方正书宋_GBK", "sz": "22"},
        "qa_header": {"spacing": {"w:afterLines": "50", "w:after": "156", "w:line": "320", "w:lineRule": "exact"},
                      "rFonts": "方正楷体_GBK", "bold": True, "sz": "24"},
        "qa_q":     {"spacing": {"w:line": "320", "w:lineRule": "exact"}, "rFonts": "方正书宋_GBK", "szCs": "21"},
    },
    "gospel": {  # 福音加强版
        "has_outline": False,
        "title":   {"pStyle": "000", "run_extra": []},
        "source":  {"pStyle": "000", "sz": "24"},
        "reading": {"pPr": {"spacing": {"w:line": "320", "w:lineRule": "exact"},
                             "ind": {"w:leftChars": "136", "w:left": "1192", "w:hangingChars": "412", "w:hanging": "906"},
                             "jc": "left"},
                    "rFonts": "方正书宋_GBK", "sz": "22"},
        "verse":   {"pPr": {"spacing": {"w:line": "320", "w:lineRule": "exact"},
                             "ind": {"w:leftChars": "236", "w:left": "1361", "w:hangingChars": "412", "w:hanging": "865"},
                             "jc": "left"},
                    "rFonts": "方正书宋_GBK", "szCs": "21"},
        "verse_blank_after_each": False,
        "blank_after_verses": {"pPr": {"spacing": {"w:line": "320", "w:lineRule": "exact"},
                                        "ind": {"w:leftChars": "236", "w:left": "1361", "w:hangingChars": "412", "w:hanging": "865"},
                                        "jc": "left"}, "rFonts": "方正书宋_GBK", "szCs": "21"},
        "heading": {"pStyle": "21", "jc": "center"},
        "para":    {"pStyle": "31", "ind": {"w:left": "0", "w:firstLineChars": "200", "w:firstLine": "480"}},
        "blank_before_qa": {"spacing": {"w:line": "360", "w:lineRule": "exact"}, "rFonts": "方正书宋_GBK", "sz": "24"},
        "qa_header": {"spacing": {"w:afterLines": "50", "w:after": "156", "w:line": "360", "w:lineRule": "exact"},
                      "rFonts": "方正楷体_GBK", "bold": True, "sz": "24"},
        "qa_q":    {"spacing": {"w:line": "360", "w:lineRule": "exact"}, "rFonts": "方正书宋_GBK", "sz": "24"},
    },
    "life": {  # 生命加强版（与福音版结构相同，仅内容规则不同，样式规格一致）
        "has_outline": False,
        "title":   {"pStyle": "000", "run_extra": []},
        "source":  {"pStyle": "000", "sz": "24"},
        "reading": {"pPr": {"spacing": {"w:line": "320", "w:lineRule": "exact"},
                             "ind": {"w:leftChars": "136", "w:left": "1192", "w:hangingChars": "412", "w:hanging": "906"},
                             "jc": "left"},
                    "rFonts": "方正书宋_GBK", "sz": "22"},
        "verse":   {"pPr": {"spacing": {"w:line": "320", "w:lineRule": "exact"},
                             "ind": {"w:leftChars": "236", "w:left": "1361", "w:hangingChars": "412", "w:hanging": "865"},
                             "jc": "left"},
                    "rFonts": "方正书宋_GBK", "szCs": "21"},
        "verse_blank_after_each": False,
        "blank_after_verses": {"pPr": {"spacing": {"w:line": "320", "w:lineRule": "exact"},
                                        "ind": {"w:leftChars": "236", "w:left": "1361", "w:hangingChars": "412", "w:hanging": "865"},
                                        "jc": "left"}, "rFonts": "方正书宋_GBK", "szCs": "21"},
        "heading": {"pStyle": "21", "jc": "center"},
        "para":    {"pStyle": "31", "ind": {"w:left": "0", "w:firstLineChars": "200", "w:firstLine": "480"}},
        "blank_before_qa": {"spacing": {"w:line": "360", "w:lineRule": "exact"}, "rFonts": "方正书宋_GBK", "sz": "24"},
        "qa_header": {"spacing": {"w:afterLines": "50", "w:after": "156", "w:line": "360", "w:lineRule": "exact"},
                      "rFonts": "方正楷体_GBK", "bold": True, "sz": "24"},
        "qa_q":    {"spacing": {"w:line": "360", "w:lineRule": "exact"}, "rFonts": "方正书宋_GBK", "sz": "24"},
    },
    "elderly": {  # 年长放大版
        "has_outline": False,
        "title":   {"pStyle": "000", "spacing": {"w:line": "440", "w:lineRule": "exact"}, "sz": "40"},
        "source":  {"pStyle": "000", "spacing": {"w:afterLines": "100", "w:after": "312", "w:line": "440", "w:lineRule": "exact"}, "sz": "32"},
        "reading": {"pPr": {"spacing": {"w:after": "120", "w:line": "440", "w:lineRule": "exact"},
                             "ind": {"w:leftChars": "136", "w:left": "1769", "w:hangingChars": "412", "w:hanging": "1483"},
                             "jc": "left"},
                    "rFonts": "方正书宋_GBK", "sz": "36"},
        "verse":   {"pPr": {"spacing": {"w:line": "440", "w:lineRule": "exact"},
                             "ind": {"w:leftChars": "236", "w:left": "1814", "w:hangingChars": "412", "w:hanging": "1318"},
                             "jc": "left"},
                    "rFonts": "方正书宋_GBK", "sz": "32"},
        "verse_blank_after_each": True,  # 每节经文后面都插入一个空段落
        "heading": {"pStyle": "21", "spacing": {"w:line": "480", "w:lineRule": "exact"}, "jc": "center", "sz": "36"},
        "para":    {"pStyle": "31", "spacing": {"w:line": "480", "w:lineRule": "exact"},
                    "ind": {"w:left": "0", "w:firstLineChars": "200", "w:firstLine": "640"}, "sz": "32"},
        "blank_before_qa": {"pStyle": "31", "spacing": {"w:line": "440", "w:lineRule": "exact"},
                             "ind": {"w:left": "566", "w:hangingChars": "236", "w:hanging": "566"}},
        "qa_header": {"spacing": {"w:afterLines": "50", "w:after": "156", "w:line": "440", "w:lineRule": "exact"},
                      "rFonts": "方正楷体_GBK", "bold": True, "sz": "36"},
        "qa_q":    {"spacing": {"w:line": "440", "w:lineRule": "exact"}, "rFonts": "方正书宋_GBK", "sz": "32"},
    },
}

VERSION_TEMPLATE_FILES = {
    "truth": "真理加强版.docx",
    "gospel": "福音加强版.docx",
    "life": "生命加强版.docx",
    "elderly": "年长放大版.docx",
}


# ---------------------------------------------------------------------------
# 段落构建工具函数
# ---------------------------------------------------------------------------

def _make_ppr(spec_pPr=None, pStyle=None, spacing=None, ind=None, jc=None, rPr_sz=None):
    pPr = etree.Element(W("pPr"))
    if pStyle:
        el = etree.SubElement(pPr, W("pStyle"))
        el.set(W("val"), pStyle)
    src = spec_pPr or {}
    spacing = spacing or src.get("spacing")
    ind = ind or src.get("ind")
    jc = jc if jc is not None else src.get("jc")
    if spacing:
        el = etree.SubElement(pPr, W("spacing"))
        for k, v in spacing.items():
            el.set(f"{{{W_NS}}}{k.split(':')[1]}" if ":" in k else k, v)
    if ind:
        el = etree.SubElement(pPr, W("ind"))
        for k, v in ind.items():
            el.set(f"{{{W_NS}}}{k.split(':')[1]}" if ":" in k else k, v)
    if jc:
        el = etree.SubElement(pPr, W("jc"))
        el.set(W("val"), jc)
    if rPr_sz:
        rpr = etree.SubElement(pPr, W("rPr"))
        sz_el = etree.SubElement(rpr, W("sz"))
        sz_el.set(W("val"), rPr_sz)
        szcs_el = etree.SubElement(rpr, W("szCs"))
        szcs_el.set(W("val"), rPr_sz)
    return pPr


def _make_run(text, rFonts=None, sz=None, szCs=None, bold=False, hint_eastasia=True):
    r = etree.Element(W("r"))
    rpr = etree.SubElement(r, W("rPr"))
    actual_font = rFonts or DEFAULT_FALLBACK_FONT  # 不再允许留空
    el = etree.SubElement(rpr, W("rFonts"))
    el.set(W("ascii"), actual_font)
    el.set(W("eastAsia"), actual_font)
    el.set(W("hAnsi"), actual_font)
    if hint_eastasia:
        el.set(W("hint"), "eastAsia")
    if bold:
        etree.SubElement(rpr, W("b"))
        etree.SubElement(rpr, W("bCs"))
    if sz:
        el = etree.SubElement(rpr, W("sz"))
        el.set(W("val"), sz)
    if szCs:
        el = etree.SubElement(rpr, W("szCs"))
        el.set(W("val"), szCs)
    elif sz:
        el = etree.SubElement(rpr, W("szCs"))
        el.set(W("val"), sz)
    t = etree.SubElement(r, W("t"))
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    return r


def _para(children_runs, ppr=None):
    p = etree.Element(W("p"))
    if ppr is not None:
        p.append(ppr)
    for r in children_runs:
        p.append(r)
    return p


def _role_para(role_key, spec, text=None, tab_prefix=None, extra_runs=None):
    """按 STYLE_SPEC 里某个角色的规格，构建一个完整段落。"""
    role = spec[role_key]
    pStyle = role.get("pStyle")
    spacing = role.get("spacing") or (role.get("pPr") or {}).get("spacing")
    ind = role.get("ind") or (role.get("pPr") or {}).get("ind")
    jc = role.get("jc") or (role.get("pPr") or {}).get("jc")
    rpr_sz = role.get("pPr_sz")
    ppr = _make_ppr(pStyle=pStyle, spacing=spacing, ind=ind, jc=jc, rPr_sz=rpr_sz)
    runs = []
    if text is not None:
        rFonts = role.get("rFonts")
        sz = role.get("sz")
        szCs = role.get("szCs")
        bold = role.get("bold", False)
        if tab_prefix:
            runs.append(_make_run(tab_prefix, rFonts=rFonts, sz=sz, szCs=szCs, bold=bold))
            tab_r = etree.Element(W("r"))
            rpr = etree.SubElement(tab_r, W("rPr"))
            actual_font = rFonts or DEFAULT_FALLBACK_FONT
            el = etree.SubElement(rpr, W("rFonts"))
            el.set(W("ascii"), actual_font)
            el.set(W("eastAsia"), actual_font)
            el.set(W("hAnsi"), actual_font)
            el.set(W("hint"), "eastAsia")
            if sz:
                el = etree.SubElement(rpr, W("sz")); el.set(W("val"), sz)
            if szCs or sz:
                el = etree.SubElement(rpr, W("szCs")); el.set(W("val"), szCs or sz)
            etree.SubElement(tab_r, W("tab"))
            runs.append(tab_r)
            runs.append(_make_run(text, rFonts=rFonts, sz=sz, szCs=szCs, bold=bold))
        else:
            runs.append(_make_run(text, rFonts=rFonts, sz=sz, szCs=szCs, bold=bold))
    if extra_runs:
        runs.extend(extra_runs)
    return _para(runs, ppr=ppr)


def _blank_para(role_key, spec):
    role = spec[role_key]
    pStyle = role.get("pStyle")
    spacing = role.get("spacing") or (role.get("pPr") or {}).get("spacing")
    ind = role.get("ind") or (role.get("pPr") or {}).get("ind")
    jc = role.get("jc") or (role.get("pPr") or {}).get("jc")
    ppr = _make_ppr(pStyle=pStyle, spacing=spacing, ind=ind, jc=jc)
    return _para([], ppr=ppr)


CN_MAJOR = "壹贰叁肆伍陆柒捌玖拾"
CN_MINOR = "一二三四五六七八九十"


def build_body_paragraphs(version_key, unified_fields, version_data):
    spec = STYLE_SPEC[version_key]
    paras = []

    # 1. 标题
    paras.append(_role_para("title", spec, text=unified_fields["title"]))
    # 2. 整体出处
    paras.append(_role_para("source", spec, text=unified_fields["overall_source"]))

    # 3. 读经行
    verses = unified_fields["verses"]
    verse_display = verses[-1].get("display") or verses[0].get("display") or verses[0].get("ref_gb", "")
    hymn = unified_fields.get("hymn")
    if hymn:
        hymn_text = f"诗歌：{hymn['source']}{hymn['no']}"
    else:
        # 正常情况不应该走到：Step1 已要求必须给出有效诗歌，重试用尽会直接报错。
        # 若仍出现，说明诗歌重试机制失效或上游传入了残缺 unified_fields，需要排查。
        hymn_text = "诗歌：（未找到贴合主题的推荐）"
    reading_text = f"读经：{verse_display}\u3000\u3000{hymn_text}"
    paras.append(_role_para("reading", spec, text=reading_text))

    # 4. 逐节经文
    for v in verses:
        ref = v.get("ref_gb") or v.get("display") or ""
        vtext = f"{ref}\u3000{v['text']}"
        paras.append(_role_para("verse", spec, text=vtext))
        if spec.get("verse_blank_after_each"):
            paras.append(_blank_para("verse", spec))
    if spec.get("blank_after_verses") and not spec.get("verse_blank_after_each"):
        paras.append(_blank_para("blank_after_verses", spec))

    # 5. 鸟瞰纲目（仅真理版）
    if spec["has_outline"] and version_data.get("outline"):
        outline = version_data["outline"]
        for i, mp in enumerate(outline["major_points"]):
            major_num = CN_MAJOR[i] if i < len(CN_MAJOR) else str(i + 1)
            paras.append(_role_para("outline_major", spec, text=mp["text"], tab_prefix=major_num))
            for j, minp in enumerate(mp.get("minor_points", [])):
                minor_num = CN_MINOR[j] if j < len(CN_MINOR) else str(j + 1)
                paras.append(_role_para("outline_minor", spec, text=minp["text"], tab_prefix=minor_num))
        paras.append(_blank_para("blank_after_outline", spec))

    # 6. 各篇小标题 + 段落（source_line 拼接在该篇最后一段正文末尾，不单独成段——
    #    这是从真实模版逆向验证过的规则：模版里"（XX生命读经，第X篇）"直接跟在
    #    最后一段正文文字后面，中间没有换行/没有独立段落）
    sections = version_data.get("sections", [])
    for sec in sections:
        subsections = sec.get("subsections", [])
        source_line = sec.get("source_line", "")
        for si, sub in enumerate(subsections):
            paras.append(_role_para("heading", spec, text=sub["heading"]))
            sub_paragraphs = sub.get("paragraphs", [])
            is_last_sub = si == len(subsections) - 1
            for pi, p in enumerate(sub_paragraphs):
                text = p["text"]
                is_last_para_of_section = is_last_sub and pi == len(sub_paragraphs) - 1
                if is_last_para_of_section and source_line:
                    text = text + source_line
                paras.append(_role_para("para", spec, text=text))

    # 7. 彼此问互相答
    paras.append(_blank_para("blank_before_qa", spec))
    paras.append(_role_para("qa_header", spec, text="彼此问互相答："))
    for i, qa in enumerate(version_data.get("qa", []), 1):
        paras.append(_role_para("qa_q", spec, text=f"{i}. {qa['question']}"))

    return paras


def generate_docx(version_key, unified_fields, version_data, template_path, output_path):
    """
    读取模版 docx，替换 body 内容（保留 sectPr / styles / footer / theme 等一切基础设施），
    输出新的 docx 文件。
    """
    template_path = Path(template_path)
    output_path = Path(output_path)

    tmp_dir = output_path.parent / f".__build_{version_key}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    with zipfile.ZipFile(template_path, "r") as zf:
        zf.extractall(tmp_dir)

    doc_xml_path = tmp_dir / "word" / "document.xml"
    tree = etree.parse(str(doc_xml_path))
    root = tree.getroot()
    body = root.find("w:body", NSMAP)

    # 保留最后的 sectPr（页面设置），删除所有 w:p
    sectPr = body.find("w:sectPr", NSMAP)
    for p in body.findall("w:p", NSMAP):
        body.remove(p)

    new_paras = build_body_paragraphs(version_key, unified_fields, version_data)
    if sectPr is not None:
        body.remove(sectPr)
        for p in new_paras:
            body.append(p)
        body.append(sectPr)
    else:
        for p in new_paras:
            body.append(p)

    _write_xml_with_double_quote_declaration(tree, doc_xml_path)

    # 重新打包成 docx
    if output_path.exists():
        output_path.unlink()
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in tmp_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(tmp_dir))

    shutil.rmtree(tmp_dir)
    return output_path
