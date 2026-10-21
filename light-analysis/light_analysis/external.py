"""外部登记结果抽验协议（§7.0 外部抽验，第五批 P1-2）。

计算集外的模型（混合模型 / GLM / 贝叶斯采样等）走外部工具计算，
结果登记进判定材料（judge-data 条目的 external_result 字段）。
登记不等于采信：本模块按登记材料机械复算关键数字，任一抽验不过
即整行不判并点名——替代旧口径的「集外即空白」。

覆盖清单（成文，与 SKILL §7.0 同步）：
- 模型类（model_kind）：mixed_model / glm / bayes_sampling / other。
  类别只决定适用哪几项抽验，不决定采信程度。
- 抽验项：
  1. ci_from_effect_se：由 effect 与 se 按登记 df（t 分布；df 缺省
     走正态）与登记置信水平复算 CI，两端须与登记 CI 在有效数字
     取整容差内一致（登记按 reported_digits 位有效数字报告，
     容差 = 半个末位单位 × 1.0002 取整余量）。
  2. p_from_effect_se：由 effect/se 复算双侧 p（t 或正态），与
     登记 p_value 同容差比对；未登记 p 时跳过并在 checks 点名
     skipped（judge 以复算 p 为该行 p_raw，来源在行内点名）。
  3. materials_welch：登记了两组对照材料（group_summaries 两组
     {mean, spread, n}）时，复算 Welch 对照：符号须与登记 effect
     一致，且 |复算 − 登记| ≤ tolerance_materials（材料容差由
     登记者声明，缺声明而给材料 → 结构缺陷点名）。
  4. posterior_direction：登记了后验（posterior{mean, sd,
     prob_direction}）时，prob_direction 须与 Φ(mean/sd) 在
     0.01 绝对容差内一致（正态近似口径，成文声明）。
- 结构纪律：tool{name, version} / model_kind / model_spec /
  effect / se 必填；external_result 与两臂材料（treatment /
  reference / *_summary）不许同条目并存（judge 层点名拒绝）。

抽验只用纯标准库（calc 的 t/正态机械），不依赖外部统计包；
与 statsmodels/scipy 的数值对拍在包外抽验件
（05-analysis/external-crosscheck/）冻结成文。
"""

from __future__ import annotations

import math

from . import calc

MODEL_KINDS = ("mixed_model", "glm", "bayes_sampling", "other")
POSTERIOR_DIRECTION_TOL = 0.01


def _sig_tol(x: float, digits: int) -> float:
    """按有效数字取整容差：|x| 的第 digits 位有效数字的半个单位。

    x = 0 时以 10^(-digits) 为尺度（报告 0 意味着真值在该尺度内）。
    乘 1.0002 吸收浮点复算噪声，不放宽取整语义本身。
    """
    if x == 0:
        return 0.5001 * 10.0 ** (-digits)
    exp = math.floor(math.log10(abs(x)))
    return 0.5001 * 10.0 ** (exp - digits + 1)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) \
        and math.isfinite(v)


