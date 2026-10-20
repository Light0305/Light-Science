"""schema 词表与代码计算口径：severity 只取独立提案 MAX、佐证不抬级。"""

from light_review import schema


def test_computed_severity_takes_max_of_proposals():
    assert schema.computed_severity({"S1": "minor", "S2": "major"}) == "major"
    assert schema.computed_severity({"S1": "critical"}) == "critical"
    assert schema.computed_severity({}) is None


def test_computed_severity_independent_of_corroboration_count():
    # 五席同提 minor 仍是 minor：佐证数不进 severity 计算（RV-05）
    many = {f"S{i}": "minor" for i in range(5)}
    assert schema.computed_severity(many) == "minor"


def test_form_rank_order():
    assert schema.form_rank("full") < schema.form_rank("qualified")
    assert schema.form_rank("limitations_only") < schema.form_rank("omit")


def test_seat_row_default_visibility_blinds_panel_stage():
    row = schema.seat_row("S1", "methods", "claude")
    panel = row["visibility"]["panel"]
    assert "other_reports" not in panel
    assert "consensus" not in panel
    assert "manuscript" in panel and "own_materials" in panel
    reported = row["visibility"]["reported"]
    assert "other_reports" in reported and "consensus" in reported


def test_new_review_phase2_pending_named():
    review = schema.new_review("r1")
    assert review["status"] == "intake"
    assert "domain_gate" in review["phase2_pending"]
    assert "decision" in review["phase2_pending"]
