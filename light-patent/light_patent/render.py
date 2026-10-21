"""P3 渲染层：申报副本（draft/filing/*.md）→ DOCX 申报文件。

MD 仍是工作与申报的文本真相（LP-04 剥离链不变）；本模块只把
已剥离、已洁净检查的申报副本渲染成 Word 文件，供人工递交前
复核与打印。渲染前对源 MD 复跑过程词扫描（与 strip 同词表），
命中即拒渲染——渲染层不许成为过程标记绕过洁净门的旁路。

渲染后机械核验（render_docx 自带）：用 python-docx 回读产物，
逐段比对源 MD 解析出的段落清单（标题/节标题/正文/权要编号集
全等）、过程词零命中、页面设置与渲染规程一致。核验结果连同
源/产物哈希落 draft/filing/render_report.yaml。

渲染规程（本包定版，非官方逐字规范；递交前仍须按当期 CNIPA
电子申请客户端口径复核）：A4；页边距上 25mm / 左 25mm /
下 20mm / 右 20mm；页眉居中为文件名称，页脚居中为页码域；
正文宋体 14pt、1.5 倍行距；文件名称黑体 16pt 居中；说明书
节标题宋体 14pt 加粗。发明名称行紧随文件名称之后。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .project import PatentError, case_path, load_case
from .util import dump_yaml, read_text, sha256_file, sha256_text, today

# ---------------------------------------------------------------- 渲染规程

PAGE_WIDTH_MM = 210
PAGE_HEIGHT_MM = 297
MARGIN_MM = {"top": 25, "left": 25, "bottom": 20, "right": 20}
BODY_FONT = "宋体"
BODY_SIZE_PT = 14
TITLE_FONT = "黑体"
TITLE_SIZE_PT = 16
LINE_SPACING = 1.5

#: 申报三件与渲染文件名（docx 落 draft/filing/ 下同名 .docx）。
FILING_DOCS = (
    ("claims_md", "claims.md", "权利要求书.docx", "权利要求书"),
    ("specification_md", "specification.md", "说明书.docx", "说明书"),
    ("abstract_md", "abstract.md", "说明书摘要.docx", "说明书摘要"),
)

_CLAIM_LINE_RE = re.compile(r"^(\d+)\.\s*(.*)$")


def parse_filing_md(text: str) -> list:
    """把申报副本 MD 解析成段落清单（渲染与核验共用同一解析）。

    返回 [{role, text}]：role ∈ title（# 一级标题）/ invention
    （发明名称行）/ section（## 节标题）/ claim（权要编号行）/
    body（其余正文行）。空行与 HTML 批注不入段落清单。
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    paras = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            paras.append({"role": "section", "text": line[3:].strip()})
        elif line.startswith("# "):
            paras.append({"role": "title",
                          "text": line[2:].strip().replace("（工作副本）", "")})
        elif line.startswith("发明名称："):
            paras.append({"role": "invention", "text": line})
        else:
            m = _CLAIM_LINE_RE.match(line)
            if m and paras and any(p["role"] == "title" and
                                   "权利要求书" in p["text"] for p in paras):
                paras.append({"role": "claim", "text": line,
                              "claim_no": int(m.group(1))})
            else:
                paras.append({"role": "body", "text": line})
    return paras


def _expected_paragraph_texts(paras: list) -> list:
    return [p["text"] for p in paras]


def _set_run_font(run, name: str, size_pt: int, bold: bool = False) -> None:
    from docx.shared import Pt
    from docx.oxml.ns import qn

    run.font.name = name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)


def _add_page_number_footer(section) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    para = section.footer.paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run_el = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "1"
    run_el.append(t)
    fld.append(run_el)
    para._p.append(fld)


def _build_docx(paras: list, doc_label: str, dest: Path) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Mm

    doc = Document()
    section = doc.sections[0]
    section.page_width = Mm(PAGE_WIDTH_MM)
    section.page_height = Mm(PAGE_HEIGHT_MM)
    section.top_margin = Mm(MARGIN_MM["top"])
    section.left_margin = Mm(MARGIN_MM["left"])
    section.bottom_margin = Mm(MARGIN_MM["bottom"])
    section.right_margin = Mm(MARGIN_MM["right"])

    header_para = section.header.paragraphs[0]
    header_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_run_font(header_para.add_run(doc_label), BODY_FONT, 10)
    _add_page_number_footer(section)

    for p in paras:
        if p["role"] == "title":
            para = doc.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _set_run_font(para.add_run(p["text"]), TITLE_FONT, TITLE_SIZE_PT)
        elif p["role"] == "section":
            para = doc.add_paragraph()
            para.paragraph_format.line_spacing = LINE_SPACING
            _set_run_font(para.add_run(p["text"]), BODY_FONT, BODY_SIZE_PT,
                          bold=True)
        elif p["role"] == "invention":
            para = doc.add_paragraph()
            para.paragraph_format.line_spacing = LINE_SPACING
            _set_run_font(para.add_run(p["text"]), BODY_FONT, BODY_SIZE_PT)
        else:  # claim / body
            para = doc.add_paragraph()
            para.paragraph_format.line_spacing = LINE_SPACING
            _set_run_font(para.add_run(p["text"]), BODY_FONT, BODY_SIZE_PT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dest))


