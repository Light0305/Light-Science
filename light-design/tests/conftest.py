"""测试共用构造器：一份完整合法的 full 级设计书 + 项目夹具。"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from light_design.project import init_project, save_design
from light_design.schema import INTAKE_ITEMS, STAGE1_ITEMS, empty_design
from light_design.util import today

TITLE = "Zero-tuning tracker thresholds: controlled evaluation design"


def make_design(tier: str = "full") -> dict:
    """构造一份能通过 validate_design 的完整设计书（draft）。"""
    d = empty_design("design_test_abc123", "idea_test_def456", TITLE, tier, today())
    d["registration"].update({
        "visibility": "no_runs_yet",
        "existing_assets": [],
        "software_env": "python 3.12 / torch 2.x",
        "designer": {"model": "claude-opus-x", "family": "anthropic-claude"},
    })
    d["intake"].update({
        "source_handoff": {"path": "idea_card.json", "consumed_at": today(),
                            "handoff_hash": "0123456789abcdef"},
        "original_question": "视频级统计量能否预测多目标跟踪的关联阈值？",
        "spec_intake": [
            {"item": item, "handoff_value": "交接原值摘要",
             "design_location": "见 INTAKE_LOCATIONS", "status": "accepted"}
            for item in INTAKE_ITEMS
        ],
        "returned_items": [],
    })
    d["claims"].update({
        "primary_claims": [{
            "id": "C1",
            "statement": "视频级统计量可预测关联阈值，留出视频 MOTA 达神谕 98% 内",
            "why_it_matters": "免逐集调参是部署瓶颈",
            "minimum_convincing_evidence": "留一交叉验证下全面优于固定阈值且距神谕 ≤2 点",
            "confirmatory": tier == "full",
        }],
        "supporting_claim": None,
        "anti_claims": [{
            "id": "A1",
            "statement": "增益只来自时长查表（时长是唯一有效特征）",
            "excluded_by": "ABL-3",
        }],
    })
    d["plan"].update({
        "design_type": "对照实验型",
        "variables": [
            {"name": "threshold_source", "group": "treatment",
             "domain": {"kind": "choice",
                        "values": ["predicted", "fixed", "oracle"]}},
            {"name": "MOTA", "group": "outcome",
             "domain": {"kind": "range", "min": 0.0, "max": 1.0}},
            {"name": "video_duration", "group": "covariate",
             "domain": {"kind": "choice", "values": ["2.5min", "5min"]}},
        ],
        "intervention_mechanism": [{
            "variable": "threshold_source",
            "how": "跟踪启动前由回归器/固定值/神谕表写入三阈值配置，运行日志回读实际值",
        }],
        "intervention_checkpoints": ["每 run 后核对日志中实际三阈值与声称取值一致"],
        "replication_level": "video",
        "replication_counts": {"videos": 6},
    })
    d["contract"].update({
        "controls": [{
            "name": "种子论文附录 A 逐视频神谕阈值扫描（上限对照）",
            "role": "control", "status_quo": True,
            "source": "doi:10.1016/j.compag.2025.110856",
        }],
        "ablations": [{
            "id": "ABL-1", "what_it_tests": "轨迹长度分布特征的边际贡献",
            "expected_if_component_matters": "去掉后留出 MOTA 下降 ≥ SESOI",
            "type": "component", "form": "leave_one_out", "claim_ref": "C1",
        }],
        "unnecessary_ablations": [
            {"what": "去掉目标密度特征的消融", "reason": "与 ABL-1 共线，合并检验"}],
        "runs": [
            {"run_id": "R-CTRL", "role": "control", "stage": "main",
             "depends_on": [], "priority": 1},
            {"run_id": "R-TREAT", "role": "treatment", "control_run": "R-CTRL",
             "depends_on": ["R-CTRL"], "stage": "main", "priority": 2},
        ],
    })
    d["evaluation"].update({
        "primary_metric": {"name": "MOTA", "definition": "MOTChallenge 口径",
                           "direction": "higher_better",
                           "convention_source": "MOTChallenge 与种子论文口径"},
        "sesoi": {
            "value": 2.0, "unit": "MOTA 百分点", "direction": "higher",
            "bounds": "等价界取 ±value 对称双侧界",
            "basis": "承卡判别实验预写判读阈值（距神谕 ≤2 点）",
            "estimand_ref": "claims.primary_claims[C1]",
            "summary_measure": "mean_diff",
        },
        "guardrail_metrics": [{"name": "IDF1", "bound": "不低于固定阈值基线"}],
        "readout": {
            "positive": {"meaning": "留出 MOTA 达神谕 98% 内且优于固定阈值：映射成立",
                         "action": "进入铺开阶段"},
            "negative": {"meaning": "任一留出段低于固定阈值基线：映射不存在",
                         "action": "回炉 facet"},
            "null": {"meaning": "与固定阈值差 <1 点且距神谕 >2 点：判别力不足",
                     "action": "先扩样本段数再判"},
        },
        "tuning_parity": {"statement": "回归器与固定阈值基线同等调参预算：各 20 次试验",
                          "details": []},
        "seeds": {"count": 5, "policy": "预先生成并登记种子清单"},
        "repetitions": 5,
    })
    d["validity"].update({
        "threats": [
            {"category": "conclusion", "item": "低统计功效",
             "status": "mitigated", "note": "功效核算见 resources.power，种子数按 SESOI 推导"},
            {"category": "internal", "item": "批次与条件对齐",
             "status": "mitigated", "note": "同批同期对照，运行顺序随机化"},
            {"category": "construct", "item": "指标即构念",
             "status": "residual", "note": "MOTA 只代表跟踪精度，不外推行为识别质量"},
            {"category": "external", "item": "单一数据集推广",
             "status": "na", "note": "本设计只声称自建火鸡视频范围，不作跨物种声称"},
        ],
        "structural_checks": [
            {"item": "数据泄漏", "status": "pass", "note": "统计量只用视频前段"},
            {"item": "伪重复", "status": "pass", "note": "独立重复层级=视频"},
        ],
    })
    d["resources"].update({
        "power": {
            "sesoi": "MOTA 2 个百分点", "basis": "SESOI",
            "alpha": 0.05, "target_power": 0.8, "method": "模拟",
            "derived": {"seeds": 5, "repetitions": 5, "eval_set_size": 6},
            "sensitivity_range": "SESOI 1–3 点时所需视频段数 4–11 段",
            "sufficient": True,
        },
        "budget": {"compute": "30 GPU 时", "time": "3 周", "human": "含标注校验人时"},
        "stages": [{"name": "判别实验", "goal": "留一交叉验证",
                    "entry_condition": "设计冻结",
                    "exit_condition": "判读非 negative"}],
        "circuit_breakers": [
            {"metric": "运行失败率", "threshold": ">30%", "action": "停机审查"}],
    })
    d["handoff"].update({
        "expected_registry": [{
            "run_id": "R-CTRL", "expected": "复现附录 A 神谕值 ±2%",
            "sesoi": {
                "value": 2.0, "unit": "MOTA 百分点", "direction": "higher",
                "bounds": "等价界取 ±value 对称双侧界",
                "basis": "承卡判别实验预写判读阈值（距神谕 ≤2 点）",
                "estimand_ref": "claims.primary_claims[C1]",
                "summary_measure": "mean_diff",
            },
        }],
        "repro_fields": {"seeds": [1, 2, 3, 4, 5]},
        "checkpoints": [{"node": "主实验前", "human_confirm": True}],
    })
    return d


def add_review(d: dict, *, family: str = "openai-gpt", decision: str = "pass",
               review_status: str = "ok") -> dict:
    """给设计书写入一份齐全的定版评审记录。"""
    d["freeze"]["review"] = {
        "reviewer": "gpt-reviewer",
        "family": family,
        "date": today(),
        "items": {it: {"status": "pass", "note": "过"} for it in STAGE1_ITEMS},
        "decision": decision,
        "review_status": review_status,
    }
    return d


def frozen_design() -> dict:
    """一份已走完门冻结的设计书（draft → reviewed → frozen 全真推进）。"""
    from light_design.gates import advance
    d = add_review(make_design())
    advance(d, "reviewed", date=today())
    advance(d, "frozen", date=today())
    return d


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    init_project(root, "测试方向")
    return root


@pytest.fixture()
def design() -> dict:
    return make_design()


@pytest.fixture()
def design_in_project(project: Path) -> dict:
    d = make_design()
    save_design(project, d)
    return d


def clone(d: dict) -> dict:
    return copy.deepcopy(d)
