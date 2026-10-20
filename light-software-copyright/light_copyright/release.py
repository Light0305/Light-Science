"""SC7 递交核对与资料包：发布门禁 + 逐字段清单 + declaration 门。

门禁口径：任何一项不过都不许 packaged，失败逐项点名（不许汇总含糊）。
declaration 门（Q2 拍板硬门）：本包不保存、不臆造当期申请表 AI 使用
声明的任何措辞；发布前必须同时具备：
  1) 用户自备的当期声明原文文件落案（declaration/current_text.txt，
     内容由用户从当期官方表单取得，本包只登记其哈希与来源说明）；
  2) 用户本人的逐字核对回执（绑原文哈希，原文一变回执即失效）；
  3) 工具使用记录完整在案，且用户若在回执中声称「未使用工具起草」
     而 tool_use.jsonl 有 tool 起草记录，判定矛盾并阻断（HC-4 机械形）。
签署动作不存在于本包：回执只是用户已核对的登记，签字永远由用户本人
在登记系统完成。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import render, schema
from .case import (CaseError, confirmation_valid, confirmations, load_case,
                   load_facts, log_tool_use, save_case)
from .form import derive_application
from .select import load_selection, selection_fingerprint
from .snapshot import verify_snapshot
from .util import dump_json, load_structured, read_jsonl, sha256_file

DECLARATION_DIR = "declaration"
SHOTS_DIR = "screenshots"
PACKAGE_DIR = "资料包"


# ---------------------------------------------------------- declaration 门
def declaration_text_path(root) -> Path:
    return Path(root) / DECLARATION_DIR / "current_text.txt"


def record_declaration_text(root, source_file, origin_note: str) -> dict:
    """登记用户自备的当期声明原文：只搬运与登记哈希，不解读不改写。"""
    root = Path(root)
    src = Path(source_file)
    if not src.exists():
        raise CaseError([f"声明原文文件不存在：{source_file}"])
    if not (origin_note or "").strip():
        raise CaseError(["必须注明原文取得渠道（如当期申请表/版权中心官网），"
                         "无来源说明不登记"])
    dst_dir = root / DECLARATION_DIR
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "current_text.txt"
    shutil.copyfile(src, dst)
    meta = {"origin": origin_note, "sha256": sha256_file(dst),
            "chars": len(dst.read_text(encoding="utf-8"))}
    dump_json(dst_dir / "meta.json", meta)
    log_tool_use(root, "user", "declaration-record", "declaration",
                 f"来源：{origin_note}；哈希 {meta['sha256'][:12]}")
    return meta


def declaration_gate(root) -> list:
    """返回阻断理由清单（空 = 过门）。"""
    root = Path(root)
    gaps = []
    text_p = declaration_text_path(root)
    meta_p = root / DECLARATION_DIR / "meta.json"
    if not text_p.exists() or not text_p.read_text(
            encoding="utf-8").strip():
        gaps.append("declaration 门：当期申请表声明原文未落案"
                    "（须用户从当期官方渠道取得原文后 declaration record 登记；"
                    "本包不提供任何声明措辞）")
        return gaps
    if not meta_p.exists():
        gaps.append("declaration 门：声明原文缺来源登记（meta.json）")
        return gaps
    meta = load_structured(meta_p)
    cur_hash = sha256_file(text_p)
    if meta.get("sha256") != cur_hash:
        gaps.append("declaration 门：声明原文在登记后被改动，哈希不符，"
                    "须重新登记并重新逐字核对")
    ok = confirmation_valid(root, "declaration", "current_text", cur_hash)
    if not ok:
        gaps.append("declaration 门：缺逐字核对回执（用户本人读完当期原文"
                    "后以 declaration verify 落回执，绑原文哈希）")
    # HC-4 矛盾检：回执若声称未用工具起草而留痕有 tool 起草行 → 阻断
    for row in confirmations(root):
        if row.get("kind") == "declaration" and \
                (row.get("note") or "").startswith("claims_no_tool_drafting"):
            used = [r for r in read_jsonl(root / "tool_use.jsonl")
                    if r.get("actor") == "tool"
                    and r.get("action") in ("draft", "render")]
            if used:
                gaps.append("declaration 门：回执声称未使用工具起草，但工具"
                            "使用记录含起草/渲染留痕——与记录不符的声明"
                            "本包不协助（HC-4），须按真实记录核对")
    return gaps


# ---------------------------------------------------------- 截图导入（Q6）
def import_screenshot(root, image_file, caption: str) -> dict:
    root = Path(root)
    src = Path(image_file)
    if not src.exists():
        raise CaseError([f"截图文件不存在：{image_file}"])
    d = root / SHOTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    dst = d / src.name
    shutil.copyfile(src, dst)
    row = {"file": src.name, "caption": caption,
           "sha256": sha256_file(dst)}
    rows = read_jsonl(d / "index.jsonl")
    rows = [r for r in rows if r["file"] != src.name] + [row]
    with (d / "index.jsonl").open("w", encoding="utf-8") as fh:
        import json
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    log_tool_use(root, "user", "import-shot", f"screenshots:{src.name}",
                 caption)
    return row


# ---------------------------------------------------------- 发布门禁
def load_manifests(root):
    mdir = Path(root) / render.MATERIALS_DIR
    code_p, doc_p = mdir / "code-manifest.json", mdir / "doc-manifest.json"
    code = load_structured(code_p) if code_p.exists() else None
    doc = load_structured(doc_p) if doc_p.exists() else None
    return code, doc


def _scan_materials(root, code, doc) -> list:
    """占位残留 + 敏感形态扫描（截图预留位为登记豁免形态）。"""
    gaps = []
    mdir = Path(root) / render.MATERIALS_DIR
    for man in (code, doc):
        if not man:
            continue
        text = (mdir / man["file"]).read_text(encoding="utf-8")
        for ln_no, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith(schema.SCREENSHOT_SLOT_PREFIX):
                continue
            for label, pat in schema.PLACEHOLDER_PATTERNS:
                if re.search(pat, line):
                    gaps.append(f"占位/残留扫描：{man['file']} 第 {ln_no} 行"
                                f"命中{label}（HC-3，定版前清零）")
                    break
            for label, pat in schema.SECRET_PATTERNS:
                if re.search(pat, line):
                    gaps.append(f"敏感扫描：{man['file']} 第 {ln_no} 行命中"
                                f"{label}（HC-5）")
                    break
    return gaps


def run_release_checks(root) -> dict:
    """SC7 全门禁：返回 {ok, gaps, warnings, facts_warnings}。"""
    root = Path(root)
    case = load_case(root)
    facts = load_facts(root)
    gaps, warns = [], []

    from .case import facts_fingerprint, facts_warnings, validate_facts
    gaps += validate_facts(facts)
    warns += facts_warnings(facts)
    if not confirmation_valid(root, "facts", "facts",
                              facts_fingerprint(facts)):
        gaps.append("事实确认回执失效或缺失（facts 改动后须重新确认，HC-6）")

    drift = verify_snapshot(root)
    gaps += [f"源码快照：{g}" for g in drift]

    try:
        sel = load_selection(root)
        if not confirmation_valid(root, "selection", "selection",
                                  selection_fingerprint(sel)):
            gaps.append("选材确认回执失效或缺失（选材变动后须重新确认）")
        if not sel["included"]:
            gaps.append("选材入选为空：无源程序可出材料")
    except CaseError as exc:
        gaps += exc.gaps

    code, doc = load_manifests(root)
    if code is None:
        gaps.append("源程序鉴别材料未渲染（先 render-code）")
    else:
        meas = render.measure_code_material(root, code)
        if meas["measured_pages"] != code["constructed_pages"]:
            gaps.append(f"代码材料实测页数 {meas['measured_pages']} 与构造值 "
                        f"{code['constructed_pages']} 不符")
        if meas["bad_pages"]:
            gaps.append(f"代码材料非末页行数不为 50 的页：{meas['bad_pages']}")
        hdr = render.header_line(facts)
        if code.get("header") != hdr:
            gaps.append("代码材料页眉与 facts 派生页眉不一致（HC-2）")
    if doc is None:
        gaps.append("文档鉴别材料未渲染（先 draft-doc + 逐段确认 + render-doc）")
    else:
        hdr = render.header_line(facts)
        if doc.get("header") != hdr:
            gaps.append("文档材料页眉与 facts 派生页眉不一致（HC-2）")

    # 逐段确认（Q2 折中）：每段回执须绑当前段哈希
    try:
        man = render.load_segments(root)
        for seg in man["segments"]:
            text = render.segment_text(root, seg)
            from .util import sha256_text
            if sha256_text(text) != seg["sha256"]:
                gaps.append(f"段 {seg['seg_id']} 在生成后被改动，清单哈希"
                            "失效（须重新生成或按新哈希确认）")
            if not confirmation_valid(root, "segment", seg["seg_id"],
                                      seg["sha256"]):
                gaps.append(f"段 {seg['seg_id']}（{seg['section']}）未确认"
                            "（Q2：逐段确认后才许定版）")
            if not seg.get("evidence"):
                gaps.append(f"段 {seg['seg_id']} 无源码证据指针（HC-3）")
    except CaseError as exc:
        gaps += exc.gaps

    gaps += _scan_materials(root, code, doc)
    gaps += declaration_gate(root)

    shots = read_jsonl(root / SHOTS_DIR / "index.jsonl")
    for row in shots:
        p = root / SHOTS_DIR / row["file"]
        if not p.exists() or sha256_file(p) != row["sha256"]:
            gaps.append(f"截图 {row['file']} 哈希漂移（导入后被改动）")
    return {"ok": not gaps, "gaps": gaps, "warnings": warns,
            "case_status": case.get("status")}


# ---------------------------------------------------------- 打包与清单
def render_checklist(root, facts, code, doc, checks) -> str:
    rows = derive_application(root, facts, code, doc)
    lines = [f"# 递交清单（逐字段）—— {render.header_line(facts)}", "",
             "> 本清单由登记事实单源与实测派生，是唯一的填写口径；"
             "官网填报与签章由用户本人在登记系统完成（v1 不代办，Q4）。",
             ""]
    lines.append("| 字段 | 值 | 来源 | 填写位置 | 注意 |")
    lines.append("|---|---|---|---|---|")
    for r in rows:
        val = str(r["value"]).replace("|", "｜")
        lines.append(f"| {r['field']} | {val} | {r['source']} | "
                     f"{r['where']} | {r['note']} |")
    lines += ["", "## 材料文件", ""]
    for man, label in ((code, "源程序鉴别材料"), (doc, "文档鉴别材料")):
        if man:
            lines.append(f"- {label}：{man['file']}"
                         f"（{man['constructed_pages']} 页，"
                         f"{man.get('page_basis', '')}）")
    shots = read_jsonl(Path(root) / SHOTS_DIR / "index.jsonl")
    if shots:
        lines += ["", "## 已导入截图（仅导入整理，Q6）", ""]
        for s in shots:
            lines.append(f"- {s['file']}：{s['caption']}"
                         f"（sha256 {s['sha256'][:12]}）")
    unfilled = [seg for seg in render.load_segments(root)["segments"]
                if schema.SCREENSHOT_SLOT_PREFIX in
                render.segment_text(root, seg)]
    if unfilled:
        lines += ["", "## 待补项", ""]
        for seg in unfilled:
            lines.append(f"- 段 {seg['seg_id']} 含截图预留位，递交前由用户"
                         "导入真实截图或确认跳过理由")
    lines += ["", "## 时限备忘（A 级规则）", "",
              f"- 审查期：受理日起 {schema.EXAM_DAYS} 日内（登记办法第二十条）",
              f"- 补正期：补正通知后 {schema.CORRECTION_DAYS} 日内"
              "（登记办法第二十二条），逾期视为撤回",
              "- 声明原文：以递交当日当期申请表原文为准，本包已登记核对"
              "回执；系统口径变化须重新核对"]
    return "\n".join(lines) + "\n"


def build_package(root) -> dict:
    root = Path(root)
    checks = run_release_checks(root)
    if not checks["ok"]:
        raise CaseError(["发布门禁未过，拒绝打包："] + checks["gaps"])
    facts = load_facts(root)
    code, doc = load_manifests(root)
    pkg = root / PACKAGE_DIR
    pkg.mkdir(parents=True, exist_ok=True)
    mdir = root / render.MATERIALS_DIR
    copied = []
    for man in (code, doc):
        for name in {man["file"], man.get("docx")} - {None}:
            src = mdir / name
            if src.exists():
                shutil.copyfile(src, pkg / name)
                copied.append(name)
    if (mdir / "源程序鉴别材料.index.jsonl").exists():
        shutil.copyfile(mdir / "源程序鉴别材料.index.jsonl",
                        pkg / "源程序鉴别材料.index.jsonl")
        copied.append("源程序鉴别材料.index.jsonl")
    checklist = render_checklist(root, facts, code, doc, checks)
    (pkg / "递交清单.md").write_text(checklist, encoding="utf-8")
    shutil.copyfile(root / "tool_use.jsonl", pkg / "工具使用记录.jsonl")
    log_tool_use(root, "tool", "package", PACKAGE_DIR,
                 f"产出 {len(copied)} 个材料文件 + 递交清单")
    return {"package_dir": str(pkg), "files": copied + ["递交清单.md",
                                                        "工具使用记录.jsonl"]}
