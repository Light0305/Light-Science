"""数据图生产：源级预检（样式哈希/禁用色标/登记完整性）+ 真实渲染。"""

import pytest

from light_figure.gates import advance
from light_figure.produce import (
    ProduceError, parse_script_header, precheck_script,
    produce_data_figure,
)
from light_figure.project import load_package, provenance_row
from light_figure.style import build_style
from light_figure.util import sha256_file
from conftest import (
    DATA_SCRIPT, FIG_DATA, FIG_METHOD, write_data_script, write_source_data,
)


@pytest.fixture()
def contracted_pkg(filled_pkg):
    result = advance(filled_pkg["root"])
    assert result["advanced"], result["gaps"]
    filled_pkg["bundle"] = build_style(filled_pkg["root"])
    return filled_pkg


def test_produce_full_path(contracted_pkg):
    root = contracted_pkg["root"]
    write_source_data(root)
    write_data_script(root, contracted_pkg["bundle"]["style_build_hash"])
    outcome = produce_data_figure(root, FIG_DATA)
    assert (root / "exports" / "fig-data.pdf").exists()
    assert (root / "data" / "previews" / "fig-data.png").exists()
    assert (root / "audit" / "fig-data.alignment-input.json").exists()
    assert outcome["panels_measured"] == 2
    prov = load_package(root)["provenance"]
    row = provenance_row(prov, FIG_DATA)
    assert row["script_hash"] == sha256_file(
        root / "data" / "scripts" / "fig-data.py")
    assert row["source_data_hash"] == sha256_file(
        root / "data" / "source-data" / "fig-data.csv")
    assert row["style_build_hash"] == \
        contracted_pkg["bundle"]["style_build_hash"]
    assert row["backend"] == "python"
    assert "matplotlib" in row["runtime_version"]


def test_precheck_rejects_wrong_bundle_hash(contracted_pkg):
    root = contracted_pkg["root"]
    write_data_script(root, "0" * 64)
    _header, gaps = precheck_script(
        root, FIG_DATA, contracted_pkg["bundle"])
    assert any("style_build_hash" in g for g in gaps)


def test_precheck_rejects_banned_colormap(contracted_pkg):
    root = contracted_pkg["root"]
    script = DATA_SCRIPT.replace(
        'ax2.plot(arms, means, marker="o")',
        'ax2.plot(arms, means, marker="o")\n    '
        'ax2.imshow([[0, 1]], cmap="jet")')
    write_data_script(root, contracted_pkg["bundle"]["style_build_hash"],
                      script=script)
    _header, gaps = precheck_script(
        root, FIG_DATA, contracted_pkg["bundle"])
    assert any("禁用色标" in g for g in gaps)


def test_precheck_rejects_own_figsize(contracted_pkg):
    root = contracted_pkg["root"]
    script = DATA_SCRIPT.replace(
        'ax2.plot(arms, means, marker="o")',
        'fig.set_size_inches(7, 3)\n    ax2.plot(arms, means, marker="o")')
    write_data_script(root, contracted_pkg["bundle"]["style_build_hash"],
                      script=script)
    _header, gaps = precheck_script(
        root, FIG_DATA, contracted_pkg["bundle"])
    assert any("figsize" in g or "set_size_inches" in g for g in gaps)


def test_precheck_missing_header(contracted_pkg):
    root = contracted_pkg["root"]
    path = root / "data" / "scripts" / "fig-data.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def draw(fig, axes):\n    pass\n", encoding="utf-8")
    _header, gaps = precheck_script(
        root, FIG_DATA, contracted_pkg["bundle"])
    assert any("文件头登记块" in g for g in gaps)


def test_produce_fails_without_source_data(contracted_pkg):
    root = contracted_pkg["root"]
    write_data_script(root, contracted_pkg["bundle"]["style_build_hash"])
    with pytest.raises(ProduceError) as exc:
        produce_data_figure(root, FIG_DATA)
    assert any("源数据" in g for g in exc.value.gaps)


def test_produce_only_for_data_line(contracted_pkg):
    with pytest.raises(ProduceError):
        produce_data_figure(contracted_pkg["root"], FIG_METHOD)


def test_parse_header_roundtrip(contracted_pkg):
    root = contracted_pkg["root"]
    write_data_script(root, contracted_pkg["bundle"]["style_build_hash"])
    header = parse_script_header(
        (root / "data" / "scripts" / "fig-data.py")
        .read_text(encoding="utf-8"))
    assert header["fig_id"] == FIG_DATA
    assert header["axes"]["y"]["direction"] == "increasing"
    assert header["palette"]["categorical"] == "PAL-OI-8"
