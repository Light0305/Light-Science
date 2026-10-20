"""承接（F0）：从 Write 的 figures_manifest 或独立立项清单开立图包。

纪律（草案 §1.1 / §二 intake 门）：
- 承接落快照：源文件哈希 + 条目快照（figure_id / kind / 正文占位锚 /
  图注草案哈希）；快照后上游变动 → 承接失效须重新 intake，不许静默沿用。
- 承接同时开立：逐图状态行、图合同骨架、provenance 账行（约束 10：
  账随图合同开立）。
- 期刊合同随承接登记时先过数值校验（validate.check_journal_contract），
  非法合同不许入包；AI 政策快照字段缺项逐项点名（约束 8）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import (
    FILES, load_package, new_contract_stub, new_figure_row,
    new_provenance_row, save_contract, save_head, save_journal_contract,
    save_provenance,
)
from .util import load_structured, sha256_file, sha256_text, today
from .validate import Report, check_journal_contract


class IntakeError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _entries_from(data, source_kind: str):
    """把承接源规范化为条目列表；形态不对逐项点名。"""
    if isinstance(data, dict):
        rows = data.get("figures")
    else:
        rows = data
    if not isinstance(rows, list) or not rows:
        raise IntakeError(["承接源 figures 为空或形态不对（须为条目列表）"])
    entries = []
    gaps = []
    seen = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            gaps.append(f"承接条目 #{i + 1} 不是对象")
            continue
        fig_id = row.get("figure_id") or row.get("id") or row.get("fig_id")
        kind = row.get("kind")
        if not fig_id:
            gaps.append(f"承接条目 #{i + 1} 缺 figure_id")
            continue
        if fig_id in seen:
            gaps.append(f"承接条目 figure_id 重复：{fig_id}")
            continue
        seen.add(fig_id)
        if kind not in schema.INTAKE_KINDS:
            gaps.append(
                f"条目 {fig_id} 的 kind {kind!r} 不在 {schema.INTAKE_KINDS}"
                "（承接口径 data/schematic/table）")
            continue
        anchor = row.get("intext_anchor")
        if anchor is None and row.get("intext_refs"):
            refs = row["intext_refs"]
            anchor = refs[0] if isinstance(refs, list) and refs else None
        caption_hash = row.get("caption_text_hash") or row.get("caption_hash")
        if caption_hash is None:
            caption_text = row.get("caption") or row.get("caption_draft")
            if caption_text:
                caption_hash = sha256_text(str(caption_text))
        entries.append({
            "figure_id": fig_id,
            "kind": kind,
            "line": schema.KIND_TO_LINE[kind],
            "intext_anchor": anchor,
            "caption_draft_hash": caption_hash,
        })
    if gaps:
        raise IntakeError(gaps)
    return entries


def run_intake(root, manifest=None, standalone=None,
               journal_contract_file=None, template_record_id=None,
               ai_policy_file=None, by=None) -> dict:
    root = Path(root)
    pkg = load_package(root)
    head = pkg["head"]
    if head is None:
        raise IntakeError(["图包不存在（先 init）"])
    if head.get("status") != "intake":
        raise IntakeError([
            f"包状态为 {head.get('status')}，承接只许在 intake 段重做"])

    if bool(manifest) == bool(standalone):
        raise IntakeError(["承接源二选一：--manifest（Write 图表清单）"
                           "或 --standalone（独立立项清单）"])
    source = manifest or standalone
    source_kind = "write_manifest" if manifest else "standalone"
    source_path = Path(source)
    if not source_path.exists():
        raise IntakeError([f"承接源文件不存在：{source}"])
    entries = _entries_from(load_structured(source_path), source_kind)
    source_hash = sha256_file(source_path)

    # 期刊合同登记（可选）：先校验数值合法性，非法不许入包
    journal_registered = False
    if journal_contract_file:
        jc_path = Path(journal_contract_file)
        if not jc_path.exists():
            raise IntakeError([f"期刊合同文件不存在：{journal_contract_file}"])
        journal_contract = load_structured(jc_path)
        if not isinstance(journal_contract, dict):
            raise IntakeError(["期刊合同须为对象（字段见 SKILL §6）"])
        rep = Report()
        check_journal_contract(journal_contract, rep)
        if rep.errors:
            raise IntakeError(
                [f"[{e['code']}] {e['message']}" for e in rep.errors])
        journal_contract["registered"] = True
        save_journal_contract(root, journal_contract)
        journal_registered = True

    # AI 政策快照（可选）：字段缺项逐项点名（约束 8）
    ai_policy_snapshot = None
    if ai_policy_file:
        ap_path = Path(ai_policy_file)
        if not ap_path.exists():
            raise IntakeError([f"AI 政策快照文件不存在：{ai_policy_file}"])
        ai_policy_snapshot = load_structured(ap_path)
        if not isinstance(ai_policy_snapshot, dict):
            raise IntakeError(["AI 政策快照须为对象"])
        missing = [f for f in schema.AI_POLICY_FIELDS
                   if ai_policy_snapshot.get(f) is None
                   and f != "exhibit_exemption"]
        if ai_policy_snapshot.get("exhibit_exemption") is None \
                and "exhibit_exemption" not in ai_policy_snapshot:
            missing.append("exhibit_exemption（无豁免口径时显式记 null）")
        if missing:
            raise IntakeError(
                [f"AI 政策快照缺字段：{f}" for f in missing])
        ai_policy_snapshot.setdefault(
            "review_cycle_days", schema.POLICY_REVIEW_CYCLE_DAYS)

    if journal_registered or ai_policy_snapshot is not None \
            or template_record_id:
        head["target_journal"] = {
            "template_record_id": template_record_id,
            "journal_contract_ref": FILES["journal_contract"],
            "ai_policy_snapshot": ai_policy_snapshot,
        }

    head["intake"] = {
        "source_kind": source_kind,
        "source_ref": str(source),
        "source_hash": source_hash,
        "intake_at": today(),
        "by": by,
        "entries_snapshot": entries,
    }
    head["figures"] = [
        new_figure_row(e["figure_id"], e["kind"], e["line"]) for e in entries
    ]
    save_head(root, head)

    provenance = pkg["provenance"]
    provenance["entries"] = [
        new_provenance_row(e["figure_id"], e["line"]) for e in entries
    ]
    save_provenance(root, provenance)
    for e in entries:
        save_contract(root, new_contract_stub(e["figure_id"], e["line"]))

    return {
        "package_id": head["package_id"],
        "source_kind": source_kind,
        "source_hash": source_hash,
        "figures": [e["figure_id"] for e in entries],
        "journal_registered": journal_registered,
        "ai_policy_snapshot": ai_policy_snapshot is not None,
    }
