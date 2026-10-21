"""校正谱系扩法测试（第五批 §4 P1-1）。

冻结向量 EXPECTED 由 statsmodels 0.15.0 multipletests 在建批时直出
（生成脚本与全谱随机对拍在 05-analysis/external-crosscheck/）；
包内测试只用标准库，把冻结数字钉住——入集纪律：逐法对拍后才许
入词表，此处即对拍证据的包内钉子。
"""

from __future__ import annotations

import pytest

from light_analysis import calc, schema

VECTORS = {
    "V1": [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205,
           0.212, 0.216, 0.222, 0.3, 0.445, 0.61, 0.89],
    "V2": [0.04, 0.04, 0.04, 0.5, 0.5, 0.99, 1.0],
    "V3": [0.9],
}

EXPECTED = {
    ("sidak", 0.05, "V1"): [0.014895453637998001, 0.11350746606366116, 0.44938147965408914, 0.46632223659461475, 0.4746089913236252, 0.6047082012403182, 0.6843797930722686, 0.9679736880279375, 0.9719525577586822, 0.9740139098792093, 0.9768423783121145, 0.995252438490057, 0.9998539859164935, 0.9999992655383815, 0.9999999999999958],
    ("sidak", 0.05, "V2"): [0.24855252189184, 0.24855252189184, 0.24855252189184, 0.9921875, 0.9921875, 0.99999999999999, 1.0],
    ("sidak", 0.05, "V3"): [0.9],
    ("holm_sidak", 0.05, "V1"): [0.014895453637998001, 0.1063583327254649, 0.4037834328121279, 0.4037834328121279, 0.4037834328121279, 0.46138488590510024, 0.49939073833332676, 0.8404352231293205, 0.8404352231293205, 0.8404352231293205, 0.8404352231293205, 0.8404352231293205, 0.8404352231293205, 0.8479, 0.89],
    ("holm_sidak", 0.05, "V2"): [0.24855252189184, 0.24855252189184, 0.24855252189184, 0.9375, 0.9375, 0.9999, 1.0],
    ("holm_sidak", 0.05, "V3"): [0.9],
    ("simes_hochberg", 0.05, "V1"): [0.015, 0.112, 0.462, 0.462, 0.462, 0.6, 0.6659999999999999, 0.89, 0.89, 0.89, 0.89, 0.89, 0.89, 0.89, 0.89],
    ("simes_hochberg", 0.05, "V2"): [0.2, 0.2, 0.2, 1.0, 1.0, 1.0, 1.0],
    ("simes_hochberg", 0.05, "V3"): [0.9],
    ("hommel", 0.05, "V1"): [0.015, 0.112, 0.37, 0.37, 0.378, 0.444, 0.518, 0.8133333333333334, 0.8133333333333334, 0.8133333333333334, 0.8133333333333334, 0.89, 0.89, 0.89, 0.89],
    ("hommel", 0.05, "V2"): [0.2, 0.2, 0.2, 1.0, 1.0, 1.0, 1.0],
    ("hommel", 0.05, "V3"): [0.9],
    ("fdr_gbs", 0.05, "V1"): [0.015015015015015015, 0.056451612903225805, 0.17585848074921956, 0.17585848074921956, 0.17585848074921956, 0.17585848074921956, 0.17585848074921956, 0.2578616352201258, 0.2578616352201258, 0.2578616352201258, 0.2578616352201258, 0.2578616352201258, 0.2578616352201258, 0.2578616352201258, 0.5393939393939394],
    ("fdr_gbs", 0.05, "V2"): [0.2916666666666667, 0.2916666666666667, 0.2916666666666667, 1.0, 1.0, 1.0, 1.0],
    ("fdr_gbs", 0.05, "V3"): [1.0],
    ("fdr_tsbh", 0.05, "V1"): [0.014000000000000002, 0.05600000000000001, 0.11760000000000002, 0.11760000000000002, 0.11760000000000002, 0.13999999999999999, 0.148, 0.28254545454545454, 0.28254545454545454, 0.28254545454545454, 0.28254545454545454, 0.35, 0.4792307692307692, 0.61, 0.8306666666666667],
    ("fdr_tsbh", 0.05, "V2"): [0.09333333333333334, 0.09333333333333334, 0.09333333333333334, 0.7, 0.7, 1.0, 1.0],
    ("fdr_tsbh", 0.05, "V3"): [0.9],
    ("fdr_tsbh", 0.1, "V1"): [0.013000000000000001, 0.052000000000000005, 0.10920000000000003, 0.10920000000000003, 0.10920000000000003, 0.13, 0.13742857142857143, 0.26236363636363635, 0.26236363636363635, 0.26236363636363635, 0.26236363636363635, 0.32499999999999996, 0.44499999999999995, 0.5664285714285715, 0.7713333333333334],
    ("fdr_tsbh", 0.1, "V2"): [0.05333333333333333, 0.05333333333333333, 0.05333333333333333, 0.39999999999999997, 0.39999999999999997, 0.5714285714285714, 0.5714285714285714],
    ("fdr_tsbh", 0.1, "V3"): [0.9],
    ("fdr_tsbky", 0.05, "V1"): [0.014700000000000003, 0.05880000000000001, 0.12348000000000003, 0.12348000000000003, 0.12348000000000003, 0.147, 0.1554, 0.2966727272727273, 0.2966727272727273, 0.2966727272727273, 0.2966727272727273, 0.3675, 0.5031923076923077, 0.6405, 0.8722000000000001],
    ("fdr_tsbky", 0.05, "V2"): [0.098, 0.098, 0.098, 0.735, 0.735, 1.0, 1.0],
    ("fdr_tsbky", 0.05, "V3"): [0.9450000000000001],
    ("fdr_tsbky", 0.1, "V1"): [0.014300000000000002, 0.05720000000000001, 0.12012000000000005, 0.12012000000000005, 0.12012000000000005, 0.14300000000000002, 0.1511714285714286, 0.2886, 0.2886, 0.2886, 0.2886, 0.3575, 0.4895, 0.6230714285714287, 0.8484666666666668],
    ("fdr_tsbky", 0.1, "V2"): [0.10266666666666668, 0.10266666666666668, 0.10266666666666668, 0.77, 0.77, 1.0, 1.0],
    ("fdr_tsbky", 0.1, "V3"): [0.9900000000000001],
}

