"""Phase 2 · meta 合成与决定建议降级（R3 / RV-14）。

校准门四件齐 + bench 在册 → decision.md（不对称合成 + 封顶）；
缺一 → problem_list.md，decision.md 出现即被校验器咬死。
"""
import pytest

from conftest import drive_panel, drive_to_reported
from light_review.bench import run_bench
from light_review.calibration import init_calibration
from light_review.gates import advance_package, deliver_package
from light_review.meta import apply_caps, run_meta
from light_review.panel import build_consensus, freeze_reports
from light_review.forensic import run_forensic
from light_review.project import FILES, load_package
from light_review.selfcheck import run_selfcheck
from light_review.validate import validate_package


def _reported_full_calibrated(root):
    """席位集先定 → 校准登记 → bench（哈希含席位集）→ 全程到 reported。"""
    drive_panel(root)
    init_calibration(root)
    run_bench(root)
    run_forensic(root)
    advance_package(root)
    advance_package(root)
    freeze_reports(root)
    from conftest import DEFAULT_CONCERNS
    build_consensus(root, DEFAULT_CONCERNS)
    advance_package(root)
    return root


# ------------------------------------------------------------ 降级形态

def test_meta_degrades_without_calibration(review_pkg):
    drive_to_reported(review_pkg)
    record = run_meta(review_pkg)
    assert record["mode"] == "degraded"
    assert record["band"] is None
    assert record["calibration_missing"], "缺件必须逐项登记"
    assert (review_pkg / FILES["problem_list"]).exists()
    assert not (review_pkg / FILES["decision_md"]).exists()
    assert (review_pkg / FILES["meta_review"]).exists()
    pkg = load_package(review_pkg)
    assert pkg["review"]["decision"]["mode"] == "degraded"
    assert "decision" not in pkg["review"]["phase2_pending"]
    assert "meta_review" not in pkg["review"]["phase2_pending"]
    assert validate_package(review_pkg) == []


def test_degraded_with_decision_md_present_is_rejected(review_pkg):
    """degraded 下出现 decision.md → 校验器咬死（条件给纪律）。"""
    drive_to_reported(review_pkg)
    run_meta(review_pkg)
    (review_pkg / FILES["decision_md"]).write_text(
        "# 偷跑的决定建议\n", encoding="utf-8")
    errors = validate_package(review_pkg)
    assert any("degraded" in e and "decision.md" in e for e in errors)


def test_degraded_rerun_after_full_removes_decision(review_pkg):
    """先 full 后配置漂移重跑 meta → 降级且 decision.md 必须消失。"""
    _reported_full_calibrated(review_pkg)
    run_meta(review_pkg)
    assert (review_pkg / FILES["decision_md"]).exists()
    from light_review.util import dump_yaml, load_structured
    cal_path = review_pkg / FILES["calibration"]
    cal = load_structured(cal_path)
    cal["scale"]["version"] = "v9.9"
    dump_yaml(cal_path, cal)                      # 配置漂移 → bench 过期
    record = run_meta(review_pkg)
    assert record["mode"] == "degraded"
    assert record["decision_file_removed"] is True
    assert not (review_pkg / FILES["decision_md"]).exists()
    assert (review_pkg / FILES["problem_list"]).exists()
    assert validate_package(review_pkg) == []


# ------------------------------------------------------------ full 形态

def test_meta_full_produces_decision(review_pkg):
    _reported_full_calibrated(review_pkg)
    record = run_meta(review_pkg)
    assert record["mode"] == "full"
    assert record["band"] in ("ready", "minor_revision", "major_revision",
                              "reject_risk")
    text = (review_pkg / FILES["decision_md"]).read_text(encoding="utf-8")
    assert "bounded 非编辑判断" in text
    assert f"建议档位：{record['band']}" in text
    assert "reject 权重" in text          # 不对称合成留痕
    assert not (review_pkg / FILES["problem_list"]).exists()
    assert validate_package(review_pkg) == []


def test_meta_full_then_advance_and_deliver(review_pkg):
    _reported_full_calibrated(review_pkg)
    run_meta(review_pkg)
    run_selfcheck(review_pkg)
    advance_package(review_pkg)           # adjudicated（自审门已过）
    deliver_package(review_pkg)
    pkg = load_package(review_pkg)
    assert pkg["review"]["status"] == "delivered"
    text = pkg["delivery_md"]
    assert "决定建议" in text and "full" in text


# ------------------------------------------------------------ 封顶规则

def _fake_pkg(*, findings=None, domain_fact_status=None, consensus=None):
    return {"review": {"domain": ({"fact_source": {
        "fact_status": domain_fact_status}} if domain_fact_status else None)},
        "findings": findings or [],
        "consensus": {"concerns": consensus or []},
        "domain_gate": None}


def test_cap_open_confirmed_error_clamps_to_major():
    from light_review.calibration import DEFAULT_CAPS
    pkg = _fake_pkg(findings=[{"type": "finding", "finding_id": "F001",
                               "status": "confirmed_error",
                               "category": "confirmed_error",
                               "layer": "numbers_numbers"}])
    band, applied = apply_caps("ready", pkg, DEFAULT_CAPS)
    assert band == "major_revision"
    assert applied and applied[0]["cap_id"] == "CAP-01"


def test_cap_unverified_facts_clamps_to_minor():
    from light_review.calibration import DEFAULT_CAPS
    pkg = _fake_pkg(domain_fact_status="unverified")
    band, applied = apply_caps("ready", pkg, DEFAULT_CAPS)
    assert band == "minor_revision"
    assert applied[0]["cap_id"] == "CAP-02"


def test_cap_clerical_only_prevents_overharsh():
    """全是文书级小问题时不许过度悲观：min_favorable 把档位拉回。"""
    from light_review.calibration import DEFAULT_CAPS
    pkg = _fake_pkg(consensus=[{"concern_id": "RV-C001",
                                "severity_proposals": {"S1": "minor"},
                                "severity": "minor", "consensus": False,
                                "status": "open"}])
    band, applied = apply_caps("reject_risk", pkg, DEFAULT_CAPS)
    assert band == "minor_revision"
    assert applied[0]["cap_id"] == "CAP-03"


def test_caps_do_not_fire_without_triggers():
    from light_review.calibration import DEFAULT_CAPS
    pkg = _fake_pkg(consensus=[{"concern_id": "RV-C001",
                                "severity_proposals": {"S1": "major"},
                                "severity": "major", "consensus": False,
                                "status": "open"}])
    band, applied = apply_caps("major_revision", pkg, DEFAULT_CAPS)
    assert band == "major_revision"
    assert applied == []
