"""席位与冻结（R1/R4）：可见性矩阵、逐席草稿隔离、报告冻结、共识门。

纪律：
- 可见性即权限（RV-01）：每席能读什么由 seats.yaml 的矩阵行决定，
  读取接口按「包状态 → 阶段」放行；panel 阶段席间报告互不可见，
  靠数据结构强制，不靠 prompt 自觉；
- 报告先冻结后比较（RV-12）：冻结件 append-only + 内容哈希钉住，
  冻结后只许被比较与引用；文件被改即 STALE 可检；
- 共识门（RV-05）：consensus 须 ≥2 席独立同向；severity 由代码取
  各席独立提案 MAX，佐证数不进计算——任何手填 severity 与计算值
  不符、单席标 consensus、佐证抬级，在落盘口就被拒；
- 条目终态（RV-11）：concern 关闭必须带理由，不许静默丢弃。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import schema
from .project import (
    fold_findings, load_package, refresh_counts, save_consensus, save_review,
    save_seats,
)
from .util import sha256_file, today

_STAGE_BY_STATUS = {
    "intake": "panel", "forensic_checked": "panel", "paneled": "panel",
    "reported": "reported", "adjudicated": "adjudication",
    "delivered": "adjudication",
}


class PanelError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


class VisibilityError(PanelError):
    """可见性矩阵拒绝：席位在当前阶段无权读该工件（RV-01）。"""


def _seat(seats: dict, seat_id: str) -> dict:
    for s in (seats or {}).get("seats") or []:
        if s.get("seat_id") == seat_id:
            return s
    raise PanelError([f"席位 {seat_id} 未登记（先 seat 登记）"])


def register_seat(root, seat_id, role, model_family, persona=None,
                  knows_authors=False, visibility=None) -> dict:
    root = Path(root)
    pkg = load_package(root)
    if pkg["review"] is None:
        raise PanelError(["评审包不存在（先 init）"])
    seats = pkg["seats"] or schema.new_seats()
    if any(s.get("seat_id") == seat_id for s in seats.get("seats") or []):
        raise PanelError([f"席位 {seat_id} 已登记，不许重复登记或改写"])
    if visibility is not None:
        for stage, kinds in visibility.items():
            if stage not in schema.PANEL_STAGES:
                raise PanelError([f"可见性阶段 {stage!r} 不在词表 "
                                  f"{schema.PANEL_STAGES}"])
            bad = [k for k in kinds if k not in schema.ARTIFACT_KINDS]
            if bad:
                raise PanelError([f"可见性工件类不在词表：{bad}"])
        # 硬纪律：panel 阶段任何席不许见 other_reports / consensus，
        # 自定义矩阵也不许绕过互盲（RV-01 的底线不是默认值）。
        panel_kinds = visibility.get("panel") or []
        if "other_reports" in panel_kinds or "consensus" in panel_kinds:
            raise PanelError(
                ["panel 阶段可见性不许含 other_reports/consensus："
                 "冻结前互盲是硬纪律，自定义矩阵不许绕过"])
    row = schema.seat_row(seat_id, role, model_family, persona=persona,
                          knows_authors=knows_authors,
                          visibility=visibility)
    seats.setdefault("seats", []).append(row)
    save_seats(root, seats)
    return row


def visible_kinds(root, seat_id, stage=None) -> list:
    """某席在某阶段可见的工件类集合（矩阵行原文）。"""
    pkg = load_package(root)
    seat = _seat(pkg["seats"], seat_id)
    if stage is None:
        status = (pkg["review"] or {}).get("status", "intake")
        stage = _STAGE_BY_STATUS.get(status, "panel")
    return list((seat.get("visibility") or {}).get(stage) or [])


def classify_artifact(relpath: str, requester: str) -> str:
    """把评审包内相对路径归到可见性工件类（以请求席为参照）。"""
    rel = str(relpath).replace("\\", "/").lstrip("./")
    if rel == "consensus.yaml":
        return "consensus"
    if rel.startswith("forensic/"):
        return "forensic"
    if rel.startswith("reports/"):
        name = rel.rsplit("/", 1)[-1]
        owner = name[:-3] if name.endswith(".md") else name
        return "own_materials" if owner == requester else "other_reports"
    return "manuscript"


def read_for_seat(root, seat_id, relpath, stage=None) -> str:
    """按可见性矩阵放行的读取接口：无权即 VisibilityError（RV-01）。

    这是编排层给席位供料的唯一正道：席位 prompt 里写什么不重要，
    供料口只按矩阵放行，运行后可审计某席写报告前不可能看到什么。
    """
    root = Path(root)
    p = Path(relpath)
    if p.is_absolute():
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = None  # 包外路径（如上游稿件包文件）：归 manuscript 类
    else:
        rel = p.as_posix()
    kind = classify_artifact(rel, seat_id) if rel is not None else "manuscript"
    allowed = visible_kinds(root, seat_id, stage=stage)
    if kind not in allowed:
        raise VisibilityError(
            [f"席位 {seat_id} 在当前阶段不可见 {kind}"
             f"（请求 {relpath}）：可见性矩阵拒绝"])
    target = p if p.is_absolute() else root / p
    if not target.exists():
        raise PanelError([f"工件不存在：{relpath}"])
    return target.read_text(encoding="utf-8")


def write_draft(root, seat_id, source_path) -> dict:
    """把席位草稿落入 reports/drafts/<seat>.md（席间物理隔离）。"""
    root = Path(root)
    pkg = load_package(root)
    seats = pkg["seats"]
    seat = _seat(seats, seat_id)
    if seat.get("status") == "frozen":
        raise PanelError([f"席位 {seat_id} 报告已冻结：冻结件只增不改，"
                          "修订走新 round（RV-12）"])
    src = Path(source_path)
    if not src.exists():
        raise PanelError([f"草稿源文件不存在：{src}"])
    dst = root / "reports" / "drafts" / f"{seat_id}.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    seat["status"] = "drafted"
    seat["draft_path"] = f"reports/drafts/{seat_id}.md"
    save_seats(root, seats)
    return seat


def freeze_reports(root, by="light-review freeze") -> list:
    """冻结全部席位报告：drafts → reports/<seat>.md + 哈希钉住。

    append-only：目标冻结件已存在即拒绝（不许覆盖旧冻结件）；
    冻结记录追加进登记头 freezes 账，冻结后改文件即 STALE 可检。
    """
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    seats = pkg["seats"] or {"seats": []}
    rows = seats.get("seats") or []
    if not rows:
        raise PanelError(["无登记席位，无从冻结"])
    gaps = [f"席位 {s['seat_id']} 尚无草稿（先 panel 落草稿）"
            for s in rows if s.get("status") != "drafted"]
    if gaps:
        raise PanelError(gaps)
    records = []
    for seat in rows:
        target = root / "reports" / f"{seat['seat_id']}.md"
        if target.exists():
            raise PanelError(
                [f"冻结件已存在：reports/{seat['seat_id']}.md"
                 "（append-only，不许覆盖已冻结报告）"])
        src = root / seat["draft_path"]
        shutil.copyfile(src, target)
        digest = sha256_file(target)
        seat["status"] = "frozen"
        seat["report_path"] = f"reports/{seat['seat_id']}.md"
        seat["report_hash"] = digest
        seat["frozen_at"] = today()
        records.append({"seat_id": seat["seat_id"], "report_hash": digest,
                        "at": today(), "by": by})
    review.setdefault("freezes", []).extend(records)
    review["updated_at"] = today()
    save_seats(root, seats)
    save_review(root, review)
    return records


def verify_frozen(root) -> list:
    """重算冻结件哈希与登记比对，返回 STALE 描述（空 = 未篡改）。"""
    pkg = load_package(root)
    stale = []
    for seat in (pkg["seats"] or {}).get("seats") or []:
        if seat.get("status") != "frozen":
            continue
        p = Path(root) / (seat.get("report_path") or "")
        if not p.exists():
            stale.append(f"席位 {seat['seat_id']} 冻结件缺失"
                         f"（{seat.get('report_path')}）")
        elif sha256_file(p) != seat.get("report_hash"):
            stale.append(f"席位 {seat['seat_id']} 冻结件哈希漂移"
                         "（冻结后被改，STALE）")
    return stale


def build_consensus(root, concerns_data) -> dict:
    """由逐席关切输入生成共识与分歧账（共识门在落盘口强制，RV-05）。

    concerns_data 每条：{statement, raised_by, severity_proposals,
    close_criterion?, pointers?, status?, close_reason?}。
    severity 与 consensus 均由代码判定：输入若自带 severity 与计算
    值不符、或单席自称 consensus，直接拒绝——佐证永不抬级。
    """
    root = Path(root)
    pkg = load_package(root)
    if pkg["review"] is None:
        raise PanelError(["评审包不存在（先 init）"])
    known = {s.get("seat_id")
             for s in (pkg["seats"] or {}).get("seats") or []}
    concerns, gaps = [], []
    seen_ids = set()
    for i, raw in enumerate(concerns_data or []):
        cid = raw.get("concern_id") or f"RV-C{i + 1:03d}"
        if cid in seen_ids:
            gaps.append(f"concern {cid} 重复（stable ID 不许复用）")
            continue
        seen_ids.add(cid)
        raised = list(dict.fromkeys(raw.get("raised_by") or []))
        unknown = [s for s in raised if s not in known]
        if unknown:
            gaps.append(f"concern {cid} 的 raised_by 含未登记席位：{unknown}")
            continue
        if not raised:
            gaps.append(f"concern {cid} 无提出席位：无来源关切不立案（RV-04）")
            continue
        proposals = dict(raw.get("severity_proposals") or {})
        bad_sev = [v for v in proposals.values()
                   if v not in schema.SEVERITIES]
        if bad_sev:
            gaps.append(f"concern {cid} 的 severity 提案不在词表：{bad_sev}")
            continue
        extra = [s for s in proposals if s not in raised]
        if extra:
            gaps.append(f"concern {cid} 的 severity 提案来自未提出该关切的"
                        f"席位：{extra}（提案权随提出权）")
            continue
        computed = schema.computed_severity(proposals)
        if raw.get("severity") is not None and raw["severity"] != computed:
            gaps.append(
                f"concern {cid} 手填 severity={raw['severity']} ≠ 代码计算 "
                f"{computed}：severity 只许由各席独立提案取 MAX，"
                "佐证数不许抬级（RV-05）")
            continue
        is_consensus = len(raised) >= 2
        if raw.get("consensus") and not is_consensus:
            gaps.append(
                f"concern {cid} 单席提出却自称 consensus：共识门要求 "
                "≥2 席互盲下独立同向（RV-05）")
            continue
        if raw.get("status") == "closed" and \
                not (raw.get("close_reason") or "").strip():
            gaps.append(f"concern {cid} 关闭缺理由：条目离开活跃集必须"
                        "落带理由终态（RV-11）")
            continue
        concerns.append(schema.concern_row(
            cid, raw.get("statement") or "", raised,
            proposals,
            consensus=is_consensus,
            consensus_basis={"independent_seats": len(raised),
                             "via_escalation": False},
            close_criterion=raw.get("close_criterion"),
            status=raw.get("status", "open"),
            close_reason=raw.get("close_reason"),
            pointers=raw.get("pointers")))
    if gaps:
        raise PanelError(gaps)
    consensus = {"concerns": concerns}
    save_consensus(root, consensus)
    review = pkg["review"]
    refresh_counts(review, fold_findings(pkg["findings"] or []), consensus)
    review["updated_at"] = today()
    save_review(root, review)
    return consensus
