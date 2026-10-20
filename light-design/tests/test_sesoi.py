"""DES-D01：结构化 SESOI 登记（evaluation.sesoi 单一事实源 + 登记行派生）。

覆盖 phase2-sesoi.md 验收 A2–A6：校验器完整性/一致性规则、确认性
必登记、登记行不许单独填、export 机械派生、amendment 命门 + 副本刷新。
"""

from __future__ import annotations

import copy
import json

import pytest
from conftest import clone, frozen_design, make_design

from light_design.export import ExportError, export_design
from light_design.gates import GateError, apply_amendment
from light_design.project import save_design
from light_design.schema import validate_design
from light_design.util import today


def _errs(d) -> str:
    return "；".join(validate_design(d))


# ---------------------------------------------------------------- A2 完整性

def test_valid_block_passes(design):
    assert validate_design(design) == []


def test_block_missing_basis_rejected(design):
    design["evaluation"]["sesoi"]["basis"] = ""
    errs = _errs(design)
    assert "evaluation.sesoi.basis" in errs and "推导依据" in errs


def test_block_missing_estimand_and_measure_rejected(design):
    design["evaluation"]["sesoi"]["estimand_ref"] = None
    design["evaluation"]["sesoi"]["summary_measure"] = "  "
    errs = _errs(design)
    assert "estimand_ref" in errs and "summary_measure" in errs


def test_block_nonpositive_value_rejected(design):
    design["evaluation"]["sesoi"]["value"] = 0
    assert "evaluation.sesoi.value" in _errs(design)
    design["evaluation"]["sesoi"]["value"] = "2.0"
    assert "evaluation.sesoi.value" in _errs(design)


def test_block_direction_mismatch_with_metric_rejected(design):
    design["evaluation"]["sesoi"]["direction"] = "lower"
    errs = _errs(design)
    assert "direction" in errs and "不一致" in errs


def test_block_bad_direction_word_rejected(design):
    design["evaluation"]["sesoi"]["direction"] = "up"
    assert "direction 非法" in _errs(design)


# ---------------------------------------------------------------- A3 必登记

def test_confirmatory_full_design_requires_block(design):
    design["evaluation"]["sesoi"] = None
    design["handoff"]["expected_registry"][0].pop("sesoi")
    errs = _errs(design)
    assert "evaluation.sesoi 缺失" in errs


def test_exploratory_design_block_optional():
    d = make_design(tier="minimal")
    d["evaluation"]["sesoi"] = None
    d["handoff"]["expected_registry"][0].pop("sesoi")
    assert validate_design(d) == []


# ---------------------------------------------------------------- A4 派生一致

def test_row_copy_tampered_rejected(design):
    design["handoff"]["expected_registry"][0]["sesoi"]["value"] = 3.0
    errs = _errs(design)
    assert "R-CTRL" in errs and "不一致" in errs


def test_row_sesoi_without_registration_rejected(design):
    design["evaluation"]["sesoi"] = None
    errs = _errs(design)
    assert "无 evaluation 登记来源" in errs


def test_confirmatory_row_missing_copy_rejected(design):
    design["handoff"]["expected_registry"][0].pop("sesoi")
    errs = _errs(design)
    assert "缺 sesoi 派生副本" in errs and "R-CTRL" in errs


# ---------------------------------------------------------------- A5 export

def test_export_registry_lines_carry_block(project):
    d = frozen_design()
    save_design(project, d)
    out = export_design(project, d)
    lines = [json.loads(x) for x in
             out["expected_registry"].read_text(encoding="utf-8").splitlines()
             if x.strip()]
    assert lines, "导出登记表不应为空"
    block = d["evaluation"]["sesoi"]
    for line in lines:
        assert line["sesoi"] == block


def test_export_rejects_tampered_row_copy(project):
    # export 自带派生一致性门（独立于 validate 的冻结哈希门）：冻结书的
    # 行内副本被改后，export 必须拒绝而不是把被改值复制进登记表。
    d = frozen_design()
    save_design(project, d)
    d["handoff"]["expected_registry"][0]["sesoi"]["value"] = 9.0
    with pytest.raises(ExportError) as e:
        export_design(project, d)
    assert any("不一致" in x for x in e.value.errors)


# ---------------------------------------------------------------- A6 amendment

def test_amend_sesoi_requires_user_signature():
    d = frozen_design()
    with pytest.raises(GateError) as e:
        apply_amendment(d, "evaluation.sesoi.value", 3.0,
                        reason="想放宽", results_seen="未跑任何运行",
                        date=today())
    assert any("命门字段" in x for x in e.value.errors)
    assert d["freeze"]["amendments"] == []


def test_amend_sesoi_with_signature_refreshes_row_copies():
    d = frozen_design()
    amd = apply_amendment(d, "evaluation.sesoi.value", 2.5,
                          reason="用户确认 SESOI 依据更新",
                          results_seen="未跑任何运行",
                          user_signed=True, by="user", date=today())
    assert amd["critical"] is True and amd["user_signed"] is True
    assert d["evaluation"]["sesoi"]["value"] == 2.5
    row = d["handoff"]["expected_registry"][0]
    assert row["sesoi"]["value"] == 2.5  # 派生副本同条 amendment 内刷新
    assert validate_design(d) == []      # 哈希链 + 一致性自洽


def test_amend_whole_block_with_signature():
    d = frozen_design()
    new_block = copy.deepcopy(d["evaluation"]["sesoi"])
    new_block["basis"] = "用户复核后更新的推导依据指针"
    apply_amendment(d, "evaluation.sesoi", new_block,
                    reason="依据指针更新", results_seen="未跑任何运行",
                    user_signed=True, by="user", date=today())
    assert d["handoff"]["expected_registry"][0]["sesoi"]["basis"] == \
        "用户复核后更新的推导依据指针"
    assert validate_design(d) == []
