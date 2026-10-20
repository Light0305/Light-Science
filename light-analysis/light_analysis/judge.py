"""判定子流程（Phase 2）：SESOI 登记、逐行判定落字、补充消融回流。

纪律要点（LEARNING 约束 1/2/3/6/11 + 拍板①③⑥）：
- 判定计算只认分析规格登记值：SESOI 必须先登记进 analysis.yaml 的
  spec 区；judge 时 SESOI 未登记的行直接落 undetermined，不许临场
  从文本猜。登记三路（v1.1 ANA-D02）：主路 `register_sesoi_from_registry`
  直读 A0 承接捕获的登记行结构化块（DES-D01）；结构化指针路取到登记
  块时整块快照；裸数值指针路为 v1.0 兼容路（via=pointer_compat）。
  任一路登记都与登记行块比对，不一致拒绝并点名；judge 开判前再比对
  一遍。快照在案但结构不完整（值非正数/块缺字段/块值与快照值不符）
  的行落 undetermined 并点名缺陷，绝不猜测、绝不用分析时临时值。
- positive 双门：规格集联合推断（中位效应同向 + 方向份额 ≥0.5 +
  Stouffer 合并 p 达门）与 Type S/M 校准（D = 登记 SESOI，Type M 不超
  规格登记阈值，默认 2.0）缺一不可；任一门未过落 undetermined 并逐项
  点名缺哪门。
- null 必须靠 TOST 挣来；承接带 null 精度预警的行判不了 null。
- 判定材料（judge-data）逐行登记两臂原始值（或分布摘要），列名/字段
  机械核对：未知行、缺行、n 与对账不一致都在本层点名（防 BLADE 式
  幻觉列名与单点冒充分布）。
- 配对/区组结构（ANA-D03）：结构声明两处对表（judge-data 条目的
  pairing 与登记行经 intake 透传的 pairing），不一致逐行落
  undetermined 点名；声明在案时判定走差值序列口径（paired 按对齐键
  作差、blocked 先算区组内对照），声明与数据不符（无对齐键、缺对侧、
  区组缺臂、只有摘要材料）逐行落 undetermined 点名，绝不静默按独立
  样本判；未声明时走既有独立口径并在 structure 区落结构假设，两臂
  同源信号（run 引用交叠 / 两臂逐元素相同）点名警告不改判。
- 稳健性覆盖（ANA-D04 短期）：真改计算的决策点只有
  COMPUTED_DECISION_POINTS（与 _spec_effect 的实现同源），冻结账本
  其余决策点只留痕；每行落 robustness_scope 机械列明，留痕点占比
  过半时方向性行强度封顶 suggestive 并点名（grading.row_grade）。
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
              "bayes", "diagnostics", "validity_residual",
              "pairing", "treatment_keys", "reference_keys",
              "treatment_run_refs", "reference_run_refs"}

# ANA-D04：真改判定计算的决策点集——与 _spec_effect 的实际实现同源
# （estimator 决定逐规格口径，其余决策点 v1 只留痕不改计算）。账本里
# 不在此集的决策点一律 trace_only，robustness_scope 据此机械导出。
COMPUTED_DECISION_POINTS = {"estimator"}


def robustness_scope_of(ledger) -> dict:
    """由冻结账本机械导出稳健性覆盖（ANA-D04 短期落字）。

    方向份额只反映 computed 决策点维度的稳健性；trace_only 决策点的
    规格与主规格数值成对相同，不许被读成「该维度也验过」。
    """
    points = [d.get("point") for d in (ledger or {}).get("decisions") or []]
    computed = [p for p in points if p in COMPUTED_DECISION_POINTS]
    trace = [p for p in points if p not in COMPUTED_DECISION_POINTS]
    total = len(points)
    return {
        "computed": computed,
        "trace_only": trace,
        "trace_only_fraction": (len(trace) / total) if total else 0.0,
        "basis": "真改计算的决策点集由 light_analysis.judge."
                 "COMPUTED_DECISION_POINTS 声明（与逐规格计算实现同源），"
                 "账本其余决策点只留痕不改计算（ANA-D04）",
    }


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


def _registry_conflicts(analysis, line_ids, entry) -> list:
    """ANA-D02 一致性比对：待登记快照 vs 登记行块（承接快照内）。

    登记行带结构化块时，本次登记的值/块必须与之逐字段一致；
    不一致返回逐行点名的错误列表（两处 SESOI 必须同源）。"""
    errs: list = []
    snap_lines = {l["registry_line_id"]: l
                  for l in (analysis.get("registry_snapshot") or {}).get("lines")
                  or []}
    for lid in line_ids:
        blk = (snap_lines.get(lid) or {}).get("sesoi")
        if not isinstance(blk, dict):
            continue
        if entry.get("sesoi_block") is not None:
            diff = schema.sesoi_diff_fields(entry["sesoi_block"], blk)
            if diff:
                errs.append(
                    f"登记行 {lid} 的 sesoi 登记块与本次登记快照不一致"
                    f"（字段 {diff}）：两处 SESOI 必须同源，拒绝登记")
        else:
            cb = schema.sesoi_canonical(blk)
            if cb is None or cb.get("value") is None:
                errs.append(f"登记行 {lid} 的 sesoi 登记块不完整，"
                            "无法与本次登记值比对：拒绝登记")
            elif float(cb["value"]) != float(entry["sesoi_value"]):
                errs.append(
                    f"登记行 {lid} 的 sesoi 登记值 {cb['value']} 与本次"
                    f"登记值 {entry['sesoi_value']} 不一致：拒绝登记")
    return errs


def register_sesoi(root, source_path, pointer, line_ids=None) -> dict:
    """从 Design 来源文件按指针取 SESOI，落快照进 analysis.yaml 的 spec 区。

    指针取到结构化登记块（dict）时整块快照（via=structured_block，
    块不完整直接拒）；取到裸正数时按 v1.0 形态快照（via=pointer_compat，
    旧登记表兼容路）。快照带 source_hash，来源文件事后变动验得出。
    登记前与登记行块比对（_registry_conflicts），不一致拒绝。
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
    snap = (analysis.get("registry_snapshot") or {}).get("lines") or []
    if line_ids is None:
        line_ids = [l["registry_line_id"] for l in snap
                    if l.get("judgeability") == "judgeable"]
    if isinstance(value, dict):
        berrs = schema.validate_sesoi_block(value)
        if berrs:
            raise JudgeError([f"指针 {pointer} 取到的 SESOI 登记块不完整："
                              + "；".join(berrs)])
        block = schema.sesoi_canonical(value)
        entry = {
            "sesoi_pointer": pointer,
            "sesoi_value": float(block["value"]),
            "sesoi_block": block,
            "via": "structured_block",
            "source_path": str(source_path),
            "source_hash": sha256_file(source_path),
            "registered_at": today(),
        }
    elif isinstance(value, (int, float)) and not isinstance(value, bool) \
            and float(value) > 0:
        entry = {
            "sesoi_pointer": pointer,
            "sesoi_value": float(value),
            "via": "pointer_compat",
            "source_path": str(source_path),
            "source_hash": sha256_file(source_path),
            "registered_at": today(),
        }
    else:
        raise JudgeError([f"指针 {pointer} 取到 {value!r}，SESOI 须为正数"
                          "或完整的结构化登记块"])
    conflicts = _registry_conflicts(analysis, line_ids, entry)
    if conflicts:
        raise JudgeError(conflicts)
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


