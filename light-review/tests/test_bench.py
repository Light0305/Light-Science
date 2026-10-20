"""Phase 2 · 验证台判别力报表（RV-15）。

缺陷注入金标准集跑的是生产检查器：已知缺陷必须全检出、干净例
必须零误报；报表按缺陷类分列并绑评审配置哈希。
"""
from light_review.bench import run_bench
from light_review.calibration import config_hash, init_calibration
from light_review.project import load_package


def test_bench_report_full_detection_no_false_positives(review_pkg):
    init_calibration(review_pkg)
    report = run_bench(review_pkg)
    assert report["passed_all"] is True
    assert report["false_positive"]["rate"] == 0.0
    assert report["false_positive"]["flagged"] == 0
    for cls in ("claim_overreach", "missing_evidence",
                "number_inconsistency", "citation_gap", "grim_incompatible"):
        row = report["by_class"][cls]
        assert row["detection_rate"] == 1.0, cls
        assert row["detected"] == row["total"] == 1
    clean = [c for c in report["cases"] if not c["expected_detect"]]
    assert len(clean) == 4
    assert all(c["detected"] is False for c in clean)


def test_bench_report_binds_config_hash(review_pkg):
    init_calibration(review_pkg)
    report = run_bench(review_pkg)
    assert report["config_hash"] == config_hash(review_pkg)
    pkg = load_package(review_pkg)
    assert pkg["bench_report"]["config_hash"] == report["config_hash"]
    assert pkg["review"]["bench"]["passed_all"] is True
