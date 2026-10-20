"""二期：定版评审子流程 review prepare / record。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from conftest import clone, frozen_design, make_design
from light_design import cli
from light_design.gates import GateError, advance
from light_design.project import save_design
from light_design.review import (
    ReviewError,
    prepare_review,
    record_review,
    record_review_unavailable,
    review_dir,
)
from light_design.schema import STAGE1_ITEMS
from light_design.util import today

DID = "design_test_abc123"


def good_items(verdict: str = "pass") -> dict:
    return {it: {"verdict": verdict, "note": "逐项核对字段，依据充分"}
            for it in STAGE1_ITEMS}


def good_data(**over) -> dict:
    data = {"reviewer_model": "gpt-reviewer", "reviewer_family": "openai-gpt",
            "decision": "pass", "items": good_items()}
    data.update(over)
    return data


# ---------- prepare ----------

def test_prepare_writes_packet_and_checklist(project):
    d = make_design()
    save_design(project, d)
    out = prepare_review(project, d, date=today())
    assert out["packet"].exists() and out["checklist"].exists()
    packet = out["packet"].read_text(encoding="utf-8")
    for it in STAGE1_ITEMS:  # 五条标准逐条在包内
        assert it in packet
    assert "异家族" in packet and "自评不作数" in packet  # 评审者须知
    assert "no_runs_yet" in packet  # 结果可见性声明
    assert d["title"] in packet  # 设计书全文渲染在包内
    assert "--from-json" in packet  # 外部判定 JSON 回填说明
    checklist = yaml.safe_load(out["checklist"].read_text(encoding="utf-8"))
    assert set(checklist["items"]) == set(STAGE1_ITEMS)
    assert all(v["verdict"] is None for v in checklist["items"].values())
    assert checklist["designer"]["family"] == "anthropic-claude"


def test_prepare_rejected_when_frozen(project):
    d = frozen_design()
    with pytest.raises(ReviewError) as e:
        prepare_review(project, d, date=today())
    assert any("frozen" in x for x in e.value.errors)


def test_prepare_via_cli(project, design_in_project):
    assert cli.main(["review", "prepare", str(project), DID]) == 0
    assert (review_dir(project, DID) / "review_packet.md").exists()


# ---------- record：正例与落盘 ----------

def test_record_happy_path_then_freeze(project):
    d = make_design()
    save_design(project, d)
    rec = record_review(project, d, good_data(), date=today())
    assert rec["review_id"].startswith("RV-")
    assert d["freeze"]["review"]["review_status"] == "ok"
    stub = review_dir(project, DID) / "review_record.json"
    assert json.loads(stub.read_text(encoding="utf-8"))["review_id"] == rec["review_id"]
    # 落盘后全流可定版
    advance(d, "reviewed", date=today())
    advance(d, "frozen", date=today())
    assert d["status"] == "frozen"


def test_record_reject_decision_blocks_freeze(project):
    d = make_design()
    items = good_items()
    items["methodological_soundness"] = {"verdict": "fail", "note": "功效给不起"}
    record_review(project, d, good_data(decision="reject", items=items), date=today())
    advance(d, "reviewed", date=today())
    with pytest.raises(GateError) as e:
        advance(d, "frozen", date=today())
    assert any("decision" in x for x in e.value.errors)


# ---------- record：拒收纪律 ----------

def test_record_same_family_rejected(project):
    d = make_design()
    with pytest.raises(ReviewError) as e:
        record_review(project, d, good_data(reviewer_family="Anthropic-Claude"),
                      date=today())
    assert any("同模型家族" in x for x in e.value.errors)
    assert d["freeze"]["review"] is None  # 拒收不落盘


def test_record_same_model_rejected(project):
    d = make_design()
    with pytest.raises(ReviewError) as e:
        record_review(project, d, good_data(reviewer_model="claude-opus-x",
                                            reviewer_family="other-family"),
                      date=today())
    assert any("同一模型" in x for x in e.value.errors)


def test_record_missing_item_rejected(project):
    d = make_design()
    items = good_items()
    del items["competing_explanations"]
    with pytest.raises(ReviewError) as e:
        record_review(project, d, good_data(items=items), date=today())
    assert any("competing_explanations" in x and "缺项" in x
               for x in e.value.errors)


def test_record_item_without_note_rejected(project):
    d = make_design()
    items = good_items()
    items["question_quality"] = {"verdict": "pass", "note": ""}
    with pytest.raises(ReviewError) as e:
        record_review(project, d, good_data(items=items), date=today())
    assert any("note" in x for x in e.value.errors)


def test_record_shorthand_without_note_rejected(project):
    d = make_design()
    items = {it: "pass" for it in STAGE1_ITEMS}  # 只给结论不给依据
    with pytest.raises(ReviewError):
        record_review(project, d, good_data(items=items), date=today())


def test_record_bad_verdict_and_decision_rejected(project):
    d = make_design()
    items = good_items()
    items["theoretical_basis"] = {"verdict": "ok", "note": "x"}
    with pytest.raises(ReviewError):
        record_review(project, d, good_data(items=items), date=today())
    with pytest.raises(ReviewError):
        record_review(project, d, good_data(decision="maybe"), date=today())
    with pytest.raises(ReviewError):
        record_review(project, d, good_data(reviewer_family=""), date=today())


def test_record_pass_decision_with_failed_item_rejected(project):
    d = make_design()
    items = good_items()
    items["analysis_predetermined"] = {"verdict": "fail", "note": "判读未写死"}
    with pytest.raises(ReviewError) as e:
        record_review(project, d, good_data(decision="pass", items=items),
                      date=today())
    assert any("矛盾" in x for x in e.value.errors)


def test_record_on_frozen_rejected(project):
    d = frozen_design()
    with pytest.raises(ReviewError):
        record_review(project, d, good_data(), date=today())


# ---------- REVIEW_UNAVAILABLE 降级通道 ----------

def test_review_unavailable_recorded_and_freeze_blocked(project):
    d = make_design()
    save_design(project, d)
    rec = record_review_unavailable(project, d, date=today())
    assert d["freeze"]["review"]["review_status"] == "REVIEW_UNAVAILABLE"
    assert rec["review_id"].startswith("RV-")
    assert (review_dir(project, DID) / "review_record.json").exists()
    advance(d, "reviewed", date=today())
    with pytest.raises(GateError) as e:
        advance(d, "frozen", date=today())
    assert any("REVIEW_UNAVAILABLE" in x for x in e.value.errors)


def test_review_unavailable_then_recovered_by_real_review(project):
    d = make_design()
    record_review_unavailable(project, d, date=today())
    record_review(project, d, good_data(), date=today())  # 恢复后补评审覆盖降级记录
    assert d["freeze"]["review"]["review_status"] == "ok"
    advance(d, "reviewed", date=today())
    advance(d, "frozen", date=today())


def test_review_unavailable_via_cli(project, design_in_project):
    assert cli.main(["review", "record", str(project), DID,
                     "--review-unavailable"]) == 0
    from light_design.project import load_design
    d = load_design(project, DID)
    assert d["freeze"]["review"]["review_status"] == "REVIEW_UNAVAILABLE"


# ---------- 外部判定 JSON 回填 / 清单回填（CLI） ----------

def test_record_from_external_json_via_cli(project, design_in_project, tmp_path):
    verdict = {"reviewer_model": "gemini-judge", "reviewer_family": "google-gemini",
               "decision": "pass",
               "items": {it: {"verdict": "pass", "note": "外部判定依据"}
                         for it in STAGE1_ITEMS}}
    jp = tmp_path / "verdict.json"
    jp.write_text(json.dumps(verdict, ensure_ascii=False), encoding="utf-8")
    assert cli.main(["review", "record", str(project), DID,
                     "--from-json", str(jp)]) == 0
    from light_design.project import load_design
    d = load_design(project, DID)
    assert d["freeze"]["review"]["family"] == "google-gemini"
    assert d["freeze"]["review"]["source"] == "external_json"


def test_record_from_json_same_family_via_cli(project, design_in_project, tmp_path):
    verdict = {"reviewer_model": "claude-judge", "reviewer_family": "anthropic-claude",
               "decision": "pass",
               "items": {it: {"verdict": "pass", "note": "x"} for it in STAGE1_ITEMS}}
    jp = tmp_path / "verdict.json"
    jp.write_text(json.dumps(verdict, ensure_ascii=False), encoding="utf-8")
    assert cli.main(["review", "record", str(project), DID,
                     "--from-json", str(jp)]) == 1


def test_record_from_filled_checklist_via_cli(project, design_in_project):
    assert cli.main(["review", "prepare", str(project), DID]) == 0
    cp = review_dir(project, DID) / "review_checklist.yaml"
    data = yaml.safe_load(cp.read_text(encoding="utf-8"))
    data["reviewer"] = {"model": "deepseek-judge", "family": "deepseek"}
    data["decision"] = "pass"
    for it in STAGE1_ITEMS:
        data["items"][it]["verdict"] = "pass"
        data["items"][it]["note"] = "清单回填依据"
    cp.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert cli.main(["review", "record", str(project), DID]) == 0
    from light_design.project import load_design
    d = load_design(project, DID)
    assert d["freeze"]["review"]["reviewer"] == "deepseek-judge"
