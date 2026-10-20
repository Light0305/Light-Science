"""A0 承接与可判性：哈希对齐、逐行点名、预登记、拦截分支。"""

import json
from pathlib import Path

import pytest

from conftest import CONTENT_HASH, REPO_ROOT, make_upstream
from light_analysis.intake import IntakeError, run_intake
from light_analysis.project import init_package, load_package


def _lines_by_id(audit):
    return {l["registry_line_id"]: l for l in audit["lines"]}


def test_intake_judgeability_map(pkg):
    audit = load_package(pkg)["audit"]
    lines = _lines_by_id(audit)
    assert lines["L-OK"]["judgeability"] == "judgeable"
    assert lines["L-VOID"]["judgeability"] == "untested_candidate"
    assert lines["L-VOID"]["void_supported"] is True
    assert lines["L-FUND"]["judgeability"] == "untested_candidate"
    assert lines["L-FUND"]["fundamental_failure"] is True
    assert lines["L-MISS"]["judgeability"] == "untested_candidate"
    assert lines["L-INC"]["judgeability"] == "undetermined_candidate"
    assert lines["L-PART"]["judgeability"] == "judgeable"
    s = audit["summary"]
    assert s["total"] == 6 and s["judgeable"] == 2
    assert s["untested_candidate"] == 3 and s["undetermined_candidate"] == 1
    assert audit["hash_alignment"] == "pass"


def test_intake_null_precision_warnings(pkg):
    lines = _lines_by_id(load_package(pkg)["audit"])
    assert lines["L-PART"]["null_precision_warning"] is True   # n=4 < 6
    assert lines["L-FUND"]["null_precision_warning"] is True    # n=2 < 6
    assert lines["L-OK"]["null_precision_warning"] is False


def test_intake_preregisters_terminal_rows(pkg):
    rows = load_package(pkg)["verdicts"]
    by_line = {r["registry_line_id"]: r for r in rows}
    assert by_line["L-VOID"]["verdict"] == "untested"
    assert by_line["L-FUND"]["verdict"] == "untested"
    assert by_line["L-MISS"]["verdict"] == "untested"
    assert by_line["L-INC"]["verdict"] == "undetermined"
    assert all(r["decided_by"] == "intake-audit" for r in rows)
    assert "L-OK" not in by_line and "L-PART" not in by_line
    counts = load_package(pkg)["analysis"]["counts"]
    assert counts["untested"] == 3 and counts["undetermined"] == 1
    assert counts["total_lines"] == 6


def test_intake_families_and_claims(pkg):
    analysis = load_package(pkg)["analysis"]
    fams = analysis["correction_families"]
    assert len(fams) == 1 and fams[0]["family_id"] == "claim:C1"
    assert fams[0]["method"] == "fdr_bh"
    assert set(fams[0]["member_line_ids"]) == {
        "L-OK", "L-VOID", "L-FUND", "L-PART", "L-MISS", "L-INC"}
    assert analysis["claim_ids"] == ["C1"]
    assert analysis["design_ref"]["registry_lines"] == 6
    assert (pkg / "audit.md").exists()


def test_intake_rejects_registry_hash_mismatch(tmp_path, upstream):
    card_path, reg_path, _ = upstream
    rows = [json.loads(l) for l in reg_path.read_text().splitlines()]
    rows[0]["content_hash"] = "f" * 64
    reg_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    root = tmp_path / "ana"
    init_package(root)
    with pytest.raises(IntakeError) as ei:
        run_intake(root, card_path, reg_path)
    assert any("L-OK" in g and "content_hash" in g for g in ei.value.gaps)


def test_intake_rejects_undelivered_card(tmp_path, upstream):
    card_path, reg_path, _ = upstream
    card = json.loads(card_path.read_text())
    card["status"] = "reconciling"
    card_path.write_text(json.dumps(card))
    root = tmp_path / "ana"
    init_package(root)
    with pytest.raises(IntakeError) as ei:
        run_intake(root, card_path, reg_path)
    assert any("delivered" in g for g in ei.value.gaps)


def test_intake_rejects_single_point_material(tmp_path):
    card_path, reg_path, _ = make_upstream(tmp_path)
    card = json.loads(card_path.read_text())
    for row in card["reconciliation"]["rows"]:
        if row["registry_run_id"] == "L-OK":
            row["readout_actual"] = 72.5  # 单点冒充分布
    card_path.write_text(json.dumps(card, ensure_ascii=False))
    root = tmp_path / "ana"
    init_package(root)
    with pytest.raises(IntakeError) as ei:
        run_intake(root, card_path, reg_path)
    assert any("单点" in g for g in ei.value.gaps)


def test_intake_twice_rejected(pkg, upstream):
    card_path, reg_path, dc_path = upstream
    with pytest.raises(IntakeError):
        run_intake(pkg, card_path, reg_path, design_card_path=dc_path)


def test_intake_real_demo_package(tmp_path):
    """对 light-experiment 合成演示执行包（明示合成身份）真实承接一遍。"""
    demo = REPO_ROOT / "light-experiment" / "examples" / "demo-synthetic"
    card_path = demo / "proj" / "executions" / \
        "video-threshold-predict_synth01-b2" / "execution_card.json"
    reg_path = demo / "inputs" / "export-good" / "expected_registry.jsonl"
    dc_path = demo / "inputs" / "export-good" / "design_card.json"
    if not card_path.exists():
        pytest.skip("演示执行包不在仓内")
    root = tmp_path / "ana-demo"
    init_package(root)
    audit = run_intake(root, card_path, reg_path, design_card_path=dc_path)
    lines = _lines_by_id(audit)
    assert audit["summary"]["total"] == 5
    # R-NEG：fundamental 失败 F-0001 → untested 候选，不是 negative
    assert lines["R-NEG"]["judgeability"] == "untested_candidate"
    assert lines["R-NEG"]["fundamental_failure"] is True
    # R-PRED：a1 被 DV-0001 作废但有替代 run a2 → 仍可判
    assert lines["R-PRED"]["judgeability"] == "judgeable"
    assert lines["R-PRED"]["void_supported"] is False
    assert lines["R-FIX"]["judgeability"] == "judgeable"
    analysis = load_package(root)["analysis"]
    assert analysis["claim_ids"] == ["C1"]
    assert analysis["correction_families"][0]["family_id"] == "claim:all"
    assert analysis["design_ref"]["content_hash"] == \
        "1ed8de06e50e72257c1f57de3b3ce74fb39247e16cfe6de36280653a44d3475f"
