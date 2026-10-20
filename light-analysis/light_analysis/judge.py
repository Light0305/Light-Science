"""判定子流程（Phase 2）：SESOI 登记、逐行判定落字、补充消融回流。

纪律要点（LEARNING 约束 1/2/3/6/11 + 拍板①③⑥）：
- 判定计算只认分析规格登记值：SESOI 必须先经 `register_sesoi` 从
  Design 文件按指针取数、落快照 + 来源哈希进 analysis.yaml 的 spec 区；
  judge 时 SESOI 未登记的行直接落 undetermined，不许临场从文本猜。
- positive 双门：规格集联合推断（中位效应同向 + 方向份额 ≥0.5 +
  Stouffer 合并 p 达门）与 Type S/M 校准（D = 登记 SESOI，Type M 不超
  规格登记阈值，默认 2.0）缺一不可；任一门未过落 undetermined 并逐项
  点名缺哪门。
- null 必须靠 TOST 挣来；承接带 null 精度预警的行判不了 null。
- 判定材料（judge-data）逐行登记两臂原始值（或分布摘要），列名/字段
  机械核对：未知行、缺行、n 与对账不一致都在本层点名（防 BLADE 式
  幻觉列名与单点冒充分布）。
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from . import calc, grading, schema
from .project import (
    assign_row_refs, current_verdicts, load_package, refresh_counts,
    save_analysis, save_conclusions, save_spec_results, save_verdicts,
)
from .specs import verify_ledger_hash
from .util import component_hash, dump_json, load_structured, sha256_file, today

TYPE_M_MAX_DEFAULT = 2.0
_DATA_KEYS = {"treatment", "reference", "treatment_summary",
              "reference_summary", "reference_label", "run_refs",
              "bayes", "diagnostics", "validity_residual"}


class JudgeError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- SESOI 登记

def _resolve_pointer(obj, pointer: str):
    cur = obj
    for part in pointer.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise JudgeError([f"SESOI 指针 {pointer} 在来源文件中断在 {part!r}（键不存在）"])
            cur = cur[part]
        else:
            raise JudgeError([f"SESOI 指针 {pointer} 在来源文件中断在 {part!r}（非容器）"])
    return cur


def register_sesoi(root, source_path, pointer, line_ids=None) -> dict:
    """从 Design 来源文件按指针取 SESOI，落快照进 analysis.yaml 的 spec 区。

    快照 = {sesoi_pointer, sesoi_value, source_path, source_hash}；
    判定计算只认快照值，来源文件事后变动由 source_hash 验得出。
    line_ids 缺省 = 全部可判登记行。
    """
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise JudgeError(["分析包不存在（先 init）"])
    source_path = Path(source_path)
    if not source_path.exists():
        raise JudgeError([f"SESOI 来源文件不存在：{source_path}"])
    source = load_structured(source_path)
    value = _resolve_pointer(source, pointer)
    if not isinstance(value, (int, float)) or isinstance(value, bool) \
            or float(value) <= 0:
        raise JudgeError([f"指针 {pointer} 取到 {value!r}，SESOI 须为正数"])
    snap = (analysis.get("registry_snapshot") or {}).get("lines") or []
    if line_ids is None:
        line_ids = [l["registry_line_id"] for l in snap
                    if l.get("judgeability") == "judgeable"]
    entry = {
        "sesoi_pointer": pointer,
        "sesoi_value": float(value),
        "source_path": str(source_path),
        "source_hash": sha256_file(source_path),
        "registered_at": today(),
    }
    spec = analysis.setdefault("spec", {})
    sesoi_map = spec.setdefault("sesoi", {})
    for lid in line_ids:
        sesoi_map[lid] = dict(entry)
    spec.setdefault("judge_params", {
        "gamma": schema.GAMMA_DEFAULT,
        "type_m_max": TYPE_M_MAX_DEFAULT,
    })
    save_analysis(root, analysis)
    return entry


# ---------------------------------------------------------------- 判定材料

def _load_judge_data(root, data_path):
    data_path = Path(data_path)
    if not data_path.exists():
        raise JudgeError([f"判定材料文件不存在：{data_path}"])
    data = load_structured(data_path)
    lines = (data or {}).get("lines")
    if not isinstance(lines, dict):
        raise JudgeError(["判定材料须为 {lines: {登记行id: {treatment, reference, …}}} 形态"])
    return data_path, lines


def _arms(entry):
    """取两臂计算输入：原始值优先；只有摘要时走 summary 口径并标注。"""
    if entry.get("treatment") is not None and entry.get("reference") is not None:
        return {"form": "raw",
                "a": [float(x) for x in entry["treatment"]],
                "b": [float(x) for x in entry["reference"]]}
    ts, rs = entry.get("treatment_summary"), entry.get("reference_summary")
    if ts and rs:
        for tag, s in (("treatment_summary", ts), ("reference_summary", rs)):
            if not set(schema.DISTRIBUTION_KEYS) <= set(s):
                raise ValueError(f"{tag} 不是分布四件套（缺 "
                                 f"{sorted(set(schema.DISTRIBUTION_KEYS) - set(s))}）")
        return {"form": "summary", "a": ts, "b": rs}
    raise ValueError("判定材料缺两臂：须给 treatment/reference 原始值，"
                     "或 treatment_summary/reference_summary 分布四件套")


def _spec_effect(spec, arms, sign):
    """逐规格效应与 p：estimator 决策点决定口径，其余决策点 v1 只留痕。

    mean_diff → Welch；median_diff → 中位差 + Mann-Whitney p；
    摘要材料下秩类规格退化为 Welch 口径（在结果行 note 落字）。
    返回 (oriented_effect, p_two_sided, degraded_note | None)。
    """
    estimator = (spec.get("choices") or {}).get("estimator", "mean_diff")
    if arms["form"] == "raw":
        a, b = arms["a"], arms["b"]
        if estimator == "median_diff":
            eff = calc.median_diff(a, b)
            p = calc.mann_whitney_p(a, b)["p_two_sided"]
            return sign * eff, p, None
        res = calc.effect_and_ci(a, b)
        return sign * res["mean_diff"], res["p_two_sided"], None
    ta, rb = arms["a"], arms["b"]
    res = calc.effect_and_ci_summary(ta["mean"], ta["spread"], ta["n"],
                                     rb["mean"], rb["spread"], rb["n"])
    note = None
    if estimator == "median_diff":
        note = "摘要材料无原始值：秩类规格退化为 Welch 均值口径"
    return sign * res["mean_diff"], res["p_two_sided"], note


def _primary_quantities(arms, sign):
    """主规格量组：效应 + 区间 + P(向登记方向更优) + SE/df（TOST 与校准共用）。"""
    # p_better / p_worse 均按「登记方向」定义：better = 沿登记方向更优。
    # sign 已把登记方向折进 effect（effect>0 即沿登记方向），故原始两臂
    # 先按 sign 还原成（优向臂, 劣向臂）再算概率对。
    if arms["form"] == "raw":
        a, b = arms["a"], arms["b"]
        res = calc.effect_and_ci(a, b)
        hi_arm, lo_arm = (a, b) if sign > 0 else (b, a)
        p_better = calc.p_superiority(hi_arm, lo_arm)["value"]
        p_worse = calc.p_superiority(lo_arm, hi_arm)["value"]
        prov = res["provenance"]
    else:
        ta, rb = arms["a"], arms["b"]
        res = calc.effect_and_ci_summary(ta["mean"], ta["spread"], ta["n"],
                                         rb["mean"], rb["spread"], rb["n"])
        hi_s, lo_s = (ta, rb) if sign > 0 else (rb, ta)
        p_better = calc.p_superiority_normal(
            hi_s["mean"], hi_s["spread"], lo_s["mean"], lo_s["spread"])["value"]
        p_worse = 1.0 - p_better  # 连续近似无并列质量
        prov = res["provenance"]
    return {
        "effect": sign * res["mean_diff"],
        "se": res["se"], "df": res["df"],
        "interval": {"kind": "ci", "level": 0.95,
                     "lo": sign * res["ci"]["lo"] if sign > 0 else -res["ci"]["hi"],
                     "hi": sign * res["ci"]["hi"] if sign > 0 else -res["ci"]["lo"]},
        "hedges_g": sign * res["hedges_g"],
        "p_raw": res["p_two_sided"],
        "p_better": p_better,
        "p_worse": p_worse,
        "provenance": prov,
    }


def _decide(*, effect, p_adj, p_ab, alpha, gamma, joint, type_m,
            type_m_max, tost_pass, null_precision_warning):
    """四象限落字规则（纯函数）。返回 (verdict, quadrant, gate_notes)。

    gate_notes 逐项点名未过的门——undetermined 行 note 必须逐项写明。
    """
    notes = []
    direction = 1 if effect > 0 else (-1 if effect < 0 else 0)
    # p_ab 由调用方按判定方向传入：positive 候选传 P(更优)、negative
    # 候选传 P(更劣)，同一 γ 门（分布判据只认方向概率，不认单点）。
    dist_ok = p_ab >= gamma
    significant = (p_adj < alpha) and dist_ok and direction != 0
    if p_adj >= alpha:
        notes.append(f"主规格校正后 p={p_adj:.4g} 未达族 α={alpha}")
    if not dist_ok:
        notes.append(f"分布判据未达门：判定方向概率 P={p_ab:.3f} < γ={gamma}")
    joint_ok = (joint["median_effect"] * direction > 0
                and joint["direction_share"] >= 0.5
                and joint["stouffer_p"] < alpha) if direction != 0 else False
    if direction != 0 and not joint_ok:
        notes.append(
            f"规格集联合推断未过（中位效应 {joint['median_effect']:.4g}、"
            f"方向份额 {joint['direction_share']:.2f}、"
            f"Stouffer p={joint['stouffer_p']:.4g}）")
    tm_ok = type_m is not None and type_m <= type_m_max
    if direction > 0:
        if significant and joint_ok and tm_ok:
            quad = "significant_but_equivalent" if tost_pass \
                else "significant_not_equivalent"
            return "positive", quad, notes
        if significant and joint_ok and not tm_ok:
            notes.append(f"Type M={type_m:.2f} 超登记阈值 {type_m_max}："
                         "量级夸大风险未过校准门，positive 被拦")
            return "undetermined", "undetermined", notes
    if direction < 0:
        if significant and joint_ok:
            quad = "significant_but_equivalent" if tost_pass \
                else "significant_not_equivalent"
            return "negative", quad, notes
    # 非方向性出口：null 须 TOST 挣来且未达方向门
    if tost_pass and not significant:
        if null_precision_warning:
            notes.append("承接 null 精度预警在案：先天精度不足，"
                         "本行判不了 null（只许 undetermined）")
            return "undetermined", "undetermined", notes
        return "null", "equivalent_only", notes
    if not tost_pass:
        notes.append("TOST 未过：等价未挣得，不许落 null")
    return "undetermined", "undetermined", notes


def run_judge(root, data_path, decided_by=None) -> dict:
    """执行判定：前置门 → 逐行计算 → 按族校正 → 落字 → spec_results 账平。"""
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise JudgeError(["分析包不存在（先 init）"])
    gaps = []
    if analysis.get("status") != "checked":
        gaps.append(f"包状态为 {analysis.get('status')}：判定前置门要求先过 "
                    "checked（账本冻结 + 承接点名齐备）")
    ledger = pkg["spec_ledger"] or {}
    ok, detail = verify_ledger_hash(ledger)
    if not ok:
        gaps.append(f"规格集账本未冻结或已篡改：{detail}")
    if gaps:
        raise JudgeError(gaps)

    data_path, data_lines = _load_judge_data(root, data_path)
    snap_lines = {l["registry_line_id"]: l
                  for l in (analysis.get("registry_snapshot") or {}).get("lines") or []}
    unknown = [lid for lid in data_lines if lid not in snap_lines]
    if unknown:
        raise JudgeError([f"判定材料含未登记行 {unknown}：判定只认登记行"
                          "（列名/行名机械核对，防幻觉行）"])

    # 登记表（direction / criteria 来源）：design_ref.registry_path
    registry_path = (analysis.get("design_ref") or {}).get("registry_path")
    reg_rows = {}
    if registry_path and Path(registry_path).exists():
        for line in Path(registry_path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                reg_rows[r.get("run_id")] = r

    spec_cfg = analysis.get("spec") or {}
    params = {"gamma": schema.GAMMA_DEFAULT, "type_m_max": TYPE_M_MAX_DEFAULT}
    params.update(spec_cfg.get("judge_params") or {})
    gamma, type_m_max = params["gamma"], params["type_m_max"]
    sesoi_map = spec_cfg.get("sesoi") or {}

    included = [s for s in ledger.get("specs") or []
                if s.get("status") == "included"]
    if not included:
        raise JudgeError(["规格集账本无 included 规格，无从判定"])
    primary = next((s for s in included if s.get("primary")), included[0])

    families = analysis.get("correction_families") or []
    fam_by_line = {}
    for fam in families:
        for lid in fam.get("member_line_ids") or []:
            fam_by_line[lid] = fam

    current = current_verdicts(pkg["verdicts"] or [])
    judgeable = [lid for lid, l in snap_lines.items()
                 if l.get("judgeability") == "judgeable"]
    already = [lid for lid in judgeable
               if lid in current
               and current[lid].get("decided_by") != "intake-audit"]
    if already:
        raise JudgeError([f"登记行 {already} 已有判定行：改判走 supersedes "
                          "新行，不许 judge 覆盖重跑"])

    analyst = analysis.get("analyst") or {}
    decided_by = decided_by or analyst.get("name") or "light-analysis judge"

    # ---- 第一遍：逐行计算量组与逐规格结果（校正须全行 p 齐后统一做）
    computed = {}
    spec_result_rows = []
    new_rows = []

    def _skip_line(lid, snap, note):
        """落 undetermined 行 + 逐规格 not_judged 结果行（矩阵账平）。"""
        new_rows.append(schema.verdict_row(
            lid, "undetermined", claim_ref=snap.get("claim_ref"),
            quadrant="undetermined",
            n_registered=snap.get("n_registered"),
            n_effective=snap.get("n_effective"),
            note=note, decided_by=decided_by, decided_at=today()))
        for spec in included:
            spec_result_rows.append({
                "spec_id": spec["spec_id"], "registry_line_id": lid,
                "status": "not_judged", "reason": note})

    for lid in judgeable:
        snap = snap_lines[lid]
        entry = data_lines.get(lid)
        base_note = []
        if entry is None:
            _skip_line(lid, snap,
                       "判定材料未登记该行（judge-data 缺行）：无材料不许判")
            continue
        bad_keys = set(entry) - _DATA_KEYS
        if bad_keys:
            raise JudgeError([f"登记行 {lid} 判定材料含未知字段 {sorted(bad_keys)}"
                              "（列名机械核对：字段集与登记口径对不齐）"])
        sesoi_entry = sesoi_map.get(lid)
        if sesoi_entry is None:
            _skip_line(lid, snap,
                       "SESOI 未在分析规格登记（spec.sesoi 缺行）：判定计算"
                       "只认登记快照值，不许临场从 Design 文本猜")
            continue
        sesoi = float(sesoi_entry["sesoi_value"])
        try:
            arms = _arms(entry)
        except ValueError as e:
            _skip_line(lid, snap, f"判定材料不合格：{e}")
            continue
        if arms["form"] == "raw" and snap.get("n_effective") is not None \
                and len(arms["a"]) != snap["n_effective"]:
            _skip_line(lid, snap,
                       f"判定材料 n={len(arms['a'])} 与对账有效 n="
                       f"{snap['n_effective']} 不一致：材料对不齐不许判")
            continue

        reg = reg_rows.get(lid) or {}
        direction_word = ((reg.get("primary_metric") or {}).get("direction")
                          or "higher")
        sign = 1 if direction_word != "lower" else -1
        q = _primary_quantities(arms, sign)

        # 逐规格计算（联合推断材料）
        spec_effects, spec_ps, spec_signs = [], [], []
        for spec in included:
            eff, p, degraded = _spec_effect(spec, arms, sign)
            spec_effects.append(eff)
            spec_ps.append(p)
            spec_signs.append(1 if eff > 0 else (-1 if eff < 0 else 0))
            spec_result_rows.append({
                "spec_id": spec["spec_id"], "registry_line_id": lid,
                "status": "computed",
                "effect_size": {"type": (spec.get("choices") or {}).get(
                    "estimator", "mean_diff"), "value": eff},
                "p_value": p,
                "note": degraded,
                "provenance": q["provenance"] if spec is primary else None,
            })
        direction_sign = 1 if q["effect"] > 0 else (-1 if q["effect"] < 0 else 0)
        # 同向份额：符号一致，或主效应与该规格效应都小于 SESOI（等价一致，
        # null 行的方向份额按等价口径算，不按符号算）
        agree = sum(1 for e in spec_effects
                    if (e != 0 and (1 if e > 0 else -1) == direction_sign)
                    or (abs(e) < sesoi and abs(q["effect"]) < sesoi))
        joint = {
            "median_effect": statistics.median(spec_effects),
            "direction_share": (agree / len(spec_effects)) if spec_effects else 0.0,
            "stouffer_p": calc.stouffer_combine(spec_ps, spec_signs)["p_two_sided"],
            "specs_used": [s["spec_id"] for s in included],
        }
        tost_res = calc.tost(q["effect"], q["se"], q["df"], sesoi,
                             alpha=(fam_by_line.get(lid) or {}).get("alpha", 0.05))
        da = calc.design_analysis(sesoi, q["se"],
                                  alpha=(fam_by_line.get(lid) or {}).get("alpha", 0.05))
        computed[lid] = {
            "snap": snap, "entry": entry, "sign": sign,
            "direction_word": direction_word, "sesoi": sesoi,
            "sesoi_entry": sesoi_entry, "q": q, "joint": joint,
            "tost": tost_res, "design_analysis": da,
            "base_note": base_note,
        }

    # ---- 按族校正（拍板⑥：族口径以登记头声明为准）
    corr_items = [{"line_id": lid, "p_raw": c["q"]["p_raw"]}
                  for lid, c in computed.items()]
    corr_map = calc.corrections_by_family(corr_items, families) \
        if corr_items else {}

    # ---- 第二遍：落字
    for lid, c in computed.items():
        snap, q, joint = c["snap"], c["q"], c["joint"]
        fam = fam_by_line.get(lid) or {}
        alpha = fam.get("alpha", 0.05)
        corr = corr_map[lid]
        da = c["design_analysis"]
        # 分布判据按判定方向取概率：沿登记方向为 P(更优)，逆登记方向为 P(更劣)
        p_claim = q["p_better"] if q["effect"] >= 0 else q["p_worse"]
        verdict, quadrant, gate_notes = _decide(
            effect=q["effect"], p_adj=corr["p_adj"], p_ab=p_claim,
            alpha=alpha, gamma=gamma, joint=joint,
            type_m=da["type_m"], type_m_max=type_m_max,
            tost_pass=c["tost"]["result"] == "pass",
            null_precision_warning=bool(snap.get("null_precision_warning")))
        grade, cap_reason = grading.row_grade(
            verdict, joint["direction_share"],
            type_m=da["type_m"], tost_p=c["tost"]["p_tost"], alpha=alpha)
        note_parts = list(gate_notes)
        if verdict in ("positive", "negative", "null"):
            note_parts.append(
                f"按冻结判据落字：主规格 {primary['spec_id']}、"
                f"方向份额 {joint['direction_share']:.2f}、"
                f"中位效应 {joint['median_effect']:.4g}")
        row = schema.verdict_row(
            lid, verdict, claim_ref=snap.get("claim_ref"),
            quadrant=quadrant,
            basis_spec_id=primary["spec_id"],
            criteria_ref=(f"登记行冻结判据 direction={c['direction_word']}，"
                          f"SESOI 指针 {c['sesoi_entry']['sesoi_pointer']}"),
            direction=c["direction_word"],
            effect_size={"type": "mean_diff", "value": q["effect"]},
            interval=q["interval"],
            p_ab=p_claim, p_ab_gamma=gamma,
            n_effective=snap.get("n_effective"), n_registered=snap.get("n_registered"),
            type_sm={"assumed_D": {"value": c["sesoi"],
                                   "basis": "sesoi_frozen",
                                   "source_ref": c["sesoi_entry"]["sesoi_pointer"]},
                     "power": da["power"], "type_s": da["type_s"],
                     "type_m": da["type_m"]},
            tost={"bounds": {"lo": -c["sesoi"], "hi": c["sesoi"],
                             "source": "design_sesoi"},
                  "p_tost": c["tost"]["p_tost"],
                  "ci90": c["tost"]["ci90"],
                  "ci90_in_bounds": c["tost"]["ci90_in_bounds"],
                  "result": c["tost"]["result"]},
            correction=corr,
            strength_grade=grade, strength_cap_reason=cap_reason,
            note="；".join(note_parts),
            decided_by=decided_by, decided_at=today())
        row["joint"] = joint
        row["calc_provenance"] = q["provenance"]
        row["distribution_ref"] = {
            "source": "judge-data", "data_file": str(data_path),
            "reference_label": c["entry"].get("reference_label"),
            "run_refs": c["entry"].get("run_refs") or [],
        }
        if c["entry"].get("validity_residual"):
            row["validity_residual"] = c["entry"]["validity_residual"]
        if c["entry"].get("bayes") or c["entry"].get("diagnostics"):
            row["bayes"] = True
            diag = c["entry"].get("diagnostics")
            row["diagnostics"] = diag
            diag_fail = (not diag) or any(diag.get(k) is None for k in
                                          ("r_hat", "ess_bulk", "ess_tail", "mcse")) \
                or diag.get("r_hat", 0) >= schema.R_HAT_MAX \
                or diag.get("ess_bulk", 0) <= schema.ESS_MIN \
                or diag.get("ess_tail", 0) <= schema.ESS_MIN
            if diag_fail and verdict != "undetermined":
                row["verdict"] = "undetermined"
                row["quadrant"] = "undetermined"
                row["strength_grade"] = None
                row["strength_cap_reason"] = None
                row["note"] = ("贝叶斯诊断未过门（rank-normalized R̂<1.01、"
                               "ESS_bulk/ESS_tail 均 >400 为硬字段门）："
                               "诊断未过，只许落 undetermined")
        new_rows.append(row)

    # ---- spec_results 账平：终态行落显式 not_judged 行
    for lid, snap in snap_lines.items():
        if lid in judgeable:
            continue
        for spec in included:
            spec_result_rows.append({
                "spec_id": spec["spec_id"], "registry_line_id": lid,
                "status": "not_judged",
                "reason": "承接预登记终态行（untested/undetermined），不进判定计算",
            })

    all_rows = assign_row_refs((pkg["verdicts"] or []) + new_rows)
    save_verdicts(root, all_rows)
    existing_sr = pkg["spec_results"] or []
    save_spec_results(root, existing_sr + spec_result_rows)
    pkg2 = load_package(root)
    refresh_counts(pkg2["analysis"], all_rows)
    pkg2["analysis"].setdefault("judge_runs", []).append({
        "at": today(), "data_file": str(data_path),
        "data_hash": sha256_file(data_path),
        "primary_spec_id": primary["spec_id"],
        "lines_judged": sorted(computed),
        "by": decided_by,
    })
    spec_area = pkg2["analysis"].setdefault("spec", {})
    spec_area["primary_spec_id"] = primary["spec_id"]
    save_analysis(root, pkg2["analysis"])
    return {"judged": sorted(computed),
            "undetermined": sorted(r["registry_line_id"] for r in new_rows
                                   if r["verdict"] == "undetermined"),
            "primary_spec_id": primary["spec_id"],
            "spec_results_rows": len(spec_result_rows)}


# ---------------------------------------------------------------- 回流

REFLUX_KINDS = {
    "supplementary_ablation": "experiment",   # 补充消融：≤1 轮、一次提全
    "standard_gap": "design",                 # 标准缺失报告
    "evidence_notice": "idea",                # 主张证据状态通知
}


def request_reflux(root, kind, line_ids, reason, target=None) -> dict:
    """生成回流条目：落 analysis.yaml + conclusions.yaml + reflux/<id>.json。

    只生成条目、不越权决策（接收端是 Experiment/Design/Idea 的既有
    回流口径）。supplementary_ablation 全生命周期 ≤1 轮：已有同类
    条目时再请求直接拒绝。
    """
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise JudgeError(["分析包不存在（先 init）"])
    if kind not in REFLUX_KINDS:
        raise JudgeError([f"回流 kind {kind!r} 不在词表 {sorted(REFLUX_KINDS)}"])
    existing = analysis.get("reflux") or []
    if kind == "supplementary_ablation" and \
            any(r.get("kind") == kind for r in existing):
        raise JudgeError(["补充消融全生命周期只许 1 轮且一次提全："
                          "本包已有 supplementary_ablation 条目，不许再提"])
    entry = {
        "reflux_id": f"RX-A{len(existing) + 1:03d}",
        "kind": kind,
        "target": target or REFLUX_KINDS[kind],
        "line_ids": list(line_ids),
        "reason": reason,
        "requested_at": today(),
        "analysis_id": analysis.get("analysis_id"),
        "design_content_hash": (analysis.get("design_ref") or {}).get("content_hash"),
    }
    analysis.setdefault("reflux", []).append(entry)
    save_analysis(root, analysis)
    conclusions = pkg["conclusions"] or schema.new_conclusions()
    conclusions.setdefault("reflux", []).append({
        "kind": kind, "target": entry["target"],
        "detail": f"{entry['reflux_id']}：{reason}（行 {'/'.join(line_ids)}）",
        "reflux_id": entry["reflux_id"],
    })
    save_conclusions(root, conclusions)
    out_dir = root / "reflux"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{entry['reflux_id']}.json"
    dump_json(out_path, entry)
    entry["file"] = str(out_path)
    return entry
