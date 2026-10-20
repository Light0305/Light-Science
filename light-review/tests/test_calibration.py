"""Phase 2 · 校准门四件（R3 / RV-14 / RV-15）。

量表锚 / 封顶规则 / 不对称合成 / 验证台——缺一判不齐；配置漂移
（席位集/量表/封顶/权重任一变更）使 bench 报表过期。
"""
import pytest

from light_review.bench import BenchError, run_bench
from light_review.calibration import (CalibrationError, assess_calibration,
                                      config_hash, init_calibration)
from light_review.project import FILES, load_package
from light_review.util import dump_yaml, load_structured
from light_review.validate import validate_package


def _cal_path(root):
    return root / FILES["calibration"]


def test_init_writes_template_and_refuses_overwrite(review_pkg):
    cal = init_calibration(review_pkg)
    assert cal["scale"]["anchors"] and cal["scale"]["anti_inflation"]
    assert cal["caps"] and cal["asymmetry"]["reject_weight"] > \
        cal["asymmetry"]["accept_weight"]
    with pytest.raises(CalibrationError):
        init_calibration(review_pkg)


def test_assess_names_missing_bench(review_pkg):
    init_calibration(review_pkg)
    a = assess_calibration(review_pkg)
    assert a["complete"] is False
    assert a["pieces"] == {"scale_anchor": True, "caps": True,
                           "asymmetry": True, "bench_report": False}
    assert any("验证台" in m for m in a["missing"])


def test_bench_makes_calibration_complete(review_pkg):
    init_calibration(review_pkg)
    run_bench(review_pkg)
    a = assess_calibration(review_pkg)
    assert a["complete"] is True, a["missing"]
    assert a["missing"] == []
    pkg = load_package(review_pkg)
    assert "calibration" not in pkg["review"]["phase2_pending"]


def test_asymmetry_must_favor_reject(review_pkg):
    """reject 权重不高于 accept → 不对称件判缺（RV-14）。"""
    init_calibration(review_pkg)
    cal = load_structured(_cal_path(review_pkg))
    cal["asymmetry"]["reject_weight"] = cal["asymmetry"]["accept_weight"]
    dump_yaml(_cal_path(review_pkg), cal)
    a = assess_calibration(review_pkg)
    assert a["pieces"]["asymmetry"] is False
    errors = validate_package(review_pkg)
    assert any("不对称" in e for e in errors)


def test_cap_without_source_is_incomplete(review_pkg):
    init_calibration(review_pkg)
    cal = load_structured(_cal_path(review_pkg))
    cal["caps"][0].pop("source")
    dump_yaml(_cal_path(review_pkg), cal)
    a = assess_calibration(review_pkg)
    assert a["pieces"]["caps"] is False
    assert any("出处" in m for m in a["missing"])


def test_scale_without_anti_inflation_is_incomplete(review_pkg):
    init_calibration(review_pkg)
    cal = load_structured(_cal_path(review_pkg))
    cal["scale"]["anti_inflation"] = ""
    dump_yaml(_cal_path(review_pkg), cal)
    a = assess_calibration(review_pkg)
    assert a["pieces"]["scale_anchor"] is False


def test_config_drift_stales_bench_report(review_pkg):
    """配置漂移：bench 后改量表 → 报表过期、校准门重新判不齐。"""
    init_calibration(review_pkg)
    run_bench(review_pkg)
    assert assess_calibration(review_pkg)["complete"] is True
    cal = load_structured(_cal_path(review_pkg))
    cal["scale"]["version"] = "v9.9-drifted"
    dump_yaml(_cal_path(review_pkg), cal)
    a = assess_calibration(review_pkg)
    assert a["complete"] is False
    assert a["pieces"]["bench_report"] is False
    assert any("过期" in m for m in a["missing"])


def test_seat_set_drift_stales_bench_report(review_pkg):
    """席位集也是评审配置的一部分：bench 后加席 → 报表过期。"""
    from conftest import drive_panel
    from light_review.panel import register_seat
    drive_panel(review_pkg, seats=("S1",))
    init_calibration(review_pkg)
    run_bench(review_pkg)
    assert assess_calibration(review_pkg)["complete"] is True
    register_seat(review_pkg, "S9", "role-S9", "gpt")
    a = assess_calibration(review_pkg)
    assert a["pieces"]["bench_report"] is False


def test_bench_requires_calibration(review_pkg):
    with pytest.raises(BenchError):
        run_bench(review_pkg)