def register_sesoi_from_registry(root, line_ids=None) -> dict:
    """ANA-D02 主路：直读承接快照中的登记行 SESOI 块生成 spec 快照。

    块已在 A0 承接时从 expected_registry 登记行捕获（DES-D01 派生
    副本）；本函数逐行校验完整性后整块快照进 spec.sesoi，条目带
    登记表哈希与 design content_hash，Design amendment 后漂移可察。
    无块的行跳过并在返回中点名（skipped）；全部行都无块时报错，
    提示改走指针兼容路。返回 {registered, skipped, entry}。
    """
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise JudgeError(["分析包不存在（先 init）"])
    snap = (analysis.get("registry_snapshot") or {}).get("lines") or []
    design_ref = analysis.get("design_ref") or {}
    registry_path = design_ref.get("registry_path")
    if line_ids is None:
        line_ids = [l["registry_line_id"] for l in snap
                    if l.get("judgeability") == "judgeable"]
    by_id = {l["registry_line_id"]: l for l in snap}
    entries: dict = {}
    registered: list = []
    skipped: list = []
    for lid in line_ids:
        blk = (by_id.get(lid) or {}).get("sesoi")
        if not isinstance(blk, dict):
            skipped.append(lid)
            continue
        berrs = schema.validate_sesoi_block(blk)
        if berrs:
            raise JudgeError([f"登记行 {lid} 的 sesoi 登记块不完整："
                              + "；".join(berrs)])
        entries[lid] = {
            "sesoi_pointer": "expected_registry.sesoi",
            "sesoi_value": float(blk["value"]),
            "sesoi_block": schema.sesoi_canonical(blk),
            "via": "registry_row",
            "source_path": registry_path,
            "source_hash": sha256_file(registry_path)
            if registry_path and Path(registry_path).exists() else None,
            "registry_hash": design_ref.get("registry_hash"),
            "design_content_hash": design_ref.get("content_hash"),
            "registered_at": today(),
        }
        registered.append(lid)
    if not registered:
        raise JudgeError(["登记行未携带结构化 SESOI 登记块（DES-D01 之前"
                          "的旧登记表）：请改走 register-sesoi 指针兼容路径"])
    spec = analysis.setdefault("spec", {})
    sesoi_map = spec.setdefault("sesoi", {})
    sesoi_map.update(entries)
    spec.setdefault("judge_params", {
        "gamma": schema.GAMMA_DEFAULT,
        "type_m_max": TYPE_M_MAX_DEFAULT,
    })
    save_analysis(root, analysis)
    return {"registered": registered, "skipped": skipped,
            "entry": entries[registered[0]]}


