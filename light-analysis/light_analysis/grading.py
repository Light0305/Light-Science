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


def row_grade(verdict, direction_share, type_m=None, tost_p=None,
              alpha=0.05):
    """行级强度机械合成。返回 (grade | None, cap_reason)。

    方向性行（positive/negative）：
      conclusive ⟺ 全规格同向（share=1）且 Type M ≤ 1.5；
      strong     ⟺ share ≥ 0.75 且 Type M ≤ 2.0；
      suggestive ⟺ share ≥ 0.5；其余 insufficient。
    null 行以 TOST p 替代 Type M 作校准分量：
      conclusive ⟺ share=1 且 p_tost < α/5；strong ⟺ share ≥ 0.75 且
      p_tost < α；suggestive ⟺ share ≥ 0.5；其余 insufficient。
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
        return "conclusive", "全规格同向且 Type M 余量充足，未封顶"
    if share >= 0.75 and tm <= 2.0:
        return "strong", "规格方向份额或 Type M 封顶 strong"
    if share >= 0.5:
        return "suggestive", "规格方向份额或 Type M 封顶 suggestive"
    return "insufficient", "规格方向份额过半未达，封顶 insufficient"


def claim_grade(support, line_grades, worst_share, type_sm_worst,
                validity_residual):
    """主张级强度合成：行级最低档起步，再逐项封顶。返回 (grade, inputs, cap_reason)。

    封顶规则（逐项落字）：
      - 任一行未检验/不可判（support=untested 或含 undetermined 行的
        partial）：封顶 insufficient / suggestive 分别处理；
      - 稳健档 low（最差行方向份额 < 0.75）：封顶 suggestive；
      - Type M 最差值 > 2.0：封顶 suggestive；
      - 效度残余非空：封顶 strong。
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
        "validity_residual": list(validity_residual or []),
        "evidence_cap": ("分布材料（delivered 执行包对账分布）"
                         if support != "untested" else "含未检验行"),
    }
    cap_reason = "；".join(caps) if caps else "逐项合成未触发封顶"
    return grade, inputs, cap_reason
