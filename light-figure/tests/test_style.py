"""样式编译：确定性哈希、色板版本钉住、尺寸推导、文本产物。"""

import pytest

from light_figure.style import (
    StyleError, build_style, bundle_current, compile_bundle,
    derive_figsize,
)
from conftest import make_journal_contract


def test_compile_is_deterministic():
    jc = make_journal_contract()
    a = compile_bundle(jc)
    b = compile_bundle(jc)
    assert a["style_build_hash"] == b["style_build_hash"]
    assert len(a["style_build_hash"]) == 64


def test_compile_resolves_registered_palettes():
    bundle = compile_bundle(make_journal_contract())
    cat = bundle["palettes"]["categorical"]
    assert cat["entry_id"] == "PAL-OI-8"
    assert "#e69f00" in cat["colors"]
    cont = bundle["palettes"]["continuous"]
    assert cont["entry_id"] == "PAL-BATLOW"
    assert cont["colors"][0] == "#011959"  # batlow 起点（实测采样）
    assert bundle["rcparams"]["pdf.fonttype"] == 42
    assert bundle["rcparams"]["svg.fonttype"] == "none"


def test_compile_rejects_unregistered_journal():
    jc = make_journal_contract()
    jc["registered"] = False
    with pytest.raises(StyleError):
        compile_bundle(jc)


def test_compile_rejects_palette_version_drift():
    jc = make_journal_contract()
    jc["palettes"]["categorical"] = {"entry_id": "PAL-OI-8",
                                     "version": "9.9"}
    with pytest.raises(StyleError) as exc:
        compile_bundle(jc)
    assert "版本漂移" in "；".join(exc.value.gaps)


def test_compile_rejects_unknown_palette():
    jc = make_journal_contract()
    jc["palettes"]["continuous"] = {"entry_id": "PAL-NOPE", "version": "1"}
    with pytest.raises(StyleError):
        compile_bundle(jc)


def test_derive_figsize_from_column_width():
    bundle = compile_bundle(make_journal_contract())
    size = derive_figsize(bundle, "single", rows=1, cols=1)
    assert size["width_mm"] == 89.0
    assert size["figsize_in"][0] == pytest.approx(89 / 25.4, abs=1e-3)
    assert size["adjusted_to_max_height"] is False
    size = derive_figsize(bundle, "double", rows=1, cols=2)
    assert size["width_mm"] == 183.0


def test_derive_figsize_clamps_to_max_height():
    bundle = compile_bundle(make_journal_contract())
    size = derive_figsize(bundle, "double", rows=4, cols=1, aspect=1.0)
    assert size["adjusted_to_max_height"] is True
    assert size["height_mm"] <= 170.0 + 1e-6


def test_build_style_writes_three_artifacts(pkg):
    bundle = build_style(pkg["root"])
    styles = pkg["root"] / "data" / "styles"
    assert (styles / "bundle.json").exists()
    mplstyle = (styles / "light.mplstyle").read_text(encoding="utf-8")
    assert "axes.prop_cycle" in mplstyle
    theme = (styles / "theme.R").read_text(encoding="utf-8")
    assert "theme_light_figure" in theme
    assert "#e69f00" in theme
    loaded, problem = bundle_current(pkg["root"])
    assert problem is None
    assert loaded["style_build_hash"] == bundle["style_build_hash"]


def test_bundle_current_detects_journal_change(pkg):
    from light_figure.project import load_package, save_journal_contract

    build_style(pkg["root"])
    data = load_package(pkg["root"])
    jc = data["journal_contract"]
    jc["columns_mm"]["single"] = 95.0
    save_journal_contract(pkg["root"], jc)
    _bundle, problem = bundle_current(pkg["root"])
    assert problem is not None and "重跑 style build" in problem
