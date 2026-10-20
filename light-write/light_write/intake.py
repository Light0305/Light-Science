"""W0 承接：conclusion_card + Literature verified 集 → 快照与主张登记初建。

纪律要点（LEARNING 约束 3/11/12 + 草案 §1.1/§1.2 + Analysis 期通则）：
- 快照后上游变动 → 承接失效：intake 落 conclusion_card 文件哈希、卡内
  主张集哈希、数字溯源表哈希、verified 集哈希；validate 逐项复算。
- 上游状态如实落字：Analysis 包 status 与 review_status（含
  REVIEW_UNAVAILABLE）原样进快照；非 delivered 时按降级口径登记
  （writable_form 上限照常由规则导出，untested 主张只许 limitations_only/omit）。
- 主张规范文本若上游未给结构化值，登记期留空并落 gap，不许临场编造文本
  （承 Analysis SESOI 教训：上游只有文本、下游需结构化值时登记快照，
  缺失就点名，不猜）。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import schema
from .project import FILES, load_package, save_claims, save_lock, save_manuscript
from .render import cite_key_for, render_bib
from .util import (
    claim_text_hash, component_hash, dump_yaml, load_structured, sha256_file,
    sha256_text, today, utcnow,
)


class IntakeError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ------------------------------------------------------------- 卡内一致性

_COUNT_KEYS = ["positive", "negative", "null", "undetermined", "untested"]


def _card_value_decimals(value) -> int:
    """卡内值的呈现精度（小数位数）：指针目标值按此精度舍入后比对。"""
    s = repr(value)
    if "e" in s or "E" in s:
        return 10
    return len(s.split(".")[1]) if "." in s else 0


def check_card_consistency(card: dict, card_path) -> tuple:
    """WRT-D05 卡内一致性校验：只验结论卡自洽，不重算 Analysis 模型。

    返回 (gaps, summary)。卡内自查恒执行；卡同目录有 spec_results.jsonl
    时追加指针目标值比对（effect_size 行按 (登记行, spec_id) 定位，
    目标值按卡内值呈现精度半上舍入后比对）；无该文件记 not_available，
    诚实未核、不拦承接。
    """
    from decimal import ROUND_HALF_UP, Decimal

    gaps = []
    # ---- 主张行判定汇总（同行在不同主张下判定冲突 = 卡内不一致）
    line_verdicts = {}
    for claim in card.get("claims") or []:
        for line, verdict in (claim.get("line_verdicts") or {}).items():
            if line in line_verdicts and line_verdicts[line] != verdict:
                gaps.append(
                    f"卡内不一致：登记行 {line} 在不同主张下判定冲突"
                    f"（{line_verdicts[line]} vs {verdict}）")
            line_verdicts[line] = verdict
    # ---- counts 对账（counts 在场才查，缺失由 Analysis 侧口径负责）
    counts = card.get("counts")
    if isinstance(counts, dict):
        tally = {}
        for v in line_verdicts.values():
            tally[v] = tally.get(v, 0) + 1
        for key in _COUNT_KEYS:
            if key in counts and counts[key] != tally.get(key, 0):
                gaps.append(
                    f"卡内不一致：counts.{key} 登记为 {counts[key]}，"
                    f"但主张 line_verdicts 实计 {tally.get(key, 0)}")
        if "total_lines" in counts and \
                counts["total_lines"] != len(line_verdicts):
            gaps.append(
                f"卡内不一致：counts.total_lines 登记为 "
                f"{counts['total_lines']}，但 line_verdicts 登记行数实计 "
                f"{len(line_verdicts)}")
    # ---- 溯源行自查
    rows = card.get("number_provenance") or []
    seen = {}
    summary_unclaimed = []
    for i, row in enumerate(rows):
        where = f"number_provenance[{i}]"
        rid = row.get("registry_line_id")
        vl = row.get("verdict_line")
        qty = row.get("quantity")
        value = row.get("value")
        if rid and line_verdicts and rid not in line_verdicts:
            # 不拦：Analysis 溯源行可对应无主张映射的登记行（claim_ref
            # 为空的行也有判定与数字），卡未声称行集封闭——只在摘要
            # 留痕，真悬空由 spec 指针层与门二溯源解析兜底
            summary_unclaimed.append(i)
        if vl and rid and not str(vl).startswith(f"{rid}#"):
            gaps.append(
                f"卡内不一致：{where} 判定行指针 {vl!r} 与登记行 {rid} "
                "不匹配（指针应以 '<登记行>#' 开头）")
        key = (vl, qty)
        if key in seen and seen[key] != value:
            gaps.append(
                f"卡内不一致：{where} 与先行同为 (判定行 {vl}, 量 {qty}) "
                f"却值不同（{seen[key]!r} vs {value!r}）：同指针两值")
        seen[key] = value
        if qty == "no_numeric_result":
            if value is not None:
                gaps.append(
                    f"卡内不一致：{where} 量为 no_numeric_result 但 value "
                    f"非空（{value!r}）：无数字行不许带值")
        elif value is not None:
            if not row.get("spec_id"):
                gaps.append(
                    f"卡内不一致：{where}（{vl}/{qty}）有值却缺 spec_id "
                    "指针：登记数字须有卡内 spec 指针可核")
            if not row.get("calc_provenance"):
                gaps.append(
                    f"卡内不一致：{where}（{vl}/{qty}）有值却缺 "
                    "calc_provenance 指针")
    # ---- 指针目标值比对（spec_results.jsonl 与卡同目录时）
    summary = {"rows": len(rows), "lines": len(line_verdicts),
               "spec_results": "not_available", "spec_rows_checked": 0,
               "unclaimed_provenance_rows": summary_unclaimed,
               "p_ab_rows": sum(1 for r in rows
                                if r.get("quantity") == "p_ab")}
    sibling = Path(card_path).parent / "spec_results.jsonl" \
        if card_path else None
    if sibling is not None and sibling.exists():
        try:
            spec_index = {}
            for line in sibling.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                srow = json.loads(line)
                spec_index[(srow.get("registry_line_id"),
                            srow.get("spec_id"))] = srow
        except Exception as e:
            gaps.append(f"卡内核查未成：spec_results.jsonl 不可读（{e}），"
                        "指针目标无从核对，不许带病承接")
            summary["spec_results"] = "unreadable"
            return gaps, summary
        summary["spec_results"] = "checked"
        for i, row in enumerate(rows):
            if row.get("quantity") != "effect_size" \
                    or row.get("value") is None:
                continue
            target = spec_index.get((row.get("registry_line_id"),
                                     row.get("spec_id")))
            if target is None:
                gaps.append(
                    f"卡内不一致：number_provenance[{i}] 指针 "
                    f"({row.get('registry_line_id')}, {row.get('spec_id')}) "
                    "在 spec_results 中落空：登记数字与所指 spec 结果对不上")
                continue
            spec_val = (target.get("effect_size") or {}).get("value")
            if spec_val is None:
                gaps.append(
                    f"卡内不一致：number_provenance[{i}] 所指 spec 结果"
                    "无 effect_size 值，卡内却登记了值")
                continue
            decimals = _card_value_decimals(row["value"])
            expected = float(Decimal(str(spec_val)).quantize(
                Decimal("1e-%d" % decimals), rounding=ROUND_HALF_UP))
            if abs(expected - float(row["value"])) > 1e-9:
                gaps.append(
                    f"卡内不一致：number_provenance[{i}] 登记值 "
                    f"{row['value']} 与所指 spec 结果值 {spec_val} 按呈现"
                    f"精度（{decimals} 位）舍入后不一致")
            summary["spec_rows_checked"] += 1
    return gaps, summary


# ------------------------------------------------------------- 贡献草案

def claims_source_hash(claim_rows) -> str:
    """上游主张集（id + 规范文本）的哈希：贡献回执与漂移检出共用口径。"""
    return component_hash([
        {"claim_id": r.get("claim_id"), "claim_text": r.get("claim_text")}
        for r in claim_rows or []])


def build_contribution_draft(claim_rows) -> dict:
    """由上游主张规范文本组装主导贡献陈述草案（WRT-D04）。

    草案 = 各主张规范文本按登记序拼接；无文本的主张不入草案（已在
    intake gaps 点名）。草案未经用户签认不具任何效力（status=unsigned）。
    """
    texts = [r["claim_text"] for r in claim_rows if r.get("claim_text")]
    draft = " ".join(texts) if texts else None
    return {
        "statement_draft": draft,
        "draft_hash": sha256_text(draft) if draft else None,
        "source_claims_hash": claims_source_hash(claim_rows),
        "derived_claim_ids": [r["claim_id"] for r in claim_rows],
        "status": "unsigned",
        "receipt": None,
    }


class ContributionError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def confirm_contribution(root, by, statement=None, drift_note=None) -> dict:
    """用户签认主导贡献陈述 → 落回执（WRT-D04）。

    statement 缺省取草案原文；与草案不一致时必须带 drift_note 点名
    差异（陈述与上游主张不一致时点名，不许静默改写）。回执含陈述哈希
    与签认时点的主张集哈希，事后改陈述或上游主张漂移由 validate 检出。
    """
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        raise ContributionError(["稿件包不存在（先 init）"])
    contribution = manuscript.get("contribution")
    if not contribution:
        raise ContributionError(
            ["贡献陈述草案不存在：先跑 intake 生成草案再签认"])
    draft = contribution.get("statement_draft")
    final = statement if statement is not None else draft
    if final is None or not str(final).strip():
        raise ContributionError(
            ["贡献陈述为空：草案无文本（上游主张未给规范文本）时须由用户"
             "亲笔给出陈述文本再签认，不许工具代拟"])
    drift = final != draft
    if drift and not drift_note:
        raise ContributionError(
            ["签认陈述与承接草案不一致：须以 drift_note 点名差异"
             "（改了哪条主张的口径、为什么），不许静默改写上游主张"])
    claim_rows = (pkg["claims"] or {}).get("claims") or []
    receipt = {
        "statement": final,
        "statement_hash": sha256_text(final),
        "draft_hash": contribution.get("draft_hash"),
        "drift_from_draft": drift,
        "drift_note": drift_note if drift else None,
        "confirmed_by": by,
        "confirmed_at": today(),
        "source_claims_hash": claims_source_hash(claim_rows),
    }
    contribution["status"] = "signed"
    contribution["receipt"] = receipt
    manuscript["contribution"] = contribution
    save_manuscript(root, manuscript)
    return receipt


# ------------------------------------------------------------- 文献集快照

def _raw_literature_rows(path: Path):
    """读 Literature 导出：候选池 JSONL 行 / JSON 列表 / {entries: [...]}。"""
    data = load_structured(path)
    if isinstance(data, dict):
        data = data.get("entries") or data.get("studies") or []
    if not isinstance(data, list):
        raise IntakeError([f"文献导出形态不可识别（须为条目列表）：{path}"])
    return data


def _map_retraction(raw_status, doi):
    """Literature retraction_status → Write 撤稿四态（差异 c 口径）。"""
    raw = (raw_status or "").strip().lower()
    if raw == "retracted":
        return "retracted"
    if not doi:
        return "no_doi"
    if raw in ("clear", "clean"):
        return "clean"
    return "unknown"


def verified_snapshot(literature_path):
    """从 Literature 导出提取 verified 条目并规范化（intake 与 validate 共用）。

    只收 verification.identity_status == verified 的条目；未核实条目
    不进快照（成稿层硬规则：未核实文献一律不用）。返回 (entries, set_hash)。
    """
    rows = _raw_literature_rows(Path(literature_path))
    entries = []
    for row in rows:
        verification = row.get("verification") or {}
        if verification.get("identity_status") != "verified":
            continue
        entry_id = (row.get("study_id") or row.get("paper_id")
                    or row.get("entry_id") or row.get("doi"))
        if not entry_id:
            continue
        doi = row.get("doi")
        entries.append({
            "entry_id": entry_id,
            "doi": doi,
            "title": row.get("title"),
            "authors": row.get("authors") or [],
            "year": row.get("year"),
            "venue": row.get("venue"),
            "entry_type": row.get("type"),
            "verified_by": verification.get("checked_by")
                           or "light-literature verify-identity",
            "verified_at": verification.get("checked_at"),
            "retraction_state": _map_retraction(
                verification.get("retraction_status"), doi),
            "retraction_raw": verification.get("retraction_status"),
        })
    entries.sort(key=lambda e: e["entry_id"])
    return entries, component_hash(entries)


# ------------------------------------------------------------------ 承接

def run_intake(root, conclusion_card_path, literature_path, by=None) -> dict:
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        raise IntakeError(["稿件包不存在（先 init）"])
    card_path = Path(conclusion_card_path)
    if not card_path.exists():
        raise IntakeError([f"conclusion_card 不存在：{card_path}"])
    lit_path = Path(literature_path)
    if not lit_path.exists():
        raise IntakeError([f"Literature verified 导出不存在：{lit_path}"])

    card = load_structured(card_path)
    if not isinstance(card, dict) or "claims" not in card:
        raise IntakeError(["conclusion_card 形态不可识别（缺 claims）"])

    # ---- 卡内一致性校验（WRT-D05）：卡本身自相矛盾 → 拦 intake 点名，
    # 不许带病承接（门二三方对账只能查「一致地错」之外的问题）
    card_gaps, card_consistency = check_card_consistency(card, card_path)
    if card_gaps:
        raise IntakeError(card_gaps)

    language = manuscript.get("language")
    entries, set_hash = verified_snapshot(lit_path)

    # ---- 主张登记初建
    claim_rows = []
    gaps = []
    for claim in card.get("claims") or []:
        analysis_ref = claim.get("claim_id")
        upstream_status = claim.get("support")
        grade = claim.get("grade")
        if upstream_status not in schema.UPSTREAM_STATUSES:
            gaps.append(f"主张 {analysis_ref} 上游状态 {upstream_status!r} "
                        "不在词表，承接拒绝")
            continue
        if grade not in schema.STRENGTH_GRADES:
            gaps.append(f"主张 {analysis_ref} 强度档 {grade!r} 不在词表，承接拒绝")
            continue
        ceiling = schema.writable_ceiling(upstream_status, grade)
        text = claim.get("text") or claim.get("statement") or claim.get("title")
        if not text:
            gaps.append(f"主张 {analysis_ref} 上游未给规范文本：text_hash 未登记，"
                        "登记期留空待补（不许临场编造）")
        claim_rows.append({
            "claim_id": analysis_ref,
            "analysis_claim_ref": analysis_ref,
            "upstream_status": upstream_status,
            "strength_grade": grade,
            "cap_reason": claim.get("cap_reason"),
            "line_verdicts": claim.get("line_verdicts") or {},
            "writable_ceiling": ceiling,
            # 三选一落字：untested/undetermined 的合法形态在 intake 时点即登记，
            # 初值取上限形态；降格选择（如改 omit）须改登记并留 form_choice_note。
            "writable_form": ceiling,
            "form_choice_note": f"intake 按规则表导出上限形态（{upstream_status}×{grade}）",
            "wording_ceiling": schema.wording_ceiling_for(language, grade),
            "claim_text": text,
            "text_hash": claim_text_hash(text) if text else None,
            "manuscript_locations": [],
            "evidence_refs": [
                {"kind": "analysis_verdict_lines",
                 "refs": sorted((claim.get("line_verdicts") or {}).keys())},
            ],
        })
    if gaps and not claim_rows:
        raise IntakeError(gaps)

    # ---- 引用锁快照（verified 集全量入锁；起草期引用子集在 Phase 2 收窄）
    taken = set()
    lock_entries = []
    for e in entries:
        lock_entries.append({
            "key": cite_key_for(e, taken),
            "entry_id": e["entry_id"],
            "doi": e["doi"],
            "title": e["title"],
            "authors": e["authors"],
            "year": e["year"],
            "venue": e["venue"],
            "entry_type": e["entry_type"],
            "verified_by": e["verified_by"],
            "verified_at": e["verified_at"],
            "retraction_state": e["retraction_state"],
            "retraction_note": None,
            "entry_hash": component_hash(e),
        })
    lock = {
        "kind": "light-write/references-lock",
        "version": "1.0",
        "generated_at": utcnow(),
        "source": {
            "path": str(lit_path),
            "set_hash": set_hash,
            "entry_count": len(lock_entries),
        },
        "entries": lock_entries,
    }
    save_lock(root, lock)
    (root / FILES["bib"]).write_text(render_bib(lock_entries), encoding="utf-8")

    # ---- 承接快照落登记头
    review = card.get("review") or {}
    upstream_flags = []
    analysis_status = card.get("status")
    if analysis_status != "delivered":
        upstream_flags.append(
            f"analysis_not_delivered: 上游结论包状态为 {analysis_status}"
            "（非 delivered），主张按降级口径登记")
    if review.get("review_status"):
        upstream_flags.append(
            f"analysis_review_status: {review.get('review_status')}（原样落字）")
    manuscript["intake"] = {
        "conclusion_card": {
            "path": str(card_path),
            "sha256": sha256_file(card_path),
            "analysis_id": card.get("analysis_id"),
            "analysis_status": analysis_status,
            "exported_at": card.get("exported_at"),
            "review_status": review.get("review_status"),
            "review_reason": review.get("reason"),
        },
        "card_claims_hash": component_hash(card.get("claims") or []),
        "number_provenance_hash": component_hash(
            card.get("number_provenance") or []),
        "number_provenance_count": len(card.get("number_provenance") or []),
        "claim_ids": [r["claim_id"] for r in claim_rows],
        "card_consistency": card_consistency,
        "literature": {
            "source_path": str(lit_path),
            "set_hash": set_hash,
            "entry_count": len(lock_entries),
        },
        "intake_at": today(),
        "intake_by": by or "light-write intake",
        "upstream_flags": upstream_flags,
    }
    # ---- 贡献确认回执的草案（WRT-D04）：承接 Design 主张后生成主导
    # 贡献陈述草案，待用户签认（confirm-contribution）；草案由上游主张
    # 规范文本机械组装，不许临场改写成「更好听」的版本
    manuscript["contribution"] = build_contribution_draft(claim_rows)
    save_manuscript(root, manuscript)
    save_claims(root, {"claims": claim_rows})
    return {
        "claims_registered": [r["claim_id"] for r in claim_rows],
        "writable_forms": {r["claim_id"]: r["writable_form"] for r in claim_rows},
        "literature_entries_locked": len(lock_entries),
        "upstream_flags": upstream_flags,
        "card_consistency": card_consistency,
        "gaps": gaps,
    }
