"""最小判定计算集的已知答案测试（Phase 2）。

对拍来源逐条注明：手算例 / 教科书分位数 / R p.adjust 与 statsmodels
multipletests 文档口径 / 数值积分独立实现 / 蒙特卡洛模拟。
"""

import math
import random

import pytest

from light_analysis import calc


# ---------------------------------------------------------------- 正态 / t

def test_norm_ppf_known_values():
    assert calc.norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-6)
    assert calc.norm_ppf(0.5) == pytest.approx(0.0, abs=1e-9)
    assert calc.norm_ppf(0.001) == pytest.approx(-3.090232, abs=1e-5)
    for p in (0.01, 0.1, 0.3, 0.7, 0.99):
        assert calc.norm_cdf(calc.norm_ppf(p)) == pytest.approx(p, abs=1e-8)


def test_t_ppf_textbook_values():
    # 教科书 t 表：df=10 → 2.2281，df=30 → 2.0423（双侧 95%）
    assert calc.t_ppf(0.975, 10) == pytest.approx(2.2281, abs=1e-3)
    assert calc.t_ppf(0.975, 30) == pytest.approx(2.0423, abs=1e-3)
    assert calc.t_cdf(0.0, 7) == pytest.approx(0.5)
    assert calc.t_cdf(1.5, 12) + calc.t_cdf(-1.5, 12) == pytest.approx(1.0)


def _t_cdf_numeric(t, df):
    """独立参照：对 t 密度做 Simpson 数值积分（不共用被测实现）。"""
    def pdf(x):
        return math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2)) \
            / math.sqrt(df * math.pi) * (1 + x * x / df) ** (-(df + 1) / 2)
    if t == 0:
        return 0.5
    n, a, b = 20000, 0.0, abs(t)
    h = (b - a) / n
    s = pdf(a) + pdf(b)
    for i in range(1, n):
        s += (4 if i % 2 else 2) * pdf(a + i * h)
    return 0.5 + (1 if t > 0 else -1) * s * h / 3


def test_t_cdf_against_numeric_integration():
    for df in (5, 20):
        for t in (0.4, 1.8, 3.0):
            assert calc.t_cdf(t, df) == pytest.approx(
                _t_cdf_numeric(t, df), abs=1e-6)


# ---------------------------------------------------------------- P(A>B)

def test_p_superiority_hand_examples():
    # 手算：a=[1,2,3] 对 b=[2,2,2]：胜 3 + 并列 3×0.5 = 4.5 / 9 = 0.5
    assert calc.p_superiority([1, 2, 3], [2, 2, 2])["value"] == 0.5
    assert calc.p_superiority([5, 6], [1, 2])["value"] == 1.0
    assert calc.p_superiority([1, 2], [5, 6])["value"] == 0.0
    # 全并列 → 0.5
    assert calc.p_superiority([3, 3], [3, 3, 3])["value"] == 0.5


def test_p_superiority_equals_mann_whitney_u():
    a = [7, 9, 9, 12, 15]
    b = [5, 9, 10, 11]
    res = calc.p_superiority(a, b)
    mw = calc.mann_whitney_p(a, b)
    assert res["value"] == pytest.approx(mw["u"] / (len(a) * len(b)))
    # 对称：两向概率各含 0.5·并列份额，相加恰为 1（胜+负+并列=全部对）
    back = calc.p_superiority(b, a)["value"]
    assert res["value"] + back == pytest.approx(1.0)


def test_p_superiority_normal_variant():
    # 同分布 → 0.5；均值差 = 合成标准差 → Φ(1/√2)≈0.7602
    assert calc.p_superiority_normal(10, 2, 10, 2)["value"] == 0.5
    v = calc.p_superiority_normal(12, 2, 10, 2)["value"]
    assert v == pytest.approx(0.7602, abs=1e-3)


# ---------------------------------------------------------------- 效应 + 区间

