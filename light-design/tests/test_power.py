"""功效真计算模块验收夹具（v1.2）。

判据冻结于 03-design/power-module-acceptance.md §4，数字来自
21-benchmark/measured-round1.md §三实测（参照侧 statsmodels
TTestIndPower / TTestPower / FTestAnovaPower；模拟侧 numpy 种子
20261021、2000 次/点）。冻结纪律：只许改实现，不许改判据刷分；
判据变更须单独留痕（验收规格 §5）。
"""

from __future__ import annotations

import copy
import math

import pytest

from light_design import cli, power as P
from light_design.schema import power_warnings, validate_design

from conftest import make_design

# 冻结参照值（statsmodels 精确解 / scipy 非中心分布 CDF）
FROZEN = {
    "p1_raw": 99.080325, "p1_achieved100": 0.8036475044212659,
    "p1_power99": 0.7996786866906126,
    "p2_raw": {1.0: 393.405693, 2.0: 99.080325, 3.0: 44.585789},
    "p3_raw_total": 157.189792, "p3_achieved159": 0.8048872853010696,
    "p3_power156": 0.7967328616673734,
    "p4_raw": 19.666951, "p4_achieved20": 0.8072916797687586,
    "p4_power18": 0.7598683587176238,
    # measured-round1 模拟复核（numpy 流）：P1@99 0.7795 / @100 0.8075；
    # P3 每组 52 时 0.7875 / 53 时 0.8165；P4@18 0.744 / @20 0.8055
    "mc_numpy": {"p1_99": 0.7795, "p1_100": 0.8075, "p3_52": 0.7875,
                 "p3_53": 0.8165, "p4_18": 0.744, "p4_20": 0.8055},
}


def _rel(a: float, b: float) -> float:
    return abs(a - b) / abs(b)


# ---------- 数值原语：非中心 CDF 对冻结 scipy 值 ----------

@pytest.mark.parametrize("df,nc,t,exp", [
    (5, 1.5, 2.0, 0.6314492472556718),
    (10, 0.0, 1.812461, 0.949999989981125),
    (30, 2.8, 2.5, 0.37982852802377054),
    (198, 2.828427, 1.972017, 0.19635329745050722),
    (2, -1.0, 0.5, 0.920304260068485),
])
def test_nct_cdf_frozen(df, nc, t, exp):
    assert abs(P.nct_cdf(t, df, nc) - exp) < 1e-9


@pytest.mark.parametrize("d1,d2,lam,f,exp", [
    (2, 156, 9.9375, 3.0539, 0.19510071681597863),
    (5, 50, 10.0, 2.4, 0.37800359710997383),
    (1, 10, 3.0, 5.0, 0.6551040047121446),
])
def test_ncf_cdf_frozen(d1, d2, lam, f, exp):
    assert abs(P.ncf_cdf(f, d1, d2, lam) - exp) < 1e-9


def test_central_quantiles():
    # 中心 t/F 分位与统计表对齐（df=10 的 t 0.975 = 2.228139…）
    assert abs(P.t_ppf(0.975, 10) - 2.2281388519649385) < 1e-9
    assert abs(P.t_cdf(2.2281388519649385, 10) - 0.975) < 1e-9
    assert abs(P.f_cdf(P.f_ppf(0.95, 2, 156), 2, 156) - 0.95) < 1e-9


# ---------- 验收四案（规格 §4，逐案复现） ----------

def test_p1_two_arm_exact():
    r = P.solve_two_sample_t(5.0, 2.0, 0.05, 0.80)
    assert _rel(r["raw_n"], FROZEN["p1_raw"]) < 1e-6
    assert r["per_group_n"] == 100 and r["total_n"] == 200
    assert abs(r["achieved_power"] - FROZEN["p1_achieved100"]) < 1e-9
    # n=99 实际功效 < 0.80：必须被判不达标
    assert abs(P.power_two_sample_t(99, 0.4) - FROZEN["p1_power99"]) < 1e-9
    assert P.power_two_sample_t(99, 0.4) < 0.80
    # z 路线给 99：只作 reference 落字，角色标注 reference_only
    assert r["z_reference"]["per_group_n"] == 99
    assert r["z_reference"]["route"] == P.ROUTE_Z
    assert r["route"] == P.ROUTE_T


def test_p2_sensitivity_points():
    rows = P.sensitivity_table("two_arm", [1.0, 2.0, 3.0], sigma=5.0)
    assert [row["per_group_n"] for row in rows] == [394, 100, 45]
    for row in rows:
        assert _rel(row["raw_n"], FROZEN["p2_raw"][row["sesoi_value"]]) < 1e-6
        assert row["achieved_power"] >= 0.80  # 逐点落实际功效（§1.4）
    # z 路线逐点对照：393 / 99 / 44（measured-round1 规程解析列）
    assert [P.z_reference_n("two_arm", sigma=5.0, sesoi=s)
            for s in (1.0, 2.0, 3.0)] == [393, 99, 44]


