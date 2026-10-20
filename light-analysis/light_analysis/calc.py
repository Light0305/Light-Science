"""最小判定计算集（Phase 2，拍板①）：纯标准库，判定量全部可复算。

只算判定要用的量，口径逐个写死并带已知答案测试（tests/test_calc.py）：

- `p_superiority`：两组原始值的经验 P(A>B)（并列计 0.5，与 Mann-Whitney
  U/(n1·n2) 恒等）；只有分布摘要时用正态近似变体。
- `effect_and_ci`：Welch 均值差 + Hedges g + t 区间（t 分位数由不完全
  Beta 连续分数自实现，不引 scipy）。
- `tost`：双单侧 t 检验（bounds 只许由调用方传入登记 SESOI，本模块不
  决定 bounds）+ 90% CI 落界判定。
- `corrections`：BH-FDR / Holm / Bonferroni / BY 对 p 向量的机械校正，
  与 statsmodels multipletests 文档口径对拍。
- `design_analysis`：Type S/M 设计分析三元组（Gelman & Carlin 2014
  正态近似闭式）。D 只许外部代入（冻结 SESOI / 外部先验），本模块
  不从数据效应反推 D——事后功效禁令在调用层由字段纪律守（约束 11）。
- `stouffer_combine`：带方向的 Stouffer 合并（规格集联合推断用）。

每个公开计算函数返回 dict，带 `provenance`（method / inputs_hash /
params）：落 spec_results 与判定行后可按同一口径机械复算。
"""

from __future__ import annotations

import math

from .util import component_hash

_EPS = 1e-15


def _prov(method: str, inputs, params: dict) -> dict:
    return {"method": method,
            "inputs_hash": component_hash(inputs),
            "params": params}


# ---------------------------------------------------------------- 正态