def spot_check_external(reg) -> dict:
    """对一条 external_result 登记做全项抽验。

    返回 {passed, checks: [{name, recomputed, registered, tol, ok,
    note?}], failures: [点名文本]}。结构缺陷直接进 failures 且
    passed=False（不抛异常：调用方按行落 undetermined 点名）。
    """
    checks: list[dict] = []
    failures: list[str] = []
    if not isinstance(reg, dict):
        return {"passed": False, "checks": checks,
                "failures": ["external_result 不是对象"]}

    tool = reg.get("tool") or {}
    if not tool.get("name") or not tool.get("version"):
        failures.append("external_result.tool 缺 name/version：外部结果"
                        "必须登记计算工具与版本，不许无出处登记")
    kind = reg.get("model_kind")
    if kind not in MODEL_KINDS:
        failures.append(f"external_result.model_kind={kind!r} 不在覆盖"
                        f"清单 {list(MODEL_KINDS)}")
    if not reg.get("model_spec"):
        failures.append("external_result.model_spec 缺失：外部模型规格"
                        "（固定/随机效应、链接函数等）必须成文登记")
    effect, se = reg.get("effect"), reg.get("se")
    if not _is_num(effect):
        failures.append("external_result.effect 缺失或非有限数")
    if not _is_num(se) or (_is_num(se) and se <= 0):
        failures.append("external_result.se 缺失、非有限数或不为正")
    if failures:
        return {"passed": False, "checks": checks, "failures": failures}

    digits = reg.get("reported_digits", 3)
    if not isinstance(digits, int) or isinstance(digits, bool) \
            or not (1 <= digits <= 10):
        return {"passed": False, "checks": checks,
                "failures": [f"external_result.reported_digits="
                             f"{digits!r} 须为 1..10 的整数"]}
    df = reg.get("df")
    if df is not None and (not _is_num(df) or df <= 0):
        return {"passed": False, "checks": checks,
                "failures": [f"external_result.df={df!r} 须为正数或缺省"
                             "（缺省=正态口径）"]}

    z = effect / se
    # 1) CI 复算
    ci = reg.get("ci") or {}
    level = ci.get("level", 0.95)
    if not _is_num(level) or not (0.0 < level < 1.0) \
            or not _is_num(ci.get("lo")) or not _is_num(ci.get("hi")):
        failures.append("external_result.ci 缺 level/lo/hi 或水平非法："
                        "置信区间是必填登记项，不许只登记点估计")
    else:
        crit_p = 1.0 - (1.0 - level) / 2.0
        crit = (calc.t_ppf(crit_p, df) if df is not None
                else calc.norm_ppf(crit_p))
        lo_r, hi_r = effect - crit * se, effect + crit * se
        for nm, rec, rv in (("lo", lo_r, ci["lo"]), ("hi", hi_r, ci["hi"])):
            tol = _sig_tol(rv, digits)
            ok = abs(rec - rv) <= tol
            checks.append({"name": f"ci_{nm}", "recomputed": rec,
                           "registered": rv, "tol": tol, "ok": ok})
            if not ok:
                failures.append(
                    f"CI {nm} 端复算不一致：登记 {rv} vs 由 effect/se/df "
                    f"复算 {rec:.6g}（容差 {tol:.3g}，有效数字 "
                    f"{digits} 位）——登记数字自相矛盾，不采信")

    # 2) p 复算
    p_reg = reg.get("p_value")
    if df is not None:
        p_rec = 2.0 * (1.0 - calc.t_cdf(abs(z), df))
    else:
        p_rec = 2.0 * (1.0 - calc.norm_cdf(abs(z)))
    if p_reg is None:
        checks.append({"name": "p_value", "recomputed": p_rec,
                       "registered": None, "tol": None, "ok": True,
                       "note": "未登记 p：judge 以复算 p 为 p_raw，"
                               "来源在判定行点名"})
    elif not _is_num(p_reg) or not (0.0 <= p_reg <= 1.0):
        failures.append(f"external_result.p_value={p_reg!r} 非 [0,1] 数")
    else:
        tol = _sig_tol(p_reg, digits)
        ok = abs(p_rec - p_reg) <= tol
        checks.append({"name": "p_value", "recomputed": p_rec,
                       "registered": p_reg, "tol": tol, "ok": ok})
        if not ok:
            failures.append(
                f"p 值复算不一致：登记 {p_reg} vs 由 effect/se/df 复算 "
                f"{p_rec:.6g}（容差 {tol:.3g}）——登记数字自相矛盾，"
                "不采信")

    # 3) 材料对照（登记了对照材料才查；查必查严）
    mats = (reg.get("materials") or {}).get("group_summaries")
    if mats is not None:
        tol_m = (reg.get("materials") or {}).get("tolerance")
        if not isinstance(mats, list) or len(mats) != 2:
            failures.append("materials.group_summaries 须恰两组"
                            "（处理/对照各一），登记形态不合")
        elif not _is_num(tol_m):
            failures.append("materials 给了对照材料但缺 tolerance："
                            "材料容差须由登记者声明，不许事后挑")
        else:
            try:
                g1, g2 = mats
                w = calc.effect_and_ci_summary(
                    g1["mean"], g1["spread"], g1["n"],
                    g2["mean"], g2["spread"], g2["n"])
                w_eff = w["mean_diff"]
                sign_ok = (w_eff == 0 and effect == 0) or \
                    (w_eff * effect > 0)
                dev = abs(w_eff - effect)
                ok = sign_ok and dev <= tol_m
                checks.append({"name": "materials_welch",
                               "recomputed": w_eff, "registered": effect,
                               "tol": tol_m, "ok": ok})
                if not sign_ok:
                    failures.append(
                        f"材料对照符号相反：登记 effect={effect}，两组"
                        f"材料复算 Welch 对照={w_eff:.6g}——登记与材料"
                        "不是同一个对照，不采信")
                elif not ok:
                    failures.append(
                        f"材料对照偏差超容差：|复算 {w_eff:.6g} − 登记 "
                        f"{effect}| = {dev:.6g} > tolerance {tol_m}")
            except (KeyError, TypeError, ValueError) as exc:
                failures.append(f"materials.group_summaries 形态不合："
                                f"{exc}")

    # 4) 后验方向概率（登记了后验才查）
    post = reg.get("posterior")
    if post is not None:
        pm, psd, ppd = post.get("mean"), post.get("sd"), \
            post.get("prob_direction")
        if not (_is_num(pm) and _is_num(psd) and psd > 0
                and _is_num(ppd)):
            failures.append("posterior 须含 mean / sd(>0) / "
                            "prob_direction 三个有限数")
        else:
            rec = calc.norm_cdf(pm / psd)
            ok = abs(rec - ppd) <= POSTERIOR_DIRECTION_TOL
            checks.append({"name": "posterior_direction",
                           "recomputed": rec, "registered": ppd,
                           "tol": POSTERIOR_DIRECTION_TOL, "ok": ok})
            if not ok:
                failures.append(
                    f"后验方向概率复算不一致：登记 {ppd} vs "
                    f"Φ(mean/sd)={rec:.6g}（容差 "
                    f"{POSTERIOR_DIRECTION_TOL}）")

    return {"passed": not failures, "checks": checks,
            "failures": failures}
