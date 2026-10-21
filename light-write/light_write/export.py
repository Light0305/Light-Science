"""投稿文件导出渲染链（pandoc）。

定位：稿件包（逐节 MD + 登记文件）→ 投稿成品（DOCX / LaTeX / PDF）。
v1 只出 MD 稿件包的缺口在此补齐（PLAN §5.3 P0、V1.1-BACKLOG §二）。

纪律：
- 源稿是权威：导出只做机械变换（标记剥离 / 图表落位 / 引用键归一 /
  摘要提升），不改写内容；变换逐项留痕于 export_record.json。
- 渲染后机械复核（与审计门同源口径）：数字账值逐行在场、引用键集
  合一致、禁用词表在渲染文本上重扫、占位符零残留、节标题齐全；
  任一失败逐项点名，不产出「看似成功」的记录。
- 工具缺失如实落字：pandoc / LaTeX 引擎 / SVG 转换器缺席时点名缺口
  （PANDOC_MISSING / ENGINE_MISSING / SVG_CONVERTER_MISSING），
  绝不假渲染、绝不用占位文件冒充成品。
- 产物绑 manuscript_hash：稿改即 STALE（export check 检出），与
  audit / review / disclose 的绑定口径一致。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
import zipfile
from pathlib import Path

from . import schema
from .project import FILES, load_package, manuscript_hash, section_files
from .util import dump_json, load_structured, sha256_file, utcnow

EXPORT_RECORD = "export_record.json"

_NUM_MARK_RE = re.compile(r"\[num:([A-Za-z0-9_-]+)\]")
_CLAIM_MARK_RE = re.compile(r"\[claim:([A-Za-z0-9_-]+)\]")
_FIG_MARK_RE = re.compile(r"\[fig:([A-Za-z0-9_-]+)\]")
_DIRECTIVE_RE = re.compile(r"\[directive:[^\]]*\]?")
_CITE_GROUP_RE = re.compile(r"\[([^\]]*@[^\]]*)\]")
_CITE_KEY_RE = re.compile(r"@([A-Za-z0-9_][A-Za-z0-9_:.#$%&+?<>~/~-]*)")
_NUM_TOKEN_RE = re.compile(r"[0-9][0-9.,%]*")
_PLACEHOLDER_PATTERNS = [
    "[num:", "[claim:", "[fig:", "[directive:", "[@",
    "AUTHOR_INPUT_NEEDED",
]


class ExportError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 工具发现

def find_pandoc():
    """pandoc 可执行文件：PATH 优先，其次 pypandoc 自带二进制。"""
    exe = shutil.which("pandoc")
    if exe:
        return exe
    try:
        import pypandoc

        path = pypandoc.get_pandoc_path()
        if path and Path(path).exists():
            return str(path)
    except Exception:
        pass
    return None


def find_latex_engine():
    for name in ("xelatex", "pdflatex", "lualatex"):
        exe = shutil.which(name)
        if exe:
            return exe
    return None


def find_svg_converter():
    for name in ("rsvg-convert", "inkscape"):
        exe = shutil.which(name)
        if exe:
            return (name, exe)
    try:
        import cairosvg  # noqa: F401

        return ("cairosvg", "python-module:cairosvg")
    except Exception:
        return None


def _tool_version(exe, *args):
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True,
                             timeout=30)
        text = (out.stdout or out.stderr or "").strip().splitlines()
        return text[0].strip() if text else None
    except Exception:
        return None


def _run(cmd, cwd=None, timeout=600):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)
    return {
        "cmd": [str(c) for c in cmd],
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


# ---------------------------------------------------------------- 导出配置

def default_profile():
    return {
        "label": "generic",
        "source": "built-in default (no template record / library entry)",
        "journal_name": None,
        "documentclass": "article",
        "classoptions": [],
        "citation_mode": "citeproc",
        "bst_name": None,
        "csl_id": None,
        "csl_file": None,
        "reference_doc": None,
        "class_files": [],
        "template_file": None,
    }


def profile_from_record(record):
    """模板变量映射：核查记录 B/E 组 → pandoc 变量与引用模式。

    B.latex_class → documentclass；B.options_axis（字典取其值、列表
    直用）→ classoptions；B.citation_package → citation_mode
    （natbib / biblatex / citeproc，其余值落 citeproc 并在映射留痕）；
    E.bst_name → biblio-style；E.csl_id 只登记 ID（样式文件由模板库
    实物解析，包内不打包 CSL 生态）。
    """
    prof = default_profile()
    if not record:
        return prof
    group_a = record.get("A") or {}
    group_b = record.get("B") or {}
    group_e = record.get("E") or {}
    prof["journal_name"] = group_a.get("journal_name")
    prof["label"] = _profile_label(
        group_b.get("latex_class") or group_a.get("journal_name")
        or "record")
    prof["source"] = ("package template_record.json "
                      f"({group_a.get('record_id')})")
    if group_b.get("latex_class"):
        prof["documentclass"] = str(group_b["latex_class"])
    options = group_b.get("options_axis")
    if isinstance(options, dict):
        prof["classoptions"] = [str(v) for v in options.values()
                                if v is not None]
    elif isinstance(options, list):
        prof["classoptions"] = [str(v) for v in options]
    package = str(group_b.get("citation_package") or "").lower()
    if package in ("natbib", "biblatex"):
        prof["citation_mode"] = package
    elif package:
        prof["citation_mode"] = "citeproc"
        prof["citation_package_raw"] = package
    prof["bst_name"] = group_e.get("bst_name")
    prof["csl_id"] = group_e.get("csl_id")
    return prof


def _profile_label(raw):
    text = unicodedata.normalize("NFKD", str(raw or "export"))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "export"


def load_library_profile(template_id, library_root):
    """从模板库登记（registry.jsonl）按 id 取 export_profile。

    模板库是独立于包的本地资产（libraries/journal-templates）；
    registry 行的 redistribution 决定实物可用面：prohibited 的条目
    只许规程登记，export_profile 不得出实物路径（库校验已拦，
    此处再验一次，fail-closed）。
    """
    root = Path(library_root)
    registry_path = root / "registry.jsonl"
    if not registry_path.exists():
        raise ExportError([f"模板库登记不存在：{registry_path}"])
    rows = load_structured(registry_path)
    for row in rows:
        if row.get("template_id") == template_id:
            prof = row.get("export_profile")
            if not prof:
                raise ExportError([
                    f"模板库条目 {template_id} 无 export_profile"
                    "（仅登记规程、无实物映射）"])
            if row.get("redistribution") == "prohibited":
                raise ExportError([
                    f"模板库条目 {template_id} 标记 prohibited"
                    "（禁止再分发），不许用于导出实物"])
            merged = default_profile()
            merged.update(prof)
            merged["source"] = (f"template library {registry_path} "
                                f"#{template_id}")
            # 相对路径按库根解析
            for key in ("csl_file", "reference_doc", "template_file"):
                if merged.get(key):
                    merged[key] = str(root / merged[key])
            merged["class_files"] = [str(root / p)
                                     for p in merged.get("class_files")
                                     or []]
            return merged
    raise ExportError([f"模板库中无条目：{template_id}"])


# ---------------------------------------------------------------- 源稿组装

def _norm_ws(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _frontiers_metadata(structured):
    """Frontiers 类的 \\def 式 frontmatter 变量（自制模板消费）。

    单位按首次出现顺序编号；通讯作者加 * 上标；通讯邮箱稿件包未
    登记时留空（类文件允许空值，不许编造邮箱）。
    """
    if not structured:
        return {}
    affiliations = []
    for a in structured:
        aff = a.get("affiliation") or ""
        if aff and aff not in affiliations:
            affiliations.append(aff)

    def marks(a):
        out = []
        aff = a.get("affiliation") or ""
        if aff:
            out.append(str(affiliations.index(aff) + 1))
        if a.get("corresponding"):
            out.append("*")
        return ",".join(out)

    parts = []
    for a in structured:
        m = marks(a)
        parts.append(a["name"] + (f"\\,$^{{{m}}}$" if m else ""))
    if len(parts) > 2:
        authors_tex = ", ".join(parts[:-1]) + " and " + parts[-1]
    else:
        authors_tex = " and ".join(parts)
    address_tex = " \\\\\n".join(
        f"$^{{{i + 1}}}${aff}" for i, aff in enumerate(affiliations))
    first = structured[0]["name"].strip().split()
    first_last = first[-1] if first else ""
    if len(structured) > 1:
        first_last += " {et~al.}"
    corr = next((a for a in structured if a.get("corresponding")), None)
    return {
        "frontiers_first_author_last": first_last,
        "frontiers_authors": authors_tex,
        "frontiers_address": address_tex,
        "frontiers_corr_author": (corr or {}).get("name", ""),
        "frontiers_corr_email": "",
    }


def _section_order(pkg):
    """节序：登记头 sections 登记序优先，缺失时文件名字典序。"""
    files = section_files(pkg["root"])
    ordered = []
    seen = set()
    for row in (pkg["manuscript"] or {}).get("sections") or []:
        name = row.get("file")
        if name in files and name not in seen:
            ordered.append((name, row.get("role")))
            seen.add(name)
    for name in sorted(files):
        if name not in seen:
            ordered.append((name, None))
    return ordered


def assemble_markdown(pkg):
    """逐节 MD → 单一投稿源（机械变换 + 逐项留痕）。

    变换：[num:N] 剥离（呈现值留原位，逐个与数字账比对）；
    [claim:C] 剥离；[@lit:<条目ID>] 按 lock 归一为 [@key]；
    独行 [fig:F] 落位为图块（图注取 figures_manifest，紧随的同文
    段落视为图注本体不重复出）；行内 [fig:F] 换 display_label；
    role=abstract 的节提升为 pandoc 摘要元数据。
    返回 (combined_md, log, gaps)。
    """
    root = pkg["root"]
    manuscript = pkg["manuscript"] or {}
    files = section_files(root)
    ledger = {r.get("num_id"): r
              for r in (pkg["numbers"] or {}).get("numbers") or []}
    figures = {r.get("figure_id"): r
               for r in (pkg["figures"] or {}).get("figures") or []}
    lock_by_entry = {}
    lock_keys = set()
    for e in (pkg["lock"] or {}).get("entries") or []:
        lock_keys.add(e.get("key"))
        if e.get("entry_id"):
            lock_by_entry[e["entry_id"]] = e.get("key")
    log = {
        "numbers": [], "claims_stripped": [], "figures_placed": [],
        "figures_intext": [], "lit_resolved": [], "cited_keys": [],
        "abstract_hoisted": None, "sections": [],
    }
    gaps = []

    def sub_numbers(text, fname):
        def repl(m):
            nid = m.group(1)
            rest = text[m.end():]
            token_m = _NUM_TOKEN_RE.match(rest.lstrip())
            row = ledger.get(nid)
            if token_m:
                # 标记后（可隔空白）紧跟数字 token = 呈现值本体：
                # 只删标记，呈现串原位保留
                log["numbers"].append({
                    "num_id": nid, "file": fname,
                    "printed_in_text": token_m.group(0),
                    "ledger_value": (row or {}).get("value_as_printed"),
                })
                return "\x00NUMKEEP\x00"
            log["numbers"].append({
                "num_id": nid, "file": fname, "printed_in_text": None,
                "ledger_value": (row or {}).get("value_as_printed")})
            return "\x00NUMFILL:" + nid + "\x00"

        out = _NUM_MARK_RE.sub(repl, text)
        # NUMKEEP：删标记与标记后空白，保留呈现 token 本体
        out = out.replace("\x00NUMKEEP\x00", "")
        # 标记与 token 之间的空白在 sub 时未动：NUMKEEP 占位替换后需
        # 把标记后紧跟的空白折叠为零（呈现串不变）
        def fill(m):
            row = ledger.get(m.group(1))
            if row is None or row.get("value_as_printed") is None:
                gaps.append(f"{fname} 的 [num:{m.group(1)}] 在数字账中"
                            "无登记行或无呈现值，不许凭空填数")
                return ""
            return str(row["value_as_printed"])

        out = re.sub(r"\x00NUMFILL:([A-Za-z0-9_-]+)\x00", fill, out)
        return out

    body_parts = []
    abstract_text = None
    for fname, role in _section_order(pkg):
        raw = files[fname]
        log["sections"].append(fname)
        if role == "abstract":
            lines = raw.splitlines()
            body = "\n".join(
                ln for ln in lines
                if not ln.lstrip().startswith("# ")).strip()
            abstract_text = body
            log["abstract_hoisted"] = fname
            continue
        text = raw
        # 图块落位：独占一段的标记，或段首独占一行的标记（标记行与
        # 图注段之间只隔单换行时同属一块，须一并识别）
        blocks = re.split(r"\n\s*\n", text)
        out_blocks = []
        i = 0
        while i < len(blocks):
            block = blocks[i]
            stripped = block.strip()
            fm = _FIG_MARK_RE.fullmatch(stripped)
            caption_in_block = None
            if fm is None:
                first, _, rest = stripped.partition("\n")
                fm = _FIG_MARK_RE.fullmatch(first.strip())
                if fm:
                    caption_in_block = rest.strip()
            if fm:
                fid = fm.group(1)
                row = figures.get(fid)
                if row is None:
                    gaps.append(f"{fname} 的 [fig:{fid}] 在图表清单中"
                                "无登记行")
                    i += 1
                    continue
                if row.get("kind") == "table":
                    gaps.append(
                        f"{fname} 的 [fig:{fid}] 登记为 table：表格内容"
                        "须以 MD 表格直接入节，导出链不凭空造表")
                    i += 1
                    continue
                if row.get("status") not in ("delivered", "backfilled"):
                    gaps.append(
                        f"{fname} 的 [fig:{fid}] 状态为 "
                        f"{row.get('status')}（未交付/未回填），不许出图块")
                    i += 1
                    continue
                src = row.get("source_ref")
                if not src or not (root / src).exists():
                    gaps.append(f"{fname} 的 [fig:{fid}] 图件文件不存在"
                                f"：{src}")
                    i += 1
                    continue
                caption = row.get("caption") or ""
                # 图注本体不重复出：同块余下文本或紧随段落与登记
                # 图注同文时消费之（图注以登记行为权威）
                if caption_in_block and caption and \
                        _norm_ws(caption_in_block) == _norm_ws(caption):
                    caption_in_block = None
                if i + 1 < len(blocks) and caption and \
                        _norm_ws(blocks[i + 1]) == _norm_ws(caption):
                    i += 1
                label = row.get("display_label") or fid
                out_blocks.append(
                    f"![{label}. {caption}]({src})"
                    f"{{#fig:{fid.lower()}}}")
                log["figures_placed"].append(
                    {"figure_id": fid, "file": fname, "source_ref": src})
                if caption_in_block:
                    # 与登记图注不同文的同块余文是正文本体，留在图后
                    out_blocks.append(caption_in_block)
                i += 1
                continue
            out_blocks.append(block)
            i += 1
        text = "\n\n".join(out_blocks)
        # 行内图引用 → display_label
        def fig_inline(m):
            fid = m.group(1)
            row = figures.get(fid)
            if row is None:
                gaps.append(f"{fname} 的行内 [fig:{fid}] 无登记行")
                return m.group(0)
            log["figures_intext"].append(
                {"figure_id": fid, "file": fname})
            return row.get("display_label") or fid

        text = _FIG_MARK_RE.sub(fig_inline, text)
        # 数字标记
        text = sub_numbers(text, fname)
        # 主张标记剥离
        for cid in _CLAIM_MARK_RE.findall(text):
            log["claims_stripped"].append({"claim_id": cid, "file": fname})
        text = _CLAIM_MARK_RE.sub("", text)
        # 引用键归一：[@lit:<条目ID>] → [@key]
        def cite_norm(m):
            inner = m.group(1)
            keys = []
            for key in _CITE_KEY_RE.findall(inner):
                if key.startswith("lit:"):
                    entry_id = key[4:]
                    target = lock_by_entry.get(entry_id)
                    if target is None:
                        gaps.append(
                            f"{fname} 的 [@lit:{entry_id}] 在 lock 中"
                            "无对应条目")
                        keys.append(key)
                    else:
                        log["lit_resolved"].append(
                            {"entry_id": entry_id, "key": target,
                             "file": fname})
                        keys.append(target)
                else:
                    keys.append(key)
            log["cited_keys"].extend(keys)
            return "[" + "; ".join("@" + k for k in keys) + "]"

        text = _CITE_GROUP_RE.sub(cite_norm, text)
        # 占位符残留（源级）
        for pat in ("AUTHOR_INPUT_NEEDED", "[directive:"):
            if pat in text:
                gaps.append(f"{fname} 含未决占位 {pat}，投稿成品不许带"
                            "占位符残留（先补齐或登记处置）")
        body_parts.append(text.strip())

    log["cited_keys"] = sorted(set(log["cited_keys"]))
    unknown = [k for k in log["cited_keys"] if k not in lock_keys]
    if unknown:
        gaps.append(f"正文引用键不在 lock 内：{unknown}"
                    "（占位符隔离纪律，见 SKILL §7）")
    # 数字呈现值 vs 账（源级先验；渲染后在场性在 verify 阶段）
    for item in log["numbers"]:
        if item["printed_in_text"] is not None and \
                item["ledger_value"] is not None and \
                item["printed_in_text"] != str(item["ledger_value"]):
            gaps.append(
                f"{item['file']} 的 [num:{item['num_id']}] 呈现值 "
                f"{item['printed_in_text']} 与数字账登记值 "
                f"{item['ledger_value']} 不符（账是权威，先改账或改稿）")

    meta = {"title": manuscript.get("title") or ""}
    authors = []
    structured = []
    for a in manuscript.get("authors") or []:
        if isinstance(a, dict):
            authors.append(a.get("name") or "")
            structured.append({
                "name": a.get("name") or "",
                "affiliation": a.get("affiliation") or "",
                "corresponding": bool(a.get("corresponding")),
            })
        else:
            authors.append(str(a))
            structured.append({"name": str(a), "affiliation": "",
                               "corresponding": False})
    if authors:
        meta["author"] = authors
        meta["authors_structured"] = structured
        meta.update(_frontiers_metadata(structured))
    if abstract_text:
        meta["abstract"] = abstract_text
    import yaml

    header = "---\n" + yaml.safe_dump(
        meta, allow_unicode=True, sort_keys=False) + "---\n\n"
    combined = header + "\n\n".join(p for p in body_parts if p) + "\n"
    return combined, log, gaps


# ---------------------------------------------------------------- 渲染

_TARGET_FORMATS = ("docx", "tex", "pdf")


def _convert_svg(svg_path, out_dir, converter):
    """SVG → PDF（LaTeX 用）：转换器缺席返回 None 并点名。"""
    name, exe = converter
    target = out_dir / (Path(svg_path).stem + ".pdf")
    if name == "rsvg-convert":
        proc = _run([exe, "-f", "pdf", "-o", str(target), str(svg_path)])
    elif name == "inkscape":
        proc = _run([exe, str(svg_path), "--export-type=pdf",
                     f"--export-filename={target}"])
    else:  # cairosvg
        import cairosvg

        cairosvg.svg2pdf(url=str(svg_path), write_to=str(target))
        return target
    if proc["exit_code"] != 0 or not target.exists():
        return None
    return target


def run_export(root, formats=("docx", "tex", "pdf"), profile=None,
               template_id=None, library_root=None):
    root = Path(root)
    pkg = load_package(root)
    if pkg["manuscript"] is None:
        raise ExportError(["稿件包不存在（先 init）"])
    formats = [f for f in formats if f in _TARGET_FORMATS]
    if not formats:
        raise ExportError([f"无有效导出格式，可选 {_TARGET_FORMATS}"])
    if profile is None:
        if template_id:
            if not library_root:
                raise ExportError(["--template 须同时给 --library 模板库根"])
            profile = load_library_profile(template_id, library_root)
        else:
            profile = profile_from_record(pkg["template_record"])
    pandoc = find_pandoc()
    if pandoc is None:
        raise ExportError([
            "PANDOC_MISSING：本机无 pandoc（PATH 与 pypandoc 自带二进制"
            "均缺席），导出链不启动；安装 pandoc 或 pip install "
            "pypandoc-binary 后重试，不许以占位文件冒充成品"])

    combined, log, gaps = assemble_markdown(pkg)
    if gaps:
        raise ExportError(gaps)

    out_dir = root / "export" / profile["label"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "combined.md").write_text(combined, encoding="utf-8")
    bib_src = root / FILES["bib"]
    if bib_src.exists():
        shutil.copyfile(bib_src, out_dir / "references.bib")
    # 模板类文件（.cls/.bst/.cfg 等）随导出目录就位，编译才找得到；
    # 条目可带 glob（如 achemso 的逐刊 cfg 集），逐个展开
    copied_class_files = []
    import glob as _glob

    for path in profile.get("class_files") or []:
        candidates = [Path(p) for p in sorted(_glob.glob(path))] \
            if "*" in path else [Path(path)]
        for src in candidates:
            if src.exists():
                shutil.copyfile(src, out_dir / src.name)
                copied_class_files.append(src.name)
    assets_dir = root / "assets"
    if assets_dir.exists():
        shutil.copytree(assets_dir, out_dir / "assets",
                        dirs_exist_ok=True)

    record = {
        "kind": "light-write/export-record",
        "version": "1.0",
        "exported_at": utcnow(),
        "manuscript_id": pkg["manuscript"].get("manuscript_id"),
        "manuscript_status": pkg["manuscript"].get("status"),
        "manuscript_hash": manuscript_hash(root),
        "profile": profile,
        "tools": {
            "pandoc": {"path": pandoc,
                       "version": _tool_version(pandoc, "--version")},
            "latex_engine": None,
            "svg_converter": None,
        },
        "transform_log": log,
        "commands": [],
        "products": {},
        "notes": [],
    }

    # EPS 类文件预转换：部分期刊类（Frontiers）按 <name>-eps-converted
    # -to.pdf 内嵌名引图，而受限 shell 的 repstopdf 在本机静默失败；
    # 导出时以 ghostscript 预生成并留痕，缺 gs 则落注记（不假转换）
    gs = shutil.which("gs")
    for name in copied_class_files:
        if not name.lower().endswith(".eps"):
            continue
        target = out_dir / (Path(name).stem + "-eps-converted-to.pdf")
        if target.exists():
            continue
        if gs:
            proc = _run([gs, "-o", target.name, "-sDEVICE=pdfwrite",
                         "-dEPSCrop", name], cwd=out_dir)
            record["commands"].append({"target": "eps-convert", **proc})
            if proc["exit_code"] != 0:
                record["notes"].append(
                    f"EPS 预转换失败：{name}（gs exit {proc['exit_code']}）")
        else:
            record["notes"].append(
                f"GS_MISSING：{name} 未做 EPS→PDF 预转换（本机无 "
                "ghostscript），编译可能因缺 *-eps-converted-to.pdf 失败")

    bib_args = []
    if (out_dir / "references.bib").exists() and log["cited_keys"]:
        bib_args = ["--bibliography", "references.bib"]
    cite_args = []
    if profile["citation_mode"] == "natbib":
        cite_args = ["--natbib"]
    elif profile["citation_mode"] == "biblatex":
        cite_args = ["--biblatex"]
    elif bib_args:
        cite_args = ["--citeproc"]

    # ---- DOCX
    if "docx" in formats:
        cmd = [pandoc, "combined.md", "-o", "manuscript.docx",
               "--resource-path", str(out_dir)] + cite_args + bib_args
        if profile.get("reference_doc"):
            if Path(profile["reference_doc"]).exists():
                cmd += ["--reference-doc", profile["reference_doc"]]
            else:
                record["notes"].append(
                    f"reference_doc 不存在，DOCX 回退 pandoc 默认样式："
                    f"{profile['reference_doc']}")
        proc = _run(cmd, cwd=out_dir)
        record["commands"].append({"target": "docx", **proc})
        if proc["exit_code"] == 0 and (out_dir / "manuscript.docx").exists():
            record["products"]["docx"] = _product(out_dir / "manuscript.docx")
        else:
            raise ExportError([
                f"pandoc DOCX 渲染失败（exit {proc['exit_code']}）："
                f"{proc['stderr_tail'][-500:]}"])

    # ---- LaTeX（PDF 的前置产物，请求 pdf 时一并产出）
    tex_md = out_dir / "combined.md"
    if "tex" in formats or "pdf" in formats:
        # SVG 图件：LaTeX 不能直引，逐个转 PDF 并改写一份 tex 专用源
        tex_text = combined
        svg_refs = sorted(set(re.findall(
            r"\(([^)]+\.svg)\)", combined)))
        if svg_refs:
            converter = find_svg_converter()
            if converter is None:
                raise ExportError([
                    "SVG_CONVERTER_MISSING：LaTeX 目标含 SVG 图件 "
                    f"{svg_refs}，本机无 rsvg-convert / inkscape / "
                    "cairosvg，不许静默丢图；装任一转换器后重试"])
            record["tools"]["svg_converter"] = {
                "name": converter[0], "path": converter[1]}
            conv_dir = out_dir / "assets-converted"
            conv_dir.mkdir(exist_ok=True)
            for ref in svg_refs:
                src = (out_dir / ref).resolve()
                made = _convert_svg(src, conv_dir, converter)
                if made is None:
                    raise ExportError([f"SVG 转换失败：{ref}"])
                tex_text = tex_text.replace(
                    f"({ref})", f"(assets-converted/{made.name})")
            tex_md = out_dir / "combined-tex.md"
            tex_md.write_text(tex_text, encoding="utf-8")
        cmd = [pandoc, tex_md.name, "-s", "-o", "manuscript.tex",
               "--resource-path", str(out_dir)] + cite_args + bib_args
        if profile.get("documentclass"):
            cmd += ["-V", f"documentclass={profile['documentclass']}"]
        for opt in profile.get("classoptions") or []:
            cmd += ["-V", f"classoption={opt}"]
        if profile["citation_mode"] == "natbib" and profile.get("bst_name"):
            cmd += ["-V", f"biblio-style={profile['bst_name']}"]
        if profile.get("template_file"):
            cmd += ["--template", profile["template_file"]]
        proc = _run(cmd, cwd=out_dir)
        record["commands"].append({"target": "tex", **proc})
        if proc["exit_code"] == 0 and (out_dir / "manuscript.tex").exists():
            record["products"]["tex"] = _product(out_dir / "manuscript.tex")
        else:
            raise ExportError([
                f"pandoc LaTeX 渲染失败（exit {proc['exit_code']}）："
                f"{proc['stderr_tail'][-500:]}"])

    # ---- PDF（LaTeX 引擎编译冒烟）
    if "pdf" in formats:
        engine = find_latex_engine()
        if engine is None:
            record["notes"].append(
                "ENGINE_MISSING：本机无 xelatex/pdflatex/lualatex，"
                "PDF 未编译（LaTeX 源已产出）；装 TeX 后以 export 补跑")
            record["products"]["pdf"] = {
                "status": "not_compiled", "reason": "ENGINE_MISSING"}
        else:
            record["tools"]["latex_engine"] = {
                "path": engine,
                "version": _tool_version(engine, "--version")}
            tex_name = "manuscript.tex"
            passes = [_run([engine, "-interaction=nonstopmode",
                            tex_name], cwd=out_dir)]
            if profile["citation_mode"] in ("natbib", "biblatex") \
                    and bib_args:
                bibtex = shutil.which("bibtex") or shutil.which("biber")
                if bibtex:
                    passes.append(_run([bibtex, "manuscript"],
                                       cwd=out_dir))
                    passes.append(_run([engine, "-interaction=nonstopmode",
                                        tex_name], cwd=out_dir))
                else:
                    record["notes"].append(
                        "BIBTEX_MISSING：natbib/biblatex 模式需 bibtex/"
                        "biber 跑参考文献遍，本机缺席，PDF 参考文献可能"
                        "未解析（日志检查会点名）")
            passes.append(_run([engine, "-interaction=nonstopmode",
                                tex_name], cwd=out_dir))
            record["commands"].extend(
                {"target": "pdf", **p} for p in passes)
            pdf_path = out_dir / "manuscript.pdf"
            log_text = ""
            log_path = out_dir / "manuscript.log"
            if log_path.exists():
                log_text = log_path.read_text(encoding="utf-8",
                                               errors="replace")
            if pdf_path.exists() and passes[-1]["exit_code"] == 0:
                record["products"]["pdf"] = _product(pdf_path)
                record["products"]["pdf"]["compile_log_tail"] = \
                    log_text[-1000:]
            else:
                errors = [ln for ln in log_text.splitlines()
                          if ln.startswith("!")][:5]
                raise ExportError([
                    "LaTeX 编译失败：" + " | ".join(errors or
                    [passes[-1]["stderr_tail"][-300:]])])

    record["checks"] = verify_products(pkg, out_dir, record)
    record["overall"] = all(c["ok"] for c in record["checks"]
                            if c.get("applicable", True))
    dump_json(out_dir / EXPORT_RECORD, record)
    return record


def _product(path):
    return {"path": path.name, "bytes": path.stat().st_size,
            "sha256": sha256_file(path)}


# ---------------------------------------------------------------- 渲染后复核

def _docx_text(path):
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    xml = re.sub(r"<w:p[ >]", "\n<w:p ", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    import html

    return html.unescape(text)


def _tex_plain(tex_text):
    """LaTeX → 近似纯文本（供词表/数字/标题复核）：删注释与命令名，
    保留花括号内文本。"""
    lines = []
    for ln in tex_text.splitlines():
        ln = re.sub(r"(?<!\\)%.*$", "", ln)
        lines.append(ln)
    text = "\n".join(lines)
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", text)


def _rendered_texts(out_dir, record):
    texts = {}
    products = record.get("products") or {}
    if "docx" in products and \
            isinstance(products["docx"], dict) and \
            products["docx"].get("sha256"):
        texts["docx"] = _docx_text(out_dir / "manuscript.docx")
    if "tex" in products:
        texts["tex"] = (out_dir / "manuscript.tex").read_text(
            encoding="utf-8")
    return texts


def verify_products(pkg, out_dir, record):
    """渲染后机械复核五项（与审计门口径同源，作用面为渲染产物）。"""
    out_dir = Path(out_dir)
    manuscript = pkg["manuscript"] or {}
    language = manuscript.get("language")
    log = record.get("transform_log") or {}
    texts = _rendered_texts(out_dir, record)
    checks = []

    def add(name, ok, details, applicable=True):
        checks.append({"name": name, "ok": bool(ok),
                       "applicable": applicable, "details": details})

    if not texts:
        add("products_present", False, "无可复核的渲染产物")
        return checks

    # 1) 数字账值在场：每行呈现值在每种产物文本中的出现次数
    #    不少于源稿呈现次数（变换日志口径）。
    src_counts = {}
    for item in log.get("numbers") or []:
        if item.get("printed_in_text") is not None:
            src_counts[item["num_id"]] = \
                src_counts.get(item["num_id"], 0) + 1
    ledger = {r.get("num_id"): r
              for r in (pkg["numbers"] or {}).get("numbers") or []}
    missing = []
    for nid, count in src_counts.items():
        value = str((ledger.get(nid) or {}).get("value_as_printed"))
        for kind, text in texts.items():
            hay = text
            if hay.count(value) < count:
                missing.append(f"{kind} 中 {nid}={value} 出现 "
                               f"{hay.count(value)} 次 < 源稿 {count} 次")
    add("numbers_in_render", not missing,
        missing or f"{len(src_counts)} 个数字账行全部在场")

    # 2) 引用键集合：natbib/biblatex 的 tex 查 \\cite 键集相等；
    #    citeproc 产物查每条被引条目的一作姓 + 年份在渲染文本在场。
    cited = set(log.get("cited_keys") or [])
    lock = {e.get("key"): e
            for e in (pkg["lock"] or {}).get("entries") or []}
    mode = (record.get("profile") or {}).get("citation_mode")
    cite_details = []
    cite_ok = True
    if "tex" in texts and mode in ("natbib", "biblatex"):
        found = set()
        for m in re.finditer(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])?\{([^}]*)\}",
                             texts["tex"]):
            found.update(k.strip() for k in m.group(1).split(","))
        if found != cited:
            cite_ok = False
            cite_details.append(
                f"tex \\cite 键集与源稿不一致：缺 {sorted(cited - found)}"
                f"，多 {sorted(found - cited)}")
    else:
        for kind, text in texts.items():
            plain = _tex_plain(text) if kind == "tex" else text
            for key in sorted(cited):
                entry = lock.get(key) or {}
                authors = entry.get("authors") or []
                surname = ""
                if authors:
                    surname = str(authors[0]).strip().split()[-1]
                    surname = unicodedata.normalize("NFKD", surname)
                    surname = surname.encode(
                        "ascii", "ignore").decode("ascii")
                year = str(entry.get("year") or "")
                if surname and surname.lower() not in plain.lower():
                    cite_ok = False
                    cite_details.append(
                        f"{kind} 中被引条目 {key} 的一作姓 {surname} "
                        "未在渲染文本出现（引用可能未解析）")
                if year and year not in plain:
                    cite_ok = False
                    cite_details.append(
                        f"{kind} 中被引条目 {key} 的年份 {year} "
                        "未在渲染文本出现")
    add("citations_in_render", cite_ok,
        cite_details or f"{len(cited)} 个引用键全部落实")

    # 3) 措辞重扫：全档禁用词表在渲染纯文本上重跑（与门三同一匹配
    #    函数：英文词界 + significant 族变体归一，中文全形匹配）。
    from .audit import _en_banned_hit

    table = (schema.WORDING_TABLES.get(language) or {})
    banned = table.get("banned_terms") or []
    hits = []
    for kind, text in texts.items():
        plain = _tex_plain(text) if kind == "tex" else text
        for term in banned:
            if language == "en":
                hit = _en_banned_hit(term, plain.lower())
            else:
                hit = term in plain
            if hit:
                hits.append(f"{kind} 渲染文本命中全档禁用词 {term!r}")
    add("wording_rescan", not hits,
        hits or f"{len(banned)} 条全档禁用词零命中")

    # 4) 占位符零残留
    residue = []
    for kind, text in texts.items():
        for pat in _PLACEHOLDER_PATTERNS:
            if pat in text:
                residue.append(f"{kind} 残留 {pat}")
    log_path = out_dir / "manuscript.log"
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        for pat in ("Citation", "Reference"):
            for ln in log_text.splitlines():
                if pat in ln and "undefined" in ln:
                    residue.append(f"编译日志：{ln.strip()[:160]}")
    add("placeholders_absent", not residue,
        residue or "标记/占位符零残留")

    # 5) 节标题齐全：各节首个一级标题文本在渲染文本在场
    files = section_files(pkg["root"])
    absent = []
    for fname, _role in _section_order(pkg):
        if _role == "abstract":
            continue
        head = None
        for ln in files[fname].splitlines():
            if ln.lstrip().startswith("# "):
                head = ln.lstrip()[2:].strip()
                break
        if not head:
            continue
        for kind, text in texts.items():
            plain = _tex_plain(text) if kind == "tex" else text
            if _norm_ws(head) not in _norm_ws(plain):
                absent.append(f"{kind} 缺节标题 {head!r}（{fname}）")
    add("sections_present", not absent,
        absent or "全部节标题在场")

    # 6) 图件在场：落位图逐个在产物中落实（tex 查 \includegraphics
    #    指向的文件名；docx 查 word/media 内嵌件数）
    placed = log.get("figures_placed") or []
    fig_missing = []
    if placed:
        if "tex" in texts:
            graphics = re.findall(r"\\includegraphics(?:\[[^\]]*\])?"
                                  r"\{([^}]*)\}", texts["tex"])
            stems = {Path(g).stem for g in graphics}
            for item in placed:
                stem = Path(item["source_ref"]).stem
                if stem not in stems:
                    fig_missing.append(
                        f"tex 未引图件 {item['source_ref']}")
        products = record.get("products") or {}
        if products.get("docx", {}).get("sha256"):
            with zipfile.ZipFile(out_dir / "manuscript.docx") as zf:
                media = [n for n in zf.namelist()
                         if n.startswith("word/media/")]
            if len(media) < len(placed):
                fig_missing.append(
                    f"docx 内嵌图件 {len(media)} 件 < 落位图 "
                    f"{len(placed)} 个")
    add("figures_in_render", not fig_missing,
        fig_missing or f"{len(placed)} 个落位图全部在场",
        applicable=bool(placed))
    return checks


def check_export(root):
    """复核既有导出：哈希绑定（STALE）+ 产物在场 + 复核五项重跑。"""
    root = Path(root)
    pkg = load_package(root)
    if pkg["manuscript"] is None:
        raise ExportError(["稿件包不存在（先 init）"])
    export_root = root / "export"
    results = []
    if not export_root.exists():
        return {"exports": [], "note": "尚无导出产物"}
    current_hash = manuscript_hash(root)
    for sub in sorted(export_root.iterdir()):
        record_path = sub / EXPORT_RECORD
        if not record_path.exists():
            continue
        record = load_structured(record_path)
        stale = record.get("manuscript_hash") != current_hash
        entry = {
            "profile": sub.name,
            "exported_at": record.get("exported_at"),
            "stale": stale,
            "products": list((record.get("products") or {}).keys()),
        }
        if not stale:
            entry["checks"] = verify_products(pkg, sub, record)
            entry["ok"] = all(c["ok"] for c in entry["checks"]
                              if c.get("applicable", True))
        results.append(entry)
    return {"exports": results, "manuscript_hash": current_hash}