def norm_cdf(x: float) -> float:
    """标准正态 CDF（math.erf 实现）。"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """标准正态分位数（Acklam 有理逼近，|误差| < 1.15e-9 量级）。"""
    if not (0.0 < p < 1.0):
        raise ValueError(f"norm_ppf 只接受 (0,1) 内的 p，现为 {p}")
    a = [-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


# ---------------------------------------------------------------- t 分布

def _betacf(a: float, b: float, x: float) -> float:
    """不完全 Beta 的连续分数（Numerical Recipes betacf）。"""
    max_it, eps, fpmin = 200, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_it + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """正则化不完全 Beta I_x(a,b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    """Student t 分布 CDF（经不完全 Beta）。"""
    if df <= 0:
        raise ValueError("t_cdf 的 df 必须为正")
    x = df / (df + t * t)
    ib = _betainc(df / 2.0, 0.5, x)
    return 1.0 - 0.5 * ib if t >= 0 else 0.5 * ib


def t_ppf(p: float, df: float) -> float:
    """Student t 分位数：对 t_cdf 二分求根（单调，稳健）。"""
    if not (0.0 < p < 1.0):
        raise ValueError(f"t_ppf 只接受 (0,1) 内的 p，现为 {p}")
    if p == 0.5:
        return 0.0
    lo, hi = -1.0, 1.0
    while t_cdf(hi, df) < p:
        hi *= 2.0
    while t_cdf(lo, df) > p:
        lo *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------- 基础量

def _mean(xs):
    return sum(xs) / len(xs)


def _var(xs, m=None):
    m = _mean(xs) if m is None else m
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def _check_pair(a, b):
    a, b = [float(x) for x in a], [float(x) for x in b]
    if len(a) < 2 or len(b) < 2:
        raise ValueError("两组各至少需要 2 个独立重复层级观测")
    return a, b


def p_superiority(a, b) -> dict:
    """经验 P(A>B)：逐对比较，并列计 0.5。恒等于 Mann-Whitney U/(n1·n2)。"""
    a, b = _check_pair(a, b)
    wins = ties = 0
    for x in a:
        for y in b:
            if x > y:
                wins += 1
            elif x == y:
                ties += 1
    total = len(a) * len(b)
    value = (wins + 0.5 * ties) / total
    return {"value": value, "wins": wins, "ties": ties, "pairs": total,
            "provenance": _prov("empirical_p_superiority",
                                {"a": a, "b": b}, {"ties": 0.5})}


def p_superiority_normal(mean_a, sd_a, mean_b, sd_b) -> dict:
    """只有分布摘要时的 P(A>B) 正态近似：Φ((μa−μb)/√(σa²+σb²))。"""
    denom = math.sqrt(sd_a ** 2 + sd_b ** 2)
    if denom <= 0:
        raise ValueError("两组 spread 均为 0，P(A>B) 正态近似无定义")
    value = norm_cdf((mean_a - mean_b) / denom)
    return {"value": value,
            "provenance": _prov("normal_p_superiority",
                                {"mean_a": mean_a, "sd_a": sd_a,
                                 "mean_b": mean_b, "sd_b": sd_b}, {})}


def _welch_core(m1, v1, n1, m2, v2, n2):
    """Welch 两样本核心量：差、SE、Satterthwaite df（摘要与原始值共用）。"""
    diff = m1 - m2
    se = math.sqrt(v1 / n1 + v2 / n2)
    if se <= 0:
        raise ValueError("合并标准误为 0（组内零方差），判定计算无定义")
    df_num = (v1 / n1 + v2 / n2) ** 2
    df_den = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    df = df_num / df_den
    return diff, se, df


def _effect_from_stats(m1, v1, n1, m2, v2, n2, level):
    diff, se, df = _welch_core(m1, v1, n1, m2, v2, n2)
    tcrit = t_ppf(0.5 + level / 2.0, df)
    ci = (diff - tcrit * se, diff + tcrit * se)
    # Hedges g：合并标准差 + 小样本校正 J
    sp = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    if sp <= 0:
        raise ValueError("合并标准差为 0，标准化效应无定义")
    d = diff / sp
    j = 1.0 - 3.0 / (4.0 * (n1 + n2) - 9.0)
    g = j * d
    se_g = j * math.sqrt((n1 + n2) / (n1 * n2) + d * d / (2.0 * (n1 + n2 - 2)))
    g_ci = (g - tcrit * se_g, g + tcrit * se_g)
    t_stat = diff / se
    p_two = 2.0 * (1.0 - t_cdf(abs(t_stat), df))
    return {"mean_diff": diff, "se": se, "df": df,
            "ci": {"level": level, "lo": ci[0], "hi": ci[1]},
            "hedges_g": g, "g_ci": {"level": level, "lo": g_ci[0], "hi": g_ci[1]},
            "t_stat": t_stat, "p_two_sided": min(1.0, max(0.0, p_two))}


def effect_and_ci(a, b, level=0.95) -> dict:
    """原始值版：均值差 + 区间 + Hedges g + Welch 双侧 p。"""
    a, b = _check_pair(a, b)
    out = _effect_from_stats(_mean(a), _var(a), len(a),
                             _mean(b), _var(b), len(b), level)
    out["provenance"] = _prov("welch_effect_and_ci", {"a": a, "b": b},
                              {"level": level})
    return out


def effect_and_ci_summary(mean_a, sd_a, n_a, mean_b, sd_b, n_b,
                          level=0.95) -> dict:
    """分布摘要版（只有 {mean, spread, n} 时）：与原始值版同一 Welch 口径。"""
    if n_a < 2 or n_b < 2:
        raise ValueError("两组 n 各至少为 2")
    out = _effect_from_stats(mean_a, sd_a ** 2, n_a,
                             mean_b, sd_b ** 2, n_b, level)
    out["provenance"] = _prov(
        "welch_effect_and_ci_summary",
        {"mean_a": mean_a, "sd_a": sd_a, "n_a": n_a,
         "mean_b": mean_b, "sd_b": sd_b, "n_b": n_b}, {"level": level})
    return out


def mann_whitney_p(a, b) -> dict:
    """Mann-Whitney U 双侧 p（正态近似 + 并列校正）；秩类规格的 p 来源。"""
    a, b = _check_pair(a, b)
    n1, n2 = len(a), len(b)
    u = p_superiority(a, b)["value"] * n1 * n2
    # 并列校正：合并样本的并列组规模
    from collections import Counter
    counts = Counter(a + b)
    tie_term = sum(t ** 3 - t for t in counts.values())
    n = n1 + n2
    var_u = n1 * n2 / 12.0 * ((n + 1) - tie_term / (n * (n - 1.0)))
    if var_u <= 0:
        raise ValueError("Mann-Whitney 方差为 0（全部并列），p 无定义")
    z = (u - n1 * n2 / 2.0) / math.sqrt(var_u)
    p = 2.0 * (1.0 - norm_cdf(abs(z)))
    return {"u": u, "z": z, "p_two_sided": min(1.0, max(0.0, p)),
            "provenance": _prov("mann_whitney_normal_approx",
                                {"a": a, "b": b}, {"tie_correction": True})}


def median_diff(a, b) -> float:
    def med(xs):
        s = sorted(xs)
        m = len(s) // 2
        return s[m] if len(s) % 2 else 0.5 * (s[m - 1] + s[m])
    return med([float(x) for x in a]) - med([float(x) for x in b])


# ---------------------------------------------------------------- TOST

def tost(diff, se, df, sesoi, alpha=0.05) -> dict:
    """双单侧 t 检验：H01: diff ≤ −Δ 与 H02: diff ≥ Δ，Δ = 登记 SESOI。

    p_tost = max(p1, p2)；等价成立 ⟺ p_tost < α ⟺ (1−2α) 区间全落
    [−Δ, Δ] 内——两个判据同时给出并交叉核对（result 取两者一致结论）。
    bounds 由调用方从分析规格登记值传入，本函数不决定 bounds。
    """
    if sesoi <= 0:
        raise ValueError("TOST bounds 的 SESOI 必须为正")
    if se <= 0:
        raise ValueError("TOST 的 SE 必须为正")
    t1 = (diff + sesoi) / se
    p1 = 1.0 - t_cdf(t1, df)
    t2 = (diff - sesoi) / se
    p2 = t_cdf(t2, df)
    p_tost = max(p1, p2)
    tcrit = t_ppf(1.0 - alpha, df)
    lo, hi = diff - tcrit * se, diff + tcrit * se
    in_bounds = (lo >= -sesoi) and (hi <= sesoi)
    passed = (p_tost < alpha) and in_bounds
    return {"p_tost": p_tost, "p_lower": p1, "p_upper": p2,
            "ci90": {"lo": lo, "hi": hi} if abs(alpha - 0.05) < 1e-12
            else {"lo": lo, "hi": hi, "level": 1 - 2 * alpha},
            "ci90_in_bounds": in_bounds,
            "result": "pass" if passed else "fail",
            "bounds": {"lo": -sesoi, "hi": sesoi},
            "provenance": _prov("tost_two_one_sided_t",
                                {"diff": diff, "se": se, "df": df},
                                {"sesoi": sesoi, "alpha": alpha})}


def tost_from_samples(a, b, sesoi, alpha=0.05) -> dict:
    """原始值版 TOST：diff/SE/df 取 Welch 口径后走 tost()。"""
    a, b = _check_pair(a, b)
    diff, se, df = _welch_core(_mean(a), _var(a), len(a),
                               _mean(b), _var(b), len(b))
    return tost(diff, se, df, sesoi, alpha=alpha)


# ---------------------------------------------------------------- 多重校正

def _clip01(xs):
    return [min(1.0, max(0.0, x)) for x in xs]


def bh_adjust(pvals) -> list:
    """Benjamini-Hochberg 校正后 p（step-up + 自大到小单调化）。"""
    pvals = [float(p) for p in pvals]
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    adj_sorted = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvals[i] * m / rank)
        adj_sorted[rank - 1] = running
    out = [0.0] * m
    for rank, i in enumerate(order):
        out[i] = adj_sorted[rank]
    return _clip01(out)


