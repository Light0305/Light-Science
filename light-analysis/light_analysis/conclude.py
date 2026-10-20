"""结论包填充与交接（Phase 2）：grade（主张映射 + 强度合成 + 溯源表）
与 export（conclusion_card.json 投影 + ANALYSIS_REPORT.md 渲染）。

汇总规则先于判定冻结在本模块（LEARNING §7，逐行判定不许被一句话压平）：
  任一行 untested → 主张落 untested（未检验 ≠ 不成立）；
  全部行 positive → supported；
  全部行 negative/null → not_supported；
  其余混合 → partial，aggregation_note 逐行列明。
强度由 grading.claim_grade 机械合成（行级最低档起步 + 逐项封顶），
数字溯源表逐个被引用数字一行：值 → 判定行 row_ref → 登记行 → 依据规格。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import grading, schema
from .project import (
    current_verdicts, load_package, save_conclusions,
)
from .render import render_report
from .util import dump_json, today


class ConcludeError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _claim_lines(analysis):
    """登记行 → 主张映射：优先行自带 claim_ref；无 claim_ref 的行在
    全包只有一个主张时归该主张（承接退化口径，与校正族退化同理）。"""
    snap = (analysis.get("registry_snapshot") or {}).get("lines") or []
    claim_ids = analysis.get("claim_ids") or []
    mapping = {cid: [] for cid in claim_ids}
    for line in snap:
        cid = line.get("claim_ref")
        if cid is None and len(claim_ids) == 1:
            cid = claim_ids[0]
        if cid is not None:
            mapping.setdefault(cid, []).append(line["registry_line_id"])
    return mapping


def _support_of(verdicts) -> str:
    if any(v == "untested" for v in verdicts):
        return "untested"
    if verdicts and all(v == "positive" for v in verdicts):
        return "supported"
    if verdicts and all(v in ("negative", "null") for v in verdicts):
        return "not_supported"
    return "partial"


def run_grade(root, notes_path=None) -> dict:
    """填充 conclusions.yaml：claims_verdict / strength / number_provenance。

    boundaries / limitations：已有内容保留；缺时可由 notes JSON 补入
    （{boundaries: [...], limitations: [...]}），graded 门会点名缺口。
    """
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise ConcludeError(["分析包不存在（先 init）"])
    if analysis.get("status") not in ("judged", "graded", "delivered", "blocked"):
        raise ConcludeError([
            f"包状态为 {analysis.get('status')}：grade 须在 judged 之后"
            "（判定行齐备才谈主张合成）"])
    current = current_verdicts(pkg["verdicts"] or [])
    mapping = _claim_lines(analysis)
    if not mapping:
        raise ConcludeError(["无主张可合成：claim_ids 为空且登记行无 claim_ref"])

    conclusions = pkg["conclusions"] or schema.new_conclusions()
    claims_verdict, strength = [], []
    for cid, line_ids in mapping.items():
        line_verdicts = {lid: (current.get(lid) or {}).get("verdict")
                         for lid in line_ids}
        support = _support_of(list(line_verdicts.values()))
        detail = "、".join(f"{lid}={v}" for lid, v in line_verdicts.items())
        claims_verdict.append({
            "claim_id": cid, "support": support,
            "line_verdicts": line_verdicts,
            "aggregation_note": f"逐行判定机械映射（{detail}），未压平",
        })
        line_grades, shares, type_ms, residuals = [], [], [], []
        scope = None
        for lid in line_ids:
            row = current.get(lid) or {}
            if row.get("strength_grade"):
                line_grades.append(row["strength_grade"])
            share = (row.get("joint") or {}).get("direction_share")
            if share is not None:
                shares.append(share)
            tm = (row.get("type_sm") or {}).get("type_m")
            if tm is not None:
                type_ms.append(tm)
            residuals += row.get("validity_residual") or []
            if scope is None and row.get("robustness_scope"):
                scope = row["robustness_scope"]
        grade, inputs, cap_reason = grading.claim_grade(
            support, line_grades,
            worst_share=min(shares) if shares else None,
            type_sm_worst=max(type_ms) if type_ms else None,
            validity_residual=residuals,
            robustness_scope=scope)
        inputs["line_verdicts"] = line_verdicts
        strength.append({"claim_id": cid, "grade": grade,
                         "inputs": inputs, "cap_reason": cap_reason})
    conclusions["claims_verdict"] = claims_verdict
    conclusions["strength"] = strength

    # ---- 数字溯源表：每个将被引用的数字一行（效应值 + 方向概率）
    provenance = []
    for lid, row in current.items():
        es = row.get("effect_size") or {}
        if es.get("value") is not None:
            provenance.append({
                "value": es["value"], "quantity": "effect_size",
                "verdict_line": row.get("row_ref"),
                "registry_line_id": lid,
                "run_refs": (row.get("distribution_ref") or {}).get("run_refs") or [],
                "spec_id": row.get("basis_spec_id"),
                "calc_provenance": (row.get("calc_provenance") or {}).get("method"),
            })
        if row.get("p_ab") is not None:
            provenance.append({
                "value": row["p_ab"], "quantity": "p_ab",
                "verdict_line": row.get("row_ref"),
                "registry_line_id": lid,
                "run_refs": (row.get("distribution_ref") or {}).get("run_refs") or [],
                "spec_id": row.get("basis_spec_id"),
                "calc_provenance": (row.get("calc_provenance") or {}).get("method"),
            })
        if es.get("value") is None and row.get("p_ab") is None:
            # 终态行无数字进结论包：落显式空溯源行，声明「无数字」本身可审计
            provenance.append({
                "value": None, "quantity": "no_numeric_result",
                "verdict_line": row.get("row_ref"),
                "registry_line_id": lid,
                "run_refs": [],
                "spec_id": None,
                "calc_provenance": None,
            })
    conclusions["number_provenance"] = provenance

    if notes_path:
        notes = json.loads(Path(notes_path).read_text(encoding="utf-8"))
        if notes.get("boundaries"):
            conclusions["boundaries"] = notes["boundaries"]
        if notes.get("limitations"):
            conclusions["limitations"] = notes["limitations"]
    save_conclusions(root, conclusions)
    return {"claims": {cv["claim_id"]: cv["support"]
                       for cv in claims_verdict},
            "grades": {s["claim_id"]: s["grade"] for s in strength},
            "provenance_rows": len(provenance)}


def export_conclusion(root, out_dir=None) -> dict:
    """A7 交接：conclusion_card.json（给 Write 的结构化投影）+ 报告渲染。

    Write 只消费结构化字段、不许另行解读数字——卡里每个数字都带
    溯源行指针（verdict row_ref），效度残余与复核状态随卡传递。
    """
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise ConcludeError(["分析包不存在（先 init）"])
    conclusions = pkg["conclusions"] or {}
    if not conclusions.get("claims_verdict"):
        raise ConcludeError(["结论包未填充：先 grade 再 export"])
    out_dir = Path(out_dir) if out_dir else root
    out_dir.mkdir(parents=True, exist_ok=True)
    grades = {s["claim_id"]: s for s in conclusions.get("strength") or []}
    card = {
        "kind": "light-analysis/conclusion-card",
        "version": "1.0",
        "analysis_id": analysis.get("analysis_id"),
        "exported_at": today(),
        "status": analysis.get("status"),
        "execution_ref": analysis.get("execution_ref"),
        "design_ref": analysis.get("design_ref"),
        "review": analysis.get("review"),
        "counts": analysis.get("counts"),
        "claims": [{
            "claim_id": cv["claim_id"],
            "support": cv["support"],
            "grade": (grades.get(cv["claim_id"]) or {}).get("grade"),
            "cap_reason": (grades.get(cv["claim_id"]) or {}).get("cap_reason"),
            "line_verdicts": cv.get("line_verdicts"),
            "aggregation_note": cv.get("aggregation_note"),
        } for cv in conclusions.get("claims_verdict") or []],
        "boundaries": conclusions.get("boundaries") or [],
        "limitations": conclusions.get("limitations") or [],
        "number_provenance": conclusions.get("number_provenance") or [],
        "reflux": conclusions.get("reflux") or [],
    }
    card_path = out_dir / "conclusion_card.json"
    dump_json(card_path, card)
    report_path = out_dir / "ANALYSIS_REPORT.md"
    report_path.write_text(render_report(load_package(root)), encoding="utf-8")
    return {"conclusion_card": str(card_path), "report": str(report_path),
            "claims": len(card["claims"])}
