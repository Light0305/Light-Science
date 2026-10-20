"""提示词产物：六段结构、front matter 登记、正文无 hex、改版归档。"""

import re

import pytest

from light_figure.project import load_package, provenance_row
from light_figure.prompt import PromptError, build_prompt, parse_front_matter
from conftest import FIG_DATA, FIG_METHOD


def test_prompt_six_sections_and_front_matter(filled_pkg):
    outcome = build_prompt(filled_pkg["root"], FIG_METHOD)
    assert outcome["version"] == 3  # 取图库条目绑定的提示词版本
    text = (filled_pkg["root"] / "schematic" / "prompts" / "fig-method.md") \
        .read_text(encoding="utf-8")
    for heading in ("## 1 全局", "## 2 分区", "## 3 全局标注",
                    "## 4 风格规格", "## 5 负面约束", "## 6 政策段"):
        assert heading in text
    meta, body = parse_front_matter(text)
    assert meta["gallery"]["entry_id"] == "MG-FLOW-014"
    assert meta["gallery"]["bound_prompt_version"] == "3"
    assert meta["style_rules"]["id"] == "anchor-compact-flow"
    assert meta["role_palette"]["entry_id"] == "PAL-ROLE-METHOD"
    assert meta["policy_snapshot_ref"] == \
        "figure.yaml#ai_policy_snapshot"
    # 正文只引角色名、不落 hex（逐字面量红线）
    assert not re.search(r"#[0-9a-fA-F]{6}\b", body)
    assert "model_core" in body
    assert "policy_block 门按哈希机械执行" in body  # 政策段
    prov = load_package(filled_pkg["root"])["provenance"]
    row = provenance_row(prov, FIG_METHOD)
    assert row["prompt_version"] == "3"


def test_prompt_revision_archives_old_version(filled_pkg):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD)
    outcome = build_prompt(root, FIG_METHOD)
    assert outcome["version"] == 4
    archive = root / "schematic" / "prompts" / "archive" / \
        "fig-method.v3.md"
    assert archive.exists()
    assert outcome["archived"] == \
        "schematic/prompts/archive/fig-method.v3.md"


def test_prompt_rejects_metric_literals_in_labels(filled_pkg):
    from light_figure.project import load_package as lp, save_contract

    data = lp(filled_pkg["root"])
    contract = data["contracts"][FIG_METHOD]
    contract["panel_map"][0]["labels"] = ["箭头宽 12 pt"]
    save_contract(filled_pkg["root"], contract)
    with pytest.raises(PromptError) as exc:
        build_prompt(filled_pkg["root"], FIG_METHOD)
    assert any("度量字面量" in g for g in exc.value.gaps)


def test_prompt_data_line_rejected(filled_pkg):
    with pytest.raises(PromptError):
        build_prompt(filled_pkg["root"], FIG_DATA)
