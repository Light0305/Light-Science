"""状态机门：intake→outlined 全路径、合同硬门、contested 降级、Phase 2 占位门。"""

from pathlib import Path

from light_write.gates import advance, freeze_contract, status_summary
from light_write.project import load_package
from light_write.util import dump_yaml
from light_write.validate import validate_package
from conftest import add_assertions, full_pkg


def test_advance_without_intake_blocked(tmp_path):
    from light_write.project import init_package

    root = tmp_path / "ms"
    init_package(root, "Empty", "en")
    result = advance(root)
    assert result["advanced"] is False
    assert any("intake" in g for g in result["gaps"])


def test_advance_blocked_when_contract_unfrozen(pkg, record_path):
    from light_write.template_reg import register_template

    register_template(pkg["root"], record_path)
    result = advance(pkg["root"])
    assert result["advanced"] is False
    assert any("验收合同未冻结" in g for g in result["gaps"])


def test_full_path_to_outlined(pkg, record_path):
    full_pkg(pkg, record_path)
    result = advance(pkg["root"])
    assert result == {"advanced": True, "from": "intake", "to": "outlined", "gaps": []}
    ms = load_package(pkg["root"])["manuscript"]
    assert ms["status"] == "outlined"
    assert ms["contract_contested"] is False
    summary = status_summary(pkg["root"])
    assert summary["status"] == "outlined" and summary["claims"] == 2


def test_contested_contract_degrades_but_outlines(pkg, record_path):
    full_pkg(pkg, record_path, contested_ids=("A03",))
    result = advance(pkg["root"])
    assert result["advanced"] is True and result["to"] == "outlined"
    ms = load_package(pkg["root"])["manuscript"]
    assert ms["contract_contested"] is True
    assert "contested" in ms["submission_blocked_reason"]
    assert ms["acceptance_contract"]["status"] == "contested"


def test_advance_beyond_outlined_blocked_without_sections(pkg, record_path):
    # Phase 2 起 drafted 段门为真门：无逐节稿 → 按栏目序列逐项点名不许过
    full_pkg(pkg, record_path)
    advance(pkg["root"])
    result = advance(pkg["root"])
    assert result["advanced"] is False
    assert result["from"] == "outlined" and result["to"] == "drafted"
    assert any("栏目" in g for g in result["gaps"])


def test_frozen_contract_tamper_detected(pkg, record_path):
    full_pkg(pkg, record_path)
    contract = load_package(pkg["root"])["contract"]
    contract["assertions"][0]["text"] = "被静默改掉的断言"
    dump_yaml(pkg["root"] / "acceptance_contract.yaml", contract)
    report = validate_package(pkg["root"])
    assert "contract.frozen_hash_drift" in {i["code"] for i in report["errors"]}
    result = advance(pkg["root"])
    assert result["advanced"] is False


def test_freeze_requires_checkable_assertions(pkg):
    add_assertions(pkg["root"], n=3)
    result = freeze_contract(pkg["root"])
    assert result["status"] == "agreed" and result["assertions"] == 3
    # 条数不在 10–20 只警告不拒绝，validate 可见
    report = validate_package(pkg["root"])
    assert "contract.assertion_count" in {i["code"] for i in report["warnings"]}
