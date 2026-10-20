"""A0 承接与可判性校验（Phase 1 核心）。

消费 light-experiment 的 execution_card.json（只认 delivered 包）与
light-design 的 expected_registry.jsonl，做三件事：

1. 哈希对齐：execution_card.design_ref.content_hash ≡ 登记行 content_hash
   ≡ 对账 content_hash，任一不一致逐项点名、整包拦截（不放行）；
2. 逐行可判性点名：分布材料齐否 / 作废命中 / fundamental 失败 /
   null 先天可判性（覆盖 n < 登记 repetitions → undetermined 预警），
   结果落 audit.json + audit.md 双份；
3. 不可判行预登记：untested / undetermined 候选直接落 verdicts.jsonl
   一等终态行（decided_by=intake-audit），不许留到判定期硬判。

分布材料只认四件套 {mean, spread, n, replication_level}——
单点数值冒充分布在承接期即判失败项（承 Experiment 纪律 14）。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import schema
from .project import (
    assign_row_refs, load_package, refresh_counts, save_analysis, save_verdicts,
)
from .util import component_hash, dump_json, sha256_file, today


class IntakeError(Exception):
    """承接失败：gaps 为逐项缺口清单（点名，不许含糊放行）。"""

    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def registry_hash_of(rows) -> str:
    """登记行集哈希：按 run_id 排序后逐行规范化 JSON 再整体哈希。"""
    ordered = sorted(rows, key=lambda r: r.get("run_id") or "")
    return component_hash([json.loads(json.dumps(r)) for r in ordered])


def _judge_line(reg_row, rec_row, runs_by_id, failures_by_run):
    """单条登记行的可判性裁定（纯函数，可单测）。"""
    line_id = reg_row.get("run_id")
    reasons = []
    void_supported = False
    fundamental_failure = False
    null_precision_warning = False

    run_ids = (rec_row or {}).get("run_ids") or []
    supporting = [runs_by_id[r] for r in run_ids if r in runs_by_id]

    if rec_row is None:
        judgeability = "untested_candidate"
        reasons.append("执行包无对账行：该登记行未执行或未回填事实层")
        return {
            "registry_line_id": line_id,
            "role": reg_row.get("role"),
            "claim_ref": reg_row.get("claim_ref"),
            "judgeability": judgeability,
            "void_supported": void_supported,
            "fundamental_failure": fundamental_failure,
            "null_precision_warning": null_precision_warning,
            "n_registered": reg_row.get("repetitions"),
            "n_effective": None,
            "reasons": reasons,
        }

    if supporting and all((r.get("voided_by") or []) for r in supporting):
        void_supported = True
        reasons.append(
            "支撑 run 全部被作废（"
            + "、".join(f"{r['run_id']}←{'/'.join(r['voided_by'])}"
                        for r in supporting)
            + "）：作废 run 的分布不许进判定")

    for r in supporting:
        for f in failures_by_run.get(r["run_id"], []):
            if f.get("failure_class") == "fundamental":
                fundamental_failure = True
                reasons.append(
                    f"支撑 run {r['run_id']} 有 fundamental 失败 "
                    f"{f.get('failure_id')}（{f.get('mast_code')}）："
                    "主张未被检验，不许落 negative")

    ra = rec_row.get("readout_actual")
    material_fail = None
    blocking = []  # 阻断性理由（落 undetermined 候选）；精度预警不阻断方向判定
    if rec_row.get("status") != "filled":
        blocking.append(f"对账行状态为 {rec_row.get('status')}，事实层未回填完成")
    elif ra is None:
        blocking.append("对账行无 readout_actual 分布材料")
    elif not isinstance(ra, dict) or not set(schema.DISTRIBUTION_KEYS) <= set(ra):
        material_fail = (
            f"登记行 {line_id} 的 readout_actual 不是分布四件套"
            f"（须含 {'/'.join(schema.DISTRIBUTION_KEYS)}）：单点材料不许冒充分布")
    else:
        rf = ((rec_row.get("layers") or {}).get("result_fact") or {})
        if rf.get("verdict") == "incomparable":
            blocking.append(f"事实层比对为 incomparable：{rf.get('reason')}")
        n_reg = reg_row.get("repetitions")
        if n_reg and ra.get("n") is not None and ra["n"] < n_reg:
            null_precision_warning = True
            reasons.append(
                f"覆盖 n={ra['n']} < 登记 repetitions={n_reg}："
                "先天精度不足，null 不可判（undetermined 预警）")
    reasons = blocking + reasons

    if material_fail:
        judgeability = "material_fail"
    elif void_supported or fundamental_failure:
        judgeability = "untested_candidate"
    elif blocking:
        judgeability = "undetermined_candidate"
    else:
        judgeability = "judgeable"

    return {
        "registry_line_id": line_id,
        "role": reg_row.get("role"),
        "claim_ref": reg_row.get("claim_ref"),
        "judgeability": judgeability,
        "void_supported": void_supported,
        "fundamental_failure": fundamental_failure,
        "null_precision_warning": null_precision_warning,
        "n_registered": reg_row.get("repetitions"),
        "n_effective": (ra or {}).get("n") if isinstance(ra, dict) else None,
        "reasons": reasons,
        "_material_fail": material_fail,
    }


def run_intake(root, execution_card_path, registry_path,
               design_card_path=None, analyst_name=None,
               analyst_family=None) -> dict:
    """执行承接：成功返回 audit dict；失败抛 IntakeError（逐项缺口）。"""
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise IntakeError(["分析包不存在或 analysis.yaml 缺失（先 init）"])
    if analysis.get("execution_ref"):
        raise IntakeError(["本包已完成承接（execution_ref 已冻结），不许换包重判而不留痕"])

    gaps: list[str] = []

    card_path = Path(execution_card_path)
    registry_path = Path(registry_path)
    if not card_path.exists():
        raise IntakeError([f"execution_card 不存在：{card_path}"])
    if not registry_path.exists():
        raise IntakeError([f"expected_registry 不存在：{registry_path}"])

    card = json.loads(card_path.read_text(encoding="utf-8"))
    card_hash = sha256_file(card_path)
    registry_rows = [json.loads(line) for line in
                     registry_path.read_text(encoding="utf-8").splitlines()
                     if line.strip()]

    # ---- 哈希对齐
    design_ref_card = card.get("design_ref") or {}
    content_hash = design_ref_card.get("content_hash")
    if card.get("status") != "delivered":
        gaps.append(f"执行包状态为 {card.get('status')}，只消费 delivered 包")
    if not content_hash:
        gaps.append("execution_card 缺 design_ref.content_hash")
    for row in registry_rows:
        if content_hash and row.get("content_hash") != content_hash:
            gaps.append(
                f"登记行 {row.get('run_id')} 的 content_hash 与执行包登记的 "
                "Design content_hash 不一致（设计已被改动或登记表过期）")
    rec_hash = (card.get("reconciliation") or {}).get("content_hash")
    if content_hash and rec_hash and rec_hash != content_hash:
        gaps.append("execution_card.reconciliation.content_hash 与 "
                    "design_ref.content_hash 不一致")
    reg_ids = [r.get("run_id") for r in registry_rows]
    if len(set(reg_ids)) != len(reg_ids):
        gaps.append("expected_registry 存在重复 run_id")
    registry_hash = registry_hash_of(registry_rows)

    # ---- SESOI 登记块捕获（ANA-D02）：行带块 → 验完整 + 全表一致
    # Design 登记行 sesoi 只能是 evaluation 登记块的派生副本（DES-D01）：
    # 同一设计只许一份登记；块缺字段或多行不一致都在承接期点名拦截，
    # 不许把半成品带进判定期再猜。
    sesoi_blocks: dict = {}
    for row in registry_rows:
        blk = row.get("sesoi")
        if blk is None:
            continue
        berrs = schema.validate_sesoi_block(blk)
        if berrs:
            gaps.append(f"登记行 {row.get('run_id')} 的 sesoi 登记块不完整："
                        + "；".join(berrs))
        else:
            sesoi_blocks[row.get("run_id")] = schema.sesoi_canonical(blk)
    _distinct = {json.dumps(b, ensure_ascii=False, sort_keys=True)
                 for b in sesoi_blocks.values()}
    if len(_distinct) > 1:
        gaps.append("登记行 sesoi 登记块不一致（同一设计只许一份登记，"
                    "行内只许派生副本）：涉及行 "
                    + "、".join(sorted(sesoi_blocks)))

    # ---- 配对/区组结构声明形状点名（ANA-D03）：登记行可声明 pairing，
    # 承接只验形状（mode 词表 + 对应键名字段齐全），声明随快照透传，
    # 判定期的结构与数据对齐由 judge 机械核（缺对侧等逐行点名）。
    for row in registry_rows:
        decl = row.get("pairing")
        if decl is None:
            continue
        rid = row.get("run_id")
        if not isinstance(decl, dict) \
                or decl.get("mode") not in ("paired", "blocked"):
            gaps.append(f"登记行 {rid} 的 pairing 声明形状不对：mode 须为 "
                        "paired 或 blocked（ANA-D03 结构声明词表）")
            continue
        key_field = "paired_by" if decl["mode"] == "paired" else "blocked_by"
        if not (isinstance(decl.get(key_field), str)
                and decl[key_field].strip()):
            gaps.append(f"登记行 {rid} 的 pairing 声明缺 {key_field} 键名："
                        "结构声明须点名两臂按什么键对齐")

    # ---- 逐行可判性
    runs_by_id = {r["run_id"]: r for r in card.get("runs") or []}
    failures_by_run: dict[str, list] = {}
    for f in card.get("failures") or []:
        failures_by_run.setdefault(f.get("run_id"), []).append(f)
    rec_by_id = {r.get("registry_run_id"): r
                 for r in (card.get("reconciliation") or {}).get("rows") or []}

    lines = []
    for reg_row in registry_rows:
        line = _judge_line(reg_row, rec_by_id.get(reg_row.get("run_id")),
                           runs_by_id, failures_by_run)
        material_fail = line.pop("_material_fail", None)
        if material_fail:
            gaps.append(material_fail)
        # 登记行 SESOI 块随快照行落盘（ANA-D02：judge 与登记时的比对源）
        line["sesoi"] = reg_row.get("sesoi") \
            if isinstance(reg_row.get("sesoi"), dict) else None
        # 配对/区组结构声明随快照行透传（ANA-D03：judge 的登记侧声明源）
        line["pairing"] = reg_row.get("pairing") \
            if isinstance(reg_row.get("pairing"), dict) else None
        lines.append(line)

    if gaps:
        raise IntakeError(gaps)

    # ---- 校正族声明（默认按主张族；登记行无 claim_ref 时退化单族并落字）
    claims_in_rows = sorted({l["claim_ref"] for l in lines if l.get("claim_ref")})
    families = []
    if claims_in_rows:
        for c in claims_in_rows:
            families.append({
                "family_id": f"claim:{c}",
                "member_line_ids": [l["registry_line_id"] for l in lines
                                    if l.get("claim_ref") == c],
                "method": schema.DEFAULT_CORRECTION_METHOD,
                "alpha": 0.05,
                "basis": "按主张族（拍板⑥默认 BH-FDR）",
            })
    else:
        families.append({
            "family_id": "claim:all",
            "member_line_ids": [l["registry_line_id"] for l in lines],
            "method": schema.DEFAULT_CORRECTION_METHOD,
            "alpha": 0.05,
            "basis": "登记行未带 claim_ref，退化为全行单族（待 Design 补 claim 映射后可在新包细分）",
        })

    # ---- 主张 id 快照（可选 design_card）
    claim_ids = list(claims_in_rows)
    if design_card_path:
        dc = json.loads(Path(design_card_path).read_text(encoding="utf-8"))
        prim = ((dc.get("claims") or {}).get("primary_claims") or [])
        claim_ids = [c.get("id") for c in prim if c.get("id")] or claim_ids

    # ---- 落盘：登记头承接区 + 快照
    analysis["execution_ref"] = {
        "execution_id": card.get("exec_id"),
        "package_path": str(card_path.parent),
        "execution_card": str(card_path),
        "execution_card_hash": card_hash,
        "card_status": card.get("status"),
    }
    analysis["design_ref"] = {
        "design_id": design_ref_card.get("design_id"),
        "content_hash": content_hash,
        "registry_hash": registry_hash,
        "registry_lines": len(registry_rows),
        "registry_path": str(registry_path),
    }
    analysis["registry_snapshot"] = {
        "line_ids": reg_ids,
        "lines": lines,
    }
    analysis["claim_ids"] = claim_ids
    analysis["correction_families"] = families
    if analyst_name or analyst_family:
        analysis["analyst"] = {"name": analyst_name, "family": analyst_family}

    # ---- 不可判行预登记（一等终态落 verdicts.jsonl）
    pre_rows = []
    for line in lines:
        if line["judgeability"] == "judgeable":
            continue
        verdict = ("untested" if line["judgeability"] == "untested_candidate"
                   else "undetermined")
        pre_rows.append(schema.verdict_row(
            line["registry_line_id"], verdict,
            claim_ref=line.get("claim_ref"),
            quadrant="undetermined" if verdict == "undetermined" else None,
            n_registered=line.get("n_registered"),
            n_effective=line.get("n_effective"),
            note="承接预登记：" + "；".join(line["reasons"]),
            decided_by="intake-audit",
            decided_at=today(),
        ))
    if pre_rows:
        existing = pkg["verdicts"] or []
        save_verdicts(root, assign_row_refs(existing + pre_rows))
    refresh_counts(analysis, load_package(root)["verdicts"] or [])
    save_analysis(root, analysis)

    audit = {
        "analysis_id": analysis["analysis_id"],
        "checked_at": today(),
        "execution_id": card.get("exec_id"),
        "execution_card_hash": card_hash,
        "design_content_hash": content_hash,
        "registry_hash": registry_hash,
        "hash_alignment": "pass",
        "lines": lines,
        "summary": {
            "total": len(lines),
            "judgeable": sum(1 for l in lines if l["judgeability"] == "judgeable"),
            "untested_candidate": sum(1 for l in lines if l["judgeability"] == "untested_candidate"),
            "undetermined_candidate": sum(1 for l in lines if l["judgeability"] == "undetermined_candidate"),
            "null_precision_warnings": sum(1 for l in lines if l["null_precision_warning"]),
        },
        "failures": [],
    }
    dump_json(root / "audit.json", audit)
    from .render import render_audit
    (root / "audit.md").write_text(render_audit(audit), encoding="utf-8")
    return audit
