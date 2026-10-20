import pytest

from light_leader import scaffold
from light_leader.layout import SCAFFOLD_DIRS
from light_leader.util import load_yaml


def test_init_creates_skeleton(tmp_path):
    root = tmp_path / "proj"
    head = scaffold.init_project(root, "demo-proj", title="演示项目",
                                 goal="验证骨架")
    assert head.is_file()
    for d in SCAFFOLD_DIRS:
        assert (root / d).is_dir(), d
    data = load_yaml(head)
    assert data["kind"] == "light-leader/project"
    assert data["name"] == "demo-proj"
    assert data["title"] == "演示项目"
    stages = {s["stage"]: s for s in data["stages"]}
    # 十个阶段位齐全，含选刊扩展位与 memory 横贯位
    assert set(stages) == {
        "literature", "idea", "design", "experiment", "analysis",
        "journal-select", "write", "figure", "review", "memory"}
    assert stages["journal-select"]["skill"] == "light-journal-select"
    assert (root / "README.md").is_file()


def test_init_refuses_overwrite(tmp_path):
    root = tmp_path / "proj"
    scaffold.init_project(root, "demo-proj")
    with pytest.raises(FileExistsError):
        scaffold.init_project(root, "demo-proj")


def test_init_journal_target_landing(tmp_path):
    root = tmp_path / "proj"
    scaffold.init_project(root, "p")
    # 选刊 handoff 落点在项目根 journal/target（不在选刊包目录内）
    assert (root / "journal" / "target" / "guideline").is_dir()
    assert (root / "journal" / "target" / "templates").is_dir()
