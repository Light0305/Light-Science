"""图包骨架：init 布局、package_id、读写往返。"""

import re
from pathlib import Path

import pytest

from light_figure.project import DIRS, FILES, init_package, load_package


def test_init_creates_full_layout(tmp_path):
    root = tmp_path / "figs"
    head = init_package(root, "Demo Paper Figures")
    for name in FILES.values():
        if name == FILES["report"]:
            continue  # report 由 report 命令生成，init 不预建
        assert (root / name).exists(), name
    for d in DIRS:
        assert (root / d).is_dir(), d
    assert head["status"] == "intake"
    assert head["figures"] == []
    assert head["intake"] is None


def test_package_id_format(tmp_path):
    head = init_package(tmp_path / "a", "Demo Paper Figures")
    assert re.fullmatch(r"demo-paper-figures_[0-9a-f]{6}",
                        head["package_id"])


def test_init_refuses_existing_package(tmp_path):
    root = tmp_path / "figs"
    init_package(root, "Once")
    with pytest.raises(FileExistsError):
        init_package(root, "Twice")


def test_load_package_roundtrip(tmp_path):
    root = tmp_path / "figs"
    init_package(root, "Roundtrip")
    pkg = load_package(root)
    assert pkg["head"]["title"] == "Roundtrip"
    assert pkg["backend"]["backend"] is None
    assert pkg["journal_contract"]["registered"] is False
    assert pkg["provenance"]["entries"] == []
    assert pkg["contracts"] == {}


def test_journal_skeleton_uses_nature_anchors(tmp_path):
    root = tmp_path / "figs"
    init_package(root, "Anchors")
    jc = load_package(root)["journal_contract"]
    assert jc["columns_mm"] == {"single": 89.0, "double": 183.0}
    assert jc["max_height_mm"] == 170.0
    assert jc["font"]["min_pt"] == 5.0 and jc["font"]["max_pt"] == 7.0
    # 骨架容差 = 全局默认参数集（未放宽）
    from light_figure import schema

    assert jc["tolerances"] == {
        k: v["default"] for k, v in schema.TOLERANCE_PARAMS.items()}
