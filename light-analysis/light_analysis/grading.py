"""结论强度合成（约束 8）：机械合成式，judge（行级）与 conclude（主张级）共用。

强度 = 证据类型上限 × 规格稳健度 × 校准（Type S/M / TOST）逐项合成，
不许只给总档：合成输入逐项落字（行级落 direction_share / type_m，
主张级落 conclusions.strength[].inputs），cap_reason 写明封顶来源。

档位序：conclusive > strong > suggestive > insufficient。
undetermined / untested 是判定状态、不是强度——行级不入档（返回 None），
主张级若含未检验行，support 先落 untested、强度封顶 insufficient 并注明。
措辞纪律：本模块产生的文本不许出现冻结词表禁用词（校验器会扫）。
"""

from __future__ import annotations

GRADE_ORDER = ["insufficient", "suggestive", "strong", "conclusive"]


def _cap(grade: str, cap: str) -> str:
    return grade if GRADE_ORDER.index(grade) <= GRADE_ORDER.index(cap) else cap


def _min_grade(grades) -> str:
    return min(grades, key=GRADE_ORDER.index)


def robustness_tier(direction_share) -> str:
    """规格稳健档：方向份额 → high / medium / low（落字用英文档名，全包一致）。"""
    if direction_share is None:
        return "unknown"
    if direction_share >= 0.9:
        return "high"
    if direction_share >= 0.75:
        return "medium"
    return "low"


def _scope_cap_clause(scope) -> str:
    """ANA-D04 稳健性覆盖封顶的点名句（方向份额只覆盖真算维度的事实）。"""
    frac = scope.get("trace_only_fraction") or 0.0
    return (f"稳健性覆盖封顶：留痕型决策点 {'/'.join(scope.get('trace_only') or [])}"
            f"占 {frac:.0%} 过半，方向份额只反映 "
            f"{'/'.join(scope.get('computed') or [])} 维度的稳健性，"
            "方向性行强度封顶 suggestive（ANA-D04）")


def row_grade(verdict, direction_share, type_m=None, tost_p=None,
              alpha=0.05, robustness_scope=None):
    """行级强度机械合成。返回 (grade | None, cap_reason)。

    方向性行（positive/negative）：
      conclusive ⟺ 全规格同向（share=1）且 Type M ≤ 1.5；
      strong     ⟺ share ≥ 0.75 且 Type M ≤ 2.0；
      suggestive ⟺ share ≥ 0.5；其余 insufficient。
    null 行以 TOST p 替代 Type M 作校准分量：
      conclusive ⟺ share=1 且 p_tost < α/5；strong ⟺ share ≥ 0.75 且
      p_tost < α；suggestive ⟺ share ≥ 0.5；其余 insufficient。
    稳健性覆盖封顶（ANA-D04 短期）：robustness_scope 在案且留痕型
    决策点占比过半时，方向性行再封顶 suggestive 并在 cap_reason
    点名——方向份额只证明真改计算的那几个决策点维度的稳健性。
    null 行不读此封顶（封顶只对方向性行）。
    """
    if verdict in ("undetermined", "untested"):
        return None, None
    share = 1.0 if direction_share is None else direction_share
    if verdict == "null":
        if share >= 1.0 and tost_p is not None and tost_p < alpha / 5:
            return "conclusive", "全规格同向且 TOST 余量充足，未封顶"
        if share >= 0.75 and tost_p is not None and tost_p < alpha:
            return "strong", "规格方向份额或 TOST 余量封顶 strong"
        if share >= 0.5:
            return "suggestive", "规格方向份额封顶 suggestive"
        return "insufficient", "规格方向份额过半未达，封顶 insufficient"
    # 方向性行
    tm = type_m if type_m is not None else float("inf")
    if share >= 1.0 and tm <= 1.5:
        grade, reason = "conclusive", "全规格同向且 Type M 余量充足，未封顶"
    elif share >= 0.75 and tm <= 2.0:
        grade, reason = "strong", "规格方向份额或 Type M 封顶 strong"
    elif share >= 0.5:
        grade, reason = "suggestive", "规格方向份额或 Type M 封顶 suggestive"
    else:
        grade, reason = "insufficient", "规格方向份额过半未达，封顶 insufficient"
    if robustness_scope is not None \
            and (robustness_scope.get("trace_only_fraction") or 0.0) > 0.5:
        clause = _scope_cap_clause(robustness_scope)
        if GRADE_ORDER.index(grade) > GRADE_ORDER.index("suggestive"):
            return "suggestive", clause
        return grade, f"{reason}；{clause}"
    return grade, reason


def claim_grade(support, line_grades, worst_share, type_sm_worst,
                validity_residual, robustness_scope=None):
    """主张级强度合成：行级最低档起步，再逐项封顶。返回 (grade, inputs, cap_reason)。

    封顶规则（逐项落字）：
      - 任一行未检验/不可判（support=untested 或含 undetermined 行的
        partial）：封顶 insufficient / suggestive 分别处理；
      - 稳健档 low（最差行方向份额 < 0.75）：封顶 suggestive；
      - Type M 最差值 > 2.0：封顶 suggestive；
      - 效度残余非空：封顶 strong。
    稳健性覆盖（ANA-D04）：robustness_scope 只落 inputs 供判读，不在
    主张级叠加第二重封顶——行级覆盖封顶已由行级最低档合成传导，
    同一事实不双重计罚。
    """
    caps = []
    if support == "untested":
        grade = "insufficient"
        caps.append("主张含未检验行，强度封顶 insufficient")
    else:
        grade = _min_grade(line_grades) if line_grades else "insufficient"
        if support == "partial":
            grade = _cap(grade, "suggestive")
            caps.append("主张内判定混合（partial），封顶 suggestive")
    tier = robustness_tier(worst_share)
    if tier == "low":
        grade = _cap(grade, "suggestive")
        caps.append("稳健档 low（最差行规格方向份额 <0.75），封顶 suggestive")
    if type_sm_worst is not None and type_sm_worst > 2.0:
        grade = _cap(grade, "suggestive")
        caps.append(f"Type M 最差值 {type_sm_worst:.2f} > 2.0，封顶 suggestive")
    if validity_residual:
        grade = _cap(grade, "strong")
        caps.append("效度残余非空，封顶 strong")
    inputs = {
        "line_grades": line_grades,
        "robustness_tier": tier,
        "worst_direction_share": worst_share,
        "type_sm_worst": type_sm_worst,
        "robustness_scope": robustness_scope,
        "validity_residual": list(validity_residual or []),
        "evidence_cap": ("分布材料（delivered 执行包对账分布）"
                         if support != "untested" else "含未检验行"),
    }
    cap_reason = "；".join(caps) if caps else "逐项合成未触发封顶"
    return grade, inputs, cap_reason
