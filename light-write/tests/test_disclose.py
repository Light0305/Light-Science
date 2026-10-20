"""按刊披露生成：多落点、缺字段点名不编造、output_validity 作者落字、STALE。"""

from pathlib import Path

import pytest

from light_write.disclose import (
    DiscloseError, disclosures_status, generate_disclosures,
)
from light_write.project import load_package, save_manuscript
from light_write.template_reg import register_template
from light_write.util import dump_json
from conftest import add_section, make_record


def test_disclose_single_position_filled_from_use_log(drafted_pkg):
    root = drafted_pkg["root"]
    result = generate_disclosures(root)
    assert len(result["generated"]) == 1
    text = (root / "sections" / "05-declarations.md").read_text(
        encoding="utf-8")
    assert "<!-- light-write:disclosure:declarations -->" in text
    assert "Declaration of AI Use" in text
    # 模板占位符由 use_log 聚合回填：{tool} ({version}) for {purpose}
    assert "Claude (Claude opus-4.5) for language editing" in text
    status = disclosures_status(root)
    assert status["complete"] is True and status["stale"] is False
    ms = load_package(root)["manuscript"]
    assert ms["disclosures"][0]["position"] == "declarations"


def test_disclose_rerun_replaces_block_not_duplicates(drafted_pkg):
    root = drafted_pkg["root"]
    generate_disclosures(root)
    generate_disclosures(root)
    text = (root / "sections" / "05-declarations.md").read_text(
        encoding="utf-8")
    assert text.count("light-write:disclosure:declarations") == 2  # 开+闭各一


def test_disclose_multi_position(pkg, tmp_path):
    root = pkg["root"]
    record = make_record()
    record["G"]["ai_policy"]["disclosure_positions"] = [
        "methods", "declarations"]
    record_path = tmp_path / "record-multi.json"
    dump_json(record_path, record)
    register_template(root, record_path)
    ms = load_package(root)["manuscript"]
    ms["use_log"] = [{"tool": "Claude", "model": "Claude",
                      "model_version": "opus-4.5", "purpose": "drafting",
                      "section": "methods", "date": "2026-10-20"}]
    ms["sections"] = [
        {"section_id": "S-methods", "file": "02-methods.md",
         "role": "methods", "goal": "方法", "required_info": [],
         "claim_ids": []},
        {"section_id": "S-declarations", "file": "05-declarations.md",
         "role": "declarations", "goal": "声明", "required_info": [],
         "claim_ids": []},
    ]
    save_manuscript(root, ms)
    (root / "sections" / "02-methods.md").write_text("Methods body.\n",
                                                    encoding="utf-8")
    (root / "sections" / "05-declarations.md").write_text(
        "Declarations body.\n", encoding="utf-8")
    result = generate_disclosures(root)
    assert {g["position"] for g in result["generated"]} == {
        "methods", "declarations"}
    for fname in ("02-methods.md", "05-declarations.md"):
        assert "disclosure:" in (root / "sections" / fname).read_text(
            encoding="utf-8")


def test_disclose_missing_wording_fields_named_not_fabricated(pkg, tmp_path):
    root = pkg["root"]
    record = make_record()
    record["G"]["ai_policy"]["disclosure_title"] = None
    record["G"]["ai_policy"]["disclosure_wording_template"] = None
    record_path = tmp_path / "record-nowording.json"
    dump_json(record_path, record)
    register_template(root, record_path)
    ms = load_package(root)["manuscript"]
    ms["use_log"] = [{"tool": "Claude", "model": "Claude",
                      "model_version": "opus-4.5", "purpose": "drafting",
                      "section": "methods", "date": "2026-10-20"}]
    save_manuscript(root, ms)
    with pytest.raises(DiscloseError) as exc:
        generate_disclosures(root)
    assert any("不许编造措辞" in g for g in exc.value.gaps)


def test_disclose_empty_use_log_blocked(drafted_pkg):
    root = drafted_pkg["root"]
    ms = load_package(root)["manuscript"]
    ms["use_log"] = []
    save_manuscript(root, ms)
    with pytest.raises(DiscloseError):
        generate_disclosures(root)


def test_disclose_output_validity_requires_author_note(pkg, tmp_path):
    root = pkg["root"]
    record = make_record()
    record["G"]["ai_policy"]["output_validity_evaluation"] = \
        "须说明作者如何评估 AI 输出有效性"
    record_path = tmp_path / "record-plos.json"
    dump_json(record_path, record)
    register_template(root, record_path)
    ms = load_package(root)["manuscript"]
    ms["use_log"] = [{"tool": "Claude", "model": "Claude",
                      "model_version": "opus-4.5", "purpose": "drafting",
                      "section": "declarations", "date": "2026-10-20"}]
    save_manuscript(root, ms)
    add_section(root, filename="05-declarations.md",
                text="Declarations body.\n", section_id="S-declarations")
    ms = load_package(root)["manuscript"]
    ms["sections"][0]["role"] = "declarations"
    save_manuscript(root, ms)
    with pytest.raises(DiscloseError) as exc:
        generate_disclosures(root)
    assert any("output_validity" in g for g in exc.value.gaps)
    ms = load_package(root)["manuscript"]
    ms["output_validity_note"] = "作者逐条人工核对了 AI 建议的全部数字与引用。"
    save_manuscript(root, ms)
    result = generate_disclosures(root)
    assert len(result["generated"]) == 1
    text = (root / "sections" / "05-declarations.md").read_text(
        encoding="utf-8")
    assert "逐条人工核对" in text
