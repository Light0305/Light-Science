"""模板核查记录消费校验：九组完整性、限额数值化、AI 政策组、过期、语言。"""

import copy

import pytest

from light_write.project import load_package
from light_write.template_reg import TemplateError, register_template
from light_write.util import dump_json
from light_write.validate import validate_package
from conftest import make_record


def _write_record(tmp_path, record, name="record.json"):
    path = tmp_path / name
    dump_json(path, record)
    return path


def test_register_good_record(pkg, record_path):
    result = register_template(pkg["root"], record_path)
    assert result["template_record_id"] == "TPL-DEMO-001"
    ms = load_package(pkg["root"])["manuscript"]
    assert ms["target_journal"]["journal_name"] == "Journal of Examples"
    report = validate_package(pkg["root"])
    assert not [i for i in report["errors"] if i["code"].startswith("template.")]


def test_register_missing_group_rejected(pkg, tmp_path):
    record = make_record()
    del record["F"]
    with pytest.raises(TemplateError) as exc:
        register_template(pkg["root"], _write_record(tmp_path, record))
    assert any("template.group_missing" in g for g in exc.value.gaps)


def test_register_non_numeric_limit_rejected(pkg, tmp_path):
    record = make_record()
    record["D"]["word_limit_abstract"] = "about 250 words"
    with pytest.raises(TemplateError) as exc:
        register_template(pkg["root"], _write_record(tmp_path, record))
    assert any("template.limit_not_numeric" in g for g in exc.value.gaps)


def test_register_empty_limits_rejected(pkg, tmp_path):
    record = make_record()
    record["D"] = {k: None for k in record["D"]}
    with pytest.raises(TemplateError) as exc:
        register_template(pkg["root"], _write_record(tmp_path, record))
    assert any("template.limits_empty" in g for g in exc.value.gaps)


def test_register_disclosure_without_positions_rejected(pkg, tmp_path):
    record = make_record()
    record["G"]["ai_policy"]["disclosure_positions"] = []
    with pytest.raises(TemplateError) as exc:
        register_template(pkg["root"], _write_record(tmp_path, record))
    assert any("template.ai_disclosure_positions" in g for g in exc.value.gaps)


def test_expired_record_registers_with_warning(pkg, tmp_path):
    record = make_record(verified_at="2025-01-01")
    result = register_template(pkg["root"], _write_record(tmp_path, record))
    assert any("过期" in w for w in result["warnings"])
    report = validate_package(pkg["root"])
    assert "template.expired" in {i["code"] for i in report["warnings"]}


def test_language_mismatch_rejected(pkg, tmp_path):
    record = make_record(language="zh")
    with pytest.raises(TemplateError):
        register_template(pkg["root"], _write_record(tmp_path, record))


def test_zh_record_registers_on_zh_manuscript(tmp_path, upstreams):
    from light_write.intake import run_intake
    from light_write.project import init_package

    root = tmp_path / "ms"
    init_package(root, "中文稿件", "zh")
    run_intake(root, upstreams["card"], upstreams["literature"])
    result = register_template(root, _write_record(tmp_path, make_record(language="zh")))
    assert result["journal_name"] == "Journal of Examples"


def test_record_snapshot_tamper_detected(pkg, record_path):
    register_template(pkg["root"], record_path)
    snap = pkg["root"] / "template_record.json"
    data = load_package(pkg["root"])["template_record"]
    data["A"]["journal_name"] = "Tampered Journal"
    dump_json(snap, data)
    report = validate_package(pkg["root"])
    assert "template.record_hash_drift" in {i["code"] for i in report["errors"]}
