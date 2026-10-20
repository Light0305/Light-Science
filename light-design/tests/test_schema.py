"""校验器：每条硬规则的正反例。"""

from __future__ import annotations

from conftest import clone, make_design

from light_design.schema import validate_design


def _errs(d) -> str:
    return "；".join(validate_design(d))


def test_valid_full_design_passes(design):
    assert validate_design(design) == []


def test_valid_minimal_design_passes():
    assert validate_design(make_design(tier="minimal")) == []


def test_not_a_mapping():
    assert validate_design(["x"]) == ["设计书不是 YAML 映射"]


def test_missing_idea_id(design):
    design["idea_id"] = ""
    assert "idea_id" in _errs(design)


def test_visibility_missing(design):
    design["registration"]["visibility"] = None
    assert "visibility" in _errs(design)


def test_visibility_results_seen_blocks_confirmatory(design):
    design["registration"]["visibility"] = "results_seen"
    assert "results_seen" in _errs(design)
    design["claims"]["primary_claims"][0]["confirmatory"] = False
    assert validate_design(design) == []


def test_claims_over_two(design):
    c = clone(design["claims"]["primary_claims"][0])
    design["claims"]["primary_claims"] += [c, clone(c)]
    assert "上限 2 条" in _errs(design)


def test_claims_empty(design):
    design["claims"]["primary_claims"] = []
    assert "primary_claims 为空" in _errs(design)


def test_claim_without_minimum_evidence(design):
    design["claims"]["primary_claims"][0]["minimum_convincing_evidence"] = ""
    assert "minimum_convincing_evidence" in _errs(design)


def test_anti_claims_empty(design):
    design["claims"]["anti_claims"] = []
    assert "anti_claims 为空" in _errs(design)


def test_minimal_confirmatory_conflict():
    d = make_design(tier="minimal")
    d["claims"]["primary_claims"][0]["confirmatory"] = True
    assert "不许承载确认性主结论" in _errs(d)


def test_variables_groups_incomplete(design):
    design["plan"]["variables"] = [
        v for v in design["plan"]["variables"] if v["group"] != "covariate"]
    assert "三组不齐" in _errs(design)


def test_variable_domain_missing(design):
    design["plan"]["variables"][0]["domain"] = {}
    assert "domain" in _errs(design)


def test_variable_choice_domain_needs_values(design):
    design["plan"]["variables"][0]["domain"] = {"kind": "choice", "values": []}
    assert "values" in _errs(design)


def test_replication_level_missing(design):
    design["plan"]["replication_level"] = None
    assert "replication_level" in _errs(design)


def test_intervention_checkpoints_required_full(design):
    design["plan"]["intervention_checkpoints"] = []
    assert "intervention_checkpoints" in _errs(design)


def test_controls_empty(design):
    design["contract"]["controls"] = []
    assert "controls 为空" in _errs(design)


def test_status_quo_missing(design):
    design["contract"]["controls"][0]["status_quo"] = False
    assert "status_quo" in _errs(design)


def test_ablation_missing_what_it_tests(design):
    design["contract"]["ablations"][0]["what_it_tests"] = ""
    assert "what_it_tests" in _errs(design)


def test_ablation_missing_expected_if(design):
    design["contract"]["ablations"][0]["expected_if_component_matters"] = None
    assert "expected_if_component_matters" in _errs(design)


def test_unnecessary_ablations_must_exist(design):
    del design["contract"]["unnecessary_ablations"]
    assert "unnecessary_ablations" in _errs(design)


def test_treatment_run_without_control_run(design):
    design["contract"]["runs"][1]["control_run"] = None
    assert "control_run" in _errs(design)


def test_treatment_run_control_not_in_depends_on(design):
    design["contract"]["runs"][1]["depends_on"] = []
    assert "depends_on" in _errs(design) and "对照先行" in _errs(design)


def test_treatment_run_control_wrong_role(design):
    design["contract"]["runs"][0]["role"] = "other"
    assert "不是 control 角色" in _errs(design)


def test_depends_on_unknown_run(design):
    design["contract"]["runs"][1]["depends_on"] = ["R-CTRL", "R-GHOST"]
    assert "不存在的 run" in _errs(design)


def test_dependency_cycle(design):
    design["contract"]["runs"][0]["depends_on"] = ["R-TREAT"]
    assert "有环" in _errs(design)


def test_readout_missing_null(design):
    design["evaluation"]["readout"]["null"] = None
    assert "readout.null" in _errs(design)


def test_tuning_parity_missing(design):
    design["evaluation"]["tuning_parity"] = None
    assert "tuning_parity" in _errs(design)


def test_primary_metric_missing(design):
    design["evaluation"]["primary_metric"] = None
    assert "primary_metric" in _errs(design)


def test_seeds_missing(design):
    design["evaluation"]["seeds"] = {"count": None, "policy": ""}
    assert "seeds.count" in _errs(design)


def test_validity_category_missing(design):
    design["validity"]["threats"] = [
        t for t in design["validity"]["threats"] if t["category"] != "external"]
    assert "效度类别缺失" in _errs(design)


def test_threat_bad_status(design):
    design["validity"]["threats"][0]["status"] = "ignored"
    assert "三态" in _errs(design)


def test_threat_na_without_note(design):
    t = design["validity"]["threats"][3]  # external / na
    assert t["status"] == "na"
    t["note"] = ""
    assert "note 为空" in _errs(design)


def test_power_missing_full(design):
    design["resources"]["power"] = None
    assert "power" in _errs(design)


def test_power_sesoi_missing(design):
    design["resources"]["power"]["sesoi"] = ""
    assert "sesoi" in _errs(design)


def test_power_sensitivity_range_missing(design):
    design["resources"]["power"]["sensitivity_range"] = ""
    assert "sensitivity_range" in _errs(design)


def test_power_derived_missing(design):
    design["resources"]["power"]["derived"] = {}
    assert "derived" in _errs(design)


def test_power_insufficient_blocks_confirmatory(design):
    design["resources"]["power"]["sufficient"] = False
    assert "下调声称" in _errs(design)
    design["claims"]["primary_claims"][0]["confirmatory"] = False
    assert validate_design(design) == []


def test_circuit_breakers_empty(design):
    design["resources"]["circuit_breakers"] = []
    assert "circuit_breakers" in _errs(design)


def test_minimal_six_baseline_enforced():
    d = make_design(tier="minimal")
    d["resources"]["circuit_breakers"] = []
    assert "circuit_breakers" in _errs(d)  # 熔断线是极简底线六件之一


def test_aux_forbidden_key(design):
    design["aux"] = {"verdict": "pass"}
    assert "aux 区混入判定字段" in _errs(design)


def test_aux_unknown_key(design):
    design["aux"] = {"whatever_score": 1}
    assert "aux 区未知字段" in _errs(design)


def test_aux_allowed_key(design):
    design["aux"] = {"info_gain_estimates": {"R-TREAT": 0.7}}
    assert validate_design(design) == []
