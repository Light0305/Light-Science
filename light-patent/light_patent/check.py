"""P4 审核：确定性检查器 + 红队记录 + 交付分级。

双层缺一不可（LP-11）：确定性脚本检查先行，红队两队（权要红队
攻新颖性/创造性/客体，整包红队攻跨文件一致性与哈希时序）随后；
检查报告自报覆盖与未查项。ERROR 未清或红队缺位，交付等级只许
incomplete draft，禁止措辞放行。检查绑定工件哈希：检查后改稿，
validate 即点名 STALE。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .project import (
    PatentError, case_path, load_case, load_ledger, load_yaml_or,
    save_ledger, set_status,
)
from .util import dump_yaml, read_text, sha256_text, today

_SENTENCE_END = "。"
_ANTECEDENT_RE = re.compile(r"所述([一-鿿]{1,8})")


def _claims_text(root) -> list:
    """从 claims.md 解析逐条权要文本（编号行）。"""
    text = read_text(case_path(root, "claims_md"))
    claims, current = [], None
    for line in text.splitlines():
        m = re.match(r"^(\d+)\.\s*(.*)$", line.strip())
        if m:
            current = {"claim_no": int(m.group(1)), "text": m.group(2)}
            claims.append(current)
        elif current is not None and line.strip():
            current["text"] += line.strip()
    return claims


def run_check(root) -> dict:
    root = Path(root)
    case = load_case(root)
    findings = []  # {check_id, level: ERROR/WARN, detail}

    def err(cid, detail):
        findings.append({"check_id": cid, "level": "ERROR", "detail": detail})

    def warn(cid, detail):
        findings.append({"check_id": cid, "level": "WARN", "detail": detail})

    claims_data = load_yaml_or(root, "claims", None)
    spec = read_text(case_path(root, "specification_md"))
    abstract = read_text(case_path(root, "abstract_md"))
    claims_text = _claims_text(root)
    checked, not_checked = [], []

    if not claims_data or not claims_text:
        err("C-00", "权要未登记或权利要求书未生成：检查无对象")
        claims_data = claims_data or {"claims": []}
    else:
        checked.append("claims_structure_and_text")

    # C-01 编号连续
    nos = [c["claim_no"] for c in claims_data.get("claims") or []]
    if nos and nos != list(range(1, len(nos) + 1)):
        err("C-01", f"权要编号不连续：{nos}")

    # C-02 单句号 + C-03 不确定词
    for c in claims_text:
        body = c["text"].rstrip()
        if body.count(_SENTENCE_END) != 1 or not body.endswith(_SENTENCE_END):
            err("C-02", f"权要 {c['claim_no']} 非单句号形态"
                        f"（句号数 {body.count(_SENTENCE_END)}）：每条权要只许一句话")
        for w in schema.UNCERTAIN_WORDS:
            if w in body:
                err("C-03", f"权要 {c['claim_no']} 含不确定词「{w}」")

    # C-04 引用规则：多项引用不得作为多项引用的基础
    by_no = {c["claim_no"]: c for c in claims_data.get("claims") or []}
    for c in claims_data.get("claims") or []:
        deps = c.get("depends_on") or []
        if len(deps) > 1:
            for d in deps:
                if len((by_no.get(d) or {}).get("depends_on") or []) > 1:
                    err("C-04", f"权要 {c['claim_no']} 多项引用了多项从属"
                                f"权要 {d}：多项从属权要不得再作多项引用基础")

    # C-05 先行基础（启发式）：所述 X 之前应有引入
    for c in claims_text:
        introduced = set()
        for m in _ANTECEDENT_RE.finditer(c["text"]):
            term = m.group(1)
            head = term[:2]
            before = c["text"][:m.start()]
            if not any(kw in before for kw in
                       (f"一{head}", f"一个{head}", f"一种{head}", f"所述{head}")):
                if head not in introduced:
                    warn("C-05", f"权要 {c['claim_no']}「所述{term}」未见"
                                 "先行引入（启发式，需人工复核）")
                    introduced.add(head)
    checked.append("antecedent_basis_heuristic")

    # C-06 名称长度 / C-07 摘要字数
    if len(case.get("title") or "") > schema.TITLE_WARN_CHARS:
        warn("C-06", f"发明名称 {len(case['title'])} 字超经验上限 "
                     f"{schema.TITLE_WARN_CHARS}：考虑收窄")
    abstract_body = re.sub(r"^#.*$", "", abstract, flags=re.M).strip()
    if abstract_body and len(abstract_body) > schema.ABSTRACT_MAX_CHARS:
        err("C-07", f"摘要 {len(abstract_body)} 字超上限 "
                    f"{schema.ABSTRACT_MAX_CHARS} 字")
    elif not abstract_body:
        warn("C-07", "摘要未落字")
    checked.append("title_and_abstract")

    # C-08 附图标记一致：正文引用 图N 须有图登记；标记须在说明书出现
    numerals = load_yaml_or(root, "numerals", {"numerals": []})
    marks = {r["mark"] for r in numerals.get("numerals") or []}
    spec_figs = set(re.findall(r"图\s*(\d+)", spec))
    for fignum in sorted(spec_figs):
        if not any(m.startswith(fignum) or fignum in m for m in marks):
            warn("C-08", f"说明书引用图{fignum} 但附图标记登记未见对应图号")
    for r in numerals.get("numerals") or []:
        if r["mark"] not in spec and r["name"] not in spec:
            warn("C-08", f"附图标记 {r['mark']}（{r['name']}）未在说明书中出现/解释")
    checked.append("numeral_consistency")

    # C-09 支持覆盖：支持映射每行须有说明书章节或锚点；说明书镜像独权
    support = load_yaml_or(root, "support_map", {"rows": []})
    for row in support.get("rows") or []:
        if row["support_state"] == "unsupported":
            err("C-09", f"权要 {row['claim_no']} 特征 {row['feature_ref']} "
                        "支持状态 unsupported 却已入权要")
        if not row.get("spec_section") and not row.get("anchors"):
            err("C-09", f"权要 {row['claim_no']} 特征 {row['feature_ref']} "
                        "支持映射无章节无锚点（说明书未镜像）")
    checked.append("support_coverage")

    # C-10 占位符与缺口对账：说明书「待补充：」须逐条登记在 gaps
    gaps_data = load_yaml_or(root, "gaps", {"gaps": []})
    registered = {(g.get("location") or "") + (g.get("item") or "")
                  for g in gaps_data.get("gaps") or []}
    placeholders = re.findall(r"待补充：([^\n。；]+)", spec)
    for ph in placeholders:
        if not any(ph.strip() in r or r in ph.strip() for r in registered if r):
            err("C-10", f"说明书占位符「待补充：{ph.strip()}」未登记进缺口清单")
    checked.append("placeholder_gap_reconciliation")

    # C-11 AI 充分公开 + C-12 伦理审查登记
    if case.get("ai_related"):
        registered_items = set()
        ai_block = (load_yaml_or(root, "claims", {}) or {}).get("ai_sufficiency") or {}
        registered_items = set(ai_block.get("items") or [])
        missing = [i for i in schema.AI_SUFFICIENCY_ITEMS
                   if i not in registered_items]
        for item in missing:
            err("C-11", f"AI 类案件充分公开清单缺项 {item}（84 号令 "
                        "6.3.1：模块/层级连接/训练步骤参数/输入输出设置须落字）")
        checked.append("ai_sufficiency_84order")
    else:
        not_checked.append("ai_sufficiency（非 AI 类案件，不适用）")
    ethics = (load_yaml_or(root, "audit", {}) or {}).get("ethics_review")
    flags = case.get("ethics_flags") or []
    if flags and not ethics:
        err("C-12", "案件命中伦理触发面（数据采集/标签管理/规则设置/"
                    "推荐决策）但未登记伦理审查结论（84 号令 6.1.1，"
                    "专利法第 5 条第 1 款）")
    checked.append("ethics_registration")

    # C-13 申报副本洁净：filing 存在时复查过程词
    filing_dir = case_path(root, "filing_dir")
    report_file = filing_dir / "strip_report.yaml"
    if report_file.exists():
        from .util import load_structured
        rep = load_structured(report_file) or {}
        for f in rep.get("files") or []:
            if f.get("process_hits"):
                err("C-13", f"申报副本 {f['file']} 过程词未剥净："
                            f"{f['process_hits']}")
        checked.append("filing_cleanliness")
    else:
        not_checked.append("filing_cleanliness（申报副本未生成）")

    errors = [f for f in findings if f["level"] == "ERROR"]
    redteam = load_yaml_or(root, "redteam", None)
    red_ok = bool(redteam and redteam.get("claims_team")
                  and redteam.get("package_team"))
    grade = "deliverable_draft" if not errors and red_ok else "incomplete_draft"
    hashes = {}
    for key in ("claims_md", "specification_md", "abstract_md"):
        p = case_path(root, key)
        if p.exists():
            hashes[key] = sha256_text(read_text(p))
    report = {
        "kind": "light-patent/check-report",
        "case_id": case["case_id"],
        "checked_at": today(),
        "findings": findings,
        "errors": len(errors),
        "warnings": len([f for f in findings if f["level"] == "WARN"]),
        "coverage": {"checked": checked, "not_checked": not_checked},
        "redteam_present": red_ok,
        "delivery_grade": grade,
        "artifact_hashes": hashes,
        "disclaimers": [schema.DRAFT_DISCLAIMER],
    }
    dump_yaml(case_path(root, "check_report"), report)
    if grade == "deliverable_draft" and case["status"] == "drafted":
        set_status(root, case, "checked", "light-patent check")
    ledger = load_ledger(root)
    ledger.setdefault("version_chain", []).append({
        "at": today(), "event": "check",
        "grade": grade, "artifact_hashes": hashes})
    save_ledger(root, ledger)
    return report


def register_redteam(root, payload: dict) -> dict:
    """登记红队两队记录。payload: {claims_team: {findings, checked,
    not_checked}, package_team: {...}}。两队缺一不可（LP-11）。"""
    root = Path(root)
    load_case(root)
    gaps = []
    for team in ("claims_team", "package_team"):
        rec = payload.get(team) or {}
        if not rec.get("checked"):
            gaps.append(f"红队 {team} 缺覆盖自报 checked 清单")
        if "findings" not in rec:
            gaps.append(f"红队 {team} 缺 findings 字段（无发现写空表）")
    if gaps:
        raise PatentError(gaps)
    dump_yaml(case_path(root, "redteam"), {
        "kind": "light-patent/redteam", "case_id": load_case(root)["case_id"],
        "recorded_at": today(), **payload})
    return {"teams": ["claims_team", "package_team"]}
