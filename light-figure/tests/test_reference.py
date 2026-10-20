"""参考图入包登记与验收落字（约束 9）。"""

import pytest

from light_figure.project import load_package, provenance_row
from light_figure.reference import (
    ReferenceError, accept_reference, register_reference,
)
from light_figure.util import sha256_file
from conftest import FIG_DATA, FIG_METHOD, make_reference_png


def test_register_copies_and_pins_hash(pkg, tmp_path):
    src = make_reference_png(tmp_path / "ref.png")
    outcome = register_reference(pkg["root"], FIG_METHOD, src,
                                 model_name="GPT Image",
                                 model_version="1")
    copied = pkg["root"] / "schematic" / "reference" / "fig-method.png"
    assert copied.exists()
    assert outcome["sha256"] == sha256_file(copied)
    prov = load_package(pkg["root"])["provenance"]
    row = provenance_row(prov, FIG_METHOD)
    assert row["reference_image_hash"] == outcome["sha256"]
    assert row["generation_model"] == {"name": "GPT Image",
                                        "version": "1"}


def test_register_rejects_duplicate(pkg, tmp_path):
    src = make_reference_png(tmp_path / "ref.png")
    register_reference(pkg["root"], FIG_METHOD, src)
    with pytest.raises(ReferenceError):
        register_reference(pkg["root"], FIG_METHOD, src)


def test_register_data_line_rejected(pkg, tmp_path):
    src = make_reference_png(tmp_path / "ref.png")
    with pytest.raises(ReferenceError):
        register_reference(pkg["root"], FIG_DATA, src)


def test_accept_requires_all_three_checks(pkg, tmp_path):
    src = make_reference_png(tmp_path / "ref.png")
    register_reference(pkg["root"], FIG_METHOD, src)
    with pytest.raises(ReferenceError) as exc:
        accept_reference(pkg["root"], FIG_METHOD, by="author",
                         checks={"labels_verbatim": True})
    assert any("structures_factual" in g for g in exc.value.gaps)
    accept_reference(pkg["root"], FIG_METHOD, by="author",
                     checks={"labels_verbatim": True,
                             "structures_factual": True,
                             "formulas_values_checked": True})
    prov = load_package(pkg["root"])["provenance"]
    row = provenance_row(prov, FIG_METHOD)
    assert row["reference_acceptance"]["done"] is True
    assert row["reference_acceptance"]["by"] == "author"
    assert row["reference_acceptance"]["checks"] == {
        "labels_verbatim": True, "structures_factual": True,
        "formulas_values_checked": True}
