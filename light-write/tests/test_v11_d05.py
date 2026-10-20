"""WRT-D05 卡内一致性：不一致必拦点名、一致必过、无 spec 文件诚实标注。"""

import copy

import pytest

from light_write.intake import IntakeError, check_card_consistency, run_intake
from light_write.project import init_package
from light_write.util import dump_json
from conftest import make_card, make_literature_rows, write_jsonl


def _setup(tmp_path, card, spec_rows=None):
    root = tmp_path / "ms"
    init_package(root, "Card Check Demo", "en")
    card_path = tmp_path / "conclusion_card.json"
    dump_json(card_path, card)
    if spec_rows is not None:
        (tmp_path / "spec_results.jsonl").write_text(
            "".join(__import__("json").dumps(r) + "\n" for r in spec_rows),
            encoding="utf-8")
    lit_path = write_jsonl(tmp_path / "pool.jsonl", make_literature_rows())
    return root, card_path, lit_path


def _spec_row(value, spec_id="S001", line="R-PRED"):
    return {"spec_id": spec_id, "registry_line_id": line,
            "status": "computed",
            "effect_size": {"type": "mean_diff", "value": value},
            "p_value": 0.01, "note": None, "provenance": None}


def test_consistent_card_with_spec_target_passes(tmp_path):
    root, card_path, lit_path = _setup(
        tmp_path, make_card(), spec_rows=[_spec_row(5.2)])
    result = run_intake(root, card_path, lit_path)
    assert result["card_consistency"]["spec_results"] == "checked"
    assert result["card_consistency"]["spec_rows_checked"] == 1


def test_card_value_conflicting_spec_target_blocked(tmp_path):
    root, card_path, lit_path = _setup(
        tmp_path, make_card(), spec_rows=[_spec_row(9.9)])
    with pytest.raises(IntakeError) as exc:
        run_intake(root, card_path, lit_path)
    assert any("卡内不一致" in g for g in exc.value.gaps)


def test_spec_pointer_dangling_blocked(tmp_path):
    root, card_path, lit_path = _setup(
        tmp_path, make_card(), spec_rows=[_spec_row(5.2, spec_id="S999")])
    with pytest.raises(IntakeError):
        run_intake(root, card_path, lit_path)


def test_no_spec_file_is_not_available_not_blocked(tmp_path):
    root, card_path, lit_path = _setup(tmp_path, make_card())
    result = run_intake(root, card_path, lit_path)
    assert result["card_consistency"]["spec_results"] == "not_available"


def test_counts_mismatch_blocked(tmp_path):
    card = make_card()
    card["counts"] = {"positive": 5, "negative": 0, "null": 0,
                      "undetermined": 0, "untested": 0, "total_lines": 2}
    gaps, _ = check_card_consistency(card, None)
    assert any("counts.positive" in g for g in gaps)


def test_provenance_to_unclaimed_line_noted_not_blocked(tmp_path):
    # 溯源行指向无主张映射的登记行（claim_ref 为空的行）在 Analysis
    # 侧合法存在：不拦，但在摘要留痕（真悬空由指针层/门二兜底）
    card = make_card()
    card["number_provenance"][0]["registry_line_id"] = "R-GHOST"
    card["number_provenance"][0]["verdict_line"] = "R-GHOST#v1"
    gaps, summary = check_card_consistency(card, None)
    assert gaps == []
    assert summary["unclaimed_provenance_rows"] == [0]


def test_same_pointer_two_values_blocked(tmp_path):
    card = make_card()
    card["number_provenance"].append(
        copy.deepcopy(card["number_provenance"][0]))
    card["number_provenance"][1]["value"] = 7.7
    gaps, _ = check_card_consistency(card, None)
    assert any("同指针两值" in g for g in gaps)


def test_numeric_row_without_spec_pointer_blocked(tmp_path):
    card = make_card()
    del card["number_provenance"][0]["spec_id"]
    gaps, _ = check_card_consistency(card, None)
    assert any("spec_id" in g for g in gaps)


def test_rounded_match_at_printed_precision_passes(tmp_path):
    # spec 原值 5.24933…，卡内登记呈现值 5.2（1 位精度）→ 舍入后一致
    card = make_card()
    card["number_provenance"][0]["value"] = 5.2
    root, card_path, lit_path = _setup(
        tmp_path, card, spec_rows=[_spec_row(5.2493333333)])
    result = run_intake(root, card_path, lit_path)
    assert result["card_consistency"]["spec_rows_checked"] == 1