def holm_adjust(pvals) -> list:
    """Holm 校正后 p（step-down + 自小到大单调化）。"""
    pvals = [float(p) for p in pvals]
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    adj_sorted = [0.0] * m
    running = 0.0
    for rank in range(1, m + 1):
        i = order[rank - 1]
        running = max(running, pvals[i] * (m - rank + 1))
        adj_sorted[rank - 1] = running
    out = [0.0] * m
    for rank, i in enumerate(order):
        out[i] = adj_sorted[rank]
    return _clip01(out)


def bonferroni_adjust(pvals) -> list:
    m = len(pvals)
    return _clip01([float(p) * m for p in pvals])


def by_adjust(pvals) -> list:
    """Benjamini-Yekutieli：BH 再乘调和因子 c(m)（任意依赖兜底）。"""
    m = len(pvals)
    if m == 0:
        return []
    c_m = sum(1.0 / i for i in range(1, m + 1))
    return _clip01([x * c_m for x in bh_adjust(pvals)])


_CORRECTION_FUNCS = {"fdr_bh": bh_adjust, "holm": holm_adjust,
                     "bonferroni": bonferroni_adjust, "fdr_by": by_adjust}


def corrections(pvals, method) -> dict:
    """按受控词表方法校正一个 p 向量（一个校正族的一次应用）。"""
    fn = _CORRECTION_FUNCS.get(method)
    if fn is None:
        raise ValueError(f"校正方法 {method!r} 不在受控词表 "
                         f"{sorted(_CORRECTION_FUNCS)}")
    pvals = [float(p) for p in pvals]
    adj = fn(pvals)
    return {"method": method, "p_raw": pvals, "p_adj": adj,
            "provenance": _prov(f"correction_{method}", {"pvals": pvals},
                                {"method": method, "m": len(pvals)})}


