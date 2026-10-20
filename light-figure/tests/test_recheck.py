"""v1.1 本地复核环（FIG-D11）与 SVG 桥受限子集校验（FIG-D03）。"""

import pymupdf
import pytest

from light_figure.recheck import run_recheck
from light_figure.svgbridge import validate_svg_subset
from light_figure.util import load_structured
from conftest import FIG_DATA, FIG_METHOD


def test_recheck_demo_package_passes(produced_pkg):
    root = produced_pkg["root"]
    out = run_recheck(root)
    assert out["figures"][FIG_DATA]["overall"] == "PASS"
    assert out["figures"][FIG_METHOD]["overall"] == "PASS"
    for fig_id in (FIG_DATA, FIG_METHOD):
        record = load_structured(root / "audit" / f"{fig_id}.recheck.json")
        assert record["kind"] == "light-figure/recheck"
        assert record["scope"]["panels"] is None
        assert "file_layer" in record["measurement_basis"]


def test_recheck_local_scope_recorded(produced_pkg):
    root = produced_pkg["root"]
    run_recheck(root, fig_id=FIG_METHOD, panels=["a"])
    record = load_structured(root / "audit" / f"{FIG_METHOD}.recheck.json")
    assert record["scope"]["panels"] == ["a"]
    assert "局部复检" in record["scope"]["note"]


def test_recheck_detects_off_palette_color(pkg):
    from light_figure.style import build_style

    root = pkg["root"]
    build_style(root)  # 用色对合同色板须有 bundle 在场才可判
    doc = pymupdf.open()
    page = doc.new_page(width=252.28, height=120)  # ≈ 单栏 89mm
    page.draw_rect(pymupdf.Rect(20, 20, 120, 80), color=(1, 0, 0),
                   fill=(1, 0, 0))
    page.insert_text((20, 100), "Panel label", fontsize=7)
    exports = root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    doc.save(exports / f"{FIG_DATA}.pdf")
    doc.close()
    out = run_recheck(root, fig_id=FIG_DATA)
    findings = out["figures"][FIG_DATA]["findings"]
    hit = [f for f in findings if f["check"] == "colors_vs_palette"]
    assert hit and hit[0]["level"] == "fail"


def test_recheck_detects_unembedded_font(pkg):
    root = pkg["root"]
    doc = pymupdf.open()
    page = doc.new_page(width=252.28, height=120)
    page.insert_text((20, 60), "Base-14 font, not embedded", fontsize=7)
    exports = root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    doc.save(exports / f"{FIG_DATA}.pdf")
    doc.close()
    out = run_recheck(root, fig_id=FIG_DATA)
    findings = out["figures"][FIG_DATA]["findings"]
    hit = [f for f in findings if f["check"] == "fonts_embedded"]
    assert hit and hit[0]["level"] == "fail"


CLEAN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60">
  <rect x="5" y="5" width="40" height="30" fill="#0072b2"/>
  <text x="10" y="25" font-size="8">Video statistics</text>
  <path d="M45 20 L60 20" stroke="#000000"/>
</svg>
"""

DIRTY_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60">
  <image href="https://example.org/ref.png" x="0" y="0" width="10" height="10"/>
  <script>alert(1)</script>
  <text x="5" y="50">Label</text>
</svg>
"""


def test_svg_subset_clean_passes_with_texts(tmp_path):
    path = tmp_path / "clean.svg"
    path.write_text(CLEAN_SVG, encoding="utf-8")
    out = validate_svg_subset(path)
    assert out["ok"] is True
    assert out["texts"] == ["Video statistics"]


def test_svg_subset_rejects_image_script_external(tmp_path):
    path = tmp_path / "dirty.svg"
    path.write_text(DIRTY_SVG, encoding="utf-8")
    out = validate_svg_subset(path)
    assert out["ok"] is False
    joined = "；".join(out["gaps"])
    assert "image" in joined and "script" in joined
    assert "外部" in joined