def test_p3_anova_native():
    r = P.solve_anova(3, 0.25, 0.05, 0.80)
    assert _rel(r["raw_n"], FROZEN["p3_raw_total"]) < 1e-6
    assert r["per_group_n"] == 53 and r["total_n"] == 159
    assert abs(r["achieved_power"] - FROZEN["p3_achieved159"]) < 1e-9
    # 每组 52（总 156）实际功效 < 0.80：判不达标
    assert abs(P.power_anova(156, 3, 0.25) - FROZEN["p3_power156"]) < 1e-9
    assert P.power_anova(156, 3, 0.25) < 0.80
    assert r["route"] == P.ROUTE_F


def test_p4_paired_exact():
    r = P.solve_paired_t(3.0, 2.0, 0.05, 0.80)
    assert _rel(r["raw_n"], FROZEN["p4_raw"]) < 1e-6
    assert r["per_group_n"] == 20 and r["total_n"] == 20
    assert abs(r["achieved_power"] - FROZEN["p4_achieved20"]) < 1e-9
    # z 路线的 18 对实际功效只有约 0.76：必须被判不达标
    assert r["z_reference"]["per_group_n"] == 18
    assert abs(P.power_paired_t(18, 2.0 / 3.0) - FROZEN["p4_power18"]) < 1e-9
    assert P.power_paired_t(18, 2.0 / 3.0) < 0.80


# ---------- 蒙特卡洛交叉验证（口径同 measured-round1） ----------

def test_mc_crosscheck_two_arm():
    s100 = P.simulate_power("two_arm", 100, effect_d=0.4)
    s99 = P.simulate_power("two_arm", 99, effect_d=0.4)
    assert s100["reps"] == 2000 and s100["seed"] == 20261021
    assert abs(s100["mc_se"] - 0.009) < 0.002  # MC 标准误量级如实登记
    # 与精确解、与冻结 numpy 流三方对照（带宽按合并 MC 噪声取）
    assert abs(s100["estimate"] - FROZEN["p1_achieved100"]) < 0.04
    assert abs(s100["estimate"] - FROZEN["mc_numpy"]["p1_100"]) < 0.045
    assert abs(s99["estimate"] - FROZEN["mc_numpy"]["p1_99"]) < 0.045
    assert s99["estimate"] < 0.80  # 模拟口径同样判 99 不达标


def test_mc_crosscheck_paired_and_anova():
    s20 = P.simulate_power("paired", 20, effect_d=2.0 / 3.0)
    s18 = P.simulate_power("paired", 18, effect_d=2.0 / 3.0)
    assert abs(s20["estimate"] - FROZEN["mc_numpy"]["p4_20"]) < 0.045
    assert abs(s18["estimate"] - FROZEN["mc_numpy"]["p4_18"]) < 0.045
    assert s18["estimate"] < 0.80
    s53 = P.simulate_power("anova", 53, cohen_f=0.25, k_groups=3)
    s52 = P.simulate_power("anova", 52, cohen_f=0.25, k_groups=3)
    assert abs(s53["estimate"] - FROZEN["p3_achieved159"]) < 0.04
    assert abs(s52["estimate"] - FROZEN["p3_power156"]) < 0.04


# ---------- 设计书承接：SESOI 单一事实源 ----------

def test_solve_from_design_consumes_registered_sesoi():
    d = make_design()  # evaluation.sesoi.value = 2.0；power alpha .05/target .8
    out = P.solve_from_design(d, "paired", sigma_diff=1.5)
    ds = out["design_size"]
    assert ds["sesoi_value"] == 2.0  # 只认登记块，不许外部覆盖
    assert ds["per_group_n"] == 7  # 精确解原值 6.581… → 7 对
    assert ds["achieved_power"] >= 0.80
    out2 = P.solve_from_design(d, "paired", sigma_diff=1.5,
                               sesoi_points=[1.0, 2.0, 3.0])
    assert [r["per_group_n"] for r in out2["sensitivity_table"]] == [20, 7, 5]


def test_solve_from_design_requires_sesoi_block():
    d = make_design()
    d["evaluation"]["sesoi"] = None
    with pytest.raises(ValueError, match="单一事实源"):
        P.solve_from_design(d, "paired", sigma_diff=1.5)


# ---------- 校验器：落格拦截（规格 §2/§3/§5 完成定义） ----------

def _with_design_size(design: dict, ds: dict) -> dict:
    d = copy.deepcopy(design)
    d["resources"]["power"]["design_size"] = ds
    return d