def corrections_by_family(items, families) -> dict:
    """按族分组应用校正。

    items: [{line_id, p_raw}]；families: 登记头校正族声明
    [{family_id, member_line_ids, method, alpha}]。
    返回 {line_id: {family_id, method, p_raw, p_adj}}。
    行不在任何族内 → 抛错（族是字段，不许有无族之行，约束 6）。
    """
    by_id = {it["line_id"]: it for it in items}
    out = {}
    for fam in families:
        members = [lid for lid in fam.get("member_line_ids") or []
                   if lid in by_id]
        if not members:
            continue
        res = corrections([by_id[lid]["p_raw"] for lid in members],
                          fam["method"])
        for lid, raw, adj in zip(members, res["p_raw"], res["p_adj"]):
            out[lid] = {"family_id": fam["family_id"],
                        "method": fam["method"], "p_raw": raw, "p_adj": adj}
    missing = [lid for lid in by_id if lid not in out]
    if missing:
        raise ValueError(f"判定行未落入任何校正族：{missing}（约束 6：family 须声明）")
    return out


# ---------------------------------------------------------------- Type S/M

def design_analysis(assumed_d, se, alpha=0.05) -> dict:
    """设计分析三元组（Gelman & Carlin 2014，正态近似闭式）。

    设估计量 est ~ N(D, se²)，D 为外部代入的真实效应假设（冻结 SESOI
    或外部先验），显著阈 c = z_{1−α/2}·se：
      power  = P(|est| > c)
      Type S = P(est < −c) / power（显著但方向反的概率，条件于显著）
      Type M = E[|est| | |est| > c] / D（夸大倍数 exaggeration ratio）
    D 绝不许来自本批数据效应——调用方负责 basis 纪律，本函数只算。
    """
    d = abs(float(assumed_d))
    if d <= 0:
        raise ValueError("design_analysis 的 D 必须为正（外部代入的效应假设）")
    if se <= 0:
        raise ValueError("design_analysis 的 SE 必须为正")
    z = norm_ppf(1.0 - alpha / 2.0)
    c = z * se
    # 上尾（方向正确）与下尾（方向反）
    a_hi = (c - d) / se
    a_lo = (-c - d) / se
    p_hi = 1.0 - norm_cdf(a_hi)
    p_lo = norm_cdf(a_lo)
    power = p_hi + p_lo
    if power <= 0:
        raise ValueError("power 为 0：D/SE 组合下设计分析无定义")
    type_s = p_lo / power
    # 截断正态一阶矩：E[est·1(est>c)] = D·p_hi + se·φ(a_hi)
    #                 E[−est·1(est<−c)] = −D·p_lo + se·φ(a_lo)
    phi_hi = math.exp(-0.5 * a_hi ** 2) / math.sqrt(2 * math.pi)
    phi_lo = math.exp(-0.5 * a_lo ** 2) / math.sqrt(2 * math.pi)
    e_abs = (d * p_hi + se * phi_hi) + (-d * p_lo + se * phi_lo)
    type_m = (e_abs / power) / d
    return {"assumed_D": d, "se": se, "alpha": alpha,
            "power": power, "type_s": type_s, "type_m": type_m,
            "exaggeration_ratio": type_m,
            "provenance": _prov("gelman_carlin_design_analysis",
                                {"assumed_d": d, "se": se},
                                {"alpha": alpha, "approx": "normal"})}


# ---------------------------------------------------------------- Stouffer

def stouffer_combine(pvals, signs) -> dict:
    """带方向的 Stouffer 合并：z_i = sign_i · Φ⁻¹(1 − p_i/2)，Z = Σz/√k。

    pvals 为逐规格双侧 p，signs 为逐规格效应方向（+1/−1/0）。
    返回合并双侧 p 与合并 Z（规格集联合推断用，约束/A4）。
    """
    if not pvals or len(pvals) != len(signs):
        raise ValueError("stouffer_combine 需要等长的 p 向量与方向向量")
    zs = []
    for p, s in zip(pvals, signs):
        p = min(max(float(p), 1e-300), 1.0 - 1e-16)
        z = norm_ppf(1.0 - p / 2.0)
        zs.append(z if s > 0 else (-z if s < 0 else 0.0))
    z_comb = sum(zs) / math.sqrt(len(zs))
    p_comb = 2.0 * (1.0 - norm_cdf(abs(z_comb)))
    return {"z": z_comb, "p_two_sided": min(1.0, max(0.0, p_comb)), "k": len(zs),
            "provenance": _prov("stouffer_signed",
                                {"pvals": [float(p) for p in pvals],
                                 "signs": [int(s) for s in signs]}, {})}
