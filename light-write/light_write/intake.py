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
    today, utcnow,
)


class IntakeError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


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
        "literature": {
            "source_path": str(lit_path),
            "set_hash": set_hash,
            "entry_count": len(lock_entries),
        },
        "intake_at": today(),
        "intake_by": by or "light-write intake",
        "upstream_flags": upstream_flags,
    }
    save_manuscript(root, manuscript)
    save_claims(root, {"claims": claim_rows})
    return {
        "claims_registered": [r["claim_id"] for r in claim_rows],
        "writable_forms": {r["claim_id"]: r["writable_form"] for r in claim_rows},
        "literature_entries_locked": len(lock_entries),
        "upstream_flags": upstream_flags,
        "gaps": gaps,
    }
