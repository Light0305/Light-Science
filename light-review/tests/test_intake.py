"""承接：快照冻结、缺项点名、隔离登记、STALE 漂移检测（§2）。"""

import pytest

from conftest import make_analysis
from light_review.intake import IntakeError, run_intake, snapshot_drift
from light_review.project import init_package, load_package


def _init(tmp_path):
    return init_package(tmp_path / "review-pkg", title="t")


def test_intake_freezes_three_package_snapshot(tmp_path, world):
    root = _init(tmp_path)
    info = run_intake(root, world["manuscript"],
                      analysis_path=world["analysis"],
                      figure_path=world["figure"], intensity="standard")
    assert info["input_scope"]["packages"] == [
        "manuscript", "analysis", "figure"]
    assert len(info["manuscript"]["files"]) == 6  # 5 核心文件 + 1 节稿
    assert info["manuscript"]["package_hash"]
    assert info["figure_note"] is None
    review = load_package(root)["review"]
    assert review["constraints"]["intensity"] == "standard"


def test_intake_requires_intensity_no_silent_default(tmp_path, world):
    root = _init(tmp_path)
    with pytest.raises(IntakeError) as ei:
        run_intake(root, world["manuscript"],
                   analysis_path=world["analysis"])
    assert any("intensity" in g or "强度档" in g for g in ei.value.gaps)


def test_intake_names_missing_analysis(tmp_path, world):
    root = _init(tmp_path)
    with pytest.raises(IntakeError) as ei:
        run_intake(root, world["manuscript"],
                   analysis_path=tmp_path / "nope",
                   intensity="standard")
    assert any("结论包" in g for g in ei.value.gaps)


def test_intake_missing_figure_is_noted_not_faked(tmp_path, world):
    root = _init(tmp_path)
    info = run_intake(root, world["manuscript"],
                      analysis_path=world["analysis"],
                      intensity="standard")
    assert info["figure"] is None
    assert "未承接" in info["figure_note"]


def test_degraded_isolation_requires_reason(tmp_path, world):
    root = _init(tmp_path)
    with pytest.raises(IntakeError) as ei:
        run_intake(root, world["manuscript"],
                   analysis_path=world["analysis"], intensity="standard",
                   isolation_mode="degraded")
    assert any("登记理由" in g for g in ei.value.gaps)
    root2 = init_package(tmp_path / "review-pkg-2")
    run_intake(root2, world["manuscript"],
               analysis_path=world["analysis"], intensity="standard",
               isolation_mode="degraded",
               isolation_reason="单模型环境无法跨家族隔离")
    assert load_package(root2)["review"]["isolation"]["mode"] == "degraded"


def test_snapshot_drift_detected(tmp_path, world):
    root = _init(tmp_path)
    run_intake(root, world["manuscript"], analysis_path=world["analysis"],
               figure_path=world["figure"], intensity="standard")
    assert snapshot_drift(root) == []
    section = world["manuscript"] / "sections" / "03-results.md"
    section.write_text(section.read_text(encoding="utf-8") + "\n改稿了\n",
                       encoding="utf-8")
    drift = snapshot_drift(root)
    assert any("manuscript" in d and "03-results.md" in d for d in drift)
