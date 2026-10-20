"""WRT-D13 溯源键三元组：同登记行两量独立锚定、裸键兼容与歧义点名。"""

import json
from pathlib import Path

import pytest

from light_write.audit import gate_numbers, parse_trace_ref
from light_write.intake import run_intake
from light_write.project import init_package, load_package
from light_write.util import dump_json, dump_yaml
from conftest import make_literature_rows, write_jsonl


def _two_quantity_card():
    card = {
        "kind": "light-analysis/conclusion-card",
        "version": "1.0",
        "analysis_id": "demo-twoqty",
        "exported_at": "2026-10-21",
        "status": "delivered",
        "review": {"reviewer": None, "family": None,
                   "review_status": None, "receipt_id": None,
                   "reason": None},
        "claims": [
            {"claim_id": "C1", "support": "supported", "grade": "strong",
             "cap_reason": None,
             "text": "Method A outperforms the fixed-threshold baseline.",
             "line_verdicts": {"R-PRED": "positive"}},
        ],
        "number_provenance": [
            {"value": 5.2, "quantity": "effect_size",
             "verdict_line": "R-PRED#v1", "registry_line_id": "R-PRED",
             "spec_id": "S001", "calc_provenance": "welch_effect_and_ci"},
            {"value": 0.78, "quantity": "p_ab",
             "verdict_line": "R-PRED#v1", "registry_line_id": "R-PRED",
             "spec_id": "S001", "calc_provenance": "welch_effect_and_ci"},
        ],
    }
    return card


@pytest.fixture()
def twoqty_pkg(tmp_path):
    root = tmp_path / "ms"
    init_package(root, "Two Quantity Demo", "en")
    card_path = tmp_path / "conclusion_card.json"
    dump_json(card_path, _two_quantity_card())
    lit_path = write_jsonl(tmp_path / "pool.jsonl", make_literature_rows())
    run_intake(root, card_path, lit_path)
    (root / "sections" / "01-introduction.md").write_text(
        "The effect reached [num:N001] 5.2 with direction probability "
        "[num:N002] 0.78 in the primary metric.\n", encoding="utf-8")
    return root


def _set_numbers(root, rows):
    dump_yaml(Path(root) / "numbers_ledger.yaml", {"numbers": rows})


def _codes(gate):
    return {f["code"] for f in gate.findings}


def test_parse_trace_ref_forms():
    assert parse_trace_ref("R-PRED#v1") == ("R-PRED#v1", None)
    assert parse_trace_ref("R-PRED#v1:effect_size") == (
        "R-PRED#v1", "effect_size")


def test_two_quantities_independently_anchored(twoqty_pkg):
    _set_numbers(twoqty_pkg, [
        {"num_id": "N001", "value_as_printed": "5.2",
         "trace_ref": "R-PRED#v1:effect_size"},
        {"num_id": "N002", "value_as_printed": "0.78",
         "trace_ref": "R-PRED#v1:p_ab"},
    ])
    gate = gate_numbers(load_package(twoqty_pkg))
    assert gate.status == "pass", gate.findings


def test_only_wrong_quantity_row_fails(twoqty_pkg):
    _set_numbers(twoqty_pkg, [
        {"num_id": "N001", "value_as_printed": "5.2",
         "trace_ref": "R-PRED#v1:effect_size"},
        {"num_id": "N002", "value_as_printed": "0.71",
         "trace_ref": "R-PRED#v1:p_ab"},
    ])
    # 正文呈现串同步改掉（账实一致），只剩对溯源值的比对失败
    p = Path(twoqty_pkg) / "sections" / "01-introduction.md"
    p.write_text(p.read_text(encoding="utf-8").replace("0.78", "0.71"),
                 encoding="utf-8")
    gate = gate_numbers(load_package(twoqty_pkg))
    assert gate.status == "fail"
    fails = [f for f in gate.findings
             if f["code"] == "numbers.printed_vs_trace"]
    assert len(fails) == 1 and "N002" in fails[0]["message"]


def test_bare_key_ambiguous_on_multi_quantity_line(twoqty_pkg):
    _set_numbers(twoqty_pkg, [
        {"num_id": "N001", "value_as_printed": "5.2",
         "trace_ref": "R-PRED#v1"},
        {"num_id": "N002", "value_as_printed": "0.78",
         "trace_ref": "R-PRED#v1:p_ab"},
    ])
    gate = gate_numbers(load_package(twoqty_pkg))
    assert "numbers.trace_ambiguous" in _codes(gate)


def test_quantity_field_and_suffix_conflict(twoqty_pkg):
    _set_numbers(twoqty_pkg, [
        {"num_id": "N001", "value_as_printed": "5.2",
         "trace_ref": "R-PRED#v1:effect_size", "quantity": "p_ab"},
        {"num_id": "N002", "value_as_printed": "0.78",
         "trace_ref": "R-PRED#v1:p_ab"},
    ])
    gate = gate_numbers(load_package(twoqty_pkg))
    assert "numbers.trace_quantity_conflict" in _codes(gate)
