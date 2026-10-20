"""项目骨架、交接导入、渲染横幅与 CLI 全流。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import add_review, make_design

from light_design import cli
from light_design.project import (
    design_dir,
    init_project,
    load_design,
    new_design,
    render_design_md,
    save_design,
)
from light_design.schema import empty_design
from light_design.util import read_yaml, today

FULL_HANDOFF = {
    "idea_id": "idea_x_123abc",
    "title": "种子想法",
    "finalization_level": "executable",
    "exec_spec": {
        "datasets": [{"name": "自建火鸡视频", "version": "6 段", "access": "自建"}],
        "strongest_baseline": {"name": "附录 A 神谕扫描", "doi": "10.1016/j.compag.2025.110856"},
        "metrics": [{"name": "MOTA", "convention_source": "MOTChallenge"}],
        "ablations": ["去掉轨迹长度特征"],
        "resource_budget": {"gpu_hours": 30},
        "key_details": ["三阈值联合回归"],
        "discriminating_experiment": {
            "description": "留一交叉验证",
            "readout_positive": "达神谕 98% 内",
            "readout_negative": "低于固定阈值基线",
            "readout_null": "差 <1 点且距神谕 >2 点",
        },
    },
}


def _write_handoff(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "idea_card.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_init_structure(project: Path):
    for rel in ("project.yaml", "index.yaml", "index.md",
                "design-stage/DESIGN_REPORT.md", "design-stage/intake_log.md",
                "designs", "exports"):
        assert (project / rel).exists(), rel
    meta = read_yaml(project / "project.yaml")
    assert meta["tool"] == "light-design"


def test_init_refuses_overwrite(project: Path):
    with pytest.raises(FileExistsError):
        init_project(project, " again")


def test_new_without_handoff(project: Path):
    d, missing = new_design(project, "无交接设计", "idea_1")
    assert d["status"] == "draft" and missing == []
    assert (design_dir(project, d["design_id"]) / "design.yaml").exists()
    assert (design_dir(project, d["design_id"]) / "design.md").exists()


def test_new_duplicate_title_rejected(project: Path):
    new_design(project, "重复题名", "idea_1")
    with pytest.raises(FileExistsError):
        new_design(project, "重复题名", "idea_2")


def test_import_full_handoff(project: Path, tmp_path: Path):
    hp = _write_handoff(tmp_path, FULL_HANDOFF)
    d, missing = new_design(project, "承接完整交接", "", handoff_path=hp)
    assert missing == []
    assert d["idea_id"] == "idea_x_123abc"  # 未显式给时从交接件回填
    statuses = {s["item"]: s["status"] for s in d["intake"]["spec_intake"]}
    assert all(v == "accepted" for v in statuses.values())
    assert len(statuses) == 6
    # 预填：status_quo 与 readout 三向
    assert d["contract"]["controls"][0]["status_quo"] is True
    assert d["evaluation"]["readout"]["positive"]["meaning"] == "达神谕 98% 内"
    log = (project / "design-stage" / "intake_log.md").read_text(encoding="utf-8")
    assert "承接齐全" in log


def test_import_missing_items_returns_list(project: Path, tmp_path: Path):
    bad = json.loads(json.dumps(FULL_HANDOFF))
    del bad["exec_spec"]["strongest_baseline"]
    bad["exec_spec"]["metrics"] = []
    hp = _write_handoff(tmp_path, bad)
    d, missing = new_design(project, "缺项交接", "", handoff_path=hp)
    assert sorted(missing) == ["metrics", "strongest_baseline"]
    returned = {r["item"] for r in d["intake"]["returned_items"]}
    assert returned == {"metrics", "strongest_baseline"}
    by_item = {s["item"]: s["status"] for s in d["intake"]["spec_intake"]}
    assert by_item["metrics"] == "returned"
    assert by_item["datasets"] == "accepted"
    log = (project / "design-stage" / "intake_log.md").read_text(encoding="utf-8")
    assert "打回 2 项" in log


def test_import_md_handoff_rejected(project: Path, tmp_path: Path):
    md = tmp_path / "design_handoff.md"
    md.write_text("# handoff", encoding="utf-8")
    with pytest.raises(ValueError):
        new_design(project, "md 交接", "", handoff_path=md)


def test_render_minimal_banner():
    md = render_design_md(make_design(tier="minimal"))
    assert "极简设计 · 不承载确认性结论" in md


def test_render_full_no_minimal_banner():
    md = render_design_md(make_design(tier="full"))
    assert "极简设计" not in md


def test_render_frozen_banner(project: Path):
    from light_design.gates import advance
    d = add_review(make_design())
    advance(d, "reviewed", date=today())
    advance(d, "frozen", date=today())
    md = render_design_md(d)
    assert "已冻结" in md
    assert d["freeze"]["content_hash"][:8] in md or d["freeze"]["content_hash"] in md
    assert "no_runs_yet" in md  # 可见性声明横幅


def test_render_aux_marked_provisional():
    d = make_design()
    d["aux"] = {"info_gain_estimates": {"R-TREAT": 0.7}}
    md = render_design_md(d)
    assert "暂定" in md


def test_cli_end_to_end(project: Path, tmp_path: Path, capsys):
    hp = _write_handoff(tmp_path, FULL_HANDOFF)
    root = str(project)
    assert cli.main(["new", root, "--title", "CLI 全流设计",
                     "--from-handoff", str(hp)]) == 0
    out = capsys.readouterr().out
    assert "承接齐全" in out
    designs = [p.name for p in (project / "designs").iterdir()]
    did = designs[0]
    # 空骨架 validate 应失败并逐条列缺（骨架用途即在于此）
    assert cli.main(["validate", root, did]) == 1
    # 用完整设计覆盖后全流走通
    d = make_design()
    d["design_id"] = did
    add_review(d)
    save_design(project, d)
    assert cli.main(["validate", root, did]) == 0
    assert cli.main(["advance", root, did, "--to", "reviewed"]) == 0
    assert cli.main(["advance", root, did, "--to", "frozen"]) == 0
    assert cli.main(["list", root]) == 0
    assert cli.main(["render", root, did]) == 0
    saved = load_design(project, did)
    assert saved["status"] == "frozen"


def test_cli_new_missing_handoff_lists_returns(project: Path, tmp_path: Path, capsys):
    bad = {"idea_id": "i1", "exec_spec": {"datasets": [{"name": "d"}]}}
    hp = _write_handoff(tmp_path, bad)
    assert cli.main(["new", str(project), "--title", "缺项 CLI",
                     "--from-handoff", str(hp)]) == 0
    out = capsys.readouterr().out
    assert "打回清单" in out and "strongest_baseline" in out


def test_empty_design_skeleton_sections_present():
    d = empty_design("d1", "i1", "t", "full", today())
    for section in ("registration", "intake", "claims", "plan", "contract",
                    "evaluation", "validity", "resources", "freeze",
                    "handoff", "aux"):
        assert section in d