def verify_docx(dest: Path, paras: list) -> dict:
    """回读核验：段落文本全等 + 权要编号集 + 过程词零命中 + 页面设置。"""
    from docx import Document

    doc = Document(str(dest))
    got = [p.text for p in doc.paragraphs if p.text.strip()]
    expected = _expected_paragraph_texts(paras)
    problems = []
    if got != expected:
        for i, (g, e) in enumerate(zip(got, expected)):
            if g != e:
                problems.append(f"第 {i + 1} 段不一致：产物 {g[:30]!r}… "
                                f"vs 源 {e[:30]!r}…")
                break
        if len(got) != len(expected):
            problems.append(f"段落数不一致：产物 {len(got)} vs 源 {len(expected)}")
    claim_nos = [p["claim_no"] for p in paras if p["role"] == "claim"]
    if claim_nos:
        doc_claim_nos = []
        for t in got:
            m = _CLAIM_LINE_RE.match(t.strip())
            if m:
                doc_claim_nos.append(int(m.group(1)))
        if doc_claim_nos != claim_nos:
            problems.append(f"权要编号集不一致：产物 {doc_claim_nos} vs 源 {claim_nos}")
    full = "\n".join(got)
    hits = [t for t in schema.PROCESS_TOKENS if t in full]
    if hits:
        problems.append(f"产物含过程词（LP-04 洁净门）：{hits}")
    sec = doc.sections[0]
    from docx.shared import Mm
    if abs(sec.page_width - Mm(PAGE_WIDTH_MM)) > Mm(1) \
            or abs(sec.page_height - Mm(PAGE_HEIGHT_MM)) > Mm(1):
        problems.append("页面尺寸非 A4（与渲染规程不符）")
    return {"ok": not problems, "problems": problems,
            "paragraphs": len(got),
            "claims": len(claim_nos)}


def render_docx(root) -> dict:
    """把 draft/filing/ 三件申报副本渲染为 DOCX 并逐件核验。

    前置：strip 已生成申报副本。源 MD 过程词复扫命中即整批拒
    渲染（LP-04）；任一件缺失即点名报错，不许部分静默跳过。
    """
    root = Path(root)
    case = load_case(root)
    try:
        import docx  # noqa: F401
    except ImportError:
        raise PatentError([
            "缺渲染依赖 python-docx：先在包环境安装 python-docx>=1.0"
            "（pyproject 的 render 可选依赖组）"])
    filing_dir = case_path(root, "filing_dir")
    report = {"kind": "light-patent/render-report",
              "case_id": case["case_id"], "rendered_at": today(),
              "profile": {"page": "A4", "margins_mm": MARGIN_MM,
                          "body_font": f"{BODY_FONT} {BODY_SIZE_PT}pt",
                          "line_spacing": LINE_SPACING},
              "files": []}
    gaps = []
    for key, md_name, docx_name, label in FILING_DOCS:
        src = filing_dir / md_name
        if not src.exists():
            gaps.append(f"申报副本 {md_name} 不存在：先跑 strip 生成申报副本")
            continue
        text = read_text(src)
        hits = [t for t in schema.PROCESS_TOKENS if t in text]
        if hits:
            gaps.append(f"{md_name} 过程词复扫命中 {hits}：申报副本不洁净，"
                        "拒渲染（LP-04），重跑 strip 并处理命中项")
            continue
        paras = parse_filing_md(text)
        if not paras:
            gaps.append(f"{md_name} 解析出零段落：源文件为空或形态异常")
            continue
        dest = filing_dir / docx_name
        _build_docx(paras, label, dest)
        verdict = verify_docx(dest, paras)
        report["files"].append({
            "source": md_name, "docx": docx_name, "label": label,
            "source_sha256": sha256_text(text),
            "docx_sha256": sha256_file(dest),
            "verify": verdict,
        })
        if not verdict["ok"]:
            gaps.extend(f"{docx_name} 核验未过：{p}"
                        for p in verdict["problems"])
    if gaps:
        raise PatentError(gaps)
    dump_yaml(filing_dir / "render_report.yaml", report)
    return {"files": len(report["files"]),
            "docx": [f["docx"] for f in report["files"]],
            "all_verified": all(f["verify"]["ok"] for f in report["files"]),
            "report": "draft/filing/render_report.yaml"}
