"""状态机：intake → outlined → drafted → audited → submission_ready。

五段门（Phase 2 全接通）：
- intake→outlined：承接快照 + 主张登记 + 模板记录 + 验收合同冻结
  （拍板⑥硬门；contested 降级落字，后续不许 submission_ready）。
- outlined→drafted：逐节稿齐备（按模板栏目序列）+ 三类标记全量校验 +
  主张/数字锚定覆盖 + 图表占位对齐 + lock 引用子集收窄清单（只列不删）。
- drafted→audited：审计四门全过且产物未 STALE（audit 模块出判定，
  本模块把门——审计与把门分离，约束 13）。
- audited→submission_ready：四门新鲜全过 + 落点底线层全 addressed +
  披露按刊生成齐备 + 声明无 absent + 合同非 contested + 跨模型复核
  收据（REVIEW_UNAVAILABLE → 落 blocked 原因，停在本段不许置真，
  与 Idea/Design/Analysis 同构）。
门不过 → 停在当前段并逐项点名，不许整体放行（约束 13/15）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .audit import audit_status, load_audit_report
from .disclose import disclosures_status
from .figures import scan_intext_refs
from .project import (
    contract_content_hash, load_package, save_contract, save_manuscript,
    section_files,
)
from .util import today
from .validate import (
    CLAIM_MARK_RE, NUM_MARK_RE, _cited_keys, template_record_expired,
    validate_package,
)

NEXT_STATE = {
    "intake": "outlined",
    "outlined": "drafted",
    "drafted": "audited",
    "audited": "submission_ready",
}

# 模板栏目序列中不要求独立节文件的伪栏目（题名页与文献表由包级产物承担）
_NON_SECTION_ROLES = {"title", "references"}


class GateError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def freeze_contract(root) -> dict:
    """冻结验收合同：落内容哈希与状态（agreed / contested），同步登记头。"""
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        raise GateError(["稿件包不存在（先 init）"])
    contract = pkg["contract"]
    assertions = contract.get("assertions") or []
    if not assertions:
        raise GateError(["验收合同无断言：先在 acceptance_contract.yaml "
                         "登记 10–20 条只读终稿即可判定的断言"])
    bad = [a.get("assertion_id") for a in assertions
           if not a.get("text") or not a.get("checkable_via")
           or a.get("status") not in schema.ASSERTION_STATUSES]
    if bad:
        raise GateError([f"断言 {bad} 字段不全或状态不在词表，冻结拒绝"])
    contested = any(a.get("status") == "contested" for a in assertions)
    contract["status"] = "contested" if contested else "agreed"
    contract["frozen"] = True
    contract["frozen_at"] = today()
    contract["content_hash"] = contract_content_hash(contract)
    save_contract(root, contract)
    manuscript["acceptance_contract"] = {
        "file": "acceptance_contract.yaml",
        "status": contract["status"],
        "content_hash": contract["content_hash"],
    }
    if contested:
        manuscript["contract_contested"] = True
        manuscript["submission_blocked_reason"] = (
            "验收合同 contested（拍板⑥硬门）：稿件包降级，争议逐字留档待人类裁决，"
            "不许达 submission_ready")
    save_manuscript(root, manuscript)
    return {
        "status": contract["status"],
        "content_hash": contract["content_hash"],
        "assertions": len(assertions),
        "contested": contested,
    }


def _intake_gate_gaps(pkg) -> list:
    gaps = []
    manuscript = pkg["manuscript"]
    report = validate_package(pkg["root"])
    for e in report["errors"]:
        gaps.append(f"[{e['code']}] {e['message']}")
    if not manuscript.get("intake"):
        gaps.append("承接快照为空：先跑 intake（conclusion_card + verified 集）")
    if not (pkg["claims"] or {}).get("claims"):
        gaps.append("claims_register 为空：主张未登记不许进提纲")
    if manuscript.get("target_journal") is None:
        gaps.append("目标期刊模板记录未登记：先 register-template")
    elif pkg["template_record"] is not None and \
            template_record_expired(pkg["template_record"]):
        gaps.append("模板核查记录已过期：须按官方原文重新核查并重新登记"
                    "（过期记录不许静默沿用）")
    contract = pkg["contract"] or {}
    if not contract.get("frozen"):
        gaps.append("验收合同未冻结：先补断言并 freeze-contract（拍板⑥硬门）")
    contribution = manuscript.get("contribution") or {}
    if contribution.get("status") != "signed" \
            or not (contribution.get("receipt") or {}).get("statement_hash"):
        gaps.append("贡献确认回执未签认：先 confirm-contribution 由用户签认"
                    "主导贡献陈述（WRT-D04，未签认拦 outlined）")
    return gaps


def _validate_gaps(pkg) -> list:
    report = validate_package(pkg["root"])
    return [f"[{e['code']}] {e['message']}" for e in report["errors"]]


def _drafted_gate_gaps(pkg) -> list:
    gaps = _validate_gaps(pkg)
    manuscript = pkg["manuscript"]
    record = pkg["template_record"] or {}
    sequence = (record.get("C") or {}).get("section_sequence") or []
    files = section_files(pkg["root"])
    registered = {s.get("role"): s for s in manuscript.get("sections") or []}
    for role in sequence:
        if role in _NON_SECTION_ROLES:
            continue
        section = registered.get(role)
        if section is None:
            gaps.append(f"栏目 {role} 无登记节：逐节稿须按模板记录栏目序列"
                        "齐备（register 节并写节文件）")
        elif not (files.get(section.get("file")) or "").strip():
            gaps.append(f"栏目 {role} 的节文件 sections/{section.get('file')} "
                        "为空：节稿未成形")
    for s in manuscript.get("sections") or []:
        text = files.get(s.get("file"))
        if text is not None and not text.strip():
            gaps.append(f"节文件 sections/{s.get('file')} 为空")
    # 主张锚定覆盖：非 omit 须在场，omit 不许在场
    anchored_claims = set()
    anchored_nums = set()
    for text in files.values():
        anchored_claims.update(CLAIM_MARK_RE.findall(text))
        anchored_nums.update(NUM_MARK_RE.findall(text))
    for row in (pkg["claims"] or {}).get("claims") or []:
        cid = row.get("claim_id")
        if row.get("writable_form") == "omit":
            if cid in anchored_claims:
                gaps.append(f"主张 {cid} writable_form=omit 却在正文出现 "
                            "[claim:] 锚点：omit 主张不许入稿")
        elif cid not in anchored_claims:
            gaps.append(f"主张 {cid}（{row.get('writable_form')}）未在正文 "
                        "以 [claim:] 锚定：已登记主张须逐条入稿或改登记形态")
    for n in (pkg["numbers"] or {}).get("numbers") or []:
        if n.get("num_id") not in anchored_nums:
            gaps.append(f"数字 {n.get('num_id')} 已登记但正文无 [num:] 锚点")
    # 草稿标记纪律（D-W13）：未结 [directive:] 必改指令不许过 drafted 门
    from .ledger import scan_markers
    markers = scan_markers(pkg)
    for d in markers["open_directives"]:
        gaps.append(f"节 {d['section']} 有未结 [directive:] 必改指令"
                    f"「{d['text']}」：指令未执行不许过 drafted 门")
    for u in markers["unknown"]:
        gaps.append(f"节 {u['section']} 出现未注册草稿标记 {u['marker']}："
                    "标记分工外不许私设标记（D-W13 纯度纪律）")
    # 图表占位对齐
    refs = scan_intext_refs(pkg["root"])
    rows = {r.get("figure_id"): r
            for r in (pkg["figures"] or {}).get("figures") or []}
    for fid in refs:
        if fid not in rows:
            gaps.append(f"正文图标记 [fig:{fid}] 无 figures_manifest 登记行")
    for fid, row in rows.items():
        if row.get("status") in ("delivered", "backfilled") \
                and fid not in refs:
            gaps.append(f"图表 {fid} 已 {row.get('status')} 但正文无 "
                        "[fig:] 引用点")
    return gaps


def _lock_narrowing(pkg) -> dict:
    cited = _cited_keys(pkg)
    entries = (pkg["lock"] or {}).get("entries") or []
    cited_ids = set()
    for token in cited:
        if token.startswith("lit:"):
            cited_ids.add(token[4:])
        else:
            for e in entries:
                if e.get("key") == token:
                    cited_ids.add(e.get("entry_id"))
    uncited = [e for e in entries if e.get("entry_id") not in cited_ids]
    return {
        "at": today(),
        "cited_entry_ids": sorted(cited_ids),
        "uncited_entry_ids": [e.get("entry_id") for e in uncited],
        "uncited_keys": [e.get("key") for e in uncited],
        "note": "收窄只列清单不删条目：未被引条目保留在 lock 中"
                "（后续起草可能引用），bib 仍按全 lock 渲染",
    }


def _audit_gate_gaps(pkg) -> list:
    status = audit_status(pkg["root"])
    if not status["exists"]:
        return ["审计产物不存在：先跑 audit（四门全过才许进 audited）"]
    if status["stale"]:
        return ["审计产物 STALE：稿件在审计后已变动（哈希漂移），须重跑 audit"]
    if status["overall"] != "pass":
        report = load_audit_report(pkg["root"]) or {}
        from .ledger import allocation_check
        for i in allocation_check(pkg):
            if i["level"] == "error":
                gaps.append(f"正文分配纪律：{i['message']}")
        gaps = [f"审计总判定为 {status['overall']}：四门须全 pass"]
        for g in report.get("gates") or []:
            if g.get("status") != "pass":
                errs = [f["message"] for f in g.get("findings") or []
                        if f["level"] == "error"]
                gaps.append(f"{g.get('title')}：{g.get('status')}"
                            + (f"（{errs[0]}）" if errs else ""))
        return gaps
    gaps = _validate_gaps(pkg)
    from .ledger import allocation_check
    for i in allocation_check(pkg):
        if i["level"] == "error":
            gaps.append(f"正文分配纪律：{i['message']}")
    return gaps


def _ready_gate_gaps(pkg) -> list:
    gaps = _audit_gate_gaps(pkg)
    manuscript = pkg["manuscript"]
    for item in (pkg["checklist"] or {}).get("items") or []:
        if item.get("tier") == "baseline" and \
                item.get("status") != "addressed":
            gaps.append(f"落点底线层条目 {item.get('item_id')} 状态为 "
                        f"{item.get('status')}：底线层须全 addressed")
    for key, entry in (manuscript.get("declarations") or {}).items():
        if entry.get("state") == "absent":
            gaps.append(f"声明 {key} 仍为 absent：投稿前须补齐或改 na 落理由")
    dstatus = disclosures_status(pkg["root"])
    if dstatus["required"]:
        if not dstatus["complete"]:
            gaps.append("按刊披露未生成齐备：先跑 disclose"
                        "（全部披露位置落锚才算齐）")
        elif dstatus["stale"]:
            gaps.append("披露记录 STALE：政策或 use_log 已变动，须重跑 disclose")
    if manuscript.get("contract_contested"):
        gaps.append("验收合同 contested（拍板⑥硬门）："
                    + (manuscript.get("submission_blocked_reason") or "不许置真"))
    review = manuscript.get("review") or {}
    if not review.get("review_status"):
        gaps.append("缺成稿复核记录（review.review_status 为空）："
                    "先 review prepare 并落收据，或显式落 REVIEW_UNAVAILABLE")
    elif review["review_status"] == "REVIEW_UNAVAILABLE":
        gaps.append("REVIEW_UNAVAILABLE：跨模型复核不可用，停在 audited "
                    "不许置真（执行者不许自判自赦）")
    elif review.get("review_status") == "approved":
        packet = manuscript.get("review_packet") or {}
        from .project import manuscript_hash

        if review.get("manuscript_hash") != manuscript_hash(pkg["root"]):
            gaps.append("复核收据对应的稿件哈希已漂移（STALE）："
                        "稿改后须重新 review prepare + 复核")
        if not review.get("receipt_id"):
            gaps.append("复核记录缺收据号（receipt_id）")
    return gaps


def advance(root) -> dict:
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        raise GateError(["稿件包不存在（先 init）"])
    current = manuscript.get("status")
    if current not in NEXT_STATE:
        return {"advanced": False, "from": current, "to": None,
                "gaps": [f"状态 {current} 已是终态或不在状态机词表内"]}
    target = NEXT_STATE[current]
    if current == "intake":
        gaps = _intake_gate_gaps(pkg)
    elif current == "outlined":
        gaps = _drafted_gate_gaps(pkg)
    elif current == "drafted":
        gaps = _audit_gate_gaps(pkg)
    else:  # audited
        gaps = _ready_gate_gaps(pkg)
    result = {"advanced": False, "from": current, "to": target, "gaps": gaps}
    if gaps:
        if target == "submission_ready" and \
                any("REVIEW_UNAVAILABLE" in g for g in gaps) and \
                not manuscript.get("contract_contested"):
            manuscript["submission_blocked_reason"] = (
                "REVIEW_UNAVAILABLE：跨模型复核不可用，稿件停在 audited"
                "（与 Idea/Design/Analysis 同构降级，恢复后补复核再置真）")
            save_manuscript(root, manuscript)
        return result
    if target == "drafted":
        narrowing = _lock_narrowing(pkg)
        manuscript["lock_check"] = narrowing
        result["lock_narrowing"] = {
            "cited": narrowing["cited_entry_ids"],
            "uncited": narrowing["uncited_entry_ids"],
        }
    manuscript["status"] = target
    manuscript.setdefault("status_history", []).append(
        {"state": target, "at": today(), "by": "light-write advance"})
    save_manuscript(root, manuscript)
    result["advanced"] = True
    return result


def readiness_state(pkg, report) -> str:
    """投稿就绪三态（D-W09）：ready / ready_with_author_checks / blocked。"""
    manuscript = pkg["manuscript"]
    if report["errors"] or manuscript.get("contract_contested"):
        return "blocked"
    if manuscript.get("status") != "submission_ready":
        return "blocked"
    pending = [i for i in (pkg["checklist"] or {}).get("items") or []
               if i.get("applicability") == "author_input_needed"
               and i.get("status") != "addressed"]
    return "ready_with_author_checks" if pending else "ready"


def status_summary(root) -> dict:
    pkg = load_package(Path(root))
    manuscript = pkg["manuscript"]
    if manuscript is None:
        return {"exists": False}
    report = validate_package(root)
    from .ledger import scan_markers
    markers = scan_markers(pkg)
    return {
        "exists": True,
        "readiness": readiness_state(pkg, report),
        "evidence_readiness_open_fact_markers": markers["evidence_readiness_open"],
        "open_directives": len(markers["open_directives"]),
        "manuscript_id": manuscript.get("manuscript_id"),
        "title": manuscript.get("title"),
        "language": manuscript.get("language"),
        "status": manuscript.get("status"),
        "claims": len((pkg["claims"] or {}).get("claims") or []),
        "lock_entries": len((pkg["lock"] or {}).get("entries") or []),
        "numbers": len((pkg["numbers"] or {}).get("numbers") or []),
        "figures": len((pkg["figures"] or {}).get("figures") or []),
        "target_journal": (manuscript.get("target_journal") or {}).get("journal_name"),
        "contribution_signed": (
            (manuscript.get("contribution") or {}).get("status") == "signed"),
        "contract_status": (pkg["contract"] or {}).get("status"),
        "contract_contested": manuscript.get("contract_contested", False),
        "submission_blocked_reason": manuscript.get("submission_blocked_reason"),
        "audit": audit_status(root),
        "review_status": (manuscript.get("review") or {}).get("review_status"),
        "review_receipt": (manuscript.get("review") or {}).get("receipt_id"),
        "disclosures": len(manuscript.get("disclosures") or []),
        "figures_numbering_frozen": bool(
            ((pkg["figures"] or {}).get("numbering") or {}).get("frozen")),
        "validate_errors": report["error_count"],
        "validate_warnings": report["warning_count"],
    }