def _sesoi_entry_defect(entry) -> str | None:
    """快照条目结构缺陷（ANA-D02）：值须为正数；带块时块须完整且值一致。

    返回缺陷描述（None = 结构完整）。兼容路条目（无块）只验值。"""
    if not isinstance(entry, dict):
        return "快照条目不是映射"
    v = entry.get("sesoi_value")
    if isinstance(v, bool) or not isinstance(v, (int, float)) \
            or float(v) <= 0:
        return f"快照值 sesoi_value={v!r} 缺失或不是正数"
    blk = entry.get("sesoi_block")
    if blk is not None:
        errs = schema.validate_sesoi_block(blk)
        if errs:
            return "；".join(errs)
        if float(blk["value"]) != float(v):
            return (f"登记块 value={blk['value']} 与快照值 "
                    f"sesoi_value={v} 不一致")
    return None


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


_STRUCTURE_MODES = ("paired", "blocked")


def _decl_key(decl):
    if not isinstance(decl, dict):
        return None
    if decl.get("mode") == "paired":
        return decl.get("paired_by")
    if decl.get("mode") == "blocked":
        return decl.get("blocked_by")
    return None


def _resolve_structure(entry, snap):
    """结构声明对表（ANA-D03）。返回 (decl | None, defect | None)。

    decl = {mode, key, source}。两处（judge-data 条目 / 登记行快照）
    都无声明 → (None, None) 走独立口径；任一处形状不对、或两处
    mode/键名不一致 → defect 点名（该行落 undetermined）。
    """
    jd = entry.get("pairing")
    rg = (snap or {}).get("pairing")
    for tag, d in (("判定材料", jd), ("登记行", rg)):
        if d is None:
            continue
        if not isinstance(d, dict) or d.get("mode") not in _STRUCTURE_MODES:
            return None, (f"{tag}的 pairing 结构声明形状不对：mode 须为 "
                          "paired 或 blocked（ANA-D03）")
        if not (isinstance(_decl_key(d), str) and _decl_key(d).strip()):
            field = "paired_by" if d["mode"] == "paired" else "blocked_by"
            return None, (f"{tag}的 pairing 结构声明缺 {field} 键名"
                          "（ANA-D03）")
    if jd is not None and rg is not None:
        if jd["mode"] != rg["mode"] or _decl_key(jd) != _decl_key(rg):
            return None, (
                "判定材料与登记行的结构声明不一致（材料 "
                f"{jd['mode']}/{_decl_key(jd)} vs 登记行 "
                f"{rg['mode']}/{_decl_key(rg)}）：两个完整来源互相矛盾，"
                "不许带病开判（ANA-D03）")
        return {"mode": jd["mode"], "key": _decl_key(jd),
                "source": "judge_data+registry_row"}, None
    if jd is not None:
        return {"mode": jd["mode"], "key": _decl_key(jd),
                "source": "judge_data"}, None
    if rg is not None:
        return {"mode": rg["mode"], "key": _decl_key(rg),
                "source": "registry_row"}, None
    return None, None


