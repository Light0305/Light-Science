"""P3 撰写：权要结构登记、三箱分拣、支持映射、申报副本剥离。

权要先行：独权特征三箱分拣（必要/实施例选择/接口细节），只有
必要特征许进独权；从属一机制一权项；载体权要须有支持才许加。
工作副本可带过程标记（HTML 批注、撰写说明段），申报副本由工作
副本机械剥离生成并做洁净检查 + diff 留痕（LP-04）。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .intake import require_audited
from .project import (
    PatentError, case_path, load_case, load_yaml_or, set_status,
)
from .util import dump_yaml, read_text, sha256_text, today

_PROCESS_HEADINGS = ("撰写说明", "查新过程", "自检记录", "过程记录")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_ANCHOR_TOKEN_RE = re.compile(r"\b[PEFC]\d{3}\b")


def _require_searched(root, case) -> dict:
    d1 = load_yaml_or(root, "d1", None)
    if not d1:
        raise PatentError(["未锁定 D1：撰写前先完成查新并锁定 D1（P2）"])
    return d1


def register_claims(root, payload: dict) -> dict:
    """登记结构化权要。payload: {claims: [{claim_no, type, depends_on,
    preamble, features: [{feature_ref, text, box, support}]}]}。
    support 为源图谱/说明书支持登记：{state, anchors}。"""
    root = Path(root)
    case = load_case(root)
    require_audited(root, case)
    _require_searched(root, case)
    claims = payload.get("claims") or []
    gaps = []
    sm = load_yaml_or(root, "source_map", {"anchors": []})
    known = {a["anchor"] for a in sm["anchors"]}
    d1 = load_yaml_or(root, "d1", {})
    fk_refs = {f["feature_ref"] for f in d1.get("distinguishing_features") or []}
    seen_nos = set()
    for c in claims:
        no = c.get("claim_no")
        if no in seen_nos:
            gaps.append(f"权要编号重复：{no}")
        seen_nos.add(no)
        if c.get("type") not in schema.CLAIM_TYPES:
            gaps.append(f"权要 {no} 类型 {c.get('type')!r} 不在词表内")
        for dep in c.get("depends_on") or []:
            if dep >= no:
                gaps.append(f"权要 {no} 引用方向错误：只能引用在先权要"
                            f"（引用了 {dep}）")
        for f in c.get("features") or []:
            box = f.get("box")
            if box not in schema.FEATURE_BOXES:
                gaps.append(f"权要 {no} 特征 {f.get('feature_ref')!r} "
                            f"分箱 {box!r} 不在三箱词表内")
            if no == 1 and box != "necessary":
                gaps.append(f"独权特征 {f.get('feature_ref')!r} 分箱为 "
                            f"{box}：只有必要特征许进独权（三箱分拣）")
            sup = f.get("support") or {}
            state = sup.get("state")
            if state not in schema.SUPPORT_STATES:
                gaps.append(f"权要 {no} 特征 {f.get('feature_ref')!r} "
                            "缺支持状态（四值必填，LP-02）")
            if state == "unsupported":
                gaps.append(f"权要 {no} 特征 {f.get('feature_ref')!r} "
                            "支持状态为 unsupported：禁止进入正式权要（LP-02）")
            for anchor in sup.get("anchors") or []:
                if anchor not in known:
                    gaps.append(f"权要 {no} 特征 {f.get('feature_ref')!r} "
                                f"支持锚点 {anchor!r} 不在源图谱内（虚锚）")
    if 1 not in seen_nos:
        gaps.append("缺权利要求 1（独权）")
    carriers = [c for c in claims if c.get("type") in schema.CARRIER_CLAIM_TYPES]
    for c in carriers:
        if not (c.get("features")):
            gaps.append(f"载体权要 {c.get('claim_no')} 无特征：载体权要"
                        "须由方法权要特征支持生成，不许空挂")
    if gaps:
        raise PatentError(gaps)
    data = {
        "kind": "light-patent/claims",
        "case_id": case["case_id"],
        "claims": claims,
        "claim_count": len(claims),
        "extra_fee_claims": max(0, len(claims) - schema.EXTRA_CLAIM_FEE_FROM),
        "distinguishing_refs": sorted(fk_refs),
        "ai_sufficiency": payload.get("ai_sufficiency") or {},
        "registered_at": today(),
    }
    dump_yaml(case_path(root, "claims"), data)
    _render_claims_md(root, case, claims)
    _build_support_map(root, case, claims)
    if case["status"] in ("searched", "mined", "audited"):
        set_status(root, case, "drafted", "light-patent draft")
    return {"claims": len(claims),
            "extra_fee_claims": data["extra_fee_claims"]}


def _feature_line(f) -> str:
    return f.get("text") or ""


def _render_claims_md(root, case, claims) -> None:
    lines = [f"# 权利要求书（工作副本）", "",
             f"发明名称：{case['title']}", ""]
    for c in sorted(claims, key=lambda x: x["claim_no"]):
        body = "；".join(_feature_line(f) for f in c.get("features") or [])
        lines.append(f"{c['claim_no']}. {c.get('preamble') or ''}{body}。")
        lines.append("")
    target = case_path(root, "claims_md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")


def _build_support_map(root, case, claims) -> None:
    rows = []
    for c in claims:
        for f in c.get("features") or []:
            sup = f.get("support") or {}
            rows.append({
                "claim_no": c["claim_no"],
                "feature_ref": f.get("feature_ref"),
                "support_state": sup.get("state"),
                "anchors": sup.get("anchors") or [],
                "spec_section": sup.get("spec_section") or "",
            })
    dump_yaml(case_path(root, "support_map"), {
        "kind": "light-patent/support-map", "case_id": case["case_id"],
        "rows": rows, "built_at": today(),
    })


def register_text(root, kind: str, source_file) -> dict:
    """落说明书/摘要工作副本（kind: specification / abstract）。"""
    root = Path(root)
    case = load_case(root)
    require_audited(root, case)
    key = {"specification": "specification_md",
           "abstract": "abstract_md"}[kind]
    text = read_text(source_file)
    if not text.strip():
        raise PatentError([f"{kind} 来源文件为空"])
    target = case_path(root, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {"kind": kind, "chars": len(text)}


def register_numerals(root, payload: dict) -> dict:
    rows = payload.get("numerals") or []
    gaps = [f"附图标记 {r.get('mark')!r} 缺名称或说明"
            for r in rows if not r.get("name") or not r.get("description")]
    if gaps:
        raise PatentError(gaps)
    dump_yaml(case_path(root, "numerals"), {
        "kind": "light-patent/numerals",
        "case_id": load_case(root)["case_id"], "numerals": rows})
    return {"numerals": len(rows)}


def register_gaps(root, payload: dict) -> dict:
    rows = payload.get("gaps") or []
    dump_yaml(case_path(root, "gaps"), {
        "kind": "light-patent/gaps",
        "case_id": load_case(root)["case_id"], "gaps": rows})
    return {"gaps": len(rows)}


def _strip_process(text: str) -> str:
    text = _COMMENT_RE.sub("", text)
    out, skipping = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            skipping = any(h in line for h in _PROCESS_HEADINGS)
        if line.startswith("> 过程"):
            continue
        if not skipping:
            out.append(line)
    return "\n".join(out).strip() + "\n"


def strip_filing(root) -> dict:
    """由工作副本机械剥离生成申报副本 + 洁净检查 + diff 留痕。"""
    root = Path(root)
    case = load_case(root)
    filing_dir = case_path(root, "filing_dir")
    filing_dir.mkdir(parents=True, exist_ok=True)
    report = {"case_id": case["case_id"], "stripped_at": today(), "files": []}
    for key, name in (("claims_md", "claims.md"),
                      ("specification_md", "specification.md"),
                      ("abstract_md", "abstract.md")):
        src = case_path(root, key)
        if not src.exists():
            continue
        raw = read_text(src)
        clean = _strip_process(raw)
        hits = [t for t in schema.PROCESS_TOKENS if t in clean]
        if _ANCHOR_TOKEN_RE.search(clean):
            hits.append("源锚点令牌(P/E/F/C+三位数字)")
        target = filing_dir / name
        target.write_text(clean, encoding="utf-8")
        report["files"].append({
            "file": name, "work_sha256": sha256_text(raw),
            "filing_sha256": sha256_text(clean),
            "removed_chars": len(raw) - len(clean),
            "process_hits": hits,
        })
    dump_yaml(filing_dir / "strip_report.yaml", report)
    bad = [f for f in report["files"] if f["process_hits"]]
    return {"files": len(report["files"]),
            "unclean": [f["file"] for f in bad]}
