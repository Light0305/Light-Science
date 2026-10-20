"""校验器：覆盖自报重算、severity 重算、越层拦截、降档交付纪律。"""

import json
from pathlib import Path

import yaml

from conftest import drive_panel
from light_review.forensic import run_forensic
from light_review.gates import advance_package, deliver_package
from light_review.intake import run_intake
from light_review.panel import build_consensus, freeze_reports
from light_review.project import init_package, load_package
from light_review.validate import validate_package
from test_gates import CONCERNS, _pkg, _to_reported


def _edit_jsonl(path: Path, fn):
    rows = [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]
    fn(rows)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in rows), encoding="utf-8")


def _edit_yaml(path: Path, fn):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_summary_recount_tamper_detected(review_pkg):
    run_forensic(review_pkg)
    assert validate_package(review_pkg) == []

    def tamper(rows):
        for r in rows:
            if r.get("type") == "summary":
                r["errors"] = 99
    _edit_jsonl(review_pkg / "forensic" / "reconciliation.jsonl", tamper)
    errors = validate_package(review_pkg)
    assert any("覆盖自报" in e and "重算" in e for e in errors)


def test_consensus_severity_tamper_detected(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    build_consensus(review_pkg, CONCERNS)
    assert validate_package(review_pkg) == []

    def tamper(data):
        data["concerns"][0]["severity"] = "critical"
    _edit_yaml(review_pkg / "consensus.yaml", tamper)
    errors = validate_package(review_pkg)
    assert any("severity" in e for e in errors)


def test_single_seat_consensus_flag_detected(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    build_consensus(review_pkg, [
        {"concern_id": "RV-C001", "statement": "单席关切",
         "raised_by": ["S1"], "severity_proposals": {"S1": "minor"}}])
    assert validate_package(review_pkg) == []

    def tamper(data):
        data["concerns"][0]["consensus"] = True
    _edit_yaml(review_pkg / "consensus.yaml", tamper)
    errors = validate_package(review_pkg)
    assert any("consensus" in e and "2" in e for e in errors)


def test_conclusion_flip_layer_overreach_detected(review_pkg):
    run_forensic(review_pkg)
    fake = {"type": "finding", "finding_id": "F999", "check_id": "F-CE-001",
            "edge": "claims_evidence", "category": "confirmed_error",
            "layer": "conclusion_flip", "subject": "C1",
            "claim_pointer": "C1", "evidence_pointer": "C1",
            "detail": "伪造的越层发现", "raw": "", "flag_only": False}
    with open(review_pkg / "forensic" / "findings.jsonl", "a",
              encoding="utf-8") as fh:
        fh.write(json.dumps(fake, ensure_ascii=False) + "\n")
    errors = validate_package(review_pkg)
    assert any("结论翻转" in e for e in errors)


def test_delivered_degraded_without_statement_detected(tmp_path):
    root = _pkg(tmp_path, isolation_mode="degraded",
                isolation_reason="单模型环境")
    _to_reported(root)
    advance_package(root)
    deliver_package(root, degradation_statement="降档声明在此。")
    assert validate_package(root) == []

    def tamper(data):
        data["delivery"]["degradation_statement"] = None
    _edit_yaml(root / "review.yaml", tamper)
    errors = validate_package(root)
    assert any("降档" in e for e in errors)