def test_effect_and_ci_point_estimates():
    a = [5.1, 4.9, 5.3, 5.0, 4.8, 5.2]
    b = [4.2, 4.5, 4.1, 4.4, 4.3, 4.6]
    r = calc.effect_and_ci(a, b)
    assert r["mean_diff"] == pytest.approx(0.7, abs=1e-9)
    assert r["ci"]["lo"] < r["mean_diff"] < r["ci"]["hi"]
    # Hedges g 手工复核：合并 sd 与 J 校正独立重算
    import statistics
    sp = math.sqrt((5 * statistics.variance(a) + 5 * statistics.variance(b)) / 10)
    j = 1 - 3 / (4 * 12 - 9)
    assert r["hedges_g"] == pytest.approx(j * 0.7 / sp, rel=1e-9)
    assert 0 < r["p_two_sided"] < 0.001


def test_effect_summary_matches_raw():
    a = [5.1, 4.9, 5.3, 5.0, 4.8, 5.2]
    b = [4.2, 4.5, 4.1, 4.4, 4.3, 4.6]
    import statistics
    raw = calc.effect_and_ci(a, b)
    summ = calc.effect_and_ci_summary(
        statistics.mean(a), statistics.stdev(a), len(a),
        statistics.mean(b), statistics.stdev(b), len(b))
    for key in ("mean_diff", "se", "df", "hedges_g", "p_two_sided"):
        assert summ[key] == pytest.approx(raw[key], rel=1e-9)


# ---------------------------------------------------------------- TOST

def test_tost_known_case():
    # 与数值积分独立对拍过的算例：diff=0.3, se=0.5, df=20, Δ=1.5
    r = calc.tost(diff=0.3, se=0.5, df=20, sesoi=1.5)
    assert r["p_tost"] == pytest.approx(0.0131244, abs=1e-5)
    assert r["result"] == "pass"
    assert r["ci90_in_bounds"] is True
    assert r["ci90"]["lo"] == pytest.approx(-0.5624, abs=1e-3)
    assert r["ci90"]["hi"] == pytest.approx(1.1624, abs=1e-3)


def test_tost_fail_when_interval_crosses_bound():
    # diff 贴近上界：90% CI 越界 → fail，且 p_tost 与 CI 判据一致
    r = calc.tost(diff=1.3, se=0.5, df=20, sesoi=1.5)
    assert r["result"] == "fail"
    assert r["ci90_in_bounds"] is False
    assert r["p_tost"] >= 0.05


def test_tost_from_samples_zero_effect():
    r = calc.tost_from_samples([65, 66, 64, 65, 66, 64],
                               [65, 64, 66, 65, 64, 66], sesoi=2.0)
    assert r["result"] == "pass"
    assert r["p_tost"] < 0.01


# ---------------------------------------------------------------- 校正

def test_bh_holm_hand_values():
    # 手算对拍（与 R p.adjust / statsmodels multipletests 同口径）
    p = [0.001, 0.01, 0.04, 0.20]
    assert calc.bh_adjust(p) == pytest.approx(
        [0.004, 0.02, 0.04 * 4 / 3, 0.20])
    assert calc.holm_adjust(p) == pytest.approx([0.004, 0.03, 0.08, 0.20])
    assert calc.bonferroni_adjust(p) == pytest.approx(
        [0.004, 0.04, 0.16, 0.80])


def test_corrections_monotone_and_bounded():
    random.seed(7)
    p = [random.random() for _ in range(25)]
    for fn in (calc.bh_adjust, calc.holm_adjust, calc.by_adjust):
        adj = fn(p)
        assert all(raw <= a <= 1.0 for raw, a in zip(p, adj))
    # Holm 不宽于 BH（FWER 强于 FDR）
    assert all(h >= b for h, b in zip(calc.holm_adjust(p), calc.bh_adjust(p)))