def _errs_with(design: dict, needle: str) -> list[str]:
    return [e for e in validate_design(design) if needle in e]


def test_validator_accepts_exact_block(design):
    ds = P.solve_two_sample_t(5.0, 2.0)
    d = _with_design_size(design, ds)
    assert validate_design(d) == []


def test_validator_accepts_anova_block(design):
    ds = P.solve_anova(3, 0.25)
    ds["sesoi_value"] = 2.0
    d = _with_design_size(design, ds)
    assert _errs_with(d, "design_size") == []


def test_validator_blocks_p1_n99(design):
    # 完成定义实测：P1 的每臂 99（z 路线产出）必须被拦下
    ds = P.solve_two_sample_t(5.0, 2.0)
    ds.update({"per_group_n": 99, "total_n": 198,
               "achieved_power": P.power_two_sample_t(99, 0.4)})
    # raw_n 保持 99.08：取整关系与实际功效两处都应报错，至少实际功效被拦
    d = _with_design_size(design, ds)
    errs = _errs_with(d, "design_size")
    assert any("实际功效未达目标" in e or "复算实际功效" in e for e in errs)


def test_validator_blocks_p4_n18(design):
    # 完成定义实测：P4 的 18 对必须被拦下（落字与复算一致也拦）
    ds = {
        "form": "paired", "route": P.ROUTE_T, "alpha": 0.05,
        "target_power": 0.8, "sesoi_value": 2.0, "sigma_diff": 3.0,
        "raw_n": 17.66, "per_group_n": 18, "groups": 1, "total_n": 18,
        "achieved_power": P.power_paired_t(18, 2.0 / 3.0),
    }
    d = _with_design_size(design, ds)
    errs = _errs_with(d, "design_size")
    assert any("未达目标" in e for e in errs)


def test_validator_rejects_z_route(design):
    ds = P.solve_two_sample_t(5.0, 2.0)
    ds["route"] = "z_approx"
    d = _with_design_size(design, ds)
    errs = _errs_with(d, "design_size")
    assert any("z 近似路线只许作" in e for e in errs)


def test_validator_recompute_catches_tampered_achieved(design):
    ds = P.solve_two_sample_t(5.0, 2.0)
    ds["achieved_power"] = 0.95  # 手填虚高：与求解器复算 0.803648 不符
    d = _with_design_size(design, ds)
    errs = _errs_with(d, "design_size")
    assert any("复算" in e and "不一致" in e for e in errs)


def test_validator_grouped_caliber_requires_block(design):
    d = copy.deepcopy(design)
    d["resources"]["power"]["caliber"] = "grouped"
    errs = _errs_with(d, "caliber=grouped")
    assert errs


def test_validator_sensitivity_table_rows(design):
    d = _with_design_size(design, P.solve_two_sample_t(5.0, 2.0))
    d["resources"]["power"]["sensitivity_table"] = P.sensitivity_table(
        "two_arm", [1.0, 2.0, 3.0], sigma=5.0)
    assert validate_design(d) == []
    d["resources"]["power"]["sensitivity_table"][0]["achieved_power"] = 0.5
    assert _errs_with(d, "sensitivity_table")


def test_borrowing_warning(design):
    d = copy.deepcopy(design)
    assert power_warnings(d) == []  # 无分组声明时不误报
    d["contract"]["groups"] = [{"name": "处理臂"}, {"name": "对照臂"}]
    warns = power_warnings(d)
    assert warns and "借位" in warns[0]
    d["resources"]["power"]["design_size"] = P.solve_two_sample_t(5.0, 2.0)
    assert power_warnings(d) == []  # 原生落格后警告消


# ---------- CLI：power 命令全链 ----------

def test_cli_power_apply_and_validate(project, design_in_project, capsys):
    from light_design.project import load_design
    root = str(project)
    did = design_in_project["design_id"]
    rc = cli.main(["power", root, did, "--form", "paired",
                   "--sigma-diff", "1.5", "--sesoi-points", "1,2,3",
                   "--simulate", "--apply"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "nct_exact" in out and "已落格" in out
    saved = load_design(project, did)
    ds = saved["resources"]["power"]["design_size"]
    assert ds["per_group_n"] == 7 and ds["route"] == P.ROUTE_T
    assert "sim_check" in ds and "route_note" in ds
    assert [r["per_group_n"] for r in
            saved["resources"]["power"]["sensitivity_table"]] == [20, 7, 5]
    assert validate_design(saved) == []
    # 非 draft 拒 --apply
    cli.main(["advance", root, did, "--to", "reviewed"])
    rc = cli.main(["power", root, did, "--form", "paired",
                   "--sigma-diff", "1.5", "--apply"])
    assert rc == 1
