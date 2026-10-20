"""测试夹具：合成 Design 交接四件套（与 light_design.export 同形态）。

注意：合成卡是测试夹具——真实 frozen 设计目前不存在（Design 演示停在
reviewed），演示纪律见 REDESIGN-DRAFT §1；这里只验工具行为。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from light_experiment.project import init_project, intake

DESIGN_ID = "tracker-thresholds_ab12cd"
DESIGN_HASH = hashlib.sha256(b"frozen-design-v1").hexdigest()

SPEC = {
    "config": {"model": "byte3track", "threshold_source": "predicted"},
    "params": {"theta_high": 0.6, "theta_low": 0.1, "theta_mod_iou": 0.35},
    "code_snapshot": {"hash": "c" * 64, "git_commit": "abc1234", "git_dirty": False},
    "data_version": {"dataset": "turkey-barn-repro", "version": "v3", "split_seed": 7},
    "environment": {"declaration": "python 3.11 / torch 2.3 / RTX5000 x1",
                    "machine_tier": "lab-1gpu"},
    "root_seed": 42,
}


def registry_line(run_id: str, role: str, control_run=None, stage: str = "main") -> dict:
    """与 light_design.export._registry_line 同形态的一行。"""
    return {
        "design_id": DESIGN_ID,
        "run_id": run_id,
        "role": role,
        "control_run": control_run,
        "stage": stage,
        "primary_metric": {"name": "MOTA", "direction": "higher"},
        "readout": {
            "positive": {"meaning": "留出段 MOTA 达神谕 98% 以内"},
            "negative": {"meaning": "任一留出段低于固定阈值基线"},
            "null": {"meaning": "与固定阈值差 <1 点且距神谕 >2 点"},
        },
        "expected": None,
        "seeds": 3,
        "repetitions": 6,
        "content_hash": DESIGN_HASH,
    }


def make_card(status: str = "frozen") -> dict:
    return {
        "design_id": DESIGN_ID,
        "title": "零调参阈值预测（设计）",
        "status": status,
        "idea_id": "zero-tuning-tracker-thresholds-predicted_77cdb7",
        "freeze": {"content_hash": DESIGN_HASH, "frozen_at": "2026-10-20",
                   "amendments": []},
        # 方案区（与 light_design.export 的 design_card 全量投影同
        # 形态）：干预核查点在设计级全局声明，EXP-D04 齐备检查认此来源
        "plan": {
            "design_type": "判别实验",
            "intervention_checkpoints": [
                "theta_source 实际生效：处理臂产物逐 run 留证，声称来源"
                "与实际生效来源一致才算干预成立"],
        },
        "contract": {
            "runs": [
                {"run_id": "R00", "role": "control", "control_run": None,
                 "depends_on": [], "stage": "main"},
                {"run_id": "R01", "role": "treatment", "control_run": "R00",
                 "depends_on": ["R00"], "stage": "main"},
            ],
            "controls": [{"name": "固定阈值（种子 2.5 分钟组）", "status_quo": True}],
            "ablations": [],
        },
        "evaluation": {"primary_metric": {"name": "MOTA", "direction": "higher"}},
        "resources": {
            "budget": {"compute": "30 GPU 小时", "time": "3 周"},
            "circuit_breakers": [
                {"metric": "gpu_hours", "threshold": 30, "action": "stop"}],
        },
    }


def write_export(base: Path, *, card: dict | None = None,
                 lines: list[dict] | None = None, brief: str | None = None,
                 repro: str | None = None, skip: tuple[str, ...] = ()) -> Path:
    """把四件套写进 base/exports/<design_id>/ 并返回该目录。"""
    card = card if card is not None else make_card()
    out = base / "exports" / DESIGN_ID
    out.mkdir(parents=True, exist_ok=True)
    if "experiment_brief.md" not in skip:
        (out / "experiment_brief.md").write_text(
            brief if brief is not None else
            f"# 实验运行清单\n\n> 🔒 冻结哈希 `{DESIGN_HASH}`\n", encoding="utf-8")
    if "design_card.json" not in skip:
        (out / "design_card.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    if "expected_registry.jsonl" not in skip:
        lines = lines if lines is not None else [
            registry_line("R00", "control"),
            registry_line("R01", "treatment", control_run="R00"),
        ]
        (out / "expected_registry.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines),
            encoding="utf-8")
    if "reproducibility.md" not in skip:
        (out / "reproducibility.md").write_text(
            repro if repro is not None else
            f"# 复现字段清单\n\n- 内容哈希：`{DESIGN_HASH}`\n", encoding="utf-8")
    return out


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    init_project(root, "火鸡行为检测")
    return root


@pytest.fixture()
def export_dir(tmp_path: Path) -> Path:
    return write_export(tmp_path)


@pytest.fixture()
def exec_pkg(project: Path, export_dir: Path) -> tuple[Path, str]:
    """承接成功的执行包：返回 (project_root, exec_id)。"""
    execution, gaps = intake(project, export_dir)
    assert gaps == []
    return project, execution["exec_id"]
