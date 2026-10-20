"""全包校验（STALE/身份纪律兜底）+ 政策雷达 lite。"""

import yaml

from light_patent import check, draft, radar
from light_patent.project import case_path, load_case
from light_patent.util import dump_yaml, load_structured
from light_patent.validate import validate_package

from conftest import drive_to_drafted


def _checked(root, tmp_path):
    drive_to_drafted(root, tmp_path)
    draft.strip_filing(root)
    check.register_redteam(root, {
        "claims_team": {"checked": ["创造性"], "not_checked": [],
                        "findings": []},
        "package_team": {"checked": ["一致性"], "not_checked": [],
                         "findings": []}})
    check.run_check(root)
    return root


def test_validate_clean_case(case_root, tmp_path):
    _checked(case_root, tmp_path)
    result = validate_package(case_root)
    assert result["ok"], result["errors"]


def test_validate_detects_stale(case_root, tmp_path):
    _checked(case_root, tmp_path)
    spec = case_path(case_root, "specification_md")
    spec.write_text(spec.read_text(encoding="utf-8") + "\n改稿一句。\n",
                    encoding="utf-8")
    result = validate_package(case_root)
    assert any("STALE" in e for e in result["errors"])


def test_validate_blocks_sensitive_fields(case_root):
    case = load_case(case_root)
    case["parties"]["id_card"] = "不许落"
    dump_yaml(case_path(case_root, "case"), case)
    result = validate_package(case_root)
    assert any("敏感字段" in e for e in result["errors"])


def test_validate_blocks_non_natural_inventor(case_root):
    case = load_case(case_root)
    case["parties"]["inventors"] = [{"name": "火鸡课题组"}]
    dump_yaml(case_path(case_root, "case"), case)
    result = validate_package(case_root)
    assert any("自然人" in e for e in result["errors"])


def test_radar_seed_entries_are_grade_a():
    entries = radar.seed_if_missing()
    seeds = [e for e in entries if e["entry_id"].startswith("PR-2026-")]
    assert len(seeds) == 5
    assert all(e["source_grade"] == "A" for e in seeds)


def test_radar_add_entry_and_dup_reject(tmp_path, monkeypatch):
    monkeypatch.setattr(radar, "_RADAR_FILE", tmp_path / "radar.yaml")
    radar.seed_if_missing()
    entry = {"entry_id": "PR-2027-001", "title": "测试条目",
             "source_grade": "B", "source": "某律所解读",
             "effective": "2027-01-01", "summary": "s",
             "impact_disclosure": "d", "impact_drafting": "w"}
    radar.add_entry(entry)
    import pytest
    from light_patent.project import PatentError
    with pytest.raises(PatentError):
        radar.add_entry(entry)


def test_radar_brief_states_no_auto_change():
    brief = radar.render_brief()
    assert "不自动修改" in brief
    assert "6.1.1" in brief or "伦理审查" in brief
