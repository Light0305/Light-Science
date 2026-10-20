"""P0 公开状态审计 + P1 交底挖掘（含代码仓机械盘点）。

P0 决策表（公开状态前置，LP-09）：未完成审计不许挖掘、不许撰写。
判定只对已登记的公开事实机械作答：无登记不等于未公开，须由
登记人具名确认「已穷尽登记」才许下 clear 结论（防漏登记假绿）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import (
    PatentError, case_path, load_case, load_yaml_or, save_case, set_status,
)
from .util import dump_yaml, parse_date, read_text, today

CODE_EXTS = {
    ".py", ".js", ".ts", ".java", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".go", ".rs", ".m", ".r", ".jl", ".scala", ".kt", ".swift",
}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
             "dist", "build", ".idea", ".scratch"}


def require_audited(root, case) -> None:
    audit = load_yaml_or(root, "audit", None)
    if not audit:
        raise PatentError(["未完成 P0 公开审计：先 audit 再推进（LP-09）"])
    if audit.get("conclusion") == "blocked_prior_disclosure":
        raise PatentError([
            "P0 审计结论 blocked_prior_disclosure：成果已公开且非宽限"
            "情形，论文即现有技术；只许围绕未公开的改进点重新立项"
            "（LP-09），不许在本案继续挖掘/撰写"])
    if audit.get("conclusion") == "unknown":
        raise PatentError([
            "P0 审计结论 unknown：公开状态未确认，不许进挖掘/撰写；"
            "先补齐公开事实登记"])


def run_audit(root, payload: dict) -> dict:
    """落公开审计。payload: {disclosures: [...], confirmed_complete: bool,
    planned_filing_date: str|None, examiner: str}。"""
    root = Path(root)
    case = load_case(root)
    disclosures = payload.get("disclosures") or []
    gaps = []
    for i, d in enumerate(disclosures):
        if d.get("kind") not in schema.DISCLOSURE_KINDS:
            gaps.append(f"公开登记第 {i + 1} 条 kind {d.get('kind')!r} 不在词表")
        if not parse_date(d.get("date")):
            gaps.append(f"公开登记第 {i + 1} 条缺可解析的公开日期 date")
        sit = d.get("grace_situation")
        if sit is not None and sit not in schema.GRACE_SITUATIONS:
            gaps.append(f"公开登记第 {i + 1} 条 grace_situation {sit!r} 不在"
                        "专利法第 24 条四情形词表内")
    if gaps:
        raise PatentError(gaps)
    planned = parse_date(payload.get("planned_filing_date")
                         or (case.get("filing") or {}).get("planned_filing_date"))
    conclusion, detail, window = _decide(disclosures, payload, planned)
    audit = {
        "kind": "light-patent/public-audit",
        "case_id": case["case_id"],
        "audited_at": today(),
        "examiner": payload.get("examiner") or "待填写/需确认",
        "confirmed_complete": bool(payload.get("confirmed_complete")),
        "disclosures": disclosures,
        "planned_filing_date": planned.isoformat() if planned else None,
        "grace_window": window,
        "conclusion": conclusion,
        "detail": detail,
        "ethics_review": payload.get("ethics_review"),
        "disclaimers": [schema.DRAFT_DISCLAIMER],
    }
    if payload.get("ethics_flags"):
        case["ethics_flags"] = payload["ethics_flags"]
    dump_yaml(case_path(root, "audit"), audit)
    if conclusion == "blocked_prior_disclosure":
        case["blocked"] = {
            "gate_id": "public_disclosure_block",
            "detail": detail,
            "fix_pointer": "围绕未公开的改进点重新立项，或改走其他"
                           "权利形态；不得以本案材料继续撰写",
        }
    elif case.get("blocked", {}).get("gate_id") == "public_disclosure_block" \
            if isinstance(case.get("blocked"), dict) else False:
        case["blocked"] = None
    save_case(root, case)
    if case["status"] == "intake":
        set_status(root, case, "audited", "light-patent audit")
    return audit


def _decide(disclosures, payload, planned):
    if not disclosures:
        if payload.get("confirmed_complete"):
            return ("clear",
                    "已具名确认无任何在先公开登记：先申请后公开；"
                    "论文、预印本、代码公开一律排在申请日之后", None)
        return ("unknown",
                "无公开登记且未具名确认穷尽登记：公开状态未知，"
                "不许进挖掘/撰写", None)
    dated = [(parse_date(d["date"]), d) for d in disclosures]
    earliest = min(d for d, _ in dated)
    ref = planned or parse_date(today())
    grace_hits = [d for d in disclosures if d.get("grace_situation")]
    from .util import add_months
    deadline = add_months(earliest, schema.GRACE_MONTHS)
    window = {
        "earliest_disclosure": earliest.isoformat(),
        "grace_deadline": deadline.isoformat(),
        "proof_within_months": schema.GRACE_PROOF_MONTHS,
        "basis": "专利法（2020 年修正）第 24 条；证明程序见实施细则"
                 "（2023 年修订）第 33 条",
    }
    if ref <= deadline and grace_hits:
        return ("grace_possible",
                "最早公开在申请（计划）日前六个月内且属第 24 条四情形"
                "之一：须在申请时提出声明，并在申请日起二个月内提交"
                "有关证明文件；一般国际会议（如 CVPR/NeurIPS）通常不"
                "属「规定的学术会议」，arXiv 预印本不属四情形", window)
    if ref <= deadline and not grace_hits:
        return ("blocked_prior_disclosure",
                "最早公开在六个月内但未登记属第 24 条四情形之一："
                "宽限不成立，该公开构成现有技术", window)
    return ("blocked_prior_disclosure",
            "最早公开已超出六个月宽限窗：该成果已构成现有技术，"
            "论文即现有技术，本案不得以该成果为发明点继续", window)


# ---------------------------------------------------------------- 源图谱与挖掘

def _load_source_map(root) -> dict:
    sm = load_yaml_or(root, "source_map", None)
    if sm is None:
        sm = {"kind": "light-patent/source-map",
              "case_id": load_case(root)["case_id"], "anchors": []}
    return sm


def _save_source_map(root, sm) -> None:
    dump_yaml(case_path(root, "source_map"), sm)


def _next_anchor(sm: dict, prefix: str) -> str:
    used = [a["anchor"] for a in sm["anchors"]
            if a["anchor"].startswith(prefix)]
    n = len(used) + 1
    while f"{prefix}{n:03d}" in used:
        n += 1
    return f"{prefix}{n:03d}"


def register_sources(root, payload: dict) -> dict:
    """登记源材料锚点。payload: {sources: [{kind_prefix, ref, note, route}]}。"""
    root = Path(root)
    case = load_case(root)
    require_audited(root, case)
    sm = _load_source_map(root)
    added = []
    for s in payload.get("sources") or []:
        prefix = s.get("kind_prefix")
        if prefix not in schema.SOURCE_KINDS:
            raise PatentError([f"锚点类别 {prefix!r} 不在 P/E/F/C 词表内"])
        if s.get("route") not in schema.INPUT_ROUTES:
            raise PatentError([f"输入路线 {s.get('route')!r} 不在四路词表内"
                               "（paper/code/experiment/oral）"])
        anchor = s.get("anchor") or _next_anchor(sm, prefix)
        sm["anchors"].append({
            "anchor": anchor,
            "kind": schema.SOURCE_KINDS[prefix],
            "route": s["route"],
            "ref": s.get("ref") or "",
            "note": s.get("note") or "",
        })
        added.append(anchor)
    _save_source_map(root, sm)
    return {"added": added, "total": len(sm["anchors"])}


def scan_code(root, repo_path) -> dict:
    """代码仓机械盘点（Q5 代码挖掘）：遍历源文件、按顶层目录分组，
    逐文件落 C 锚点。只盘点不判发明点——候选由 mine 登记并回锚。"""
    root = Path(root)
    case = load_case(root)
    require_audited(root, case)
    repo = Path(repo_path)
    if not repo.is_dir():
        raise PatentError([f"代码仓路径不存在：{repo}"])
    files = []
    for p in sorted(repo.rglob("*")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and p.suffix.lower() in CODE_EXTS:
            files.append(p)
    sm = _load_source_map(root)
    added = []
    for p in files:
        rel = p.relative_to(repo)
        anchor = _next_anchor(sm, "C")
        sm["anchors"].append({
            "anchor": anchor, "kind": "code", "route": "code",
            "ref": str(rel),
            "note": f"子系统 {rel.parts[0] if len(rel.parts) > 1 else '(根)'}"
                    f"；{sum(1 for _ in p.open(encoding='utf-8', errors='ignore'))} 行",
        })
        added.append(anchor)
    _save_source_map(root, sm)
    return {"repo": str(repo), "files": len(files), "anchors": added}


def register_candidates(root, payload: dict) -> dict:
    """登记发明点候选表（八字段）。证据锚点必须真实存在于源图谱。"""
    root = Path(root)
    case = load_case(root)
    require_audited(root, case)
    sm = _load_source_map(root)
    known = {a["anchor"] for a in sm["anchors"]}
    gaps = []
    rows = []
    for i, c in enumerate(payload.get("candidates") or []):
        for field in schema.CANDIDATE_FIELDS:
            if c.get(field) in (None, "", []):
                gaps.append(f"候选第 {i + 1} 条缺字段 {field}"
                            "（候选表八字段必填）")
        for ev in c.get("evidence") or []:
            anchor = ev.get("anchor") if isinstance(ev, dict) else ev
            if anchor not in known:
                gaps.append(f"候选 {c.get('candidate_id')!r} 证据锚点 "
                            f"{anchor!r} 不在源图谱内（虚锚，LP-02）")
    if gaps:
        raise PatentError(gaps)
    data = load_yaml_or(root, "candidates",
                        {"kind": "light-patent/candidates",
                         "case_id": case["case_id"], "candidates": [],
                         "selected": None})
    data["candidates"].extend(payload.get("candidates") or [])
    if payload.get("selected"):
        ids = {c["candidate_id"] for c in data["candidates"]}
        if payload["selected"] not in ids:
            raise PatentError([f"选定候选 {payload['selected']!r} 不在候选表内"])
        data["selected"] = payload["selected"]
    dump_yaml(case_path(root, "candidates"), data)
    if case["status"] == "audited":
        set_status(root, case, "mined", "light-patent mine")
    return {"candidates": len(data["candidates"]),
            "selected": data.get("selected")}


def write_disclosure(root, source_file) -> dict:
    """落交底书工作副本（intake/disclosure.md）。内容由模型按规程
    撰写后经此登记，本命令只作落盘与状态推进，不代写正文。"""
    root = Path(root)
    case = load_case(root)
    require_audited(root, case)
    text = read_text(source_file)
    if not text.strip():
        raise PatentError(["交底书来源文件为空"])
    target = case_path(root, "disclosure")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {"path": str(target), "chars": len(text)}