def _structure_units(entry, decl):
    """按声明从原始两臂取判定单位序列（未取向：差值或区组内对照）。

    材料与声明不符抛 ValueError（点名文本，调用方落 undetermined）。
    """
    ka = entry.get("treatment_keys")
    kb = entry.get("reference_keys")
    if ka is None or kb is None:
        raise ValueError(
            f"声明 {decl['mode']} 结构（键 {decl['key']}）但判定材料缺 "
            "treatment_keys/reference_keys 对齐键：声明了结构就必须给"
            "两臂逐元素对齐键，不许按位置或独立样本凑（ANA-D03）")
    if decl["mode"] == "paired":
        return calc.align_by_keys(entry["treatment"], ka,
                                  entry["reference"], kb)
    return calc.block_contrasts(entry["treatment"], ka,
                                entry["reference"], kb)


def _same_origin_warnings(entry, arms):
    """未声明结构时的同源信号（ANA-D03）：点名警告，不改判。"""
    warns = []
    tra = set(entry.get("treatment_run_refs") or [])
    rra = set(entry.get("reference_run_refs") or [])
    if tra and rra and (tra & rra):
        warns.append("两臂 run 引用交叠（" + "、".join(sorted(tra & rra))
                     + "）：同源信号，未声明配对/区组结构——本行按独立"
                     "样本口径判，该事实只警告落字（ANA-D03）")
    if arms.get("form") == "raw" and arms["a"] == arms["b"]:
        warns.append("两臂原始值逐元素完全相同：同源/配对信号，未声明"
                     "配对结构——本行按独立样本口径判，该事实只警告"
                     "落字（ANA-D03）")
    return warns


def _spec_effect(spec, arms, sign, units=None):
    """逐规格效应与 p：estimator 决策点决定口径，其余决策点 v1 只留痕。

    mean_diff → Welch；median_diff → 中位差 + Mann-Whitney p；
    摘要材料下秩类规格退化为 Welch 口径（在结果行 note 落字）。
    结构在案时（units = 未取向差值/区组对照序列）改走配对口径：
    mean_diff → 差值均值 + 单样本 t p；median_diff → 差值中位数 +
    符号检验 p。
    返回 (oriented_effect, p_two_sided, degraded_note | None)。
    """
    estimator = (spec.get("choices") or {}).get("estimator", "mean_diff")
    if units is not None:
        if estimator == "median_diff":
            vals = sorted(units)
            m = len(vals) // 2
            med = vals[m] if len(vals) % 2 else 0.5 * (vals[m - 1] + vals[m])
            return sign * med, calc.sign_test_p(units)["p_two_sided"], None
        res = calc.paired_effect_and_ci(units)
        return sign * res["mean_diff"], res["p_two_sided"], None
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