NEW_METHODS = ["sidak", "holm_sidak", "simes_hochberg", "hommel",
               "fdr_tsbh", "fdr_tsbky", "fdr_gbs"]


@pytest.mark.parametrize("method", NEW_METHODS)
def test_new_method_matches_statsmodels_frozen(method):
    alphas = [0.05, 0.1] if method in ("fdr_tsbh", "fdr_tsbky") else [0.05]
    for alpha in alphas:
        for vn, vec in VECTORS.items():
            got = calc.corrections(vec, method, alpha=alpha)["p_adj"]
            exp = EXPECTED[(method, alpha, vn)]
            assert len(got) == len(exp)
            for g, e in zip(got, exp):
                assert abs(g - e) <= 1e-12, (method, alpha, vn, g, e)


def test_wordlist_consistency_schema_calc():
    assert set(schema.CORRECTION_METHODS) == set(calc.CORRECTION_METHOD_NAMES)
    assert len(schema.CORRECTION_METHODS) == 11
    for m in NEW_METHODS:
        assert m in schema.CORRECTION_METHODS


def test_unknown_method_rejected_with_wordlist():
    with pytest.raises(ValueError) as ei:
        calc.corrections([0.01, 0.2], "fdr_bky")
    assert "不在受控词表" in str(ei.value)


def test_twostage_alpha_bound_and_provenance():
    vec = VECTORS["V1"]
    a5 = calc.corrections(vec, "fdr_tsbky", alpha=0.05)
    a1 = calc.corrections(vec, "fdr_tsbky", alpha=0.1)
    # 两阶法校正 p 与 alpha 绑定：换 alpha 结果必变（程序性质）
    assert a5["p_adj"] != a1["p_adj"]
    assert a5["provenance"]["params"]["alpha"] == 0.05
    assert a5["provenance"]["params"]["alpha_bound"] is True
    # alpha 无关方法不落 alpha 绑定标记
    bh = calc.corrections(vec, "fdr_bh", alpha=0.1)
    assert "alpha_bound" not in bh["provenance"]["params"]


def test_family_alpha_flows_to_twostage():
    items = [{"line_id": "L1", "p_raw": 0.001},
             {"line_id": "L2", "p_raw": 0.03},
             {"line_id": "L3", "p_raw": 0.2},
             {"line_id": "L4", "p_raw": 0.6}]
    fams = [{"family_id": "F1", "member_line_ids": ["L1", "L2", "L3", "L4"],
             "method": "fdr_tsbky", "alpha": 0.1}]
    out = calc.corrections_by_family(items, fams)
    direct = calc.corrections([0.001, 0.03, 0.2, 0.6], "fdr_tsbky",
                              alpha=0.1)["p_adj"]
    for lid, exp in zip(["L1", "L2", "L3", "L4"], direct):
        assert out[lid]["p_adj"] == exp
        assert out[lid]["method"] == "fdr_tsbky"


def test_sidak_holm_sidak_ordering_sanity():
    vec = [0.01, 0.04, 0.03, 0.005, 0.55]
    bonf = calc.corrections(vec, "bonferroni")["p_adj"]
    sid = calc.corrections(vec, "sidak")["p_adj"]
    holm = calc.corrections(vec, "holm")["p_adj"]
    hs = calc.corrections(vec, "holm_sidak")["p_adj"]
    for i in range(len(vec)):
        # Šidák 系不劣于 Bonferroni 系（同骨架下因子更松）
        assert sid[i] <= bonf[i] + 1e-15
        assert hs[i] <= holm[i] + 1e-15
        # 校正只许收紧
        assert sid[i] >= vec[i] - 1e-15 and hs[i] >= vec[i] - 1e-15


def test_empty_and_single():
    for m in calc.CORRECTION_METHOD_NAMES:
        assert calc.corrections([], m)["p_adj"] == []
        one = calc.corrections([0.03], m)["p_adj"]
        assert len(one) == 1 and 0.0 <= one[0] <= 1.0
    # m=1 时多数方法校正 p 恒等于原 p；例外是程序性质本身：
    # fdr_tsbky 在 r1=m 支路乘 (1+alpha) 因子、fdr_gbs 的
    # p/(1-p) 变换——两者与 statsmodels 同口径，数值由上方
    # 冻结向量 V3 钉住（0.9 → tsbky@0.05 得 0.945、gbs 得 1.0），
    # 不在此处冒充恒等。
    for m in ("bonferroni", "sidak", "holm", "holm_sidak",
              "simes_hochberg", "hommel", "fdr_bh", "fdr_by", "fdr_tsbh"):
        assert abs(calc.corrections([0.03], m)["p_adj"][0] - 0.03) < 1e-12
