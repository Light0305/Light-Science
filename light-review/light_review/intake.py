"""承接（R0）：消费 Write 稿件包 + Analysis 结论包 + Figure 图包。

纪律（草案 §二/§四、RV-07/RV-12）：
- 承接时对三包各取快照哈希，登记头是唯一权威；任一上游文件事后变动，
  本轮评审标 STALE，法医与过门都先验快照、不许静默沿用旧快照；
- 约束缺项逐项点名，不许静默默认（强度档必须显式给）；
- 图包/目标刊记录可缺，但缺必须落字（对应边将全边 not assessable）；
- 隔离模式在此登记（R1 硬纪律）：degraded 必须带理由，做不到全规格
  就明说，delivered 时强制附降档声明。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import load_package, save_review
from .util import component_hash, load_structured, sha256_file, today

MANUSCRIPT_CORE = ["manuscript.yaml", "claims_register.yaml",
                   "numbers_ledger.yaml", "references.lock.json",
                   "figures_manifest.yaml"]
ANALYSIS_CORE = ["conclusions.yaml", "verdicts.jsonl", "spec_results.jsonl"]


class IntakeError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _hash_files(base: Path, relpaths) -> dict:
    out = {}
    for rel in relpaths:
        p = base / rel
        out[rel] = sha256_file(p) if p.exists() else None
    return out


def _manuscript_snapshot(path: Path) -> dict:
    sections = sorted(p.name for p in (path / "sections").glob("*.md")) \
        if (path / "sections").is_dir() else []
    rels = list(MANUSCRIPT_CORE) + [f"sections/{s}" for s in sections]
    files = _hash_files(path, rels)
    manuscript = load_structured(path / "manuscript.yaml") or {}
    return {
        "package_path": str(path),
        "files": files,
        "package_hash": component_hash(files),
        "manuscript_id": manuscript.get("manuscript_id"),
        "manuscript_status": manuscript.get("status"),
        "sections": sections,
    }


def _analysis_snapshot(path: Path) -> dict:
    files = _hash_files(path, ANALYSIS_CORE)
    return {
        "package_path": str(path),
        "files": files,
        "package_hash": component_hash(files),
    }


def _figure_snapshot(path: Path) -> dict:
    files = _hash_files(path, ["delivery.yaml"])
    return {
        "package_path": str(path),
        "files": files,
        "package_hash": component_hash(files),
    }


def run_intake(root, manuscript_path, analysis_path=None, figure_path=None,
               journal_name=None, target_record=None, intensity=None,
               seats_spec=None, want_decision=None,
               isolation_mode="full", isolation_reason=None,
               by="light-review intake") -> dict:
    """执行承接并冻结快照进登记头。缺口逐项点名，任一不过不落盘。"""
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    if review is None:
        raise IntakeError(["评审包不存在（先 init）"])
    if review.get("intake"):
        raise IntakeError(["承接快照已冻结：重承接请开新 round，不许覆盖"])

    gaps = []

    # ---- 约束：缺项点名，不许静默默认（草案 §二）
    if intensity is None:
        gaps.append("缺评审强度档（--intensity light|standard|thorough）："
                    "约束缺项不许静默默认")
    elif intensity not in schema.INTENSITIES:
        gaps.append(f"强度档 {intensity!r} 不在词表 {schema.INTENSITIES}")
    if isolation_mode not in schema.ISOLATION_MODES:
        gaps.append(f"隔离模式 {isolation_mode!r} 不在词表 "
                    f"{schema.ISOLATION_MODES}")
    elif isolation_mode == "degraded" and not (isolation_reason or "").strip():
        gaps.append("isolation_mode=degraded 必须登记理由（R1 硬纪律："
                    "做不到全规格就明说，不许冒充 full）")

    # ---- 稿件包（必承）
    manuscript = None
    if not manuscript_path:
        gaps.append("缺稿件包路径（--manuscript）：评审主对象不可缺")
    else:
        mp = Path(manuscript_path)
        if not (mp / "manuscript.yaml").exists():
            gaps.append(f"稿件包缺 manuscript.yaml：{mp}")
        else:
            missing = [rel for rel in MANUSCRIPT_CORE
                       if not (mp / rel).exists()]
            if missing:
                gaps.append("稿件包缺核心文件：" + "、".join(missing))
            else:
                manuscript = _manuscript_snapshot(mp)

    # ---- 结论包（必承：法医对账的证据侧）
    analysis = None
    if not analysis_path:
        gaps.append("缺结论包路径（--analysis）：主张↔证据、数字↔数字两边"
                    "的证据侧不可缺")
    else:
        ap = Path(analysis_path)
        missing = [rel for rel in ANALYSIS_CORE if not (ap / rel).exists()]
        if missing:
            gaps.append("结论包缺核心文件：" + "、".join(missing))
        else:
            analysis = _analysis_snapshot(ap)

    # ---- 图包（可缺，缺必须落字）
    figure = None
    figure_note = None
    if figure_path:
        fp = Path(figure_path)
        if not (fp / "delivery.yaml").exists():
            gaps.append(f"图包缺 delivery.yaml：{fp}")
        else:
            figure = _figure_snapshot(fp)
    else:
        figure_note = ("未承接图包：数字↔图边将全边 not_assessable"
                       "（覆盖自报如实登记，RV-07）")

    # ---- 目标刊（可缺记录，缺必须落字；易变事实只存指针，RV-17）
    target = {"name": journal_name, "record": None, "note": None}
    if target_record:
        rp = Path(target_record)
        if not rp.exists():
            gaps.append(f"目标刊核查记录不存在：{rp}")
        else:
            verified_at = None
            try:
                rec = load_structured(rp)
                if isinstance(rec, dict):
                    verified_at = rec.get("verified_at")
            except Exception:
                verified_at = None
            target["record"] = {
                "path": str(rp), "sha256": sha256_file(rp),
                "verified_at": verified_at,
            }
    if not journal_name and not target_record:
        target["note"] = ("未登记目标刊：领域门按刊事实与政策核查无源"
                          "（Phase 2 领域门将如实标未覆盖）")

    if gaps:
        raise IntakeError(gaps)

    review["intake"] = {
        "manuscript": manuscript,
        "analysis": analysis,
        "figure": figure,
        "figure_note": figure_note,
        "target_journal": target,
        "input_scope": {
            "manuscript_sections": manuscript["sections"],
            "packages": [p for p, v in
                         (("manuscript", manuscript), ("analysis", analysis),
                          ("figure", figure)) if v],
        },
        "intake_at": today(),
        "intake_by": by,
    }
    review["constraints"] = {
        "intensity": intensity,
        "seats_spec": seats_spec or "full",
        "want_decision": want_decision,
    }
    review["isolation"] = {"mode": isolation_mode,
                           "reason": isolation_reason}
    review["updated_at"] = today()
    save_review(root, review)
    return review["intake"]


def snapshot_drift(root) -> list:
    """重算承接快照哈希并与登记头比对，返回漂移描述（空 = 未漂移）。

    上游三包任一文件变动 → 本轮评审 STALE（草案 §四纪律，与 Write
    审计产物绑哈希同法）。文件消失同样算漂移。
    """
    pkg = load_package(root)
    review = pkg["review"] or {}
    intake = review.get("intake")
    if not intake:
        return ["承接快照未冻结（先 intake）"]
    drift = []
    for part, snap in (("manuscript", intake.get("manuscript")),
                       ("analysis", intake.get("analysis")),
                       ("figure", intake.get("figure"))):
        if not snap:
            continue
        base = Path(snap["package_path"])
        for rel, recorded in (snap.get("files") or {}).items():
            p = base / rel
            current = sha256_file(p) if p.exists() else None
            if current != recorded:
                drift.append(f"{part}/{rel} 哈希漂移（承接后上游已变动，"
                             "本轮评审 STALE）")
    target = (intake.get("target_journal") or {}).get("record")
    if target:
        rp = Path(target["path"])
        current = sha256_file(rp) if rp.exists() else None
        if current != target["sha256"]:
            drift.append("目标刊核查记录哈希漂移（本轮评审 STALE）")
    return drift
