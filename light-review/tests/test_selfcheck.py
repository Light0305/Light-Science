"""Phase 2 · 评审产物自审门（RV-13）。

五类命名可靠性测试各一正一反 + 与冻结清单对账（可少说不可矛盾）
+ 自审过期（target_hash）被 adjudicated 门咬。
"""
import pytest

from conftest import drive_to_reported
from light_review.gates import GateError, advance_package
from light_review.meta import run_meta
from light_review.project import FILES
from light_review.selfcheck import run_selfcheck


def _failed_tests(report):
    return {t["test_id"] for t in report["tests"] if t["result"] == "fail"}


def _meta_with_narrative(root, narrative: str):
    path = root / "narrative.md"
    path.write_text(narrative, encoding="utf-8")
    run_meta(root, narrative_file=path)
    return run_selfcheck(root)


def test_mechanical_meta_passes_selfcheck(review_pkg):
    drive_to_reported(review_pkg)
    run_meta(review_pkg)
    report = run_selfcheck(review_pkg)
    assert report["passed"] is True, report["tests"]
    assert report["reconciliation"]["unknown_in_meta"] == []


def test_vague_unsupported_caught(review_pkg):
    drive_to_reported(review_pkg)
    report = _meta_with_narrative(review_pkg, "整体感觉不错，建议继续努力。\n")
    assert "vague_unsupported" in _failed_tests(report)
    assert report["passed"] is False


def test_wrong_object_caught(review_pkg):
    drive_to_reported(review_pkg)
    report = _meta_with_narrative(
        review_pkg, "建议补做 RV-C999 指出的对照实验，共 3 组。\n")
    assert "wrong_object" in _failed_tests(report)


def test_wrong_object_upstream_ids_ok(review_pkg):
    """承接登记的上游对象（结论登记行/图号）是合法引用域。

    Phase 3 演示实测回归：meta 渲染 concern 陈述时引用上游行号
    （如 R-NEG）与图号（F001），旧库存只认本包 ID 会误判库存外。
    """
    drive_to_reported(review_pkg)
    report = _meta_with_narrative(
        review_pkg,
        "R-ORA 行判定 undetermined，F001 图件登记齐备，共 2 项已核。\n")
    assert "wrong_object" not in _failed_tests(report)
    assert report["passed"] is True, report["tests"]


def test_wrong_object_pointer_cited_token_ok(review_pkg):
    """concern 双指针正式引用的对象（如回流票号）不判库存外。"""
    concerns = [
        {"concern_id": "RV-C001", "statement": "判读标准转写件未闭环",
         "raised_by": ["S1", "S2"],
         "severity_proposals": {"S1": "minor", "S2": "minor"},
         "close_criterion": "Design 补结构化字段",
         "pointers": {"claim_pointer": "sections/02-methods.md",
                      "evidence_pointer": "reflux/RX-A001"}},
    ]
    drive_to_reported(review_pkg, concerns=concerns)
    report = _meta_with_narrative(
        review_pkg, "RV-C001 的回流 RX-A001 未闭环，共 1 项待办。\n")
    assert "wrong_object" not in _failed_tests(report)
    assert report["passed"] is True, report["tests"]


def test_wrong_object_unregistered_token_still_caught(review_pkg):
    """既未承接登记、也无指针引用的 ID 形 token 仍判库存外。"""
    drive_to_reported(review_pkg)
    report = _meta_with_narrative(
        review_pkg, "建议按 ZZ-999 的口径补做 2 组实验。\n")
    assert "wrong_object" in _failed_tests(report)


def test_praise_only_caught(review_pkg):
    drive_to_reported(review_pkg)
    report = _meta_with_narrative(
        review_pkg, "这项工作非常出色，方法优秀，行文精彩。\n")
    assert "praise_only" in _failed_tests(report)


def test_mere_restatement_caught(review_pkg):
    """叙述逐字抄冻结报告的一句长句且不带锚 → 只是复述。"""
    from conftest import DEFAULT_CONCERNS
    from light_review.forensic import run_forensic
    from light_review.gates import advance_package
    from light_review.panel import (build_consensus, freeze_reports,
                                    register_seat, write_draft)
    line = ("The manuscript fails to report the random seed configuration "
            "used for the main tracking experiments in the methods section")
    run_forensic(review_pkg)
    advance_package(review_pkg)
    for sid in ("S1", "S2"):
        register_seat(review_pkg, sid, f"role-{sid}", "claude")
        src = review_pkg / f"draft-{sid}.md"
        src.write_text(f"# {sid} 评审草稿\n\n{line}\n", encoding="utf-8")
        write_draft(review_pkg, sid, src)
    advance_package(review_pkg)
    freeze_reports(review_pkg)
    build_consensus(review_pkg, DEFAULT_CONCERNS)
    advance_package(review_pkg)
    report = _meta_with_narrative(review_pkg, line + "\n")
    assert "mere_restatement" in _failed_tests(report)


def test_contradiction_with_frozen_list_caught(review_pkg):
    drive_to_reported(review_pkg)
    run_meta(review_pkg)
    meta_path = review_pkg / FILES["meta_review"]
    text = meta_path.read_text(encoding="utf-8")
    # RV-C002 冻结严重度是 minor，meta 里标注 critical = 与冻结清单矛盾
    meta_path.write_text(text + "\n- RV-C002（severity=critical）：补记\n",
                         encoding="utf-8")
    report = run_selfcheck(review_pkg)
    assert "contradicts_frozen" in _failed_tests(report)


def test_missing_from_meta_is_not_a_failure(review_pkg):
    """报告可少说：只提一条 concern 的叙述不因漏提另一条而不过。"""
    drive_to_reported(review_pkg)
    report = _meta_with_narrative(
        review_pkg, "RV-C001 需补齐 3 项参数，其余见冻结清单。\n")
    assert report["passed"] is True, report["tests"]
    assert "RV-C002" in report["reconciliation"]["missing_from_meta"]


def test_adjudicated_gate_blocks_without_selfcheck(review_pkg):
    drive_to_reported(review_pkg)
    run_meta(review_pkg)
    with pytest.raises(GateError) as exc:
        advance_package(review_pkg)
    assert any("自审" in g for g in exc.value.gaps)


def test_adjudicated_gate_blocks_failed_selfcheck(review_pkg):
    drive_to_reported(review_pkg)
    _meta_with_narrative(review_pkg, "整体感觉不错，建议继续努力。\n")
    with pytest.raises(GateError):
        advance_package(review_pkg)


def test_adjudicated_gate_blocks_stale_selfcheck(review_pkg):
    drive_to_reported(review_pkg)
    run_meta(review_pkg)
    run_selfcheck(review_pkg)
    meta_path = review_pkg / FILES["meta_review"]
    meta_path.write_text(meta_path.read_text(encoding="utf-8")
                         + "\n补记一行。\n", encoding="utf-8")
    with pytest.raises(GateError) as exc:
        advance_package(review_pkg)
    assert any("过期" in g for g in exc.value.gaps)
