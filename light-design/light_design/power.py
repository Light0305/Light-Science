"""功效真计算模块（v1.2）：经典分组设计的精确解求解器。

立项依据：21-benchmark/measured-round1.md §三实测坐实旧规程「经模拟/
解析推出」欠定——z 近似路线系统性少算（双臂每臂少 1、配对少 2 对），
小样本处实际功效跌破规程自设目标（P4 的 18 对只有 0.744）。验收口径
冻结于 03-design/power-module-acceptance.md，本模块逐条对之：

- 最终 n 只认精确解：双臂/配对走非中心 t 精确解（nct_exact），单因素
  ANOVA 走非中心 F（ncf_exact）；z 近似只作合理性速查（z_reference），
  产物中显式标注 reference_only，不许作最终产出；
- 模拟（蒙特卡洛）只作交叉验证：口径同 measured-round1（种子
  20261021、每点 2000 次、双侧 alpha），产出登记 MC 标准误；
- 精确解与模拟取整不一致时以精确解为准，分歧与 MC 标准误一并落字
  （见 solve 结果的 route_note / 校验器的复算拦截）。

数值实现为纯标准库（不完全 Beta 连分式 + 非中心分布 Poisson 混合
级数），与 statsmodels（TTestIndPower / TTestPower / FTestAnovaPower）
逐案对拍：四案原值相对误差 1e-6 量级内（夹具见 tests/test_power.py，
数字冻结自 measured-round1 实测轮，不许改判据刷分）。
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist

ROUTE_T = "nct_exact"          # 非中心 t 精确解（双臂 / 配对）
ROUTE_F = "ncf_exact"          # 非中心 F 精确解（单因素 ANOVA）
ROUTE_Z = "z_approx_reference_only"  # z 近似：只许速查，不许作产出
EXACT_ROUTES = (ROUTE_T, ROUTE_F)
FORMS = ("two_arm", "paired", "anova")

DEFAULT_SEED = 20261021        # measured-round1 模拟口径
DEFAULT_REPS = 2000


# ---------- 数值原语：正态 / 不完全 Beta / 中心 t、F ----------

def norm_cdf(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def norm_ppf(p: float) -> float:
    return NormalDist().inv_cdf(p)


def _betacf(a: float, b: float, x: float) -> float:
    """不完全 Beta 的连分式（Lentz 法，Numerical Recipes betacf）。"""
    MAXIT, EPS, FPMIN = 300, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betainc_reg(a: float, b: float, x: float) -> float:
    """正则化不完全 Beta I_x(a, b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    """中心 t 分布 CDF（df 可为实数）。"""
    if t == 0.0:
        return 0.5
    x = df / (df + t * t)
    ib = betainc_reg(df / 2.0, 0.5, x)
    return 1.0 - 0.5 * ib if t > 0 else 0.5 * ib


def t_ppf(p: float, df: float) -> float:
    """中心 t 分位（对 CDF 二分反解）。"""
    if not 0.0 < p < 1.0:
        raise ValueError(f"t_ppf 的 p 须在 (0, 1)：{p!r}")
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -t_ppf(1.0 - p, df)
    lo, hi = 0.0, 1.0
    while t_cdf(hi, df) < p:
        lo, hi = hi, hi * 2.0
        if hi > 1e7:
            raise ValueError("t_ppf 括号扩张失败")
    for _ in range(120):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def f_cdf(f: float, d1: float, d2: float) -> float:
    """中心 F 分布 CDF。"""
    if f <= 0.0:
        return 0.0
    x = d1 * f / (d1 * f + d2)
    return betainc_reg(d1 / 2.0, d2 / 2.0, x)


def f_ppf(p: float, d1: float, d2: float) -> float:
    """中心 F 分位（对 CDF 二分反解）。"""
    if not 0.0 < p < 1.0:
        raise ValueError(f"f_ppf 的 p 须在 (0, 1)：{p!r}")
    lo, hi = 0.0, 1.0
    while f_cdf(hi, d1, d2) < p:
        lo, hi = hi, hi * 2.0
        if hi > 1e9:
            raise ValueError("f_ppf 括号扩张失败")
    for _ in range(120):
        mid = 0.5 * (lo + hi)
        if f_cdf(mid, d1, d2) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------- 非中心 t / F 的 CDF（Poisson 混合级数） ----------

def nct_cdf(t: float, df: float, nc: float) -> float:
    """非中心 t 分布 CDF。

    级数形（t > 0）：F(t) = Φ(−δ) + ½·Σ_j [ p_j·I_x(j+½, ν/2)
    + q_j·I_x(j+1, ν/2) ]，x = t²/(ν+t²)，p_j 为 Poisson(λ=δ²/2)
    权重，q_j = δ·e^(−λ)·λ^j / (√2·Γ(j+3/2))。t < 0 用对称性。
    与 scipy.stats.nct 逐点对拍（夹具见 tests/test_power.py）。"""
    if t == 0.0:
        return norm_cdf(-nc)
    if t < 0:
        return 1.0 - nct_cdf(-t, df, -nc)
    x = t * t / (df + t * t)
    lam = 0.5 * nc * nc
    b = df / 2.0
    p = math.exp(-lam) if lam < 700 else 0.0
    q = nc * math.exp(-lam) / (math.sqrt(2.0) * math.gamma(1.5)) \
        if lam < 700 else 0.0
    total = 0.0
    j = 0
    while True:
        total += p * betainc_reg(j + 0.5, b, x) \
            + q * betainc_reg(j + 1.0, b, x)
        if j > lam and p < 1e-15 and abs(q) < 1e-15:
            break
        j += 1
        if j > 100000:
            raise ValueError("nct_cdf 级数未收敛")
        p *= lam / j
        q *= lam / (j + 0.5)
    return norm_cdf(-nc) + 0.5 * total


def ncf_cdf(f: float, d1: float, d2: float, lam: float) -> float:
    """非中心 F 分布 CDF：非中心卡方 = 中心卡方的 Poisson 混合，
    F 比随之成为 Beta 混合：F(f) = Σ_j p_j·I_x(d1/2+j, d2/2)，
    x = d1·f/(d1·f+d2)，p_j 为 Poisson(λ/2) 权重。"""
    if f <= 0.0:
        return 0.0
    if lam == 0.0:
        return f_cdf(f, d1, d2)
    x = d1 * f / (d1 * f + d2)
    half = lam / 2.0
    p = math.exp(-half) if half < 700 else 0.0
    total = p * betainc_reg(d1 / 2.0, d2 / 2.0, x)
    j = 0
    while True:
        if j > half and p < 1e-15:
            break
        j += 1
        if j > 100000:
            raise ValueError("ncf_cdf 级数未收敛")
        p *= half / j
        total += p * betainc_reg(d1 / 2.0 + j, d2 / 2.0, x)
    return min(total, 1.0)


# ---------- 功效函数（n 可为实数，供原值反解） ----------

def _t_power(df: float, nc: float, alpha: float) -> float:
    crit = t_ppf(1.0 - alpha / 2.0, df)
    return 1.0 - nct_cdf(crit, df, nc) + nct_cdf(-crit, df, nc)


def power_two_sample_t(n_per_arm: float, effect_d: float,
                       alpha: float = 0.05) -> float:
    """双臂独立样本 t（等分配、合并方差）的功效。d = SESOI/σ。"""
    if n_per_arm <= 1.0:
        raise ValueError("双臂每臂 n 须 > 1")
    df = 2.0 * n_per_arm - 2.0
    nc = effect_d * math.sqrt(n_per_arm / 2.0)
    return _t_power(df, nc, alpha)


def power_paired_t(n_pairs: float, effect_d: float,
                   alpha: float = 0.05) -> float:
    """配对 t 的功效。d = SESOI/σ_diff（差值标准差）。"""
    if n_pairs <= 1.0:
        raise ValueError("配对数须 > 1")
    df = n_pairs - 1.0
    nc = effect_d * math.sqrt(n_pairs)
    return _t_power(df, nc, alpha)


def power_anova(total_n: float, k_groups: int, cohen_f: float,
                alpha: float = 0.05) -> float:
    """单因素 ANOVA（等组）的功效。λ = f²·N（总样本量口径）。"""
    if k_groups < 2:
        raise ValueError("ANOVA 组数须 ≥ 2")
    if total_n <= k_groups:
        raise ValueError("ANOVA 总 N 须大于组数")
    d1 = float(k_groups - 1)
    d2 = total_n - k_groups
    lam = cohen_f * cohen_f * total_n
    crit = f_ppf(1.0 - alpha, d1, d2)
    return 1.0 - ncf_cdf(crit, d1, d2, lam)


# ---------- 精确解求解器 ----------

def _solve_raw(power_fn, target: float, lo: float) -> float:
    """对单调递增的 power_fn(n) 二分反解 power = target 的实数 n。"""
    if power_fn(lo) >= target:
        return lo
    hi = lo * 2.0
    while power_fn(hi) < target:
        lo, hi = hi, hi * 2.0
        if hi > 1e8:
            raise ValueError("目标功效在 n ≤ 1e8 内不可达（效应量过小）")
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if power_fn(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def z_reference_n(form: str, *, sigma: float | None = None,
                  sigma_diff: float | None = None, sesoi: float,
                  alpha: float = 0.05, target_power: float = 0.80) -> int:
    """z 近似路线的 n（标准正态公式）：只作合理性速查/历史对照，
    角色恒为 reference_only——最终产出不许用它（验收规格 §2）。
    ANOVA 无公认 z 速算式，返回 None 对应的缺省（由调用方处理）。"""
    z = norm_ppf(1.0 - alpha / 2.0) + norm_ppf(target_power)
    if form == "two_arm":
        return math.ceil(2.0 * (z * sigma / sesoi) ** 2)
    if form == "paired":
        return math.ceil((z * sigma_diff / sesoi) ** 2)
    raise ValueError(f"z 速查不支持形态 {form!r}")


def solve_two_sample_t(sigma: float, sesoi: float, alpha: float = 0.05,
                       target_power: float = 0.80) -> dict:
    """双臂独立样本 t 精确解：给定 σ 与 SESOI（= evaluation.sesoi
    登记值口径），输出原值 n、取整每臂 n 与该 n 的实际功效。"""
    if sigma <= 0 or sesoi <= 0:
        raise ValueError("sigma 与 sesoi 须为正数")
    d = sesoi / sigma
    raw = _solve_raw(lambda n: power_two_sample_t(n, d, alpha),
                     target_power, 2.0)
    n = math.ceil(raw)
    return {
        "form": "two_arm", "route": ROUTE_T,
        "alpha": alpha, "target_power": target_power,
        "sesoi_value": sesoi, "sigma": sigma,
        "effect_size": d,
        "raw_n": raw, "per_group_n": n, "groups": 2,
        "total_n": 2 * n,
        "achieved_power": power_two_sample_t(n, d, alpha),
        "z_reference": {"route": ROUTE_Z, "per_group_n": z_reference_n(
            "two_arm", sigma=sigma, sesoi=sesoi, alpha=alpha,
            target_power=target_power)},
    }


def solve_paired_t(sigma_diff: float, sesoi: float, alpha: float = 0.05,
                   target_power: float = 0.80) -> dict:
    """配对 t 精确解：σ_diff 为配对差的标准差。"""
    if sigma_diff <= 0 or sesoi <= 0:
        raise ValueError("sigma_diff 与 sesoi 须为正数")
    d = sesoi / sigma_diff
    raw = _solve_raw(lambda n: power_paired_t(n, d, alpha),
                     target_power, 2.0)
    n = math.ceil(raw)
    return {
        "form": "paired", "route": ROUTE_T,
        "alpha": alpha, "target_power": target_power,
        "sesoi_value": sesoi, "sigma_diff": sigma_diff,
        "effect_size": d,
        "raw_n": raw, "per_group_n": n, "groups": 1, "unit": "pairs",
        "total_n": n,
        "achieved_power": power_paired_t(n, d, alpha),
        "z_reference": {"route": ROUTE_Z, "per_group_n": z_reference_n(
            "paired", sigma_diff=sigma_diff, sesoi=sesoi, alpha=alpha,
            target_power=target_power)},
    }


def solve_anova(k_groups: int, cohen_f: float, alpha: float = 0.05,
                target_power: float = 0.80) -> dict:
    """单因素 ANOVA 非中心 F 精确解（等组分配）：原值为总 N，
    每组 n = ceil(总 N 原值 / 组数)，实际功效按每组 n×组数复算。"""
    if cohen_f <= 0:
        raise ValueError("cohen_f 须为正数")
    raw_total = _solve_raw(
        lambda n: power_anova(n, k_groups, cohen_f, alpha),
        target_power, k_groups + 1.0)
    per = math.ceil(raw_total / k_groups)
    total = per * k_groups
    return {
        "form": "anova", "route": ROUTE_F,
        "alpha": alpha, "target_power": target_power,
        "cohen_f": cohen_f,
        "raw_n": raw_total, "raw_per_group_n": raw_total / k_groups,
        "per_group_n": per, "groups": k_groups, "total_n": total,
        "achieved_power": power_anova(total, k_groups, cohen_f, alpha),
        "z_reference": None,
    }


def sensitivity_table(form: str, sesoi_points, *, sigma: float | None = None,
                      sigma_diff: float | None = None,
                      alpha: float = 0.05,
                      target_power: float = 0.80) -> list[dict]:
    """敏感性表（验收规格 §1.4）：多 SESOI 点逐点精确解——每行给
    原值、取整 n 与实际功效，不许只给文本范围。ANOVA 的敏感性维度
    是 Cohen f，请直接对每个 f 调 solve_anova。"""
    rows: list[dict] = []
    for s in sesoi_points:
        if form == "two_arm":
            r = solve_two_sample_t(sigma, s, alpha, target_power)
        elif form == "paired":
            r = solve_paired_t(sigma_diff, s, alpha, target_power)
        else:
            raise ValueError(f"敏感性表不支持形态 {form!r}（ANOVA 请逐 f 求解）")
        rows.append({
            "sesoi_value": s, "raw_n": r["raw_n"],
            "per_group_n": r["per_group_n"], "total_n": r["total_n"],
            "achieved_power": r["achieved_power"],
        })
    return rows


# ---------- 蒙特卡洛交叉验证（口径同 measured-round1） ----------

def _mean(xs) -> float:
    return sum(xs) / len(xs)


def _t_stat_two_sample(a, b) -> float:
    na, nb = len(a), len(b)
    ma, mb = _mean(a), _mean(b)
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    sp2 = ((na - 1) * va + (nb - 1) * vb) / (na + nb - 2)
    if sp2 <= 0:
        return 0.0
    return (ma - mb) / math.sqrt(sp2 * (1.0 / na + 1.0 / nb))


def simulate_power(form: str, n: int, *, effect_d: float | None = None,
                   cohen_f: float | None = None, k_groups: int = 2,
                   alpha: float = 0.05, reps: int = DEFAULT_REPS,
                   seed: int = DEFAULT_SEED) -> dict:
    """模拟交叉验证：在给定 n 处实跑检验，数拒绝率。

    口径与 measured-round1 §三一致（种子 20261021、默认 2000 次、
    双侧 alpha、正态生成）。返回估计功效与 MC 标准误
    sqrt(p(1−p)/reps)（p≈0.8 时约 0.009，不宣称更细精度）。
    本函数只作交叉验证，不作最终产出口径（验收规格 §2）。"""
    rng = random.Random(seed)
    hits = 0
    if form == "two_arm":
        df = 2 * n - 2
        crit = t_ppf(1.0 - alpha / 2.0, df)
        for _ in range(reps):
            a = [rng.gauss(0.0, 1.0) for _ in range(n)]
            b = [rng.gauss(effect_d, 1.0) for _ in range(n)]
            if abs(_t_stat_two_sample(a, b)) > crit:
                hits += 1
    elif form == "paired":
        df = n - 1
        crit = t_ppf(1.0 - alpha / 2.0, df)
        for _ in range(reps):
            diffs = [rng.gauss(effect_d, 1.0) for _ in range(n)]
            md = _mean(diffs)
            sd = math.sqrt(sum((x - md) ** 2 for x in diffs) / (n - 1))
            if sd > 0 and abs(md / (sd / math.sqrt(n))) > crit:
                hits += 1
    elif form == "anova":
        base = [i - (k_groups - 1) / 2.0 for i in range(k_groups)]
        pstdev = math.sqrt(sum(v * v for v in base) / k_groups)
        means = [cohen_f * v / pstdev for v in base]
        d1, d2 = k_groups - 1, k_groups * (n - 1)
        crit = f_ppf(1.0 - alpha, d1, d2)
        for _ in range(reps):
            groups = [[rng.gauss(means[g], 1.0) for _ in range(n)]
                      for g in range(k_groups)]
            grand = _mean([x for g in groups for x in g])
            ssb = sum(n * (_mean(g) - grand) ** 2 for g in groups)
            ssw = sum(sum((x - _mean(g)) ** 2 for x in g) for g in groups)
            if ssw > 0 and (ssb / d1) / (ssw / d2) > crit:
                hits += 1
    else:
        raise ValueError(f"未知设计形态 {form!r}")
    est = hits / reps
    return {"estimate": est, "mc_se": math.sqrt(est * (1.0 - est) / reps),
            "reps": reps, "seed": seed, "n": n, "form": form}


# ---------- 设计书承接：SESOI 单一事实源消费 ----------

def solve_from_design(design: dict, form: str, *,
                      sigma: float | None = None,
                      sigma_diff: float | None = None,
                      cohen_f: float | None = None,
                      k_groups: int | None = None,
                      sesoi_points=None,
                      simulate: bool = False,
                      reps: int = DEFAULT_REPS,
                      seed: int = DEFAULT_SEED) -> dict:
    """从设计书求解：SESOI 只认 evaluation.sesoi 登记块的 value
    （DES-D01 单一事实源，本函数不接受外部 SESOI 覆盖登记值）；
    alpha / target_power 承 resources.power 的登记值，缺省
    0.05 / 0.80。σ（或 σ_diff / Cohen f）是设计前提，由调用方
    给出并须在 resources.power.basis 落字依据。

    返回 {design_size: {...}, sensitivity_table: [...]?}，
    design_size 可直接写入 resources.power.design_size 落格。"""
    ev = design.get("evaluation") or {}
    sesoi_block = ev.get("sesoi")
    if not isinstance(sesoi_block, dict) \
            or not isinstance(sesoi_block.get("value"), (int, float)):
        raise ValueError(
            "evaluation.sesoi 登记块缺失或无数值 value：功效求解只消费"
            "登记块（DES-D01 单一事实源），先登记 SESOI 再求解")
    sesoi = float(sesoi_block["value"])
    power = (design.get("resources") or {}).get("power") or {}
    alpha = float(power.get("alpha") or 0.05)
    target = float(power.get("target_power") or 0.80)

    if form == "two_arm":
        if sigma is None:
            raise ValueError("two_arm 形态须给 sigma（组内标准差前提）")
        result = solve_two_sample_t(sigma, sesoi, alpha, target)
    elif form == "paired":
        if sigma_diff is None:
            raise ValueError("paired 形态须给 sigma_diff（配对差标准差前提）")
        result = solve_paired_t(sigma_diff, sesoi, alpha, target)
    elif form == "anova":
        if cohen_f is None or k_groups is None:
            raise ValueError("anova 形态须给 cohen_f 与 k_groups")
        result = solve_anova(k_groups, cohen_f, alpha, target)
        result["sesoi_value"] = sesoi  # 登记承接（f 的定义依据另在 basis 落字）
    else:
        raise ValueError(f"未知设计形态 {form!r}（须为 {FORMS} 之一）")

    out: dict = {"design_size": result}
    if sesoi_points:
        if form == "anova":
            raise ValueError("ANOVA 敏感性请逐 f 求解，不走 SESOI 点表")
        out["sensitivity_table"] = sensitivity_table(
            form, sesoi_points, sigma=sigma, sigma_diff=sigma_diff,
            alpha=alpha, target_power=target)
    if simulate:
        if form == "anova":
            sim = simulate_power("anova", result["per_group_n"],
                                 cohen_f=cohen_f, k_groups=k_groups,
                                 alpha=alpha, reps=reps, seed=seed)
        else:
            sim = simulate_power(form, result["per_group_n"],
                                 effect_d=result["effect_size"],
                                 alpha=alpha, reps=reps, seed=seed)
        result["sim_check"] = sim
        exact_n = result["per_group_n"]
        sim_n = _sim_min_n(form, result, alpha, target, reps, seed)
        result["route_note"] = (
            f"精确解取整 n={exact_n}（唯一产出口径）；模拟交叉验证在该 n "
            f"处估计 {sim['estimate']:.4f}（MC 标准误 {sim['mc_se']:.4f}），"
            f"模拟口径下最小达标 n={sim_n}；两路线取整"
            f"{'一致' if sim_n == exact_n else '不一致，按验收规格 §2 以精确解为准并登记本分歧'}")
    return out


def _sim_min_n(form: str, result: dict, alpha: float, target: float,
               reps: int, seed: int) -> int:
    """模拟口径下最小达标 n（从精确解附近向下/向上探，只作分歧登记）。"""
    n = result["per_group_n"]
    kw = {"effect_d": result.get("effect_size"),
          "cohen_f": result.get("cohen_f"),
          "k_groups": result.get("groups", 2), "alpha": alpha,
          "reps": reps, "seed": seed}

    def est(m: int) -> float:
        return simulate_power(form, m, **kw)["estimate"]

    if est(n) >= target:
        while n > 2 and est(n - 1) >= target:
            n -= 1
        return n
    m = n
    while est(m) < target:
        m += 1
    return m