def _primary_quantities(arms, sign, units=None):
    """主规格量组：效应 + 区间 + P(向登记方向更优) + SE/df（TOST 与校准共用）。

    units 在案时（ANA-D03 结构口径）量组全部取自差值/区组对照序列：
    效应 = 取向后差值均值、SE/df 为单样本口径、P 对为配对符号口径。
    """
    if units is not None:
        res = calc.paired_effect_and_ci(units)
        oriented = [sign * d for d in units]
        return {
            "effect": sign * res["mean_diff"],
            "se": res["se"], "df": res["df"],
            "interval": {"kind": "ci", "level": 0.95,
                         "lo": sign * res["ci"]["lo"] if sign > 0
                         else -res["ci"]["hi"],
                         "hi": sign * res["ci"]["hi"] if sign > 0
                         else -res["ci"]["lo"]},
            "hedges_g": (sign * res["hedges_g"]
                         if res["hedges_g"] is not None else None),
            "p_raw": res["p_two_sided"],
            "p_better": calc.p_superiority_paired(oriented)["value"],
            "p_worse": calc.p_superiority_paired(
                [-d for d in oriented])["value"],
            "provenance": res["provenance"],
        }
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

    # ANA-D02 开判前比对：登记行块（承接快照）vs spec 登记快照，
    # 两处不一致整包点名拒绝——不许带病开判，事后改判更不许。
    # 域划分：条目本身结构残缺（_sesoi_entry_defect 非空）的不在此比对，
    # 留给逐行判定落 undetermined 并点名缺陷；此处只拦「条目完整但与
    # 登记行分歧」——两个完整来源互相矛盾才是带病开判。
    conflicts: list = []
    for lid in judgeable:
        blk = snap_lines[lid].get("sesoi")
        entry = sesoi_map.get(lid)
        if not isinstance(blk, dict) or entry is None:
            continue
        if _sesoi_entry_defect(entry) is not None:
            continue
        if entry.get("sesoi_block") is not None:
            diff = schema.sesoi_diff_fields(entry["sesoi_block"], blk)
            if diff:
                conflicts.append(
                    f"登记行 {lid}：spec 快照 SESOI 与登记行登记块不一致"
                    f"（字段 {diff}）")
        else:
            cb = schema.sesoi_canonical(blk)
            ev_ = entry.get("sesoi_value")
            if cb is not None and cb.get("value") is not None \
                    and isinstance(ev_, (int, float)) \
                    and float(cb["value"]) != float(ev_):
                conflicts.append(
                    f"登记行 {lid}：spec 快照 SESOI 值 {ev_} 与登记行"
                    f"登记值 {cb['value']} 不一致")
    if conflicts:
        raise JudgeError(conflicts + [
            "两处 SESOI 不一致：先对齐登记（Design 侧 amendment 或重新"
            "登记），不许带病开判"])

    analyst = analysis.get("analyst") or {}
    decided_by = decided_by or analyst.get("name") or "light-analysis judge"

    scope = robustness_scope_of(ledger)

    # ---- 第一遍：逐行计算量组与逐规格结果（校正须全行 p 齐后统一做）
    computed = {}
    spec_result_rows = []
    new_rows = []

    def _skip_line(lid, snap, note, structure=None):
        """落 undetermined 行 + 逐规格 not_judged 结果行（矩阵账平）。"""
        new_rows.append(schema.verdict_row(
            lid, "undetermined", claim_ref=snap.get("claim_ref"),
            quadrant="undetermined",
            n_registered=snap.get("n_registered"),
            n_effective=snap.get("n_effective"),
            structure=structure, robustness_scope=scope,
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
        defect = _sesoi_entry_defect(sesoi_entry)
        if defect:
            _skip_line(lid, snap,
                       f"SESOI 登记快照不完整：{defect}（判定只认结构完整"
                       "的登记快照，缺失或不完整不许猜测、不用临时值）")
            continue
        sesoi = float(sesoi_entry["sesoi_value"])
        try:
            arms = _arms(entry)
        except ValueError as e:
            _skip_line(lid, snap, f"判定材料不合格：{e}")
            continue
        # ANA-D03 结构对表：声明在案必须被 honored，声明与材料不符
        # 逐行落 undetermined 点名，绝不静默按独立样本判。
        decl, defect = _resolve_structure(entry, snap)
        units = None
        structure = None
        if defect:
            _skip_line(lid, snap, defect, structure={
                "mode": None,
                "assumption": "structure_declaration_conflict",
                "key": None, "source": None, "n_units": None,
                "warnings": []})
            continue
        if decl is not None:
            structure = {"mode": decl["mode"], "assumption": "declared",
                         "key": decl["key"], "source": decl["source"],
                         "n_units": None, "warnings": []}
            if arms["form"] != "raw":
                _skip_line(lid, snap,
                           f"声明 {decl['mode']} 结构（键 {decl['key']}）但"
                           "判定材料只有分布摘要：配对/区组对齐须逐元素"
                           "原始值，摘要无从对齐（ANA-D03）",
                           structure=structure)
                continue
            try:
                units = _structure_units(entry, decl)
            except ValueError as e:
                _skip_line(lid, snap, f"结构声明与材料不符：{e}",
                           structure=structure)
                continue
            structure["n_units"] = len(units)
        else:
            structure = {"mode": "independent",
                         "assumption": "undeclared_independent_default",
                         "key": None, "source": None, "n_units": None,
                         "warnings": _same_origin_warnings(entry, arms)}
        blocked = decl is not None and decl["mode"] == "blocked"
        if arms["form"] == "raw" and not blocked \
                and snap.get("n_effective") is not None \
                and len(arms["a"]) != snap["n_effective"]:
            _skip_line(lid, snap,
                       f"判定材料 n={len(arms['a'])} 与对账有效 n="
                       f"{snap['n_effective']} 不一致：材料对不齐不许判",
                       structure=structure)
            continue

        reg = reg_rows.get(lid) or {}
        direction_word = ((reg.get("primary_metric") or {}).get("direction")
                          or "higher")
        sign = 1 if direction_word != "lower" else -1
        q = _primary_quantities(arms, sign, units=units)

        # 逐规格计算（联合推断材料）
        spec_effects, spec_ps, spec_signs = [], [], []
        for spec in included:
            eff, p, degraded = _spec_effect(spec, arms, sign, units=units)
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
        alpha_l = (fam_by_line.get(lid) or {}).get("alpha", 0.05)
        if units is not None:
            tost_res = calc.tost_paired([sign * d for d in units], sesoi,
                                        alpha=alpha_l)
        else:
            tost_res = calc.tost(q["effect"], q["se"], q["df"], sesoi,
                                 alpha=alpha_l)
        if q["se"] > 0:
            da = calc.design_analysis(sesoi, q["se"], alpha=alpha_l)
        else:
            # 配对差值零方差的退化情形：设计分析取 SE 趋 0 的极限值
            da = {"assumed_D": sesoi, "se": 0.0, "alpha": alpha_l,
                  "power": 1.0, "type_s": 0.0, "type_m": 1.0,
                  "exaggeration_ratio": 1.0,
                  "provenance": {"method": "design_analysis_se0_limit"}}
        computed[lid] = {
            "snap": snap, "entry": entry, "sign": sign,
            "direction_word": direction_word, "sesoi": sesoi,
            "sesoi_entry": sesoi_entry, "q": q, "joint": joint,
            "tost": tost_res, "design_analysis": da,
            "structure": structure,
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
            type_m=da["type_m"], tost_p=c["tost"]["p_tost"], alpha=alpha,
            robustness_scope=scope)
        note_parts = list(gate_notes)
        if verdict in ("positive", "negative", "null"):
            note_parts.append(
                f"按冻结判据落字：主规格 {primary['spec_id']}、"
                f"方向份额 {joint['direction_share']:.2f}、"
                f"中位效应 {joint['median_effect']:.4g}")
        st = c["structure"]
        if st["mode"] in ("paired", "blocked"):
            unit_label = "对" if st["mode"] == "paired" else "区组"
            note_parts.append(
                f"结构口径 {st['mode']}（键 {st['key']}、"
                f"{st['n_units']} 个{unit_label}、声明来源 "
                f"{st['source']}）：效应与 TOST 走差值序列口径（ANA-D03）")
        note_parts.extend(st.get("warnings") or [])
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
            structure=c["structure"], robustness_scope=scope,
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
