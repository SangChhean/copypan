"""
小排生命读经材料制作 - 边框功能
把边框图片以"衬于文字下方、铺满整页、锁定位置"的方式插入 docx 的页眉。
纯 Python 实现（zipfile + lxml），不依赖 Word/pywin32，可在 Linux 服务器上运行。
"""
import random
import shutil
import zipfile
from pathlib import Path
from lxml import etree

from back_cn.roundtable.docx_builder import (
    _repack_docx,
    _write_xml_with_double_quote_declaration,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

# 每个版本对应的边框图，以及是否需要额外的页脚间距调整（真理版页码之前被边框图案盖住，单独下移页脚）
BORDER_CONFIG = {
    "truth":   {"image": "真理加强版.jpeg", "footer_override": 1080},
    "gospel":  {"image": "福音加强版.jpeg", "footer_override": None},
    "life":    {"image": "生命加强版.jpeg", "footer_override": None},
    "elderly": {"image": "年长放大版.jpeg", "footer_override": None},
}

HEADER1_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="{w}" xmlns:wp="{wp}" xmlns:a="{a}" xmlns:pic="{pic}" xmlns:r="{r}">
<w:p><w:pPr><w:pStyle w:val="a3"/></w:pPr><w:r><w:rPr><w:noProof/></w:rPr>
<w:drawing>
<wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="251658240" behindDoc="1" locked="1" layoutInCell="1" allowOverlap="1">
<wp:simplePos x="0" y="0"/>
<wp:positionH relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionH>
<wp:positionV relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionV>
<wp:extent cx="{cx}" cy="{cy}"/>
<wp:effectExtent l="0" t="0" r="0" b="0"/>
<wp:wrapNone/>
<wp:docPr id="{docpr_id}" name="边框底图" descr="边框装饰图片，不可编辑内容" title="边框"/>
<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic><pic:nvPicPr><pic:cNvPr id="{docpr_id}" name="边框底图"/>
<pic:cNvPicPr><a:picLocks noChangeAspect="1" noMove="1" noResize="1" noSelect="1"/></pic:cNvPicPr></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="rIdBorderImg"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>
</a:graphicData></a:graphic>
</wp:anchor>
</w:drawing>
</w:r>
</w:p>
</w:hdr>""".format(
    w=W_NS,
    wp=WP_NS,
    a=A_NS,
    pic=PIC_NS,
    r=R_NS,
    cx="{cx}",
    cy="{cy}",
    docpr_id="{docpr_id}",
)

HEADER_RELS_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{rels}"><Relationship Id="rIdBorderImg" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{image_name}"/></Relationships>""".format(rels=RELS_NS, image_name="{image_name}")


def _generate_docpr_id() -> int:
    """模拟真实Word生成的docPr id风格（大随机数），避免用固定小数字可能带来的潜在ID冲突风险"""
    return random.randint(100000000, 2000000000)


def _validate_docx_openable(docx_path: Path) -> None:
    """
    用 python-docx 尝试打开生成的文件，做一次基本的健全性检查。
    这不能100%代表Word的严格校验行为，但至少能提前发现一些明显的结构性错误，
    比python-docx都打不开的文件，Word大概率也会有问题。
    """
    import docx

    try:
        docx.Document(str(docx_path))
    except Exception as e:
        raise RuntimeError(f"生成的docx文件校验失败，可能存在结构性问题: {e}") from e


def add_border(docx_path: Path, border_image_path: Path, footer_override: int | None = None) -> None:
    """
    原地修改 docx_path，插入边框图片。
    - 边框图衬于文字下方、铺满整页（页面尺寸由原文档 pgSz 自动读取，不写死）
    - 锁定位置，不可选中/移动/缩放（noSelect/noMove/noResize + locked="1"）
    - footer_override：如果传入，覆盖页脚距离页面底边的距离（twips），用于避免页码被边框图案压住
    """
    tmp_dir = docx_path.parent / f".__border_tmp_{docx_path.stem}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    with zipfile.ZipFile(docx_path, "r") as zf:
        zf.extractall(tmp_dir)

    # 1. 读取页面尺寸（EMU = twips * 635）
    doc_xml_path = tmp_dir / "word" / "document.xml"
    doc_tree = etree.parse(str(doc_xml_path))
    doc_root = doc_tree.getroot()
    nsmap = {"w": W_NS}
    sectPr = doc_root.find(".//w:body/w:sectPr", nsmap)
    if sectPr is None:
        raise RuntimeError("document.xml 中找不到 sectPr，无法获取页面尺寸")
    pgSz = sectPr.find("w:pgSz", nsmap)
    pg_w_twips = int(pgSz.get(f"{{{W_NS}}}w"))
    pg_h_twips = int(pgSz.get(f"{{{W_NS}}}h"))
    cx = pg_w_twips * 635  # twips -> EMU
    cy = pg_h_twips * 635

    # 2. 拷贝边框图片进 media 目录
    media_dir = tmp_dir / "word" / "media"
    media_dir.mkdir(exist_ok=True)
    image_name = "border_" + border_image_path.name
    shutil.copy2(border_image_path, media_dir / image_name)

    # 3. 写 header1.xml（如果已存在同名文件，说明这个 docx 已经加过边框，直接覆盖）
    docpr_id = _generate_docpr_id()
    header_xml_content = (
        HEADER1_XML_TEMPLATE.replace("{cx}", str(cx))
        .replace("{cy}", str(cy))
        .replace("{docpr_id}", str(docpr_id))
    )
    (tmp_dir / "word" / "header1.xml").write_text(header_xml_content, encoding="utf-8")

    # 4. 写 header1.xml.rels
    rels_dir = tmp_dir / "word" / "_rels"
    rels_dir.mkdir(exist_ok=True)
    header_rels_content = HEADER_RELS_TEMPLATE.replace("{image_name}", image_name)
    (rels_dir / "header1.xml.rels").write_text(header_rels_content, encoding="utf-8")

    # 5. 更新 [Content_Types].xml：确保 jpeg 默认类型 + header1.xml 的 Override 都存在
    ct_path = tmp_dir / "[Content_Types].xml"
    ct_tree = etree.parse(str(ct_path))
    ct_root = ct_tree.getroot()
    ct_nsmap = {"ct": CT_NS}

    has_jpeg_default = any(
        el.get("Extension") == "jpeg" for el in ct_root.findall("ct:Default", ct_nsmap)
    )
    if not has_jpeg_default:
        default_el = etree.SubElement(ct_root, f"{{{CT_NS}}}Default")
        default_el.set("Extension", "jpeg")
        default_el.set("ContentType", "image/jpeg")
        ct_root.insert(0, default_el)

    has_header1_override = any(
        el.get("PartName") == "/word/header1.xml" for el in ct_root.findall("ct:Override", ct_nsmap)
    )
    if not has_header1_override:
        override_el = etree.SubElement(ct_root, f"{{{CT_NS}}}Override")
        override_el.set("PartName", "/word/header1.xml")
        override_el.set(
            "ContentType",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml",
        )
    _write_xml_with_double_quote_declaration(ct_tree, ct_path)

    # 6. 更新 word/_rels/document.xml.rels：注册 header1.xml 关系（如果已存在同类型关系，先复用，不重复添加）
    doc_rels_path = rels_dir / "document.xml.rels"
    doc_rels_tree = etree.parse(str(doc_rels_path))
    doc_rels_root = doc_rels_tree.getroot()
    rels_nsmap = {"r": RELS_NS}

    existing_header_rel = None
    for rel in doc_rels_root.findall("r:Relationship", rels_nsmap):
        if rel.get("Target") == "header1.xml":
            existing_header_rel = rel
            break

    if existing_header_rel is not None:
        header_rid = existing_header_rel.get("Id")
    else:
        existing_ids = [rel.get("Id") for rel in doc_rels_root.findall("r:Relationship", rels_nsmap)]
        existing_nums = [int(i.replace("rId", "")) for i in existing_ids if i and i.startswith("rId") and i[3:].isdigit()]
        next_num = (max(existing_nums) + 1) if existing_nums else 1
        header_rid = f"rId{next_num}"
        rel_el = etree.SubElement(doc_rels_root, f"{{{RELS_NS}}}Relationship")
        rel_el.set("Id", header_rid)
        rel_el.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header")
        rel_el.set("Target", "header1.xml")
        _write_xml_with_double_quote_declaration(doc_rels_tree, doc_rels_path)

    # 7. 更新 document.xml 的 sectPr：加 headerReference（如果已存在则不重复加），并按需覆盖页脚距离
    has_header_ref = sectPr.find('w:headerReference[@w:type="default"]', nsmap) is not None
    if not has_header_ref:
        header_ref_el = etree.Element(f"{{{W_NS}}}headerReference")
        header_ref_el.set(f"{{{W_NS}}}type", "default")
        header_ref_el.set(f"{{{R_NS}}}id", header_rid)
        sectPr.insert(0, header_ref_el)

    if footer_override is not None:
        pgMar = sectPr.find("w:pgMar", nsmap)
        if pgMar is not None:
            pgMar.set(f"{{{W_NS}}}footer", str(footer_override))

    _write_xml_with_double_quote_declaration(doc_tree, doc_xml_path)

    # 8. 重新打包
    _repack_docx(tmp_dir, docx_path)

    shutil.rmtree(tmp_dir)

    # 9. 最终校验：python-docx 能打开，才算结构基本健全
    _validate_docx_openable(docx_path)


def add_border_for_version(docx_path: Path, version_key: str, borders_dir: Path) -> None:
    """按版本自动选用对应边框图，真理版自动带上页脚间距修正。"""
    cfg = BORDER_CONFIG[version_key]
    border_image_path = borders_dir / cfg["image"]
    if not border_image_path.exists():
        raise FileNotFoundError(f"边框图片未找到：{border_image_path}")
    add_border(docx_path, border_image_path, footer_override=cfg["footer_override"])
