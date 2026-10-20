"""WRT-D02 词表实测轮的回归钉：证据登记齐全、英文词界口径、中文全形口径。"""

from pathlib import Path

from light_write import schema
from light_write.audit import gate_wording
from light_write.project import load_package
from conftest import make_record
from light_write.intake import run_intake
from light_write.project import init_package, save_manuscript
from light_write.template_reg import register_template
from light_write.util import dump_json


def test_wording_tables_evidence_complete():
    assert schema.validate_wording_tables() == []


def test_every_term_has_evidence_entry():
    for language, table in schema.WORDING_TABLES.items():
        ev = schema.WORDING_EVIDENCE[language]
        for term in table["banned_terms"]:
            assert ev["banned"][term]["evidence"]
            assert ev["banned"][term]["disposition"]
        for grade, entry in table["grades"].items():
            for term in entry["allowed_terms"]:
                assert ev["grades"][grade][term]["evidence"]


def _edit_section(root, fname, old, new):
    path = Path(root) / "sections" / fname
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_en_improves_is_not_a_banned_hit(drafted_pkg):
    # 首测证伪的子串误报：improves 含 proves 子串但不是证明级断言
    _edit_section(drafted_pkg["root"], "01-introduction.md",
                  "Method A shows a clear improvement over the "
                  "fixed-threshold baseline",
                  "Method A improves on the fixed-threshold baseline")
    gate = gate_wording(load_package(drafted_pkg["root"]))
    banned = [f for f in gate.findings if f["code"] == "wording.banned_term"]
    assert banned == [], gate.findings


def test_en_proves_still_banned_with_word_boundary(drafted_pkg):
    _edit_section(drafted_pkg["root"], "01-introduction.md",
                  "Method A shows a clear improvement",
                  "Method A proves a clear improvement")
    gate = gate_wording(load_package(drafted_pkg["root"]))
    assert any(f["code"] == "wording.banned_term" for f in gate.findings)


def _zh_pkg(tmp_path, upstreams):
    root = tmp_path / "ms-zh-d02"
    init_package(root, "中文词表实测稿", "zh")
    run_intake(root, upstreams["card"], upstreams["literature"])
    record_path = tmp_path / "record-zh-d02.json"
    dump_json(record_path, make_record(language="zh"))
    register_template(root, record_path)
    (root / "sections" / "01-introduction.md").write_text(
        "在显著性水平 0.05 下，两组差异未达预设界值 [claim:C1]。\n",
        encoding="utf-8")
    pkg_data = load_package(root)
    pkg_data["manuscript"]["sections"] = [
        {"section_id": "S-introduction", "file": "01-introduction.md",
         "role": "introduction", "goal": "确立空白",
         "required_info": ["空白"], "claim_ids": []}]
    save_manuscript(root, pkg_data["manuscript"])
    return root


def test_zh_xianzhuxing_not_carved_out_after_first_measurement(
        tmp_path, upstreams):
    # 首测未触发切分（语料中「显著性」0 命中）：含「显著性」的主张句
    # 仍按全形匹配命中「显著」——此口径由测量报告存档，非临场豁免
    root = _zh_pkg(tmp_path, upstreams)
    gate = gate_wording(load_package(root))
    assert any(f["code"] == "wording.banned_term" for f in gate.findings)