def test_corrections_by_family_groups_applied():
    items = [{"line_id": "L1", "p_raw": 0.001},
             {"line_id": "L2", "p_raw": 0.04},
             {"line_id": "L3", "p_raw": 0.02}]
    families = [
        {"family_id": "claim:C1", "member_line_ids": ["L1", "L2"],
         "method": "fdr_bh", "alpha": 0.05},
        {"family_id": "claim:C2", "member_line_ids": ["L3"],
         "method": "holm", "alpha": 0.05},
    ]
    out = calc.corrections_by_family(items, families)
    assert out["L1"]["p_adj"] == pytest.approx(0.002)   # BH m=2: 0.001*2
    assert out["L2"]["p_adj"] == pytest.approx(0.04)
    assert out["L3"]["p_adj"] == pytest.approx(0.02)    # 单成员 Holm 不变
    assert out["L1"]["family_id"] == "claim:C1"
    with pytest.raises(ValueError):
        calc.corrections_by_family(
            [{"line_id": "LX", "p_raw": 0.01}], families)


# ---------------------------------------------------------------- Type S/M

def test_design_analysis_against_monte_carlo():
    # 闭式 vs 蒙特卡洛（Gelman & Carlin 口径）：三组 D/se 量级对拍
    random.seed(42)
    for d_true, se in ((0.5, 1.0), (2.0, 1.0), (0.1, 1.0)):
        da = calc.design_analysis(d_true, se)
        n = 60000
        crit = calc.norm_ppf(0.975) * se
        sig = wrong = 0
        mag = 0.0
        for _ in range(n):
            e = random.gauss(d_true, se)
            if abs(e) > crit:
                sig += 1
                mag += abs(e)
                if e < 0:
                    wrong += 1
        assert da["power"] == pytest.approx(sig / n, abs=0.005)
        assert da["type_s"] == pytest.approx(wrong / sig, abs=0.01)
        assert da["type_m"] == pytest.approx((mag / sig) / d_true, rel=0.03)
        assert da["exaggeration_ratio"] == da["type_m"]


def test_design_analysis_low_power_magnitudes():
    # Gelman & Carlin 的核心图景：功效越低，Type S/M 越糟（量级对拍）
    low = calc.design_analysis(0.1, 1.0)
    assert low["power"] == pytest.approx(0.0511, abs=0.001)
    assert low["type_s"] == pytest.approx(0.385, abs=0.01)   # 近四成方向反
    assert low["type_m"] > 20                                # 夸大逾 20 倍
    high = calc.design_analysis(3.0, 1.0)
    assert high["type_m"] < 1.2 and high["type_s"] < 0.001
    with pytest.raises(ValueError):
        calc.design_analysis(0.0, 1.0)   # D 必须为正：不许拿 0 效应算校准


# ---------------------------------------------------------------- Stouffer

def test_stouffer_combine():
    # 同向同 p：合并 p 小于单个 p；方向相消：合并 p 回到不达门区
    same = calc.stouffer_combine([0.04, 0.04, 0.04], [1, 1, 1])
    assert same["p_two_sided"] < 0.01
    opposite = calc.stouffer_combine([0.04, 0.04], [1, -1])
    assert opposite["z"] == pytest.approx(0.0)
    assert opposite["p_two_sided"] == pytest.approx(1.0)


def test_stouffer_zero_p_saturates_not_crashes():
    # 第五批修复：p=0（零方差规格的退化 p）曾使 1 − p/2 在双精度
    # 下等于 1.0、norm_ppf(1.0) 抛错打崩整包判定；现 z 饱和不崩。
    out = calc.stouffer_combine([0.0, 0.04], [1, 1])
    assert out["p_two_sided"] < 0.01
    assert out["z"] > 5.0


def test_calc_results_carry_provenance():
    r = calc.effect_and_ci([3, 4, 5, 6], [1, 2, 2, 3])
    prov = r["provenance"]
    assert prov["method"] == "welch_effect_and_ci"
    assert len(prov["inputs_hash"]) == 64
    # 同输入同哈希（可复算）、异输入异哈希
    r2 = calc.effect_and_ci([3, 4, 5, 6], [1, 2, 2, 3])
    assert r2["provenance"]["inputs_hash"] == prov["inputs_hash"]
