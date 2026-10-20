"""schema 词表与容差方向函数。"""

from light_figure import schema


def test_state_chain_consistent():
    assert schema.STATES[0] == "intake"
    assert schema.STATES[-1] == "delivered"
    for current, nxt in schema.NEXT_STATE.items():
        idx = schema.STATES.index(current)
        assert schema.STATES[idx + 1] == nxt
    assert "delivered" not in schema.NEXT_STATE


def test_kind_to_line_covers_intake_kinds():
    for kind in schema.INTAKE_KINDS:
        assert schema.KIND_TO_LINE[kind] in schema.LINES


def test_tolerance_defaults_match_yuan_params():
    # 约束 13 / 拍板 D3：Yuan 审计器实测参数集
    defaults = {k: v["default"] for k, v in schema.TOLERANCE_PARAMS.items()}
    assert defaults == {
        "alignment_pt": 1.5,
        "collision_inset_pt": 0.6,
        "collision_min_overlap_ratio": 0.05,
        "collision_clip_pt": 0.5,
        "collision_background_exempt_ratio": 0.20,
        "glyph_floor_pt": 5.0,
    }


def test_tolerance_relaxed_directions():
    # 偏差类容差：调大 = 放宽
    assert schema.tolerance_relaxed("alignment_pt", 2.5) is True
    assert schema.tolerance_relaxed("alignment_pt", 1.5) is False
    assert schema.tolerance_relaxed("alignment_pt", 1.0) is False
    # 字形地板是下限：调小 = 放宽
    assert schema.tolerance_relaxed("glyph_floor_pt", 4.0) is True
    assert schema.tolerance_relaxed("glyph_floor_pt", 6.0) is False
    # 非数值 / 未知参数不判（由数值校验报错）
    assert schema.tolerance_relaxed("glyph_floor_pt", "x") is False
    assert schema.tolerance_relaxed("nope", 99) is False
    assert schema.tolerance_relaxed("alignment_pt", True) is False


def test_r_enable_conditions_are_the_three_from_d2():
    assert sorted(schema.R_ENABLE_CONDITIONS) == [
        "library_r_only", "pipeline_in_r", "r_decisive_advantage"]


def test_audit_vocabularies():
    assert schema.AUDIT_VERDICTS == [
        "PASS", "REVIEW_REQUIRED", "FIX_BEFORE_DELIVERY", "NOT_AUDITABLE"]
    assert "policy_block" in schema.AUDIT_GATES
    assert len(schema.PANEL_ROLES) == 10
    assert len(schema.ARCHETYPES) == 4
